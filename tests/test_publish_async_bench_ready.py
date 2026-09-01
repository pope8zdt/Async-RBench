from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish_async_bench_ready.py"


def test_ready_manifest_is_unique_and_revisioned(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("publish_async_bench_ready", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.INTAKE = tmp_path / "intake"
    module.READY = module.INTAKE / "ready.jsonl"
    module.LOCK = module.INTAKE / "ready.lock"
    module.SCHEMA = module.INTAKE / "ready.schema.json"
    case = tmp_path / "case-a"
    case.mkdir()
    for relative in module.REQUIRED_CASE_FILES:
        path = case / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    checks = {
        "validate": "passed",
        "candidate_family_pair_smoke": "passed",
        "case_promote_dry_run": "passed",
    }
    first = module.publish(
        case_id="case-a",
        case_path=case,
        source_category="SWE-bench",
        static_checks=checks,
        revision=1,
        control_prefix="case_a_cf",
    )
    assert first["revision"] == 1
    with pytest.raises(ValueError):
        module.publish(
            case_id="case-a",
            case_path=case,
            source_category="SWE-bench",
            static_checks=checks,
            revision=1,
            control_prefix="case_a_cf",
        )
    second = module.publish(
        case_id="case-a",
        case_path=case,
        source_category="SWE-bench",
        static_checks=checks,
        revision=2,
        control_prefix="case_a_cf",
    )
    records = [json.loads(line) for line in module.READY.read_text(encoding="utf-8").splitlines()]
    assert [record["revision"] for record in records] == [1, 2]
    assert second["bundle_sha256"] == first["bundle_sha256"]
