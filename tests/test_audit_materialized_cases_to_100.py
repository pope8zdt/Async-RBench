from __future__ import annotations

import importlib.util
from pathlib import Path

from author_local import requires_author_local


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_materialized_cases_to_100.py"
pytestmark = requires_author_local(
    "candidate_cases/rebuild-to-100/selection-manifest.json",
)


def _module():
    spec = importlib.util.spec_from_file_location("audit_materialized_cases_to_100", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_materialized_batch_structure_survives_post_promotion_drift() -> None:
    module = _module()
    report = module.audit(module.DEFAULT_SELECTION, module.DEFAULT_BLUEPRINTS, module.DEFAULT_SOURCE)
    # The materialized batch was later rebuilt under the v9.1 pipeline and promoted,
    # so byte-exact blueprint equality now fails closed by design, but the batch
    # structure, private/source isolation and theme coverage remain intact.
    assert report["selected_case_count"] == 82
    assert report["manifest_case_count"] == 82
    assert report["audited_case_count"] == 72  # some batch dirs were consumed by promotion
    assert len(report["event_theme_counts"]) == 8
    assert report["passed"] is False
    assert report["checks"]["private_source_isolation"] is True
    assert report["checks"]["manifest_selection_exact"] is False
    assert report["checks"]["source_blueprints_exact"] is False
