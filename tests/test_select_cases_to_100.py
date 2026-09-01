from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.select_cases_to_100 import ROOT, build_selection


def test_selection_pipeline_closes_once_registry_exceeds_fixed_target() -> None:
    # The rebuild-to-100 selection pipeline is superseded: the registry grew from
    # 18 to 201 registered instances, past its fixed 100-task target distribution.
    registry = json.loads((ROOT / "cases/registry.json").read_text(encoding="utf-8"))
    registered = sum(len(f["instances"]) for f in registry["case_families"])
    assert registered > 100
    with pytest.raises(RuntimeError, match="registered distribution exceeds fixed target"):
        build_selection()
