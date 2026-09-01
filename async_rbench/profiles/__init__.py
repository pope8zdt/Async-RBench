"""Pluggable adapter-profile layer (Layer 3).

Profiles own *policy* (agent loop, planner, scheduler, tool router, subagent
manager, memory/cancellation/revalidation policy). They never own kernel
*mechanism* and never reach for a container primitive directly — see
``async_rbench.evaluation.contract.validate_kernel_adapter_contract``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .profile import AdapterProfile, PROFILE_TYPES, RUNTIME_MODES

# Adapters are spawned by the kernel as subprocesses. Use the kernel's own
# interpreter (``sys.executable``) rather than a bare ``python`` so the spawn
# cannot resolve to a different, dependency-less interpreter via PATH on
# Windows multi-python setups. ``adapters/*.py`` remain runnable directly.
BUILTIN_PROFILES: dict[str, AdapterProfile] = {
    "reference_scaffold_api": AdapterProfile(
        profile="reference_scaffold_api",
        runtime_mode="api_only",
        provider={"kind": "openai_compatible", "endpoint_env": "OPENAI_API_KEY"},
        adapter_command=[sys.executable, "adapters/reference_scaffold_api.py"],
    ),
    "native_agent": AdapterProfile(
        profile="native_agent",
        runtime_mode="native_agent",
        provider={"kind": "openai_compatible", "endpoint_env": "OPENAI_API_KEY"},
        adapter_command=[sys.executable, "adapters/native_agent.py"],
    ),
    "minimal_api": AdapterProfile(
        profile="minimal_api",
        runtime_mode="minimal",
        provider={"kind": "openai_compatible", "endpoint_env": "OPENAI_API_KEY"},
        adapter_command=[sys.executable, "adapters/minimal_api.py"],
    ),
    "conformance_mock": AdapterProfile(
        profile="conformance_mock",
        runtime_mode="conformance",
        child_isolation="disabled",
        workspace_mode="disabled",
        cancellation_policy="automatic",
        adapter_command=[sys.executable, "adapters/conformance_mock.py"],
    ),
}


def load_profile(name_or_path: str | Path) -> AdapterProfile:
    """Resolve a profile by built-in name or by YAML path."""
    if isinstance(name_or_path, str) and name_or_path in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[name_or_path]
    path = Path(name_or_path)
    if path.is_file():
        return AdapterProfile.from_file(path)
    raise ValueError(f"unknown adapter profile: {name_or_path}")


__all__ = [
    "AdapterProfile",
    "PROFILE_TYPES",
    "RUNTIME_MODES",
    "BUILTIN_PROFILES",
    "load_profile",
]
