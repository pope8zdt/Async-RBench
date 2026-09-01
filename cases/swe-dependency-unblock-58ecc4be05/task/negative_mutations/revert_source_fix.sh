#!/bin/bash
set -euo pipefail
cd /testbed
git checkout HEAD -- src/builder/command.rs src/builder/arg.rs
