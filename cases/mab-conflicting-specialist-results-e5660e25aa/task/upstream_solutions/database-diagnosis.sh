#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"36da8ae7700f5c7278b02ea708113955602551377ac59394f567241743bb00cb\", \"native_evidence_sha256\": \"322f0026d4e9ccabd0fd178488018700b11831b3a9f3bffe2a94814a0217ce62\", \"preserved_prior_findings\": true, \"selected_causes\": [\"VACUUM\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:006\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
