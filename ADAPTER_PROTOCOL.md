# Async-RBench adapter protocol 3.0

The official interface is JSONL over stdin/stdout. The benchmark kernel owns scheduling, result release, private case truth, workspace isolation, artifact observation, verification, and scoring. The adapter owns only the evaluated main agent and its subagents.

## Episode start

`episode_started` exposes only information needed to perform the task:

- episode identity, `linear` or `async` execution mode, seed, task instruction and neutral guidance;
- public workstream IDs, tasks, targets, priorities and structural result schemas;
- the benchmark-owned initial wave and spawn budget context;
- public artifact IDs and paths;
- container/workspace handles required by the fixed harness.

It never exposes result roles, authoritative/superseded labels, event schedules, stale truth, invalidation/reopen sets, validator commands, hidden checks, observer commands, or case capability labels.

## Adapter events

The adapter may emit registration/runtime metadata and `ready`; child lifecycle; main actions; explicit result consumption and promotion outcomes; evaluator-observed artifact commits; episode termination; and infrastructure failures.

`child_completed` contains `child_id`, `completion_id`, `payload`, and optional usage. It does not contain `result_kind`; the kernel privately binds the child’s validated workstream to evaluator truth. Adapters cannot emit verification truth.

## Gateway outcomes

The adapter receives one of these public projections:

```json
{"type":"result_delivered","child_id":"c1","completion_id":"p1","workstream_id":"ws","payload":{},"payload_sha256":"..."}
```

```json
{"type":"result_rejected","child_id":"c1","completion_id":"p1","workstream_id":"ws","reason_codes":["..."]}
```

Neither shape contains stale, authority, invalidation, reopen, schedule, or private result-role fields. The main agent must infer what to do from the task, payload, workspace and observed outcomes.

## Kernel capabilities

Capability requests are transport messages, not scored events. The fixed harness exposes child workspace creation, main/child terminal access, promotion and cleanup, plus:

- `observe_artifact(artifact_id)`: returns only public path and digest while the observer command stays private;
- `verify_current_state(artifact_ids, lineage_completion_ids)`: returns aggregate pass/fail counts while hidden check IDs, commands and per-check truth stay private.

Event assets are isolated before the adapter starts and staged by the kernel only after it observes a valid child/workstream binding. The adapter cannot request an asset path or role.

## Lineage and traces

A completion is usable only after gateway delivery and explicit `result_consumed`. Artifact and verification lineage may reference only consumed completion IDs. Artifact digests are evaluator-observed; self-reported verification is a protocol violation.

`participant_trace.jsonl` is the participant-visible audit surface. `event_source.jsonl` and `trace.jsonl` contain evaluator-private facts needed for reproducible scoring and must not be exposed to a running participant.
