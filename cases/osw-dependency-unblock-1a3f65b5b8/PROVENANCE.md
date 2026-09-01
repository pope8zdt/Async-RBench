# osw-dependency-unblock-1a3f65b5b8

Source benchmark: `OSWorld`

Source task: `osworld:chrome:121ba48f-9e17-48ce-9bc6-a4fb17a7ebba`

Native evaluator: `is_added_to_steam_cart`

Primary event: `delayed_authoritative_result`

The participant image contains only the source instruction, public async protocol, and a payload-agnostic event consumer. Evaluator truth lives under `task/tests/fixtures/`; Oracle-only truth and event payloads live under `task/upstream_solutions/fixtures/` and are injected after participant isolation. The final state must consume the exact receipt and pass the task-specific OSWorld semantic checks.
