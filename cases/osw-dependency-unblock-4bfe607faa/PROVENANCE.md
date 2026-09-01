# osw-dependency-unblock-4bfe607faa

Source benchmark: `OSWorld`

Source task: `osworld:chrome:9f3f70fc-5afc-4958-a7b7-3bb4fcb01805`

Native evaluator: `check_url_and_content_include`

Primary event: `delayed_authoritative_result`

The participant image contains only the source instruction, public async protocol, and a payload-agnostic event consumer. Evaluator truth lives under `task/tests/fixtures/`; Oracle-only truth and event payloads live under `task/upstream_solutions/fixtures/` and are injected after participant isolation. The final state must consume the exact receipt and pass the task-specific OSWorld semantic checks.
