from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


KNOWN_FRAMEWORKS = frozenset({"claude-code", "langgraph", "openai-agents", "deterministic"})
COMPONENT_NAMES = frozenset({
    "context_builder",
    "delegation_policy",
    "agent_policy",
    "lifecycle_hooks",
    "model_backend",
})


@dataclass(frozen=True)
class TrackBConfig:
    track: str
    framework: str
    model: str
    credential_env: str = ""
    components: dict[str, str] = field(default_factory=dict)
    limits: dict[str, int] = field(default_factory=dict)
    framework_options: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = field(default=None, compare=False, repr=False)

    @classmethod
    def from_file(cls, path: Path) -> "TrackBConfig":
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Track B config must be a mapping")
        allowed = {
            "track", "framework", "model", "credential_env", "components",
            "limits", "framework_options",
        }
        unknown = sorted(set(loaded) - allowed)
        if unknown:
            raise ValueError(f"unknown Track B config fields: {', '.join(unknown)}")
        config = cls(
            track=str(loaded.get("track") or ""),
            framework=str(loaded.get("framework") or ""),
            model=str(loaded.get("model") or ""),
            credential_env=str(loaded.get("credential_env") or ""),
            components=dict(loaded.get("components") or {}),
            limits=dict(loaded.get("limits") or {}),
            framework_options=dict(loaded.get("framework_options") or {}),
            source_path=path.resolve(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.track != "B":
            raise ValueError("track must be B")
        if self.framework not in KNOWN_FRAMEWORKS:
            raise ValueError(f"unknown Track B framework: {self.framework!r}")
        if not self.model:
            raise ValueError("Track B model is required")
        unknown_components = sorted(set(self.components) - COMPONENT_NAMES)
        if unknown_components:
            raise ValueError(
                "unknown Track B components: " + ", ".join(unknown_components)
            )
        for name, value in self.components.items():
            if not isinstance(value, str) or ":" not in value:
                raise ValueError(f"component {name!r} must be an absolute module:factory")
        for name, value in self.limits.items():
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"limit {name!r} must be a positive integer")

    def _public_payload(self) -> dict[str, Any]:
        return {
            "track": self.track,
            "framework": self.framework,
            "model": self.model,
            "credential_env": self.credential_env,
            "components": dict(sorted(self.components.items())),
            "limits": dict(sorted(self.limits.items())),
            "framework_options": self.framework_options,
        }

    def public_metadata(self) -> dict[str, Any]:
        payload = self._public_payload()
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        return {**payload, "config_sha256": hashlib.sha256(encoded).hexdigest()}
