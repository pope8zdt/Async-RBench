from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from async_rbench.release import build_public_release, validate_paper_invariants


ROOT = Path(__file__).resolve().parents[1]


def _public_leaks() -> list[Path]:
    cases = ROOT / "data" / "async-rbench" / "cases"
    private_paths = (
        "evaluator",
        "task/tests",
        "task/equivalence_solutions",
        "task/negative_mutations",
        "task/upstream_solutions",
        "task/oracle.sh",
        "task/run-tests.sh",
        "STATUS.json",
        "mutation_families.json",
    )
    return [
        case_dir / relative
        for case_dir in cases.iterdir()
        if case_dir.is_dir()
        for relative in private_paths
        if (case_dir / relative).exists()
    ]


def test_public_release_has_required_documents_and_no_private_case_paths() -> None:
    for name in ("README.md", "CITATION.cff", "NOTICE"):
        assert (ROOT / name).is_file(), name
    for name in ("contributing.md", "security.md", "protocol.md", "adapter-protocol.md"):
        assert (ROOT / "docs" / name).is_file(), name
    for name in (
        "CONTRIBUTING.md",
        "SECURITY.md",
        "PROTOCOL.md",
        "ADAPTER_PROTOCOL.md",
        "dataset_policy.json",
        "evaluation_contract.json",
    ):
        assert not (ROOT / name).exists(), name
    assert len(list((ROOT / "data" / "async-rbench" / "cases").iterdir())) == 200
    assert _public_leaks() == []


def test_frozen_public_manifest_matches_current_200_task_corpus() -> None:
    path = ROOT / "data" / "async-rbench" / "release.json"
    frozen = json.loads(path.read_text(encoding="utf-8"))
    current = build_public_release(ROOT)
    assert frozen == current.to_dict()
    assert validate_paper_invariants(current) == []


def test_release_visible_documents_do_not_contain_local_absolute_paths() -> None:
    files = [ROOT / "README.md", ROOT / "NOTICE"]
    files.extend((ROOT / "docs").glob("*.md"))
    windows_absolute = re.compile(r"(?i)(?:^|[\s`(])[a-z]:\\")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not windows_absolute.search(text), path


@pytest.mark.xfail(
    not (ROOT / "LICENSE").is_file(),
    reason="owner action required: select and add the project license before public redistribution",
    strict=True,
)
def test_repository_owner_selected_project_license() -> None:
    assert (ROOT / "LICENSE").is_file()
