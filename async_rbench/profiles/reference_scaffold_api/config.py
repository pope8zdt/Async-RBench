from __future__ import annotations

import os
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ...evaluation.model_backend import ModelBackend, build_backend


# Role-specific provider fields that may be overridden per role inside the
# ``main_provider`` / ``child_provider`` nested mappings.  The legacy top-level
# single-provider fields remain the migration fallback for development configs
# that have not yet been split (spec §8).
_ROLE_PROVIDER_FIELDS = (
    "backend",
    "api_url",
    "api_key_env",
    "api_key_required",
    "max_api_concurrency",
    "max_tokens_parameter",
    "request_body_extra",
    "tokenizer",
)


@dataclass(frozen=True)
class ProviderRoleConfig:
    """The per-role provider-facing config surface the kernel backend reads.

    Structurally satisfies ``ProviderConfig`` (the kernel backend protocol),
    while additionally carrying the role identity and the fixed child-pool id so
    each backend can record role-separated provider metadata (spec §8).
    """

    backend: str
    api_url: str
    api_key_env: str
    api_key_required: bool
    max_api_concurrency: int
    max_tokens_parameter: str
    max_output_tokens: int
    send_seed: bool
    temperature: float | None
    request_body_extra: dict[str, Any]
    extra_headers: dict[str, str]
    request_timeout_sec: int
    codex_executable: str
    codex_reasoning_effort: str
    tokenizer: str
    role: str
    model: str
    child_pool_id: str

    def api_key(self) -> str:
        value = os.getenv(self.api_key_env, "") if self.api_key_env else ""
        if self.backend == "openai_compatible" and self.api_key_required and not value:
            raise RuntimeError(f"missing model API credential in environment variable {self.api_key_env}")
        return value

    def provider_identity(self) -> tuple[Any, ...]:
        """A hashable identity of the transport surface (role-agnostic).

        Two role configs are transport-reusable when every provider field except
        ``role`` / ``model`` / ``child_pool_id`` is identical.
        """
        return (
            self.backend,
            self.api_url,
            self.api_key_env,
            self.api_key_required,
            self.max_api_concurrency,
            self.max_tokens_parameter,
            self.max_output_tokens,
            self.send_seed,
            self.temperature,
            tuple(sorted((self.request_body_extra or {}).items())),
            tuple(sorted(self.extra_headers.items())),
            self.request_timeout_sec,
            self.codex_executable,
            self.codex_reasoning_effort,
            self.tokenizer,
        )


class _RoleView:
    """A role-scoped view over one shared backend transport (spec §8 reuse).

    Built only when the two role configs are exactly identical AND
    ``reuse_transport_when_identical`` is explicitly enabled.  The underlying
    backend is built once; this view re-labels the metadata (role /
    ``child_pool_id``) so logical configuration and metadata stay role-separated
    even though the transport is shared.
    """

    def __init__(self, inner: ModelBackend, role_config: ProviderRoleConfig) -> None:
        self._inner = inner
        self._role_config = role_config

    async def complete(self, **kwargs: Any) -> Any:
        return await self._inner.complete(**kwargs)

    def estimate_input_tokens(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        return self._inner.estimate_input_tokens(messages, tools)

    def runtime_metadata(self) -> dict[str, Any]:
        meta = dict(self._inner.runtime_metadata() or {})
        meta["role"] = self._role_config.role
        meta["child_pool_id"] = self._role_config.child_pool_id
        return meta


def build_backends(config: "ScaffoldConfig") -> tuple[ModelBackend, ModelBackend]:
    """Build the role-scoped ``main_backend`` and ``child_backend`` (spec §8).

    ``build_backend()`` is called twice by default.  When the two provider
    configs are exactly identical and transport reuse is explicitly enabled, one
    underlying backend is built and the child role is exposed through a
    role-scoped view so metadata stays separated by role.
    """
    main_cfg = config.provider_role_config("main")
    child_cfg = config.provider_role_config("child")
    if config.reuse_transport_when_identical and main_cfg.provider_identity() == child_cfg.provider_identity():
        shared = build_backend(main_cfg)
        return shared, _RoleView(shared, child_cfg)
    return build_backend(main_cfg), build_backend(child_cfg)


@dataclass
class ScaffoldConfig:
    """Runtime configuration. Secrets are always read from the environment."""

    backend: str = "openai_compatible"
    api_url: str = "https://api.openai.com/v1/chat/completions"
    api_key_env: str = "OPENAI_API_KEY"
    api_key_required: bool = True
    main_model: str = ""
    child_model: str = ""
    temperature: float | None = 0.0
    max_output_tokens: int = 8192
    max_tokens_parameter: str = "max_completion_tokens"
    send_seed: bool = True
    max_main_turns: int = 100
    max_child_turns: int = 40
    max_concurrent_children: int = 3
    # Bounded model-requested replacement/recovery spawns. Benchmark-owned
    # initial-wave children are tracked separately and do not consume this.
    max_total_child_spawns: int = 5
    max_api_concurrency: int = 4
    # Legacy single-pool ceiling, retained only for non-official legacy profiles
    # (spec §7.3).  Official Track A profiles declare the split pools below.
    max_total_tokens: int = 500000
    # Split token budget pools (spec §7).  Async: main_pre / child_shared /
    # main_post.  Linear: child_shared / main_total (the two 500k main pools
    # merged to keep the same 1M main budget).
    budget_child_shared: int = 1_000_000
    budget_main_pre: int = 500_000
    budget_main_post: int = 500_000
    budget_main_total: int = 1_000_000
    # Optional exact tokenizer identity; empty string opts into conservative
    # input estimation with accounting_mode="conservative" (spec §7.3).
    tokenizer: str = ""
    main_terminal_timeout_sec: int = 180
    child_terminal_timeout_sec: int = 180
    child_timeout_sec: int = 900
    start_barrier_timeout_sec: int = 120
    live_cancellation_grace_sec: int = 60
    workspace_mode: str = "container_clone"
    keep_child_workspaces: bool = False
    max_tool_output_chars: int = 20000
    request_timeout_sec: int = 300
    codex_executable: str = "codex"
    codex_reasoning_effort: str = "high"
    extra_headers: dict[str, str] = field(default_factory=dict)
    request_body_extra: dict[str, Any] = field(default_factory=dict)
    # Dual provider roles (spec §8). ``main_provider`` / ``child_provider`` are
    # role-specific overrides; when a key is absent the legacy top-level single
    # provider field is used as the migration fallback.  ``child_pool_id`` is the
    # stable identity of the fixed child pool shared across compared models.
    main_provider: dict[str, Any] = field(default_factory=dict)
    child_provider: dict[str, Any] = field(default_factory=dict)
    child_pool_id: str = ""
    # Transport-reuse optimization for exactly-identical main/child providers.
    # Metadata and budget accounting remain role-separated even when enabled.
    reuse_transport_when_identical: bool = False

    @classmethod
    def from_file(cls, path: Path | None, overrides: dict[str, Any] | None = None) -> "ScaffoldConfig":
        raw: dict[str, Any] = {}
        if path is not None:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if loaded:
                if not isinstance(loaded, dict):
                    raise ValueError("scaffold config must be a mapping")
                raw = loaded
        env_overrides = {
            "api_url": os.getenv("ASYNC_RBENCH_MODEL_API_URL"),
            "api_key_env": os.getenv("ASYNC_RBENCH_MODEL_API_KEY_ENV"),
            "main_model": os.getenv("ASYNC_RBENCH_MAIN_MODEL"),
            "child_model": os.getenv("ASYNC_RBENCH_CHILD_MODEL"),
            "max_total_tokens": (
                int(os.environ["ASYNC_RBENCH_MAX_TOTAL_TOKENS"])
                if os.getenv("ASYNC_RBENCH_MAX_TOTAL_TOKENS") else None
            ),
        }
        raw.update({key: value for key, value in env_overrides.items() if value is not None})
        raw.update({key: value for key, value in (overrides or {}).items() if value is not None})
        config = cls(**raw)
        if config.backend == "scripted_test" and not config.main_model:
            config.main_model = "scripted-test"
        if not config.child_model:
            config.child_model = config.main_model
        config.validate()
        return config

    def provider_role_config(self, role: str) -> ProviderRoleConfig:
        """Resolve the per-role provider config, overlaying the nested mapping.

        The legacy top-level single-provider fields are the fallback for every
        role (the migration path for development configs); a role-provider
        mapping overrides the role-specific keys when present.
        """
        if role not in {"main", "child"}:
            raise ValueError(f"provider role must be 'main' or 'child', got {role!r}")
        override = self.main_provider if role == "main" else self.child_provider
        if not isinstance(override, dict):
            raise ValueError(f"{role}_provider must be a mapping")
        resolver: dict[str, Any] = {
            "backend": self.backend,
            "api_url": self.api_url,
            "api_key_env": self.api_key_env,
            "api_key_required": self.api_key_required,
            "max_api_concurrency": self.max_api_concurrency,
            "max_tokens_parameter": self.max_tokens_parameter,
            "request_body_extra": self.request_body_extra,
            "tokenizer": self.tokenizer,
        }
        for key in _ROLE_PROVIDER_FIELDS:
            if key in override and override[key] is not None:
                resolver[key] = override[key]
        return ProviderRoleConfig(
            backend=resolver["backend"],
            api_url=resolver["api_url"],
            api_key_env=resolver["api_key_env"],
            api_key_required=resolver["api_key_required"],
            max_api_concurrency=resolver["max_api_concurrency"],
            max_tokens_parameter=resolver["max_tokens_parameter"],
            max_output_tokens=self.max_output_tokens,
            send_seed=self.send_seed,
            temperature=self.temperature,
            request_body_extra=resolver["request_body_extra"],
            extra_headers=self.extra_headers,
            request_timeout_sec=self.request_timeout_sec,
            codex_executable=self.codex_executable,
            codex_reasoning_effort=self.codex_reasoning_effort,
            tokenizer=resolver["tokenizer"],
            role=role,
            model=self.main_model if role == "main" else self.child_model,
            child_pool_id=self.child_pool_id,
        )

    def _provider_identity_metadata(self, role: str) -> dict[str, Any]:
        """Provider identity (never secrets) for participant metadata (spec §8)."""
        cfg = self.provider_role_config(role)
        return {
            "backend": cfg.backend,
            "api_url": cfg.api_url,
            "max_api_concurrency": cfg.max_api_concurrency,
            "max_tokens_parameter": cfg.max_tokens_parameter,
            "request_body_extra": cfg.request_body_extra,
            "tokenizer": cfg.tokenizer,
            "model": cfg.model,
        }

    def validate(self) -> None:
        if self.backend not in {"openai_compatible", "codex_cli", "scripted_test"}:
            raise ValueError(f"unsupported backend {self.backend!r}")
        if self.backend in {"openai_compatible", "codex_cli"} and not self.main_model:
            raise ValueError(f"main_model is required for {self.backend} backend")
        if self.backend == "openai_compatible" and self.api_key_required and not self.api_key_env:
            raise ValueError("api_key_env is required when api_key_required is true")
        if self.workspace_mode not in {"container_clone", "disabled"}:
            raise ValueError("workspace_mode must be container_clone or disabled")
        if self.max_tokens_parameter not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("max_tokens_parameter must be max_tokens or max_completion_tokens")
        if self.codex_reasoning_effort not in {"low", "medium", "high", "xhigh", "max", "ultra"}:
            raise ValueError("unsupported codex_reasoning_effort")
        if self.backend == "codex_cli" and not self.codex_executable.strip():
            raise ValueError("codex_executable is required for codex_cli backend")
        protected = {"model", "messages", "tools", "tool_choice", "max_tokens", "max_completion_tokens"}
        overlap = protected & set(self.request_body_extra)
        if overlap:
            raise ValueError(f"request_body_extra cannot override protected fields: {sorted(overlap)}")
        for name in (
            "max_main_turns", "max_child_turns", "max_concurrent_children",
            "max_total_child_spawns", "max_api_concurrency",
            "max_total_tokens",
            "budget_child_shared", "budget_main_pre", "budget_main_post",
            "budget_main_total",
            "start_barrier_timeout_sec", "live_cancellation_grace_sec",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_total_child_spawns < self.max_concurrent_children:
            raise ValueError("max_total_child_spawns must be at least max_concurrent_children")
        if self.budget_main_total != self.budget_main_pre + self.budget_main_post:
            raise ValueError(
                "budget_main_total must equal budget_main_pre + budget_main_post"
            )
        for role in ("main", "child"):
            override = self.main_provider if role == "main" else self.child_provider
            if not isinstance(override, dict):
                raise ValueError(f"{role}_provider must be a mapping")
            provider_backend = override.get("backend", self.backend)
            if provider_backend not in {"openai_compatible", "codex_cli", "scripted_test"}:
                raise ValueError(f"{role}_provider has unsupported backend {provider_backend!r}")
            if override.get("max_api_concurrency") is not None and int(override["max_api_concurrency"]) <= 0:
                raise ValueError(f"{role}_provider max_api_concurrency must be positive")
            if override.get("max_tokens_parameter") is not None and override["max_tokens_parameter"] not in {
                "max_tokens", "max_completion_tokens"
            }:
                raise ValueError(
                    f"{role}_provider max_tokens_parameter must be max_tokens or max_completion_tokens"
                )
            sub_extra = override.get("request_body_extra")
            if isinstance(sub_extra, dict):
                overlap_sub = protected & set(sub_extra)
                if overlap_sub:
                    raise ValueError(
                        f"{role}_provider request_body_extra cannot override protected fields: {sorted(overlap_sub)}"
                    )

    def public_metadata(self) -> dict[str, Any]:
        payload = {
            "backend": self.backend,
            "api_url": self.api_url,
            "api_key_required": self.api_key_required,
            "main_model": self.main_model,
            "child_model": self.child_model,
            "child_pool_id": self.child_pool_id,
            "main_provider": self._provider_identity_metadata("main"),
            "child_provider": self._provider_identity_metadata("child"),
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "max_tokens_parameter": self.max_tokens_parameter,
            "send_seed": self.send_seed,
            "max_main_turns": self.max_main_turns,
            "max_child_turns": self.max_child_turns,
            "max_concurrent_children": self.max_concurrent_children,
            "max_total_child_spawns": self.max_total_child_spawns,
            "max_api_concurrency": self.max_api_concurrency,
            "max_total_tokens": self.max_total_tokens,
            "budget_child_shared": self.budget_child_shared,
            "budget_main_pre": self.budget_main_pre,
            "budget_main_post": self.budget_main_post,
            "budget_main_total": self.budget_main_total,
            "tokenizer": self.tokenizer,
            "start_barrier_timeout_sec": self.start_barrier_timeout_sec,
            "live_cancellation_grace_sec": self.live_cancellation_grace_sec,
            "workspace_mode": self.workspace_mode,
            "request_body_extra": self.request_body_extra,
            "codex_reasoning_effort": self.codex_reasoning_effort,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return {**payload, "config_sha256": hashlib.sha256(encoded).hexdigest()}

    def api_key(self) -> str:
        value = os.getenv(self.api_key_env, "") if self.api_key_env else ""
        if self.backend == "openai_compatible" and self.api_key_required and not value:
            raise RuntimeError(f"missing model API credential in environment variable {self.api_key_env}")
        return value
