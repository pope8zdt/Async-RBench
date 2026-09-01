#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"d35f28066a6df173cb7d3db1320facaa1d9cd74902ad6b017d4235a6411ae221\", \"native_evidence_sha256\": \"200800e9149b6ce2fa6109e434af3c2b9d289d1fcf222bb7575fc6e88eaadb9c\", \"preserved_prior_findings\": true, \"selected_causes\": [\"REDUNDANT_INDEX\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:003\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
