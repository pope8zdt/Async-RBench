# Connecting an evaluated agent system

This directory exposes Async-RBench's low-level adapter entrypoints. The current
formal evaluation is the Model API Track through `reference_scaffold_api`.
Track B provides benchmark-maintained drivers for Claude Code, LangGraph and
the OpenAI Agents SDK, so those runtimes do not implement JSONL directly. See
`docs/track-b.md`.

For an unknown or experimental agent system, one adapter process represents the
whole evaluated system. It owns participant policy: the main-agent loop,
subagent manager and tool-selection strategy. Async-RBench owns the result-delivery
gateway, execution workspaces, execution-mode scheduler, private verifier and scoring.

Use `async_rbench.protocol_sdk.gateway.JsonlGateway` to instrument lifecycle hooks:

1. receive `episode_started` and give its instruction/guidance to the main agent;
2. emit child spawn/start lifecycle events;
3. emit `child_completed` without a participant-selected result role, and keep its payload hidden from the main;
4. pass payload to the main only after `receive_delivery()`;
5. emit main actions, result consumption and artifact lineage; request observation and verification through kernel capabilities;
6. emit `episode_ended`.

Stdout is reserved for JSONL; send model/tool logs to stderr. Terminal, child
workspace, promotion and cleanup operations must use the kernel capability RPC;
an adapter must not invoke Docker directly.

`tests/mock_adapter.py` is a protocol conformance example, not an evaluated agent.
`adapters/native_agent.py` is also currently a deterministic protocol smoke
profile, not a real native-agent integration.

`adapters/track_b.py` is the common Agent System Track entry point. Framework
and custom component selection belongs in `configs/track-b/*.yaml`; the adapter
validates every component before emitting `ready`.

## Included reference scaffold

`adapters/reference_scaffold_api.py` is a thin executable participant implementation,
not just a protocol mock. It provides a model tool loop, main-created concurrent
children, Docker-snapshot isolation, wait/cancel, gateway buffering, explicit
result decisions, artifact lineage and evaluator-mediated hidden verification. Configure
an exact model API using `configs/model-profiles/reference-config.example.yaml`.

See `REFERENCE_SCAFFOLD.md` for the visibility boundary, conformance command and
real Docker command.
