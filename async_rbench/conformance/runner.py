"""No-container conformance driver (Layer 4).

Runs a deterministic, protocol-only episode per case and evaluates the
conformance suite against the recorded event source. It never scores task
capability and never requires a model API or Docker.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..evaluation.runner import EpisodeConfig, run_episode
from ..profiles import AdapterProfile
from ..spec import case_instance_key, discover_case_instances
from .suite import run_checks


def conformance_adapter_command(
    profile: AdapterProfile,
    config_path: Path | None = None,
    base_command: list[str] | None = None,
) -> list[str]:
    """Resolve the deterministic, no-model/no-Docker command for a profile.

    Conformance never talks to a real model or Docker, so profiles whose adapter
    would otherwise default to an OpenAI backend are pinned to the scripted
    backend and a disabled workspace. ``config_path`` (when the adapter accepts
    one) supplies the participant's own config for validation.
    """
    command = list(base_command or profile.adapter_command)
    if profile.profile == "reference_scaffold_api":
        command += ["--backend", "scripted_test", "--workspace-mode", "disabled"]
        if config_path is not None and "--config" not in command:
            command += ["--config", str(config_path)]
    elif profile.profile in {"native_agent", "minimal_api", "conformance_mock"}:
        command += ["--workspace-mode", "disabled"]
    return command


async def run_conformance(
    root: Path,
    *,
    adapter_command: list[str] | None = None,
    profile: AdapterProfile | None = None,
    config_path: Path | None = None,
    output_dir: Path,
    case_ids: list[str],
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if adapter_command is None:
        if profile is None:
            raise ValueError("run_conformance requires adapter_command or profile")
        adapter_command = conformance_adapter_command(profile, config_path)
    results_by_case: dict[str, list[dict[str, Any]]] = {}
    instances = discover_case_instances(root, case_ids)
    total_cases = len(instances)
    for case_index, instance in enumerate(instances, start=1):
        case_id = instance.case_id
        instance_id = instance.instance_id
        instance_key = case_instance_key(case_id, instance_id)
        if progress is not None:
            progress(f"[DTB2 conformance {case_index}/{total_cases} {instance_key}] starting")
        episode_id = f"conformance-{case_id}-{instance_id}"
        episode_output = output_dir / episode_id
        config = EpisodeConfig(
            episode_id=episode_id,
            case_id=case_id,
            execution_mode="linear",
            guidance="incentive",
            agent_seed=1,
            adapter_command=adapter_command,
            output_dir=episode_output,
            instance_id=instance_id,
            use_container=False,
            timeout_sec=120,
        )
        await run_episode(root, config)
        trace_path = episode_output / "trace.jsonl"
        events = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        results_by_case[instance_key] = [
            check.as_dict()
            for check in run_checks(events, {
                "root": root, "case_id": case_id, "instance_id": instance_id,
            })
        ]
        if progress is not None:
            case_passed = all(item["passed"] for item in results_by_case[instance_key])
            progress(
                f"[DTB2 conformance {case_index}/{total_cases} {instance_key}] "
                f"{'passed' if case_passed else 'failed'}"
            )
    passed = all(
        result["passed"]
        for case_results in results_by_case.values()
        for result in case_results
    )
    result = {
        "conformance_passed": passed,
        "cases": results_by_case,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "conformance.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    return result
