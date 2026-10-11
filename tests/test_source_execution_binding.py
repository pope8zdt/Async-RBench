import json
from pathlib import Path

import pytest
import yaml

from async_rbench import release

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("source,old_source", [("gaia2", "MultiAgentBench"), ("terminal-bench", "OSWorld")])
def test_rebound_case_execution_matches_source_binding(tmp_path, source, old_source):
    (tmp_path / "public").mkdir()
    (tmp_path / "task/task_file").mkdir(parents=True)
    binding = {"benchmark": source, "source_task_id": "bound", "source_revision": "pinned"}
    (tmp_path / "public/source_binding.json").write_text(json.dumps(binding))
    (tmp_path / "task/task_file/source_task.json").write_text(json.dumps(binding))
    (tmp_path / "task/task_file/participant_task.json").write_text(json.dumps({"benchmark": old_source}))
    (tmp_path / "task/task.yaml").write_text(yaml.safe_dump({"runtime_status": "qualified"}))
    errors = release.validate_source_execution(tmp_path)
    assert any("participant source mismatch" in error for error in errors)


def test_runtime_pending_cannot_be_certified_as_executable():
    case = ROOT / "data/async-rbench/cases/mab-late-constraint-3a268eae01"
    assert any("runtime_pending" in error for error in release.validate_source_execution(case))


def test_current_rebound_materials_remain_explicitly_unqualified():
    cases = ROOT / "data/async-rbench/cases"
    bound = list(cases.glob("*/public/source_binding.json"))
    errors = [release.validate_source_execution(path.parent.parent) for path in bound]
    assert len(errors) == 46
    assert all(any("runtime_pending" in error for error in case_errors) for case_errors in errors)
    assert sum(any("participant source mismatch" in error for error in row) for row in errors) == 38
