from __future__ import annotations

import argparse
import asyncio
import json
import hashlib
import sys
from pathlib import Path

from .conformance import conformance_adapter_command, run_conformance
from .evaluation.aggregate import aggregate_reports, load_reports
from .evaluation.audit import audit_run
from .evaluation.guidance import GUIDANCE_MODES, render_guidance
from .evaluation.manifest import EXECUTION_MODES, create_manifest, write_manifest
from .evaluation.protocol import canonical_digest, load_trace
from .evaluation.runner import (
    EpisodeConfig, _case_digest, _evaluation_contract_identity, _source_digest,
    parse_adapter_command, run_episode,
)
from .evaluation.resource_policy import validate_official_resource_policy
from .evaluation.scoring import score_trace
from .evaluation.termination import score_status_decision
from .evaluation.version import EVALUATION_CONTRACT_VERSION
from .private_eval import verifier_bundle_sha256
from .profiles import RUNTIME_MODES, load_profile
from .spec import (
    case_instance_key, discover_cases, load_case, resolve_case_instance,
)


ROOT = Path(__file__).resolve().parents[1]
RUN_BINDING_VERSION = "1.0"
RUN_BINDING_FILENAME = "run-binding.json"


def _command_entrypoint(command: list[str]) -> tuple[str, ...]:
    """Return the executable/script identity, excluding runtime arguments."""
    if not command:
        return ()
    if len(command) >= 2 and Path(command[0]).stem.lower() in {"python", "python3", "py"}:
        return ("python-script", str(Path(command[1]).resolve()).lower())
    return (Path(command[0]).name.lower(),)


def _append_config(command: list[str], config_path: Path | None) -> list[str]:
    if config_path is None or "--config" in command:
        return list(command)
    return [*command, "--config", str(config_path)]


def _conformance_binding_digest(
    command: list[str], profile_name: str | None, config_path: Path | None,
) -> str:
    config_sha256 = (
        hashlib.sha256(config_path.read_bytes()).hexdigest()
        if config_path is not None else None
    )
    return canonical_digest({
        "adapter_command": command,
        "adapter_profile": profile_name,
        "config_sha256": config_sha256,
    })


def _ensure_run_binding(
    output_root: Path,
    *,
    manifest_sha256: str,
    adapter_profile: str | None,
    runtime_mode: str | None,
    conformance_binding_sha256: str,
    resource_policy_sha256: str | None,
    model: object,
) -> None:
    """Pin execution factors before an output directory can contain scores."""
    binding_path = output_root / RUN_BINDING_FILENAME
    expected = {
        "binding_version": RUN_BINDING_VERSION,
        "manifest_sha256": manifest_sha256,
        "adapter_profile": adapter_profile,
        "runtime_mode": runtime_mode,
        "conformance_binding_sha256": conformance_binding_sha256,
        "resource_policy_sha256": resource_policy_sha256,
        "model": model,
    }
    if binding_path.is_file():
        observed = json.loads(binding_path.read_text(encoding="utf-8"))
        if not isinstance(observed, dict):
            raise ValueError("run binding must be a JSON object")
        mismatches = sorted(
            key for key, value in expected.items() if observed.get(key) != value
        )
        if mismatches:
            raise ValueError("run binding drift: " + ", ".join(mismatches))
        return
    existing_scores = list(output_root.glob("*/score.json")) if output_root.is_dir() else []
    if existing_scores:
        raise ValueError(
            "run binding is missing for existing scores; use a fresh output directory"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    binding_path.write_text(
        json.dumps(expected, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def cmd_make_manifest(args) -> int:
    if args.cases and args.instances:
        raise ValueError("use either --cases or --instances, not both")
    case_ids = args.cases or [case.case_id for case in discover_cases(ROOT)]
    manifest = create_manifest(
        case_ids, args.repetitions, args.guidance, args.seed, args.execution_modes,
        args.instances, model=(args.model or None),
    )
    write_manifest(Path(args.output).resolve(), manifest)
    print(json.dumps({"episodes": len(manifest["episodes"]), "output": str(Path(args.output).resolve())}, indent=2))
    return 0


def cmd_guidance(args) -> int:
    print(render_guidance(args.mode)); return 0


def cmd_score(args) -> int:
    if getattr(args, "legacy", False):
        raise ValueError(
            "legacy trace.jsonl (protocol 1.0) is not loadable by contract 10.1.1; "
            "create and rerun a new manifest with the current repository"
        )
    trace_path = Path(args.trace).resolve()
    instance = resolve_case_instance(ROOT, args.case, args.instance)
    case_path = instance.contract_path
    case_spec = load_case(case_path).raw
    semantic_registry = json.loads(
        (instance.case_dir / "task/tests/semantic_checks.json").read_text(encoding="utf-8")
    )
    control_registry = json.loads(
        (instance.case_dir / "task/tests/control_flow_checks.json").read_text(encoding="utf-8")
    )
    report = score_trace(
        load_trace(trace_path), case_spec, args.execution_mode,
        semantic_registry=semantic_registry,
        control_flow_checks=list(control_registry.get("checks") or []),
        event_contracts=list(control_registry.get("event_contracts") or []),
    )
    # An offline re-score must remain joinable to its original manifest episode.
    # Inherit only run identity/provenance from the sibling score; all scoring
    # fields and the evaluation-policy binding are recomputed above.
    source_score_path = trace_path.with_name("score.json")
    source_metadata: dict[str, object] = {}
    if source_score_path.is_file():
        source_score = json.loads(source_score_path.read_text(encoding="utf-8"))
        expected_identity = {
            "case_id": args.case,
            "instance_id": args.instance,
            "execution_mode": args.execution_mode,
        }
        mismatches = [
            key for key, expected in expected_identity.items()
            if source_score.get(key) not in {None, expected}
        ]
        if mismatches:
            raise ValueError(
                "source score identity does not match offline re-score arguments: "
                + ", ".join(mismatches)
            )
        metadata_fields = (
            "episode_id", "case_id", "instance_id", "execution_mode",
            "counterfactual_pair_id", "guidance", "repeat", "agent_seed",
            "adapter_profile", "runtime_mode", "execution_tier",
            "requested_model", "resolved_model", "participant_image_id",
            "case_sha256", "verifier_bundle_sha256", "manifest_sha256",
            "manifest_episode_count", "manifest_episode_ids_sha256",
            "controlled_order", "capability_categories", "total_tokens",
            "main_tokens", "child_tokens", "episode_duration_ms",
        )
        source_metadata = {
            key: source_score[key] for key in metadata_fields if key in source_score
        }
    report.update(source_metadata)
    # Scored status is benchmark-owned: the scenario must have been constructed
    # for a measurement to exist.  Under the Task-11 protocol the headline
    # evidence is the Base Task Score (and, for async, the Async DRS); the legacy
    # semantic / dynamic_control fields remain as fallbacks so offline rescoring
    # of pre-rollover records still classifies them.
    has_base_evidence = (
        report.get("base_task_score") is not None
        or report.get("semantic_task_score") is not None
    )
    async_evidence = (
        report.get("async_drs") is not None
        or report.get("dynamic_control_score") is not None
    )
    score_status, score_status_reason = score_status_decision(
        scenario_constructed=report.get("scenario_constructed"),
        score_integrity_ok=(
            has_base_evidence
            and (args.execution_mode != "async" or async_evidence)
        ),
        integrity_reason="score_evidence_incomplete",
        trace_exclusion_reason=report.get("trace_score_status_reason"),
    )
    report.update({
        "score_status": score_status,
        "score_status_reason": score_status_reason,
        "case_id": args.case,
        "instance_id": args.instance,
        "execution_mode": args.execution_mode,
        "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
        "leaderboard_eligible": False,
        "leaderboard_ineligibility_reasons": ["offline_rescore"],
        "offline_rescore": True,
    })
    output = Path(args.output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2)); return 0


def cmd_conformance(args) -> int:
    case_ids = args.cases or [case.case_id for case in discover_cases(ROOT)]
    output = Path(args.output).resolve()
    profile = load_profile(args.profile) if args.profile else None
    config_path = Path(args.config).resolve() if args.config else None
    if args.adapter_command:
        adapter_command = _append_config(parse_adapter_command(args.adapter_command), config_path)
    elif profile is not None:
        adapter_command = None  # resolved from the profile inside run_conformance
    else:
        # Backward-compatible smoke: the built-in protocol-only mock.
        adapter_command = [sys.executable, str(ROOT / "adapters" / "conformance_mock.py")]
    result = asyncio.run(run_conformance(
        ROOT,
        adapter_command=adapter_command,
        profile=profile,
        config_path=config_path,
        output_dir=output,
        case_ids=case_ids,
    ))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["conformance_passed"] else 1


def cmd_aggregate(args) -> int:
    if getattr(args, "legacy", False):
        raise ValueError(
            "legacy score.json artifacts are not loadable by contract 10.1.1; "
            "create and rerun a new manifest with the current repository"
        )
    root = Path(args.root).resolve()
    records = load_reports(root)
    manifest_path = (
        Path(args.manifest).resolve()
        if getattr(args, "manifest", None)
        else root.parent / "manifest.json"
    )
    planned_episodes = None
    if manifest_path.is_file():
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        planned_episodes = list(manifest.get("episodes") or [])
        manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
        mismatched = [
            str(item.get("episode_id")) for item in records
            if item.get("manifest_sha256") not in {None, manifest_digest}
        ]
        if mismatched:
            raise ValueError(
                "aggregate manifest does not match score records: "
                + ", ".join(sorted(mismatched))
            )
    minimum_coverage = (
        args.minimum_counterfactual_coverage
        if args.minimum_counterfactual_coverage is not None else 0.0
    )
    report = aggregate_reports(
        records, args.bootstrap_iterations, minimum_coverage,
        planned_episodes=planned_episodes,
    )
    output = Path(args.output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2))
    hard_fail = report["audit"]["hard_fail"]
    if hard_fail:
        print(
            "aggregate hard-fail: " + ", ".join(report["audit"]["hard_fail_reasons"]),
            file=sys.stderr,
        )
    return 1 if hard_fail else 0


def cmd_audit_run(args) -> int:
    root = Path(args.root).resolve()
    report = audit_run(root, ROOT)
    gates = {
        "contract_fixtures_passed": report["contract_fixtures"]["passed"] is True,
        # A run with zero audited episodes certifies nothing about the manifest.
        "episodes_present": int(report["episode_count"]) > 0,
        # Digest drift against the current benchmark tree must fail the audit.
        "artifact_digests_match_current": (
            report["artifact_compatibility"]["all_episodes_match_current"] is True
            if int(report["episode_count"]) > 0 else False
        ),
    }
    manifest_path = root.parent / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_bytes())
        planned_ids = {
            str(item["episode_id"]) for item in manifest.get("episodes") or []
            if item.get("episode_id") is not None
        }
        audited_case_ids = {
            str(item.get("case_id")) for item in report["resources"]["episodes"]
        }
        planned_case_ids = {
            str(item.get("case_id")) for item in manifest.get("episodes") or []
        }
        gates["manifest_complete"] = bool(planned_ids) and planned_case_ids <= audited_case_ids
        report["manifest_audit"] = {
            "planned_episode_count": len(planned_ids),
            "observed_episode_count": int(report["episode_count"]),
            "missing_case_ids": sorted(planned_case_ids - audited_case_ids),
        }
    else:
        gates["manifest_complete"] = None  # no manifest bound to this run root
    # Task 10: surface every audit hard-fail reason as an explicit pass-gate so
    # audit-run exits nonzero when the contract fixtures fail, a submission-stage
    # validator hides a private constraint, a private-only rejection reached the
    # scorer, a spawned child was still in flight when its episode closed, or an
    # official Linear run recorded zero main tokens.
    for reason in (
        "contract_fixture_failure",
        "hidden_submission_constraint",
        "private_submission_rejection",
        "unknown_child_terminal",
        "official_linear_zero_main_tokens",
    ):
        gates[f"no_{reason}"] = reason not in (report.get("hard_fail_reasons") or [])
    report["gates"] = gates
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("hard_fail"):
        print(
            "audit-run hard-fail: " + ", ".join(report.get("hard_fail_reasons") or []),
            file=sys.stderr,
        )
    hard_gates = [value for value in gates.values() if value is not None]
    return 0 if hard_gates and all(hard_gates) else 1


async def _run_manifest(args) -> int:
    manifest_path = Path(args.manifest).resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("manifest_version") != "4.0":
        raise ValueError("run-manifest accepts only manifest_version 4.0")
    episodes = manifest.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        raise ValueError("manifest episodes must be a non-empty list")
    if any(not str(item.get("instance_id") or "").strip() for item in episodes):
        raise ValueError("manifest 4.0 requires instance_id on every episode")
    pair_bindings: dict[str, tuple[object, ...]] = {}
    pair_modes: dict[str, set[str]] = {}
    for item in episodes:
        pair_id = str(item.get("counterfactual_pair_id") or "")
        if not pair_id:
            raise ValueError("manifest 4.0 requires counterfactual_pair_id on every episode")
        binding = (
            str(item.get("case_id")), str(item.get("instance_id")),
            item.get("repeat", 0), str(item.get("guidance")), item.get("agent_seed"),
        )
        if pair_id in pair_bindings and pair_bindings[pair_id] != binding:
            raise ValueError(f"counterfactual pair {pair_id!r} mixes instance bindings")
        pair_bindings[pair_id] = binding
        mode = str(item.get("execution_mode") or "")
        if mode in pair_modes.setdefault(pair_id, set()):
            raise ValueError(f"counterfactual pair {pair_id!r} repeats mode {mode!r}")
        pair_modes[pair_id].add(mode)
    output_root = Path(args.output).resolve()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    expected_episode_ids = sorted(str(item["episode_id"]) for item in episodes)
    if len(expected_episode_ids) != len(set(expected_episode_ids)):
        raise ValueError("manifest episode_id values must be unique")
    manifest_episode_ids_sha256 = canonical_digest(expected_episode_ids)
    manifest_episode_count = len(expected_episode_ids)
    current_source_digest = _source_digest(ROOT)
    current_contract_version, current_contract_digest = _evaluation_contract_identity(ROOT)
    # Integrity checks run for every experiment, not just a strict mode: the
    # manifest must pin the frozen contract and the exact verifier bundles.
    if manifest.get("evaluation_contract_version") != EVALUATION_CONTRACT_VERSION:
        raise ValueError(
            "manifest evaluation contract version differs from the frozen executable version"
        )
    if manifest.get("evaluation_contract_sha256") != current_contract_digest:
        raise ValueError("manifest evaluation contract digest has drifted")
    pinned_verifiers = manifest.get("verifier_bundle_sha256") or {}
    pinned_cases = manifest.get("case_bundle_sha256") or {}
    manifest_instances = {
        (str(item["case_id"]), str(item.get("instance_id") or "seed-1"))
        for item in episodes
    }
    expected_digest_keys = {
        case_instance_key(case_id, instance_id)
        for case_id, instance_id in manifest_instances
    }
    if set(pinned_verifiers) != expected_digest_keys:
        raise ValueError("manifest verifier digest keys do not match its registered instances")
    if set(pinned_cases) != expected_digest_keys:
        raise ValueError("manifest case digest keys do not match its registered instances")
    for case_id, instance_id in manifest_instances:
        instance = resolve_case_instance(ROOT, case_id, instance_id)
        digest_key = case_instance_key(case_id, instance_id)
        current_verifier_digest = verifier_bundle_sha256(instance.case_dir / "task")
        if pinned_verifiers.get(digest_key) != current_verifier_digest:
            raise ValueError(
                f"manifest verifier bundle digest has drifted for {case_id}/{instance_id}"
            )
        current_case_digest = _case_digest(instance.case_dir)
        if pinned_cases.get(digest_key) != current_case_digest:
            raise ValueError(
                f"manifest case bundle digest has drifted for {case_id}/{instance_id}"
            )
    official_track = bool(getattr(args, "official_track", False))
    if official_track:
        if getattr(args, "adapter_command", None):
            raise ValueError("official Track A forbids --adapter-command")
        if getattr(args, "skip_conformance", False):
            raise ValueError("official Track A forbids --skip-conformance")
        if getattr(args, "no_container", False):
            raise ValueError("official Track A requires container isolation")
        requested_profile = getattr(args, "profile", None)
        requested_mode = getattr(args, "runtime_mode", None)
        if requested_profile not in (None, "reference_scaffold_api"):
            raise ValueError("official Track A requires profile reference_scaffold_api")
        if requested_mode not in (None, "api_only"):
            raise ValueError("official Track A requires runtime mode api_only")
        args.profile = "reference_scaffold_api"
        args.runtime_mode = "api_only"

    runtime_mode = getattr(args, "runtime_mode", None)
    profile_name = getattr(args, "profile", None) or {
        "api_only": "reference_scaffold_api",
        "native_agent": "native_agent",
        "minimal": "minimal_api",
        "conformance": "conformance_mock",
    }.get(runtime_mode or "")
    profile = load_profile(profile_name) if profile_name else None
    if args.adapter_command:
        command = parse_adapter_command(args.adapter_command)
    elif profile is not None:
        command = list(profile.adapter_command)
    else:
        raise ValueError("run-manifest requires --adapter-command or --runtime-mode/--profile")
    config_path = Path(args.config).resolve() if getattr(args, "config", None) else None
    command = _append_config(command, config_path)
    conformance_binding_sha256 = _conformance_binding_digest(
        command, profile_name, config_path,
    )
    resource_policy_sha256 = None
    if official_track:
        resource_policy_sha256 = validate_official_resource_policy(
            ROOT, config_path,
            episode_timeout_sec=int(args.timeout),
            gateway_grace_sec=int(args.gateway_grace),
        )
    _ensure_run_binding(
        output_root,
        manifest_sha256=manifest_sha256,
        adapter_profile=profile_name,
        runtime_mode=runtime_mode,
        conformance_binding_sha256=conformance_binding_sha256,
        resource_policy_sha256=resource_policy_sha256,
        model=manifest.get("model"),
    )
    if profile is not None and _command_entrypoint(command) != _command_entrypoint(profile.adapter_command):
        raise ValueError("adapter command entrypoint does not match the selected profile")
    # Bind the conformance gate to the actual profile before running any
    # episode: the same adapter that runs the manifest should first pass the
    # protocol suite in its deterministic, no-model/no-Docker conformance mode.
    # A requested conformance run is a gate: a failing adapter must not consume
    # model calls or produce episode scores.  Development callers that need to
    # inspect a non-conformant adapter can opt out explicitly with
    # ``--skip-conformance``.
    conformance_passed: bool | None = None
    if not getattr(args, "skip_conformance", False) and profile is not None:
        conformance_result = await run_conformance(
            ROOT,
            adapter_command=conformance_adapter_command(
                profile, config_path=config_path, base_command=command,
            ),
            output_dir=output_root / ".conformance",
            case_ids=sorted({str(item["case_id"]) for item in manifest["episodes"]}),
            progress=(
                (lambda message: print(message, flush=True))
                if not getattr(args, "no_progress", False) else None
            ),
        )
        conformance_passed = bool(conformance_result["conformance_passed"])
        if conformance_passed is not True:
            raise ValueError(
                "adapter conformance failed; episodes were not started "
                "(use --skip-conformance only for explicit development diagnostics)"
            )
    if official_track and conformance_passed is not True:
        raise ValueError("official Track A requires a passing conformance run")
    built: set[tuple[str, str]] = set(); scores = []
    total_episodes = len(episodes)
    for episode_index, episode in enumerate(episodes, start=1):
        case_id = episode["case_id"]
        instance_id = str(episode.get("instance_id") or "seed-1")
        instance = resolve_case_instance(ROOT, str(case_id), instance_id)
        build_key = (str(case_id), instance_id)
        execution_mode = str(episode.get("execution_mode") or "")
        if execution_mode not in EXECUTION_MODES:
            raise ValueError(f"unknown execution mode in manifest: {execution_mode!r}")
        episode_output = output_root / episode["episode_id"]
        existing_score = episode_output / "score.json"
        if args.resume and existing_score.is_file():
            prior = json.loads(existing_score.read_text(encoding="utf-8"))
            if prior.get("manifest_sha256") != manifest_sha256:
                raise ValueError(f"resume rejected manifest mismatch for {episode['episode_id']}")
            if prior.get("scaffold_and_protocol_sha256") != current_source_digest:
                raise ValueError(
                    f"resume rejected evaluator source drift for {episode['episode_id']}; "
                    "data must be rerun from a fresh output directory"
                )
            if (
                prior.get("evaluation_contract_version") != current_contract_version
                or prior.get("evaluation_contract_sha256") != current_contract_digest
            ):
                raise ValueError(
                    f"resume rejected evaluation contract drift for {episode['episode_id']}"
                )
            current_verifier_digest = verifier_bundle_sha256(
                instance.case_dir / "task"
            )
            if prior.get("verifier_bundle_sha256") != current_verifier_digest:
                raise ValueError(
                    f"resume rejected verifier bundle drift for {episode['episode_id']}"
                )
            if prior.get("case_sha256") != _case_digest(instance.case_dir):
                raise ValueError(
                    f"resume rejected case instance drift for {episode['episode_id']}"
                )
            retained_binding = {
                "conformance_binding_sha256": conformance_binding_sha256,
                "adapter_profile": profile_name,
                "runtime_mode": runtime_mode,
                "resource_policy_sha256": resource_policy_sha256,
                "model": episode.get("model"),
            }
            binding_mismatches = sorted(
                key for key, value in retained_binding.items()
                if prior.get(key) != value
            )
            if binding_mismatches:
                raise ValueError(
                    f"resume rejected adapter binding drift for {episode['episode_id']}: "
                    + ", ".join(binding_mismatches)
                )
            scores.append(prior)
            if not args.no_progress:
                print(
                    f"[DTB2 {episode_index}/{total_episodes} {case_id} {execution_mode} resume] "
                    "existing score retained",
                    flush=True,
                )
            continue
        config = EpisodeConfig(
            episode_id=episode["episode_id"], case_id=case_id, execution_mode=execution_mode,
            guidance=episode["guidance"], agent_seed=episode["agent_seed"], adapter_command=command,
            output_dir=episode_output,
            instance_id=instance_id, repeat=episode.get("repeat", 0),
            counterfactual_pair_id=episode.get("counterfactual_pair_id"), timeout_sec=args.timeout,
            gateway_grace_sec=args.gateway_grace,
            use_container=not args.no_container,
            build_image=not args.no_container and build_key not in built,
            keep_container=args.keep_containers,
            manifest_sha256=manifest_sha256,
            manifest_episode_ids_sha256=manifest_episode_ids_sha256,
            manifest_episode_count=manifest_episode_count,
            progress=not args.no_progress,
            progress_heartbeat_sec=args.progress_heartbeat,
            episode_index=episode_index, episode_total=total_episodes,
            conformance_passed=conformance_passed,
            runtime_mode=runtime_mode, adapter_profile=profile_name,
            conformance_binding_sha256=conformance_binding_sha256,
            official_track=official_track,
            resource_policy_sha256=resource_policy_sha256,
            split=episode.get("split", "unassigned"),
            model=episode.get("model"),
        )
        scores.append(await run_episode(ROOT, config)); built.add(build_key)
        print(json.dumps({
            "episode": config.episode_id,
            "score_status": scores[-1]["score_status"],
            "base_task_score": scores[-1].get("base_task_score"),
            "async_drs": scores[-1].get("async_drs"),
            # legacy fields, retained so pre-rollover progress lines stay comparable
            "dynamic_control_score": scores[-1].get("dynamic_control_score"),
            "semantic_task_score": scores[-1].get("semantic_task_score"),
            "dt_score": scores[-1].get("dt_score"),
            "dynamic_success": scores[-1].get("dynamic_success"),
        }))
    return 0


def cmd_run_manifest(args) -> int:
    return asyncio.run(_run_manifest(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m async_rbench.eval_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    manifest = sub.add_parser("make-manifest")
    manifest.add_argument("--output", required=True); manifest.add_argument("--repetitions", type=int, default=3)
    manifest.add_argument("--guidance", choices=GUIDANCE_MODES, default="incentive"); manifest.add_argument("--seed", type=int, default=2026)
    manifest.add_argument("--cases", nargs="*"); manifest.add_argument(
        "--execution-modes", nargs="*", choices=EXECUTION_MODES,
    )
    manifest.add_argument(
        "--instances", nargs="*",
        help="Registered case_id::instance_id keys; cannot be combined with --cases",
    )
    manifest.add_argument(
        "--model", default=None,
        help="single formal model name stamped on every episode; use the provider config's "
        "main_model (configs/model-profiles/*.yaml)",
    )
    manifest.set_defaults(func=cmd_make_manifest)
    guidance = sub.add_parser("show-guidance"); guidance.add_argument("mode", choices=GUIDANCE_MODES); guidance.set_defaults(func=cmd_guidance)
    score = sub.add_parser("score")
    score.add_argument("--trace", required=True); score.add_argument("--case", required=True)
    score.add_argument("--instance", default="seed-1")
    score.add_argument(
        "--execution-mode", required=True, choices=EXECUTION_MODES,
    ); score.add_argument("--output", required=True)
    score.add_argument(
        "--legacy", action="store_true",
        help="Report that protocol-1.0 traces are not loadable by contract 10.1.1",
    )
    score.set_defaults(func=cmd_score)
    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--root", required=True); aggregate.add_argument("--output", required=True)
    aggregate.add_argument(
        "--manifest",
        help="Manifest that defines planned episode and pair coverage; defaults to <root>/../manifest.json",
    )
    aggregate.add_argument("--bootstrap-iterations", type=int, default=1000)
    aggregate.add_argument(
        "--minimum-counterfactual-coverage", type=float,
        help="Minimum digest-equal A/B pair coverage required for controlled-order audit eligibility (default: 0.0)",
    )
    aggregate.add_argument(
        "--legacy", action="store_true",
        help="Report that legacy scores are not loadable by contract 10.1.1",
    )
    aggregate.set_defaults(func=cmd_aggregate)
    audit = sub.add_parser("audit-run")
    audit.add_argument("--root", required=True, help="Directory containing episode score/event-source files")
    audit.add_argument("--output", required=True, help="Path for the machine-readable audit report")
    audit.set_defaults(func=cmd_audit_run)
    conformance = sub.add_parser("conformance")
    conformance.add_argument("--output", required=True)
    conformance.add_argument(
        "--cases", nargs="*",
        help="Case ids to run conformance against (default: all discovered cases)",
    )
    conformance.add_argument("--profile", help="Adapter profile name or YAML path to run conformance against")
    conformance.add_argument("--adapter-command", help="Explicit adapter command (overrides --profile)")
    conformance.add_argument("--config", help="YAML config path passed to the adapter as --config")
    conformance.set_defaults(func=cmd_conformance)
    run = sub.add_parser("run-manifest")
    run.add_argument("--manifest", required=True); run.add_argument("--output", required=True)
    run.add_argument("--adapter-command", help="Override the adapter command (default: the selected profile's)")
    run.add_argument("--runtime-mode", choices=RUNTIME_MODES, help="Runtime mode selects the adapter profile")
    run.add_argument("--profile", help="Adapter profile name or YAML path (overrides --runtime-mode)")
    run.add_argument("--config", help="Participant config path bound to both conformance and manifest episodes")
    run.add_argument("--timeout", type=int, default=2400); run.add_argument("--gateway-grace", type=int, default=15)
    run.add_argument("--no-container", action="store_true"); run.add_argument("--keep-containers", action="store_true")
    run.add_argument("--no-progress", action="store_true", help="Disable live human-readable progress lines")
    run.add_argument("--progress-heartbeat", type=int, default=30, help="Seconds between waiting heartbeats")
    run.add_argument("--resume", action="store_true", help="Resume only manifest-matched completed episodes")
    run.add_argument(
        "--official-track", action="store_true",
        help="Run formal Track A: fixed reference harness, API-only backend, containers and conformance are mandatory",
    )
    run.add_argument(
        "--skip-conformance", action="store_true",
        help="Skip the pre-run conformance gate (development only; keeps conformance_passed unset)",
    )
    run.set_defaults(func=cmd_run_manifest)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv); return int(args.func(args))


if __name__ == "__main__": raise SystemExit(main())
