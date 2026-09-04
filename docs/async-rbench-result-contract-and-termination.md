# Async-RBench — Result Contract and Termination Semantics

One child attempt is decomposed along three orthogonal axes:

1. **Run-termination reason** — *why* the attempt ended (`termination.py`), including
   whether it ended in a submission at all.
2. **Public submission-contract verdict** — whether the sealed submission satisfied the
   participant-visible accept rule the Gateway enforces (`public_result_validation.py`).
3. **Main-agent consumption decision** — whether the main agent later used a delivered
   result (`consumed_by_main`); this never changes the terminal class.

The runtime is built so that only a *public* contract can produce `result_rejected`;
every spawned child resolves to exactly one terminal class once its episode closes; and
the paper metrics read those classifications, never re-derived guesses from mixed states.
This document states the boundary, lifecycle, audit gates, and v11.0.0 metric
denominators.

---

## 1. Public submission contract vs private semantic validation

### 1.1 Two surfaces, one shared validator

Each workstream carries a **public result contract** and an optional **private validator**,
distinguished by `validator_stage`:

| Stage | Kind | Role |
|---|---|---|
| `submission_contract` | Gateway-gating | The sealed submission must pass the *participant-visible* accept rule. Failure → `result_rejected`. |
| `semantic_evidence` | Evaluator fact | Hidden semantic check (`evaluate_private_semantics`) that may affect score/audit but **never** gates delivery. Failure → a recorded private code, no `result_rejected`. |

`public_result_contract.kind` is one of:

- `payload_only` — the transport/payload-shape checks below are the whole accept rule.
- `report_file` — additionally, the submission must point at one report artifact
  (`required_files[0]`) and that artifact must satisfy the declared accept rule:
  `must_exist`, `must_be_valid_json`, and `fields_equal_evidence` (fields in the JSON that
  must equal the participant-visible evidence fields).

The evaluator-private `validator_command` is **rendered from the public rule**
(`report_contract.render_validator_command`), not hand-authored: there is no
model-invisible structural constraint. A hand-typed command that diverges from the public
rule is a conformance violation rejected by the contract audit (Section 3).

Child self-check (`validate_result`), Child `submit_result`, and the Gateway all route
through one implementation (`validate_public_submission` in
`public_result_validation.py`), so the same payload and workspace state yield identical
public reason codes at every layer. The Gateway validator prints
`ASYNC_RBENCH_CONTRACT_FAIL:<code>` (one code per line); `report_contract.classify_validator_output`
maps output back to the granular report-file codes.

### 1.2 Public rejection codes

`case_contract.PUBLIC_RESULT_REJECTION_CODES` — the only codes that may appear in a
`result_rejected`:

- **Payload shape:** `payload_not_object`, `evidence_not_object`,
  `missing_required_evidence`, `files_not_string_list`, `duplicate_files`,
  `unexpected_files`, `missing_required_files`.
- **Report-file artifact:** `report_path_not_required_file`, `report_file_missing`,
  `report_json_invalid`, `report_missing_required_field`, `report_payload_field_mismatch`,
  `reported_file_contract_failed`.

Each maps to the participant-visible **contract part** the model must repair
(`contract_part_for_codes`): `report_file` / `evidence` / `payload` / `reported_files` /
`submission` (fallback). A `result_rejected` carrying **no** public code is a
gateway/case-contract failure — a private-only rejection reaching the scorer classifies as
`case_contract_failure` (never a model verdict), and the audit hard-fails it
(Section 3).

Private codes such as `semantic_validator_failed`, evaluator-designed
failures, revision/pressure/deadline facts, and the evaluator reason/validator output are
recorded as kernel-private scoring facts; they are not participant-visible and never
cause a rejection.

---

## 2. Child lifecycle and terminal classification

`termination.classify_child_terminals(events)` returns exactly **one row per spawned
child**, deterministic by event order, reading only child-level events (Linear and Async
record them identically). Classes are exhaustive and mutually exclusive.

### 2.1 Text lifecycle diagram

```
child_spawned                       attempt N for workstream W
   │
   ├── infrastructure_failure(component=case_contract)   ─▶ case_contract_failure
   ├── infrastructure_failure(other component)           ─▶ infrastructure_failure
   ├── child_cancelled(initiated_by=infrastructure)      ─▶ infrastructure_failure
   │
   ├── result_delivered(terminal_outcome=timeout)        ─▶ timeout
   ├── result_delivered(terminal_outcome=crash)          ─▶ crash
   ├── child_cancelled(initiated_by=main)                ─▶ cancel
   │
   ├── child_step_limit_reached      (no submission)     ─▶ step_limit_reached
   ├── child_resource_safety_abort   (no submission)     ─▶ resource_safety_abort
   ├── child_no_submission           (no submission)     ─▶ no_submission
   │
   ├── result_rejected  with ≥1 public code              ─▶ public_rejection
   ├── result_rejected  with private codes only          ─▶ case_contract_failure
   │
   ├── result_delivered  (accepted, no terminal_outcome) ─▶ gateway_accepted
   ├── child_completed   (no gateway verdict before      ─▶ sealed_pending_verdict
   │                      episode close)
   └── still queued/running at episode_ended             ─▶ in_flight
```

### 2.2 Precedence and facets

Precedence per attempt (higher wins):

1. `case_contract_failure` / `infrastructure_failure`
2. designed terminal (`timeout` / `crash`)
3. explicit main cancellation (`cancel`)
4. step-limit/safety-abort/no-submission terminal event
5. public `result_rejected` (`public_rejection`); private-only ⇒ `case_contract_failure`
6. `result_delivered` ⇒ `gateway_accepted`
7. `child_completed` without a verdict ⇒ `sealed_pending_verdict`
8. otherwise ⇒ `in_flight`

Each row carries facets beyond `terminal_class`:

- `attempt_number` / `retry` — spawn order within the workstream (a retry is attempt ≥ 2).
- `sealed_submission` — the attempt physically sealed a submission
  (`gateway_accepted` / `public_rejection` / `sealed_pending_verdict`).
- `gateway_verdict` — the Gateway reached accept/reject on the sealed submission
  (`gateway_accepted` / `public_rejection` only).
- `consumed_by_main` — the main agent later consumed the delivered result (joined by
  completion id); never changes the class.
- `tokens` — child-side model-call tokens for the attempt.
- `reason_codes` / `public_codes` / `contract_part` — rejection detail.
- `terminal_outcome` / `detail` — designed-terminal and failure detail.

Contract acceptance is the **Gateway verdict**, not the main agent's later use:
`result_delivered` means the Gateway accepted and released the submission, so the attempt
is `gateway_accepted` whether or not the main agent consumed it. A sealed submission that
reached no verdict before the episode closed is `sealed_pending_verdict` and never enters a
verdict acceptance/rejection denominator.

### 2.3 Exactly-one-terminal integrity

Every spawned child must reach exactly one concrete terminal once its episode closes.
`in_flight` after close, and a private-only rejection (`case_contract_failure` row with
`reason_codes` and no `public_codes`), are mechanism defects, not model submission
verdicts; both are reported and, on official records, hard-fail the run (Section 3).
Runner shutdown cancels stragglers with `initiated_by="scaffold_shutdown"`; the audit only
flags `in_flight` rows in episodes that actually closed (`episode_ended` present), so a
crash-abandoned artifact is not misclassified as a live mechanism defect.

---

## 3. Official-run gates consuming the taxonomy

Two consumers turn these integrity facts into non-zero exits / hard-fails. Development
runs are always reported (counts + ids) but only *official* records
(`leaderboard_eligible is True` and `score_policy_version == SCORE_POLICY_VERSION`) append
a hard-fail reason.

| Reason | `audit_run` trigger | `aggregate_reports` trigger |
|---|---|---|
| `contract_fixture_failure` | contract fixtures did not pass | (aggregate relies on audit of the run root) |
| `hidden_submission_constraint` | fixtures still hide a submission-stage validator with no public contract | — |
| `private_submission_rejection` | any episode has a private-only rejection row | any **official** record has one |
| `unknown_child_terminal` | any *closed* episode has an `in_flight` row | any **official** record has one |
| `official_linear_zero_main_tokens` | an official Linear episode recorded zero/None main tokens | an official Linear record recorded zero main tokens |

`audit-run` (`eval_cli.cmd_audit_run`) exits 1 (and prints the reasons to stderr) when the
report's `hard_fail` is set; `cmd_aggregate` exits 1 when `report["audit"]["hard_fail"]`.
Each report carries the per-episode lists under `child_terminal_integrity` (audit) and the
aggregate audit keys `private_submission_rejection_count/_episode_ids` and
`unknown_child_terminal_count/_episode_ids`.

---

## 4. Paper metrics — numerators and denominators

`aggregate._paper_metrics(records)` computes per-mode and all-modes-descriptive metrics
from the scorer-stamped `child_terminal_classifications`. Paper-facing claims must read
the mode-specific subgroup of `paper_metrics_by_mode`; the all-modes rollup is explicitly
descriptive only. Counts have no denominator; rates list their denominator explicitly.

### 4.1 Counts (denominator n/a)

| Metric | Counts |
|---|---|
| `terminal_class_counts` | per-`terminal_class` histogram over all attempts (12 keys, incl. `in_flight`) |
| `sealed_submission_count` | attempts with `sealed_submission` facet true |
| `gateway_verdict_count` | attempts with `gateway_verdict` facet true |
| `gateway_accepted_count` | `gateway_accepted` rows |
| `public_rejected_count` | `public_rejection` rows |
| `sealed_pending_verdict_count` | `sealed_pending_verdict` rows |
| `first_attempt_verdict_count` / `first_attempt_accepted_count` | verdict/accepted rows on attempt 1 |
| `retry_verdict_count` / `retry_accepted_count` | verdict/accepted rows on attempt ≥ 2 |
| `extra_child_tokens_from_public_rejections` | per-episode tokens on public-rejected attempts (per workstream, attempts before the accepted one, or all when none accepted) |
| `redelegation_attempt_count` | attempts with `retry` true |
| `invalid_redelegation_count` | per-record `invalid_redelegation_count` |
| `step_limit_attempts` / `resource_safety_abort_attempts` / `no_submission_attempts` | rows in each non-submission class |

### 4.2 Rates

| Metric | Numerator | Denominator |
|---|---|---|
| `submission_acceptance_rate` | `gateway_accepted` | `gateway_verdict` (verdict-bearing submissions only) |
| `submission_rejection_rate` | `public_rejected` | `gateway_verdict` |
| `first_attempt_acceptance_rate` | `first_attempt_accepted` | `first_attempt_verdict` |
| `retry_acceptance_rate` | `retry_accepted` | `retry_verdict` |
| `child_step_limit_rate_per_attempt` | `step_limit_attempts` | `total_attempts` (all rows) |
| `resource_safety_abort_rate_per_attempt` | `resource_safety_abort_attempts` | `total_attempts` |
| `no_submission_rate_per_attempt` | `no_submission_attempts` | `total_attempts` |
| `avg_child_tokens_per_gateway_accepted` | child tokens summed over `gateway_accepted` rows | `gateway_accepted` |
| `invalid_redelegation_rate` | `invalid_redelegation_count` | `redelegation_attempt_count` |

**Non-overlapping denominators.** Verdict acceptance/rejection rates run over
verdict-bearing submissions only. `sealed_pending_verdict`, step/safety/no-submission
ends, designed terminals, cancels, case-contract failures, infrastructure failures, and
in-flight closes never enter a verdict denominator. The three per-attempt outcome rates
run over *all* attempts and are therefore disjoint from the verdict rates.

---

## 5. Interpretation guidance

- **`submission_acceptance_rate` / `submission_rejection_rate` are Gateway verdict rates**:
  among submissions on which the Gateway reached accept/reject, what fraction were
  accepted/rejected. A run with many non-submission exits and few verdicts will show a *low
  verdict count*, not a high rejection rate.
- **Step-limit, emergency-safety-abort, and no-submission are model/runtime outcome
  rates over attempts — they are *not* rejection rates and never describe a submission.**
  `child_step_limit_rate_per_attempt`, `resource_safety_abort_rate_per_attempt`, and
  `no_submission_rate_per_attempt` share `total_attempts` as denominator. A step-limit
  exit is an ordinary scored model outcome. A safety abort is an abnormal protection
  event that makes the episode unscored; it is not evidence that a submission failed.
- **`sealed_pending_verdict` measures submissions whose verdict the episode never reached**;
  it is a runtime-completeness signal (gateway didn't settle before close), not a model
  outcome.
- **`extra_child_tokens_from_public_rejections` is rejection cost, not acceptance cost**;
  read it together with `avg_child_tokens_per_gateway_accepted` when judging whether
  public feedback loops are spending tokens.
- **Acceptance ≠ consumption.** A high acceptance rate does not imply the main agent used
  every delivered result; use the `consumed_by_main` facet for the orchestration/use view.

---
