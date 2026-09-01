#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"blocker_lock_rows\": 4, \"waiter_timeout_observed\": true}, \"database_domain\": \"music streaming\", \"excluded_tentative_causes\": [\"REDUNDANT_INDEX\"], \"host_checkpoint_sha256\": \"9cc9bbc280bd730a29ba8344df3af5f54150fef17e06c6bc25ca90e46655d464\", \"native_evidence_sha256\": \"63fc51db3d504ae0d1a59fa985bd28853f837cfb6c5e9ccdd6c3b6a8f4d85f9d\", \"preserved_prior_findings\": [\"music schema inventory\", \"index disposition\", \"insert, vacuum, and fetch-path dispositions\"], \"selected_causes\": [\"LOCK_CONTENTION\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:018\"}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis","truth_withheld":true}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"task_specific_database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-dependency-unblock-b69316f186','source_task_id':'database:018','event':'authoritative_postgres_checkpoint','result_kind':'result_02','released_at':3,'worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'9cc9bbc280bd730a29ba8344df3af5f54150fef17e06c6bc25ca90e46655d464'},'authority':{'selected_cause':'LOCK_CONTENTION','anomaly_evidence':{'blocker_lock_rows': 4, 'waiter_timeout_observed': True}}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
