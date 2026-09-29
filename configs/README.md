# Configuration

`evaluation-contract.json` and `dataset-policy.json` are the machine-readable
contracts for the v11.0.0 evaluation and public dataset.

`model-profiles/experiment-profile.template.yaml` is the public template for a
paper-protocol run. It fixes the v11.0.0 response horizons, concurrency limits,
timeouts, adapter runtime, and credential environment-variable fields without
publishing provider credentials or account routing.

`model-profiles/reference-config.example.yaml` is a minimal reference-scaffold
example. Copy a template to an untracked local directory before adding a model
endpoint or credential variable.

The native-runtime requirement inputs and locks support the optional OSWorld
and MARBLE execution paths used by corresponding task families.

The nine model configurations and 10,800-episode experiment matrix used in the
paper are recorded in [`paper_artifacts/experiment_manifest.json`](../paper_artifacts/experiment_manifest.json).
