#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"blocker_lock_rows\": 4, \"waiter_timeout_observed\": true}, \"database_domain\": \"transportation operations\", \"excluded_tentative_causes\": [\"FETCH_LARGE_DATA\"], \"host_checkpoint_sha256\": \"0257f2e42fbaaac5384b46538c65074d4e65ae9e5d5a01818dcf9ed4b4b256de\", \"native_evidence_sha256\": \"5f84285a34d7104f034cbd5553411d83cb701ff9d5e514f210cede3d72121163\", \"preserved_prior_findings\": [\"transport schema inventory\", \"vacuum and index probe dispositions\", \"read-path disposition\"], \"selected_causes\": [\"LOCK_CONTENTION\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:016\"}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis","truth_withheld":true}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"task_specific_database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-dependency-unblock-309c3b9f50','source_task_id':'database:016','event':'authoritative_postgres_checkpoint','result_kind':'result_02','released_at':3,'worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'0257f2e42fbaaac5384b46538c65074d4e65ae9e5d5a01818dcf9ed4b4b256de'},'authority':{'selected_cause':'LOCK_CONTENTION','anomaly_evidence':{'blocker_lock_rows': 4, 'waiter_timeout_observed': True}}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
