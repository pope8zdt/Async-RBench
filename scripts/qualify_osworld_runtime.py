"""Qualify all source-native OSWorld cases with a local control-plane smoke.

This script is intentionally not a GUI benchmark runner.  It writes
``environment_smoke_validated`` evidence only: official source/dispatch
binding, deterministic start/reset, a changed local action-history revision,
and the pinned ``FAIL`` terminal evaluator path.  Real provider readiness is
reported separately and never inferred from the local smoke.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.native_runtime_registry import (  # noqa: E402
    ENVIRONMENT_SMOKE_READY_STATUS,
    read_registry,
    write_registry,
)
from async_rbench.osworld_runtime import (  # noqa: E402
    OSWorldDispatchCatalog,
    load_osworld_cases,
    probe_real_vm_provider,
    qualify_environment_smoke,
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _failure_entry(case: Any, exc: Exception, provider_probe: Any) -> dict[str, Any]:
    return {
        "schema_version": "source-native-runtime-qualification-v2",
        "case_id": case.case_id,
        "benchmark": "OSWorld",
        "source_task_id": case.source_task_id,
        "status": "validation_failed",
        "execution_scope": "infrastructure_smoke",
        "checks": {
            "real_vm_executed": False,
            "model_episode_executed": False,
            "official_task_setup_executed": False,
            "official_gold_metric_executed": False,
        },
        "real_vm_provider_preflight": provider_probe.as_dict(),
        "failure": {"type": type(exc).__name__, "message": str(exc)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-native-root", default="artifacts/source-native-v4")
    parser.add_argument("--upstream-root", default="upstream/osworld")
    parser.add_argument("--registry", default="artifacts/native-runtime-v4/runtime_registry.jsonl")
    parser.add_argument("--output", default="artifacts/native-runtime-v4/osworld-environment-smoke")
    parser.add_argument("--work-root")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--provider", default="docker")
    parser.add_argument("--path-to-vm")
    parser.add_argument("--docker-image", default="happysixd/osworld-docker")
    parser.add_argument("--no-registry-write", action="store_true")
    parser.add_argument(
        "--require-real-provider-ready",
        action="store_true",
        help="also fail if the non-mutating real-provider prerequisite check is not launch-ready",
    )
    args = parser.parse_args()

    source_native_root = (ROOT / args.source_native_root).resolve()
    upstream_root = (ROOT / args.upstream_root).resolve()
    cases = load_osworld_cases(
        ROOT,
        source_native_root=source_native_root,
        upstream_root=upstream_root,
    )
    requested = set(args.case_id)
    known = {case.case_id for case in cases}
    unknown = sorted(requested - known)
    if unknown:
        raise SystemExit("unknown OSWorld case id(s): " + ",".join(unknown))
    selected = [case for case in cases if not requested or case.case_id in requested]

    path_to_vm = Path(args.path_to_vm).resolve() if args.path_to_vm else None
    provider_probe = probe_real_vm_provider(
        upstream_root,
        provider=args.provider,
        path_to_vm=path_to_vm,
        docker_image=args.docker_image,
    )
    dispatch_identity = OSWorldDispatchCatalog(upstream_root).source_identity()
    output = (ROOT / args.output).resolve()
    entries: list[dict[str, Any]] = []

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.work_root:
        work_root = Path(args.work_root).resolve()
        work_root.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="dtbench-osworld-smoke-")
        work_root = Path(temporary.name)
    try:
        for case in selected:
            try:
                entry = qualify_environment_smoke(
                    case,
                    work_root / case.case_id,
                    provider_probe=provider_probe,
                    dispatch_identity=dispatch_identity,
                )
            except Exception as exc:  # A failed case is evidence, never readiness.
                entry = _failure_entry(case, exc, provider_probe)
            entries.append(entry)
            write_json(output / "cases" / f"{case.case_id}.json", entry)
    finally:
        if temporary is not None:
            temporary.cleanup()

    if not args.no_registry_write:
        registry_path = (ROOT / args.registry).resolve()
        registry = read_registry(registry_path)
        for entry in entries:
            registry[str(entry["case_id"])] = entry
        # Merge-at-write preserves all pre-existing SWE/MARBLE and unrelated rows.
        write_registry(registry_path, registry.values())

    ready = [entry for entry in entries if entry["status"] == ENVIRONMENT_SMOKE_READY_STATUS]
    score_counts = Counter(str(entry.get("score_probe", {}).get("score")) for entry in ready)
    report = {
        "schema_version": "osworld-environment-smoke-report-v1",
        "execution_scope": "infrastructure_smoke",
        "selected_case_count": len(selected),
        "environment_smoke_validated_count": len(ready),
        "failed_count": len(entries) - len(ready),
        "score_probe_counts": dict(sorted(score_counts.items())),
        "real_vm_provider_preflight": provider_probe.as_dict(),
        "real_vm_executed_count": 0,
        "model_episode_executed_count": 0,
        "official_task_setup_executed_count": 0,
        "official_gold_metric_executed_count": 0,
        "research_claim": "environment_runnable_smoke_only_not_gui_task_execution",
        "registry_merged": not args.no_registry_write,
        "failures": [
            {"case_id": entry["case_id"], "failure": entry.get("failure", {})}
            for entry in entries
            if entry["status"] != ENVIRONMENT_SMOKE_READY_STATUS
        ],
    }
    write_json(output / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    all_smokes_ready = len(ready) == len(selected) and len(selected) > 0
    provider_requirement_met = provider_probe.launch_ready or not args.require_real_provider_ready
    return 0 if all_smokes_ready and provider_requirement_met else 1


if __name__ == "__main__":
    raise SystemExit(main())

