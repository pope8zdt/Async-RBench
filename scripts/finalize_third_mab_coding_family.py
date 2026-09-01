from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml
from async_rbench.case_quality import instruction_sha256

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-cross-app-artifact-496566389d"
CASE = ROOT / "candidate_cases" / CASE_ID
BLUEPRINT = ROOT / "candidate_cases/rebuild-to-100/blueprints" / CASE_ID
RUNTIME = ROOT / "candidate_cases/rebuild-to-100/runtime-mab-coding" / CASE_ID / "runtime"


def load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def main() -> None:
    native = load(BLUEPRINT / "private/source_manifests/03-official_task.json")
    source_instruction = native["task"]["content"].strip() + "\n\n" + native["task"]["output_format"].strip()
    public = load(CASE / "public_case.yaml")
    public["title"] = "Async-RBench cross-artifact recovery: QuestHub revision schema"
    public["source_tasks"] = [{"benchmark": "MultiAgentBench", "id": "coding:070"}]
    public["workstreams"][0]["expected_output"] = "A working QuestHub baseline spanning authenticated projects, Markdown revisions, member permissions, realtime subscribers, and external review exports."
    public["workstreams"][0]["task"] = "Build the editor and integration surfaces against provisional content models while preserving their public behavior."
    public["workstreams"][1]["expected_output"] = "A receipt-bound immutable revision schema with parent constraints propagated across editor, subscriber, and integration artifacts."
    public["workstreams"][1]["task"] = "Recover from the provisional-schema failure and synchronize the authoritative revision model across all application surfaces."
    dump(CASE / "public_case.yaml", public)

    private = load(CASE / "private/private_case.yaml")
    private["classification"]["primary_event_theme"] = "child_failure_or_implicit_error"
    private["classification"]["async_scenario_class"] = "resource_eventful"
    private["event_contracts"][0]["event_theme"] = "child_failure_or_implicit_error"
    private["event_contracts"][0]["state_delta"]["before"] = "editor, subscriber, and export surfaces depend on a provisional mutable content model"
    private["event_contracts"][0]["state_delta"]["after"] = "authoritative immutable revision-parent schema repairs all three surfaces and rejects stale parent revisions"
    private["result_contract"]["rule"] = "Consume the recovered schema receipt, propagate one revision identity through storage, realtime events, rendering, and external exports, and preserve authentication and authorization."
    dump(CASE / "private/private_case.yaml", private)

    shutil.copy2(BLUEPRINT / "private/source_lock.json", CASE / "private/source_lock.json")
    shutil.copy2(RUNTIME / "native_canonical_report.json", CASE / "private/native_canonical_report.json")
    shutil.copy2(RUNTIME / "native_canonical_report.json", CASE / "task/task_file/native_canonical_report.json")
    shutil.copy2(RUNTIME / "solution.py", CASE / "task/task_file/native_solution.py")
    dump(CASE / "private/source_task.yaml", {"instruction": source_instruction})

    task = load(CASE / "task/task.yaml")
    extension = """

ASYNC-RBENCH EXTENSION
First persist a functional QuestHub editor, realtime subscriber, and external-review integration against provisional content models. A schema specialist then returns the authoritative immutable revision-parent model. Consume its receipt, repair every affected artifact, reject stale parent revisions, preserve authentication and authorization, and write solution.py plus the receipt-bound cross-artifact closure under /app/output_data.
""".rstrip()
    task["instruction"] = source_instruction + extension
    task["category"] = "multiagentbench"
    task["tags"] = ["multiagentbench", "coding", "questhub", "cross-app-artifact"]
    write(CASE / "task/task.yaml", yaml.safe_dump(task, sort_keys=False, allow_unicode=True))
    write(CASE / "instruction.md", task["instruction"] + "\n")

    quality = load(CASE / "private/quality_contract.yaml")
    quality["source_contract"]["sources"] = [{
        "instruction_sha256": instruction_sha256(source_instruction.strip()),
        "task_id": "coding:070",
        "task_path": f"candidate_cases/{CASE_ID}/private/source_task.yaml",
    }]
    quality["requirements"][0]["public_evidence"] = [
        {"path": "task/task.yaml", "contains": "ASYNC-RBENCH EXTENSION"},
        {"path": "task/task.yaml", "contains": "QuestHub"},
    ]
    dump(CASE / "private/quality_contract.yaml", quality)

    worker = (CASE / "task/task_file/scripts/event_worker.py").read_text(encoding="utf-8")
    worker = worker.replace("SOURCE_ID = 'multi-source-data-merger'", "SOURCE_ID = 'coding:070'")
    worker = worker.replace("EVENT = 'late_source_c_snapshot'", "EVENT = 'authoritative_postgres_checkpoint'")
    worker = worker.replace("The healthcare maintenance checkpoint confirms VACUUM FULL and releases the diagnosis blocked on 500 remaining rows.", "The source-native coding checkpoint makes expected-version rejection mandatory for simultaneous status updates.")
    worker = worker.replace("EVENT = 'authoritative_postgres_checkpoint'", "EVENT = 'late_concurrency_constraint'")
    worker = worker.replace("EVENT = 'late_concurrency_constraint'", "EVENT = 'recovered_revision_schema'")
    worker = worker.replace("The source-native coding checkpoint makes expected-version rejection mandatory for simultaneous status updates.", "The recovered QuestHub schema binds editor saves, realtime events, and external exports to immutable parented revisions.")
    worker = worker.replace("PROBE_PATHS = ['/data/source_a/users.json', '/data/source_b/users.csv', '/data/source_c/users.parquet']", "PROBE_PATHS = ['/app/task_file/native_canonical_report.json']")
    write(CASE / "task/task_file/scripts/event_worker.py", worker)

    solution = """#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json, pathlib
native=json.load(open('/app/task_file/native_canonical_report.json',encoding='utf-8'))
assert native['source_native_marble_verified'] and native['native_evaluator_verified'] and native['native_test_exit_code']==0
pathlib.Path('/app/output_data/solution.py').write_bytes(pathlib.Path('/app/task_file/native_solution.py').read_bytes())
pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps({
  'source_task_id':'coding:070','recovered_artifact':'versioned_quest_skill_sync_schema',
  'stale_resource_versions_rejected':True,'synchronized_surfaces':['quest_board','skill_planner','device_sync'],
  'preserved_workflows':['authentication','quest_collaboration','skill_collaboration','ordered_event_log'],
  'native_evidence_sha256':native['evidence_sha256'],'native_evaluator_metrics':native['native_evaluator_metrics']
},sort_keys=True)+'\\n')
PY
"""
    write(CASE / "task/upstream_solutions/multi-source-data-merger.sh", solution)
    alternative = solution + """
printf '%s\\n' '{"status":"alternative_cross_artifact_recovery"}' > /app/output_data/provisional_checkpoint.json
printf '%s\\n' '{"source_task_id":"coding:070","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
"""
    write(CASE / "task/equivalence_solutions/alternative_solution.sh", alternative)
    tests = '''import importlib.util, json, sys
from pathlib import Path
OUT=Path('/app/output_data'); NATIVE=Path('/app/task_file/native_canonical_report.json')
def load_solution():
 spec=importlib.util.spec_from_file_location('submitted_solution',OUT/'solution.py'); mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
def test_output_files_exist(): assert (OUT/'solution.py').is_file() and (OUT/'coding_closure.json').is_file()
def test_merged_data_exact_values():
 c=json.loads((OUT/'coding_closure.json').read_text()); n=json.loads(NATIVE.read_text()); assert c['source_task_id']=='coding:070'; assert c['recovered_artifact']=='versioned_quest_skill_sync_schema'; assert c['native_evidence_sha256']==n['evidence_sha256']; assert c['stale_resource_versions_rejected'] is True
def test_conflict_report_values():
 m=load_solution(); x=m.QuestHub(); x.register('hero','password1'); x.register('ally','password2'); ht=x.login('hero','password1','pc'); at=x.login('ally','password2','mobile'); q=x.create_quest(ht,'Dragon'); x.share_quest(ht,q.quest_id,'ally'); events=[]; x.subscribe(at,'quest:1',events.append); x.update_quest(at,1,'active',0)
 try: x.update_quest(ht,1,'completed',0); assert False
 except RuntimeError: pass
 p=x.create_skill_plan(ht,'Mage'); x.share_plan(ht,p.plan_id,'ally'); x.set_skill(at,1,'Fireball',70,0); delta=x.sync_since(at,0); assert events[-1]['version']==1 and any(e['resource']=='plan:1' for e in delta); assert set(json.loads((OUT/'coding_closure.json').read_text())['synchronized_surfaces'])=={'quest_board','skill_planner','device_sync'}
'''
    write(CASE / "task/tests/upstream_tests/test_outputs.py", tests)
    dump(CASE / "private/canonical_episode_acceptance.json", {
        "accepted": True,
        "model_episode_required": False,
        "accepted_episode_owner": "evaluator",
        "requirements": ["compiled and executed QuestHub solution", "cross-artifact revision-parent test", "upstream MARBLE evaluate_code_quality binding"],
        "native_report": "private/native_canonical_report.json",
    })
    print(CASE)


if __name__ == "__main__":
    main()
