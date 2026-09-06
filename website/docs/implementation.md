# Main repository website integration

The user selected participant-local execution and GitHub Pages / Vercel hosting, then supplied pope8zdt/Async-RBench as the main repository. The remote main commit edf361af2e977677204c6bf7f945bfa426f903c0 matches the local v11.0.0 benchmark release.

- Website source lives in website/ and uses native Next.js static export.
- The root Pages workflow builds and checks website/out, then publishes only that artifact. Pull requests build without deploying.
- Vercel uses Root Directory website and the included vercel.json.
- Track A uses real configuration, documentation and diagnostic summaries; Track B is simulation.
- Public GitHub issue form collects cleared Track A summaries for manual maintainer review. It does not certify scores or automatically add rankings.
- Benchmark execution, task data, credentials and raw artifacts are outside the published website artifact.

Verification: existing exporter/configuration tests, TypeScript during static build, application lint, static route and subpath checks, and GitHub Actions deployment status after publication.
