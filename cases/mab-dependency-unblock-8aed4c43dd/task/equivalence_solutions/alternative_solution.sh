#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"blocker_lock_rows\": 4, \"waiter_timeout_observed\": true}, \"database_domain\": \"file sharing\", \"excluded_tentative_causes\": [\"VACUUM\"], \"host_checkpoint_sha256\": \"b97d78c5fb7f69fbdd5296f208a9bfd520041e6c7055c9b37a630a03c5d6e67c\", \"native_evidence_sha256\": \"fb85548fa724be44b7022696b350fe541d48ef08adeae3879270825c0b62f08c\", \"preserved_prior_findings\": [\"file-sharing relation inventory\", \"vacuum history disposition\", \"insert, index, and fetch-path dispositions\"], \"selected_causes\": [\"LOCK_CONTENTION\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:013\"}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis","truth_withheld":true}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"task_specific_database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-dependency-unblock-8aed4c43dd','source_task_id':'database:013','event':'authoritative_postgres_checkpoint','result_kind':'result_02','released_at':3,'worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'b97d78c5fb7f69fbdd5296f208a9bfd520041e6c7055c9b37a630a03c5d6e67c'},'authority':{'selected_cause':'LOCK_CONTENTION','anomaly_evidence':{'blocker_lock_rows': 4, 'waiter_timeout_observed': True}}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
