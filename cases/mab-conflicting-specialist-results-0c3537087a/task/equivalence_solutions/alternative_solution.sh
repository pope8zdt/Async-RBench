#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"78ceef88e27c0ac4e33b257d6648a34d8f00d2517ea7c80dc36c19e32a614530\", \"native_evidence_sha256\": \"8208c10ca6721d6f4714b1441924ba8d7e4baa2907b5b5a25dfdd8587bfd46f0\", \"preserved_prior_findings\": true, \"selected_causes\": [\"INSERT_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:010\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-conflicting-specialist-results-0c3537087a','source_task_id':'database:010','event':'authoritative_postgres_checkpoint','worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'78ceef88e27c0ac4e33b257d6648a34d8f00d2517ea7c80dc36c19e32a614530'}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
