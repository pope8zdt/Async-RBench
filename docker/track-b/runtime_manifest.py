"""Record installed dependency and CLI versions without reading authentication."""
from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if platform.system() != "Linux" or sys.version_info[:2] != (3, 12):
        raise RuntimeError("Track B images require Linux and Python 3.12")
    framework = sys.argv[1]
    manifest = {
        "framework": framework,
        "platform": "linux/" + platform.machine(),
        "python": platform.python_version(),
        "packages": dict(sorted(
            (item.metadata["Name"], item.version)
            for item in importlib.metadata.distributions()
        )),
        "cli_versions": {},
    }
    if framework in {"codex-cli", "claude-code"}:
        executable = "codex" if framework == "codex-cli" else "claude"
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, check=True, timeout=30,
        )
        manifest["cli_versions"][executable] = result.stdout.strip()
    Path("/opt/async-rbench-runtime.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )


if __name__ == "__main__":
    main()
