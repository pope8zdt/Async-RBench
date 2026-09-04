# Paper-Eval-80 Case Redistribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stale public case surface with a reproducible Paper-Eval-80 cohort containing 61 retained cases and 19 new cases, while fully removing `gaia2-stockholm-moveout`.

**Architecture:** Preserve historical dataset splits as provenance and add a separate, generated Paper-Eval manifest. Derive migration status from each scored event contract rather than every baseline delivery in the async schedule, normalize four v4 legacy cases to the v7 private/evaluator layout, build 19 source-locked candidates through one production builder, and publish only candidates that pass the existing promotion and release gates.

**Tech Stack:** Python 3.12, pytest, PyYAML, JSON/CSV manifests, existing `async_rbench` case factory and Docker case lifecycle.

**Spec:** `docs/superpowers/specs/2026-09-04-paper-eval-80-case-redistribution-design.md`

## Global Constraints

- Work from `origin/main@48d98c2f21aa518f5fe840a683ee126200fbe989` on `codex/paper-eval-80-redesign`.
- Preserve original `calibration`, `development`, and `test` values; Paper-Eval membership is a separate cohort field.
- Final cohort is exactly 61 retained cases plus 19 new cases.
- Final cohort quotas are 10 cases per event theme, 40 Hard / 40 Medium, and sources MAB 34 / OSWorld 16 / SWE 15 / TBN 15 / GAIA2 0.
- Remove `gaia2-stockholm-moveout` from every tracked path and tracked textual reference.
- Remove exactly six additional unselected legacy case directories and the extra `secure-release/tracebench-git-recovery-late-authority-001` instance.
- Do not delete ignored local candidate pools or experiment outputs.
- Reuse the existing selection salts `async-rbench-paper-eval-80-v1` and `async-rbench-paper-eval-80-run-order-v1`.
- Linear and Async tracks must use the same semantic verifier.
- New cases require source lock, executable event contract, four dynamic stages, one equivalence solution, and at least two killed negative mutations.
- The 16 previously reported migration cases already contain migrated event semantics; fix their audit classification and revalidate them without rebuilding their tasks.
- Freeze all five TerminalBench gap sources from `https://github.com/harbor-framework/terminal-bench-1.git` at commit `d28711d0da2675d0bb1d56de45ae5df6082438a3`.

## File and Responsibility Map

- Create `async_rbench/paper_eval.py`: typed loader, validator, deterministic ordering, digest calculation, and manifest renderer for Paper-Eval inputs.
- Create `async_rbench/paper_eval_case_builder.py`: production-only builder for the 19 approved source/event blueprints.
- Create `scripts/build_paper_eval_manifest.py`: CLI wrapper that writes or checks generated selection artifacts.
- Create `scripts/freeze_paper_eval_sources.py`: source-tree hashing and source-lock capture for the 19 new cases.
- Create `scripts/normalize_v4_event_contracts.py`: deterministic normalization of the four retained v4 roots.
- Create `async_rbench/evaluation/paper_eval_analysis.py`: cluster-aware bootstrap and one-source-one sensitivity summaries for Paper-Eval results.
- Create `research/experiment-design/paper-eval-80-existing-61.csv`: retained selection input with original split provenance.
- Create `research/experiment-design/paper-eval-80-gap-19.csv`: approved gap input and construction status.
- Create `research/experiment-design/paper-eval-80-source-specs.json`: exact source/reference bindings for all 19 new cases.
- Create `research/experiment-design/paper-eval-80-manifest.json`: generated final 80-row cohort with hashes and run order.
- Modify `scripts/audit_event_mechanisms.py`: classify the focal scored event and its explicitly linked control stimuli.
- Modify `event_taxonomy.json`: freeze the post-redistribution 212-instance theme counts.
- Modify `dataset_policy.json`: freeze the 212-instance split, scenario-class, theme, and difficulty totals without changing historical splits of retained cases.
- Modify `cases/registry.json`: remove retired entries/instance and register 19 promoted cases.
- Modify `research/experiment-design/async-rbench-event-migration-manifest.json`: regenerate from case truth.
- Modify `async_rbench/dynamic_pilot.py`: remove the GAIA2 pilot and retarget secure pilot sources to the retained root instance.
- Modify GAIA2-specific tests and shared fixtures listed in Task 4 so they use retained cases or disappear with the removed pilot.
- Create `tests/test_paper_eval_80.py`: cohort quotas, identity, source uniqueness, readiness, digest, and generated-file checks.
- Modify `tests/test_event_mechanism_migration.py`: 212-instance coverage and focal-event classification assertions.
- Modify `tests/test_dataset_policy.py` and `tests/test_case_quality.py`: replace the 200/201 release freeze with the final 212/212 freeze.
- Create `tests/test_v4_normalization.py`: exact four-case v7 normalization checks.
- Modify the three theme migration tests for child failure, replay, and straggler only to add Paper-Eval membership assertions; do not rewrite their already-passing theme semantics.

---

### Task 1: Implement the Paper-Eval manifest model

**Files:**
- Create: `async_rbench/paper_eval.py`
- Create: `scripts/build_paper_eval_manifest.py`
- Create: `tests/test_paper_eval_80.py`

**Interfaces:**
- Consumes: `cases/registry.json`, the two selection CSVs, and per-case private/source metadata.
- Produces: `load_selection_rows(path: Path, kind: Literal["existing", "new"]) -> list[dict[str, str]]`, `build_source_components(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]`, `build_paper_eval_manifest(root: Path) -> dict[str, Any]`, `validate_paper_eval_manifest(root: Path, manifest: dict[str, Any]) -> list[str]`, and `render_generated_artifacts(root: Path, check: bool = False) -> list[Path]`.

- [ ] **Step 1: Write failing unit tests over temporary CSV inputs**

```python
def test_manifest_rejects_duplicate_case_and_new_source(tmp_path: Path) -> None:
    root = write_minimal_selection_repo(tmp_path, duplicate_case=True, duplicate_new_source=True)
    report = build_paper_eval_manifest(root)
    errors = validate_paper_eval_manifest(root, report)
    assert any("duplicate case_id" in error for error in errors)
    assert any("duplicate new source_task" in error for error in errors)


def test_existing_shared_sources_form_sensitivity_components(tmp_path: Path) -> None:
    root = write_minimal_selection_repo(tmp_path, shared_existing_source=True)
    report = build_paper_eval_manifest(root)
    assert report["source_components"]
    assert len(report["one_source_one_case_ids"]) < len(report["rows"])


def test_run_order_uses_frozen_salt(tmp_path: Path) -> None:
    root = write_minimal_selection_repo(tmp_path)
    report = build_paper_eval_manifest(root)
    expected = sorted(
        (row["case_id"] for row in report["rows"]),
        key=lambda case_id: hashlib.sha256(
            f"async-rbench-paper-eval-80-run-order-v1|{case_id}".encode()
        ).hexdigest(),
    )
    assert [row["case_id"] for row in report["rows"]] == expected
```

- [ ] **Step 2: Run the new tests and confirm the module is missing**

Run: `python -m pytest tests/test_paper_eval_80.py -q`

Expected: collection fails because `async_rbench.paper_eval` does not exist.

- [ ] **Step 3: Implement the loader, canonical JSON digest, quota validator, and check-mode renderer**

```python
SELECTION_SALT = "async-rbench-paper-eval-80-v1"
RUN_ORDER_SALT = "async-rbench-paper-eval-80-run-order-v1"
EVENT_THEME_IDS = (
    "child_failure_or_implicit_error",
    "conflicting_valid_results",
    "delayed_authoritative_result",
    "duplicate_or_replayed_completion",
    "late_or_out_of_order_superseded_result",
    "partial_then_complete_result",
    "straggler_under_resource_pressure",
    "task_scope_or_dependency_change",
)
EXPECTED_THEME_COUNTS = {theme: 10 for theme in EVENT_THEME_IDS}
EXPECTED_DIFFICULTY_COUNTS = {"hard": 40, "medium": 40}
EXPECTED_SOURCE_COUNTS = {"MAB": 34, "OSWorld": 16, "SWE": 15, "TBN": 15}


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_order_key(case_id: str) -> str:
    return hashlib.sha256(f"{RUN_ORDER_SALT}|{case_id}".encode("utf-8")).hexdigest()
```

The validator must compare registry membership, original split, source lock, case digest, theme, difficulty, readiness, exact quotas, unique case/instance keys, unique source tasks across the 19 new rows, and stored manifest digest. Existing composite cases may share source tasks only when the manifest derives the overlap as a connected component of the case-to-source-task graph. Choose one deterministic representative per component with the selection salt and publish it as `one_source_one_case_ids`. In `--check` mode, generate bytes in memory and fail when committed bytes differ.

- [ ] **Step 4: Add CLI arguments and rerun the focused tests**

Run: `python scripts/build_paper_eval_manifest.py --help`

Expected: help includes `--root`, `--output`, and `--check`.

Run: `python -m pytest tests/test_paper_eval_80.py -q`

Expected: all temporary-fixture tests pass.

- [ ] **Step 5: Commit the manifest framework**

```bash
git add async_rbench/paper_eval.py scripts/build_paper_eval_manifest.py tests/test_paper_eval_80.py
git commit -m "feat(eval): add reproducible Paper-Eval manifest"
```

### Task 2: Freeze the 61+19 selection inputs

**Files:**
- Create: `research/experiment-design/paper-eval-80-existing-61.csv`
- Create: `research/experiment-design/paper-eval-80-gap-19.csv`
- Create: `research/experiment-design/paper-eval-80-source-specs.json`
- Modify: `tests/test_paper_eval_80.py`

**Interfaces:**
- Consumes: the approved 62-row local selection artifact and the design spec.
- Produces: stable input rows consumed by `build_paper_eval_manifest()` and by the case builder.

- [ ] **Step 1: Add failing identity and quota tests**

```python
RETAINED_NORMALIZATION_IDS = {
    "git-conflict-and-cleanup-closure",
    "scheduler-selective-replan",
    "distributed-model-runtime",
    "secure-release",
}


def test_selection_inputs_are_exactly_61_plus_19() -> None:
    existing = load_selection_rows(EXISTING_CSV, "existing")
    new = load_selection_rows(GAP_CSV, "new")
    assert len(existing) == 61
    assert len(new) == 19
    assert {row["case_id"] for row in existing}.isdisjoint(
        {row["case_id"] for row in new}
    )
    assert "gaia2-stockholm-moveout" not in {
        row["case_id"] for row in existing + new
    }
```

Also assert that the existing rows contain 41 `ready`, 16 `migration_audit_false_positive`, and 4 `normalization_required` records.

- [ ] **Step 2: Run the test and confirm the three input files are absent**

Run: `python -m pytest tests/test_paper_eval_80.py::test_selection_inputs_are_exactly_61_plus_19 -q`

Expected: fail with a missing selection input path.

- [ ] **Step 3: Create the 61-row CSV**

Use the approved 62-row artifact, remove only `gaia2-stockholm-moveout`, retain the other 61 IDs and their original `split`, source, theme, difficulty, and difficulty score, and translate statuses as follows:

```python
STATUS_TRANSLATION = {
    "contract_completion_required": "normalization_required",
    "migration_required": "migration_audit_false_positive",
    "ready": "ready",
}
```

Preserve the original selection order as `selection_order`; do not renumber the removed row. Final `run_order` belongs only in the generated 80-row manifest.

- [ ] **Step 4: Create the 19-row gap CSV and exact source-spec JSON**

The exact source bindings are:

| Case ID | Theme | Source / difficulty | Source binding |
|---|---|---|---|
| `osw-conflicting-valid-results-pe80-01` | conflicting | OSWorld / Hard | `osworld:vs_code:ea98c5d7-3cf9-4f9b-8ad3-366b58e0fcae`, reference `osw-dependency-unblock-3e78382c85` |
| `osw-conflicting-valid-results-pe80-02` | conflicting | OSWorld / Medium | `osworld:libreoffice_calc:21ab7b40-77c2-4ae6-8321-e00d3a086c73`, reference `osw-dependency-unblock-3686cb057d` |
| `swe-conflicting-valid-results-pe80-01` | conflicting | SWE / Hard | `pydata__xarray-7229`, reference `swe-dependency-unblock-3fa1a02dd5` |
| `swe-conflicting-valid-results-pe80-02` | conflicting | SWE / Hard | `instance_element-hq__element-web-fe14847bb9bb07cab1b9c6c54335ff22ca5e516a-vnan`, reference `swe-dependency-unblock-4a74272d52` |
| `osw-child-failure-pe80-01` | child failure | OSWorld / Medium | `osworld:chrome:121ba48f-9e17-48ce-9bc6-a4fb17a7ebba`, reference `osw-dependency-unblock-1a3f65b5b8` |
| `osw-child-failure-pe80-02` | child failure | OSWorld / Medium | `osworld:libreoffice_writer:88fe4b2d-3040-4c70-9a70-546a47764b48`, reference `osw-dependency-unblock-0ec654e205` |
| `swe-child-failure-pe80-01` | child failure | SWE / Hard | `instance_future-architect__vuls-b8db2e0b74f60cb7d45f710f255e061f054b6afc`, reference `swe-dependency-unblock-866543c501` |
| `tbn-child-failure-pe80-01` | child failure | TBN / Medium | TerminalBench `processing-pipeline` at `d28711d0da2675d0bb1d56de45ae5df6082438a3` |
| `osw-duplicate-replayed-completion-pe80-01` | duplicate/replay | OSWorld / Medium | `osworld:multi_apps:f8369178-fafe-40c2-adc4-b9b08a125456`, reference `osw-dependency-unblock-166790a6f2` |
| `osw-duplicate-replayed-completion-pe80-02` | duplicate/replay | OSWorld / Medium | `osworld:vlc:5ac2891a-eacd-4954-b339-98abba077adb`, reference `osw-dependency-unblock-22ed3b1d66` |
| `swe-duplicate-replayed-completion-pe80-01` | duplicate/replay | SWE / Hard | `django__django-12262`, reference `swe-dependency-unblock-db84717172` |
| `swe-duplicate-replayed-completion-pe80-02` | duplicate/replay | SWE / Hard | `pylint-dev__pylint-4604`, reference `swe-dependency-unblock-f27fc59f3c` |
| `tbn-duplicate-replayed-completion-pe80-01` | duplicate/replay | TBN / Medium | TerminalBench `log-summary` at `d28711d0da2675d0bb1d56de45ae5df6082438a3` |
| `tbn-duplicate-replayed-completion-pe80-02` | duplicate/replay | TBN / Medium | TerminalBench `pcap-to-netflow` at `d28711d0da2675d0bb1d56de45ae5df6082438a3` |
| `osw-straggler-resource-pressure-pe80-01` | straggler | OSWorld / Medium | `osworld:os:5812b315-e7bd-4265-b51f-863c02174c28`, reference `osw-dependency-unblock-72d6a6fe27` |
| `osw-straggler-resource-pressure-pe80-02` | straggler | OSWorld / Medium | `osworld:multi_apps:51f5801c-18b3-4f25-b0c3-02f85507a078`, reference `osw-cross-app-artifact-c449a6c0e0` |
| `swe-straggler-resource-pressure-pe80-01` | straggler | SWE / Hard | `astropy__astropy-14539`, reference `swe-late-test-evidence-739f820ffd` |
| `tbn-straggler-resource-pressure-pe80-01` | straggler | TBN / Medium | TerminalBench `video-processing` at `d28711d0da2675d0bb1d56de45ae5df6082438a3` |
| `tbn-task-scope-dependency-change-pe80-01` | scope/dependency | TBN / Hard | TerminalBench `kv-store-grpc` at `d28711d0da2675d0bb1d56de45ae5df6082438a3`; retiring reference `data-recovery-service` confirms prior source use |

Every JSON source spec must contain `case_id`, `source`, `source_task`, `reference_case`, `primary_event_theme`, `difficulty`, `control_prefix`, and `source_binding_status`. Use unique two-letter/digit control prefixes for all 19 rows.

- [ ] **Step 5: Run input validation**

Run: `python -m pytest tests/test_paper_eval_80.py -q`

Expected: 61+19 counts, exact quotas, unique IDs, and 0 GAIA2 rows pass; final manifest construction remains blocked only because new case directories do not exist.

- [ ] **Step 6: Commit the frozen inputs**

```bash
git add research/experiment-design/paper-eval-80-existing-61.csv research/experiment-design/paper-eval-80-gap-19.csv research/experiment-design/paper-eval-80-source-specs.json tests/test_paper_eval_80.py
git commit -m "data(eval): freeze Paper-Eval 61 plus 19 inputs"
```

### Task 3: Correct focal-event migration auditing

**Files:**
- Modify: `scripts/audit_event_mechanisms.py`
- Modify: `tests/test_event_mechanism_migration.py`
- Modify: `tests/test_migration_child_failure_theme.py`
- Modify: `tests/test_migration_duplicate_theme.py`
- Modify: `tests/test_migration_straggler_theme.py`

**Interfaces:**
- Consumes: `task/tests/control_flow_checks.json.event_contracts`, `private/private_case.yaml.scenarios.async.events`.
- Produces: `_focal_event_ids(case_dir: Path) -> set[str]` and `_current_theme_stimulus_types(raw: dict[str, Any], focal_event_ids: set[str]) -> list[str]`.

- [ ] **Step 1: Add failing tests proving baseline deliveries are not theme stimuli**

```python
def test_migration_status_uses_scored_focal_event_not_baseline_deliveries() -> None:
    report = build_event_migration_manifest(ROOT)
    rows = {row["case_id"]: row for row in report["rows"]}
    assert rows["mab-dependency-unblock-09f3ab60d7"]["current_stimulus_type"] == "implicit_error_result"
    assert rows["mab-dependency-unblock-031ed6f5bc"]["current_stimulus_type"] == "completion_replay"
    assert rows["mab-dependency-unblock-0daa930906"]["current_stimulus_type"] == "deadline_update|resource_pressure"
    assert all(rows[case_id]["migration_status"] == "matches_frozen_stimulus" for case_id in PAPER_EVAL_MIGRATED_16)
```

- [ ] **Step 2: Run the test and observe the false positives**

Run: `python -m pytest tests/test_event_mechanism_migration.py::test_migration_status_uses_scored_focal_event_not_baseline_deliveries -q`

Expected: fail because `result_delivery` is included in each current stimulus set.

- [ ] **Step 3: Implement focal and companion stimulus selection**

```python
def _focal_event_ids(case_dir: Path) -> set[str]:
    control = _read_json(case_dir / "task/tests/control_flow_checks.json") or {}
    return {
        str(contract["event_id"])
        for contract in control.get("event_contracts") or []
        if isinstance(contract, dict) and str(contract.get("event_id") or "").strip()
    }


def _current_theme_stimulus_types(raw: dict[str, Any], focal_ids: set[str]) -> list[str]:
    events = ((raw.get("scenarios") or {}).get("async") or {}).get("events") or []
    kinds = {
        str(event["stimulus_type"])
        for event in events
        if isinstance(event, dict)
        and str(event.get("stimulus_type") or "") in STIMULUS_EVENT_TYPES
        and (
            str(event.get("id") or "") in focal_ids
            or str(event.get("id") or "").rsplit(".", 1)[0] in focal_ids
        )
    }
    return sorted(kinds or {"result_delivery"})
```

For replay, include `.replay`; for straggler, include `.deadline_update`; the focal result-bearing resource row supplies `resource_pressure`. Keep task-scope delivery rows classified by their explicit `task_scope_revision` or `dependency_graph_revision` tag even when taxonomy permits `result_delivery`.

- [ ] **Step 4: Re-run the migration and theme tests**

Run: `python -m pytest tests/test_event_mechanism_migration.py tests/test_migration_child_failure_theme.py tests/test_migration_duplicate_theme.py tests/test_migration_straggler_theme.py -q`

Expected: all tests pass and all 16 selected migrated cases report `matches_frozen_stimulus`.

- [ ] **Step 5: Commit the audit correction**

```bash
git add scripts/audit_event_mechanisms.py tests/test_event_mechanism_migration.py tests/test_migration_child_failure_theme.py tests/test_migration_duplicate_theme.py tests/test_migration_straggler_theme.py
git commit -m "fix(audit): classify scored event stimuli only"
```

### Task 4: Remove retired cases and every GAIA2 case reference

**Files:**
- Delete: `cases/gaia2-stockholm-moveout/`
- Delete: `cases/mab-dependency-unblock-3005dbb57f/`
- Delete: `cases/mab-dependency-unblock-8d29bb0513/`
- Delete: `cases/swe-dependency-unblock-8902c7f431/`
- Delete: `cases/swe-late-constraint-7ce47cda27/`
- Delete: `cases/data-recovery-service/`
- Delete: `cases/swe-bench-selective-patch/`
- Delete: `cases/secure-release/instances/tracebench-git-recovery-late-authority-001/`
- Modify: `cases/registry.json`
- Modify: `async_rbench/dynamic_pilot.py`
- Modify: `tests/test_candidate_prompt_leakage.py`
- Modify: `tests/test_case_instances.py`
- Modify: `tests/test_dynamic_pilot_pipeline_order.py`
- Modify: `tests/test_integrity_safeguards.py`
- Modify: `tests/test_migration_scope_theme.py`
- Modify: `tests/test_reference_scaffold_api.py`
- Modify: `tests/test_scenario_construction.py`
- Modify: `tests/test_paper_eval_80.py`

**Interfaces:**
- Consumes: the exact retirement set in the design.
- Produces: a 193-case/193-instance intermediate registry, with no tracked `gaia2-stockholm-moveout` text.

- [ ] **Step 1: Add a failing tracked-surface guard**

```python
RETIRED_CASE_IDS = {
    "gaia2-stockholm-moveout",
    "mab-dependency-unblock-3005dbb57f",
    "mab-dependency-unblock-8d29bb0513",
    "swe-dependency-unblock-8902c7f431",
    "swe-late-constraint-7ce47cda27",
    "data-recovery-service",
    "swe-bench-selective-patch",
}


def test_retired_cases_are_absent_from_registry_and_case_tree() -> None:
    registry = json.loads((ROOT / "cases/registry.json").read_text(encoding="utf-8"))
    registered = {row["case_id"] for row in registry["case_families"]}
    assert registered.isdisjoint(RETIRED_CASE_IDS)
    assert all(not (ROOT / "cases" / case_id).exists() for case_id in RETIRED_CASE_IDS)
    secure = next(row for row in registry["case_families"] if row["case_id"] == "secure-release")
    assert [row["instance_id"] for row in secure["instances"]] == ["seed-1"]
```

- [ ] **Step 2: Run the guard and confirm the exact old surface fails**

Run: `python -m pytest tests/test_paper_eval_80.py::test_retired_cases_are_absent_from_registry_and_case_tree -q`

Expected: fail listing seven registered case IDs and the extra secure instance.

- [ ] **Step 3: Delete only the approved tracked paths and registry rows**

Use `git rm -r` with each literal directory above. Remove exactly those seven registry case objects and the extra secure instance object; do not sort or rewrite unrelated registry entries.

- [ ] **Step 4: Remove or retarget case-specific references**

Remove `pilot-gaia2-live-revision-001` from `dynamic_pilot.py`. Retarget the two secure pilot definitions from the deleted nested instance to `root / "cases/secure-release"`. Replace shared schema/validation fixtures that loaded GAIA2 with `tbn-partial-failure-recovery-0e92790bd0`; delete only tests whose sole purpose was the removed GAIA2 pilot. Update scope-theme expected membership from 38-plus-one-legacy to the retained registered set without a GAIA exception.

- [ ] **Step 5: Run deletion and reference tests**

Run: `python -m pytest tests/test_paper_eval_80.py tests/test_case_instances.py tests/test_dynamic_pilot_pipeline_order.py tests/test_integrity_safeguards.py tests/test_migration_scope_theme.py tests/test_reference_scaffold_api.py tests/test_scenario_construction.py tests/test_candidate_prompt_leakage.py -q`

Expected: all pass; registry discovery reports 193 cases and 193 instances at this intermediate point.

Run: `git grep -n "gaia2-stockholm-moveout" -- . ":(exclude)docs/superpowers/specs/2026-09-04-paper-eval-80-case-redistribution-design.md" ":(exclude)docs/superpowers/plans/2026-09-04-paper-eval-80-case-redistribution.md"`

Expected: no output. The approved design and plan retain the historical decision text; production files do not.

- [ ] **Step 6: Commit the retirement**

```bash
git add cases async_rbench/dynamic_pilot.py tests
git commit -m "chore(cases): remove retired legacy case surface"
```

### Task 5: Normalize the four retained v4 roots to v7

**Files:**
- Create: `scripts/normalize_v4_event_contracts.py`
- Create: `tests/test_v4_normalization.py`
- Modify in each of `git-conflict-and-cleanup-closure`, `scheduler-selective-replan`, `distributed-model-runtime`, and `secure-release`:
  - `private/private_case.yaml`
  - `task/tests/control_flow_checks.json`
  - `task/tests/semantic_checks.json`
- Create in each of those four roots:
  - `private/dynamic_point_plan.json`
  - `private/event_policy.json`
  - `private/case_ir.json`
  - `private/score_plan.json`
- Modify where needed: each root's `mutation_families.json`, `private/quality_contract.yaml`, and negative mutation scripts.

**Interfaces:**
- Consumes: the existing event contracts and semantic checks in each root.
- Produces: `normalize_case(root: Path, case_id: str) -> None`, using `write_case_ir()` and `write_dynamic_registry()`.

- [ ] **Step 1: Add failing exact-case normalization tests**

```python
EXPECTED = {
    "git-conflict-and-cleanup-closure": ("gc_a_authority", "conflicting_valid_results"),
    "scheduler-selective-replan": ("sc_a_b2", "conflicting_valid_results"),
    "distributed-model-runtime": ("dm_a_profile", "delayed_authoritative_result"),
    "secure-release": ("sr_a_rewrite", "late_or_out_of_order_superseded_result"),
}


@pytest.mark.parametrize("case_id", EXPECTED)
def test_retained_legacy_case_is_v7_normalized(case_id: str) -> None:
    case_dir = ROOT / "cases" / case_id
    event_id, theme = EXPECTED[case_id]
    control = load_json(case_dir / "task/tests/control_flow_checks.json")
    assert load_json(case_dir / "private/dynamic_point_plan.json") == control
    assert load_json(case_dir / "private/case_ir.json")["event_contract"]["event_id"] == event_id
    assert load_json(case_dir / "private/score_plan.json")["primary_event_theme"] == theme
    assert {point["dimension"] for point in control["checks"]} == {
        "event_intake", "state_revision", "plan_revision", "closure"
    }
    assert all(point["event_id"] == event_id for point in control["checks"])
```

- [ ] **Step 2: Run the tests and confirm private v7 files are missing**

Run: `python -m pytest tests/test_v4_normalization.py -q`

Expected: four failures on missing `private/dynamic_point_plan.json`.

- [ ] **Step 3: Implement four explicit normalization definitions**

Each definition must bind the existing four control decisions to one Case IR decision each, preserve existing semantic outcome anchors, and use the existing event policy mutation vocabulary. Add the explicit focal `stimulus_type: result_delivery`, the existing trigger boundary, and the scored `event_id` to all four control points. Call:

```python
score_plan = write_case_ir(case_dir, case_ir, control_prefix)
write_dynamic_registry(case_dir, score_plan["points"], event_contracts)
```

Copy no participant-visible strategy text. Keep existing source tasks, source-native tests, oracle, verifier, and original split unchanged.

- [ ] **Step 4: Verify idempotence and case quality**

Run: `python scripts/normalize_v4_event_contracts.py --root .`

Expected: writes exactly four normalized roots.

Run: `python scripts/normalize_v4_event_contracts.py --root . --check`

Expected after the writing run: check mode exits 0 without changing bytes.

Run: `python -m pytest tests/test_v4_normalization.py tests/test_case_quality.py tests/test_registry_audit.py -q`

Expected: all pass.

- [ ] **Step 5: Commit normalization**

```bash
git add scripts/normalize_v4_event_contracts.py tests/test_v4_normalization.py cases/git-conflict-and-cleanup-closure cases/scheduler-selective-replan cases/distributed-model-runtime cases/secure-release
git commit -m "feat(cases): normalize retained legacy contracts to v7"
```

### Task 6: Implement the production builder and freeze all 19 sources

**Files:**
- Create: `async_rbench/paper_eval_case_builder.py`
- Create: `scripts/freeze_paper_eval_sources.py`
- Create: `tests/test_paper_eval_case_builder.py`
- Modify: `research/experiment-design/paper-eval-80-source-specs.json`

**Interfaces:**
- Consumes: source specs, an existing reference case or an explicit upstream source root, and existing `write_case_ir`, `write_dynamic_registry`, case quality, provenance, and promotion validators.
- Produces: `load_blueprints(path: Path) -> list[CaseBlueprint]`, `freeze_source(root: Path, blueprint: CaseBlueprint, source_roots: Mapping[str, Path]) -> dict[str, Any]`, `preserve_source_files(case_dir: Path, source_tree_sha256: str) -> None`, `rewrite_case_identity(case_dir: Path, blueprint: CaseBlueprint) -> None`, `install_theme_contract(case_dir: Path, blueprint: CaseBlueprint) -> None`, `install_equivalence_and_mutations(case_dir: Path, blueprint: CaseBlueprint) -> None`, `materialize_candidate(root: Path, blueprint: CaseBlueprint) -> Path`, and `main(argv: Sequence[str] | None = None) -> int` for `python -m async_rbench.paper_eval_case_builder`.

- [ ] **Step 1: Add failing builder safety tests**

```python
def test_builder_refuses_unfrozen_source(tmp_path: Path) -> None:
    blueprint = replace(valid_blueprint(), source_tree_sha256="")
    with pytest.raises(ValueError, match="source tree digest"):
        materialize_candidate(tmp_path, blueprint)


def test_builder_writes_one_shared_verifier_contract(tmp_path: Path) -> None:
    candidate = materialize_candidate(write_reference_repo(tmp_path), valid_blueprint())
    public = load_case(candidate / "public_case.yaml").raw
    assert public["scenarios"]["linear"].get("events", []) == []
    assert (candidate / "task/tests/semantic_checks.json").is_file()
    assert not (candidate / "task/tests/semantic_checks.async.json").exists()
```

- [ ] **Step 2: Run the test and confirm the builder module is missing**

Run: `python -m pytest tests/test_paper_eval_case_builder.py -q`

Expected: collection fails because `async_rbench.paper_eval_case_builder` does not exist.

- [ ] **Step 3: Extract reusable production primitives from the existing dynamic pilot flow**

Implement the builder around the established sequence: copy/freeze source material, specialize participant task, remove strategy hints, install runtime event boundary, create Case IR, compile score plan, write evaluator/private mirror, write source lock/provenance, validate participant leakage, and emit candidate metadata. Do not copy `simulation_only.json`, pilot review claims, nested `instances/`, or old case identity strings.

```python
@dataclass(frozen=True)
class CaseBlueprint:
    case_id: str
    source: str
    source_task: str
    reference_case: str | None
    primary_event_theme: str
    difficulty: str
    control_prefix: str
    source_tree_sha256: str
    source_commit: str


def materialize_candidate(root: Path, blueprint: CaseBlueprint) -> Path:
    if not SHA256_RE.fullmatch(blueprint.source_tree_sha256):
        raise ValueError("source tree digest is required")
    target = root / "candidate_cases" / blueprint.case_id
    if target.exists():
        raise FileExistsError(target)
    # source copy/specialization occurs here, followed by existing validators
    return target
```

- [ ] **Step 4: Freeze source commits and tree hashes**

For OSWorld and SWE rows, hash the reference case's already-vendored source manifests and record the upstream task ID. Clone the official TerminalBench repository into ignored `work/source-freeze/terminal-bench-1`, detach at `d28711d0da2675d0bb1d56de45ae5df6082438a3`, and hash exactly `original-tasks/{processing-pipeline,log-summary,pcap-to-netflow,video-processing,kv-store-grpc}`. For `kv-store-grpc`, additionally compare the task tree lock against the provenance recorded by `data-recovery-service` in baseline commit `48d98c2f21aa518f5fe840a683ee126200fbe989`.

```powershell
git clone --filter=blob:none --no-checkout https://github.com/harbor-framework/terminal-bench-1.git work/source-freeze/terminal-bench-1
git -C work/source-freeze/terminal-bench-1 checkout --detach d28711d0da2675d0bb1d56de45ae5df6082438a3
```

Run: `python scripts/freeze_paper_eval_sources.py --root . --spec research/experiment-design/paper-eval-80-source-specs.json`

Run: `python scripts/freeze_paper_eval_sources.py --root . --spec research/experiment-design/paper-eval-80-source-specs.json --check`

Expected: all 19 rows have a 64-character `source_tree_sha256`, non-empty source revision, and unique source task; command exits 0.

- [ ] **Step 5: Run builder tests and commit**

Run: `python -m pytest tests/test_paper_eval_case_builder.py tests/test_case_factory.py tests/test_case_promotion_transaction.py -q`

Expected: all pass.

```bash
git add async_rbench/paper_eval_case_builder.py scripts/freeze_paper_eval_sources.py tests/test_paper_eval_case_builder.py research/experiment-design/paper-eval-80-source-specs.json
git commit -m "feat(cases): add source-locked Paper-Eval builder"
```

### Task 7: Build and qualify the eight OSWorld gap cases

**Files:**
- Modify: `async_rbench/paper_eval_case_builder.py`
- Modify: `tests/test_paper_eval_case_builder.py`
- Create then promote: the eight `cases/osw-*-pe80-*` roots declared in Task 2.

**Interfaces:**
- Consumes: eight OSWorld source specs and their reference cases.
- Produces: `install_osworld_semantic_registry(case_dir: Path, source_task: str) -> None`, `specialize_osworld(case_dir: Path, blueprint: CaseBlueprint) -> None`, and eight fully relocatable case roots with OSWorld semantic control registries and source-native task assets.

- [ ] **Step 1: Add failing parameterized tests for the eight OSWorld blueprints**

Assert exact event shapes by theme: two conflicting valid deliveries; designed implicit child failure after preserved sibling output; completion replay with same completion ID and digest conflict branch; resource pressure plus deadline update after barrier closure.

```python
@pytest.mark.parametrize("case_id", OSWORLD_GAP_IDS)
def test_osworld_gap_has_complete_release_contract(case_id: str) -> None:
    assert_candidate_contract(ROOT / "candidate_cases" / case_id, expected_source="OSWorld")
```

- [ ] **Step 2: Run tests and confirm all eight candidate roots are absent**

Run: `python -m pytest tests/test_paper_eval_case_builder.py -k osworld -q`

Expected: eight missing-candidate failures.

- [ ] **Step 3: Implement four OSWorld theme specializers and materialize all eight candidates**

Each specializer must preserve the reference case's source-native app/task binding and replace the event contract, Case IR, semantic checks, control checks, equivalence solution, and two negative mutations with the approved theme behavior. Hard conflict case must cover at least three workstreams and two dependency edges.

```python
def specialize_osworld(case_dir: Path, blueprint: CaseBlueprint) -> None:
    preserve_source_files(case_dir, blueprint.source_tree_sha256)
    rewrite_case_identity(case_dir, blueprint)
    install_theme_contract(case_dir, blueprint)
    install_osworld_semantic_registry(case_dir, blueprint.source_task)
    install_equivalence_and_mutations(case_dir, blueprint)
    assert validate_candidate_source_fidelity(case_dir) == []
```

Run: `python -m async_rbench.paper_eval_case_builder --source-spec research/experiment-design/paper-eval-80-source-specs.json --source OSWorld --root .`

Expected: eight candidates created and static validation passes.

- [ ] **Step 4: Run quality preflight and promote each case**

For every OSWorld row in the source-spec JSON, run:

```powershell
$specs = Get-Content -Raw research/experiment-design/paper-eval-80-source-specs.json | ConvertFrom-Json
foreach ($row in ($specs.cases | Where-Object source -eq 'OSWorld')) {
  python -m async_rbench.cli candidate-quality-preflight --candidate $row.case_id --control-prefix $row.control_prefix --output (Join-Path work/paper-eval-preflight $row.case_id)
  if ($LASTEXITCODE -ne 0) { throw "quality preflight failed: $($row.case_id)" }
  python -m async_rbench.cli case-promote --candidate $row.case_id --control-prefix $row.control_prefix --dry-run
  if ($LASTEXITCODE -ne 0) { throw "promotion dry-run failed: $($row.case_id)" }
  python -m async_rbench.cli case-promote --candidate $row.case_id --control-prefix $row.control_prefix --yes
  if ($LASTEXITCODE -ne 0) { throw "promotion failed: $($row.case_id)" }
}
```

Expected: baseline and equivalence pass, both negative mutations are killed, dry-run passes, then promotion registers one temporary calibration `seed-1` instance. Task 10 moves only these never-evaluated new instances to `test` at the final freeze.

- [ ] **Step 5: Run OSWorld-specific validation and commit**

Run: `python -m pytest tests/test_paper_eval_case_builder.py tests/test_source_native_case_support.py tests/test_registry_audit.py -k "osworld or registry" -q`

Expected: all pass.

```bash
git add cases/registry.json cases/osw-*-pe80-* async_rbench/paper_eval_case_builder.py tests/test_paper_eval_case_builder.py
git commit -m "feat(cases): add eight Paper-Eval OSWorld cases"
```

### Task 8: Build and qualify the six SWE-bench gap cases

**Files:**
- Modify: `async_rbench/paper_eval_case_builder.py`
- Modify: `tests/test_paper_eval_case_builder.py`
- Create then promote: the six `cases/swe-*-pe80-*` roots declared in Task 2.

**Interfaces:**
- Consumes: six SWE source specs and already-vendored source-native tests from their reference cases.
- Produces: `bind_swe_revision_and_native_tests(case_dir: Path, source_task: str) -> None`, `specialize_swe(case_dir: Path, blueprint: CaseBlueprint) -> None`, and six registered cases whose task and regression tests remain bound to the exact source revision.

- [ ] **Step 1: Add failing parameterized tests for all six SWE blueprints**

```python
@pytest.mark.parametrize("case_id", SWE_GAP_IDS)
def test_swe_gap_pins_issue_revision_and_native_tests(case_id: str) -> None:
    candidate = ROOT / "candidate_cases" / case_id
    lock = json.loads((candidate / "private/source_lock.json").read_text())
    assert lock["source_revision"]
    assert lock["source_file_sha256"]
    assert validate_candidate_source_fidelity(candidate) == []
```

- [ ] **Step 2: Run tests and confirm six missing candidates**

Run: `python -m pytest tests/test_paper_eval_case_builder.py -k swe -q`

Expected: six missing-candidate failures.

- [ ] **Step 3: Implement SWE specializers and materialize candidates**

Conflict cases must arbitrate incompatible source-native test evidence by revision/authority; child failure must preserve static-analysis evidence while rebuilding the failed branch; duplicate cases must reject repeated patch/test completion; straggler must reject an expired test result for an older revision. Preserve the underlying issue task and tests byte-for-byte where declared by the source lock.

```python
def specialize_swe(case_dir: Path, blueprint: CaseBlueprint) -> None:
    preserve_source_files(case_dir, blueprint.source_tree_sha256)
    rewrite_case_identity(case_dir, blueprint)
    install_theme_contract(case_dir, blueprint)
    bind_swe_revision_and_native_tests(case_dir, blueprint.source_task)
    install_equivalence_and_mutations(case_dir, blueprint)
    assert validate_candidate_source_fidelity(case_dir) == []
```

Run: `python -m async_rbench.paper_eval_case_builder --source-spec research/experiment-design/paper-eval-80-source-specs.json --source SWE --root .`

Expected: six candidates created and static validation passes.

- [ ] **Step 4: Preflight and promote all six SWE cases**

```powershell
$specs = Get-Content -Raw research/experiment-design/paper-eval-80-source-specs.json | ConvertFrom-Json
foreach ($row in ($specs.cases | Where-Object source -eq 'SWE')) {
  python -m async_rbench.cli candidate-quality-preflight --candidate $row.case_id --control-prefix $row.control_prefix --output (Join-Path work/paper-eval-preflight $row.case_id)
  if ($LASTEXITCODE -ne 0) { throw "quality preflight failed: $($row.case_id)" }
  python -m async_rbench.cli case-promote --candidate $row.case_id --control-prefix $row.control_prefix --dry-run
  if ($LASTEXITCODE -ne 0) { throw "promotion dry-run failed: $($row.case_id)" }
  python -m async_rbench.cli case-promote --candidate $row.case_id --control-prefix $row.control_prefix --yes
  if ($LASTEXITCODE -ne 0) { throw "promotion failed: $($row.case_id)" }
}
```

Expected: equivalence passes, two distinct negative failure families are killed for each Hard case, and six temporary calibration `seed-1` instances are registered for final allocation in Task 10.

- [ ] **Step 5: Run SWE validation and commit**

Run: `python -m pytest tests/test_paper_eval_case_builder.py tests/test_source_native_case_support.py tests/test_registry_audit.py -k "swe or registry" -q`

Expected: all pass.

```bash
git add cases/registry.json cases/swe-*-pe80-* async_rbench/paper_eval_case_builder.py tests/test_paper_eval_case_builder.py
git commit -m "feat(cases): add six Paper-Eval SWE cases"
```

### Task 9: Build and qualify the five TerminalBench gap cases

**Files:**
- Modify: `async_rbench/paper_eval_case_builder.py`
- Modify: `tests/test_paper_eval_case_builder.py`
- Create then promote:
  - `cases/tbn-child-failure-pe80-01/`
  - `cases/tbn-duplicate-replayed-completion-pe80-01/`
  - `cases/tbn-duplicate-replayed-completion-pe80-02/`
  - `cases/tbn-straggler-resource-pressure-pe80-01/`
  - `cases/tbn-task-scope-dependency-change-pe80-01/`

**Interfaces:**
- Consumes: the five frozen TerminalBench task trees.
- Produces: `specialize_pipeline_failure`, `specialize_log_summary_replay`, `specialize_pcap_conflicting_replay`, `specialize_video_lease_straggler`, and `specialize_kv_membership_revision`, each with signature `(case_dir: Path, blueprint: CaseBlueprint) -> None`; `specialize_tbn(case_dir: Path, blueprint: CaseBlueprint) -> None`; and five registered, source-native, Docker-verifiable cases.

- [ ] **Step 1: Add failing TBN blueprint and source uniqueness tests**

```python
@pytest.mark.parametrize("case_id,source_task", {
    "tbn-child-failure-pe80-01": "processing-pipeline",
    "tbn-duplicate-replayed-completion-pe80-01": "log-summary",
    "tbn-duplicate-replayed-completion-pe80-02": "pcap-to-netflow",
    "tbn-straggler-resource-pressure-pe80-01": "video-processing",
    "tbn-task-scope-dependency-change-pe80-01": "kv-store-grpc",
}.items())
def test_tbn_gap_preserves_exact_source_task(case_id: str, source_task: str) -> None:
    candidate = ROOT / "candidate_cases" / case_id
    contract = yaml.safe_load((candidate / "private/quality_contract.yaml").read_text())
    assert [row["task_id"] for row in contract["source_contract"]["sources"]] == [source_task]
```

- [ ] **Step 2: Run tests and confirm five missing candidates**

Run: `python -m pytest tests/test_paper_eval_case_builder.py -k tbn -q`

Expected: five missing-candidate failures.

- [ ] **Step 3: Implement the five task-specific TBN specializers**

Use non-zero stage failure for `processing-pipeline`; exact-once output checksum and downstream counter for `log-summary`; conflicting same-ID payload quarantine for `pcap-to-netflow`; expired worker lease after resource release for `video-processing`; and a post-provisional membership/dependency revision for `kv-store-grpc`. The Hard `kv-store-grpc` case must contain at least three workstreams, two dependency edges, preserved unaffected evidence, and two negative mutation families.

```python
TBN_SPECIALIZERS = {
    "processing-pipeline": specialize_pipeline_failure,
    "log-summary": specialize_log_summary_replay,
    "pcap-to-netflow": specialize_pcap_conflicting_replay,
    "video-processing": specialize_video_lease_straggler,
    "kv-store-grpc": specialize_kv_membership_revision,
}


def specialize_tbn(case_dir: Path, blueprint: CaseBlueprint) -> None:
    rewrite_case_identity(case_dir, blueprint)
    TBN_SPECIALIZERS[blueprint.source_task](case_dir, blueprint)
    install_theme_contract(case_dir, blueprint)
    install_equivalence_and_mutations(case_dir, blueprint)
```

Run: `python -m async_rbench.paper_eval_case_builder --source-spec research/experiment-design/paper-eval-80-source-specs.json --source TBN --root .`

Expected: five candidates created and static validation passes.

- [ ] **Step 4: Preflight and promote all five TBN cases**

```powershell
$specs = Get-Content -Raw research/experiment-design/paper-eval-80-source-specs.json | ConvertFrom-Json
foreach ($row in ($specs.cases | Where-Object source -eq 'TBN')) {
  python -m async_rbench.cli candidate-quality-preflight --candidate $row.case_id --control-prefix $row.control_prefix --output (Join-Path work/paper-eval-preflight $row.case_id)
  if ($LASTEXITCODE -ne 0) { throw "quality preflight failed: $($row.case_id)" }
  python -m async_rbench.cli case-promote --candidate $row.case_id --control-prefix $row.control_prefix --dry-run
  if ($LASTEXITCODE -ne 0) { throw "promotion dry-run failed: $($row.case_id)" }
  python -m async_rbench.cli case-promote --candidate $row.case_id --control-prefix $row.control_prefix --yes
  if ($LASTEXITCODE -ne 0) { throw "promotion failed: $($row.case_id)" }
}
```

Expected: five Docker oracle/verifier lifecycles pass and five temporary calibration `seed-1` instances are registered for final allocation in Task 10.

- [ ] **Step 5: Run TBN validation and commit**

Run: `python -m pytest tests/test_paper_eval_case_builder.py tests/test_source_native_case_support.py tests/test_registry_audit.py -k "tbn or registry" -q`

Expected: all pass.

```bash
git add cases/registry.json cases/tbn-*-pe80-* async_rbench/paper_eval_case_builder.py tests/test_paper_eval_case_builder.py
git commit -m "feat(cases): add five Paper-Eval TerminalBench cases"
```

### Task 10: Freeze final registry and event taxonomy counts

**Files:**
- Modify: `event_taxonomy.json`
- Modify: `dataset_policy.json`
- Modify: `tests/test_event_mechanism_migration.py`
- Modify: `tests/test_case_instances.py`
- Modify: `tests/test_dataset_policy.py`
- Modify: `tests/test_case_quality.py`
- Modify: `tests/test_paper_eval_80.py`
- Modify: `tests/test_migration_child_failure_theme.py`
- Modify: `tests/test_migration_conflicting_theme.py`
- Modify: `tests/test_migration_duplicate_theme.py`
- Modify: `tests/test_migration_late_theme.py`
- Modify: `tests/test_migration_partial_theme.py`
- Modify: `tests/test_migration_scope_theme.py`
- Modify: `tests/test_migration_straggler_theme.py`

**Interfaces:**
- Consumes: final promoted registry.
- Produces: exact 212-case/212-instance and full-repository theme freeze.

- [ ] **Step 1: Add failing final-count tests**

```python
def test_final_registered_surface_is_212_by_212() -> None:
    instances = discover_case_instances(ROOT)
    assert len({row.case_id for row in instances}) == 212
    assert len(instances) == 212


def test_final_repository_theme_distribution() -> None:
    report = build_event_migration_manifest(ROOT)
    assert report["summary"]["primary_event_theme_counts"] == {
        "child_failure_or_implicit_error": 10,
        "conflicting_valid_results": 10,
        "delayed_authoritative_result": 90,
        "duplicate_or_replayed_completion": 10,
        "late_or_out_of_order_superseded_result": 21,
        "partial_then_complete_result": 22,
        "straggler_under_resource_pressure": 10,
        "task_scope_or_dependency_change": 39,
    }


def test_final_dataset_freeze() -> None:
    policy = load_dataset_policy(ROOT)
    assert policy["target_instance_count"] == 212
    assert policy["splits"] == {"calibration": 76, "development": 30, "test": 106}
    assert policy["async_scenario_class_targets"] == {
        "live_eventful": 39, "resource_eventful": 20, "result_eventful": 153
    }
    assert policy["difficulty_targets"] == {"easy": 0, "hard": 97, "medium": 115}
```

- [ ] **Step 2: Run final-count tests and inspect any difference**

Run: `python -m pytest tests/test_case_instances.py tests/test_event_mechanism_migration.py tests/test_dataset_policy.py tests/test_case_quality.py tests/test_paper_eval_80.py -q`

Expected before taxonomy update: theme-freeze discrepancy; registry count already equals 212.

- [ ] **Step 3: Update the frozen taxonomy, dataset policy, and exact theme membership sets**

Use the exact eight theme counts above. In `dataset_policy.json`, set target/range/family/instance counts to 212, splits to 76/30/106, scenario classes to 39/20/153, and difficulties to 0/97/115. Register every new case as `test` and record that the 19 new test cases were frozen before any model evaluation. Update exact-set migration tests for the seven removed and 19 added case IDs; do not change stimulus taxonomy or event semantics.

- [ ] **Step 4: Re-run final-count tests and commit**

Run: `python -m pytest tests/test_case_instances.py tests/test_event_mechanism_migration.py tests/test_dataset_policy.py tests/test_case_quality.py tests/test_paper_eval_80.py tests/test_migration_child_failure_theme.py tests/test_migration_conflicting_theme.py tests/test_migration_duplicate_theme.py tests/test_migration_late_theme.py tests/test_migration_partial_theme.py tests/test_migration_scope_theme.py tests/test_migration_straggler_theme.py -q`

Expected: all pass.

```bash
git add event_taxonomy.json dataset_policy.json tests/test_case_instances.py tests/test_event_mechanism_migration.py tests/test_dataset_policy.py tests/test_case_quality.py tests/test_paper_eval_80.py tests/test_migration_*_theme.py
git commit -m "data(cases): freeze redistributed registry counts"
```

### Task 11: Generate final 61, 19, 80, and migration artifacts

**Files:**
- Modify: `research/experiment-design/paper-eval-80-existing-61.csv`
- Modify: `research/experiment-design/paper-eval-80-gap-19.csv`
- Create: `research/experiment-design/paper-eval-80-manifest.json`
- Modify: `research/experiment-design/async-rbench-event-migration-manifest.json`
- Modify: `scripts/build_paper_eval_manifest.py`
- Modify: `tests/test_paper_eval_80.py`

**Interfaces:**
- Consumes: final case files, registry, source specs, and fixed salts.
- Produces: byte-stable committed generated artifacts and a validation-only CI mode.

- [ ] **Step 1: Add failing generated-file freshness tests**

```python
def test_committed_paper_eval_artifacts_are_current() -> None:
    assert render_generated_artifacts(ROOT, check=True) == []


def test_final_paper_eval_rows_are_release_ready() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(manifest["rows"]) == 80
    assert Counter(row["origin"] for row in manifest["rows"]) == {
        "existing": 61, "new": 19
    }
    assert all(row["readiness"] == "ready" for row in manifest["rows"])


def test_source_cluster_sensitivity_subset_is_deterministic() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rebuilt = build_paper_eval_manifest(ROOT)
    assert manifest["source_components"] == rebuilt["source_components"]
    assert manifest["one_source_one_case_ids"] == rebuilt["one_source_one_case_ids"]
    assert set(manifest["one_source_one_case_ids"]) <= {
        row["case_id"] for row in manifest["rows"]
    }
```

- [ ] **Step 2: Run the tests and confirm generated files are stale or absent**

Run: `python -m pytest tests/test_paper_eval_80.py -q`

Expected: fail on missing final manifest or stale readiness values.

- [ ] **Step 3: Generate all selection artifacts and migration inventory**

Run: `python scripts/build_paper_eval_manifest.py --root . --output research/experiment-design/paper-eval-80-manifest.json`

Run: `python scripts/audit_event_mechanisms.py --root . --output research/experiment-design/async-rbench-event-migration-manifest.json`

Expected: 80 Paper-Eval rows, 212 migration rows, no discrepancies, and all 61+19 selected rows ready.

- [ ] **Step 4: Prove byte-level idempotence**

Run: `python scripts/build_paper_eval_manifest.py --root . --check`

Run: `python scripts/audit_event_mechanisms.py --root . --output work/rebuilt-event-migration.json`

Run: `git diff --no-index -- research/experiment-design/async-rbench-event-migration-manifest.json work/rebuilt-event-migration.json`

Expected: all commands exit 0 and no diff is printed.

- [ ] **Step 5: Commit generated artifacts**

```bash
git add research/experiment-design/paper-eval-80-existing-61.csv research/experiment-design/paper-eval-80-gap-19.csv research/experiment-design/paper-eval-80-manifest.json research/experiment-design/async-rbench-event-migration-manifest.json scripts/build_paper_eval_manifest.py tests/test_paper_eval_80.py
git commit -m "data(eval): publish frozen Paper-Eval-80 manifest"
```

### Task 12: Add cluster-aware analysis and update public documentation

**Files:**
- Create: `async_rbench/evaluation/paper_eval_analysis.py`
- Create: `tests/test_paper_eval_analysis.py`
- Modify: `README.md`
- Modify: `docs/CASE_RUNBOOK.zh-CN.md`
- Create: `research/experiment-design/paper-eval-80-selection.md`
- Modify: any tracked release/audit documentation that reports the old 200/201 or 62+18 surface.
- Modify: `tests/test_paper_eval_80.py`

**Interfaces:**
- Consumes: generated manifest statistics.
- Produces: `summarize_paper_eval(rows: Sequence[dict[str, Any]], manifest: dict[str, Any], seed: int = 20260904, bootstrap_samples: int = 10000) -> dict[str, Any]`, a public description of the dual-layer split/cohort model, and an executable stale-number guard.

- [ ] **Step 1: Add failing cluster-analysis and public-document guards**

```python
def test_cluster_summary_is_deterministic_and_reports_sensitivity_subset() -> None:
    rows = fixture_scores_for_every_manifest_case()
    first = summarize_paper_eval(rows, MANIFEST, seed=7, bootstrap_samples=500)
    second = summarize_paper_eval(rows, MANIFEST, seed=7, bootstrap_samples=500)
    assert first == second
    assert first["case_count"] == 80
    assert first["one_source_one"]["case_ids"] == MANIFEST["one_source_one_case_ids"]
    assert first["cluster_bootstrap"]["samples"] == 500


def test_public_paper_eval_document_matches_generated_summary() -> None:
    text = (ROOT / "research/experiment-design/paper-eval-80-selection.md").read_text("utf-8")
    assert "61 个现有 case + 19 个新 case" in text
    assert "MAB 34 / OSWorld 16 / SWE 15 / TBN 15 / GAIA2 0" in text
    assert "Paper-Eval-80 cohort" in text
    assert "held-out" in text and "不宣称" in text
```

- [ ] **Step 2: Run the guards and confirm the analysis module/document are absent**

Run: `python -m pytest tests/test_paper_eval_analysis.py tests/test_paper_eval_80.py::test_public_paper_eval_document_matches_generated_summary -q`

Expected: collection fails on the missing analysis module and the document guard fails on the missing document.

- [ ] **Step 3: Implement cluster-level bootstrap and one-source-one summaries**

Validate that result rows contain every manifest case exactly once. Compute one mean per connected source component, bootstrap those component means with replacement using `random.Random(seed)`, and report the point estimate, 2.5/97.5 percentiles, standard error, seed, and sample count. Separately filter the exact frozen representative IDs and report their arithmetic mean. Never resample individual cases as though shared-source cases were independent.

```python
def summarize_paper_eval(rows, manifest, seed=20260904, bootstrap_samples=10000):
    scores = {str(row["case_id"]): float(row["score"]) for row in rows}
    expected = {str(row["case_id"]) for row in manifest["rows"]}
    if set(scores) != expected:
        raise ValueError("result rows must cover the Paper-Eval manifest exactly once")
    component_means = [
        statistics.fmean(scores[case_id] for case_id in component["case_ids"])
        for component in manifest["source_components"]
    ]
    rng = random.Random(seed)
    draws = [
        statistics.fmean(rng.choice(component_means) for _ in component_means)
        for _ in range(bootstrap_samples)
    ]
    representatives = manifest["one_source_one_case_ids"]
    ordered = sorted(draws)
    percentile = lambda q: ordered[round((len(ordered) - 1) * q)]
    return {
        "case_count": len(scores),
        "cluster_bootstrap": {
            "point_estimate": statistics.fmean(component_means),
            "ci95": [percentile(0.025), percentile(0.975)],
            "standard_error": statistics.stdev(draws),
            "seed": seed,
            "samples": bootstrap_samples,
        },
        "one_source_one": {
            "case_ids": representatives,
            "mean": statistics.fmean(scores[case_id] for case_id in representatives),
        },
    }
```

- [ ] **Step 4: Write public documentation from generated facts**

Document the 61+19 composition, exact quotas, selection/run-order salts, generated source components, the exact `one_source_one_case_ids` sensitivity subset, original split provenance, full GAIA2 removal, and the command used to verify freshness. Explain that result aggregation must report both the 80-case estimate and a cluster-aware bootstrap/one-source-one sensitivity result. Avoid claiming all 80 cases are previously unseen test data.

- [ ] **Step 5: Run analysis, documentation, and repository-surface tests**

Run: `python -m pytest tests/test_paper_eval_analysis.py tests/test_paper_eval_80.py tests/test_candidate_prompt_leakage.py -q`

Expected: all pass.

- [ ] **Step 6: Commit analysis and documentation**

```bash
git add async_rbench/evaluation/paper_eval_analysis.py tests/test_paper_eval_analysis.py README.md docs/CASE_RUNBOOK.zh-CN.md research/experiment-design/paper-eval-80-selection.md tests/test_paper_eval_80.py
git commit -m "docs(eval): document Paper-Eval-80 cohort"
```

### Task 13: Run release verification and prepare GitHub publication

**Files:**
- Modify only if a verifier exposes a scoped defect in files already covered by this plan.
- Create outside Git tracking: `work/paper-eval-80-release/` verification output.

**Interfaces:**
- Consumes: the completed branch.
- Produces: fresh static, mutation, Docker, and full-test evidence suitable for review.

- [ ] **Step 1: Verify generated artifacts and tracked surface**

Run: `python scripts/build_paper_eval_manifest.py --root . --check`

Run: `git grep -n "gaia2-stockholm-moveout" -- . ":(exclude)docs/superpowers/specs/2026-09-04-paper-eval-80-case-redistribution-design.md" ":(exclude)docs/superpowers/plans/2026-09-04-paper-eval-80-case-redistribution.md"`

Expected: manifest check exits 0; grep prints nothing.

- [ ] **Step 2: Run static release gates**

Run: `python -m async_rbench.cli validate --release`

Run: `python -m async_rbench.cli dataset-audit --require-publication-ready --output work/paper-eval-80-release/dataset-audit.json`

Run: `python -m async_rbench.cli event-coverage --output work/paper-eval-80-release/event-coverage.json`

Expected: all exit 0.

- [ ] **Step 3: Run focused migration, registry, selection, and quality suites**

Run: `python -m pytest -q tests/test_paper_eval_80.py tests/test_paper_eval_analysis.py tests/test_paper_eval_case_builder.py tests/test_v4_normalization.py tests/test_event_mechanism_migration.py tests/test_migration_child_failure_theme.py tests/test_migration_duplicate_theme.py tests/test_migration_straggler_theme.py tests/test_registry_audit.py tests/test_case_quality.py tests/test_source_native_case_support.py`

Expected: 0 failures.

- [ ] **Step 4: Run the full unit/integration suite**

Run: `python -m pytest -q`

Expected: 0 failures; record the pass/skip counts and duration.

- [ ] **Step 5: Run the full per-instance Oracle/verifier lifecycle**

Run: `python -m async_rbench.cli build-all --output work/paper-eval-80-release/instances --seed 1`

Run: `python -m async_rbench.cli validate-all --root work/paper-eval-80-release/instances --output work/paper-eval-80-release/validate-all.json`

Expected: all 212 registered instances report `success: true`.

- [ ] **Step 6: Inspect final diff and commit any verification-only scoped fixes**

Run: `git diff --check`

Run: `git status --short`

Run: `git diff --stat origin/main...HEAD`

Expected: no whitespace errors, no ignored work output staged, and only approved case/data/code/documentation changes.

- [ ] **Step 7: Request code review before publishing**

Invoke `superpowers:requesting-code-review`, address only verified findings, rerun affected tests, then push `codex/paper-eval-80-redesign` and open a pull request. Do not force-push or update `main` directly.

## Completion Checklist

- [ ] Seven retired case directories and one extra instance are absent.
- [ ] Production files contain no `gaia2-stockholm-moveout` reference.
- [ ] The four retained legacy roots have complete v7 private/evaluator mirrors.
- [ ] The 16 already-migrated cases remain semantically unchanged and audit as matching their frozen stimulus.
- [ ] Nineteen new cases pass source-native, equivalence, negative mutation, Oracle, and hidden verifier gates.
- [ ] Registry is exactly 212 cases / 212 instances.
- [ ] Paper-Eval is exactly 61+19, 10 per theme, 40/40 difficulty, and 34/16/15/15 source distribution.
- [ ] Shared legacy sources are represented as deterministic connected components and the one-source-one sensitivity subset is frozen.
- [ ] Generated manifests are byte-stable under check mode.
- [ ] Full pytest and all-instance lifecycle validation pass with fresh evidence.
