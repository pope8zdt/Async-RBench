from pathlib import Path

from async_rbench.evaluation.mutation_audit import validate_mutation_manifest


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_mutation_manifest_covers_every_semantic_point() -> None:
    assert validate_mutation_manifest(ROOT) == []


def test_mutation_audit_reports_invalid_manifest_instead_of_raising(tmp_path: Path) -> None:
    manifest = tmp_path / "tests" / "verifier_mutations" / "mutation_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"policy": {"minimum_concrete_mutants_per_case": "many"}}')

    errors = validate_mutation_manifest(tmp_path)
    assert len(errors) == 1
    assert "policy counts must be integers" in errors[0]
