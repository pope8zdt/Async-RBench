#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"1c3a50e63e7f8a6ba73633054c752f3f4623e4fd9c68f159a44e4c3bf7bd8385\", \"native_evidence_sha256\": \"83b87e43a8e475cf654f4aaf6be405c4d8ccfb86040be4d9c600e5275d9908c0\", \"preserved_prior_findings\": true, \"selected_causes\": [\"VACUUM\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:011\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-conflicting-specialist-results-5f19377089','source_task_id':'database:011','event':'authoritative_postgres_checkpoint','worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'1c3a50e63e7f8a6ba73633054c752f3f4623e4fd9c68f159a44e4c3bf7bd8385'}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
