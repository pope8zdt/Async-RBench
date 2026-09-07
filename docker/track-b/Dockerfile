ARG PYTHON_IMAGE=python:3.12.12-slim-bookworm@sha256:2986c55feb36e6cae00fa1fefb454283e4b33f35e75ff8bdd123b134130be301
FROM ${PYTHON_IMAGE} AS base
ENV HOME=/home/agent \
    SHELL=/bin/bash \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN groupadd --gid 1000 agent && useradd --uid 1000 --gid 1000 --shell /bin/bash --home-dir /home/agent --create-home agent \
    && python -m venv /opt/venv
COPY docker/track-b/requirements-base.lock /opt/build/requirements-base.lock
RUN pip install --no-deps --only-binary=:all: -r /opt/build/requirements-base.lock
COPY docker/track-b/requirements-*.lock /opt/build/
COPY docker/track-b/install_codex.py docker/track-b/runtime_manifest.py /opt/build/
WORKDIR /home/agent
ENTRYPOINT ["python", "-m", "async_rbench.track_b.container_entry"]

# The source-only wheel is rebuilt when the local adapter changes. No repository
# root, cases, evaluator inputs, credentials, or local configuration are copied.
FROM base AS package
COPY pyproject.toml /opt/source/pyproject.toml
COPY async_rbench /opt/source/async_rbench
RUN pip wheel --no-deps --no-build-isolation --wheel-dir /opt/wheels /opt/source

FROM base AS codex-deps
RUN pip install --no-deps --only-binary=:all: -r /opt/build/requirements-codex.lock \
    && python /opt/build/install_codex.py \
    && codex --version
FROM codex-deps AS codex
LABEL org.async-rbench.track-b.framework="codex-cli"
COPY --from=package /opt/wheels /opt/wheels
COPY event_taxonomy.json /opt/venv/lib/python3.12/site-packages/event_taxonomy.json
RUN pip install --no-deps /opt/wheels/*.whl \
    && python /opt/build/runtime_manifest.py codex-cli
USER 1000:1000

FROM base AS claude-deps
RUN pip install --no-deps --only-binary=:all: -r /opt/build/requirements-claude.lock \
    && python -c "from pathlib import Path; import claude_agent_sdk; p=Path(claude_agent_sdk.__file__).parent/'_bundled'/'claude'; assert p.is_file(); Path('/opt/venv/bin/claude').symlink_to(p)" \
    && claude --version
FROM claude-deps AS claude
LABEL org.async-rbench.track-b.framework="claude-code"
COPY --from=package /opt/wheels /opt/wheels
COPY event_taxonomy.json /opt/venv/lib/python3.12/site-packages/event_taxonomy.json
RUN pip install --no-deps /opt/wheels/*.whl \
    && python /opt/build/runtime_manifest.py claude-code
USER 1000:1000

FROM base AS langgraph-deps
RUN pip install --no-deps --only-binary=:all: -r /opt/build/requirements-langgraph.lock
FROM langgraph-deps AS langgraph
LABEL org.async-rbench.track-b.framework="langgraph"
COPY --from=package /opt/wheels /opt/wheels
COPY event_taxonomy.json /opt/venv/lib/python3.12/site-packages/event_taxonomy.json
RUN pip install --no-deps /opt/wheels/*.whl \
    && python /opt/build/runtime_manifest.py langgraph
USER 1000:1000

FROM base AS openai-deps
RUN pip install --no-deps --only-binary=:all: -r /opt/build/requirements-openai.lock
FROM openai-deps AS openai
LABEL org.async-rbench.track-b.framework="openai-agents"
COPY --from=package /opt/wheels /opt/wheels
COPY event_taxonomy.json /opt/venv/lib/python3.12/site-packages/event_taxonomy.json
RUN pip install --no-deps /opt/wheels/*.whl \
    && python /opt/build/runtime_manifest.py openai-agents
USER 1000:1000
