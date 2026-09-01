from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = (
    "gaia2-stockholm-moveout",
    "scheduler-selective-replan",
    "git-conflict-and-cleanup-closure",
    "swe-bench-selective-patch",
)

FORBIDDEN_PARTICIPANT_GUIDANCE = (
    "must be replanned",
    "must not be needlessly rewritten",
    "wait, accept or reject deliveries",
    "re-delegate the cleanup",
    "if it reports closed=false",
    "superseded fix revision is stale",
    "do not report completion",
    "recovery must not be inferred",
    "after every module group has passed against the same",
    "keep the result of every run that fails",
    "after the fix is integrated",
)


def _participant_text(case_id: str) -> str:
    case_dir = ROOT / "candidate_cases" / case_id
    if not case_dir.is_dir():
        case_dir = ROOT / "cases" / case_id
    case = yaml.safe_load((case_dir / "public_case.yaml").read_text(encoding="utf-8"))
    task = yaml.safe_load((case_dir / "task" / "task.yaml").read_text(encoding="utf-8"))
    wave_text = "\n".join(
        f"{item.get('task', '')}\n{item.get('expected_output', '')}"
        for item in case.get("workstreams", [])
    )
    public_scripts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((case_dir / "task" / "task_file").rglob("*.py"))
    )
    return f"{task['instruction']}\n{wave_text}\n{public_scripts}".lower()


def test_candidate_visible_surfaces_do_not_prescribe_scored_control_policy() -> None:
    for case_id in CANDIDATES:
        text = _participant_text(case_id)
        hits = [phrase for phrase in FORBIDDEN_PARTICIPANT_GUIDANCE if phrase in text]
        assert not hits, f"{case_id} leaks target control guidance: {hits}"


def test_global_guidance_does_not_request_or_teach_the_initial_strategy() -> None:
    text = "\n".join(
        [
            (ROOT / "async_rbench" / "evaluation" / "guidance.py").read_text(encoding="utf-8"),
            (ROOT / "async_rbench" / "profiles" / "reference_scaffold_api" / "runtime.py").read_text(
                encoding="utf-8"
            ),
        ]
    ).lower()
    for phrase in (
        "request an initial wave",
        "use an initial wave of at least",
        "do not adopt it solely because it arrived last",
        "for example after a late authoritative result",
    ):
        assert phrase not in text
