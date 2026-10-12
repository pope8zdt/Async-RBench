"""Evaluator-owned filesystem observations at declared command boundaries.

These snapshots are not an operation journal: an edit and restoration inside
one command is outside their coverage. Strict whole-window scoring remains a
separate capability requirement.
"""
from __future__ import annotations

import json
import shlex
from typing import Any


_SNAPSHOT_SCRIPT = """import hashlib,json,pathlib,sys
rows=[]
for item in json.loads(sys.argv[1]):
    row={'artifact_id': item['id'], 'observed_path': item['path']}
    try:
        p=pathlib.Path(item['path'])
        row['exists']=p.exists()
        h=hashlib.sha256()
        if not p.exists():
            h.update(b'async-rbench:absent-artifact')
        else:
            files=[p] if p.is_file() else sorted(q for q in p.rglob('*') if q.is_file())
            for q in files:
                h.update((q.name if p.is_file() else q.relative_to(p).as_posix()).encode('utf-8','surrogateescape'))
                h.update(b'\\0'); h.update(q.read_bytes()); h.update(b'\\0')
        row['observed_digest']=h.hexdigest()
    except Exception as exc:
        row['observed_digest']=None
        row['observation_error']=str(exc)
    rows.append(row)
print(json.dumps(rows))
"""


def artifact_snapshot_command(artifacts: list[dict[str, Any]]) -> str:
    paths = [{"id": item["id"], "path": item["path"]} for item in artifacts]
    return f"python3 -c {shlex.quote(_SNAPSHOT_SCRIPT)} {shlex.quote(json.dumps(paths))}"
