import json
from pathlib import Path

from async_rbench.dynamic_pilot import build_dynamic_pilot_batch

from author_local import requires_author_local


ROOT = Path(__file__).resolve().parents[1]
pytestmark = requires_author_local(
    "candidate_instances/gaia2-stockholm-moveout/gaia2-zip-revision-sim-001",
)


def test_review_is_a_hard_input_to_case_production(tmp_path: Path) -> None:
    output = tmp_path / "pilot"
    report = build_dynamic_pilot_batch(ROOT, output)

    assert report["stage_order"] == [
        "agent_screening",
        "simulated_human_review",
        "case_production",
        "static_validation",
        "runtime_preflight",
        "linear_feasibility",
        "dual_model_experiment",
        "final_audit",
    ]
    assert (output / "01-agent-screening/screening.jsonl").is_file()
    assert (output / "02-simulated-human-review/simulated-review.jsonl").is_file()
    assert (output / "03-case-production/cases").is_dir()
    assert (output / "04-static-validation/static-gate.json").is_file()
    assert report["stage_status"]["runtime_preflight"] == "pending"
    nginx = next(
        row for row in report["cases"]
        if row["pilot_id"] == "pilot-nginx-live-authority-001"
    )
    private = __import__("yaml").safe_load(
        (Path(nginx["case_dir"]) / "private/private_case.yaml").read_text(
            encoding="utf-8"
        )
    )
    authority = next(
        event for event in private["scenarios"]["async"]["events"]
        if event["id"] == "np_a_port"
    )
    assert authority["intervention"]["required_changed_artifacts"] == ["runtime_state"]

    reviews = {
        row["candidate_id"]: row
        for row in (
            json.loads(line)
            for line in (output / "02-simulated-human-review/simulated-review.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    }
    for case in report["cases"]:
        review = reviews[case["pilot_id"]]
        assert review["decision"] == "candidate_confirmed"
        assert case["production_gate"]["human_review_confirmed"] is True
        assert (
            case["production_gate"]["human_review_record_sha256"]
            == report_case_review_hash(case, output)
        )


def report_case_review_hash(case: dict, output: Path) -> str:
    design = json.loads(
        (output / "03-case-production/designs" / f"{case['pilot_id']}.json")
        .read_text(encoding="utf-8")
    )
    return design["production_inputs"]["human_review_sha256"]
