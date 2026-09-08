# Evaluation tracks

> Current main experiment / 当前主实验：仅统计固定 47-case 清单，Linear/Async 各 3 次重复，每模型 282 次运行。历史 split 不作为主实验榜单筛选条件。统一入口与统计规则见 [formal-47](../experiments/formal-47/README.md)。

## Track A — official

Track A is the only publication/leaderboard track. It fixes the reference API harness, kernel, two-mode manifest design, container isolation, conformance suite, case contracts, private verifier, scoring and aggregation. Participants configure supported model/API settings but cannot replace orchestration code.

Eligibility is recorded per episode. Any custom adapter, scripted backend, disabled workspace, skipped conformance, contract drift or digest mismatch moves the run out of Track A instead of silently mixing it into official results.

## Track B — agent systems

Track B runs complete agent systems through a benchmark-maintained bridge. It includes Linux-container drivers for Claude Code, Codex CLI, LangGraph and the OpenAI Agents SDK. Participants may replace `ModelBackend`, `ContextBuilder`, `DelegationPolicy`, `AgentPolicy` and `LifecycleHooks` with `module:factory` components.

The adapter profile and v1 public result packages are development-only. The kernel still owns scheduling, result release, capability execution, workspace isolation, private verification and scoring. Track B results do not enter the Track A leaderboard.

See [Track B agent systems](track-b.md) for installation, configuration and commands.

## Development runs

Development runs exist for debugging adapters, cases and infrastructure. They may disable containers, use deterministic backends, skip conformance or use another adapter. Their scores and diagnostics are reported separately and cannot affect the official leaderboard.

Both tracks use only `linear` and `async`; old five-condition and shared-fork designs are not supported.
