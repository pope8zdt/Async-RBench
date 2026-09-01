from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from ..evaluation.protocol import validate_adapter_event


def configure_utf8_stdio() -> None:
    """Force UTF-8 on stdio so non-ASCII payloads survive direct adapter launches.

    The benchmark runner already configures a UTF-8 subprocess environment, but a
    participant that launches their own adapter outside the runner (notably on
    Windows CP936) needs this defense-in-depth. Never leaves stdout non-JSON.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="strict")
        except Exception:
            # Best effort: a stream that cannot be reconfigured keeps its default.
            pass


class JsonlGateway:
    """Synchronous SDK for instrumenting an existing agent-system adapter.

    Every helper emits an event that already passes ``validate_adapter_event``;
    ``emit`` validates before writing so a malformed event fails at the call site
    instead of reaching the kernel as a protocol violation.
    """

    def __init__(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout

    def receive(self) -> dict[str, Any]:
        line = self.stdin.readline()
        if not line:
            raise EOFError("Async-RBench gateway closed")
        return json.loads(line)

    def emit(self, event_type: str, **fields: Any) -> None:
        event = {"type": event_type, **fields}
        validate_adapter_event(event)
        self.stdout.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        self.stdout.flush()

    def child_spawned(self, child_id: str, work_units: list[str]) -> None:
        self.emit("child_spawned", child_id=child_id, parent_id="main", work_units=work_units)

    def child_started(self, child_id: str) -> None:
        self.emit("child_started", child_id=child_id)

    def child_progress_checkpoint(self, child_id: str, tokens: int) -> None:
        self.emit(
            "child_progress_checkpoint", child_id=child_id,
            phase="first_model_turn_finished", tokens=tokens,
        )

    def child_completed(self, child_id: str, completion_id: str,
                        payload: Any, tokens: int = 0) -> None:
        # Keep payload hidden from the main agent until result_delivered is received.
        self.emit("child_completed", child_id=child_id, completion_id=completion_id,
                  payload=payload, usage={"tokens": tokens})

    def receive_delivery(self) -> dict[str, Any]:
        message = self.receive_result_outcome()
        if message.get("type") != "result_delivered":
            raise ValueError(
                "completion was rejected by the evaluator-owned result contract: "
                f"{message.get('reason_codes', [])!r}"
            )
        return message

    def receive_result_outcome(self) -> dict[str, Any]:
        message = self.receive()
        if message.get("type") not in {"result_delivered", "result_rejected"}:
            raise ValueError(
                f"expected result_delivered or result_rejected, got {message.get('type')!r}"
            )
        return message

    def main_action(self, action_id: str, kind: str, **metadata: Any) -> None:
        self.emit("main_action", action_id=action_id, kind=kind, **metadata)

    def child_path_promotion_result(
        self, action_id: str, completion_id: str, child_id: str | None,
        source_path: str, destination_path: str, success: bool,
        exit_code: int | None, failure_detail: str = "",
    ) -> None:
        self.emit(
            "child_path_promotion_result",
            action_id=action_id,
            completion_id=completion_id,
            child_id=child_id,
            source_path=source_path,
            destination_path=destination_path,
            success=success,
            exit_code=exit_code,
            failure_detail=failure_detail,
        )

    def result_consumed(self, completion_id: str, action_id: str) -> None:
        self.emit("result_consumed", completion_id=completion_id, action_id=action_id)

    def artifact_committed(self, artifact_id: str, version: str,
                           lineage_completion_ids: list[str],
                           observed_digest: str, observed_path: str = "",
                           final: bool = False) -> None:
        # The commit must be evaluator-observed: the caller supplies the SHA-256
        # of the observed artifact and its observed path.
        self.emit("artifact_committed", artifact_id=artifact_id, version=version,
                  lineage_completion_ids=lineage_completion_ids,
                  observed_digest=observed_digest, observed_path=observed_path,
                  evaluator_observed=True, final=final)
