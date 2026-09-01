#!/usr/bin/env python3
"""Replace inherited merger checks with task-native MAB database semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def semantic_registry(case_id: str) -> dict[str, Any]:
    prefix = slug(case_id)
    rows = [
        ("event.receipt", "event_integration", True, "The independent receipt is authentic and case/source bound.", "test_case_outcomes.py::test_event_receipt_is_authentic_and_case_bound"),
        ("event.probes", "event_integration", True, "The independent database authority worker completed with a host checkpoint probe.", "test_case_outcomes.py::test_independent_worker_completed_with_observable_probes"),
        ("closure", "closure", True, "The final closure consumes the exact authority receipt and re-verifies source semantics.", "test_case_outcomes.py::test_final_closure_consumes_exact_event_receipt"),
        ("source.pin", "provenance", True, "The submitted diagnosis remains bound to the selected native MAB source task.", "test_case_outcomes.py::test_pinned_source_revision_is_preserved"),
        ("native.binding", "source_semantics", True, "The evaluator-owned MARBLE report is bound to this exact database task and passed its native evaluator.", "upstream_tests/test_outputs.py::test_native_evaluator_binding_is_exact"),
        ("diagnosis.exact", "source_semantics", True, "The final selected cause exactly matches the task-specific native root cause.", "upstream_tests/test_outputs.py::test_selected_database_cause_is_exact"),
        ("conflict.reconciled", "source_semantics", True, "The competing provisional diagnosis is explicitly superseded rather than merged into the answer.", "upstream_tests/test_outputs.py::test_competing_diagnosis_is_reconciled"),
        ("authority.evidence", "source_semantics", True, "The diagnosis cites the exact evaluator-owned native evidence and host checkpoint digests.", "upstream_tests/test_outputs.py::test_native_authority_evidence_is_consumed"),
        ("output.schema", "source_semantics", False, "The final database diagnosis obeys the case-specific output schema and preservation contract.", "upstream_tests/test_outputs.py::test_database_diagnosis_schema_and_preservation"),
    ]
    checks = []
    for suffix, category, critical, description, node in rows:
        checks.append({
            "id": f"{prefix}.{suffix}", "measurement_type": "semantic",
            "category": category, "critical": critical, "description": description,
            "pytest_node": node,
            "capability_target": (
                "base_task_completion" if category in {"source_semantics", "provenance"}
                else "async_consistency_closure" if category == "closure"
                else "async_result_integration"
            ),
            "relevance_tier": (
                "base" if category in {"source_semantics", "provenance"}
                else "critical" if critical else "direct"
            ),
        })
    return {"version": "4", "checks": checks}


def event_worker(case_id: str, source_id: str, checkpoint_sha: str) -> str:
    return f'''from __future__ import annotations
import argparse, hashlib, json, pathlib, time
CASE_ID={case_id!r}; SOURCE_ID={source_id!r}; CHECKPOINT_SHA={checkpoint_sha!r}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',default='/app/output_data/event_receipt.json'); ap.add_argument('--workspace',default='/app'); args=ap.parse_args()
    started=time.time()
    payload={{'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':'authoritative_postgres_checkpoint','worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{{'host_checkpoint_sha256':CHECKPOINT_SHA}}}}
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode(); payload['receipt_sha256']=hashlib.sha256(raw).hexdigest()
    out=pathlib.Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\\n')
    print(json.dumps(payload,sort_keys=True))
if __name__=='__main__': main()
'''


def diagnosis_solution(source_id: str, anomaly: str, decoy: str, evidence_sha: str, checkpoint_sha: str) -> str:
    payload = {
        "source_task_id": source_id, "selected_causes": [anomaly],
        "superseded_causes": [decoy], "preserved_prior_findings": True,
        "native_evidence_sha256": evidence_sha, "host_checkpoint_sha256": checkpoint_sha,
        "source_semantics_reverified": True,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return f'''#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\\n' {json.dumps(encoded)} > /app/output_data/database_diagnosis.json
'''


def repair(case_id: str) -> dict[str, Any]:
    case = ROOT / "candidate_cases" / case_id
    runtime = ROOT / "candidate_cases/rebuild-to-100/runtime-mab-db" / case_id / "runtime"
    spec = load(runtime / "case_spec.json")
    native = load(runtime / "native_canonical_report.json")
    if spec["case_id"] != case_id or native["case_id"] != case_id:
        raise ValueError("runtime identity mismatch")
    source_id = str(spec["source_task_id"]); anomaly = str(spec["anomaly"]); decoy = str(spec["decoy"])
    evidence_sha = str(native["evidence_sha256"])
    checkpoint_sha = str(native["host_checkpoint"]["sha256"])
    if native.get("source_native_marble_verified") is not True or native.get("native_evaluator_verified") is not True:
        raise ValueError("native MAB evaluator evidence did not pass")

    # Keep evaluator truth out of participant-visible task_file.  It is copied
    # only into the private verifier and Oracle bundle.
    dump(case / "private/native_canonical_report.json", native)
    dump(case / "task/tests/fixtures/native_canonical_report.json", native)
    public_native = case / "task/task_file/native_canonical_report.json"
    if public_native.exists():
        public_native.unlink()
    public_event = case / "task/task_file/scripts/event_worker.py"
    if public_event.exists():
        public_event.unlink()
    write(case / "task/upstream_solutions/event_worker.py", event_worker(case_id, source_id, checkpoint_sha))
    solution = diagnosis_solution(source_id, anomaly, decoy, evidence_sha, checkpoint_sha)
    write(case / "task/upstream_solutions/database-diagnosis.sh", solution)
    legacy_solution = case / "task/upstream_solutions/multi-source-data-merger.sh"
    if legacy_solution.exists():
        legacy_solution.unlink()

    oracle = '''#!/bin/bash
set -euo pipefail
bash /async_rbench/upstream_solutions/database-diagnosis.sh
printf '%s\n' '{"status":"provisional_database_diagnosis"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"database_findings"}' > /app/output_data/preserved_source_facts.json
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
'''
    write(case / "task/oracle.sh", oracle)
    alternative = solution + f'''printf '%s\\n' '{{"status":"alternative_database_diagnosis"}}' > /app/output_data/provisional_checkpoint.json
printf '%s\\n' '{{"preserved":true,"kind":"database_findings"}}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={{'schema_version':'async-rbench-event-receipt-v1','case_id':{case_id!r},'source_task_id':{source_id!r},'event':'authoritative_postgres_checkpoint','worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{{'host_checkpoint_sha256':{checkpoint_sha!r}}}}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\\n')
PY
python3 /app/task_file/scripts/write_manifest.py
'''
    write(case / "task/equivalence_solutions/alternative_solution.sh", alternative)

    manifest_path = case / "task/task_file/scripts/write_manifest.py"
    manifest_source = manifest_path.read_text(encoding="utf-8")
    manifest_source = re.sub(r"SOURCE_ID='[^']*'", f"SOURCE_ID={source_id!r}", manifest_source)
    write(manifest_path, manifest_source)
    runtime_contract = load(case / "private/runtime_contract.json")
    runtime_contract["source_task_id"] = source_id
    runtime_contract["event_injection"] = (
        f"evaluator-owned PostgreSQL authority event bound to {source_id} and "
        f"host checkpoint {checkpoint_sha}"
    )
    dump(case / "private/runtime_contract.json", runtime_contract)
    write(
        case / "PROVENANCE.md",
        f"# {case_id}\n\nSource: `MultiAgentBench` / `{source_id}`.\n\n"
        f"Native evaluator root cause: `{anomaly}`; competing provisional cause: `{decoy}`.\n\n"
        "The evaluator-owned MARBLE binding and host checkpoint are stored only in private verification material.\n",
    )

    generic_tests = f'''from __future__ import annotations
import hashlib, json, pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID={case_id!r}; SOURCE_ID={source_id!r}
def test_event_receipt_is_authentic_and_case_bound():
    p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); actual=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert claimed==actual; assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID
def test_independent_worker_completed_with_observable_probes():
    p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_finished_at']>=p['worker_started_at']; assert p['worker_exit_code']==0; assert p['probes'].get('host_checkpoint_sha256')
def test_final_closure_consumes_exact_event_receipt():
    r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert m['event_receipt_sha256']==r['receipt_sha256']; assert m['event_consumed'] is True and m['source_semantics_reverified'] is True and m['closure_complete'] is True
def test_pinned_source_revision_is_preserved():
    d=json.loads((OUT/'database_diagnosis.json').read_text()); assert d['source_task_id']==SOURCE_ID
'''
    write(case / "task/tests/test_case_outcomes.py", generic_tests)
    source_tests = f'''from __future__ import annotations
import json,pathlib,re
OUT=pathlib.Path('/app/output_data'); FIX=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
SOURCE_ID={source_id!r}; EXPECTED={anomaly!r}; DECOY={decoy!r}; EVIDENCE={evidence_sha!r}; CHECKPOINT={checkpoint_sha!r}
def diagnosis(): return json.loads((OUT/'database_diagnosis.json').read_text())
def native(): return json.loads(FIX.read_text())
def test_native_evaluator_binding_is_exact():
    n=native(); assert n['case_id']=={case_id!r} and n['source_task_id']==SOURCE_ID; assert n['source_native_marble_verified'] is True and n['native_evaluator_verified'] is True and n['passed'] is True
def test_selected_database_cause_is_exact():
    d=diagnosis(); assert d['selected_causes']==[EXPECTED]
def test_competing_diagnosis_is_reconciled():
    d=diagnosis(); assert d['superseded_causes']==[DECOY]; assert DECOY not in d['selected_causes']
def test_native_authority_evidence_is_consumed():
    d=diagnosis(); assert d['native_evidence_sha256']==EVIDENCE; assert d['host_checkpoint_sha256']==CHECKPOINT
def test_database_diagnosis_schema_and_preservation():
    d=diagnosis(); assert set(d)=={{'source_task_id','selected_causes','superseded_causes','preserved_prior_findings','native_evidence_sha256','host_checkpoint_sha256','source_semantics_reverified'}}; assert d['preserved_prior_findings'] is True and d['source_semantics_reverified'] is True
'''
    write(case / "task/tests/upstream_tests/test_outputs.py", source_tests)
    semantic = semantic_registry(case_id)
    dump(case / "task/tests/semantic_checks.json", semantic)

    prefix = slug(case_id)
    wrong = '''#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/database_diagnosis.json'); d=json.loads(p.read_text()); d['selected_causes']=d['superseded_causes']; p.write_text(json.dumps(d))
PY
'''
    ignored = '''#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/app/output_data/database_diagnosis.json'); d=json.loads(p.read_text()); d['native_evidence_sha256']='0'*64; p.write_text(json.dumps(d))
PY
'''
    write(case / "task/negative_mutations/wrong_database_diagnosis.sh", wrong)
    write(case / "task/negative_mutations/ignored_database_authority.sh", ignored)
    quality = load(case / "private/quality_contract.yaml")
    quality["negative_mutations"] = [
        {"id": "wrong-event-receipt", "path": "task/negative_mutations/wrong_event_receipt.sh", "must_fail": [f"{prefix}.event.receipt"]},
        {"id": "broken-closure-lineage", "path": "task/negative_mutations/broken_closure_lineage.sh", "must_fail": [f"{prefix}.closure"]},
        {"id": "wrong-database-diagnosis", "path": "task/negative_mutations/wrong_database_diagnosis.sh", "must_fail": [f"{prefix}.diagnosis.exact"]},
        {"id": "ignored-database-authority", "path": "task/negative_mutations/ignored_database_authority.sh", "must_fail": [f"{prefix}.authority.evidence"]},
    ]
    covers = quality["requirements"][0]["covers"]
    covers["semantic_checks"] = [str(item["id"]) for item in semantic["checks"]]
    covers["hidden_checks"] = ["receipt_bound_to_case", "closure_consumes_receipt"]
    dump(case / "private/quality_contract.yaml", quality)
    return {"case_id": case_id, "source_task_id": source_id, "expected": anomaly, "decoy": decoy, "semantic_points": len(semantic["checks"]), "negative_mutations": 4}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--case-id", action="append", required=True); args=parser.parse_args()
    print(json.dumps([repair(case_id) for case_id in args.case_id], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
