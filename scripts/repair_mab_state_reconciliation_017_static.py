"""Repair the static contracts for the database:017 source-native candidate.

This deliberately contains no runner, Docker, or MARBLE invocation.  It is a
repeatable packaging step for the candidate-side evidence contracts only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from async_rbench.case_quality import instruction_sha256


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-state-reconciliation-bda6dda56f"
SOURCE_ID = "database:017"
CASE = ROOT / "candidate_cases" / CASE_ID
SOURCE = ROOT / "artifacts/source-native-v4/cases/multiagentbench" / CASE_ID
EVENT_ID = "evt.db017.insert-authority"


def load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dump_yaml(path: Path, value) -> None:
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


def source_semantic(check_id: str, node: str, description: str, *, critical: bool = True) -> dict:
    return {
        "id": check_id,
        "capability_target": "base_task_completion",
        "category": "source_semantics",
        "critical": critical,
        "description": description,
        "measurement_type": "semantic",
        "pytest_node": node,
        "relevance_tier": "base",
    }


def control(
    index: str,
    decision: str,
    dimension: str,
    gate: str,
    expected: str,
    forbidden: str,
    anchor: str,
    fact: str,
    *,
    critical: bool,
) -> dict:
    check_id = f"mab_db017.cf.{index}_{decision}"
    return {
        "id": check_id,
        "independence_key": check_id,
        "capability_target": "async_dynamic_replanning",
        "category": "state_reconciliation_control",
        "critical": critical,
        "description": expected,
        "measurement_type": "control",
        "relevance_tier": "critical" if critical else "direct",
        "execution_modes": ["async"],
        "decision_group": f"{index}_{decision}",
        "dimension": dimension,
        "event_id": EVENT_ID,
        "stage_tag": dimension,
        "gate": gate,
        "gate_args": {
            "artifacts": ["provisional_checkpoint", "final_state"],
            "preserve_artifacts": ["preserved_source_facts"],
            "workstreams": ["requirement_worker_01", "requirement_worker_02"],
        },
        "mutation_family": gate,
        "mutation_id": f"mab_db017.mutation.{index}_{decision}",
        "obligation": decision,
        "expected_behavior": expected,
        "forbidden_behavior": forbidden,
        "precondition": "Evaluator-owned INSERT_LARGE_DATA authority delivery exists.",
        "precondition_contract": {"on_missing": "fail_point", "required_facts": ["authority_delivery"]},
        "primary_evidence": f"episode_trace:{dimension}:{decision}:{index}",
        "evidence_group": f"db017.{decision}",
        "evidence_spec": {"primary_fact": fact, "subject": "req.01.source_native_resolution"},
        "outcome_anchors": [anchor],
        "must_still_pass": ["mab_db017.sem.native_binding"],
        "requires_outcome_anchor": False,
        "task_requirement_id": "req.01.source_native_resolution",
    }


def family(identifier: str, description: str, must_fail: str, operation: str) -> dict:
    return {
        "id": identifier,
        "case_id": CASE_ID,
        "description": description,
        "must_fail": [must_fail],
        "operation": operation,
        "variants": [
            "omit_required_evidence",
            "corrupt_authoritative_value",
            "replay_provisional_state",
            "claim_completion_without_required_behavior",
        ],
    }


def main() -> None:
    manifests = CASE / "private/source_manifests"
    manifest_map = {
        "native_case.json": "01-native_case.json",
        "participant_task.json": "02-participant_task.json",
        "official_task.json": "03-official_task.json",
        "native_config.yaml": "04-native_config.yaml",
    }
    for source_name, target_name in manifest_map.items():
        (manifests / target_name).write_bytes((SOURCE / source_name).read_bytes())
    source_files = [f"private/source_manifests/{name}" for name in manifest_map.values()]
    dump_json(CASE / "private/source_lock.json", {
        "benchmark": "MultiAgentBench", "locked": True, "production_case_path": ".",
        "source_task_id": SOURCE_ID, "source_files": source_files,
        "source_file_sha256": {rel: hashlib.sha256((CASE / rel).read_bytes()).hexdigest() for rel in source_files},
    })

    semantic_checks = [
        source_semantic("mab_db017.sem.native_binding", "upstream_tests/test_outputs.py::test_source_native_binding", "The report is pinned to MultiAgentBench database:017 and the File Sharing System source task."),
        source_semantic("mab_db017.sem.insert_authority", "upstream_tests/test_outputs.py::test_insert_large_data_evidence_and_selected_set", "Authoritative evidence selects INSERT_LARGE_DATA from the source-native pg_stat_statements workload."),
        source_semantic("mab_db017.sem.native_digest", "upstream_tests/test_outputs.py::test_closure_uses_native_digest", "The closure binds the exact source record digest and the 100-thread, 20,000-row INSERT workload."),
        source_semantic("mab_db017.sem.probe_preservation", "test_case_outcomes.py::test_reconciliation_retracts_only_stale_join_branch", "Reconciliation retracts only provisional join explanations while retaining completed LOCK_CONTENTION and VACUUM probes."),
        source_semantic("mab_db017.sem.receipt_bound", "test_case_outcomes.py::test_native_checkpoint_precedes_authority", "The evaluator receipt is bound to the native checkpoint before its diagnosis is adopted."),
        {
            **source_semantic("mab_db017.sem.closure", "test_case_outcomes.py::test_receipt_bound_closure_rechecks_source_state", "Closure rechecks source-native state after reconciliation and cannot finish without the receipt."),
            "capability_target": "async_consistency_closure", "category": "closure", "relevance_tier": "critical",
        },
    ]
    dump_json(CASE / "task/tests/semantic_checks.json", {"version": "4", "checks": semantic_checks})

    controls = [
        control("01", "checkpoint_then_authority", "event_intake", "wait_for_authority", "Hold the provisional join diagnosis until the evaluator-owned INSERT_LARGE_DATA receipt arrives.", "Do not promote file-sharing join symptoms as final before native authority is observed.", "mab_db017.sem.receipt_bound", "authority_consumption", critical=True),
        control("02", "retract_stale_join", "state_revision", "reject_late_stale", "Retract both provisional join causes while preserving completed LOCK_CONTENTION and VACUUM probes.", "Do not erase valid probes or retain a provisional join cause after the authoritative INSERT result.", "mab_db017.sem.probe_preservation", "stale_result_decision", critical=False),
        control("03", "reverify_closure", "closure", "rederive_from_authority", "Rebuild the final cause matrix from the native INSERT evidence and reverify closure after action sequence three.", "Do not close from a stale provisional matrix or an unbound receipt.", "mab_db017.sem.closure", "closure_reverification", critical=True),
    ]
    event_contract = {
        "event_id": EVENT_ID, "event_theme": "conflicting_valid_results", "authority_source": "requirement_worker_02",
        "main_visible_before_delivery": False, "observation_mode": "gateway_only", "required_opportunities": ["authority_delivery"], "track": "atomic_event",
        "arrival_contract": {"after_artifacts": ["provisional_checkpoint", "preserved_source_facts"], "after_facts": ["authority_delivery"], "after_results": ["result_01"], "before_facts": ["provisional_checkpoint", "preserved_source_facts"]},
        "state_delta": {"before": "A provisional File Sharing System join diagnosis is persisted without native workload authority.", "after": "The authoritative INSERT_LARGE_DATA result retracts only provisional join causes and leaves completed probes intact.", "affected_artifacts": ["provisional_checkpoint", "final_state"], "unaffected_artifacts": ["preserved_source_facts"]},
    }
    dump_json(CASE / "task/tests/control_flow_checks.json", {"version": "7", "checks": controls, "event_contracts": [event_contract]})

    source_instruction = load(CASE / "private/source_task.yaml")["instruction"].strip()
    quality = {
        "schema_version": "1",
        "source_contract": {"instruction_preservation": "verbatim_append", "sources": [{"task_id": SOURCE_ID, "instruction_sha256": instruction_sha256(source_instruction), "task_path": "private/source_task.yaml"}]},
        "requirements": [{"id": "source_and_async_closure_contract", "public_evidence": [{"path": "task/task.yaml", "contains": "File Sharing System"}, {"path": "task/task.yaml", "contains": "INSERT_LARGE_DATA"}], "covers": {"semantic_checks": [item["id"] for item in semantic_checks], "dynamic_control_checks": [item["id"] for item in controls], "hidden_checks": ["receipt_bound_to_case", "closure_consumes_receipt"], "workstream_validators": ["requirement_worker_01", "requirement_worker_02"]}}],
        "equivalence_solutions": [{"id": "alternative-db017-reconciliation", "path": "task/equivalence_solutions/alternative_solution.sh", "distinguishes_from_oracle": "Independently emits the same receipt-bound state reconciliation rather than copying the oracle entrypoint."}],
        "negative_mutations": [
            {"id": "wrong-cause", "path": "task/negative_mutations/wrong_cause.sh", "must_fail": ["mab_db017.sem.insert_authority"]},
            {"id": "stale-join", "path": "task/negative_mutations/stale_join.sh", "must_fail": ["mab_db017.sem.probe_preservation"]},
            {"id": "forged-receipt", "path": "task/negative_mutations/forged_receipt.sh", "must_fail": ["mab_db017.sem.receipt_bound"]},
            {"id": "broken-closure", "path": "task/negative_mutations/broken_closure.sh", "must_fail": ["mab_db017.sem.closure"]},
        ],
    }
    dump_yaml(CASE / "private/quality_contract.yaml", quality)

    families = []
    for number, semantic in enumerate(semantic_checks, start=1):
        check_id = semantic["id"]
        stem = check_id.rsplit(".", 1)[-1]
        operation = "mutate_semantic_closure" if check_id.endswith(".closure") else "mutate_semantic_source_semantics"
        families.extend([
            family(f"mab_db017.mut.{number:02d}_{stem}", f"Directly challenge: {semantic['description']}", check_id, operation),
            family(f"mab_db017.mut.{number:02d}_{stem}_crosscheck", f"Cross-check independent source evidence for: {semantic['description']}", check_id, "cross_corrupt_closure_evidence" if check_id.endswith(".closure") else "cross_corrupt_source_semantics_evidence"),
        ])
    for number, check in enumerate(controls, start=20):
        gate = check["gate"]
        families.extend([
            family(f"mab_db017.mut.{number}_{check['obligation']}", f"Directly challenge: {check['expected_behavior']}", check["id"], f"mutate_control_{gate}"),
            family(f"mab_db017.mut.{number}_{check['obligation']}_crosscheck", f"Cross-check independent control evidence for: {check['expected_behavior']}", check["id"], f"cross_corrupt_{gate}_evidence"),
        ])
    dump_json(CASE / "mutation_families.json", {"version": "1", "families": families})

    private = load(CASE / "private/private_case.yaml")
    private["classification"]["primary_event_theme"] = "conflicting_valid_results"
    private["event_contracts"] = [event_contract]
    private["scenarios"]["async"]["events"][0]["id"] = f"{EVENT_ID}.provisional"
    private["scenarios"]["async"]["events"][1]["id"] = EVENT_ID
    # Child workspaces are intentionally isolated.  Gateway validators must
    # therefore validate a non-empty, schema-required completion receipt,
    # while the hidden verifier later audits the promoted main-workspace
    # authority receipt and closure.
    # Requiring the validator to open the child-only report path causes a
    # false authority-entry failure in consumer runs.
    private["workstream_bindings"]["requirement_worker_01"]["validator_command"] = (
        "python3 -c \"import base64,json,os; "
        "e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; "
        "f=e['finding']; assert isinstance(f,str) and f.strip()\""
    )
    private["workstream_bindings"]["requirement_worker_02"]["validator_command"] = (
        "python3 -c \"import base64,json,os; "
        "e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; "
        "f=e['finding']; assert isinstance(f,str) and f.strip()\""
    )
    dump_yaml(CASE / "private/private_case.yaml", private)

    policy = load(CASE / "private/event_policy.json")
    policy["event_id"] = EVENT_ID; policy["theme"] = "conflicting_valid_results"; policy["event_contract"] = {"event_id": EVENT_ID, "primary_event_theme": "conflicting_valid_results", "before_state": event_contract["state_delta"]["before"], "after_state": event_contract["state_delta"]["after"], "affected_nodes": ["event_input"], "unaffected_nodes": ["preserve_prior"], "affected_closure": ["event_input", "final_state"]}
    policy["required_decisions"] = ["checkpoint_then_authority", "retract_stale_join", "reverify_closure"]
    dump_json(CASE / "private/event_policy.json", policy)

    dump_json(CASE / "private/runtime_contract.json", {
        "case_id": CASE_ID, "source_task_id": SOURCE_ID,
        "docker_interpreters": ["/usr/local/bin/python3", "/usr/bin/bash"],
        "event_injection": EVENT_ID, "participant_truth_visible": False,
        "runtime_status": "source_native_runtime_reconstructable",
        "source_native_evaluator": "marble.evaluator.evaluator.Evaluator.evaluate_task_db",
    })
    dump_json(CASE / "private/case_ir.json", {
        "schema_version": "1", "instance_id": "database017-source-native-reconciliation",
        "case_id": CASE_ID, "task_archetype": "source_native_task_causal_rebuild",
        "event_contract": {"event_id": EVENT_ID, "primary_event_theme": "conflicting_valid_results", "before_state": event_contract["state_delta"]["before"], "after_state": event_contract["state_delta"]["after"], "affected_nodes": ["event_input"], "unaffected_nodes": ["preserve_prior"], "affected_closure": ["event_input", "final_state"]},
        "decision_contracts": controls,
        "task_requirements": [
            {"id": "req.01.source_native_resolution", "description": "Adopt only the authoritative INSERT_LARGE_DATA result from database:017.", "observable_probe": "mab_db017.sem.insert_authority", "public_evidence": "File Sharing System source instruction"},
            {"id": "req.02.preserve_unaffected", "description": "Retract join-only provisional claims while retaining valid probes.", "observable_probe": "mab_db017.sem.probe_preservation", "public_evidence": "reconciliation extension"},
            {"id": "req.03.receipt_bound_closure", "description": "Close only after receipt-bound native-state reverification.", "observable_probe": "mab_db017.sem.closure", "public_evidence": "reconciliation extension"},
        ],
        "dependency_graph": {"nodes": [{"id": "event_input", "kind": "event"}, {"id": "final_state", "kind": "closure"}, {"id": "preserve_prior", "kind": "preservation"}], "edges": [{"source": "event_input", "relation": "invalidates", "target": "final_state"}]},
    })

    # The private design and score ledgers are evaluator inputs, not public
    # documentation.  Keeping exact copies prevents a stale template plan from
    # silently grading a different event topology than the frozen V7 registry.
    dynamic_registry = {"version": "7", "checks": controls, "event_contracts": [event_contract]}
    dump_json(CASE / "private/dynamic_point_plan.json", dynamic_registry)
    dump_json(CASE / "private/score_plan.json", {"control_points": controls, "semantic_points": semantic_checks})

    write_manifest = "from state_reconciliation import CASE_ID, SOURCE_ID, main\nassert SOURCE_ID == 'database:017'\nif __name__ == '__main__': main()\n"
    (CASE / "task/task_file/scripts/write_manifest.py").write_text(write_manifest, encoding="utf-8")

    # These files belonged to the bargaining scaffold that supplied only the
    # directory layout.  They are not a valid alternate implementation of the
    # database task and must not survive as runnable distractors.
    for relative in (
        "private/canonical_agreement.json",
        "task/upstream_solutions/negotiation-agreement.sh",
        "task/task_file/scripts/event_worker.py",
        "task/negative_mutations/accepted_stale_revision.sh",
        "task/negative_mutations/broken_closure_lineage.sh",
        "task/negative_mutations/wrong_event_receipt.sh",
        "task/negative_mutations/wrong_product_terms.sh",
    ):
        (CASE / relative).unlink(missing_ok=True)
    print(CASE)


if __name__ == "__main__":
    main()
