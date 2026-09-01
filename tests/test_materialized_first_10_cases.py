from __future__ import annotations

import json
from pathlib import Path

import yaml

from async_rbench.case_ir import validate_case_ir, validate_score_plan
from async_rbench.case_quality import validate_case_quality
from async_rbench.evaluation.registry_audit import validate_case_registries
from async_rbench.evaluation.mutation_audit import validate_candidate_mutation_suite
from async_rbench.provenance import validate_sources
from async_rbench.spec import load_case, validate_case


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "candidate_cases" / "rebuild-batch-001"


def _cases() -> list[dict]:
    manifest = json.loads((BATCH / "batch-manifest.json").read_text(encoding="utf-8"))
    assert manifest["case_count"] == 10
    return manifest["cases"]


def test_first_ten_are_complete_static_case_packages() -> None:
    errors: list[str] = []
    control_prefixes: list[str] = []
    for item in _cases():
        case_dir = BATCH / item["case_id"]
        spec = load_case(case_dir / "public_case.yaml")
        errors.extend(f"{item['case_id']}: {value}" for value in validate_case(spec))
        errors.extend(f"{item['case_id']}: {value}" for value in validate_sources(ROOT, [spec]))
        errors.extend(
            f"{item['case_id']}: {value}"
            for value in validate_case_quality(ROOT, case_dir, require_contract=True)
        )
        semantic_path = case_dir / "task/tests/semantic_checks.json"
        control_path = case_dir / "task/tests/control_flow_checks.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        prefix = str(control["checks"][0]["id"]).split(".cf.", 1)[0]
        control_prefixes.append(prefix)
        errors.extend(
            f"{item['case_id']}: {value}"
            for value in validate_case_registries(
                {
                    **spec.raw,
                    "_registry_path": str(semantic_path),
                    "_control_path": str(control_path),
                },
                prefix,
            )
        )
        errors.extend(
            f"{item['case_id']}: {value}"
            for value in validate_candidate_mutation_suite(
                ROOT, case_dir, str(item["case_id"])
            )
        )
    assert len(control_prefixes) == len(set(control_prefixes))
    assert not errors, "\n".join(errors)


def test_first_ten_use_content_derived_scoring_and_case_ir() -> None:
    semantic_counts: list[int] = []
    control_counts: list[int] = []
    for item in _cases():
        case_dir = BATCH / item["case_id"]
        semantic = json.loads((case_dir / "task/tests/semantic_checks.json").read_text(encoding="utf-8"))
        control = json.loads((case_dir / "task/tests/control_flow_checks.json").read_text(encoding="utf-8"))
        case_ir = json.loads((case_dir / "private/case_ir.json").read_text(encoding="utf-8"))
        score_plan = json.loads((case_dir / "private/score_plan.json").read_text(encoding="utf-8"))
        assert not validate_case_ir(case_ir)
        assert not validate_score_plan(score_plan)
        assert len({point["id"] for point in semantic["checks"]}) == len(semantic["checks"])
        assert len({point["pytest_node"] for point in semantic["checks"]}) == len(semantic["checks"])
        assert len({point["primary_evidence"] for point in control["checks"]}) == len(control["checks"])
        assert 1 <= len(spec := load_case(case_dir / "public_case.yaml").raw["source_tasks"]) <= 4
        assert 2 <= len(load_case(case_dir / "public_case.yaml").raw["delegation_workstreams"]) <= 4
        semantic_counts.append(len(semantic["checks"]))
        control_counts.append(len(control["checks"]))
    assert len(set(semantic_counts)) > 1
    assert set(control_counts) == {3, 4}
    assert 24 not in semantic_counts


def test_evaluator_material_is_not_baked_into_participant_images() -> None:
    for item in _cases():
        task = BATCH / item["case_id"] / "task"
        ignored = set((task / ".dockerignore").read_text(encoding="utf-8").splitlines())
        assert {"tests", "upstream_solutions", "equivalence_solutions", "negative_mutations", "oracle.sh", "run-tests.sh"} <= ignored
        assert (task / "upstream_solutions").is_dir()
        assert (task / "tests/test_case_outcomes.py").is_file()
        assert (task / "task_file/scripts/event_worker.py").is_file()
        source_instance = task / "task_file/source_instance.json"
        if source_instance.is_file():
            visible = json.loads(source_instance.read_text(encoding="utf-8"))
            assert "patch" not in visible and "test_patch" not in visible


def test_first_ten_bind_causal_root_to_authority_delivery() -> None:
    for package_root in (BATCH, ROOT / "cases"):
        for item in _cases():
            case_dir = package_root / item["case_id"]
            private = yaml.safe_load(
                (case_dir / "private/private_case.yaml").read_text(encoding="utf-8")
            )
            contracts = private["event_contracts"]
            assert len(contracts) == 1
            event_id = contracts[0]["event_id"]
            authority_kind = private["authoritative_result_kind"]
            root_events = [
                event
                for event in private["scenarios"]["async"]["events"]
                if event["id"] == event_id
            ]
            assert len(root_events) == 1
            root_event = root_events[0]
            assert root_event["result"] == authority_kind
            assert root_event["invalidates_artifacts"]
            assert root_event["reopens_milestones"]
            authority_events = [
                event
                for event in private["scenarios"]["async"]["events"]
                if event.get("result") == authority_kind
            ]
            assert authority_events == [root_event]


def test_first_ten_control_points_do_not_double_penalise_semantics() -> None:
    for package_root in (BATCH, ROOT / "cases"):
        for item in _cases():
            control = json.loads(
                (
                    package_root
                    / item["case_id"]
                    / "task/tests/control_flow_checks.json"
                ).read_text(encoding="utf-8")
            )
            assert control["checks"]
            assert all(
                point.get("requires_outcome_anchor") is False
                for point in control["checks"]
            )
            assert all(
                point.get("precondition_contract", {}).get("on_missing") == "fail_point"
                for point in control["checks"]
            )
