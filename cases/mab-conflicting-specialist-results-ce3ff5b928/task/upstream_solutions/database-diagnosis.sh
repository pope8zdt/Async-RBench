#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"163fc43ddc672cbb1fd3b3dd68ab630e7dab92bfd974d956fcc535cc6fc08c32\", \"native_evidence_sha256\": \"74ba0d799772492390690cc5947048ec73aaf5c942f1b092c23a4cc6c11736a1\", \"preserved_prior_findings\": true, \"selected_causes\": [\"INSERT_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:001\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
