# Run a seeded random sample of Async-RBench cases (1-2 per event-theme / case
# family) through the qwen3-coder-480b-a35b-instruct relay model.
#
# WHY THIS SHAPE: the sampled instance list lives in THIS file, not on the
# command line. Each iteration calls run_case.ps1 with a single short
# -Instance argument, so no command line ever approaches Windows' length
# ceiling (~8k chars in cmd.exe / ~32k in CreateProcess). Run from the repo
# root and the driver prepends the venv python to PATH so run_case.ps1's bare
# `python` resolves to the .venv interpreter (the one with yaml + jsonschema).
#
# Prereqs: Docker Linux engine running; repo validated (run_case does it each
# run); QWEN3_CODER_API_KEY set in the session or provided at the prompt.

param(
    [string]$Config = "configs/model-profiles/qwen3-coder-480b-a35b-instruct-relay.yaml",
    [int]$Repetitions = 1,
    [int]$Seed = 2026
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# 1) Make bare `python` resolve to the venv interpreter (has yaml/jsonschema).
$venvScripts = Join-Path $PSScriptRoot ".venv\Scripts"
if (Test-Path -LiteralPath $venvScripts) {
    $env:PATH = "$venvScripts;$env:PATH"
}
python -c "import yaml, async_rbench" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "The .venv python (with yaml + async_rbench) must be on PATH. Activate .venv and re-run."
}

# 2) Resolve and verify the model config.
$configPath = Join-Path $PSScriptRoot $Config
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Model config not found: $configPath"
}

# 3) API credential — required by this profile (api_key_env: QWEN3_CODER_API_KEY).
if ([string]::IsNullOrWhiteSpace($env:QWEN3_CODER_API_KEY)) {
    try {
        $env:QWEN3_CODER_API_KEY = Read-Host "QWEN3_CODER_API_KEY" -MaskInput
    } catch {
        # Windows PowerShell 5.1 has no -MaskInput; fall back to a plain prompt.
        $env:QWEN3_CODER_API_KEY = Read-Host "QWEN3_CODER_API_KEY"
    }
    if ([string]::IsNullOrWhiteSpace($env:QWEN3_CODER_API_KEY)) {
        throw "No QWEN3_CODER_API_KEY provided."
    }
}

# 4) Docker Linux engine must be up (run_case.ps1 re-checks, but fail fast here).
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker is not on PATH."
}
docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Linux engine is not running."
}
Write-Host ("[preflight] model=" + $Config + "  seed=" + $Seed + "  reps=" + $Repetitions) -ForegroundColor Cyan

# 5) The sampled instances. Seed=2026, 1-2 per theme, calibration/development
#    only (test-split cases excluded per runbook policy). One run per instance.
$instances = @(
    'mab-dependency-unblock-2cf6576816::seed-1',
    'mab-conflicting-specialist-results-5f19377089::seed-1',
    'swe-late-constraint-acaa77b306::seed-1',
    'swe-late-constraint-3a01a4fcef::seed-1',
    'mab-late-test-evidence-60efb2bdee::seed-1',
    'mab-late-test-evidence-4c6c77884e::seed-1',
    'mab-dependency-unblock-1c96d4414d::seed-1',
    'mab-cross-app-artifact-7bfdfeaa3c::seed-1',
    'mab-dependency-unblock-0daa930906::seed-1',
    'swe-late-constraint-3950516755::seed-1',
    'tbn-late-test-evidence-30aa2ad8de::seed-1'
)

$ok = @()
$fail = @()
$skip = @()

foreach ($inst in $instances) {
    Write-Host "`n===== $inst =====" -ForegroundColor Cyan

    # Idempotent re-run guard: skip only if a run already COMPLETED (results.json
    # present). A prior failed/partial attempt leaves a directory without
    # results.json, so a fresh attempt is started (auto-named, non-destructive).
    $safe = ($inst -replace '::', '-' -replace '[^A-Za-z0-9._-]', '-')
    $prior = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot "artifacts\experiments") `
        -Directory -Filter "manual-$safe-*" -ErrorAction SilentlyContinue
    $completed = $prior | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "results.json") }
    if ($completed) {
        Write-Host ("[skip] already completed -> " + $completed[0].Name) -ForegroundColor Yellow
        $skip += $inst
        continue
    } elseif ($prior) {
        Write-Host ("[note] prior incomplete run for " + $inst + " -> starting a fresh attempt") -ForegroundColor Magenta
    }

    try {
        & .\run_case.ps1 -Instance $inst -Config $Config -Repetitions $Repetitions -Seed $Seed
        $ok += $inst
    } catch {
        Write-Host ("[FAIL] " + $inst + " : " + $_.Exception.Message) -ForegroundColor Red
        $fail += $inst
    }
}

Write-Host "`n===== SUMMARY =====" -ForegroundColor Green
Write-Host ("ok:    " + $ok.Count)
Write-Host ("skip:  " + $skip.Count)
Write-Host ("fail:  " + $fail.Count)
if ($fail) {
    Write-Host ("failed instances: " + ($fail -join ', ')) -ForegroundColor Red
}
Write-Host "Results under artifacts/experiments/manual-<case>-<timestamp>/. Inspect run-audit.json and live.log per run."
