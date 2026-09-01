#!/usr/bin/env bash
set -euo pipefail
cd /app
bash /async_rbench/upstream_solutions/db-wal-recovery.sh
bash /async_rbench/upstream_solutions/multi-source-data-merger.sh
bash /async_rbench/upstream_solutions/kv-store-grpc.sh
python3 - <<'PY'
import hashlib, json
from pathlib import Path
import pandas as pd

recovered=json.loads(Path('/app/recovered.json').read_text())
merged=pd.read_parquet('/app/merged_users.parquet')
seed={f"item:{row['name']}": int(row['value']) for row in recovered}
seed.update({f"user:{int(row.user_id)}": 1 if row.status == 'active' else 0 for row in merged.itertuples()})
Path('/app/service_seed.json').write_text(json.dumps(seed, sort_keys=True, indent=2))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
lineage={'recovered_sha256':sha('/app/recovered.json'), 'merged_sha256':sha('/app/merged_users.parquet'),
         'seed_sha256':sha('/app/service_seed.json'), 'recovered_row_count':len(recovered)}
Path('/app/service-lineage.json').write_text(json.dumps(lineage, sort_keys=True, indent=2))

p=Path('/app/server.py'); s=p.read_text()
s=s.replace('self.kv_dict: dict[str, int] = {}', "self.kv_dict: dict[str, int] = json.loads(open('/app/service_seed.json').read())")
s=s.replace('import grpc\n', 'import grpc\nimport json\n', 1)
p.write_text(s)
PY
pkill -f 'python server.py' || true
cd /app
nohup python server.py >/tmp/async_rbench-grpc.log 2>&1 &
for i in $(seq 1 20); do
  python3 -c "import socket; s=socket.socket(); s.settimeout(.2); raise SystemExit(0 if s.connect_ex(('127.0.0.1',5328)) == 0 else 1)" && exit 0 || true
  sleep .2
done
exit 1
