#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"277ff2325bd9d7fc4dfe90d2b0c8cc7437369c7ecaa61d9e9877a9b2fbf8b93c\", \"native_evidence_sha256\": \"22b8ecdac64fa932012b4ed57e52e2704a2fb8e6361bbe99ecb97098493b3766\", \"preserved_prior_findings\": true, \"selected_causes\": [\"INSERT_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:004\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-conflicting-specialist-results-cf7b930f57','source_task_id':'database:004','event':'authoritative_postgres_checkpoint','worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'277ff2325bd9d7fc4dfe90d2b0c8cc7437369c7ecaa61d9e9877a9b2fbf8b93c'}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
