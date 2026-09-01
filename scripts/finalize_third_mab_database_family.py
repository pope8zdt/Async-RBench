from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-conflicting-specialist-results-5f19377089"
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
    public["title"] = "Async-RBench source-native database diagnosis: database:011"
    public["source_tasks"] = [{"benchmark": "MultiAgentBench", "id": "database:011"}]
    public["workstreams"][0]["expected_output"] = "A provisional specialist comparison covering the maintenance pressure against its competing lock, vacuum, index, and fetch hypotheses."
    public["workstreams"][0]["task"] = "Inspect the supplied canonical PostgreSQL evidence and report the strongest competing diagnosis before authority arrives."
    authority = public["workstreams"][1]
    authority["expected_output"] = "A promotable, receipt-bound authoritative PostgreSQL report identifying VACUUM, together with /app/output_data/event_receipt.json."
    authority["task"] = "Use the evaluator-staged /app/task_file/scripts/event_worker.py to validate the host-owned PostgreSQL checkpoint. Run it with --workspace /app, then report its observed VACUUM finding, checkpoint revision, receipt path, and receipt digest. Do not replace the staged checkpoint probe with a connection to a live localhost PostgreSQL service."
    authority["allowed_files"] = [
        "/app/output_data/workstreams/requirement_worker_02.json",
        "/app/output_data/event_receipt.json",
    ]
    authority["required_files"] = list(authority["allowed_files"])
    authority["required_evidence_fields"] = [
        "report_path", "receipt_path", "receipt_sha256", "revision_sha256", "finding",
    ]
    authority["evidence_schema"].update({
        "receipt_path": {"type": "string", "pattern": "^/app/output_data/event_receipt\\.json$"},
        "receipt_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    })
    artifact_ids = {item["id"] for item in public["artifacts"]}
    if "authority_receipt" not in artifact_ids:
        public["artifacts"].insert(-1, {
            "id": "authority_receipt", "path": "/app/output_data/event_receipt.json",
        })
    if "database_diagnosis" not in artifact_ids:
        public["artifacts"].insert(-1, {
            "id": "database_diagnosis", "path": "/app/output_data/database_diagnosis.json",
        })
    dump(CASE / "public_case.yaml", public)

    private = load(CASE / "private/private_case.yaml")
    private["classification"]["primary_event_theme"] = "conflicting_valid_results"
    private["event_contracts"][0]["event_theme"] = "conflicting_valid_results"
    private["event_contracts"][0]["state_delta"]["after"] = "The receipt-bound authority checkpoint identifies VACUUM and supersedes the provisional LOCK_CONTENTION diagnosis."
    private["result_contract"]["rule"] = "Arbitrate conflicting specialist results by adopting the post-checkpoint PostgreSQL authority receipt; completion order alone is not authority."
    authority_binding = private["workstream_bindings"]["requirement_worker_02"]
    authority_binding["private_evidence_schema"].update({
        "finding": {"type": "string", "const": "VACUUM"},
        "revision_sha256": {
            "type": "string",
            "const": "1c3a50e63e7f8a6ba73633054c752f3f4623e4fd9c68f159a44e4c3bf7bd8385",
        },
        "receipt_path": {
            "type": "string", "const": "/app/output_data/event_receipt.json",
        },
        "receipt_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    })
    authority_binding["validator_command"] = (
        "python3 -c \"import base64,hashlib,json,os; "
        "payload=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64'])); "
        "e=payload['evidence']; report=json.load(open(e['report_path'],encoding='utf-8')); "
        "receipt=json.load(open(e['receipt_path'],encoding='utf-8')); claimed=receipt.pop('receipt_sha256'); "
        "actual=hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()).hexdigest(); "
        "assert claimed==actual==e['receipt_sha256']==report['receipt_sha256']; "
        "assert report['finding']==e['finding']=='VACUUM'; "
        "assert report['revision_sha256']==e['revision_sha256']=='1c3a50e63e7f8a6ba73633054c752f3f4623e4fd9c68f159a44e4c3bf7bd8385'; "
        "assert receipt['case_id']=='mab-conflicting-specialist-results-5f19377089' and receipt['source_task_id']=='database:011' and receipt['worker_exit_code']==0; "
        "assert receipt['probes']['host_checkpoint_sha256']==e['revision_sha256'] and receipt['probes']['selected_cause']=='VACUUM' and receipt['probes']['native_evidence_sha256']=='83b87e43a8e475cf654f4aaf6be405c4d8ccfb86040be4d9c600e5275d9908c0'\""
    )
    for item in private.get("information_sufficiency", []):
        if item.get("workstream_id") == "requirement_worker_02":
            item["required_output_fields"] = [
                "report_path", "receipt_path", "receipt_sha256",
                "revision_sha256", "finding",
            ]
    dump(CASE / "private/private_case.yaml", private)

    shutil.copy2(BLUEPRINT / "private/source_lock.json", CASE / "private/source_lock.json")
    shutil.copy2(RUNTIME / "native_canonical_report.json", CASE / "private/native_canonical_report.json")
    shutil.copy2(RUNTIME / "native_canonical_report.json", CASE / "task/task_file/native_canonical_report.json")
    dump(CASE / "private/source_task.yaml", {"instruction": source_instruction})

    task = load(CASE / "task/task.yaml")
    extension = """

ASYNC-RBENCH EXTENSION
First persist a provisional comparison of all five declared root-cause hypotheses. An independent authority worker then returns a receipt bound to the host-owned PostgreSQL checkpoint. Reopen the diagnosis, preserve the valid comparison, adopt the authoritative receipt, and close with exactly VACUUM as the selected maintenance cause. Write the final receipt-bound closure under /app/output_data.

The source text describes a database, but this isolated participant container does not expose a live localhost PostgreSQL service; the independent authority workstream carries the evaluator-owned checkpoint probe. After accepting that result, promote its /app/output_data/event_receipt.json into the main workspace. Run /app/task_file/scripts/write_database_diagnosis.py to create database_diagnosis.json, then run /app/task_file/scripts/write_manifest.py to create decision_manifest.json. Preserve provisional_checkpoint.json and preserved_source_facts.json. Commit authority_receipt, database_diagnosis, and final_state with final=true and lineage containing the accepted authority completion, then reverify before declaring completion.
""".rstrip()
    task["instruction"] = source_instruction + extension
    task["category"] = "multiagentbench"
    task["tags"] = ["multiagentbench", "database", "conflicting_valid_results"]
    write(CASE / "task/task.yaml", yaml.safe_dump(task, sort_keys=False, allow_unicode=True))
    write(CASE / "instruction.md", task["instruction"] + "\n")

    quality = load(CASE / "private/quality_contract.yaml")
    quality["source_contract"]["sources"] = [{
        "instruction_sha256": hashlib.sha256(source_instruction.encode()).hexdigest(),
        "task_id": "database:011",
        "task_path": f"candidate_cases/{CASE_ID}/private/source_task.yaml",
    }]
    quality["requirements"][0]["public_evidence"] = [
        {"path": "task/task.yaml", "contains": "ASYNC-RBENCH EXTENSION"},
        {"path": "task/task.yaml", "contains": "This database is used for managing financial data"},
    ]
    dump(CASE / "private/quality_contract.yaml", quality)

    worker = (ROOT / "scripts/assets/mab_database_011_event_worker.py").read_text(encoding="utf-8")
    # Keep the authority probe outside the participant image. The evaluator
    # stages it at the public /app/task_file/scripts/event_worker.py destination
    # only for the authority workstream declared in private_case.yaml.
    write(CASE / "task/upstream_solutions/event_worker.py", worker)
    diagnosis_writer = (
        ROOT / "scripts/assets/mab_database_011_write_diagnosis.py"
    ).read_text(encoding="utf-8")
    write(CASE / "task/task_file/scripts/write_database_diagnosis.py", diagnosis_writer)

    solution = """#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json, pathlib
native=json.load(open('/app/task_file/native_canonical_report.json',encoding='utf-8'))
assert native['source_native_marble_verified'] and native['native_evaluator_verified']
pathlib.Path('/app/output_data/database_diagnosis.json').write_text(json.dumps({
  'source_task_id':'database:011','selected_causes':['VACUUM'],
  'provisional_competing_diagnosis':'LOCK_CONTENTION','native_evidence_sha256':native['evidence_sha256']
},sort_keys=True)+'\\n')
PY
"""
    write(CASE / "task/upstream_solutions/multi-source-data-merger.sh", solution)
    write(CASE / "task/equivalence_solutions/alternative_solution.sh", solution + "\n" + (CASE / "task/equivalence_solutions/alternative_solution.sh").read_text(encoding="utf-8").split("mkdir -p /app/output_data", 1)[-1])
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
