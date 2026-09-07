# Track B Agent-System Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real Track B runner with three maintained agent-framework integrations, public harness component interfaces, a safe local CLI, and a two-case engineering acceptance report.

**Architecture:** A Track B adapter composes participant-owned policy components and a framework driver above the existing JSONL/capability boundary. The evaluator kernel remains unchanged; Track B is registered as a development-only adapter profile and delegates manifest execution to the existing runner.

**Tech Stack:** Python 3.11+, `typing.Protocol`, dataclasses, PyYAML, argparse, optional Claude Agent SDK, LangGraph, OpenAI Agents SDK, pytest, Next.js static website.

**Spec:** `docs/superpowers/specs/2026-09-07-track-b-harness-design.md`

## Global Constraints

- Work only in `outputs/track-b-harness` on branch `codex/track-b-harness`.
- Do not modify or reuse the active formal experiment checkout, environment, processes, ports, manifests, outputs, or Docker resources.
- Do not start Docker or make real model calls while formal experiment processes are active.
- Track B must never set `official_track=true` or become eligible for the Track A leaderboard.
- Framework packages are optional dependencies; Track A imports and commands must work without them.
- The evaluator owns scheduling, release, workspaces, private truth, verification, scoring, and aggregation.

---

### Task 1: Track B configuration, contracts, and component loading

**Files:**
- Create: `async_rbench/track_b/__init__.py`
- Create: `async_rbench/track_b/contracts.py`
- Create: `async_rbench/track_b/config.py`
- Create: `async_rbench/track_b/components.py`
- Test: `tests/test_track_b_components.py`

**Interfaces:**
- Produces: `TrackBConfig.from_file(path: Path) -> TrackBConfig`
- Produces: `load_component(spec: str, expected: type[T]) -> T`
- Produces: `AgentRuntime`, `ModelBackend`, `ContextBuilder`, `DelegationPolicy`, `AgentPolicy`, and `LifecycleHooks` protocols.
- Produces: immutable `FrameworkRequest`, `FrameworkResult`, `HarnessAction`, and `PublicEpisodeContext` values.

- [ ] **Step 1: Write failing configuration and component tests**

```python
def test_track_b_config_rejects_track_a(tmp_path):
    path = tmp_path / "track-b.yaml"
    path.write_text("track: A\nframework: langgraph\nmodel: test\n")
    with pytest.raises(ValueError, match="track must be B"):
        TrackBConfig.from_file(path)

def test_component_loader_requires_protocol_methods(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="ContextBuilder"):
        load_component("tests.track_b_fixtures:invalid_context_builder", ContextBuilder)
```

- [ ] **Step 2: Run tests and verify imports/functions are missing**

Run: `python -m pytest tests/test_track_b_components.py -q`
Expected: collection fails because `async_rbench.track_b` does not exist.

- [ ] **Step 3: Implement strict YAML validation, sanitized metadata, protocols, defaults, and entry-point loading**

```python
@runtime_checkable
class ContextBuilder(Protocol):
    def build(self, context: PublicEpisodeContext) -> FrameworkRequest: ...

def load_component(spec: str, expected: type[T]) -> T:
    module_name, separator, factory_name = spec.partition(":")
    if not separator or module_name.startswith("."):
        raise ValueError("component entry point must be an absolute module:factory")
    value = getattr(importlib.import_module(module_name), factory_name)()
    if not isinstance(value, expected):
        raise ValueError(f"component does not implement {expected.__name__}")
    return value
```

- [ ] **Step 4: Run focused and profile regression tests**

Run: `python -m pytest tests/test_track_b_components.py tests/test_profiles.py -q`
Expected: all pass.

- [ ] **Step 5: Commit the component API**

```text
git add async_rbench/track_b tests/test_track_b_components.py
git commit -m "Add Track B harness component API"
```

### Task 2: Maintained framework catalog and drivers

**Files:**
- Create: `async_rbench/track_b/frameworks/__init__.py`
- Create: `async_rbench/track_b/frameworks/catalog.py`
- Create: `async_rbench/track_b/frameworks/claude_code.py`
- Create: `async_rbench/track_b/frameworks/langgraph.py`
- Create: `async_rbench/track_b/frameworks/openai_agents.py`
- Create: `async_rbench/track_b/frameworks/deterministic.py`
- Modify: `pyproject.toml`
- Test: `tests/test_track_b_frameworks.py`

**Interfaces:**
- Consumes: `AgentRuntime`, `FrameworkRequest`, `FrameworkResult`, `HarnessAction`, `TrackBConfig`.
- Produces: `FrameworkSpec`, `FRAMEWORKS`, `get_framework(name)`, and `doctor_framework(name, config)`.
- Produces: one `build_runtime(config)` factory per framework module.

- [ ] **Step 1: Write failing catalog, dependency-check, and normalized-result tests**

```python
def test_catalog_contains_three_public_frameworks():
    assert set(public_frameworks()) == {"claude-code", "langgraph", "openai-agents"}

def test_doctor_reports_missing_optional_dependency(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda _: None)
    report = doctor_framework("langgraph", sample_config())
    assert report.ready is False
    assert "async-rbench[langgraph]" in report.install_hint
```

- [ ] **Step 2: Run tests and confirm catalog imports fail**

Run: `python -m pytest tests/test_track_b_frameworks.py -q`
Expected: FAIL because the framework catalog is missing.

- [ ] **Step 3: Implement lazy integrations and deterministic driver**

```python
FRAMEWORKS = {
    "claude-code": FrameworkSpec("claude-code", "claude_agent_sdk", "claude"),
    "langgraph": FrameworkSpec("langgraph", "langgraph", None),
    "openai-agents": FrameworkSpec("openai-agents", "agents", None),
    "deterministic": FrameworkSpec("deterministic", None, None, public=False),
}
```

Each module imports its third-party package only inside `build_runtime`. SDK calls accept injected client/runner factories so tests exercise normalized behavior without external network calls.

- [ ] **Step 4: Add optional dependency groups**

```toml
track-b-claude = ["claude-agent-sdk>=0.2,<0.3"]
track-b-langgraph = ["langgraph>=1,<2"]
track-b-openai = ["openai-agents>=0.2,<1"]
```

- [ ] **Step 5: Run framework and import-isolation tests**

Run: `python -m pytest tests/test_track_b_frameworks.py tests/test_profiles.py -q`
Expected: all pass without optional packages installed.

- [ ] **Step 6: Commit maintained framework drivers**

```text
git add async_rbench/track_b/frameworks pyproject.toml tests/test_track_b_frameworks.py
git commit -m "Add maintained Track B framework drivers"
```

### Task 3: Protocol adapter, profile, and CLI

**Files:**
- Create: `async_rbench/track_b/adapter.py`
- Create: `async_rbench/track_b/cli.py`
- Create: `async_rbench/track_b/__main__.py`
- Create: `adapters/track_b.py`
- Modify: `async_rbench/profiles/profile.py`
- Modify: `async_rbench/profiles/__init__.py`
- Modify: `pyproject.toml`
- Test: `tests/test_track_b_cli.py`
- Test: `tests/test_track_b_adapter.py`

**Interfaces:**
- Consumes: Track B configuration, component loader, framework catalog, `JsonlGateway`, `CapabilityRuntimeProxy`, and existing `eval_cli` functions.
- Produces: `async-rbench-track-b` executable and `python -m async_rbench.track_b` commands.
- Produces: development-only profile `track_b` with runtime mode `agent_system`.

- [ ] **Step 1: Write failing CLI and adapter tests**

```python
def test_run_command_never_requests_official_track(monkeypatch, tmp_path):
    captured = []
    monkeypatch.setattr(track_b_cli, "run_eval_cli", lambda argv: captured.extend(argv) or 0)
    assert track_b_cli.main(["run", "--config", str(config), "--manifest", str(manifest), "--output", str(tmp_path / "out")]) == 0
    assert "--official-track" not in captured

def test_adapter_rejects_private_context_field():
    with pytest.raises(ValueError, match="private"):
        build_public_context({"instruction": "x", "result_kind": "authoritative"})
```

- [ ] **Step 2: Run tests and confirm commands/profile are absent**

Run: `python -m pytest tests/test_track_b_cli.py tests/test_track_b_adapter.py -q`
Expected: FAIL because the CLI and adapter do not exist.

- [ ] **Step 3: Implement adapter lifecycle and capability tool bridge**

The adapter receives the public start event, emits sanitized metadata and `ready`, runs the configured runtime, validates every normalized action, uses only `CapabilityRuntimeProxy` for workspace actions, records delivery acknowledgement and lineage, and emits a typed `episode_ended`. Stdout remains JSONL-only.

- [ ] **Step 4: Implement CLI delegation and Track B profile**

```python
run_args = [
    "run-manifest", "--manifest", args.manifest,
    "--profile", "track_b", "--config", args.config,
    "--output", str(safe_output),
]
return eval_cli.main(run_args)
```

`run` rejects output paths inside `artifacts/experiments/formal-*` and refuses to run when the manifest declares an official track.

- [ ] **Step 5: Run Track B plus kernel boundary tests**

Run: `python -m pytest tests/test_track_b_cli.py tests/test_track_b_adapter.py tests/test_kernel_adapter_boundary.py tests/test_conformance.py -q`
Expected: all pass.

- [ ] **Step 6: Commit the executable Track B path**

```text
git add async_rbench/track_b adapters/track_b.py async_rbench/profiles pyproject.toml tests/test_track_b_cli.py tests/test_track_b_adapter.py
git commit -m "Add Track B protocol adapter and CLI"
```

### Task 4: Two-case engineering acceptance command

**Files:**
- Create: `configs/track-b/deterministic-validation.yaml`
- Create: `configs/track-b/claude-code.example.yaml`
- Create: `configs/track-b/langgraph.example.yaml`
- Create: `configs/track-b/openai-agents.example.yaml`
- Create: `scripts/validate_track_b.py`
- Test: `tests/test_track_b_validation.py`

**Interfaces:**
- Consumes: Track B CLI and deterministic runtime.
- Produces: `run_validation(root, output) -> dict` and `track-b-validation.json`.

- [ ] **Step 1: Write a failing acceptance-report test**

```python
def test_validation_report_is_two_case_non_leaderboard(tmp_path):
    report = run_validation(ROOT, tmp_path)
    assert report["case_count"] == 2
    assert report["episode_count"] == 4
    assert report["leaderboard_eligible"] is False
    assert report["model_calls"] == 0
    assert report["docker_started"] is False
```

- [ ] **Step 2: Run it and verify the validation helper is missing**

Run: `python -m pytest tests/test_track_b_validation.py -q`
Expected: FAIL because `run_validation` is missing.

- [ ] **Step 3: Implement the fixed development-instance validation**

Use `mab-dependency-unblock-8b943d725b::seed-1` and `mab-late-test-evidence-4c6c77884e::seed-1`. Build a paired one-repeat manifest, exercise the Track B adapter with deterministic inputs, run protocol checks, and write explicit engineering-only status.

- [ ] **Step 4: Run the two-case validation**

Run: `python scripts/validate_track_b.py --output artifacts/track-b-validation`
Expected: exit 0 and a report with two cases, four episodes, zero model calls, zero Docker starts, passing adapter/protocol checks, and `leaderboard_eligible=false`.

- [ ] **Step 5: Commit configs and validation**

```text
git add configs/track-b scripts/validate_track_b.py tests/test_track_b_validation.py
git commit -m "Add safe two-case Track B acceptance run"
```

### Task 5: Participant documentation and website

**Files:**
- Modify: `docs/evaluation-tracks.md`
- Create: `docs/track-b.md`
- Modify: `adapters/README.md`
- Modify: `README.md`
- Modify: `website/components/evaluate-form.tsx`
- Modify: `website/app/docs/page.tsx`
- Modify: `website/tests/static-artifact.test.mjs`

**Interfaces:**
- Consumes: implemented CLI names, framework names, component names, and example config paths.
- Produces: bilingual concise Track B website flow and detailed repository tutorial.

- [ ] **Step 1: Update the static website behavior test first**

The test must assert that Track B offers Claude Code, LangGraph, OpenAI Agents SDK, and custom harness selection; generates a local command; and contains no simulation-only status.

- [ ] **Step 2: Run the website test and verify it fails on the current simulation page**

Run: `npm test -- --runInBand`
Expected: FAIL on the Track B availability behavior.

- [ ] **Step 3: Write the detailed Track B tutorial and concise bilingual site copy**

The tutorial includes the customizable/fixed matrix, install commands, `doctor`/conformance/run flow, all three example configs, custom `module:factory` example, outputs, and publication status. The browser form builds commands only; execution remains on the participant computer.

- [ ] **Step 4: Run website tests and production build**

Run: `npm test`
Expected: all website tests pass.

Run: `npm run build`
Expected: static export completes.

- [ ] **Step 5: Commit documentation and site changes**

```text
git add README.md docs adapters/README.md website
git commit -m "Document and present the Track B workflow"
```

### Task 6: Final regression, audit, and branch publication

**Files:**
- Modify only files needed to fix failures reproduced by a new failing test.

**Interfaces:**
- Consumes: all Track B modules, tests, docs, and generated validation report.
- Produces: a clean branch and published GitHub ref `codex/track-b-harness`.

- [ ] **Step 1: Run Track B and protocol regression tests**

Run: `python -m pytest tests/test_track_b_components.py tests/test_track_b_frameworks.py tests/test_track_b_cli.py tests/test_track_b_adapter.py tests/test_track_b_validation.py tests/test_profiles.py tests/test_adapter_sdk.py tests/test_kernel_adapter_boundary.py tests/test_conformance.py -q`
Expected: all pass.

- [ ] **Step 2: Run release validation without Docker**

Run: `python -m async_rbench.cli validate`
Expected: exit 0.

- [ ] **Step 3: Inspect branch isolation and diff**

Run: `git status --short`, `git diff --check`, and `git diff --stat <base>...HEAD`.
Expected: clean status, no whitespace errors, changes limited to Track B, docs, tests, package metadata, and website Track B surfaces.

- [ ] **Step 4: Confirm active formal experiment resources were untouched**

Compare the formal runner process IDs, command lines, and output paths recorded before implementation. Do not inspect or change their live files.

- [ ] **Step 5: Publish the branch through the GitHub Git Data API**

Create a commit from the remote main tree plus the reviewed branch diff, then create `refs/heads/codex/track-b-harness`. Do not update `refs/heads/main`.

- [ ] **Step 6: Report the branch URL, commands, two-case report, tests, and deferred live validation condition**

The final report distinguishes engineering acceptance from a model-quality benchmark result and states that live Docker/model validation remains gated on the formal experiment becoming idle.
