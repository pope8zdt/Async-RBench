from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from async_rbench.conformance import CONFORMANCE_TESTS, run_checks, run_conformance
from async_rbench.profiles.conformance_mock.scripted_backend import ScriptedTestBackend


ROOT = Path(__file__).resolve().parents[1]


def test_scripted_conformance_evidence_satisfies_sha_patterns() -> None:
    for pattern in ("[0-9a-f]{40}", "^[0-9a-f]{64}$"):
        value = ScriptedTestBackend._pattern_value(pattern)
        assert re.fullmatch(pattern, value), (pattern, value)


def test_registry_has_ten_protocol_tests():
    assert len(CONFORMANCE_TESTS) == 10
    ids = [spec["id"] for spec in CONFORMANCE_TESTS]
    assert len(set(ids)) == 10


def test_kernel_invariant_checks_pass_without_an_episode():
    results = run_checks([], {})
    by_id = {result.test_id: result for result in results}
    for test_id in (
        "child_workspace_isolation",
        "stale_result_rejection",
        "event_asset_scoping",
        "private_truth_projection",
        "promotion_outcome_audit",
        "event_theme_expressibility",
    ):
        assert by_id[test_id].passed, f"{test_id}: {by_id[test_id].detail}"


def test_conformance_mock_passes_all_checks(tmp_path: Path):
    adapter = [sys.executable, str(ROOT / "adapters" / "conformance_mock.py")]
    result = asyncio.run(run_conformance(
        ROOT, adapter_command=adapter, output_dir=tmp_path, case_ids=["secure-release"],
    ))
    assert result["conformance_passed"] is True
    for case_id, checks in result["cases"].items():
        for check in checks:
            assert check["passed"], f"{case_id}/{check['test_id']}: {check['detail']}"


def test_pre_delivery_leak_fails_the_leak_check(tmp_path: Path):
    events = [
        {"type": "child_completed", "completion_id": "leak-1"},
        {"type": "result_consumed", "completion_id": "leak-1"},
    ]
    leak_check = next(
        check for check in run_checks(events, {})
        if check.test_id == "no_pre_delivery_leak"
    )
    assert leak_check.passed is False


def test_conformance_adapter_command_pins_reference_scaffold_to_scripted():
    from async_rbench.conformance.runner import conformance_adapter_command
    from async_rbench.profiles import load_profile

    profile = load_profile("reference_scaffold_api")
    base = list(profile.adapter_command)
    command = conformance_adapter_command(profile)
    assert command == base + ["--backend", "scripted_test", "--workspace-mode", "disabled"]

    command = conformance_adapter_command(profile, Path("cfg.yaml"))
    assert command == base + [
        "--backend", "scripted_test", "--workspace-mode", "disabled", "--config", "cfg.yaml",
    ]

    actual = base + ["--config", "actual.yaml", "--main-model", "participant-model"]
    command = conformance_adapter_command(
        profile, Path("ignored.yaml"), base_command=actual,
    )
    assert command[:len(actual)] == actual
    assert command.count("--config") == 1
    assert command[-4:] == ["--backend", "scripted_test", "--workspace-mode", "disabled"]


def test_conformance_adapter_command_pins_non_scaffold_profiles_to_disabled():
    from async_rbench.conformance.runner import conformance_adapter_command
    from async_rbench.profiles import load_profile

    for name in ("native_agent", "minimal_api", "conformance_mock"):
        profile = load_profile(name)
        base = list(profile.adapter_command)
        command = conformance_adapter_command(profile)
        assert command == base + ["--workspace-mode", "disabled"]
        assert "--backend" not in command


def test_run_conformance_with_profile_runs_the_real_adapter(tmp_path: Path):
    from async_rbench.profiles import AdapterProfile

    # Bind conformance to the actual reference adapter (pinned to the scripted
    # backend + disabled workspace by ``conformance_adapter_command``). It must
    # pass all eight checks and persist conformance.json.
    profile = AdapterProfile(
        profile="reference_scaffold_api",
        runtime_mode="api_only",
        adapter_command=[sys.executable, str(ROOT / "adapters" / "reference_scaffold_api.py")],
    )
    result = asyncio.run(run_conformance(
        ROOT, profile=profile, output_dir=tmp_path, case_ids=["secure-release"],
    ))
    assert result["conformance_passed"] is True
    assert (tmp_path / "conformance.json").is_file()
    for check in result["cases"]["secure-release::seed-1"]:
        assert check["passed"], f"{check['test_id']}: {check['detail']}"
