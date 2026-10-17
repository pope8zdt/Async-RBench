"""Small public projections for static hosting; never publishes private evidence."""
import math
import re

from .artifacts import HEX, _metadata
from .github_flow import ISSUES_URL, LOGIN, _timestamp, prepare_submission
from ..evaluation.weighting import SCORE_POLICY_VERSION

BOARD_SCHEMA = "async-rbench-community-board-1"
ENTRY_FIELDS = {"issue", "url", "receipt_sha256", "metadata", "metrics", "submitter",
                "reviewer", "review_url", "reviewed_at", "verification", "score_policy_version"}


def public_submission(receipt):
    draft = prepare_submission(receipt)
    return {"schema": "async-rbench-public-submission-1",
            **{key: draft[key] for key in ("metadata", "coverage", "sha256")}}


def validate_public_board(value):
    def require(condition):
        if not condition:
            raise ValueError("Invalid public community snapshot")
    require(isinstance(value, dict) and set(value) == {"schema", "entries"})
    require(value["schema"] == BOARD_SCHEMA and isinstance(value["entries"], list))
    seen = set()
    for row in value["entries"]:
        require(isinstance(row, dict) and set(row) == ENTRY_FIELDS)
        issue = row["issue"]
        require(type(issue) is int and 0 < issue < 2**53 and issue not in seen)
        seen.add(issue)
        require(row["url"] == f"{ISSUES_URL}/{issue}")
        require(isinstance(row["review_url"], str) and re.fullmatch(re.escape(row["url"]) + r"#issuecomment-[1-9][0-9]*", row["review_url"]))
        require(isinstance(row["receipt_sha256"], str) and HEX.fullmatch(row["receipt_sha256"]))
        _metadata(row["metadata"])
        _timestamp(row["reviewed_at"])
        for key in ("submitter", "reviewer"):
            require(isinstance(row[key], str) and LOGIN.fullmatch(row[key]))
        require(row["submitter"].lower() != row["reviewer"].lower())
        require(row["verification"] == "maintainer-reviewed" and row["score_policy_version"] == SCORE_POLICY_VERSION)
        metrics = row["metrics"]
        require(isinstance(metrics, dict) and set(metrics) == {"drs", "success", "tasks", "episodes", "repetitions"})
        for key in ("drs", "success"):
            number = metrics[key]
            require(type(number) in (int, float) and math.isfinite(number) and 0 <= number <= 100)
        for key in ("tasks", "episodes", "repetitions"):
            require(type(metrics[key]) is int and 0 < metrics[key] < 2**53)
        require(metrics["episodes"] == metrics["tasks"] * metrics["repetitions"])
    return value


def public_board(store):
    # entries() exposes approved records only; fail closed on unexpected fields.
    return validate_public_board({"schema": BOARD_SCHEMA, "entries": store.entries()})
