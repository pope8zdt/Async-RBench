#!/usr/bin/env python3
"""Unified Docker release gate over every registered case instance.

For each (case_id, instance_id) in cases/registry.json, at the *current* case
digest, execute the full release chain under Docker lifecycle isolation:

  canonical: generate -> oracle (Docker) -> hidden verifier
  each declared equivalence solution: generate -> solution -> hidden verifier
  each declared negative mutation: generate -> oracle -> mutation -> verifier
                                        must fail its declared points

A case passes only when the canonical and every equivalence solution verify,
at least two declared negatives are killed, and every variant was judged by
one identical hidden-verifier bundle. Results are appended to an immutable
JSONL evidence ledger keyed by (case_id, instance_id, digest); passing rows
also update cases/<case_id>/STATUS.json execution-evidence fields. Already
passing digests are resumed without re-execution.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from async_rbench.case_quality import equivalence_solutions, negative_mutations
from async_rbench.docker_case import cleanup_instance, run_solution_script
from async_rbench.evaluation.pytest_results import parse_semantic_check_results
from async_rbench.evaluation.runner import _case_digest
from async_rbench.evaluation.version import EVALUATION_CONTRACT_VERSION
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION

OUTPUT = ROOT / "artifacts" / "unified-release-gate"
LEDGER = OUTPUT / "evidence-ledger.jsonl"

# Instances of one family may publish identical host ports in their compose
# files, so two instances of the same family must never execute concurrently.
_FAMILY_LOCKS: dict[str, threading.Lock] = {}
_FAMILY_LOCKS_GUARD = threading.Lock()


def _family_lock(case_id: str) -> threading.Lock:
    with _FAMILY_LOCKS_GUARD:
        return _FAMILY_LOCKS.setdefault(case_id, threading.Lock())


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_ledger() -> dict[tuple[str, str, str], dict[str, Any]]:
    entries: dict[tuple[str, str, str], dict[str, Any]] = {}
    if LEDGER.is_file():
        for number, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            entries[(row["case_id"], row["instance_id"], row["case_bundle_sha256"])] = row
    return entries


def append_ledger(row: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=ROOT, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )


def script(case_dir: Path, name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, str(case_dir / name), *args])


def registered_instances() -> list[dict[str, Any]]:
    registry = json.loads((ROOT / "cases" / "registry.json").read_text(encoding="utf-8"))
    return [
        {
            "case_id": str(family["case_id"]),
            "instance_id": str(instance["instance_id"]),
            "path": ROOT / "cases" / str(family["case_id"]) / str(instance.get("path") or "."),
        }
        for family in registry["case_families"]
        for instance in family["instances"]
    ]


def gate_one(case_id: str, instance_id: str, case_dir: Path, seed: int) -> dict[str, Any]:
    with _family_lock(case_id):
        return _gate_one_locked(case_id, instance_id, case_dir, seed)


def _gate_one_locked(case_id: str, instance_id: str, case_dir: Path, seed: int) -> dict[str, Any]:
    digest = _case_digest(case_dir)
    report_dir = OUTPUT / "reports" / f"{case_id}-{instance_id}-{digest[:12]}"
    row: dict[str, Any] = {
        "schema_version": "unified-release-gate-v1",
        "case_id": case_id, "instance_id": instance_id,
        "case_bundle_sha256": digest,
        "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
        "score_policy_version": SCORE_POLICY_VERSION,
        "seed": seed, "passed": False, "started_at": now(),
    }
    variants: list[dict[str, Any]] = []
    negatives: list[dict[str, Any]] = []

    def work_dir(tag: str) -> Path:
        return report_dir / "work" / tag

    def verify(case_key: str, work: Path, tag: str) -> dict[str, Any]:
        report_path = report_dir / "reports" / f"{tag}.json"
        result = script(case_dir, "verify.py", "--instance", str(work), "--output", str(report_path))
        entry: dict[str, Any] = {"id": tag, "success": False, "exit_code": result.returncode}
        if report_path.is_file():
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            entry["success"] = payload.get("success") is True
            entry["verifier_bundle_sha256"] = payload.get("verifier_bundle_sha256")
            if not entry["success"]:
                entry["verifier_isolation"] = payload.get("verifier_isolation")
        else:
            entry["output_tail"] = result.stdout[-4000:]
        return entry

    try:
        canonical_work = work_dir("canonical")
        gen = script(case_dir, "generate.py", "--output", str(canonical_work), "--seed", str(seed))
        if gen.returncode:
            row["error"] = f"generate failed: {gen.stdout[-3000:]}"
            return row
        oracle = script(case_dir, "oracle.py", "--instance", str(canonical_work))
        row["docker_oracle_executed"] = oracle.returncode == 0
        if oracle.returncode:
            row["error"] = f"oracle failed: {oracle.stdout[-3000:]}"
            return row
        canonical = verify(case_id, canonical_work, "canonical")
        variants.append(canonical)
        cleanup_instance(case_id, canonical_work)

        for variant in equivalence_solutions(case_dir):
            work = work_dir(f"equiv-{variant['id']}")
            gen = script(case_dir, "generate.py", "--output", str(work), "--seed", str(seed))
            if gen.returncode:
                variants.append({"id": variant["id"], "success": False, "error": "generate failed"})
                continue
            solution = run_solution_script(case_id, work, Path(str(variant["path"])))
            entry = verify(case_id, work, f"equiv-{variant['id']}")
            entry["solution_exit_code"] = getattr(solution, "returncode", None)
            variants.append(entry)
            cleanup_instance(case_id, work)

        semantic_registry = json.loads(
            (case_dir / "task/tests/semantic_checks.json").read_text(encoding="utf-8")
        )
        for mutation in negative_mutations(case_dir):
            tag = f"negative-{mutation['id']}"
            work = work_dir(tag)
            entry: dict[str, Any] = {
                "id": mutation["id"], "must_fail": list(mutation["must_fail"]), "killed": False,
            }
            try:
                gen = script(case_dir, "generate.py", "--output", str(work), "--seed", str(seed))
                if gen.returncode:
                    entry["error"] = "generate failed"
                    negatives.append(entry)
                    continue
                if script(case_dir, "oracle.py", "--instance", str(work)).returncode:
                    entry["error"] = "oracle failed"
                    negatives.append(entry)
                    continue
                run_solution_script(case_id, work, Path(str(mutation["path"])), fresh=False)
                report_path = report_dir / "reports" / f"{tag}.json"
                script(
                    case_dir, "verify.py", "--instance", str(work), "--output", str(report_path),
                )
                if report_path.is_file():
                    payload = json.loads(report_path.read_text(encoding="utf-8"))
                    semantic = parse_semantic_check_results(
                        str(payload.get("test_output") or ""), semantic_registry,
                    )
                    failed_ids = {
                        str(item["id"]) for item in (semantic or {}).get("results") or []
                        if item.get("passed") is False
                    }
                    entry["observed_failed"] = sorted(failed_ids)
                    entry["verifier_bundle_sha256"] = payload.get("verifier_bundle_sha256")
                    entry["killed"] = (
                        payload.get("success") is False
                        and set(entry["must_fail"]).issubset(failed_ids)
                    )
            except (OSError, ValueError, subprocess.CalledProcessError) as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                cleanup_instance(case_id, work)
            negatives.append(entry)

        digests = {
            str(item.get("verifier_bundle_sha256"))
            for item in variants + negatives if item.get("verifier_bundle_sha256")
        }
        row.update({
            "canonical_passed": bool(variants) and variants[0]["success"],
            "equivalence_passed": all(item["success"] for item in variants[1:]),
            "negative_mutations_killed": sum(bool(item["killed"]) for item in negatives),
            "negative_mutation_count": len(negatives),
            "same_verifier_bundle": len(digests) == 1,
            "verifier_bundle_sha256": next(iter(digests), None),
            "variants": variants,
            "negative_mutations": negatives,
        })
        row["passed"] = (
            bool(variants) and all(item["success"] for item in variants)
            and row["negative_mutations_killed"] >= 2
            and all(item["killed"] for item in negatives)
            and row["same_verifier_bundle"]
        )
        return row
    except Exception as exc:  # fail closed, keep the queue running
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row
    finally:
        if _case_digest(case_dir) != digest:
            row["case_changed_during_gate"] = True
            row["passed"] = False


def update_status(case_dir: Path, row: dict[str, Any]) -> None:
    status_path = case_dir / "STATUS.json"
    status: dict[str, Any] = {}
    if status_path.is_file():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {}
    status.update({
        "docker_oracle_executed": True,
        "docker_oracle_passed": True,
        "hidden_verifier_executed": True,
        "hidden_verifier_passed": True,
        "equivalence_solution_passed": bool(row.get("equivalence_passed")),
        "negative_mutations_killed": int(row.get("negative_mutations_killed") or 0),
        "unified_gate_case_bundle_sha256": row["case_bundle_sha256"],
        "unified_gate_verifier_bundle_sha256": row.get("verifier_bundle_sha256"),
        "unified_gate_passed": row["passed"],
        "unified_gate_ledger": "artifacts/unified-release-gate/evidence-ledger.jsonl",
        "unified_gate_completed_at": row.get("completed_at"),
        "evaluation_contract_version": row["evaluation_contract_version"],
        "score_policy_version": row["score_policy_version"],
    })
    status["status"] = (
        "unified_release_gate_passed"
        if row["passed"] else "unified_release_gate_failed"
    )
    temporary = status_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(status_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--instance-id", action="append")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260901)
    parser.add_argument(
        "--force", action="store_true",
        help="re-execute instances whose current digest already has a passing ledger row",
    )
    args = parser.parse_args()

    ledger = load_ledger()
    selected = [
        item for item in registered_instances()
        if (not args.case_id or item["case_id"] in args.case_id)
        and (not args.instance_id or item["instance_id"] in args.instance_id)
    ]
    pending: list[dict[str, Any]] = []
    resumed = 0
    for item in selected:
        key = (item["case_id"], item["instance_id"], _case_digest(item["path"]))
        if not args.force and key in ledger and ledger[key].get("passed"):
            resumed += 1
            # A prior passing run at this digest stands; refresh the STATUS
            # evidence so a resumed run leaves per-family evidence consistent.
            update_status(item["path"], dict(ledger[key]))
        else:
            pending.append(item)
    print(json.dumps({"queued": len(pending), "resumed_from_ledger": resumed}), flush=True)
    passed = failed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(gate_one, item["case_id"], item["instance_id"], item["path"], args.seed): item
            for item in pending
        }
        for future in as_completed(futures):
            item = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    "case_id": item["case_id"], "instance_id": item["instance_id"],
                    "case_bundle_sha256": "", "passed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            row["completed_at"] = now()
            append_ledger(row)
            passed += bool(row["passed"])
            failed += not bool(row["passed"])
            if row["passed"]:
                update_status(item["path"], row)
            print(json.dumps({
                "case_id": row["case_id"], "instance_id": row["instance_id"],
                "passed": row.get("passed"),
                "negative_mutations_killed": row.get("negative_mutations_killed"),
                "error": row.get("error"),
            }, ensure_ascii=False), flush=True)
    summary = {
        "schema_version": "unified-release-gate-summary-v1",
        "attempted": resumed + passed + failed,
        "passed": passed + resumed,
        "failed": failed,
        "resumed_from_ledger": resumed,
        "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
        "generated_at": now(),
    }
    (OUTPUT / "latest.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(json.dumps(summary))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
