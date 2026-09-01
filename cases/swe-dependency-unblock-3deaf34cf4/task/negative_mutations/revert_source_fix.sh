#!/bin/bash
set -euo pipefail
cd /testbed
git apply -R /tmp/gold.patch 2>/dev/null || git diff HEAD | git apply -R
