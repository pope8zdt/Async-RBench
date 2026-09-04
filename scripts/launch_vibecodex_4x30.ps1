# Launch the four-model v10.1 relay batch. Every model receives the same first
# N registered instances; lanes stride that set without overlap.
# API-key values are read into environment variables and never written or shown.

param(
    [string]$KeysPath = "",
    [int]$Jobs = 30,
    [int]$Repeat = 3,
    [int]$Lanes = 2,
    [string]$WorkRoot = "",
    [switch]$Smoke
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($WorkRoot)) {
    $WorkRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if ([string]::IsNullOrWhiteSpace($KeysPath)) { $KeysPath = $env:KEYS_PATH }
if (-not (Test-Path -LiteralPath $WorkRoot)) { throw "WorkRoot not found: $WorkRoot" }
if (-not (Test-Path -LiteralPath $KeysPath)) { throw "APIKey file not found: $KeysPath" }
Set-Location -LiteralPath $WorkRoot

if ($Smoke) { $Jobs = 1 }

$models = [ordered]@{
    "1" = @{ env = "QWEN35_27B_API_KEY";        profile = "configs/model-profiles/qwen35-27b-vibecodex.yaml";         tag = "qwen" }
    "5" = @{ env = "ASYNC_RBENCH_DEEPSEEK_KEY"; profile = "configs/model-profiles/deepseek-v4-flash-vibecodex.yaml"; tag = "dsv4" }
    "6" = @{ env = "GEMINI3_FLASH_API_KEY";     profile = "configs/model-profiles/gemini-3-flash-high-vibecodex.yaml"; tag = "geminihigh" }
    "7" = @{ env = "GPT56_LUNA_API_KEY";        profile = "configs/model-profiles/gpt-5.6-luna-vibecodex.yaml";       tag = "luna" }
}

$venvPython = Join-Path $WorkRoot ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) {
    $venvPython
} else {
    (Get-Command python -ErrorAction Stop).Source
}
$env:PATH = "$(Split-Path -Parent $python);" + $env:PATH
$driver = Join-Path $WorkRoot "scripts\run_batch_parallel.py"

$lines = Get-Content -LiteralPath $KeysPath -Encoding UTF8
$parsed = @{}
$keyPattern = '"key"\s*:\s*"([^"]+)"'
$currentNumber = $null
$buffer = ""
foreach ($line in $lines) {
    $trimmed = $line.Trim()
    if ($trimmed -match '^(\d+)\.\S') {
        if ($null -ne $currentNumber -and $buffer -ne "") {
            $match = [regex]::Match($buffer, $keyPattern)
            if ($match.Success) { $parsed[$currentNumber] = $match.Groups[1].Value }
        }
        $currentNumber = $Matches[1]
        $buffer = $trimmed
    } elseif ($null -ne $currentNumber -and $trimmed -ne "") {
        $buffer += " " + $trimmed
    }
}
if ($null -ne $currentNumber -and $buffer -ne "") {
    $match = [regex]::Match($buffer, $keyPattern)
    if ($match.Success) { $parsed[$currentNumber] = $match.Groups[1].Value }
}

$processes = @()
foreach ($number in $models.Keys) {
    $model = $models[$number]
    $key = $parsed[$number]
    if ([string]::IsNullOrWhiteSpace($key)) {
        throw "No api_key found for model #$number"
    }
    Set-Item -Path "Env:$($model.env)" -Value $key

    for ($lane = 0; $lane -lt $Lanes; $lane++) {
        $tag = "{0}-L{1}" -f $model.tag, $lane
        $output = Join-Path $WorkRoot "artifacts\experiments\batch-$tag-results.jsonl"
        $arguments = @(
            $driver,
            "--profile", $model.profile,
            "--env-key", $model.env,
            "--lane", "$lane",
            "--lanes", "$Lanes",
            "--repeat", "$Repeat",
            "--jobs", "$Jobs",
            "--tag", $tag,
            "--out", $output
        )
        Write-Host ("[launch] model #{0} ({1}) lane={2}/{3}" -f $number, $model.tag, $lane, ($Lanes - 1))
        $processes += Start-Process -FilePath $python -ArgumentList $arguments `
            -WorkingDirectory $WorkRoot -NoNewWindow -PassThru
    }
}

Write-Host ("Launched {0} drivers; PIDs: {1}" -f $processes.Count, (($processes.Id) -join ", "))
$processes | ForEach-Object { $_ | Wait-Process }
$processes | ForEach-Object {
    Write-Host ("PID {0} exit={1}" -f $_.Id, $_.ExitCode)
}
