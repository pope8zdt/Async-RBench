#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"5932d06eb74bb685d2600424226fcc2a4d802528b7dd3df0516e0990f02a20c7\", \"native_evidence_sha256\": \"bd2449c5466652ee1f79f6a7433093683df327ecce051192fc28598df645712f\", \"preserved_prior_findings\": true, \"selected_causes\": [\"LOCK_CONTENTION\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:005\", \"superseded_causes\": [\"FETCH_LARGE_DATA\"]}" > /app/output_data/database_diagnosis.json
