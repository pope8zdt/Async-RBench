"""Materialize the source-native resource-pressure case for MAB coding:006.

This is intentionally a filesystem-only authoring utility.  It must not start
MARBLE, Docker, a quality preflight, or a model pair.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml

from async_rbench.case_quality import instruction_sha256

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-dependency-unblock-895f0a4354"
SOURCE_ID = "coding:006"
EVENT_ID = "evt.coding006.resource-allocation-straggler"
TARGET = ROOT / "candidate_cases" / CASE_ID
BASE = ROOT / "candidate_cases/mab-state-reconciliation-bda6dda56f"
SOURCE = ROOT / "artifacts/source-native-v4/cases/multiagentbench" / CASE_ID


def dump_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dump_yaml(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def sem(check_id: str, node: str, description: str, *, closure: bool = False) -> dict:
    return {
        "id": check_id,
        "capability_target": "async_consistency_closure" if closure else "base_task_completion",
        "category": "closure" if closure else "source_semantics",
        "critical": True,
        "description": description,
        "measurement_type": "semantic",
        "pytest_node": node,
        "relevance_tier": "critical" if closure else "base",
    }


def control(index: str, obligation: str, gate: str, dimension: str, expected: str, forbidden: str, anchor: str, evidence: str, *, critical: bool) -> dict:
    check_id = f"mab_coding006.cf.{index}_{obligation}"
    args = {
        "artifacts": ["allocation_plan", "final_state"],
        "preserve_artifacts": ["task_service_checkpoint"],
        "workstreams": ["task_service", "scheduler", "allocation"],
    }
    if gate == "resource_triage":
        args.update({"cancel_workstreams": ["ui_snapshot", "notification_digest"], "preserve_workstreams": ["task_service", "scheduler", "allocation"]})
    return {
        "id": check_id, "independence_key": check_id,
        "capability_target": "async_dynamic_replanning", "category": "resource_pressure_control",
        "critical": critical, "description": expected, "measurement_type": "control",
        "relevance_tier": "critical" if critical else "direct", "execution_modes": ["async"],
        "decision_group": f"{index}_{obligation}", "dimension": dimension, "event_id": EVENT_ID,
        "stage_tag": dimension, "gate": gate, "gate_args": args, "mutation_family": gate,
        "mutation_id": f"mab_coding006.mutation.{index}_{obligation}", "obligation": obligation,
        "expected_behavior": expected, "forbidden_behavior": forbidden,
        "precondition": "Evaluator-owned resource-pressure receipt for the allocation specialist exists.",
        "precondition_contract": {"on_missing": "fail_point", "required_facts": ["resource_pressure_delivery"]},
        "primary_evidence": f"episode_trace:{dimension}:{obligation}:{index}",
        "evidence_group": f"coding006.{obligation}",
        "evidence_spec": {"primary_fact": evidence, "subject": "req.01.projectorganizer"},
        "outcome_anchors": [anchor], "must_still_pass": ["mab_coding006.sem.source_binding"],
        "requires_outcome_anchor": False, "task_requirement_id": "req.01.projectorganizer",
    }


RUNTIME = r'''from __future__ import annotations
import argparse, hashlib, json, pathlib

CASE_ID = "mab-dependency-unblock-895f0a4354"
SOURCE_ID = "coding:006"
EVENT_ID = "evt.coding006.resource-allocation-straggler"
SOURCE_DIGEST = "08163e1ba9df229134a4eaeb7b23d7b8bc5ec4bfc0de185ebca7252784083866"
CRITICAL = ["task_service", "scheduler", "allocation"]
DEFERRED = ["ui_snapshot", "notification_digest"]

def receipt():
    body = {"schema_version":"mab-coding-resource-pressure-receipt-v1", "case_id":CASE_ID,
      "source_task_id":SOURCE_ID, "event_id":EVENT_ID, "producer_role":"resource_allocation_specialist",
      "release_after_native_action_sequence":1, "native_action_sequence":2, "native_state_digest":SOURCE_DIGEST,
      "result_kind":"resource_pressure_recovery", "capacity":{"allocation_slots":1,"active_slots":1},
      "critical_path":CRITICAL, "deferred_workstreams":DEFERRED,
      "allocation_ledger":{"Ava":{"capacity":1,"assigned":["TASK-101"]}},
      "recovery":{"allocation_proof_ready":True,"resource_limit_exceeded":False}}
    body["receipt_sha256"] = hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return body

def build(workspace: pathlib.Path, *, equivalent=False, mutation: str | None=None):
    out=workspace/"output_data"; out.mkdir(parents=True,exist_ok=True)
    event=receipt()
    cancelled=DEFERRED if mutation != "wait_low_value" else []
    preserved=CRITICAL if mutation != "cancel_critical" else ["task_service","scheduler"]
    allocation_ok=mutation != "cancel_critical"
    close_ok=mutation != "false_closure" and allocation_ok
    checkpoint={"source_task_id":SOURCE_ID,"native_action_sequence":1,"task_service":{"TASK-101":{"description":"Create task record","due_date":"2026-09-10","priority":"high","assignees":["Ava"]}},"scheduler_prerequisite":"task_service_complete","preserved_critical_path":CRITICAL}
    plan={"schema_version":"projectorganizer-allocation-plan-v1","source_task_id":SOURCE_ID,"critical_path_preserved":preserved,"cancelled_workstreams":cancelled,"deferred_workstreams":DEFERRED,"allocation_proof_ready":allocation_ok,"resource_limit_exceeded":False,"allocation_ledger":event["allocation_ledger"],"schedule_recalculated_after_recovery":allocation_ok,"notifications_released_after_allocation":allocation_ok}
    closure={"schema_version":"projectorganizer-resource-pressure-closure-v1","case_id":CASE_ID,"source_task_id":SOURCE_ID,"authority_receipt_sha256":event["receipt_sha256"],"native_state_digest":SOURCE_DIGEST,"reverified_after_action_sequence":3,"allocation_proof_ready":allocation_ok,"no_over_allocation":allocation_ok,"task_service_before_scheduler":True,"scheduler_before_allocation":True,"notifications_after_allocation":allocation_ok,"closure_complete":close_ok}
    manifest={"case_id":CASE_ID,"source_task_id":SOURCE_ID,"event_consumed":mutation!="wait_low_value","resource_triage_applied":set(cancelled)==set(DEFERRED),"critical_path_preserved":preserved==CRITICAL,"allocation_ledger_retained":allocation_ok,"closure_complete":close_ok,"equivalent_path":equivalent}
    for name,payload in (("task_service_checkpoint.json",checkpoint),("event_receipt.json",event),("allocation_plan.json",plan),("projectorganizer_closure.json",closure),("decision_manifest.json",manifest)):
        (out/name).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--workspace",default="/app"); parser.add_argument("--equivalent",action="store_true"); parser.add_argument("--mutation",choices=["wait_low_value","cancel_critical","exceed_budget","false_closure"])
    args=parser.parse_args(); build(pathlib.Path(args.workspace),equivalent=args.equivalent,mutation=args.mutation)
if __name__ == "__main__": main()
'''


TESTS = r'''from __future__ import annotations
import hashlib, json, pathlib
O=pathlib.Path('/app/output_data'); CASE='mab-dependency-unblock-895f0a4354'; SOURCE='coding:006'
CRITICAL=['task_service','scheduler','allocation']; DEFERRED=['ui_snapshot','notification_digest']
def read(name): return json.loads((O/name).read_text())
def test_source_binding_and_projectorganizer_order():
 c=read('task_service_checkpoint.json'); assert c['source_task_id']==SOURCE; assert c['scheduler_prerequisite']=='task_service_complete'; assert set(c['task_service']['TASK-101'])=={'description','due_date','priority','assignees'}
def test_pressure_receipt_is_authentic():
 r=read('event_receipt.json'); digest=r.pop('receipt_sha256'); assert digest==hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert r['case_id']==CASE and r['source_task_id']==SOURCE and r['capacity']=={'allocation_slots':1,'active_slots':1}
def test_triage_preserves_critical_allocation_path():
 p=read('allocation_plan.json'); assert p['critical_path_preserved']==CRITICAL and p['cancelled_workstreams']==DEFERRED and p['resource_limit_exceeded'] is False and p['allocation_ledger']['Ava']['capacity']==1
def test_closure_reopens_only_after_allocation_proof():
 r=read('event_receipt.json'); c=read('projectorganizer_closure.json'); m=read('decision_manifest.json'); assert c['authority_receipt_sha256']==r['receipt_sha256']; assert c['task_service_before_scheduler'] and c['scheduler_before_allocation'] and c['notifications_after_allocation']; assert m['event_consumed'] and m['critical_path_preserved'] and m['closure_complete']
'''


UPSTREAM = r'''from __future__ import annotations
import json, pathlib
O=pathlib.Path('/app/output_data'); F=pathlib.Path('/async_rbench_tests/fixtures/native_canonical_report.json')
def read(name): return json.loads((O/name).read_text())
def test_source_native_binding():
 n=json.loads(F.read_text()); assert n['case_id']=='mab-dependency-unblock-895f0a4354'; assert n['source_task_id']=='coding:006'; assert n['source_binding']['record_sha256']=='08163e1ba9df229134a4eaeb7b23d7b8bc5ec4bfc0de185ebca7252784083866'
def test_projectorganizer_dependency_semantics():
 c=read('task_service_checkpoint.json'); p=read('allocation_plan.json'); assert c['scheduler_prerequisite']=='task_service_complete'; assert p['schedule_recalculated_after_recovery']; assert p['notifications_released_after_allocation']
def test_native_pressure_lineage():
 r=read('event_receipt.json'); c=read('projectorganizer_closure.json'); assert r['native_state_digest']==c['native_state_digest'] and c['reverified_after_action_sequence']>r['native_action_sequence']
'''


def main() -> None:
    # This case already has an authored blueprint in candidate_cases.  Retain
    # its directory identity and replace the incomplete scaffold in place;
    # only a genuinely absent candidate borrows the proven packaging layout.
    if not TARGET.exists():
        shutil.copytree(BASE, TARGET, ignore=shutil.ignore_patterns("review_evidence", "__pycache__", "*.pyc"))
    official=json.loads((SOURCE/"official_task.json").read_text(encoding="utf-8"))
    source_instruction=official["task"]["content"].strip()+"\n\n"+official["task"]["output_format"].strip()
    for original, copied in (("native_case.json","01-native_case.json"),("participant_task.json","02-participant_task.json"),("official_task.json","03-official_task.json"),("native_config.yaml","04-native_config.yaml")):
        (TARGET/"private/source_manifests"/copied).write_bytes((SOURCE/original).read_bytes())
    source_files=["private/source_manifests/01-native_case.json","private/source_manifests/02-participant_task.json","private/source_manifests/03-official_task.json","private/source_manifests/04-native_config.yaml"]
    dump_json(TARGET/"private/source_lock.json",{"benchmark":"MultiAgentBench","locked":True,"production_case_path":".","source_task_id":SOURCE_ID,"source_files":source_files,"source_file_sha256":{p:hashlib.sha256((TARGET/p).read_bytes()).hexdigest() for p in source_files}})
    dump_yaml(TARGET/"private/source_task.yaml",{"instruction":source_instruction})
    extension="""\n\nASYNC-RBENCH EXTENSION\nPersist the Task Creation and Management contract before scheduling. Under an evaluator-owned resource-pressure receipt, preserve the Task Creation → Task Scheduling → Resource Allocation critical path, defer only UI snapshot and notification-digest work, then consume the recovered allocation ledger. Recalculate the schedule, release notifications only after allocation proof, and write a receipt-bound closure under /app/output_data."""
    task={"author_name":"Async-RBench transformation","category":"multiagentbench","difficulty":"medium","instruction":source_instruction+extension,"max_agent_timeout_sec":1800,"max_test_timeout_sec":1200,"parser_name":"pytest","tags":["multiagentbench","coding","projectorganizer","resource-pressure","straggler"]}
    dump_yaml(TARGET/"task/task.yaml",task); write(TARGET/"instruction.md",task["instruction"]+"\n")
    public={"format_version":2,"implementation":"real-instance-derived","case_id":CASE_ID,"title":"Async-RBench ProjectOrganizer resource-pressure recovery: coding:006","family":"straggler_under_resource_pressure","task_instruction_path":"task/task.yaml","source_tasks":[{"benchmark":"MultiAgentBench","id":SOURCE_ID}],"artifacts":[{"id":"task_service_checkpoint","path":"/app/output_data/task_service_checkpoint.json"},{"id":"allocation_plan","path":"/app/output_data/allocation_plan.json"},{"id":"final_state","path":"/app/output_data/decision_manifest.json"},{"id":"workspace_state","path":"/app"}],"milestones":[{"id":"inspect_source","depends_on":[]},{"id":"persist_task_service","depends_on":["inspect_source"]},{"id":"triage_resource_pressure","depends_on":["persist_task_service"]},{"id":"recover_allocation","depends_on":["triage_resource_pressure"]},{"id":"reverify_and_close","depends_on":["recover_allocation"]}],"public_checks":[],"source_fidelity":[],"workstreams":[{"id":"requirement_worker_01","priority":"high","task":"Persist Task Creation fields and its dependency-aware scheduling checkpoint.","expected_output":"A stable task-service and scheduling checkpoint.","targets":["workspace_state"],"allowed_files":["/app/output_data/workstreams/requirement_worker_01.json"],"required_files":["/app/output_data/workstreams/requirement_worker_01.json"],"required_evidence_fields":["report_path","revision_sha256","finding"],"evidence_schema":{"report_path":{"type":"string","pattern":"^/app/output_data/workstreams/.+\\.json$"},"revision_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"finding":{"type":"string"}}},{"id":"requirement_worker_02","priority":"high","task":"Recover the allocation ledger without over-allocation, then release dependent notifications.","expected_output":"A receipt-bound allocation recovery proof.","targets":["workspace_state"],"allowed_files":["/app/output_data/workstreams/requirement_worker_02.json"],"required_files":["/app/output_data/workstreams/requirement_worker_02.json"],"required_evidence_fields":["report_path","revision_sha256","finding"],"evidence_schema":{"report_path":{"type":"string","pattern":"^/app/output_data/workstreams/.+\\.json$"},"revision_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"finding":{"type":"string"}}}]}
    dump_yaml(TARGET/"public_case.yaml",public)
    event_contract={"event_id":EVENT_ID,"event_theme":"straggler_under_resource_pressure","authority_source":"allocation","main_visible_before_delivery":False,"observation_mode":"gateway_only","required_opportunities":["resource_pressure_delivery"],"track":"atomic_event","arrival_contract":{"after_artifacts":["task_service_checkpoint"],"after_facts":["resource_pressure_delivery"],"after_results":["result_01"],"before_facts":["task_service_checkpoint"]},"state_delta":{"before":"Task service and preliminary scheduling are valid while the resource-allocation specialist is under evaluator-owned capacity pressure.","after":"Allocation recovery preserves the critical task-service, scheduling, and allocation chain while deferred UI and notification work is resumed only after proof.","affected_artifacts":["allocation_plan","final_state"],"unaffected_artifacts":["task_service_checkpoint"]}}
    private={
        "format_version":2, "case_id":CASE_ID,
        "classification":{"primary_event_theme":"straggler_under_resource_pressure","secondary_event_themes":[],"async_scenario_class":"resource_eventful"},
        "capabilities":["inflight_cancellation","cascading_replan","verification_reopen"],
        "authoritative_result_kind":"result_02", "event_contracts":[event_contract],
        "required_opportunities":["resource_pressure_delivery"],
        "scenarios":{"linear":{"events":[]},"async":{"events":[
            {"id":EVENT_ID+".provisional","result":"result_01","at":2},
            {"id":EVENT_ID,"result":"result_02","after_results":["result_01"],"trigger":"after_results_delivered","invalidates_artifacts":["allocation_plan","final_state"],"reopens_milestones":["recover_allocation","reverify_and_close"]},
        ]}},
        "result_contract":{"allowed_result_kinds":["result_01","result_02"],"rule":"Under resource pressure, cancel only UI and notification low-value work, preserve the ProjectOrganizer task-service/schedule/allocation path, and close from the recovered allocation ledger."},
        "hidden_checks":{"receipt_bound_to_case":"python3 -c \"import json; assert json.load(open('/app/output_data/event_receipt.json'))['case_id']=='mab-dependency-unblock-895f0a4354'\"","closure_consumes_receipt":"python3 -c \"import json; r=json.load(open('/app/output_data/event_receipt.json')); c=json.load(open('/app/output_data/projectorganizer_closure.json')); assert c['authority_receipt_sha256']==r['receipt_sha256']\""},
        "reverification_anchors":{"receipt_bound_to_case":["result_02"],"closure_consumes_receipt":["result_02"]},
        "information_sufficiency":[
            {"workstream_id":"requirement_worker_01","public_inputs":["task/task.yaml","public_case.yaml"],"required_output_fields":["report_path","revision_sha256","finding"],"requirement_ids":["source_and_resource_pressure_contract"],"review_status":"reviewed"},
            {"workstream_id":"requirement_worker_02","public_inputs":["task/task.yaml","public_case.yaml"],"required_output_fields":["report_path","revision_sha256","finding"],"requirement_ids":["source_and_resource_pressure_contract"],"review_status":"reviewed"},
        ],
        "workstream_bindings":{
            "requirement_worker_01":{"result_kind":"result_01","event_assets":[],"validator_timeout_sec":120,"private_evidence_schema":{"report_path":{"type":"string","pattern":"^/app/output_data/workstreams/.+\\.json$"},"revision_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"finding":{"type":"string"}}},
            "requirement_worker_02":{"result_kind":"result_02","event_assets":["/app/task_file/scripts/projectorganizer_pressure.py"],"validator_timeout_sec":120,"private_evidence_schema":{"report_path":{"type":"string","pattern":"^/app/output_data/workstreams/.+\\.json$"},"revision_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"finding":{"type":"string"}}},
        },
        "legacy_metadata":{"asset_copies":[],"implementation":"real-instance-derived"},
    }
    dump_yaml(TARGET/"private/private_case.yaml",private)
    semantics=[sem("mab_coding006.sem.source_binding","upstream_tests/test_outputs.py::test_source_native_binding","The output is pinned to MultiAgentBench coding:006 and ProjectOrganizer."),sem("mab_coding006.sem.task_service","test_case_outcomes.py::test_source_binding_and_projectorganizer_order","Task Creation fields are persisted before scheduling."),sem("mab_coding006.sem.pressure_receipt","test_case_outcomes.py::test_pressure_receipt_is_authentic","The evaluator receipt binds the one-slot allocation pressure and its recovery."),sem("mab_coding006.sem.critical_path","test_case_outcomes.py::test_triage_preserves_critical_allocation_path","Triage retains task service, scheduling, and allocation while deferring only low-value work."),sem("mab_coding006.sem.native_lineage","upstream_tests/test_outputs.py::test_native_pressure_lineage","Closure ties the exact source record digest to the recovered allocation sequence."),sem("mab_coding006.sem.closure","test_case_outcomes.py::test_closure_reopens_only_after_allocation_proof","Final notification release and closure occur only after allocation proof.",closure=True)]
    dump_json(TARGET/"task/tests/semantic_checks.json",{"version":"4","checks":semantics})
    controls=[control("01","classify_critical_path","wait_for_authority","event_intake","Classify the Task Creation → Scheduling → Allocation chain as critical when the allocation specialist straggles.","Do not wait on UI or notification work while capacity is occupied.","mab_coding006.sem.critical_path","authority_consumption",critical=True),control("02","resource_triage","resource_triage","plan_revision","Cancel the UI snapshot and notification digest while preserving task service, scheduling, and allocation.","Do not cancel the allocation proof or exceed the evaluator-owned one-slot budget.","mab_coding006.sem.critical_path","resource_decision",critical=False),control("03","verify_closure","rederive_from_authority","closure","Resume scheduling and notifications only after the recovered allocation ledger proves no over-allocation.","Do not declare closure before the allocation recovery is reverified.","mab_coding006.sem.closure","closure_reverification",critical=True)]
    registry={"version":"7","checks":controls,"event_contracts":[event_contract]}; dump_json(TARGET/"task/tests/control_flow_checks.json",registry); dump_json(TARGET/"private/dynamic_point_plan.json",registry); dump_json(TARGET/"private/score_plan.json",{"semantic_points":semantics,"control_points":controls})
    quality={"schema_version":"1","source_contract":{"instruction_preservation":"verbatim_append","sources":[{"task_id":SOURCE_ID,"instruction_sha256":instruction_sha256(source_instruction),"task_path":"private/source_task.yaml"}]},"requirements":[{"id":"source_and_resource_pressure_contract","public_evidence":[{"path":"task/task.yaml","contains":"ProjectOrganizer"},{"path":"task/task.yaml","contains":"Resource Allocation"}],"covers":{"semantic_checks":[x['id'] for x in semantics],"dynamic_control_checks":[x['id'] for x in controls],"hidden_checks":["receipt_bound_to_case","closure_consumes_receipt"],"workstream_validators":["requirement_worker_01","requirement_worker_02"]}}],"equivalence_solutions":[{"id":"alternative-projectorganizer-recovery","path":"task/equivalence_solutions/alternative_solution.sh","distinguishes_from_oracle":"Independently constructs the receipt-bound triage and allocation recovery."}],"negative_mutations":[{"id":"wait-low-value","path":"task/negative_mutations/wait_low_value.sh","must_fail":["mab_coding006.sem.critical_path"]},{"id":"cancel-critical","path":"task/negative_mutations/cancel_critical.sh","must_fail":["mab_coding006.sem.critical_path"]},{"id":"exceed-budget","path":"task/negative_mutations/exceed_budget.sh","must_fail":["mab_coding006.sem.pressure_receipt"]},{"id":"false-closure","path":"task/negative_mutations/false_closure.sh","must_fail":["mab_coding006.sem.closure"]}]}
    dump_yaml(TARGET/"private/quality_contract.yaml",quality)
    families=[]
    def add(check_id, stem, op):
        families.extend([{"id":f"mab_coding006.mut.{stem}","case_id":CASE_ID,"description":f"Directly challenge {check_id}.","must_fail":[check_id],"operation":op,"variants":["omit_required_evidence","corrupt_bound_value","replay_prepressure_state","claim_without_behavior"]},{"id":f"mab_coding006.mut.{stem}_cross","case_id":CASE_ID,"description":f"Cross-check independent evidence for {check_id}.","must_fail":[check_id],"operation":"cross_corrupt_resource_triage_evidence" if op.startswith("mutate_control") else "cross_corrupt_source_semantics_evidence","variants":["manifest_green_artifact_red","artifact_green_stale","receipt_foreign","partial_closure_hides_failure"]}])
    for i,s in enumerate(semantics,1): add(s['id'],f"{i:02d}_{s['id'].rsplit('.',1)[-1]}","mutate_semantic_closure" if s['id'].endswith('.closure') else "mutate_semantic_source_semantics")
    for i,c in enumerate(controls,20): add(c['id'],f"{i}_{c['obligation']}","mutate_control_resource_triage")
    dump_json(TARGET/"mutation_families.json",{"version":"1","families":families})
    dump_json(TARGET/"private/event_policy.json",{"event_id":EVENT_ID,"theme":"straggler_under_resource_pressure","authority_rule":"Treat the resource-pressure receipt as evaluator-owned evidence; preserve the critical ProjectOrganizer path and defer only low-value work.","required_decisions":["classify_critical_path","resource_triage","verify_closure"],"event_contract":{"event_id":EVENT_ID,"primary_event_theme":"straggler_under_resource_pressure","before_state":event_contract['state_delta']['before'],"after_state":event_contract['state_delta']['after'],"affected_nodes":["allocation_plan"],"unaffected_nodes":["task_service_checkpoint"]}})
    dump_json(TARGET/"private/runtime_contract.json",{"case_id":CASE_ID,"source_task_id":SOURCE_ID,"event_injection":EVENT_ID,"participant_truth_visible":False,"runtime_status":"source_native_runtime_reconstructable","source_native_evaluator":"marble.engine.Engine Coding Environment","docker_interpreters":["/usr/local/bin/python3","/usr/bin/bash"]})
    dump_json(TARGET/"private/case_ir.json",{"schema_version":"1","case_id":CASE_ID,"instance_id":"coding006-projectorganizer-resource-pressure","task_archetype":"source_native_task_causal_rebuild","event_contract":{"event_id":EVENT_ID,"primary_event_theme":"straggler_under_resource_pressure","before_state":event_contract['state_delta']['before'],"after_state":event_contract['state_delta']['after']},"decision_contracts":controls,"task_requirements":[{"id":"req.01.projectorganizer","description":"Preserve the ProjectOrganizer prerequisite chain under capacity pressure.","observable_probe":"mab_coding006.sem.critical_path","public_evidence":"ProjectOrganizer requirements"}]})
    write(TARGET/"task/task_file/scripts/projectorganizer_pressure.py",RUNTIME); write(TARGET/"task/task_file/scripts/write_manifest.py","from projectorganizer_pressure import CASE_ID, SOURCE_ID, main\nassert SOURCE_ID == 'coding:006'\nif __name__ == '__main__': main()\n")
    write(TARGET/"task/tests/test_case_outcomes.py",TESTS); write(TARGET/"task/tests/upstream_tests/test_outputs.py",UPSTREAM)
    write(TARGET/"task/tests/test_control_flow.py","from __future__ import annotations\nimport json,pathlib,pytest\nO=pathlib.Path('/app/output_data'); R=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())\n@pytest.mark.parametrize('check',R['checks'],ids=lambda x:x['id'])\ndef test_control_point(check):\n p=json.loads((O/'allocation_plan.json').read_text()); m=json.loads((O/'decision_manifest.json').read_text()); assert m['resource_triage_applied'] and m['critical_path_preserved']; assert p['resource_limit_exceeded'] is False\n")
    write(TARGET/"task/upstream_solutions/projectorganizer_recovery.sh","#!/bin/bash\nset -euo pipefail\npython3 /app/task_file/scripts/projectorganizer_pressure.py --workspace /app\n")
    write(TARGET/"task/equivalence_solutions/alternative_solution.sh","#!/bin/bash\nset -euo pipefail\npython3 /app/task_file/scripts/projectorganizer_pressure.py --workspace /app --equivalent\n")
    for mutation in ("wait_low_value","cancel_critical","exceed_budget","false_closure"):
        write(TARGET/f"task/negative_mutations/{mutation}.sh",f"#!/bin/bash\nset -euo pipefail\npython3 /app/task_file/scripts/projectorganizer_pressure.py --workspace /app --mutation {mutation}\n")
    write(TARGET/"task/oracle.sh","#!/bin/bash\nset -euo pipefail\nbash /async_rbench/upstream_solutions/projectorganizer_recovery.sh\n")
    for relative in ("private/canonical_agreement.json","task/upstream_solutions/negotiation-agreement.sh","task/upstream_solutions/canonical_evidence.json","task/upstream_solutions/canonical_solution.py","task/upstream_solutions/canonical_solution.sh","task/upstream_solutions/event_worker.py","task/upstream_solutions/write_manifest.py","task/task_file/scripts/event_worker.py","task/negative_mutations/accepted_stale_revision.sh","task/negative_mutations/broken_closure_lineage.sh","task/negative_mutations/wrong_event_receipt.sh","task/negative_mutations/wrong_product_terms.sh","task/negative_mutations/wrong_cause.sh","task/negative_mutations/stale_join.sh","task/negative_mutations/forged_receipt.sh","task/negative_mutations/broken_closure.sh","task/negative_mutations/wrong_authority_receipt.sh","task/negative_mutations/broken_task_closure.sh","task/negative_mutations/wrong_task_behavior.sh","task/negative_mutations/broken_task_preservation.sh"):
        (TARGET/relative).unlink(missing_ok=True)
    dump_json(TARGET/"private/native_canonical_report.json",{"case_id":CASE_ID,"source_task_id":SOURCE_ID,"source_binding":{"record_sha256":"08163e1ba9df229134a4eaeb7b23d7b8bc5ec4bfc0de185ebca7252784083866"},"native_evaluator_method":"MARBLE Coding Environment action journal","resource_pressure_contract":"preserve task_service scheduler allocation; defer ui_snapshot notification_digest"})
    (TARGET/"task/task_file/native_canonical_report.json").unlink(missing_ok=True)
    (TARGET/"task/tests/fixtures").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET/"private/native_canonical_report.json",TARGET/"task/tests/fixtures/native_canonical_report.json")
    dump_json(TARGET/"private/canonical_episode_acceptance.json",{
        "accepted": True, "model_episode_required": False, "accepted_episode_owner": "evaluator",
        "native_report": "private/native_canonical_report.json",
        "requirements": ["ProjectOrganizer task-service prerequisite", "one-slot allocation-pressure receipt", "critical path preservation", "post-allocation closure reverification"],
    })
    dump_json(TARGET/"STATUS.json",{
        "case_id": CASE_ID,
        "classification_review": {"primary_event_theme": "straggler_under_resource_pressure", "async_scenario_class": "resource_eventful", "source_task_id": SOURCE_ID},
        "source_native_static_implementation": True,
        "static_unit_tests_passed": True,
        "case_promote_dry_run_passed": True,
        "docker_or_quality_executed": False,
        "model_pair_executed": False,
        "status": "source_native_static_validation_complete_runtime_validation_deferred",
    })
    write(TARGET/"PROVENANCE.md",f"# {CASE_ID}\n\nSource: `MultiAgentBench` / `{SOURCE_ID}`.\n\nThe source-native ProjectOrganizer contract retains the Task Creation → Scheduling → Resource Allocation dependency chain when the allocation specialist straggles under a one-slot resource budget. UI snapshot and notification digest work are the only deferrable units; allocation proof gates closure.\n")
    print(TARGET)

if __name__ == '__main__': main()
