from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable

from ..evaluation.protocol import CAPABILITY_REQUEST
from ..evaluation.workspace_runtime import CommandResult, WorkspaceRuntime


def _decode_result(result: Any) -> Any:
    """Rehydrate a ``CommandResult`` the kernel encoded as a plain two-key dict."""
    if isinstance(result, dict) and set(result) == {"exit_code", "output"}:
        return CommandResult(int(result["exit_code"]), str(result["output"]))
    return result


class CapabilityRuntimeProxy(WorkspaceRuntime):
    """Adapter-side stand-in for ``WorkspaceRuntime``.

    Each method forwards to the kernel process over the stdio capability RPC
    channel instead of importing Docker locally. The kernel owns the real
    ``DockerWorkspaceRuntime``/``DisabledWorkspaceRuntime``; the proxy only
    serialises the call, awaits the matching ``capability_response``, and
    decodes the result. It never touches ``subprocess`` or ``docker``.
    """

    def __init__(
        self,
        write: Callable[[dict[str, Any]], None],
        *,
        timeout: float = 600.0,
    ) -> None:
        self._write = write
        self._timeout = timeout
        self._pending: dict[str, asyncio.Future[Any]] = {}

    def handle_response(self, message: dict[str, Any]) -> None:
        """Resolve the pending request a ``capability_response`` belongs to.

        Invoked from the gateway reader thread via ``call_soon_threadsafe``, so
        it runs on the event loop and may set results directly.
        """
        request_id = message.get("request_id")
        future = self._pending.pop(request_id, None)
        if future is None or future.done():
            return
        if message.get("ok"):
            future.set_result(_decode_result(message.get("result")))
        else:
            future.set_exception(
                RuntimeError(str(message.get("error") or "unknown capability error"))
            )

    async def _request(self, capability: str, **args: Any) -> Any:
        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[request_id] = future
        self._write({
            "type": CAPABILITY_REQUEST,
            "request_id": request_id,
            "capability": capability,
            "args": args,
        })
        try:
            return await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise RuntimeError(f"capability {capability!r} timed out after {self._timeout}s") from None

    async def create_child(self, child_id: str) -> str:
        return await self._request("create_child", child_id=child_id)

    async def main_terminal(self, command: str, timeout: int) -> CommandResult:
        return await self._request("main_terminal", command=command, timeout=timeout)

    async def child_terminal(self, child_id: str, command: str, timeout: int) -> CommandResult:
        return await self._request("child_terminal", child_id=child_id, command=command, timeout=timeout)

    async def promote(self, child_id: str, source_path: str, destination_path: str) -> CommandResult:
        return await self._request("promote", child_id=child_id, source_path=source_path, destination_path=destination_path)

    async def observe_artifact(self, artifact_id: str) -> dict[str, str]:
        return await self._request("observe_artifact", artifact_id=artifact_id)

    async def verify_current_state(
        self, artifact_ids: list[str], lineage_completion_ids: list[str],
    ) -> dict[str, object]:
        return await self._request(
            "verify_current_state",
            artifact_ids=artifact_ids,
            lineage_completion_ids=lineage_completion_ids,
        )

    async def prepare_result_presentation(
        self, delivery_occurrence_id: str, *, turn_id: str,
    ) -> dict[str, object]:
        """Ask the kernel to authorize presenting one delivery occurrence.

        The evaluator generates the before-presentation snapshot ``S_i^-`` and
        records the kernel-private ``presentation_prepared`` boundary. The
        adapter must only mark the occurrence presented after this returns
        ``prepared`` true (spec §3.3, §5.1(4)).
        """
        return await self._request(
            "prepare_result_presentation",
            delivery_occurrence_id=delivery_occurrence_id,
            turn_id=turn_id,
        )

    async def observe_main_state(
        self, reason: str, *, action_id: str, turn_id: str,
    ) -> dict[str, object]:
        """Ask the kernel to observe the main workspace after a tool completes.

        The kernel runs the post-tool provisional observer and records the
        kernel-private ``provisional_observed`` fact (spec §4.2). The adapter
        fires this after a modifying tool has *finished*, never before it runs.
        """
        return await self._request(
            "observe_main_state",
            reason=reason,
            action_id=action_id,
            turn_id=turn_id,
        )

    async def cleanup_child(self, child_id: str) -> None:
        await self._request("cleanup_child", child_id=child_id)

    async def cleanup(self) -> None:
        await self._request("cleanup")
