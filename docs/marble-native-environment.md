# MARBLE native environment

The MARBLE collection validator covers all 341 source-native
MultiAgentBench cases: 96 bargaining, 97 coding, 98 database, and 50 research.
It uses an isolated uv-managed CPython 3.9 environment and an exact dependency
lock, stages the pinned upstream tree without mutating it, then constructs a
fresh upstream `Config`, `Engine`, scenario `Environment`, and `Evaluator` for
each case.

## Bootstrap

Create or verify the dedicated environment:

```powershell
python scripts\bootstrap_marble_runtime.py --recreate
```

The bootstrap writes `artifacts/native-runtime-v4/marble_bootstrap_report.json`
and a normalized installed-package lock artifact. It fails closed unless the
venv has `system-site-packages=false`, every locked distribution matches, `uv
pip check` succeeds, and the engine/evaluator, all four scenario environments,
database anomaly adapter, and reachable lazy dependencies import successfully.
The current 97-package lock SHA-256 is
`7cf800dc8f9753e171bd46e9860ae2f9aabb54cb6451ee4d1da4db16c1ec644b`;
the stable bootstrap report SHA-256 is
`90ebdfd17109a78ca5856b191f93afddb962b37339a18d7b7009c4e6b7526d73`.

## Initialize the collection

Provision the digest-pinned database/monitoring stack and initialize all cases:

```powershell
python scripts\initialize_marble_collection.py `
  --resume `
  --provision-database
```

`--resume` is safe after an interruption: existing evidence is reused only
when it matches the exact current case ID, source task, scenario, source JSONL
record, source config evidence, runtime binding, venv, dependency lock, and
bootstrap report.
The Python/import checks and database readiness probe run unconditionally even
when every case is already present. Compose bind mounts use the persistent
workspace staging at
`artifacts/native-runtime-v4/marble_database_runtime_staging`, not a temporary
directory.

The staged Compose file pins PostgreSQL 17, Prometheus, node-exporter, and
PostgreSQL-exporter by digest. In particular, PostgreSQL uses
`sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675`;
each of the 98 database-case evidence files records all four configured
references and current image IDs.

The complete report is
`artifacts/native-runtime-v4/marble_native_initialization/batch_report.json`.
Accept a full run only when it records all of the following:

- `selected_count=341` and `all_341_selected=true`;
- `validated_count=341` and `failed_count=0`;
- `full_collection_validated=true`;
- zero model-provider and `Engine.start` calls in every case evidence file.

The current canonical report satisfies these gates: 341 selected, 341
validated, 0 failed, and full-collection validation true. Attempted and skipped
counts are resume-run details rather than fixed acceptance values.

Merge reviewed evidence through the guarded canonical sync:

```powershell
python scripts\sync_source_native_runtime.py `
  --merge-evidence artifacts\native-runtime-v4\marble_native_initialization `
  --require-initialized-benchmark MultiAgentBench
```

## Evidence boundary

`native_environment_initialization_validated` proves that the real staged
MARBLE classes and scenario dependencies initialize and reset without a model
call. Database cases additionally bind the running PostgreSQL, Prometheus,
node-exporter, and PostgreSQL-exporter image digests and perform a case-scoped
schema reset. The anomaly workload is deliberately deferred to a model episode.

This tier deliberately does not claim a model episode, gold score, persistent
native checkpoint, or `runtime_ready=true`. Actual benchmark execution still
requires an explicitly configured model provider and invokes the unchanged
upstream engine/evaluator after this environment gate.
