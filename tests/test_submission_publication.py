import copy
import json

import pytest

from async_rbench.submissions.__main__ import main
from async_rbench.submissions.artifacts import export_receipt
from async_rbench.submissions.github_flow import sync_issue
from async_rbench.submissions.publication import public_submission, public_board, validate_public_board
from async_rbench.submissions.validation import digest
from submission_fixtures import runner_files
from test_github_submissions import setup


def test_public_packet_is_bound_to_private_receipt_without_leaking_it(tmp_path):
    run, manifest, audit, meta, _ = runner_files(tmp_path)
    receipt = export_receipt(run, manifest, audit, meta)
    packet = public_submission(receipt)
    assert set(packet) == {"schema", "metadata", "coverage", "sha256"}
    assert packet["schema"] == "async-rbench-public-submission-1"
    assert packet["sha256"] == digest(receipt)
    assert packet["metadata"] == meta
    assert packet["coverage"]["tasks"] == 2
    assert "manifest" not in json.dumps(packet)
    assert "PRIVATE-DO-NOT-EXPORT" not in json.dumps(packet)
    receipt["scores"][0]["async_drs"] = True
    with pytest.raises(ValueError):
        public_submission(receipt)


def test_cli_prepare_keeps_private_file_unchanged_and_refuses_overwrite(tmp_path):
    run, manifest, audit, meta, _ = runner_files(tmp_path)
    receipt = export_receipt(run, manifest, audit, meta)
    private = tmp_path / "private.json"
    private.write_text(json.dumps(receipt), encoding="utf-8")
    original = private.read_bytes()
    output = tmp_path / "submission.json"
    assert main(["prepare", str(private), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["sha256"] == digest(receipt)
    assert main(["prepare", str(private), "--output", str(output)]) == 1
    assert private.read_bytes() == original


def test_board_export_follows_real_approval_then_withdrawal(tmp_path):
    receipt, policy, evidence, github, store = setup(tmp_path)
    assert public_board(store) == {"schema": "async-rbench-community-board-1", "entries": []}
    github.decide("approve", receipt)
    sync_issue(github, store, 7, receipt, evidence, policy)
    board = public_board(store)
    assert len(board["entries"]) == 1
    assert board["entries"][0]["issue"] == 7
    assert board["entries"][0]["verification"] == "maintainer-reviewed"
    assert "operator" not in json.dumps(board)
    assert "PRIVATE-DO-NOT-EXPORT" not in json.dumps(board)
    assert validate_public_board(board) == board
    github.decide("withdraw", receipt)
    sync_issue(github, store, 7, receipt)
    assert public_board(store)["entries"] == []


@pytest.mark.parametrize("mutation", ["private", "bad_url", "nonfinite", "boolean", "duplicate"])
def test_publication_refuses_corrupt_or_private_board_fields(tmp_path, mutation):
    receipt, policy, evidence, github, store = setup(tmp_path)
    github.decide("approve", receipt)
    sync_issue(github, store, 7, receipt, evidence, policy)
    board = public_board(store)
    entry = board["entries"][0]
    if mutation == "private": entry["raw_trace"] = "must not publish"
    if mutation == "bad_url": entry["review_url"] = "https://evil.example/"
    if mutation == "nonfinite": entry["metrics"]["drs"] = float("nan")
    if mutation == "boolean": entry["issue"] = True
    if mutation == "duplicate": board["entries"].append(copy.deepcopy(entry))
    with pytest.raises(ValueError):
        validate_public_board(board)
