import copy
import json

import pytest

from async_rbench.submissions.artifacts import export_receipt, validate_receipt, verify_evidence
from submission_fixtures import runner_files


def test_exports_real_shaped_files_without_private_payloads(tmp_path):
    run, manifest, audit, meta, policy = runner_files(tmp_path)
    receipt = export_receipt(run, manifest, audit, meta)
    assert "PRIVATE-DO-NOT-EXPORT" not in json.dumps(receipt)
    assert "api_key" not in json.dumps(receipt)
    result = validate_receipt(receipt, policy)
    assert result["valid"] and result["rankable"]
    assert result["metrics"] == {"drs": 62.5, "success": 50.0, "tasks": 2, "episodes": 6, "repetitions": 3}
    verify_evidence(receipt, run, manifest, audit)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "boolean", "nan", "unbound", "conformance", "audit", "model", "theme", "judge", "repeat", "mode", "secret"])
def test_rejects_inconsistent_or_untrusted_receipts(tmp_path, mutation):
    run, manifest, audit, meta, policy = runner_files(tmp_path)
    receipt = export_receipt(run, manifest, audit, meta)
    if mutation == "missing": receipt["scores"].pop()
    elif mutation == "duplicate": receipt["scores"].append(copy.deepcopy(receipt["scores"][0]))
    elif mutation == "extra": receipt["evidence"].append({**receipt["evidence"][0], "episode_id": "extra"})
    elif mutation == "boolean": receipt["scores"][0]["async_drs"] = True
    elif mutation == "nan": receipt["scores"][0]["async_drs"] = float("nan")
    elif mutation == "unbound": receipt["manifest_json"] += " "
    elif mutation == "conformance": receipt["scores"][0]["conformance_passed"] = False
    elif mutation == "audit": receipt["audit"]["gates"].pop("manifest_digest_match")
    elif mutation == "model": receipt["scores"][0]["model"] = "another-model"
    elif mutation == "theme": receipt["scores"][0]["event_theme"] = "invented"
    elif mutation == "judge": policy["judge_sha256"] = "9" * 64
    elif mutation == "repeat": receipt["scores"][0]["repeat"] = False
    elif mutation == "mode": receipt["scores"][0]["execution_mode"] = "linear"
    elif mutation == "secret": receipt["metadata"]["api_key"] = "private"
    assert not validate_receipt(receipt, policy)["valid"]


def test_partial_run_is_not_rankable(tmp_path):
    run, manifest, audit, meta, policy = runner_files(tmp_path)
    receipt = export_receipt(run, manifest, audit, meta)
    policy["cases"]["another-case::seed-1"] = copy.deepcopy(next(iter(policy["cases"].values())))
    result = validate_receipt(receipt, policy)
    assert result["valid"] and not result["rankable"]


def test_original_evidence_changes_fail_even_when_receipt_is_unchanged(tmp_path):
    run, manifest, audit, meta, policy = runner_files(tmp_path)
    receipt = export_receipt(run, manifest, audit, meta)
    score_path = next(run.glob("*/score.json"))
    score = json.loads(score_path.read_text())
    score["participant_metadata"]["changed"] = True
    score_path.write_text(json.dumps(score))
    with pytest.raises(ValueError, match="evidence|receipt"):
        verify_evidence(receipt, run, manifest, audit)


def test_event_hash_mismatch_prevents_export(tmp_path):
    run, manifest, audit, meta, _ = runner_files(tmp_path)
    event_file = next(run.glob("*/event_source.jsonl"))
    event_file.write_text(event_file.read_text().replace("episode_ended", "other_event"))
    with pytest.raises(ValueError, match="event"):
        export_receipt(run, manifest, audit, meta)


@pytest.mark.parametrize("value", [None, [], {}, {"schema": "async-rbench-submission-demo-1"}])
def test_rejects_demo_and_malformed_input(value):
    assert not validate_receipt(value)["valid"]


def test_ranking_pins_frozen_resource_policy_even_if_all_episodes_agree(tmp_path):
    run, manifest, audit, meta, policy = runner_files(tmp_path)
    receipt = export_receipt(run, manifest, audit, meta)
    for score in receipt["scores"]:
        score["resource_policy_sha256"] = "0" * 64
    result = validate_receipt(receipt, policy)
    assert not result["valid"]
    assert not result["rankable"]
