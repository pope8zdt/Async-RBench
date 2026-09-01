param(
    [ValidateSet("preflight", "smoke", "calibration")]
    [string]$Mode = "preflight",
    [string]$ApiBaseUrl = "https://api.deepseek.com",
    [string]$ExperimentRoot = "",
    [switch]$Resume,
    [ValidateRange(60, 14400)]
    [int]$EpisodeTimeout = 2400,
    [ValidateRange(5, 300)]
    [int]$ProgressHeartbeat = 20
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$model = "deepseek-v4-pro"
$keyEnv = "ASYNC_RBENCH_DEEPSEEK_KEY"
$profile = Join-Path $PSScriptRoot "configs\model-profiles\deepseek-v4-pro.yaml"
$apiKey = [Environment]::GetEnvironmentVariable($keyEnv, "Process")
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    throw "$keyEnv is not set in this PowerShell process. Set it before running; never write the key into the project directory."
}
if (-not (Test-Path -LiteralPath $profile -PathType Leaf)) {
    throw "Model profile not found: $profile"
}

$baseUrl = $ApiBaseUrl.TrimEnd("/")
if ([string]::IsNullOrWhiteSpace($baseUrl)) { throw "ApiBaseUrl must not be empty." }
$chatCompletionsUrl = "$baseUrl/chat/completions"

Write-Host "[preflight] Validating Async-RBench..."
& python -m async_rbench.cli validate
if ($LASTEXITCODE -ne 0) { throw "Repository validation failed." }

$headers = @{ Authorization = "Bearer $apiKey" }
$probeTool = @{
    type = "function"
    function = @{
        name = "async_rbench_health_probe"
        description = "Confirm OpenAI-compatible function tool support."
        parameters = @{
            type = "object"
            properties = @{ value = @{ type = "string" } }
            required = @("value")
            additionalProperties = $false
        }
    }
}
$probePayload = @{
    model = $model
    messages = @(@{ role = "user"; content = "Call async_rbench_health_probe with value=ok. Do not answer directly." })
    tools = @($probeTool)
    tool_choice = "auto"
    max_tokens = 256
    stream = $false
}
$probeBody = $probePayload | ConvertTo-Json -Depth 12 -Compress
try {
    $probeResponse = Invoke-RestMethod `
        -Method Post -Uri $chatCompletionsUrl -Headers $headers `
        -ContentType "application/json; charset=utf-8" `
        -Body ([Text.Encoding]::UTF8.GetBytes($probeBody)) -TimeoutSec 120
} catch {
    throw "DeepSeek API preflight failed at $chatCompletionsUrl. $($_.Exception.Message)"
}
$probeCalls = @($probeResponse.choices[0].message.tool_calls)
if (-not ($probeCalls | Where-Object { [string]$_.function.name -eq "async_rbench_health_probe" })) {
    throw "The endpoint responded but did not return the required function tool call."
}
Write-Host "[preflight] DeepSeek V4 Pro endpoint and function tools: OK"
if ($Mode -eq "preflight") {
    Write-Host "[complete] Preflight passed; no paid benchmark episode was started."
    return
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI is not available on PATH. Install and start Docker Desktop first."
}
$dockerServerVersion = & docker info --format '{{.ServerVersion}}' 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($dockerServerVersion)) {
    throw "Docker Desktop Linux engine is not running."
}
Write-Host "[preflight] Docker Linux engine: $dockerServerVersion"

$env:ASYNC_RBENCH_MODEL_API_URL = $chatCompletionsUrl
$env:ASYNC_RBENCH_MODEL_API_KEY_ENV = $keyEnv
$env:ASYNC_RBENCH_MAIN_MODEL = $model
$env:ASYNC_RBENCH_CHILD_MODEL = $model

if ([string]::IsNullOrWhiteSpace($ExperimentRoot)) {
    if ($Resume) { throw "-Resume requires -ExperimentRoot pointing to an existing experiment directory." }
    $runTag = Get-Date -Format "yyyyMMdd-HHmmss"
    $ExperimentRoot = Join-Path "artifacts\experiments" "$model-$Mode-$runTag"
}
if ([IO.Path]::IsPathRooted($ExperimentRoot)) {
    $ExperimentRoot = [IO.Path]::GetFullPath($ExperimentRoot)
} else {
    $ExperimentRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $ExperimentRoot))
}
New-Item -ItemType Directory -Force -Path $ExperimentRoot | Out-Null

$manifest = Join-Path $ExperimentRoot "manifest.json"
$runs = Join-Path $ExperimentRoot "runs"
$results = Join-Path $ExperimentRoot "results.json"
$audit = Join-Path $ExperimentRoot "run-audit.json"
$liveLog = Join-Path $ExperimentRoot $(if ($Resume) { "resume.log" } else { "live.log" })

if (-not $Resume) {
    $manifestArgs = @(
        "-m", "async_rbench.eval_cli", "make-manifest",
        "--output", $manifest, "--guidance", "incentive", "--seed", "2026",
        "--execution-modes", "linear", "async"
    )
    if ($Mode -eq "smoke") {
        $manifestArgs += @("--repetitions", "1", "--instances", "secure-release::seed-1")
    } else {
        $manifestArgs += @("--repetitions", "3")
    }
    Write-Host "[manifest] Creating $Mode manifest at $manifest"
    & python @manifestArgs
    if ($LASTEXITCODE -ne 0) { throw "Manifest creation failed." }
} elseif (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
    throw "Resume manifest not found: $manifest"
}

$runArgs = @(
    "-m", "async_rbench.eval_cli", "run-manifest",
    "--manifest", $manifest, "--profile", "reference_scaffold_api",
    "--config", $profile, "--output", $runs,
    "--timeout", "$EpisodeTimeout", "--progress-heartbeat", "$ProgressHeartbeat",
    "--official-track"
)
if ($Resume) { $runArgs += "--resume" }

Write-Host "[run] Model=$model; mode=$Mode; output=$ExperimentRoot"
$savedErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & python @runArgs 2>&1 | Tee-Object -FilePath $liveLog
    $runExit = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $savedErrorActionPreference
}
if ($runExit -ne 0) {
    throw "Experiment stopped with exit code $runExit. Inspect $liveLog before resuming."
}

& python -m async_rbench.eval_cli aggregate --root $runs --manifest $manifest --output $results
if ($LASTEXITCODE -ne 0) { throw "Aggregation failed." }
& python -m async_rbench.eval_cli audit-run --root $runs --output $audit
if ($LASTEXITCODE -ne 0) { throw "Run audit failed." }

Write-Host "[complete] Results: $results"
Write-Host "[complete] Audit: $audit"
Write-Host "[complete] Live log: $liveLog"
