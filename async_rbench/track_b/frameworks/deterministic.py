from __future__ import annotations

from ..config import TrackBConfig
from ..contracts import FrameworkRequest, FrameworkResult, HarnessAction


class DeterministicRuntime:
    """No-model runtime for protocol and packaging validation only."""

    def __init__(self, config: TrackBConfig) -> None:
        self.config = config

    async def run(self, request: FrameworkRequest) -> FrameworkResult:
        return FrameworkResult(
            output_text="Track B deterministic validation complete",
            actions=(HarnessAction("finish", {"declared_task_success": False}),),
            usage={"input_tokens": 0, "output_tokens": 0},
            status="completed",
        )


def build_runtime(config: TrackBConfig) -> DeterministicRuntime:
    return DeterministicRuntime(config)
