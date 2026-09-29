from __future__ import annotations

from pathlib import Path

import pytest

from async_rbench.evaluation.runner import EpisodeConfig, _track_a_eligibility


@pytest.mark.parametrize("split", ["calibration", "development", "test"])
def test_all_registered_splits_are_eligible_for_the_200_task_paper_run(
    tmp_path: Path, split: str,
) -> None:
    config = EpisodeConfig(
        episode_id=f"case-{split}-async-0",
        case_id=f"case-{split}",
        execution_mode="async",
        guidance="incentive",
        agent_seed=2026,
        adapter_command=["adapter"],
        output_dir=tmp_path,
        official_track=True,
        adapter_profile="reference_scaffold_api",
        runtime_mode="api_only",
        conformance_passed=True,
        resource_policy_sha256="frozen-policy",
        use_container=True,
        split=split,
        model="paper-model",
    )
    eligible, reasons = _track_a_eligibility(
        config,
        {
            "backend": "openai_compatible",
            "workspace_mode": "container_clone",
            "resolved_model": "paper-model",
        },
    )
    assert eligible is True
    assert reasons == []


def test_unknown_split_remains_ineligible(tmp_path: Path) -> None:
    config = EpisodeConfig(
        episode_id="case-unassigned-async-0",
        case_id="case-unassigned",
        execution_mode="async",
        guidance="incentive",
        agent_seed=2026,
        adapter_command=["adapter"],
        output_dir=tmp_path,
        official_track=True,
        adapter_profile="reference_scaffold_api",
        runtime_mode="api_only",
        conformance_passed=True,
        resource_policy_sha256="frozen-policy",
        use_container=True,
        split="unassigned",
        model="paper-model",
    )
    eligible, reasons = _track_a_eligibility(
        config,
        {
            "backend": "openai_compatible",
            "workspace_mode": "container_clone",
            "resolved_model": "paper-model",
        },
    )
    assert eligible is False
    assert reasons == ["split_not_registered"]
