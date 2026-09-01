from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "candidate_cases" / "rebuild-to-100" / "runtime-mab-db"
STAGED = BATCH / "_staged_marble"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", action="append")
    args = parser.parse_args()
    manifest = json.loads((BATCH / "batch_manifest.json").read_text(encoding="utf-8"))
    selected = args.case_id or [row["case_id"] for row in manifest["cases"]]
    unknown = sorted(set(selected) - {row["case_id"] for row in manifest["cases"]})
    if unknown:
        raise SystemExit("unknown case ids: " + ",".join(unknown))

    # The staging directory is generated output owned only by this batch.
    resolved = STAGED.resolve()
    if resolved.parent != BATCH.resolve() or resolved.name != "_staged_marble":
        raise RuntimeError("unsafe staged runtime path")
    if STAGED.exists():
        shutil.rmtree(STAGED)
    from async_rbench.marble_runtime import stage_marble_runtime
    stage_marble_runtime(ROOT / "upstream" / "marble", STAGED)

    python = ROOT / ".venv-marble-native" / "Scripts" / "python.exe"
    worker = ROOT / "scripts" / "run_mab_database_native_worker.py"
    reports = []
    for case_id in selected:
        runtime = BATCH / case_id / "runtime"
        output = runtime / "native_canonical_report.json"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(STAGED)
        completed = subprocess.run(
            [str(python), str(worker), "--spec", str(runtime / "case_spec.json"),
             "--native-case", str(BATCH / case_id / "private" / "source_manifests" / "01-native_case.json"),
             "--output", str(output), "--lock", str(BATCH / ".postgres-runtime.lock")],
            cwd=STAGED,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        if output.is_file():
            report = json.loads(output.read_text(encoding="utf-8"))
        else:
            report = {"case_id": case_id, "passed": False, "errors": [(completed.stderr or completed.stdout)[-1000:]]}
        reports.append(report)
        print(json.dumps({"case_id": case_id, "passed": report.get("passed"), "errors": report.get("errors", [])}, sort_keys=True))
    summary = {
        "schema_version": "async-rbench-mab-db-native-canonical-batch-v1",
        "passed": all(r.get("passed") for r in reports) and len(reports) == len(selected),
        "summary": {"requested": len(selected), "passed": sum(bool(r.get("passed")) for r in reports),
                    "source_native_marble_verified": sum(bool(r.get("source_native_marble_verified")) for r in reports),
                    "native_evaluator_verified": sum(bool(r.get("native_evaluator_verified")) for r in reports)},
        "cases": reports,
    }
    (BATCH / "native_canonical_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
