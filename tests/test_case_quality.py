from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from async_rbench.case_quality import validate_case_quality
from async_rbench.retrospective_quality import build_retrospective_quality_audit
from async_rbench.spec import discover_case_instances

from author_local import requires_author_local


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "candidate_cases/nginx-live-port-conflict"
_CANDIDATE = requires_author_local("candidate_cases/nginx-live-port-conflict")


@_CANDIDATE
def test_nginx_candidate_quality_contract_is_complete() -> None:
    assert validate_case_quality(ROOT, SOURCE, require_contract=True) == []


@_CANDIDATE
def test_quality_gate_detects_public_instruction_loss(tmp_path: Path) -> None:
    candidate = tmp_path / "nginx-live-port-conflict"
    shutil.copytree(SOURCE, candidate)
    task_path = candidate / "task/task.yaml"
    task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    task["instruction"] = task["instruction"].replace(
        '"Welcome to the benchmark webserver"', '"A generic page"',
    )
    task_path.write_text(yaml.safe_dump(task, sort_keys=False), encoding="utf-8")
    errors = validate_case_quality(ROOT, candidate, require_contract=True)
    assert any("source instruction is not preserved verbatim" in error for error in errors)
    assert any("Welcome to the benchmark webserver" in error for error in errors)


@_CANDIDATE
def test_quality_gate_detects_uncovered_semantic_point(tmp_path: Path) -> None:
    candidate = tmp_path / "nginx-live-port-conflict"
    shutil.copytree(SOURCE, candidate)
    contract_path = candidate / "private/quality_contract.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    for requirement in contract["requirements"]:
        checks = requirement.get("covers", {}).get("semantic_checks", [])
        if "np.runtime.index" in checks:
            checks.remove("np.runtime.index")
    contract_path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    errors = validate_case_quality(ROOT, candidate, require_contract=True)
    assert any("np.runtime.index" in error for error in errors)


@_CANDIDATE
def test_quality_gate_requires_noncanonical_solution(tmp_path: Path) -> None:
    candidate = tmp_path / "nginx-live-port-conflict"
    shutil.copytree(SOURCE, candidate)
    contract_path = candidate / "private/quality_contract.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    contract["equivalence_solutions"] = []
    contract_path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    errors = validate_case_quality(ROOT, candidate, require_contract=True)
    assert any("at least one equivalence solution" in error for error in errors)


@_CANDIDATE
def test_quality_gate_rejects_arbitrary_file_as_public_evidence(tmp_path: Path) -> None:
    candidate = tmp_path / "nginx-live-port-conflict"
    shutil.copytree(SOURCE, candidate)
    decoy = candidate / "author_notes.txt"
    decoy.write_text("Welcome to the benchmark webserver", encoding="utf-8")
    contract_path = candidate / "private/quality_contract.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    contract["requirements"][0]["public_evidence"][0] = {
        "path": "author_notes.txt", "contains": "Welcome to the benchmark webserver",
    }
    contract_path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    errors = validate_case_quality(ROOT, candidate, require_contract=True)
    assert any("not an allowed participant-visible contract" in error for error in errors)


@_CANDIDATE
def test_requirements_manifest_needs_source_anchors_and_human_approval(tmp_path: Path) -> None:
    candidate = tmp_path / "nginx-live-port-conflict"
    shutil.copytree(SOURCE, candidate)
    contract_path = candidate / "private/quality_contract.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    contract["source_contract"]["instruction_preservation"] = "requirements_manifest"
    contract_path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    errors = validate_case_quality(ROOT, candidate, require_contract=True)
    assert any("requires manifest_review" in error for error in errors)
    assert any("requirement_mappings must be non-empty" in error for error in errors)


def test_legacy_retrospective_audit_holds_every_uncontracted_seed() -> None:
    report = build_retrospective_quality_audit(ROOT, discover_case_instances(ROOT))
    assert report["registered_instance_count"] == 201
    assert report["eligible_for_execution_reaudit"] == 201
    assert report["held_for_retrofit"] == 0
    assert report["publication_ready"] is True
    assert sum(
        row["disposition"] == "hold_for_retrofit" for row in report["rows"]
    ) == 0
