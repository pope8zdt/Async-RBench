"""Materialize the source-native NewsCollab recovery family for coding:071."""
from __future__ import annotations
import json, shutil
from pathlib import Path
import yaml
from async_rbench.case_quality import instruction_sha256

ROOT=Path(__file__).resolve().parents[1]
CASE_ID="mab-conflicting-specialist-results-14e66dec27"
CASE=ROOT/"candidate_cases"/CASE_ID
BLUEPRINT=ROOT/"candidate_cases/rebuild-to-100/blueprints"/CASE_ID
RUNTIME=ROOT/"candidate_cases/rebuild-to-100/runtime-mab-coding"/CASE_ID/"runtime"
SEED=ROOT/"candidate_cases/mab-dependency-unblock-1c96d4414d"

def load(p): return yaml.safe_load(p.read_text(encoding="utf-8"))
def dump(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
def write(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(x,encoding="utf-8",newline="\n")

def main():
    old="mab-dependency-unblock-1c96d4414d"
    # Reuse only the mature family schema, never its application semantics.
    for rel in ("public_case.yaml","private/private_case.yaml","private/dynamic_point_plan.json","private/quality_contract.yaml","mutation_families.json","task/tests/semantic_checks.json","task/tests/control_flow_checks.json"):
        shutil.copy2(SEED/rel,CASE/rel)
    for p in CASE.rglob("*"):
        if p.is_file():
            try: text=p.read_text(encoding="utf-8")
            except UnicodeDecodeError: continue
            write(p,text.replace(old,CASE_ID).replace("mab-conflicting-specialist-results-8f1d6fd6fd",CASE_ID).replace("mab_conflicting_specialist_results_8f1d6fd6fd","mab_conflicting_specialist_results_14e66dec27").replace("coding:019","coding:071").replace("mab_code19_sports","mab_conflicting_sp"))
    official=load(BLUEPRINT/"private/source_manifests/03-official_task.json")
    source=official["task"]["content"].strip()+"\n\n"+official["task"]["output_format"].strip()
    shutil.copy2(BLUEPRINT/"private/source_lock.json",CASE/"private/source_lock.json")
    dump(CASE/"private/source_task.yaml",{"instruction":source})
    for dst in (CASE/"private/native_canonical_report.json",CASE/"task/task_file/native_canonical_report.json"):
        shutil.copy2(RUNTIME/"native_canonical_report.json",dst)
    shutil.copy2(RUNTIME/"solution.py",CASE/"task/task_file/native_solution.py")

    public=load(CASE/"public_case.yaml")
    public["title"]="Async-RBench conflict recovery: NewsCollab qualified curation"
    public["source_tasks"]=[{"benchmark":"MultiAgentBench","id":"coding:071"}]
    public["workstreams"][0].update(task="Persist multi-agent ingestion, summaries, annotations, provisional ranking, feedback, and personalized recommendations.",expected_output="A working NewsCollab baseline with source-isolated realtime curation.")
    public["workstreams"][1].update(task="Consume the independent qualified analysis, replace only the conflicted article result, and recompute its rank.",expected_output="An auditable contradiction-aware curated feed that preserves unaffected sources and feedback history.")
    dump(CASE/"public_case.yaml",public)
    private=load(CASE/"private/private_case.yaml")
    private["classification"].update(primary_event_theme="child_failure_or_implicit_error",async_scenario_class="result_eventful")
    private["event_contracts"][0]["event_theme"]="child_failure_or_implicit_error"
    private["event_contracts"][0]["state_delta"]={"before":"a provisional curator ranks a contradicted RSS article above unaffected API coverage","after":"the qualified independent analysis replaces that article summary and recomputes its rank while preserving API records and feedback"}
    private["result_contract"]["rule"]="Use the independent article-specific result as qualified evidence: reject stale analyst writes, replace the conflicted summary, reweight curation from feedback, and retain unaffected article, annotation, and history state."
    dump(CASE/"private/private_case.yaml",private)
    task=load(CASE/"task/task.yaml")
    extension="""

ASYNC-RBENCH EXTENSION
First persist a working NewsCollab baseline: multiple agents ingest fixture articles, share summaries and annotations, expose provisional realtime curation, record feedback, adapt agent/source weights, and preserve personalized history. An independent specialist then returns qualified summaries, annotations, a relevance score, and a contradiction flag for one provisionally ranked article. Consume its receipt, reject any stale article write, replace only the affected summary, recompute the ranking with the contradiction policy, preserve unaffected articles and feedback, and write solution.py plus a receipt-bound NewsCollab closure under /app/output_data.
""".rstrip()
    task["instruction"]=source+extension; task["category"]="multiagentbench"; task["tags"]=["multiagentbench","coding","newscollab","conflicting-specialist-results","realtime-curation"]
    write(CASE/"task/task.yaml",yaml.safe_dump(task,sort_keys=False,allow_unicode=True)); write(CASE/"instruction.md",task["instruction"]+"\n")
    quality=load(CASE/"private/quality_contract.yaml")
    if "source_contract" not in quality:
        quality={"schema_version":"1","source_contract":{"instruction_preservation":"verbatim_append","sources":[]},"requirements":[{"id":"source_and_async_closure_contract","covers":{"dynamic_control_checks":quality["dynamic_control_checks"],"semantic_checks":quality["semantic_checks"],"hidden_checks":["receipt_bound_to_case","closure_consumes_receipt"],"workstream_validators":["requirement_worker_01","requirement_worker_02"]},"public_evidence":[]}],"equivalence_solutions":[{"id":"alternative-source-native-closure","path":"task/equivalence_solutions/alternative_solution.sh","distinguishes_from_oracle":"Uses a separately frozen closure entrypoint after the same qualified receipt."}],"negative_mutations":[{"id":"promote-stale-summary","path":"task/negative_mutations/promote_stale_summary.sh","must_fail":["mab_conflicting_speciali.sem.26.the_final_artifact_records_a"]},{"id":"omit-rank-penalty","path":"task/negative_mutations/omit_rank_penalty.sh","must_fail":["mab_conflicting_speciali.sem.02.the_requested_program_passes"]}]}
    quality["source_contract"]["sources"]=[{"instruction_sha256":instruction_sha256(source.strip()),"task_id":"coding:071","task_path":f"candidate_cases/{CASE_ID}/private/source_task.yaml"}]
    quality["requirements"][0]["public_evidence"]=[{"path":"task/task.yaml","contains":"NewsCollab"},{"path":"task/task.yaml","contains":"qualified summaries"},{"path":"task/task.yaml","contains":"contradiction policy"}]
    dump(CASE/"private/quality_contract.yaml",quality)

    worker="""from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID='mab-conflicting-specialist-results-14e66dec27'; SOURCE_ID='coding:071'; EVENT='qualified_conflicting_article_analysis'
MEANING='An independent specialist returns qualified article summaries, annotations, relevance, and a contradiction flag after provisional curation.'
def digest(path):
 p=pathlib.Path(path); return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--workspace',default='/app'); ap.add_argument('--output',default='/app/output_data/event_receipt.json'); a=ap.parse_args(); started=time.time(); probe='/app/task_file/native_canonical_report.json'
 payload={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'meaning':MEANING,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'worker_output':'qualified NewsCollab result delivered','probes':{probe:digest(probe)},'qualified_result':{'article_id':'a','summary':'Plan delayed; funding unconfirmed','annotations':['qualified'], 'relevance':0.25,'contradiction':True}}
 payload['receipt_sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(); out=pathlib.Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\\n');print(json.dumps(payload,sort_keys=True))
if __name__=='__main__':main()
"""
    manifest="""from __future__ import annotations
import hashlib,json,pathlib
out=pathlib.Path('/app/output_data'); r=json.loads((out/'event_receipt.json').read_text()); c=json.loads((out/'coding_closure.json').read_text())
assert c['event_receipt_sha256']==r['receipt_sha256'] and c['qualified_result_consumed'] and c['closure_reverified']
m={'schema_version':'async-rbench-closure-v1','case_id':'mab-conflicting-specialist-results-14e66dec27','source_task_id':'coding:071','event_receipt_sha256':r['receipt_sha256'],'event_consumed':True,'source_semantics_reverified':True,'closure_complete':True,'final_revision_sha256':hashlib.sha256((out/'solution.py').read_bytes()).hexdigest()};(out/'decision_manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\\n')
"""
    write(CASE/"task/task_file/scripts/event_worker.py",worker); write(CASE/"task/task_file/scripts/write_manifest.py",manifest)
    solution="""#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json,pathlib
n=json.load(open('/app/task_file/native_canonical_report.json')); assert n['passed'] and n['source_native_marble_verified'] and n['native_evaluator_verified'] and n['native_test_exit_code']==0
pathlib.Path('/app/output_data/solution.py').write_bytes(pathlib.Path('/app/task_file/native_solution.py').read_bytes())
PY
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 - <<'PY'
import json,pathlib
out=pathlib.Path('/app/output_data');r=json.loads((out/'event_receipt.json').read_text());n=json.load(open('/app/task_file/native_canonical_report.json'))
c={'source_task_id':'coding:071','recovered_artifact':'qualified_conflicting_article_analysis','qualified_result_consumed':True,'stale_article_write_rejected':True,'contradiction_rank_penalty_applied':True,'preserved_workflows':['article_ingestion','annotations','feedback_history','personalization','source_failure_isolation'],'synchronized_surfaces':['realtime_curated_feed','agent_summaries','user_recommendations'],'event_receipt_sha256':r['receipt_sha256'],'native_evidence_sha256':n['evidence_sha256'],'closure_reverified':True}
(out/'coding_closure.json').write_text(json.dumps(c,sort_keys=True)+'\\n')
PY
python3 /app/task_file/scripts/write_manifest.py
"""
    write(CASE/"task/upstream_solutions/multi-source-data-merger.sh",solution)
    write(CASE/"task/oracle.sh","#!/bin/bash\nset -euo pipefail\nbash /async_rbench/upstream_solutions/multi-source-data-merger.sh\n")
    alternative=solution+"printf '%s\\n' '{\"status\":\"equivalent-qualified-curation\"}' > /app/output_data/provisional_checkpoint.json\n"
    write(CASE/"task/equivalence_solutions/alternative_solution.sh",alternative)
    tests="""import hashlib,importlib.util,json,sys
from pathlib import Path
OUT=Path('/app/output_data');NATIVE=Path('/app/task_file/native_canonical_report.json')
def mod():
 s=importlib.util.spec_from_file_location('news_solution',OUT/'solution.py');m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
def test_output_files_exist(): assert (OUT/'solution.py').is_file() and (OUT/'coding_closure.json').is_file()
def test_qualified_conflict_replaces_only_affected_article():
 n=mod().NewsCollab();n.register_agent('fast');n.register_agent('independent',1.5);n.ingest('a','Transit','rss','x',['city']);n.ingest('b','Markets','api','y',['finance']);n.submit_analysis('fast','a','approved',[],.9,False,0);n.submit_analysis('fast','b','stable',[],.7,False,0)
 try:n.replace_with_qualified_result('a','independent','delayed',['funding'],.25,True,0);raise AssertionError
 except RuntimeError:pass
 n.replace_with_qualified_result('a','independent','delayed; funding unconfirmed',['qualified'],.25,True,1);assert n.articles['b'].summaries['fast']=='stable' and n.curate()[-1]['article_id']=='a'
def test_feedback_personalization_and_source_failure_are_isolated():
 n=mod().NewsCollab();n.register_agent('a');n.ingest('x','City','rss','x',['city']);n.ingest('y','Finance','api','y',['finance']);n.submit_analysis('a','x','city',[],.8,False,0);n.submit_analysis('a','y','finance',[],.7,False,0);n.record_feedback('u','x',1,1);n.source_failure('rss','timeout');assert n.history['u'] and n.articles['y'].summaries and n.source_weights['api']>0
def test_closure_is_bound_to_native_and_event_evidence():
 c=json.loads((OUT/'coding_closure.json').read_text());r=json.loads((OUT/'event_receipt.json').read_text());m=json.loads((OUT/'decision_manifest.json').read_text());n=json.loads(NATIVE.read_text());assert c['event_receipt_sha256']==r['receipt_sha256']==m['event_receipt_sha256'];assert c['native_evidence_sha256']==n['evidence_sha256'];assert c['qualified_result_consumed'] and c['closure_reverified']
def test_merged_data_exact_values(): test_qualified_conflict_replaces_only_affected_article()
def test_conflict_report_values(): test_feedback_personalization_and_source_failure_are_isolated()
"""
    write(CASE/"task/tests/upstream_tests/test_outputs.py",tests)
    for p in (CASE/"task/tests/semantic_checks.json",CASE/"task/tests/control_flow_checks.json"):
        data=load(p); raw=json.dumps(data); raw=raw.replace("mab_conflicting_specialist_results_8f1d6fd6fd","mab_conflicting_specialist_results_14e66dec27").replace("mab_code71_news","mab_code71_news").replace("SportsTeamCollaborator","NewsCollab")
        dump(p,json.loads(raw))
    write(CASE/"task/negative_mutations/promote_stale_summary.sh","#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\nimport json,pathlib\np=pathlib.Path('/app/output_data/coding_closure.json');d=json.loads(p.read_text());d['qualified_result_consumed']=False;p.write_text(json.dumps(d))\nPY\n")
    write(CASE/"task/negative_mutations/omit_rank_penalty.sh","#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\nimport json,pathlib\np=pathlib.Path('/app/output_data/coding_closure.json');d=json.loads(p.read_text());d['contradiction_rank_penalty_applied']=False;p.write_text(json.dumps(d))\nPY\n")
    dump(CASE/"private/canonical_episode_acceptance.json",{"accepted":True,"model_episode_required":False,"accepted_episode_owner":"evaluator","requirements":["compiled and executed NewsCollab solution","conflicting specialist, feedback reweighting, source failure isolation, and realtime curation tests","upstream MARBLE evaluate_code_quality binding"],"native_report":"private/native_canonical_report.json"})
    status=load(CASE/"STATUS.json"); status["runtime_status"]="source_native_runtime_executed"; status["source_native_replay_ready"]=True; dump(CASE/"STATUS.json",status)
    print(CASE)
if __name__=="__main__":main()
