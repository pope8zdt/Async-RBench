# Track B: Codex CLI + Luna live validation

On 2026-09-07, the participant's saved ChatGPT login completed two real development cases in both Linear and Async modes. All four episodes produced scored records with valid protocol traces and no model, adapter or child infrastructure failures. None passed the complete task verifier.

This is a development smoke test of Codex CLI model decisions inside the Track B reference harness. The CLI's native tools are disabled; the benchmark executes proposed actions. These results describe this configuration and are excluded from the public Track A leaderboard.

## Results

One repetition per case and mode. Values below come from the frozen v11 episode scores; the signed BTS difference is **Async minus Linear**.

| Case | Linear BTS | Async BTS | BTS difference | Raw Async DRS |
| --- | ---: | ---: | ---: | ---: |
| `mab-dependency-unblock-8b943d725b::seed-1` | 16.67% | 16.67% | +0.00 pp | 0.00% |
| `mab-late-test-evidence-4c6c77884e::seed-1` | 20.00% | 20.00% | +0.00 pp | 25.00% |
| Two-case descriptive mean | 18.33% | 18.33% | +0.00 pp | 12.50% |

**The 25% DRS requires a qualification:** its preservation component is 1 because both compared artifact maps are empty. No artifact was committed in that episode. The [current preservation comparison](https://github.com/pope8zdt/Async-RBench/blob/af3fd630c82d26be664ed42167e670d09c5f99e9/async_rbench/evaluation/control_flow_gates.py#L631) treats the two missing values as equal; this does not establish successful artifact preservation or replanning. The original score is retained without changing the scoring contract.

Completed records: **4/4**. Scored records without infrastructure failures: **4/4**. Complete paired comparisons: **2/2**. Complete task passes: **0/4**. Linear DRS is not applicable and remains `null`.

The ordinary aggregate audit reports no hard failure, no pair-quality errors, comparable development denominators and no detected visibility leakage. Scenario construction is 100%; scenario exposure is 50%. Both Async records have incomplete dynamic opportunity, schedule coverage and scenario exposure because of premature termination or missing result roles; the frozen policy still scores them. Each theme has only one instance, below the aggregate's minimum of three, so the ordinary theme-level headline metrics remain `null`. The table's two-case descriptive means do not replace those headline metrics.

## Configuration and provenance

- Tested source: [`af3fd630c82d26be664ed42167e670d09c5f99e9`](https://github.com/pope8zdt/Async-RBench/commit/af3fd630c82d26be664ed42167e670d09c5f99e9).
- Evaluation contract: `11.0.0`; scoring, verifier and case bundles unchanged.
- Framework: `codex-cli`; requested model: `gpt-5.6-luna`; reasoning effort: `medium`.
- Authentication: participant-local saved ChatGPT login. No API key is used by this integration.
- Codex CLI: `0.153.4`; Windows host, Python `3.12.13`, `jsonschema 4.26.0`; benchmark tools execute in Linux containers.
- Same config in both modes: 100 main steps, 40 child steps, 180-second request timeout; runner episode timeout 2,400 seconds.
- Every validation container is limited to 0.25 CPU and 512 MB memory. Participant images are reused by immutable image ID after task-file hash verification.
- Manifest seed: `2026`; within-pair agent seeds and case, verifier, contract and configuration digests match. A seed does not make remote model responses deterministic.
- The CLI does not independently return a provider-resolved model identity; that field remains `null`.

The four completed episodes account for **374,711 input plus output tokens** reported by successful turns. This excludes probes and earlier interrupted attempts and is not an account billing total. Episode durations sum to **1,042.498 seconds**; whole-batch wall time including initialization and other overhead is **1,142.487 seconds** (about 19 minutes).

Implementation and validation used the existing `codex/track-b-harness` linked worktree. The active main-experiment processes remained running; this work did not edit their code, configuration or raw results. The validation's CLI processes and participant containers were removed after use.

## What the run revealed

1. **The account and execution path work.** Main and child requests, terminal actions, structured evidence, submission validation, gateway delivery, private verification and score export all ran with the real account. Six child attempts submitted accepted results; six ended without submission. Gateway acceptance checks the submission contract and does not establish task correctness.
2. **Execution-environment presentation needs improvement.** The CLI still describes its Windows/PowerShell host context, while benchmark terminal actions run in Linux bash. In the first Linear episode, the main agent and both children initially issued PowerShell commands and received exit code 127. This is a harness context limitation, so the low scores should not be interpreted as a clean estimate of the model's standalone ability.
3. **Delegated assets need clearer discovery instructions.** The first case stages a receipt-producing script at `/async_rbench/upstream_solutions/event_worker.py` for the designated child. The runner copies this asset but does not execute it automatically. The reviewed child searched `/app`, did not run the producer and reported the receipt missing. There is no evidence that an already-produced receipt was lost by the framework. Five failed BTS checks in the first Linear episode directly reflect the missing final `database_diagnosis.json`. In both late-test modes, the missing `output_data/solution.py` causes four base-task failures; only `source.pin` passes. The agent's self-reported completion is not verifier success.
4. **DRS has a missing-artifact boundary to audit separately.** In late-test Async, process score is `(preservation 1 + closure 0) / 2 = 0.5`, event outcome is 0, and DRS is `0.5 × 0.5 + 0.5 × 0 = 0.25`. The preservation comparison uses empty before/after maps. This run records that behavior; it does not revise historical or active experiment scores.

The next harness improvements should clarify Linux execution and staged asset locations, and make submission/termination expectations easier for the agent to follow. Any change to the missing-artifact scoring rule requires a separate versioned scoring review and new measurements.

## Engineering checks and retained records

The full Track B regression suite passed **187 tests** before the final provider-reference compatibility patch. That patch passed **58 driver and isolation tests**, including its added regression. An independent read-only audit checked all four episode digests, public trace projections, model-call accounting and verifier results against their scores.

The installed CLI was also checked against a local mock Responses endpoint: every advertised tool was inspected, including nested `additional_tools`, and the native tool list was empty. Repository instructions, evaluator-private context and installed skill content were absent. Real probes separately verified main actions and the complete child schema with nested evidence.

Earlier attempts exposed transport reconnection handling, nested JSON argument escaping, and a provider restriction against keywords beside `$ref`. These were fixed before the reported source revision. Earlier raw records and interrupted workspaces remain separate and do not enter this table.

Maintainer-local records are retained under `artifacts/track-b-luna-live-v3/`: `manifest.json`, `config.yaml`, `provenance.json`, image verification, probes, four episode directories, `aggregate.json` and the case-wise `summary.json`. The summary's `event_source_sha256` hashes the canonical `event_source.jsonl` file. This public report contains aggregates and configuration only; account authentication and raw participant traces are not published.

For participant setup and customizable harness interfaces, see [Track B guide](../track-b.md).
