# osw-dependency-unblock-75855f9fc5

Source benchmark: `OSWorld`

Source task: `osworld:chrome:2ad9387a-65d8-4e33-ad5b-7580065a27ca`

Native evaluator: `is_expected_bookmarks`

Primary event: `delayed_authoritative_result`

The participant image contains only the source instruction, public async protocol, and a payload-agnostic event consumer. Evaluator truth lives under `task/tests/fixtures/`; Oracle-only truth and event payloads live under `task/upstream_solutions/fixtures/` and are injected after participant isolation. The final state must consume the exact receipt and pass the task-specific OSWorld semantic checks.
