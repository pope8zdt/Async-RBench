import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import fetch_osworld_assets as assets


class FakeRangeResponse:
    status_code = 206

    def __init__(self, body: bytes, content_range: str):
        self.body = body
        self.headers = {"content-range": content_range}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, _size):
        yield self.body


def test_range_download_rejects_oversize_before_writing(tmp_path, monkeypatch):
    destination = tmp_path / "asset.bin"
    destination.write_bytes(b"\0" * 4)
    downloader = assets.RangeDownloader(
        url="https://example.invalid/asset",
        destination=destination,
        expected_size=4,
        expected_sha256="0" * 64,
        workers=1,
        chunk_size=4,
    )
    monkeypatch.setattr(
        assets.requests,
        "get",
        lambda *_args, **_kwargs: FakeRangeResponse(b"abcde", "bytes 0-3/4"),
    )
    monkeypatch.setattr(assets.time, "sleep", lambda _seconds: None)
    with pytest.raises(RuntimeError, match="exceeded its declared length"):
        downloader._fetch_chunk(0)
    assert destination.read_bytes() == b"\0" * 4


def test_whole_hash_failure_clears_resume_state(tmp_path, monkeypatch):
    destination = tmp_path / "asset.bin"
    destination.write_bytes(b"data")
    local_digest = hashlib.sha256(b"data").hexdigest()
    downloader = assets.RangeDownloader(
        url="https://example.invalid/asset",
        destination=destination,
        expected_size=4,
        expected_sha256="0" * 64,
        workers=1,
        chunk_size=4,
    )
    downloader.state_path.write_text(
        json.dumps(
            {
                "url": downloader.url,
                "size": 4,
                "sha256": "0" * 64,
                "chunk_size": 4,
                "completed_chunks": {"0": local_digest},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(downloader, "_metadata", lambda: None)
    with pytest.raises(RuntimeError, match="resume state was cleared"):
        downloader.run()
    state = json.loads(downloader.state_path.read_text(encoding="utf-8"))
    assert state["completed_chunks"] == {}


def test_orphan_resume_state_does_not_read_missing_archive(tmp_path):
    destination = tmp_path / "missing.bin"
    downloader = assets.RangeDownloader(
        url="https://example.invalid/asset",
        destination=destination,
        expected_size=4,
        expected_sha256="0" * 64,
        workers=1,
        chunk_size=4,
    )
    downloader.state_path.write_text(
        json.dumps(
            {
                "url": downloader.url,
                "size": 4,
                "sha256": "0" * 64,
                "chunk_size": 4,
                "completed_chunks": {"0": "f" * 64},
            }
        ),
        encoding="utf-8",
    )
    assert downloader.verified_remaining_bytes() == 4


def test_failed_extraction_removes_partial_file(tmp_path, monkeypatch):
    archive = tmp_path / "asset.zip"
    output = tmp_path / "Ubuntu.qcow2"
    partial = output.with_suffix(output.suffix + ".partial")
    partial.write_bytes(b"stale")
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Ubuntu.qcow2", b"data")
    monkeypatch.setattr(assets, "QCOW2_SIZE", 4)
    monkeypatch.setattr(assets, "QCOW2_SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="SHA-256"):
        assets.extract_qcow2(archive, output)
    assert not partial.exists()
    assert not output.exists()


def test_docker_digest_is_tagged_to_upstream_latest(monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if "inspect" in command:
            return SimpleNamespace(stdout="sha256:verified\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(assets.subprocess, "run", fake_run)
    identity = assets.pull_docker_image()
    assert ["docker", "tag", assets.DOCKER_IMAGE_DIGEST, assets.DOCKER_IMAGE] in calls
    assert identity == {
        "digest_image_id": "sha256:verified",
        "upstream_latest_image_id": "sha256:verified",
    }


def test_official_qcow_digest_is_pinned():
    assert assets.QCOW2_SIZE == 24_460_197_888
    assert assets.QCOW2_SHA256 == (
        "6bf667a852b3c307f61d9f09c42559351f45e0607e428b4997becf534cf4d313"
    )
