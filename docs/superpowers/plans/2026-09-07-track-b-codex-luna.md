# Track B Codex CLI and Luna Implementation Plan

> **For agentic workers:** Use subagent-driven-development or executing-plans task by task. The user approved the Track B design and authorized this implementation and live validation.

**Goal:** Add a saved-ChatGPT-login Codex CLI runtime and validate two real development tasks in paired Linear/Async modes using `gpt-5.6-luna`.

**Architecture:** Codex chooses structured benchmark actions from participant-safe messages. The existing Track B adapter, reference scaffold, Docker capability gateway, delivery schedule and verifier remain responsible for execution and scoring. Each Codex invocation receives a fresh empty working directory, controlled settings and no native host tools.

**Tech Stack:** Python asyncio subprocesses, installed Codex CLI, JSON Schema/JSONL, pytest, existing immutable participant Docker images.

**Spec:** `docs/superpowers/specs/2026-09-07-track-b-harness-design.md`, supplemented by the user's approved Codex CLI + Luna validation sequence.

## Global constraints

- Work only in the existing `outputs/track-b-harness` linked worktree and `codex/track-b-harness` branch. Main experiment processes and data must remain untouched.
- Use `.venv-track-b/Scripts/python.exe`; do not modify the main environment or global Codex preferences.
- Reuse official saved ChatGPT authentication; never extract or publish account credentials.
- Use the exact Luna model and identical reasoning settings in both modes. Report unavailable resolved model identity as unknown.
- Public task wording, official cohort and frozen per-episode scoring remain unchanged. These are development-only Track B records.
- Verify no native host tool is exposed before a live task. Empty cwd and prompt instructions alone are not isolation.
- Keep live diagnostics and raw responses local under ignored artifacts. Preserve prior Gemini runs.

## Task 1: Controlled Codex runtime

Files: create `async_rbench/track_b/frameworks/codex_cli.py` and `tests/test_track_b_codex_cli.py`.

Interface: `CodexCLIRuntime(config).run(FrameworkRequest) -> FrameworkResult`; `check_cli_login() -> tuple[bool, str]`; `build_runtime(config)`.

- [x] Discover and verify CLI settings that remove host tools, external integrations, skills and inherited project context.
- [x] Write failing tests for selected model/effort, stdin prompt, fresh cwd, controlled environment, schema and flags, successful JSONL usage, ambiguous output, native tool events, malformed actions, login failure and timeout cleanup.
- [x] Build a strict response envelope containing `output_text` and typed `actions` with `kind` and `arguments`; validate decoded arguments against the original schemas, then reuse the shared action allowlist/parser. Arbitrary evidence uses recursive key/value entries. This replaces the initial nested JSON string format after real validation exposed escaping errors.
- [x] Reject empty output, CLI failures, missing completed-turn events and any native action. Count input/output once; do not add cached or total counters again.
- [x] Run runtime tests and perform an isolated real Luna connectivity/tool-selection probe before full evaluation.

## Task 2: Framework registration and guidance

Files: `config.py`, `frameworks/catalog.py`, `configs/track-b/codex-cli.example.yaml`, `docs/track-b.md`, catalog tests.

- [x] Add `codex-cli` to known frameworks and expose CLI installation/login readiness.
- [x] Require saved ChatGPT authentication for this integration and reject API credential environment overrides.
- [x] Add a Luna example with medium reasoning, bounded request time and existing benchmark concurrency/step limits.
- [x] Document participant-local account usage, controlled tool execution and separate Track B results.
- [x] Run framework, adapter, protocol and new Codex tests; review the combined diff.

## Task 3: Real paired validation and publication

Local artifacts: `artifacts/track-b-luna-live/` with config, image map, manifest, probe, logs, runs and report.

- [x] Verify existing immutable image IDs/task content and limit all validation containers to 0.25 CPU and 512 MB memory.
- [ ] Run dependency-unblock and late-test-evidence, one repetition of Linear and Async per case, using new output paths and a fresh config-bound conformance run.
- [ ] Inspect protocol events, tool use, result delivery, verifier and score status. Distinguish task failure from infrastructure failure; report actual BTS/DRS without inventing success.
- [ ] Verify the main experiment continues and scan published files/diagnostics for credential leakage.
- [ ] Commit tested implementation and publish only the existing Track B branch. Report concrete measurements and any remaining limitations.
