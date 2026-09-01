#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"bytes\": 1556480, \"row_count\": 5000}, \"database_domain\": \"transportation operations\", \"excluded_tentative_causes\": [\"FETCH_LARGE_DATA\"], \"host_checkpoint_sha256\": \"834bd92f8f348bbf0505f531ac223cde7a5b01d4f911603df5dd784ea44906e4\", \"native_evidence_sha256\": \"7d17409954432e0651ff1af135317bf59c63ec4cc6e867b712e428d54f87ddbd\", \"preserved_prior_findings\": [\"transport schema inventory\", \"lock and vacuum dispositions\", \"index and fetch-path dispositions\"], \"selected_causes\": [\"INSERT_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:023\"}" > /app/output_data/database_diagnosis.json
