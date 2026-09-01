from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "candidate_cases" / "rebuild-to-100" / "runtime-swe-first5"
RUNTIME = ROOT / "artifacts" / "runtime-swe-first5"


def run(command: list[str]) -> int:
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, cwd=ROOT).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--rerun-passed", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((BATCH / "batch-manifest.json").read_text(encoding="utf-8"))
    selected = set(args.case_id or [])
    results = []
    RUNTIME.mkdir(parents=True, exist_ok=True)
    for case in manifest["cases"]:
        case_id = case["case_id"]
        if selected and case_id not in selected:
            continue
        case_dir = BATCH / case_id
        instance = RUNTIME / case_id
        report = RUNTIME / f"{case_id}-verifier.json"
        if report.is_file() and not args.rerun_passed:
            prior = json.loads(report.read_text(encoding="utf-8"))
            if prior.get("success") is True:
                result = {"case_id": case_id, "oracle": "PASS", "verifier": "PASS", "reused": True}
                results.append(result)
                status = json.loads((case_dir / "STATUS.json").read_text(encoding="utf-8"))
                status.update({"status": "runtime_qualified_pending_promotion_review", "docker_oracle_executed": True, "docker_oracle_passed": True, "hidden_verifier_executed": True, "hidden_verifier_passed": True, "verifier_report": str(report.relative_to(ROOT)).replace("\\", "/")})
                (case_dir / "STATUS.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
                print(json.dumps(result), flush=True)
                continue
        started = time.time()
        # A failed rerun must never leave an older passing verifier report that
        # can later be mistaken for evidence about the current materialization.
        if report.exists():
            report.unlink()
        generate = run([sys.executable, str(case_dir / "generate.py"), "--output", str(instance)])
        oracle = run([sys.executable, str(case_dir / "oracle.py"), "--instance", str(instance)]) if generate == 0 else 125
        verifier = run([sys.executable, str(case_dir / "verify.py"), "--instance", str(instance), "--output", str(report)]) if oracle == 0 else 125
        result = {"case_id": case_id, "generate_exit_code": generate, "oracle_exit_code": oracle, "verifier_exit_code": verifier, "elapsed_sec": round(time.time() - started, 3)}
        results.append(result)
        status = json.loads((case_dir / "STATUS.json").read_text(encoding="utf-8"))
        status.update({
            "status": "runtime_qualified_pending_promotion_review" if oracle == verifier == 0 else "runtime_failed_requires_repair",
            "docker_oracle_executed": oracle != 125,
            "docker_oracle_passed": oracle == 0,
            "hidden_verifier_executed": verifier != 125,
            "hidden_verifier_passed": verifier == 0,
            "runtime_exit_codes": result,
            "verifier_report": str(report.relative_to(ROOT)).replace("\\", "/") if report.is_file() else None,
        })
        (case_dir / "STATUS.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)
    summary = {"schema_version": "1", "results": results, "passed": sum(item.get("verifier") == "PASS" or item.get("verifier_exit_code") == 0 for item in results), "total": len(results)}
    (RUNTIME / "runtime-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
