from __future__ import annotations

import json
from pathlib import Path

from async_rbench.evaluation.manifest import create_manifest
from async_rbench.evaluation.case_bundle import case_bundle_sha256
from async_rbench.spec import (
    case_instance_key,
    discover_case_instances,
    load_case_registry,
    resolve_case_instance,
)


ROOT = Path(__file__).resolve().parents[1]


def test_registered_instances_include_one_seed_per_family() -> None:
    instances = discover_case_instances(ROOT)
    seed_instances = [item for item in instances if item.instance_id == "seed-1"]
    registry, errors = load_case_registry(ROOT)
    assert errors == []
    assert len(seed_instances) == len(registry["case_families"])
    assert (
        "secure-release", "tracebench-git-recovery-late-authority-001"
    ) in {(item.case_id, item.instance_id) for item in instances}
    for instance in instances:
        assert instance.contract_path.is_file()
        assert resolve_case_instance(
            ROOT, instance.case_id, instance.instance_id,
        ).case_dir == instance.case_dir


def test_manifest_enumerates_and_pins_registered_instances() -> None:
    manifest = create_manifest(["secure-release"], 2, "incentive", 2026)
    assert manifest["manifest_version"] == "4.0"
    registered = {
        (item.case_id, item.instance_id)
        for item in discover_case_instances(ROOT)
        if item.case_id == "secure-release"
    }
    assert {
        (episode["case_id"], episode["instance_id"])
        for episode in manifest["episodes"]
    } == registered
    assert len(manifest["episodes"]) == len(registered) * 2 * 2
    for case_id, instance_id in registered:
        key = case_instance_key(case_id, instance_id)
        assert len(manifest["case_bundle_sha256"][key]) == 64
        assert len(manifest["verifier_bundle_sha256"][key]) == 64


def test_manifest_can_select_one_registered_instance_key() -> None:
    manifest = create_manifest(
        [], 1, "incentive", 2026,
        instance_keys=["secure-release::seed-1"],
    )
    assert {item["case_id"] for item in manifest["episodes"]} == {"secure-release"}
    assert {item["instance_id"] for item in manifest["episodes"]} == {"seed-1"}


def test_registry_rejects_instance_path_escape(tmp_path: Path) -> None:
    registry_dir = tmp_path / "cases"
    registry_dir.mkdir()
    (registry_dir / "registry.json").write_text(json.dumps({
        "schema_version": "2",
        "case_families": [{
            "case_id": "family",
            "benchmark": "terminal-bench",
            "control_prefix": "f",
            "instances": [{"instance_id": "seed-1", "path": "../outside"}],
        }],
    }), encoding="utf-8")
    _, errors = load_case_registry(tmp_path)
    assert any("escapes its family directory" in error for error in errors)


def test_unknown_instance_fails_closed() -> None:
    try:
        resolve_case_instance(ROOT, "secure-release", "unregistered")
    except ValueError as exc:
        assert "unknown registered case instance" in str(exc)
    else:
        raise AssertionError("unregistered instance unexpectedly resolved")


def test_seed_digest_excludes_sibling_instances_but_includes_other_files(
    tmp_path: Path,
) -> None:
    family = tmp_path / "family"
    payload = family / "task" / "assets"
    payload.mkdir(parents=True)
    (payload / "input.txt").write_text("input", encoding="utf-8")
    (family / "public_case.yaml").write_text("case_id: family", encoding="utf-8")
    baseline = case_bundle_sha256(family)
    sibling = family / "instances" / "seed-2"
    sibling.mkdir(parents=True)
    (sibling / "anything.txt").write_text("sibling", encoding="utf-8")
    assert case_bundle_sha256(family) == baseline
    (family / "PROVENANCE.md").write_text("changed", encoding="utf-8")
    assert case_bundle_sha256(family) != baseline


def test_seed_digest_excludes_mutable_execution_evidence(tmp_path: Path) -> None:
    """STATUS.json / *.json.tmp are per-run evidence, not case content.

    The release gate rewrites STATUS.json (via a .json.tmp) on every pass.
    Hashing it would change the bundle digest on each run, so the digest-keyed
    gate resume could never skip an already-verified instance. Writing evidence
    files must leave the bundle digest stable.
    """
    family = tmp_path / "family"
    payload = family / "task" / "assets"
    payload.mkdir(parents=True)
    (payload / "input.txt").write_text("input", encoding="utf-8")
    (family / "public_case.yaml").write_text("case_id: family", encoding="utf-8")
    baseline = case_bundle_sha256(family)
    (family / "STATUS.json").write_text(
        json.dumps({"status": "unified_release_gate_passed"}),
        encoding="utf-8",
    )
    assert case_bundle_sha256(family) == baseline
    (family / "STATUS.json.tmp").write_text("partial", encoding="utf-8")
    assert case_bundle_sha256(family) == baseline
    (family / "public_case.yaml").write_text("case_id: changed", encoding="utf-8")
    assert case_bundle_sha256(family) != baseline
