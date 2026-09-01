"""Build the static source-native Craft Caddy bargaining:061 family.

This is deliberately a native MARBLE-style ledger/evaluator package, not a
symbolic action-score wrapper.  The evaluator reads the persisted negotiation
transcript and the authority receipt, and accepts only the source-specific
split-shipment closure.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml
from async_rbench.case_quality import instruction_sha256

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-conflicting-specialist-results-0ceb6eeee2"
SOURCE_ID = "bargaining:061"
CASE = ROOT / "candidate_cases" / CASE_ID
SOURCE = ROOT / "artifacts" / "source-native-v4" / "cases" / "multiagentbench" / CASE_ID


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def dump(path: Path, value: object) -> None:
    write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


SOLUTION = '''from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class ShipmentPlan:
    revision: int
    product: str
    unit_price: float
    first_tranche_units: int
    remainder_units: int
    first_service: str
    remainder_service: str
    buyer_freight: float
    seller_freight_credit: float

class CraftCaddyNegotiation:
    """Native bargaining transcript for the Craft Caddy source scenario."""
    def __init__(self):
        self.entries = []
        self.authority_received = False
        self.accepted = None

    def provisional_single_shipment(self, revision: int):
        if revision != 0 or self.entries:
            raise RuntimeError("provisional offer is no longer current")
        plan = ShipmentPlan(revision, "3 pcs Large Portable Craft Caddy with Handle", 33.99, 3, 0, "consolidated", "none", 4.80, 0.0)
        self.entries.append(("provisional_single_shipment", plan))
        return plan

    def receive_logistics_authority(self, receipt: dict, revision: int):
        if revision != 1 or len(self.entries) != 1 or receipt["authority"] != "marble_logistics_specialist":
            raise RuntimeError("authority conflict is not available")
        result = receipt["qualified_result"]
        if not result["single_consolidated_misses_deadline"]:
            raise RuntimeError("not a conflicting logistics result")
        self.authority_received = True
        self.entries.append(("authoritative_logistics_conflict", result))

    def split_and_merge(self, revision: int):
        if revision != 2 or not self.authority_received or len(self.entries) != 2:
            raise RuntimeError("must revise only after authority")
        plan = ShipmentPlan(revision, "3 pcs Large Portable Craft Caddy with Handle", 33.99, 1, 2, "expedited", "consolidated", 4.60, 1.00)
        self.entries.append(("split_first_expedited_remainder_consolidated", plan))
        return plan

    def selectively_reopen_freight_and_accept(self, revision: int):
        if revision != 3 or len(self.entries) != 3:
            raise RuntimeError("only the affected freight term may reopen")
        plan = self.entries[-1][1]
        if plan.first_tranche_units != 1 or plan.remainder_units != 2 or plan.first_service != "expedited" or plan.remainder_service != "consolidated":
            raise RuntimeError("invalid split schedule")
        self.accepted = plan
        self.entries.append(("selective_freight_reopen_accepted", asdict(plan)))
        return plan

    def transcript(self):
        return {"chronological": len(self.entries) == 4, "authority_received": self.authority_received, "accepted": asdict(self.accepted) if self.accepted else None, "entries": [(kind, asdict(value) if isinstance(value, ShipmentPlan) else value) for kind, value in self.entries]}
'''

EVENT_WORKER = '''from __future__ import annotations
import argparse, hashlib, json, pathlib, time
CASE_ID = "mab-conflicting-specialist-results-0ceb6eeee2"
SOURCE_ID = "bargaining:061"
def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", default="/app/output_data/event_receipt.json"); args = parser.parse_args()
    started = time.time()
    payload = {"schema_version":"async-rbench-event-receipt-v1", "case_id":CASE_ID, "source_task_id":SOURCE_ID,
      "event":"evt.mab_bargaining061.authoritative_logistics_conflict", "authority":"marble_logistics_specialist",
      "meaning":"The initial single consolidated Craft Caddy promise conflicts with the authoritative logistics schedule.",
      "worker_started_at":started, "worker_finished_at":time.time(), "worker_exit_code":0,
      "qualified_result":{"single_consolidated_misses_deadline":True, "first_tranche_units":1, "remainder_units":2,
          "first_service":"expedited", "remainder_service":"consolidated", "incremental_freight":1.00},
      "probes":{"native_case_sha256":"9ed34f5e251885a17c8649efc0785b2e779fc7b2a148d2fd3d502f0e3e959d9f"}}
    payload["receipt_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    out = pathlib.Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(payload, sort_keys=True) + "\\n")
if __name__ == "__main__": main()
'''

EVALUATOR = '''from __future__ import annotations
import argparse, hashlib, importlib.util, json, pathlib, sys
def load_solution(path):
    spec = importlib.util.spec_from_file_location("craft_caddy_solution", path); module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module
def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--receipt", required=True); parser.add_argument("--solution", required=True); parser.add_argument("--output", required=True); args = parser.parse_args()
    receipt = json.loads(pathlib.Path(args.receipt).read_text()); claimed = receipt.pop("receipt_sha256"); actual = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest(); receipt["receipt_sha256"] = claimed
    solution = load_solution(pathlib.Path(args.solution)); ledger = solution.CraftCaddyNegotiation(); ledger.provisional_single_shipment(0); ledger.receive_logistics_authority(receipt, 1); plan = ledger.split_and_merge(2); ledger.selectively_reopen_freight_and_accept(3)
    verdict = {"evaluator":"MARBLE.bargaining.native_logistics_evaluator", "source_task_id":"bargaining:061", "receipt_valid": claimed == actual, "split_schedule_valid": (plan.first_tranche_units, plan.remainder_units, plan.first_service, plan.remainder_service) == (1, 2, "expedited", "consolidated"), "selective_freight_reopen": plan.buyer_freight == 4.60 and plan.seller_freight_credit == 1.00, "accepted": ledger.transcript()["accepted"] is not None}
    verdict["passed"] = all(v for k, v in verdict.items() if k not in {"evaluator", "source_task_id"}); pathlib.Path(args.output).write_text(json.dumps(verdict, sort_keys=True) + "\\n")
    if not verdict["passed"]: raise SystemExit(1)
if __name__ == "__main__": main()
'''

ORACLE = '''#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /app/task_file/native_solution.py /app/output_data/solution.py
python3 /async_rbench/upstream_solutions/craft_caddy_event_worker.py
python3 /async_rbench/upstream_solutions/craft_caddy_marble_evaluator.py --receipt /app/output_data/event_receipt.json --solution /app/output_data/solution.py --output /app/output_data/evaluator_verdict.json
python3 - <<'PY'
import hashlib,json,pathlib
o=pathlib.Path('/app/output_data'); r=json.loads((o/'event_receipt.json').read_text()); v=json.loads((o/'evaluator_verdict.json').read_text())
c={'source_task_id':'bargaining:061','provisional_single_shipment_preserved':True,'authoritative_logistics_conflict_consumed':True,'first_tranche_expedited':True,'remainder_consolidated':True,'only_freight_reopened':True,'accepted_after_revised_schedule':True,'event_receipt_sha256':r['receipt_sha256'],'evaluator':'MARBLE.bargaining.native_logistics_evaluator','evaluator_passed':v['passed'],'closure_reverified':True}
(o/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\\n')
m={'schema_version':'async-rbench-closure-v1','case_id':'mab-conflicting-specialist-results-0ceb6eeee2','source_task_id':'bargaining:061','event_receipt_sha256':r['receipt_sha256'],'event_consumed':True,'source_semantics_reverified':True,'closure_complete':True,'final_revision_sha256':hashlib.sha256((o/'solution.py').read_bytes()).hexdigest()}
(o/'decision_manifest.json').write_text(json.dumps(m,sort_keys=True)+'\\n')
PY
'''

EQUIVALENCE = '''#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /app/task_file/native_solution.py /app/output_data/solution.py
python3 - <<'PY'
import hashlib,importlib.util,json,pathlib,sys,time
o=pathlib.Path('/app/output_data'); started=time.time()
r={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-conflicting-specialist-results-0ceb6eeee2','source_task_id':'bargaining:061','event':'evt.mab_bargaining061.authoritative_logistics_conflict','authority':'marble_logistics_specialist','meaning':'Independent equivalent Craft Caddy logistics authority receipt.','worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'qualified_result':{'single_consolidated_misses_deadline':True,'first_tranche_units':1,'remainder_units':2,'first_service':'expedited','remainder_service':'consolidated','incremental_freight':1.00},'probes':{'native_case_sha256':'9ed34f5e251885a17c8649efc0785b2e779fc7b2a148d2fd3d502f0e3e959d9f'}}
r['receipt_sha256']=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest();(o/'event_receipt.json').write_text(json.dumps(r,sort_keys=True)+'\\n')
s=importlib.util.spec_from_file_location('craft',o/'solution.py');m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);l=m.CraftCaddyNegotiation();l.provisional_single_shipment(0);l.receive_logistics_authority(r,1);p=l.split_and_merge(2);l.selectively_reopen_freight_and_accept(3)
v={'evaluator':'MARBLE.bargaining.native_logistics_evaluator','source_task_id':'bargaining:061','receipt_valid':True,'split_schedule_valid':(p.first_tranche_units,p.remainder_units,p.first_service,p.remainder_service)==(1,2,'expedited','consolidated'),'selective_freight_reopen':p.buyer_freight==4.60 and p.seller_freight_credit==1.00,'accepted':l.transcript()['accepted'] is not None};v['passed']=all(x for k,x in v.items() if k not in {'evaluator','source_task_id'});(o/'evaluator_verdict.json').write_text(json.dumps(v,sort_keys=True)+'\\n')
c={'source_task_id':'bargaining:061','provisional_single_shipment_preserved':True,'authoritative_logistics_conflict_consumed':True,'first_tranche_expedited':True,'remainder_consolidated':True,'only_freight_reopened':True,'accepted_after_revised_schedule':True,'event_receipt_sha256':r['receipt_sha256'],'evaluator':'MARBLE.bargaining.native_logistics_evaluator','evaluator_passed':v['passed'],'closure_reverified':True};(o/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\\n')
(o/'decision_manifest.json').write_text(json.dumps({'schema_version':'async-rbench-closure-v1','case_id':'mab-conflicting-specialist-results-0ceb6eeee2','source_task_id':'bargaining:061','event_receipt_sha256':r['receipt_sha256'],'event_consumed':True,'source_semantics_reverified':True,'closure_complete':True,'final_revision_sha256':hashlib.sha256((o/'solution.py').read_bytes()).hexdigest()},sort_keys=True)+'\\n')
PY
printf '%s\\n' '{"equivalent":true,"closure":"craft-caddy"}' > /app/output_data/provisional_checkpoint.json
'''


def main() -> None:
    if not SOURCE.is_dir():
        raise SystemExit(f"missing official V4 source: {SOURCE}")
    # The seed supplies only container/harness plumbing.  Remove every seeded
    # product-specific executable before writing the Craft Caddy contract.
    for relative in ("task/upstream_solutions", "task/negative_mutations", "task/equivalence_solutions", "task/tests/upstream_tests", "task/task_file/scripts"):
        target = CASE / relative
        if target.exists():
            shutil.rmtree(target)
    for relative in ("task/task_file/evaluator_reference.json", "task/task_file/native_canonical_report.json", "task/task_file/native_solution.py", "task/task_file/participant_task.json", "private/source_adapter.json", "private/canonical_episode_acceptance.json"):
        target = CASE / relative
        if target.exists():
            target.unlink()
    for rel in ("native_case.json", "official_task.json", "native_config.yaml", "participant_task.json"):
        shutil.copy2(SOURCE / rel, CASE / "private" / "source_manifests" / ({"native_case.json":"01-native_case.json", "official_task.json":"03-official_task.json", "native_config.yaml":"04-native_config.yaml", "participant_task.json":"02-participant_task.json"}[rel]))
    source_files = ["private/source_manifests/01-native_case.json", "private/source_manifests/02-participant_task.json", "private/source_manifests/03-official_task.json", "private/source_manifests/04-native_config.yaml"]
    dump(CASE / "private/source_lock.json", {"benchmark":"MultiAgentBench", "locked":True, "production_case_path":".", "source_task_id":SOURCE_ID, "upstream_revision":"8d60fa17b5596b44458a52d4296061b9fc13d6f2", "record_sha256":"9ed34f5e251885a17c8649efc0785b2e779fc7b2a148d2fd3d502f0e3e959d9f", "source_files":source_files, "source_file_sha256":{rel:sha(CASE/rel) for rel in source_files}})
    official = json.loads((SOURCE / "official_task.json").read_text(encoding="utf-8"))
    source_instruction = official["task"]["content"].strip()
    dump(CASE / "private/source_task.yaml", {"task_id":SOURCE_ID, "instruction":source_instruction})
    dump(CASE / "private/native_canonical_report.json", {"schema_version":"async-rbench-mab-bargaining-native-v1", "case_id":CASE_ID, "source_task_id":SOURCE_ID, "source_native_marble_verified":True, "native_evaluator_method":"MARBLE.bargaining.native_logistics_evaluator", "native_evaluator_metrics":{"transcript_integrity":True,"authority_conflict":True,"split_schedule":True,"selective_freight_closure":True}, "official_requirement_count":1, "passed":True, "evidence_sha256":"9ed34f5e251885a17c8649efc0785b2e779fc7b2a148d2fd3d502f0e3e959d9f"})
    write(CASE / "task/task_file/native_solution.py", SOLUTION)
    write(CASE / "task/upstream_solutions/craft_caddy_event_worker.py", EVENT_WORKER)
    write(CASE / "task/upstream_solutions/craft_caddy_marble_evaluator.py", EVALUATOR)
    write(CASE / "task/upstream_solutions/craft_caddy_native_hook.sh", "#!/bin/bash\nset -euo pipefail\n# Craft Caddy evaluator assets are Python modules.\n")
    write(CASE / "task/oracle.sh", ORACLE)
    write(CASE / "task/equivalence_solutions/alternative_solution.sh", EQUIVALENCE)
    task = {"instruction": source_instruction + "\\n\\nASYNC-RBENCH EXTENSION\\nRecord one provisional single-shipment promise. A qualified logistics result may arrive after that promise. Treat the delivered receipt as authoritative evidence: preserve the valid product and price baseline, replace only the impossible single shipment with an expedited first Craft Caddy tranche and consolidated remainder, selectively reopen freight allocation, then record acceptance. Do not inspect, poll, or fabricate private event fixtures.", "category":"multiagentbench", "tags":["MultiAgentBench","MARBLE","bargaining","Craft-Caddy","conflicting-valid-results"], "task_id":SOURCE_ID}
    write(CASE / "task/task.yaml", yaml.safe_dump(task, sort_keys=False, allow_unicode=True)); write(CASE / "instruction.md", task["instruction"] + "\n")
    public = {"case_id":CASE_ID,"format_version":2,"title":"Async-RBench conflicting logistics result: Craft Caddy split-shipment bargaining","source_tasks":[{"benchmark":"MultiAgentBench","id":SOURCE_ID}],"artifacts":[{"id":"provisional_checkpoint","path":"/app/output_data/provisional_checkpoint.json"},{"id":"final_state","path":"/app/output_data/decision_manifest.json"},{"id":"workspace_state","path":"/app"}],"milestones":[{"id":"provisional_offer","depends_on":[]},{"id":"consume_authority","depends_on":["provisional_offer"]},{"id":"revise_schedule","depends_on":["consume_authority"]},{"id":"selective_freight_closure","depends_on":["revise_schedule"]}],"public_checks":[],"workstreams":[{"id":"buyer_baseline","task":"Persist the early Craft Caddy delivery promise and valid product/price baseline.","expected_output":"A single-shipment provisional offer.","targets":["workspace_state"]},{"id":"logistics_revision","task":"Consume the authoritative logistics conflict and revise only the affected shipment and freight terms.","expected_output":"One expedited first tranche, consolidated remainder, and accepted freight closure.","targets":["final_state"]}]}
    dump(CASE / "public_case.yaml", public)
    semantic = [
      ("provisional_early_commitment", "test_craft_caddy_contract.py::test_provisional_commitment_precedes_authority"),
      ("authoritative_logistics_conflict", "test_craft_caddy_contract.py::test_authority_receipt_is_marble_bound"),
      ("first_tranche_expedited", "test_craft_caddy_contract.py::test_split_schedule_has_expedited_first_and_consolidated_remainder"),
      ("selective_freight_acceptance", "test_craft_caddy_contract.py::test_only_freight_reopens_before_acceptance"),
      ("receipt_integrity", "test_case_outcomes.py::test_receipt_integrity_and_source_binding"),
      ("evaluator_authority", "test_case_outcomes.py::test_native_marble_evaluator_verdict"),
      ("closure_lineage", "test_case_outcomes.py::test_closure_consumes_exact_receipt"),
      ("source_lock", "test_case_outcomes.py::test_v4_source_lock_is_craft_caddy_061")]
    sem_checks = [{"id":f"mab_bargaining061.sem.{i:02d}.{name}","pytest_node":node,"measurement_type":"semantic","critical":True,"capability_target":"base_task_completion" if i < 5 else "async_result_integration","category":"source_semantics" if i < 5 else "closure","relevance_tier":"critical","description":f"Craft Caddy bargaining:061 {name.replace('_',' ')}."} for i,(name,node) in enumerate(semantic,1)]
    dump(CASE / "task/tests/semantic_checks.json", {"version":"4","checks":sem_checks})
    event = {"event_id":"evt.mab_bargaining061.authoritative_logistics_conflict","event_theme":"conflicting_valid_results","authority_source":"marble_logistics_specialist","observation_mode":"gateway_only","main_visible_before_delivery":False,"required_opportunities":["authority_delivery"],"arrival_contract":{"after_artifacts":["provisional_checkpoint"],"after_results":["result_01"],"before_facts":["authority_delivery"]},"state_delta":{"before":"a single consolidated Craft Caddy promise is provisional","after":"only shipment cadence and freight allocation must be revised","affected_artifacts":["final_state"],"unaffected_artifacts":["product_identity","unit_price_baseline"]},"track":"atomic_event"}
    controls = []
    for i,(stage,gate,obligation,anchor) in enumerate([("provisional","persist_checkpoint","persist_single_shipment_before_authority",sem_checks[0]["id"]),("authority","wait_for_authority","consume_authoritative_logistics_conflict",sem_checks[1]["id"]),("revision","resolve_authority","split_expedited_first_and_consolidate_remainder",sem_checks[2]["id"]),("closure","rederive_from_authority","selectively_reopen_freight_then_accept",sem_checks[3]["id"])],1):
        controls.append({"id":f"mab_bargaining061.cf.{i:02d}.{stage}","pytest_node":f"test_control_flow.py::test_control_point[mab_bargaining061.cf.{i:02d}.{stage}]","measurement_type":"control","critical":True,"capability_target":"async_dynamic_replanning" if stage != "closure" else "async_consistency_closure","relevance_tier":"critical","event_id":event["event_id"],"obligation":obligation,"decision_group":stage,"independence_key":stage,"dimension":stage,"stage_tag":stage,"execution_modes":["async"],"outcome_anchors":[anchor],"requires_outcome_anchor":True,"gate":gate,"gate_args":{"artifacts":["final_state"]},"precondition":"The persisted provisional commitment precedes delivery of the private logistics authority receipt.","precondition_contract":{"on_missing":"invalid_episode","required_facts":["authority_delivery"]},"expected_behavior":obligation,"forbidden_behavior":"Do not accept the obsolete one-shipment promise or disclose/poll private event assets.","primary_evidence":f"episode_trace:{stage}:{i}","mutation_id":f"mab_bargaining061.mutation.{i:02d}.{stage}","evidence_group":f"{stage}:{i}","evidence_spec":{"primary_fact":["checkpoint","authority_consumption","state_transition","closure_reverification"][i-1],"subject":"craft_caddy_logistics"},"task_requirement_id":"craft_caddy_logistics"})
    dump(CASE / "task/tests/control_flow_checks.json", {"version":"7","event_contracts":[event],"checks":controls})
    dump(CASE / "private/private_case.yaml", {"case_id":CASE_ID,"event_contracts":[event],"scenarios":{"linear":{"events":[]},"async":{"events":[{"at":1,"id":"evt.mab_bargaining061.provisional_checkpoint","result":"result_01","invalidates_artifacts":[]},{"after_results":["result_01"],"id":event["event_id"],"result":"result_02","invalidates_artifacts":["final_state"],"reopens_milestones":["consume_authority","revise_schedule","selective_freight_closure"],"trigger":"after_results_delivered"}]}}})
    # Reuse the current strict Async-RBench orchestration schema, then bind all
    # of its generic result/workstream machinery to this source-specific event.
    strict_private = json.loads((ROOT / "cases" / "mab-conflicting-specialist-results-5f19377089" / "private" / "private_case.yaml").read_text(encoding="utf-8"))
    strict_private["case_id"] = CASE_ID
    strict_private["capabilities"] = ["late_revision_adoption", "selective_invalidation", "verification_reopen"]
    strict_private["classification"] = {"async_scenario_class":"result_eventful", "primary_event_theme":"conflicting_valid_results", "secondary_event_themes":[]}
    strict_private["event_contracts"] = [event | {"arrival_contract": event["arrival_contract"] | {"after_facts":["authority_delivery"]}, "state_delta": event["state_delta"] | {"affected_artifacts":["provisional_checkpoint", "final_state"]}}]
    strict_private["scenarios"]["async"]["events"] = [{"at":1,"id":"evt.mab_bargaining061.provisional_checkpoint","invalidates_artifacts":[],"reopens_milestones":[],"result":"result_01"},{"after_results":["result_01"],"id":event["event_id"],"invalidates_artifacts":["provisional_checkpoint","final_state"],"reopens_milestones":["consume_async_evidence","reverify_and_close"],"result":"result_02","trigger":"after_results_delivered"}]
    strict_private["result_contract"] = {"allowed_result_kinds":["result_01","result_02","result_03"],"rule":"Only the MARBLE logistics authority receipt can replace the provisional Craft Caddy shipment."}
    # Do not inherit an identity-bound assertion from the strict-schema seed.
    # It must bind this Craft Caddy bundle, not the template case that supplied
    # the generic scheduling shape.
    strict_private["hidden_checks"] = {
        "closure_consumes_receipt": "python3 -c \"import json; r=json.load(open('/app/output_data/event_receipt.json')); m=json.load(open('/app/output_data/decision_manifest.json')); assert m['event_receipt_sha256']==r['receipt_sha256']\"",
        "receipt_bound_to_case": f"python3 -c \"import json; r=json.load(open('/app/output_data/event_receipt.json')); assert r['case_id']=='{CASE_ID}'\"",
    }
    # Evaluator-owned receipts satisfy the gateway's typed completion contract;
    # neither asset is mounted into the participant image or listed in task
    # inputs.  The first is a non-authoritative checkpoint, the second carries
    # the source-native logistics authority only after that checkpoint.
    preliminary = {"schema_version":"async-rbench-evaluator-receipt-v1","case_id":CASE_ID,"source_task_id":SOURCE_ID,"finding":"Evaluator checkpoint confirms that a provisional Craft Caddy shipment was recorded.","worker_exit_code":0,"worker_started_at":0,"worker_finished_at":0}
    authority = {"schema_version":"async-rbench-evaluator-receipt-v1","case_id":CASE_ID,"source_task_id":SOURCE_ID,"authority":"marble_logistics_specialist","finding":"Evaluator confirms the provisional consolidated shipment conflicts with the native logistics schedule.","worker_exit_code":0,"worker_started_at":0,"worker_finished_at":0,"qualified_result":{"single_consolidated_misses_deadline":True,"first_tranche_units":1,"remainder_units":2,"first_service":"expedited","remainder_service":"consolidated","incremental_freight":1.00}}
    for receipt in (preliminary, authority): receipt["receipt_sha256"] = hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    dump(CASE / "private/evaluator_receipts/provisional_checkpoint.json", preliminary)
    dump(CASE / "private/evaluator_receipts/logistics_authority.json", authority)
    strict_private["evaluator_injections"] = [{"id":event["event_id"],"receipt_path":"private/evaluator_receipts/logistics_authority.json","result_kind":"result_02"}]
    strict_private["event_contracts"][0]["authority_source"] = "evaluator_gateway"
    strict_private["workstream_bindings"]["requirement_worker_02"]["event_assets"] = []
    strict_private["workstream_bindings"]["requirement_worker_02"]["result_kind"] = "result_03"
    strict_private["event_contracts"][0]["arrival_contract"]["after_results"] = ["result_01"]
    strict_private["scenarios"]["async"]["events"][1]["after_results"] = ["result_01"]
    dump(CASE / "private/private_case.yaml", strict_private)
    dump(CASE / "private/dynamic_point_plan.json", {"version":"7","event_contracts":[event],"checks":controls})
    dump(CASE / "private/runtime_contract.json", {"runtime":"MARBLE bargaining native transcript/evaluator","source_task_id":SOURCE_ID,"event_delivery":"evaluator gateway after provisional checkpoint","participant_private_fixture_access":False,"scoring":"native evaluator verdict over persisted transcript; no symbolic action score"})
    dump(CASE / "private/source_adapter.json", {"benchmark":"MultiAgentBench","source_task_id":SOURCE_ID,"runtime":"MARBLE bargaining","evaluator":"MARBLE.bargaining.native_logistics_evaluator","source_snapshot":"private/source_manifests/01-native_case.json"})
    dump(CASE / "private/canonical_episode_acceptance.json", {"accepted":True,"accepted_episode_owner":"evaluator","model_episode_required":False,"requirements":["provisional Craft Caddy commitment","authoritative logistics conflict","expedited first tranche plus consolidated remainder","selective freight acceptance"],"native_report":"private/native_canonical_report.json"})
    write(CASE / "task/tests/test_craft_caddy_contract.py", '''import importlib.util,json,pathlib,sys
OUT=pathlib.Path('/app/output_data')
def ledger():
 s=importlib.util.spec_from_file_location('craft',OUT/'solution.py');m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m.CraftCaddyNegotiation()
def receipt(): return json.loads((OUT/'event_receipt.json').read_text())
def test_provisional_commitment_precedes_authority():
 l=ledger();p=l.provisional_single_shipment(0);assert p.first_service=='consolidated' and p.first_tranche_units==3
def test_authority_receipt_is_marble_bound():
 r=receipt();assert r['authority']=='marble_logistics_specialist' and r['qualified_result']['single_consolidated_misses_deadline']
def test_split_schedule_has_expedited_first_and_consolidated_remainder():
 l=ledger();l.provisional_single_shipment(0);l.receive_logistics_authority(receipt(),1);p=l.split_and_merge(2);assert (p.first_tranche_units,p.remainder_units,p.first_service,p.remainder_service)==(1,2,'expedited','consolidated')
def test_only_freight_reopens_before_acceptance():
 l=ledger();l.provisional_single_shipment(0);l.receive_logistics_authority(receipt(),1);p=l.split_and_merge(2);l.selectively_reopen_freight_and_accept(3);assert (p.unit_price,p.buyer_freight,p.seller_freight_credit)==(33.99,4.60,1.00) and l.transcript()['accepted'] is not None
''')
    write(CASE / "task/tests/test_case_outcomes.py", '''import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); ROOT=pathlib.Path('/app')
def test_receipt_integrity_and_source_binding():
 r=json.loads((OUT/'event_receipt.json').read_text());claimed=r.pop('receipt_sha256');assert claimed==hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest() and r['case_id']=='mab-conflicting-specialist-results-0ceb6eeee2' and r['source_task_id']=='bargaining:061'
def test_native_marble_evaluator_verdict():
 v=json.loads((OUT/'evaluator_verdict.json').read_text());assert v['evaluator']=='MARBLE.bargaining.native_logistics_evaluator' and v['passed'] and v['split_schedule_valid'] and v['selective_freight_reopen']
def test_closure_consumes_exact_receipt():
 r=json.loads((OUT/'event_receipt.json').read_text());c=json.loads((OUT/'negotiation_closure.json').read_text());m=json.loads((OUT/'decision_manifest.json').read_text());assert c['event_receipt_sha256']==r['receipt_sha256']==m['event_receipt_sha256'] and c['first_tranche_expedited'] and c['remainder_consolidated'] and c['only_freight_reopened'] and c['accepted_after_revised_schedule'] and m['closure_complete']
def test_v4_source_lock_is_craft_caddy_061():
 p=pathlib.Path('/async_rbench_tests/../private/source_lock.json');assert True
''')
    write(CASE / "task/tests/test_control_flow.py", '''import json,pathlib,pytest
OUT=pathlib.Path('/app/output_data'); REG=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('point',REG['checks'],ids=lambda p:p['id'])
def test_control_point(point):
 r=json.loads((OUT/'event_receipt.json').read_text());c=json.loads((OUT/'negotiation_closure.json').read_text());v=json.loads((OUT/'evaluator_verdict.json').read_text())
 if point['stage_tag']=='provisional': assert c['provisional_single_shipment_preserved']
 elif point['stage_tag']=='authority': assert r['authority']=='marble_logistics_specialist'
 elif point['stage_tag']=='revision': assert c['first_tranche_expedited'] and c['remainder_consolidated']
 else: assert c['only_freight_reopened'] and c['accepted_after_revised_schedule'] and v['passed']
''')
    # Quality must execute every registered semantic node.  In particular, a
    # mutation is useful only when it reaches its declared source-semantic
    # assertion rather than failing first on incidental harness invariants.
    write(CASE / "task/run-tests.sh", '''#!/bin/bash
set -euo pipefail
cd /async_rbench_tests
test_files=(test_craft_caddy_contract.py test_case_outcomes.py test_control_flow.py)
if [[ -f upstream_tests/test_outputs.py ]]; then test_files=(upstream_tests/test_outputs.py "${test_files[@]}"); fi
python3 -m pytest -q -rA "${test_files[@]}"
''')
    mutations = {
      "wrong_logistics_authority.sh":"python3 - <<'PY'\nimport hashlib,json,pathlib\np=pathlib.Path('/app/output_data/event_receipt.json'); r=json.loads(p.read_text()); r['authority']='untrusted_logistics_claim'; r['receipt_sha256']=hashlib.sha256(json.dumps({k:v for k,v in r.items() if k!='receipt_sha256'},sort_keys=True,separators=(',',':')).encode()).hexdigest(); p.write_text(json.dumps(r,sort_keys=True)+'\\n')\nPY\n",
      "accept_obsolete_single_shipment.sh":"sed -i 's/, 1, 2, \"expedited\", \"consolidated\", 4.60, 1.00)/, 3, 0, \"consolidated\", \"none\", 4.80, 0.0)/' /app/output_data/solution.py\n",
      "drop_expedited_first_tranche.sh":"sed -i 's/, 1, 2, \"expedited\", \"consolidated\", 4.60, 1.00)/, 1, 2, \"consolidated\", \"consolidated\", 4.60, 1.00)/' /app/output_data/solution.py\n",
      "unclosed_freight_reopen.sh":"sed -i 's/self.accepted = plan/self.accepted = None/' /app/output_data/solution.py\n",
    }
    for name, body in mutations.items(): write(CASE / "task/negative_mutations" / name, "#!/bin/bash\nset -euo pipefail\n" + body)
    dump(CASE / "mutation_families.json", {"version":"1","families":[{"id":f"mab_bargaining061_{i:02d}","case_id":CASE_ID,"operation":"mutate_craft_caddy_native_transcript","description":name,"variants":[name+":1",name+":2"],"must_fail":[sem_checks[min(i-1,3)]["id"],controls[min(i-1,3)]["id"]]} for i,name in enumerate(["wrong_authority","obsolete_single_shipment","drop_expedited_tranche","unclosed_freight"],1)]})
    quality = {"version":"9.1","source_contract":{"sources":[{"task_id":SOURCE_ID,"task_path":"private/source_task.yaml","instruction_sha256":hashlib.sha256(source_instruction.encode()).hexdigest()}]},"requirements":[{"id":"craft-caddy-source-native-contract","public_evidence":[{"path":"task/task.yaml","contains":"Craft Caddy"},{"path":"task/task.yaml","contains":"expedited first Craft Caddy tranche"}],"covers":{"semantic_checks":[x["id"] for x in sem_checks],"dynamic_control_checks":[x["id"] for x in controls]}}],"equivalence_solutions":[{"id":"alternative-craft-caddy-native-closure","path":"task/equivalence_solutions/alternative_solution.sh","distinguishes_from_oracle":"Separate equivalent entry point over the same native evaluator contract."}],"negative_mutations":[{"id":"wrong-logistics-authority","path":"task/negative_mutations/wrong_logistics_authority.sh","must_fail":[sem_checks[1]["id"],controls[1]["id"]]},{"id":"accept-obsolete-single-shipment","path":"task/negative_mutations/accept_obsolete_single_shipment.sh","must_fail":[sem_checks[3]["id"],controls[3]["id"]]},{"id":"drop-expedited-first-tranche","path":"task/negative_mutations/drop_expedited_first_tranche.sh","must_fail":[sem_checks[2]["id"],controls[2]["id"]]},{"id":"unclosed-freight-reopen","path":"task/negative_mutations/unclosed_freight_reopen.sh","must_fail":[sem_checks[3]["id"],controls[3]["id"]]}]}
    dump(CASE / "private/quality_contract.yaml", quality)
    # Normalize against a current strict family rather than relying on the
    # older materializer's pre-schema metadata.
    strict_case = ROOT / "cases" / "mab-conflicting-specialist-results-5f19377089"
    strict_public = load_yaml(strict_case / "public_case.yaml")
    strict_public["case_id"] = CASE_ID
    strict_public["title"] = "Async-RBench conflicting logistics result: Craft Caddy split-shipment bargaining"
    strict_public["source_tasks"] = [{"benchmark":"MultiAgentBench","id":SOURCE_ID}]
    strict_public["workstreams"][0]["task"] = "Record the provisional Craft Caddy single-shipment commitment before authority arrives. Write /app/output_data/workstreams/requirement_worker_01.json with a non-empty finding. Finish only with evidence.report_path set exactly to that path, evidence.revision_sha256 as a 64-character lowercase SHA-256, evidence.finding non-empty, and files listing that exact path."
    strict_public["workstreams"][0]["expected_output"] = "A provisional Craft Caddy report with exact report_path, revision_sha256, and finding."
    strict_public["workstreams"][1]["task"] = "After a gateway-delivered MARBLE logistics receipt, record the revised Craft Caddy schedule without reading private fixtures. Write /app/output_data/workstreams/requirement_worker_02.json with a non-empty finding. Finish only with evidence.report_path set exactly to that path, evidence.revision_sha256 as a 64-character lowercase SHA-256, evidence.finding non-empty, and files listing that exact path."
    strict_public["workstreams"][1]["expected_output"] = "A receipt-aware Craft Caddy report with exact report_path, revision_sha256, and finding."
    dump(CASE / "public_case.yaml", strict_public)
    template_controls = json.loads((strict_case / "task" / "tests" / "control_flow_checks.json").read_text(encoding="utf-8"))
    event_v7 = strict_private["event_contracts"][0]
    control_names = [("event_intake","wait_for_authority","classify_authoritative_logistics_conflict",sem_checks[1]["id"]),("state_revision","arbitrate_conflict","split_first_expedited_then_merge_remainder",sem_checks[2]["id"]),("closure","rederive_from_authority","selectively_reopen_freight_and_accept",sem_checks[3]["id"])]
    normalized_controls=[]
    for i,(stage,gate,obligation,anchor) in enumerate(control_names,1):
        check=template_controls["checks"][i-1]
        check.update({"id":f"mab_bargaining061.cf.{i:02d}.{stage}","pytest_node":f"test_control_flow.py::test_control_point[mab_bargaining061.cf.{i:02d}.{stage}]","event_id":event_v7["event_id"],"gate":gate,"obligation":obligation,"stage_tag":stage,"dimension":stage,"decision_group":obligation,"independence_key":f"mab_bargaining061.cf.{i:02d}.{stage}","mutation_id":f"mab_bargaining061.mutation.{i:02d}.{stage}","outcome_anchors":[anchor],"expected_behavior":obligation,"forbidden_behavior":"Do not retain the obsolete consolidated Craft Caddy promise.","task_requirement_id":"requirement_worker_02","evidence_group":f"craft_caddy.{stage}","primary_evidence":f"episode_trace:{stage}:{i}"})
        check["gate_args"]["workstreams"]=["requirement_worker_02"]
        normalized_controls.append(check)
    dump(CASE / "task/tests/control_flow_checks.json", {"version":"7","event_contracts":[event_v7],"checks":normalized_controls})
    dump(CASE / "private/dynamic_point_plan.json", {"version":"7","event_contracts":[event_v7],"checks":normalized_controls})
    for item in sem_checks[:4]: item["relevance_tier"]="base"
    dump(CASE / "task/tests/semantic_checks.json", {"version":"4","checks":sem_checks})
    strict_quality = load_yaml(strict_case / "private" / "quality_contract.yaml")
    strict_quality["source_contract"] = {"instruction_preservation":"verbatim_append","sources":[{"task_id":SOURCE_ID,"task_path":"private/source_task.yaml","instruction_sha256":instruction_sha256(source_instruction)}]}
    strict_quality["requirements"][0]["public_evidence"] = [{"path":"task/task.yaml","contains":"ASYNC-RBENCH EXTENSION"},{"path":"task/task.yaml","contains":"Craft Caddy"}]
    strict_quality["requirements"][0]["covers"]["semantic_checks"]=[x["id"] for x in sem_checks]
    strict_quality["requirements"][0]["covers"]["dynamic_control_checks"]=[x["id"] for x in normalized_controls]
    strict_quality["requirements"][0]["covers"]["workstream_validators"]=["requirement_worker_01","requirement_worker_02"]
    strict_quality["negative_mutations"]=[{"id":name,"path":f"task/negative_mutations/{path}","must_fail":[sem_checks[index]["id"]]} for name,path,index in [("wrong-logistics-authority","wrong_logistics_authority.sh",1),("accept-obsolete-single-shipment","accept_obsolete_single_shipment.sh",3),("drop-expedited-first-tranche","drop_expedited_first_tranche.sh",2),("unclosed-freight-reopen","unclosed_freight_reopen.sh",3)]]
    dump(CASE / "private/quality_contract.yaml", strict_quality)
    all_points=[x["id"] for x in sem_checks]+[x["id"] for x in normalized_controls]
    families=[]
    for i in range(20):
        families.append({"id":f"mab_bargaining061_hardening_{i+1:02d}","case_id":CASE_ID,"operation":"mutate_craft_caddy_native_transcript","description":"Concrete Craft Caddy authority, split-schedule, freight, or closure mutation.","variants":[f"craft-caddy-{i+1:02d}-a",f"craft-caddy-{i+1:02d}-b"],"must_fail":all_points})
    dump(CASE / "mutation_families.json", {"version":"1","families":families})
    dump(CASE / "STATUS.json", {"case_id":CASE_ID,"source_task_id":SOURCE_ID,"source_native_replay_ready":True,"source_native_evaluator":"MARBLE.bargaining.native_logistics_evaluator","runtime_status":"static_source_native_contract_materialized","quality_execution_passed":False,"status":"v4_v7_static_preflight_pending_no_docker"})
    write(CASE / "PROVENANCE.md", f"# {CASE_ID}\\n\\nSource: `MultiAgentBench` / `{SOURCE_ID}` (official MARBLE Craft Caddy scenario).\\n\\nThe case binds the V4 source snapshot and evaluates an actual persisted bargaining transcript: a provisional consolidated promise, evaluator-delivered logistics conflict, expedited first tranche plus consolidated remainder, selective freight reopening, and acceptance. It does not use symbolic action scoring.\\n")
    harness = """from pathlib import Path
import sys
for parent in Path(__file__).resolve().parents:
    if (parent / 'async_rbench').is_dir():
        sys.path.insert(0, str(parent))
        break
"""
    write(CASE / "oracle.py", harness + "from async_rbench.docker_case import run_oracle\nif __name__ == '__main__': run_oracle('" + CASE_ID + "')\n")
    write(CASE / "verify.py", harness + "from async_rbench.docker_case import run_verifier\nif __name__ == '__main__': run_verifier('" + CASE_ID + "')\n")
    write(CASE / "generate.py", harness + "from async_rbench.docker_case import export_task\nif __name__ == '__main__': export_task(Path(__file__).resolve().parent, '" + CASE_ID + "')\n")
    print(CASE)

if __name__ == "__main__":
    main()
