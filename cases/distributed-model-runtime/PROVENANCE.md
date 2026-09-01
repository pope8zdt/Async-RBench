# Locked provenance

Source commit: `d28711d0da2675d0bb1d56de45ae5df6082438a3`.

- `pytorch-model-recovery`: exact `weights.pt` and `dataset.pt` used by the independent model branch;
- `torch-tensor-parallelism`: original API used for the provisional v1 candidate;
- `torch-pipeline-parallelism`: original API used by the authoritative-profile-compatible backend;
- `llm-inference-batching-scheduler`: exact request buckets used by downstream plans.

The transformation adds paired hardware profiles and cryptographic deployment lineage. Private scoring checks authority-driven backend selection, minimum usability of the selected runtime, regeneration of downstream plans, and exact deployment/lineage hashes. It deliberately does not rescore detailed TP/PP numerical conformance or the upstream scheduler optimization thresholds. Copied inputs and maintenance oracle scripts remain hash-verified.
