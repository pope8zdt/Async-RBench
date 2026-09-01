# DeepSeek V4 Pro small-calibration instructions

## Purpose and scope

This run checks Async-RBench endpoint compatibility, paired linear/async execution, resource ceilings, failure handling, token consumption, and evaluator point responsiveness with one real model: `deepseek-v4-pro`.

It is not a paper result. A successful run does not freeze `evaluation_contract.json`; the later freeze audit still requires at least five models from at least three model families.

The calibration manifest contains 8 registered calibration instances, 2 execution modes, and 3 paired repetitions with seed `2026`: 48 paid episodes in total.

## Requirements

- Windows PowerShell 7;
- Python 3.11 or newer;
- Docker Desktop using the Linux container engine;
- a DeepSeek API key with access to the exact model ID `deepseek-v4-pro`;
- enough API balance and local disk space for Docker case images and run artifacts.

## One-time setup

Open PowerShell in the extracted `Async-RBench` directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
docker info
python -m async_rbench.cli validate
```

`docker info` must succeed before any paid episode is started.

## Set the credential

Set the key only in the current PowerShell process:

```powershell
$env:ASYNC_RBENCH_DEEPSEEK_KEY = Read-Host "DeepSeek API key" -MaskInput
```

Do not create `apikey.txt`, `.env`, or any credential file inside the project.

## Step 1: preflight

```powershell
.\run_calibration.ps1 -Mode preflight
```

This validates the repository and makes one small function-tool API probe. It starts no benchmark episode. Continue only if the exact model endpoint and tool call both pass.

## Step 2: two-episode smoke run

```powershell
.\run_calibration.ps1 -Mode smoke
```

The smoke manifest runs `secure-release::seed-1` once in each execution mode. Inspect the newly created directory under `artifacts\experiments\deepseek-v4-pro-smoke-*` and confirm:

- `manifest.json` lists exactly two episodes;
- `live.log` contains no infrastructure or authentication failure;
- `results.json` was generated;
- `run-audit.json` was generated and contains no digest/configuration mismatch.

A model failure is a valid scored outcome. Do not retry it merely because the score is low.

## Step 3: full small calibration

```powershell
.\run_calibration.ps1 -Mode calibration
```

The launcher creates the 48-episode manifest, runs the fixed reference scaffold, aggregates results, and writes a run audit. Do not edit cases, prompts, model settings, the manifest, or the evaluation contract after the run starts.

## Resume an interrupted run

Resume only an infrastructure-interrupted experiment and use the exact existing experiment directory:

```powershell
.\run_calibration.ps1 `
  -Mode calibration `
  -Resume `
  -ExperimentRoot "artifacts\experiments\deepseek-v4-pro-calibration-YYYYMMDD-HHMMSS"
```

Do not create a fresh manifest to replace a partially completed run. Participant failures and turn-budget exhaustion are scored and must not be retried. At most one retry is allowed for a documented infrastructure failure.

## Files to return

Return the complete experiment directory without modification. It must contain at least:

- `manifest.json`;
- `runs/` with every episode trace and score artifact;
- `results.json`;
- `run-audit.json`;
- `live.log`, plus `resume.log` if a resume occurred.

Compress that experiment directory and calculate its SHA-256 hash:

```powershell
Compress-Archive `
  -LiteralPath "artifacts\experiments\deepseek-v4-pro-calibration-YYYYMMDD-HHMMSS" `
  -DestinationPath "deepseek-v4-pro-calibration-YYYYMMDD-HHMMSS.zip"
Get-FileHash "deepseek-v4-pro-calibration-YYYYMMDD-HHMMSS.zip" -Algorithm SHA256
```

Send both the ZIP and the printed SHA-256 value. Never send the API key.

## Report separately

Along with the artifacts, report the operating system and Docker version, start/end time and timezone, official API or relay endpoint, every interruption or resume with its reason, and the actual provider charge if available.

Do not summarize or manually repair missing traces. The raw artifacts are the calibration evidence.
