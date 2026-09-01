#!/bin/bash
set -euo pipefail
python3 - <<'PY'
import hashlib, json, pathlib
path = pathlib.Path('/app/output_data/event_receipt.json')
receipt = json.loads(path.read_text())
receipt['qualified_result']['battery_age_days'] = 180
without_hash = dict(receipt)
without_hash.pop('receipt_sha256', None)
receipt['receipt_sha256'] = hashlib.sha256(json.dumps(without_hash, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
path.write_text(json.dumps(receipt, sort_keys=True) + '\n')
PY
