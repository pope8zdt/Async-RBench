"""Frozen semantic outcome checks for the swe-bench-selective-patch case.

Each registered pytest function is one leaderboard point. The tests read the
participant's module-group reports, fix records, integration record, regression
record and decision manifest under /app/output_data, plus the fix target and the
build-time base-revision manifest under /app/task_file/src. The manifest is a
self-report; these tests cross-check every manifest claim against the actual
artifacts, file hashes and on-disk state so a hand-written manifest cannot pass
alone.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

OUT = Path("/app/output_data")
AUTHORITY_RECEIPT = "sp2-fix-authority-c34a8e217d5946bf"
GROUPS = OUT / "module_groups"
SRC = Path("/app/task_file/src")
SKLEARN = SRC / "sklearn"
FIX_TARGET = SKLEARN / "utils" / "multiclass.py"
BASE_MANIFEST = SRC / "BASE_MANIFEST.json"

# The verifier itself does not import sklearn (the committed clone keeps only
# participant material); the importability check re-adds the source path so a
# plain interpreter import resolves the trimmed package.
SRC_PATH = str(SRC)
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict:
    return _json(OUT / "decision_manifest.json")


def _base_manifest() -> dict:
    return _json(BASE_MANIFEST)


def _group_report(group: str) -> dict:
    return _json(GROUPS / f"{group}_result.json")


# ---- base_task_completion (sp2.base) ---------------------------------------
def test_package_importable():
    from sklearn.metrics import confusion_matrix  # noqa: F401
    from sklearn.preprocessing import LabelBinarizer  # noqa: F401
    from sklearn.utils.multiclass import type_of_target, unique_labels  # noqa: F401

    assert callable(confusion_matrix)
    assert callable(LabelBinarizer)
    assert callable(type_of_target)
    assert callable(unique_labels)


def test_fix_applied():
    manifest = _manifest()
    current = _sha256(FIX_TARGET)
    actual_base = _base_manifest()["utils/multiclass.py"]
    assert manifest["base_fix_revision"] == actual_base
    assert current != actual_base
    assert current == manifest["final_fix_revision"]
    applied = _json(OUT / "applied_fix.json")
    assert applied["fix_revision"] == current
    assert applied["authority_receipt"] == AUTHORITY_RECEIPT
    assert manifest["authority_receipt"] == AUTHORITY_RECEIPT


def test_reports_exist():
    for path in (
        GROUPS / "A_result.json",
        GROUPS / "B_result.json",
        GROUPS / "C_result.json",
        OUT / "integrated_fix.json",
        OUT / "regression_result.json",
        OUT / "applied_fix.json",
        OUT / "decision_manifest.json",
    ):
        assert path.is_file(), path


def test_manifest_valid():
    manifest = _manifest()
    for key in (
        "case_id",
        "authoritative_result_kind",
        "superseded_result_kind",
        "base_fix_revision",
        "final_fix_revision",
        "module_groups",
        "failed_groups",
        "repair_applied",
        "passing_branches_preserved",
        "waited_for_all_groups",
        "regression_passed",
        "regression_revision",
    ):
        assert key in manifest, key


# ---- async_result_integration (sp2.integ) ----------------------------------
def test_a_group_passes():
    assert _group_report("A")["passed"] is True


def test_c_group_passes():
    assert _group_report("C")["passed"] is True


def test_a_run_revision_consistent():
    manifest = _manifest()
    assert _group_report("A")["run_revision"] == manifest["final_fix_revision"]


def test_c_run_revision_consistent():
    manifest = _manifest()
    assert _group_report("C")["run_revision"] == manifest["final_fix_revision"]


def test_a_branch_preserved():
    base = _base_manifest()
    manifest = _manifest()
    rel = "metrics/_classification.py"
    assert manifest["preserved_modules"][rel] == base[rel]
    assert _sha256(SKLEARN / rel) == base[rel]


def test_c_branch_preserved():
    base = _base_manifest()
    manifest = _manifest()
    rel = "preprocessing/_label.py"
    assert manifest["preserved_modules"][rel] == base[rel]
    assert _sha256(SKLEARN / rel) == base[rel]


# ---- async_dynamic_replanning (sp2.repair) ---------------------------------
def test_b_first_failure_recorded():
    initial = _json(GROUPS / "B_result_initial.json")
    assert initial["group"] == "B"
    assert initial["passed"] is False


def test_b_repair_applied():
    manifest = _manifest()
    assert manifest["failed_groups"] == ["B"]
    assert manifest["module_groups"]["B"]["first"] == "fail"
    assert manifest["module_groups"]["B"]["final"] == "pass"
    assert manifest["final_fix_revision"] != manifest["base_fix_revision"]
    assert manifest["repair_applied"] is True


def test_b_group_passes_final():
    assert _group_report("B")["passed"] is True


def test_repair_selective_single_file():
    manifest = _manifest()
    assert set(manifest["changed_files_final"]) <= {"utils/multiclass.py"}
    assert "utils/multiclass.py" in manifest["changed_files_final"]
    assert set(manifest["changed_files_initial"]) <= {"utils/multiclass.py"}


def test_passing_branches_preserved_recorded():
    manifest = _manifest()
    assert manifest["module_groups"]["A"]["first"] == "pass"
    assert manifest["module_groups"]["C"]["first"] == "pass"
    assert manifest["module_groups"]["B"]["first"] == "fail"
    assert set(manifest["passing_branches_preserved"]) == {"A", "C"}


def test_b_run_revision_final():
    manifest = _manifest()
    report = _group_report("B")
    assert report["run_revision"] == manifest["final_fix_revision"]
    assert manifest["repair_revision"] == manifest["final_fix_revision"]


# ---- async_consistency_closure (sp2.closure) -------------------------------
def test_all_groups_pass_final():
    manifest = _manifest()
    for group in ("A", "B", "C"):
        assert manifest["module_groups"][group]["final"] == "pass", group


def test_regression_passes():
    regression = _json(OUT / "regression_result.json")
    manifest = _manifest()
    assert regression["passed"] is True
    assert manifest["regression_passed"] is True


def test_regression_covers_all_groups():
    regression = _json(OUT / "regression_result.json")
    for test_file in (
        "test_classification.py",
        "test_label.py",
        "test_multiclass.py",
        "test_smoke.py",
    ):
        assert regression["groups"].get(test_file) == "pass", test_file


def test_manifest_matches_reports():
    manifest = _manifest()
    for group in ("A", "B", "C"):
        report = _group_report(group)
        assert (report["passed"] is True) == (
            manifest["module_groups"][group]["final"] == "pass"
        ), group


def test_waited_for_all_groups():
    manifest = _manifest()
    assert manifest["waited_for_all_groups"] is True
    assert manifest["regression_passed"] is True


def test_regression_revision_final():
    regression = _json(OUT / "regression_result.json")
    manifest = _manifest()
    assert regression["regression_revision"] == manifest["final_fix_revision"]


def test_no_gold_patch_material():
    # The reference solution, oracle and private test runner are injected only
    # into isolated benchmark-maintenance / verifier clones; none may ship in
    # the participant tree under /app/task_file.
    for forbidden in (
        "/app/task_file/upstream_solutions",
        "/app/task_file/oracle.sh",
        "/app/task_file/run-tests.sh",
    ):
        assert not Path(forbidden).exists(), forbidden
    for path in Path("/app/task_file").rglob("*"):
        if path.is_file() and path.suffix in (".patch", ".diff"):
            raise AssertionError(f"unexpected patch/diff material: {path}")


def test_manifest_case_id():
    manifest = _manifest()
    assert manifest["case_id"] == "swe-bench-selective-patch"
    assert manifest["source_task_id"] == "scikit-learn__scikit-learn-25638"
    assert manifest["authoritative_result_kind"] == "applied_fix"
    assert manifest["superseded_result_kind"] == "module_group_B_result"
