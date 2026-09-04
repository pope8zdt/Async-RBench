import json
from pathlib import Path
import tomllib

import yaml

from async_rbench import __version__
from async_rbench.evaluation.version import EVALUATION_CONTRACT_VERSION


ROOT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = "10.1.1"


STALE_RELEASE_PATHS = (
    "docs/case-acceptance-policy.md",
    "docs/expansion_v2_pipeline.md",
    "docs/redesign-technical-debt.md",
    "docs/small-calibration-protocol.md",
    "docs/task-causal-case-production.md",
    "research/acceptance-cases.txt",
    "research/scan_instance_registries.py",
    "run_qwen_family_sample.ps1",
    "scripts/migrate_workstream_result_contracts.py",
    "tests/test_workstream_contract_migration.py",
    "tools/sanitize_public_cases_v3.py",
)


def test_v101_release_surface_excludes_superseded_material() -> None:
    present = [path for path in STALE_RELEASE_PATHS if (ROOT / path).exists()]
    assert present == []


def test_release_version_is_synchronized_across_public_surfaces() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contract = json.loads((ROOT / "evaluation_contract.json").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert __version__ == RELEASE_VERSION
    assert EVALUATION_CONTRACT_VERSION == RELEASE_VERSION
    assert pyproject["project"]["version"] == RELEASE_VERSION
    assert contract["version"] == RELEASE_VERSION
    assert f"Version: {RELEASE_VERSION}" in readme


def test_current_contract_surfaces_describe_five_million_fuse_and_zero_rule() -> None:
    protocol = (ROOT / "PROTOCOL.md").read_text(encoding="utf-8")
    contract = json.loads((ROOT / "evaluation_contract.json").read_text(encoding="utf-8"))
    metric = contract["metric_definitions"]["async_dynamic_replanning_score"]

    assert "5,000,000-token emergency fuse" in protocol
    assert "20,000,000-token emergency fuse" not in protocol
    assert "participant-controlled unreached events contribute zero" in metric
    assert "construction, infrastructure, and resource-safety failures remain unscored" in metric


def test_readme_is_concise_and_names_the_registered_release_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert len(readme.splitlines()) <= 220
    assert "10.1.1" in readme
    assert "200 case directories" in readme
    assert "201 registered instances" in readme
    assert "82 calibration / 30 development / 89 test" in readme
    assert "linear_base_task_score" in readme
    assert "async_base_task_score" in readme
    assert "async_dynamic_replanning_score" in readme
    assert "F:/DTbench" not in readme
    assert "F:\\DTbench" not in readme


def test_release_docs_do_not_reference_removed_or_missing_guides() -> None:
    config_readme = (ROOT / "configs" / "README.md").read_text(encoding="utf-8")
    upstream_readme = (ROOT / "upstream" / "README.md").read_text(encoding="utf-8")
    eval_cli = (ROOT / "async_rbench" / "eval_cli.py").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "CASE_RUNBOOK.zh-CN.md").read_text(encoding="utf-8")

    assert "only paid model profile" not in config_readme
    assert "source_native_v4_rebuild_report.md" not in upstream_readme
    assert "MIGRATION.md" not in eval_cli
    assert "482 collected" not in runbook
    assert "paper_metrics_by_mode" in runbook
    assert "gateway_accepted" in runbook
    assert "private_rejection" not in runbook


def test_v101_profiles_have_one_step_bounded_resource_schema() -> None:
    removed = {
        "max_main_turns", "max_child_turns", "max_total_tokens",
        "budget_child_shared", "budget_main_pre", "budget_main_post",
        "budget_main_total", "child_context_budget_chars",
    }
    for path in (ROOT / "configs" / "model-profiles").glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        profile = yaml.safe_load(text)
        assert "max_main_steps:" in text, path
        assert "max_child_steps:" in text, path
        assert "emergency_total_token_cap:" in text, path
        assert profile["emergency_total_token_cap"] == 5_000_000, path
        for key in removed:
            assert f"{key}:" not in text, (path, key)
