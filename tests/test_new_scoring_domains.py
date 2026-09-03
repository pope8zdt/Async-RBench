from __future__ import annotations

import pytest

from async_rbench.evaluation.scoring import (
    EventDRS,
    score_async_drs,
    score_base_task,
    score_event_replanning,
)
from async_rbench.evaluation.case_contract import validate_scoring_domains


def _check(
    point_id: str,
    *,
    domain: str | None = None,
    event_id: str | None = None,
    passed: bool = True,
    relevance_tier: str | None = None,
) -> dict:
    check: dict = {
        "id": point_id,
        "measurement_type": "semantic",
        "passed": passed,
    }
    if domain is not None:
        check["score_domain"] = domain
    if event_id is not None:
        check["event_id"] = event_id
    if relevance_tier is not None:
        check["relevance_tier"] = relevance_tier
    return check


# ---------------------------------------------------------------------------
# Semantic-domain validation.
# ---------------------------------------------------------------------------


def test_every_semantic_check_has_exactly_one_score_domain() -> None:
    # Valid: each check declares exactly one domain.
    assert validate_scoring_domains([
        _check("b1", domain="base_task"),
        _check("e1", domain="async_replanning", event_id="evt.a"),
    ]) == []

    # Invalid: absent domain.
    errors = validate_scoring_domains([
        _check("x1", domain=None),  # no score_domain key
    ])
    assert any("score_domain must be" in error for error in errors)

    # Invalid: unknown domain value.
    errors = validate_scoring_domains([
        _check("x2", domain="trajectory"),
    ])
    assert any("score_domain must be" in error for error in errors)


def test_async_replanning_requires_a_valid_event_id() -> None:
    errors = validate_scoring_domains([
        _check("e1", domain="async_replanning", event_id=""),  # empty
        _check("e2", domain="async_replanning", event_id=None),  # missing
    ])
    assert any("requires a non-empty event_id" in error for error in errors)

    # A base_task check is not required to bind an event.
    assert validate_scoring_domains([
        _check("b1", domain="base_task", event_id=None),
    ]) == []


def test_relevance_tier_is_tolerated_as_transitional() -> None:
    # relevance_tier is still the live weighting knob (weighting.py) and a
    # registry-audit/spec input; it is transitional, not part of the new
    # scoring-domain gate, so its presence must not fail validation.
    assert validate_scoring_domains([
        _check("b1", domain="base_task", relevance_tier="critical"),
    ]) == []


# ---------------------------------------------------------------------------
# Correct no-replan: stale rejection with unchanged state.
# ---------------------------------------------------------------------------

# A no-replan event (reject_stale) declares no required changes, so
# RequiredEffectCoverage is inapplicable.  Preservation + Forbidden + Closure
# remain the process denominator, and no state change is NOT a failure.
reject_stale_contract = {
    "event_id": "evt.late_authority",
    "expected_disposition": "reject_stale",
    "required_changes": [],
    "required_preservation": ["prior.baseline"],
    "forbidden_changes": ["saved_list"],
    "closure_checks": ["evt.late_authority.closure"],
}

S0 = {
    "prior.baseline": "unchanged-baseline-digest",
    "saved_list": "provisional-digest",
}

passed_async_checks = [
    _check("evt.late_authority.closure", domain="async_replanning", event_id="evt.late_authority", passed=True),
    _check("evt.late_authority.preserve", domain="async_replanning", event_id="evt.late_authority", passed=True),
]


def test_stale_result_correctly_preserves_state_for_full_process_score() -> None:
    score = score_event_replanning(
        contract=reject_stale_contract, before=S0, after=S0,
        semantic_results=passed_async_checks,
    )
    assert score.component_scores["preservation"] == 1.0
    assert score.component_scores["forbidden_effect_compliance"] == 1.0
    assert score.component_scores["closure"] == 1.0
    assert score.component_scores["required_effect_coverage"] is None
    assert score.process_score == 1.0
    assert score.async_outcome == 1.0
    assert score.total == 1.0


def test_no_state_change_is_not_a_failure_for_no_replan_disposition() -> None:
    # Even though before == after, a no-replan event that preserved prior work
    # and avoided forbidden effects must not be penalised.
    score = score_event_replanning(
        contract=reject_stale_contract, before=S0, after=S0,
        semantic_results=passed_async_checks,
    )
    assert score.process_score == 1.0
    assert score.total == 1.0


# ---------------------------------------------------------------------------
# Required revision with unchanged state must score zero RequiredEffectCoverage.
# ---------------------------------------------------------------------------

revise_contract = {
    "event_id": "evt.required_revision",
    "expected_disposition": "revise",
    "required_changes": ["affected.artifact"],
    "required_preservation": ["prior.baseline"],
    "forbidden_changes": ["unaffected.factor"],
    "closure_checks": ["evt.required_revision.closed"],
}

unchanged_revision_state = {
    "affected.artifact": "provisional-digest",
    "prior.baseline": "same-digest",
    "unaffected.factor": "same-digest",
}

passed_async_checks_revision = [
    _check("evt.required_revision.closed", domain="async_replanning", event_id="evt.required_revision", passed=True),
]


def test_required_revision_with_unchanged_state_gets_zero_effect_coverage() -> None:
    # before == after: every required_change was left at its provisional value.
    score = score_event_replanning(
        contract=revise_contract, before=unchanged_revision_state,
        after=unchanged_revision_state, semantic_results=passed_async_checks_revision,
    )
    assert score.component_scores["required_effect_coverage"] == 0.0
    assert score.component_scores["preservation"] == 1.0
    assert score.component_scores["forbidden_effect_compliance"] == 1.0
    assert score.component_scores["closure"] == 1.0
    # process = mean([0.0, 1.0, 1.0, 1.0]) = 0.75
    assert score.process_score == 0.75


def test_required_revision_with_unchanged_state_scores_below_full_even_when_base_tasks_pass() -> None:
    base_results = [
        _check("b1", domain="base_task", passed=True),
        _check("b2", domain="base_task", passed=True),
    ]
    assert score_base_task(base_results) == 1.0
    score = score_event_replanning(
        contract=revise_contract, before=unchanged_revision_state,
        after=unchanged_revision_state, semantic_results=passed_async_checks_revision,
    )
    assert score.process_score < 1.0
    assert score.total == pytest.approx(0.5 * 0.75 + 0.5 * 1.0)


# ---------------------------------------------------------------------------
# Component ratios and the 0.5/0.5 blend.
# ---------------------------------------------------------------------------

revision_after_state = {
    "affected.artifact": "authoritative-digest",
    "prior.baseline": "same-digest",
    "unaffected.factor": "same-digest",
}


def test_event_drs_is_half_process_half_async_outcome() -> None:
    # RequiredEffectCoverage = 1/1 changed; Preservation = 1/1; Forbidden = 1/1;
    # Closure = 1/1.  process = 1.0.  async_outcome = 1.0.
    score = score_event_replanning(
        contract=revise_contract, before=unchanged_revision_state,
        after=revision_after_state, semantic_results=passed_async_checks_revision,
    )
    assert score.component_scores["required_effect_coverage"] == 1.0
    assert score.process_score == 1.0
    assert score.async_outcome == 1.0
    assert score.total == 1.0


def test_component_ratios_track_partial_compliance() -> None:
    contract = {
        **revise_contract,
        "required_changes": ["a.affected", "b.affected"],
        "required_preservation": ["p1", "p2"],
        "forbidden_changes": ["f1", "f2"],
        "closure_checks": ["k1", "k2"],
    }
    before = {
        "a.affected": "old", "b.affected": "old",
        "p1": "same", "p2": "same",
        "f1": "same", "f2": "same",
    }
    after = {
        "a.affected": "new", "b.affected": "old",  # b not changed
        "p1": "same", "p2": "changed",  # p2 violated preservation
        "f1": "same", "f2": "changed",  # f2 violated forbidden
    }
    closure_results = [
        _check("k1", domain="async_replanning", event_id="evt.required_revision", passed=True),
        _check("k2", domain="async_replanning", event_id="evt.required_revision", passed=False),
    ]
    score = score_event_replanning(
        contract=contract, before=before, after=after, semantic_results=closure_results,
    )
    assert score.component_scores["required_effect_coverage"] == 0.5
    assert score.component_scores["preservation"] == 0.5
    assert score.component_scores["forbidden_effect_compliance"] == 0.5
    assert score.component_scores["closure"] == 0.5
    assert score.process_score == 0.5
    assert score.async_outcome == 0.5
    assert score.total == 0.5


# ---------------------------------------------------------------------------
# BTS consumes only base_task; async outcome consumes only event-bound checks.
# ---------------------------------------------------------------------------


def test_bts_consumes_only_base_task_domain() -> None:
    results = [
        _check("b1", domain="base_task", passed=True),
        _check("b2", domain="base_task", passed=False),
        _check("e1", domain="async_replanning", event_id="evt.x", passed=True),
    ]
    assert score_base_task(results) == 0.5


def test_async_outcome_ignores_other_events_and_base_task() -> None:
    results = [
        _check("evt.x.ok", domain="async_replanning", event_id="evt.x", passed=True),
        _check("evt.x.bad", domain="async_replanning", event_id="evt.x", passed=False),
        _check("evt.y.ok", domain="async_replanning", event_id="evt.y", passed=True),
        _check("b1", domain="base_task", passed=True),
    ]
    contract = {
        "event_id": "evt.x",
        "expected_disposition": "revise",
        "required_changes": ["a"],
        "required_preservation": ["p"],
        "forbidden_changes": ["f"],
        "closure_checks": ["evt.x.ok"],
    }
    score = score_event_replanning(
        contract=contract, before={"a": "old", "p": "s", "f": "s"},
        after={"a": "new", "p": "s", "f": "s"}, semantic_results=results,
    )
    # async_outcome is only the two evt.x checks -> 0.5.
    assert score.async_outcome == 0.5


def test_async_drs_aggregates_scored_events_ignoring_base_task_failure() -> None:
    base_results = [
        _check("b1", domain="base_task", passed=False),
        _check("b2", domain="base_task", passed=False),
    ]
    assert score_base_task(base_results) == 0.0

    # Final base-task failure must not erase a measurable event DRS.
    score = score_event_replanning(
        contract=reject_stale_contract, before=S0, after=S0,
        semantic_results=passed_async_checks,
    )
    assert score.total == 1.0
    assert score_async_drs([score]) == 1.0


def test_unreached_event_is_excluded_from_async_drs_not_scored_as_zero() -> None:
    # Pinned current semantics: when a contract carries scoring fields but the
    # event has no evaluator-observed boundary (the participant never reached
    # it), score_trace skips it, so it contributes NO EventDRS and is EXCLUDED
    # from the async_drs mean -- treated as unscored, never as a model-0.
    # Pending a final spec-owner ruling (unreached -> unscored vs 0).
    reached_a = EventDRS(process_score=1.0, async_outcome=1.0, component_scores={})
    reached_b = EventDRS(process_score=0.0, async_outcome=0.0, component_scores={})
    # The unreached event would have scored 0, but it contributed no entry.
    total = score_async_drs([reached_a, reached_b])
    assert total == 0.5  # not (1.0 + 0.0 + 0.0) / 3 = 1/3
    assert total == (reached_a.total + reached_b.total) / 2


# ---------------------------------------------------------------------------
# Eligibility / failure attribution.
# ---------------------------------------------------------------------------


def test_missing_provisional_within_full_pre_budget_scores_zero_drs() -> None:
    contract = {
        **revise_contract,
        "requires_provisional": True,
        "provisional_artifact": "affected.artifact",
    }
    # The evaluator observed a delivery gate but the participant never created
    # the required pre-event provisional state (before is None).
    score = score_event_replanning(
        contract=contract, before=None, after=revision_after_state,
        semantic_results=passed_async_checks_revision,
    )
    assert score.process_score == 0.0
    assert score.async_outcome == 0.0
    assert score.total == 0.0


def test_evaluator_unable_to_present_event_is_unscored_infrastructure() -> None:
    # An event the evaluator failed to deliver is an infrastructure/case failure,
    # not a model score: DRS is None and aggregation stays unscored.
    contract = {
        **reject_stale_contract,
        "event_status": "unscored_infrastructure",
    }
    score = score_event_replanning(
        contract=contract, before=S0, after=S0, semantic_results=passed_async_checks,
    )
    assert score.status == "unscored_infrastructure"
    assert score.total is None
    assert score_async_drs([score]) is None
