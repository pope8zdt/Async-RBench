"""Opt-in container limits for an isolated Track B launch process.

Unset variables preserve the evaluator's existing Docker commands. Launchers
must scope these variables to their own process rather than changing host-wide
settings. Immutable participant image overrides are restricted to development
Track B episodes; they never change official image selection.
"""
from __future__ import annotations

import json
import os
import re
from decimal import Decimal


def container_resource_args() -> tuple[str, ...]:
    """Validate explicit limits before the caller creates any Docker resources."""
    args: list[str] = []
    cpus = os.environ.get("TRACK_B_CONTAINER_CPUS")
    if cpus is not None:
        if not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)", cpus) or Decimal(cpus) <= 0:
            raise ValueError("TRACK_B_CONTAINER_CPUS must be a positive decimal number")
        args.extend(("--cpus", cpus))
    memory = os.environ.get("TRACK_B_CONTAINER_MEMORY")
    if memory is not None:
        match = re.fullmatch(r"([0-9]+)([bkmg]?)", memory, flags=re.IGNORECASE)
        if match is None or int(match.group(1)) <= 0:
            raise ValueError("TRACK_B_CONTAINER_MEMORY must be a positive integer with optional b/k/m/g unit")
        args.extend(("--memory", memory))
    return tuple(args)


def participant_image_override(
    case_id: str, instance_id: str, *, adapter_profile: str | None, official_track: bool,
) -> str | None:
    """Use only immutable IDs from an explicitly supplied nonofficial Track B map."""
    if adapter_profile != "track_b" or official_track:
        return None
    variable = "TRACK_B_PARTICIPANT_IMAGE_IDS"
    raw = os.environ.get(variable)
    if raw is None:
        return None
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{variable} must be a JSON object of case::instance to image ID") from exc
    if not isinstance(mapping, dict):
        raise ValueError(f"{variable} must be a JSON object of case::instance to image ID")
    for key, image_id in mapping.items():
        if (
            not re.fullmatch(r"[^:\s]+::[^:\s]+", key)
            or not isinstance(image_id, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
        ):
            raise ValueError(f"{variable} requires case::instance keys and immutable sha256 image IDs")
    key = f"{case_id}::{instance_id}"
    if key not in mapping:
        raise ValueError(f"{variable} has no image for {key}; refusing an implicit image build")
    return mapping[key]
