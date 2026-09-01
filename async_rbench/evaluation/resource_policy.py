from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def load_resource_policy(root: Path) -> tuple[dict[str, Any], str]:
    contract_path = root / "evaluation_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    policy = dict(contract.get("resource_policy") or {})
    if not policy:
        raise ValueError("evaluation contract has no frozen resource_policy")
    digest = hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return policy, digest


def validate_official_resource_policy(
    root: Path, config_path: Path | None, *, episode_timeout_sec: int,
    gateway_grace_sec: int,
) -> str:
    """Reject an official run whose harness limits drift from the frozen policy."""
    if config_path is None:
        raise ValueError("official Track A requires --config bound to a frozen model profile")
    policy, digest = load_resource_policy(root)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("official Track A model profile must be a mapping")
    expected_profile = dict(policy.get("profile_limits") or {})
    mismatches = {
        key: {"expected": expected, "observed": config.get(key)}
        for key, expected in expected_profile.items()
        if config.get(key) != expected
    }
    expected_episode_timeout = int(policy.get("episode_timeout_sec") or 0)
    if episode_timeout_sec != expected_episode_timeout:
        mismatches["episode_timeout_sec"] = {
            "expected": expected_episode_timeout, "observed": episode_timeout_sec,
        }
    expected_gateway_grace = int(policy.get("gateway_grace_sec") or 0)
    if gateway_grace_sec != expected_gateway_grace:
        mismatches["gateway_grace_sec"] = {
            "expected": expected_gateway_grace, "observed": gateway_grace_sec,
        }
    if mismatches:
        raise ValueError(
            "official Track A resource policy mismatch: "
            + json.dumps(mismatches, sort_keys=True)
        )
    return digest
