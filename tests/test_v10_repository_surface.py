from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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


def test_v10_release_surface_excludes_superseded_material() -> None:
    present = [path for path in STALE_RELEASE_PATHS if (ROOT / path).exists()]
    assert present == []


def test_readme_is_concise_and_names_the_registered_release_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert len(readme.splitlines()) <= 220
    assert "10.0.0" in readme
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
