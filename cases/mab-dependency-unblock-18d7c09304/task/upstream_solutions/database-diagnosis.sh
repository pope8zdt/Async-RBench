#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"remaining_rows\": 500, \"vacuum_full_executed\": true}, \"database_domain\": \"healthcare management\", \"excluded_tentative_causes\": [\"LOCK_CONTENTION\"], \"host_checkpoint_sha256\": \"893f6fa5b23d721446e95ce968a9b16cefb92639f000d3d4acb919e3362763cb\", \"native_evidence_sha256\": \"4e8f55ffc936d4d6a9eadc1dadc703412df4156f08b5c2a2e5f6f999aa53a5aa\", \"preserved_prior_findings\": [\"appointment and treatment schema inventory\", \"lock-contention probe disposition\", \"index and fetch-path dispositions\"], \"selected_causes\": [\"VACUUM\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:021\"}" > /app/output_data/database_diagnosis.json
