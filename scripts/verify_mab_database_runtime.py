from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "candidate_cases" / "rebuild-to-100" / "runtime-mab-db"


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def main() -> int:
    manifest = json.loads((BATCH / "batch_manifest.json").read_text(encoding="utf-8"))
    rows = []
    for item in manifest["cases"]:
        runtime = ROOT / item["output"] / "runtime"
        native_path = runtime / "native_canonical_report.json"
        native = json.loads(native_path.read_text(encoding="utf-8")) if native_path.is_file() else {}
        adapter = run([sys.executable, "adapter.py"], runtime)
        variants = {}
        for name in ["oracle_resolution.json", "equivalent_resolution.json", "negative_wrong_diagnosis.json", "negative_ignored_authority.json"]:
            result = run([sys.executable, "verify.py", name], runtime)
            variants[name] = {"exit_code": result.returncode, "result": json.loads(result.stdout.strip()) if result.stdout.strip() else {"errors": [result.stderr]}}
        passed = adapter.returncode == 0 and variants["oracle_resolution.json"]["exit_code"] == 0 and variants["equivalent_resolution.json"]["exit_code"] == 0 and all(variants[n]["exit_code"] != 0 for n in ["negative_wrong_diagnosis.json", "negative_ignored_authority.json"]) and bool(native.get("source_native_marble_verified")) and bool(native.get("native_evaluator_verified"))
        rows.append({"case_id": item["case_id"], "passed": passed, "adapter_exit_code": adapter.returncode,
                     "variants": variants, "source_native_marble_executed": False, "native_evaluator_executed": False,
                     "source_native_marble_verified": bool(native.get("source_native_marble_verified")),
                     "native_evaluator_verified": bool(native.get("native_evaluator_verified")),
                     "native_evidence_sha256": native.get("evidence_sha256"),
                     "qualification": "native_canonical_verified" if passed else "failed"})
    report = {"schema_version": "async-rbench-mab-db-verification-v1", "passed": all(r["passed"] for r in rows),
              "summary": {"case_count": len(rows), "adapter_verified": sum(r["passed"] for r in rows),
                          "source_native_marble_verified": sum(r["source_native_marble_verified"] for r in rows),
                          "native_evaluator_verified": sum(r["native_evaluator_verified"] for r in rows)}, "cases": rows}
    (BATCH / "verification_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
