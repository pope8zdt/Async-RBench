"""Connectivity probe for external OpenAI-compatible providers through Codex CLI."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def credentials() -> list[tuple[str, str, str, str, str]]:
    lines = (ROOT / "APIKey.txt").read_text(encoding="utf-8-sig").splitlines()
    qwen = json.loads(lines[0][lines[0].index("{"):])
    deepseek = lines[1].split("=", 1)[1].strip()
    return [
        ("deepseek-v4-flash", "deepseek", "https://api.deepseek.com", "DTBENCH_DS_KEY", deepseek),
        ("qwen3-coder-480b-a35b-instruct", "qwen", str(qwen["url"]).rstrip("/") + "/v1", "DTBENCH_QWEN_KEY", str(qwen["key"])),
    ]


for model, provider, base_url, env_key, key in credentials():
    environment = os.environ.copy()
    environment[env_key] = key
    command = [
        "codex", "exec", "--json", "--ephemeral", "--ignore-user-config",
        "--skip-git-repo-check", "--sandbox", "read-only", "--model", model,
        "-c", f'model_provider="{provider}"',
        "-c", f'model_providers.{provider}.name="{provider}"',
        "-c", f'model_providers.{provider}.base_url="{base_url}"',
        "-c", f'model_providers.{provider}.env_key="{env_key}"',
        "-c", f'model_providers.{provider}.wire_api="responses"',
        "Reply with exactly OK.",
    ]
    result = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120, check=False,
    )
    print(json.dumps({
        "model": model,
        "exit_code": result.returncode,
        "stdout_tail": result.stdout[-1000:],
        "stderr_tail": result.stderr[-1000:],
    }, ensure_ascii=True))
