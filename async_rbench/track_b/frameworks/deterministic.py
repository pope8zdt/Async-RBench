from __future__ import annotations

from ..config import TrackBConfig
from ..contracts import FrameworkRequest, FrameworkResult, HarnessAction


class DeterministicRuntime:
    """No-model runtime for protocol and packaging validation only."""

    def __init__(self, config: TrackBConfig) -> None:
        self.config = config
        self._backend = None

    async def run(self, request: FrameworkRequest) -> FrameworkResult:
        if request.tools:
            from ...profiles.conformance_mock.scripted_backend import ScriptedTestBackend

            if self._backend is None:
                self._backend = ScriptedTestBackend()
            turn = await self._backend.complete(
                role=str(request.metadata.get("role") or "main"),
                model=str(request.metadata.get("model") or self.config.model),
                messages=[dict(item) for item in request.messages],
                tools=[dict(item) for item in request.tools],
                seed=int(request.metadata.get("seed") or 1),
            )
            return FrameworkResult(
                output_text=str(turn.assistant_message.get("content") or ""),
                actions=tuple(
                    HarnessAction(call.name, call.arguments) for call in turn.tool_calls
                ),
                usage={"total_tokens": int(turn.total_tokens)},
            )
        return FrameworkResult(
            output_text="Track B deterministic validation complete",
            actions=(HarnessAction("finish", {
                "status": "incomplete",
                "summary": "Track B deterministic validation complete",
            }),),
            usage={"input_tokens": 0, "output_tokens": 0},
            status="completed",
        )


def build_runtime(config: TrackBConfig) -> DeterministicRuntime:
    return DeterministicRuntime(config)
