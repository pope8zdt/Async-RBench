# osw-dependency-unblock-5c3a1789cf

Source benchmark: `OSWorld`

Source task: `osworld:chrome:1704f00f-79e6-43a7-961b-cedd3724d5fd`

Native evaluator: `check_direct_json_object`

Primary event: `delayed_authoritative_result`

The participant image contains only the source instruction, public async protocol, and a payload-agnostic event consumer. Evaluator truth lives under `task/tests/fixtures/`; Oracle-only truth and event payloads live under `task/upstream_solutions/fixtures/` and are injected after participant isolation. The final state must consume the exact receipt and pass the task-specific OSWorld semantic checks.
