from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "async-rbench" / "cases"


def test_every_public_case_has_only_the_frozen_public_surface() -> None:
    case_dirs = sorted(path for path in CASES.iterdir() if path.is_dir())
    assert len(case_dirs) == 200
    expected = {"public", "task", "PROVENANCE.md"}
    offenders = {
        case_dir.name: sorted(path.name for path in case_dir.iterdir())
        for case_dir in case_dirs
        if {path.name for path in case_dir.iterdir()} != expected
    }
    assert offenders == {}


def test_public_provenance_is_registered_and_does_not_name_private_paths() -> None:
    forbidden = (
        "this candidate",
        "not registered",
        "remains unregistered",
        "upstream_solutions",
        "task/tests",
        "evaluator/",
        "not human annotation",
    )
    offenders: dict[str, list[str]] = {}
    for provenance in CASES.glob("*/PROVENANCE.md"):
        text = provenance.read_text(encoding="utf-8").lower()
        hits = [token for token in forbidden if token in text]
        if hits:
            offenders[provenance.parent.name] = hits
    assert offenders == {}


def test_paper_facing_contract_uses_batched_async_and_drs() -> None:
    protocol = (ROOT / "PROTOCOL.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    contract = json.loads((ROOT / "evaluation_contract.json").read_text(encoding="utf-8"))

    assert "Batched (`linear`)" in protocol
    assert "Dynamic Replanning Score" in protocol
    assert "DTScore =" not in protocol
    assert "Batched" in readme and "Async" in readme
    assert contract["execution_mode_labels"] == {"linear": "Batched", "async": "Async"}
    assert contract["primary_metrics"] == [
        "batched_task_success",
        "async_task_success",
        "async_dynamic_replanning_score",
    ]


def test_repository_has_publishable_license_and_source_notices() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Apache License" in license_text
    for source in ("GAIA2", "MultiAgentBench", "OSWorld", "SWE-bench", "Terminal-Bench"):
        assert source in notice
