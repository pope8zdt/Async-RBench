# Command line

The package installs three entry points.

| Command | Purpose |
|---|---|
| `async-rbench` | Inspect and validate the frozen public corpus or an explicitly supplied judge bundle |
| `async-rbench-eval` | Build manifests, run episodes, score traces, aggregate results, and audit runs |
| `async-rbench-reference-adapter` | Run the fixed reference participant scaffold |

## Public corpus

```bash
async-rbench list
async-rbench inspect <case-id>
async-rbench validate-public
```

`validate` is a compatibility alias for `validate-public`. These commands read
only participant-visible files and work without a judge bundle.

## Judge validation

Task scoring requires an explicit external judge root:

First follow [judge access and setup](judge-bundle.md) to request a bundle for
your exact checkout. A version label is not sufficient; task and scoring
bindings must match. Keep the bundle outside this repository.

```bash
async-rbench validate-judge --judge-root <judge-root>
async-rbench certify-release --judge-root <judge-root>
```

Release maintainers may refresh both bound release manifests only after all
checks pass:

```bash
async-rbench certify-release \
  --judge-root <judge-root> \
  --write-manifests
```

No command searches for a sibling private directory or reads a judge path from
an environment variable.

## Evaluation

Start Docker in Linux-container mode and configure a copy of
[`experiment-profile.template.yaml`](../configs/model-profiles/experiment-profile.template.yaml).
Set its API-key environment variable locally. Use the same model identifier in
the profile and manifest; the paper uses the same model for main and children.
Create a paired Batched/Async plan over all 200 tasks:

```bash
async-rbench-eval make-manifest \
  --output manifest.json \
  --repetitions 3 \
  --guidance incentive \
  --seed 2026 \
  --execution-modes linear async \
  --model <model-id> \
  --judge-root <judge-root>
```

The internal key `linear` is the frozen compatibility key for the paper-facing
**Batched** condition; `async` is **Async**. Both modes run children
concurrently. The judge root contributes only verifier and release digests to
the manifest.

Run, score, aggregate, and audit:

```bash
async-rbench-eval run-manifest \
  --manifest manifest.json \
  --output <run-directory> \
  --profile reference_scaffold_api \
  --runtime-mode api_only \
  --config <profile.yaml> \
  --judge-root <judge-root>

async-rbench-eval score \
  --trace <trace.jsonl> \
  --case <case-id> \
  --execution-mode async \
  --output score.json \
  --judge-root <judge-root>

async-rbench-eval aggregate \
  --root <run-directory> \
  --manifest manifest.json \
  --output aggregate.json

async-rbench-eval audit-run \
  --root <run-directory> \
  --output audit.json
```

Add `--resume` to `run-manifest` to continue in the same output directory without
rerunning completed episodes. Keep the manifest, judge and profile unchanged.
The commands above retain containers and the adapter conformance gate by default.
Normal runs are reported in `aggregate.json` under `development_summary`, with per-episode
scores in each episode's `score.json`. They do not update the website leaderboard.

The runtime judge uses `command-boundaries-v1`: uniform point means within
applicable components, equal C/R/F/V component means, and a 50:50 process/outcome
blend. Artifact state is observed at presentation, after main terminal commands,
promotions and runtime verification, and at participant termination. This is not
an intra-command operation journal. New scores use
`async-rbench-runtime-boundaries-1`; aggregate different policies separately.

`--official-track` is a separate strict paper-protocol check, not a prerequisite
for these commands. It requires explicit weighted ERCs and refuses R/F contracts
without full-window operation evidence. Do not use it with the runtime judge.

## Adapter conformance

To check protocol behavior without running a task-solving model:

```bash
async-rbench-eval conformance \
  --profile <profile.yaml> \
  --judge-root <judge-root> \
  --output conformance.json
```

This checks protocol behavior independently of task-solving quality.

The reference scaffold is started with:

```bash
async-rbench-reference-adapter \
  --config <profile.yaml> \
  --backend {openai_compatible,codex_cli,scripted_test} \
  --workspace-mode {container_clone,disabled}
```

All validation and conformance commands return a non-zero exit code on failure,
so they can be used directly as CI gates.
