from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from async_rbench.evaluation.runner import EpisodeConfig, run_episode
from async_rbench.profiles import (
    AdapterProfile,
    BUILTIN_PROFILES,
    PROFILE_TYPES,
    load_profile,
)
from async_rbench.profiles.reference_scaffold_api.config import ScaffoldConfig


ROOT = Path(__file__).resolve().parents[1]

# runtime_mode -> (profile name, extra adapter argv)
RUNTIME_MODE_SMOKE = {
    "api_only": ("reference_scaffold_api", ["--backend", "scripted_test", "--workspace-mode", "disabled"]),
    "native_agent": ("native_agent", ["--workspace-mode", "disabled"]),
    "minimal": ("minimal_api", ["--workspace-mode", "disabled"]),
    "conformance": ("conformance_mock", ["--workspace-mode", "disabled"]),
}


def test_all_four_profile_types_are_registered():
    assert set(BUILTIN_PROFILES) == set(PROFILE_TYPES)


def test_all_builtin_profiles_load_and_validate():
    for name in PROFILE_TYPES:
        profile = load_profile(name)
        assert profile.profile == name
        assert profile.validate() == []


def test_reference_scaffold_api_is_the_formal_evaluation_profile():
    profile = load_profile("reference_scaffold_api")
    assert profile.runtime_mode == "api_only"
    assert profile.workspace_mode == "container_clone"
    assert profile.child_isolation == "container_clone"


def test_conformance_mock_is_a_development_profile():
    profile = load_profile("conformance_mock")
    assert profile.runtime_mode == "conformance"
    assert profile.workspace_mode == "disabled"


def test_from_dict_ignores_unknown_keys():
    profile = AdapterProfile.from_dict({
        "profile": "minimal_api",
        "runtime_mode": "minimal",
        "not_a_real_field": True,
    })
    assert profile.profile == "minimal_api"
    assert profile.validate() == []


def test_load_profile_from_yaml_path(tmp_path: Path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        "profile: native_agent\nruntime_mode: native_agent\n",
        encoding="utf-8",
    )
    profile = load_profile(path)
    assert profile.profile == "native_agent"
    assert profile.validate() == []


def test_unknown_profile_raises():
    with pytest.raises(ValueError):
        load_profile("does_not_exist")


def test_scaffold_config_migrates_legacy_single_provider_to_dual_roles() -> None:
    config = ScaffoldConfig(
        backend="openai_compatible",
        api_url="https://shared.example/v1/chat/completions",
        api_key_env="SHARED_KEY",
        main_model="main-x",
        child_model="child-y",
        child_pool_id="pool-7",
    )
    main = config.provider_role_config("main")
    child = config.provider_role_config("child")
    assert main.role == "main"
    assert child.role == "child"
    assert main.model == "main-x"
    assert child.model == "child-y"
    assert main.child_pool_id == child.child_pool_id == "pool-7"
    # Legacy top-level fields are the migration fallback for every role.
    assert main.backend == child.backend == "openai_compatible"
    assert main.api_url == child.api_url == "https://shared.example/v1/chat/completions"
    assert main.api_key_env == child.api_key_env == "SHARED_KEY"


def test_scaffold_config_nested_provider_overrides_are_role_scoped() -> None:
    config = ScaffoldConfig(
        backend="openai_compatible",
        api_url="https://shared.example/v1/chat/completions",
        api_key_env="SHARED_KEY",
        main_model="main-x",
        child_model="child-y",
        child_pool_id="pool-7",
        main_provider={
            "backend": "codex_cli",
            "api_url": "https://main.example/v1/chat/completions",
            "api_key_env": "MAIN_KEY",
        },
        child_provider={"max_api_concurrency": 2},
    )
    main = config.provider_role_config("main")
    child = config.provider_role_config("child")
    # main role adopts the nested main_provider backend/url/env override.
    assert main.backend == "codex_cli"
    assert main.api_url == "https://main.example/v1/chat/completions"
    assert main.api_key_env == "MAIN_KEY"
    # child role keeps the legacy fallback except for its own override.
    assert child.backend == "openai_compatible"
    assert child.api_url == "https://shared.example/v1/chat/completions"
    assert child.max_api_concurrency == 2


def test_scaffold_config_public_metadata_stamps_child_pool_and_provider_identity() -> None:
    config = ScaffoldConfig(
        backend="openai_compatible",
        main_model="main-x",
        child_model="child-y",
        child_pool_id="pool-7",
    )
    metadata = config.public_metadata()
    assert metadata["child_pool_id"] == "pool-7"
    assert metadata["main_provider"]["model"] == "main-x"
    assert metadata["child_provider"]["model"] == "child-y"
    assert metadata["main_provider"]["backend"] == "openai_compatible"
    assert metadata["child_provider"]["backend"] == "openai_compatible"
    assert len(metadata["config_sha256"]) == 64


@pytest.mark.parametrize("runtime_mode", list(RUNTIME_MODE_SMOKE))
def test_runtime_modes_run_no_container(runtime_mode: str, tmp_path: Path):
    profile_name, extra_argv = RUNTIME_MODE_SMOKE[runtime_mode]
    adapter_path = ROOT / "adapters" / f"{profile_name}.py"
    adapter_command = [sys.executable, str(adapter_path), *extra_argv]
    episode_id = f"smoke-{runtime_mode}"
    config = EpisodeConfig(
        episode_id=episode_id,
        case_id="secure-release",
        execution_mode="linear",
        guidance="incentive",
        agent_seed=1,
        adapter_command=adapter_command,
        output_dir=tmp_path / episode_id,
        use_container=False,
        timeout_sec=120,
        runtime_mode=runtime_mode,
        adapter_profile=profile_name,
    )
    score = asyncio.run(run_episode(ROOT, config))
    assert score["episode_id"] == episode_id
    assert score["runtime_mode"] == runtime_mode
    assert score["adapter_profile"] == profile_name
    assert (tmp_path / episode_id / "trace.jsonl").is_file()
    assert (tmp_path / episode_id / "score.json").is_file()
