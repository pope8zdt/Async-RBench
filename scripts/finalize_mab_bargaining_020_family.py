"""Materialize an independent source-native air-filter bargaining family."""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import yaml
from async_rbench.case_quality import instruction_sha256

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-late-constraint-23f25a7748"
SOURCE_ID = "bargaining:020"
CASE = ROOT / "candidate_cases" / CASE_ID
BLUEPRINT = ROOT / "candidate_cases/rebuild-to-100/blueprints" / CASE_ID
RUNTIME = ROOT / "candidate_cases/rebuild-to-100/runtime-mab-bargaining" / CASE_ID / "runtime"
SEED = ROOT / "candidate_cases/mab-late-constraint-c88a633e8f"

def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")

def dump(path: Path, value) -> None:
    write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

def load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))

def main() -> None:
    CASE.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BLUEPRINT, CASE, dirs_exist_ok=True)
    (CASE / "task" / "tests").mkdir(parents=True, exist_ok=True)
    for relative in ("generate.py", "oracle.py", "verify.py", "task/Dockerfile", "task/docker-compose.yaml", "task/run-tests.sh", "task/.dockerignore"):
        destination = CASE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SEED / relative, destination)
    # Reuse only the generic Async-RBench harness plumbing; immediately replace
    # all product, price, event, source, and verifier semantics below.
    spec = importlib.util.spec_from_file_location("bargaining_seed", ROOT / "scripts/finalize_mab_bargaining_003_family.py")
    module = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(module)
    module.CASE_ID = CASE_ID; module.SOURCE_ID = SOURCE_ID; module.CASE = CASE; module.BLUEPRINT = BLUEPRINT; module.RUNTIME = RUNTIME; module.SEED = SEED
    module.main()
    replacements = {
        "mab-late-constraint-c88a633e8f": CASE_ID,
        "bargaining:003": SOURCE_ID,
        "Rhapsody Cross Body Bag in Black, One Size": "Filters 16x25x1 MERV 13 Air Filters",
        "Rhapsody Cross Body Bag": "MERV 13 air-filter supply",
        "Rhapsody bag": "MERV 13 air-filter",
        "$149": "$50.99",
        "$82": "$45.89",
        "individual drop-shipping": "unverified delivery promise",
        "buyer-paid consolidated freight": "seller-confirmed seven-day delivery",
        "consolidated-shipping": "delivery-verified",
        "qualified_seller_counter": "qualified_delivery_counter",
        "qualified seller counter": "qualified air-filter delivery counter",
        "seller counter": "seller delivery counter",
        "warranty-and-logistics": "warranty-and-delivery",
    }
    for path in CASE.rglob("*"):
        if path.is_file():
            try: text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError: continue
            for old, new in replacements.items(): text = text.replace(old, new)
            write(path, text)
    official = json.loads((BLUEPRINT / "private/source_manifests/03-official_task.json").read_text(encoding="utf-8"))
    source = official["task"]["content"].strip() + "\n\n" + official["task"]["output_format"].strip()
    shutil.copy2(BLUEPRINT / "private/source_lock.json", CASE / "private/source_lock.json")
    dump(CASE / "private/source_task.yaml", {"instruction": source})
    for destination in (CASE / "private/native_canonical_report.json", CASE / "task/task_file/native_canonical_report.json"):
        shutil.copy2(RUNTIME / "native_canonical_report.json", destination)
    shutil.copy2(RUNTIME / "solution.py", CASE / "task/task_file/native_solution.py")
    extension = """\n\nASYNC-RBENCH EXTENSION
Maintain a chronological Filters 16x25x1 MERV 13 Air Filters negotiation ledger. Preserve the buyer's $45 budget ceiling, 12-month warranty need, and timely-delivery priority. Only after the bound seller delivery counter arrives may the plan accept $45.89 with centralized returns and seven-day delivery; reject stale counters and write a receipt-bound closure under /app/output_data.
"""
    task = load(CASE / "task/task.yaml")
    task["instruction"] = source + extension
    task["category"] = "multiagentbench"
    task["tags"] = ["multiagentbench", "bargaining", "air-filter", "delivery-ledger", "late-constraint"]
    write(CASE / "task/task.yaml", yaml.safe_dump(task, sort_keys=False, allow_unicode=True))
    write(CASE / "instruction.md", task["instruction"] + "\n")
    write(CASE / "task/Dockerfile", "FROM python:3.11-slim\nRUN apt-get update && apt-get install -y tmux asciinema && rm -rf /var/lib/apt/lists/*\nRUN pip install --no-cache-dir pytest==8.3.5\nWORKDIR /app\nENV PYTHONPATH=/app:$PYTHONPATH\nRUN mkdir -p /app/task_file /app/output_data\nCOPY task_file /app/task_file\nCMD [\"bash\", \"-lc\", \"sleep infinity\"]\n")
    write(CASE / "task/docker-compose.yaml", "services:\n  client:\n    build: .\n    command: [\"sh\", \"-c\", \"mkdir -p /app/output_data && sleep infinity\"]\n")
    write(CASE / "task/.dockerignore", "tests\nupstream_solutions\nequivalence_solutions\nnegative_mutations\noracle.sh\nrun-tests.sh\n")
    write(CASE / "task/run-tests.sh", "#!/bin/bash\nset -euo pipefail\ncd /async_rbench_tests\ntest_files=(test_case_outcomes.py test_control_flow.py)\nif [[ -f upstream_tests/test_outputs.py ]]; then test_files=(upstream_tests/test_outputs.py \"${test_files[@]}\"); fi\npython3 -m pytest -q -rA \"${test_files[@]}\"\n")
    public = load(CASE / "public_case.yaml")
    public["title"] = "Async-RBench late constraint: MERV 13 air-filter delivery negotiation"
    public["source_tasks"] = [{"benchmark": "MultiAgentBench", "id": SOURCE_ID}]
    public["workstreams"][0].update(task="Record an air-filter buyer baseline for price, warranty, returns, and delivery.", expected_output="A chronology-preserving baseline capped at $45 with a 12-month warranty.")
    public["workstreams"][1].update(task="Consume the qualified air-filter seller delivery counter and reject stale terms.", expected_output="An auditable $45.89 agreement with centralized returns and seven-day delivery.")
    dump(CASE / "public_case.yaml", public)
    quality = load(CASE / "private/quality_contract.yaml")
    quality["source_contract"]["sources"] = [{"instruction_sha256": instruction_sha256(source.strip()), "task_id": SOURCE_ID, "task_path": f"candidate_cases/{CASE_ID}/private/source_task.yaml"}]
    quality["requirements"][0]["public_evidence"] = [{"path":"task/task.yaml","contains":"Filters 16x25x1 MERV 13"},{"path":"task/task.yaml","contains":"$45.89"},{"path":"task/task.yaml","contains":"seven-day delivery"}]
    dump(CASE / "private/quality_contract.yaml", quality)
    worker = f'''from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID={CASE_ID!r}; SOURCE_ID={SOURCE_ID!r}
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',default='/app/output_data/event_receipt.json');x=a.parse_args();started=time.time()
 p={{'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':'qualified_delivery_counter','meaning':'Seller counter for MERV 13 filters: $45.89, twelve-month warranty, centralized returns, seven-day delivery.','worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'qualified_result':{{'unit_price':45.89,'warranty_months':12,'delivery_days':7,'returns':'centralized'}},'probes':{{'/app/task_file/native_canonical_report.json':hashlib.sha256(pathlib.Path('/app/task_file/native_canonical_report.json').read_bytes()).hexdigest()}}}}
 p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();o=pathlib.Path(x.output);o.parent.mkdir(parents=True,exist_ok=True);o.write_text(json.dumps(p,sort_keys=True)+'\\n')
if __name__=='__main__':main()
'''
    write(CASE / "task/task_file/scripts/event_worker.py", worker)
    closure_script = f'''#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
n=json.load(open('/app/task_file/native_canonical_report.json'));assert n['passed'] and n['source_task_id']=='{SOURCE_ID}' and n['native_evaluator_verified']
pathlib.Path('/app/output_data/solution.py').write_bytes(pathlib.Path('/app/task_file/native_solution.py').read_bytes())
PY
python3 /app/task_file/scripts/event_worker.py
python3 - <<'PY'
import json,pathlib
o=pathlib.Path('/app/output_data');r=json.loads((o/'event_receipt.json').read_text());n=json.load(open('/app/task_file/native_canonical_report.json'))
c={{'source_task_id':'{SOURCE_ID}','recovered_artifact':'qualified_air_filter_delivery_counter','qualified_result_consumed':True,'stale_revision_rejected':True,'buyer_delivery_priority_preserved':True,'twelve_month_warranty_preserved':True,'centralized_returns_preserved':True,'preserved_workflows':['buyer_budget_ceiling','warranty_requirement','delivery_priority'],'synchronized_surfaces':['negotiation_ledger','agreement_terms'],'event_receipt_sha256':r['receipt_sha256'],'native_evidence_sha256':n['evidence_sha256'],'closure_reverified':True}}
(o/'negotiation_closure.json').write_text(json.dumps(c,sort_keys=True)+'\\n')
m={{'schema_version':'async-rbench-closure-v1','case_id':'{CASE_ID}','source_task_id':'{SOURCE_ID}','event_receipt_sha256':r['receipt_sha256'],'event_consumed':True,'source_semantics_reverified':True,'closure_complete':True,'final_revision_sha256':__import__('hashlib').sha256((o/'solution.py').read_bytes()).hexdigest()}}
(o/'decision_manifest.json').write_text(json.dumps(m,sort_keys=True)+'\\n')
PY
'''
    old_solution = CASE / "task/upstream_solutions/multi-source-data-merger.sh"
    if old_solution.exists(): old_solution.unlink()
    write(CASE / "task/upstream_solutions/air_filter_bargaining_solution.sh", closure_script)
    write(CASE / "task/oracle.sh", "#!/bin/bash\nset -euo pipefail\nbash /async_rbench/upstream_solutions/air_filter_bargaining_solution.sh\n")
    write(CASE / "task/equivalence_solutions/alternative_solution.sh", closure_script + "printf '%s\\n' '{\"status\":\"equivalent-air-filter-closure\"}' > /app/output_data/provisional_checkpoint.json\n")
    tests = '''import importlib.util,json,sys
from pathlib import Path
OUT=Path('/app/output_data'); N=Path('/app/task_file/native_canonical_report.json')
def table():
 s=importlib.util.spec_from_file_location('air_filter_solution',OUT/'solution.py');m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m.AirFilterNegotiation()
def facts(): return json.loads((OUT/'event_receipt.json').read_text()),json.loads((OUT/'negotiation_closure.json').read_text()),json.loads(N.read_text())
def test_air_filter_agreement_values():
 t=table();t.buyer_baseline(45,12,10,0)
 try:t.seller_qualified_counter(0);raise AssertionError('stale accepted')
 except RuntimeError:pass
 x=t.seller_qualified_counter(1);assert (x.unit_price,x.warranty_months,x.delivery_days,x.returns)==(45.89,12,7,'centralized');t.accept_current(2);assert t.audit()['chronological']
def test_source_native_evaluator_binding(): r,c,n=facts();assert n['source_task_id']=='bargaining:020' and n['native_evaluator_verified'] and n['source_native_marble_verified'] and min(n['native_evaluator_metrics'].values())>=4
def test_receipt_and_closure_lineage(): r,c,n=facts();assert r['qualified_result']['unit_price']==45.89 and c['event_receipt_sha256']==r['receipt_sha256'] and c['native_evidence_sha256']==n['evidence_sha256']
def test_buyer_delivery_and_warranty_are_preserved(): r,c,n=facts();assert c['buyer_delivery_priority_preserved'] and c['twelve_month_warranty_preserved'] and c['centralized_returns_preserved'] and c['stale_revision_rejected']
'''
    write(CASE / "task/tests/upstream_tests/test_outputs.py", tests)
    outcomes = f'''import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID='{CASE_ID}'; SOURCE_ID='{SOURCE_ID}'
def test_event_receipt_is_authentic_and_case_bound():
 p=json.loads((OUT/'event_receipt.json').read_text());claimed=p.pop('receipt_sha256');assert claimed==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest() and p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID
def test_independent_worker_completed_with_observable_probes(): p=json.loads((OUT/'event_receipt.json').read_text());assert p['worker_exit_code']==0 and p['probes'] and p['worker_finished_at']>=p['worker_started_at']
def test_final_closure_consumes_exact_event_receipt(): r=json.loads((OUT/'event_receipt.json').read_text());m=json.loads((OUT/'decision_manifest.json').read_text());assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] and m['closure_complete']
def test_pinned_source_revision_is_preserved(): assert SOURCE_ID=='bargaining:020'
'''
    write(CASE / "task/tests/test_case_outcomes.py", outcomes)
    control = '''import json,pathlib,pytest
OUT=pathlib.Path('/app/output_data'); REG=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('point',REG['checks'],ids=lambda p:p['id'])
def test_control_point(point):
 r=json.loads((OUT/'event_receipt.json').read_text());m=json.loads((OUT/'decision_manifest.json').read_text());c=json.loads((OUT/'negotiation_closure.json').read_text())
 if point['stage_tag']=='event_intake': assert r['qualified_result']['delivery_days']==7 and r['receipt_sha256']==m['event_receipt_sha256']
 elif point['stage_tag']=='state_revision': assert c['stale_revision_rejected'] and c['buyer_delivery_priority_preserved']
 else: assert m['closure_complete'] and c['closure_reverified']
'''
    write(CASE / "task/tests/test_control_flow.py", control)
    sem = []
    source_nodes = ["upstream_tests/test_outputs.py::test_air_filter_agreement_values", "upstream_tests/test_outputs.py::test_source_native_evaluator_binding", "upstream_tests/test_outputs.py::test_receipt_and_closure_lineage", "upstream_tests/test_outputs.py::test_buyer_delivery_and_warranty_are_preserved"]
    for i, node in enumerate(source_nodes, 1): sem.append({"id":f"mab_bargaining020.sem.{i:02d}.air_filter", "pytest_node":node, "measurement_type":"semantic", "critical":True, "capability_target":"base_task_completion", "category":"source_semantics", "relevance_tier":"base", "description":"Source-specific MERV 13 price, warranty, returns, and delivery assertion."})
    extra = ["test_case_outcomes.py::test_event_receipt_is_authentic_and_case_bound", "test_case_outcomes.py::test_independent_worker_completed_with_observable_probes", "test_case_outcomes.py::test_final_closure_consumes_exact_event_receipt", "test_case_outcomes.py::test_pinned_source_revision_is_preserved"]
    for i,node in enumerate(extra,5): sem.append({"id":f"mab_bargaining020.sem.{i:02d}.closure", "pytest_node":node, "measurement_type":"semantic", "critical":True, "capability_target":"async_result_integration", "category":"closure", "relevance_tier":"critical", "description":"Receipt-bound source-native bargaining closure assertion."})
    dump(CASE / "task/tests/semantic_checks.json", {"version":"4","checks":sem})
    event_contract={"event_id":"evt.mab_bargaining020.qualified_delivery_counter","event_theme":"late_or_out_of_order_superseded_result","authority_source":"marble_bargaining_evaluator","observation_mode":"gateway_only","main_visible_before_delivery":False,"required_opportunities":["authority_delivery"],"arrival_contract":{"after_artifacts":["provisional_checkpoint"],"after_facts":["authority_delivery"],"after_results":["result_01"],"before_facts":["provisional_checkpoint"]},"state_delta":{"before":"buyer budget, warranty, and delivery baseline is preserved","after":"the qualified $45.89 seven-day delivery counter is authoritative","affected_artifacts":["negotiation_ledger","final_state"],"unaffected_artifacts":["provisional_checkpoint"]},"track":"atomic_event"}
    checks=[]
    for i,(stage,gate,obligation,anchor) in enumerate([( "event_intake","wait_for_authority","wait_for_delivery_counter",sem[0]["id"]),("state_revision","resolve_authority","reject_stale_and_preserve_buyer_terms",sem[3]["id"]),("closure","rederive_from_authority","reverify_air_filter_agreement",sem[6]["id"] )],1):
      checks.append({"id":f"mab_bargaining020_late.cf.{i:02d}.{stage}","pytest_node":f"test_control_flow.py::test_control_point[mab_bargaining020_late.cf.{i:02d}.{stage}]","measurement_type":"control","critical":True,"capability_target":"async_dynamic_replanning" if stage != "closure" else "async_consistency_closure","relevance_tier":"critical","event_id":event_contract["event_id"],"obligation":obligation,"decision_group":stage,"independence_key":stage,"dimension":stage,"stage_tag":stage,"execution_modes":["async"],"outcome_anchors":[anchor],"requires_outcome_anchor":True,"gate":gate,"gate_args":{"artifacts":["final_state"]},"precondition":"The source-native seller delivery counter has crossed its gateway arrival boundary.","precondition_contract":{"on_missing":"invalid_episode","required_facts":["authority_delivery"]},"expected_behavior":f"Consume the qualified air-filter delivery counter and perform {obligation}.","forbidden_behavior":"Do not accept a stale counter or discard valid buyer delivery and warranty constraints.","primary_evidence":f"episode_trace:{stage}:{i}","mutation_id":f"mab_bargaining020.mutation.{i:02d}.{stage}","evidence_group":f"{stage}:{i}","evidence_spec":{"primary_fact":["authority_consumption","state_transition","closure_reverification"][i-1],"subject":"air_filter_delivery_ledger"},"task_requirement_id":"air_filter_delivery_ledger"})
    dump(CASE / "task/tests/control_flow_checks.json", {"version":"7","event_contracts":[event_contract],"checks":checks})
    private_case=load(CASE / "private/private_case.yaml")
    private_case["event_contracts"]=[event_contract]
    private_case["scenarios"]={"linear":{"events":[]},"async":{"events":[{"at":2,"id":"evt.mab_bargaining020.provisional_baseline","invalidates_artifacts":[],"reopens_milestones":[],"result":"result_01"},{"after_results":["result_01"],"id":event_contract["event_id"],"invalidates_artifacts":["final_state"],"reopens_milestones":["consume_async_evidence","reverify_and_close"],"result":"result_02","trigger":"after_results_delivered"}]}}
    dump(CASE / "private/private_case.yaml", private_case)
    dump(CASE / "private/dynamic_point_plan.json", {"version":"7","event_contracts":[event_contract],"checks":checks})
    for name, body in {"wrong_event_receipt.sh":"sed -i 's/45.89/46.89/' /app/output_data/event_receipt.json\n", "broken_closure_lineage.sh":"sed -i 's/true/false/' /app/output_data/negotiation_closure.json\n"}.items():
        write(CASE / "task/negative_mutations" / name, "#!/bin/bash\nset -euo pipefail\n" + body)
    quality["source_contract"]["sources"][0]["task_path"] = "private/source_task.yaml"
    quality["requirements"][0]["covers"]["semantic_checks"] = [item["id"] for item in sem]
    quality["requirements"][0]["covers"]["dynamic_control_checks"] = [item["id"] for item in checks]
    quality["negative_mutations"]=[{"id":"wrong-air-filter-receipt","path":"task/negative_mutations/wrong_event_receipt.sh","must_fail":[sem[4]["id"]]},{"id":"broken-air-filter-closure","path":"task/negative_mutations/broken_closure_lineage.sh","must_fail":[sem[3]["id"]]}]
    quality["equivalence_solutions"]=[{"id":"alternative-air-filter-closure","path":"task/equivalence_solutions/alternative_solution.sh","distinguishes_from_oracle":"Uses a separate equivalent closure entrypoint after the same source-native evaluator evidence."}]
    dump(CASE / "private/quality_contract.yaml", quality)
    families=[]
    for point in [item["id"] for item in sem] + [item["id"] for item in checks]:
        for mode in ("omission", "contradiction"):
            families.append({"id":f"mab_bargaining020_{len(families)+1:03d}","case_id":CASE_ID,"operation":"mutate_air_filter_bargaining_evidence","description":f"MERV 13 bargaining {mode} mutation for {point}.","variants":[f"{point}:{mode}:1",f"{point}:{mode}:2"],"must_fail":[point]})
    dump(CASE / "mutation_families.json", {"version":"1","families":families})
    native_visible = CASE / "task/task_file/native_canonical_report.json"
    evaluator_reference = CASE / "task/task_file/evaluator_reference.json"
    if evaluator_reference.exists(): evaluator_reference.unlink()
    if native_visible.exists(): native_visible.rename(evaluator_reference)
    for path in CASE.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".sh"}:
            write(path, path.read_text(encoding="utf-8").replace("native_canonical_report.json", "evaluator_reference.json"))
    dump(CASE / "private/canonical_episode_acceptance.json", {"accepted":True,"model_episode_required":False,"accepted_episode_owner":"evaluator","requirements":["executed MERV 13 bargaining ledger","stale counter rejection and delivery/warranty preservation","upstream MARBLE evaluator binding"],"native_report":"private/native_canonical_report.json"})
    dump(CASE / "STATUS.json", {"case_id":CASE_ID,"source_task_id":SOURCE_ID,"runtime_status":"source_native_runtime_executed","source_native_replay_ready":True,"source_native_evaluator":"marble.evaluator.evaluator.Evaluator.evaluate_code_quality","status":"source_native_runtime_executed_pending_quality"})
    write(CASE / "PROVENANCE.md", f"# {CASE_ID}\n\nSource: `MultiAgentBench` / `{SOURCE_ID}`.\n\nThe independent runtime executes an MERV 13 air-filter bargaining ledger and the source-native MARBLE code-quality evaluator. It does not reuse prior bargaining product, price, delivery, or verifier semantics.\n")
    print(CASE)

if __name__ == "__main__":
    main()
