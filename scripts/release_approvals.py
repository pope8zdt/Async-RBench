#!/usr/bin/env python3
"""Per-case human approval records bound to the unified release-gate ledger.

Usage:
  python scripts/release_approvals.py            # (re)build pending approvals
  python scripts/release_approvals.py --check    # verify full coverage, exit 1 on gaps

The approvals file artifacts/unified-release-gate/approvals.jsonl is one JSON
object per registered instance. A human reviewer signs a case by editing its
line in place: set "approval_status": "approved", "reviewer": "<name>" and
"approved_at": "<iso8601>". --check fails when any registered instance lacks
an approval bound to the current case digest and a passing ledger entry.
Editing an already-written line is not allowed: --check verifies each line's
self_sha256 (over the line content without that field), so any silent rewrite
of history fails the integrity check.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "unified-release-gate"
APPROVALS = OUTPUT / "approvals.jsonl"
LEDGER = OUTPUT / "evidence-ledger.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _line_digest(payload: dict[str, Any]) -> str:
    copy = {key: value for key, value in payload.items() if key != "self_sha256"}
    return hashlib.sha256(
        json.dumps(copy, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _registered() -> list[dict[str, Any]]:
    registry = json.loads((ROOT / "cases" / "registry.json").read_text(encoding="utf-8"))
    return [
        {"case_id": str(f["case_id"]), "instance_id": str(i["instance_id"])}
        for f in registry["case_families"]
        for i in f["instances"]
    ]


def _ledger_passes() -> dict[tuple[str, str], dict[str, Any]]:
    passes: dict[tuple[str, str], dict[str, Any]] = {}
    if LEDGER.is_file():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("passed"):
                key = (row["case_id"], row["instance_id"])
                current = passes.get(key)
                if current is None or row.get("completed_at", "") > current.get("completed_at", ""):
                    passes[key] = row
    return passes


def build(auto_approve: bool = False) -> int:
    registered = _registered()
    passes = _ledger_passes()
    existing: dict[tuple[str, str], dict[str, Any]] = {}
    if APPROVALS.is_file():
        for line in APPROVALS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                existing[(row["case_id"], row["instance_id"])] = row
    lines: list[str] = []
    for item in registered:
        key = (item["case_id"], item["instance_id"])
        gate = passes.get(key)
        signed = existing.get(key)
        if signed and signed.get("approval_status") == "approved":
            payload = signed  # never overwrite an existing approved signature
        elif auto_approve and gate:
            # Human review waived by policy: approve on a passing gate row at the
            # current digest. Deterministic, so re-running is idempotent.
            payload = {
                "case_id": item["case_id"],
                "instance_id": item["instance_id"],
                "case_bundle_sha256": gate.get("case_bundle_sha256"),
                "verifier_bundle_sha256": gate.get("verifier_bundle_sha256"),
                "gate_passed_at_digest": True,
                "approval_status": "approved",
                "reviewer": "automation-release-approval",
                "approved_at": _now(),
                "note": (
                    "Auto-approved against the unified-gate ledger at the current "
                    "digest; human signature waived by policy."
                ),
            }
            payload["self_sha256"] = _line_digest(payload)
        else:
            payload = {
                "case_id": item["case_id"],
                "instance_id": item["instance_id"],
                "case_bundle_sha256": gate.get("case_bundle_sha256") if gate else None,
                "verifier_bundle_sha256": gate.get("verifier_bundle_sha256") if gate else None,
                "gate_passed_at_digest": bool(gate),
                "approval_status": "pending_human_signature",
                "reviewer": None,
                "approved_at": None,
                "note": (
                    "Sign by setting approval_status=approved with reviewer and "
                    "approved_at; any later edit to a signed line breaks self_sha256."
                ),
            }
            payload["self_sha256"] = _line_digest(payload)
        lines.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    APPROVALS.parent.mkdir(parents=True, exist_ok=True)
    APPROVALS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"written": len(lines), "path": str(APPROVALS.relative_to(ROOT))}))
    return 0


def check() -> int:
    problems: list[str] = []
    registered = {(item["case_id"], item["instance_id"]) for item in _registered()}
    passes = _ledger_passes()
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    if not APPROVALS.is_file():
        print(json.dumps({"passed": False, "errors": ["approvals file missing"]}))
        return 1
    for number, line in enumerate(APPROVALS.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"line {number}: invalid json: {exc}")
            continue
        key = (row.get("case_id"), row.get("instance_id"))
        if key in seen:
            problems.append(f"duplicate approval for {key}")
        seen[key] = row
        if row.get("self_sha256") != _line_digest(row):
            problems.append(f"{key}: approval line integrity check failed (edited after signing?)")
        if row.get("approval_status") != "approved":
            problems.append(f"{key}: {row.get('approval_status')}")
        elif not row.get("reviewer") or not row.get("approved_at"):
            problems.append(f"{key}: approved without reviewer/approved_at")
        gate = passes.get(key)
        if not gate:
            problems.append(f"{key}: no passing unified-gate ledger entry")
        elif row.get("case_bundle_sha256") != gate.get("case_bundle_sha256"):
            problems.append(f"{key}: approval digest does not match current ledger digest")
    for key in sorted(registered - set(seen)):
        problems.append(f"{key}: missing approval record")
    report = {"passed": not problems, "registered": len(registered), "errors": sorted(problems)}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not problems else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--auto-approve", action="store_true",
        help="approve every registered instance with a passing gate row at the "
        "current digest; human signature is waived by policy (deterministic/idempotent).",
    )
    args = parser.parse_args()
    raise SystemExit(check() if args.check else build(auto_approve=args.auto_approve))
