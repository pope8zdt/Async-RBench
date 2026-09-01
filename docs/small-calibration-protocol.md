# Small calibration protocol

The executable plan is `configs/calibration-plan.json`; operator instructions are in `EXPERIMENT.md`.

The present stage runs every registered calibration instance in paired `linear` and `async` modes with `deepseek-v4-pro`, three repetitions, and seed `2026`. It is a one-model diagnostic of endpoint compatibility, resource ceilings, failure modes, token use, and point responsiveness.

Infrastructure failures may be retried once. Participant failures, invalid outputs, and turn-budget exhaustion are scored and are not retried. Raw artifacts and all configuration, case-bundle, scaffold, and verifier digests must be retained.

This stage cannot authorize contract freeze. Cross-model calibration still requires at least five models from at least three families, executed mutation evidence, cross-model point responses, and a zero-gap `calibration-audit` report.
