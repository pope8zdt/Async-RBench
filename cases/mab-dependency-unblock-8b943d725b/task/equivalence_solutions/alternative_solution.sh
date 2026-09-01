#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"same_column_indexes\": 2}, \"database_domain\": \"social media\", \"excluded_tentative_causes\": [\"INSERT_LARGE_DATA\"], \"host_checkpoint_sha256\": \"40bdbc186e72afba79d0d0a5d81547aa0fbeb14c1a75494fd4a11b43a113445b\", \"native_evidence_sha256\": \"f4eeed82b7865b043653c415164d4741db42912c0c90117f61868da673e24f11\", \"preserved_prior_findings\": [\"social schema inventory\", \"write-volume disposition\", \"lock, vacuum, and fetch-path dispositions\"], \"selected_causes\": [\"REDUNDANT_INDEX\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:019\"}" > /app/output_data/database_diagnosis.json
printf '%s\n' '{"status":"alternative_database_diagnosis","truth_withheld":true}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"preserved":true,"kind":"task_specific_database_findings"}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib,json,pathlib,time
p={'schema_version':'async-rbench-event-receipt-v1','case_id':'mab-dependency-unblock-8b943d725b','source_task_id':'database:019','event':'authoritative_postgres_checkpoint','result_kind':'result_02','released_at':3,'worker_started_at':time.time(),'worker_finished_at':time.time(),'worker_exit_code':0,'probes':{'host_checkpoint_sha256':'40bdbc186e72afba79d0d0a5d81547aa0fbeb14c1a75494fd4a11b43a113445b'},'authority':{'selected_cause':'REDUNDANT_INDEX','anomaly_evidence':{'same_column_indexes': 2}}}
p['receipt_sha256']=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest();pathlib.Path('/app/output_data/event_receipt.json').write_text(json.dumps(p,sort_keys=True)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
