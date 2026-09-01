from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .spec import (
    SUPPORTED_CASE_BENCHMARKS, discover_case_instances, discover_cases, load_case,
    normalize_case_benchmark,
    load_case_registry, validate_case, validate_case_registry,
)
from .provenance import validate_relocatable_source_native_lock, validate_sources
from .evaluation.contract import validate_evaluation_contract
from .evaluation.mutation_audit import (
    validate_candidate_mutation_suite, validate_mutation_manifest,
)
from .evaluation.registry_audit import (
    validate_case_registries, validate_semantic_registries,
)
from .evaluation.calibration import audit_score_calibration
from .evaluation.event_coverage import build_event_coverage, write_event_coverage
from .evaluation.event_taxonomy import validate_event_taxonomy, validate_event_theme_fixtures
from .evaluation.weighting import (
    DYNAMIC_CONTROL_DIMENSIONS, SCORE_POLICY_VERSION,
)
from .evaluation.runner import EpisodeConfig, run_episode
from .trajectory_curation import (
    DEFAULT_MANIFEST, initialise_curation, read_jsonl,
    render_decision_review_html, render_review_html, validate_review,
)
from .trajectory_screening import render_screening_workspace, screen_reviews
from .case_factory import (
    audit_candidate_instances, build_candidate_backlog, build_transformation_spec,
    candidate_bundle_sha256, scaffold_candidate_instance, validate_candidate_instance,
)
from .case_quality import (
    equivalence_solutions, negative_mutations, validate_case_quality,
    validate_relocatable_source_contract,
)
from .docker_case import cleanup_instance, run_solution_script
from .evaluation.pytest_results import parse_semantic_check_results
from .simple_review import (
    audit_paired_reviews, build_blind_calibration_batch, build_simple_review_batch,
    collect_uncertain_records, render_simple_review_html,
    simulate_paired_calibration_reviews,
)
from .pipeline_pilot import promotion_eligibility, run_pipeline_pilot
from .dataset_policy import build_dataset_audit, validate_dataset_policy
from .experiment_plan import (
    validate_calibration_plan, validate_frozen_release, validate_release_security,
)
from .retrospective_quality import build_retrospective_quality_audit
from .gaia2_curation import build_gaia2_review_records, read_gaia2_parquet, SELECTION_RULE
from .dynamic_pilot import (
    audit_dynamic_pilot_batch, build_dynamic_pilot_batch,
    preflight_dynamic_pilot_batch,
)
from .source_fidelity import validate_candidate_source_fidelity


ROOT = Path(__file__).resolve().parents[1]


def _run_script(case_dir: Path, script: str, *args: str) -> None:
    command = [sys.executable, str(case_dir / script), *args]
    subprocess.run(command, check=True)


def cmd_validate(args: argparse.Namespace) -> int:
    cases = discover_cases(ROOT)
    instances = [instance.load() for instance in discover_case_instances(ROOT)]
    errors = [error for case in instances for error in validate_case(case)]
    errors.extend(
        error
        for case in instances
        for error in validate_case_quality(ROOT, case.case_dir, require_contract=False)
    )
    errors.extend(validate_sources(ROOT, instances))
    errors.extend(validate_evaluation_contract(ROOT))
    errors.extend(validate_event_taxonomy(ROOT / "event_taxonomy.json"))
    errors.extend(validate_event_theme_fixtures())
    errors.extend(validate_semantic_registries(ROOT))
    errors.extend(validate_mutation_manifest(ROOT))
    errors.extend(validate_dataset_policy(ROOT))
    errors.extend(validate_calibration_plan(ROOT))
    errors.extend(validate_release_security(ROOT))
    errors.extend(validate_case_registry(ROOT, cases))
    if getattr(args, "release", False):
        # Certifying a formal Track A headline requires the experiment to be
        # frozen.  Generic dataset validation does not; this gate is opt-in so a
        # pre-frozen dataset can still be validated while it is still in
        # calibration.
        errors.extend(validate_frozen_release(ROOT))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(json.dumps({
        "valid": True,
        "registered_cases": [case.case_id for case in cases],
        "instances": len(instances),
    }, indent=2))
    return 0


def _case_promote_prechecks(
    case_id: str, candidate: Path, control_prefix: str, *, allow_existing_revision: bool = False,
) -> tuple[dict | None, list[str]]:
    """Run every pre-check for promotion. Returns (registry, errors).

    Pre-checks: candidate exists and case_id matches the directory name;
    spec.py validate_case; provenance validate_sources; the frozen per-case
    content-derived semantic and causal-control registry audit using
    ``control_prefix``; and that the target cases/<case_id> is not already
    registered or on disk. Nothing is moved or registered here.
    """
    case_contract = candidate / "public_case.yaml"
    private_contract = candidate / "private" / "private_case.yaml"
    if not case_contract.is_file() or not private_contract.is_file():
        return None, [f"candidate case not found: {candidate}"]
    spec = load_case(case_contract)
    if spec.raw["case_id"] != case_id:
        return None, [
            f"case_id {spec.raw['case_id']!r} does not match candidate dir name {case_id!r}"
        ]
    if spec.raw.get("implementation") == "blocked-access-review":
        blocker = spec.raw.get("blocker") or {}
        detail = (
            blocker.get("reason") or blocker.get("message") or blocker.get("evidence")
            or "source access is blocked"
        )
        return None, [
            f"candidate {case_id!r} is a blocked-access review record, not an implementable "
            f"case, and cannot be promoted: {detail}"
        ]
    benchmark = normalize_case_benchmark(
        (spec.raw.get("source_tasks") or [{}])[0].get("benchmark")
    )
    if benchmark not in SUPPORTED_CASE_BENCHMARKS:
        return None, [f"unsupported benchmark {benchmark!r} for promotion"]

    errors: list[str] = []
    errors.extend(validate_case(spec))
    errors.extend(validate_case_quality(ROOT, candidate, require_contract=True))
    errors.extend(validate_relocatable_source_contract(candidate))
    errors.extend(validate_relocatable_source_native_lock(candidate))
    errors.extend(validate_sources(ROOT, [spec]))
    registry, registry_errors = load_case_registry(ROOT)
    if registry is None:
        errors.extend(registry_errors)
        return None, errors
    families = registry.get("case_families", [])
    if not allow_existing_revision and case_id in {str(f.get("case_id")) for f in families}:
        errors.append(f"case {case_id!r} is already registered in cases/registry.json")
    if not allow_existing_revision and control_prefix in {str(f.get("control_prefix")) for f in families}:
        errors.append(f"control_prefix {control_prefix!r} is already in use")
    if not allow_existing_revision and (ROOT / "cases" / case_id).exists():
        errors.append(f"target already exists on disk: {ROOT / 'cases' / case_id}")
    if not control_prefix.strip():
        errors.append("control_prefix must be a non-empty string")
    errors.extend(validate_case_registries(
        {
            **spec.raw,
            "_registry_path": str(candidate / "task" / "tests" / "semantic_checks.json"),
            "_control_path": str(candidate / "task" / "tests" / "control_flow_checks.json"),
        },
        control_prefix,
    ))
    errors.extend(validate_candidate_mutation_suite(ROOT, candidate, case_id))
    errors.extend(validate_candidate_source_fidelity(candidate))
    return registry, errors


def _candidate_case_promotion_eligibility(candidate: Path) -> tuple[bool, str | None]:
    """Fail closed when a candidate family is backed by simulated review."""
    marker_path = candidate / "simulation_only.json"
    if not marker_path.is_file():
        return True, None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return False, f"invalid simulation-only marker: {exc}"
    if marker.get("simulation_only") is True or marker.get("promotion_eligible") is False:
        return False, (
            "simulation-only candidate family cannot be promoted; independent human "
            "re-review and replacement approval evidence are required"
        )
    return True, None


def cmd_case_promote(args: argparse.Namespace) -> int:
    candidate = ROOT / "candidate_cases" / args.candidate
    case_id = args.candidate
    registry, errors = _case_promote_prechecks(
        case_id, candidate, args.control_prefix,
        allow_existing_revision=bool(args.dry_run),
    )
    if errors:
        print(json.dumps({"promoted": False, "errors": errors}, indent=2), file=sys.stderr)
        return 1
    eligible, eligibility_error = _candidate_case_promotion_eligibility(candidate)
    if not eligible:
        print(json.dumps({
            "promoted": False,
            "technical_gate": "PASS",
            "promotion_gate": "BLOCKED",
            "errors": [eligibility_error],
        }, indent=2), file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps({"dry_run": True, "promoted": False, "case_id": case_id}, indent=2))
        return 0
    # NO auto-promotion: an explicit --yes is mandatory for every promotion.
    if not args.yes:
        print(
            "promotion refused: no auto-promotion. Re-run with --yes to promote "
            f"{case_id!r} (control_prefix {args.control_prefix!r}).",
            file=sys.stderr,
        )
        return 2
    registry_path = ROOT / "cases" / "registry.json"
    original_registry_text = registry_path.read_text(encoding="utf-8")
    target = ROOT / "cases" / case_id
    try:
        shutil.move(str(candidate), str(target))
    except OSError as exc:
        print(f"promotion move failed: {exc}", file=sys.stderr)
        return 1
    benchmark = "unknown"
    audit_errors: list[str] = []
    try:
        benchmark = normalize_case_benchmark(
            (load_case(target / "public_case.yaml").raw.get("source_tasks") or [{}])[0].get("benchmark")
        )
        families = registry.get("case_families", [])
        families.append({
            "case_id": case_id,
            "benchmark": benchmark,
            "control_prefix": args.control_prefix,
            # Promotion is admission to the verifier-calibration corpus.  A
            # development/test split is assigned only by the later frozen
            # dataset-allocation procedure.
            "instances": [{"instance_id": "seed-1", "path": ".", "split": "calibration"}],
        })
        registry_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
        )
        promoted = discover_cases(ROOT)
        promoted_spec = load_case(target / "public_case.yaml")
        audit_errors.extend(validate_case(promoted_spec))
        audit_errors.extend(validate_case_quality(ROOT, target, require_contract=True))
        audit_errors.extend(validate_relocatable_source_contract(target))
        audit_errors.extend(validate_relocatable_source_native_lock(target))
        audit_errors.extend(validate_sources(ROOT, [promoted_spec]))
        audit_errors.extend(validate_case_registry(ROOT, promoted))
        audit_errors.extend(validate_semantic_registries(ROOT))
        audit_errors.extend(validate_mutation_manifest(ROOT))
    except Exception as exc:
        # Promotion is a filesystem+registry transaction.  Global validators
        # may fail closed by raising (for example on malformed instance
        # metadata); those failures must take the same rollback path as a
        # returned audit error.
        audit_errors.append(f"post-promotion audit raised {type(exc).__name__}: {exc}")
    rollback_errors: list[str] = []
    if audit_errors:
        try:
            registry_path.write_text(original_registry_text, encoding="utf-8")
        except OSError as exc:
            rollback_errors.append(f"registry rollback failed: {exc}")
        try:
            if target.exists() and not candidate.exists():
                shutil.move(str(target), str(candidate))
            elif target.exists() or candidate.exists():
                rollback_errors.append(
                    "case directory rollback refused because source/target state is ambiguous"
                )
        except OSError as exc:
            rollback_errors.append(f"case directory rollback failed: {exc}")
    summary = {
        "promoted": not audit_errors,
        "case_id": case_id,
        "control_prefix": args.control_prefix,
        "benchmark": benchmark,
        "moved": f"candidate_cases/{case_id} -> cases/{case_id}",
        "registry_path": str(registry_path),
        "post_promotion_audit": "PASS" if not audit_errors else audit_errors,
        "rollback": (
            None if not audit_errors else
            ("PASS" if not rollback_errors else rollback_errors)
        ),
        "note": "official experiments now auto-discover this family via cases/; "
                "candidate_cases/ is not auto-discovered",
    }
    print(json.dumps(summary, indent=2))
    return 0 if not audit_errors and not rollback_errors else 1


def cmd_instance_promote(args: argparse.Namespace) -> int:
    candidate_root = (ROOT / "candidate_instances").resolve()
    candidate = (candidate_root / args.family / args.candidate).resolve()
    try:
        candidate.relative_to(candidate_root)
    except ValueError:
        print("candidate path escapes candidate_instances/", file=sys.stderr)
        return 2
    metadata, errors = validate_candidate_instance(ROOT, args.family, candidate)
    instance_id = str((metadata or {}).get("instance_id") or args.candidate)
    if errors:
        print(json.dumps({
            "promoted": False,
            "family_id": args.family,
            "instance_id": instance_id,
            "errors": errors,
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    eligible, eligibility_error = promotion_eligibility(metadata or {})
    if not eligible:
        print(json.dumps({
            "promoted": False,
            "family_id": args.family,
            "instance_id": instance_id,
            "errors": [eligibility_error],
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps({
            "dry_run": True, "promoted": False,
            "family_id": args.family, "instance_id": instance_id,
            "gate_status": "PASS",
        }, indent=2))
        return 0
    if not args.yes:
        print(
            "instance promotion refused: re-run with --yes after reviewing the dry-run report",
            file=sys.stderr,
        )
        return 2

    registry, registry_errors = load_case_registry(ROOT)
    if registry is None or registry_errors:
        print(json.dumps({"promoted": False, "errors": registry_errors}, indent=2), file=sys.stderr)
        return 1
    target = ROOT / "cases" / args.family / "instances" / instance_id
    registry_path = ROOT / "cases" / "registry.json"
    original_registry_text = registry_path.read_text(encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    moved = False

    def rollback_promotion() -> list[str]:
        rollback_errors: list[str] = []
        try:
            registry_path.write_text(original_registry_text, encoding="utf-8")
        except OSError as exc:
            rollback_errors.append(f"registry rollback failed: {exc}")
        if moved and target.exists():
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(candidate))
            except OSError as exc:
                rollback_errors.append(f"instance rollback failed: {exc}")
        return rollback_errors

    try:
        shutil.move(str(candidate), str(target))
        moved = True
        family = next(
            item for item in registry["case_families"]
            if item["case_id"] == args.family
        )
        family["instances"].append({
            "instance_id": instance_id,
            "path": f"instances/{instance_id}",
            "split": metadata["dataset_binding"]["split"],
        })
        registry_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        rollback_errors = rollback_promotion()
        print(json.dumps({
            "promoted": False,
            "rolled_back": not rollback_errors,
            "error": f"instance promotion failed: {exc}",
            "rollback_errors": rollback_errors,
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    cases = discover_cases(ROOT)
    post_errors: list[str] = []
    post_errors.extend(validate_case_registry(ROOT, cases))
    post_errors.extend(validate_semantic_registries(ROOT))
    post_errors.extend(validate_mutation_manifest(ROOT))
    if post_errors:
        rollback_errors = rollback_promotion()
        summary = {
            "promoted": False,
            "rolled_back": not rollback_errors,
            "family_id": args.family,
            "instance_id": instance_id,
            "post_promotion_audit": post_errors,
            "rollback_errors": rollback_errors,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    summary = {
        "promoted": True,
        "family_id": args.family,
        "instance_id": instance_id,
        "moved_to": str(target),
        "registry_key": f"{args.family}::{instance_id}",
        "post_promotion_audit": "PASS" if not post_errors else post_errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_instance_audit(args: argparse.Namespace) -> int:
    report = audit_candidate_instances(ROOT)
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _execute_declared_quality_variants(
    candidate: Path, case_id: str, variant_root: Path, reports_dir: Path,
    *, seed: int, canonical_verifier_digest: str,
) -> dict:
    """Execute all declared equivalent positives and targeted negative mutations."""
    reports_dir.mkdir(parents=True, exist_ok=False)
    variant_root.mkdir(parents=True, exist_ok=False)
    semantic_registry = json.loads(
        (candidate / "task/tests/semantic_checks.json").read_text(encoding="utf-8")
    )
    equivalents: list[dict] = []
    negatives: list[dict] = []
    for variant in equivalence_solutions(candidate):
        variant_id = str(variant["id"])
        instance = variant_root / f"equivalence-{variant_id}"
        report_path = reports_dir / f"equivalence-{variant_id}.json"
        row = {"id": variant_id, "success": False, "report": str(report_path)}
        try:
            _run_script(
                candidate, "generate.py", "--output", str(instance), "--seed", str(seed),
            )
            run_solution_script(case_id, instance, Path(str(variant["path"])))
            _run_script(
                candidate, "verify.py", "--instance", str(instance),
                "--output", str(report_path),
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            row["success"] = report.get("success") is True
            row["verifier_bundle_sha256"] = report.get("verifier_bundle_sha256")
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            row["error_type"] = type(exc).__name__
            row["exit_code"] = getattr(exc, "returncode", None)
        finally:
            cleanup_instance(case_id, instance)
        equivalents.append(row)
    for mutation in negative_mutations(candidate):
        mutation_id = str(mutation["id"])
        instance = variant_root / f"negative-{mutation_id}"
        report_path = reports_dir / f"negative-{mutation_id}.json"
        row = {
            "id": mutation_id, "must_fail": list(mutation["must_fail"]),
            "killed": False, "report": str(report_path),
        }
        try:
            _run_script(
                candidate, "generate.py", "--output", str(instance), "--seed", str(seed),
            )
            _run_script(candidate, "oracle.py", "--instance", str(instance))
            run_solution_script(
                case_id, instance, Path(str(mutation["path"])), fresh=False,
            )
            try:
                _run_script(
                    candidate, "verify.py", "--instance", str(instance),
                    "--output", str(report_path),
                )
            except subprocess.CalledProcessError:
                pass
            if report_path.is_file():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                semantic = parse_semantic_check_results(
                    str(report.get("test_output") or ""), semantic_registry,
                )
                failed_ids = {
                    str(item["id"]) for item in (semantic or {}).get("results") or []
                    if item.get("passed") is False
                }
                row["observed_failed"] = sorted(failed_ids)
                row["verifier_bundle_sha256"] = report.get("verifier_bundle_sha256")
                row["killed"] = (
                    report.get("success") is False
                    and set(row["must_fail"]).issubset(failed_ids)
                )
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            row["error_type"] = type(exc).__name__
            row["exit_code"] = getattr(exc, "returncode", None)
        finally:
            cleanup_instance(case_id, instance)
        negatives.append(row)
    digests = {
        str(row.get("verifier_bundle_sha256"))
        for row in equivalents + negatives if row.get("verifier_bundle_sha256")
    }
    same_verifier = digests == {canonical_verifier_digest}
    passed = (
        bool(equivalents) and all(row["success"] for row in equivalents)
        and len(negatives) >= 2 and all(row["killed"] for row in negatives)
        and same_verifier
    )
    return {
        "schema_version": "1.0", "passed": passed,
        "canonical_verifier_bundle_sha256": canonical_verifier_digest,
        "same_verifier_bundle": same_verifier,
        "equivalence_solutions": equivalents,
        "negative_mutations": negatives,
    }


def cmd_instance_preflight(args: argparse.Namespace) -> int:
    """Run a candidate's real build -> Oracle -> hidden verifier release chain."""
    candidate_root = (ROOT / "candidate_instances").resolve()
    candidate = (candidate_root / args.family / args.candidate).resolve()
    try:
        candidate.relative_to(candidate_root)
    except ValueError:
        print("candidate path escapes candidate_instances/", file=sys.stderr)
        return 2
    metadata, errors = validate_candidate_instance(
        ROOT, args.family, candidate, require_execution_evidence=False,
    )
    if errors or metadata is None:
        print(json.dumps({"passed": False, "errors": errors}, indent=2), file=sys.stderr)
        return 1
    output = Path(args.output).resolve()
    if output.exists():
        print(
            f"preflight output already exists; refusing to overwrite it: {output}",
            file=sys.stderr,
        )
        return 2
    instance_id = str(metadata["instance_id"])
    report_path = candidate / "review_evidence" / "execution_verification.json"
    try:
        _run_script(candidate, "generate.py", "--output", str(output), "--seed", str(args.seed))
        _run_script(candidate, "oracle.py", "--instance", str(output))
        _run_script(
            candidate, "verify.py", "--instance", str(output), "--output", str(report_path),
        )
    except subprocess.CalledProcessError as exc:
        print(json.dumps({
            "passed": False, "case_id": args.family, "instance_id": instance_id,
            "failed_command": exc.cmd, "exit_code": exc.returncode,
            "note": "No passing release evidence was written.",
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("success") is not True:
        print(json.dumps({"passed": False, "verification": report}, indent=2), file=sys.stderr)
        return 1
    quality_dir = candidate / "review_evidence" / "execution_quality"
    variant_root = output.parent / f"{output.name}-quality-variants"
    if quality_dir.exists() or variant_root.exists():
        print(
            "quality execution outputs already exist; refusing to overwrite them",
            file=sys.stderr,
        )
        return 2
    quality_summary = _execute_declared_quality_variants(
        candidate, args.family, variant_root, quality_dir,
        seed=args.seed,
        canonical_verifier_digest=str(report.get("verifier_bundle_sha256") or ""),
    )
    quality_summary_path = quality_dir / "summary.json"
    quality_summary_path.write_text(
        json.dumps(quality_summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if quality_summary.get("passed") is not True:
        print(json.dumps({
            "passed": False, "case_id": args.family, "instance_id": instance_id,
            "quality_execution": quality_summary,
            "note": "No passing release evidence was written.",
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    evidence = {
        "schema_version": "1.0", "status": "pass", "case_id": args.family,
        "instance_id": instance_id, "seed": args.seed,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "case_bundle_sha256": candidate_bundle_sha256(candidate),
        "oracle_completed": True,
        "score_policy_version": SCORE_POLICY_VERSION,
        "dynamic_contract_validation": {
            "passed": True,
            "dimensions": sorted({
                str(item.get("dimension") or "")
                for item in json.loads(
                    (candidate / "task/tests/control_flow_checks.json").read_text(
                        encoding="utf-8"
                    )
                ).get("checks") or []
            }),
            "critical_point_count": sum(
                item.get("critical") is True
                for item in json.loads(
                    (candidate / "task/tests/control_flow_checks.json").read_text(
                        encoding="utf-8"
                    )
                ).get("checks") or []
            ),
            "note": (
                "Static registry and mutation-contract validation; model performance "
                "is calibrated separately from official async score reports."
            ),
        },
        "quality_execution": {
            "passed": True,
            "summary_sha256": hashlib.sha256(quality_summary_path.read_bytes()).hexdigest(),
        },
        "verification": {
            "success": True,
            "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            "verifier_bundle_sha256": report.get("verifier_bundle_sha256"),
            "verifier_isolation": report.get("verifier_isolation"),
        },
    }
    evidence_path = candidate / "review_evidence" / "release_evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _, final_errors = validate_candidate_instance(ROOT, args.family, candidate)
    summary = {
        "passed": not final_errors, "case_id": args.family, "instance_id": instance_id,
        "artifact_root": str(output), "release_evidence": str(evidence_path),
        "errors": final_errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not final_errors else 1


def cmd_candidate_quality_preflight(args: argparse.Namespace) -> int:
    """Execute canonical and non-canonical solutions against one hidden verifier."""
    candidate = (ROOT / "candidate_cases" / args.candidate).resolve()
    _, errors = _case_promote_prechecks(
        args.candidate, candidate, args.control_prefix,
        allow_existing_revision=True,
    )
    if errors:
        print(json.dumps({"passed": False, "errors": errors}, indent=2), file=sys.stderr)
        return 1
    output = Path(args.output).resolve()
    if output.exists():
        print(f"quality-preflight output already exists: {output}", file=sys.stderr)
        return 2
    output.mkdir(parents=True)
    reports_dir = output / "reports"
    reports_dir.mkdir()
    rows: list[dict] = []
    variants = [{"id": "canonical-oracle", "path": None}] + equivalence_solutions(candidate)
    for variant in variants:
        variant_id = str(variant["id"])
        instance = output / "instances" / variant_id
        report_path = reports_dir / f"{variant_id}.json"
        row = {
            "id": variant_id,
            "kind": "canonical" if variant["path"] is None else "equivalence",
            "instance": str(instance),
            "report": str(report_path),
            "success": False,
        }
        try:
            _run_script(
                candidate, "generate.py", "--output", str(instance),
                "--seed", str(args.seed),
            )
            if variant["path"] is None:
                _run_script(candidate, "oracle.py", "--instance", str(instance))
            else:
                run_solution_script(args.candidate, instance, Path(str(variant["path"])))
            _run_script(
                candidate, "verify.py", "--instance", str(instance),
                "--output", str(report_path),
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            row["success"] = report.get("success") is True
            row["verifier_bundle_sha256"] = report.get("verifier_bundle_sha256")
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            row["error_type"] = type(exc).__name__
            row["exit_code"] = getattr(exc, "returncode", None)
        finally:
            cleanup_instance(args.candidate, instance)
        rows.append(row)
    semantic_registry = json.loads(
        (candidate / "task/tests/semantic_checks.json").read_text(encoding="utf-8")
    )
    negative_rows: list[dict] = []
    for mutation in negative_mutations(candidate):
        mutation_id = str(mutation["id"])
        instance = output / "instances" / f"negative-{mutation_id}"
        report_path = reports_dir / f"negative-{mutation_id}.json"
        row = {
            "id": mutation_id,
            "kind": "negative_mutation",
            "instance": str(instance),
            "report": str(report_path),
            "must_fail": list(mutation["must_fail"]),
            "killed": False,
        }
        try:
            _run_script(
                candidate, "generate.py", "--output", str(instance),
                "--seed", str(args.seed),
            )
            _run_script(candidate, "oracle.py", "--instance", str(instance))
            run_solution_script(
                args.candidate, instance, Path(str(mutation["path"])), fresh=False,
            )
            try:
                _run_script(
                    candidate, "verify.py", "--instance", str(instance),
                    "--output", str(report_path),
                )
            except subprocess.CalledProcessError:
                pass
            if report_path.is_file():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                semantic = parse_semantic_check_results(
                    str(report.get("test_output") or ""), semantic_registry,
                )
                failed_ids = {
                    str(item["id"]) for item in (semantic or {}).get("results") or []
                    if item.get("passed") is False
                }
                row["observed_failed"] = sorted(failed_ids)
                row["verifier_bundle_sha256"] = report.get("verifier_bundle_sha256")
                row["killed"] = (
                    report.get("success") is False
                    and set(row["must_fail"]).issubset(failed_ids)
                )
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            row["error_type"] = type(exc).__name__
            row["exit_code"] = getattr(exc, "returncode", None)
        finally:
            cleanup_instance(args.candidate, instance)
        negative_rows.append(row)
    passed = all(row["success"] for row in rows) and all(
        row["killed"] for row in negative_rows
    )
    verifier_digests = {
        str(row.get("verifier_bundle_sha256"))
        for row in rows + negative_rows if row.get("verifier_bundle_sha256")
    }
    if len(verifier_digests) != 1:
        passed = False
        errors.append("solution variants were not evaluated by one identical verifier bundle")
    summary = {
        "schema_version": "1.0",
        "passed": passed,
        "case_id": args.candidate,
        "seed": args.seed,
        "static_quality_gate": "PASS",
        "canonical_passed": bool(rows and rows[0]["success"]),
        "equivalence_passed": all(row["success"] for row in rows[1:]),
        "negative_mutations_killed": all(row["killed"] for row in negative_rows),
        "verifier_bundle_sha256": next(iter(verifier_digests), None),
        "variants": rows,
        "negative_mutations": negative_rows,
        "errors": errors,
    }
    (output / "quality-execution-report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


def cmd_build_all(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for instance in discover_case_instances(ROOT):
        target = output / instance.case_id / instance.instance_id
        _run_script(instance.case_dir, "generate.py", "--output", str(target), "--seed", str(args.seed))
    return 0


def cmd_oracle_all(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    for instance in discover_case_instances(ROOT):
        target = root / instance.case_id / instance.instance_id
        _run_script(instance.case_dir, "oracle.py", "--instance", str(target))
    return 0


def cmd_verify_all(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    reports = []
    for instance in discover_case_instances(ROOT):
        target = root / instance.case_id / instance.instance_id
        report_path = target / "verification.json"
        _run_script(
            instance.case_dir,
            "verify.py",
            "--instance",
            str(target),
            "--output",
            str(report_path),
        )
        reports.append(json.loads(report_path.read_text(encoding="utf-8")))
    success = all(report.get("success") for report in reports)
    print(json.dumps({"success": success, "reports": reports}, indent=2))
    return 0 if success else 1


def cmd_validate_all(args: argparse.Namespace) -> int:
    """Run each registered task through Oracle and verifier as one lifecycle.

    Keeping every successful Oracle container alive until a later verify-all
    pass is unsafe when two registered instances publish the same host ports.
    The per-instance lifecycle also makes cleanup happen before the next task
    starts, while retaining oracle-all/verify-all for targeted debugging.
    """
    root = Path(args.root).resolve()
    reports = []
    for instance in discover_case_instances(ROOT):
        target = root / instance.case_id / instance.instance_id
        report_path = target / "verification.json"
        _run_script(instance.case_dir, "oracle.py", "--instance", str(target))
        _run_script(
            instance.case_dir,
            "verify.py",
            "--instance",
            str(target),
            "--output",
            str(report_path),
        )
        reports.append(json.loads(report_path.read_text(encoding="utf-8")))
    success = all(report.get("success") for report in reports)
    summary = {"success": success, "reports": reports}
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if success else 1


def cmd_calibration_audit(args: argparse.Namespace) -> int:
    report = audit_score_calibration(ROOT, Path(args.evidence_root).resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report.get("gaps") else 0


def cmd_event_coverage(args: argparse.Namespace) -> int:
    report = build_event_coverage(discover_case_instances(ROOT))
    if args.output:
        write_event_coverage(Path(args.output).resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


def cmd_dataset_audit(args: argparse.Namespace) -> int:
    policy_errors = validate_dataset_policy(ROOT)
    report = (
        {"static_valid": False, "errors": policy_errors}
        if policy_errors
        else build_dataset_audit(ROOT, discover_case_instances(ROOT))
    )
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    gate = "publication_ready" if args.require_publication_ready else "static_valid"
    return 0 if report.get(gate) else 1


def cmd_retrospective_quality_audit(args: argparse.Namespace) -> int:
    report = build_retrospective_quality_audit(ROOT, discover_case_instances(ROOT))
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["publication_ready"] else 1


def cmd_curation_init(args: argparse.Namespace) -> int:
    summary = initialise_curation(
        root=ROOT,
        manifest=args.manifest,
        output=Path(args.output).resolve(),
        per_task=args.per_task,
        fetch_artifacts=args.download_artifacts,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not summary["missing_tasks"] else 1


def cmd_curation_validate(args: argparse.Namespace) -> int:
    records = read_jsonl(Path(args.input).resolve())
    failures = []
    for index, record in enumerate(records, 1):
        errors = validate_review(record, args.kind)
        if errors:
            failures.append({
                "line": index,
                "id": record.get("review_id") or record.get("decision_id"),
                "errors": errors,
            })
    report = {
        "valid": not failures, "kind": args.kind,
        "record_count": len(records), "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


def cmd_curation_render(args: argparse.Namespace) -> int:
    records = read_jsonl(Path(args.input).resolve())
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.kind == "trajectory":
        render_review_html(records, output)
    else:
        render_decision_review_html(records, output)
    print(json.dumps({
        "rendered": True, "kind": args.kind,
        "record_count": len(records), "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_curation_screen(args: argparse.Namespace) -> int:
    records = read_jsonl(Path(args.input).resolve())
    if args.review_id:
        selected_ids = set(args.review_id)
        records = [record for record in records if record.get("review_id") in selected_ids]
    if args.task:
        selected_tasks = set(args.task)
        records = [record for record in records if record.get("task_name") in selected_tasks]
    if args.agent:
        selected_agents = {value.lower() for value in args.agent}
        records = [
            record for record in records
            if str((record.get("source") or {}).get("agent") or "").lower() in selected_agents
        ]
    if args.limit is not None:
        records = records[:args.limit]
    if not records:
        print("no trajectory review records matched the filters", file=sys.stderr)
        return 2
    summary = asyncio.run(screen_reviews(
        records,
        Path(args.output).resolve(),
        mode=args.mode,
        config_path=Path(args.config).resolve() if args.config else None,
        key_file=Path(args.key_file).resolve() if args.key_file else ROOT / "apikey.txt",
        key_label=args.key_label,
        max_prompt_chars=args.max_prompt_chars,
        max_retries=args.max_retries,
        prepare_concurrency=args.prepare_concurrency,
    ))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not summary["failure_count"] else 1


def cmd_curation_workspace(args: argparse.Namespace) -> int:
    reviews = read_jsonl(Path(args.trajectory_input).resolve())
    decisions = read_jsonl(Path(args.decision_input).resolve())
    wanted = {str(review.get("review_id")) for review in reviews}
    normalized_by_id: dict[str, dict] = {}
    for directory in args.normalized_dir:
        for path in Path(directory).resolve().glob("*.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            review_id = str(value.get("review_id") or "")
            if review_id in wanted:
                normalized_by_id[review_id] = value
    missing = sorted(wanted - set(normalized_by_id))
    if missing:
        print(json.dumps({"missing_normalized_trajectories": missing}, indent=2), file=sys.stderr)
        return 2
    labels = []
    for review in reviews:
        human = review.get("human_review") or {}
        labels.append({
            "review_id": review.get("review_id"), "screening_mode": "human_simulation",
            "trajectory_quality": human.get("trajectory_quality"),
            "replanning_evidence": human.get("replanning_evidence"),
            "summary": human.get("reviewer_note"), "candidate_decisions": [],
        })
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    render_screening_workspace(
        reviews, list(normalized_by_id.values()), labels, decisions, output,
    )
    print(json.dumps({
        "rendered": True, "trajectory_count": len(reviews),
        "decision_count": len(decisions), "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_curation_export_candidates(args: argparse.Namespace) -> int:
    report = build_candidate_backlog(
        read_jsonl(Path(args.trajectory_input).resolve()),
        read_jsonl(Path(args.decision_input).resolve()),
    )
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


def cmd_curation_simple_review(args: argparse.Namespace) -> int:
    source = Path(args.input).resolve()
    value = json.loads(source.read_text(encoding="utf-8"))
    records = value if isinstance(value, list) else [value]
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("simple review input must be an object or a list of objects")
    output = Path(args.output).resolve()
    render_simple_review_html(records, output)
    print(json.dumps({
        "rendered": True,
        "record_count": len(records),
        "output": str(output),
        "annotation_format": "JSONL downloaded from the review page",
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_curation_build_simple_batch(args: argparse.Namespace) -> int:
    normalized_dir = Path(args.normalized_dir).resolve()
    normalized = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(normalized_dir.glob("*.json"))
    ]
    decisions = read_jsonl(Path(args.decisions).resolve())
    labels = read_jsonl(Path(args.screening_labels).resolve())
    labels_by_id = {str(row.get("review_id") or ""): row for row in labels}
    records, source_map = build_simple_review_batch(
        normalized, decisions, limit=args.limit,
    )
    missing_labels = [
        item["source_review_id"] for item in source_map
        if item["source_review_id"] not in labels_by_id
    ]
    if missing_labels:
        raise ValueError(f"selected review records have no model screening label: {missing_labels}")
    for item in source_map:
        label = labels_by_id[item["source_review_id"]]
        item["screening"] = {
            "screening_mode": label.get("screening_mode"),
            "trajectory_quality": label.get("trajectory_quality"),
            "replanning_evidence": label.get("replanning_evidence"),
            "research_events": label.get("research_events"),
            "candidate_decision_count": len(label.get("candidate_decisions") or []),
            "summary": label.get("summary"),
        }
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "review-records.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    internal = output / "internal"
    internal.mkdir(parents=True, exist_ok=True)
    (internal / "source-map.json").write_text(
        json.dumps(source_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    review_path = output / "review.html"
    render_simple_review_html(records, review_path)
    summary = {
        "schema_version": "1.0",
        "normalized_trajectory_count": len(normalized),
        "decision_candidate_count": len(decisions),
        "model_screened_count": len(labels),
        "selected_model_positive_count": sum(
            item["screening"]["candidate_decision_count"] > 0 for item in source_map
        ),
        "selected_model_negative_count": sum(
            item["screening"]["candidate_decision_count"] == 0 for item in source_map
        ),
        "review_record_count": len(records),
        "blind": True,
        "standalone_review_page": True,
        "questions_per_record": 4,
        "output": str(output),
    }
    (output / "batch-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if 30 <= len(records) <= 50 else 1


def cmd_gaia2_structured_review(args: argparse.Namespace) -> int:
    parquet = Path(args.parquet).resolve()
    rows = read_gaia2_parquet(parquet)
    records, source_map = build_gaia2_review_records(rows, limit=args.limit)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "review-records.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    internal = output / "internal"
    internal.mkdir(parents=True, exist_ok=True)
    (internal / "source-map.json").write_text(
        json.dumps(source_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    parquet_sha = hashlib.sha256(parquet.read_bytes()).hexdigest()
    source_lock = {
        "schema_version": "1.0",
        "repository": "meta-agents-research-environments/gaia2",
        "revision": args.revision,
        "file": "mini/validation-00000-of-00001.parquet",
        "parquet_sha256": parquet_sha,
        "source_row_count": len(rows),
        "selection_rule": SELECTION_RULE,
        "selected_review_count": len(records),
    }
    (internal / "source-lock.json").write_text(
        json.dumps(source_lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    render_simple_review_html(records, output / "review.html")
    categories: dict[str, int] = {}
    for item in source_map:
        category = str(item["category"])
        categories[category] = categories.get(category, 0) + 1
    summary = {
        "schema_version": "1.0",
        "source_row_count": len(rows),
        "causal_review_count": len(records),
        "categories": dict(sorted(categories.items())),
        "blind": True,
        "standalone_review_page": True,
        "questions_per_record": 4,
        "selection_rule": SELECTION_RULE,
        "output": str(output),
    }
    (output / "batch-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if 30 <= len(records) <= 50 else 1


def cmd_curation_build_calibration_batch(args: argparse.Namespace) -> int:
    candidate_records = json.loads(Path(args.candidates).resolve().read_text(encoding="utf-8"))
    audit_records = json.loads(Path(args.audit_controls).resolve().read_text(encoding="utf-8"))
    if not isinstance(candidate_records, list) or not isinstance(audit_records, list):
        raise ValueError("candidate and audit-control inputs must both be JSON lists")
    records, source_map = build_blind_calibration_batch(
        candidate_records,
        audit_records,
        candidate_limit=args.candidate_limit,
        audit_limit=args.audit_limit,
        seed=args.seed,
    )
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "review-records.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    internal = output / "internal"
    internal.mkdir(parents=True, exist_ok=True)
    (internal / "source-map.json").write_text(
        json.dumps(source_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    render_simple_review_html(records, output / "review.html")
    strata: dict[str, int] = {}
    for item in source_map:
        stratum = str(item["stratum"])
        strata[stratum] = strata.get(stratum, 0) + 1
    summary = {
        "schema_version": "1.0",
        "review_record_count": len(records),
        "internal_strata": dict(sorted(strata.items())),
        "blind": True,
        "stable_shuffle": True,
        "questions_per_record": 4,
        "standalone_review_page": True,
        "output": str(output),
    }
    (output / "batch-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if 30 <= len(records) <= 50 else 1


def cmd_curation_audit_paired_reviews(args: argparse.Namespace) -> int:
    records = json.loads(Path(args.input).resolve().read_text(encoding="utf-8"))
    source_map = json.loads(Path(args.source_map).resolve().read_text(encoding="utf-8"))
    annotations = []
    for path_value in args.annotations:
        annotations.extend(read_jsonl(Path(path_value).resolve()))
    report, rereview_records = audit_paired_reviews(records, annotations, source_map)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "paired-review-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (output / "rereview-records.json").write_text(
        json.dumps(rereview_records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    if rereview_records:
        render_simple_review_html(rereview_records, output / "rereview.html")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready_for_case_design"] else 1


def cmd_curation_simulate_paired_reviews(args: argparse.Namespace) -> int:
    records = json.loads(Path(args.input).resolve().read_text(encoding="utf-8"))
    source_map = json.loads(Path(args.source_map).resolve().read_text(encoding="utf-8"))
    first, second = simulate_paired_calibration_reviews(
        records, source_map, reviewer_ids=(args.reviewer_a, args.reviewer_b),
    )
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for filename, values in (
        (f"annotations-{args.reviewer_a}.jsonl", first),
        (f"annotations-{args.reviewer_b}.jsonl", second),
    ):
        (output / filename).write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in values),
            encoding="utf-8",
        )
    notice = {
        "schema_version": "1.0",
        "simulation_only": True,
        "not_human_annotation": True,
        "may_not_be_used_for_release_or_paper_results": True,
        "record_count_per_reviewer": len(first),
        "reviewer_ids": [args.reviewer_a, args.reviewer_b],
    }
    (output / "SIMULATION-NOTICE.json").write_text(
        json.dumps(notice, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(notice, ensure_ascii=False, indent=2))
    return 0


def cmd_curation_collect_uncertain(args: argparse.Namespace) -> int:
    source_value = json.loads(Path(args.input).resolve().read_text(encoding="utf-8"))
    records = source_value if isinstance(source_value, list) else [source_value]
    annotations = read_jsonl(Path(args.annotations).resolve())
    queue = collect_uncertain_records(records, annotations)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "source_record_count": len(records),
        "annotation_count": len(annotations),
        "uncertain_rereview_count": len(queue),
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_curation_build_transformation_spec(args: argparse.Namespace) -> int:
    record_value = json.loads(Path(args.input).resolve().read_text(encoding="utf-8"))
    if isinstance(record_value, list):
        if not args.review_id:
            raise ValueError("--review-id is required when transformation input is a list")
        matches = [
            item for item in record_value
            if isinstance(item, dict) and str(item.get("review_id") or "") == args.review_id
        ]
        if len(matches) != 1:
            raise ValueError(f"expected exactly one review record for {args.review_id!r}")
        record_value = matches[0]
    if not isinstance(record_value, dict):
        raise ValueError("transformation input must be a review object or list of review objects")
    annotations = []
    for path_value in args.annotations:
        annotations.extend(read_jsonl(Path(path_value).resolve()))
    plan = json.loads(Path(args.plan).resolve().read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("transformation plan must be an object")
    spec = build_transformation_spec(record_value, annotations, plan)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "built": True,
        "candidate_id": spec["candidate_id"],
        "reviewer_count": spec["review_consensus"]["reviewer_count"],
        "target": (
            f"{spec['design']['target_family']}::{spec['design']['instance_id']}"
        ),
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_instance_scaffold(args: argparse.Namespace) -> int:
    spec = json.loads(Path(args.spec).resolve().read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("transformation spec must be an object")
    target = scaffold_candidate_instance(ROOT, spec)
    print(json.dumps({
        "scaffolded": True,
        "candidate": str(target),
        "next": "run instance-promote --dry-run, review, then explicitly promote",
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_pipeline_pilot(args: argparse.Namespace) -> int:
    report = run_pipeline_pilot(
        ROOT, Path(args.config).resolve(), Path(args.output).resolve(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "static_gate_pass" else 1


def cmd_dynamic_pilot_build(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    report = build_dynamic_pilot_batch(
        ROOT, output,
        Path(args.human_review).resolve() if args.human_review else None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


def cmd_dynamic_pilot_audit(args: argparse.Namespace) -> int:
    result = audit_dynamic_pilot_batch(Path(args.batch).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["batch_valid"] else 1


def cmd_dynamic_pilot_preflight(args: argparse.Namespace) -> int:
    result = preflight_dynamic_pilot_batch(
        Path(args.batch).resolve(), seed=int(args.seed),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


async def _run_dynamic_pilot_pair(args: argparse.Namespace) -> int:
    batch = Path(args.batch).resolve()
    report_path = batch / "batch-report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        print(f"invalid dynamic pilot batch: {exc}", file=sys.stderr)
        return 2
    row = next(
        (item for item in report.get("cases", []) if item.get("pilot_id") == args.pilot_id),
        None,
    )
    if row is None or not row.get("registry_valid") or row.get("participant_leakage_hits"):
        print("pilot case is missing or failed its static/leakage gate", file=sys.stderr)
        return 2
    if (report.get("stage_status") or {}).get("runtime_preflight") != "passed":
        print(
            "pilot batch has not passed the canonical runtime-preflight stage",
            file=sys.stderr,
        )
        return 2
    candidate = Path(row["case_dir"]).resolve()
    config_path = Path(args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    output = Path(args.output).resolve()
    if output.exists():
        print(f"dynamic pilot pair output already exists: {output}", file=sys.stderr)
        return 2
    output.mkdir(parents=True)
    credential_name = str(config.get("api_key_env") or "")
    model = str(config.get("main_model") or "unknown")
    if bool(config.get("api_key_required")) and not os.environ.get(credential_name):
        blocked = {
            "schema_version": "dynamic-pilot-pair-1",
            "pilot_id": args.pilot_id,
            "model": model,
            "status": "blocked_missing_credential",
            "missing_environment_variable": credential_name,
            "scores": [],
            "note": "No substitute or scripted model was used.",
        }
        (output / "pair-results.json").write_text(
            json.dumps(blocked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        print(json.dumps(blocked, ensure_ascii=False, indent=2))
        return 3
    case = load_case(candidate / "public_case.yaml")
    pair_id = f"dynamic-pilot-{args.pilot_id}-{model}-{args.seed}"
    adapter = [
        sys.executable, str(ROOT / "adapters/reference_scaffold_api.py"),
        "--config", str(config_path),
    ]
    scores: list[dict[str, Any]] = []
    linear_gate: dict[str, Any] | None = None
    for index, mode in enumerate(("linear", "async"), 1):
        episode_id = f"{pair_id}-{mode}"
        score = await run_episode(ROOT, EpisodeConfig(
            episode_id=episode_id,
            case_id=case.case_id,
            instance_id=args.pilot_id,
            execution_mode=mode,
            guidance="incentive",
            agent_seed=args.seed,
            adapter_command=adapter,
            output_dir=output / "episodes" / episode_id,
            repeat=0,
            counterfactual_pair_id=pair_id,
            timeout_sec=args.timeout,
            gateway_grace_sec=args.gateway_grace,
            max_total_tokens=(
                args.max_linear_tokens if mode == "linear" else args.max_async_tokens
            ),
            use_container=True,
            build_image=(index == 1),
            keep_container=False,
            progress=True,
            episode_index=index,
            episode_total=2,
            adapter_profile="reference_scaffold_api",
            runtime_mode="api_only",
            official_track=False,
            case_dir_override=candidate,
        ))
        scores.append(score)
        if mode == "linear":
            semantic = score.get("semantic_task_score")
            linear_gate = {
                "threshold": args.linear_threshold,
                "semantic_score": semantic,
                "score_status_ok": score.get("score_status") == "scored",
                "scenario_ok": score.get("scenario_constructed") is True,
                "protocol_ok": score.get("protocol_valid") is True,
                "infrastructure_ok": not score.get("infrastructure_failures"),
                "token_budget_ok": int(score.get("total_tokens") or 0) <= args.max_linear_tokens,
                "duration_budget_ok": float(score.get("episode_duration_ms") or 0) <= args.max_linear_duration_ms,
            }
            linear_gate["passed"] = bool(
                isinstance(semantic, (int, float))
                and semantic >= args.linear_threshold
                and all(linear_gate[key] for key in (
                    "score_status_ok", "scenario_ok", "protocol_ok",
                    "infrastructure_ok", "token_budget_ok",
                    "duration_budget_ok",
                ))
            )
            if not linear_gate["passed"]:
                break
    result_rows = [{
        "episode_id": score.get("episode_id"),
        "execution_mode": score.get("execution_mode"),
        "score_status": score.get("score_status"),
        "semantic_task_score": score.get("semantic_task_score"),
        "dynamic_control_score": score.get("dynamic_control_score"),
        "dt_score": score.get("dt_score"),
        "dynamic_dimension_scores": score.get("dynamic_dimension_scores"),
        "dynamic_decision_group_scores": score.get("dynamic_decision_group_scores"),
        "semantic_points": len(score.get("semantic_check_results") or []),
        "semantic_passed": sum(
            item.get("passed") is True for item in score.get("semantic_check_results") or []
        ),
        "dynamic_points_applicable": (score.get("control_flow_check_counts") or {}).get("applicable"),
        "dynamic_points_passed": (score.get("control_flow_check_counts") or {}).get("passed"),
        "scenario_constructed": score.get("scenario_constructed"),
        "scenario_exposed": score.get("scenario_exposure_complete"),
        "infrastructure_failures": score.get("infrastructure_failures"),
        "gateway_failure_count": score.get("gateway_failure_count"),
    } for score in scores]
    async_score = next(
        (score for score in scores if score.get("execution_mode") == "async"), None,
    )
    async_resource_gate = None
    if async_score is not None:
        async_resource_gate = {
            "max_total_tokens": args.max_async_tokens,
            "max_duration_ms": args.max_async_duration_ms,
            "observed_total_tokens": int(async_score.get("total_tokens") or 0),
            "observed_duration_ms": float(async_score.get("episode_duration_ms") or 0),
        }
        async_resource_gate["passed"] = bool(
            async_resource_gate["observed_total_tokens"] <= args.max_async_tokens
            and async_resource_gate["observed_duration_ms"] <= args.max_async_duration_ms
        )
    pair_status = "linear_gate_failed"
    if len(scores) == 2:
        pair_status = (
            "completed" if async_resource_gate and async_resource_gate["passed"]
            else "async_resource_gate_failed"
        )
    result = {
        "schema_version": "dynamic-pilot-pair-1",
        "pilot_id": args.pilot_id,
        "case_id": case.case_id,
        "model": model,
        "model_config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "status": pair_status,
        "linear_feasibility_gate": linear_gate,
        "async_resource_gate": async_resource_gate,
        "simulation_only": True,
        "official_track": False,
        "semantic_registry_points": row["semantic_points"],
        "dynamic_registry_points": row["dynamic_points"],
        "scores": result_rows,
    }
    (output / "pair-results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_dynamic_pilot_pair(args: argparse.Namespace) -> int:
    return asyncio.run(_run_dynamic_pilot_pair(args))


async def _run_dynamic_pilot_pipeline(args: argparse.Namespace) -> int:
    """Execute the complete fail-closed pilot pipeline from build to audit."""
    batch = Path(args.output).resolve()
    report = build_dynamic_pilot_batch(
        ROOT, batch, Path(args.human_review).resolve() if args.human_review else None,
    )
    preflight = preflight_dynamic_pilot_batch(batch, seed=args.seed)
    if preflight.get("passed") is not True:
        print(json.dumps({
            "batch": str(batch), "stage": "runtime_preflight",
            "passed": False, "preflight": preflight,
        }, ensure_ascii=False, indent=2))
        return 1
    configurations = {
        "gpt54": Path(args.gpt54_config).resolve(),
        "deepseek": Path(args.deepseek_config).resolve(),
    }
    pair_exit_codes: dict[str, int] = {}
    for case_row in report.get("cases") or []:
        if not case_row.get("experiment_selected", True):
            continue
        for model_directory, config_path in configurations.items():
            key = f"{model_directory}/{case_row['pilot_id']}"
            pair_exit_codes[key] = await _run_dynamic_pilot_pair(argparse.Namespace(
                batch=str(batch), pilot_id=case_row["pilot_id"],
                config=str(config_path),
                output=str(batch / "06-runs" / model_directory / case_row["pilot_id"]),
                seed=args.seed, timeout=args.timeout,
                linear_threshold=args.linear_threshold,
                max_linear_tokens=args.max_linear_tokens,
                max_linear_duration_ms=args.max_linear_duration_ms,
                max_async_tokens=args.max_async_tokens,
                max_async_duration_ms=args.max_async_duration_ms,
                gateway_grace=args.gateway_grace,
            ))
    audit = audit_dynamic_pilot_batch(batch)
    print(json.dumps({
        "batch": str(batch),
        "pair_exit_codes": pair_exit_codes,
        "batch_valid": audit["batch_valid"],
        "final_results": str((batch / "07-audit/final-results.json").resolve()),
    }, ensure_ascii=False, indent=2))
    return 0 if audit["batch_valid"] else 1


def cmd_dynamic_pilot_run(args: argparse.Namespace) -> int:
    return asyncio.run(_run_dynamic_pilot_pipeline(args))


async def _run_candidate_pair(args: argparse.Namespace) -> int:
    candidate_root = (ROOT / "candidate_instances").resolve()
    candidate = (candidate_root / args.family / args.candidate).resolve()
    try:
        candidate.relative_to(candidate_root)
    except ValueError:
        print("candidate path escapes candidate_instances/", file=sys.stderr)
        return 2
    metadata, errors = validate_candidate_instance(ROOT, args.family, candidate)
    if errors or metadata is None:
        print(json.dumps({"passed": False, "errors": errors}, indent=2), file=sys.stderr)
        return 1
    output = Path(args.output).resolve()
    if output.exists():
        print(f"candidate pair output already exists: {output}", file=sys.stderr)
        return 2
    output.mkdir(parents=True)
    config_path = Path(args.config).resolve() if args.config else None
    if config_path is not None and not config_path.is_file():
        print(f"model config not found: {config_path}", file=sys.stderr)
        return 2
    real_model_run = config_path is not None
    instance_id = str(metadata["instance_id"])
    pair_id = f"candidate-{args.family}-{instance_id}-{args.seed}"
    episodes = [
        {
            "episode_id": f"{pair_id}-linear",
            "execution_mode": "linear",
        },
        {
            "episode_id": f"{pair_id}-async",
            "execution_mode": "async",
        },
    ]
    manifest = {
        "manifest_version": "candidate-pair-1.0",
        "simulation_only": True,
        "official_track": False,
        "protocol_only": bool(args.protocol_only),
        "participant": "reference_scaffold_api" if real_model_run else "conformance_mock",
        "model_config_sha256": (
            hashlib.sha256(config_path.read_bytes()).hexdigest()
            if config_path is not None else None
        ),
        "case_id": args.family,
        "instance_id": instance_id,
        "counterfactual_pair_id": pair_id,
        "agent_seed": args.seed,
        "episodes": episodes,
    }
    (output / "pair-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    scores: list[dict] = []
    adapter = (
        [sys.executable, str(ROOT / "adapters" / "reference_scaffold_api.py"),
         "--config", str(config_path)]
        if config_path is not None else
        [sys.executable, "-m", "async_rbench.profiles.conformance_mock.adapter",
         "--workspace-mode", "container_clone"]
    )
    for index, episode in enumerate(episodes, 1):
        score = await run_episode(ROOT, EpisodeConfig(
            episode_id=episode["episode_id"],
            case_id=args.family,
            instance_id=instance_id,
            execution_mode=episode["execution_mode"],
            guidance="incentive",
            agent_seed=args.seed,
            adapter_command=adapter,
            output_dir=output / "episodes" / episode["episode_id"],
            repeat=0,
            counterfactual_pair_id=pair_id,
            timeout_sec=args.timeout,
            gateway_grace_sec=15,
            use_container=not args.protocol_only,
            build_image=(index == 1 and not args.protocol_only),
            keep_container=False,
            progress=True,
            episode_index=index,
            episode_total=len(episodes),
            adapter_profile=("reference_scaffold_api" if real_model_run else "conformance_mock"),
            runtime_mode=("api_only" if real_model_run else "conformance"),
            official_track=False,
            case_dir_override=candidate,
        ))
        scores.append(score)
    summary = {
        "schema_version": "1.0",
        "passed": all(
            score.get("scenario_constructed") is True
            and score.get("scenario_exposure_complete") is True
            for score in scores
        ),
        "simulation_only": True,
        "official_track": False,
        "protocol_only": bool(args.protocol_only),
        "participant": "reference_scaffold_api" if real_model_run else "conformance_mock",
        "model_config_sha256": manifest["model_config_sha256"],
        "case_id": args.family,
        "instance_id": instance_id,
        "counterfactual_pair_id": pair_id,
        "episode_count": len(scores),
        "scenario_constructed_count": sum(
            score.get("scenario_constructed") is True for score in scores
        ),
        "scenario_exposed_count": sum(
            score.get("scenario_exposure_complete") is True for score in scores
        ),
        "scores": [{
            "episode_id": score.get("episode_id"),
            "execution_mode": score.get("execution_mode"),
            "score_status": score.get("score_status"),
            "test_point_pass_rate": score.get("test_point_pass_rate"),
            "scenario_constructed": score.get("scenario_constructed"),
            "scenario_exposed": score.get("scenario_exposure_complete"),
            "scenario_entry": score.get("scenario_entry"),
            "infrastructure_failures": score.get("infrastructure_failures"),
        } for score in scores],
    }
    (output / "pair-results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


def cmd_candidate_pair_smoke(args: argparse.Namespace) -> int:
    return asyncio.run(_run_candidate_pair(args))


async def _run_candidate_family_pair(args: argparse.Namespace) -> int:
    candidate_root = (ROOT / "candidate_cases").resolve()
    # Keep the lexical candidate path for the containment check.  A published
    # revision may intentionally use a Windows directory junction to an
    # immutable registered bundle; resolving it first would incorrectly make
    # that zero-copy binding appear to escape candidate_cases/.
    candidate = candidate_root / args.candidate
    try:
        candidate.relative_to(candidate_root)
    except ValueError:
        print("candidate path escapes candidate_cases/", file=sys.stderr)
        return 2
    _, errors = _case_promote_prechecks(
        args.candidate, candidate, args.control_prefix,
        allow_existing_revision=True,
    )
    if errors:
        print(json.dumps({"passed": False, "errors": errors}, indent=2), file=sys.stderr)
        return 1
    output = Path(args.output).resolve()
    if output.exists():
        print(f"candidate family pair output already exists: {output}", file=sys.stderr)
        return 2
    output.mkdir(parents=True)
    pair_id = f"candidate-family-{args.candidate}-{args.seed}"
    episodes = [
        {"episode_id": f"{pair_id}-linear", "execution_mode": "linear"},
        {"episode_id": f"{pair_id}-async", "execution_mode": "async"},
    ]
    config_path = Path(args.config).resolve() if args.config else None
    if config_path is not None and not config_path.is_file():
        print(f"model config not found: {config_path}", file=sys.stderr)
        return 2
    real_model_run = config_path is not None
    manifest = {
        "manifest_version": "candidate-family-pair-1.0",
        "simulation_only": True,
        "official_track": False,
        "protocol_only": bool(args.protocol_only),
        "participant": "reference_scaffold_api" if real_model_run else "conformance_mock",
        "model_config_sha256": (
            hashlib.sha256(config_path.read_bytes()).hexdigest()
            if config_path is not None else None
        ),
        "case_id": args.candidate,
        "instance_id": "candidate-family",
        "counterfactual_pair_id": pair_id,
        "agent_seed": args.seed,
        "episodes": episodes,
    }
    (output / "pair-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    adapter = (
        [sys.executable, str(ROOT / "adapters" / "reference_scaffold_api.py"),
         "--config", str(config_path)]
        if config_path is not None else
        [sys.executable, "-m", "async_rbench.profiles.conformance_mock.adapter",
         "--workspace-mode", "container_clone"]
    )
    # A real participant may freely alter its container workspace. Give each
    # counterfactual arm a disposable case clone while keeping the original
    # candidate and the verifier inputs immutable for the entire pair.
    pair_workspace = Path(tempfile.mkdtemp(prefix="async-rbench-pair-"))
    verifier_case = pair_workspace / "verifier-source"
    copy_ignore = shutil.ignore_patterns("review_evidence", "__pycache__")
    shutil.copytree(candidate, verifier_case, ignore=copy_ignore)
    scores: list[dict] = []
    try:
        for index, episode in enumerate(episodes, 1):
            episode_case = pair_workspace / f"episode-{index}"
            shutil.copytree(verifier_case, episode_case, ignore=copy_ignore)
            scores.append(await run_episode(ROOT, EpisodeConfig(
            episode_id=episode["episode_id"],
            case_id=args.candidate,
            instance_id="candidate-family",
            execution_mode=episode["execution_mode"],
            guidance="incentive",
            agent_seed=args.seed,
            adapter_command=adapter,
            output_dir=output / "episodes" / episode["episode_id"],
            repeat=0,
            counterfactual_pair_id=pair_id,
            timeout_sec=args.timeout,
            gateway_grace_sec=15,
            use_container=not args.protocol_only,
            build_image=(index == 1 and not args.protocol_only),
            keep_container=False,
            progress=True,
            episode_index=index,
            episode_total=len(episodes),
            adapter_profile=("reference_scaffold_api" if real_model_run else "conformance_mock"),
            runtime_mode=("api_only" if real_model_run else "conformance"),
            official_track=False,
                case_dir_override=episode_case,
                verifier_task_dir=verifier_case / "task",
            )))
    finally:
        shutil.rmtree(pair_workspace, ignore_errors=True)
    summary = {
        "schema_version": "1.0",
        "passed": all(
            score.get("scenario_constructed") is True
            and score.get("scenario_exposure_complete") is True
            for score in scores
        ),
        "simulation_only": True,
        "official_track": False,
        "protocol_only": bool(args.protocol_only),
        "participant": "reference_scaffold_api" if real_model_run else "conformance_mock",
        "model_config_sha256": manifest["model_config_sha256"],
        "case_id": args.candidate,
        "instance_id": "candidate-family",
        "counterfactual_pair_id": pair_id,
        "episode_count": len(scores),
        "scenario_constructed_count": sum(
            score.get("scenario_constructed") is True for score in scores
        ),
        "scenario_exposed_count": sum(
            score.get("scenario_exposure_complete") is True for score in scores
        ),
        "scores": [{
            "episode_id": score.get("episode_id"),
            "execution_mode": score.get("execution_mode"),
            "score_status": score.get("score_status"),
            "test_point_pass_rate": score.get("test_point_pass_rate"),
            "scenario_constructed": score.get("scenario_constructed"),
            "scenario_exposed": score.get("scenario_exposure_complete"),
            "scenario_entry": score.get("scenario_entry"),
            "infrastructure_failures": score.get("infrastructure_failures"),
        } for score in scores],
    }
    (output / "pair-results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


def cmd_candidate_family_pair_smoke(args: argparse.Namespace) -> int:
    return asyncio.run(_run_candidate_family_pair(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="async_rbench")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument(
        "--release", action="store_true",
        help="Also certify the release gate: no Track A headline until frozen",
    )
    validate.set_defaults(func=cmd_validate)

    promote = sub.add_parser(
        "case-promote",
        help="Promote a candidate case into cases/ after passing every pre-check",
    )
    promote.add_argument("--candidate", required=True, help="case dir under candidate_cases/")
    promote.add_argument("--control-prefix", required=True, help="registry control-flow id prefix, e.g. gc/sp/sm")
    promote.add_argument("--yes", action="store_true", help="explicit consent; promotion is never automatic")
    promote.add_argument("--dry-run", action="store_true", help="run all pre-checks and stop")
    promote.set_defaults(func=cmd_case_promote)

    instance_promote = sub.add_parser(
        "instance-promote",
        help="Promote a human-approved candidate instance into an existing family",
    )
    instance_promote.add_argument("--family", required=True)
    instance_promote.add_argument(
        "--candidate", required=True,
        help="instance directory under candidate_instances/<family>/",
    )
    instance_promote.add_argument(
        "--yes", action="store_true", help="explicit consent; promotion is never automatic",
    )
    instance_promote.add_argument(
        "--dry-run", action="store_true", help="run every release gate without moving files",
    )
    instance_promote.set_defaults(func=cmd_instance_promote)

    instance_audit = sub.add_parser(
        "instance-audit",
        help="Inventory candidate instances and evaluate release gates without promotion",
    )
    instance_audit.add_argument("--output")
    instance_audit.set_defaults(func=cmd_instance_audit)

    instance_preflight = sub.add_parser(
        "instance-preflight",
        help="Execute build, Oracle, and isolated hidden verification for a candidate",
    )
    instance_preflight.add_argument("--family", required=True)
    instance_preflight.add_argument("--candidate", required=True)
    instance_preflight.add_argument("--output", required=True)
    instance_preflight.add_argument("--seed", type=int, default=1)
    instance_preflight.set_defaults(func=cmd_instance_preflight)

    candidate_quality = sub.add_parser(
        "candidate-quality-preflight",
        help="Run canonical and non-canonical equivalent solutions through one hidden verifier",
    )
    candidate_quality.add_argument("--candidate", required=True)
    candidate_quality.add_argument("--control-prefix", required=True)
    candidate_quality.add_argument("--output", required=True)
    candidate_quality.add_argument("--seed", type=int, default=1)
    candidate_quality.set_defaults(func=cmd_candidate_quality_preflight)

    build = sub.add_parser("build-all")
    build.add_argument("--output", required=True)
    build.add_argument("--seed", type=int, default=1)
    build.set_defaults(func=cmd_build_all)

    oracle = sub.add_parser("oracle-all")
    oracle.add_argument("--root", required=True)
    oracle.set_defaults(func=cmd_oracle_all)

    verify = sub.add_parser("verify-all")
    verify.add_argument("--root", required=True)
    verify.set_defaults(func=cmd_verify_all)

    validate = sub.add_parser(
        "validate-all",
        help="Run Oracle and verifier per registered task with lifecycle isolation",
    )
    validate.add_argument("--root", required=True)
    validate.add_argument("--output")
    validate.set_defaults(func=cmd_validate_all)

    calibration = sub.add_parser("calibration-audit")
    calibration.add_argument("--evidence-root", default="tests/calibration")
    calibration.set_defaults(func=cmd_calibration_audit)

    event_coverage = sub.add_parser(
        "event-coverage",
        help="Audit case event-theme, scenario-class and capability coverage separately",
    )
    event_coverage.add_argument("--output")
    event_coverage.set_defaults(func=cmd_event_coverage)

    dataset_audit = sub.add_parser(
        "dataset-audit",
        help="Audit split, event, scenario, difficulty, source and duplication quotas",
    )
    dataset_audit.add_argument("--output")
    dataset_audit.add_argument(
        "--require-publication-ready",
        action="store_true",
        help="Fail unless the full target dataset and every case quality contract are ready",
    )
    dataset_audit.set_defaults(func=cmd_dataset_audit)

    retrospective = sub.add_parser(
        "retrospective-quality-audit",
        help="Audit registered legacy instances against transformed-case publication gates",
    )
    retrospective.add_argument("--output", required=True)
    retrospective.set_defaults(func=cmd_retrospective_quality_audit)

    curation = sub.add_parser(
        "curation-init", help="Select public trajectories and build fixed-choice review forms",
    )
    curation.add_argument("--output", required=True)
    curation.add_argument("--manifest", default=DEFAULT_MANIFEST)
    curation.add_argument("--per-task", type=int, default=4)
    curation.add_argument("--download-artifacts", action="store_true")
    curation.set_defaults(func=cmd_curation_init)

    review = sub.add_parser(
        "curation-validate", help="Validate completed trajectory or decision reviews",
    )
    review.add_argument("--input", required=True)
    review.add_argument("--kind", required=True, choices=("trajectory", "decision"))
    review.set_defaults(func=cmd_curation_validate)

    render = sub.add_parser(
        "curation-render", help="Render fixed-choice trajectory or decision review HTML",
    )
    render.add_argument("--input", required=True)
    render.add_argument("--output", required=True)
    render.add_argument("--kind", required=True, choices=("trajectory", "decision"))
    render.set_defaults(func=cmd_curation_render)

    screen = sub.add_parser(
        "curation-screen",
        help="Download/read public trajectory archives and run rule or model coarse screening",
    )
    screen.add_argument("--input", required=True)
    screen.add_argument("--output", required=True)
    screen.add_argument("--mode", choices=("rules", "model"), default="rules")
    screen.add_argument("--config", help="Model profile YAML; required only in model mode")
    screen.add_argument("--key-file", default=str(ROOT / "apikey.txt"))
    screen.add_argument("--key-label", help="Optional apikey.txt label override")
    screen.add_argument("--task", action="append", help="Keep only this task id; repeatable")
    screen.add_argument("--agent", action="append", help="Keep only this source agent; repeatable")
    screen.add_argument(
        "--review-id", action="append", help="Keep only this trajectory review id; repeatable",
    )
    screen.add_argument("--limit", type=int)
    screen.add_argument("--max-prompt-chars", type=int, default=80000)
    screen.add_argument("--max-retries", type=int, default=1)
    screen.add_argument("--prepare-concurrency", type=int, default=8)
    screen.set_defaults(func=cmd_curation_screen)

    workspace = sub.add_parser(
        "curation-workspace", help="Assemble completed reviews with normalized traces side by side",
    )
    workspace.add_argument("--trajectory-input", required=True)
    workspace.add_argument("--decision-input", required=True)
    workspace.add_argument("--normalized-dir", action="append", required=True)
    workspace.add_argument("--output", required=True)
    workspace.set_defaults(func=cmd_curation_workspace)

    export_candidates = sub.add_parser(
        "curation-export-candidates",
        help="Export accepted human reviews into a non-promoting transformation backlog",
    )
    export_candidates.add_argument("--trajectory-input", required=True)
    export_candidates.add_argument("--decision-input", required=True)
    export_candidates.add_argument("--output", required=True)
    export_candidates.set_defaults(func=cmd_curation_export_candidates)

    simple_review = sub.add_parser(
        "curation-simple-review",
        help="Render neutral choice-only key-trajectory verification cards",
    )
    simple_review.add_argument("--input", required=True)
    simple_review.add_argument("--output", required=True)
    simple_review.set_defaults(func=cmd_curation_simple_review)

    simple_batch = sub.add_parser(
        "curation-build-simple-batch",
        help="Build a blind one-near-miss-per-trajectory standalone review batch",
    )
    simple_batch.add_argument("--normalized-dir", required=True)
    simple_batch.add_argument("--decisions", required=True)
    simple_batch.add_argument("--screening-labels", required=True)
    simple_batch.add_argument("--output", required=True)
    simple_batch.add_argument("--limit", type=int, default=50)
    simple_batch.set_defaults(func=cmd_curation_build_simple_batch)

    gaia2_review = sub.add_parser(
        "gaia2-structured-review",
        help="Build blind review cards from pinned GAIA2 causal event graphs",
    )
    gaia2_review.add_argument("--parquet", required=True)
    gaia2_review.add_argument("--output", required=True)
    gaia2_review.add_argument("--limit", type=int, default=50)
    gaia2_review.add_argument("--revision", default="78ea3bdbdeec2bdcd6afa542091")
    gaia2_review.set_defaults(func=cmd_gaia2_structured_review)

    calibration_batch = sub.add_parser(
        "curation-build-calibration-batch",
        help="Mix causal candidates and hard controls into one blinded pilot batch",
    )
    calibration_batch.add_argument("--candidates", required=True)
    calibration_batch.add_argument("--audit-controls", required=True)
    calibration_batch.add_argument("--output", required=True)
    calibration_batch.add_argument("--candidate-limit", type=int, default=42)
    calibration_batch.add_argument("--audit-limit", type=int, default=8)
    calibration_batch.add_argument("--seed", default="dtbench-calibration-v1")
    calibration_batch.set_defaults(func=cmd_curation_build_calibration_batch)

    paired_review_audit = sub.add_parser(
        "curation-audit-paired-reviews",
        help="Validate two completed blind-review files and build the adjudication queue",
    )
    paired_review_audit.add_argument("--input", required=True)
    paired_review_audit.add_argument("--source-map", required=True)
    paired_review_audit.add_argument("--annotations", action="append", required=True)
    paired_review_audit.add_argument("--output", required=True)
    paired_review_audit.set_defaults(func=cmd_curation_audit_paired_reviews)

    simulate_paired_reviews = sub.add_parser(
        "curation-simulate-paired-reviews",
        help="Generate two explicitly synthetic review files for pipeline testing",
    )
    simulate_paired_reviews.add_argument("--input", required=True)
    simulate_paired_reviews.add_argument("--source-map", required=True)
    simulate_paired_reviews.add_argument("--output", required=True)
    simulate_paired_reviews.add_argument("--reviewer-a", default="SIM-A")
    simulate_paired_reviews.add_argument("--reviewer-b", default="SIM-B")
    simulate_paired_reviews.set_defaults(func=cmd_curation_simulate_paired_reviews)

    collect_uncertain = sub.add_parser(
        "curation-collect-uncertain",
        help="Collect uncertain annotations into a blind expanded-context rereview queue",
    )
    collect_uncertain.add_argument("--input", required=True)
    collect_uncertain.add_argument("--annotations", required=True)
    collect_uncertain.add_argument("--output", required=True)
    collect_uncertain.set_defaults(func=cmd_curation_collect_uncertain)

    transformation_spec = sub.add_parser(
        "curation-build-transformation-spec",
        help="Bind confirmed choice-only reviews to an explicit technical case design",
    )
    transformation_spec.add_argument("--input", required=True)
    transformation_spec.add_argument("--annotations", action="append", required=True)
    transformation_spec.add_argument("--review-id")
    transformation_spec.add_argument("--plan", required=True)
    transformation_spec.add_argument("--output", required=True)
    transformation_spec.set_defaults(func=cmd_curation_build_transformation_spec)

    instance_scaffold = sub.add_parser(
        "instance-scaffold",
        help="Create an isolated candidate instance from an approved transformation spec",
    )
    instance_scaffold.add_argument("--spec", required=True)
    instance_scaffold.set_defaults(func=cmd_instance_scaffold)

    pipeline_pilot = sub.add_parser(
        "pipeline-pilot",
        help="Run a disclosed simulation-only screen-to-case mechanics pilot",
    )
    pipeline_pilot.add_argument("--config", required=True)
    pipeline_pilot.add_argument("--output", required=True)
    pipeline_pilot.set_defaults(func=cmd_pipeline_pilot)

    dynamic_pilot_build = sub.add_parser(
        "dynamic-pilot-build",
        help="Build a simulation-only three-family V7 task-causal pilot batch",
    )
    dynamic_pilot_build.add_argument("--output", required=True)
    dynamic_pilot_build.add_argument("--human-review")
    dynamic_pilot_build.set_defaults(func=cmd_dynamic_pilot_build)

    dynamic_pilot_pair = sub.add_parser(
        "dynamic-pilot-pair",
        help="Run one V7 pilot case as a real-model linear/async pair",
    )
    dynamic_pilot_pair.add_argument("--batch", required=True)
    dynamic_pilot_pair.add_argument("--pilot-id", required=True)
    dynamic_pilot_pair.add_argument("--config", required=True)
    dynamic_pilot_pair.add_argument("--output", required=True)
    dynamic_pilot_pair.add_argument("--seed", type=int, default=20260829)
    dynamic_pilot_pair.add_argument("--timeout", type=int, default=2400)
    dynamic_pilot_pair.add_argument("--linear-threshold", type=float, default=0.75)
    dynamic_pilot_pair.add_argument("--max-linear-tokens", type=int, default=500000)
    dynamic_pilot_pair.add_argument("--max-linear-duration-ms", type=int, default=1200000)
    dynamic_pilot_pair.add_argument("--max-async-tokens", type=int, default=500000)
    dynamic_pilot_pair.add_argument("--max-async-duration-ms", type=int, default=1200000)
    dynamic_pilot_pair.add_argument(
        "--gateway-grace", type=int, default=60,
        help="Maximum controlled hold in seconds before a live result is released",
    )
    dynamic_pilot_pair.set_defaults(func=cmd_dynamic_pilot_pair)

    dynamic_pilot_preflight = sub.add_parser(
        "dynamic-pilot-preflight",
        help="Run build, Oracle and isolated verifier for every selected pilot case",
    )
    dynamic_pilot_preflight.add_argument("--batch", required=True)
    dynamic_pilot_preflight.add_argument("--seed", type=int, default=20260829)
    dynamic_pilot_preflight.set_defaults(func=cmd_dynamic_pilot_preflight)

    dynamic_pilot_audit = sub.add_parser(
        "dynamic-pilot-audit",
        help="Aggregate real pilot runs and apply leakage/feasibility/calibration gates",
    )
    dynamic_pilot_audit.add_argument("--batch", required=True)
    dynamic_pilot_audit.set_defaults(func=cmd_dynamic_pilot_audit)

    dynamic_pilot_run = sub.add_parser(
        "dynamic-pilot-run",
        help="Run build, runtime preflight, two-model pairs and final audit as one pipeline",
    )
    dynamic_pilot_run.add_argument("--output", required=True)
    dynamic_pilot_run.add_argument("--human-review")
    dynamic_pilot_run.add_argument("--gpt54-config", required=True)
    dynamic_pilot_run.add_argument("--deepseek-config", required=True)
    dynamic_pilot_run.add_argument("--seed", type=int, default=20260829)
    dynamic_pilot_run.add_argument("--timeout", type=int, default=2400)
    dynamic_pilot_run.add_argument("--linear-threshold", type=float, default=0.75)
    dynamic_pilot_run.add_argument("--max-linear-tokens", type=int, default=500000)
    dynamic_pilot_run.add_argument("--max-linear-duration-ms", type=int, default=1200000)
    dynamic_pilot_run.add_argument("--max-async-tokens", type=int, default=500000)
    dynamic_pilot_run.add_argument("--max-async-duration-ms", type=int, default=1200000)
    dynamic_pilot_run.add_argument("--gateway-grace", type=int, default=60)
    dynamic_pilot_run.set_defaults(func=cmd_dynamic_pilot_run)

    candidate_pair = sub.add_parser(
        "candidate-pair-smoke",
        help="Run a non-registered candidate in paired linear/async development episodes",
    )
    candidate_pair.add_argument("--family", required=True)
    candidate_pair.add_argument("--candidate", required=True)
    candidate_pair.add_argument("--output", required=True)
    candidate_pair.add_argument("--seed", type=int, default=2026)
    candidate_pair.add_argument("--timeout", type=int, default=1800)
    candidate_pair.add_argument(
        "--config",
        help="Optional real-model scaffold YAML; omission keeps the scripted smoke backend",
    )
    candidate_pair.add_argument(
        "--protocol-only", action="store_true",
        help="Disable task workspace/verifier and test only paired event delivery semantics",
    )
    candidate_pair.set_defaults(func=cmd_candidate_pair_smoke)

    candidate_family_pair = sub.add_parser(
        "candidate-family-pair-smoke",
        help="Run an unregistered candidate family in paired linear/async episodes",
    )
    candidate_family_pair.add_argument("--candidate", required=True)
    candidate_family_pair.add_argument("--control-prefix", required=True)
    candidate_family_pair.add_argument("--output", required=True)
    candidate_family_pair.add_argument("--seed", type=int, default=2026)
    candidate_family_pair.add_argument("--timeout", type=int, default=1800)
    candidate_family_pair.add_argument("--protocol-only", action="store_true")
    candidate_family_pair.add_argument(
        "--config",
        help="Optional real-model scaffold YAML; omission keeps the scripted smoke backend",
    )
    candidate_family_pair.set_defaults(func=cmd_candidate_family_pair_smoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
