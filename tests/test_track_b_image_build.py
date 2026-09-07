from __future__ import annotations

import importlib.util
import tarfile
from pathlib import Path

import pytest


def _builder():
    path = Path(__file__).resolve().parents[1] / "docker" / "track-b" / "build.py"
    spec = importlib.util.spec_from_file_location("track_b_image_builder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_image_context_excludes_task_data_credentials_and_caches(tmp_path):
    builder = _builder()
    paths = ["pyproject.toml", "event_taxonomy.json", "async_rbench/__init__.py",
             "async_rbench/track_b/adapter.py", "async_rbench/private.key",
             "async_rbench/__pycache__/adapter.pyc", "cases/task/private-truth.json",
             "artifacts/run/trace.jsonl", ".codex/auth.json", ".env"]
    paths += ["docker/track-b/" + name for name in builder.BUILD_FILES]
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    archive = tmp_path / "context.tar"
    builder.write_context(tmp_path, archive)
    with tarfile.open(archive) as context:
        names = set(context.getnames())
        assert "async_rbench/track_b/adapter.py" in names
        assert "event_taxonomy.json" in names
        assert not any(name.startswith(("cases/", "artifacts/", ".codex/")) for name in names)
        assert "async_rbench/private.key" not in names
        assert not any("__pycache__" in name for name in names)
        assert ".env" not in names
        assert all(not member.issym() and not member.islnk() for member in context.getmembers())


def test_image_context_rejects_linked_source(tmp_path):
    builder = _builder()
    package = tmp_path / "async_rbench"
    package.mkdir()
    outside = tmp_path / "secret.py"
    outside.write_text("private", encoding="utf-8")
    try:
        (package / "linked.py").symlink_to(outside)
    except OSError:
        pytest.skip("host does not permit symlink creation")
    with pytest.raises(ValueError, match="linked"):
        builder.context_files(tmp_path)
