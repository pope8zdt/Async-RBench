"""Bounded evidence archive parser. Never executes archive contents."""
import io
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import zipfile

from ..artifacts import export_receipt, strict_json, validate_receipt, verify_evidence

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_FILE = 256 * 1024 * 1024
PATH = re.compile(r"(?:receipt|manifest|audit)\.json|runs/[a-zA-Z0-9][a-zA-Z0-9._-]{0,199}/(?:score\.json|event_source\.jsonl)")
SECRET = re.compile(rb'"(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)"\s*:\s*"[^"\s][^"]*"|\bBearer\s+[A-Za-z0-9._-]{12,}|\bsk-[A-Za-z0-9_-]{20,}', re.I)


def check_policy(policy):
    cases = policy.get("cases", {}) if isinstance(policy, dict) else {}
    if len(cases) != 200 or policy.get("repetitions") != 3:
        raise ValueError("A trusted 200-task, three-repeat policy is required")
    themes = [v.get("theme") for v in cases.values()]
    if len(set(themes)) != 8 or any(themes.count(t) != 25 for t in set(themes)):
        raise ValueError("The trusted policy must contain eight balanced scenarios")


def inspect_bundle(raw, directory, policy):
    check_policy(policy)
    directory = Path(directory)
    if directory.exists() or directory.is_symlink():
        raise ValueError("Evidence destination must be new")
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_ARCHIVE:
        raise ValueError("Evidence archive exceeds the upload limit")
    created = False
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if not 3 <= len(infos) <= 1203 or len(set(names)) != len(names):
                raise ValueError("Duplicate or excessive evidence entries")
            if sum(i.file_size for i in infos) > MAX_EXPANDED:
                raise ValueError("Expanded evidence exceeds the limit")
            for info in infos:
                mode = info.external_attr >> 16
                if (not PATH.fullmatch(info.filename) or ".." in info.filename.split("/")
                    or info.flag_bits & 1 or stat.S_ISLNK(mode)
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                    or info.file_size > MAX_FILE or info.file_size > max(info.compress_size, 1) * 250):
                    raise ValueError("Unsupported or unsafe evidence entry")
            if not {"receipt.json", "manifest.json", "audit.json"} <= set(names):
                raise ValueError("Missing evidence documents")
            directory.mkdir(parents=True, exist_ok=False)
            created = True
            for info in infos:
                data = archive.read(info)
                if SECRET.search(data):
                    raise ValueError("Possible credentials in evidence; inspect the originals before submitting")
                target = directory / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        receipt = strict_json((directory / "receipt.json").read_bytes())
        verify_evidence(receipt, directory / "runs", directory / "manifest.json", directory / "audit.json")
        result = validate_receipt(receipt, policy)
        if not result["valid"] or not result["rankable"]:
            raise ValueError("Original evidence does not satisfy the full trusted protocol")
        expected = {"receipt.json", "manifest.json", "audit.json"} | {
            f"runs/{e['episode_id']}/{name}" for e in receipt["evidence"]
            for name in ("score.json", "event_source.jsonl")}
        if set(names) != expected:
            raise ValueError("Unexpected evidence files")
        return {"receipt": receipt, "metrics": result["metrics"],
                "receipt_bytes_sha256": hashlib.sha256((directory / "receipt.json").read_bytes()).hexdigest()}
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError) as exc:
        if created:
            shutil.rmtree(directory)
        raise ValueError("Evidence package could not be validated") from exc


def pack_bundle(run_root, manifest, audit, metadata):
    receipt = export_receipt(run_root, manifest, audit, metadata)
    files = {"receipt.json": json.dumps(receipt, allow_nan=False).encode(),
             "manifest.json": Path(manifest).read_bytes(), "audit.json": Path(audit).read_bytes()}
    for evidence in receipt["evidence"]:
        for name in ("score.json", "event_source.jsonl"):
            key = f"runs/{evidence['episode_id']}/{name}"
            files[key] = (Path(run_root) / evidence["episode_id"] / name).read_bytes()
    if any(SECRET.search(data) for data in files.values()):
        raise ValueError("Possible credentials in evidence")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return stream.getvalue()
