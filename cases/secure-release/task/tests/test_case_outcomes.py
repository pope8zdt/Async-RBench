"""Frozen semantic checks for authority-driven secure release rebuilding."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import time
from pathlib import Path

import requests


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def _git(repo: str, *args: str) -> str:
    return _run("git", "-C", repo, *args).stdout.strip()


def _manifest() -> dict:
    return json.loads(Path("/app/release-manifest.json").read_text())


def _branch_source(branch: str) -> str:
    return _git("/app/repo", "show", f"{branch}:bottle.py")


def _load_bottle(source: str, label: str):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / f"bottle_{label}.py"
        path.write_text(source)
        spec = importlib.util.spec_from_file_location(f"dtb2_bottle_{label}", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module


def _assert_controls_rejected(source: str, label: str, controls: tuple[str, ...]) -> None:
    module = _load_bottle(source, label)
    for control in controls:
        for function, value in (
            (module._hkey, f"X{control}Header"),
            (module._hval, f"value{control}suffix"),
        ):
            try:
                function(value)
            except ValueError:
                pass
            else:
                raise AssertionError(f"{label} accepts control {control!r}")


def _wait_text(url: str, expected: str, timeout: float = 3.0) -> float:
    start = time.monotonic()
    last = ""
    while time.monotonic() - start <= timeout:
        try:
            last = requests.get(url, verify=False, timeout=.5).text.strip()
            if last == expected:
                return (time.monotonic() - start) * 1000
        except requests.RequestException:
            pass
        time.sleep(.05)
    raise AssertionError(f"{url} did not serve {expected!r}; last={last!r}")


def _push_parent_then_restore(branch: str, url: str) -> None:
    final_ref = _git("/app/repo", "rev-parse", branch)
    parent_ref = _git("/app/repo", "rev-parse", f"{branch}^")
    expected = _git("/app/repo", "show", f"{branch}:index.html")
    try:
        _git("/app/repo", "push", "-f", "/git/project.git", f"{parent_ref}:refs/heads/{branch}")
        start = time.monotonic()
        _git("/app/repo", "push", "-f", "/git/project.git", f"{final_ref}:refs/heads/{branch}")
        elapsed = _wait_text(url, expected)
        assert elapsed <= 3000
        assert (time.monotonic() - start) * 1000 <= 3000
    finally:
        _git("/app/repo", "push", "-f", "/git/project.git", f"{final_ref}:refs/heads/{branch}")


# authority_final_truth (4)
def test_authority_secret_recovered():
    assert Path("/app/secret.txt").read_text().strip() == "secret[lost_and_found_in_git]"


def test_authority_no_secret_in_any_object():
    object_ids = _git(
        "/app/repo", "cat-file", "--batch-all-objects", "--batch-check=%(objectname)"
    ).splitlines()
    assert object_ids
    for object_id in object_ids:
        payload = _run("git", "-C", "/app/repo", "cat-file", "-p", object_id).stdout
        assert "secret[" not in payload
    assert _run("git", "-C", "/app/repo", "fsck", "--full", "--no-reflogs").returncode == 0


def test_authority_final_main_baseline():
    assert _git("/app/repo", "show", "main:index.html") == "main branch content"
    log = _git("/app/repo", "log", "main", "--format=%s").splitlines()
    assert "chore: adopt post-sanitization main header baseline" in log


def test_authority_final_dev_baseline():
    assert _git("/app/repo", "show", "dev:index.html") == "dev branch content"
    log = _git("/app/repo", "log", "dev", "--format=%s").splitlines()
    assert "chore: adopt post-sanitization dev header baseline" in log


# stale_exclusion (4)
def test_stale_pre_rewrite_main_patch_rejected():
    main = _git("/app/repo", "rev-parse", "main")
    baseline = _git("/app/repo", "log", "main", "--grep=post-sanitization main", "-1", "--format=%H")
    assert baseline and main != baseline
    assert _run("git", "-C", "/app/repo", "merge-base", "--is-ancestor", baseline, main).returncode == 0
    _assert_controls_rejected(_branch_source("main"), "fresh_main", ("\n", "\r", "\0"))


def test_stale_pre_rewrite_dev_patch_rejected():
    dev = _git("/app/repo", "rev-parse", "dev")
    baseline = _git("/app/repo", "log", "dev", "--grep=post-sanitization dev", "-1", "--format=%H")
    assert baseline and dev != baseline
    assert _run("git", "-C", "/app/repo", "merge-base", "--is-ancestor", baseline, dev).returncode == 0
    _assert_controls_rejected(_branch_source("dev"), "fresh_dev", ("\n", "\r", "\0"))


def test_stale_old_deployment_rejected():
    assert _git("/git/project.git", "rev-parse", "refs/heads/main") == _git("/app/repo", "rev-parse", "main")
    assert _git("/git/project.git", "rev-parse", "refs/heads/dev") == _git("/app/repo", "rev-parse", "dev")


def test_stale_old_manifest_rejected():
    manifest = _manifest()
    assert manifest["security_revision"] == _git("/app/repo", "rev-parse", "main")
    assert manifest["deployed_main"] == _git("/git/project.git", "rev-parse", "refs/heads/main")
    assert manifest["deployed_dev"] == _git("/git/project.git", "rev-parse", "refs/heads/dev")


# downstream_rebuild (5)
def test_downstream_main_header_controls():
    _assert_controls_rejected(_branch_source("main"), "main_controls", ("\n", "\r", "\0"))


def test_downstream_dev_header_controls():
    _assert_controls_rejected(_branch_source("dev"), "dev_controls", ("\n", "\r", "\0"))


def test_downstream_valid_header_regression():
    for branch in ("main", "dev"):
        module = _load_bottle(_branch_source(branch), f"valid_{branch}")
        assert module._hkey("x_custom-header") == "X-Custom-Header"
        assert module._hval("value with spaces") == "value with spaces"


def test_downstream_report_cwe93_exact():
    reports = [json.loads(line) for line in Path("/app/report.jsonl").read_text().splitlines() if line.strip()]
    matches = [
        item for item in reports
        if item.get("file_path") == "/app/bottle.py"
        and "cwe-93" in {str(value).lower() for value in item.get("cwe_id", [])}
    ]
    assert matches


def test_downstream_remote_final_refs():
    assert _git("/git/project.git", "show", "main:index.html") == _git("/app/repo", "show", "main:index.html")
    assert _git("/git/project.git", "show", "dev:index.html") == _git("/app/repo", "show", "dev:index.html")


# runtime_behavior (4)
def test_runtime_https_main():
    expected = _git("/app/repo", "show", "main:index.html")
    response = requests.get("https://127.0.0.1:8443/index.html", verify=False, timeout=3)
    assert response.status_code == 200 and response.text.strip() == expected


def test_runtime_https_dev():
    expected = _git("/app/repo", "show", "dev:index.html")
    response = requests.get("https://127.0.0.1:8443/dev/index.html", verify=False, timeout=3)
    assert response.status_code == 200 and response.text.strip() == expected


def test_runtime_push_deploy_main():
    _push_parent_then_restore("main", "https://127.0.0.1:8443/index.html")


def test_runtime_push_deploy_dev():
    _push_parent_then_restore("dev", "https://127.0.0.1:8443/dev/index.html")


# lineage_reverification (4)
def test_lineage_manifest_schema():
    assert set(_manifest()) == {"sanitized_head", "security_revision", "deployed_main", "deployed_dev"}


def test_lineage_sanitized_head_reachable():
    manifest = _manifest()
    assert _run(
        "git", "-C", "/app/repo", "merge-base", "--is-ancestor",
        manifest["sanitized_head"], _git("/app/repo", "rev-parse", "main"), check=False,
    ).returncode == 0
    assert _run("git", "-C", "/app/repo", "cat-file", "-e", f"{manifest['sanitized_head']}^{{commit}}", check=False).returncode == 0


def test_lineage_security_revision_final():
    manifest = _manifest()
    assert manifest["security_revision"] == _git("/app/repo", "rev-parse", "main")
    _assert_controls_rejected(_git("/app/repo", "show", f"{manifest['security_revision']}:bottle.py"), "manifest_security", ("\n", "\r", "\0"))


def test_lineage_deployed_ref_consistency():
    manifest = _manifest()
    assert manifest["deployed_main"] == _git("/app/repo", "rev-parse", "main")
    assert manifest["deployed_dev"] == _git("/app/repo", "rev-parse", "dev")
    assert manifest["deployed_main"] == _git("/git/project.git", "rev-parse", "refs/heads/main")
    assert manifest["deployed_dev"] == _git("/git/project.git", "rev-parse", "refs/heads/dev")


# independent_preservation (3)
def test_support_nginx_content_and_404():
    index = requests.get("http://127.0.0.1:8080/", timeout=3)
    missing = requests.get("http://127.0.0.1:8080/dtb2-hidden-missing", timeout=3)
    assert (index.status_code, index.text.strip()) == (200, "Welcome to the benchmark webserver")
    assert (missing.status_code, missing.text.strip()) == (404, "Page not found - Please check your URL")


def test_support_nginx_logs():
    marker = f"dtb2-log-{time.time_ns()}"
    requests.get("http://127.0.0.1:8080/", headers={"User-Agent": marker}, timeout=3)
    access = Path("/var/log/nginx/benchmark-access.log")
    error = Path("/var/log/nginx/benchmark-error.log")
    assert access.is_file() and error.is_file()
    deadline = time.monotonic() + 2
    while marker not in access.read_text(errors="replace") and time.monotonic() < deadline:
        time.sleep(.05)
    line = next(line for line in access.read_text(errors="replace").splitlines() if marker in line)
    assert "GET" in line and "200" in line and f'"{marker}"' in line


def test_support_nginx_rate_limit_config():
    main = Path("/etc/nginx/nginx.conf").read_text()
    site = Path("/etc/nginx/conf.d/benchmark-site.conf").read_text()
    assert "limit_req_zone" in main and "10m" in main and "rate=10r/s" in main
    assert "$time_local" in main and "$request_method" in main and "$status" in main
    assert '"$http_user_agent"' in main
    assert "limit_req" in site and "burst=10" in site
    assert "/var/log/nginx/benchmark-access.log" in site
    assert "/var/log/nginx/benchmark-error.log" in site
    assert _run("nginx", "-t", check=False).returncode == 0

