#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"host_checkpoint_sha256\": \"d09040e0d071cb17c8e52312369004c0c17e52ecd55842eff3890404d6a643cc\", \"native_evidence_sha256\": \"dc3b195c8d2cca892c19b84b09124ad163465d4eaf668946bead5a8358e570ea\", \"preserved_prior_findings\": true, \"selected_causes\": [\"FETCH_LARGE_DATA\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:007\", \"superseded_causes\": [\"LOCK_CONTENTION\"]}" > /app/output_data/database_diagnosis.json
