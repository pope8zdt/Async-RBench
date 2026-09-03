# Optional upstream material

Registered bundles under `cases/` are self-contained for the standard containerized evaluation path.

Local copies under this directory may contain pinned third-party repositories, source caches, VM assets, or datasets used for provenance validation and source-native reconstruction. These large, separately licensed materials are intentionally excluded from Git.

Relevant setup guides and utilities:

- `docs/osworld-environment-smoke.md`;
- `docs/marble-native-environment.md`;
- `scripts/fetch_osworld_assets.py`;
- `scripts/bootstrap_marble_runtime.py`.

Do not commit upstream checkouts, caches, credentials, or nested Git histories.
