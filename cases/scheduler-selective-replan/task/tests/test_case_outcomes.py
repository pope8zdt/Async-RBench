"""Frozen semantic outcome checks for the scheduler selective-replan case.

Each registered pytest function is one leaderboard point. The tests read the
submitted plan files, the first-pass preservation snapshots, and the
decision manifest under /app/task_file/output_data, plus the request fixtures
under /app/task_file/input_data. The shared public validator and cost model in
/app/task_file/scripts are reused so the participant and the verifier agree.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

TASK = Path(os.environ.get("ASYNC_RBENCH_TASK_ROOT", "/app/task_file"))
sys.path.insert(0, str(TASK / "scripts"))
from cost_model import CostModel  # noqa: E402
from validate_plan import THRESHOLDS, load_plan, load_requests  # noqa: E402
INPUT = TASK / "input_data"
OUTPUT = TASK / "output_data"
BUDGET = 8
AUTHORITY_RECEIPT = "sc-bucket2-authority-91d7a63e5b284f10"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _requests(bucket: int) -> dict[str, dict]:
    return load_requests(INPUT / f"requests_bucket_{bucket}.jsonl")


def _plan(bucket: int) -> list[dict]:
    return load_plan(OUTPUT / f"plan_b{bucket}.jsonl")[0]


def _manifest() -> dict:
    return _json(OUTPUT / "decision_manifest.json")


def _metrics(bucket: int) -> dict:
    plan = _plan(bucket)
    return CostModel(64).plan_metrics(_requests(bucket), plan)


def _shapes(bucket: int) -> set:
    _, by_batch = load_plan(OUTPUT / f"plan_b{bucket}.jsonl")
    return {
        (shape["seq_align"], shape["heads_align"], shape["hidden_align"])
        for shape in by_batch.values()
    }


# ---- base_task_completion (s1) ------------------------------------------
def test_plan_files_exist():
    assert (OUTPUT / "plan_b1.jsonl").is_file()
    assert (OUTPUT / "plan_b2.jsonl").is_file()


def test_plan_jsonl_valid():
    for bucket in (1, 2):
        for line in (OUTPUT / f"plan_b{bucket}.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            assert entry["request_id"] and entry["batch_id"]
            assert set(entry["shape"]) == {"seq_align", "heads_align", "hidden_align"}


def test_all_requests_covered_exactly():
    for bucket in (1, 2):
        req_ids = set(_requests(bucket))
        plan_ids = {entry["request_id"] for entry in _plan(bucket)}
        assert plan_ids == req_ids


def test_shape_fields_valid():
    for bucket in (1, 2):
        reqs = _requests(bucket)
        _, by_batch = load_plan(OUTPUT / f"plan_b{bucket}.jsonl")
        for entry in _plan(bucket):
            shape = entry["shape"]
            need = ((int(reqs[entry["request_id"]]["prompt_len"]) + 63) // 64) * 64
            assert shape["seq_align"] % 64 == 0
            assert shape["seq_align"] >= need
            assert shape["heads_align"] == 32
            assert shape["hidden_align"] == 4096


# ---- preservation of the passing bucket (s2) -----------------------------
def test_preservation_snapshot_exists():
    assert (OUTPUT / "first_pass" / "plan_b1.jsonl").is_file()
    assert (OUTPUT / "first_pass" / "plan_b2.jsonl").is_file()


def test_preserved_bucket_final_matches_snapshot():
    manifest = _manifest()
    preserved = manifest["preserved_bucket"]
    n = 1 if preserved == "bucket1" else 2
    assert _sha256(OUTPUT / f"plan_b{n}.jsonl") == _sha256(
        OUTPUT / "first_pass" / f"plan_b{n}.jsonl"
    )


def test_manifest_names_preserved_bucket():
    manifest = _manifest()
    assert manifest["preserved_bucket"] in {"bucket1", "bucket2"}
    assert manifest["preserved_bucket_final_sha256"] == _sha256(
        OUTPUT / f"plan_b{1 if manifest['preserved_bucket'] == 'bucket1' else 2}.jsonl"
    )


def test_preserved_bucket_plan_valid():
    manifest = _manifest()
    n = 1 if manifest["preserved_bucket"] == "bucket1" else 2
    reqs = _requests(n)
    plan = _plan(n)
    for entry in plan:
        shape = entry["shape"]
        need = ((int(reqs[entry["request_id"]]["prompt_len"]) + 63) // 64) * 64
        assert shape["seq_align"] >= need


# ---- selective replan of the failing bucket (s3) -------------------------
def test_replanned_bucket_differs_from_snapshot():
    manifest = _manifest()
    assert manifest["authority_receipt"] == AUTHORITY_RECEIPT
    assert _json(OUTPUT / "validator_reports" / "bucket2.json")[
        "authority_receipt"
    ] == AUTHORITY_RECEIPT
    replanned = manifest["replanned_bucket"]
    n = 1 if replanned == "bucket1" else 2
    assert _sha256(OUTPUT / f"plan_b{n}.jsonl") != _sha256(
        OUTPUT / "first_pass" / f"plan_b{n}.jsonl"
    )


def test_replanned_bucket_coverage():
    manifest = _manifest()
    n = 1 if manifest["replanned_bucket"] == "bucket1" else 2
    reqs = _requests(n)
    for entry in _plan(n):
        shape = entry["shape"]
        need = ((int(reqs[entry["request_id"]]["prompt_len"]) + 63) // 64) * 64
        assert shape["seq_align"] >= need


def test_replanned_bucket_pad_threshold():
    manifest = _manifest()
    n = 1 if manifest["replanned_bucket"] == "bucket1" else 2
    name = f"bucket{n}"
    assert _metrics(n)["pad_ratio"] <= THRESHOLDS[name]["pad_ratio"]


def test_replanned_bucket_cost_threshold():
    manifest = _manifest()
    n = 1 if manifest["replanned_bucket"] == "bucket1" else 2
    name = f"bucket{n}"
    assert _metrics(n)["cost"] <= THRESHOLDS[name]["cost"]


# ---- global constraint (s4) ----------------------------------------------
def test_max_shapes_respected():
    combined = _shapes(1) | _shapes(2)
    assert len(combined) <= BUDGET


def test_bucket1_thresholds():
    metrics = _metrics(1)
    assert metrics["cost"] <= THRESHOLDS["bucket1"]["cost"]
    assert metrics["pad_ratio"] <= THRESHOLDS["bucket1"]["pad_ratio"]
    assert metrics["p95_latency_ms"] <= THRESHOLDS["bucket1"]["p95_ms"]
    assert metrics["sequential_timecost"] <= THRESHOLDS["bucket1"]["seq_ms"]


def test_bucket2_thresholds():
    metrics = _metrics(2)
    assert metrics["cost"] <= THRESHOLDS["bucket2"]["cost"]
    assert metrics["pad_ratio"] <= THRESHOLDS["bucket2"]["pad_ratio"]
    assert metrics["p95_latency_ms"] <= THRESHOLDS["bucket2"]["p95_ms"]
    assert metrics["sequential_timecost"] <= THRESHOLDS["bucket2"]["seq_ms"]


def test_global_shape_set_matches_actual():
    combined = sorted(_shapes(1) | _shapes(2))
    committed = _json(OUTPUT / "global_shape_plan.json")
    reported = [tuple(shape) for shape in committed["global_shape_set"]]
    assert sorted(reported) == combined


def test_combined_unique_shape_count_reported():
    combined = len(_shapes(1) | _shapes(2))
    committed = _json(OUTPUT / "global_shape_plan.json")
    assert committed["combined_unique_shapes"] == combined


def test_no_missing_or_duplicate_requests_global():
    seen = []
    for bucket in (1, 2):
        seen.extend(entry["request_id"] for entry in _plan(bucket))
    assert len(seen) == len(set(seen))
    all_expected = set(_requests(1)) | set(_requests(2))
    assert set(seen) == all_expected


# ---- consistency closure (s5) --------------------------------------------
def test_both_validator_reports_pass():
    manifest = _manifest()
    assert manifest["validator_results"] == {"bucket1": "pass", "bucket2": "pass"}


def test_manifest_wait_for_all_validators():
    assert _manifest()["wait_for_all_validators"] is True


def test_manifest_closure_verified():
    assert _manifest()["closure_verified"] is True


def test_full_recompute_both_buckets_pass():
    # Recompute independently from the shared validator semantics.
    for bucket, name in ((1, "bucket1"), (2, "bucket2")):
        metrics = _metrics(bucket)
        thr = THRESHOLDS[name]
        assert metrics["cost"] <= thr["cost"]
        assert metrics["pad_ratio"] <= thr["pad_ratio"]
        assert metrics["p95_latency_ms"] <= thr["p95_ms"]
        assert metrics["sequential_timecost"] <= thr["seq_ms"]


def test_manifest_preservation_hashes_consistent():
    manifest = _manifest()
    preserved = manifest["preserved_bucket"]
    pn = 1 if preserved == "bucket1" else 2
    assert manifest["preserved_bucket_first_pass_sha256"] == _sha256(
        OUTPUT / "first_pass" / f"plan_b{pn}.jsonl"
    )
    assert manifest["preserved_bucket_final_sha256"] == _sha256(
        OUTPUT / f"plan_b{pn}.jsonl"
    )


def test_manifest_replan_hashes_consistent():
    manifest = _manifest()
    replanned = manifest["replanned_bucket"]
    rn = 1 if replanned == "bucket1" else 2
    assert manifest["replanned_bucket_first_pass_sha256"] == _sha256(
        OUTPUT / "first_pass" / f"plan_b{rn}.jsonl"
    )
    assert manifest["replanned_bucket_final_sha256"] == _sha256(
        OUTPUT / f"plan_b{rn}.jsonl"
    )
