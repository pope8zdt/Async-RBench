"""Inspect an installed CLI's real request without contacting any model service."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from async_rbench.track_b.config import TrackBConfig
from async_rbench.track_b.contracts import FrameworkRequest
from async_rbench.track_b.frameworks import codex_cli
from async_rbench.track_b.frameworks.common import render_protocol_prompt


def _advertised_tools(payload: dict[str, Any]) -> list[dict[str, Any]]:
    # Current Codex places tools in input.additional_tools, not top-level tools.
    pending = list(payload.get("tools", []))
    for item in payload.get("input", []):
        if item.get("type") == "additional_tools":
            pending.extend(item.get("tools", []))
    leaves = []
    while pending:
        item = pending.pop()
        if item.get("type") == "namespace":
            pending.extend(item.get("tools", []))
        else:
            leaves.append(item)
    return leaves


def _context_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _context_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _context_strings(child)


def test_installed_codex_advertises_no_host_tools_or_private_context(monkeypatch):
    executable = shutil.which("codex")
    if executable is None:
        pytest.skip("Codex CLI is not installed; this test requires the real executable")

    model = "gpt-5.6-luna"
    catalog = codex_cli.load_model_catalog(executable, model)
    request = FrameworkRequest(
        messages=({"role": "user", "content": "Select a benchmark terminal action."},),
        tools=({"type": "function", "function": {
            "name": "terminal", "parameters": {
                "type": "object", "properties": {"command": {"type": "string"}},
                "required": ["command"], "additionalProperties": False,
            },
        }},),
    )
    final_text = json.dumps({"output_text": "Inspect the benchmark workspace", "actions": [
        {"kind": "terminal", "arguments": {"command": "pwd"}},
    ]})
    captures: list[dict[str, Any]] = []
    paths: list[str] = []
    authorization_present: list[bool] = []

    class CaptureHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            paths.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(catalog).encode())

        def do_POST(self):
            paths.append(self.path)
            authorization_present.append("Authorization" in self.headers)
            body = self.rfile.read(int(self.headers["Content-Length"]))
            captures.append(json.loads(body))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            message = {
                "id": "msg_isolation_fixture", "type": "message", "status": "completed",
                "role": "assistant", "content": [
                    {"type": "output_text", "text": final_text, "annotations": []},
                ],
            }
            events = [
                {"type": "response.output_item.done", "output_index": 0, "item": message},
                {"type": "response.completed", "response": {
                    "id": "resp_isolation_fixture", "status": "completed", "output": [message],
                    "usage": {"input_tokens": 13, "output_tokens": 7, "total_tokens": 20},
                }},
            ]
            for event in events:
                self.wfile.write(("event: " + event["type"] + "\ndata: "
                                 + json.dumps(event) + "\n\n").encode())
            self.wfile.flush()

    # Synthetic secrets detect unintended inheritance without reading real values.
    monkeypatch.setenv("OPENAI_API_KEY", "isolation-secret-sentinel")
    monkeypatch.setenv("CODEX_APP_TOOLS_PIPE_PATH", "isolation-app-pipe-sentinel")
    server = HTTPServer(("127.0.0.1", 0), CaptureHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix="track-b-cli-isolation-") as temp:
            directory = Path(temp)
            (directory / "instructions.txt").write_text(codex_cli.MODEL_INSTRUCTIONS, encoding="utf-8")
            (directory / "model-catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
            (directory / "response-schema.json").write_text(
                json.dumps(codex_cli.response_schema(request)), encoding="utf-8",
            )
            config = TrackBConfig(track="B", framework="codex-cli", model=model)
            args = codex_cli.build_command(config, directory, executable=executable)
            # The test alone replaces transport. Production retains official saved login.
            provider = (
                'model_providers.isolation_capture={name="Local isolation capture",'
                f'base_url="http://127.0.0.1:{server.server_port}/v1",'
                'wire_api="responses",requires_openai_auth=false}'
            )
            args[-1:-1] = ["-c", 'model_provider="isolation_capture"', "-c", provider]
            environment = codex_cli.child_environment()
            for key in list(environment):
                if key.upper().endswith("_PROXY"):
                    del environment[key]
            environment["NO_PROXY"] = "127.0.0.1,localhost"
            result = subprocess.run(
                args, cwd=directory, env=environment,
                input=render_protocol_prompt(request).encode(), capture_output=True, timeout=45,
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
            )
            assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
            decoded = codex_cli.decode_codex_result(
                result.stdout, (directory / "final.json").read_text(encoding="utf-8"), request,
            )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)

    assert len(captures) == 1
    assert authorization_present == [False]
    assert all(path.startswith(("/v1/responses", "/v1/models")) for path in paths)
    payload = captures[0]
    assert payload["model"] == model
    output_format = payload["text"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["strict"] is True
    assert output_format["schema"] == codex_cli.response_schema(request)

    # Inspect every advertised leaf, including native discovery and the passive
    # question tool: an empty top-level tools field alone is insufficient.
    advertised = _advertised_tools(payload)
    assert advertised == []
    # Compare decoded strings so Windows path backslashes are not JSON-escaped.
    context = "\n".join(_context_strings(payload))
    root = Path(__file__).resolve().parents[1]
    for forbidden in (
        str(root), root.as_posix(), "formal-47", "evaluator", "<skills_instructions>",
        "### Available skills", "AGENTS.md", "isolation-secret-sentinel", "isolation-app-pipe-sentinel",
    ):
        assert forbidden not in context
    assert codex_cli.MODEL_INSTRUCTIONS in context
    assert decoded.actions[0].kind == "terminal"
    assert decoded.actions[0].arguments == {"command": "pwd"}
    assert decoded.usage == {"input_tokens": 13, "output_tokens": 7}
