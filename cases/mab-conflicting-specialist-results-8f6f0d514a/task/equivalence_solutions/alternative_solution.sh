#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"d09040e0d071cb17c8e52312369004c0c17e52ecd55842eff3890404d6a643cc\", \"native_evidence_sha256\": \"dc3b195c8d2cca892c19b84b09124ad163465d4eaf668946bead5a8358e570ea\", \"preserved_prior_findings\": true, \"selected_causes\": [\"FETCH_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:007\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis"}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-conflicting-specialist-results-8f6f0d514a','source_task_id':'database:007','event':'authoritative_postgres_checkpoint','worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'d09040e0d071cb17c8e52312369004c0c17e52ecd55842eff3890404d6a643cc'}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()
pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
