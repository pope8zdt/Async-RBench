from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


PROFILE_TYPES = ("reference_scaffold_api", "native_agent", "minimal_api", "conformance_mock")
RUNTIME_MODES = ("api_only", "native_agent", "minimal", "conformance")
CHILD_ISOLATIONS = ("container_clone", "disabled")
TOKEN_ACCOUNTING = ("provider_usage", "adapter_estimated")


@dataclass
class AdapterProfile:
    """Declarative, participant-owned adapter profile.

    Describes *policy* (which policies are used, which runtime mode, which
    provider) without owning any kernel *mechanism*. A profile is validated by
    ``validate``.
    """

    profile: str
    runtime_mode: str
    child_isolation: str = "container_clone"
    workspace_mode: str = "container_clone"
    cancellation_policy: str = "model_decision"
    artifact_promotion: str = "explicit"
    same_model_main_child: bool = True
    token_accounting: str = "provider_usage"
    provider: dict[str, Any] = field(default_factory=dict)
    adapter_command: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AdapterProfile":
        known = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known})

    @classmethod
    def from_file(cls, path: Path) -> "AdapterProfile":
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"profile must be a mapping: {path}")
        return cls.from_dict(loaded)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.profile not in PROFILE_TYPES:
            errors.append(f"unknown profile type {self.profile!r}")
        if self.runtime_mode not in RUNTIME_MODES:
            errors.append(f"unknown runtime_mode {self.runtime_mode!r}")
        if self.child_isolation not in CHILD_ISOLATIONS:
            errors.append(f"unknown child_isolation {self.child_isolation!r}")
        if self.workspace_mode not in CHILD_ISOLATIONS:
            errors.append(f"unknown workspace_mode {self.workspace_mode!r}")
        if self.token_accounting not in TOKEN_ACCOUNTING:
            errors.append(f"unknown token_accounting {self.token_accounting!r}")
        return errors

    def metadata(self) -> dict[str, Any]:
        """Public profile metadata; excludes participant ``config``."""
        payload = asdict(self)
        payload.pop("config", None)
        return payload
