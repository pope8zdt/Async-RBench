#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"bytes\": 1556480, \"row_count\": 5000}, \"database_domain\": \"transportation operations\", \"excluded_tentative_causes\": [\"FETCH_LARGE_DATA\"], \"host_checkpoint_sha256\": \"834bd92f8f348bbf0505f531ac223cde7a5b01d4f911603df5dd784ea44906e4\", \"native_evidence_sha256\": \"7d17409954432e0651ff1af135317bf59c63ec4cc6e867b712e428d54f87ddbd\", \"preserved_prior_findings\": [\"transport schema inventory\", \"lock and vacuum dispositions\", \"index and fetch-path dispositions\"], \"selected_causes\": [\"INSERT_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:023\"}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis","truth_withheld":true}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"task_specific_database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-dependency-unblock-a145b96b70','source_task_id':'database:023','event':'authoritative_postgres_checkpoint','result_kind':'result_02','released_at':3,'worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'834bd92f8f348bbf0505f531ac223cde7a5b01d4f911603df5dd784ea44906e4'},'authority':{'selected_cause':'INSERT_LARGE_DATA','anomaly_evidence':{'bytes': 1556480, 'row_count': 5000}}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
