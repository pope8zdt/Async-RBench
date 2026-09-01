from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import argparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from async_rbench.evaluation.pair_qualification import pair_qualification_errors
from scripts.watch_async_bench_intake import apply_status_corrections


INTAKE = ROOT / "artifacts" / "async-bench-intake"
STATE = INTAKE / "consumer-state.json"
REPORT = INTAKE / "pair-status-audit.json"
CORRECTIONS = INTAKE / "consumer-status-corrections.jsonl"


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-state", action="store_true")
    args = parser.parse_args()
    state = load(STATE, {})
    audited = []
    corrections = []
    for key, entry in sorted(state.items()):
        if entry.get("status") != "passed":
            continue
        run_dir = Path(str(entry.get("run_dir") or ""))
        command_path = run_dir / "model-pair.command.json"
        results_path = run_dir / "model-pair" / "pair-results.json"
        command = load(command_path, {})
        results = load(results_path, {})
        exit_code = command.get("exit_code", entry.get("pair_exit_code"))
        if not isinstance(exit_code, int):
            exit_code = -999
        errors = pair_qualification_errors(exit_code, results)
        row = {
            "key": key,
            "case_id": entry.get("case_id"),
            "revision": entry.get("revision"),
            "recorded_status": "passed",
            "corrected_status": "passed" if not errors else "completed_with_findings",
            "pair_exit_code": exit_code,
            "pair_results_passed": results.get("passed"),
            "scenario_constructed_count": results.get("scenario_constructed_count"),
            "scenario_exposed_count": results.get("scenario_exposed_count"),
            "episode_count": results.get("episode_count"),
            "qualification_errors": errors,
            "command_evidence": str(command_path),
            "results_evidence": str(results_path),
        }
        audited.append(row)
        if errors:
            corrections.append(row)
    generated = datetime.now(timezone.utc).isoformat()
    report = {
        "schema_version": "async-bench-pair-status-audit-v1",
        "generated_at": generated,
        "source_state": str(STATE),
        "passed_records_audited": len(audited),
        "valid_passed_records": len(audited) - len(corrections),
        "incorrect_passed_records": len(corrections),
        "correction_policy": (
            "Historical evidence is immutable. corrected_status supersedes recorded_status "
            "when qualification_errors is non-empty."
        ),
        "records": audited,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with CORRECTIONS.open("w", encoding="utf-8", newline="\n") as stream:
        for row in corrections:
            stream.write(json.dumps({"corrected_at": generated, **row}, sort_keys=True) + "\n")
    if args.apply_state:
        apply_status_corrections(state)
        temporary = STATE.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(STATE)
    print(json.dumps({key: report[key] for key in (
        "passed_records_audited", "valid_passed_records", "incorrect_passed_records"
    )}, indent=2))
    return 1 if corrections else 0


if __name__ == "__main__":
    raise SystemExit(main())
