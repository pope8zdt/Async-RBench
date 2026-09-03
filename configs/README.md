# Configuration

`model-profiles/` contains versioned model and adapter settings. Each profile declares its provider endpoint, model identifier, credential environment variable, runtime mode, and resource limits.

`calibration-plan.json` records the current development calibration protocol. Native-runtime dependency inputs and locks support the optional Marble and OSWorld source-native paths.

Credentials are read only from the environment variable named by each profile's `api_key_env`. Never store credentials in this directory.
