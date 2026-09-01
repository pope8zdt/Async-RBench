#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"6575848e09714573ebfd2587160c09a38c624f3f3daef0ccf18eef641aa66489\", \"native_evidence_sha256\": \"b9547cf163e91b90f887ef9610c33415e1ae2b61d5519e3f4244d85f233ea345\", \"preserved_prior_findings\": true, \"selected_causes\": [\"FETCH_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:009\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
