# Track B agent systems

Track B runs an agent framework on the participant's computer while Async-RBench retains control of paired Linear/Async execution, asynchronous result delivery, isolated workspaces, private verification and scoring.

Track B is a development track. Its records are deliberately excluded from the Track A leaderboard.

## Maintained integrations

| Framework | Install | Runtime |
| --- | --- | --- |
| Claude Code | Install the `claude` command or run `pip install -e ".[track-b-claude]"` | Claude Code CLI, with Agent SDK preferred when installed |
| LangGraph | `pip install -e ".[track-b-langgraph]"` | LangChain agent compiled on LangGraph |
| OpenAI Agents SDK | `pip install -e ".[track-b-openai]"` | `Agent` and `Runner` |

Framework dependencies are optional. Installing Async-RBench or running Track A does not import them.

## What can be customized

| Component | Participant control | Evaluator boundary |
| --- | --- | --- |
| `ModelBackend` | Provider client, exact model, retries and usage normalization | Cannot execute capabilities or read evaluator-private state |
| `ContextBuilder` | Rendering public task state, released results and prior public actions | Receives only the participant-safe projection |
| `DelegationPolicy` | Replacement-child proposals, cancellation and retry decisions | Kernel enforces workstreams, concurrency and spawn budgets |
| `AgentPolicy` | Consume, reject, defer, promote, verify, wait and finish decisions | Cannot assign result roles or verifier truth |
| `LifecycleHooks` | Sanitized diagnostics under the Track B output directory | Read-only; cannot alter events, model input or scores |

The Agent framework runtime is selected with `framework`. Every runtime receives the same public messages and benchmark tool schemas. Its structured actions are checked against those schemas before the fixed reference execution loop sends them to the kernel.

The following are fixed: execution modes, event schedule, result gateway, delivery occurrence identities, case bundles, capability RPC, workspaces, private truth, verifier, scoring points, denominators, aggregation and protocol conformance.

## Configure a maintained framework

Copy one example:

```powershell
Copy-Item configs/track-b/claude-code.example.yaml track-b-config.yaml
```

Set an exact model ID and the name of its credential environment variable. Keep the credential itself outside YAML and version control.

```yaml
track: B
framework: claude-code
model: replace-with-exact-claude-model-id
credential_env: ANTHROPIC_API_KEY
limits:
  max_main_steps: 100
  max_child_steps: 40
  max_concurrent_children: 3
  max_total_child_spawns: 5
  request_timeout_sec: 600
```

Check installation and credentials:

```powershell
python -m async_rbench.track_b doctor --config track-b-config.yaml
python -m async_rbench.track_b conformance `
  --config track-b-config.yaml `
  --output artifacts/track-b/conformance
```

Create a paired manifest and run it:

```powershell
python -m async_rbench.track_b make-manifest `
  --instances "secure-release::seed-1" `
  --model "replace-with-exact-model-id" `
  --repetitions 1 `
  --output artifacts/track-b/manifest.json

python -m async_rbench.track_b run `
  --config track-b-config.yaml `
  --manifest artifacts/track-b/manifest.json `
  --output artifacts/track-b/runs
```

`run` executes conformance again against the exact config-bound adapter before starting an episode. It never passes `--official-track` and rejects output paths inside formal experiment directories.

## Implement a custom component

Factories use absolute `module:factory` entry points. A context builder can be as small as:

```python
from async_rbench.track_b.contracts import FrameworkRequest, PublicEpisodeContext


class CompactContext:
    def build(self, context: PublicEpisodeContext) -> FrameworkRequest:
        return FrameworkRequest(
            messages=context.messages[-12:],
            tools=context.tools,
            metadata={"context_policy": "last-12"},
        )


def build_context() -> CompactContext:
    return CompactContext()
```

Reference it in YAML:

```yaml
components:
  context_builder: my_harness.components:build_context
```

Available protocol definitions are in `async_rbench/track_b/contracts.py`. The loader imports the factory, calls it with no arguments, and verifies the returned object at runtime before the adapter emits `ready`.

## Validation without model calls

The repository includes a deterministic engineering acceptance run over two development instances and both execution modes:

```powershell
python scripts/validate_track_b.py --output artifacts/track-b-validation
```

It runs protocol conformance and writes four episode records plus `track-b-validation.json`. It does not start Docker or call a model. The records are expected to be unscored and are never leaderboard eligible; they prove only that configuration, framework normalization, the adapter boundary and paired episode plumbing work together.

Use a maintained framework with container isolation for model-quality measurements. Do not add `--no-container` to those runs.

## Output and audit

Each run records the Track B config digest, framework and model identity, component entry points, participant runtime metadata, event source, participant trace and score. Secrets and environment-variable values are never placed in public metadata.

Stdout from an adapter is reserved for JSONL. Framework logs go to stderr. A malformed component, unavailable tool, private-field leak, invalid lineage reference or conformance failure stops the run before it can be treated as a valid measurement.
