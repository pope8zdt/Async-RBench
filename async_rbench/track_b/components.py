from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Mapping
from typing import TypeVar

from .config import TrackBConfig
from .contracts import (
    AgentPolicy,
    ContextBuilder,
    DelegationPolicy,
    FrameworkRequest,
    FrameworkResult,
    HarnessAction,
    LifecycleHooks,
    ModelBackend,
    PublicEpisodeContext,
)


T = TypeVar("T")


def load_component(spec: str, expected: type[T]) -> T:
    module_name, separator, factory_name = spec.partition(":")
    if (
        not separator
        or not module_name
        or module_name.startswith(".")
        or not factory_name
    ):
        raise ValueError("component entry point must be an absolute module:factory")
    module = importlib.import_module(module_name)
    factory = getattr(module, factory_name, None)
    if not callable(factory):
        raise ValueError(f"component factory is not callable: {spec}")
    component = factory()
    if not isinstance(component, expected):
        raise ValueError(f"component does not implement {expected.__name__}: {spec}")
    return component


class DefaultContextBuilder:
    def build(self, context: PublicEpisodeContext) -> FrameworkRequest:
        messages = context.messages or ({"role": "user", "content": context.instruction},)
        return FrameworkRequest(messages=messages, tools=context.tools)


class DefaultDelegationPolicy:
    def initial_actions(self, context: PublicEpisodeContext) -> tuple[HarnessAction, ...]:
        return ()


class DefaultAgentPolicy:
    def select_actions(
        self,
        context: PublicEpisodeContext,
        result: FrameworkResult,
    ) -> tuple[HarnessAction, ...]:
        return result.actions


class NullLifecycleHooks:
    def on_event(self, event: Mapping[str, Any]) -> None:
        return None


@dataclass(frozen=True)
class HarnessComponents:
    context_builder: ContextBuilder
    delegation_policy: DelegationPolicy
    agent_policy: AgentPolicy
    lifecycle_hooks: LifecycleHooks
    model_backend: ModelBackend | None = None


def resolve_components(config: TrackBConfig) -> HarnessComponents:
    defaults: dict[str, Any] = {
        "context_builder": DefaultContextBuilder(),
        "delegation_policy": DefaultDelegationPolicy(),
        "agent_policy": DefaultAgentPolicy(),
        "lifecycle_hooks": NullLifecycleHooks(),
        "model_backend": None,
    }
    protocols: dict[str, type[Any]] = {
        "context_builder": ContextBuilder,
        "delegation_policy": DelegationPolicy,
        "agent_policy": AgentPolicy,
        "lifecycle_hooks": LifecycleHooks,
        "model_backend": ModelBackend,
    }
    for name, spec in config.components.items():
        defaults[name] = load_component(spec, protocols[name])
    return HarnessComponents(**defaults)
