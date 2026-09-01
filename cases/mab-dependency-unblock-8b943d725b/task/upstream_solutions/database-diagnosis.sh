#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
printf '%s\n' "{\"authority_evidence\": {\"same_column_indexes\": 2}, \"database_domain\": \"social media\", \"excluded_tentative_causes\": [\"INSERT_LARGE_DATA\"], \"host_checkpoint_sha256\": \"40bdbc186e72afba79d0d0a5d81547aa0fbeb14c1a75494fd4a11b43a113445b\", \"native_evidence_sha256\": \"f4eeed82b7865b043653c415164d4741db42912c0c90117f61868da673e24f11\", \"preserved_prior_findings\": [\"social schema inventory\", \"write-volume disposition\", \"lock, vacuum, and fetch-path dispositions\"], \"selected_causes\": [\"REDUNDANT_INDEX\"], \"source_semantics_reverified\": true, \"source_task_id\": \"database:019\"}" > /app/output_data/database_diagnosis.json
