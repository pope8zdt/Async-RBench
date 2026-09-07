# Track B agent systems

Track B runs an agent framework on the participant's computer while Async-RBench retains control of paired Linear/Async execution, asynchronous result delivery, isolated workspaces, private verification and scoring.

Track B is a development track. Its records are deliberately excluded from the Track A leaderboard.

See the [two-case Codex CLI + Luna live validation](reports/2026-09-07-track-b-codex-luna.md) for measured results and current harness/scoring limitations.

## Maintained integrations

| Framework | Install | Runtime |
| --- | --- | --- |
| Claude Code | Install the `claude` command or run `pip install -e ".[track-b-claude]"` | Claude Code CLI, with Agent SDK preferred when installed |
| Codex CLI | `pip install -e ".[track-b-codex]"`, install `codex` and sign in with ChatGPT | Model-only CLI using the participant's saved subscription login |
| LangGraph | `pip install -e ".[track-b-langgraph]"` | LangChain agent compiled on LangGraph |
| OpenAI Agents SDK | `pip install -e ".[track-b-openai]"` | `Agent` and `Runner` |

Framework dependencies are optional. Installing Async-RBench or running Track A does not import them.

## Run frameworks in Linux containers

The maintained example configs run the framework and custom harness components in a Linux agent container. The benchmark kernel stays on the participant's computer and executes task actions in separate task/child containers. All scheduling, deliveries and scoring use the existing v11.0 protocol.

Install the benchmark and build the selected runtime from the repository root:

```powershell
python -m pip install -e .
python docker/track-b/build.py codex
Copy-Item configs/track-b/codex-cli.example.yaml track-b-config.yaml
python -m async_rbench.track_b doctor --config track-b-config.yaml
```

Use `claude`, `langgraph` or `openai` in the build command for the corresponding framework. `all` builds the four targets sequentially. The build helper sends only Python package source and declared build inputs to Docker; task data, artifacts, Git history and credentials are excluded. Framework versions are pinned in `docker/track-b/`. Host execution remains available by omitting `runtime` or setting `runtime: {type: host}` and installing the relevant optional dependencies.

```yaml
runtime:
  type: docker
  image: async-rbench-track-b:codex
  cpus: 0.5
  memory: 768m
  timeout_sec: 2400
```

`run` resolves the image once before the batch and saves `track-b-runtime-config.json` in the output directory. Both execution modes use this immutable image ID, which is also included in episode metadata. The original configuration is unchanged. CPU/memory limits here cover the agent runtime; task-container limits are separate. The wall-clock timeout includes framework startup and model calls.

The agent container runs without root privileges, with a read-only root filesystem and temporary home/work files. It receives public protocol messages and returns benchmark actions; it has no host filesystem or Docker socket mount. Task paths belong to the task container: use benchmark terminal actions to inspect them, even though both containers run Linux/bash.

Authentication is configured per framework. For Codex, the launcher transfers only file-backed saved ChatGPT authentication into the temporary container home. For the other integrations, set the provider credential named by `credential_env`; use an uppercase variable ending in `_KEY`, `_TOKEN` or `_SECRET`. Credentials travel through the private bootstrap input, not Docker arguments, image layers or result metadata. Container credentials are discarded at shutdown; global account files and preferences are not rewritten.

Docker mode also supports the five existing custom component interfaces. Install your component package in a derived image and reference its `module:factory` in the config:

```dockerfile
FROM async-rbench-track-b:langgraph
USER root
COPY my_harness-0.1.0-py3-none-any.whl /tmp/my_harness-0.1.0-py3-none-any.whl
RUN chmod -R u+w /opt/venv && pip install --no-deps /tmp/my_harness-0.1.0-py3-none-any.whl \
    && rm /tmp/my_harness-0.1.0-py3-none-any.whl && chmod -R a-w /opt/venv
USER 1000:1000
```

Set `runtime.image` to the derived image. Include any additional dependencies explicitly. Keep component diagnostics on stderr and preserve stdout for the benchmark protocol. Files written in the agent container are temporary; task artifacts must be created through benchmark capabilities. Cancellation, input closure and runtime timeouts terminate the agent container and its model processes.

For an OpenAI-compatible provider, use the OpenAI Agents SDK integration with an explicit client:

```yaml
track: B
framework: openai-agents
model: your-exact-model-id
credential_env: TRACK_B_API_KEY
framework_options:
  base_url: https://your-provider.example/v1
  api_mode: chat_completions
  max_retries: 1
limits:
  request_timeout_sec: 120
  max_output_tokens: 4096
```

The selected credential variable is required; this driver never falls back to another account. SDK tracing is disabled. Token usage comes from the SDK response, while an unavailable provider-returned model identity remains empty rather than being inferred from configuration.

## Use a local ChatGPT subscription with Codex

Run this integration on your own computer with the Codex CLI installed. It uses your saved ChatGPT sign-in; subscription access and API-key access are separate authentication modes. See the official [Codex authentication guide](https://learn.chatgpt.com/docs/auth).

If you have not signed in, run `codex login` and choose ChatGPT. Confirm the saved login and copy the Luna example:

```powershell
python -m pip install -e .
codex login status
python docker/track-b/build.py codex
Copy-Item configs/track-b/codex-cli.example.yaml track-b-config.yaml
python -m async_rbench.track_b doctor --config track-b-config.yaml
```

The example selects `gpt-5.6-luna`, medium reasoning effort and a 180-second request timeout. Keep the same model and effort in paired Linear/Async runs. Leave `credential_env` empty: this integration rejects API-key credential overrides and requires the CLI to report a saved ChatGPT login. In Docker mode, the doctor checks the CLI inside the selected image; it does not require host framework dependencies or prove that the selected model is available to the account.

Each model request runs the CLI in a fresh empty directory with controlled settings and native tools disabled. Codex returns structured benchmark actions; the Async-RBench kernel executes tools inside participant containers and retains control of child scheduling, private verification and scoring. The CLI supplies model decisions only. The implementation uses Codex's [non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) and leaves global preferences unchanged.

The isolation profile is verified with Codex CLI `0.153.4`. A temporary copy of the selected model's bundled catalog entry disables native tool presentation while preserving the exact model ID and other model capabilities. The integration test captures the CLI's actual request against a local mock endpoint, including nested tool declarations, and checks that no native tool, repository instructions or installed skill content is advertised. Run `python -m pytest tests/test_track_b_codex_isolation.py -q` before using a different CLI version. This test makes no real model call.

The runtime selects HTTPS transport through a per-invocation OpenAI provider entry that retains saved authentication and the CLI's official endpoint selection. This avoids repeated WebSocket connection attempts on networks where that transport is unavailable. Recoverable reconnection diagnostics are accepted only when the CLI subsequently completes a turn with valid usage and matching structured output. On Windows, each CLI process tree is tied to its adapter's lifetime, including termination of a virtual-environment Python launcher.

Tool arguments use typed structured output and are validated against the original benchmark schemas before execution. Optional non-nullable fields use `null` to request omission; arbitrary evidence objects use key/value entries and are reconstructed without parsing JSON embedded in strings. All maintained benchmark tools are covered. Unsupported custom schema constructs, including optional nullable properties, are rejected explicitly rather than silently changing their meaning.

Keep account authentication files and tokens on the participant's computer. Do not put them in YAML, GitHub repositories, GitHub Actions secrets or a hosted submission service. Participants run the evaluation locally and share permitted aggregate results; Track B remains separate from the public Track A leaderboard.

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

Set an exact model ID and, for API-backed integrations, the name of its credential environment variable. Codex uses the saved-login flow above. Keep credentials outside YAML and version control.

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

For a resource-limited development run, set `TRACK_B_CONTAINER_CPUS` and `TRACK_B_CONTAINER_MEMORY` in the launch process (for example, `0.25` and `512m`). These limits apply to participant, child and verifier containers; record them with the results because they can affect execution time. `TRACK_B_PARTICIPANT_IMAGE_IDS` accepts a JSON mapping from `case::instance` to immutable `sha256:` image IDs and disables rebuilding those images for Track B. Verify their task files against the registered task before reusing them. Keep these environment variables local to that launch process.

## Output and audit

Each run records the Track B config digest, framework and model identity, component entry points, participant runtime metadata, event source, participant trace and score. Secrets and environment-variable values are never placed in public metadata.

Stdout from an adapter is reserved for JSONL. Framework logs go to stderr. A malformed component, unavailable tool, private-field leak, invalid lineage reference or conformance failure stops the run before it can be treated as a valid measurement.

## Diagnose billed requests without usable output

Provider token usage can include reasoning and failed or refused responses. Episode token totals currently cover successful adapter turns only; they are not billing totals. Check the HTTP status, provider request ID, `finish_reason`, answer length, reasoning length and raw usage separately. Keep response bodies and credentials local.

The OpenAI Agents SDK can synthesize a refusal when a Chat Completions response has `finish_reason: content_filter` and no answer, refusal text or tool calls. That SDK message alone does not identify which upstream component set the status. A timeout likewise means the client did not receive a complete response within its configured limit, even if the provider recorded consumption. Preserve request IDs to correlate both sides.

The text protocol accepts one JSON action object, including one complete fenced object accompanied by explanatory text or a malformed draft. Multiple complete action objects are ambiguous and rejected. Malformed protocol output and an empty structured answer fail explicitly; they must not become an implicit agent stop. Reasoning text is never substituted for an answer or executed as a tool call. Preserve old episode records and use a fresh output directory after changing an adapter.
