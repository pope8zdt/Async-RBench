from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from scripts import initialize_marble_collection as collection
from scripts import probe_marble_native_collection as probe


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module", (collection, probe))
def test_atomic_json_keeps_previous_document_when_replace_fails(
    tmp_path, monkeypatch, module
):
    target = tmp_path / "evidence.json"
    target.write_text('{"generation":"previous"}\n', encoding="utf-8")
    fsync_calls = []
    real_fsync = module.os.fsync

    def recording_fsync(fd):
        fsync_calls.append(fd)
        return real_fsync(fd)

    def interrupted_replace(_source, _target):
        raise OSError("simulated interruption before atomic replace")

    monkeypatch.setattr(module.os, "fsync", recording_fsync)
    monkeypatch.setattr(module.os, "replace", interrupted_replace)

    with pytest.raises(OSError, match="simulated interruption"):
        module.atomic_json(target, {"generation": "new"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"generation": "previous"}
    assert fsync_calls
    assert list(tmp_path.glob(".evidence.json.*.tmp")) == []


@pytest.mark.parametrize("module", (collection, probe))
def test_atomic_json_uses_unique_temps_for_concurrent_writers(
    tmp_path, monkeypatch, module
):
    target = tmp_path / "evidence.json"
    barrier = threading.Barrier(2)
    sources = []
    synchronized_sources = set()
    sources_guard = threading.Lock()
    errors = []
    real_replace = module.os.replace

    def synchronized_replace(source, destination):
        source_name = Path(source).name
        with sources_guard:
            sources.append(source_name)
            first_attempt = source_name not in synchronized_sources
            synchronized_sources.add(source_name)
        if first_attempt:
            barrier.wait(timeout=10)
        return real_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", synchronized_replace)

    def writer(generation):
        try:
            module.atomic_json(target, {"generation": generation})
        except Exception as exc:  # pragma: no cover - assertion reports details
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(value,)) for value in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert len(set(sources)) == 2
    assert json.loads(target.read_text(encoding="utf-8"))["generation"] in {1, 2}
    assert list(tmp_path.glob(".evidence.json.*.tmp")) == []


def _lock_probe(lock_path: Path) -> subprocess.CompletedProcess[str]:
    code = """
from pathlib import Path
import sys
from scripts.initialize_marble_collection import (
    BatchOutputLockUnavailable,
    exclusive_batch_output_lock,
)

try:
    with exclusive_batch_output_lock(Path(sys.argv[1])):
        print("acquired")
except BatchOutputLockUnavailable:
    print("locked")
    raise SystemExit(23)
"""
    return subprocess.run(
        [sys.executable, "-c", code, str(lock_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_batch_output_lock_rejects_a_second_process_and_releases(tmp_path):
    lock_path = tmp_path / "batch" / ".batch.lock"

    with collection.exclusive_batch_output_lock(lock_path):
        rejected = _lock_probe(lock_path)

    acquired = _lock_probe(lock_path)
    assert rejected.returncode == 23
    assert rejected.stdout.strip() == "locked"
    assert acquired.returncode == 0
    assert acquired.stdout.strip() == "acquired"


def test_collection_cli_rejects_locked_output_before_writing_report(tmp_path):
    batch_root = tmp_path / "batch"
    lock_path = batch_root / ".batch.lock"

    with collection.exclusive_batch_output_lock(lock_path):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/initialize_marble_collection.py"),
                "--output",
                str(batch_root),
                "--limit",
                "0",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    assert completed.returncode == 2
    assert json.loads(completed.stdout)["status"] == ("marble_collection_output_locked")
    assert not (batch_root / "batch_report.json").exists()
