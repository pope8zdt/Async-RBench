from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import subprocess
import hashlib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Sequence

import yaml

from .guidance import render_guidance
from .protocol import (
    CAPABILITY_REQUEST, CAPABILITY_RESPONSE, ProtocolError, TraceRecorder,
    canonical_digest, validate_adapter_event,
)
from .workspace_runtime import (
    CommandResult, DisabledWorkspaceRuntime, WorkspaceRuntime, build_workspace_runtime,
)
from .result_contract import (
    ResultContractValidation,
    evaluate_private_semantics,
    validate_completion_contract,
)
from .scheduler import DeliveryController
from .scoring import score_trace
from .event_store import EventStore, strip_for_adapter
from .observation import (
    ObservationPoint, ProvisionalObserver, WorkspaceSnapshot,
    parse_observation_output, snapshot_observation_command,
)
from .case_contract import assert_participant_safe
from .case_contract import public_delivery, public_rejection
from .case_contract import validate_scoring_domains
from .case_bundle import case_bundle_sha256
from .version import EVALUATION_CONTRACT_STATUS, EVALUATION_CONTRACT_VERSION
from .weighting import DYNAMIC_CONTROL_DIMENSIONS, SCORE_POLICY_VERSION
from ..private_eval import (
    audit_participant_container, run_isolated_verifier, tree_sha256,
    verifier_bundle_sha256,
)
from ..spec import load_case, resolve_case_instance


# The adapter can request only the stable WorkspaceRuntime protocol surface.
# Keeping this explicit prevents a capability string from becoming arbitrary
# attribute access on the kernel-owned runtime object.
CAPABILITY_METHODS = frozenset({
    "create_child", "main_terminal", "child_terminal", "promote",
    "cleanup_child", "cleanup",
    # Evaluator-mediated operations.  Their implementation is special-cased
    # in the dispatcher because private commands must never be adapter args.
    "observe_artifact", "verify_current_state",
    # Evaluator-owned presentation handshake and post-tool provisional observer.
    # Both are funnelled through the kernel so the S^- snapshot and the observed
    # workspace state stay kernel-private (spec §3.3, §4.2).
    "prepare_result_presentation", "observe_main_state",
})

# asyncio's subprocess StreamReader defaults to 64 KiB per line. Async-RBench uses
# JSONL and a capability request can legitimately carry a long terminal
# command above that size. Keep the transport bounded, but
# large enough for the protocol's existing payload envelope.
ADAPTER_PROTOCOL_STREAM_LIMIT_BYTES = 16 * 1024 * 1024

# Child terminal calls cross the evaluator-owned capability boundary.  Persist
# the exact command and result as kernel-private audit events so a stored
# trajectory explains what each child actually executed without exposing the
# audit stream back to the participant adapter.
CHILD_TERMINAL_AUDIT_TYPES = frozenset({
    "child_terminal_started", "child_terminal_finished",
})

# Main runtime phase events (spec §3.2) emitted by the reference scaffold after a
# tool *has actually run*. They are not yet in the off-limits protocol module's
# adapter-event registry, so the kernel accepts them as runtime phase boundaries
# without calling ``validate_adapter_event`` (which would otherwise reject them).
# They are recorded as adapter events for replay/audit; the framework treats
# ``main_action`` (the legacy controller trigger) as the authoritative count.
RUNTIME_PHASE_EVENT_TYPES = frozenset({
    "main_action_started", "main_action_finished", "main_turn_completed",
    # The adapter records the adapter-side delivery-occurrence boundaries (spec
    # §3.3) and the Linear atomic aggregation boundaries (spec §6). They are
    # runtime phase markers rather than protocol-validated adapter events, so
    # they bypass ``validate_adapter_event`` but remain recorded for replay.
    "result_available", "response_window_closed",
    "linear_bundle_ready", "linear_bundle_presented",
    # P0-9: repeated evidence across attempts is a descriptive diagnostic.
    "duplicate_evidence_retry_detected",
})


@dataclass(frozen=True)
class EpisodeConfig:
    episode_id: str
    case_id: str
    execution_mode: str
    guidance: str
    agent_seed: int
    adapter_command: list[str]
    output_dir: Path
    instance_id: str = "seed-1"
    repeat: int = 0
    counterfactual_pair_id: str | None = None
    timeout_sec: int = 2400
    gateway_grace_sec: int = 15
    use_container: bool = True
    build_image: bool = True
    keep_container: bool = False
    manifest_sha256: str | None = None
    manifest_episode_ids_sha256: str | None = None
    manifest_episode_count: int | None = None
    progress: bool = False
    progress_heartbeat_sec: int = 30
    episode_index: int = 1
    episode_total: int = 1
    conformance_passed: bool | None = None
    runtime_mode: str | None = None
    adapter_profile: str | None = None
    conformance_binding_sha256: str | None = None
    official_track: bool = False
    resource_policy_sha256: str | None = None
    # Dataset split (calibration / development / test) and the single-model factor
    # are stamped from the manifest into every episode so the aggregate can refuse
    # a headline that mixes held-out test cases or more than one model.
    split: str = "unassigned"
    model: str | None = None
    # Development-only candidate preflight. Official manifest runs always
    # resolve immutable registered instances and leave this unset.
    case_dir_override: Path | None = None
    # Optional immutable verifier source for development pair runs. This keeps
    # private tests available even if a participant deletes its disposable
    # workspace clone before the frozen-filesystem verifier begins.
    verifier_task_dir: Path | None = None


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # Docker Desktop emits UTF-8 progress output even when Windows' active
    # locale is GBK.  Pin the decoder so non-GBK layer names/log glyphs cannot
    # crash an otherwise successful build.
    return subprocess.run(
        ["docker", *args], check=check, text=True,
        encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def _cleanup_workspace_resources(workspace_run_id: str) -> None:
    """Remove only child resources carrying this evaluator-issued run label."""
    if not workspace_run_id or not all(ch in "0123456789abcdef" for ch in workspace_run_id):
        raise ValueError("invalid workspace_run_id for Docker cleanup")
    label = f"label=async_rbench.workspace_run_id={workspace_run_id}"
    # The run id alone is intentionally insufficient: a participant container
    # must remain available until the private verifier commits its submitted
    # filesystem.  Requiring the child-role label keeps this defensive sweep
    # incapable of selecting the main container even if it later acquires a
    # workspace label for observability.
    containers = [
        item for item in _docker(
            "ps", "-aq", "--filter", label,
            "--filter", "label=async_rbench.managed=child", check=False,
        ).stdout.splitlines()
        if re.fullmatch(r"[0-9a-f]{12,64}", item.strip())
    ]
    if containers:
        _docker("rm", "-f", *containers, check=False)
    images = [
        item for item in _docker(
            "images", "-q", "--filter", label,
            "--filter", "label=async_rbench.managed=child", check=False,
        ).stdout.splitlines()
        if re.fullmatch(r"[0-9a-f]{12,64}", item.strip())
    ]
    if images:
        _docker("image", "rm", "-f", *sorted(set(images)), check=False)


def _progress(config: EpisodeConfig, stage: str, message: str) -> None:
    if not config.progress:
        return
    prefix = (
        f"[DTB2 {config.episode_index}/{config.episode_total} "
        f"{config.case_id}/{config.instance_id} {config.execution_mode} {stage}]"
    )
    print(f"{time.strftime('%H:%M:%S')} {prefix} {message}", flush=True)


def _prepare_container(
    root: Path, case_id: str, instance_id: str, episode_id: str, build: bool,
    workspace_run_id: str,
    case_dir_override: Path | None = None,
) -> tuple[str, str, str]:
    case_dir = (
        case_dir_override.resolve()
        if case_dir_override is not None
        else resolve_case_instance(root, case_id, instance_id).case_dir
    )
    task = case_dir / "task"
    image_component = re.sub(r"[^a-z0-9_.-]+", "-", f"{case_id}-{instance_id}".lower())
    image = f"async_rbench-eval-{image_component}:locked"
    episode_component = "".join(
        ch for ch in episode_id.lower() if ch.isalnum() or ch in "-_"
    )[:40].rstrip("-_")
    container = f"dtb2-{episode_component}-{workspace_run_id}"
    if build:
        _docker("build", "-t", image, str(task))
    # A crashed/interrupted run may leave only this deterministic episode
    # container behind. Removing that exact name makes --resume reliable.
    _docker("rm", "-f", container, check=False)
    _docker(
        "run", "-d", "--name", container,
        "--label", "async_rbench.managed=participant", image,
    )
    image_id = _docker("image", "inspect", "--format", "{{.Id}}", image).stdout.strip()
    return image, container, image_id


def _source_digest(root: Path) -> str:
    # The source digest spans the whole four-layer boundary: the kernel,
    # every adapter profile, the conformance tool layer, and the adapter shims —
    # not just the single reference scaffold. Any change to any of these
    # invalidates previously captured forks/manifests (a clean break).
    return tree_sha256([
        root / "async_rbench" / "evaluation",
        root / "async_rbench" / "profiles",
        root / "async_rbench" / "conformance",
        root / "async_rbench" / "private_eval.py",
        root / "adapters",
        root / "PROTOCOL.md",
        root / "ADAPTER_PROTOCOL.md",
        root / "evaluation_contract.json",
        root / "event_taxonomy.json",
    ])


def _case_digest(case_dir: Path) -> str:
    """Backward-compatible name for the shared per-instance digest."""
    return case_bundle_sha256(case_dir)


def _case_contract_path(
    root: Path, case_id: str, instance_id: str = "seed-1",
    case_dir_override: Path | None = None,
) -> Path:
    if case_dir_override is not None:
        return case_dir_override.resolve() / "public_case.yaml"
    return resolve_case_instance(root, case_id, instance_id).contract_path


def _record_gateway_outcome(
    recorder: TraceRecorder,
    outcome: dict[str, Any],
    child_workstreams: dict[str, str],
) -> dict[str, Any]:
    """Persist one public gateway event plus its separate evaluator fact."""
    workstream_id = child_workstreams.get(str(outcome.get("child_id")))
    if outcome.get("type") == "result_delivered":
        recorder.record({
            "type": "result_delivery_evaluator_fact",
            "completion_id": outcome.get("completion_id"),
            "result_kind": outcome.get("result_kind"),
            "benchmark_event_id": outcome.get("benchmark_event_id"),
            "controlled_order": outcome.get("controlled_order"),
            "delivery_fallback_reason": outcome.get("delivery_fallback_reason"),
            "stale": outcome.get("evaluator_stale"),
            "stale_measurable": outcome.get("evaluator_stale_measurable"),
            "stale_reason": outcome.get("evaluator_stale_reason"),
            "invalidates_artifacts": list(outcome.get("invalidates_artifacts") or []),
            "reopens_milestones": list(outcome.get("reopens_milestones") or []),
            "replayed": outcome.get("replayed") is True,
            "replay_of_completion_id": outcome.get("replay_of_completion_id"),
            # Task 9 specialised-stimulus private facts: gateway-owned occurrence
            # identity and the implicit/designed-failure markers that are never
            # participant-visible but score the stimulus truthfully.
            "delivery_occurrence_id": outcome.get("delivery_occurrence_id"),
            "replay_of_occurrence_id": outcome.get("replay_of_occurrence_id"),
            "implicit_error": outcome.get("evaluator_implicit_error"),
            "implicit_error_measurable": outcome.get("evaluator_implicit_error_measurable"),
            "implicit_error_reason": outcome.get("evaluator_implicit_error_reason"),
            "designed_failure": outcome.get("evaluator_designed_failure"),
            "terminal_outcome": outcome.get("terminal_outcome"),
            "terminal_reason": outcome.get("evaluator_terminal_reason"),
        }, "kernel")
        return recorder.record(
            public_delivery(outcome, workstream_id=workstream_id), "gateway"
        )
    recorder.record({
        "type": "result_rejection_evaluator_fact",
        "completion_id": outcome.get("completion_id"),
        "result_kind": outcome.get("result_kind"),
        "benchmark_event_id": outcome.get("benchmark_event_id"),
        "controlled_order": outcome.get("controlled_order"),
        "delivery_fallback_reason": outcome.get("delivery_fallback_reason"),
        "reason_codes": list(outcome.get("reason_codes") or []),
    }, "kernel")
    return recorder.record(
        public_rejection(outcome, workstream_id=workstream_id), "gateway"
    )


def _record_controller_stimulus_audits(
    controller: DeliveryController,
    recorder: TraceRecorder,
) -> None:
    """Persist the gateway classifier's specialised-stimulus private facts.

    The ``DeliveryController`` is the only actor that decides designed vs
    infrastructure, computes the before/after digests, and proves in-flight
    stragglers.  The kernel persists those decisions verbatim as
    ``kernel_private`` facts so score/audit can reconstruct the stimulus without
    exposing the designed truth to the participant.
    """
    for audit in (
        *controller.revision_audits,
        *controller.pressure_audits,
        *controller.deadline_audits,
        *controller.terminal_outcomes,
    ):
        recorder.record({**audit, "visibility": "kernel_private"}, "kernel")
    for item in controller.infrastructure_failures:
        recorder.record({**item, "visibility": "kernel_private"}, "kernel")


def _evaluation_contract_identity(root: Path) -> tuple[str, str]:
    path = root / "evaluation_contract.json"
    raw = path.read_bytes()
    contract = json.loads(raw)
    if contract.get("version") != EVALUATION_CONTRACT_VERSION:
        raise ValueError("evaluation contract version differs from executable version")
    if contract.get("status") != EVALUATION_CONTRACT_STATUS:
        raise ValueError("evaluation contract status differs from executable status")
    return EVALUATION_CONTRACT_VERSION, hashlib.sha256(raw).hexdigest()


def _adapter_environment(config: EpisodeConfig) -> dict[str, str]:
    """Return a deterministic UTF-8 environment for the JSONL protocol process."""
    return {
        **os.environ,
        "ASYNC_RBENCH_EPISODE_ID": config.episode_id,
        # Windows otherwise inherits the active ANSI code page for Python stdio.
        # The wire protocol is UTF-8 on every platform.
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }


def _metadata_audit(
    metadata: dict[str, Any] | None,
    runtime_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """Non-fatal audit of the participant metadata and resolved model identity.

    Runs for every episode, not just a strict mode. Nothing here decides
    score_status: infrastructure failures are what make an episode unscored.
    Requested-vs-resolved model mismatches and a missing resolved fingerprint
    are recorded faithfully as notes/null, never as a model rejection.
    """
    if metadata is None:
        return {
            "metadata_present": False,
            "requested_model": None,
            "resolved_model": None,
            "child_pool_id": None,
            "child_provider_backend": None,
            "child_provider_model": None,
            "notes": ["adapter did not emit participant_metadata"],
        }
    requested_main = str(metadata.get("main_model", "")).strip() or None
    requested_child = str(metadata.get("child_model", "")).strip() or None
    resolved_model: str | None = None
    observations = (runtime_metadata or {}).get("model_observations")
    if isinstance(observations, list):
        # Only the main role's observation resolves the identity that
        # _metadata_audit compares against ``requested_main``.  Dual-provider
        # backends merge main→child observations, so the last non-empty value is
        # the child's resolved_model; scoping to the main role keeps the audit from
        # reporting a spurious main/child mismatch note or stamping the child's
        # identity as the resolved model (F2).  Untagged observations are legacy
        # single-provider main emissions and remain accepted.
        for item in observations:
            role = str((item or {}).get("role", "")).strip()
            if role not in {"", "main"}:
                continue
            value = str((item or {}).get("resolved_model", "")).strip()
            if value:
                resolved_model = value
    # Fixed child pool identity (spec §8): every compared main model must run the
    # same child model/provider/prompt/runtime policy. The runner exposes the declared
    # ``child_pool_id`` and the child provider backend so a model group's
    # constancy can be verified at aggregation without reading secrets.
    child_pool_id = str(metadata.get("child_pool_id", "")).strip() or None
    child_provider = metadata.get("child_provider") or {}
    child_provider_backend = (
        str(child_provider.get("backend", "")).strip() if isinstance(child_provider, dict) else ""
    ) or None
    child_provider_model = str(child_provider.get("model", "")).strip() or requested_child
    notes: list[str] = []
    if resolved_model is None:
        notes.append("model API returned no resolved model fingerprint; recorded as null")
    elif requested_main and resolved_model and requested_main != resolved_model:
        notes.append(
            f"requested model {requested_main!r} differs from resolved model {resolved_model!r}"
        )
    for key in ("main_model", "child_model"):
        if not str(metadata.get(key, "")).strip():
            notes.append(f"{key} is empty")
    if child_pool_id is None:
        notes.append("child_pool_id is empty (fixed child-pool identity is not declared)")
    if child_provider_backend is None:
        notes.append("child_provider has no explicit backend identity")
    return {
        "metadata_present": True,
        "requested_model": requested_main,
        "resolved_model": resolved_model,
        "child_pool_id": child_pool_id,
        "child_provider_backend": child_provider_backend,
        "child_provider_model": child_provider_model,
        "notes": notes,
    }


def child_pool_identity(metadata: dict[str, Any] | None) -> str | None:
    """A canonical fixed child-pool identity from participant metadata (spec §8).

    Returns ``None`` when the metadata does not declare a stable child-pool id.
    The identity combines the pool id with the child provider backend and model
    so a compared model group is comparable only when all share the same
    ``child_pool_id`` AND child provider/model.
    """
    if not metadata:
        return None
    child_pool_id = str(metadata.get("child_pool_id", "")).strip() or None
    if child_pool_id is None:
        return None
    child_provider = metadata.get("child_provider") or {}
    backend = (
        str(child_provider.get("backend", "")).strip()
        if isinstance(child_provider, dict) else ""
    )
    child_model = str(metadata.get("child_model", "")).strip()
    return f"{child_pool_id}:{backend}:{child_model}"


def verify_child_pool_constancy(episode_metadata: list[dict[str, Any] | None]) -> tuple[bool, str | None]:
    """Verify one compared model group shares a single fixed child-pool identity.

    A fixed child pool means different main models use the same child
    model/provider/prompt/runtime/workstream config (spec §8). The runner
    integrity check therefore refuses a group whose episodes declare different
    ``child_pool_id`` / child provider / child model, or where one episode
    omits the identity entirely.
    """
    identities = {child_pool_identity(item) for item in episode_metadata}
    if None in identities:
        return False, "an episode in the model group does not declare a child_pool_id"
    if len(identities) > 1:
        return False, f"model group mixes child-pool identities: {sorted(identities)}"
    return True, None


def _infrastructure_error_notes(events: list[dict[str, Any]]) -> list[str]:
    return [
        f"infrastructure failure ({event.get('component')}): {event.get('detail')}"
        for event in events
        if event.get("type") == "infrastructure_failure"
    ]


async def _send(
    process: asyncio.subprocess.Process,
    message: dict[str, Any],
    lock: asyncio.Lock | None = None,
) -> None:
    assert process.stdin
    data = (json.dumps(message, ensure_ascii=False, sort_keys=True) + "\n").encode()
    if lock is not None:
        async with lock:
            process.stdin.write(data)
            await process.stdin.drain()
    else:
        process.stdin.write(data)
        await process.stdin.drain()


async def _apply_delivery_intervention(
    workspace: WorkspaceRuntime,
    case_spec: dict[str, Any],
    delivery: dict[str, Any],
    recorder: TraceRecorder,
    applied_event_ids: set[str],
) -> bool:
    """Apply and privately observe an evaluator-owned live intervention.

    A child report from an isolated snapshot is not, by itself, proof that the
    main workspace changed. Live-event cases can therefore bind a scheduled
    delivery to a private mutation plus before/after observers. The mutation is
    completed before the public result is delivered and its commands never
    enter participant-visible events.
    """
    if delivery.get("type") != "result_delivered" or delivery.get("replayed") is True:
        return True
    event_id = str(delivery.get("benchmark_event_id") or "")
    if not event_id or event_id in applied_event_ids:
        return True
    events = ((case_spec.get("scenarios") or {}).get("async") or {}).get("events") or []
    schedule_event = next(
        (event for event in events if str(event.get("id") or "") == event_id), None,
    )
    intervention = (schedule_event or {}).get("intervention")
    if not isinstance(intervention, dict):
        return True
    applied_event_ids.add(event_id)
    observers = dict(intervention.get("observer_commands") or {})
    required_changed = {
        str(value) for value in intervention.get("required_changed_artifacts") or []
    }
    timeout = int(intervention.get("timeout_sec") or 30)

    async def observe() -> tuple[dict[str, str], list[str]]:
        values: dict[str, str] = {}
        failures: list[str] = []
        for artifact_id, command in observers.items():
            result = await workspace.main_terminal(str(command), timeout)
            value = result.output.strip().splitlines()[-1] if result.output.strip() else ""
            if result.exit_code != 0 or not value:
                failures.append(str(artifact_id))
            else:
                values[str(artifact_id)] = value
        return values, failures

    before, before_failures = await observe()
    mutation = await workspace.main_terminal(
        str(intervention.get("mutation_command") or "false"), timeout,
    )
    after, after_failures = await observe()
    changed = {
        artifact_id for artifact_id in set(before) & set(after)
        if before[artifact_id] != after[artifact_id]
    }
    reasons: list[str] = []
    if before_failures:
        reasons.append("pre-observation failed: " + ", ".join(sorted(before_failures)))
    if mutation.exit_code != 0:
        reasons.append(f"mutation exited {mutation.exit_code}")
    if after_failures:
        reasons.append("post-observation failed: " + ", ".join(sorted(after_failures)))
    missing_changes = sorted(required_changed - changed)
    if missing_changes:
        reasons.append("required state did not change: " + ", ".join(missing_changes))
    passed = not reasons
    recorder.record({
        "type": "intervention_applied",
        "benchmark_event_id": event_id,
        "passed": passed,
        "required_changed_artifacts": sorted(required_changed),
        "changed_artifacts": sorted(changed),
        "before_observations": before,
        "after_observations": after,
        "failure_reasons": reasons,
    }, "kernel")
    if not passed:
        recorder.record({
            "type": "infrastructure_failure",
            "component": "delivery_intervention",
            "detail": f"{event_id}: {'; '.join(reasons)}",
        }, "kernel")
    return passed


def _kernel_workspace_config(config: EpisodeConfig) -> SimpleNamespace:
    """The workspace-mode surface the kernel derives from an EpisodeConfig.

    The kernel — not the adapter — owns Docker execution, so the mode is chosen
    here from ``use_container``. ``child_terminal_timeout_sec`` matches the
    scaffold default and only matters for container_clone episodes.
    """
    return SimpleNamespace(
        workspace_mode="container_clone" if config.use_container else "disabled",
        child_terminal_timeout_sec=180,
        keep_child_workspaces=config.keep_container,
    )


def _encode_capability_result(result: Any) -> Any:
    if isinstance(result, CommandResult):
        return {"exit_code": result.exit_code, "output": result.output}
    return result


async def _observe_artifact_private(
    workspace: WorkspaceRuntime,
    artifact_id: str,
    private_artifacts: dict[str, dict[str, Any]],
) -> dict[str, str]:
    spec = private_artifacts.get(artifact_id)
    if spec is None:
        raise ValueError(f"unknown artifact: {artifact_id!r}")
    path = str(spec.get("path") or "")
    if isinstance(workspace, DisabledWorkspaceRuntime):
        return {
            "observed_digest": hashlib.sha256(
                f"disabled:{artifact_id}:{path}".encode()
            ).hexdigest(),
            "observed_path": path,
        }
    command = str(spec.get("observer_command") or "")
    if not command:
        if not path.startswith("/") or path.startswith("runtime:") or ":" in path[1:]:
            raise ValueError(f"artifact {artifact_id!r} has no evaluator observer")
        script = (
            "import hashlib,pathlib,sys; p=pathlib.Path(sys.argv[1]); "
            "assert p.exists(), f'missing artifact: {p}'; h=hashlib.sha256(); "
            "files=[p] if p.is_file() else sorted(q for q in p.rglob('*') if q.is_file()); "
            "[(h.update((q.name if p.is_file() else q.relative_to(p).as_posix()).encode()), "
            "h.update(b'\\0'), h.update(q.read_bytes()), h.update(b'\\0')) for q in files]; "
            "print(h.hexdigest())"
        )
        command = f"python -c {shlex.quote(script)} {shlex.quote(path)}"
    result = await workspace.main_terminal(command, 900)
    if result.exit_code != 0:
        raise ValueError(f"artifact observation failed for {artifact_id!r}")
    digest = next(
        (
            line.strip().lower()
            for line in reversed(result.output.splitlines())
            if len(line.strip()) == 64
            and all(ch in "0123456789abcdefABCDEF" for ch in line.strip())
        ),
        "",
    )
    if not digest:
        raise ValueError(f"artifact observer failed for {artifact_id!r}")
    return {"observed_digest": digest, "observed_path": path}


async def _verify_current_state_private(
    workspace: WorkspaceRuntime,
    *,
    artifact_ids: list[str],
    lineage_completion_ids: list[str],
    private_artifacts: dict[str, dict[str, Any]],
    private_checks: dict[str, str],
    consumed_completions: set[str],
    recorder: TraceRecorder | None,
) -> dict[str, Any]:
    unknown = sorted(set(artifact_ids) - set(private_artifacts))
    if unknown:
        raise ValueError(f"unknown artifacts: {unknown!r}")
    if not set(lineage_completion_ids).issubset(consumed_completions):
        raise ValueError("verification lineage contains an unaccepted completion")
    passed_count = 0
    for check_id, command in sorted(private_checks.items()):
        result = await workspace.main_terminal(str(command), 900)
        passed = result.exit_code == 0
        passed_count += int(passed)
        if recorder is not None:
            recorder.record({
                "type": "verification_requested",
                "check_id": check_id,
                "passed": passed,
                "lineage_completion_ids": list(lineage_completion_ids),
                "artifact_ids": list(artifact_ids),
                "evaluator_owned": True,
            }, "verifier")
    check_count = len(private_checks)
    return {
        "passed": passed_count == check_count,
        "passed_count": passed_count,
        "check_count": check_count,
    }


def _observation_points_for_case(case_spec: dict[str, Any]) -> list[ObservationPoint]:
    """Materialise the case's evaluator-observable observation points."""
    points: list[ObservationPoint] = []
    for spec in case_spec.get("observation_points") or []:
        if not isinstance(spec, dict):
            continue
        point = ObservationPoint.from_spec(spec)
        if point.point_id:
            points.append(point)
    return points


def _provisional_predicate_for_case(case_spec: dict[str, Any]) -> dict[str, Any]:
    return dict(case_spec.get("provisional_predicate") or {})


def _build_snapshot_provider(
    workspace: WorkspaceRuntime,
) -> Callable[[Sequence[ObservationPoint]], Awaitable[WorkspaceSnapshot]]:
    """Build an async snapshot provider that observes points via the workspace.

    Each point is observed through the kernel-owned ``main_terminal`` executing
    the synthesised evaluator command; the output is canonicalised and any point
    the workspace cannot observe (missing file, non-zero exit) is reported as
    missing so the snapshot is incomplete and can never establish a boundary.
    """
    async def provide(points: Sequence[ObservationPoint]) -> WorkspaceSnapshot:
        values: dict[str, str] = {}
        missing: list[str] = []
        for point in points:
            command = snapshot_observation_command(point)
            result = await workspace.main_terminal(command, 900)
            if result.exit_code != 0:
                missing.append(point.point_id)
                continue
            value = parse_observation_output(point, result.output)
            if not value:
                missing.append(point.point_id)
                continue
            values[point.point_id] = value
        return WorkspaceSnapshot(
            points=values,
            missing_points=tuple(sorted(missing)),
        )

    return provide


async def _prepare_result_presentation_private(
    workspace: WorkspaceRuntime,
    *,
    delivery_occurrence_id: str,
    turn_id: str,
    recorder: TraceRecorder,
    case_spec: dict[str, Any],
) -> dict[str, Any]:
    """Authorize presenting one delivery occurrence with an evaluator-owned S^-.

    The evaluator captures the before-presentation snapshot ``S_i^-`` and, only
    if it is complete, records the kernel-private ``presentation_prepared``
    boundary and reports ``prepared`` true. A failed snapshot leaves the
    occurrence queued & un-presented (spec §5.1(4)).
    """
    points = _observation_points_for_case(case_spec)
    provider = _build_snapshot_provider(workspace)
    snapshot = await provider(points)
    if not snapshot.complete:
        return {
            "prepared": False,
            "error": snapshot.error or "incomplete_snapshot",
        }
    recorder.record({
        "type": "presentation_prepared",
        "delivery_occurrence_id": delivery_occurrence_id,
        "turn_id": turn_id,
        "snapshot_digest": snapshot.digest,
    }, "kernel")
    return {
        "prepared": True,
        "snapshot_digest": snapshot.digest,
        "observed_points": dict(snapshot.points),
    }


async def _observe_main_state_private(
    workspace: WorkspaceRuntime,
    *,
    reason: str,
    action_id: str,
    turn_id: str,
    recorder: TraceRecorder,
    case_spec: dict[str, Any],
) -> dict[str, Any]:
    """Run the post-tool provisional observer and record a kernel-private fact.

    The adapter fires this only after a modifying tool has finished. The
    observer captures the evaluator-observable workspace state and records a
    ``provisional_observed`` fact whose digest and observed points are
    evaluator-private (spec §4.2).
    """
    points = _observation_points_for_case(case_spec)
    predicate = _provisional_predicate_for_case(case_spec)
    provider = _build_snapshot_provider(workspace)
    observer = ProvisionalObserver(
        points, predicate=predicate, snapshot_provider=provider,
    )
    try:
        observation = await observer.observe(action_id=action_id)
    except Exception as exc:  # noqa: BLE001
        recorder.record({
            "type": "provisional_observed",
            "visibility": "kernel_private",
            "provisional_established": False,
            "action_id": action_id,
            "turn_id": turn_id,
            "reason": f"observer_failure: {exc}",
            "provisional_digest": None,
        }, "kernel")
        return {"provisional_observed": False}
    recorder.record({
        "type": "provisional_observed",
        "visibility": "kernel_private",
        "provisional_established": observation.established,
        "provisional_digest": observation.digest,
        "action_id": action_id,
        "turn_id": turn_id,
        "reason": observation.reason,
        "observed_points": dict(observation.points),
    }, "kernel")
    return {"provisional_observed": observation.established}


async def _dispatch_capability(
    workspace: WorkspaceRuntime,
    message: dict[str, Any],
    process: asyncio.subprocess.Process,
    write_lock: asyncio.Lock,
    recorder: TraceRecorder | None = None,
    private_event_assets: dict[str, list[str]] | None = None,
    child_workstreams: dict[str, str] | None = None,
    private_artifacts: dict[str, dict[str, Any]] | None = None,
    private_checks: dict[str, str] | None = None,
    consumed_completions: set[str] | None = None,
    case_spec: dict[str, Any] | None = None,
) -> None:
    """Resolve one adapter capability request against the kernel-owned workspace.

    Runs as its own task so multiple children can issue e.g. ``child_terminal``
    concurrently instead of serialising behind the single stdout read loop. The
    Raw request/response messages remain transport and are never recorded or
    scored.  For ``child_terminal`` only, the kernel derives private start and
    finish audit events containing the exact command and result.
    """
    request_id = message.get("request_id")
    capability = message.get("capability")
    args = message.get("args") or {}
    audit_child_terminal = capability == "child_terminal" and recorder is not None
    audit_started_at = time.monotonic_ns()
    audit_command = str(args.get("command", ""))
    audit_child_id = str(args.get("child_id", ""))
    if audit_child_terminal:
        recorder.record({
            "type": "child_terminal_started",
            "request_id": request_id,
            "child_id": audit_child_id,
            "command": audit_command,
            "command_chars": len(audit_command),
            "command_sha256": hashlib.sha256(audit_command.encode("utf-8")).hexdigest(),
            "timeout_sec": args.get("timeout"),
        }, "kernel")
    try:
        if capability not in CAPABILITY_METHODS:
            raise ValueError(f"unsupported capability: {capability!r}")
        if capability == "observe_artifact":
            result = await _observe_artifact_private(
                workspace,
                str(args.get("artifact_id", "")),
                private_artifacts or {},
            )
        elif capability == "verify_current_state":
            result = await _verify_current_state_private(
                workspace,
                artifact_ids=[str(item) for item in args.get("artifact_ids") or []],
                lineage_completion_ids=[
                    str(item) for item in args.get("lineage_completion_ids") or []
                ],
                private_artifacts=private_artifacts or {},
                private_checks=private_checks or {},
                consumed_completions=consumed_completions or set(),
                recorder=recorder,
            )
        elif capability == "prepare_result_presentation":
            if recorder is None:
                raise ValueError("prepare_result_presentation requires a recorder")
            result = await _prepare_result_presentation_private(
                workspace,
                delivery_occurrence_id=str(args.get("delivery_occurrence_id", "")),
                turn_id=str(args.get("turn_id", "")),
                recorder=recorder,
                case_spec=case_spec or {},
            )
        elif capability == "observe_main_state":
            if recorder is None:
                raise ValueError("observe_main_state requires a recorder")
            result = await _observe_main_state_private(
                workspace,
                reason=str(args.get("reason", "")),
                action_id=str(args.get("action_id", "")),
                turn_id=str(args.get("turn_id", "")),
                recorder=recorder,
                case_spec=case_spec or {},
            )
        else:
            method = getattr(workspace, capability)
            result = await method(**args)
        if capability == "create_child":
            child_id = str(args.get("child_id", ""))
            workstream_id = (child_workstreams or {}).get(child_id)
            # The capability RPC and public lifecycle event share one stdout
            # stream but are dispatched as separate asyncio tasks. Allow the
            # main protocol loop a bounded moment to validate child_spawned and
            # install its binding; never trust an adapter-supplied asset role.
            for _ in range(100):
                if workstream_id:
                    break
                await asyncio.sleep(0.01)
                workstream_id = (child_workstreams or {}).get(child_id)
            if not workstream_id:
                raise ValueError(
                    "create_child has no prior evaluator-observed child/workstream binding; "
                    f"child_id={child_id!r}, observed={sorted((child_workstreams or {}).items())!r}"
                )
            try:
                await workspace.stage_child_assets(
                    child_id, [workstream_id], private_event_assets or {},
                )
            except Exception as exc:
                # A child workspace failing to start (docker commit/run/cp) is
                # benchmark tooling failing, not a model decision; the recovery
                # child simply never ran.  Record it as an infrastructure crash
                # so the episode is unscored rather than measured as X=0.  The
                # ValueError above (no workstream binding) stays a protocol
                # error and is reported to the adapter, never scored-as-unscored.
                if recorder is not None:
                    recorder.record({
                        "type": "infrastructure_failure",
                        "component": "child_start",
                        "detail": f"{child_id}: {exc}",
                    }, "kernel")
                raise
        response = {
            "type": CAPABILITY_RESPONSE, "request_id": request_id,
            "ok": True, "result": _encode_capability_result(result),
        }
        if audit_child_terminal:
            output = result.output if isinstance(result, CommandResult) else ""
            recorder.record({
                "type": "child_terminal_finished",
                "request_id": request_id,
                "child_id": audit_child_id,
                "command_sha256": hashlib.sha256(audit_command.encode("utf-8")).hexdigest(),
                "duration_ms": round((time.monotonic_ns() - audit_started_at) / 1_000_000, 3),
                "capability_ok": True,
                "exit_code": result.exit_code if isinstance(result, CommandResult) else None,
                "command_succeeded": (
                    result.exit_code == 0 if isinstance(result, CommandResult) else None
                ),
                "output": output,
                "output_chars": len(output),
                "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
                "output_truncated": False,
            }, "kernel")
    except Exception as exc:  # noqa: BLE001 — a failed capability is a response, not a crash
        response = {
            "type": CAPABILITY_RESPONSE, "request_id": request_id,
            "ok": False, "error": str(exc),
        }
        if audit_child_terminal:
            recorder.record({
                "type": "child_terminal_finished",
                "request_id": request_id,
                "child_id": audit_child_id,
                "command_sha256": hashlib.sha256(audit_command.encode("utf-8")).hexdigest(),
                "duration_ms": round((time.monotonic_ns() - audit_started_at) / 1_000_000, 3),
                "capability_ok": False,
                "exit_code": None,
                "command_succeeded": False,
                "error": str(exc),
                "output": "",
                "output_chars": 0,
                "output_sha256": hashlib.sha256(b"").hexdigest(),
                "output_truncated": False,
            }, "kernel")
    await _send(process, response, lock=write_lock)


def _make_start(
    config: EpisodeConfig,
    case_spec: dict[str, Any],
    task_yaml: dict[str, Any],
    container: str | None,
    workspace_run_id: str,
) -> dict[str, Any]:
    start = {
        "type": "episode_started", "protocol_version": "3.0", "episode_id": config.episode_id,
        "case_id": config.case_id, "execution_mode": config.execution_mode, "agent_seed": config.agent_seed,
        "instruction": task_yaml["instruction"], "guidance": render_guidance(config.guidance),
        "container_name": container, "result_gateway_required": True,
        "result_contract_enforced": bool(config.use_container),
        "workspace_run_id": workspace_run_id,
        "allowed_work_units": [item["id"] for item in case_spec["delegation_workstreams"]],
        "workstream_contracts": {
            item["id"]: {
                "required_evidence_fields": list(item.get("required_evidence_fields") or []),
                # Only structural constraints are participant-visible. Exact
                # evaluator constants/enums remain private so the result
                # contract cannot leak the answer it is meant to validate.
                "evidence_schema": {
                    field_name: {
                        key: value for key, value in dict(field_spec or {}).items()
                        if key in {"type", "pattern", "min_items", "enum"}
                    }
                    for field_name, field_spec in dict(
                        item.get("public_evidence_schema")
                        or item.get("evidence_schema") or {}
                    ).items()
                },
                "allowed_files": list(item.get("allowed_files") or []),
                "required_files": list(item.get("required_files") or []),
                # Public artifact shape/semantics are carried to every child,
                # including main-agent re-delegations. This must never contain
                # evaluator-owned answer constants.
                "public_result_contract": dict(
                    item.get("public_result_contract") or {}
                ),
            }
            for item in case_spec["delegation_workstreams"]
        },
        "initial_wave": [
            {
                key: value for key, value in item.items()
                if key in {
                    "workstream_id", "task", "targets", "expected_output",
                    "priority", "required_evidence_fields",
                }
            }
            for item in case_spec.get("initial_wave", [])
        ],
        "allowed_artifacts": [item["id"] for item in case_spec["artifacts"]],
        "artifact_specs": {
            item["id"]: {key: item[key] for key in ("id", "path") if key in item}
            for item in case_spec["artifacts"]
        },
    }
    assert_participant_safe(start, surface="episode_started")
    return start


# Infrastructure-failure components that must make an episode unscored rather
# than scored as X=0.  These are crashes of the benchmark tooling itself (the
# model API call, a child container starting, the adapter process) — never a
# decision the participant made.  A component here is distinct from a
# scenario-construction failure: the scenario may have already constructed and
# started correctly before, say, the model API call crashed mid-episode.
UNSCORED_INFRASTRUCTURE_COMPONENTS = frozenset({
    "model_request", "child_start", "adapter_crash",
    # A child crash from a provider/workspace outage (not a designed case crash)
    # is benchmark tooling failing mid-run, so it makes the episode unscored.
    "child_terminal",
    # The Linear wave never reached a terminal bundle within the benchmark's own
    # child lifecycle cap.  The scenario may have constructed fine, but the
    # benchmark never handed the main model its atomic bundle, so no designed
    # measurement took place -- scoring it as an empty X=0 (or worse, scored
    # with main_tokens=0) would misreport the run.
    "linear_bundle_barrier",
})


def _score_status_decision(
    scenario_constructed: Any, score_integrity_ok: bool,
    integrity_reason: str | None = None,
    dynamic_scenario_qualified: Any = True,
    infrastructure_crash: bool = False,
    resource_safety_abort: bool = False,
) -> tuple[str, str | None]:
    """Decide an episode's score_status from construction and integrity.

    An episode is ``unscored`` only when the benchmark failed to construct its
    designed scenario (``scenario_constructed`` false), a runtime infrastructure
    crash interrupted a fair measurement (``infrastructure_crash``), or the
    measurement itself is incomplete. Model behaviour never makes an episode
    ``unscored``: failures of waiting, cancelling, selecting, integrating,
    redelegating, rebuilding or reverifying fail the registered X points
    instead. The old ``invalid_scenario`` status caused by the model not
    entering the scenario is gone. A model API crash or child-start failure is
    infrastructure (the benchmark tooling failed), not model behaviour, so it is
    unscored rather than converted to X=0.
    """
    if not bool(scenario_constructed):
        return "unscored", "scenario_construction_failed"
    if infrastructure_crash:
        return "unscored", "infrastructure_crash"
    if resource_safety_abort:
        return "unscored", "resource_safety_abort"
    if dynamic_scenario_qualified is False:
        return "unscored", "dynamic_scenario_qualification_failed"
    if not score_integrity_ok:
        return "unscored", integrity_reason or "semantic_registry_or_verifier_incomplete"
    return "scored", None


def _track_a_eligibility(
    config: EpisodeConfig,
    participant_metadata: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Return formal Track-A eligibility independently from task performance."""
    reasons: list[str] = []
    if not config.official_track:
        reasons.append("development_run")
        return False, reasons
    if config.adapter_profile != "reference_scaffold_api":
        reasons.append("adapter_profile_not_fixed_reference_scaffold")
    if config.runtime_mode != "api_only":
        reasons.append("runtime_mode_not_api_only")
    if config.conformance_passed is not True:
        reasons.append("conformance_not_passed")
    if not config.resource_policy_sha256:
        reasons.append("resource_policy_not_frozen")
    if not config.use_container:
        reasons.append("workspace_not_container_clone")
    if config.split != "test":
        # Formal Track-A is a held-out test-split headline. A calibration or
        # development episode must never be certified as a test result.
        reasons.append("split_not_test")
    metadata = participant_metadata or {}
    if metadata.get("backend") != "openai_compatible":
        reasons.append("backend_not_real_model_api")
    if metadata.get("workspace_mode") != "container_clone":
        reasons.append("participant_workspace_mode_not_container_clone")
    if not str(metadata.get("resolved_model") or metadata.get("main_model") or "").strip():
        reasons.append("resolved_model_missing")
    return not reasons, reasons


# P1-15: a Linear episode in which the main model never performed a single
# successful main call measures nothing for the paper head-to-head.  The atomic
# bundle is the only thing Linear shows the model, so "never shown" (barrier
# failure) or "never answered" both mean zero main-side behaviour was recorded.
# Such runs are forbidden from the leaderboard: the runner marks them unscored
# and leaderboard-ineligible, and a certification containing one is hard-failed
# at aggregation time (a second, flag-independent defense).
LINEAR_ZERO_MAIN_REASON = "linear_zero_main_tokens"
LINEAR_ABNORMAL_STATUS_REASON = "linear_no_main_measurement"


def _linear_main_measurement_abnormal(execution_mode: str, main_tokens: Any) -> bool:
    """P1-15 abnormal-Linear signature: zero main-side tokens measured."""
    return execution_mode == "linear" and int(main_tokens or 0) == 0


def _primary_event_theme(case_path: Path, public_spec: dict[str, Any]) -> str:
    """An episode's single primary event theme, evaluator-side only.

    The headline macro unit is one of the eight ``primary_event_theme``
    categories (the case families), and "each case has exactly one primary
    event theme for dataset counting."  Registered cases keep that theme in the
    private classification (``private/private_case.yaml``), not in the public
    case spec, so the episode must read the evaluator-side classification to
    stamp it on the score.  It is never written to the participant trace: the
    public stream is built from ``store.public_stream()``, which does not
    include this field.  A case whose theme fails to resolve stays
    ``unassigned_theme`` rather than masking a hard assignment as empty.
    """
    public = str(public_spec.get("primary_event_theme") or public_spec.get("event_theme") or "")
    if public:
        return public
    private_path = case_path.parent / "private" / "private_case.yaml"
    if private_path.is_file():
        try:
            classification = (
                yaml.safe_load(private_path.read_text(encoding="utf-8")) or {}
            ).get("classification") or {}
            theme = str(classification.get("primary_event_theme") or "")
        except (OSError, ValueError, TypeError):
            theme = ""
        if theme:
            return theme
    return "unassigned_theme"


async def run_episode(root: Path, config: EpisodeConfig) -> dict[str, Any]:
    case_path = _case_contract_path(
        root, config.case_id, config.instance_id, config.case_dir_override,
    )
    case_spec = load_case(case_path).raw
    task_yaml = yaml.safe_load((case_path.parent / "task/task.yaml").read_text(encoding="utf-8"))
    semantic_registry_path = case_path.parent / "task" / "tests" / "semantic_checks.json"
    semantic_registry = json.loads(semantic_registry_path.read_text(encoding="utf-8"))
    # Hard gate (pre-run): every frozen semantic check must declare exactly one
    # scoring domain (with a non-empty event_id for async_replanning).  A
    # malformed registry would silently empty the base_task_score / async_drs
    # headline consumers, so it fails deterministically before any participant
    # container starts or model call is made — same fail-fast class as a failed
    # conformance gate or an unknown execution mode.
    domain_errors = validate_scoring_domains(
        list(semantic_registry.get("checks") or []),
    )
    if domain_errors:
        raise ValueError(
            "semantic registry scoring domains are malformed "
            f"({config.case_id}/{config.instance_id}): "
            + "; ".join(domain_errors)
            + f" [registry: {semantic_registry_path}]"
        )
    evaluation_contract_version, evaluation_contract_sha256 = _evaluation_contract_identity(root)
    recorder = TraceRecorder(config.episode_id)
    controller = DeliveryController(config.execution_mode, case_spec)
    # Private evaluator receipts are registered before the participant exists.
    # DeliveryController still applies the case's ordinary causal schedule, so
    # their contents cannot reach the adapter until the required boundary.
    for injection in case_spec.get("evaluator_injections") or []:
        controller.inject_evaluator_result(
            injection_id=str(injection.get("id") or ""),
            result_kind=str(injection.get("result_kind") or ""),
            payload=injection.get("payload"),
        )
    workspace_run_id = uuid.uuid4().hex[:12]
    container = None
    image_id = None
    if config.use_container:
        _progress(config, "prepare", "building/loading clean participant image")
        _, container, image_id = _prepare_container(
            root, config.case_id, config.instance_id, config.episode_id,
            config.build_image, workspace_run_id, config.case_dir_override,
        )
        audit_participant_container(container)
        _progress(config, "prepare", f"participant container ready and clean: {container}")

    case_digest = _case_digest(case_path.parent)
    source_digest = _source_digest(root)
    recorder.record({
        "type": "run_metadata",
        "case_sha256": case_digest,
        "verifier_bundle_sha256": verifier_bundle_sha256(case_path.parent / "task"),
        "scaffold_and_protocol_sha256": source_digest,
        "evaluation_contract_version": evaluation_contract_version,
        "evaluation_contract_sha256": evaluation_contract_sha256,
        "kernel_version": EVALUATION_CONTRACT_VERSION,
        "adapter_profile": config.adapter_profile,
        "runtime_mode": config.runtime_mode,
        "conformance_binding_sha256": config.conformance_binding_sha256,
        "resource_policy_sha256": config.resource_policy_sha256,
        "workspace_mode": "container_clone" if config.use_container else "disabled",
        "participant_image_id": image_id,
        "adapter_command_sha256": hashlib.sha256("\0".join(config.adapter_command).encode()).hexdigest(),
        "manifest_sha256": config.manifest_sha256,
        "manifest_episode_ids_sha256": config.manifest_episode_ids_sha256,
        "manifest_episode_count": config.manifest_episode_count,
    }, "benchmark")
    start = _make_start(config, case_spec, task_yaml, container, workspace_run_id)
    workspace = build_workspace_runtime(
        start, _kernel_workspace_config(config), case_path.parent / "task",
    )
    # Private event assets are sourced directly from the task build context
    # when possible, so they never need to exist in the participant image. For
    # legacy transformed assets, the runtime isolates and removes the in-image
    # copy before the participant process exists. The kernel later stages only
    # assets bound to each evaluator-observed child/workstream pair.
    try:
        await workspace.prepare_event_assets(case_spec.get("event_assets", {}))
    except Exception:
        await workspace.cleanup()
        if container and not config.keep_container:
            _docker("rm", "-f", container, check=False)
        raise
    process = await asyncio.create_subprocess_exec(
        *config.adapter_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=root,
        env=_adapter_environment(config),
        limit=ADAPTER_PROTOCOL_STREAM_LIMIT_BYTES,
    )
    assert process.stderr
    _progress(config, "adapter", "participant scaffold process started")
    stderr_task = asyncio.create_task(process.stderr.read())
    write_lock = asyncio.Lock()
    capability_tasks: set[asyncio.Task] = set()
    recorder.record(start, "benchmark")
    await _send(process, start)

    async def communicate() -> None:
        assert process.stdout
        known_children: set[str] = set()
        child_workstreams: dict[str, str] = {}
        initial_workstreams_seen: set[str] = set()
        known_completions: set[str] = set()
        delivered_completions: set[str] = set()
        consumed_completions: set[str] = set()
        applied_intervention_event_ids: set[str] = set()
        allowed_units = set(start["allowed_work_units"])
        allowed_artifacts = set(start["allowed_artifacts"])
        workstream_specs = {
            str(item["id"]): item for item in case_spec.get("delegation_workstreams", [])
        }
        participant_metadata: dict[str, Any] | None = None
        while True:
            held_wait = controller.has_held_completion()
            initial_gate_wait = held_wait and not controller.gate_open
            read_timeout: float | None
            if held_wait:
                remaining = controller.remaining_hold_seconds(config.gateway_grace_sec)
                # A tiny positive timeout lets asyncio reach the deadline path
                # without resetting the absolute hold clock on every event.
                read_timeout = max(0.001, float(remaining or 0.0))
            elif config.progress:
                read_timeout = float(config.progress_heartbeat_sec)
            else:
                read_timeout = None
            try:
                if read_timeout is not None:
                    raw = await asyncio.wait_for(process.stdout.readline(), timeout=read_timeout)
                else:
                    raw = await process.stdout.readline()
            except asyncio.TimeoutError:
                if not held_wait:
                    _progress(config, "heartbeat", "still running; waiting for the next model/tool event")
                    continue
                if initial_gate_wait:
                    controller.protocol_notes.append(
                        "delegation gate grace expired; held result released uncontrolled and scenario entry is ineligible"
                    )
                    recorder.record({"type": "delegation_gate_fallback",
                                     "grace_sec": config.gateway_grace_sec}, "gateway")
                    deadline_deliveries = controller.force_release()
                else:
                    recorder.record({
                        "type": "scheduled_delivery_deadline",
                        "grace_sec": config.gateway_grace_sec,
                        "reason": "held completion reached benchmark-owned delivery SLA",
                    }, "gateway")
                    deadline_deliveries = controller.deadline_release()
                for delivery in deadline_deliveries:
                    await _apply_delivery_intervention(
                        workspace, case_spec, delivery, recorder,
                        applied_intervention_event_ids,
                    )
                    recorded_delivery = _record_gateway_outcome(
                        recorder, delivery, child_workstreams,
                    )
                    if delivery["type"] == "result_delivered":
                        delivered_completions.add(delivery["completion_id"])
                        _progress(
                            config, "delivery",
                            f"fallback delivery {delivery['completion_id']} kind={delivery['result_kind']}",
                        )
                    else:
                        _progress(
                            config, "delivery",
                            f"fallback rejection {delivery['completion_id']} kind={delivery['result_kind']}",
                        )
                    await _send(process, strip_for_adapter(recorded_delivery), lock=write_lock)
                continue
            if not raw:
                break
            try:
                event = json.loads(raw.decode())
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                recorder.record({"type": "protocol_violation", "detail": str(exc), "raw": raw.decode(errors="replace")}, "benchmark")
                continue
            if event.get("type") == CAPABILITY_REQUEST:
                capability_tasks.add(asyncio.create_task(
                    _dispatch_capability(
                        workspace, event, process, write_lock, recorder,
                        private_event_assets=case_spec.get("event_assets", {}),
                        child_workstreams=child_workstreams,
                        private_artifacts={
                            str(item["id"]): dict(item)
                            for item in case_spec.get("artifacts", [])
                        },
                        private_checks=case_spec.get("hidden_reverification_commands", {}),
                        consumed_completions=consumed_completions,
                        case_spec=case_spec,
                    )
                ))
                continue
            if event.get("type") not in RUNTIME_PHASE_EVENT_TYPES:
                try:
                    validate_adapter_event(event)
                except ProtocolError as exc:
                    recorder.record({"type": "protocol_violation", "detail": str(exc), "raw": raw.decode(errors="replace")}, "benchmark")
                    continue
            recorded = recorder.record(event, "adapter")
            controller_recorded = recorded
            violation = None
            gateway = False
            contract_validation: ResultContractValidation | None = None
            controller_side_deliveries: list[dict[str, Any]] = []
            if event["type"] == "participant_metadata":
                if participant_metadata is not None:
                    violation = "duplicate participant_metadata"
                participant_metadata = event
            elif event["type"] == "ready" and participant_metadata is None:
                violation = "participant_metadata must precede ready"
            elif event["type"] == "child_spawned":
                if event["child_id"] in known_children:
                    violation = "duplicate child_id"
                elif not set(event["work_units"]).issubset(allowed_units):
                    violation = "unknown work_unit"
                else:
                    workstream = str(event["work_units"][0])
                    if initial_workstreams_seen != allowed_units and workstream in initial_workstreams_seen:
                        violation = "duplicate initial workstream"
                    else:
                        initial_workstreams_seen.add(workstream)
                        child_workstreams[event["child_id"]] = workstream
                known_children.add(event["child_id"])
            elif event["type"] == "child_progress_checkpoint":
                if event["child_id"] not in known_children:
                    violation = "progress checkpoint for unknown child"
            elif event["type"] == "child_completed":
                if event["child_id"] not in known_children:
                    violation = "completion for unknown child"
                elif event["completion_id"] in known_completions:
                    violation = "duplicate completion_id"
                known_completions.add(event["completion_id"])
            elif event["type"] == "result_consumed":
                if event["completion_id"] not in delivered_completions:
                    violation = "result consumed before gateway delivery"
                    gateway = True
                else:
                    consumed_completions.add(event["completion_id"])
                    controller_side_deliveries = controller.on_consumed(event)
            elif event["type"] == "artifact_committed":
                if event["artifact_id"] not in allowed_artifacts:
                    violation = "unknown artifact_id"
                elif not set(event["lineage_completion_ids"]).issubset(delivered_completions):
                    violation = "artifact lineage includes an undelivered completion"
                    gateway = True
                elif not set(event["lineage_completion_ids"]).issubset(consumed_completions):
                    violation = "artifact lineage includes a completion not explicitly accepted for use"
                    gateway = True
            if violation:
                record = {"type": "protocol_violation", "detail": violation,
                          "adapter_event_seq": recorded["seq"]}
                if gateway:
                    record["gateway"] = True
                recorder.record(record, "benchmark")
            event_type = event["type"]
            completion_case_contract_failure = False
            if event_type == "child_completed":
                workstream_id = child_workstreams.get(str(event.get("child_id")))
                workstream = workstream_specs.get(str(workstream_id))
                if workstream is not None:
                    # ``result_kind`` is evaluator truth.  Bind it only on the
                    # private in-memory copy consumed by the scheduler; never
                    # mutate or persist the participant's public completion.
                    controller_recorded = {
                        **recorded,
                        "result_kind": str(workstream["result_kind"]),
                    }
                if violation is not None:
                    contract_validation = ResultContractValidation(
                        valid=False,
                        reason_codes=("protocol_contract_mismatch",),
                        details=(violation,),
                    )
                elif start.get("result_contract_enforced") is not True:
                    contract_validation = ResultContractValidation(
                        valid=True,
                        reason_codes=(),
                        details=("semantic result contract skipped outside scored container mode",),
                    )
                elif workstream is None:
                    contract_validation = ResultContractValidation(
                        valid=False,
                        reason_codes=("unknown_workstream_contract",),
                        details=("child completion has no assigned workstream contract",),
                    )
                else:
                    contract_validation = await validate_completion_contract(
                        workstream, recorded, workspace,
                    )
                recorder.record({
                    "type": "result_contract_validated",
                    "child_id": recorded.get("child_id"),
                    "completion_id": recorded.get("completion_id"),
                    "workstream_id": workstream_id,
                    **contract_validation.private_event_fields(),
                }, "gateway")
                if "invalid_public_result_contract" in contract_validation.reason_codes:
                    completion_case_contract_failure = True
                    recorder.record({
                        "type": "infrastructure_failure",
                        "component": "case_contract",
                        "child_id": recorded.get("child_id"),
                        "completion_id": recorded.get("completion_id"),
                        "detail": "; ".join(contract_validation.details),
                    }, "benchmark")
                elif (
                    contract_validation.valid
                    and workstream is not None
                    and workstream.get("validator_stage") == "semantic_evidence"
                    and start.get("result_contract_enforced") is True
                ):
                    semantic = await evaluate_private_semantics(
                        workstream, recorded, workspace,
                    )
                    recorder.record({
                        "type": "child_semantic_validated",
                        "child_id": recorded.get("child_id"),
                        "completion_id": recorded.get("completion_id"),
                        "workstream_id": workstream_id,
                        "passed": semantic.valid,
                        "validator_exit_code": semantic.validator_exit_code,
                        "details": list(semantic.details),
                        "validator_output_sha256": canonical_digest(
                            semantic.validator_output
                        ),
                    }, "gateway")
            if event_type == "participant_metadata":
                _progress(
                    config, "adapter",
                    f"backend={event.get('backend')} main={event.get('main_model')} child={event.get('child_model')}",
                )
            elif event_type == "ready":
                _progress(config, "adapter", "scaffold ready")
            elif event_type == "agent_progress":
                phase = str(event.get("phase", ""))
                role = str(event.get("role", "agent"))
                turn = event.get("turn", "?")
                if phase == "model_call_started":
                    _progress(config, "model", f"{role} turn {turn} API call started")
                elif phase == "model_call_finished":
                    _progress(config, "model", f"{role} turn {turn} API call finished; tokens={event.get('tokens', 0)}")
            elif event_type == "infrastructure_failure":
                _progress(
                    config, "infrastructure",
                    f"{event.get('component')}: {event.get('detail', '')}",
                )
            elif event_type == "child_spawned":
                _progress(config, "subagent", f"spawned {event['child_id']} work_units={event.get('work_units', [])}")
            elif event_type == "child_started":
                _progress(config, "subagent", f"{event['child_id']} started in isolated snapshot")
            elif event_type == "child_completed":
                _progress(config, "subagent", f"{event['child_id']} completed; result held by gateway")
            elif event_type == "child_cancelled":
                _progress(config, "subagent", f"{event['child_id']} cancelled: {event.get('reason', '')}")
            elif event_type in {
                "child_step_limit_reached",
                "child_resource_safety_abort",
                "child_no_submission",
            }:
                _progress(
                    config,
                    "subagent",
                    f"{event.get('child_id')} {event_type.removeprefix('child_')}: "
                    f"{event.get('reason', '')}",
                )
            elif event_type == "main_action":
                _progress(config, "main", f"action {event.get('action_id')} tool={event.get('kind')}")
            elif event_type == "artifact_committed":
                _progress(config, "artifact", f"committed {event.get('artifact_id')} version={event.get('version')}")
            elif event_type == "verification_requested":
                _progress(config, "reverify", f"{event.get('check_id')} passed={event.get('passed')}")
            elif event_type == "episode_ended":
                _progress(config, "agent", f"episode declared {event.get('local_status', 'ended')}")
            deliveries = []
            if event["type"] == "child_spawned":
                deliveries = controller.on_spawn(recorded)
            elif event["type"] == "child_started":
                # The gateway records this so it can *prove* a child was in
                # flight before a designed terminal outcome or resource-pressure
                # boundary fires (spec §6.2).  It then consumes any designed
                # terminal the case declares in its schedule for this child, so a
                # declared `child_timeout`/`child_crash` reaches the corresponding
                # apply_* producer and the designed failure is delivered to main.
                deliveries = controller.on_child_started(recorded)
                deliveries += controller.consume_declared_stimuli(recorded)
            elif event["type"] == "child_completed" and not completion_case_contract_failure:
                deliveries = controller.on_complete(controller_recorded, contract_validation)
                if controller_recorded["completion_id"] not in controller.delivered:
                    recorder.record({
                        "type": "result_held",
                        "child_id": controller_recorded["child_id"],
                        "completion_id": controller_recorded["completion_id"],
                        "result_kind": controller_recorded.get("result_kind"),
                    }, "gateway")
            elif event["type"] == "main_action":
                deliveries = controller.on_main_action(recorded)
            elif event["type"] in {"artifact_committed", "verification_requested"} and violation is None:
                deliveries = controller.on_observation(recorded)
            elif event["type"] == "result_consumed":
                deliveries = controller_side_deliveries
            for delivery in deliveries:
                await _apply_delivery_intervention(
                    workspace, case_spec, delivery, recorder,
                    applied_intervention_event_ids,
                )
                recorded_delivery = _record_gateway_outcome(
                    recorder, delivery, child_workstreams,
                )
                if delivery["type"] == "result_delivered":
                    delivered_completions.add(delivery["completion_id"])
                    _progress(
                        config, "delivery",
                        f"{'replayed' if delivery.get('replayed') else 'delivered'} "
                        f"{delivery['completion_id']} kind={delivery['result_kind']} "
                        f"stale={delivery.get('stale', False)}",
                    )
                else:
                    _progress(
                        config, "delivery",
                        f"rejected {delivery['completion_id']} kind={delivery['result_kind']} contract={delivery.get('reason_codes', [])}",
                    )
                await _send(process, strip_for_adapter(recorded_delivery), lock=write_lock)
            if event["type"] == "episode_ended":
                break
        for delivery in controller.force_release():
            _record_gateway_outcome(recorder, delivery, child_workstreams)
            if delivery["type"] == "result_delivered":
                delivered_completions.add(delivery["completion_id"])

    timed_out = False
    try:
        await asyncio.wait_for(communicate(), timeout=config.timeout_sec)
    except asyncio.TimeoutError:
        timed_out = True
        recorder.record({"type": "episode_timeout", "timeout_sec": config.timeout_sec}, "benchmark")
        process.kill()
    await process.wait()
    if capability_tasks:
        await asyncio.gather(*capability_tasks, return_exceptions=True)
    # A benchmark-enforced timeout necessarily kills the adapter and prevents a
    # final episode_ended. Those are consequences of the resource limit, not two
    # additional participant protocol violations.
    if process.returncode != 0 and not timed_out:
        recorder.record({"type": "protocol_violation",
                         "detail": f"adapter exited with code {process.returncode}"}, "benchmark")
    if not timed_out and not any(event.get("type") == "episode_ended" for event in recorder.events):
        recorder.record({"type": "protocol_violation",
                         "detail": "adapter terminated without episode_ended"}, "benchmark")
    stderr = (await stderr_task).decode(errors="replace")
    if stderr:
        recorder.record({"type": "adapter_stderr", "text": stderr[-20000:]}, "benchmark")

    # Persist the gateway classifier's specialised-stimulus private facts before
    # the metadata/infrastructure audit, so an infrastructure child crash is seen
    # by ``_score_status_decision`` and a designed outcome is auditable.
    _record_controller_stimulus_audits(controller, recorder)

    metadata_events = [event for event in recorder.events if event.get("type") == "participant_metadata"]
    runtime_metadata_events = [event for event in recorder.events if event.get("type") == "participant_runtime_metadata"]
    infrastructure_failure_events = [
        event for event in recorder.events if event.get("type") == "infrastructure_failure"
    ]
    # Audit fields run for every episode. Nothing here decides score_status:
    # a requested/resolved model mismatch is a warning note, a missing resolved
    # fingerprint is recorded as null, and only infrastructure failure events
    # make the episode unscored.
    metadata_audit = _metadata_audit(
        metadata_events[-1] if metadata_events else None,
        runtime_metadata_events[-1] if runtime_metadata_events else None,
    )
    if config.use_container and container:
        _progress(config, "verifier", "freezing submitted filesystem and starting private hidden verifier")
        try:
            verify = run_isolated_verifier(
                main_container=container,
                task_dir=config.verifier_task_dir or case_path.parent / "task",
                episode_id=config.episode_id,
                timeout_sec=config.timeout_sec,
            )
        except Exception as exc:
            recorder.record({
                "type": "infrastructure_failure", "component": "private_verifier",
                "detail": str(exc),
            }, "benchmark")
            config.output_dir.mkdir(parents=True, exist_ok=True)
            recorder.write(config.output_dir / "trace.jsonl")
            # This is intentionally after the verifier attempt: cleanup may
            # remove child snapshots, but it must never precede the audit and
            # frozen-filesystem commit of the participant container.
            await workspace.cleanup()
            _cleanup_workspace_resources(workspace_run_id)
            if container and not config.keep_container:
                _docker("rm", "-f", container, check=False)
            raise
        recorder.record({
            "type": "verifier_result", "success": verify.success,
            "exit_code": verify.exit_code, "output": (verify.output or "")[-50000:],
            "isolated": True, "isolation": verify.isolation,
            "verifier_bundle_sha256": verify.verifier_bundle_sha256,
            "test_pass_fraction": verify.test_pass_fraction,
            "test_counts": verify.test_counts,
            "component_results": verify.component_results,
            "test_point_pass_rate": verify.test_point_pass_rate,
            "semantic_check_results": verify.semantic_check_results,
            "semantic_check_counts": verify.semantic_check_counts,
            "semantic_registry_version": verify.semantic_registry_version,
        }, "benchmark")
        _progress(
            config, "verifier",
            f"finished exit_code={verify.exit_code} task_success={verify.success}",
        )
    else:
        ends = [e for e in recorder.events if e.get("type") == "episode_ended"]
        recorder.record({"type": "verifier_result", "success": bool(ends and ends[-1].get("declared_task_success")),
                         "synthetic": True}, "benchmark")

    # Keep the participant container and all child snapshots intact until the
    # hidden verifier has audited and committed the participant filesystem. The
    # labelled child sweep is deliberately after that boundary as a second
    # defence against lifecycle changes in workspace adapters.
    await workspace.cleanup()
    _cleanup_workspace_resources(workspace_run_id)

    trace_path = config.output_dir / "trace.jsonl"
    recorder.write(trace_path)
    # Persist the normalised event source (Step 8): the canonical record of the
    # episode is the EventStore's envelope-stamped stream, not the legacy trace.
    # Scoring reads from this source so ``score.json`` and ``event_source.jsonl``
    # agree by construction.
    store = EventStore.from_records(recorder.events, config.episode_id)
    (config.output_dir / "event_source.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in store.events),
        encoding="utf-8",
    )
    (config.output_dir / "participant_trace.jsonl").write_text(
        "".join(
            json.dumps(strip_for_adapter(event), ensure_ascii=False, sort_keys=True) + "\n"
            for event in store.public_stream()
        ),
        encoding="utf-8",
    )
    control_flow_registry_path = case_path.parent / "task" / "tests" / "control_flow_checks.json"
    control_flow_registry = json.loads(control_flow_registry_path.read_text(encoding="utf-8"))
    score = score_trace(
        store.events, case_spec, config.execution_mode,
        semantic_registry=semantic_registry,
        control_flow_checks=list(control_flow_registry.get("checks") or []),
        event_contracts=list(control_flow_registry.get("event_contracts") or []),
    )
    episode_end_events = [
        event for event in store.events if event.get("type") == "episode_ended"
    ]
    episode_local_status = (
        episode_end_events[-1].get("local_status") if episode_end_events else None
    )
    token_usage_events = [
        event for event in store.events if event.get("type") == "token_usage_snapshot"
    ]
    token_usage_report = None
    if token_usage_events:
        last_usage = token_usage_events[-1]
        token_usage_report = {
            key: last_usage.get(key)
            for key in (
                "emergency_cap", "total", "main", "child", "by_actor",
                "tripped", "trigger_role",
            )
        }
    finish_events = [
        event for event in store.events if event.get("type") == "finish_invoked"
    ]
    finish_quality = None
    if finish_events:
        last_finish = finish_events[-1]
        finish_quality = {
            key: last_finish.get(key)
            for key in (
                "requested_status", "pending_occurrence_count",
                "active_response_window", "final_commit_current",
                "verification_current", "closure_complete",
            )
        }
    resource_safety_abort = bool(
        episode_local_status == "resource_safety_abort"
        or any(event.get("type") == "resource_safety_abort" for event in store.events)
    )
    step_limit_reached = episode_local_status == "step_limit_reached"
    if resource_safety_abort:
        termination_reason = "resource_safety_abort"
    elif finish_events:
        termination_reason = "explicit_finish"
    elif any(event.get("type") == "main_implicit_stop" for event in store.events):
        termination_reason = "implicit_stop"
    elif step_limit_reached:
        termination_reason = "step_limit_reached"
    elif timed_out:
        termination_reason = "episode_timeout"
    elif infrastructure_failure_events:
        termination_reason = "infrastructure_failure"
    else:
        termination_reason = str(episode_local_status or "unknown")
    score.update({
        "episode_id": config.episode_id, "case_id": config.case_id, "instance_id": config.instance_id,
        "execution_mode": config.execution_mode, "guidance": config.guidance, "agent_seed": config.agent_seed,
        "capability_categories": sorted(case_spec.get("capabilities") or []),
        # The primary event theme is the headline macro unit (the 8 case
        # categories).  It lives in the private classification for registered
        # cases; we stamp it evaluator-side so a hard "unassigned" case is
        # distinct from one whose theme simply failed to resolve.  Never in the
        # participant trace.
        "event_theme": _primary_event_theme(case_path, case_spec),
        "repeat": config.repeat, "counterfactual_pair_id": config.counterfactual_pair_id,
        "timed_out": timed_out, "gateway_notes": controller.protocol_notes,
        "episode_local_status": episode_local_status,
        "termination_reason": termination_reason,
        "finish_quality": finish_quality,
        "step_limit_reached": step_limit_reached,
        "resource_safety_abort": resource_safety_abort,
        "token_usage_report": token_usage_report,
        "gateway_result_bundle_digest": controller.result_bundle_digest(),
        "requested_model": metadata_audit["requested_model"],
        "resolved_model": metadata_audit["resolved_model"],
        "metadata_audit_notes": metadata_audit["notes"],
        # Fixed child-pool identity (spec §8): stamped evaluator-side so a model
        # group's aggregation can reject a headline whose episodes used
        # different child models/providers/pools.
        "child_pool_id": metadata_audit["child_pool_id"],
        "child_provider_identity": child_pool_identity(metadata_events[-1] if metadata_events else None),
        "conformance_passed": config.conformance_passed,
        "conformance_binding_sha256": config.conformance_binding_sha256,
        "adapter_profile": config.adapter_profile,
        "runtime_mode": config.runtime_mode,
        # Formal experiment factors: the dataset split and the single model.
        # These are stamped from the manifest so aggregation can reject a
        # headline that mixes held-out test cases or more than one model.
        "split": config.split,
        "model": config.model,
        "kernel_version": EVALUATION_CONTRACT_VERSION,
        "event_source_integrity": store.integrity_digest(),
        "case_sha256": case_digest,
        "verifier_bundle_sha256": verifier_bundle_sha256(case_path.parent / "task"),
        "scaffold_and_protocol_sha256": source_digest,
        "evaluation_contract_version": evaluation_contract_version,
        "evaluation_contract_sha256": evaluation_contract_sha256,
        "resource_policy_sha256": config.resource_policy_sha256,
        "participant_image_id": image_id,
        "manifest_sha256": config.manifest_sha256,
        "manifest_episode_ids_sha256": config.manifest_episode_ids_sha256,
        "manifest_episode_count": config.manifest_episode_count,
        "participant_metadata": metadata_events[-1] if metadata_events else None,
        "participant_runtime_metadata": runtime_metadata_events[-1] if runtime_metadata_events else None,
        "infrastructure_failures": [
            {
                "component": event.get("component"),
                "child_id": event.get("child_id"),
                "detail": event.get("detail"),
            }
            for event in infrastructure_failure_events
        ],
    })
    leaderboard_eligible, eligibility_reasons = _track_a_eligibility(
        config, metadata_events[-1] if metadata_events else None,
    )
    # P1-15: a zero-main-measurement Linear run is never leaderboard-eligible,
    # even when every formal Track-A gate passed (the run measured nothing in
    # the arm the pairing design exists to compare).
    linear_abnormal = _linear_main_measurement_abnormal(
        config.execution_mode, score.get("main_tokens"),
    )
    if linear_abnormal:
        eligibility_reasons.append(LINEAR_ZERO_MAIN_REASON)
        leaderboard_eligible = False
    if resource_safety_abort:
        eligibility_reasons.append("resource_safety_abort")
        leaderboard_eligible = False
    score.update({
        "execution_tier": "official_track_a" if config.official_track else "development",
        "leaderboard_eligible": leaderboard_eligible,
        "leaderboard_ineligibility_reasons": eligibility_reasons,
        "linear_main_measurement_abnormal": linear_abnormal,
    })
    semantic_counts = score.get("semantic_check_counts") or {}
    semantic_results = score.get("semantic_check_results") or []
    expected_semantic_count = len(semantic_registry.get("checks") or [])
    score["control_flow_registry_version"] = str(control_flow_registry.get("version", "1"))
    expected_control_flow_count = len(control_flow_registry.get("checks") or [])
    control_flow_results = score.get("control_flow_check_results") or []
    control_flow_counts = score.get("control_flow_check_counts") or {}
    # The merged X denominator must equal the registry-fixed weighted
    # denominator: a runtime trace can never shrink or grow the applicable-point
    # set under an execution mode, or X stops being comparable across models.
    semantic_weighted = score.get("semantic_check_weighted_counts") or {}
    control_flow_weighted = score.get("control_flow_check_weighted_counts") or {}
    expected_weighted_denominator = (
        int(semantic_weighted.get("total", 0)) + int(control_flow_weighted.get("applicable", 0))
    )
    dynamic_dimensions = score.get("dynamic_dimension_scores") or {}
    expected_dynamic_dimensions = {
        str(item.get("dimension") or "")
        for item in control_flow_registry.get("checks") or []
        if config.execution_mode in (item.get("execution_modes") or [])
    }
    dynamic_scenario_qualified = (
        config.execution_mode != "async"
        or score.get("dynamic_scenario_qualified") is not False
    )
    score_integrity_ok = (
        score.get("test_point_pass_rate") is not None
        and score.get("semantic_task_score") is not None
        and score.get("score_policy_version") == SCORE_POLICY_VERSION
        and (
            config.execution_mode != "async" or not dynamic_scenario_qualified
            or (
                score.get("dynamic_control_score") is not None
                and score.get("dt_score") is not None
                and set(dynamic_dimensions) == expected_dynamic_dimensions
            )
        )
        and int(semantic_counts.get("total", -1)) == expected_semantic_count
        and len(semantic_results) == expected_semantic_count
        and len(control_flow_results) == expected_control_flow_count
        and int(control_flow_counts.get("total", -1)) == expected_control_flow_count
        and score.get("weighted_denominator") == expected_weighted_denominator
        and score.get("promotion_audit_complete") is True
    )
    integrity_reason = (
        "promotion_audit_incomplete"
        if score.get("promotion_audit_complete") is not True else None
    )
    infrastructure_crash = any(
        event.get("component") in UNSCORED_INFRASTRUCTURE_COMPONENTS
        for event in infrastructure_failure_events
    )
    score["score_status"], score["score_status_reason"] = _score_status_decision(
        score.get("scenario_constructed"), score_integrity_ok, integrity_reason,
        dynamic_scenario_qualified, infrastructure_crash, resource_safety_abort,
    )
    if linear_abnormal and score["score_status"] == "scored":
        # The main arm measured nothing: score as unscored rather than an
        # artificial empty X=0 that would look like a model failing to act.
        score["score_status"] = "unscored"
        score["score_status_reason"] = LINEAR_ABNORMAL_STATUS_REASON
    if score["score_status"] != "scored":
        score["test_point_pass_rate"] = None
        score["dynamic_control_score"] = None
        score["dt_score"] = None
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "score.json").write_text(json.dumps(score, indent=2, sort_keys=True), encoding="utf-8")
    if config.use_container and container and not config.keep_container:
        _docker("rm", "-f", container, check=False)
    _progress(
        config, "done",
        f"score_status={score['score_status']} D={score.get('dynamic_control_score')} "
        f"S={score.get('semantic_task_score')} DT={score.get('dt_score')} "
        f"scenario_constructed={score['scenario_constructed']}",
    )
    return score


def parse_adapter_command(value: str) -> list[str]:
    command = shlex.split(value, posix=os.name != "nt")
    if os.name == "nt":
        # shlex's Windows mode preserves surrounding quotes, but
        # create_subprocess_exec expects already-unquoted argv entries.
        command = [
            item[1:-1] if len(item) >= 2 and item[0] == item[-1] == '"' else item
            for item in command
        ]
    if not command:
        raise ValueError("adapter command is empty")
    return command
