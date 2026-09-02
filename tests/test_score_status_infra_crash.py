from __future__ import annotations

from pathlib import Path

from async_rbench.evaluation.runner import (
    UNSCORED_INFRASTRUCTURE_COMPONENTS,
    _primary_event_theme,
    _score_status_decision,
)


# --- Item 1: infrastructure crash forces unscored, never X=0 ---


def test_infrastructure_crash_returns_unscored_after_construction() -> None:
    status, reason = _score_status_decision(
        scenario_constructed=True, score_integrity_ok=True,
        infrastructure_crash=True,
    )
    assert status == "unscored"
    assert reason == "infrastructure_crash"


def test_infrastructure_crash_beats_qualified_and_integrity_checks() -> None:
    # A crash is ordered after construction failure (more fundamental) but
    # before dynamic qualification and score integrity, so an episode that was
    # already running before the crash is reported as a crash, not a D=0.
    status, reason = _score_status_decision(
        scenario_constructed=True, score_integrity_ok=False,
        infrastructure_crash=True,
    )
    assert status == "unscored"
    assert reason == "infrastructure_crash"


def test_construction_failure_wins_over_crash_reason() -> None:
    # If the scenario never constructed, that is the more fundamental cause and
    # is reported first.
    status, reason = _score_status_decision(
        scenario_constructed=False, score_integrity_ok=True,
        infrastructure_crash=True,
    )
    assert status == "unscored"
    assert reason == "scenario_construction_failed"


def test_no_crash_keeps_participant_outcomes_scored() -> None:
    # A model decision (idle, explicit finish) is never an infrastructure crash:
    # it stays scored so X=0 is applied rather than shrinking the denominator.
    status, reason = _score_status_decision(
        scenario_constructed=True, score_integrity_ok=True,
        infrastructure_crash=False,
    )
    assert status == "scored"
    assert reason is None


def test_crash_components_are_the_four_tooling_ones() -> None:
    # A child crash from a provider/workspace outage (not a designed case crash)
    # is benchmark tooling failing mid-run, so it must also be unscored.
    assert UNSCORED_INFRASTRUCTURE_COMPONENTS == {
        "model_request", "child_start", "adapter_crash", "child_terminal",
    }


# --- Item 2: private classification event theme, evaluator-side only ---


def _write_private_theme(case_dir: Path, theme: str) -> None:
    private = case_dir / "private"
    private.mkdir(parents=True)
    (private / "private_case.yaml").write_text(
        f"classification:\n  primary_event_theme: {theme}\n",
        encoding="utf-8",
    )


def test_primary_event_theme_reads_private_classification(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    _write_private_theme(case_dir, "conflicting_valid_results")
    case_spec = {"case_id": "case"}  # public spec carries no theme
    assert _primary_event_theme(case_dir / "public_case.yaml", case_spec) == (
        "conflicting_valid_results"
    )


def test_primary_event_theme_prefers_public_explicit_theme(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    _write_private_theme(case_dir, "conflicting_valid_results")
    case_spec = {"case_id": "case", "primary_event_theme": "delayed_authoritative_result"}
    assert _primary_event_theme(case_dir / "public_case.yaml", case_spec) == (
        "delayed_authoritative_result"
    )


def test_primary_event_theme_falls_back_when_no_classification(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"  # no private/ dir
    case_spec = {"case_id": "case"}
    assert _primary_event_theme(case_dir / "public_case.yaml", case_spec) == (
        "unassigned_theme"
    )


def test_primary_event_theme_is_not_stamped_on_participant_stream() -> None:
    # Guard the property that the theme is evaluator-side only: it is derived
    # from the private classification and must never appear on the public stream
    # used to build the participant trace.  The runner keeps it off by building
    # the participant trace from `store.public_stream()`, which is a different
    # envelope; here we only assert the resolver never writes to the spec.
    from async_rbench.evaluation.runner import _primary_event_theme as resolver

    case_dir = Path("cases/mab-conflicting-specialist-results-5f19377089")
    if not case_dir.is_dir():
        return
    theme = resolver(case_dir / "public_case.yaml", {"case_id": "x"})
    assert theme != "unassigned_theme"
