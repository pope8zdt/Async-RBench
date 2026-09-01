"""Fetch and attest the official OSWorld Docker runtime assets.

The upstream downloader is single-stream and keeps both the 11 GiB archive
and 23 GiB image.  This bootstrapper is resumable, downloads byte ranges into
one sparse file, verifies the Hub object digest, extracts through a temporary
file, and removes the archive only after the qcow2 size is verified.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

import requests
from filelock import FileLock


ROOT = Path(__file__).resolve().parents[1]
ASSET_URL = (
    "https://huggingface.co/datasets/xlangai/ubuntu_osworld/resolve/main/"
    "Ubuntu.qcow2.zip"
)
ARCHIVE_NAME = "Ubuntu.qcow2.zip"
QCOW2_NAME = "Ubuntu.qcow2"
ARCHIVE_SIZE = 12_273_896_463
# The Hub/Xet ETag is a CAS identity, not the SHA-256 of the reconstructed ZIP.
ARCHIVE_REMOTE_ETAG = "6fce6ba39479eb03c94de90b3a568636cee287b8a5973effdd816fc976f01c57"
ARCHIVE_SHA256 = "b795b6cd4c69b252c1b4f10150a347795555032501b60fd031751ed09b896712"
QCOW2_SIZE = 24_460_197_888
QCOW2_SHA256 = "6bf667a852b3c307f61d9f09c42559351f45e0607e428b4997becf534cf4d313"
DOCKER_IMAGE = "happysixd/osworld-docker:latest"
DOCKER_IMAGE_DIGEST = (
    "happysixd/osworld-docker@"
    "sha256:0e6497a9295647cf05bf2b2af522fdd79bdeba2737595259cab310a3bcf6baa9"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


class RangeDownloader:
    def __init__(
        self,
        *,
        url: str,
        destination: Path,
        expected_size: int,
        expected_sha256: str,
        workers: int,
        chunk_size: int,
    ) -> None:
        self.url = url
        self.destination = destination
        self.expected_size = expected_size
        self.expected_sha256 = expected_sha256
        self.workers = workers
        self.chunk_size = chunk_size
        self.state_path = destination.with_suffix(destination.suffix + ".download.json")
        self._lock = threading.Lock()
        self._completed: dict[int, str] = {}
        self._resolved_url = url

    def _metadata(self) -> None:
        response = requests.head(self.url, allow_redirects=True, timeout=(20, 60))
        response.raise_for_status()
        size = int(response.headers.get("content-length", "0"))
        etag = response.headers.get("etag", "").strip('"').lower()
        if size != self.expected_size:
            raise RuntimeError(
                f"OSWorld archive size changed: expected {self.expected_size}, got {size}"
            )
        if etag != ARCHIVE_REMOTE_ETAG:
            raise RuntimeError(
                f"OSWorld archive remote identity changed: expected {ARCHIVE_REMOTE_ETAG}, got {etag}"
            )
        if response.headers.get("accept-ranges", "").lower() != "bytes":
            raise RuntimeError("OSWorld asset server does not advertise byte ranges")
        self._resolved_url = str(response.url)

    def _load_state(self) -> None:
        if not self.state_path.is_file():
            return
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        identity = (
            state.get("url"),
            state.get("size"),
            state.get("sha256"),
            state.get("chunk_size"),
        )
        expected = (self.url, self.expected_size, self.expected_sha256, self.chunk_size)
        if identity != expected:
            raise RuntimeError(
                f"resume metadata does not match requested OSWorld asset: {self.state_path}"
            )
        if not self.destination.is_file() or self.destination.stat().st_size != self.expected_size:
            self._completed = {}
            return
        completed = state.get("completed_chunks") or {}
        # Old list-only state cannot prove that a completed range stayed intact;
        # fail safe by downloading those ranges again.
        if isinstance(completed, dict):
            self._completed = {int(index): str(digest) for index, digest in completed.items()}
        else:
            self._completed = {}
        for index, expected_digest in list(self._completed.items()):
            if self._local_chunk_sha256(index) != expected_digest:
                del self._completed[index]

    def _local_chunk_sha256(self, index: int) -> str:
        start = index * self.chunk_size
        length = min(self.chunk_size, self.expected_size - start)
        digest = hashlib.sha256()
        with self.destination.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining:
                block = handle.read(min(8 * 1024 * 1024, remaining))
                if not block:
                    raise RuntimeError(f"partial archive ended inside chunk {index}")
                digest.update(block)
                remaining -= len(block)
        return digest.hexdigest()

    def _persist_state(self) -> None:
        _write_json_atomic(
            self.state_path,
            {
                "url": self.url,
                "size": self.expected_size,
                "sha256": self.expected_sha256,
                "chunk_size": self.chunk_size,
                "completed_chunks": {
                    str(index): digest for index, digest in sorted(self._completed.items())
                },
            },
        )

    def _fetch_chunk(self, index: int) -> int:
        start = index * self.chunk_size
        end = min(start + self.chunk_size, self.expected_size) - 1
        expected_length = end - start + 1
        last_error: Exception | None = None
        for attempt in range(1, 7):
            try:
                with requests.get(
                    self._resolved_url,
                    headers={"Range": f"bytes={start}-{end}"},
                    stream=True,
                    timeout=(30, 120),
                ) as response:
                    if response.status_code != 206:
                        raise RuntimeError(
                            f"range {start}-{end} returned HTTP {response.status_code}"
                        )
                    content_range = response.headers.get("content-range", "")
                    if content_range != f"bytes {start}-{end}/{self.expected_size}":
                        raise RuntimeError(f"unexpected Content-Range: {content_range}")
                    written = 0
                    chunk_digest = hashlib.sha256()
                    with self.destination.open("r+b", buffering=0) as output:
                        output.seek(start)
                        for block in response.iter_content(1024 * 1024):
                            if block:
                                remaining = expected_length - written
                                if len(block) > remaining:
                                    raise RuntimeError(
                                        f"range {start}-{end} exceeded its declared length"
                                    )
                                output.write(block)
                                chunk_digest.update(block)
                                written += len(block)
                    if written != expected_length:
                        raise RuntimeError(
                            f"range {start}-{end} wrote {written}, expected {expected_length}"
                        )
                with self._lock:
                    self._completed[index] = chunk_digest.hexdigest()
                    self._persist_state()
                    print(
                        json.dumps(
                            {
                                "downloaded_chunks": len(self._completed),
                                "total_chunks": self.total_chunks,
                                "downloaded_bytes": min(
                                    len(self._completed) * self.chunk_size,
                                    self.expected_size,
                                ),
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                return index
            except Exception as exc:  # network retry boundary
                last_error = exc
                if attempt < 6:
                    time.sleep(min(2**attempt, 20))
        raise RuntimeError(f"range {start}-{end} failed after retries: {last_error}")

    @property
    def total_chunks(self) -> int:
        return (self.expected_size + self.chunk_size - 1) // self.chunk_size

    def verified_remaining_bytes(self) -> int:
        """Return remaining transfer bytes after re-hashing every resume chunk."""

        if (
            self.destination.is_file()
            and self.destination.stat().st_size == self.expected_size
            and sha256_file(self.destination) == self.expected_sha256
        ):
            self._completed = {}
            return 0
        self._load_state()
        completed_bytes = sum(
            min(self.chunk_size, self.expected_size - index * self.chunk_size)
            for index in self._completed
        )
        return self.expected_size - completed_bytes

    def run(self) -> Path:
        if self.destination.is_file() and self.destination.stat().st_size == self.expected_size:
            digest = sha256_file(self.destination)
            if digest == self.expected_sha256:
                return self.destination
        self._metadata()
        self._load_state()
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        if not self.destination.exists():
            with self.destination.open("wb") as output:
                output.truncate(self.expected_size)
        elif self.destination.stat().st_size != self.expected_size:
            raise RuntimeError(
                f"partial archive has unexpected size: {self.destination.stat().st_size}"
            )
        self._persist_state()
        pending = [index for index in range(self.total_chunks) if index not in self._completed]
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = [executor.submit(self._fetch_chunk, index) for index in pending]
            for future in concurrent.futures.as_completed(futures):
                future.result()
        digest = sha256_file(self.destination)
        if digest != self.expected_sha256:
            self._completed.clear()
            self._persist_state()
            raise RuntimeError(
                "OSWorld archive SHA-256 mismatch; resume state was cleared so the next run "
                f"will re-fetch every range (expected {self.expected_sha256}, got {digest})"
            )
        return self.destination


def extract_qcow2(archive: Path, output: Path) -> Path:
    if output.is_file():
        if output.stat().st_size == QCOW2_SIZE and sha256_file(output) == QCOW2_SHA256:
            return output
        raise RuntimeError(f"existing OSWorld qcow2 failed attestation: {output}")
    temporary = output.with_suffix(output.suffix + ".partial")
    if temporary.exists():
        temporary.unlink()
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos = [info for info in bundle.infolist() if Path(info.filename).name == QCOW2_NAME]
            if len(infos) != 1 or infos[0].file_size != QCOW2_SIZE:
                raise RuntimeError("OSWorld archive does not contain the attested Ubuntu.qcow2")
            digest = hashlib.sha256()
            with bundle.open(infos[0]) as source, temporary.open("wb") as destination:
                while block := source.read(8 * 1024 * 1024):
                    destination.write(block)
                    digest.update(block)
        if temporary.stat().st_size != QCOW2_SIZE:
            raise RuntimeError("extracted OSWorld qcow2 has an unexpected size")
        if digest.hexdigest() != QCOW2_SHA256:
            raise RuntimeError("extracted OSWorld qcow2 failed SHA-256 attestation")
        os.replace(temporary, output)
    except Exception:
        if temporary.is_file():
            temporary.unlink()
        raise
    return output


def pull_docker_image() -> dict[str, Any]:
    subprocess.run(["docker", "pull", DOCKER_IMAGE_DIGEST], check=True)
    # Upstream provider.py launches the mutable `:latest` name.  Point that
    # exact name at the verified digest and prove both references resolve to
    # the same local image ID.
    subprocess.run(["docker", "tag", DOCKER_IMAGE_DIGEST, DOCKER_IMAGE], check=True)

    def inspect(reference: str) -> str:
        completed = subprocess.run(
            ["docker", "image", "inspect", reference, "--format", "{{.Id}}"],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    digest_id = inspect(DOCKER_IMAGE_DIGEST)
    latest_id = inspect(DOCKER_IMAGE)
    if not digest_id.startswith("sha256:") or latest_id != digest_id:
        raise RuntimeError("Docker did not return an immutable OSWorld image ID")
    return {"digest_image_id": digest_id, "upstream_latest_image_id": latest_id}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="artifacts/native-runtime-v4/osworld-assets",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--chunk-size-mib", type=int, default=64)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-docker-pull", action="store_true")
    parser.add_argument("--keep-archive", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 32:
        parser.error("--workers must be between 1 and 32")
    if not 8 <= args.chunk_size_mib <= 512:
        parser.error("--chunk-size-mib must be between 8 and 512")

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = (ROOT / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / ARCHIVE_NAME
    qcow2 = output_dir / QCOW2_NAME

    lock_path = output_dir / ".fetch_osworld_assets.lock"
    with FileLock(str(lock_path), timeout=1):
        if not args.skip_download:
            stale_partial = qcow2.with_suffix(qcow2.suffix + ".partial")
            if stale_partial.is_file():
                stale_partial.unlink()
            if qcow2.is_file():
                if qcow2.stat().st_size != QCOW2_SIZE or sha256_file(qcow2) != QCOW2_SHA256:
                    raise RuntimeError(f"existing OSWorld qcow2 failed attestation: {qcow2}")
            else:
                downloader = RangeDownloader(
                    url=ASSET_URL,
                    destination=archive,
                    expected_size=ARCHIVE_SIZE,
                    expected_sha256=ARCHIVE_SHA256,
                    workers=args.workers,
                    chunk_size=args.chunk_size_mib * 1024 * 1024,
                )
                archive_remaining = downloader.verified_remaining_bytes()
                required = archive_remaining + QCOW2_SIZE + 2 * 1024**3
                available = shutil.disk_usage(output_dir).free
                if available < required:
                    raise RuntimeError(
                        "insufficient free space for verified OSWorld download/extraction: "
                        f"need {required} bytes including safety margin, have {available}"
                    )
                downloader.run()
                extract_qcow2(archive, qcow2)
        elif (
            not qcow2.is_file()
            or qcow2.stat().st_size != QCOW2_SIZE
            or sha256_file(qcow2) != QCOW2_SHA256
        ):
            raise RuntimeError("--skip-download requires the SHA-256-attested Ubuntu.qcow2")

        docker_identity = None if args.skip_docker_pull else pull_docker_image()
        qcow2_stat = qcow2.stat()
        evidence = {
            "schema_version": "osworld-official-assets-v1",
            "source_url": ASSET_URL,
            "archive_remote_etag": ARCHIVE_REMOTE_ETAG,
            "archive_sha256": ARCHIVE_SHA256,
            "archive_size": ARCHIVE_SIZE,
            "qcow2_path": str(qcow2),
            "qcow2_size": qcow2_stat.st_size,
            "qcow2_sha256": QCOW2_SHA256,
            "qcow2_mtime_ns": qcow2_stat.st_mtime_ns,
            "qcow2_sha256_verified": True,
            "docker_image": DOCKER_IMAGE_DIGEST,
            "docker_identity": docker_identity,
            "assets_ready": (
                qcow2_stat.st_size == QCOW2_SIZE
                and bool(docker_identity)
                and docker_identity["digest_image_id"]
                == docker_identity["upstream_latest_image_id"]
            ),
        }
        _write_json_atomic(output_dir / "asset_attestation.json", evidence)
        if not args.keep_archive and archive.is_file():
            archive.unlink()
            state_path = archive.with_suffix(archive.suffix + ".download.json")
            if state_path.is_file():
                state_path.unlink()
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
