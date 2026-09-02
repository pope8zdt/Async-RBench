"""Narrow e2e probes for Task 10 lane: child_failure_or_implicit_error.

The theme's three frozen ``stimulus_type`` values are
``child_timeout`` / ``child_crash`` / ``implicit_error_result``.  The
controller unit surface is already exercised in
``test_evaluation_method``; these probes drive the same mechanism
through ``run_episode`` so the delivery the participant would observe,
the kernel-private evaluator fact, and the private classifier audit all
land in the trace for the exact authoring shape this lane stamps onto
its migrated cases:

* ``child_crash`` with ``crash_source: case_designed`` is a scored,
  model-visible terminal delivery (the public row shows
  ``terminal_outcome`` but never the designed/infrastructure truth).
* ``child_crash`` with a provider ``crash_source`` is an unscored
  ``infrastructure_failure`` audit with no delivery at all.
* ``implicit_error_result`` is a result-bearing delivery row: the
  authority completion is delivered and the kernel fact records
  ``implicit_error`` truth that is never participant-visible.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml

import test_evaluation_method as tem
from async_rbench.spec import discover_cases, load_case, validate_case

ROOT = Path(__file__).resolve().parents[1]
SCORE_DOMAINS = frozenset({"base_task", "async_replanning"})
OBSERVATION_FIELDS = (
    "required_changes",
    "required_preservation",
    "forbidden_changes",
    "closure_checks",
    "expected_disposition",
    "event_status",
)
EXPECTED_DISPOSITION = "classify_implicit_failure_and_recover"
EXPECTED_CHILD_FAILURE_DIRS = frozenset({
    "mab-dependency-unblock-09f3ab60d7",
    "mab-dependency-unblock-0de81e81ac",
    "mab-dependency-unblock-2cf6576816",
    "mab-dependency-unblock-720c69400a",
    "mab-dependency-unblock-940b9b95f0",
    "mab-dependency-unblock-94c68e7815",
})


def _child_failure_cases() -> list[Path]:
    cases = []
    for case in discover_cases(ROOT):
        private = yaml.safe_load(
            (case.case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        theme = ((private.get("classification") or {}).get("primary_event_theme") or "")
        if theme == "child_failure_or_implicit_error":
            cases.append(case.case_dir)
    return sorted(cases)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _valid_adapter_events(*, with_completion: bool) -> list[dict]:
    """Protocol-valid adapter script driving one authority child.

    ``participant_metadata.config_sha256`` and ``child_spawned.parent_id`` are
    required by ``validate_adapter_event``; omitting them drops the spawn before
    ``run_episode`` can bind the child to its workstream, which would make the
    probes exercise a degenerate path instead of the real delivery flow.
    """
    events = [
        {"type": "participant_metadata", "backend": "scripted_test",
         "main_model": "scripted-main", "child_model": "scripted-child",
         "workspace_mode": "container_clone",
         "config_sha256": "0123456789abcdef0123456789abcdef"},
        {"type": "ready"},
        {"type": "child_spawned", "child_id": "c1", "parent_id": "main",
         "work_units": ["authority"]},
        {"type": "child_started", "child_id": "c1"},
    ]
    if with_completion:
        events.append({"type": "child_completed", "child_id": "c1",
                       "completion_id": "comp-c1",
                       "payload": {"statuses": {"macao": {"status": "pass"}},
                                   "percentage": 100}})
    events.append({"type": "episode_ended", "final_answer": "done",
                   "local_status": "completed", "declared_task_success": True})
    return events


def test_run_episode_designed_child_crash_is_model_visible_and_scored(
    tmp_path, monkeypatch,
) -> None:
    """(a) crash_source=case_designed yields a scored terminal delivery."""
    case = tem._write_live_case(tmp_path, events=[
        {"id": "crash-designed", "stimulus_type": "child_crash",
         "child_id": "c1", "result": "authority",
         "payload": {"result": "partial"},
         "crash_source": "case_designed", "outcome_detail": "designed crash"},
    ])
    tem._patch_live_adapter(monkeypatch, _valid_adapter_events(with_completion=False))
    config = tem._live_episode_config(tmp_path, case, "probe-crash-designed")
    asyncio.run(tem.runner_module.run_episode(tem.ROOT, config))
    rows = tem._trace_rows(tmp_path)

    terminal = [
        r for r in rows
        if r.get("type") == "result_delivered" and r.get("terminal_outcome") == "crash"
    ]
    assert terminal, "designed crash was never delivered"
    assert terminal[0]["child_id"] == "c1"
    assert terminal[0]["completion_id"] == "terminal:crash-designed"
    # The public projection hides the designed/infrastructure classification.
    assert all("evaluator_designed_failure" not in row for row in terminal)
    # The kernel fact carries the designed truth and the classifier audit proves
    # the child was genuinely in flight when the crash fired.
    fact = [
        r for r in rows if r.get("type") == "result_delivery_evaluator_fact"
        and r.get("completion_id") == "terminal:crash-designed"
    ]
    assert fact and fact[0]["designed_failure"] is True
    assert fact[0]["terminal_outcome"] == "crash"
    audit = [r for r in rows if r.get("type") == "child_terminal_outcome"]
    assert audit and audit[0]["was_in_flight"] is True and audit[0]["designed"] is True


def test_run_episode_infrastructure_child_crash_is_unscored_and_never_delivered(
    tmp_path, monkeypatch,
) -> None:
    """(b) a provider crash_source is an unscored infra failure, no delivery."""
    case = tem._write_live_case(tmp_path, events=[
        {"id": "crash-infra", "stimulus_type": "child_crash",
         "child_id": "c1", "result": "authority",
         "payload": {"result": "partial"},
         "crash_source": "provider_outage", "outcome_detail": "provider outage"},
    ])
    tem._patch_live_adapter(monkeypatch, _valid_adapter_events(with_completion=False))
    config = tem._live_episode_config(tmp_path, case, "probe-crash-infra")
    asyncio.run(tem.runner_module.run_episode(tem.ROOT, config))
    rows = tem._trace_rows(tmp_path)

    assert not any(
        r.get("type") == "result_delivered" and r.get("terminal_outcome") == "crash"
        for r in rows
    ), "an infrastructure crash must never be delivered to the model"
    assert not any(
        r.get("type") == "result_delivery_evaluator_fact"
        and r.get("terminal_outcome") == "crash"
        for r in rows
    )
    infra = [r for r in rows if r.get("type") == "infrastructure_failure"]
    assert infra, "infrastructure crash was never audited"
    assert infra[0]["component"] == "child_terminal"
    assert infra[0]["outcome"] == "crash"
    assert infra[0]["child_id"] == "c1"
    assert infra[0]["visibility"] == "kernel_private"


def test_run_episode_implicit_error_result_is_truthful_but_kernel_private(
    tmp_path, monkeypatch,
) -> None:
    """(c) implicit_error_result stamps evaluator truth, hides it publicly."""
    case = tem._write_live_case(tmp_path, events=[
        {"id": "implicit-auth", "stimulus_type": "implicit_error_result",
         "result": "authority", "payload": {"result": "authoritative"}},
    ])
    tem._patch_live_adapter(monkeypatch, _valid_adapter_events(with_completion=True))
    config = tem._live_episode_config(tmp_path, case, "probe-implicit")
    asyncio.run(tem.runner_module.run_episode(tem.ROOT, config))
    rows = tem._trace_rows(tmp_path)

    facts = [
        r for r in rows
        if r.get("type") == "result_delivery_evaluator_fact"
        and r.get("benchmark_event_id") == "implicit-auth"
    ]
    assert facts, "implicit_error_result delivery fact never reached the trace"
    assert facts[0]["implicit_error"] is True
    assert facts[0]["implicit_error_measurable"] is True
    assert facts[0]["implicit_error_reason"] == "implicit_error_result schedule event"
    assert facts[0]["terminal_outcome"] is None
    # The public delivery row the model sees carries the payload but never the
    # evaluator's implicit-failure classification.
    public = [
        r for r in rows if r.get("type") == "result_delivered"
    ]
    assert public, "the implicit-error authority result was never delivered"
    assert all("implicit_error" not in r for r in public)


# ---------------------------------------------------------------------------
# Migration data guards over the six registered child_failure cases
# ---------------------------------------------------------------------------


def test_lane_targets_the_six_registered_child_failure_cases() -> None:
    target_dirs = {case_dir.name for case_dir in _child_failure_cases()}
    assert target_dirs == EXPECTED_CHILD_FAILURE_DIRS


def test_every_child_failure_case_stamps_focal_authority_delivery_implicit_error() -> None:
    """The case's scored event (the event_contract event_id) is the authoritative
    result-bearing delivery row and carries ``stimulus_type: implicit_error_result``.

    The two sibling terminal kinds (``child_timeout`` / ``child_crash``) require a
    ``child_id``-bearing live row that applies a designed terminal to a running
    child; none of the six cases declares one -- their schedules deliver the
    authority's structurally-valid result (which the participant must classify as
    an implicit failure and recover), so ``implicit_error_result`` is the only
    theme stimulus consistent with the declared runtime shape.
    """
    for case_dir in _child_failure_cases():
        private = yaml.safe_load(
            (case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        authoritative = str(private.get("authoritative_result_kind") or "")
        contracts = control.get("event_contracts") or []
        assert contracts, case_dir.name
        focal_id = str(contracts[0]["event_id"])
        events = (private.get("scenarios") or {}).get("async", {}).get("events") or []
        focal = [e for e in events if str(e.get("id") or "") == focal_id]
        assert len(focal) == 1, (case_dir.name, "focal event must be unique")
        assert str(focal[0].get("result") or "") == authoritative, (
            case_dir.name, "the scored event must be the authoritative result",
        )
        assert focal[0].get("stimulus_type") == "implicit_error_result", (
            case_dir.name, focal_id,
        )
        # The un-stamped rows are only the plain upstream/baseline deliveries that
        # precede the scored event; every remaining async row stays a plain result
        # delivery and is never mis-tagged with a terminal/terminal-payload kind.
        untagged = [
            e for e in events if e.get("stimulus_type") is None
        ]
        assert untagged, case_dir.name
        assert all(str(e.get("result") or "") != authoritative for e in untagged), (
            case_dir.name, "authoritative delivery must be the tagged focal row",
        )
        # The whole composed case still passes ordinary contract validation.
        spec = load_case(case_dir / "public_case.yaml")
        assert not validate_case(spec), (case_dir.name, validate_case(spec))


def test_every_child_failure_case_check_has_exactly_one_scoring_domain() -> None:
    for case_dir in _child_failure_cases():
        semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        contract_event_ids = {
            str(contract.get("event_id"))
            for contract in (control.get("event_contracts") or [])
            if contract.get("event_id")
        }
        assert contract_event_ids, case_dir.name
        async_domains = []
        for check in semantic["checks"]:
            check_id = str(check["id"])
            domain = check.get("score_domain")
            assert domain in SCORE_DOMAINS, (case_dir.name, check_id, domain)
            # relevance_tier is deliberately retained in the migrated file.
            assert "relevance_tier" in check, (case_dir.name, check_id)
            if domain == "async_replanning":
                async_domains.append(check)
                event_id = str(check.get("event_id") or "")
                assert event_id in contract_event_ids, (
                    case_dir.name, check_id, event_id, contract_event_ids,
                )
            elif check.get("event_id") is not None:
                raise AssertionError((case_dir.name, check_id, "base_task carried event_id"))
        # The child_failure shape: the event_integration/closure gates sit on the
        # async dimension, the five source-* checks stay on the base task.
        assert len(async_domains) == 3, (case_dir.name, len(async_domains))
        assert len(semantic["checks"]) == len(async_domains) + 5, case_dir.name
        for check in async_domains:
            assert check.get("category") in {"event_integration", "closure"}, (
                case_dir.name, check["id"],
            )


def test_every_child_failure_case_event_contract_carries_observation_fields() -> None:
    for case_dir in _child_failure_cases():
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        contracts = control.get("event_contracts") or []
        assert contracts, case_dir.name
        for contract in contracts:
            missing = [field for field in OBSERVATION_FIELDS if field not in contract]
            assert not missing, (case_dir.name, contract.get("event_id"), missing)
            assert isinstance(contract.get("required_changes"), list)
            assert isinstance(contract.get("required_preservation"), list)
            assert isinstance(contract.get("forbidden_changes"), list)
            assert contract.get("closure_checks"), (case_dir.name, contract.get("event_id"))
            assert str(contract.get("expected_disposition") or "") == EXPECTED_DISPOSITION, (
                case_dir.name, contract.get("event_id"),
            )
            assert contract.get("event_status") == "scored", (case_dir.name, contract.get("event_id"))
            # The closure semantic id must exist in the case's semantic registry so
            # the async-DRS closure component can resolve it (by exact id).
            semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
            semantic_ids = {str(check["id"]) for check in semantic["checks"]}
            assert set(contract.get("closure_checks")) <= semantic_ids, (
                case_dir.name, contract.get("event_id"),
            )
        # The private design ledger mirrors the evaluator registry byte-for-byte.
        ledger_path = case_dir / "private" / "dynamic_point_plan.json"
        assert ledger_path.exists(), case_dir.name
        assert _load(ledger_path) == control, case_dir.name
        # The authored private event contract mirrors the evaluator registry too.
        private = yaml.safe_load(
            (case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        assert (private.get("event_contracts") or []) == contracts, case_dir.name
