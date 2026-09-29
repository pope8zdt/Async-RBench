# Paper artifact index

`experiment_manifest.json` is the publication-safe manifest for the main paper
experiment. It freezes the nine paper model labels, all 200 registered cases,
three repetitions, and the Batched/Async delivery pair. The Cartesian product
contains 10,800 episodes. Each episode is uniquely identified by
`model_id / execution_mode / case_id / repetition`.

The manifest includes the nine paper display names and runtime model
identifiers, the shared model/resource configuration, and public release,
framework, contract, and external judge-release digests. It includes no
credentials, provider endpoints, traces, answers, ERC truth, or verifier
contents. The corresponding private judge bundle is a reviewer/maintainer
artifact, not part of the GitHub publication. This separation implements the
paper's statement that verifiers and run bindings are available in the
supplement while private verifier data and credentials are excluded from the
public package.

Regenerate the file after release certification:

    python scripts/build_paper_manifest.py \
        --judge-root <private-judge-root> \
        --output paper_artifacts/experiment_manifest.json

Runtime API URLs, account routing, and secret environment values are
intentionally not recorded.
