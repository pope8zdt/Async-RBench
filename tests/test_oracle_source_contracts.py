from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scheduler_reference_packer_loads_authority_json(tmp_path: Path) -> None:
    path = (
        ROOT
        / "cases/scheduler-selective-replan/task/upstream_solutions/reference_packer.py"
    )
    spec = importlib.util.spec_from_file_location("dtb2_reference_packer", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = tmp_path / "authority.json"
    fixture.write_text('{"authority_receipt": "receipt-v2"}', encoding="utf-8")
    assert module.load_json(fixture) == {"authority_receipt": "receipt-v2"}


def test_data_recovery_verifier_accepts_upstream_unqualified_grpc_service() -> None:
    source = (
        ROOT
        / "cases/data-recovery-service/task/tests/test_case_outcomes.py"
    ).read_text(encoding="utf-8")
    assert 'service.full_name == "KVStore"' in source
