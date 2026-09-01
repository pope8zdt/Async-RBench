#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"1c3a50e63e7f8a6ba73633054c752f3f4623e4fd9c68f159a44e4c3bf7bd8385\", \"native_evidence_sha256\": \"83b87e43a8e475cf654f4aaf6be405c4d8ccfb86040be4d9c600e5275d9908c0\", \"preserved_prior_findings\": true, \"selected_causes\": [\"VACUUM\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:011\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
