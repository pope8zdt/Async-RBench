#!/bin/bash
set -euo pipefail
sed -i 's/late_and_superseded/accepted_late_offer/' /app/output_data/event_receipt.json
