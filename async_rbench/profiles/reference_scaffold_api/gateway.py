from __future__ import annotations

import asyncio
import json
import sys
import threading
from typing import Any, TextIO


class ProtocolEmitter:
    """Thread-safe JSONL event writer. Stdout remains protocol-only."""

    def __init__(self, stdout: TextIO | None = None) -> None:
        self.stdout = stdout or sys.stdout
        # Defense in depth for direct adapter launches that do not pass through
        # the benchmark runner's UTF-8 environment (notably Windows CP936).
        if stdout is None and hasattr(self.stdout, "reconfigure"):
            self.stdout.reconfigure(encoding="utf-8", errors="strict")
        self._lock = threading.Lock()
        # A capture run needs the exact child lifecycle/payload events so both
        # counterfactual branches can replay one immutable completion bundle.
        self.events: list[dict[str, Any]] = []

    def emit(self, event_type: str, **fields: Any) -> None:
        event = {"type": event_type, **fields}
        with self._lock:
            self.events.append(event)
            self._write_line(event)

    def write(self, message: dict[str, Any]) -> None:
        """Write a raw JSONL message (e.g. a capability request) to stdout.

        Unlike ``emit``, this does not append to the lifecycle event log and does
        not validate the message — capability requests are transport, not events.
        """
        with self._lock:
            self._write_line(message)

    def _write_line(self, message: dict[str, Any]) -> None:
        line = json.dumps(message, ensure_ascii=False, sort_keys=True)
        self.stdout.write(line + "\n")
        self.stdout.flush()


class DeliveryReader:
    """Reads gateway messages without blocking the agent event loop."""

    def __init__(self, stdin: TextIO | None = None) -> None:
        self.stdin = stdin or sys.stdin
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._capability_handler: Any = None

    @staticmethod
    def receive_start(stdin: TextIO | None = None) -> dict[str, Any]:
        stream = stdin or sys.stdin
        line = stream.readline()
        if not line:
            raise EOFError("Async-RBench gateway closed before episode_started")
        message = json.loads(line)
        if message.get("type") != "episode_started":
            raise ValueError(f"expected episode_started, got {message.get('type')!r}")
        return message

    def set_capability_handler(self, handler: Any) -> None:
        """Register the callback that resolves ``capability_response`` messages."""
        self._capability_handler = handler

    def start(self) -> None:
        if self._thread is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._thread = threading.Thread(target=self._read_loop, name="async_rbench-gateway-reader", daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        assert self._loop is not None
        for line in self.stdin:
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                message = {"type": "gateway_reader_error", "detail": str(exc), "raw": line[-2000:]}
            if (
                isinstance(message, dict)
                and message.get("type") == "capability_response"
                and self._capability_handler is not None
            ):
                self._loop.call_soon_threadsafe(self._capability_handler, message)
            else:
                self._loop.call_soon_threadsafe(self.queue.put_nowait, message)
        self._loop.call_soon_threadsafe(self.queue.put_nowait, {"type": "gateway_eof"})
