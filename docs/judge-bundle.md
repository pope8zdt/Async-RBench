# Judge bundle access and setup

The public repository contains the framework and 200 participant-visible task
bundles. Task scoring additionally requires a separately distributed judge
bundle. There is no automatic judge download or online scoring endpoint.

## Request a compatible bundle

Use the [judge access request](https://github.com/pope8zdt/Async-RBench/issues/new?template=judge-access.yml)
to provide your repository commit, intended evaluation and runtime environment.
The maintainer must confirm availability, compatibility and a separate delivery
channel before you can run scoring. Request the `command-boundaries-v1` runtime
bundle for new runs. Opening an issue does not grant
access or establish that a compatible bundle is available.

Issues are public. Do not attach API keys, answers, hidden tests, ERCs, judge
files or private execution traces. Do not put personal contact details in the
request; agree on private delivery with the maintainer if needed.

## Check compatibility before running

Keep the supplied bundle outside this repository. It must include its release
manifest and match the public case identities and content digests. The
`v11.0-paper` name alone is not a compatibility check.

From an activated environment in the repository checkout:

```sh
git rev-parse HEAD
async-rbench validate-public
async-rbench validate-judge --judge-root <judge-root>
async-rbench certify-release --judge-root <judge-root>
```

Replace `<judge-root>` with the directory supplied through the agreed channel.
Do not proceed if a check fails. Do not use `--write-manifests` to force an old
bundle to match changed public tasks: maintainers must verify the task,
verifier and event bindings before generating new release manifests.

The current runtime scoring policy is `async-rbench-runtime-boundaries-1`.
It records evaluator-owned artifact state at command boundaries and uses the
runtime judge's frozen equal-weight requirements. A change restored within one
command is outside this observation scope. The bundle is for new runs, not a
reconstruction of the original paper's private ERCs. Paper results remain fixed.

For maintainers migrating an existing private bundle, the following creates a
new external directory, preserves existing tests and schedules, and refuses to
overwrite the source or write the judge inside the checkout:

```sh
python scripts/prepare_runtime_judge.py --source <existing-judge> --output <new-judge-root>
async-rbench validate-judge --judge-root <new-judge-root>
async-rbench certify-release --judge-root <new-judge-root>
```

This command does not download private materials or prove task-solving quality.
Do not regenerate either judge after starting an experiment. The strict optional
`--official-track` requires weighted ERCs and full-window operation evidence;
the ordinary runtime commands do not select it.

Once the requirements pass, follow the [evaluation commands](cli.md#evaluation)
with your local model profile. These runs can incur model API charges. Historical
paper results are retained separately and are not recomputed by setup checks.
