# OSWorld native environment runtime

`scripts/qualify_osworld_runtime.py` retains the fast, offline control-plane
smoke for every source-native OSWorld case. It validates
the pinned official config hash, setup handler names, evaluator metric/getter
dispatch, provider factory sources, deterministic reset, state revision
change, and OSWorld's official terminal `FAIL` scoring branch.

Run the offline validator only as a non-mutating diagnostic:

```powershell
python scripts/qualify_osworld_runtime.py --no-registry-write
```

Do not use the offline command to update the canonical registry after native
evidence exists: its weaker smoke rows would replace the OSWorld native rows.
Only the guarded source-native sync described below may update canonical
metadata. `--provider docker` performs a non-mutating prerequisite check for
the Docker CLI/daemon, the pinned OSWorld container image, and the Ubuntu qcow2
disk. `--require-real-provider-ready` makes missing real-VM prerequisites fail
the diagnostic command as well as being reported.

## Evidence boundary

`environment_smoke_validated` with `execution_scope=infrastructure_smoke` does
not mean that a GUI task, model episode, official setup, VM getter, or gold
metric ran. Every such field is explicitly false in the evidence. The local
runtime supports only OSWorld's `WAIT`, `FAIL`, and `DONE` control actions; a
desktop action or successful-task scoring request fails closed with
`RealVMRequiredError`.

Real native-environment qualification uses upstream `osworld.DesktopEnv` with a
launch-ready provider, VM disk/snapshot, full evaluator dependencies, task
setup, a live GUI-capable VM/control plane, and the unchanged gold evaluator.
Only that path may
produce `native_environment_validated`. OSWorld rejects the legacy generic
`gold_and_checkpoint_validated` profile; model-episode evidence is a separate,
stronger claim.

Use the separate native entry point to preflight one case. The preflight
command does not download assets, but the previously fetched and attested image
and qcow2 must already exist. The default asset attestation is produced by
`scripts/fetch_osworld_assets.py`; preflight binds its verified qcow2 hash claim
to the current file path, size, and nanosecond mtime and requires the pinned
Docker digest and `latest` tag to resolve to the same official image ID. It does
not rehash the 23 GiB qcow2 for every case.

Bootstrap the authoritative host-side Python environment before native
preflight. The script resolves uv-managed CPython 3.12, creates an isolated
venv (`include-system-site-packages=false`), installs the 276-package Windows
CPU lock, and checks all active constraints from upstream `requirements.txt`
and `setup.py`. It also runs `pip check`, imports `DesktopEnv` and the Docker
provider, binds the psutil extension binary to the venv, and emits a stable
report whose bytes do not change on an identical `-SkipInstall` rerun:

```powershell
scripts\bootstrap_osworld_native_python.ps1
scripts\bootstrap_osworld_native_python.ps1 -SkipInstall
```

Fetch and fully attest the official Docker image and qcow2 once when they are
not already present:

```powershell
.venv-osworld-native\Scripts\python.exe scripts\fetch_osworld_assets.py
```

The current attested qcow2 is 24,460,197,888 bytes with SHA-256
`6bf667a852b3c307f61d9f09c42559351f45e0607e428b4997becf534cf4d313`.
The official Docker image resolves to image ID/digest
`sha256:0e6497a9295647cf05bf2b2af522fdd79bdeba2737595259cab310a3bcf6baa9`.
The current Windows/CPU lock SHA-256 is
`4e0bbd89b0f08d3ddf68687a1c638171a594c03b927a72488a6a19a90b62cfeb`.

The lock is generated from `configs/osworld-native-requirements.in` with the
PyTorch CPU backend. The resulting environment intentionally uses CPython
3.12: upstream's NumPy 1.26, Torch 2.5, and Matplotlib 3.7 constraints do not
have a mutually installable CPython 3.13 wheel set. The bootstrap report binds
the lock hash, normalized installed-distribution hash, upstream constraint
source hashes, interpreter prefix/base-prefix, and psutil `_psutil_windows.pyd`
path. Native preflight revalidates those values and fails closed on drift.

```powershell
.venv-osworld-native\Scripts\python.exe scripts/run_osworld_native_case.py `
  --case-id <case-id> `
  --provider docker `
  --preflight-only
```

The direct and batch commands both default to the attested asset paths under
`artifacts/native-runtime-v4/osworld-assets`; explicit path overrides remain
available.

Remove `--preflight-only` only after the report is `preflight_ready`. The
native command then starts upstream `DesktopEnv`, verifies each official setup
phase returned success, invokes `environment.evaluate()` with an empty action
history, and traces the case-specific getter/expected-getter/metric dispatch.
For an infeasible task it verifies the unchanged evaluator ran and returned
zero without a `FAIL` action, while recording the gold metric as not applicable.
It next executes `WAIT`, proves the environment was marked used, performs a
second reset, and requires a different 64-hex Docker container ID. Screenshot
equality is deliberately not a reset criterion.

On Windows Docker Desktop, `/dev/kvm` can exist inside the Linux daemon even
though it is absent on the Windows host. The launcher probes the device with a
short disposable container. When available, it installs a reversible `os.path`
proxy only in `desktop_env.providers.docker.provider`; Python's global `os`
module and pinned upstream sources are unchanged. TCG is eligible only when a
successful probe establishes that `/dev/kvm` is unavailable. A probe, daemon,
or API error fails closed instead of being reclassified as TCG availability.

`native_environment_validated` means this infrastructure, setup, reset, and
unchanged baseline evaluator path passed. It still records
`model_episode_executed=false`: no model action or successful GUI task episode
is implied.

Run one or more selected cases by repeating `--case-id`, or select the complete
collection explicitly with `--all`:

```powershell
.venv-osworld-native\Scripts\python.exe scripts/run_osworld_native_batch.py `
  --case-id <case-id-1> --case-id <case-id-2> --headless

.venv-osworld-native\Scripts\python.exe scripts/run_osworld_native_batch.py `
  --all --headless
```

Only an explicit `--all` request enters promotable full-collection mode; manually
enumerating 91 case IDs remains a subset run. The full mode fails closed unless
the current manifest contains exactly 91 OSWorld cases. It reports
`full_collection_validated=true` only when the exact case set has current-bound
successful evidence, preflight and postflight use the same CLI/SDK daemon
identity, the provider lock is held, and cleanup finds no OSWorld container.
The runner does not silently expand an empty selection. It continues after a
clean case-local failure, but stops when timeout/process state or provider
cleanup is unknown, or when a residual container exists. Resume skips evidence
only when the source, upstream revision, bootstrap report, environment lock,
asset attestation, canonical VM path, evaluator/setup bindings, and current live
provider preflight still match. Use `--rerun-valid` to force replacement.

The current canonical batch reports 91 selected, 91 validated, 0 failed, and a
subsequent resume skipped all 91. Both live probes passed with a stable Docker
daemon identity and zero OSWorld residual containers.

The batch command intentionally never writes the runtime registry by itself.
After reviewing `batch_report.json`, merge case evidence and update the canonical
registry, native manifest, and production report through the guarded sync path:

```powershell
python scripts/sync_source_native_runtime.py `
  --merge-evidence artifacts\native-runtime-v4\osworld-native `
  --require-ready-benchmark OSWorld
```

As soon as OSWorld native rows are present, the sync automatically requires the
canonical exact-91 batch envelope, including every result path and evidence
file SHA-256. It holds a repository-wide source-sync lock and a batch snapshot
lock, performs a pre-write optimistic-concurrency check, replaces each canonical
file atomically, and rolls back earlier replacements on an in-process failure.
This is not a crash-atomic multi-file transaction. The sync preserves unrelated
rows and higher-ranked evidence.
