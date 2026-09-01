#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"remaining_rows\": 500, \"vacuum_full_executed\": true}, \"database_domain\": \"healthcare management\", \"excluded_tentative_causes\": [\"LOCK_CONTENTION\"], \"host_checkpoint_sha256\": \"893f6fa5b23d721446e95ce968a9b16cefb92639f000d3d4acb919e3362763cb\", \"native_evidence_sha256\": \"4e8f55ffc936d4d6a9eadc1dadc703412df4156f08b5c2a2e5f6f999aa53a5aa\", \"preserved_prior_findings\": [\"appointment and treatment schema inventory\", \"lock-contention probe disposition\", \"index and fetch-path dispositions\"], \"selected_causes\": [\"VACUUM\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:021\"}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis","truth_withheld":true}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"task_specific_database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-dependency-unblock-18d7c09304','source_task_id':'database:021','event':'authoritative_postgres_checkpoint','result_kind':'result_02','released_at':3,'worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'893f6fa5b23d721446e95ce968a9b16cefb92639f000d3d4acb919e3362763cb'},'authority':{'selected_cause':'VACUUM','anomaly_evidence':{'remaining_rows': 500, 'vacuum_full_executed': True}}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
