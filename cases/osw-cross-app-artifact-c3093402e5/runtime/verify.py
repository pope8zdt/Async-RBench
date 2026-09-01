from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
spec = json.loads((HERE / "case_spec.json").read_text(encoding="utf-8"))
candidate = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "resolution.json"
errors=[]
try: answer=json.loads(candidate.read_text(encoding="utf-8"))
except Exception as exc: answer={}; errors.append(f"invalid_resolution:{exc.__class__.__name__}")
try: report=json.loads((HERE / "runtime_report.json").read_text(encoding="utf-8"))
except Exception: report={}; errors.append("runtime_report_missing")
receipts=report.get("receipts", [])
auth=next((r for r in receipts if r.get("result_kind")=="authoritative_environment_result"), None)
if not report.get("adapter_executed"): errors.append("adapter_not_executed")
if not report.get("anomaly_probe_executed"): errors.append("anomaly_probe_not_executed")
if report.get("source_native_marble_executed"): errors.append("false_native_execution_claim")
if not report.get("checkpoint",{}).get("state_changed"): errors.append("missing_state_change")
if not auth: errors.append("authoritative_receipt_missing")
if answer.get("diagnosis") != spec["anomaly"]: errors.append("wrong_diagnosis")
if auth and answer.get("adopted_receipt_id") != auth.get("receipt_id"): errors.append("authoritative_receipt_not_adopted")
if answer.get("superseded_diagnosis") != spec["decoy"]: errors.append("conflict_not_reconciled")
if answer.get("finalized_after_logical_clock", -1) < 3: errors.append("premature_finalization")
result={"case_id":spec["case_id"],"passed":not errors,"errors":errors,
        "qualification":"adapter_verified" if not errors else "failed",
        "source_native_marble_executed":False,"native_evaluator_executed":False}
print(json.dumps(result, sort_keys=True)); raise SystemExit(0 if not errors else 1)
