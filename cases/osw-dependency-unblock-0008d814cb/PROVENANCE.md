# osw-dependency-unblock-0008d814cb

Source benchmark: `OSWorld`

Source task: `osworld:chrome:a96b564e-dbe9-42c3-9ccf-b4498073438a`

Native evaluator: `is_expected_active_tab`

Primary event: `delayed_authoritative_result`

The participant image contains only the source instruction, public async protocol, and a payload-agnostic event consumer. Evaluator truth lives under `task/tests/fixtures/`; Oracle-only truth and event payloads live under `task/upstream_solutions/fixtures/` and are injected after participant isolation. The final state must consume the exact receipt and pass the task-specific OSWorld semantic checks.
