#!/bin/bash
set -euo pipefail
cd /testbed
git checkout HEAD -- packages/svelte/src/utils.js
