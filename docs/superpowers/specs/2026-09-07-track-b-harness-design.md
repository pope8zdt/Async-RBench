# Track B agent-system harness design

## Purpose

Track B evaluates complete agent systems while preserving the Async-RBench 11.0 evaluator contract. Participants may select a maintained framework integration or provide harness components, but every run must cross the same JSONL adapter boundary and use the evaluator-owned scheduler, result gateway, workspaces, verifier, and scorer.

Track B results are development results. They remain separate from the official Track A leaderboard unless a later benchmark version defines a Track B publication policy.

## Safety and isolation

Development happens on branch `codex/track-b-harness` in a linked worktree under `outputs/track-b-harness`. The active formal experiment checkout, Python environment, manifests, result directories, processes, ports, Docker resources, and model endpoints are not modified or reused.

Engineering validation uses a deterministic runtime with workspace execution disabled. It does not start Docker or make model calls. Live two-case validation may run only after the active formal experiment processes have ended. It must use a dedicated virtual environment, a unique Track B output directory, a one-episode-at-a-time launcher, and evaluator-generated resource identities.

## Architecture

Track B adds a participant-side composition layer above the existing adapter protocol:

```text
Claude Code / LangGraph / OpenAI Agents SDK / custom runtime
                         |
               Track B component API
                         |
             Track B protocol adapter
                         |
          JSONL + capability RPC boundary
                         |
       frozen Async-RBench 11.0 evaluator
```

The evaluator continues to launch one adapter process per episode. The Track B adapter reads `episode_started`, instantiates the configured components, exposes evaluator capabilities as typed tools, forwards only released result occurrences, emits validated lifecycle events, and terminates with a framework-neutral result.

Framework packages are optional dependencies. Importing Async-RBench or using Track A must not require them. A `doctor` command reports missing executables, Python packages, credentials, and unsupported configuration before an episode starts.

## Customizable components

The public component API is defined with Python protocols and immutable data objects. A custom implementation is loaded from a `module:factory` entry point. The loader rejects relative imports, non-callable factories, incompatible return types, and reserved evaluator-owned component names.

### AgentRuntime

`AgentRuntime` owns a framework session and translates a framework response into normalized text, tool requests, usage, and status. It may choose the model and framework-specific settings. It cannot open evaluator-private paths or execute benchmark capabilities directly.

Built-in implementations:

- `claude_code`: Claude Agent SDK or Claude Code CLI in programmatic mode.
- `langgraph`: a compiled state graph with explicit planner, action, delivery, and finish nodes.
- `openai_agents`: an OpenAI Agents SDK manager agent with benchmark capabilities exposed as local function tools.
- `deterministic`: a no-model runtime used only for conformance and engineering validation.

### ModelBackend

`ModelBackend` creates the model-facing client used by a runtime and returns normalized provider usage. A framework may supply its native backend. A custom backend may configure an API endpoint, credential environment-variable name, immutable model identifier, retry policy, and request timeout. Secrets are read only from the process environment and are excluded from metadata.

### ContextBuilder

`ContextBuilder` renders the participant-visible episode start, public workstreams, delivered or rejected results, capability results, and prior public actions into framework input. It must accept only allowlisted public values. The harness performs a private-field scan on every rendered input before a model call.

### DelegationPolicy

`DelegationPolicy` proposes initial child assignments, replacement children, cancellation, and retry decisions within the budgets supplied by the episode start. The kernel remains authoritative: it accepts or rejects lifecycle and capability requests and owns actual workspace creation and cleanup.

### AgentPolicy

`AgentPolicy` interprets normalized framework output and chooses participant actions such as consume, promote, observe, verify, wait, or finish. It may implement replanning and conflict resolution. It cannot mark a result authoritative, declare verifier truth, or bypass delivery acknowledgement and lineage rules.

### LifecycleHooks

`LifecycleHooks` receives sanitized, read-only callbacks for diagnostics. Hooks may write under the configured Track B run directory. They cannot mutate messages, events, evaluator state, or scores. Hook failures are recorded and fail the episode closed.

## Fixed evaluator mechanisms

The following surfaces are never participant-replaceable:

- Linear and Async execution semantics.
- Event schedules, completion release, delivery-occurrence identities, and private result roles.
- Case bundles, registered instances, task workspaces, and event assets.
- Capability RPC execution, container lifecycle, filesystem observation, and child-path promotion.
- Public/private projection, result-contract validation, conformance checks, and event ordering.
- Private verifier commands and truth, scoring points, denominators, aggregation, and digests.

The Track B tool bridge is benchmark-maintained. Custom components call its typed methods but cannot replace the bridge or receive its underlying transport handles.

## Configuration

A Track B YAML file contains:

```yaml
track: B
framework: claude_code
model: claude-sonnet-5
credential_env: ANTHROPIC_API_KEY
components:
  context_builder: async_rbench.track_b.defaults:build_context
  delegation_policy: async_rbench.track_b.defaults:build_delegation
  agent_policy: async_rbench.track_b.defaults:build_agent_policy
limits:
  max_turns: 100
  request_timeout_sec: 600
```

The config digest, framework identity, component entry points, package versions, executable version, and model identity are recorded as participant metadata. Configuration cannot override evaluator resource limits.

## Commands and run flow

The command surface is:

```powershell
python -m async_rbench.track_b list-frameworks
python -m async_rbench.track_b doctor --framework claude-code --config <config.yaml>
python -m async_rbench.track_b validate-config --config <config.yaml>
python -m async_rbench.track_b conformance --config <config.yaml> --output <directory>
python -m async_rbench.track_b make-manifest --instances <case::instance> --output <manifest.json>
python -m async_rbench.track_b run --config <config.yaml> --manifest <manifest.json> --output <directory>
```

`make-manifest` creates paired Linear and Async episodes. `run` first validates configuration and dependencies, then runs protocol conformance against the exact adapter command and config digest. Only a passing conformance result starts episodes. It delegates episode execution to the existing evaluation runner without `--official-track`, so Track A eligibility cannot be claimed accidentally.

For maintained integrations, participants copy an example config, set the exact model and credential environment variable, run `doctor`, then `conformance`, then `run`. Custom harness users implement one or more component protocols, reference their factories in YAML, and use the same commands.

## Framework integrations

### Claude Code

The integration uses an interactive Claude Agent SDK client when installed. It maps the Track B tool bridge to an in-process MCP server, uses a dedicated session per episode, pins the working directory supplied by the kernel, disables project/user settings inheritance by default, and records the SDK and bundled CLI versions. A CLI fallback supports `claude -p` with JSON or stream-JSON output for environments that do not install the Python SDK.

### LangGraph

The integration builds a small `StateGraph`. Its state contains only normalized public context, pending tool calls, delivered result occurrences, and sanitized usage. Graph nodes call the configured model backend, dispatch typed tools, ingest newly released results, and decide whether to continue. No LangSmith service is required.

### OpenAI Agents SDK

The integration creates a manager `Agent` and exposes kernel capabilities as local function tools. The SDK `Runner` executes one model turn at a time so the harness can insert gateway deliveries between turns and record matching lifecycle events. SDK tracing is disabled by default to avoid exporting task content outside the participant's selected model endpoint.

## Errors and audit behavior

Configuration, dependency, or conformance errors stop before model or workspace execution. Framework exceptions, malformed tool arguments, timeouts, hook failures, and protocol violations produce a typed participant runtime failure and an incomplete episode. The evaluator remains responsible for deciding whether an episode is scored or unscored.

Stdout is reserved for JSONL. Framework logs go to stderr. Secrets, environment values, evaluator-private events, hidden commands, and private verifier output are excluded from participant metadata and Track B diagnostics.

## Validation

Automated tests cover:

- configuration and entry-point validation;
- the five component protocols and default implementations;
- each maintained integration through injected SDK/CLI fakes;
- public/private context filtering;
- tool-to-capability mapping and lifecycle ordering;
- optional dependency failures and `doctor` output;
- Track A profile and source-boundary regression tests;
- CLI manifest generation and safe output-path handling.

The engineering acceptance run uses these development instances:

- `mab-dependency-unblock-8b943d725b::seed-1`
- `mab-late-test-evidence-4c6c77884e::seed-1`

It creates one Linear and one Async episode for each instance with the deterministic runtime, runs the same Track B adapter and evaluator event path, and writes a machine-readable validation report. The report states that the run validates integration mechanics and is not a model-quality or leaderboard result.

After the formal experiment is idle, the live acceptance run repeats the same four episodes with one maintained framework, container isolation, real capability RPC, private verification, and scoring. Its artifacts remain under a Track B-specific output root and are never consumed by the Track A exporter.

## Documentation and website

Repository documentation explains the customization boundary, framework installation, example configs, commands, outputs, and custom component tutorial. The website replaces Track B simulation copy with concise available-framework and local-run instructions. It does not execute agents in the browser; the generated command runs on the participant's machine.

Track B remains visibly separate from the Track A leaderboard until a publication policy is defined.
