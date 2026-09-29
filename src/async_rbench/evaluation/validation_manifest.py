from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
from typing import Any

import yaml

from ..drs_validity import (
    EXPECTED_CONDITIONS,
    expected_positions,
    load_registry,
    validate_registry,
)
from ..paths import registered_case_dir
from ..private_eval import verifier_bundle_sha256
from .case_bundle import case_bundle_sha256


MANIFEST_VERSION = "drs-validity-1.0"
EXPERIMENT_RELATIVE = Path("experiments") / "drs-validity-v1"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _instrument_name(instance_key: str) -> str:
    case_id, instance_id = instance_key.split("::", 1)
    return f"{case_id}--{instance_id}.json"


def _instrument_digest(path: Path) -> str | None:
    return _file_sha256(path) if path.is_file() else None


def _event_contract(root: Path, case_id: str) -> tuple[str, str]:
    case_root = registered_case_dir(root, case_id)
    private = yaml.safe_load(
        (case_root / "evaluator" / "case.yaml").read_text(encoding="utf-8")
    )
    control_path = case_root / "task" / "tests" / "control_flow_checks.json"
    control = json.loads(control_path.read_text(encoding="utf-8"))
    contracts = list(control.get("event_contracts") or [])
    if not contracts:
        raise ValueError(f"{case_id} has no event_contracts")
    target_event_id = str(contracts[0].get("event_id") or "")
    if not target_event_id:
        raise ValueError(f"{case_id} first event contract has no event_id")
    async_events = list(
        (((private.get("scenarios") or {}).get("async") or {}).get("events") or [])
    )
    target_events = [item for item in async_events if str(item.get("id")) == target_event_id]
    if len(target_events) != 1:
        raise ValueError(
            f"{case_id} target event {target_event_id!r} does not resolve uniquely"
        )
    return target_event_id, _digest(
        {"event": target_events[0], "control_contract": contracts[0]}
    )


def _checkpoint_id(instance_key: str, model_id: str, repeat: int) -> str:
    suffix = hashlib.sha256(
        f"{instance_key}|{model_id}|{repeat}".encode("utf-8")
    ).hexdigest()[:16]
    return f"ckpt-{suffix}"


def _condition_order(checkpoint_id: str, order_seed: int) -> list[str]:
    seed_bytes = hashlib.sha256(f"{order_seed}:{checkpoint_id}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(seed_bytes[:8], "big"))
    order = list(EXPECTED_CONDITIONS)
    rng.shuffle(order)
    return order


def create_validation_manifest(
    root: Path, *, order_seed: int = 20260917,
) -> dict[str, Any]:
    root = root.resolve()
    registry_errors = validate_registry(root)
    if registry_errors:
        raise ValueError("invalid DRS validity registry: " + "; ".join(registry_errors))
    registry = load_registry(root)
    experiment = root / EXPERIMENT_RELATIVE
    condition_digest = _file_sha256(experiment / "conditions.json")
    analysis_digest = _file_sha256(experiment / "analysis-plan.json")

    model_facts: dict[str, dict[str, str]] = {}
    for model in registry["models"]:
        profile_path = root / model["profile"]
        model_facts[model["model_id"]] = {
            "profile": model["profile"],
            "profile_sha256": _file_sha256(profile_path),
        }

    case_facts: dict[str, dict[str, Any]] = {}
    instruments_frozen = True
    for item in registry["instances"]:
        instance_key = item["instance_key"]
        case_id, instance_id = instance_key.split("::", 1)
        target_event_id, event_contract_sha256 = _event_contract(root, case_id)
        card_digest = _instrument_digest(
            experiment / "oracle-cards" / _instrument_name(instance_key)
        )
        probe_digest = _instrument_digest(
            experiment / "held-out-probes" / _instrument_name(instance_key)
        )
        instruments_frozen = instruments_frozen and bool(card_digest and probe_digest)
        case_facts[instance_key] = {
            "case_id": case_id,
            "instance_id": instance_id,
            "case_bundle_sha256": case_bundle_sha256(registered_case_dir(root, case_id)),
            "verifier_bundle_sha256": verifier_bundle_sha256(
                registered_case_dir(root, case_id) / "task"
            ),
            "target_event_id": target_event_id,
            "event_contract_sha256": event_contract_sha256,
            "oracle_card_sha256": card_digest,
            "held_out_probe_sha256": probe_digest,
        }

    checkpoints: list[dict[str, Any]] = []
    continuations: list[dict[str, Any]] = []
    for instance in registry["instances"]:
        instance_key = instance["instance_key"]
        facts = case_facts[instance_key]
        for model in registry["models"]:
            model_id = model["model_id"]
            profile = model_facts[model_id]
            for repeat in registry["repeats"]:
                checkpoint_id = _checkpoint_id(instance_key, model_id, int(repeat))
                checkpoint_position = f"{instance_key}|{model_id}|{repeat}"
                checkpoint = {
                    "checkpoint_id": checkpoint_id,
                    "position_key": checkpoint_position,
                    "instance_key": instance_key,
                    "case_id": facts["case_id"],
                    "instance_id": facts["instance_id"],
                    "model_id": model_id,
                    "repeat": int(repeat),
                    "agent_seed": int(repeat),
                    "profile": profile["profile"],
                    "profile_sha256": profile["profile_sha256"],
                    "case_bundle_sha256": facts["case_bundle_sha256"],
                    "verifier_bundle_sha256": facts["verifier_bundle_sha256"],
                    "target_event_id": facts["target_event_id"],
                    "event_contract_sha256": facts["event_contract_sha256"],
                }
                checkpoints.append(checkpoint)
                for ordinal, condition in enumerate(
                    _condition_order(checkpoint_id, order_seed), start=1
                ):
                    position_key = f"{checkpoint_position}|{checkpoint_id}|{condition}"
                    continuations.append(
                        {
                            "continuation_id": "cont-"
                            + hashlib.sha256(position_key.encode("utf-8")).hexdigest()[:16],
                            "position_key": position_key,
                            "checkpoint_id": checkpoint_id,
                            "condition_order": ordinal,
                            "condition": condition,
                            "instance_key": instance_key,
                            "case_id": facts["case_id"],
                            "model_id": model_id,
                            "repeat": int(repeat),
                            "condition_sha256": condition_digest,
                            "oracle_card_sha256": facts["oracle_card_sha256"],
                            "held_out_probe_sha256": facts["held_out_probe_sha256"],
                        }
                    )

    body: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "experiment_kind": "drs_validity",
        "experiment_version": registry["experiment_version"],
        "manifest_status": "frozen" if instruments_frozen else "draft_instruments_unfrozen",
        "order_seed": int(order_seed),
        "selection_sha256": registry["selection_sha256"],
        "conditions_sha256": condition_digest,
        "analysis_plan_sha256": analysis_digest,
        "design": "shared pre-presentation checkpoint with three randomized continuations",
        "checkpoints": checkpoints,
        "continuations": continuations,
    }
    body["manifest_sha256"] = _digest(body)
    return body


def validate_validation_manifest(
    root: Path, manifest: dict[str, Any],
) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        errors.append(f"manifest_version must be {MANIFEST_VERSION}")
    if manifest.get("experiment_kind") != "drs_validity":
        errors.append("experiment_kind must be drs_validity")

    checkpoints = list(manifest.get("checkpoints") or [])
    continuations = list(manifest.get("continuations") or [])
    checkpoint_positions = [str(item.get("position_key")) for item in checkpoints]
    continuation_positions = [str(item.get("position_key")) for item in continuations]
    if len(checkpoint_positions) != len(set(checkpoint_positions)):
        errors.append("duplicate checkpoint position key")
    if len(continuation_positions) != len(set(continuation_positions)):
        errors.append("duplicate continuation position key")
    if len(checkpoints) != 144:
        errors.append(f"expected 144 checkpoints, found {len(checkpoints)}")
    if len(continuations) != 432:
        errors.append(f"expected 432 continuations, found {len(continuations)}")

    checkpoint_ids = {str(item.get("checkpoint_id")) for item in checkpoints}
    for item in continuations:
        if item.get("condition") not in EXPECTED_CONDITIONS:
            errors.append(f"unknown condition: {item.get('condition')!r}")
        if str(item.get("checkpoint_id")) not in checkpoint_ids:
            errors.append(
                f"continuation references unknown checkpoint: {item.get('checkpoint_id')!r}"
            )

    try:
        expected = create_validation_manifest(
            root, order_seed=int(manifest.get("order_seed", 20260917))
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError, yaml.YAMLError) as exc:
        errors.append(f"could not regenerate expected manifest: {exc}")
        return errors
    for field in (
        "selection_sha256",
        "conditions_sha256",
        "analysis_plan_sha256",
        "manifest_status",
    ):
        if manifest.get(field) != expected.get(field):
            errors.append(f"{field} does not match frozen inputs")
    if checkpoints != expected["checkpoints"]:
        errors.append("checkpoint records do not match frozen inputs")
    if continuations != expected["continuations"]:
        errors.append("continuation records do not match frozen inputs")
    supplied_digest = manifest.get("manifest_sha256")
    without_digest = dict(manifest)
    without_digest.pop("manifest_sha256", None)
    if supplied_digest != _digest(without_digest):
        errors.append("manifest_sha256 does not match manifest content")
    return errors


def write_validation_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
