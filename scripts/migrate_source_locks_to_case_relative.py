#!/usr/bin/env python3
"""Bundle locked source records inside each case and rewrite locks atomically."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


REPO = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def existing_snapshot(case_dir: Path, expected: str) -> Path | None:
    snapshots = case_dir / "private/source_manifests"
    if not snapshots.is_dir():
        return None
    for path in sorted(snapshots.rglob("*")):
        if path.is_file() and sha256(path) == expected:
            return path
    return None


def migrate(case_dir: Path) -> dict[str, object] | None:
    lock_path = case_dir / "private/source_lock.json"
    if not lock_path.is_file():
        return None
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    source_files = list(lock.get("source_files") or [])
    expected = dict(lock.get("source_file_sha256") or {})
    if not source_files or set(source_files) != set(expected):
        raise ValueError(f"{case_dir}: source files and hashes do not match")

    resolved: list[tuple[str, Path, str]] = []
    for relative in source_files:
        digest = str(expected[relative])
        source = case_dir / relative
        if not source.is_file():
            source = REPO / relative
        if not source.is_file():
            raise FileNotFoundError(f"{case_dir}: missing locked source {relative}")
        actual = sha256(source)
        if actual != digest:
            raise ValueError(
                f"{case_dir}: source hash mismatch for {relative}: {actual} != {digest}"
            )
        resolved.append((str(relative), source, digest))

    new_files: list[str] = []
    new_hashes: dict[str, str] = {}
    target_dir = case_dir / "private/source_manifests"
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for index, (relative, source, digest) in enumerate(resolved, 1):
        relative_path = Path(relative)
        if (
            not relative_path.is_absolute()
            and ".." not in relative_path.parts
            and relative_path.parts
            and relative_path.parts[0] == "private"
            and (case_dir / relative_path).is_file()
        ):
            target = case_dir / relative_path
        else:
            target = existing_snapshot(case_dir, digest) or (
                target_dir / f"{index:02d}-{source.name}"
            )
            if not target.is_file():
                shutil.copy2(source, target)
                copied += 1
        if sha256(target) != digest:
            raise ValueError(f"{case_dir}: bundled source hash mismatch for {target}")
        bundled = target.relative_to(case_dir).as_posix()
        new_files.append(bundled)
        new_hashes[bundled] = digest

    lock["production_case_path"] = "."
    lock["source_files"] = new_files
    lock["source_file_sha256"] = new_hashes
    dump_atomic(lock_path, lock)
    return {
        "case_id": case_dir.name,
        "source_files": len(new_files),
        "copied": copied,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, action="append", required=True)
    args = parser.parse_args()
    rows: list[dict[str, object]] = []
    for root in args.root:
        root = root.resolve()
        for lock_path in sorted(root.rglob("private/source_lock.json")):
            row = migrate(lock_path.parents[1])
            if row is not None:
                rows.append(row)
    print(json.dumps({
        "migrated": len(rows),
        "copied": sum(int(row["copied"]) for row in rows),
        "rows": rows,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
