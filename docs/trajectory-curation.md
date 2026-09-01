# Trajectory-driven case curation

Async-RBench can prepare a low-cost review bundle from pre-existing
Terminal-Bench trajectories. No model inference is needed for manifest
selection or human review.

## 1. Build the review bundle

```powershell
python -m async_rbench.cli curation-init `
  --output artifacts/trajectory-curation `
  --per-task 4
```

The default source is the public Tracebench full manifest. The command filters
the exact task directories locked under
`upstream/terminal-bench/original-tasks-locked`, then selects a solved trace, an
unsolved trace and agent-diverse additional traces where available.

Add `--download-artifacts` only when raw archives are needed. Without it, the
bundle contains source URLs and review metadata but does not download large
trajectory files.

Outputs:

- `curation_summary.json`: per-task public trajectory coverage;
- `trajectory_reviews.jsonl`: machine screening, agent coarse-label fields and
  fixed-choice human fields;
- `trajectory_review.html`: local dropdown/checkbox review page;
- `decision_review.template.json`: schema-shaped template for an agent-proposed
  decision point;
- `choice_catalog.json`: every allowed single-choice and multi-choice value.

## 2. Read archives and run coarse screening

The screening entry point downloads only the selected public archives, reads
the three known Tracebench layouts (mini-SWE-agent, OpenHands and Terminus2),
and writes a common step format. It does not expose archived system prompts or
credential files in the normalized output.

First verify the entire pipeline without API cost:

```powershell
python -m async_rbench.cli curation-screen `
  --input artifacts/trajectory-curation/trajectory_reviews.jsonl `
  --output artifacts/trajectory-screening-smoke `
  --mode rules `
  --limit 3
```

Then use a model for the real coarse pass. The command reads the credential
from the environment variable named by the selected profile. The key stays in
the current process and is never written to an output file.

```powershell
python -m async_rbench.cli curation-screen `
  --input artifacts/trajectory-curation/trajectory_reviews.jsonl `
  --output artifacts/trajectory-screening-deepseek-v4-pro `
  --mode model `
  --config configs/model-profiles/deepseek-v4-pro.yaml `
  --task db-wal-recovery `
  --limit 1
```

`--task` and `--agent` are repeatable. Start with one trajectory, inspect the
result, then remove `--limit` for a batch. `rules` labels are only pipeline
triage and must not be promoted into case designs.

Outputs:

- `raw_artifacts/`: downloaded public archives;
- `normalized/`: readable steps with stable evidence IDs;
- `coarse_labels.jsonl`: validated agent outputs;
- `decision_candidates.jsonl`: choice-form human review records;
- `trajectory_reviews.screened.jsonl`: trajectory forms with the coarse result;
- `review_workspace.html`: source trace, coarse result and human choices side by side;
- `screening_summary.json`: counts, failures and model token use (never keys).

Open `review_workspace.html` in a browser. Evidence step numbers in a proposal
link back to the exact trace step. The page exports trajectory-level and
decision-level completed JSONL separately.

### Coarse-label contract

The coarse-label agent fills only `agent_coarse_label` and emits one decision
record per proposed causal branch using `decision_review.template.json`. It
must reference concrete trajectory step IDs. Free-form explanations are not a
substitute for evidence.

The coarse agent chooses from:

- trajectory quality and failure attribution;
- direct/indirect/no replanning evidence;
- research-event types such as late authority, stale risk, downstream
  invalidation, selective preservation, cancellation, redelegation and
  reverification;
- proposed topology role, capability target and relevance tier.

## 3. Human review by choices and judgments

For fast non-expert verification, render the neutral choice-only review. It
shows only the task goal and three source-linked evidence cards: prior work,
later information and the potentially affected action. Each card contains a
neutral summary plus short verbatim trajectory excerpts. It does not show the
screening verdict, confidence, proposed event label or final task outcome.

```powershell
python -m async_rbench.cli curation-simple-review `
  --input examples/simple-review/secure-release-demo.json `
  --output artifacts/human-review-demo/review.html
```

Schema-3 review batches ask four `yes` / `no` / `uncertain` questions: whether the
observation could arrive independently from another task or live environment, whether
it arrived after relevant work began, whether it requires at least one real plan
adjustment rather than an ordinary error/fix retry, and whether all summaries are
faithful to the cited evidence. Schema-2 historical demo records retain the earlier
three-question form for reproducibility.
An evidence mismatch returns to extraction rather than discarding the source
task. A non-late event and an event with no replanning need receive separate
routes. Any `uncertain` answer goes to a separate queue. Collect that queue and
render a blind second round with expanded context:

```powershell
python -m async_rbench.cli curation-collect-uncertain `
  --input examples/simple-review/secure-release-demo.json `
  --annotations examples/simple-review/demo-uncertain-annotation.jsonl `
  --output artifacts/human-review-demo/uncertain-round2.json

python -m async_rbench.cli curation-simple-review `
  --input artifacts/human-review-demo/uncertain-round2.json `
  --output artifacts/human-review-demo/review-round2.html
```

First-round answers are retained separately and are not shown to the second
reviewer. Records that remain uncertain after the second pass can be routed to
expert adjudication or quarantined according to event-coverage priority.
The page acknowledges submission without revealing whether the candidate was
confirmed or filtered, avoiding feedback-induced answer patterns.

To build a portable 30-50 record blind near-miss audit from normalized trajectories
and coarse decision proposals, keep at most one proposal per source trajectory:

```powershell
python -m async_rbench.cli curation-build-simple-batch `
  --normalized-dir artifacts/<batch>/rule-screening/normalized `
  --decisions artifacts/<batch>/rule-screening/decision_candidates.jsonl `
  --screening-labels artifacts/<batch>/model-screening/coarse_labels.jsonl `
  --output artifacts/<batch>/human-review --limit 50
```

Send annotators only `review.html` and the instructions, never the `internal/`
source map or model-screening results. The standalone page can be opened on another
computer and exports one JSONL file per reviewer.

### Turn a confirmed review into a candidate instance

The three human answers do not select an event family or write a verifier.
After a record is confirmed, a technical transformation plan must explicitly
name the target family, event schedule, affected scope, capability labels and
dataset split (`calibration`, `development`, or `test`) plus human approval. Build the immutable bridge record from the source evidence,
completed annotation and that plan:

```powershell
python -m async_rbench.cli curation-build-transformation-spec `
  --input artifacts/e2e-pilot/02-human-review/candidate-record.json `
  --annotations artifacts/e2e-pilot/02-human-review/confirmed-annotation.jsonl `
  --plan artifacts/e2e-pilot/03-transformation/transformation-plan.json `
  --output artifacts/e2e-pilot/03-transformation/transformation-spec.json
```

Only unanimously `candidate_confirmed` annotations with distinct reviewer IDs
can pass. The resulting specification states that the source trajectory is
discovery evidence, not an action-sequence oracle. Scaffold a complete
candidate from a registered template instance:

```powershell
python -m async_rbench.cli instance-scaffold `
  --spec artifacts/e2e-pilot/03-transformation/transformation-spec.json
```

This writes `candidate_instances/<family>/<instance>/`; it does not register
the instance. Mutation IDs are namespaced to the new instance, and the copied
task still has to pass the private verifier and the promotion gate below.

Prefer the combined `review_workspace.html`. The older
`trajectory_review.html` remains available when raw archives have not yet been
prepared. Human reviewers use
dropdowns and checkboxes; only evidence step IDs and an optional short note are
text fields. Export the completed JSONL from the page.

After the coarse agent produces `decision_candidates.jsonl`, render the second
review page:

```powershell
python -m async_rbench.cli curation-render `
  --kind decision `
  --input artifacts/trajectory-curation/decision_candidates.jsonl `
  --output artifacts/trajectory-curation/decision_review.html
```

Decision review asks yes/no/uncertain questions first:

- Can the source observation become a result returned by an independent async
  subtask? (The source trace itself need not contain subagents.)
- Would a different arrival order change the main agent's required response?
- Did it require a real plan change?
- Is the affected scope local, multi-branch or global?
- Is there an observable semantic and/or control consequence?
- Would the proposed benchmark point reveal the intended answer?

Only then does the reviewer accept/revise/reject it and choose a capability
target, relevance tier and topology roles. Acceptance is invalid unless the
trigger can be converted to an async result, arrival order matters, a plan
change is required, prompt leakage risk is `no`, the point scores above base
and evidence step IDs are supplied.

Validate exported reviews:

```powershell
python -m async_rbench.cli curation-validate `
  --kind trajectory `
  --input artifacts/trajectory-curation/trajectory_reviews.completed.jsonl

python -m async_rbench.cli curation-validate `
  --kind decision `
  --input artifacts/trajectory-curation/decision_reviews.completed.jsonl
```

Export only human-accepted, causally linked decisions into the transformation
backlog:

```powershell
python -m async_rbench.cli curation-export-candidates `
  --trajectory-input artifacts/trajectory-curation/trajectory_reviews.completed.jsonl `
  --decision-input artifacts/trajectory-curation/decision_reviews.completed.jsonl `
  --output artifacts/trajectory-curation/candidate_backlog.json
```

This export suggests compatible event themes but does not create an oracle,
modify a case, or register anything. Its records remain
`awaiting_case_transformation` until the public/private/task bundle is designed
and independently reviewed.

## 4. Promotion rule

A reviewed trajectory is evidence, not automatically a case design. A
decision point may be promoted only when the review establishes a causal async
trigger, required replanning, an observable consequence, no answer leakage and
specific source steps. Base-task completion checks remain allowed, but use the
lowest relevance tier and cannot exceed 20% of a case's total registered
weight.

## 5. Transform and promote an instance

Accepted evidence is copied into a transformed candidate bundle at:

`candidate_instances/<case_id>/<instance_id>/`

The directory must contain the complete protocol bundle plus:

- `candidate_metadata.json` conforming to
  `schemas/candidate-instance.schema.json`;
- completed trajectory and decision review JSONL files under the paths named
  by `candidate_metadata.json`;
- `mutation_families.json` covering the instance's frozen semantic and
  control-flow points;
- a `dataset_binding` and deterministic `difficulty_profile` in candidate metadata.
- `private/quality_contract.yaml`, which locks source-instruction fidelity, maps every
  scored claim to public evidence, declares a non-canonical positive solution and
  declares at least two executable negative mutations.

Human review confirms that the source trajectory and proposed async decision are
faithful. It does not certify task information sufficiency or verifier correctness.
Those are separate technical release gates.

For a new registered case, run the quality preflight before any model pilot. The
case family is assigned separately through its `primary_event_theme` classification:

```powershell
python -m async_rbench.cli candidate-quality-preflight `
  --candidate <case_id> --control-prefix <prefix> `
  --output artifacts/candidate-quality/<case_id>
```

The command runs the canonical Oracle, every declared equivalent implementation and
every declared negative mutation through byte-identical hidden verifier bundles. A
case fails if an equivalent implementation is rejected or a declared semantic error
survives.

Before the promotion dry run, execute the real release preflight into a new artifact
directory (the command refuses to overwrite an existing directory):

```powershell
python -m async_rbench.cli instance-preflight `
  --family <case_id> --candidate <instance_id> `
  --output artifacts/candidate-preflight/<case_id>/<instance_id>
```

`--family` is a legacy CLI parameter name and currently means `case_id`; it does
not mean one of the eight case-family classifications.

This builds the candidate, runs its Oracle and hidden verifier, then repeats isolated
verification for all declared equivalent solutions and negative mutations. It writes
digest-bound evidence only after every positive passes, every negative is killed at its
declared points, and all runs use the same verifier digest.

First run the non-mutating release gate:

```powershell
python -m async_rbench.cli instance-promote `
  --family <case_id> --candidate <instance_id> --dry-run
```

Only after a human checks that report may the same candidate be explicitly
promoted:

```powershell
python -m async_rbench.cli instance-promote `
  --family <case_id> --candidate <instance_id> --yes
```

Promotion is fail-closed: at least one accepted trajectory and one accepted
decision linked to it are required; all review, provenance, event taxonomy,
information-sufficiency, verifier registry and mutation-design gates must pass, and
source fidelity, public-evidence traceability, equivalence and executed-negative gates
must pass, and the executed quality evidence must match the current candidate bytes. The
command moves the bundle into `cases/<case_id>/instances/<instance_id>/` and
adds it to `cases/registry.json`. Merely placing files in either candidates or
instances never makes them official.
