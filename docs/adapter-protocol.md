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

The adapter may emit registration/runtime metadata and `ready`; child lifecycle; main actions; explicit result consumption and promotion outcomes; evaluator-observed artifact commits; episode termination; and infrastructure failures. On the delivery path it additionally records `adapter_queued` (when it enqueues a released occurrence) and `result_presented` (when the result is bound to a real started main-model request); see [Delivery occurrence lifecycle](#delivery-occurrence-lifecycle).

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

`result_delivered` is retained as a documented legacy/compatibility alias. The canonical delivery model below splits its single "delivered" fact into three distinct causal boundaries, each carrying its own identity.

## Delivery occurrence lifecycle

A released completion is delivered through a **delivery occurrence** — one `delivery_occurrence_id` per delivery. A single child completion (`completion_id`) may feed **many** occurrences, because the same result may be presented into several main-model requests. Replay therefore creates a new *occurrence*, never a new *completion*.

Three previously-conflated facts must not share one event:

- `R_i` **Gateway available** = `result_available` — the Gateway/kernel has released a delivery occurrence.
- `A_i` **Adapter queued** = `adapter_queued` — the adapter has accepted the occurrence into its FIFO presentation queue.
- `O_i` **main-model observed** = `result_presented` — the occurrence was added to and committed to a real started main-model request. "Observed" means it entered the model's request context, **not** that it was understood or accepted.

Canonical event sequence:

```text
child_completed
→ result_contract_validated / result_rejected
→ result_available
→ adapter_queued
→ presentation_prepared
→ main_model_call_started
→ result_presented
→ main_model_call_finished
→ main_action_started
→ main_action_finished
→ main_turn_completed
→ response_window_closed
```

Producer boundaries (spec §3.3): the Gateway/kernel decides when a result is releasable and records `result_available`; the adapter reliably enqueues and records `adapter_queued`; the evaluator generates a before-snapshot `S_i^-` then authorizes presentation (`presentation_prepared`); the adapter records `result_presented` only once a real main-model request has started; the runtime records `main_turn_completed` after the turn's tool calls finish; the evaluator generates the after-snapshot `S_i^+` and closes the response window (`response_window_closed`).

`result_presented` must be provable only once a real main-model request started — never merely queued or snapshot-prepped. Replay reconstructs this lifecycle and rejects impossible transitions: `result_presented` before `adapter_queued`, a duplicate `delivery_occurrence_id`, or closing a window that was never opened.

### Delivery-occurrence event shape

Each canonical delivery event carries the identity fields it needs from the set `delivery_occurrence_id`, `completion_id`, `turn_id`, `window_id`:

```json
{"type":"result_available","delivery_occurrence_id":"o1","completion_id":"c1"}
{"type":"adapter_queued","delivery_occurrence_id":"o1","completion_id":"c1"}
{"type":"presentation_prepared","delivery_occurrence_id":"o1","completion_id":"c1"}
{"type":"result_presented","delivery_occurrence_id":"o1","completion_id":"c1","turn_id":"t2","window_id":"w1"}
{"type":"main_action_started","delivery_occurrence_id":"o1","turn_id":"t2"}
{"type":"main_action_finished","delivery_occurrence_id":"o1","turn_id":"t2"}
{"type":"main_turn_completed","delivery_occurrence_id":"o1","turn_id":"t2"}
{"type":"response_window_closed","delivery_occurrence_id":"o1","window_id":"w1"}
```

### Delivery visibility

`result_presented` is **public/auditable** — an observer may confirm a result was bound to a real started main-model request — but its private expected effect (result role, schedule, authority/supersede labels, snapshot digests, source case event ids) stays hidden from any model-facing projection.

`presentation_prepared` is **kernel-private**. It may carry evaluator-owned fields such as snapshot digests (`snapshot_digest`) and source case event ids (`case_event_id`); because it never reaches a model, these do not leak.

Public model-facing payloads must exclude evaluator-private role, schedule and expected disposition. Kernel-private events may include evaluator snapshot digests and source case event ids.

## Kernel capabilities

Capability requests are transport messages, not scored events. The fixed harness exposes child workspace creation, main/child terminal access, promotion and cleanup, plus:

- `observe_artifact(artifact_id)`: returns only public path and digest while the observer command stays private;
- `verify_current_state(artifact_ids, lineage_completion_ids)`: returns aggregate pass/fail counts while hidden check IDs, commands and per-check truth stay private.

Event assets are isolated before the adapter starts and staged by the kernel only after it observes a valid child/workstream binding. The adapter cannot request an asset path or role.

## Lineage and traces

A completion is usable only after gateway delivery and explicit `result_consumed`. Artifact and verification lineage may reference only consumed completion IDs. Artifact digests are evaluator-observed; self-reported verification is a protocol violation.

`participant_trace.jsonl` is the participant-visible audit surface. `event_source.jsonl` and `trace.jsonl` contain evaluator-private facts needed for reproducible scoring and must not be exposed to a running participant.
