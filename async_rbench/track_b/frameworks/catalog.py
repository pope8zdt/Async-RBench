from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
from dataclasses import dataclass

from ..config import TrackBConfig
from ..contracts import AgentRuntime


@dataclass(frozen=True)
class FrameworkSpec:
    name: str
    module: str
    dependency: str | None
    executable: str | None
    install_extra: str
    public: bool = True


@dataclass(frozen=True)
class DoctorReport:
    framework: str
    ready: bool
    dependency_present: bool
    executable_present: bool
    credential_present: bool
    install_hint: str
    detail: str


FRAMEWORKS: dict[str, FrameworkSpec] = {
    "claude-code": FrameworkSpec(
        "claude-code", "claude_code", "claude_agent_sdk", "claude",
        'pip install "async-rbench[track-b-claude]"',
    ),
    "codex-cli": FrameworkSpec(
        "codex-cli", "codex_cli", None, "codex",
        "Install the Codex CLI, then run codex login with ChatGPT",
    ),
    "langgraph": FrameworkSpec(
        "langgraph", "langgraph", "langgraph", None,
        'pip install "async-rbench[track-b-langgraph]"',
    ),
    "openai-agents": FrameworkSpec(
        "openai-agents", "openai_agents", "agents", None,
        'pip install "async-rbench[track-b-openai]"',
    ),
    "deterministic": FrameworkSpec(
        "deterministic", "deterministic", None, None, "", public=False,
    ),
}


def public_frameworks() -> tuple[str, ...]:
    return tuple(spec.name for spec in FRAMEWORKS.values() if spec.public)


def get_framework(name: str) -> FrameworkSpec:
    try:
        return FRAMEWORKS[name]
    except KeyError as exc:
        raise ValueError(f"unknown Track B framework: {name!r}") from exc


def doctor_framework(name: str, config: TrackBConfig) -> DoctorReport:
    spec = get_framework(name)
    dependency_present = spec.dependency is None or importlib.util.find_spec(spec.dependency) is not None
    executable_present = spec.executable is None or shutil.which(spec.executable) is not None
    if name == "claude-code":
        runtime_present = dependency_present or executable_present
    else:
        runtime_present = dependency_present and executable_present
    credential_detail = f"credential environment variable {config.credential_env}"
    if name == "codex-cli":
        credential_present = False
        if config.credential_env:
            credential_detail = "codex-cli uses saved ChatGPT login; credential_env must be empty"
        elif executable_present:
            from .codex_cli import check_cli_login

            credential_present, credential_detail = check_cli_login()
        else:
            credential_detail = "saved ChatGPT login (Codex CLI unavailable)"
    else:
        credential_present = not config.credential_env or bool(os.getenv(config.credential_env))
    ready = runtime_present and credential_present
    missing: list[str] = []
    if not runtime_present:
        missing.append("runtime dependency")
    if not credential_present:
        missing.append(credential_detail)
    detail = "ready" if ready else "missing " + " and ".join(missing)
    if ready and name == "codex-cli":
        detail += f"; {credential_detail}"
    return DoctorReport(
        framework=name,
        ready=ready,
        dependency_present=dependency_present,
        executable_present=executable_present,
        credential_present=credential_present,
        install_hint=spec.install_extra if not runtime_present else "",
        detail=detail,
    )


def build_runtime(config: TrackBConfig) -> AgentRuntime:
    spec = get_framework(config.framework)
    module = importlib.import_module(f"{__package__}.{spec.module}")
    runtime = module.build_runtime(config)
    if not isinstance(runtime, AgentRuntime):
        raise ValueError(f"framework {config.framework!r} returned an invalid AgentRuntime")
    return runtime
