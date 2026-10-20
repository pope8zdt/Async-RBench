# Private pull-request review

Native PR intake, review reconciliation and durable summary synchronization run
in the private review repository. The owner authorized production activation on
2026-10-20 without a second-account or real-submission acceptance test. Local
lifecycle tests and non-posting deployment checks do not replace that unperformed
end-to-end test. No public PR should
contain original evidence, private task data, credentials or rejection reasons.

## Participant

1. Prepare the complete Async result set: 200 tasks, three repetitions, with the
   result manifest and original evidence bundle. Follow [the evaluation guide](../../README.md#evaluation).
2. Keep these files in a private submission repository. Each participant uses
   their own repository; do not grant participants access to the central review
   repository or to one another's submissions.
3. Commit `submission.json` and `evidence.zip` together at the root of a new branch,
   then open a PR to `main` in that same private repository. Record the agent/model, code revision,
   score-policy version, evidence digest and coverage in the PR description.
   The worker discovers open, non-draft PRs in installed participant repositories.
   No public intake issue or separate URL form is required.
4. Read the maintainer's review on that private PR. Revise the files if changes
   are requested. A changed commit invalidates earlier validation and approval.

The participant must explicitly grant the review App and the designated
maintainer access to this repository before they can inspect its PR. No such
grant is performed by the website. A repository owner can access its evidence;
“private” means it is not exposed to the public or other participants.

## Maintainer

1. Accept the participant's collaborator invitation to their private repository.
   They never join the central review repository. Inspect the private PR and
   validation receipt. Check the submitter's immutable
   GitHub user ID, repository identity and visibility, manifest coverage, evidence
   digests, policy version, and evaluator-verified scores.
2. Use **Review changes → Request changes** and enter a reason if evidence is
   insufficient. Close without merging to reject the PR. The worker includes the
   latest authorized changes-request reason in the private receipt.
   The review itself is the private receipt; do not copy the reason into public
   issues, logs or the leaderboard.
3. Use **Review changes → Approve** on the exact validated head commit. No slash
   command or local publishing command is needed. Merging is optional; closing
   without merging withdraws the entry. Approval by the submitter, another
   participant or an unlisted reviewer is not sufficient. New commits, dismissed
   approvals or conflicting current reviews block publication.
4. The trusted workflow publishes the approved summary only after it rechecks
   all conditions. No local publishing command should be required in the enabled
   service. The default schedule is every four hours, not immediate; maintainers
   can manually run the central workflow after activation. Raw evidence is never
   copied to the public repository, even after approval.

## Workflow contract

The workflow must run trusted code in `Async-RBench-reviews`, not code from the
submission's branch. PR contents are data, never executable instructions. It
must not check out participant code with publishing credentials, execute an
uploaded archive, or print raw evidence in logs. A `pull_request_review` event
from a different repository does not by itself reach the central workflow;
the intake adapter retrieves and verifies it through GitHub's API. The PR worker
accepts only central `schedule` and `workflow_dispatch` contexts, not PR event code.

The sequence is: discover private PR → bind head commit and author → validate
original evidence → retrieve current maintainer reviews → recheck head and
repository visibility → persist the decision privately → publish an allowlisted
summary → write a private receipt. Retries must be idempotent. A later withdrawal
must remove the summary. Any latest authorized changes request blocks approval.
Dismissed approvals, changed heads, drafts, revoked maintainer permissions and
unavailable source bindings remove the row on the next successful synchronization.
Never interpret a label, a successful participant-owned
check, or a PR merge alone as authorization to publish.

Only approved metadata, GitHub attribution, policy/version identifiers, coverage
and verified scores belong in `Async-RBench-community/community.json`. Do not
include private PR/repository URLs, trace paths, uploaded files or review text.
The website reads that summary into the Community tab. Its paper table continues
to use the unchanged paper dataset.

No model is called and no new evaluation is run by this worker. It checks original
file digests, recomputes aggregates from supplied scores, and validates policy and
coverage. This is not cryptographic proof that a participant ran the evaluator
honestly: maintainers must inspect provenance and evidence before approval.

Private Git checkpoints store the records and original bundles atomically. A new
worker restores and revalidates them; no evidence is uploaded as public artifacts
or caches. Public commits contain only the allowlisted summary. A published
receipt is sent only after the summary commit is confirmed. A failed withdrawal
is retried; an outage or Pages cache can leave an already served row temporarily
visible. The software never changes repository visibility or prevents an owner
from sharing their own files.

## Local verification — maintainer development checkout only

The following test and kit-generation commands refer to the maintainer's full
development checkout. Those test and deployment files are not included in the
public participant release. Participants only need the packaging command in
the submission template; they do not deploy or run the review worker.

Run `python -m pytest tests/test_private_pull_requests.py tests/test_private_pr_worker.py`.
The tests use real evidence validation and Git checkpoint/publication code with
synthetic 200-task × 3-repeat evidence and fake external responses. They perform
no live GitHub or model calls.

`python -m async_rbench.submissions.github_only.deployment --output dist/private-pr-kit`
prepares the disabled PR deployment kit locally. Do not run the Issue and PR
workers against one checkpoint. PR mode does not inherit legacy Issue approvals;
review any migration before switching modes.

To include an already prepared private policy/configuration pair, supply
`--policy <trusted-policy.json>` and `--config <review-config.json>` together.
Use a new output directory **outside the public project and HTTP preview roots**.
The builder checks the digest, disabled mode and fixed repository bindings before
creating output. It reads only those two input files, not neighboring credentials.
Only `private-review/` receives the pair; the public sibling packages do not.
The generated README separates eventual destinations and future approval gates.
This offline check does not validate secret values or authorize uploading the kit.

## Before activation — confirm with the owner

- Add **Pull requests: read-only** to the App after authorization. Retain Contents
  read and Issues write (used for PR conversation receipts). The App does not
  approve or merge PRs. Keep the owner's installation limited to
  `Async-RBench-reviews`; each participant separately selects their private
  repository and invites the human maintainer. Contents alone cannot read reviews.
- Configure the real frozen judge/corpus policy and its SHA-256, immutable
  maintainer IDs, App private key and summary-only publishing credential. The
  prepared maintainer ID is 273166710 (`pope8zdt`); verify before activation.
  `GITHUB_TOKEN` writes only the central private checkpoint. A fine-grained
  `SUMMARY_TOKEN` gets Contents write on only `Async-RBench-community`. Keep both
  the signing key and publishing secret in the central private repository.
- Confirm GitHub Actions activation and a zero-spend limit. Free quota is finite;
  availability of private-repository features depends on the account's plan.
- Explicitly approve Actions activation and summary publication. Actual test PRs
  require separate permission; the owner waived them for the current rollout.
  Only after activation approval set `mode: live`, `REVIEW_WRITES_APPROVED=true` and
  `FREE_ONLY_CONFIRMED=true`. These flags record confirmation; they do not enforce
  GitHub billing settings. Never use paid larger runners.
- Enable Pages on the summary repository and use the public-only
  `pr-site-config.example.json` with `enabled: true` only after the real service
  is ready. The site reads its `community.json` independently of paper results.

Generating the kit or building the site grants no access and enables no workflow.

GitHub references: [PR review API](https://docs.github.com/en/rest/pulls/reviews),
[Actions security](https://docs.github.com/en/actions/reference/security/secure-use),
and [branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).
