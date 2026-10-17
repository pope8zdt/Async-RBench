import copy
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from async_rbench.submissions.artifacts import export_receipt
from async_rbench.submissions.validation import digest
from async_rbench.submissions.community import CommunityStore
from async_rbench.submissions.github_flow import prepare_submission, sync_issue, GitHubReader
from submission_fixtures import runner_files

REPO = "pope8zdt/Async-RBench"
BASE = f"repos/{REPO}"


class GitHubFixture:
    """Transport double only: real review, validation and storage execute."""
    def __init__(self, receipt):
        self.issue = {"id": 700, "number": 7, "state": "open", "html_url": f"https://github.com/{REPO}/issues/7",
                      "body": f"<!-- async-rbench-receipt:{digest(receipt)} -->", "updated_at": "2026-10-17T01:00:00Z",
                      "user": {"id": 20, "login": "participant", "type": "User"}}
        self.comments = []
        self.actor = {"id": 10, "login": "reviewer", "type": "User"}
        self.permissions = {"reviewer": {"permission": "write", "user": self.actor}}
        self.requested = []

    def decide(self, action, receipt, user=None):
        index = len(self.comments) + 1
        self.issue["updated_at"] = f"2026-10-17T01:0{index}:00Z"
        self.comments.append({"id": index, "user": user or self.actor,
            "body": f"/async-rbench {action} {digest(receipt)}\nEvidence and protocol reviewed.",
            "html_url": f"https://github.com/{REPO}/issues/7#issuecomment-{index}",
            "created_at": self.issue["updated_at"], "updated_at": self.issue["updated_at"]})

    def get(self, path):
        self.requested.append(path)
        if path == "user": return copy.deepcopy(self.actor)
        if path == BASE + "/issues/7": return copy.deepcopy(self.issue)
        if path.startswith(BASE + "/issues/7/comments?"): return copy.deepcopy(self.comments)
        prefix = BASE + "/collaborators/"
        if path.startswith(prefix) and path.endswith("/permission"):
            login = path[len(prefix):].split("/")[0]
            return copy.deepcopy(self.permissions.get(login, {"permission": "read", "user": {"id": 99, "login": login}}))
        raise AssertionError(f"Unexpected remote read: {path}")


def setup(tmp_path):
    run, manifest, audit, meta, policy = runner_files(tmp_path)
    receipt = export_receipt(run, manifest, audit, meta)
    return receipt, policy, (run, manifest, audit), GitHubFixture(receipt), CommunityStore(tmp_path / "community.sqlite")


def test_public_draft_contains_only_summary_and_exact_digest(tmp_path):
    receipt, _, _, _, _ = setup(tmp_path)
    prepared = prepare_submission(receipt)
    url = urlsplit(prepared["url"])
    assert (url.scheme, url.netloc, url.path) == ("https", "github.com", f"/{REPO}/issues/new")
    body = parse_qs(url.query)["body"][0]
    assert digest(receipt) in body
    assert "test-model" in body
    for private in ["PRIVATE-DO-NOT-EXPORT", "event_source", "kernel_private", "theme-a", "verifier_bundle", "api_key", str(tmp_path)]:
        assert private not in body
    assert "labels" not in parse_qs(url.query)


def test_pending_approve_withdraw_and_history_persist(tmp_path):
    receipt, policy, evidence, github, store = setup(tmp_path)
    assert sync_issue(github, store, 7, receipt, evidence, policy)["status"] == "pending"
    assert store.entries() == []
    github.decide("approve", receipt)
    result = sync_issue(github, store, 7, receipt, evidence, policy)
    assert result["status"] == "approved"
    public = CommunityStore(store.path).entries()
    assert len(public) == 1
    assert public[0]["submitter"] == "participant"
    assert public[0]["reviewer"] == "reviewer"
    assert public[0]["metrics"]["drs"] == 62.5
    assert "evidence" not in json.dumps(public)
    github.decide("withdraw", receipt)
    assert sync_issue(github, store, 7, receipt, None, None)["status"] == "withdrawn"
    assert store.entries() == []
    assert len(store.history(7)) == 3


@pytest.mark.parametrize("permission", ["read", "triage", "none"])
def test_operator_without_write_permission_cannot_sync(tmp_path, permission):
    receipt, policy, evidence, github, store = setup(tmp_path)
    github.permissions["reviewer"]["permission"] = permission
    github.decide("approve", receipt)
    with pytest.raises(ValueError, match="permission"):
        sync_issue(github, store, 7, receipt, evidence, policy)
    assert not store.entries()


@pytest.mark.parametrize("kind", ["outsider", "self", "spoofed_id", "different_hash", "missing_reason"])
def test_unauthorized_or_unbound_comment_cannot_approve(tmp_path, kind):
    receipt, policy, evidence, github, store = setup(tmp_path)
    user = None
    if kind == "outsider": user = {"id": 99, "login": "outsider", "type": "User"}
    if kind == "self":
        user = github.issue["user"]
        github.permissions["participant"] = {"permission": "admin", "user": user}
    if kind == "spoofed_id": user = {"id": 888, "login": "reviewer", "type": "User"}
    github.decide("approve", receipt, user)
    if kind == "different_hash": github.comments[-1]["body"] = github.comments[-1]["body"].replace(digest(receipt), "0" * 64)
    if kind == "missing_reason": github.comments[-1]["body"] = github.comments[-1]["body"].splitlines()[0]
    assert sync_issue(github, store, 7, receipt, evidence, policy)["status"] == "pending"
    assert store.entries() == []


def test_changed_receipt_needs_new_approval_and_old_snapshot_cannot_restore_it(tmp_path):
    receipt, policy, evidence, github, store = setup(tmp_path)
    github.decide("approve", receipt)
    sync_issue(github, store, 7, receipt, evidence, policy)
    old = copy.deepcopy(github)
    receipt["metadata"]["agent"] = "New revision"
    github.issue["body"] = f"<!-- async-rbench-receipt:{digest(receipt)} -->"
    github.issue["updated_at"] = "2026-10-17T02:00:00Z"
    assert sync_issue(github, store, 7, receipt, None, None)["status"] == "pending"
    assert store.entries() == []
    old_receipt = export_receipt(*evidence, {**receipt["metadata"], "agent": "Local test agent"})
    with pytest.raises(ValueError, match="older|stale"):
        sync_issue(old, store, 7, old_receipt, evidence, policy)


@pytest.mark.parametrize("kind", ["missing_evidence", "modified_evidence", "partial", "no_policy"])
def test_approval_requires_private_originals_and_trusted_complete_policy(tmp_path, kind):
    receipt, policy, evidence, github, store = setup(tmp_path)
    github.decide("approve", receipt)
    if kind == "missing_evidence": evidence = None
    if kind == "no_policy": policy = None
    if kind == "modified_evidence":
        next(evidence[0].glob("*/score.json")).write_text("{}")
    if kind == "partial": policy["cases"]["missing::seed-1"] = next(iter(policy["cases"].values()))
    with pytest.raises(ValueError):
        sync_issue(github, store, 7, receipt, evidence, policy)
    assert not store.entries()


@pytest.mark.parametrize("action,status", [("request-changes", "changes_requested"), ("reject", "rejected")])
def test_changes_and_rejection_do_not_list(tmp_path, action, status):
    receipt, _, _, github, store = setup(tmp_path)
    github.decide(action, receipt)
    assert sync_issue(github, store, 7, receipt, None, None)["status"] == status
    assert not store.entries()


def test_github_transport_cannot_write_or_follow_other_hosts(monkeypatch):
    import subprocess
    def run(args, **kwargs):
        assert args[:6] == ["gh", "api", "--hostname", "github.com", "--method", "GET"]
        assert args[-1] == "user"
        return subprocess.CompletedProcess(args, 0, '{"id":10}', "")
    monkeypatch.setattr(subprocess, "run", run)
    assert GitHubReader().get("user") == {"id": 10}
    with pytest.raises(ValueError): GitHubReader().get("https://evil.example/user")


def test_unchanged_sync_advances_watermark_against_stale_approval(tmp_path):
    store = CommunityStore(tmp_path / "watermark.sqlite")
    store.save(7, "2026-10-17T01:00:00+00:00", "withdrawal", "withdrawn", {}, {})
    store.save(7, "2026-10-17T03:00:00+00:00", "withdrawal", "withdrawn", {}, {})
    with pytest.raises(ValueError, match="older"):
        store.save(7, "2026-10-17T02:00:00+00:00", "old-approval", "approved", {"issue": 7, "metrics": {"drs": 90}}, {})
    assert not store.entries()
    assert len(store.history(7)) == 1


@pytest.mark.parametrize("new_body", ["Updated receipt pending", "<!-- async-rbench-receipt:" + "0" * 64 + " -->"])
def test_changed_issue_invalidates_old_approval_even_with_old_local_receipt(tmp_path, new_body):
    receipt, policy, evidence, github, store = setup(tmp_path)
    github.decide("approve", receipt)
    sync_issue(github, store, 7, receipt, evidence, policy)
    github.issue.update(body=new_body, updated_at="2026-10-17T03:00:00Z")
    with pytest.raises(ValueError, match="receipt"):
        sync_issue(github, store, 7, receipt, evidence, policy)
    assert store.entries() == []
    assert store.history(7)[-1]["status"] == "receipt_changed"


def test_conflicting_same_second_snapshots_cannot_restore_approval(tmp_path):
    store = CommunityStore(tmp_path / "equal-time.sqlite")
    timestamp = "2026-10-17T02:00:00+00:00"
    store.save(7, timestamp, "withdrawal", "withdrawn", {}, {})
    with pytest.raises(ValueError, match="conflict"):
        store.save(7, timestamp, "approval", "approved", {"issue": 7, "metrics": {"drs": 90}}, {})
    assert store.entries() == []
    with pytest.raises(ValueError, match="conflict"):
        store.save(7, timestamp, "approval", "approved", {"issue": 7, "metrics": {"drs": 90}}, {})
    assert store.entries() == []
    store.save(7, "2026-10-17T03:00:00+00:00", "new-approval", "approved", {"issue": 7, "metrics": {"drs": 90}}, {})
    assert len(store.entries()) == 1


def test_unstable_issue_cannot_invalidate_a_reviewed_snapshot(tmp_path):
    receipt, policy, evidence, github, store = setup(tmp_path)
    github.decide("approve", receipt)
    sync_issue(github, store, 7, receipt, evidence, policy)
    original = copy.deepcopy(github.issue)
    original_get = github.get
    reads = 0
    def moving(path):
        nonlocal reads
        value = original_get(path)
        if path == BASE + "/issues/7":
            reads += 1
            if reads == 1:
                value.update(body="Changing receipt", updated_at="2026-10-17T03:00:00Z")
            else:
                value = original
        return value
    github.get = moving
    with pytest.raises(ValueError, match="changed during"):
        sync_issue(github, store, 7, receipt, evidence, policy)
    assert len(store.entries()) == 1


@pytest.mark.parametrize("artifact", ["score", "audit", "manifest"])
def test_malformed_original_evidence_unlists_a_previously_approved_result(tmp_path, artifact):
    receipt, policy, evidence, github, store = setup(tmp_path)
    github.decide("approve", receipt)
    sync_issue(github, store, 7, receipt, evidence, policy)
    path = {"score": next(evidence[0].glob("*/score.json")), "audit": evidence[2], "manifest": evidence[1]}[artifact]
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        sync_issue(github, store, 7, receipt, evidence, policy)
    assert not store.entries()
    assert store.history(7)[-1]["status"] == "needs_evidence"
