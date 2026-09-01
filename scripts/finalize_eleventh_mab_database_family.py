from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml
from async_rbench.case_quality import instruction_sha256

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-dependency-unblock-18d7c09304"
CASE = ROOT / "candidate_cases" / CASE_ID
BLUEPRINT = ROOT / "candidate_cases/rebuild-to-100/blueprints" / CASE_ID
RUNTIME = ROOT / "candidate_cases/rebuild-to-100/runtime-mab-db" / CASE_ID / "runtime"


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
    public["title"] = "Async-RBench healthcare maintenance dependency unblock: database:021"
    public["source_tasks"] = [{"benchmark": "MultiAgentBench", "id": "database:021"}]
    public["workstreams"][0]["expected_output"] = "A preserved healthcare cause matrix that remains blocked until table counters are tied to the observation window."
    public["workstreams"][0]["task"] = "Preserve supported healthcare findings while marking the final diagnosis blocked on the maintenance checkpoint."
    public["workstreams"][1]["expected_output"] = "A receipt-bound checkpoint confirming VACUUM FULL and releasing the blocked final diagnosis."
    public["workstreams"][1]["task"] = "Validate the host-owned PostgreSQL checkpoint, release the dependency, and close on VACUUM."
    dump(CASE / "public_case.yaml", public)

    private = load(CASE / "private/private_case.yaml")
    private["classification"]["primary_event_theme"] = "task_scope_or_dependency_change"
    private["classification"]["async_scenario_class"] = "live_eventful"
    private["event_contracts"][0]["event_theme"] = "task_scope_or_dependency_change"
    private["event_contracts"][0]["state_delta"]["before"] = "final healthcare diagnosis blocked on authoritative maintenance counters"
    private["event_contracts"][0]["state_delta"]["after"] = "VACUUM checkpoint releases the blocked closure while preserving prior supported findings"
    private["result_contract"]["rule"] = "Do not close while maintenance counters are unbound; consume the host checkpoint receipt, preserve prior findings, then release exactly the dependent VACUUM conclusion."
    dump(CASE / "private/private_case.yaml", private)

    shutil.copy2(BLUEPRINT / "private/source_lock.json", CASE / "private/source_lock.json")
    shutil.copy2(RUNTIME / "native_canonical_report.json", CASE / "private/native_canonical_report.json")
    shutil.copy2(RUNTIME / "native_canonical_report.json", CASE / "task/task_file/native_canonical_report.json")
    dump(CASE / "private/source_task.yaml", {"instruction": source_instruction})

    task = load(CASE / "task/task.yaml")
    extension = """

ASYNC-RBENCH EXTENSION
First persist the supported healthcare cause matrix but keep final closure blocked. An independent authority worker then returns the host-owned PostgreSQL maintenance receipt. Consume that receipt, preserve the prior findings, release the dependency, and close with exactly VACUUM as the selected cause. Write the final receipt-bound closure under /app/output_data.
""".rstrip()
    task["instruction"] = source_instruction + extension
    task["category"] = "multiagentbench"
    task["tags"] = ["multiagentbench", "database", "healthcare", "vacuum", "dependency_unblock"]
    write(CASE / "task/task.yaml", yaml.safe_dump(task, sort_keys=False, allow_unicode=True))
    write(CASE / "instruction.md", task["instruction"] + "\n")

    quality = load(CASE / "private/quality_contract.yaml")
    quality["source_contract"]["sources"] = [{
        "instruction_sha256": instruction_sha256(source_instruction.strip()),
        "task_id": "database:021",
        "task_path": f"candidate_cases/{CASE_ID}/private/source_task.yaml",
    }]
    quality["requirements"][0]["public_evidence"] = [
        {"path": "task/task.yaml", "contains": "ASYNC-RBENCH EXTENSION"},
        {"path": "task/task.yaml", "contains": "This database is used in a healthcare management system"},
    ]
    dump(CASE / "private/quality_contract.yaml", quality)

    worker = (CASE / "task/task_file/scripts/event_worker.py").read_text(encoding="utf-8")
    worker = worker.replace("SOURCE_ID = 'multi-source-data-merger'", "SOURCE_ID = 'database:021'")
    worker = worker.replace("EVENT = 'late_source_c_snapshot'", "EVENT = 'authoritative_postgres_checkpoint'")
    worker = worker.replace("The host-owned education checkpoint confirms VACUUM FULL completed with 500 maintenance rows remaining.", "The healthcare maintenance checkpoint confirms VACUUM FULL and releases the diagnosis blocked on 500 remaining rows.")
    worker = worker.replace("PROBE_PATHS = ['/data/source_a/users.json', '/data/source_b/users.csv', '/data/source_c/users.parquet']", "PROBE_PATHS = ['/app/task_file/native_canonical_report.json']")
    write(CASE / "task/task_file/scripts/event_worker.py", worker)

    solution = """#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json, pathlib
native=json.load(open('/app/task_file/native_canonical_report.json',encoding='utf-8'))
assert native['source_native_marble_verified'] and native['native_evaluator_verified']
assert native['host_checkpoint']['anomaly_evidence']=={'remaining_rows':500,'vacuum_full_executed':True}
pathlib.Path('/app/output_data/database_diagnosis.json').write_text(json.dumps({
  'source_task_id':'database:021','selected_causes':['VACUUM'],
  'blocked_before_receipt':True,'dependency_released':True,'preserved_prior_findings':True,
  'workload':'healthcare_records_maintenance','remaining_rows':500,'vacuum_full_executed':True,
  'native_evidence_sha256':native['evidence_sha256']
},sort_keys=True)+'\\n')
PY
"""
    write(CASE / "task/upstream_solutions/multi-source-data-merger.sh", solution)
    alternative = solution + """
printf '%s\\n' '{"status":"alternative_dependency_release"}' > /app/output_data/provisional_checkpoint.json
printf '%s\\n' '{"source_task_id":"database:021","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 /app/task_file/scripts/event_worker.py --workspace /app
python3 /app/task_file/scripts/write_manifest.py
"""
    write(CASE / "task/equivalence_solutions/alternative_solution.sh", alternative)
    dump(CASE / "private/canonical_episode_acceptance.json", {
        "accepted": True,
        "model_episode_required": False,
        "accepted_episode_owner": "evaluator",
        "requirements": ["real PostgreSQL anomaly", "host-owned checkpoint", "upstream MARBLE evaluate_task_db binding"],
        "native_report": "private/native_canonical_report.json",
    })
    print(CASE)


if __name__ == "__main__":
    main()
