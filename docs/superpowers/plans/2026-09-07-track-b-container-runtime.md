# Track B Linux Agent Runtime Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement the independent tasks; run the tests below before claiming completion.

**Goal:** Run each maintained Track B framework and its custom harness components inside an isolated Linux agent container, preserving the v11 task execution and scoring contracts.

**Architecture:** Containerize the participant adapter, including its reference loop and custom components. The host kernel still owns task/child containers, capabilities, event delivery and verification. The adapter's existing JSONL protocol crosses the container boundary; no Docker socket, case tree, full repository, evaluator data or host configuration is mounted into the agent container.

**Tech Stack:** Python 3.12, Docker Linux containers, existing Track B JSONL protocol, framework-specific Python/CLI dependencies.

**Spec:** The user's approved container proposal in this conversation and `docs/superpowers/specs/2026-09-07-track-b-harness-design.md`.

## Global constraints

- Work only in `outputs/track-b-harness`, branch `codex/track-b-harness`.
- Preserve the running main experiment, existing manifests/results and frozen scoring; never prune/restart Docker or change daemon settings.
- Keep host execution available for existing configs; container mode is an explicit `runtime` setting and is recorded in configuration metadata.
- Inject only selected provider credentials through private stdin bootstrap, never argv, images, public metadata or logs. The Codex flow uses existing saved ChatGPT authentication.
- Pin framework runtime images by immutable ID for recorded measurements. Limits apply to agent containers separately from task containers.
- Containerize conformance and real adapter execution through the same launch path. Test EOF, timeout and forced launcher termination cleanup.

## Task 1: Generic container transport and configuration

**Files:** `async_rbench/track_b/config.py`, `adapter.py`, `container_runtime.py`, `container_entry.py`, `cli.py`; `tests/test_track_b_agent_container.py`.

**Interfaces:** `TrackBConfig.runtime: dict[str, Any]`; supported settings `type`, `image`, `cpus`, `memory`, `timeout_sec`. `run_container_adapter(config, adapter_args) -> int` bridges stdin/stdout; the entry module reads one private bootstrap line and forwards subsequent protocol lines to the adapter child.

- [ ] Add failing tests rejecting malformed runtime options, proving metadata binds limits/image while preserving old host-config digests.
- [ ] Add transport tests exercising bootstrap separation, protocol round-trip, failure redaction and timeout/EOF cleanup against real subprocesses where possible.
- [ ] Implement explicit Docker launch flags: non-root, read-only root, tmpfs home/tmp, resource limits, no capabilities, no host mounts/socket, unique names/labels.
- [ ] Record immutable image identity and Linux runtime metadata; make `doctor` inspect the selected image/runtime without requiring host framework dependencies.
- [ ] Run `python -m pytest tests/test_track_b_agent_container.py tests/test_track_b_adapter.py tests/test_track_b_cli.py -q`.

Configuration shape:

```yaml
runtime:
  type: docker
  image: async-rbench-track-b:codex
  cpus: 0.5
  memory: 768m
  timeout_sec: 2400
```

## Task 2: Claude runtime isolation and shared environment description

**Files:** `async_rbench/track_b/frameworks/claude_code.py`, `frameworks/common.py`; `tests/test_track_b_claude_isolation.py`, relevant existing framework tests.

- [ ] Add failing tests for both SDK and CLI request construction: no native execution/file tools, no repository configuration, isolated working directory and credential allowlist.
- [ ] Verify actual SDK/CLI option semantics using installed code or primary documentation; implement explicit disabled tools, bounded calls and cleanup.
- [ ] Include concise Linux/bash task-environment instructions in the shared protocol prompt, distinguishing the task workspace from the framework runtime workspace. Do not reveal hidden case assets or verifier inputs.
- [ ] Run the focused framework tests and report actual tool-isolation evidence separately from real model testing.

## Task 3: Reproducible framework images and usage

**Files:** `docker/track-b/Dockerfile`, build instructions/scripts under `docker/track-b/`; `docs/track-b.md`, `configs/track-b/*.example.yaml`.

- [ ] Build from an allowlisted context containing the Python package and declared dependencies only; exclude cases, artifacts, Git state and credentials.
- [ ] Provide targets for Codex CLI, Claude Code, LangGraph and OpenAI Agents SDK with fixed dependency/CLI versions. Allow custom harness packages through a documented derived image.
- [ ] Build and smoke-check Linux runtime imports/CLI help without calling paid models; record the image IDs and installed versions.
- [ ] Document the common run path, per-framework credential handling and verification status accurately.

## Task 4: Integration, real cases, publication

**Files:** `docs/reports/2026-09-07-track-b-container-runtime.md`; private raw outputs in a fresh ignored artifact directory.

- [ ] Run the complete Track B regression suite and independent boundary review.
- [ ] Verify Linux Codex requests expose no native tools or private repository content using the existing local mock endpoint technique.
- [ ] Commit the tested source, then run the same two real cases with Luna: one Linear/Async pair each, one repetition, limited resources and reused immutable task images.
- [ ] Audit traces, environment command correctness, task verifier outcomes and container cleanup. Keep the known DRS missing-value limitation explicitly disclosed and unchanged.
- [ ] Publish source and report only to `codex/track-b-harness`; confirm root main experiment processes remain untouched.
