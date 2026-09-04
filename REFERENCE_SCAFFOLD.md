# Fixed reference API scaffold

The reference scaffold is the fixed participant harness for official Track A. It supplies a main model loop, concurrent child loops, result-management tools and the protocol adapter. It contains no task-specific plan, result-selection rule, cancellation policy or replan policy; those remain model decisions.

## Visibility boundary

The scaffold receives only the kernel’s participant-safe `episode_started` projection. The main model sees the task, public workstreams/artifacts, structural result requirements, delivered payloads and observable workspace state. It does not see private result roles, schedules, stale/authority labels, invalidation/reopen sets, case capability labels, event-asset mappings, validators, artifact observer commands or hidden verification identities.

Main tools are:

- `terminal`
- `spawn_subagent`
- `list_subagents`
- `wait_for_results`
- `cancel_subagent`
- `acknowledge_result`
- `promote_child_path`
- `commit_artifact`
- `verify_current_state`
- `finish`

Children have an isolated terminal plus `submit_result`. In container mode, each child starts from a snapshot of the official main workspace. Its files become available to the main only through explicit promotion after delivery and acceptance.

Workspace, asset staging, artifact observation and verification are kernel capabilities. `commit_artifact` obtains its digest from `observe_artifact`. `verify_current_state` sends only public artifact IDs and accepted lineage; it receives aggregate counts, while all check commands and per-check facts remain evaluator-private.

## Model configuration

The backend targets an OpenAI-compatible Chat Completions API with function tools. Use an exact model snapshot where the provider supports one.

```yaml
backend: openai_compatible
api_url: https://api.openai.com/v1/chat/completions
api_key_env: OPENAI_API_KEY
api_key_required: true
main_model: exact-main-model-id
child_model: exact-child-model-id
temperature: null
max_tokens_parameter: max_completion_tokens
workspace_mode: container_clone
max_main_steps: 100
max_child_steps: 40
emergency_total_token_cap: 20000000
```

For a trusted keyless local endpoint, set `api_key_env: ""` and `api_key_required: false`. Provider/model resolution metadata is recorded for audit.

The scaffold uses fixed model-step horizons, not token reservations. Actual
token consumption is emitted as a final diagnostic snapshot. `finish` is
terminal on first execution, even when closure work is incomplete; the runtime
records the state but never returns benchmark-authored remediation advice.

## Conformance

The scripted backend is only a deterministic protocol test. It never qualifies as an evaluation result.

```powershell
python -m async_rbench.eval_cli conformance `
  --output artifacts/conformance `
  --profile reference_scaffold_api
```

## Official run

```powershell
python -m async_rbench.eval_cli make-manifest `
  --output artifacts/experiments/manifest.json `
  --repetitions 3 --guidance incentive --seed 2026

$env:OPENAI_API_KEY = "..."
python -m async_rbench.eval_cli run-manifest `
  --manifest artifacts/experiments/manifest.json `
  --output artifacts/experiments/runs `
  --profile reference_scaffold_api `
  --config path/to/model-config.yaml `
  --official-track
```

Official mode requires a real API backend, container isolation, the fixed profile and passing conformance. Any relaxed setting produces a development-only run.
