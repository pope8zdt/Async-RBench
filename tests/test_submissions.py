from __future__ import annotations

from copy import deepcopy

import pytest

from async_rbench.submissions.demo import demo_bundle, demo_policy
from async_rbench.submissions.validation import validate_bundle
from async_rbench.submissions.validation import digest
from async_rbench.submissions.store import Store, WorkflowError, REVIEW_CHECKS


@pytest.fixture
def policy():
    return demo_policy()


def test_valid_demo_has_complete_coverage_and_computed_scores(policy):
    result = validate_bundle(demo_bundle(policy), policy)
    assert result["valid"] is True
    assert result["metrics"]["episodes"] == 200
    assert result["metrics"]["scenarios"] == 8
    assert result["metrics"]["drs"] == 64.8
    assert result["metrics"]["success"] == 75
    assert result["verification"] == "synthetic-local-only"


@pytest.mark.parametrize("mutation,code", [
    (lambda b: b["scores"].pop(), "coverage"),
    (lambda b: b["scores"].append(deepcopy(b["scores"][0])), "duplicate_episode"),
    (lambda b: b["scores"][0].update(episode_id="extra"), "coverage"),
    (lambda b: b["scores"][0].update(async_drs=99), "score_range"),
    (lambda b: b["scores"][0].update(async_drs=True), "score_range"),
    (lambda b: b["scores"][0].update(base_task_score=0.5), "score_range"),
    (lambda b: b["scores"][0].update(conformance_passed=False), "conformance"),
    (lambda b: b["scores"][0].update(manifest_sha256="fake"), "manifest_binding"),
    (lambda b: b["scores"][0].update(model="other-model"), "identity"),
    (lambda b: b["scores"][0].update(score_policy_version="old"), "policy"),
    (lambda b: b["evidence"][0].update(sha256="fake"), "evidence_binding"),
    (lambda b: b["audit"].update(passed=False), "audit"),
    (lambda b: b["metadata"].update(api_key="never-store-this"), "schema"),
    (lambda b: b["manifest"]["episodes"].pop(), "manifest_coverage"),
    (lambda b: b.update(simulated=False), "simulation_only"),
    (lambda b: b["audit"].update(scores_sha256="fake"), "audit_binding"),
    (lambda b: b["scores"][0].update(execution_mode="linear"), "identity"),
])
def test_untrusted_packages_are_rejected(policy, mutation, code):
    bundle = demo_bundle(policy)
    mutation(bundle)
    result = validate_bundle(bundle, policy)
    assert result["valid"] is False
    assert code in {e["code"] for e in result["errors"]}


def test_malformed_shapes_never_raise(policy):
    for value in [None, [], {}, {"scores": [None]}, "hello"]:
        assert validate_bundle(value, policy)["valid"] is False


@pytest.fixture
def store(tmp_path, policy):
    return Store(tmp_path / "submissions.sqlite", policy)


def test_submission_review_and_listing_persist(store, policy):
    result = store.submit("participant", demo_bundle(policy))
    assert result["status"] == "pending"
    assert store.leaderboard() == []
    approved = store.review("maintainer", result["id"], 1, "approve", REVIEW_CHECKS, "Evidence inspected")
    assert approved["status"] == "approved"
    reopened = Store(store.path, policy)
    assert reopened.leaderboard()[0]["id"] == result["id"]
    assert len(reopened.get("participant", result["id"])["history"]) == 2
    assert "bundle" not in reopened.leaderboard()[0]


def test_permissions_and_checklist_cannot_be_bypassed(store, policy):
    item = store.submit("participant", demo_bundle(policy))
    with pytest.raises(WorkflowError):
        store.get("other-participant", item["id"])
    with pytest.raises(WorkflowError):
        store.review("participant", item["id"], 1, "approve", REVIEW_CHECKS, "ok")
    with pytest.raises(WorkflowError):
        store.review("maintainer", item["id"], 1, "approve", [], "ok")
    with pytest.raises(WorkflowError):
        store.submit("maintainer", demo_bundle(policy))
    assert store.leaderboard() == []


def test_changes_resubmit_and_stale_review(store, policy):
    item = store.submit("participant", demo_bundle(policy))
    store.review("maintainer", item["id"], 1, "changes_requested", [], "Add evidence")
    fresh = store.submit("participant", demo_bundle(policy, variant=1), item["id"], 2)
    assert fresh["revision"] == 2
    assert fresh["version"] == 3
    assert store.leaderboard() == []
    with pytest.raises(WorkflowError):
        store.review("maintainer", item["id"], 1, "approve", REVIEW_CHECKS, "stale")
    store.review("maintainer", item["id"], 3, "approve", REVIEW_CHECKS, "Rechecked new revision")
    detail = store.get("participant", item["id"])
    assert len(detail["history"]) == 4
    assert len(detail["revisions"]) == 2


def test_rejection_and_withdrawal_never_list(store, policy):
    item = store.submit("participant", demo_bundle(policy))
    store.review("maintainer", item["id"], 1, "reject", [], "Noncomparable settings")
    assert store.leaderboard() == []
    second = store.submit("other-participant", demo_bundle(policy))
    store.review("maintainer", second["id"], 1, "approve", REVIEW_CHECKS, "ok")
    store.review("maintainer", second["id"], 2, "withdraw", [], "Evidence withdrawn")
    assert store.leaderboard() == []


def test_failed_and_duplicate_submissions(store, policy):
    invalid = demo_bundle(policy)
    invalid["scores"].pop()
    with pytest.raises(WorkflowError):
        store.submit("participant", invalid)
    assert store.list("maintainer") == []
    one = store.submit("participant", demo_bundle(policy))
    same = store.submit("participant", demo_bundle(policy))
    assert one["id"] == same["id"]
    assert len(store.list("maintainer")) == 1


def test_reason_required_for_review(store, policy):
    item = store.submit("participant", demo_bundle(policy))
    with pytest.raises(WorkflowError):
        store.review("maintainer", item["id"], 1, "reject", [], " ")


@pytest.mark.parametrize("value", [False, 0.0])
def test_manifest_identity_is_type_sensitive(policy, value):
    bundle = demo_bundle(policy)
    bundle["manifest"]["episodes"][0]["repeat"] = value
    manifest_hash = digest(bundle["manifest"])
    for row in bundle["scores"]:
        row["manifest_sha256"] = manifest_hash
    bundle["audit"]["manifest_sha256"] = manifest_hash
    bundle["audit"]["scores_sha256"] = digest(bundle["scores"])
    assert validate_bundle(bundle, policy)["valid"] is False


def test_tampered_stored_package_cannot_be_approved(store, policy):
    row = store.submit("participant", demo_bundle(policy))
    with store.connection() as db:
        db.execute("UPDATE revisions SET hash='tampered' WHERE submission_id=?", (row["id"],))
    with pytest.raises(WorkflowError):
        store.review("maintainer", row["id"], 1, "approve", REVIEW_CHECKS, "ok")
    assert store.leaderboard() == []
