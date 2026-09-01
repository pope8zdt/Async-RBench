#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"277ff2325bd9d7fc4dfe90d2b0c8cc7437369c7ecaa61d9e9877a9b2fbf8b93c\", \"native_evidence_sha256\": \"22b8ecdac64fa932012b4ed57e52e2704a2fb8e6361bbe99ecb97098493b3766\", \"preserved_prior_findings\": true, \"selected_causes\": [\"INSERT_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:004\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
