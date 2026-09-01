"""Initialize many staged MARBLE cases in one Python 3.9 process.

This amortizes heavyweight imports while still constructing a new official Config,
Engine, scenario Environment, and Evaluator for every case.  Engine.start is never
called and no model provider method is invoked.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import tempfile
import time
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
        (
            getattr(litellm, "Router", None),
            ("completion", "acompletion"),
            "litellm.Router",
        ),
    ):
        if owner is None:
            continue
        for name in names:
            if hasattr(owner, name):
                setattr(owner, name, _forbid_model_call)
                PATCHED_MODEL_ENTRYPOINTS.append(prefix + "." + name)
    try:
        completion_module = importlib.import_module("openai.resources.chat.completions")
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
    PATCHED_MODEL_ENTRYPOINTS.append("marble.llms.model_prompting.model_prompting")


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


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(10):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.01)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--result", required=True)
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

    job_bundle = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    runtime_staging = job_bundle["runtime_staging"]
    runtime_binding = job_bundle["runtime_binding"]
    database_runtime = job_bundle.get("database_runtime")
    output_root = Path(args.output).resolve()
    results = []
    for job in job_bundle["jobs"]:
        case_id = job["case_id"]
        scenario = job["scenario"]
        try:
            config_path = Path(job["config"]).resolve()
            config = Config.load(str(config_path))
            engine = Engine(config)
            if class_entrypoint(engine) != "marble.engine.engine.Engine":
                raise RuntimeError("actual MARBLE Engine was not initialized")
            if not isinstance(engine.evaluator, Evaluator):
                raise RuntimeError("actual MARBLE Evaluator was not initialized")
            actual_environment = class_entrypoint(engine.environment)
            if actual_environment != ENVIRONMENT_CLASSES[scenario]:
                raise RuntimeError("actual MARBLE environment binding mismatch")
            if not hasattr(engine.environment, "reset"):
                raise RuntimeError("temporary environment reset adapter is missing")

            baseline_digest = digest(engine.environment.get_state())
            engine.environment.state["__dtbench_environment_healthcheck__"] = {
                "kind": "environment_healthcheck",
                "task_action": False,
            }
            healthcheck_digest = digest(engine.environment.get_state())
            reset_digest = digest(engine.environment.reset())
            if healthcheck_digest == baseline_digest or reset_digest != baseline_digest:
                raise RuntimeError("native environment reset healthcheck failed")

            evidence = {
                "schema_version": "source-native-marble-native-environment-v1",
                "case_id": case_id,
                "benchmark": "MultiAgentBench",
                "source_task_id": job["source_task_id"],
                "scenario": scenario,
                "status": "native_environment_initialization_validated",
                "execution_scope": "native_runtime",
                "qualification_profile": (
                    "marble_native_environment_initialization_v1"
                ),
                "runtime_adapter": "temporary_portable_marble_runtime_v1",
                "source_evidence": job["source_evidence"],
                "runtime_binding": runtime_binding,
                "checks": {
                    "actual_config_loaded": True,
                    "actual_engine_initialized": True,
                    "actual_environment_initialized": True,
                    "actual_evaluator_initialized": True,
                    "environment_healthcheck_changed_state": True,
                    "in_memory_control_plane_reset_reproducible": True,
                    "upstream_engine_start_not_called": (
                        CALL_AUDIT["engine_start_calls"] == 0
                    ),
                    "zero_model_calls": (CALL_AUDIT["model_entrypoint_calls"] == 0),
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
                    "healthcheck_state_sha256": healthcheck_digest,
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
                "runtime_staging": runtime_staging,
            }
            if scenario == "database":
                if database_runtime is None:
                    raise RuntimeError("database image identity evidence missing")
                evidence["database_runtime"] = database_runtime
                evidence["database_initialization_mode"] = {
                    "schema_reset_before_case": True,
                    "anomaly_adapter_validated": True,
                    "workload_anomaly_executed": False,
                    "workload_deferred_to_model_episode": True,
                }
            evidence["evidence_sha256"] = digest(evidence)
            evidence_path = output_root / (case_id + ".json")
            atomic_json(evidence_path, evidence)
            results.append(
                {"case_id": case_id, "scenario": scenario, "status": "validated"}
            )
            del engine
        except Exception as exc:
            results.append(
                {
                    "case_id": case_id,
                    "scenario": scenario,
                    "status": "failed",
                    "error": type(exc).__name__ + ":" + str(exc)[:500],
                }
            )
    result = {
        "schema_version": "marble-native-initialization-batch-child-v1",
        "engine_start_calls": CALL_AUDIT["engine_start_calls"],
        "model_calls": CALL_AUDIT["model_entrypoint_calls"],
        "patched_model_entrypoints": sorted(PATCHED_MODEL_ENTRYPOINTS),
        "results": results,
    }
    atomic_json(Path(args.result).resolve(), result)
    return 0 if all(item["status"] == "validated" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
