from __future__ import annotations

import json
import re
from pathlib import Path

from .guidance import GUIDANCE_MODES
from .manifest import EXECUTION_MODES
from .case_contract import CAPABILITY_CATEGORIES
from .event_taxonomy import ASYNC_SCENARIO_CLASSES, EVENT_THEME_IDS
from .version import EVALUATION_CONTRACT_STATUS, EVALUATION_CONTRACT_VERSION


REQUIRED_METHOD_FILES = (
    "PROTOCOL.md",
    "ADAPTER_PROTOCOL.md",
    "evaluation_contract.json",
    "event_taxonomy.json",
    "schemas/adapter-event.schema.json",
)

KERNEL_CONTRACT_DOCS = (
    "docs/kernel-contract.md",
    "docs/adapter-contract.md",
)

# A profile may not reach for a container primitive directly; it must use the
# kernel capability RPC. Match the subprocess/exec call sites, not any mention
# of "docker" in comments or strings.
_DOCKER_SUBPROCESS = re.compile(
    r"(?:subprocess\.[a-z_]+|create_subprocess_[a-z]+|os\.(?:system|popen|spawn[a-z]*))\s*\([^)]*[\"']docker[\"']"
)
# The kernel must not import the adapter-profile layer.
_KERNEL_PROFILE_IMPORT = re.compile(r"^\s*(?:from|import)\s+.*\bprofiles\b")


def validate_evaluation_contract(root: Path) -> list[str]:
    errors = []
    for filename in REQUIRED_METHOD_FILES:
        if not (root / filename).is_file():
            errors.append(f"missing evaluation method file: {filename}")
    path = root / "evaluation_contract.json"
    if not path.is_file():
        return errors
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("version") != EVALUATION_CONTRACT_VERSION:
        errors.append("evaluation_contract version differs from executable version")
    if contract.get("status") != EVALUATION_CONTRACT_STATUS:
        errors.append("evaluation_contract status differs from executable status")
    if tuple(contract.get("execution_modes", [])) != EXECUTION_MODES:
        errors.append(
            "evaluation_contract execution modes differ from executable modes"
        )
    if set(contract.get("case_capability_categories") or []) != set(CAPABILITY_CATEGORIES):
        errors.append("evaluation_contract capability categories differ from executable categories")
    if set(contract.get("case_event_themes") or []) != set(EVENT_THEME_IDS):
        errors.append("evaluation_contract event themes differ from event taxonomy")
    if set(contract.get("async_scenario_classes") or []) != set(ASYNC_SCENARIO_CLASSES):
        errors.append("evaluation_contract async scenario classes differ from event taxonomy")
    separation = contract.get("event_capability_separation") or {}
    if not all(str(separation.get(key) or "").strip() for key in (
        "event_theme", "capability", "trajectory_policy",
    )):
        errors.append("evaluation_contract must define event/capability separation and trajectory policy")
    if contract.get("default_guidance") not in GUIDANCE_MODES:
        errors.append("evaluation_contract default_guidance is invalid")
    if contract.get("judge") != "programmatic_only":
        errors.append("headline evaluation must be programmatic_only")
    if "reward_tiers" in contract:
        errors.append("X-only evaluation_contract must not define reward tiers")
    outcomes = contract.get("primary_outcomes", {})
    if set(outcomes) != {
        "dynamic_control", "semantic_task", "dt_score", "leaderboard",
        "linear_semantic_baseline", "paired_semantic_drop", "capability_breakdown",
    }:
        errors.append("evaluation_contract primary outcomes do not match v9")
    if not isinstance(contract.get("calibration_diagnostics"), dict):
        errors.append("evaluation_contract must define calibration diagnostics")
    x_rules = contract.get("x_rules", {})
    if x_rules.get("infrastructure_failure_is_unscored") is None:
        errors.append("evaluation_contract must define infrastructure-failure scoring")
    return errors


def validate_kernel_adapter_contract(root: Path) -> list[str]:
    """Enforce the kernel/adapter boundary as executable checks.

    - the two boundary documents exist;
    - no kernel module imports the adapter-profile layer;
    - no adapter profile invokes a container primitive directly.

    The profile layer may not exist yet (it is introduced in a later phase);
    the docker check is then a no-op rather than an error.
    """
    errors = []
    for filename in KERNEL_CONTRACT_DOCS:
        if not (root / filename).is_file():
            errors.append(f"missing contract document: {filename}")

    kernel_paths = [root / "async_rbench" / "private_eval.py"]
    kernel_dir = root / "async_rbench" / "evaluation"
    if kernel_dir.is_dir():
        kernel_paths.extend(sorted(kernel_dir.glob("*.py")))
    for path in kernel_paths:
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if _KERNEL_PROFILE_IMPORT.match(line):
                errors.append(
                    f"kernel imports the profile layer (forbidden): "
                    f"{path.relative_to(root)}:{lineno}"
                )

    profiles_dir = root / "async_rbench" / "profiles"
    if profiles_dir.is_dir():
        for path in sorted(profiles_dir.rglob("*.py")):
            for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if _DOCKER_SUBPROCESS.search(line):
                    errors.append(
                        f"profile calls docker directly (use kernel capability RPC): "
                        f"{path.relative_to(root)}:{lineno}"
                    )

    return errors
