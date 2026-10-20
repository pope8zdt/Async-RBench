# Submit results through a private PR

Use the [submission guide](https://pope8zdt.github.io/Async-RBench/submission-guide/)
to prepare a private PR. Automated checks run every four hours.

Create this repository with **Private** visibility. Never upload original evidence
to the public benchmark or template repository.

1. Create your own **Private** repository from this template. On a new branch,
   put `evidence.zip` and `submission.json` at the repository root.
   The ZIP contains the complete 200-task, three-repeat results, original traces,
   manifest, audit and receipt. Prepare both files locally with the command below.
2. Install **Async-RBench Review pope8zdt** on **only this repository**:
   https://github.com/apps/async-rbench-review-pope8zdt/installations/new
3. Invite **pope8zdt** as a collaborator so the maintainer can review privately.
   Open a pull request from your new branch to `main` in **this same private
   repository**. Do not create a public fork or PR. Mark it ready for review.
4. Read the validation receipt and maintainer review on that PR. Push corrections
   to the same branch; each new commit requires fresh validation and approval.
   After validation and approval, the next scheduled sync publishes only the summary.
   Checks run every four hours; GitHub scheduling and Pages caching can add delay. Closing the
   PR without merging or dismissing the approval withdraws it from the community
   results. No participant-owned workflow is needed.

## Prepare the files locally

From your installed benchmark checkout, save `metadata.json` with these four
public-summary fields. Use your actual model name and full code commit:

```json
{
  "agent": "My agent",
  "model": "MY_MODEL_ID",
  "organization": "My team",
  "code_revision": "REPLACE_WITH_YOUR_FULL_40_CHARACTER_COMMIT"
}
```

Run this single command, replacing the input paths with the existing artifacts
from your complete evaluation. The output directory must not already exist:

```text
python -m async_rbench.submissions.github_only.pack --runs results/runs --manifest results/manifest.json --audit results/audit.json --metadata metadata.json --output private-submission --consent-summary
```

It creates `private-submission/evidence.zip` and `submission.json` with the matching
digest. It does not run evaluations, contact GitHub, or upload anything. Upload
**only those two files to your private repository**, not this public template.
Local validation does not imply acceptance; maintainers verify the frozen policy
and original evidence separately. Never edit, truncate or fabricate run evidence
to pass validation; use correctly recorded originals without credentials.

Consent covers only the approved summary: agent/model/organization/code revision,
scores, coverage, submitter/reviewer usernames, review time and scoring policy.
Original evidence and rejection reasons remain private, including after approval.
Do not upload credentials. If they appear in the original artifacts, stop rather
than modifying evidence to pass the checks. Access is limited to you, anyone you explicitly add,
the designated human reviewer, and the review service through the App.

## What the maintainer does

- Read the validation receipt and inspect the original evidence. Automated checks
  verify integrity and protocol coverage; they are not proof of an honest run.
- Use GitHub **Approve** on the exact validated commit. The next sync publishes
  the approved summary automatically; no local command is needed. Merging is
  optional and does not substitute for approval.
- Use **Request changes** with a reason for corrections. To reject, write the
  reason in that review and close without merging. The participant sees the
  reason and receipt on this private PR, not on the public leaderboard.
- Dismiss an approval or close an unmerged PR to withdraw the result on the next
  successful sync. Every new commit needs a fresh validation and review.

Reviewers cannot approve their own submissions. Community results are separate
from the paper leaderboard. No participant-owned Actions workflow is required.
GitHub may send notifications according to your account preferences.
