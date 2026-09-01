param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[^:]+::[^:]+$")]
    [string]$Instance,

    [Parameter(Mandatory = $true)]
    [string]$Config,

    [ValidateRange(1, 10)]
    [int]$Repetitions = 1,

    [ValidateSet("none", "protocol", "incentive")]
    [string]$Guidance = "incentive",

    [int]$Seed = 2026,
    [string]$ExperimentRoot = "",
    [switch]$Resume,

    [ValidateRange(60, 14400)]
    [int]$EpisodeTimeout = 2400,

    [ValidateRange(5, 300)]
    [int]$ProgressHeartbeat = 20
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if ([IO.Path]::IsPathRooted($Config)) {
    $configPath = [IO.Path]::GetFullPath($Config)
} else {
    $configPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $Config))
}
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Model config not found: $configPath"
}

if ($Resume -and [string]::IsNullOrWhiteSpace($ExperimentRoot)) {
    throw "-Resume requires -ExperimentRoot pointing to the existing experiment directory."
}

Write-Host "[preflight] Validating repository..."
& python -m async_rbench.cli validate
if ($LASTEXITCODE -ne 0) { throw "Repository validation failed." }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI is not available on PATH. Install and start Docker first."
}
$dockerServerVersion = & docker info --format '{{.ServerVersion}}' 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($dockerServerVersion)) {
    throw "Docker Linux engine is not running."
}
Write-Host "[preflight] Docker Linux engine: $dockerServerVersion"

if ([string]::IsNullOrWhiteSpace($ExperimentRoot)) {
    $safeInstance = $Instance -replace "::", "-" -replace "[^A-Za-z0-9._-]", "-"
    $runTag = Get-Date -Format "yyyyMMdd-HHmmss"
    $ExperimentRoot = Join-Path "artifacts\experiments" "manual-$safeInstance-$runTag"
}
if ([IO.Path]::IsPathRooted($ExperimentRoot)) {
    $ExperimentRoot = [IO.Path]::GetFullPath($ExperimentRoot)
} else {
    $ExperimentRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $ExperimentRoot))
}

$manifest = Join-Path $ExperimentRoot "manifest.json"
$runs = Join-Path $ExperimentRoot "runs"
$results = Join-Path $ExperimentRoot "results.json"
$audit = Join-Path $ExperimentRoot "run-audit.json"
$liveLog = Join-Path $ExperimentRoot $(if ($Resume) { "resume.log" } else { "live.log" })

if ($Resume) {
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        throw "Resume manifest not found: $manifest"
    }
} else {
    if (Test-Path -LiteralPath $manifest) {
        throw "Experiment manifest already exists. Use -Resume or choose a new -ExperimentRoot: $manifest"
    }
    New-Item -ItemType Directory -Force -Path $ExperimentRoot | Out-Null
    Write-Host "[manifest] Instance=$Instance; repetitions=$Repetitions; seed=$Seed"
    & python -m async_rbench.eval_cli make-manifest `
        --output $manifest `
        --repetitions $Repetitions `
        --guidance $Guidance `
        --seed $Seed `
        --execution-modes linear async `
        --instances $Instance
    if ($LASTEXITCODE -ne 0) { throw "Manifest creation failed." }
}

$runArgs = @(
    "-m", "async_rbench.eval_cli", "run-manifest",
    "--manifest", $manifest,
    "--profile", "reference_scaffold_api",
    "--config", $configPath,
    "--output", $runs,
    "--timeout", "$EpisodeTimeout",
    "--progress-heartbeat", "$ProgressHeartbeat",
    "--official-track"
)
if ($Resume) { $runArgs += "--resume" }

Write-Host "[run] Output=$ExperimentRoot"
$savedErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & python @runArgs 2>&1 | Tee-Object -FilePath $liveLog
    $runExit = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $savedErrorActionPreference
}
if ($runExit -ne 0) {
    throw "Experiment stopped with exit code $runExit. Inspect $liveLog before deciding whether the failure is resumable."
}

& python -m async_rbench.eval_cli aggregate --root $runs --manifest $manifest --output $results
if ($LASTEXITCODE -ne 0) { throw "Aggregation failed." }
& python -m async_rbench.eval_cli audit-run --root $runs --output $audit
if ($LASTEXITCODE -ne 0) { throw "Run audit failed." }

Write-Host "[complete] Results: $results"
Write-Host "[complete] Audit: $audit"
Write-Host "[complete] Live log: $liveLog"
