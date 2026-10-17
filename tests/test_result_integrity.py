from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from async_rbench import eval_cli
from async_rbench.evaluation.aggregate import aggregate_reports
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION


def record(episode="a-async-0", **changes):
    return dict(episode_id=episode, case_id="a", instance_id="seed-1", repeat=0,
                execution_mode="async", guidance="incentive", model="demo-model",
                split="test", score_policy_version=SCORE_POLICY_VERSION,
                leaderboard_eligible=True, conformance_passed=True,
                async_drs=0.5, base_task_score=1, score_status="scored",
                denominator_digest="same", total_tokens=100, main_tokens=100, **changes)


@pytest.mark.parametrize("value", [99, -0.1, float("nan"), float("inf"), True, "0.5"])
def test_invalid_drs_cannot_be_aggregated(value):
    item = record()
    item["async_drs"] = value
    with pytest.raises(ValueError, match="DRS"):
        aggregate_reports([item], 2)


def test_failed_conformance_cannot_emit_leaderboard():
    item = record()
    item["conformance_passed"] = False
    result = aggregate_reports([item], 2)
    assert "official_conformance_failed" in result["audit"]["hard_fail_reasons"]
    assert result["leaderboard"] == []


@pytest.mark.parametrize("kind", ["duplicate", "extra", "missing"])
def test_exact_episode_coverage(kind):
    planned = [record()]
    observed = [record()]
    if kind == "duplicate":
        observed.append(record())
    elif kind == "extra":
        observed.append(record("extra"))
    else:
        planned.append(record("missing"))
    result = aggregate_reports(observed, 2, planned_episodes=planned)
    assert result["audit"]["hard_fail"] is True
    assert result["leaderboard"] == []


def test_explicit_missing_manifest_fails(tmp_path):
    args = SimpleNamespace(root=str(tmp_path), manifest=str(tmp_path / "missing.json"),
                           output=str(tmp_path / "out.json"), minimum_counterfactual_coverage=None,
                           bootstrap_iterations=2)
    with pytest.raises(ValueError, match="manifest"):
        eval_cli.cmd_aggregate(args)


def test_missing_score_manifest_digest_fails(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"episodes": [record()]}))
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "score.json").write_text(json.dumps(record()))
    args = SimpleNamespace(root=str(runs), manifest=str(manifest),
                           output=str(tmp_path / "out.json"), minimum_counterfactual_coverage=None,
                           bootstrap_iterations=2)
    with pytest.raises(ValueError, match="manifest"):
        eval_cli.cmd_aggregate(args)


def test_audit_checks_episode_ids_not_only_cases(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"episodes": [record(), record("a-async-1")]}))
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    item = record(manifest_sha256=digest)
    monkeypatch.setattr(eval_cli, "load_reports", lambda _: [item])
    monkeypatch.setattr(eval_cli, "audit_run", lambda *a, **kw: {
        "contract_fixtures": {"passed": True}, "episode_count": 1,
        "artifact_compatibility": {"all_episodes_match_current": True},
        "resources": {"episodes": [item]},
    })
    args = SimpleNamespace(root=str(tmp_path / "runs"), judge_root=str(tmp_path / "judge"),
                           manifest=str(manifest), output=str(tmp_path / "audit.json"))
    assert eval_cli.cmd_audit_run(args) == 1
    report = json.loads((tmp_path / "audit.json").read_text())
    assert report["gates"]["manifest_complete"] is False
    assert report["manifest_audit"]["missing_episode_ids"] == ["a-async-1"]
