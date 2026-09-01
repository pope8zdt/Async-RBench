from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml
from async_rbench.case_quality import instruction_sha256

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-conflicting-specialist-results-9ec14bb2f1"
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
    public["title"] = "Async-RBench source-native e-commerce lock diagnosis: database:005"
    public["source_tasks"] = [{"benchmark": "MultiAgentBench", "id": "database:005"}]
    public["workstreams"][0]["expected_output"] = "A provisional comparison of the e-commerce workload across insert, lock, vacuum, index, and oversized-read hypotheses."
    public["workstreams"][0]["task"] = "Inspect the supplied canonical PostgreSQL evidence and report the strongest competing diagnosis before authority arrives."
    public["workstreams"][1]["expected_output"] = "Receipt-bound PostgreSQL evidence of four blocker lock rows and an observed waiter timeout."
    public["workstreams"][1]["task"] = "Independently validate the host-owned PostgreSQL checkpoint and report whether LOCK_CONTENTION is the authoritative cause."
    dump(CASE / "public_case.yaml", public)

    private = load(CASE / "private/private_case.yaml")
    private["classification"]["primary_event_theme"] = "conflicting_valid_results"
    private["event_contracts"][0]["event_theme"] = "conflicting_valid_results"
    private["event_contracts"][0]["state_delta"]["after"] = "authoritative LOCK_CONTENTION evidence displaces the provisional bulk-insert diagnosis"
    private["result_contract"]["rule"] = "Arbitrate conflicting specialist results by adopting the post-checkpoint PostgreSQL authority receipt; completion order alone is not authority."
    dump(CASE / "private/private_case.yaml", private)

    shutil.copy2(BLUEPRINT / "private/source_lock.json", CASE / "private/source_lock.json")
    shutil.copy2(RUNTIME / "native_canonical_report.json", CASE / "private/native_canonical_report.json")
    shutil.copy2(RUNTIME / "native_canonical_report.json", CASE / "task/task_file/native_canonical_report.json")
    dump(CASE / "private/source_task.yaml", {"instruction": source_instruction})

    task = load(CASE / "task/task.yaml")
    extension = """

ASYNC-RBENCH EXTENSION
First persist a provisional comparison of all five declared root-cause hypotheses. An independent authority worker then returns a receipt bound to the host-owned PostgreSQL checkpoint. Reopen the diagnosis, preserve the valid comparison, adopt the authoritative receipt, and close with exactly LOCK_CONTENTION as the selected cause. Write the final receipt-bound closure under /app/output_data.
""".rstrip()
    task["instruction"] = source_instruction + extension
    task["category"] = "multiagentbench"
    task["tags"] = ["multiagentbench", "database", "e-commerce", "lock-contention", "conflicting_valid_results"]
    write(CASE / "task/task.yaml", yaml.safe_dump(task, sort_keys=False, allow_unicode=True))
    write(CASE / "instruction.md", task["instruction"] + "\n")

    quality = load(CASE / "private/quality_contract.yaml")
    quality["source_contract"]["sources"] = [{
        "instruction_sha256": instruction_sha256(source_instruction.strip()),
        "task_id": "database:005",
        "task_path": f"candidate_cases/{CASE_ID}/private/source_task.yaml",
    }]
    quality["requirements"][0]["public_evidence"] = [
        {"path": "task/task.yaml", "contains": "ASYNC-RBENCH EXTENSION"},
        {"path": "task/task.yaml", "contains": "This database is used in an e-commerce system"},
    ]
    dump(CASE / "private/quality_contract.yaml", quality)

    worker = (CASE / "task/task_file/scripts/event_worker.py").read_text(encoding="utf-8")
    worker = worker.replace("SOURCE_ID = 'multi-source-data-merger'", "SOURCE_ID = 'database:005'")
    worker = worker.replace("EVENT = 'late_source_c_snapshot'", "EVENT = 'authoritative_postgres_checkpoint'")
    worker = worker.replace("The host-owned music-catalog checkpoint records 5,000 fetched rows and 1,280,000 payload bytes, confirming FETCH_LARGE_DATA.", "The host-owned e-commerce checkpoint records four blocker lock rows and a waiter timeout, confirming LOCK_CONTENTION.")
    worker = worker.replace("PROBE_PATHS = ['/data/source_a/users.json', '/data/source_b/users.csv', '/data/source_c/users.parquet']", "PROBE_PATHS = ['/app/task_file/native_canonical_report.json']")
    write(CASE / "task/task_file/scripts/event_worker.py", worker)

    solution = """#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json, pathlib
native=json.load(open('/app/task_file/native_canonical_report.json',encoding='utf-8'))
assert native['source_native_marble_verified'] and native['native_evaluator_verified']
assert native['host_checkpoint']['anomaly_evidence']=={'blocker_lock_rows':4,'waiter_timeout_observed':True}
pathlib.Path('/app/output_data/database_diagnosis.json').write_text(json.dumps({
  'source_task_id':'database:005','selected_causes':['LOCK_CONTENTION'],
  'provisional_competing_diagnosis':'INSERT_LARGE_DATA','workload':'ecommerce_orders',
  'blocker_lock_rows':4,'waiter_timeout_observed':True,'native_evidence_sha256':native['evidence_sha256']
},sort_keys=True)+'\\n')
PY
"""
    write(CASE / "task/upstream_solutions/multi-source-data-merger.sh", solution)
    alternative = solution + """
printf '%s\\n' '{"status":"alternative_lock_checkpoint"}' > /app/output_data/provisional_checkpoint.json
printf '%s\\n' '{"source_task_id":"database:005","preserved":true}' > /app/output_data/preserved_source_facts.json
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
