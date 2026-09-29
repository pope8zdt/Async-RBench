# Registered-case provenance

- **Release:** `v11.0-paper`
- **Case ID:** `distributed-model-runtime`
- **Title:** Recover and deploy a real PyTorch model with distributed candidates and exact scheduler workload

## Source identity

- **Terminal-Bench** task `pytorch-model-recovery`; source snapshot `upstream/terminal-bench/original-tasks-locked/pytorch-model-recovery`
- **Terminal-Bench** task `torch-tensor-parallelism`; source snapshot `upstream/terminal-bench/original-tasks-locked/torch-tensor-parallelism`
- **Terminal-Bench** task `torch-pipeline-parallelism`; source snapshot `upstream/terminal-bench/original-tasks-locked/torch-pipeline-parallelism`
- **Terminal-Bench** task `llm-inference-batching-scheduler`; source snapshot `upstream/terminal-bench/original-tasks-locked/llm-inference-batching-scheduler`

## Transformation and review

This registered Async-RBench case preserves the source task objective and the
participant-visible executable materials needed to solve it. The benchmark
adds a bounded multi-workstream execution contract; controlled result delivery
and scoring are supplied only by the separately versioned judge bundle.

The frozen public case was manually reviewed for source identity,
participant-input sufficiency, executable task setup, and consistency between
the public instruction and artifact contract.

## Publication boundary

This record contains no event schedule, evaluator-only release condition,
event-response contract truth, verifier, oracle, reference solution, invalid
mutation, hidden test, or canonical answer. Those materials are excluded from
the public repository and are bound to the release through external digests.
