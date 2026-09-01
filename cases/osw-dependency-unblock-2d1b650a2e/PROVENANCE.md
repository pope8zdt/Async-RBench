# osw-dependency-unblock-2d1b650a2e

Source benchmark: `OSWorld`

Source task: `osworld:chrome:030eeff7-b492-4218-b312-701ec99ee0cc`

Native evaluator: `exact_match`

Primary event: `delayed_authoritative_result`

The participant image contains only the source instruction, public async protocol, and a payload-agnostic event consumer. Evaluator truth lives under `task/tests/fixtures/`; Oracle-only truth and event payloads live under `task/upstream_solutions/fixtures/` and are injected after participant isolation. The final state must consume the exact receipt and pass the task-specific OSWorld semantic checks.
