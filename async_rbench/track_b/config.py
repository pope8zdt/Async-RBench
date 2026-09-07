from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


KNOWN_FRAMEWORKS = frozenset({
    "claude-code", "codex-cli", "langgraph", "openai-agents", "deterministic",
})
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
    runtime: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = field(default=None, compare=False, repr=False)

    @classmethod
    def from_file(cls, path: Path) -> "TrackBConfig":
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Track B config must be a mapping")
        allowed = {
            "track", "framework", "model", "credential_env", "components",
            "limits", "framework_options", "runtime",
        }
        unknown = sorted(set(loaded) - allowed)
        if unknown:
            raise ValueError(f"unknown Track B config fields: {', '.join(unknown)}")
        if "runtime" in loaded and not isinstance(loaded["runtime"], dict):
            raise ValueError("runtime must be a mapping")
        config = cls(
            track=str(loaded.get("track") or ""),
            framework=str(loaded.get("framework") or ""),
            model=str(loaded.get("model") or ""),
            credential_env=str(loaded.get("credential_env") or ""),
            components=dict(loaded.get("components") or {}),
            limits=dict(loaded.get("limits") or {}),
            framework_options=dict(loaded.get("framework_options") or {}),
            runtime=dict(loaded.get("runtime", {})),
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
        if self.framework == "codex-cli" and self.credential_env:
            raise ValueError(
                "codex-cli uses saved ChatGPT login; credential_env must be empty"
            )
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
        self.validate_runtime()

    def validate_runtime(self) -> None:
        if not isinstance(self.runtime, dict):
            raise ValueError("runtime must be a mapping")
        if not self.runtime:
            return
        kind = self.runtime.get("type")
        if kind == "host" and set(self.runtime) == {"type"}:
            return
        if kind != "docker":
            raise ValueError("runtime must be host or docker")
        if set(self.runtime) - {"type", "image", "cpus", "memory", "timeout_sec"}:
            raise ValueError("runtime contains unsupported options")
        image = self.runtime.get("image", "")
        if not isinstance(image, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,255}", image):
            raise ValueError("runtime.image must be a Docker image reference")
        cpus = self.runtime.get("cpus", 0.5)
        if type(cpus) not in {int, float} or not math.isfinite(cpus) or cpus <= 0:
            raise ValueError("runtime.cpus must be positive and finite")
        memory = self.runtime.get("memory", "768m")
        if not isinstance(memory, str) or not re.fullmatch(r"[1-9][0-9]*[mMgG]", memory):
            raise ValueError("runtime.memory must use a positive m or g value")
        timeout = self.runtime.get("timeout_sec", 2400)
        if type(timeout) is not int or not 1 <= timeout <= 86400:
            raise ValueError("runtime.timeout_sec must be between 1 and 86400")

    def _public_payload(self) -> dict[str, Any]:
        payload = {
            "track": self.track,
            "framework": self.framework,
            "model": self.model,
            "credential_env": self.credential_env,
            "components": dict(sorted(self.components.items())),
            "limits": dict(sorted(self.limits.items())),
            "framework_options": self.framework_options,
        }
        # Preserve historical host configuration digests byte for byte.
        if self.runtime:
            payload["runtime"] = self.runtime
        return payload

    def public_metadata(self) -> dict[str, Any]:
        payload = self._public_payload()
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        return {**payload, "config_sha256": hashlib.sha256(encoded).hexdigest()}
