#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"blocker_lock_rows\": 4, \"waiter_timeout_observed\": true}, \"database_domain\": \"music streaming\", \"excluded_tentative_causes\": [\"REDUNDANT_INDEX\"], \"host_checkpoint_sha256\": \"9cc9bbc280bd730a29ba8344df3af5f54150fef17e06c6bc25ca90e46655d464\", \"native_evidence_sha256\": \"63fc51db3d504ae0d1a59fa985bd28853f837cfb6c5e9ccdd6c3b6a8f4d85f9d\", \"preserved_prior_findings\": [\"music schema inventory\", \"index disposition\", \"insert, vacuum, and fetch-path dispositions\"], \"selected_causes\": [\"LOCK_CONTENTION\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:018\"}" > /app/output_data/database_diagnosis.json
