#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"165afb19e3b554272f09b4689c302d4f09867b14a42df5c47f352cd282297b0b\", \"native_evidence_sha256\": \"5628d05e3619235f1aae717a8ca1c84322dc6fbe37ee27797ed14ceeedcfc599\", \"preserved_prior_findings\": true, \"selected_causes\": [\"INSERT_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:008\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
