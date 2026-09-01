from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "materialize_selected_case_blueprints.py"


def _module():
    spec = importlib.util.spec_from_file_location("materialize_selected_case_blueprints", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_materializes_one_private_safe_case_per_source(tmp_path: Path) -> None:
    module = _module()
    selection = json.loads(module.SELECTION.read_text(encoding="utf-8"))
    rows = module._audit_rows()
    chosen = []
    for benchmark in ("SWE-bench", "OSWorld", "MultiAgentBench"):
        chosen.append(next(item for item in selection["cases"] if item["benchmark"] == benchmark))

    for item in chosen:
        result = module.materialize(rows[item["case_id"]], tmp_path)
        case_dir = tmp_path / item["case_id"]
        assert result["status"] == "pending_source_native_implementation"
        assert (case_dir / "private/case_ir.json").is_file()
        assert (case_dir / "private/score_plan.json").is_file()
        assert (case_dir / "private/event_policy.json").is_file()
        assert (case_dir / "task/task_file/participant_task.json").is_file()
        load_case(case_dir / "public_case.yaml")
        status = json.loads((case_dir / "STATUS.json").read_text(encoding="utf-8"))
        assert status["registered"] is False
        assert status["runtime_executed"] is False
        task_files = {path.name for path in (case_dir / "task").rglob("*") if path.is_file()}
        assert "native_case.json" not in task_files
        assert "official_task.json" not in task_files
        assert "evaluation_binding.json" not in task_files
        instruction = (case_dir / "instruction.md").read_text(encoding="utf-8")
        event = rows[item["case_id"]]["case_ir_blueprint"]["event_contract"]
        assert event["before_state"] not in instruction
        assert event["after_state"] not in instruction
        assert "Authority rule:" not in instruction
        async_contract = json.loads(
            (case_dir / "task/task_file/async_contract.json").read_text(encoding="utf-8")
        )
        assert "event_id" not in async_contract
        assert "primary_event_theme" not in async_contract

    policies = {
        json.loads((path / "private/event_policy.json").read_text(encoding="utf-8"))["theme"]
        for path in tmp_path.iterdir()
        if path.is_dir()
    }
    assert policies
