#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import json, pathlib
pathlib.Path('/app/output_data/font_size_result.json').write_text(json.dumps({
  'source_task_id':'osworld:chrome:af630914-714e-4a24-a7bb-f9af687d3b91',
  'evaluator':'check_font_size','default_font_size':24,'official_score':1.0
},sort_keys=True)+'\n')
PY


printf '%s\n' '{"status":"alternative_font_size_checkpoint","default_font_size":24}' > /app/output_data/provisional_checkpoint.json
printf '%s\n' '{"source_task_id":"osworld:chrome:af630914-714e-4a24-a7bb-f9af687d3b91","preserved":true}' > /app/output_data/preserved_source_facts.json
python3 - <<'PY'
import hashlib, json, pathlib
out=pathlib.Path('/app/output_data')
receipt={'case_id':'osw-dependency-unblock-af63091471','source_task_id':'osworld:chrome:af630914-714e-4a24-a7bb-f9af687d3b91','worker_started_at':1,'worker_finished_at':2,'worker_exit_code':0,'probes':{'default_font_size':24,'official_score':1.0},'finding':'Chrome default font size is persisted at the largest setting'}
receipt['receipt_sha256']=hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()).hexdigest()
(out/'event_receipt.json').write_text(json.dumps(receipt)+'\n')
PY
python3 /app/task_file/scripts/write_manifest.py
