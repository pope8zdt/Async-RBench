from __future__ import annotations

import os
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


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

    def public_metadata(self) -> dict[str, Any]:
        payload = {
            "backend": self.backend,
            "api_url": self.api_url,
            "api_key_required": self.api_key_required,
            "main_model": self.main_model,
            "child_model": self.child_model,
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
