from __future__ import annotations

import json
from pathlib import Path

import pytest

from async_rbench.track_b.config import TrackBConfig


def load(tmp_path: Path, runtime: dict) -> TrackBConfig:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "track": "B", "framework": "deterministic", "model": "fixture",
        "runtime": runtime,
    }), encoding="utf-8")
    return TrackBConfig.from_file(path)


def test_runtime_configuration_binds_image_and_limits(tmp_path):
    first = load(tmp_path, {"type": "docker", "image": "example:test", "cpus": 0.5})
    second = load(tmp_path, {"type": "docker", "image": "example:test", "cpus": 1})
    assert first.public_metadata()["runtime"]["image"] == "example:test"
    assert first.public_metadata()["config_sha256"] != second.public_metadata()["config_sha256"]


@pytest.mark.parametrize("runtime", [False, 0, [], "", None])
def test_malformed_runtime_never_silently_falls_back_to_host(tmp_path, runtime):
    with pytest.raises(ValueError, match="runtime"):
        load(tmp_path, runtime)


@pytest.mark.parametrize("runtime", [
    {"type": "docker"}, {"type": "docker", "image": "--privileged"},
    {"type": "docker", "image": "ok", "mounts": ["/"]},
    {"type": "docker", "image": "ok", "cpus": 0},
    {"type": "docker", "image": "ok", "cpus": True},
    {"type": "docker", "image": "ok", "memory": "unlimited"},
    {"type": "docker", "image": "ok", "timeout_sec": -1},
    {"type": "host", "image": "ok"},
])
def test_runtime_rejects_unsafe_or_invalid_settings(tmp_path, runtime):
    with pytest.raises(ValueError, match="runtime"):
        load(tmp_path, runtime)


def test_existing_host_config_digest_is_preserved():
    import hashlib
    payload = {"track": "B", "framework": "deterministic", "model": "fixture",
               "credential_env": "", "components": {}, "limits": {}, "framework_options": {}}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert TrackBConfig(track="B", framework="deterministic", model="fixture").public_metadata() == {
        **payload, "config_sha256": digest,
    }


def test_codex_preserves_container_shell_without_provider_override(monkeypatch):
    from async_rbench.track_b.frameworks.codex_cli import child_environment
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unselected.example")
    environment = child_environment()
    assert environment.get("SHELL") == "/bin/bash"
    assert "OPENAI_BASE_URL" not in environment


def test_container_command_has_no_host_mounts_or_credentials(tmp_path):
    from async_rbench.track_b.container_runtime import build_docker_command
    config = load(tmp_path, {"type": "docker", "image": "example:test", "cpus": 0.5})
    command = build_docker_command(config, image_id="sha256:" + "a" * 64, name="track-b-agent-abc")
    assert command[1:3] == ["run", "--rm"]
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--user=1000:1000" in command
    assert "--cpus=0.5" in command
    assert "--privileged" not in command
    assert not any(part in {"-v", "--volume", "--mount"} for part in command)
    assert not any("docker.sock" in part for part in command)
    assert "sha256:" + "a" * 64 in command
    assert command[-2:] == ["-m", "async_rbench.track_b.container_entry"]


def test_bootstrap_uses_only_selected_credentials(tmp_path, monkeypatch):
    from async_rbench.track_b.container_runtime import make_bootstrap
    monkeypatch.setenv("BENCH_PROVIDER_KEY", "private-selected-value")
    monkeypatch.setenv("UNRELATED_SECRET", "do-not-forward")
    config = TrackBConfig(track="B", framework="openai-agents", model="fixture",
                          credential_env="BENCH_PROVIDER_KEY",
                          runtime={"type": "docker", "image": "example:test"})
    bootstrap = make_bootstrap(config, [], image_id="sha256:" + "a" * 64)
    assert bootstrap["environment"] == {"BENCH_PROVIDER_KEY": "private-selected-value"}
    assert "do-not-forward" not in json.dumps(bootstrap)
    assert "private-selected-value" not in json.dumps(config.public_metadata())
    assert "codex_auth" not in bootstrap


@pytest.mark.parametrize("name", ["PATH", "PYTHONPATH", "LD_PRELOAD", "HOME", "ASYNC_RBENCH_AGENT_CONTAINER"])
def test_bootstrap_rejects_control_variables_as_credentials(tmp_path, name):
    from async_rbench.track_b.container_runtime import make_bootstrap
    config = TrackBConfig(track="B", framework="openai-agents", model="fixture",
                          credential_env=name, runtime={"type": "docker", "image": "example:test"})
    with pytest.raises(ValueError, match="credential"):
        make_bootstrap(config, [], image_id="sha256:" + "a" * 64)


def test_image_inspection_rejects_nonlinux(monkeypatch):
    from async_rbench.track_b import container_runtime
    monkeypatch.setattr(container_runtime, "docker_json", lambda *args: [{"Id": "sha256:" + "a" * 64, "Os": "windows"}])
    with pytest.raises(ValueError, match="Linux"):
        container_runtime.inspect_image("example:test")


def test_run_pins_one_runtime_image_for_all_paired_episodes(tmp_path, monkeypatch):
    from async_rbench.track_b import cli
    from async_rbench.track_b import container_runtime
    config = load(tmp_path, {"type": "docker", "image": "example:moving"})
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"episodes": []}', encoding="utf-8")
    captured = []
    monkeypatch.setattr(container_runtime, "inspect_image", lambda _: {"image_id": "sha256:" + "b" * 64, "os": "linux"})
    monkeypatch.setattr(cli, "run_eval_cli", lambda argv: captured.extend(argv) or 0)
    assert cli.main(["run", "--config", str(config.source_path), "--manifest", str(manifest),
                     "--output", str(tmp_path / "run")]) == 0
    selected = TrackBConfig.from_file(Path(captured[captured.index("--config") + 1]))
    assert selected.runtime["image"] == "sha256:" + "b" * 64
    assert TrackBConfig.from_file(config.source_path).runtime["image"] == "example:moving"


def test_container_doctor_does_not_import_evaluator_cli(tmp_path):
    import subprocess
    import sys
    script = '''
import importlib.abc, sys
class WithoutEvaluator(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname == "async_rbench.eval_cli":
            raise ImportError("evaluator unavailable inside participant image")
sys.meta_path.insert(0, WithoutEvaluator())
from async_rbench.track_b.cli import main
raise SystemExit(main(["doctor", "--config", sys.argv[1]]))
'''
    path = tmp_path / "host.json"
    path.write_text('{"track":"B","framework":"deterministic","model":"fixture"}', encoding="utf-8")
    result = subprocess.run([sys.executable, "-c", script, str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ready"] is True


def test_conformance_routes_through_the_same_container_bootstrap(tmp_path, monkeypatch):
    from async_rbench.track_b import adapter, container_runtime
    from async_rbench.track_b.container_entry import _validate_bootstrap
    config = load(tmp_path, {"type": "docker", "image": "example:test"})
    monkeypatch.delenv("ASYNC_RBENCH_AGENT_CONTAINER", raising=False)
    def launch(selected, args):
        _validate_bootstrap(container_runtime.make_bootstrap(selected, args, image_id="sha256:" + "a" * 64))
        assert "--conformance" in args
        return 17
    monkeypatch.setattr(container_runtime, "run_container_adapter", launch)
    assert adapter.main(["--config", str(config.source_path), "--conformance", "--workspace-mode", "disabled"]) == 17


def test_host_transport_exits_when_worker_finishes_with_input_still_open():
    import subprocess
    import sys
    script = '''
import asyncio, sys
from async_rbench.track_b import container_runtime as runtime
from async_rbench.track_b.config import TrackBConfig
runtime.inspect_image = lambda image: {"image_id": "sha256:" + "a" * 64, "os":"linux"}
runtime.build_docker_command = lambda *a, **k: [sys.executable, "-u", "-c", "import sys; sys.stdin.buffer.readline(); print('worker-finished', flush=True)"]
runtime.remove_owned_container = lambda name: None
config = TrackBConfig(track="B",framework="deterministic",model="fixture",runtime={"type":"docker","image":"fixture","timeout_sec":15})
raise SystemExit(runtime.run_container_adapter(config, []))
'''
    process = subprocess.Popen([sys.executable, "-u", "-c", script], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert process.wait(timeout=25) == 0
        assert process.stdout.read().splitlines() == [b"worker-finished"]
        assert b"Fatal Python error" not in process.stderr.read()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdin.close()
