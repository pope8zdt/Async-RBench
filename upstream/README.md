# Optional upstream material

The registered case bundles under `cases/` are self-contained for the standard containerized Async-RBench evaluation path.

This directory is intentionally empty in Git. Local development copies may contain pinned third-party repositories, source caches, VM assets, and datasets used for provenance validation or source-native reconstruction. Those materials are large, have independent licenses, and may contain nested Git histories, so they are distributed separately.

For source-native setup, follow:

- `docs/osworld-environment-smoke.md`;
- `docs/marble-native-environment.md`;
- `docs/source_native_v4_rebuild_report.md`;
- `scripts/fetch_osworld_assets.py`;
- `scripts/bootstrap_marble_runtime.py`.

Do not commit local upstream checkouts or caches into this repository.
