# Stable public entry point; the canonical experiment plan remains unchanged.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'experiments/formal-47/run.ps1') @args
