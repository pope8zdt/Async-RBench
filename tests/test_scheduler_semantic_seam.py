from __future__ import annotations

"""Regression tests for the scheduler semantic seam (bug [K]).

Three legacy swe cases stamp their delayed-authority schedule rows with a
THEME id (``delayed_authoritative_result``) instead of a stimulus kind
(``result_delivery``).  ``event_taxonomy.scenario_event_type`` normalises such
tags back to ``result_delivery``; every scheduler seam that classifies a
schedule row by ``stimulus_type`` must route them through that normaliser.
Before the fix, ``DeliveryController._drain.by_result`` read the raw tag, never
found the row, and bound ``benchmark_event_id=None`` — so scoring deemed the
designed authority event "not reached" even when the model adopted it.
"""

from async_rbench.evaluation.event_taxonomy import (
    STIMULUS_EVENT_TYPES,
    scenario_event_type,
)
from async_rbench.evaluation.scheduler import DELIVERY_ROW_KINDS, DeliveryController

# The theme id stamped by the swe legacy cases in place of the stimulus kind.
THEME_TAG = "delayed_authoritative_result"


def _authority_completion(*, completion_id: str = "authority-1") -> dict:
    return {
        "type": "child_completed", "child_id": "c1",
        "completion_id": completion_id, "result_kind": "result_04",
        "payload": {"result": "authority"},
    }


def test_theme_tagged_delivery_row_reaches_drain_and_binds_event_id() -> None:
    """Bug [K] core: a theme-tagged row is found by _drain.by_result.

    The produced delivery event must carry the schedule row's own id as
    ``benchmark_event_id``; a raw-tag read misses the row and binds ``None``.
    """
    case = {
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "evt.provisional.workstream_01", "result": "result_01"},
                {"id": "evt.delayed_authority", "stimulus_type": THEME_TAG,
                 "result": "result_04"},
            ]},
        },
    }
    controller = DeliveryController("async", case)
    controller.spawned = {"c1": {}, "c2": {}}
    delivery = controller.on_complete(_authority_completion())[0]
    assert delivery["type"] == "result_delivered"
    assert delivery["completion_id"] == "authority-1"
    assert delivery["result_kind"] == "result_04"
    assert delivery["benchmark_event_id"] == "evt.delayed_authority"


def test_theme_tagged_delivery_row_is_skipped_by_the_live_consumer() -> None:
    """No double-fire: the live seam never consumes a theme-tagged delivery row.

    The row declares a result role, so it is a delivery row governed by the
    drain path alone: ``consume_declared_stimuli`` must produce nothing, record
    no terminal outcome / audit, and leave the row deliverable afterwards.
    """
    case = {
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "evt.delayed_authority", "stimulus_type": THEME_TAG,
                 "result": "result_04"},
            ]},
        },
    }
    controller = DeliveryController("async", case, min_initial_children=0)
    controller.on_child_started({"type": "child_started", "child_id": "c1"})
    assert controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "c1",
    }) == []
    assert controller.terminal_outcomes == []
    assert controller.pressure_audits == []
    assert controller.revision_audits == []
    # The row is still a delivery row and binds its event id on the drain path.
    delivery = controller.on_complete(_authority_completion())[0]
    assert delivery["benchmark_event_id"] == "evt.delayed_authority"
    # Later child boundaries stay silent: the row never fires live.
    controller.on_child_started({"type": "child_started", "child_id": "c2"})
    assert controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "c2",
    }) == []


def test_frozen_kind_rows_keep_live_and_delivery_split() -> None:
    """Normalisation leaves frozen kinds untouched (spot-check task_scope_revision).

    A ``task_scope_revision`` row without a result role still fires live at the
    first child boundary; a result-bearing ``task_scope_revision`` row is still
    a delivery row — skipped by the live consumer, delivered by the drain path
    under its own event id.
    """
    case = {
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "scope-live", "stimulus_type": "task_scope_revision",
                 "revision_id": "r-live", "new_scope": {"phase": "frozen"},
                 "participant_visible_fields": {"scope": "frozen"}},
                {"id": "scope-authority", "stimulus_type": "task_scope_revision",
                 "result": "result_04", "invalidates_artifacts": ["final"]},
            ]},
        },
    }
    controller = DeliveryController("async", case, min_initial_children=0)
    controller.on_child_started({"type": "child_started", "child_id": "c1"})
    assert controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "c1",
    }) == []
    assert [a["revision_id"] for a in controller.revision_audits] == ["r-live"]
    # The result-bearing revision row stays untouched by the live seam...
    assert controller.consume_declared_stimuli({
        "type": "child_started", "child_id": "c2",
    }) == []
    assert [a["revision_id"] for a in controller.revision_audits] == ["r-live"]
    # ...and is delivered by the drain path under its own event id.
    delivery = controller.on_complete(_authority_completion())[0]
    assert delivery["benchmark_event_id"] == "scope-authority"


def test_replay_original_event_find_normalises_theme_tagged_source() -> None:
    """_replay_delivery joins a replay back to a theme-tagged source row.

    The original-event finder must recognise the theme-tagged authority row as
    the ``result_delivery`` it schedules; a raw-tag read falls back to an empty
    event and silently drops the row's declared stale marker.
    """
    case = {
        "authoritative_result_kind": "result_04",
        "superseded_result_kind": "result_01",
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "evt.delayed_authority", "stimulus_type": THEME_TAG,
                 "result": "result_04", "stale": True},
                {"id": "evt.replay", "stimulus_type": "completion_replay",
                 "replay_of_result": "result_04", "trigger": "after_consumed"},
            ]},
        },
    }
    controller = DeliveryController("async", case, min_initial_children=0)
    original = controller.on_complete(_authority_completion())[0]
    replay = controller.on_consumed({"completion_id": "authority-1"})[0]
    assert replay["replayed"] is True
    assert replay["replay_of_completion_id"] == "authority-1"
    assert replay["replay_of_occurrence_id"] == original["delivery_occurrence_id"]
    # The stale marker comes from the found original row (theme-tagged here);
    # the pre-fix empty-event fallback would evaluate stale as False.
    assert replay["stale"] is True
    assert replay["evaluator_stale"] is True


def test_theme_tagged_held_delivery_releases_on_artifact_bound() -> None:
    """Trigger gating survives normalisation: the swe authority is held.

    The swe cases chain their theme-tagged authority on
    ``after_artifacts_committed`` (see tests/test_migration_delayed_theme_b.py).
    The row must not degrade to an immediate delivery when its theme tag is
    normalised: it is held until the declared artifacts are committed, then
    released under the row's own event id.
    """
    case = {
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "evt.delayed_authority", "stimulus_type": THEME_TAG,
                 "result": "result_04", "trigger": "after_artifacts_committed",
                 "after_artifacts": ["provisional_checkpoint",
                                     "preserved_source_facts"]},
            ]},
        },
    }
    controller = DeliveryController("async", case, min_initial_children=0)
    # Held: no result_delivered until the artifact boundary is met.
    assert controller.on_complete(_authority_completion()) == []
    assert controller.on_observation({
        "type": "artifact_committed", "artifact_id": "provisional_checkpoint",
    }) == []
    deliveries = controller.on_observation({
        "type": "artifact_committed", "artifact_id": "preserved_source_facts",
    })
    assert len(deliveries) == 1
    assert deliveries[0]["type"] == "result_delivered"
    assert deliveries[0]["completion_id"] == "authority-1"
    assert deliveries[0]["benchmark_event_id"] == "evt.delayed_authority"


def test_scenario_event_type_is_identity_for_frozen_kinds() -> None:
    """The normaliser is the identity function on the nine frozen kinds.

    Only theme ids (and other unknown tags) fall back to ``result_delivery``;
    the frozen stimulus kinds must round-trip unchanged so no seam changes
    behaviour for them.
    """
    frozen_kinds = [
        "result_delivery", "completion_replay", "child_timeout", "child_crash",
        "implicit_error_result", "task_scope_revision",
        "dependency_graph_revision", "resource_pressure", "deadline_update",
    ]
    for kind in frozen_kinds:
        assert scenario_event_type({"stimulus_type": kind}) == kind, kind
        # An empty row (no tag) is a plain scheduled delivery.
    assert scenario_event_type({}) == "result_delivery"
    for theme_or_unknown in [
        "delayed_authoritative_result", "swe_dependency_unblock",
        "late_or_out_of_order_superseded_result", "not_a_stimulus_kind",
    ]:
        assert scenario_event_type({"stimulus_type": theme_or_unknown}) == (
            "result_delivery"
        ), theme_or_unknown


def test_delivery_row_kinds_subset_of_stimulus_types() -> None:
    """Every DELIVERY_ROW_KINDS member is a frozen stimulus_event_types member.

    This is the contract that keeps ``scenario_event_type`` an identity on the
    kinds the drain seam recognises: if a new delivery kind were added to
    ``DELIVERY_ROW_KINDS`` without also entering the taxonomy, rows of that
    kind would silently normalise to ``result_delivery`` instead.
    """
    assert set(DELIVERY_ROW_KINDS) <= set(STIMULUS_EVENT_TYPES)
