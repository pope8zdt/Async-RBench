# Project Structure Cleanup Design

## Goal

Consolidate experiment design, survey, research-report, and paper materials under a single `research/` tree while removing only clearly reproducible local caches and build intermediates. Preserve benchmark code, registered cases, candidate work, experiment artifacts, environments, and all pre-existing uncommitted changes.

## Target Structure

```text
research/
  README.md
  experiment-design/
    实验设计.md
    实验设计-frozen-track-a.md
    实验图表预期设计.md
    实验设计结果示例.html
  surveys/
    agent-benchmark-experiment-survey-2026.md
    agent-benchmark-literature-review-2026.md
  reports/
    case-transformability-audit-607.md
    source_native_v4_rebuild_report.md
    strict-case-task-audit-and-rebuild-v1.md
    unified_case_set_v3_report.md
  paper/
    source documents, build scripts, figures, LaTeX sources, and final outputs
```

Operational documentation remains in `docs/`. This includes runbooks, architecture contracts, environment instructions, curation procedures, and pipeline documentation used to operate the benchmark.

## Safe Deletion Boundary

Delete only ignored, reproducible local material:

- root `__pycache__/`, `.pytest_cache/`, `.codex-work/`, `.codex-chrome-*`, `.codex-edge-*`, `.tmp-*`, and `tmp/`;
- `research/paper/__pycache__/`, `research/paper/tmp/`, and `research/paper/_render*` directories;
- LaTeX intermediates under `research/paper/latex/`: `*.aux`, `*.bbl`, `*.blg`, `*.fdb_latexmk`, `*.fls`, `*.log`, `*.out`, and `*.xdv`.

Keep all virtual environments, `artifacts/`, `outputs/`, `candidate_cases/`, `candidate_instances/`, paper source files, figures, PDFs, DOCX files, ZIP source releases, and registered case data.

## Reference Updates

- Add `research/README.md` as the research-material index.
- Update README, runbook, upstream documentation, and moved-document cross-references to their new paths.
- Change the ignored paper path from `/paper/` to `/research/paper/` and retain existing generated-directory ignore rules.
- Scan the repository for stale references to the former root and `docs/` paths.

## Validation

1. Confirm every planned source file exists at its new location and no planned source remains at the old location.
2. Search tracked files for stale research paths.
3. Run `python -m async_rbench.cli validate`.
4. Inspect `git status` to ensure pre-existing code and case changes remain intact and that only the intended tracked document moves, reference edits, and ignore-rule changes were introduced.

## Non-Goals

- No Python implementation, case definition, model profile, schema, or test behavior changes.
- No deletion of experiment results, candidate data, virtual environments, or current uncommitted work.
- No broad rewrite of operational documentation.
