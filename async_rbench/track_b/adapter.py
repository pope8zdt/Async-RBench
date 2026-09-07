from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..evaluation.case_contract import assert_participant_safe
from ..evaluation.model_backend import ModelTurn, ToolCall
from ..profiles.conformance_mock.scripted_backend import ScriptedTestBackend
from ..profiles.reference_scaffold_api.config import ScaffoldConfig
from ..profiles.reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from ..profiles.reference_scaffold_api.runtime import ReferenceScaffold
from ..protocol_sdk.capability import CapabilityRuntimeProxy
from .components import load_component
from .config import TrackBConfig
from .contracts import (
    AgentPolicy,
    AgentRuntime,
    ContextBuilder,
    DelegationPolicy,
    FrameworkRequest,
    LifecycleHooks,
    ModelBackend,
    PublicEpisodeContext,
)
from .frameworks import build_runtime


LOGGER = logging.getLogger("async_rbench.track_b")


_COMPONENT_PROTOCOLS: dict[str, type[Any]] = {
    "context_builder": ContextBuilder,
    "delegation_policy": DelegationPolicy,
    "agent_policy": AgentPolicy,
    "lifecycle_hooks": LifecycleHooks,
    "model_backend": ModelBackend,
}


def build_public_context(start: dict[str, Any]) -> PublicEpisodeContext:
    assert_participant_safe(start, surface="Track B public context")
    return PublicEpisodeContext(
        instruction=str(start.get("instruction") or ""),
        episode_id=str(start.get("episode_id") or ""),
        execution_mode=str(start.get("execution_mode") or ""),
        workstreams=tuple(start.get("workstreams") or ()),
    )


def validate_custom_components(config: TrackBConfig) -> dict[str, Any]:
    return {
        name: load_component(spec, _COMPONENT_PROTOCOLS[name])
        for name, spec in config.components.items()
    }


class FrameworkModelBackend:
    """Translate a Track B framework turn into the frozen scaffold model shape."""

    def __init__(self, config: TrackBConfig, runtime: AgentRuntime) -> None:
        self.config = config
        self.runtime = runtime
        self._observations: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        seed: int,
    ) -> ModelTurn:
        request = FrameworkRequest(
            messages=tuple(messages),
            tools=tuple(tools),
            metadata={"role": role, "model": model, "seed": seed},
        )
        assert_participant_safe(
            {"messages": request.messages, "tools": request.tools},
            surface="Track B framework request",
        )
        result = await self.runtime.run(request)
        tool_calls = [
            ToolCall(
                id=f"track-b-{role}-{index}",
                name=action.kind,
                arguments=dict(action.arguments),
            )
            for index, action in enumerate(result.actions, start=1)
        ]
        assistant_tool_calls = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in tool_calls
        ]
        total_tokens = sum(int(value) for value in result.usage.values())
        self._observations.append({
            "role": role,
            "requested_model": model,
            "resolved_model": self.config.model,
            "tokens": total_tokens,
        })
        return ModelTurn(
            assistant_message={
                "role": "assistant",
                "content": result.output_text,
                "tool_calls": assistant_tool_calls,
            },
            tool_calls=tool_calls,
            total_tokens=total_tokens,
            resolved_model=self.config.model,
        )

    def runtime_metadata(self) -> dict[str, Any]:
        return {"model_observations": list(self._observations)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Async-RBench Track B adapter")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--conformance", action="store_true")
    parser.add_argument(
        "--workspace-mode",
        choices=["container_clone", "disabled"],
        default="container_clone",
    )
    return parser


async def run_adapter(args: argparse.Namespace) -> int:
    start = DeliveryReader.receive_start()
    track_config = TrackBConfig.from_file(args.config)
    build_public_context(start)
    validate_custom_components(track_config)

    emitter = ProtocolEmitter()
    reader = DeliveryReader()
    workspace = CapabilityRuntimeProxy(emitter.write)
    reader.set_capability_handler(workspace.handle_response)
    reader.start()

    scaffold_config = ScaffoldConfig.from_file(None, {
        "backend": "scripted_test",
        "main_model": track_config.model,
        "child_model": track_config.model,
        "workspace_mode": args.workspace_mode,
        **{
            key: value
            for key, value in track_config.limits.items()
            if key in {
                "max_main_steps", "max_child_steps", "max_concurrent_children",
                "max_total_child_spawns", "request_timeout_sec",
            }
        },
    })
    if args.conformance:
        main_backend = ScriptedTestBackend()
        child_backend = ScriptedTestBackend()
    else:
        main_backend = FrameworkModelBackend(track_config, build_runtime(track_config))
        child_backend = FrameworkModelBackend(track_config, build_runtime(track_config))
    scaffold = ReferenceScaffold(
        start=start,
        config=scaffold_config,
        main_backend=main_backend,
        child_backend=child_backend,
        workspace=workspace,
        emitter=emitter,
        delivery_reader=reader,
    )
    emitter.emit(
        "participant_metadata",
        **track_config.public_metadata(),
        scaffold="async-rbench-track-b",
        development_only=True,
    )
    emitter.emit("ready")
    try:
        await scaffold.run()
    except Exception as exc:
        LOGGER.exception("Track B adapter failed")
        emitter.emit(
            "infrastructure_failure",
            component="adapter_crash",
            detail=f"Track B adapter failure: {exc}",
        )
        scaffold.finish_status = "incomplete"
        scaffold.final_summary = f"Track B adapter failure: {exc}"
    finally:
        await scaffold.shutdown()

    observations: list[dict[str, Any]] = []
    for backend in (main_backend, child_backend):
        metadata = getattr(backend, "runtime_metadata", lambda: {})() or {}
        observations.extend(metadata.get("model_observations") or [])
    emitter.emit("participant_runtime_metadata", model_observations=observations)
    emitter.emit(
        "episode_ended",
        final_answer=scaffold.final_summary,
        local_status=scaffold.finish_status,
        declared_task_success=scaffold.finish_status == "completed",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(run_adapter(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
