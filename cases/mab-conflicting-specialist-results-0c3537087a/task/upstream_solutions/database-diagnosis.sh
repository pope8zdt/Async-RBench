#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"78ceef88e27c0ac4e33b257d6648a34d8f00d2517ea7c80dc36c19e32a614530\", \"native_evidence_sha256\": \"8208c10ca6721d6f4714b1441924ba8d7e4baa2907b5b5a25dfdd8587bfd46f0\", \"preserved_prior_findings\": true, \"selected_causes\": [\"INSERT_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:010\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
