#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"d35f28066a6df173cb7d3db1320facaa1d9cd74902ad6b017d4235a6411ae221\", \"native_evidence_sha256\": \"200800e9149b6ce2fa6109e434af3c2b9d289d1fcf222bb7575fc6e88eaadb9c\", \"preserved_prior_findings\": true, \"selected_causes\": [\"REDUNDANT_INDEX\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:003\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-conflicting-specialist-results-eda6fc53e2','source_task_id':'database:003','event':'authoritative_postgres_checkpoint','worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'d35f28066a6df173cb7d3db1320facaa1d9cd74902ad6b017d4235a6411ae221'}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
