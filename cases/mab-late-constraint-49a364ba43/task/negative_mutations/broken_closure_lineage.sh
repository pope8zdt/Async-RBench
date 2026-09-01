#!/bin/bash
set -euo pipefail
sed -i 's/"event_consumed": true/"event_consumed": false/' /app/output_data/decision_manifest.json
