"""Strict public projection with no private review links or source evidence."""
import math
import re
from ..artifacts import _metadata
from ..github_flow import LOGIN, _timestamp
from ...evaluation.weighting import SCORE_POLICY_VERSION

SCHEMA = "async-rbench-community-board-2"
FIELDS = {"id", "metadata", "metrics", "submitter", "reviewer", "reviewed_at", "verification", "score_policy_version"}


def validate_board(board):
    if not isinstance(board, dict) or set(board) != {"schema", "entries"} or board["schema"] != SCHEMA or not isinstance(board["entries"], list):
        raise ValueError("Invalid community snapshot")
    ids = set()
    for row in board["entries"]:
        if not isinstance(row, dict) or set(row) != FIELDS or not re.fullmatch(r"[0-9a-f]{32}", str(row["id"])) or row["id"] in ids:
            raise ValueError("Invalid community summary")
        ids.add(row["id"])
        _metadata(row["metadata"])
        for field in ("submitter", "reviewer"):
            if not isinstance(row[field], str) or not LOGIN.fullmatch(row[field]):
                raise ValueError("Invalid public identity")
        if row["submitter"].lower() == row["reviewer"].lower():
            raise ValueError("Self review")
        _timestamp(row["reviewed_at"])
        if row["verification"] != "maintainer-reviewed" or row["score_policy_version"] != SCORE_POLICY_VERSION:
            raise ValueError("Unsupported score provenance")
        metrics = row["metrics"]
        if not isinstance(metrics, dict) or set(metrics) != {"drs", "success", "tasks", "episodes", "repetitions"}:
            raise ValueError("Invalid public metrics")
        for name, value in (("tasks", 200), ("episodes", 600), ("repetitions", 3)):
            if type(metrics[name]) is not int or metrics[name] != value:
                raise ValueError("Incomplete public metrics")
        for name in ("drs", "success"):
            if type(metrics[name]) not in (int, float) or not math.isfinite(metrics[name]) or not 0 <= metrics[name] <= 100:
                raise ValueError("Invalid public score")
    return board
