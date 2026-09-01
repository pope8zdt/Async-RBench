from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

from async_rbench import cli


def _promotion_fixture(tmp_path, monkeypatch):
    (tmp_path / "cases").mkdir()
    candidate = tmp_path / "candidate_cases" / "demo-case"
    candidate.mkdir(parents=True)
    (candidate / "public_case.yaml").write_text("case_id: demo-case\n", encoding="utf-8")
    registry = {"schema_version": "2", "case_families": []}
    registry_text = json.dumps(registry, indent=2) + "\n"
    (tmp_path / "cases" / "registry.json").write_text(registry_text, encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(
        cli, "_case_promote_prechecks", lambda *_a, **_k: (registry, []),
    )
    monkeypatch.setattr(
        cli, "_candidate_case_promotion_eligibility", lambda *_a, **_k: (True, None),
    )
    monkeypatch.setattr(cli, "validate_relocatable_source_contract", lambda *_a, **_k: [])
    monkeypatch.setattr(cli, "validate_relocatable_source_native_lock", lambda *_a, **_k: [])
    monkeypatch.setattr(
        cli, "load_case",
        lambda *_: SimpleNamespace(raw={"source_tasks": [{"benchmark": "SWE-bench"}]}),
    )
    monkeypatch.setattr(cli, "normalize_case_benchmark", lambda *_: "swe-bench")
    monkeypatch.setattr(cli, "validate_case_registry", lambda *_: [])
    monkeypatch.setattr(cli, "validate_semantic_registries", lambda *_: [])
    monkeypatch.setattr(cli, "validate_mutation_manifest", lambda *_: [])
    monkeypatch.setattr(cli, "validate_case", lambda *_: [])
    monkeypatch.setattr(cli, "validate_case_quality", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "validate_sources", lambda *_: [])
    args = argparse.Namespace(
        candidate="demo-case", control_prefix="demo", dry_run=False, yes=True,
    )
    return args, candidate, registry_text


def test_case_promotion_assigns_calibration_split(tmp_path, monkeypatch):
    args, candidate, _ = _promotion_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "discover_cases", lambda *_: [])

    assert cli.cmd_case_promote(args) == 0

    payload = json.loads((tmp_path / "cases" / "registry.json").read_text(encoding="utf-8"))
    assert payload["case_families"][0]["instances"] == [
        {"instance_id": "seed-1", "path": ".", "split": "calibration"}
    ]
    assert not candidate.exists()
    assert (tmp_path / "cases" / "demo-case").is_dir()


def test_case_promotion_rolls_back_when_global_audit_raises(tmp_path, monkeypatch):
    args, candidate, registry_text = _promotion_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        cli, "discover_cases", lambda *_: (_ for _ in ()).throw(ValueError("bad split")),
    )

    assert cli.cmd_case_promote(args) == 1

    assert candidate.is_dir()
    assert not (tmp_path / "cases" / "demo-case").exists()
    assert (tmp_path / "cases" / "registry.json").read_text(encoding="utf-8") == registry_text
