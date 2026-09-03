# Async-RBench Redesign — Technical Debt / Consolidation Ledger

Deferred improvements found during per-task review, to be addressed in a consolidation
pass before final completion (Task 12 end-to-end verification). Items are non-blocking
for their own task; they are tracked here so they are not lost.

## Correctness-fix completion record (2026-09-03 — remaining-correctness-fixes plan, Tasks 1–10)

The implementation plan `docs/superpowers/plans/2026-09-03-async-rbench-remaining-correctness-fixes.md`
is COMPLETE through its Task 10 (final gate, commit
`test: gate async rbench correctness end to end`; Task 1–9 commits end at `b1d5d2b`).
Semantics are frozen in `docs/async-rbench-result-contract-and-termination.md` and gated
end to end by `tests/test_end_to_end_acceptance_gates.py`. The debt *this* plan closed:

- ✅ Task 1 — canonical child run outcomes: non-submission ends are manager-level
  terminals; `completed_hidden`/`resource_exhausted` are never runtime statuses; no
  non-submission path emits `child_completed` / `result_contract_validated` /
  `result_rejected`.
- ✅ Task 2 — hard context bound before budget admission (context compression precedes
  estimation; serialized messages+tools payload within the configured byte limit).
- ✅ Task 3 — one shared public validation engine (`validate_public_submission`) for Child
  `validate_result` / `submit_result` / Gateway; identical public reason codes.
- ✅ Task 4 — public submission rejection decoupled from private semantic evaluation:
  `validator_stage` ∈ {`submission_contract`, `semantic_evidence`}; a private semantic
  validator can never produce `result_rejected`.
- ✅ Task 5 — contract audit fails closed; hidden submission constraints make the audit
  fail (was fail-open).
- ✅ Task 6 — idempotent full-corpus contract/validator-stage migration; all workstreams
  declare `payload_only` or `report_file`, zero hidden submission constraints.
- ✅ Task 7 — exact re-delegation admission (first complete model call reserved
  atomically) and bounded recovery (≤ one recovery spawn per workstream).
- ✅ Task 8 — exhaustive per-attempt terminal taxonomy; `gateway_accepted` no longer
  requires `result_consumed`; per-mode paper metrics with non-overlapping denominators.
- ✅ Task 9 — prompt / mode-invariance regression repair (`b1d5d2b`).
- ✅ Task 10 — end-to-end acceptance sequence plus `audit-run` and official-aggregation
  hard gates (`contract_fixture_failure`, `hidden_submission_constraint`,
  `private_submission_rejection`, `unknown_child_terminal`,
  `official_linear_zero_main_tokens`); development runs reported but never leaderboard rows.

The older forward-owned entries **below this record are retained and remain open** (they
are not addressed by this plan): `result_available` / `response_window_closed` / `S_i^+`
emission, `_KERNEL_PRIVATE_TYPES` and `validate_gateway_event` wiring (M1/M2),
designed-terminal double-delivery suppression (M4), scoring consumption of private design
facts (M5), `score_domain` ingestion wiring / `validate_scoring_domains` callers,
stimulus A–E authoring and live-seam form, pool-constancy wiring, and the dead-guard and
DRS-attribution clean-ups.

## Task 1 — event-mechanism inventory (commit 51ccadb)

(none blocking; see notes in the task report)

- 8 instances lack `event_policy.json`/`case_ir.json`; their derived contract fields are
  `not_declared`. `event_id` populated from first scenario-event id. Confirm this is the
  intended honest representation and that Task 10 populates the real values.
- `required_trigger` is always `not_declared` because the taxonomy declares no evaluator
  trigger boundary. Confirm this is acceptable for the migration manifest.

## Task 8 — observation-point BTS/DRS scoring (commit 0a413ee, spec ✅, quality APPROVED_WITH_MINOR; fixes to land)

- 🟠 F1 — `score_domain` is a SOFT constraint: `validate_scoring_domains` has zero callers
  (no ingestion path), and `schemas/unified_case_v3.schema.json` `score_points.items.required`
  omits `score_domain`. A check without `score_domain` passes both schema and runtime and is
  silently dropped from BOTH `score_base_task` and `_event_async_outcome` — the undercounting
  the domain split aims to prevent. 0 case files carry `score_domain` today, so nothing breaks
  now. **Deferred to Task 10**: wire `validate_scoring_domains` into the semantic-check
  ingestion path and add `score_domain` to the schema `required` alongside the case-data authoring,
  since adding it now would fail every current case.
- 🟡 F3 — unreached event semantics: when a contract carries scoring fields but the event has
  no boundary events (participant never reached it), `scoring.py` `continue`s so the event is
  dropped from the `async_drs` denominator (treated unscored, not 0). Currently pinned by a test
  as the intended behavior. **Open for spec owner**: unreached→unscored vs unreached→0. If the
  intent is to penalize participants who never reach a required replanning event, change it to 0.

## Task 11 — aggregate headlines + pair qualification (commit c02422f, spec ✅ SPEC_COMPLIANT, quality TBD)

- 🟠 **contract `primary_outcomes`/`x_rules` stale** (evaluation_contract.json): still describe
  `dynamic_primary`/`semantic_secondary`/`critical_dynamic_gate` as the "primary async benchmark
  metric / leaderboard", contradicting §2.2 and §13(11) ("new headlines only Linear BTS / Async
  BTS / Async DRS"). This is documentation-only — the functional headline is driven by aggregate
  `primary_metric`, so it does NOT affect computation — but should be synced to stop it from
  misleading. Fix in consolidation pass (or Task 11 follow-up) by renaming/annotating these as legacy.
- 🟡 unbounded-event DRS attribution: `scoring.py:1057-1064` `continue` treats any
  "no evaluator-boundary" event as unscored (excluded from async_drs mean), without distinguishing
  "evaluator never generated it (infra → exclude)" from "participant ended before the event
  (participant → DRS=0 per §9.4)". Implementer flagged "pending spec-owner ruling"; finish-guard
  mitigates the participant path. **Open for spec owner** (same as Task 8 F3).

## Task 11 (quality) — APPROVED_WITH_MINOR applied observations (commit c02422f)

- 7 dead `_case_macro` first returns (aggregate.py:779-782,811-813): the scalar `linear_semantic`/
  `async_semantic`/`async_dynamic`/`async_dt`/`linear_bts`/`async_bts`/`async_drs_value` mean values
  computed but never consumed (headlines use the theme_macro mean). Either `_, x_cases = _case_macro(...)`
  or add a cases-only path. Consolidation clean-up.
- Fixed-factor field names duplicated between `_pair_key` (aggregate.py:139-151) and `_PAIR_FIXED_FACTORS`
  (:157-166) — derive `_pair_key`'s fixed-factor segment from `_PAIR_FIXED_FACTORS` to remove drift.
- Opportunity-count field names duplicated reader (aggregate `_OPPORTUNITY_COUNT_FIELDS`) / writer
  (scoring.py literal dict keys) — hoist to a shared importable constant.
- `primary_metric` (singular, aggregate) vs contract `primary_metrics`/`legacy_primary_metrics`
  (plural) naming mismatch; reporter does not emit the contract's `legacy_primary_metrics` array.
- Test gap: aggregate's `audit.pair_quality_errors` wired path (`_pair_quality_errors` by_family +
  setdefault nesting) is never asserted (only the delegated unit `pair_identity_errors` /
  `pair_qualification_errors` is). Add a multi-case integration test.
- `pair_identity_errors` fixed-factor branch is actually unreachable in the aggregate path (grouping
  by `_pair_key` already includes all fixed factors, so mismatches land in different buckets and are
  handled as "unpaired" rather than "mismatch error"). Add a clarifying comment.
- `architecture_version: "8.0"` (aggregate.py:1014) sits on a different axis than contract
  `9.1.0-dev` — confirm intentional.

## Task 5 (forward-owned event-emission gaps found during Task 4 spec review)

These are delivery-lifecycle event boundaries that the spec §3.2/§3.3 assign to the
gateway/kernel and evaluator but that nothing in the runtime emits yet. Both break the
canonical event sequence and must be wired before Task 12 e2e. **Ownership: Task 5**
(which owns Async availability control + response-window completion per §11).

- 🟠 **`result_available` is never emitted** (gateway/kernel responsibility per §3.2/§3.3,
  §11 scheduler.py "Async 可用性控制"). Runtime `handle_delivery` (runtime.py:737-739) emits
  `adapter_queued` directly with no preceding `result_available`. Since `result_available` is the
  ONLY event that creates the occurrence (`_occurrence_of(create=True)`), EventStore replay of a
  live async delivery hits `_apply_adapter_queued`'s `ProtocolError("adapter_queued before
  result_available")` (event_store.py:231-235). Verify after wiring that replay no longer raises.
- 🟠 **`response_window_closed` not emitted / `S_i^+` not generated** (evaluator responsibility).
  `close_active_window` (presentation.py:222-231) only nulls `_active_window`; runtime.py:1147
  never emits `response_window_closed` nor captures an `S_i^+` snapshot. `_apply_response_window_closed`
  (event_store.py:277-286) is valid only for windows that were `result_presented`, but never fires.
  Wire the evaluator-side close (emit `response_window_closed` + `S_i^+`) once the window settles.

## Task 4 (quality) — observer/handshake APPROVED_WITH_MINOR findings (commit 383719b + 0146f02)

- **S1 — `main_action_finished.success` = "dispatch didn't raise", NOT "exit_code==0"**
  (runtime.py:1243, _finish_main_tool runner.py:1411-1432): a `terminal` command with
  `exit_code=1` still gets `success=True` if dispatch didn't throw, and feeds the provisional
  observer via `success and kind in OBSERVED_TOOLS`. Collides with §4.1(2) "finished with
  success"; a non-zero-exit command could establish provisional. Fix: derive
  `success=(result.exit_code == 0)` for terminal/promote paths, or explicitly document the
  "success = dispatch succeeded (not exit-code)" semantics and align spec intent.
- **S2 — two definitions of "which tool can establish provisional"**: production goes
  `runner.py:673 observer.observe()` (filter+success gate lives adapter-side via `OBSERVED_TOOLS`);
  the `ProvisionalObserver.on_event` started→finished state machine (`MODIFYING_TOOLS`)
  is only reached by tests. Drift risk between observation.py `MODIFYING_TOOLS` and runtime.py
  `OBSERVED_TOOLS` (both `{"terminal","promote_child_path"}`). Consolidate: either route runner
  through `on_event(finished)`, or delete the unused `on_event`.
- **S3 — dead `to_fact` methods** (observation.py:108,326-327) with zero callers and a schema that
  mismatches the inline fact dict runner actually writes (missing `visibility`/`turn_id`). Delete or
  make runner reuse `to_fact`.
- **S4 — prod vs test reason categories diverge**: `tool_failed`/`non_modifying_tool`/`unmatched_start`
  only from `on_event` (test-only); prod emits only `no_decision_bearing_points`/`incomplete_snapshot`/
  `predicate_not_met`/`observer_failure`. Align with S2.
- **S5 — missing-recorder ValueError branches** (runner.py:759-760,769-770) untested.
- **S6 — adapter post-tool observer trigger point** (OBSERVED_TOOLS→_observe_main_state) has no
  unit test asserting terminal/promote triggers & list_subagents/failure doesn't.
- (O1-O6 cosmetic: magic `900` timeout, unused `point` param in `parse_observation_output`, duplicate
  `sys` import in json snapshot script, `provisional_established` alias, docstring/body mismatch in a
  test, mark_presented timing seam not directly tested.)

## Task 5 (forward-owned spec gaps found in spec review, commit 19f67f2)

- 🟠 **`S_i^+` event-after snapshot not implemented** (§3.3): `_close_presentation_window`
  (runtime.py:1151-1169) emits only `response_window_closed`; no `S_i^+` after-snapshot is
  generated/recorded. `_KERNEL_PRIVATE_TYPES` has no S^+ type; runner/workspace has only the
  S^- `prepare_result_presentation` capability. **Does NOT break scoring** — DRS before/after is
  reconstructed from `artifact_committed.observed_digest` via `_event_state_snapshots`
  (scoring.py:150-166,1077-1082), independent of the runtime S^+ event. Must close before Task 12:
  add an after-snapshot capability in `protocol_sdk/capability.py` and register an S^+ kernel-private
  event type in `event_store._KERNEL_PRIVATE_TYPES`. Natural home: **Task 9** (real stimulus) or a
  dedicated event-model consolidation pass.
- 🟡 **§6 Linear replacement-wave synchronous gather not wired**: `_maybe_present_linear_bundle`
  is called only once at run() start; a Linear main-model subsequent `spawn()` reaches
  `handle_delivery`'s linear branch (sets `status="delivered"`, signals barrier) but neither emits a
  per-result presentation NOR a second bundle — so replacement results are invisible to the model.
  §6 requires replacement waves to also gather synchronously. Low frequency (initial wave usually
  covers all required workstreams). Fix: route Linear replacement waves through the same bundle
  barrier. Consolidation pass (or a Task 5 follow-up).

## Task 5 (quality) — APPROVED_WITH_MINOR findings (commit 19f67f2)

- **S4 (most significant) — `atomic_bundle_presentations` / `individual_result_presentations`
  are empty reads**: the new aggregate Linear invariants `linear.atomic_bundle_presentations!=1`
  and `linear.individual_result_presentations!=0` (aggregate.py:199-202) are guards that never
  fire, because the report pipeline never produces those fields (`score_trace`/report never fills
  them; grep shows only aggregate.py + test-synth dicts). So `left.get(...)` is always None and
  `!=1` never triggers — the Linear eligibility audit check is effectively a no-op (no false
  scores, just a dead guard). Fix: have the linear report count `linear_bundle_presented` into
  `atomic_bundle_presentations` and `result_presented` into `individual_result_presentations`,
  or delete the two dead guards. Consolidation pass.
- terminal-status set duplicated 3x (runtime.py:52 `LINEAR_TERMINAL_STATUSES` vs literal sets at
  :339-343 `unresolved_count`, :906 `wait()`) — churn risk; unify on the constant.
- `cancel()` (:930) and `_run_child`'s `CancelledError` path (:778) set `status="cancelled"`
  without `_delivery_event.set()` (latent; unreachable today because main can't cancel pre-bundle,
  but would hang `_wait_for_linear_terminal` if pre-bundle cancel is ever allowed). Add `set()`.
- timeout/cancellation both collapse to `status="cancelled"` (`_linear_entry` else branch
  :478-480) with no comment on the semantic loss, and that branch is untested (bundle test only
  covers delivered/contract_rejected).
- `_close_presentation_window` docstring (:1151-1153) calls `response_window_closed` the "S_i^+
  closure boundary" with no forward-note that S_i^+ is still un-emitted (ledgered). Fix docstring.
- `_linear_entry` outer envelope not `assert_participant_safe`-checked (only the two sub-dicts).

## Task 3 — FIFO presentation queue + response windows (commit 005aa8c + e4613c9, spec ✅, quality APPROVED_WITH_MINOR)

- 🟡 **`settled` is a naked field — settle path is actually dead in production**
  (presentation.py): `ResponseWindow.settled` starts False, production never sets it True, and
  there is no `mark_settled()` method (tests set `window.settled = True` directly). Net effect:
  the real runtime closes windows ONLY via `max_response_turns`; the spec §5.2 "settled or
  max_response_turns" early-close route is inert. Fix: add `mark_settled()` and route the
  evaluator→adapter settle signal (from Task 4's observer/`S^+`) through it. **Likely resolved
  when the evaluator-ownership handshake lands (Task 4/9)** — verify then.
- 🟡 **`ChildRecord.shared`/`presented` residual field** (runtime.py:59,716): `presented`
  is written `False` in `handle_delivery` but never read True; `mark_presented` uses the queue's
  `presented_occurrence` instead. Delete the field or wire it to `mark_presented`.
- 🟡 `DeliveryOccurrence.scored`/`benchmark_event_id`/`replay_of_occurrence_id` defined + tested
  but never populated/consumed by runtime — forward-looking replay reservation. Confirm wiring in
  Task 9/10 or delete to avoid speculative interface.
- 🟡 Tests hardcode `range(4)` + `min/max=1/4` duplicating production defaults (silently coupled);
  tests set `window.settled` bypassing encapsulation.
- 🟡 `receive_seq` vs spec `adapter_receive_seq`; it is really a local occurrence counter
  (equal to the FIFO arrival order). Rename or comment.
- 🠾 `presentation_prepared`/`response_window_closed` remain evaluator-owned and are **not**
  emitted by the adapter/queue (Task 3 scope). Wait for Task 4 handshake + Task 9 to wire
  S^-/S^+ and close windows from the evaluator side.
- 🟡 **case-contract override of min/max_response_turns not wired**: adapter hardcodes
  min=1/max=4; `handle_delivery` never reads the case contract. The `ResponseWindow.open`
  seam exists but no caller injects a case override. Spec §5.2 requires the case contract to
  be able to raise/lower the cap, frozen into digest. **Deferred to case-authoring/migration
  (Task 9/10)** — current cases don't yet carry these fields, so there's nothing to inject; ensure
  the digest consumer actually reads this seam.
- 🟡 §5.3 double-role prevention is enforced at the presentation layer (each occurrence
  presented once), but the adapter doesn't yet classify `scored` vs `plan_formation_input`
  (`DeliveryOccurrence.scored`/`benchmark_event_id` are always False/None in `handle_delivery`).
  That classification is contract/scoring-domain responsibility, out of Task 3 scope → Task 9/10.

## Task 2 — delivery-occurrence events (commit 7273882, spec ✅, quality APPROVED_WITH_MINOR)

- 🟠 Orphan-occurrence handling inconsistent in replay: `_apply_main_action`
  (event_store.py ~259-267) and `_apply_main_turn_completed` (event_store.py ~270-274)
  silently swallow an unknown `delivery_occurrence_id`, while `_apply_adapter_queued` /
  `_apply_presentation_prepared` / `_apply_result_presented` raise. Either make the two
  symmetric (raise via `_occurrence_of(create=False)`) or add a one-line comment justifying
  the leniency. Only affects malformed sources; well-formed sources unaffected.
- 🟡 Unreachable guard in `_apply_adapter_queued` (event_store.py ~233-234): `if not
  occurrence.available` is provably unreachable (occurrence only enters state via
  `_apply_result_available` which sets available=True); ordering is actually enforced by
  `_occurrence_of`. Drop the dead check or move availability into `_occurrence_of`.
- 🟡 `new_core_event_types` (protocol.py) is pre-existing DEAD code; the commit adds a
  parallel `delivery_occurrence_event_types`. Consider having one reference the other.
- 🟡 `delivery_occurrence_event_types` / `delivery_occurrence_identity_fields` defined but
  not yet imported anywhere. Expected until emission wiring (Tasks 4/9). `public_presentation`
  (event_store.py ~167-175) hardcodes the four identity-field keys — cheap DRY win: import
  `delivery_occurrence_identity_fields` there.
- 🟡 `_apply_presentation_prepared` doesn't require `adapter_queued` first (canonical order
  is adapter_queued → presentation_prepared). Consistency nit, not a documented guard.
- 🟡 Test coverage gaps on live branches: `result_available` missing `completion_id`,
  `result_presented` missing `turn_id`/`window_id`, the "never made available" error path,
  orphan/main_action no-op path, and `public_presentation` raising on private-field payload
  through the real `strip_for_adapter` path.
- 🟡 Operational follow-ups (not Task 2 regressions): `runner.py` does not yet emit any of
  the 8 delivery events (wired in Tasks 4/9); `schemas/adapter-event.schema.json` `type`
  enum omits `adapter_queued`/`result_presented` (only existence-checked, not enforced);
  `dynamic_pilot.py` `outbound_types` and conformance `events` predicates still key on
  `result_delivered` and must be updated once live episodes emit the new events.

## Task 6 — budget split (commits 5aa2bc1 + 198add5, spec ✅ SPEC_COMPLIANT, quality ✅ APPROVED after fixes)

- 🟢 Quality-Medium #1 (reserve leak) fixed in 198add5: `BudgetPool.release()` + child timeout/finally + main-loop except wiring, `budget_released` event.
- 🟢 Quality-Medium #2 ("exact" label) fixed: configured-tokenizer branch now reports `tokenizer_proxy`; heuristic documented as non-guaranteed upper bound; `provider_exact` reserved for a real tokenizer.
- 🟢 Low #3/#6/#7/#8a (settle docstring, main_total==pre+post validation, scaffold reserve→settle + budget_exhausted tests, switch_to_post comment) fixed in 198add5.
- 🟡 forward-owned (non-blocking, from re-review): main-loop `except` path — if `settle` itself raises (not normal single-reservation flow), `settled` stays False and the except would try to `release` the same reservation again and may raise, masking the original. Unreachable in normal flow; optionally harden later (e.g. wrap release in its own try/except).
- 🟡 note: `BudgetPool` default `accounting_mode` flipped to `conservative`; `tokenizer_proxy` is the honest label when a (proxy) tokenizer is configured.

## Task 7 — dual main/child provider backends (commit 1c22db6, spec ✅ SPEC_COMPLIANT, quality TBD)

- 🟠 **`verify_child_pool_constancy` not wired into live aggregation** (runner.py:408): defined + unit-tested, but `aggregate_reports` (aggregate.py:934) and hard-fail paths never call it. Step 4 "runner integrity checks must verify child identity constant" only produces it + unit test, not enforced at headline. Also `run_episode` stamps only `child_pool_id`; aggregate.py:148-165 references `child_provider`/`child_model`/`child_backend`/`child_budget` which are never stamped. **Forward-owned to Task 10/11/12 consolidation** — wire the check into a group-level hard-fail gate and stamp the child fields.
- 🟠 **Other model profiles not migrated to dual binding**: only `deepseek-v4-pro.yaml` is explicit; the rest of `configs/model-profiles/` rely on legacy fallback (`child_pool_id=""` → None → rejected once constancy check wired). No automated gate forces a Track A profile to declare both providers + child_pool_id. **Forward-owned to Task 10** (migration) or Task 12.
- 🟡 **validate / build_backend mismatch for `scripted_test`** (quality F1): config.py:318-320 accepts `child_provider.backend="scripted_test"`, but `build_backend` (model_backend.py:692) raises ValueError for scripted_test; the adapter's scripted_test branch keys only on top-level `config.backend` (adapter.py:37), so a nested scripted_test passes validate yet crashes build_backends. **Being fixed in Task 7 follow-up** (drop scripted_test from role allow-set / align adapter role-level branch).
- 🟡 **child_pool_identity / verify_child_pool_constancy do not cover prompt/budget constancy** (quality D2): identity is `f"{child_pool_id}:{backend}:{child_model}"` and the docstring claims it guards prompt/budget/workstream too, but only id+backend+model are compared. §8 requires prompt/budget constant. **Forward to consolidation** — either include a budget/prompt fingerprint in the identity or narrow the docstring.
- 🟡 **`_metadata_audit` resolved_model mixes child's (quality F2)**: runner.py:344-350 takes the last non-empty resolved_model; with dual backends the adapter/snapshot merge main→child, so the last is the child's — leading to a false "requested/resolved mismatch" note and a `score.resolved_model` of the child's under a §8 main≠child config. **Fixing in Task 7 follow-up** (filter by role=="main" + add unit test).
- 🟡 **role-level max_api_concurrency bypasses frozen resource-policy check** (quality F5): resource_policy.py compares only top-level profile_limits keys; role-level concurrency is outside the check. Latent — deepseek role-level=4 matches so it passes. Include role-level concurrency in validate_official_resource_policy in a later pass.
- 🟡 **`_RoleView` reuse path untested + double-counts observation** (quality F3); **`_metadata_audit:360` missing isinstance-dict guard** (F4); **`run_one_main_and_one_child_turn` is a test-driven method on a production class** (F6) — all Low/latent, consolidate later.
- 🟡 Step 1 assertions spread across 3 tests (single sentinel not used) — functionally equivalent, no action.

## Task 9 — real specialized event mechanisms (commits dccc029 + 83f1871 + ba6e81c + 6ca9d90, spec-review SPEC_ISSUES → fixed in ba6e81c, spec re-review SPEC_COMPLIANT ✅, quality APPROVED_WITH_MINOR)

- ✅ **Designed terminal outcome now presented end-to-end** (spec-review issue b+c): the adapter's
  `handle_delivery` (profiles/reference_scaffold_api/runtime.py) now falls back to binding a
  gateway-designed terminal by the delivered `child_id` when the delivery carries a
  `terminal_outcome` marker and that child is known/in-flight, so the synthetic completion_id
  no longer drops the delivery as "unknown completion". The participant-visible projection
  (`public_delivery`, case_contract.py) now exposes the observable `terminal_outcome`
  (timeout/crash) — the replanning stimulus body — while keeping
  `evaluator_designed_failure`/`evaluator_terminal_reason` kernel-private scoring facts.
  Commit `6ca9d90` additionally adds both fields to `event_store._KERNEL_PRIVATE_FIELDS` as a
  global kernel-private guarantee across non-public streams.
  **Semantic decision**: the participant sees *that* the child terminated (the observable
  state), never *whether* it was a designed vs infrastructure failure nor the design reason; a
  non-terminal delivery carries no `terminal_outcome` field at all.
- 🟠 **Case-declaration-triggered stimuli are a Task 10/authoring dependency** (spec-review issue a):
  the consumption seam now exists — `DeliveryController.consume_declared_stimuli` (scheduler.py)
  reads the async schedule for `child_timeout`/`child_crash` events and, on the declared child's
  `child_started`, fires the corresponding `apply_child_terminal_outcome`/`apply_child_crash`
  producer (wired into `run_episode`). **Only child*-terminal stimuli are wired today**; the
  remaining producers (task_scope_revision / dependency_graph_revision / resource_pressure /
  deadline_update / implicit_error_result) have no schedule declaration form yet, so their
  consumption path is authored in **Task 10** when cases actually declare these stimuli. The
  exact declared field names (`result`/`payload`/`outcome_detail`/`completion_id`/`crash_source`)
  are the Task 10 authoring contract to freeze.
- 🟡 **S^+ after-snapshot / `response_window_closed` still not emitted**: Task 9 did not emit them; still forward-owned (see Task 5 item). Does not block scoring.
- 🟡 (implementer) `validate_gateway_event` resource-pressure guard bug fixed during TDD (compared literal string `"straggler_child_id"` instead of the field's value).

## Task 9 (quality) — APPROVED_WITH_MINOR findings (commits dccc029+83f1871+ba6e81c+6ca9d90)

Verified: 4 commits touch exactly the task's allowed files, no out-of-scope; hard locks
(`max_api_concurrency=4` / `episode_timeout_sec=2400`) untouched; Task 6 budget keys + Task 7
dual-provider / `child_pool_id` preserved; `tests/test_resource_policy.py -q` passes;
related suites 56 passed; full suite **572 passed / 67 skipped** (HEAD `6ca9d90`). 8 stimulus
state machines, designed==scored / infra==unscored split, `public_delivery` projection and
synthetic completion_id fallback binding are all correct and consistent on the test path.

**Medium (disposition in brackets):**

- **M1** `_KERNEL_PRIVATE_TYPES` (event_store.py:39-51) does not include the new audit/classification
  event types (`child_terminal_outcome`, `task_scope_revision`, `dependency_graph_revision`,
  `resource_pressure`, `deadline_update`, and existing `infrastructure_failure`); privacy currently
  depends entirely on `_record_controller_stimulus_audits` stamping `kernel_private` per record.
  Keep stale `child_terminal_started`/`child_terminal_finished` entries alive too. **→ forward-owned;
  add these to `_KERNEL_PRIVATE_TYPES` as cheap defense-in-depth in Task 10/12 (before Task 12).**
- **M2** `validate_gateway_event` (protocol.py:220-252) is never called from the runtime pipeline;
  protocol.py:58-61 docstring claims it validates before kernel persistence. **→ forward-owned:
  wire (at least assertively) into the persistence path or fix the docstring; Task 10/12.**
- **M3** 4/8 stimuli are seam-only and never schedule-declaration-driven: `apply_resource_pressure` /
  `apply_deadline_update` / `apply_task_scope_revision` / `apply_dependency_graph_revision` have zero
  run_episode call sites (only test-direct), so their audits are always empty in a real episode; yet
  event_taxonomy.py still declares them legal schedule scenario events. **→ **Task 10 authoring
  dependency** — declare the remaining-5 form and wire their consumption; also document these as
  audit-only until then (see Task 9 authoring note above).**
- **M4** A designed terminal child can later deliver a real completion (double-delivery). After
  `apply_child_terminal_outcome` discards the child, nothing suppresses a subsequent real
  `child_completed` for the same child_id (delivery would land via force_release/_drain).
  **→ **Task 10 authoring constraint**: never declare `child_timeout`/`child_crash` on a child that
  could actually complete; add a suppression guard (skip real completion for a child already given a
  designed terminal) + boundary test before Task 12.** Not reachable with correctly-authored cases;
  latent mis-authoring bug.
- **M5** Private design facts are not consumed by scoring. scoring.py has no reference to
  `implicit_error`/`designed_failure`/`terminal_outcome`/`child_terminal_outcome`/revision/pressure/
  deadline audits; the only consumed private fact today is infra child_terminal→unscored (via the
  `infrastructure_failure` filter, correct). scored designed-terminal facts land in the DB but are
  unscored. **→ **Task 12 scoring wiring dependency** (not Task 9 correctness).**

**Low:**

- **L1** Dead code `state_snapshot_digest_for` (workspace_runtime.py:53-56) — no callers; actual
  mechanism uses `state_snapshot_digest`. → remove (Task 10/12 clean-up).
- **L2** `consume_declared_stimuli` docstring claims "fires at most once per child", but dedupe is by
  declared `event_id`, so multiple terminal events for the same child all fire; a schedule event with
  no `id` gets `event_id=""` and collides (215-220). → fix docstring / add dedupe by child_id
  (Task 10 authoring).
- **L3** `apply_child_terminal_outcome` hardcodes `{"type":"result_delivery","result":result_kind}`,
  `_contract_valid=True`, `controlled=False` and ignores any schedule `trigger`/`after_*`/`result_contract`
  semantics on the declaring event. → fold into Task 10 authoring contract decision.
- **L4** Empty defaults: a terminal declaration without `result`/`result_kind` yields `result_kind=""` that
  is delivered to the main model; empty `id` → `completion_id` defaults to `terminal:`. → Task 10
  authoring contract (require non-empty result_kind).
- **L5** Naming inconsistency: runner.py:287-289 abbreviates kernel lines `evaluator_designed_failure`→
  `designed_failure` / `evaluator_terminal_reason`→`terminal_reason`, unlike the rest of the `evaluator_*`
  prefix family. → cosmetic (Task 12).
- **L6** Test quality: several assertions mirror implementation internals / exact reason strings
  (`"evidence injected is truthy"`, `"straggler was not in flight"`, `"implicit_error_result schedule
  event"`), brittle to docstring/refactor; missing the M4 boundary case (designed terminal + subsequent
  real completion). → strengthen / add the M4 test in Task 10/12.

## Task 10 (swimlane 0a) — shared `stimulus_type` contract + remaining producer consumption (NOT committed)

Task 10 swimlane 0a unifies the scenario/schedule stimulus-kind field on
`stimulus_type` and wires schedule-declaration consumption of the remaining
stimulus producers. Stage A–E case migration and score_domain wiring (swimlane
0b) are out of scope. Decisions recorded here; committed source follows them.

- **Field unification (scenario vs runtime).** The scenario/schedule stimulus
  kind is now read exclusively from `stimulus_type` (never `type`, which stays
  reserved for runtime EventStore facts such as `child_completed` /
  `result_delivered` / `infrastructure_failure` / audit facts). Fixed reads:
  scheduler `consume_declared_stimuli`, `on_consumed` (completion_replay),
  `_implicit_error_truth`, `_delivery`, `_replay_delivery`, `_drain` by_result,
  the synthetic schedule event in `apply_child_terminal_outcome`, plus
  `event_taxonomy.scenario_event_type` and
  `scripts/audit_event_mechanisms._current_stimulus_types`. Full-suite sweep
  additionally caught the conformance kernel-invariant check
  (`conformance/suite._check_event_theme_expressibility`) authoring a synthetic
  schedule `completion_replay` row through `type`; flipped to `stimulus_type`
  (its DeliveryController consumption must see the row or the check fails).
  Untouched runtime `type` reads (child_started/artifact_committed/predicate
  `evidence_marker`/`revision_mismatch` schema fields; producer audit facts
  `resource_pressure`/`deadline_update`/`task_scope_revision`/`..._audits`;
  event_store/scoring/runner/observation/gateway) are NOT scenario-event reads.
  Legacy case-production tooling that still writes `type` on scenario rows
  (`scripts/materialize_swe_runtime_first5/_next`, and the `repair_first_10_*` /
  `rebuild_candidate_from_blueprint_v91` readers of old roots) is migration
  tooling: intentionally untouched by 0a, to be updated by stage A–E.
- **`scenario_event_type` fallback.** A declared `stimulus_type` that is not a
  frozen `stimulus_event_types` member is read as `result_delivery`. Three
  in-tree swe/tbn rows stamp the *theme* name `delayed_authoritative_result`
  (not a stimulus kind) and must keep their plain delivery semantics; cases are
  never migrated in 0a. Same fallback mirrored in the audit manifest reader.
- **Result-capable kinds.** `task_scope_revision` / `dependency_graph_revision`
  / `resource_pressure` / `child_timeout` / `child_crash` may carry a `result`
  role; `completion_replay` (replay_of_result) and `deadline_update` never
  declare a plain `result`. The 22 in-tree `task_scope_revision`+result and 5
  `resource_pressure`+result rows are delivery rows (authority gated by
  `after_artifacts`), unchanged from when they read as `result_delivery`.
- **Delivery-governed rows.** Scheduler `DELIVERY_ROW_KINDS` =
  {result_delivery, implicit_error_result, task_scope_revision,
  dependency_graph_revision, resource_pressure}: these rows, when they declare
  a result, govern a *real* completion's delivery in `_drain` by_result.
  Terminal kinds fabricate their own completion at the seam and never govern a
  real completion (avoids cross-wiring a child_timeout row onto a real result).
- **Consumption seam.** `consume_declared_stimuli` now dispatches the live
  (non-result) rows: child_timeout/child_crash fire on the named child's
  `child_started`; resource_pressure fires when its straggler starts (in-flight
  proof); task_scope_revision / dependency_graph_revision / deadline_update
  fire once at the first child boundary. Idempotent by declared `id`
  (`_fired_stimulus_event_ids`) — fixes L2 docstring (fires at most once,
  keyed by event id, not per child). result-bearing rows are ignored here.
- **Freeze of declared producer field names** (authoring contract for stage
  A–E): result / result_kind / payload / outcome_detail / completion_id /
  crash_source (child terminals); straggler_child_id / resource / limit /
  pool_remaining (resource_pressure); deadline_wall / reason (deadline_update);
  revision_id / new_scope / participant_visible_fields / expected_response
  (task_scope_revision); revision_id / new_edges / participant_visible_fields /
  expected_response (dependency_graph_revision); trigger / after_artifacts /
  after_results / replay_of_result (completion_replay).
- **`current_stimulus_type` now reflects reality.** The migration manifest
  reports the declared `stimulus_type` (e.g. swe/tbn rows surface
  `task_scope_revision` / `resource_pressure` instead of the old
  `result_delivery` default), which flips those instances'
  `migration_status` to `needs_stimulus_migration` — an honest, intended audit
  outcome (their tag is not in the frozen theme stimulus set) to be resolved by
  stage A–E. Migration tests assert theme counts / row shape only; no value
  assertions were changed.
- **Tests.** Scenario-row fixtures that declared `type: <stimulus>` flipped to
  `stimulus_type` (test_event_taxonomy, test_evaluation_method). New
  end-to-end (run_episode) tests assert each newly seam-wired producer records
  its kernel_private audit (resource_pressure / deadline_update /
  task_scope_revision / dependency_graph_revision) plus a controller-level
  idempotency/delivery-row-skip test. `implicit_error_result` and
  `completion_replay` presentation is re-pinned by the flipped fixtures.
- **Deferred (not 0a).** M4 double-delivery suppression guard, M1
  `_KERNEL_PRIVATE_TYPES` defense-in-depth, M2 `validate_gateway_event`
  pipeline wiring, M5 scoring consumption → Task 10/12 later swimlanes.

## Task 10 (swimlane 0a) 质量评审处置 — APPROVED_WITH_MINOR（2026-09-03；NOT committed）

Coordinator 评审对 0a 给出 APPROVED_WITH_MINOR。Medium #1 已按评审修复并随源码提交；其余条目记于此处并标注归属，供后续泳道/阶段接手。

- **Medium #1（已修，随源码提交）**：`consume_declared_stimuli` deadline_update 硬化。缺 `deadline_wall` 或非数值 `deadline_wall` 的行现都在 id 非空时先把 `event_id` 记入 `_fired_stimulus_event_ids`，再记一条 protocol_note 并 continue；不再以裸 `float()` 崩 episode，也不跨 child 边界无界重复刷 note。死分支（dispatch 尾 `elif event_type == "deadline_update"`）已移除（deadline_update 在其专用块内 `continue` 收敛）。`validate_scenario_events` 新增：live `deadline_update` 行必须携带数值型 `deadline_wall`（非空、可 `float`），否则报错。新增 3 条回归测试：缺 wall 不崩/单 note/不重放；畸形 wall（ISO 文本）不崩；taxonomy 数值校验通过/缺/畸形三态。

- **Medium #2（A–E 或 Task 12 前加固）**：stimulus kind 边界现于多处手写重复、无单一来源：`scheduler.DELIVERY_ROW_KINDS`、`consume_declared_stimuli` 内联 live 分派集、`taxonomy.RESULT_CAPABLE_EVENT_TYPES`、`audit_event_mechanisms` 内联 fallback。建议派生自 taxonomy 常量 + 不变式测试。**评审建议的「live 集与 DELIVERY_ROW_KINDS 无交叠」与 0a 实际设计不符，予以修正**：`resource_pressure` / `task_scope_revision` / `dependency_graph_revision` 是双性 kind（带 result 即交付行、不带 result 即 live 行），故两集合必然交叠。正确不变式是：(1) `DELIVERY_ROW_KINDS == STIMULUS_EVENT_TYPES − {completion_replay, deadline_update, child_timeout, child_crash}`；(2) live 分派集 == `STIMULUS_EVENT_TYPES − {result_delivery, implicit_error_result, completion_replay}`；(3) seam 消费谓词 == `kind in live 分派集 and not (kind in DELIVERY_ROW_KINDS and result is not None)`。加固时以 (1)–(3) 为准。

- **Medium #3（A–E 作者决策）**：live revision 契约与 validate revision gate 不对齐。`validate_scenario_events` 的 `REVISION_EVENT_TYPES` gate 要求 revision 行 invalidate/reopen 可观察状态，而 `apply_task_scope_revision`/`apply_dependency_graph_revision` 真正消费 `new_scope`/`new_edges`/`participant_visible_fields`/`expected_response`；0a seam 新增 live revision 测试行均不带 invalidates/reopens，若走 validate 必被拒。0a 维持现状（run_episode 不 validate；case 集 validate 中 revision 行都带 invalidates，无回归）。需明确「live revision 可观察变更 = scope/edge 快照 digest」，由 A–E 放开/改造 gate + 补 taxonomy 级测试。

- **Low #4（Task 12 前可选加固）**：`scenario_event_type` 兜底把「非空但未知」的 `stimulus_type` 吞成 `result_delivery`，与 legacy 无标签行不可区分（typo 静默降级）。建议对非空但未知标签加 lint/warn；`audit_event_mechanisms._current_stimulus_types` 内联 fallback（:104-105 一带）改 import 复用 `scenario_event_type`，消除第二处手写口径。

- **Low #5（Task 12 前可选加固）**：seam 空 `event_id` 缩并为 `""`；首个空 id live 行记 fired 后，其余空 id live 行会被 `if event_id in _fired_stimulus_event_ids` 误判已触发。deadline_update 畸形路径已按「id 非空才记 fired」处理，未含空 id 退化。建议空 id 行直接 note+skip（既不记 fired 也不触发）。

- **Low #6（文档/说明）**：`on_consumed` docstring 只讲 consumed 记账，未说明其驱动 `completion_replay`（trigger=after_consumed）；`DELIVERY_ROW_KINDS` 与 `RESULT_CAPABLE_EVENT_TYPES` 成员不同但语义同向（都排除 completion_replay/deadline_update）。建议交叉引用：DELIVERY_ROW_KINDS 是调度方「管辖真实 completion 交付」的收窄集；RESULT_CAPABLE 是 taxonomy 方「可带 result 角色」的更宽集；terminal 行（child_timeout/child_crash）seam 自造 completion 是有意差异。

- **设计债（A–E 迁移工具范围）**：`scripts/materialize_swe_runtime_first5.py:605-609`、`scripts/materialize_swe_runtime_next.py:750-754` 仍以 `type` 键写 resource_pressure/task_scope_revision；重跑会用新 reader 不读的 `type` 覆写 → live 行静默降级 / result-less 行 validate 报「result missing」。A–E 升级工具时须一并改 `stimulus_type`。

- **设计债（A–E 判类口径复核）**：manifest `current_stimulus_type` 判类把基础 `result_delivery` 计入 current_types 做 theme-subset 判断，导致 170 行中 31 行判类失真（真实标签已就位的 resource_pressure case 仍判 needs）。建议重推判类口径（区分 deliverability vs stimulus）后复核该 31 行。

## Task 10 conflicting_valid_results 泳道（2026-09-03；NOT committed）

6 case 迁移已完成并随源码提交（commit a927dc8）。仅语义/观测契约数据标注，未触碰共享引擎。记录如下债务，供 A–E / Task 12 接手：

- **git-conflict-and-cleanup-closure 与 scheduler-selective-replan 属 legacy v4**：原 control_flow_checks.json 无 `event_contracts`，CF 行不带 `event_id`。本次仅在 control registry 顶部**新建**单条 event_contract（绑 authority 场景事件 `gc_a_authority` / `sc_a_b2`）并补观测契约，但**未补** MAB(v7) 才有的完整 gateway 契约字段（`arrival_contract` / `authority_source` / `required_opportunities` / `main_visible_before_delivery`），两 case 仍无 event_policy.json / case_ir.json。后续升级为完整 v7 时须核对 authority_source（由 workstream_bindings 推导 result_03/result_05 归属）与 arrival 语义。
- **dynamic_point_plan.json 越界同步**：为通过 registry parity 审计（`ledger == control`），本次把 4 个 MAB case 的 dynamic_point_plan.json 覆写为 control_flow_checks.json 全等副本（含新增观测字段）。该文件不在泳道允许清单内，属强制镜像维护；后续 A–E 若重建该 ledger 勿回退观测字段。
- **case_ir.json / event_policy.json 未同步**：观测契约只写入 semantic_checks.json、control_flow_checks.json 与 4 个 MAB private_case.yaml（+ 镜像 ledger）；case_ir.json 的 `event_contract` 与 event_policy 仍无 required_changes 等观测字段。不在允许清单内，Task 12 消费端需以 control_flow_checks.json event_contracts 为准。
- **score_domain/event_id 为前瞻数据**：`parse_semantic_check_results` 目前不把 score_domain/event_id 拷贝进结果行，async_replanning 域与事件绑定尚未被运行时消费（Task 12 评分接线）。relevance_tier 按要求保留，但 `validate_scoring_domains`（0 调用方）会拒绝其存在——契约版本切换时须一次性移除。
- **legacy 两 case 的 forbidden_changes 为空**：authority 再推导下无「必须保持字节不变」的工件；supersede「只见权威」改由 closure_checks + required_changes/required_preservation 表达。4 个 MAB 用 `forbidden_changes: [provisional_checkpoint]`（防旧冲突被改写成权威）。
- **expected_disposition 为自拟 token**：无受控词表、引擎不读（opaque diagnostic）。如需枚举化由 Task 12 定义。

## Task 10 straggler_under_resource_pressure 泳道（2026-09-03；commit 174a5a9，本段 NOT committed）

10 case（5 mab-dependency-unblock / mab-late-constraint、4 swe-dependency-unblock / swe-late-constraint、1 tbn-late-test-evidence）已迁移并随源码提交，仅触碰 theme 内 case 的 4 类允许文件 + 新增测试，未动共享引擎。record 如下债务：

- **event_contract 观测字段为前瞻标注**：required_changes / required_preservation / forbidden_changes / closure_checks / expected_disposition / event_status 写入三处镜像（private_case.yaml 顶层 event_contracts、control_flow_checks.json、dynamic_point_plan.json）。`score_event_replanning` / async DRS 依赖这些字段存在才计分（`_contract_carries_scoring_fields`），但 presentation 侧无对照/引擎不读 expected_disposition——10 case 的 DRS 是否真正产生数值需 Task 12 评分接线验证。
- ~~**closure_checks 引用悬空**~~ **（已修复，2026-09-03 commit 9a0a811，本段仍 NOT committed）**：评审发现初稿把 `closure_checks` 写成目录横线名（`mab-dependency-unblock-0daa930906.closure`），`_closure_score` 按 id 精确 join 恒落空 → closure 分量被静默钉在 0.0（每条被评 episode 的事件 DRS process 分量约差 0.25）。修复：10 case 三处镜像的 `closure_checks` 均改写为语义 registry 中真实存在的下划线闭包 check id（`{case_id_with_underscores}.closure`，每 case 恰一个）；镜像互等与 ref 可解析由新增真 case 守卫测试覆盖（`_closure_score` 对真实 id 返 1.0、横线 id 对照组 0.0）。
- **deadline_update 为全局占位常量**：`deadline_wall=3600.0` + `reason=straggler_response_window_deadline` 统一写入 10 case，未按各 case 响应窗口语义推导真实绝对 wall。seam 只消费一次并记 kernel_private audit、主模型不可见（无 result 角色），故不影响可观察行为；case 作者后续应按真实窗口校准。
- **score_domain / event_id 为前瞻字段（承接 Task 8 F1 与 conflicting 泳道同款）**：`validate_scoring_domains` 0 调用方且会拒绝 relevance_tier，故未接入任何加载路径；`parse_semantic_check_results` 尚未把 score_domain 拷入结果行。每 check 恰一 score_domain 已按要求标注（base_task，或 async_replanning + 绑定 event_contract 的 event_id；relevance_tier 保留），但 Task 12 接线前不产生数值差异。
- **authority 行 resource_pressure 标签是双性交付行、非 live audit**：MAB 5 case 的 authority delivery 行补 `stimulus_type=resource_pressure`（+workstream_id/resource=concurrency_slot/limit=1，SWE/TBN 5 行原已带）。按 `_drain` by_result 管辖真实 authority completion 交付（沿用原 trigger，未加 intervention/observer）；run_episode 不会为该 delivery 产生 pressure_audit（delivery 行跳过 live seam）。「压力→triage」语义由观测契约表达，未落运行时 audit。若 A–E 想让 authority 压力真正产生可审计 pressure 事实，需另行加 live 行。
- **case_ir.json / event_policy.json 未同步**（与 conflicting 泳道同款、允许清单外）：case_ir 的 event_contract / event_policy 无观测字段；Task 12 消费端以 control_flow_checks.json event_contracts 为准。
- **registry 顶层版本未升**：semantic_checks.json version=4、control version=7 维持既有；只追加字段。契约版本切换时一次性重审（届时 validate_scoring_domains 会拒绝 relevance_tier，见 score_domain 条）。
- **迁移工具为一次性脚本**：留档于 `research/_lane10_*.py`（未提交、不含在 174a5a9），可按需删除或并入 A–E 工具集；`research/` 目录整体保持 untracked。

## Task 10 duplicate_or_replayed_completion 泳道（2026-09-03；commit 29d8480，本段 NOT committed）

4 case（mab-dependency-unblock-031ed6f5bc、mab-late-test-evidence-4c6c77884e / 60efb2bdee / 7d09ace3d3）已迁移并随源码提交，仅触碰 theme 内 case 的 4 类允许文件 + 新增测试 tests/test_migration_duplicate_theme.py，未动共享引擎。record 如下债务：

- **forbidden_changes 为空列表是 theme 语义、非疏漏**：completion replay 在同一 completion 下投递 *新* occurrence，旧 occurrence 不再重放；final_state 在窗口内合法变化，故无「必须字节不变的工件」可列。duplicate/replay 的 exact-once 由 closure_checks（`{case_id}.closure`，均已在 semantic registry 存在）断言，旧不被重新呈现由运行时 `replayed_schedule_events` 一次性门控。与 conflicting 泳道 `forbidden_changes: [provisional_checkpoint]` 不同——该 theme 无 old-vs-new 工件冲突。
- **事件契约观测字段为前瞻标注**：required_changes / required_preservation / forbidden_changes / closure_checks / expected_disposition(=ignore_duplicate) / event_status(=scored) 写入三处镜像（private_case.yaml 顶层 event_contracts、control_flow_checks.json、dynamic_point_plan.json byte-identical）。`score_event_replanning` 依赖这些字段存在才计分，但 replay occurrence 的数值接线（fresh delivery_occurrence_id join back、ignore_duplicate 处置）须 Task 12 完成。
- **case_ir.json / event_policy.json 未同步**（与 conflicting / straggler 泳道同款、允许清单外）：case_ir 的 event_contract 与 event_policy 无观测字段；Task 12 消费端以 control_flow_checks.json event_contracts 为准。
- **score_domain / event_id 为前瞻字段**：validate_scoring_domains 0 调用方且会拒绝 relevance_tier；parse_semantic_check_results 尚未把 score_domain 拷入结果行。每 check 恰一 score_domain 已标注（base_task 无 event_id；async_replanning 绑定 event_contract 的 event_id），relevance_tier 保留；Task 12 接线前不产生数值差异。

## Task 10 task_scope_or_dependency_change 泳道（2026-09-03；commit 1828c32 / 49a673b / 1fca3a3，本段 NOT committed）

38 case（21 mab、17 osw/swe/tbn）已迁移并随源码提交（mab 批 1828c32、osw/swe/tbn 批 49a673b、迁移一致性测试 1fca3a3），仅触碰 theme 内 case 的 4 类允许文件 + 新增 tests/test_migration_scope_theme.py，未动共享引擎。record 如下债务：

- **事件契约观测字段为前瞻标注**：required_changes / required_preservation / forbidden_changes / closure_checks / expected_disposition(=revise) / event_status(=scored) 写入三处镜像（private_case.yaml 顶层 event_contracts、control_flow_checks.json、dynamic_point_plan.json byte-identical）。`score_event_replanning` 依赖这些字段存在才计分；但 required_changes 一律取 `["final_state"]`（authority 交付即变更其字节语义），presentation 侧无独立对照 artifact；Task 12 需验证 38 case 的 DRS 是否真正产出数值。
- **closure_checks 引用悬空**（与 straggler 泳道同款）：`closure_checks: ["{case_id}.closure"]` 中 `.closure` 为语义/控制 registry 中**不存在**的占位 id（`validate_event_contracts` 不校验、registry_audit 也不比对）。评分/审计若按 id 寻 check 会落空；Task 12 需定义该 check 或把 closure_checks 当结构性约束处理。
- **revision 标签全为双性交付行、无 live 形态**：38 case 的 stimulus_type 都打在 result-bearing authority 行上（36 task_scope_revision + 2 dependency_graph_revision），按 `_drain` by_result 管辖交付，**不产生** revision_audit（delivery 行跳过 live seam）。theme 的 revision「change→re-plan」语义由观测契约表达，未落运行时 audit；测试只证明 live 形态（无 result 的 task_scope_revision 行）在 seam 上会被消费并记 kernel_private audit，但 38 case 数据里没有该形态。若 A–E 想让 revision 真正产生可审计 revision 事实，需在部分 case 另加 live 行。
- **case_ir.json / event_policy.json 未同步**（与 conflicting / straggler / duplicate 泳道同款、允许清单外）：case_ir 的 event_contract / event_policy 无观测字段；Task 12 消费端以 control_flow_checks.json event_contracts 为准。
- **score_domain / event_id 为前瞻字段**：validate_scoring_domains 0 调用方且会拒绝 relevance_tier；parse_semantic_check_results 尚未把 score_domain 拷入结果行。38 case 每 check 恰一 score_domain 已标注（base_task 无 event_id；async_replanning 绑定 event_contract 的 event_id；relevance_tier 保留；跨文件核对：每个 async_replanning check 均被某 control-flow check 的 outcome_anchor 引用），Task 12 接线前不产生数值差异。
- **dependency_graph_revision 仅 2 case（作者力所及的最小集）**：dependency 类只覆盖 mab-dependency-unblock-107bc4fe3f（versioned_maze_transition_added）与 mab-late-constraint-9636e9ce85（dependency_approval_sla_added）；其余 36 个语义上属 dependency 场景的 case 因 authority 事件已带 scope-revision 标签，本次未改判。若 A–E 复核 taxonomy 归因，需确认 36 个 scope 标签与真实场景是否一致。
- **gaia2-stockholm-moveout 为 legacy v4 未迁移**：theme 第 39 个注册 instance，control_flow_checks.json version=4、无 event_contracts/dynamic_point_plan，semantic v3 24 checks。不在允许清单可迁移形态内，本次完全未触碰（NEEDS_CONTEXT：需 v4→v7 完整升级或保留冻结）。
- **registry 顶层版本未升**：semantic_checks.json version=4、control version=7 维持既有；只追加字段。契约版本切换时一次性重审（届时 validate_scoring_domains 会拒绝 relevance_tier，见 score_domain 条）。
- **迁移工具为一次性脚本**：留档于 `%TEMP%/migrate_scope.py` 与 `%TEMP%/audit_scope.py`（未提交），可按需删除或并入 A–E 工具集。
