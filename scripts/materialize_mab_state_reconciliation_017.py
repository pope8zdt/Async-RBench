"""Materialize the source-native MAB database:017 reconciliation family.

This deliberately reuses only the delivery layout of a mature MAB family.  Its
runtime, event, source binding, tests, and mutations are database:017-specific.
No MARBLE service is started by this materializer.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-state-reconciliation-bda6dda56f"
SOURCE_ID = "database:017"
CASE = ROOT / "candidate_cases" / CASE_ID
TEMPLATE = ROOT / "candidate_cases" / "mab-late-constraint-89a5f5d134"
SOURCE = ROOT / "artifacts" / "source-native-v4" / "cases" / "multiagentbench" / CASE_ID


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def dump(path: Path, value: object) -> None:
    write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def source_instruction() -> str:
    task = json.loads((SOURCE / "official_task.json").read_text(encoding="utf-8"))["task"]
    return task["content"].strip() + "\n\n" + task["output_format"].strip()


RUNTIME = r'''from __future__ import annotations
import argparse, hashlib, json, pathlib

CASE_ID = "mab-state-reconciliation-bda6dda56f"
SOURCE_ID = "database:017"
STATE_DIGEST = "3c5a98143d1e2dfbf2865fd51dcb65a951f72a61d9a2dc265f75f9b915ef2aec"
PROVISIONAL = ["MISSING_INDEXES", "POOR_JOIN_PERFORMANCE"]
AUTHORITATIVE = ["INSERT_LARGE_DATA"]
PRESERVED = ["LOCK_CONTENTION probe completed", "VACUUM catalog probe completed"]

def receipt() -> dict:
    body = {
        "schema_version": "mab-marble-native-receipt-v1", "case_id": CASE_ID,
        "source_task_id": SOURCE_ID, "event_id": "evt.db017.insert-authority",
        "producer_role": "insert_large_data_specialist",
        "release_after_native_action_sequence": 1,
        "native_action_sequence": 2, "native_state_digest": STATE_DIGEST,
        "result_kind": "authoritative_environment_result",
        "pg_stat_statements": {"insert_threads": 100, "insert_rows_per_batch": 20000,
                               "columns": 20, "column_bytes": 100},
        "authoritative_causes": AUTHORITATIVE,
        "invalidates": PROVISIONAL,
    }
    body["receipt_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return body

def build(workspace: pathlib.Path, *, equivalent: bool = False, mutation: str | None = None) -> None:
    out = workspace / "output_data"; out.mkdir(parents=True, exist_ok=True)
    provisional = {"source_task_id": SOURCE_ID, "native_action_sequence": 1,
                   "candidate_causes": PROVISIONAL, "basis": "narrative file-sharing joins",
                   "status": "superseded_after_native_receipt"}
    event = receipt()
    selected = AUTHORITATIVE if mutation != "wrong_cause" else ["FETCH_LARGE_DATA"]
    retracted = PROVISIONAL if mutation != "stale_join" else ["MISSING_INDEXES"]
    native_sequence = event["native_action_sequence"] if mutation != "forged_receipt" else 0
    if mutation == "forged_receipt": event["native_action_sequence"] = 0
    diagnosis = {
        "schema_version": "mab-db017-diagnosis-v1", "source_task_id": SOURCE_ID,
        "selected_causes": selected, "retracted_causes": retracted,
        "preserved_probes": PRESERVED, "native_state_digest": STATE_DIGEST,
        "authority_receipt_sha256": event["receipt_sha256"],
        "native_action_sequence": native_sequence,
        "evidence_matrix": {"INSERT_LARGE_DATA": "pg_stat_statements bulk INSERT evidence",
                            "LOCK_CONTENTION": "probe retained but not selected",
                            "VACUUM": "probe retained but not selected"},
    }
    closure = {
        "schema_version": "mab-db017-closure-v1", "case_id": CASE_ID,
        "source_task_id": SOURCE_ID, "authority_receipt_sha256": event["receipt_sha256"],
        "native_state_digest": STATE_DIGEST, "reverified_after_action_sequence": 3,
        "selected_causes": selected, "closure_complete": mutation != "broken_closure",
        "source_native_evaluator": "MARBLE evaluate_task_db binding",
    }
    manifest = {"case_id": CASE_ID, "source_task_id": SOURCE_ID,
                "event_consumed": mutation != "forged_receipt",
                "provisional_retracted": retracted == PROVISIONAL,
                "valid_probes_preserved": diagnosis["preserved_probes"] == PRESERVED,
                "closure_complete": closure["closure_complete"],
                "equivalent_path": equivalent}
    for name, payload in (("provisional_diagnosis.json", provisional), ("event_receipt.json", event),
                          ("database_diagnosis.json", diagnosis), ("reconciliation_closure.json", closure),
                          ("decision_manifest.json", manifest)):
        (out / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--workspace", default="/app")
    parser.add_argument("--equivalent", action="store_true")
    parser.add_argument("--mutation", choices=["wrong_cause", "stale_join", "forged_receipt", "broken_closure"])
    args = parser.parse_args(); build(pathlib.Path(args.workspace), equivalent=args.equivalent, mutation=args.mutation)

if __name__ == "__main__": main()
'''


TEST_OUTCOMES = r'''from __future__ import annotations
import hashlib, json, pathlib
O = pathlib.Path('/app/output_data'); CASE='mab-state-reconciliation-bda6dda56f'; SOURCE='database:017'
PROVISIONAL=['MISSING_INDEXES','POOR_JOIN_PERFORMANCE']; AUTHORITATIVE=['INSERT_LARGE_DATA']; PRESERVED=['LOCK_CONTENTION probe completed','VACUUM catalog probe completed']
def read(name): return json.loads((O/name).read_text())
def test_receipt_is_bound_and_authentic():
 r=read('event_receipt.json'); digest=r.pop('receipt_sha256'); assert digest == hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert r['case_id']==CASE and r['source_task_id']==SOURCE
def test_native_checkpoint_precedes_authority():
 r=read('event_receipt.json'); assert r['native_action_sequence'] > r['release_after_native_action_sequence'] >= 1 and r['producer_role']=='insert_large_data_specialist'
def test_reconciliation_retracts_only_stale_join_branch():
 d=read('database_diagnosis.json'); assert d['retracted_causes']==PROVISIONAL and d['preserved_probes']==PRESERVED and d['selected_causes']==AUTHORITATIVE
def test_receipt_bound_closure_rechecks_source_state():
 r=read('event_receipt.json'); c=read('reconciliation_closure.json'); m=read('decision_manifest.json'); assert c['authority_receipt_sha256']==r['receipt_sha256'] and c['closure_complete'] and m['event_consumed'] and m['provisional_retracted'] and m['valid_probes_preserved']
'''


UPSTREAM_TESTS = r'''from __future__ import annotations
import json, pathlib
O=pathlib.Path('/app/output_data'); F=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def read(name): return json.loads((O/name).read_text())
def test_source_native_binding():
 n=json.loads(F.read_text()); assert n['case_id']=='mab-state-reconciliation-bda6dda56f'; assert n['source_task_id']=='database:017'; assert n['source_binding']['record_sha256']=='3c5a98143d1e2dfbf2865fd51dcb65a951f72a61d9a2dc265f75f9b915ef2aec'; assert n['native_evaluator_method']=='MARBLE evaluate_task_db binding'
def test_insert_large_data_evidence_and_selected_set():
 r=read('event_receipt.json'); d=read('database_diagnosis.json'); assert r['pg_stat_statements']=={'insert_threads':100,'insert_rows_per_batch':20000,'columns':20,'column_bytes':100}; assert d['selected_causes']==['INSERT_LARGE_DATA']
def test_closure_uses_native_digest():
 r=read('event_receipt.json'); d=read('database_diagnosis.json'); c=read('reconciliation_closure.json'); assert r['native_state_digest']==d['native_state_digest']==c['native_state_digest'] and c['reverified_after_action_sequence']>r['native_action_sequence']
'''


CONTROL = r'''from __future__ import annotations
import json, pathlib, pytest
O=pathlib.Path('/app/output_data'); R=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('check',R['checks'],ids=lambda x:x['id'])
def test_control_point(check):
 r=json.loads((O/'event_receipt.json').read_text()); d=json.loads((O/'database_diagnosis.json').read_text()); m=json.loads((O/'decision_manifest.json').read_text())
 assert r['native_action_sequence']>r['release_after_native_action_sequence']; assert m['event_consumed']; assert d['retracted_causes']==['MISSING_INDEXES','POOR_JOIN_PERFORMANCE']; assert m['valid_probes_preserved']
'''


def main() -> None:
    if CASE.exists():
        raise SystemExit(f"refusing to overwrite existing candidate: {CASE}")
    shutil.copytree(TEMPLATE, CASE, ignore=shutil.ignore_patterns("review_evidence", "__pycache__"))
    for path in CASE.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".yaml", ".md", ".py", ".sh"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            text = text.replace("mab-late-constraint-89a5f5d134", CASE_ID).replace("bargaining:015", SOURCE_ID)
            path.write_text(text, encoding="utf-8", newline="\n")
    source_text = source_instruction()
    source_hash = hashlib.sha256(source_text.encode()).hexdigest()
    native = json.loads((SOURCE / "native_case.json").read_text(encoding="utf-8"))
    for name, target in (("native_case.json", "01-native_case.json"), ("official_task.json", "03-official_task.json"), ("native_config.yaml", "04-native_config.yaml")):
        shutil.copy2(SOURCE / name, CASE / "private" / "source_manifests" / target)
    dump(CASE / "private" / "source_task.yaml", {"instruction": source_text})
    dump(CASE / "private" / "native_canonical_report.json", {
        "case_id": CASE_ID, "source_task_id": SOURCE_ID,
        "source_binding": native["source_binding"], "native_evaluator_method": "MARBLE evaluate_task_db binding",
        "source_native_runtime_qualified": True, "service_execution": "not_run_in_static_materialization",
        "state_reconciliation_contract": "native INSERT authority supersedes only the provisional join branch",
    })
    shutil.copy2(CASE / "private" / "native_canonical_report.json", CASE / "task" / "tests" / "fixtures" / "native_canonical_report.json")
    task = load_yaml(CASE / "task" / "task.yaml")
    task["instruction"] = source_text + "\n\nASYNC-RBENCH EXTENSION\nPersist a provisional file-sharing join diagnosis, then consume the evaluator-owned MARBLE INSERT_LARGE_DATA receipt only after its native checkpoint. Retract the provisional join branches, preserve completed LOCK_CONTENTION and VACUUM probes, rebuild the evidence matrix, and write a receipt-bound reconciliation closure under /app/output_data."
    task["tags"] = ["multiagentbench", "database", "state-reconciliation", "insert-large-data", "database017"]
    write(CASE / "task" / "task.yaml", yaml.safe_dump(task, sort_keys=False, allow_unicode=True))
    write(CASE / "instruction.md", task["instruction"] + "\n")
    dump(CASE / "task" / "task_file" / "participant_task.json", {"benchmark":"MultiAgentBench","case_id":CASE_ID,"source_task_id":SOURCE_ID,"answer_withheld":True,"task":json.loads((SOURCE / "participant_task.json").read_text(encoding="utf-8"))["task"]})
    dump(CASE / "task" / "task_file" / "async_contract.json", {"case_id":CASE_ID,"source_task_id":SOURCE_ID,"event_id":"evt.db017.insert-authority","required_output_root":"/app/output_data","truth_visibility":"evaluator_only","release_predicate":"after persisted MARBLE native action sequence 1"})
    write(CASE / "task" / "task_file" / "scripts" / "state_reconciliation.py", RUNTIME)
    write(CASE / "task" / "task_file" / "scripts" / "write_manifest.py", "from state_reconciliation import main\nif __name__ == '__main__': main()\n")
    write(CASE / "task" / "upstream_solutions" / "database017_reconcile.sh", "#!/bin/bash\nset -euo pipefail\npython3 /app/task_file/scripts/state_reconciliation.py --workspace /app\n")
    write(CASE / "task" / "oracle.sh", "#!/bin/bash\nset -euo pipefail\nbash /async_rbench/upstream_solutions/database017_reconcile.sh\n")
    write(CASE / "task" / "equivalence_solutions" / "alternative_solution.sh", "#!/bin/bash\nset -euo pipefail\npython3 /app/task_file/scripts/state_reconciliation.py --workspace /app --equivalent\n")
    mutations = {"wrong_cause":"wrong_cause", "stale_join":"stale_join", "forged_receipt":"forged_receipt", "broken_closure":"broken_closure"}
    for name, value in mutations.items():
        write(CASE / "task" / "negative_mutations" / f"{name}.sh", f"#!/bin/bash\nset -euo pipefail\npython3 /app/task_file/scripts/state_reconciliation.py --workspace /app --mutation {value}\n")
    write(CASE / "task" / "tests" / "test_case_outcomes.py", TEST_OUTCOMES)
    write(CASE / "task" / "tests" / "upstream_tests" / "test_outputs.py", UPSTREAM_TESTS)
    write(CASE / "task" / "tests" / "test_control_flow.py", CONTROL)
    semantic = {"version":"1","checks":[
        {"id":"mab_db017.sem.native_binding","capability_target":"base_task_completion","category":"source_semantics","critical":True,"pytest_node":"upstream_tests/test_outputs.py::test_source_native_binding"},
        {"id":"mab_db017.sem.insert_authority","capability_target":"state_reconciliation","category":"authority","critical":True,"pytest_node":"upstream_tests/test_outputs.py::test_insert_large_data_evidence_and_selected_set"},
        {"id":"mab_db017.sem.retract_only_stale","capability_target":"state_reconciliation","category":"replanning","critical":True,"pytest_node":"test_case_outcomes.py::test_reconciliation_retracts_only_stale_join_branch"},
        {"id":"mab_db017.sem.closure","capability_target":"async_consistency_closure","category":"closure","critical":True,"pytest_node":"test_case_outcomes.py::test_receipt_bound_closure_rechecks_source_state"},
    ]}
    control = {"version":"1","event_contracts":[{"event_id":"evt.db017.insert-authority","authority":"MARBLE insert_large_data_specialist","release_after_native_action_sequence":1}],"checks":[
        {"id":"mab_db017.cf.checkpoint_then_authority","stage_tag":"authority","execution_modes":["async"],"dimension":"causal_order"},
        {"id":"mab_db017.cf.retract_and_preserve","stage_tag":"replanning","execution_modes":["async"],"dimension":"state_reconciliation"},
        {"id":"mab_db017.cf.receipt_closure","stage_tag":"closure","execution_modes":["async"],"dimension":"closure"},
    ]}
    dump(CASE / "task" / "tests" / "semantic_checks.json", semantic); dump(CASE / "task" / "tests" / "control_flow_checks.json", control)
    public = load_yaml(CASE / "public_case.yaml"); public["title"] = "Async-RBench source-native database:017 state reconciliation"; public["source_tasks"]=[{"benchmark":"MultiAgentBench","id":SOURCE_ID}]; public["family"]="state_reconciliation"; write(CASE / "public_case.yaml", yaml.safe_dump(public, sort_keys=False, allow_unicode=True))
    private = load_yaml(CASE / "private" / "private_case.yaml"); private["classification"]["primary_event_theme"]="state_reconciliation"; private["result_contract"]["rule"]="Adopt the receipt-bound native INSERT_LARGE_DATA evidence, retract only provisional join causes, preserve valid global probes, and reverify closure."; private["event_contracts"][0]["event_theme"]="state_reconciliation"; write(CASE / "private" / "private_case.yaml", yaml.safe_dump(private, sort_keys=False, allow_unicode=True))
    quality = load_yaml(CASE / "private" / "quality_contract.yaml"); quality["source_contract"]["sources"]=[{"task_id":SOURCE_ID,"instruction_sha256":source_hash,"task_path":f"candidate_cases/{CASE_ID}/private/source_task.yaml"}]; quality["requirements"][0]["public_evidence"]=[{"path":"task/task.yaml","contains":"INSERT_LARGE_DATA"},{"path":"task/task.yaml","contains":"File Sharing System"}]; write(CASE / "private" / "quality_contract.yaml", yaml.safe_dump(quality, sort_keys=False, allow_unicode=True))
    dump(CASE / "mutation_families.json", {"case_id":CASE_ID,"negative_mutations":[{"id":"wrong_cause","path":"task/negative_mutations/wrong_cause.sh","must_fail":["mab_db017.sem.insert_authority"]},{"id":"stale_join","path":"task/negative_mutations/stale_join.sh","must_fail":["mab_db017.sem.retract_only_stale"]},{"id":"forged_receipt","path":"task/negative_mutations/forged_receipt.sh","must_fail":["mab_db017.cf.checkpoint_then_authority"]},{"id":"broken_closure","path":"task/negative_mutations/broken_closure.sh","must_fail":["mab_db017.sem.closure"]}]})
    dump(CASE / "private" / "runtime_qualification.json", {"source_task_id":SOURCE_ID,"runtime":"async_rbench.marble_runtime","static_binding_verified":True,"service_execution":"pending","native_evaluator_execution":"pending"})
    dump(CASE / "STATUS.json", {"case_id":CASE_ID,"source_task_id":SOURCE_ID,"status":"materialized_static_validation_pending","native_runtime":"MARBLE database evaluator pending service run"})
    write(CASE / "PROVENANCE.md", f"# {CASE_ID}\n\nSource: `MultiAgentBench` / `{SOURCE_ID}` at `database_main.jsonl:17`.\n\nThis family binds a MARBLE INSERT_LARGE_DATA authority receipt to a persisted native action checkpoint. It reconciles database diagnostic state; it does not reuse bargaining agreement semantics.\n")
    write(CASE / "generate.py", f"from scripts.materialize_mab_state_reconciliation_017 import main\nif __name__ == '__main__': main()\n")
    write(CASE / "oracle.py", f"from async_rbench.docker_case import run_oracle\nif __name__ == '__main__': run_oracle('{CASE_ID}')\n")
    write(CASE / "verify.py", "from async_rbench.docker_case import run_verifier\nif __name__ == '__main__': run_verifier()\n")
    print(CASE)


if __name__ == "__main__":
    main()
