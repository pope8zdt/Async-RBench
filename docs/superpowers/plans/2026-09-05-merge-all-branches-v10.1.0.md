# Merge All Branches into Async-RBench v10.1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate every GitHub branch into one v10.1.0 `main`, publish the formal 61-case experiment under a dedicated directory, and remove all other remote branches after verification.

**Architecture:** Build a history-preserving integration commit from `origin/main` in an isolated worktree. Merge each distinct remote tip, resolve overlapping 61-case files against the v10.1-compatible replay commit `3e604972`, then relocate experiment-owned entry files without duplicating `cases/`. Push only after tests and ancestry checks pass; delete remote branches only after the pushed `main` contains their tips.

**Tech Stack:** Git, Python 3.12, pytest, PowerShell, Async-RBench manifest tooling.

**Spec:** `docs/superpowers/specs/2026-09-05-merge-all-branches-v10.1.0-design.md`

## Global Constraints

- The final framework and evaluation contract version is exactly `10.1.0`.
- Every remote branch tip observed immediately before integration must be an ancestor of final `main`.
- Shared files use the newest v10.1-compatible state; `3e604972` is the conflict-resolution reference for the 61-case feature.
- The 61 cases remain unique under top-level `cases/`; no case directory is copied.
- Experiment-owned files live under `experiments/formal-61/`.
- The primary checkout and its uncommitted files are never reset, cleaned, stashed, or overwritten.
- No remote branch is deleted until its tip is reachable from pushed `origin/main`.
- The existing `v10.1.0` tag is not force-moved.

---

### Task 1: Preserve Every Remote Branch in the Integration History

**Files:**
- Preserve: all files unique to `origin/feat/mab-authority-infra-unscored`
- Merge: `origin/codex/paper-eval-existing-61-v10.1.0`
- Merge history: `origin/codex/paper-eval-80-redesign`
- Merge equivalence: `origin/codex/paper-eval-existing-61`
- Preserve: `docs/superpowers/specs/2026-09-01-project-structure-cleanup-design.md`

**Interfaces:**
- Consumes: remote tips from `git ls-remote --heads origin`
- Produces: an integration `HEAD` from which every distinct remote tip is reachable

- [ ] **Step 1: Refresh and freeze the remote head set**

Run:

```powershell
git fetch origin --tags
git ls-remote --heads origin
```

Expected: the six branch names in the updated spec. The sixth v10.1-compatible
61-case head was discovered by this refresh and added to the integration set.

- [ ] **Step 2: Merge the unique structure-document branch**

Run:

```powershell
git merge --no-ff origin/feat/mab-authority-infra-unscored -m "merge: preserve project structure design branch"
```

Expected: the unique design document is added and no v10.1 runtime file is
regressed.

- [ ] **Step 3: Merge the v10.1-compatible 61-case remote tip**

Run:

```powershell
git merge --no-ff origin/codex/paper-eval-existing-61-v10.1.0 -m "merge: integrate v10.1 formal 61-case branch"
```

Expected: the seven 61-case feature paths are added on top of the v10.1.0
runtime without conflicts.

- [ ] **Step 4: Merge the older 61-case history without replacing newer files**

Run:

```powershell
git merge --no-ff --no-commit origin/codex/paper-eval-80-redesign
git commit -m "merge: preserve earlier paper-evaluation branch history"
```

Expected: only the older branch's unique design and plan documents are added;
the newer v10.1-compatible 61-case files remain unchanged.

- [ ] **Step 5: Prove all same-tip and main-tip branch names are represented**

Run:

```powershell
git merge-base --is-ancestor origin/codex/paper-eval-existing-61 HEAD
git merge-base --is-ancestor origin/codex/paper-eval-existing-61-v10.1.0 HEAD
git merge-base --is-ancestor origin/codex/v10.1-step-bounded-termination HEAD
git merge-base --is-ancestor origin/feat/mab-authority-infra-unscored HEAD
```

Expected: every command exits with status 0.

### Task 2: Publish the Formal 61-Case Experiment Directory

**Files:**
- Create: `experiments/formal-61/README.md`
- Rename: `research/experiment-design/paper-eval-existing-61.csv` to `experiments/formal-61/paper-eval-existing-61.csv`
- Rename: `run_paper_eval_61.ps1` to `experiments/formal-61/run.ps1`
- Modify: `async_rbench/paper_eval.py`
- Modify: `tests/test_paper_eval_61.py`
- Modify: `README.md`
- Modify: `docs/CASE_RUNBOOK.zh-CN.md`

**Interfaces:**
- Consumes: canonical case registrations under top-level `cases/`
- Produces: `python -m async_rbench.paper_eval check --root .` and `experiments/formal-61/run.ps1` as the validated formal-experiment entry points

- [ ] **Step 1: Write failing path-layout assertions**

Add assertions to `tests/test_paper_eval_61.py`:

```python
def test_formal_experiment_assets_have_one_canonical_location() -> None:
    root = Path(__file__).resolve().parents[1]
    assert DEFAULT_EXISTING_SELECTION == Path(
        "experiments/formal-61/paper-eval-existing-61.csv"
    )
    assert (root / "experiments/formal-61/run.ps1").is_file()
    assert (root / "experiments/formal-61/README.md").is_file()
    assert not (root / "run_paper_eval_61.ps1").exists()
    assert not (
        root / "research/experiment-design/paper-eval-existing-61.csv"
    ).exists()
```

- [ ] **Step 2: Run the new assertion and confirm it fails**

Run:

```powershell
& 'F:\DTbench\DTbench2\.venv\Scripts\python.exe' -m pytest tests/test_paper_eval_61.py -q
```

Expected: failure because the formal experiment directory does not yet exist.

- [ ] **Step 3: Move the experiment-owned files**

Run:

```powershell
New-Item -ItemType Directory -Force experiments/formal-61
git mv research/experiment-design/paper-eval-existing-61.csv experiments/formal-61/paper-eval-existing-61.csv
git mv run_paper_eval_61.ps1 experiments/formal-61/run.ps1
```

Update `DEFAULT_EXISTING_SELECTION` in `async_rbench/paper_eval.py` to:

```python
DEFAULT_EXISTING_SELECTION = Path(
    "experiments/formal-61/paper-eval-existing-61.csv"
)
```

Update `experiments/formal-61/run.ps1` so its repository root is resolved two
levels above the script directory and every command executes from that root.

- [ ] **Step 4: Write the formal experiment README and update active references**

Create `experiments/formal-61/README.md` with:

```markdown
# Formal 61-Case Experiment

This is the frozen formal Async-RBench v10.1.0 evaluation cohort. The CSV
selects exactly 61 canonical case instances from `../../cases/`; it does not
copy or fork their implementations.

Validate without starting model runs:

`python -m async_rbench.paper_eval check --root .`

Run from the repository root:

`./experiments/formal-61/run.ps1 -Config configs/model-profiles/deepseek-v4-pro.yaml -Repetitions 1 -Seed 2026`
```

Replace old active paths in `README.md`, `docs/CASE_RUNBOOK.zh-CN.md`,
`async_rbench/paper_eval.py`, and `tests/test_paper_eval_61.py`. Root README must
call this the formal experiment and link to the directory README.

- [ ] **Step 5: Run focused tests and commit the directory migration**

Run:

```powershell
& 'F:\DTbench\DTbench2\.venv\Scripts\python.exe' -m pytest tests/test_paper_eval_61.py -q
& 'F:\DTbench\DTbench2\.venv\Scripts\python.exe' -m async_rbench.paper_eval check --root .
git add -- experiments/formal-61 async_rbench/paper_eval.py tests/test_paper_eval_61.py README.md docs/CASE_RUNBOOK.zh-CN.md
git commit -m "feat(eval): publish formal 61-case experiment directory"
```

Expected: tests and cohort validation pass; the commit contains no duplicated
case directories.

### Task 3: Verify the Integrated v10.1.0 Repository

**Files:**
- Verify: `pyproject.toml`
- Verify: `async_rbench/__init__.py`
- Verify: `async_rbench/evaluation/version.py`
- Verify: `evaluation_contract.json`
- Verify: `README.md`
- Verify: `experiments/formal-61/paper-eval-existing-61.csv`

**Interfaces:**
- Consumes: integrated repository tree
- Produces: objective evidence that the release, experiment, tests, and branch ancestry are consistent

- [ ] **Step 1: Check version consistency and stale active paths**

Run:

```powershell
Select-String -Path pyproject.toml,async_rbench/__init__.py,async_rbench/evaluation/version.py,evaluation_contract.json,README.md -Pattern '10\.1\.0'
git grep -n 'research/experiment-design/paper-eval-existing-61.csv\|run_paper_eval_61.ps1' -- ':!docs/superpowers/**'
$rows = Import-Csv experiments/formal-61/paper-eval-existing-61.csv
if ($rows.Count -ne 61) { throw "Expected 61 cohort rows, found $($rows.Count)" }
```

Expected: all five active surfaces report `10.1.0`, the stale-path search has
no matches, and the CSV assertion does not throw.

- [ ] **Step 2: Generate a 61-case immutable manifest without model execution**

Run:

```powershell
New-Item -ItemType Directory -Force artifacts/verification
& 'F:\DTbench\DTbench2\.venv\Scripts\python.exe' -m async_rbench.paper_eval make-manifest --root . --output artifacts/verification/formal-61-manifest.json --repetitions 1 --guidance incentive --seed 2026 --model verification-only
```

Expected: the manifest contains all 61 selected instances in both Linear and
Async modes, for 122 episode entries total.

- [ ] **Step 3: Run focused release and formal-experiment tests**

Run:

```powershell
& 'F:\DTbench\DTbench2\.venv\Scripts\python.exe' -m pytest tests/test_paper_eval_61.py tests/test_v101_runtime_contract.py tests/test_v10_repository_surface.py -q
```

Expected: all focused tests pass.

- [ ] **Step 4: Run the full suite with slow-test visibility**

Run:

```powershell
& 'F:\DTbench\DTbench2\.venv\Scripts\python.exe' -m pytest -q
```

The baseline was observed to spend more than four minutes in
`test_all_workstreams_have_passing_positive_and_negative_contract_fixtures`.
Allow that test to finish or run it separately with verbose output; do not
classify the known slowness as an integration regression.

- [ ] **Step 5: Check merge ancestry and repository cleanliness**

Run:

```powershell
git diff --check
git status --short
git merge-base --is-ancestor eaa854c5 HEAD
git merge-base --is-ancestor 9812e319 HEAD
git merge-base --is-ancestor 1a353d46 HEAD
```

Expected: no whitespace errors, only intentionally ignored verification
artifacts, and all ancestry checks exit 0.

### Task 4: Publish Main and Remove Every Other GitHub Branch

**Files:**
- Remote ref update: `refs/heads/main`
- Remote ref deletion: all non-main heads listed in Task 1

**Interfaces:**
- Consumes: verified integration `HEAD`
- Produces: a GitHub repository with only `refs/heads/main`

- [ ] **Step 1: Re-fetch and reject remote races**

Run `git fetch origin --tags`, compare `git ls-remote --heads origin` with the
Task 1 snapshot, and integrate any moved or newly created head before
continuing.

- [ ] **Step 2: Push the integration commit to main without force**

Run:

```powershell
git push origin HEAD:main
git fetch origin
```

Expected: `origin/main` equals the verified integration commit.

- [ ] **Step 3: Prove every deletion target is recoverable from main**

Run the ancestry checks for every non-main remote tip:

```powershell
git merge-base --is-ancestor origin/codex/v10.1-step-bounded-termination origin/main
git merge-base --is-ancestor origin/codex/paper-eval-80-redesign origin/main
git merge-base --is-ancestor origin/codex/paper-eval-existing-61 origin/main
git merge-base --is-ancestor origin/codex/paper-eval-existing-61-v10.1.0 origin/main
git merge-base --is-ancestor origin/feat/mab-authority-infra-unscored origin/main
```

Expected: every command exits 0 before any deletion command is issued.

- [ ] **Step 4: Delete the five non-main GitHub branch names**

Run:

```powershell
git push origin --delete codex/v10.1-step-bounded-termination codex/paper-eval-80-redesign codex/paper-eval-existing-61 codex/paper-eval-existing-61-v10.1.0 feat/mab-authority-infra-unscored
```

Expected: GitHub confirms deletion of all five names.

- [ ] **Step 5: Verify the final remote state**

Run:

```powershell
git fetch origin --prune
git ls-remote --heads origin
```

Expected: exactly one line, ending in `refs/heads/main`, whose SHA equals the
verified integration commit.
