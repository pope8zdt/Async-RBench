from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .paths import registered_case_dir, registry_file


EXPERIMENT_RELATIVE = Path("experiments") / "drs-validity-v1"
EXPECTED_INSTANCES_SHA256 = (
    "175d4f6015ce2a39f2273fdb9221cd67d5c313f9a5a86a17ef9cc2acf33d2b31"
)
EXPECTED_MODELS = (
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gemini-3-flash-preview-thinking-high",
)
EXPECTED_REPEATS = (2026, 2027, 2028)
EXPECTED_CONDITIONS = (
    "oracle_replan",
    "native_agent",
    "frozen_plan",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _normalized_instance_lines(path: Path) -> list[str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line]


def normalized_instances_sha256(path: Path) -> str:
    canonical = "\n".join(_normalized_instance_lines(path)) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_case_metadata(root: Path, case_id: str) -> dict[str, str]:
    registry = _read_json(registry_file(root))
    entries = {
        str(item["case_id"]): item
        for item in registry.get("case_families", [])
        if isinstance(item, dict) and item.get("case_id")
    }
    if case_id not in entries:
        raise ValueError(f"unregistered case: {case_id}")

    case_root = registered_case_dir(root, case_id)
    task = yaml.safe_load((case_root / "task" / "task.yaml").read_text(encoding="utf-8"))
    private = yaml.safe_load(
        (case_root / "evaluator" / "case.yaml").read_text(encoding="utf-8")
    )
    classification = private.get("classification") or {}
    theme = classification.get("primary_event_theme") or private.get(
        "primary_event_theme"
    )
    return {
        "source": str(entries[case_id]["benchmark"]),
        "difficulty": str(task["difficulty"]).lower(),
        "theme": str(theme),
    }


def load_registry(root: Path) -> dict[str, Any]:
    experiment = root.resolve() / EXPERIMENT_RELATIVE
    cohort = _read_json(experiment / "cohort.json")
    condition_document = _read_json(experiment / "conditions.json")
    return {
        **cohort,
        "conditions": condition_document.get("conditions", {}),
        "analysis_plan": _read_json(experiment / "analysis-plan.json"),
    }


def expected_positions(registry: dict[str, Any]) -> tuple[int, int]:
    prefix_count = (
        len(registry.get("instances", []))
        * len(registry.get("models", []))
        * len(registry.get("repeats", []))
    )
    continuation_count = prefix_count * len(registry.get("conditions", {}))
    return prefix_count, continuation_count


def validate_registry(root: Path) -> list[str]:
    root = root.resolve()
    experiment = root / EXPERIMENT_RELATIVE
    errors: list[str] = []
    try:
        registry = load_registry(root)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [f"registry could not be loaded: {exc}"]

    instance_path = experiment / "instances.txt"
    instance_keys = _normalized_instance_lines(instance_path)
    digest = normalized_instances_sha256(instance_path)
    if digest != EXPECTED_INSTANCES_SHA256:
        errors.append(
            f"instances digest mismatch: expected {EXPECTED_INSTANCES_SHA256}, got {digest}"
        )
    if registry.get("selection_sha256") != EXPECTED_INSTANCES_SHA256:
        errors.append("cohort selection_sha256 is not the frozen digest")
    declared = [str(item.get("instance_key")) for item in registry.get("instances", [])]
    if declared != instance_keys:
        errors.append("cohort instances do not exactly match instances.txt order")
    if len(instance_keys) != 16 or len(set(instance_keys)) != 16:
        errors.append("validation cohort must contain exactly 16 unique instances")

    for item in registry.get("instances", []):
        key = str(item.get("instance_key", ""))
        case_id, separator, instance_id = key.partition("::")
        if not separator or instance_id != "seed-1":
            errors.append(f"invalid frozen instance key: {key}")
            continue
        try:
            canonical = _canonical_case_metadata(root, case_id)
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"{key}: could not resolve canonical metadata: {exc}")
            continue
        for field in ("source", "difficulty", "theme"):
            if str(item.get(field)) != canonical[field]:
                errors.append(
                    f"{key}: {field} mismatch: declared {item.get(field)!r}, "
                    f"canonical {canonical[field]!r}"
                )

    themes = Counter(item.get("theme") for item in registry.get("instances", []))
    if len(themes) != 8 or set(themes.values()) != {2}:
        errors.append("validation cohort must contain exactly two instances per theme")
    if Counter(item.get("difficulty") for item in registry.get("instances", [])) != {
        "hard": 8,
        "medium": 8,
    }:
        errors.append("validation cohort must contain 8 hard and 8 medium instances")
    if Counter(item.get("source") for item in registry.get("instances", [])) != {
        "multiagentbench": 5,
        "terminal-bench": 4,
        "osworld": 4,
        "swe-bench": 3,
    }:
        errors.append("validation cohort source counts do not match the frozen allocation")

    models = [item.get("model_id") for item in registry.get("models", [])]
    if tuple(models) != EXPECTED_MODELS:
        errors.append("model panel does not match the frozen high/mid/low panel")
    for item in registry.get("models", []):
        profile = root / str(item.get("profile", ""))
        if not profile.is_file():
            errors.append(f"missing model profile: {item.get('profile')}")
            continue
        try:
            profile_data = yaml.safe_load(profile.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"invalid model profile {item.get('profile')}: {exc}")
            continue
        if str(profile_data.get("main_model")) != str(item.get("model_id")):
            errors.append(
                f"model profile {item.get('profile')} resolves main_model "
                f"{profile_data.get('main_model')!r}, not {item.get('model_id')!r}"
            )
    if tuple(registry.get("repeats", [])) != EXPECTED_REPEATS:
        errors.append("repeat seeds must be exactly 2026, 2027, and 2028")
    if tuple(registry.get("conditions", {})) != EXPECTED_CONDITIONS:
        errors.append("conditions must be oracle_replan, native_agent, frozen_plan")
    if registry.get("experiment_kind") != "drs_validity":
        errors.append("experiment_kind must be drs_validity")
    output_root = str(registry.get("output_root", ""))
    if output_root != "runs/drs-validity-v1":
        errors.append("validation output root must be isolated from paper experiment runs")
    if expected_positions(registry) != (144, 432):
        errors.append("registry must define 144 checkpoints and 432 continuations")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DRS validity v1 experiment")
    parser.add_argument("command", choices=["check", "create-manifest"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--order-seed", type=int, default=20260917)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    errors = validate_registry(args.root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    if args.command == "create-manifest":
        if args.output is None:
            print("ERROR: create-manifest requires --output")
            return 2
        from .evaluation.validation_manifest import (
            create_validation_manifest,
            validate_validation_manifest,
            write_validation_manifest,
        )

        manifest = create_validation_manifest(args.root, order_seed=args.order_seed)
        manifest_errors = validate_validation_manifest(args.root, manifest)
        if manifest_errors:
            for error in manifest_errors:
                print(f"ERROR: {error}")
            return 1
        write_validation_manifest(args.output, manifest)
        print(
            f"Wrote {manifest['manifest_status']} validation manifest to "
            f"{args.output} ({manifest['manifest_sha256']})"
        )
        return 0

    prefix_count, continuation_count = expected_positions(load_registry(args.root))
    print(
        "DRS validity registry OK: "
        f"{prefix_count} checkpoints, {continuation_count} continuations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
