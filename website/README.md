# Async-RBench website

Website source under the main repository's `website/` directory. Real Track A configuration generation, reference documentation, and allowlisted main-47 experiment aggregates. Track B is browser-only simulation. Participants run evaluations on their own computers. GitHub Pages or Vercel hosts the static website. Participants submit cleared summaries through the repository's Track A GitHub issue form. Maintainers review them and update published data through a pull request and website rebuild. No online submission backend or independent public ranking verification is implemented.

## Develop

Node 22.13+; `npm ci`, `npm run dev`.

`npm run build:static` generates `out/` for GitHub Pages and Vercel. `npm run test:static` checks every exported route and local asset link. Optional `NEXT_PUBLIC_BASE_PATH=/repository-name` builds for a project subpath. All experiment detail routes are rendered at build time. Changes to results require a rebuild.

`npm run build` and `npm run build:static` both produce the static website. Run all commands in `website/`.

## Refresh real data

`python scripts/export_results.py PATH_TO_AUTHORIZED_BENCHMARK_CHECKOUT`

Only the fixed 47-case cohort and current four-model main panel are exported. The three repeated pairs produce 282 planned episodes per model. Statistics read manifest-bound score.json files and reject duplicate attempts. Original dataset splits are never a leaderboard filter. Incomplete runs expose coverage and provisional observations, not final 47-case scores. Only allowlisted summary fields are exported. Case paths, original manifests, credentials, hidden scoring material and raw traces stay outside this project. Each entry keeps a digest of the selection and all source manifest/score digests. These hashes do not certify scores or independently verify results.

## Verify

`python -m unittest discover -s tests -p 'test_*.py'`

`node --test tests/config.test.mjs`

`npx tsc --noEmit`

`npm run build`

Application-source lint: `npx oxlint app components/site-shell.tsx components/leaderboard.tsx components/evaluate-form.tsx lib`. The generated starter's unused UI catalog has pre-existing lint findings; it is retained unchanged, so repository-wide `npm run lint` is not clean.

## Hosting boundary

The root Pages workflow deploys only `website/out/`. Config generation runs in the browser and does not collect secrets. Real evaluation requires an authorized local checkout and working model provider. Participants control their host computers; container isolation does not keep scoring material secret from the host owner. File hashes support file comparison, not score attestation.

See [deployment instructions](docs/deployment.md) for GitHub Pages and Vercel. Vercel can import the same repository with Root Directory set to `website`.
