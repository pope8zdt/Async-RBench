from pathlib import Path

from async_rbench.evaluation.runner import EpisodeConfig, _case_contract_path


def test_candidate_case_override_does_not_require_registry_entry(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    contract = candidate / "public_case.yaml"
    contract.write_text("case_id: example\n", encoding="utf-8")
    assert _case_contract_path(
        tmp_path, "unregistered", "pilot-1", candidate,
    ) == contract.resolve()


def test_official_episode_default_has_no_candidate_override(tmp_path: Path) -> None:
    config = EpisodeConfig(
        episode_id="episode", case_id="case", execution_mode="linear",
        guidance="none", agent_seed=1, adapter_command=["adapter"],
        output_dir=tmp_path,
    )
    assert config.case_dir_override is None
