"""Native GitHub submissions and read-only review import. Never posts an issue."""
from datetime import datetime, timezone
import re
import subprocess
from urllib.parse import urlencode

from .artifacts import strict_json, validate_receipt, verify_evidence
from .validation import digest

REPOSITORY = "pope8zdt/Async-RBench"
REPO_PATH = f"repos/{REPOSITORY}"
ISSUES_URL = f"https://github.com/{REPOSITORY}/issues"
MARKER = re.compile(r"<!-- async-rbench-receipt:([0-9a-f]{64}) -->")
COMMAND = re.compile(r"/async-rbench (approve|request-changes|reject|withdraw) ([0-9a-f]{64})\n(.+)", re.S)
LOGIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}\Z")


class GitHubReader:
    """Uses the human's existing gh login. Tokens stay inside gh; GET only."""
    def get(self, path):
        if not isinstance(path, str) or not (path == "user" or path.startswith(REPO_PATH + "/")) or any(s in path for s in (":", "..", "\\", "\n", "\r")):
            raise ValueError("Unsupported GitHub read endpoint")
        try:
            result = subprocess.run(["gh", "api", "--hostname", "github.com", "--method", "GET", path],
                                    capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("GitHub CLI is unavailable; sign in with gh on this machine") from exc
        if result.returncode:
            raise ValueError("GitHub read failed; check your login and repository permissions")
        if len(result.stdout) > 16 * 1024 * 1024:
            raise ValueError("GitHub response is too large")
        return strict_json(result.stdout)


def prepare_submission(receipt):
    checked = validate_receipt(receipt)
    if not checked["valid"]:
        raise ValueError("; ".join(checked["errors"]))
    meta, fingerprint = receipt["metadata"], digest(receipt)
    coverage = checked["coverage"]
    body = (f"## Result submission\n\nAgent: {meta['agent']}\nModel: {meta['model']}\n"
            f"Organization: {meta['organization']}\nCode revision: {meta['code_revision']}\n"
            f"Track: Async\nCoverage: {coverage['tasks']} tasks, {coverage['repetitions']} repetitions\n\n"
            f"<!-- async-rbench-receipt:{fingerprint} -->\n"
            f"Receipt SHA-256: `{fingerprint}`\n\n"
            "Please arrange private evidence review here. No private artifacts are attached.\n"
            "This is a review request, not an approved benchmark result.")
    return {"url": ISSUES_URL + "/new?" + urlencode({"title": f"[Result submission] {meta['agent']}", "body": body}),
            "body": body, "sha256": fingerprint, "metadata": meta, "coverage": coverage}


def _identity(value):
    if not isinstance(value, dict) or type(value.get("id")) is not int or value["id"] <= 0 or value.get("type") != "User" or not isinstance(value.get("login"), str) or not LOGIN.fullmatch(value["login"]):
        raise ValueError("GitHub user identity could not be verified")
    return {k: value[k] for k in ("id", "login", "type")}


def _writer(client, user):
    permission = client.get(f"{REPO_PATH}/collaborators/{user['login']}/permission")
    return (isinstance(permission, dict) and permission.get("permission") in {"write", "maintain", "admin"}
            and isinstance(permission.get("user"), dict) and type(permission["user"].get("id")) is int
            and permission["user"]["id"] == user["id"])


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("GitHub timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("GitHub timestamp has no timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def sync_issue(client, store, issue_number, receipt, evidence=None, policy=None):
    """Import an existing GitHub decision; all remote operations are reads.

    `evidence` is (run_root, manifest_path, audit_path), supplied by the human
    maintainer after privately receiving the originals. A web request cannot
    invoke this function or set its local paths.
    """
    if type(issue_number) is not int or issue_number <= 0:
        raise ValueError("Use a positive GitHub issue number")
    actor = _identity(client.get("user"))
    if not _writer(client, actor):
        raise ValueError("Repository write permission is required to import reviews")
    issue_path = f"{REPO_PATH}/issues/{issue_number}"
    issue = client.get(issue_path)
    if not isinstance(issue, dict) or "pull_request" in issue or issue.get("number") != issue_number or issue.get("html_url") != f"{ISSUES_URL}/{issue_number}":
        raise ValueError("Expected an issue in the benchmark repository")
    submitter = _identity(issue.get("user"))
    fingerprint = digest(receipt)
    body = issue.get("body")
    updated = _timestamp(issue.get("updated_at"))
    def check_snapshot():
        current = client.get(issue_path)
        if not isinstance(current, dict) or current.get("body") != body or current.get("updated_at") != issue.get("updated_at") or current.get("user", {}).get("id") != submitter["id"]:
            raise ValueError("The issue changed during review import; check it again")
    if not isinstance(body, str) or MARKER.findall(body) != [fingerprint]:
        check_snapshot()
        invalidation = {"issue_id": issue.get("id"), "body_sha256": digest(body), "submitter": submitter}
        store.save(issue_number, updated, digest(invalidation), "receipt_changed", {},
                   {"operator": actor, "submitter": submitter, "reason": "Issue no longer names the supplied receipt"})
        raise ValueError("The issue does not name this exact receipt")
    candidates = []
    # Pagination is bounded and an incomplete scan fails closed, never approves.
    for page in range(1, 21):
        comments = client.get(f"{issue_path}/comments?per_page=100&page={page}")
        if not isinstance(comments, list):
            raise ValueError("Invalid GitHub comments response")
        candidates.extend(comments)
        if len(comments) < 100:
            break
    else:
        raise ValueError("Too many comments; review import requires a complete history")
    decision = None
    permissions = {}
    for comment in sorted(candidates, key=lambda c: c.get("id", 0)):
        if type(comment.get("id")) is not int:
            raise ValueError("Invalid comment identity")
        match = COMMAND.fullmatch(str(comment.get("body") or "").replace("\r\n", "\n").strip())
        if not match or match[2] != fingerprint or not match[3].strip():
            continue
        user = _identity(comment.get("user"))
        # No self-approval, including a participant who also maintains the repo.
        if user["id"] == submitter["id"]:
            continue
        cache_key = (user["id"], user["login"])
        if cache_key not in permissions:
            permissions[cache_key] = _writer(client, user)
        if not permissions[cache_key]:
            continue
        expected_url = f"{ISSUES_URL}/{issue_number}#issuecomment-{comment['id']}"
        if comment.get("html_url") != expected_url:
            raise ValueError("Review comment belongs to another issue")
        updated = max(updated, _timestamp(comment.get("updated_at")))
        decision = {"action": match[1], "reviewer": user, "id": comment["id"], "url": expected_url,
                    "reason": match[3].strip()[:4000], "updated_at": comment["updated_at"]}
    # Reject a moving issue instead of binding approval to a half-old snapshot.
    check_snapshot()
    status = {"approve": "approved", "request-changes": "changes_requested", "reject": "rejected", "withdraw": "withdrawn"}.get(decision["action"] if decision else None, "pending")
    snapshot = digest({"receipt": fingerprint, "decision": decision, "issue_id": issue.get("id"), "submitter": submitter})
    audit = {"receipt_sha256": fingerprint, "operator": actor, "submitter": submitter, "decision": decision}
    summary = {}
    if status == "approved":
        try:
            if not evidence or policy is None:
                raise ValueError("Approval requires the original private evidence and trusted judge")
            verify_evidence(receipt, *evidence)
            checked = validate_receipt(receipt, policy)
            if not checked["valid"] or not checked["rankable"]:
                raise ValueError("Full registered coverage and trusted policy checks are required for ranking")
            summary = {"issue": issue_number, "url": issue["html_url"], "receipt_sha256": fingerprint,
                       "metadata": receipt["metadata"], "metrics": checked["metrics"],
                       "submitter": submitter["login"], "reviewer": decision["reviewer"]["login"],
                       "review_url": decision["url"], "reviewed_at": decision["updated_at"],
                       "verification": "maintainer-reviewed", "score_policy_version": receipt["scores"][0]["score_policy_version"]}
        except (ValueError, OSError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
            store.save(issue_number, updated, snapshot, "needs_evidence", {}, audit)
            raise ValueError("Original evidence and trusted policy checks must pass before ranking") from exc
    store.save(issue_number, updated, snapshot, status, summary, audit)
    return {"issue": issue_number, "status": status, "receipt_sha256": fingerprint}
