#!/usr/bin/env bash
set -euo pipefail
cd /app
bash /async_rbench/upstream_solutions/pytorch-model-recovery.sh
bash /async_rbench/upstream_solutions/torch-tensor-parallelism.sh
bash /async_rbench/upstream_solutions/torch-pipeline-parallelism.sh
bash /async_rbench/upstream_solutions/llm-inference-batching-scheduler.sh
python3 - <<'PY'
import hashlib, json
from pathlib import Path
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
d={
 'backend':'pipeline', 'profile_version':'v2', 'world_size':2,
 'model_sha256':sha('/app/model.pt'),
 'implementation_sha256':sha('/app/pipeline_parallel.py'),
 'plan_b1_sha256':sha('/app/task_file/output_data/plan_b1.jsonl'),
 'plan_b2_sha256':sha('/app/task_file/output_data/plan_b2.jsonl')}
Path('/app/deployment.json').write_text(json.dumps(d, sort_keys=True, indent=2))
lineage={k:d[k] for k in ('backend','profile_version','plan_b1_sha256','plan_b2_sha256')}
Path('/app/batch-lineage.json').write_text(json.dumps(lineage, sort_keys=True, indent=2))
PY
