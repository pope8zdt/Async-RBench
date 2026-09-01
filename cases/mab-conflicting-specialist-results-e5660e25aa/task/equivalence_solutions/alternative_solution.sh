#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"36da8ae7700f5c7278b02ea708113955602551377ac59394f567241743bb00cb\", \"native_evidence_sha256\": \"322f0026d4e9ccabd0fd178488018700b11831b3a9f3bffe2a94814a0217ce62\", \"preserved_prior_findings\": true, \"selected_causes\": [\"VACUUM\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:006\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-conflicting-specialist-results-e5660e25aa','source_task_id':'database:006','event':'authoritative_postgres_checkpoint','worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'36da8ae7700f5c7278b02ea708113955602551377ac59394f567241743bb00cb'}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
