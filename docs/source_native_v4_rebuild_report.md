# Source-native v4 rebuild report

## Outcome

The 661 OSWorld, SWE-family, and MultiAgentBench candidates from the 960-case
rebuild set were regenerated as source-native v4 specifications. There are 601
unique-source, spec-ready cases, and the current preflight passes all 601 with
zero failures.

The environment repair has separate, non-additive evidence tiers:

| Source | Input | Spec-ready | Environment smoke | Native initialization | Runtime-ready | Model-executed |
|---|---:|---:|---:|---:|---:|---:|
| OSWorld | 91 | 91 | 91 | 0 | 91 | 0 |
| SWE family | 229 | 169 | 0 | 0 | 4 | 0 |
| MultiAgentBench/MARBLE | 341 | 341 | 341 | 341 | 0 | 0 |
| Total | 661 | 601 | 432 | 341 | 95 | 0 |

OSWorld's 91 cases are native-environment qualified through a live VM.
MARBLE's 341 cases are native-environment initialization qualified. The latter
tier proves that the real scenario classes and dependencies initialize, but it
does not set `runtime_ready=true`. Four SWE-bench cases retain their stronger
gold-and-checkpoint qualification. No ReAct, Linear, or Async model episode has
run, and no case is formally promoted.

The SWE candidates bind the correct source variants: 126 Princeton SWE-bench,
19 ByteDance Multi-SWE-bench, and 24 Scale SWE-bench Pro. The 60 quarantined
records comprise 22 instances without non-empty FAIL_TO_PASS tests, 24
unresolved source IDs, and 14 Multi-SWE TypeScript records whose very large
official source snapshots were not materialized on this host.

## Source and evaluator binding

1. Participant views contain the official OSWorld instruction, SWE problem
   statement, or MARBLE task; native evaluators and tests remain harness-private.
2. Each case binds an immutable upstream revision and source hash or official
   dataset identity. SWE variants select their own official harness.
3. Async execution uses an evaluator-owned lifecycle: reset revision, worker
   launch, persisted native-state checkpoint, raw result delivery,
   repair/finalization, and native evaluator execution.
4. Unchanged checkpoints, broken hash chains, missing evaluators, undelivered
   events, and environment failures invalidate an episode; they are not imputed
   as model score zero.
5. ReAct, Linear, and Async use the same case-specific task evaluator. Async
   trace integrity is a validity gate, not a substitute score.

## Native environment qualification

OSWorld is bound to the official task JSON, setup handlers, `DesktopEnv`, and
unchanged evaluator. Its full batch launched every case with the attested
24,460,197,888-byte Ubuntu qcow2 and official Docker image, ran official setup
and getter/metric dispatch, executed `WAIT`, completed a second reset with a
replacement container, and verified cleanup. The canonical report contains the
exact 91-case set, stable preflight/postflight daemon identity, KVM capability,
read-only qcow2 binding, and zero OSWorld residual containers. The isolated
CPython 3.12 environment and its 276-package lock are independently attested.

MARBLE evidence constructs a fresh upstream `Config`, `Engine`, scenario
`Environment`, and `Evaluator` for every one of 341 cases: 96 bargaining, 97
coding, 98 database, and 50 research. The isolated CPython 3.9 environment has
97 locked packages. Database cases bind the digest-pinned PostgreSQL and
monitoring stack and perform case-scoped schema reset. The collection recorded
zero model-provider calls and zero `Engine.start` calls, so this remains an
initialization tier rather than task execution or scoring.

The four runtime-ready SWE cases are:

- `swe-dependency-unblock-3361c7af50` (`matplotlib__matplotlib-25332`);
- `swe-dependency-unblock-8902c7f431` (`django__django-12125`);
- `swe-late-constraint-3950516755` (`pytest-dev__pytest-7324`);
- `swe-late-constraint-7ce47cda27` (`django__django-11815`).

The canonical registry now has 436 rows: 91
`native_environment_validated`, 341
`native_environment_initialization_validated`, and 4
`gold_and_checkpoint_validated`. The remaining 165 spec-ready SWE cases are
unregistered for runtime evidence. Environment-smoke count (432), native
initialization count (341), and runtime-ready count (95) overlap and must not be
summed.

## Remaining evidence boundary

The missing-environment blockers for the target OSWorld and MARBLE collections
are resolved at their stated tiers. OSWorld native qualification is environment
readiness, not a successful GUI task episode. MARBLE initialization does not
claim a model episode, gold score, persistent native checkpoint, or
`runtime_ready=true`; running a task still requires an explicitly configured
model provider. Across the entire source-native collection,
`runtime_executed_count` remains zero.

Formal promotion also remains false. The promotion policy requires at least two
models, three repeats per mode, randomized paired mode order, at least 95% valid
paired episodes, and a preregistered collection-level Linear-minus-Async effect
whose 95% bootstrap lower bound is above zero. Held-out confirmation models
cannot be used to select cases.

## Reproduction

```powershell
# OSWorld host environment and assets
scripts\bootstrap_osworld_native_python.ps1
.venv-osworld-native\Scripts\python.exe scripts\fetch_osworld_assets.py
.venv-osworld-native\Scripts\python.exe scripts\run_osworld_native_batch.py `
  --all --headless

# MARBLE host environment, persistent DB stack, and all scenarios
python scripts\bootstrap_marble_runtime.py --recreate
python scripts\initialize_marble_collection.py --resume --provision-database

# One guarded canonical update with both collection gates
.venv-osworld-native\Scripts\python.exe scripts\sync_source_native_runtime.py `
  --merge-evidence artifacts\native-runtime-v4\osworld-native `
  --merge-evidence artifacts\native-runtime-v4\marble_native_initialization `
  --require-ready-benchmark OSWorld `
  --require-initialized-benchmark MultiAgentBench

.venv-osworld-native\Scripts\python.exe scripts\preflight_source_native_v4.py
.venv-osworld-native\Scripts\python.exe scripts\sync_source_native_runtime.py `
  --merge-evidence artifacts\native-runtime-v4\osworld-native `
  --merge-evidence artifacts\native-runtime-v4\marble_native_initialization `
  --check `
  --require-ready-benchmark OSWorld `
  --require-initialized-benchmark MultiAgentBench
```

The final check reports 601/601 preflight passes, 91/91 OSWorld runtime-ready,
341/341 MultiAgentBench initialization-qualified, 95 total runtime-ready, zero
drift, and zero model-executed cases.

The authoritative artifacts are
`artifacts/source-native-v4/native_manifest.jsonl`, `blocked_manifest.jsonl`,
`production_report.json`, `preflight_audit.json`, and
`artifacts/native-runtime-v4/runtime_registry.jsonl`.
