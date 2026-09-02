"""Migration guards for the ``duplicate_or_replayed_completion`` swimlane (Task 10).

The lane migrates the four cases whose ``primary_event_theme`` is
``duplicate_or_replayed_completion`` to the new event contract:

* every semantic check is tagged with exactly one ``score_domain``
  (``base_task`` | ``async_replanning``); an ``async_replanning`` check binds the
  theme's authoritative scenario event id, while ``relevance_tier`` is retained.
* every async schedule now declares a ``completion_replay`` stimulus row
  (``stimulus_type: completion_replay``) whose ``replay_of_result`` is the case's
  authoritative result kind and whose trigger is ``after_consumed``; the row never
  declares ``result`` and always has a scheduled source result to replay.
* the control-flow registry's ``event_contracts`` observation contract expresses
  the duplicate/replay resolution (the replayed completion is a *new* gateway
  occurrence under the same completion id, consumed exactly once, old effects
  preserved, no duplicate side effects) via ``required_changes`` /
  ``required_preservation`` / ``forbidden_changes`` / ``closure_checks`` /
  ``expected_disposition`` / ``event_status``.

The runtime half drives the DeliveryController and ``run_episode`` and asserts
the theme semantics the migrated data describes: a consumed completion produces
one replayed delivery (a fresh ``delivery_occurrence_id`` under the same
``completion_id``, ``replayed=True``), the old occurrence is never re-presented,
and a second consumption fires nothing.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml

import test_evaluation_method as tem
from async_rbench.evaluation.scheduler import DeliveryController
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

EXPECTED_DUPLICATE_DIRS = frozenset({
    "mab-dependency-unblock-031ed6f5bc",
    "mab-late-test-evidence-4c6c77884e",
    "mab-late-test-evidence-60efb2bdee",
    "mab-late-test-evidence-7d09ace3d3",
})


def _duplicate_cases() -> list[Path]:
    cases = []
    for case in discover_cases(ROOT):
        private = yaml.safe_load(
            (case.case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        theme = ((private.get("classification") or {}).get("primary_event_theme") or "")
        if theme == "duplicate_or_replayed_completion":
            cases.append(case.case_dir)
    return sorted(cases)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _completion(completion_id: str, result_kind: str, payload: dict) -> dict:
    return {
        "type": "child_completed",
        "child_id": "c1",
        "completion_id": completion_id,
        "result_kind": result_kind,
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Migration data guards
# ---------------------------------------------------------------------------


def test_lane_targets_the_four_registered_duplicate_cases() -> None:
    target_dirs = {case_dir.name for case_dir in _duplicate_cases()}
    assert target_dirs == EXPECTED_DUPLICATE_DIRS


def test_every_duplicate_case_schedules_completion_replay_for_authoritative_kind() -> None:
    for case_dir in _duplicate_cases():
        private = yaml.safe_load(
            (case_dir / "private" / "private_case.yaml").read_text(encoding="utf-8")
        )
        authoritative = str(private.get("authoritative_result_kind") or "")
        allowed = set((private.get("result_contract") or {}).get("allowed_result_kinds") or [])
        events = (private.get("scenarios") or {}).get("async", {}).get("events") or []
        delivered_results = {
            str(event.get("result"))
            for event in events
            if event.get("result") is not None
        }
        replays = [
            event for event in events
            if str(event.get("stimulus_type") or "") == "completion_replay"
        ]
        assert replays, (case_dir.name, "no completion_replay stimulus declared")
        assert len({str(event.get("id")) for event in replays}) == len(replays)
        for replay in replays:
            replay_id = str(replay.get("id") or "")
            replay_of = str(replay.get("replay_of_result") or "")
            assert replay_of == authoritative, (case_dir.name, replay_id, replay_of)
            assert replay_of in allowed, (case_dir.name, replay_id, replay_of)
            assert replay_of in delivered_results, (
                case_dir.name, replay_id, "replay has no scheduled source result",
            )
            assert str(replay.get("trigger") or "") == "after_consumed", (
                case_dir.name, replay_id,
            )
            assert "result" not in replay, (case_dir.name, replay_id, "replay must not carry result")
        # The whole composed case still passes ordinary contract validation.
        spec = load_case(case_dir / "public_case.yaml")
        assert not validate_case(spec), (case_dir.name, validate_case(spec))


def test_every_duplicate_case_check_has_exactly_one_scoring_domain() -> None:
    for case_dir in _duplicate_cases():
        semantic = _load(case_dir / "task" / "tests" / "semantic_checks.json")
        control = _load(case_dir / "task" / "tests" / "control_flow_checks.json")
        contract_event_ids = {
            str(contract.get("event_id"))
            for contract in (control.get("event_contracts") or [])
            if contract.get("event_id")
        }
        assert contract_event_ids, case_dir.name
        for check in semantic["checks"]:
            check_id = str(check["id"])
            domain = check.get("score_domain")
            assert domain in SCORE_DOMAINS, (case_dir.name, check_id, domain)
            # relevance_tier is deliberately retained in the migrated file.
            assert "relevance_tier" in check, (case_dir.name, check_id)
            if domain == "async_replanning":
                event_id = str(check.get("event_id") or "")
                assert event_id in contract_event_ids, (
                    case_dir.name, check_id, event_id, contract_event_ids,
                )
            elif check.get("event_id") is not None:
                raise AssertionError((case_dir.name, check_id, "base_task carried event_id"))


def test_every_duplicate_case_event_contract_carries_observation_fields() -> None:
    for case_dir in _duplicate_cases():
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
            # A replayed completion is ignored once applied (no net-new effect),
            # never re-applied as if it were a fresh event.
            assert str(contract.get("expected_disposition") or "") == "ignore_duplicate", (
                case_dir.name, contract.get("event_id"),
            )
            assert contract.get("event_status") == "scored", (case_dir.name, contract.get("event_id"))
        # The private design ledger (where present) mirrors the evaluator registry.
        ledger_path = case_dir / "private" / "dynamic_point_plan.json"
        if ledger_path.exists():
            assert _load(ledger_path) == control, case_dir.name


# ---------------------------------------------------------------------------
# Runtime theme semantics (completion replay at the DeliveryController)
# ---------------------------------------------------------------------------


def _base_case(events: list[dict]) -> dict:
    return {
        "authoritative_result_kind": "authority",
        "result_contract": {"allowed_result_kinds": ["authority"]},
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": events},
        },
    }


def test_replayed_completion_is_one_new_occurrence_fired_after_consumption() -> None:
    """Consuming an authority completion fires exactly one replay.

    The replay is a fresh gateway occurrence under the same completion id
    (never a clone of the original child completion), records which occurrence it
    replays, and never re-presents the original delivery.
    """
    controller = DeliveryController("async", _base_case(events=[
        {"id": "auth", "result": "authority"},
        {"id": "replay", "stimulus_type": "completion_replay",
         "replay_of_result": "authority", "trigger": "after_consumed"},
    ]))
    controller.spawned = {"c1": {}, "c2": {}}
    original = controller.on_complete(
        _completion("p1", "authority", {"revision": "v2"})
    )
    assert len(original) == 1
    assert original[0]["type"] == "result_delivered"
    assert original[0]["delivery_occurrence_id"].startswith("gateway-occ-")

    replay = controller.on_consumed({"completion_id": "p1"})
    assert len(replay) == 1
    message = replay[0]
    assert message["type"] == "result_delivered"
    assert message["replayed"] is True
    # Same completion, new occurrence (spec §3.3): the occurrence id is what
    # distinguishes one delivery of the same completion from another.
    assert message["completion_id"] == original[0]["completion_id"] == "p1"
    assert message["replay_of_completion_id"] == "p1"
    assert message["delivery_occurrence_id"] != original[0]["delivery_occurrence_id"]
    assert message["replay_of_occurrence_id"] == original[0]["delivery_occurrence_id"]
    assert message["payload_sha256"] == original[0]["payload_sha256"]
    # A replay never re-invalidates/reopens anything and is not stale.
    assert message["invalidates_artifacts"] == []
    assert message["reopens_milestones"] == []
    assert message["stale"] is False

    # The old occurrence is never re-presented: a second consumption fires nothing
    # and the original delivery stays a single occurrence.
    assert controller.on_consumed({"completion_id": "p1"}) == []
    assert len([d for d in controller.delivery_order if d == "p1"]) == 1


def test_replay_fires_once_even_when_completion_consumed_repeatedly() -> None:
    """The replay schedule event is consumed at most once per accepted completion."""
    controller = DeliveryController("async", _base_case(events=[
        {"id": "auth", "result": "authority"},
        {"id": "replay", "stimulus_type": "completion_replay",
         "replay_of_result": "authority", "trigger": "after_consumed"},
    ]))
    controller.spawned = {"c1": {}, "c2": {}}
    controller.on_complete(_completion("p1", "authority", {"revision": "v2"}))
    first = controller.on_consumed({"completion_id": "p1"})
    second = controller.on_consumed({"completion_id": "p1"})
    third = controller.on_consumed({"completion_id": "p1"})
    assert len(first) == 1
    assert second == []
    assert third == []
    assert list(controller.replayed_schedule_events) == ["replay"]


# ---------------------------------------------------------------------------
# Runtime theme semantics end-to-end through run_episode
# ---------------------------------------------------------------------------


def _replay_completed_events() -> list[dict]:
    """Adapter script that spawns two authority children, completes one, consumes
    it twice, and ends.

    The async delivery gate only opens once at least two children have been
    spawned, so a second child (never completed) is required for the authority
    completion to be delivered while the episode is live.
    """
    # ``participant_metadata.config_sha256`` and ``child_spawned.parent_id`` are
    # required by ``validate_adapter_event``; omitting them drops the spawns before
    # ``run_episode`` binds each child to its workstream, which would otherwise make
    # the authority completion contract-invalid and undeliverable (no result_kind).
    return [
        {"type": "participant_metadata", "backend": "scripted_test",
         "main_model": "scripted-main", "child_model": "scripted-child",
         "workspace_mode": "container_clone",
         "config_sha256": "0123456789abcdef0123456789abcdef"},
        {"type": "ready"},
        {"type": "child_spawned", "child_id": "c1", "parent_id": "main",
         "work_units": ["authority"]},
        {"type": "child_spawned", "child_id": "c2", "parent_id": "main",
         "work_units": ["authority"]},
        {"type": "child_started", "child_id": "c1"},
        {"type": "child_started", "child_id": "c2"},
        {"type": "child_completed", "child_id": "c1", "completion_id": "comp-c1",
         "payload": {"rows": 3}},
        {"type": "result_consumed", "completion_id": "comp-c1", "action_id": "accept"},
        {"type": "result_consumed", "completion_id": "comp-c1", "action_id": "accept-again"},
        {"type": "episode_ended", "final_answer": "done",
         "local_status": "completed", "declared_task_success": True},
    ]


def test_run_episode_completion_replay_delivers_fresh_occurrence_once(
    tmp_path: Path, monkeypatch,
) -> None:
    """run_episode turns the declared completion_replay into one new occurrence.

    The replayed delivery is recorded as a kernel-visible evaluator fact
    (``replayed`` / fresh ``delivery_occurrence_id``) and reaches the adapter as a
    second ``result_delivered`` of the *same* completion id, while the original
    occurrence is delivered exactly once and a repeated consumption fires nothing.
    """
    case = tem._write_live_case(tmp_path, events=[
        {"id": "auth", "result": "authority"},
        {"id": "replay", "stimulus_type": "completion_replay",
         "replay_of_result": "authority", "trigger": "after_consumed"},
    ])
    tem._patch_live_adapter(monkeypatch, _replay_completed_events())
    config = tem._live_episode_config(tmp_path, case, "probe-completion-replay")
    asyncio.run(tem.runner_module.run_episode(tem.ROOT, config))
    rows = tem._trace_rows(tmp_path)

    facts = [
        r for r in rows
        if r.get("type") == "result_delivery_evaluator_fact"
        and r.get("completion_id") == "comp-c1"
    ]
    originals = [r for r in facts if not r.get("replayed")]
    replays = [r for r in facts if r.get("replayed")]
    assert len(originals) == 1, "original completion must be delivered exactly once"
    assert len(replays) == 1, "completion_replay must fire exactly once"
    assert replays[0]["delivery_occurrence_id"] != originals[0]["delivery_occurrence_id"]
    assert replays[0]["replay_of_occurrence_id"] == originals[0]["delivery_occurrence_id"]
    assert replays[0]["replay_of_completion_id"] == "comp-c1"
    assert replays[0]["benchmark_event_id"] == "replay"
    assert replays[0]["result_kind"] == originals[0]["result_kind"] == "authority"

    # The fresh occurrence also reaches the participant as a second public
    # delivery of the same completion id; the old occurrence is not re-presented.
    public = [r for r in rows if r.get("type") == "result_delivered"]
    assert {d["completion_id"] for d in public} == {"comp-c1"}
    assert len(public) == 2
