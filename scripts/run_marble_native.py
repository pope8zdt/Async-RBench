"""Fail-closed launcher for a real source-native MARBLE model episode."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.marble_runtime import (  # noqa: E402
    MARBLE_STAGING_ADAPTER,
    MARBLE_BENCHMARK,
    MarbleUpstreamBindings,
    episode_preflight,
    materialize_episode_config,
    provider_runtime_environment,
    provision_database_services,
    qualify_marble_case,
    stage_marble_runtime,
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one real MARBLE episode after checking Python, dependencies, "
            "provider credentials/endpoints, and scenario services."
        )
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--evaluator-model", required=True)
    parser.add_argument(
        "--python",
        default=None,
        help="Supported Python executable; default auto-discovers Python 3.9--3.11.",
    )
    parser.add_argument("--source-root", default="artifacts/source-native-v4")
    parser.add_argument("--upstream", default="upstream/marble")
    parser.add_argument(
        "--native-evidence-root",
        default="artifacts/native-runtime-v4/marble_native_environment",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preflight-only",
        action="store_true",
        help="Inspect prerequisites only; never provision or initialize an environment.",
    )
    mode.add_argument(
        "--initialize-only",
        action="store_true",
        help=(
            "Initialize actual Config/Engine/Environment/Evaluator and emit "
            "evidence, with Engine.start and all model calls disabled."
        ),
    )
    parser.add_argument(
        "--provision",
        action="store_true",
        help=(
            "For database cases, explicitly recreate the fixed MARBLE Compose "
            "project before native initialization and model launch."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.preflight_only and args.provision:
        print(
            "--preflight-only is non-destructive and cannot be combined with --provision",
            file=sys.stderr,
        )
        return 2
    source_root = (ROOT / args.source_root).resolve()
    upstream_root = (ROOT / args.upstream).resolve()
    manifest_path = source_root / "native_manifest.jsonl"
    if not manifest_path.is_file():
        print(f"source-native manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    matches = [
        row
        for row in read_jsonl(manifest_path)
        if row.get("benchmark") == MARBLE_BENCHMARK
        and str(row.get("case_id")) == args.case_id
    ]
    if len(matches) != 1:
        print(f"MARBLE case not found or duplicated: {args.case_id}", file=sys.stderr)
        return 2
    row = matches[0]
    case_dir = (source_root / str(row["native_path"])).resolve()
    cases_root = (source_root / "cases").resolve()
    if not case_dir.is_relative_to(cases_root):
        print("MARBLE native_path escapes source-native cases root", file=sys.stderr)
        return 2
    try:
        qualification = qualify_marble_case(
            case_dir,
            row,
            repository_root=ROOT,
            upstream_root=upstream_root,
            bindings=MarbleUpstreamBindings(upstream_root),
        )
    except Exception as exc:
        print(
            f"MARBLE manifest/source/config qualification failed: {type(exc).__name__}:{exc}",
            file=sys.stderr,
        )
        return 1
    with tempfile.TemporaryDirectory(prefix="dtbench-marble-") as directory:
        temporary_root = Path(directory)
        staged_upstream = stage_marble_runtime(
            upstream_root, temporary_root / "runtime"
        )
        provisioning = {
            "requested": bool(args.provision),
            "performed": False,
            "compose_project": "dtbench-marble-db-runtime",
            "ready": False,
            "error": None,
        }
        preflight = episode_preflight(
            case_dir,
            python=args.python,
            model=args.model,
            evaluator_model=args.evaluator_model,
            upstream_root=staged_upstream,
            initialize_native_environment=False,
            provider_credentials_required=not args.initialize_only,
        )
        if args.provision:
            if qualification.get("scenario") != "database":
                provisioning["error"] = (
                    "marble_provision_only_supported_for_database_cases"
                )
            else:
                provision_prerequisites = all(
                    value is True
                    for name, value in preflight.checks.items()
                    if name != "scenario_service_ready"
                )
                if not provision_prerequisites:
                    provisioning["error"] = (
                        "marble_database_provision_prerequisites_failed"
                    )
                else:
                    provisioned, provision_error = provision_database_services(
                        staged_upstream
                    )
                    provisioning["performed"] = True
                    provisioning["ready"] = provisioned
                    provisioning["error"] = provision_error
                    if provisioned:
                        preflight = episode_preflight(
                            case_dir,
                            python=args.python,
                            model=args.model,
                            evaluator_model=args.evaluator_model,
                            upstream_root=staged_upstream,
                            initialize_native_environment=False,
                            provider_credentials_required=not args.initialize_only,
                        )

        provisioning_failed = bool(args.provision and not provisioning["ready"])
        if (
            not args.preflight_only
            and preflight.ready
            and not provisioning_failed
        ):
            preflight = episode_preflight(
                case_dir,
                python=args.python,
                model=args.model,
                evaluator_model=args.evaluator_model,
                upstream_root=staged_upstream,
                initialize_native_environment=True,
                provider_credentials_required=not args.initialize_only,
                source_evidence=qualification["source_evidence"],
            )
        report_errors = list(preflight.errors)
        if provisioning["error"]:
            report_errors.append(str(provisioning["error"]))
        report_ready = preflight.ready and not provisioning_failed
        if preflight.native_environment_evidence is not None:
            database_runtime = preflight.native_environment_evidence.get(
                "database_runtime"
            )
            if isinstance(database_runtime, dict):
                provisioning["images"] = database_runtime.get("services")
        report = {
            "schema_version": "source-native-marble-episode-preflight-v2",
            "case_id": args.case_id,
            "source_task_id": row["source_task_id"],
            "scenario": qualification["scenario"],
            "status": (
                "native_prerequisites_validated"
                if args.preflight_only and report_ready
                else (
                    "native_environment_initialization_validated"
                    if report_ready
                    and preflight.native_environment_evidence is not None
                    else "native_preflight_failed"
                )
            ),
            "ready": report_ready,
            "checks": preflight.checks,
            "errors": list(dict.fromkeys(report_errors)),
            "execution_scope": "native_preflight",
            "model_episode_executed": False,
            "launch_mode": (
                "preflight_only"
                if args.preflight_only
                else "initialize_only" if args.initialize_only else "model_episode"
            ),
            "selected_python": preflight.command[0],
            "runtime_adapter": MARBLE_STAGING_ADAPTER,
            "upstream_mutated": False,
            "provisioning": provisioning,
            "command": list(preflight.command),
        }
        if preflight.native_environment_evidence is not None:
            evidence_root = (ROOT / args.native_evidence_root).resolve()
            evidence_root.mkdir(parents=True, exist_ok=True)
            evidence_path = evidence_root / f"{args.case_id}.json"
            temporary_evidence = evidence_path.with_suffix(".json.tmp")
            temporary_evidence.write_text(
                json.dumps(
                    preflight.native_environment_evidence,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            temporary_evidence.replace(evidence_path)
            report["native_environment_evidence"] = str(evidence_path)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        if not report_ready:
            return 1
        if args.preflight_only:
            return 0
        if args.initialize_only:
            return 0

        materialized = temporary_root / "native_config.yaml"
        materialize_episode_config(
            case_dir / "native_config.yaml",
            materialized,
            model=args.model,
            evaluator_model=args.evaluator_model,
        )
        environment = provider_runtime_environment(os.environ)
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = str(staged_upstream) + (
            os.pathsep + existing if existing else ""
        )
        environment["COMPOSE_PROJECT_NAME"] = "dtbench-marble-db-runtime"
        command = [
            preflight.command[0],
            "-m",
            "marble.main",
            "--config_path",
            str(materialized),
        ]
        completed = subprocess.run(
            command,
            cwd=staged_upstream,
            env=environment,
            check=False,
        )
        return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
