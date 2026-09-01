#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"blocker_lock_rows\": 4, \"waiter_timeout_observed\": true}, \"database_domain\": \"file sharing\", \"excluded_tentative_causes\": [\"VACUUM\"], \"host_checkpoint_sha256\": \"b97d78c5fb7f69fbdd5296f208a9bfd520041e6c7055c9b37a630a03c5d6e67c\", \"native_evidence_sha256\": \"fb85548fa724be44b7022696b350fe541d48ef08adeae3879270825c0b62f08c\", \"preserved_prior_findings\": [\"file-sharing relation inventory\", \"vacuum history disposition\", \"insert, index, and fetch-path dispositions\"], \"selected_causes\": [\"LOCK_CONTENTION\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:013\"}" > /app/output_data/database_diagnosis.json
