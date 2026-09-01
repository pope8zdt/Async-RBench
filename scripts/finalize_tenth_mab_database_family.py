from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml
from async_rbench.case_quality import instruction_sha256

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-conflicting-specialist-results-eda6fc53e2"
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
    public["title"] = "Async-RBench source-native file-sharing index diagnosis: database:003"
    public["source_tasks"] = [{"benchmark": "MultiAgentBench", "id": "database:003"}]
    public["workstreams"][0]["expected_output"] = "A provisional comparison of the file-sharing workload across bulk ingest, lock, vacuum, index, and oversized-read hypotheses."
    public["workstreams"][0]["task"] = "Inspect the supplied canonical PostgreSQL evidence and report the strongest competing diagnosis before authority arrives."
    public["workstreams"][1]["expected_output"] = "Receipt-bound PostgreSQL evidence that two indexes cover the same file-sharing column."
    public["workstreams"][1]["task"] = "Independently validate the host-owned PostgreSQL checkpoint and report whether REDUNDANT_INDEX is the authoritative cause."
    dump(CASE / "public_case.yaml", public)

    private = load(CASE / "private/private_case.yaml")
    private["classification"]["primary_event_theme"] = "conflicting_valid_results"
    private["event_contracts"][0]["event_theme"] = "conflicting_valid_results"
    private["event_contracts"][0]["state_delta"]["after"] = "authoritative REDUNDANT_INDEX evidence displaces the provisional vacuum diagnosis"
    private["result_contract"]["rule"] = "Arbitrate conflicting specialist results by adopting the post-checkpoint PostgreSQL authority receipt; completion order alone is not authority."
    dump(CASE / "private/private_case.yaml", private)

    shutil.copy2(BLUEPRINT / "private/source_lock.json", CASE / "private/source_lock.json")
    shutil.copy2(RUNTIME / "native_canonical_report.json", CASE / "private/native_canonical_report.json")
    shutil.copy2(RUNTIME / "native_canonical_report.json", CASE / "task/task_file/native_canonical_report.json")
    dump(CASE / "private/source_task.yaml", {"instruction": source_instruction})

    task = load(CASE / "task/task.yaml")
    extension = """

ASYNC-RBENCH EXTENSION
First persist a provisional comparison of all five declared root-cause hypotheses. An independent authority worker then returns a receipt bound to the host-owned PostgreSQL checkpoint. Reopen the diagnosis, preserve the valid comparison, adopt the authoritative receipt, and close with exactly REDUNDANT_INDEX as the selected cause. Write the final receipt-bound closure under /app/output_data.
""".rstrip()
    task["instruction"] = source_instruction + extension
    task["category"] = "multiagentbench"
    task["tags"] = ["multiagentbench", "database", "file-sharing", "redundant-index", "conflicting_valid_results"]
    write(CASE / "task/task.yaml", yaml.safe_dump(task, sort_keys=False, allow_unicode=True))
    write(CASE / "instruction.md", task["instruction"] + "\n")

    quality = load(CASE / "private/quality_contract.yaml")
    quality["source_contract"]["sources"] = [{
        "instruction_sha256": instruction_sha256(source_instruction.strip()),
        "task_id": "database:003",
        "task_path": f"candidate_cases/{CASE_ID}/private/source_task.yaml",
    }]
    quality["requirements"][0]["public_evidence"] = [
        {"path": "task/task.yaml", "contains": "ASYNC-RBENCH EXTENSION"},
        {"path": "task/task.yaml", "contains": "This database is used in a File Sharing System"},
    ]
    dump(CASE / "private/quality_contract.yaml", quality)

    worker = (CASE / "task/task_file/scripts/event_worker.py").read_text(encoding="utf-8")
    worker = worker.replace("SOURCE_ID = 'multi-source-data-merger'", "SOURCE_ID = 'database:003'")
    worker = worker.replace("EVENT = 'late_source_c_snapshot'", "EVENT = 'authoritative_postgres_checkpoint'")
    worker = worker.replace("The host-owned education checkpoint confirms VACUUM FULL completed with 500 maintenance rows remaining.", "The host-owned file-sharing checkpoint finds two indexes on the same column, confirming REDUNDANT_INDEX.")
    worker = worker.replace("PROBE_PATHS = ['/data/source_a/users.json', '/data/source_b/users.csv', '/data/source_c/users.parquet']", "PROBE_PATHS = ['/app/task_file/native_canonical_report.json']")
    write(CASE / "task/task_file/scripts/event_worker.py", worker)

    solution = """#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json, pathlib
native=json.load(open('/app/task_file/native_canonical_report.json',encoding='utf-8'))
assert native['source_native_marble_verified'] and native['native_evaluator_verified']
assert native['host_checkpoint']['anomaly_evidence']=={'same_column_indexes':2}
pathlib.Path('/app/output_data/database_diagnosis.json').write_text(json.dumps({
  'source_task_id':'database:003','selected_causes':['REDUNDANT_INDEX'],
  'provisional_competing_diagnosis':'VACUUM','workload':'file_sharing_access_logs',
  'same_column_indexes':2,'native_evidence_sha256':native['evidence_sha256']
},sort_keys=True)+'\\n')
PY
"""
    write(CASE / "task/upstream_solutions/multi-source-data-merger.sh", solution)
    alternative = solution + """
printf '%s\\n' '{"status":"alternative_index_checkpoint"}' > /app/output_data/provisional_checkpoint.json
printf '%s\\n' '{"source_task_id":"database:003","preserved":true}' > /app/output_data/preserved_source_facts.json
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
