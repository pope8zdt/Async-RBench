from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class HarnessAction:
    kind: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FrameworkRequest:
    messages: tuple[Mapping[str, Any], ...]
    tools: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FrameworkResult:
    output_text: str = ""
    actions: tuple[HarnessAction, ...] = ()
    usage: Mapping[str, int] = field(default_factory=dict)
    status: str = "completed"


@dataclass(frozen=True)
class PublicEpisodeContext:
    instruction: str
    episode_id: str = ""
    execution_mode: str = ""
    workstreams: tuple[Mapping[str, Any], ...] = ()
    deliveries: tuple[Mapping[str, Any], ...] = ()
    prior_actions: tuple[Mapping[str, Any], ...] = ()
    capability_results: tuple[Mapping[str, Any], ...] = ()
    messages: tuple[Mapping[str, Any], ...] = ()
    tools: tuple[Mapping[str, Any], ...] = ()


@runtime_checkable
class AgentRuntime(Protocol):
    async def run(self, request: FrameworkRequest) -> FrameworkResult: ...


@runtime_checkable
class ModelBackend(Protocol):
    async def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> FrameworkResult: ...


@runtime_checkable
class ContextBuilder(Protocol):
    def build(self, context: PublicEpisodeContext) -> FrameworkRequest: ...


@runtime_checkable
class DelegationPolicy(Protocol):
    def initial_actions(self, context: PublicEpisodeContext) -> tuple[HarnessAction, ...]: ...


@runtime_checkable
class AgentPolicy(Protocol):
    def select_actions(
        self,
        context: PublicEpisodeContext,
        result: FrameworkResult,
    ) -> tuple[HarnessAction, ...]: ...


@runtime_checkable
class LifecycleHooks(Protocol):
    def on_event(self, event: Mapping[str, Any]) -> None: ...
