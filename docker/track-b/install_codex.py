"""Install the exact published Linux amd64 Codex artifact after digest validation."""
from __future__ import annotations

import hashlib
import io
import platform
import tarfile
import urllib.request
from pathlib import Path

VERSION = "0.153.4"
ASSET = "codex-x86_64-unknown-linux-musl"
URL = f"https://github.com/openai/codex/releases/download/rust-v{VERSION}/{ASSET}.tar.gz"
SHA256 = "f479424eca092484dc40d87ae28c44f4cc40234a60045d6131e493800d814a30"


def main() -> None:
    if platform.machine() != "x86_64":
        raise RuntimeError("The pinned Codex artifact supports Linux amd64 only")
    with urllib.request.urlopen(URL, timeout=120) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != SHA256:
        raise RuntimeError("Codex release archive checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        members = [item for item in package if item.isfile() and Path(item.name).name == ASSET]
        if len(members) != 1:
            raise RuntimeError("Codex release must contain exactly one expected executable")
        source = package.extractfile(members[0])
        if source is None:
            raise RuntimeError("Codex executable is missing")
        target = Path("/opt/venv/bin/codex")
        target.write_bytes(source.read())
        target.chmod(0o555)


if __name__ == "__main__":
    main()
