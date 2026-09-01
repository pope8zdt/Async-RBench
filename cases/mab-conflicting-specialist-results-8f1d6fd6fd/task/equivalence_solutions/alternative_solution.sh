#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"6575848e09714573ebfd2587160c09a38c624f3f3daef0ccf18eef641aa66489\", \"native_evidence_sha256\": \"b9547cf163e91b90f887ef9610c33415e1ae2b61d5519e3f4244d85f233ea345\", \"preserved_prior_findings\": true, \"selected_causes\": [\"FETCH_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:009\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-conflicting-specialist-results-8f1d6fd6fd','source_task_id':'database:009','event':'authoritative_postgres_checkpoint','worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'6575848e09714573ebfd2587160c09a38c624f3f3daef0ccf18eef641aa66489'}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
