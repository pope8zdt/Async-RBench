from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from async_rbench.evaluation.manifest import create_manifest
from async_rbench.private_eval import verifier_bundle_sha256


def test_manifest_binds_the_explicit_external_judge(tmp_path: Path) -> None:
    judge_root = tmp_path / "judge"
    verifier = judge_root / "cases" / "data-recovery-service"
    (verifier / "tests").mkdir(parents=True)
    (verifier / "tests" / "test_marker.py").write_text("MARKER = 'private'\n", encoding="utf-8")
    (verifier / "run-tests.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    release = judge_root / "release.json"
    release.write_text('{"release_id":"synthetic"}\n', encoding="utf-8")

    manifest = create_manifest(
        ["data-recovery-service"],
        repetitions=1,
        guidance="incentive",
        seed=2026,
        execution_modes=["linear", "async"],
        model="paper-model",
        judge_root=judge_root,
    )

    key = "data-recovery-service::seed-1"
    assert manifest["verifier_bundle_sha256"][key] == verifier_bundle_sha256(verifier)
    assert manifest["judge_release_sha256"] == hashlib.sha256(release.read_bytes()).hexdigest()
    assert len(manifest["episodes"]) == 2


def test_manifest_refuses_an_implicit_judge_location() -> None:
    with pytest.raises(ValueError, match="explicit judge_root"):
        create_manifest(
            ["data-recovery-service"],
            repetitions=1,
            guidance="incentive",
            seed=2026,
        )
