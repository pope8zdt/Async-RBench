"""Sequential, network-disabled runtime checks; no credentials or model calls."""
from __future__ import annotations

import argparse
import json
import subprocess
import uuid

TARGETS = ("codex", "claude", "langgraph", "openai")
CHECK = r'''
import errno, importlib.metadata, json, os, pathlib, platform, subprocess, sys
target = sys.argv[1]
assert os.getuid() == 1000 and os.getgid() == 1000
assert os.environ['HOME'] == '/home/agent'
assert platform.system() == 'Linux' and sys.version_info[:2] == (3, 12)
assert os.environ['SHELL'] == '/bin/bash'
subprocess.run(['bash', '--version'], check=True, stdout=subprocess.DEVNULL, timeout=30)
for directory in ('/home/agent', '/tmp'):
    probe = pathlib.Path(directory) / 'track-b-smoke-write'
    probe.write_text('writable')
    probe.unlink()
import async_rbench.track_b.container_entry as entry
assert str(pathlib.Path(entry.__file__).resolve()).startswith('/opt/')
try:
    pathlib.Path(entry.__file__).open('a').close()
except OSError as error:
    assert error.errno in (errno.EROFS, errno.EACCES)
else:
    raise AssertionError('installed adapter is writable')
subprocess.run(['python', '-m', 'async_rbench.track_b.adapter', '--help'], check=True, stdout=subprocess.DEVNULL, timeout=30)
subprocess.run(['python', '-m', 'async_rbench.track_b', '--help'], check=True, stdout=subprocess.DEVNULL, timeout=30)
subprocess.run(['pip', 'check'], check=True, stdout=subprocess.DEVNULL, timeout=30)
manifest = json.loads(pathlib.Path('/opt/async-rbench-runtime.json').read_text())
framework = manifest['framework']
config_path = pathlib.Path('/tmp/track-b-offline-smoke.json')
config_path.write_text(json.dumps({
    'track': 'B', 'framework': framework, 'model': 'gpt-5.6-luna' if target == 'codex' else 'offline-smoke',
    'credential_env': '' if target == 'codex' else 'TRACK_B_OFFLINE_SMOKE_CREDENTIAL',
}))
doctor = subprocess.run(['python', '-m', 'async_rbench.track_b', 'doctor', '--config', str(config_path)], capture_output=True, text=True, timeout=30)
report = json.loads(doctor.stdout)
assert doctor.returncode == 1 and not report['ready'] and not report['credential_present']
assert report['dependency_present'] and report['executable_present']
manifest['doctor'] = 'runtime-present; credentials-absent-as-expected'
if target == 'codex':
    import jsonschema
    subprocess.run(['codex', '--help'], check=True, stdout=subprocess.DEVNULL, timeout=30)
    models = json.loads(subprocess.check_output(['codex', 'debug', 'models', '--bundled'], text=True, timeout=30))
    assert sum(item.get('slug') == 'gpt-5.6-luna' for item in models['models']) == 1
    manifest['bundled_model'] = 'gpt-5.6-luna'
elif target == 'claude':
    from claude_agent_sdk import ClaudeAgentOptions, query
    help_text = subprocess.check_output(['claude', '--help'], text=True, timeout=30)
    for flag in ('--tools', '--setting-sources', '--strict-mcp-config', '--mcp-config', '--disable-slash-commands', '--no-session-persistence', '--permission-mode'):
        assert flag in help_text, flag
elif target == 'langgraph':
    from langgraph.graph import StateGraph
    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI
else:
    from agents import Agent, ModelSettings, Runner, OpenAIChatCompletionsModel, OpenAIResponsesModel, RunConfig
manifest['checks'] = ['imports', 'cli-help', 'doctor', 'pip-check', 'linux-python312', 'bash', 'uid-gid-1000', 'read-only-code', 'writable-tmpfs']
print(json.dumps(manifest, sort_keys=True))
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=(*TARGETS, "all"))
    parser.add_argument("--tag-prefix", default="async-rbench-track-b")
    parser.add_argument("--tag-suffix", default="")
    args = parser.parse_args()
    for target in TARGETS if args.target == "all" else (args.target,):
        image = f"{args.tag_prefix}:{target}{args.tag_suffix}"
        image_id = subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True, timeout=30,
        ).strip()
        image_config = json.loads(subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{json .Config}}", image_id], text=True, timeout=30,
        ))
        if image_config.get("User") != "1000:1000":
            raise RuntimeError("image must default to UID/GID 1000:1000")
        if image_config.get("Entrypoint") != ["python", "-m", "async_rbench.track_b.container_entry"]:
            raise RuntimeError("image must use the shared Track B container entry point")
        name = "async-rbench-track-b-smoke-" + uuid.uuid4().hex
        command = [
            "docker", "run", "--rm", "--interactive", "--name", name,
            "--label", "org.async-rbench.track-b.purpose=smoke", "--network", "none",
            "--read-only", "--user", "1000:1000", "--cpus", "0.5", "--memory", "768m",
            "--memory-swap", "768m", "--pids-limit", "64", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--tmpfs", "/home/agent:rw,nosuid,nodev,size=64m,uid=1000,gid=1000,mode=700",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m,mode=1777",
            "--entrypoint", "python", image_id, "-", target,
        ]
        try:
            result = subprocess.run(
                command, input=CHECK, capture_output=True, text=True, timeout=120, check=True,
            )
            report = json.loads(result.stdout)
            if image_config.get("Labels", {}).get("org.async-rbench.track-b.framework") != report["framework"]:
                raise RuntimeError("framework label does not match installed runtime manifest")
            report.update(image=image, image_id=image_id)
            print(json.dumps(report, sort_keys=True), flush=True)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"{target} smoke failed: {error.stderr.strip()}") from error
        finally:
            subprocess.run(
                ["docker", "rm", "--force", name], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=30, check=False,
            )


if __name__ == "__main__":
    main()
