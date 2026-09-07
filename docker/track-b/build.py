"""Build sequential Track B images from a source-only, symlink-free tar allowlist."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path

TARGETS = ("codex", "claude", "langgraph", "openai")
BUILD_FILES = (
    "Dockerfile", "install_codex.py", "runtime_manifest.py", "requirements-base.lock",
    *(f"requirements-{name}.lock" for name in TARGETS),
)


def _is_linked(path: Path) -> bool:
    metadata = path.lstat()
    # Path.is_junction() is unavailable on supported Python 3.9-3.11 hosts.
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & 0x400  # FILE_ATTRIBUTE_REPARSE_POINT
    )


def context_files(root: Path) -> list[Path]:
    """Only Python package source, pyproject and explicitly named build inputs."""
    root = root.resolve(strict=True)
    package = root / "async_rbench"
    # Public protocol taxonomy is required by the unchanged v11 contract loader.
    paths = [root / "pyproject.toml", root / "event_taxonomy.json"]
    paths.extend(root / "docker" / "track-b" / name for name in BUILD_FILES)
    for current, directories, filenames in os.walk(package, followlinks=False):
        directories[:] = sorted(name for name in directories if name != "__pycache__")
        for name in [*directories, *filenames]:
            candidate = Path(current) / name
            if _is_linked(candidate):
                raise ValueError(f"build context cannot include linked paths: {candidate.relative_to(root)}")
        paths.extend(Path(current) / name for name in sorted(filenames) if name.endswith(".py"))
    for path in paths:
        for parent in [path, *path.parents]:
            if parent == root:
                break
            if _is_linked(parent):
                raise ValueError("build context cannot include linked paths")
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError("build context input must be a regular file inside the project")
    if not any(path.parent == package for path in paths):
        raise ValueError("Python package source is missing")
    return sorted(paths)


def write_context(root: Path, target: Path) -> dict[str, object]:
    files = context_files(root)
    manifest = {}
    with tarfile.open(target, "w", format=tarfile.PAX_FORMAT) as context:
        for path in files:
            name = path.relative_to(root).as_posix()
            content = path.read_bytes()
            manifest[name] = hashlib.sha256(content).hexdigest()
            info = context.gettarinfo(str(path), arcname=name)
            info.size = len(content)
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            context.addfile(info, io.BytesIO(content))
    return {
        "file_count": len(files), "bytes": target.stat().st_size,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "files": manifest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=(*TARGETS, "all"))
    parser.add_argument("--tag-prefix", default="async-rbench-track-b")
    parser.add_argument("--tag-suffix", default="")
    parser.add_argument("--context-only", type=Path, help="Write an auditable tar without building")
    parser.add_argument("--builder", choices=("default", "legacy"), default="legacy")
    parser.add_argument("--python-image", help="Explicit alternative Python 3.12 base reference")
    parser.add_argument("--build-memory", default="768m")
    parser.add_argument("--build-cpus", type=float, default=0.5)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9./_-]*", args.tag_prefix):
        parser.error("tag prefix must be a local Docker repository name")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]*", args.tag_suffix):
        parser.error("tag suffix contains unsupported characters")
    if not 0 < args.build_cpus <= 4:
        parser.error("build CPU limit must be greater than zero and at most four")
    root = Path(__file__).resolve().parents[2]
    if args.context_only:
        print(json.dumps(write_context(root, args.context_only.resolve()), sort_keys=True))
        return
    env = dict(os.environ)
    if args.builder == "legacy":
        env["DOCKER_BUILDKIT"] = "0"
    help_result = subprocess.run(
        ["docker", "build", "--help"], capture_output=True, text=True, check=True,
        timeout=60, env=env,
    )
    resource_flags = []
    cleanup_flags = ["--force-rm"] if "--force-rm" in help_result.stdout else []
    if "--cpu-quota" in help_result.stdout and "--memory " in help_result.stdout:
        resource_flags = ["--cpu-period", "100000", "--cpu-quota", str(int(args.build_cpus * 100000)),
                          "--memory", args.build_memory, "--memory-swap", args.build_memory]
    else:
        print("This Docker builder exposes no per-build CPU/memory limits; builds remain sequential.", flush=True)
    with tempfile.TemporaryDirectory(prefix="async-rbench-track-b-build-") as temporary:
        archive = Path(temporary) / "context.tar"
        manifest = write_context(root, archive)
        print(json.dumps({key: value for key, value in manifest.items() if key != "files"}), flush=True)
        for target in TARGETS if args.target == "all" else (args.target,):
            tag = f"{args.tag_prefix}:{target}{args.tag_suffix}"
            command = ["docker", "build", "--platform", "linux/amd64", "--target", target,
                       "--file", "docker/track-b/Dockerfile", "--tag", tag, *resource_flags, *cleanup_flags]
            if args.python_image:
                command.extend(["--build-arg", "PYTHON_IMAGE=" + args.python_image])
            command.append("-")
            with archive.open("rb") as source:
                subprocess.run(command, stdin=source, check=True, env=env)
            image_id = subprocess.check_output(
                ["docker", "image", "inspect", "--format", "{{.Id}}", tag], text=True, timeout=60,
            ).strip()
            print(json.dumps({"target": target, "image": tag, "image_id": image_id}), flush=True)


if __name__ == "__main__":
    main()
