# Participant workflow implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement this plan task by task.

**Goal:** Complete the participant-local submission workflow and apply the user's corpus and metric-view corrections.
**Architecture:** A static Next website renders generated corpus metadata and curated aggregate records. Standard-library Python commands package and validate results locally; separate maintainer review JSON authorizes inclusion. GitHub Actions validates and builds without running participant agents.
**Tech Stack:** Existing Python, Next/React, GitHub Pages and Actions; no new runtime services.
**Spec:** docs/superpowers/specs/2026-09-06-participant-workflow.md

## Global constraints
- Exactly 47 selected cases / 282 episodes for the main leaderboard; full repository counts for task descriptions.
- No fixed child-pool condition or required public submission field; preserve frozen scoring and existing runs.
- No raw private artifacts, secrets or provider configs in published output.
- Track B stays simulation. New trust labels cannot certify unverified scores.
- Work in outputs/site-platform-v2. Do not edit or stage the root checkout's unrelated cohort/model and launcher changes.

## Task 1: Submission workflow
Files: new async_rbench/submissions.py (split helper modules if needed), tests/test_submissions.py, submissions/README.md, submissions/entries/.gitkeep, submissions/reviews/.gitkeep.
Interfaces: package_run(root, manifest_path, *, benchmark_commit, config_path=None) -> dict; validate_submission(package, cohort) -> None; load_accepted(root) -> list[dict]. Record shape extends existing main_results aggregates, with unique id, submissionId, reviewStatus, benchmarkCommit, configSha256, executionStatus='unknown'. No child pool public field.
- [x] Add tests for wrong cohort/digest, malformed metrics/coverage, forbidden fields, tampering, repeated model distinct run IDs, unreviewed exclusion and review digest mismatch.
- [x] Package only validated aggregate output of main_results.export(root, manifest); derive identity from immutable package content, no raw files.
- [x] Add package / validate / review / check CLI; explicit maintainer review stored separately, never in self-submitted envelope.
- [x] Test CLI roundtrip in temporary directories without model/network calls. Document actual commands.

## Task 2: Corpus and metric views
Files: website/app/page.tsx, new website/app/tasks/page.tsx, website/components/site-shell.tsx, website/components/leaderboard.tsx, website/app/runs/[id]/page.tsx, website/lib/content.ts, website/lib/leaderboard.mjs, website/tests/leaderboard.test.mjs, styles as needed.
Interfaces: public/data/corpus.json = {caseCount,instanceCount,generatedAt,registrySha256,themes:[{id,caseCount,instanceCount}]}; public/data/leaderboard.json same envelope as experiments.json with accepted records merged. The root integrator generates these.
- [x] Display repository case total and eight-theme distribution, with explicit 47-case leaderboard scope.
- [x] Add accessible BTS/DRS switch; BTS displays two paired columns and optional delta, DRS displays one primary column. Keep search and incomplete values.
- [x] Distinguish coverage from execution and review status; full rows sortable by selected metric, incomplete rows separately labeled and never assigned formal ranks.
- [x] Show per-theme paired BTS and DRS when available; safe fallback for old records. Test ordering/missing-value semantics.

## Task 3: Integration, docs and publication (root)
Files: async_rbench/main_results.py, website/scripts/prepare_data.py, website/scripts/refresh_results.py, website/tests/test_catalog.py, website/package.json, .github/workflows/pages.yml, issue template, configs and docs frontend.
- [x] Generate corpus counts from registry and locally read classification metadata (counts only are public), not frozen totals; prepare_data merges reviewed submissions and validates duplicate IDs.
- [x] Extend aggregates with theme metrics/coverage and explicit unknown execution state, retain existing primary calculations. Add optional cohort_root for refresh from separate authorized artifact checkout.
- [x] Remove required fixed child-pool input; keep child model optional with main-model default and make provider configuration supported by current backend.
- [x] Add local refresh preview/write command; require explicit commit/publication outside data generation. CI runs stdlib validation, node tests, build and static-link checks.
- [x] Update participant/maintainer tutorials and status definitions; verify mobile views, config, submission roundtrip, static paths; confirm Pages deployment after publishing the reviewed commit.

## Execution rulings
- User has authorized implementation and ongoing GitHub publication; do not add an approval pause.
- Existing root uncommitted model-panel addition is outside this task. Worktree uses committed panel and root artifact input may be read with worktree cohort policy; do not silently stage unrelated changes.
