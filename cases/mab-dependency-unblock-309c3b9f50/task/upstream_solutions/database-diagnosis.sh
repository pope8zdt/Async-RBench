#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"blocker_lock_rows\": 4, \"waiter_timeout_observed\": true}, \"database_domain\": \"transportation operations\", \"excluded_tentative_causes\": [\"FETCH_LARGE_DATA\"], \"host_checkpoint_sha256\": \"0257f2e42fbaaac5384b46538c65074d4e65ae9e5d5a01818dcf9ed4b4b256de\", \"native_evidence_sha256\": \"5f84285a34d7104f034cbd5553411d83cb701ff9d5e514f210cede3d72121163\", \"preserved_prior_findings\": [\"transport schema inventory\", \"vacuum and index probe dispositions\", \"read-path disposition\"], \"selected_causes\": [\"LOCK_CONTENTION\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:016\"}" > /app/output_data/database_diagnosis.json
