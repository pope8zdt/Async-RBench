# Configuration

> Current main experiment / 当前主实验：仅统计固定 47-case 清单，Linear/Async 各 3 次重复，每模型 282 次运行。历史 split 不作为主实验榜单筛选条件。统一入口与统计规则见 [formal-47](../experiments/formal-47/README.md)。

`model-profiles/` contains versioned model and adapter settings. Each profile declares its provider endpoint, model identifier, credential environment variable, runtime mode, fixed model-step horizons, and the shared emergency safety fuse.

The canonical v11.0.0 runtime fields are `max_main_steps`, `max_child_steps`, and
`emergency_total_token_cap`. Actual token use is diagnostic; profiles do not
declare normal token pools or pre-call token admission budgets. Official
profiles use a shared `5,000,000`-token emergency fuse per episode.

`calibration-plan.json` records an optional diagnostic calibration protocol. Repository validation checks the tracked definition for consistency, but v11.0.0 does not require executing it, producing a calibration audit, or meeting a model-panel minimum. Native-runtime dependency inputs and locks support the optional Marble and OSWorld source-native paths.

Credentials are read only from the environment variable named by each profile's `api_key_env`. Never store credentials in this directory.
