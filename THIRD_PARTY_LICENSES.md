# Third-party material

Async-RBench combines original benchmark infrastructure with transformed task
materials from five upstream benchmarks. The root Apache-2.0 license applies to
original Async-RBench work only; it does not override upstream copyrights or
task-specific terms.

| Source | Upstream project | Declared terms used for this release |
|---|---|---|
| GAIA2 | [Meta Agents Research Environments](https://github.com/facebookresearch/meta-agents-research-environments) | Repository code: MIT; dataset: CC BY 4.0 |
| MultiAgentBench | [MARBLE](https://github.com/ulab-uiuc/MARBLE) | MIT |
| OSWorld | [OSWorld](https://github.com/xlang-ai/OSWorld) | Apache-2.0 |
| SWE-bench | [SWE-bench](https://github.com/SWE-bench/SWE-bench) | MIT for the benchmark; embedded source repositories retain their own licenses |
| Terminal-Bench | [Terminal-Bench](https://github.com/harbor-framework/terminal-bench) | Apache-2.0; task-specific embedded components may add terms |

Every registered case names its source task or tasks in `public/case.yaml` and
`PROVENANCE.md`. Keep those records when redistributing a case. If a task
directory contains an additional license or notice, that file controls for the
corresponding third-party material.

The public repository intentionally omits upstream repository caches and all
private judge content. Anyone publishing a modified distribution is
responsible for checking the terms of newly added or changed assets.
