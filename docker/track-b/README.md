# Track B Linux runtimes

Build from the repository root with Python 3.9 or newer:

```powershell
python docker/track-b/build.py all
python docker/track-b/smoke.py all
```

The `codex`, `claude`, `langgraph`, and `openai` Dockerfile targets install the
adapter under `/opt/venv`, set Linux bash and `HOME=/home/agent`, and default to
UID/GID `1000:1000`. The entry point is
`python -m async_rbench.track_b.container_entry`. The Track B launcher supplies
the read-only root and writable home and `/tmp` tmpfs mounts; images themselves
cannot enforce those Docker launch options. No host paths or Docker socket are
needed by an agent image.

The builder sends a fresh tar containing only `pyproject.toml`, Python source
under `async_rbench/`, the public protocol dependency `event_taxonomy.json`, and
explicitly named Docker build files. It rejects
symlinks/junctions and excludes caches, case data, artifacts, Git state, and
credentials. Use `--context-only context.tar` to audit that exact allowlist before
building. Do not invoke Docker with the repository root as its build context.

Builds run sequentially. The default legacy builder supports a 0.5 CPU/768 MB
limit per build step (`--build-cpus`, `--build-memory`). On Docker releases without
that builder, `--builder default` uses the current builder and reports when its
CLI has no per-build CPU/memory controls. This does not change daemon settings,
restart containers, or prune images. `--tag-suffix=-my-run` keeps a new set of
named images. The builder prints each immutable image ID; use that ID for
measurement configurations.

Python 3.12.12 uses the pinned Linux amd64 Docker Official Image digest. If Docker
Hub is unavailable, its identical official AWS ECR mirror can be selected:

```powershell
python docker/track-b/build.py all --python-image public.ecr.aws/docker/library/python@sha256:2986c55feb36e6cae00fa1fefb454283e4b33f35e75ff8bdd123b134130be301
```

Codex CLI 0.153.4 is downloaded from its exact official GitHub release and
checked against the published archive SHA256. Claude Agent SDK 0.2.152 includes
its own Claude Code binary, exposed as `claude`. LangGraph includes the pinned
LangChain OpenAI provider. `/opt/async-rbench-runtime.json` records every installed
Python package and CLI version. The offline smoke check verifies imports, help,
UID/GID, read-only installed code, writable tmpfs paths, and Codex's exact bundled
`gpt-5.6-luna` entry. It runs without networking or credentials and does not prove
provider access or model performance.

Sources: [Codex release 0.153.4](https://github.com/openai/codex/releases/tag/rust-v0.153.4),
[Claude Agent SDK 0.2.152](https://pypi.org/project/claude-agent-sdk/0.2.152/),
[LangGraph 1.2.11](https://pypi.org/project/langgraph/1.2.11/),
[LangChain 1.4.0](https://pypi.org/project/langchain/1.4.0/),
[LangChain OpenAI 1.6.0](https://pypi.org/project/langchain-openai/1.6.0/),
[OpenAI Agents 0.22.0](https://pypi.org/project/openai-agents/0.22.0/).

## Custom harness packages

Create a separate minimal directory containing only the custom package wheel,
its pinned dependency requirements, and this derived Dockerfile:

```dockerfile
FROM async-rbench-track-b:openai
USER 0:0
COPY my_harness-1.0.0-py3-none-any.whl requirements.lock /opt/custom/
RUN pip install --only-binary=:all: -r /opt/custom/requirements.lock \
    && pip install --no-deps /opt/custom/my_harness-1.0.0-py3-none-any.whl \
    && python /opt/build/runtime_manifest.py openai-agents \
    && chmod -R a-w /opt/venv
USER 1000:1000
```

Pin the parent by immutable image ID for recorded runs. Build the derived image
from that minimal directory, select the installed custom module in the Track B
configuration, and record the resulting image ID. Do not add credentials, task
cases, local configuration, or evaluator inputs to the derived image.
