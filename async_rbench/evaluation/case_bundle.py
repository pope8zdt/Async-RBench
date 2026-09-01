from __future__ import annotations

import hashlib
from pathlib import Path

def _is_evidence(path: Path, relative: Path) -> bool:
    """Mutable per-case evidence is not part of the immutable case bundle.

    The release gate and tester rewrite ``STATUS.json`` (via a ``.json.tmp``)
    on every pass. Hashing it would change the bundle digest on every run, so a
    stable digest never matches a prior passing ledger row and the release
    gate's digest-keyed resume can never skip an already-verified instance.
    ``STATUS.json``/``*.json.tmp`` are outputs about the case, not the case.
    """
    name = relative.as_posix()
    return path.name == "STATUS.json" or name.endswith(".json.tmp")


def case_bundle_sha256(case_dir: Path) -> str:
    """Digest a complete instance without absorbing sibling instances.

    ``seed-1`` lives at the family root, so its recursive digest must skip the
    reserved top-level ``instances/`` directory. This keeps every instance
    immutable and independently addressable as a family grows.
    """
    case_dir = case_dir.resolve()
    if not any((case_dir / "task" / name).is_dir() for name in ("assets", "task_file")):
        raise FileNotFoundError(
            f"case has no public payload directory (assets/ or task_file/): {case_dir}"
        )
    files: list[tuple[str, Path]] = []
    for path in case_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(case_dir)
        if relative.parts[0] == "instances" or "__pycache__" in relative.parts:
            continue
        if path.suffix == ".pyc":
            continue
        if _is_evidence(path, relative):
            continue
        files.append((relative.as_posix(), path))
    digest = hashlib.sha256()
    for relative, path in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
