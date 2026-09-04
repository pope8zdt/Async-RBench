# Configuration

`model-profiles/` contains versioned model and adapter settings. Each profile declares its provider endpoint, model identifier, credential environment variable, runtime mode, fixed model-step horizons, and the shared emergency safety fuse.

The canonical v10.1 runtime fields are `max_main_steps`, `max_child_steps`, and
`emergency_total_token_cap`. Actual token use is diagnostic; profiles do not
declare normal token pools or pre-call token admission budgets.

`calibration-plan.json` records the current development calibration protocol. Native-runtime dependency inputs and locks support the optional Marble and OSWorld source-native paths.

Credentials are read only from the environment variable named by each profile's `api_key_env`. Never store credentials in this directory.
