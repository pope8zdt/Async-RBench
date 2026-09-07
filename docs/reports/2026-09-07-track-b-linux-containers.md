# Track B: Linux container runtime and live validation

On 2026-09-07, Track B ran Codex CLI with the exact `gpt-5.6-luna` model over two real development cases in paired Linear and Async modes. The agent framework ran in a locked Linux container while the unchanged v11.0 kernel retained task execution, child scheduling, result delivery, private verification and scoring.

This run validates the Track B execution path. It is development-only and is not eligible for the public leaderboard.

## Result

One repetition was run for each case and mode. The values are the frozen episode scores. BTS difference means **Async minus Linear** and is reported only when both measurements in a pair are valid.

| Case | Linear BTS | Async BTS | BTS difference | Async DRS | Pair status |
| --- | ---: | ---: | ---: | ---: | --- |
| `mab-dependency-unblock-8b943d725b::seed-1` | 16.67% | 16.67% raw | — | 0.00% raw | Invalid: one child framework response was empty |
| `mab-late-test-evidence-4c6c77884e::seed-1` | 20.00% | 20.00% | +0.00 pp | 25.00% | Valid |

All four episodes produced scored records with valid public protocol, constructed scenarios and passed conformance. Three episodes are valid measurements and one of the two pairs is valid. The dependency Async episode contains one child `infrastructure_failure` and one `no_submission`; the summary therefore preserves its raw scores but excludes them from paired metrics. This avoids treating a framework transport failure as model performance.

The late-test DRS of 25% is the unchanged v11 score. Its event score consists of preservation 1 and closure 0, with required-effect and forbidden-effect components not applicable. The task verifier still reports failure. This value records the current preservation behavior and does not establish a successful task solution.

Successful completed turns report 249,565 tokens in total. This is an episode-level usage summary, not an account billing total, and excludes probes and failed or aborted calls.

## Runtime boundary

The maintained image targets are:

| Framework | Locked runtime |
| --- | --- |
| Claude Code | Claude Agent SDK 0.2.152 / Claude Code 2.1.259 |
| Codex CLI | Codex CLI 0.153.4 |
| LangGraph | LangGraph 1.2.11 |
| OpenAI Agents SDK | OpenAI Agents 0.22.0 |

The four images were built from source commit `36ee2ce75f8719a394db27c66853c2ac6b4fb203` with build-context SHA-256 `2bfe03457ac20c942cfde2462f5b64f6d01b047ce9fff39a09f031d03371c936`. The validated Codex image ID is `sha256:c3f9edbe8a1a138073168b9e45f0cf347acc515e6bfdc94e09b9b1731aee4dfc`.

The runtime uses a non-root user, read-only root filesystem, dropped Linux capabilities, `no-new-privileges`, PID/CPU/memory limits and temporary home directories. It receives the public protocol and selected authentication only. It has no repository mount, task-data mount, private verifier mount or Docker socket. EOF, timeout, host-launcher termination and normal exit all clean up the container and descendant model processes.

The real run used 0.25 CPU and 512 MB for each agent container. Task and child containers used 0.1 CPU and 384 MB. These conservative limits allowed the validation to run beside the active main experiment without modifying its code, configuration, processes or result files.

The agent-facing prompt now describes the actual Linux/bash task environment and typical `/app` workspace. The prior Windows/PowerShell presentation conflict did not recur: real terminal actions were issued for Linux/bash and executed in the separate task containers.

## Reproducibility and audit

- Model: `gpt-5.6-luna`; reasoning effort: `medium`; saved ChatGPT login copied into an ephemeral agent home.
- Both modes use configuration digest `f92ddc97de0bfbe2249d4b3d1b394b1fdb8d5dd6b2a162efe1b582ed7dfc7608`.
- The agent runtime image is identical across all four episodes.
- Each Linear/Async pair uses the same immutable task image, agent seed, case digest and verifier digest.
- Task files copied from both task images match the registered case files by SHA-256.
- The exact two-case conformance run passed 20 of 20 checks.
- The independent run audit exited successfully, found no hard failure, matched all four records to the current case, scaffold and evaluation contracts, and passed all 623 contract fixtures.
- Runtime smoke checks passed for all four framework images. Docker lifecycle black-box tests passed normal doctor, EOF cleanup, timeout cleanup and forced launcher-death cleanup.

The first launch completed the dependency pair and then stopped because a Docker Desktop restart had removed the immutable task image selected for the second case. No completed episode was overwritten. The missing image was rebuilt, its task file was checked against the registered case, and the batch resumed with the exact saved runtime configuration. The resumed run reused the first two records and completed the remaining pair.

After validation, no Track B-owned container remained. The main experiment's Claude and DeepSeek resume processes remained active.

## Extending the harness

All maintained frameworks use the same container protocol and can load custom implementations of `ModelBackend`, `ContextBuilder`, `DelegationPolicy`, `AgentPolicy` and `LifecycleHooks` from an installed Python package. A participant builds a derived image, installs the package, selects its `module:factory` entries in YAML, runs `doctor` and `conformance`, creates a paired manifest, and launches `track_b run`.

Customization stays on the participant side of the public protocol. Execution modes, event schedule, task and child containers, result gateway, private state, verifier, scoring and aggregation remain fixed by Async-RBench.

See the [Track B guide](../track-b.md) for image builds, authentication, custom components and commands.
