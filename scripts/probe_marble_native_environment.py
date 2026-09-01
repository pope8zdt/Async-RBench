"""Child-process probe for the staged, actual MARBLE runtime.

This file intentionally supports Python 3.9 because upstream MARBLE pins 3.9--3.11.
It initializes Config, Engine, the scenario Environment, and Evaluator, but never
calls Engine.start() or a model provider.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path


ENVIRONMENT_CLASSES = {
    "bargaining": "marble.environments.world_env.WorldSimulationEnvironment",
    "coding": "marble.environments.coding_env.CodingEnvironment",
    "database": "marble.environments.db_env.DBEnvironment",
    "research": "marble.environments.research_env.ResearchEnvironment",
}
CALL_AUDIT = {"model_entrypoint_calls": 0, "engine_start_calls": 0}
PATCHED_MODEL_ENTRYPOINTS = []


def _forbid_model_call(*_args, **_kwargs):
    CALL_AUDIT["model_entrypoint_calls"] += 1
    raise RuntimeError("model calls are forbidden during native initialization")


def install_model_call_guards():
    import litellm

    for owner, names, prefix in (
        (litellm, ("completion", "acompletion"), "litellm"),
        (getattr(litellm, "Router", None), ("completion", "acompletion"), "litellm.Router"),
    ):
        if owner is None:
            continue
        for name in names:
            if hasattr(owner, name):
                setattr(owner, name, _forbid_model_call)
                PATCHED_MODEL_ENTRYPOINTS.append(prefix + "." + name)
    try:
        completion_module = importlib.import_module(
            "openai.resources.chat.completions"
        )
        for class_name in ("Completions", "AsyncCompletions"):
            owner = getattr(completion_module, class_name, None)
            if owner is not None and hasattr(owner, "create"):
                setattr(owner, "create", _forbid_model_call)
                PATCHED_MODEL_ENTRYPOINTS.append(
                    "openai.resources.chat.completions." + class_name + ".create"
                )
    except (ImportError, AttributeError):
        pass
    prompting_module = importlib.import_module("marble.llms.model_prompting")
    prompting_module.model_prompting = _forbid_model_call
    PATCHED_MODEL_ENTRYPOINTS.append(
        "marble.llms.model_prompting.model_prompting"
    )


def digest(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def class_entrypoint(value):
    cls = value.__class__
    return cls.__module__ + "." + cls.__name__


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--source-task-id", required=True)
    parser.add_argument("--scenario", required=True, choices=sorted(ENVIRONMENT_CLASSES))
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    install_model_call_guards()
    from marble.configs.config import Config
    from marble.engine.engine import Engine
    from marble.evaluator.evaluator import Evaluator

    def forbidden_engine_start(*_args, **_kwargs):
        CALL_AUDIT["engine_start_calls"] += 1
        raise RuntimeError("Engine.start is forbidden during native initialization")

    Engine.start = forbidden_engine_start

    config_path = Path(args.config).resolve()
    config = Config.load(str(config_path))
    engine = Engine(config)
    if engine.__class__.__module__ + "." + engine.__class__.__name__ != "marble.engine.engine.Engine":
        raise RuntimeError("actual MARBLE Engine was not initialized")
    if not isinstance(engine.evaluator, Evaluator):
        raise RuntimeError("actual MARBLE Evaluator was not initialized")
    expected_environment = ENVIRONMENT_CLASSES[args.scenario]
    actual_environment = class_entrypoint(engine.environment)
    if actual_environment != expected_environment:
        raise RuntimeError(
            "MARBLE environment mismatch: expected %s, got %s"
            % (expected_environment, actual_environment)
        )
    if not hasattr(engine.environment, "reset"):
        raise RuntimeError("temporary environment reset adapter is missing")

    baseline_state = engine.environment.get_state()
    baseline_digest = digest(baseline_state)
    engine.environment.state["__dtbench_environment_healthcheck__"] = {
        "kind": "environment_healthcheck",
        "task_action": False,
    }
    mutated_digest = digest(engine.environment.get_state())
    if mutated_digest == baseline_digest:
        raise RuntimeError("native environment healthcheck did not mutate state")
    reset_state = engine.environment.reset()
    reset_digest = digest(reset_state)
    if reset_digest != baseline_digest:
        raise RuntimeError("native environment reset was not reproducible")

    evidence = {
        "schema_version": "source-native-marble-native-environment-v1",
        "case_id": args.case_id,
        "benchmark": "MultiAgentBench",
        "source_task_id": args.source_task_id,
        "scenario": args.scenario,
        "status": "native_environment_initialization_validated",
        "execution_scope": "native_runtime",
        "qualification_profile": "marble_native_environment_initialization_v1",
        "runtime_adapter": "temporary_portable_marble_runtime_v1",
        "checks": {
            "actual_config_loaded": True,
            "actual_engine_initialized": True,
            "actual_environment_initialized": True,
            "actual_evaluator_initialized": True,
            "environment_healthcheck_changed_state": True,
            "in_memory_control_plane_reset_reproducible": True,
            "upstream_engine_start_not_called": CALL_AUDIT["engine_start_calls"] == 0,
            "zero_model_calls": CALL_AUDIT["model_entrypoint_calls"] == 0,
        },
        "call_audit": {
            "engine_start_calls": CALL_AUDIT["engine_start_calls"],
            "model_entrypoint_calls": CALL_AUDIT["model_entrypoint_calls"],
            "patched_model_entrypoints": sorted(PATCHED_MODEL_ENTRYPOINTS),
        },
        "bindings": {
            "config": Config.__module__ + "." + Config.__name__,
            "engine": class_entrypoint(engine),
            "environment": actual_environment,
            "evaluator": class_entrypoint(engine.evaluator),
        },
        "state_evidence": {
            "initial_state_sha256": baseline_digest,
            "healthcheck_state_sha256": mutated_digest,
            "in_memory_reset_state_sha256": reset_digest,
            "host_state_snapshot": False,
        },
        "claims": {
            "model_episode_executed": False,
            "gold_evaluator_executed": False,
            "task_scored": False,
            "native_checkpoint_validated": False,
        },
        "materialized_config_sha256": hashlib.sha256(
            config_path.read_bytes()
        ).hexdigest(),
    }
    if args.scenario == "database":
        initialization_probe = (
            os.environ.get("DTBENCH_MARBLE_INITIALIZATION_PROBE") == "1"
        )
        evidence["database_initialization_mode"] = {
            "schema_reset_before_case": initialization_probe,
            "anomaly_adapter_validated": True,
            "workload_anomaly_executed": not initialization_probe,
            "workload_deferred_to_model_episode": initialization_probe,
        }
    evidence["evidence_sha256"] = digest(evidence)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
