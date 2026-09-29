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

Formal scoring requires an explicit external judge root:

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

Create the paper's paired Batched/Async plan:

```bash
async-rbench-eval make-manifest \
  --output manifest.json \
  --repetitions 3 \
  --guidance incentive \
  --seed 2026 \
  --execution-modes linear async \
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

## Adapter conformance

```bash
async-rbench-eval conformance \
  --profile <profile.yaml> \
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
