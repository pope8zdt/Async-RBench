# Async-RBench unified case-set v3 report

## Outcome

The legacy 300-case capsule collection and expansion-v2 665-case collection
have been normalized into one 965-case v3 inventory.  The merge itself passes
schema, uniqueness, oracle, mutation, and CLI smoke checks.  Fine screening does
not promote any record to the formal benchmark: 960 require a source-native
rebuild and 5 are rejected.

## Unified inventory

| Benchmark | Cases |
| --- | ---: |
| GAIA2 | 223 |
| MultiAgentBench | 345 |
| OSWorld | 91 |
| SWE-bench | 229 |
| SentinelBench | 71 |
| Terminal-Bench | 6 |
| **Total** | **965** |

All cases use `async-rbench-unified-case-v3`, stable semantic IDs, seven
semantic families, a ReAct/Linear/Async scenario contract, and the same
mode-neutral outcome score in every mode.  Score-point counts range from 5 to
19 because they follow task-specific affected actions rather than a fixed
eight-point rubric.

## Source repair

Complete authoritative task text was restored for 143 SWE-bench records and
all 6 Terminal-Bench records.  Another 86 SWE-derived records do not resolve to
the official SWE-bench, Verified, Multilingual, or Multimodal tables used by the
repair pass; their clipped source text remains explicit and they are not
eligible for direct retention.

## Fine screening

Every case received two independent `gpt-5.6-sol` high-reasoning fixed-choice
reviews: a causal-methodology review and a benchmark-engineering review.  The
deterministic adjudicator requires both reviewers to return
`keep_normalized`; disagreements fail closed to `rebuild_required`.

| Fine-screen result | Legacy 300 | Expansion 665 | Total |
| --- | ---: | ---: | ---: |
| keep_normalized | 0 | 0 | 0 |
| rebuild_required | 299 | 661 | 960 |
| reject | 1 | 4 | 5 |

The causal reviewer returned 8 keep, 930 rebuild, and 27 reject decisions.  The
engineering reviewer returned 153 keep, 791 rebuild, and 21 reject decisions.
No keep decision overlapped, so the final keep set is empty.  Reviewer decisions
agree on 766/965 cases; all 199 disagreements are retained in the rebuild queue.

The dominant problems are missing source-native execution/evaluation,
unscoreable symbolic outcomes, truncated or unresolved source text, weak async
causality, generic affected-work templates, and answer/action leakage.  The
legacy set additionally has private-only stale work, non-independent review
provenance, and an async-specific fixed rubric.  The expansion set additionally
failed its collection-level empirical challenge gate.

The five rejected cases are four semantically corrupted MultiAgentBench product
negotiations (battery requirements attached to unrelated physical products and
then silently rewritten) and one Terminal-Bench case whose alleged independent
event is the focal model's own retrospective thought.

## Executability audit

- JSON Schema validation: 965/965
- unique case IDs: 965/965
- unique source tasks: 965/965
- ReAct oracle: 965/965
- Linear oracle: 965/965
- Async oracle: 965/965
- directed mutation checks: 7,177
- mutation escapes: 0
- CLI smoke: one case from each of six benchmarks, all three modes, 0 failures
- repository tests: 250 passed, 10 skipped

These checks establish normalized capsule executability; they do not establish
source-native replay or empirical Async difficulty.  Formal promotion remains
blocked until source-native environments are authored, each case is empirically
shown to preserve Linear feasibility while lowering Async performance, and a
formal dev/test split is frozen.
