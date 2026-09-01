"""Batch actual MARBLE initialization for the 341 source-native cases.

The batch stages upstream once and imports MARBLE once, but constructs a fresh
official Config, Engine, scenario Environment, and Evaluator for every case.  It
never calls Engine.start or a model provider.  Evidence is case-local and atomic,
so interrupted batches can resume after strict validation.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.marble_runtime import (  # noqa: E402
    MARBLE_BENCHMARK,
    MarbleUpstreamBindings,
    database_service_image_evidence,
    discover_supported_python,
    materialize_episode_config,
    native_runtime_binding,
    provision_database_services,
    qualify_marble_case,
    stage_marble_runtime,
    validate_native_environment_evidence,
)
from async_rbench import marble_runtime  # noqa: E402


SCENARIOS = ("bargaining", "coding", "database", "research")


class BatchOutputLockUnavailable(RuntimeError):
    """Raised when another process owns this batch output directory."""


@contextmanager
def exclusive_batch_output_lock(path: Path):
    """Hold a non-blocking, process-scoped lock for one batch output root."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    acquired = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise BatchOutputLockUnavailable(
                f"MARBLE batch output is already locked: {path.parent}"
            ) from exc
        acquired = True
        yield
    finally:
        if acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                # Closing the descriptor below also releases the OS-owned lock.
                pass
        handle.close()


def evidence_matches_case(
    entry: dict[str, Any],
    row: dict[str, Any],
    qualification: dict[str, Any],
) -> tuple[bool, str | None]:
    """Bind resumable evidence to this exact manifest row and source case."""

    valid, reason = validate_native_environment_evidence(entry)
    if not valid:
        return valid, reason
    scenario = str(row.get("source_task_id") or "").split(":", 1)[0]
    if entry.get("case_id") != row.get("case_id"):
        return False, "marble_batch_case_id_binding_mismatch"
    if entry.get("source_task_id") != row.get("source_task_id"):
        return False, "marble_batch_source_task_id_binding_mismatch"
    if entry.get("scenario") != scenario:
        return False, "marble_batch_scenario_binding_mismatch"
    if entry.get("source_evidence") != qualification.get("source_evidence"):
        return False, "marble_batch_source_evidence_binding_mismatch"
    return True, None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=None)
    parser.add_argument("--source-root", default="artifacts/source-native-v4")
    parser.add_argument("--upstream", default="upstream/marble")
    parser.add_argument(
        "--database-runtime-root",
        default="artifacts/native-runtime-v4/marble_database_runtime_staging",
        help="Stable generated staging used by Compose bind mounts.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/native-runtime-v4/marble_native_initialization",
        help="Batch root; evidence is written to cases/ and summary to batch_report.json.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--provision-database", action="store_true")
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def run_batch(args: argparse.Namespace) -> int:
    source_root = (ROOT / args.source_root).resolve()
    upstream_root = (ROOT / args.upstream).resolve()
    batch_root = (ROOT / args.output).resolve()
    database_runtime_root = (ROOT / args.database_runtime_root).resolve()
    try:
        database_runtime_root.relative_to(ROOT)
    except ValueError:
        print("MARBLE database runtime staging must stay inside the workspace")
        return 2
    if database_runtime_root == ROOT:
        print("workspace root cannot be used as MARBLE database runtime staging")
        return 2
    output_root = batch_root / "cases"
    report_path = batch_root / "batch_report.json"
    scenarios = set(args.scenarios or SCENARIOS)
    rows = [
        row
        for row in read_jsonl(source_root / "native_manifest.jsonl")
        if row.get("benchmark") == MARBLE_BENCHMARK
        and str(row.get("source_task_id") or "").split(":", 1)[0] in scenarios
    ]
    rows.sort(key=lambda row: str(row["case_id"]))
    if args.limit is not None:
        rows = rows[: args.limit]
    full_collection_requested = args.scenarios is None and args.limit is None
    selection_error = None
    if not rows:
        selection_error = "marble_collection_selection_empty"
    elif full_collection_requested and len(rows) != 341:
        selection_error = (
            f"marble_full_collection_selection_count_mismatch:{len(rows)}:expected_341"
        )
    bindings = MarbleUpstreamBindings(upstream_root)
    qualification_failures = []
    qualified = []
    for row in rows:
        try:
            case_dir = (source_root / str(row["native_path"])).resolve()
            qualification = qualify_marble_case(
                case_dir,
                row,
                repository_root=ROOT,
                upstream_root=upstream_root,
                bindings=bindings,
            )
            qualified.append((row, case_dir, qualification))
        except Exception as exc:
            qualification_failures.append(
                {
                    "case_id": row.get("case_id"),
                    "error": type(exc).__name__ + ":" + str(exc)[:500],
                }
            )

    child_results: dict[str, dict[str, Any]] = {}
    infrastructure_error: str | None = selection_error
    selected_python, python_error = discover_supported_python(args.python)
    runtime_binding: dict[str, Any] | None = None
    if selected_python is None and infrastructure_error is None:
        infrastructure_error = python_error
    elif selected_python is not None and infrastructure_error is None:
        runtime_binding, binding_error = native_runtime_binding(
            selected_python, repository_root=ROOT
        )
        if runtime_binding is None:
            infrastructure_error = binding_error

    includes_database = any(
        str(row["source_task_id"]).startswith("database:")
        for row, _case_dir, _qualification in qualified
    )
    database_runtime = None
    if infrastructure_error is None and selected_python is not None and qualified:
        # This prerequisite pass is unconditional, including a fully resumed batch.
        # A stale JSON directory must not conceal a deleted venv or stopped DB stack.
        with tempfile.TemporaryDirectory(
            prefix="dtbench-marble-collection-preflight-"
        ) as directory:
            temporary_root = Path(directory)
            staged = stage_marble_runtime(upstream_root, temporary_root / "runtime")
            dependencies_ok, dependency_error = marble_runtime._dependency_probe(
                selected_python, staged
            )
            if not dependencies_ok:
                infrastructure_error = dependency_error
            if infrastructure_error is None and includes_database:
                if database_runtime_root.exists():
                    database_manifest = marble_runtime._validated_staging_manifest(
                        database_runtime_root
                    )
                    database_staged = (
                        database_runtime_root if database_manifest is not None else None
                    )
                else:
                    database_runtime_root.parent.mkdir(parents=True, exist_ok=True)
                    database_staged = stage_marble_runtime(
                        upstream_root, database_runtime_root
                    )
                if database_staged is None:
                    infrastructure_error = "marble_persistent_database_staging_invalid"
            if infrastructure_error is None and includes_database:
                if args.provision_database:
                    provisioned, provision_error = provision_database_services(
                        database_staged
                    )
                else:
                    provisioned, provision_error = marble_runtime._docker_ready(
                        database_staged
                    )
                if not provisioned:
                    infrastructure_error = provision_error
                else:
                    database_runtime, image_error = database_service_image_evidence(
                        database_staged
                    )
                    if database_runtime is None:
                        infrastructure_error = image_error

    skipped = []
    jobs = []
    for row, case_dir, qualification in qualified:
        evidence_path = output_root / (str(row["case_id"]) + ".json")
        if args.resume and infrastructure_error is None and evidence_path.is_file():
            try:
                existing = json.loads(evidence_path.read_text(encoding="utf-8"))
                valid, _reason = evidence_matches_case(existing, row, qualification)
            except Exception:
                valid = False
            if valid:
                skipped.append(str(row["case_id"]))
                continue
        jobs.append((row, case_dir, qualification))

    if (
        jobs
        and infrastructure_error is None
        and selected_python is not None
        and runtime_binding is not None
    ):
        with tempfile.TemporaryDirectory(
            prefix="dtbench-marble-collection-run-"
        ) as directory:
            temporary_root = Path(directory)
            staged = stage_marble_runtime(upstream_root, temporary_root / "runtime")
            if infrastructure_error is None:
                config_root = temporary_root / "configs"
                child_jobs = []
                for row, case_dir, qualification in jobs:
                    materialized = (
                        config_root / str(row["case_id"]) / "native_config.yaml"
                    )
                    materialize_episode_config(
                        case_dir / "native_config.yaml",
                        materialized,
                        model="offline/deterministic",
                        evaluator_model="offline/deterministic",
                    )
                    child_jobs.append(
                        {
                            "case_id": row["case_id"],
                            "source_task_id": row["source_task_id"],
                            "scenario": str(row["source_task_id"]).split(":", 1)[0],
                            "config": str(materialized),
                            "source_evidence": qualification["source_evidence"],
                        }
                    )
                staging_manifest = json.loads(
                    (staged / "STAGING_MANIFEST.json").read_text(encoding="utf-8")
                )
                bundle = {
                    "runtime_staging": {
                        "adapter": staging_manifest["adapter"],
                        "upstream_mutated": staging_manifest["upstream_mutated"],
                        "runtime_directories": staging_manifest["runtime_directories"],
                        "runtime_assets": staging_manifest["runtime_assets"],
                        "patches": staging_manifest["patches"],
                    },
                    "runtime_binding": runtime_binding,
                    "database_runtime": database_runtime,
                    "jobs": child_jobs,
                }
                jobs_path = temporary_root / "jobs.json"
                result_path = temporary_root / "result.json"
                atomic_json(jobs_path, bundle)
                child_environment = os.environ.copy()
                for name in list(child_environment):
                    if name.endswith("_API_KEY") or name in {
                        "DTBENCH2_OPENAI_KEY",
                        "AWS_SECRET_ACCESS_KEY",
                    }:
                        child_environment.pop(name, None)
                child_environment["PYTHONPATH"] = str(staged)
                child_environment["COMPOSE_PROJECT_NAME"] = "dtbench-marble-db-runtime"
                child_environment["DTBENCH_MARBLE_INITIALIZATION_PROBE"] = "1"
                log_path = batch_root / "batch.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                completed = None
                try:
                    with log_path.open("w", encoding="utf-8", newline="\n") as log_file:
                        completed = subprocess.run(
                            [
                                selected_python,
                                str(ROOT / "scripts/probe_marble_native_collection.py"),
                                "--jobs",
                                str(jobs_path),
                                "--output",
                                str(output_root),
                                "--result",
                                str(result_path),
                            ],
                            cwd=staged,
                            env=child_environment,
                            check=False,
                            stdout=log_file,
                            stderr=subprocess.STDOUT,
                            timeout=7200,
                        )
                except subprocess.TimeoutExpired:
                    infrastructure_error = "marble_collection_child_timeout"
                if result_path.is_file():
                    child_report = json.loads(result_path.read_text(encoding="utf-8"))
                    child_results = {
                        str(item["case_id"]): item
                        for item in child_report.get("results", [])
                    }
                elif completed is not None and completed.returncode != 0:
                    infrastructure_error = (
                        "marble_collection_child_failed_without_result"
                    )

    failures = list(qualification_failures)
    if infrastructure_error is not None:
        failures.append(
            {
                "case_id": None,
                "scenario": None,
                "error": infrastructure_error,
            }
        )
    validated = []
    for row, _case_dir, qualification in qualified:
        case_id = str(row["case_id"])
        evidence_path = output_root / (case_id + ".json")
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            valid, reason = evidence_matches_case(evidence, row, qualification)
        except Exception as exc:
            valid, reason = False, type(exc).__name__ + ":" + str(exc)[:300]
        if valid:
            validated.append(case_id)
        else:
            child = child_results.get(case_id) or {}
            failures.append(
                {
                    "case_id": case_id,
                    "scenario": str(row["source_task_id"]).split(":", 1)[0],
                    "error": child.get("error") or reason or infrastructure_error,
                }
            )

    selected_scenarios = Counter(
        str(row["source_task_id"]).split(":", 1)[0] for row in rows
    )
    validated_set = set(validated)
    validated_scenarios = Counter(
        str(row["source_task_id"]).split(":", 1)[0]
        for row in rows
        if str(row["case_id"]) in validated_set
    )
    report = {
        "schema_version": "marble-native-initialization-batch-v1",
        "status": (
            (
                "native_environment_initialization_validated"
                if full_collection_requested
                else "native_environment_initialization_subset_validated"
            )
            if rows and len(validated) == len(rows) and not failures
            else "native_environment_initialization_incomplete"
        ),
        "execution_scope": "native_runtime",
        "qualification_profile": "marble_native_environment_initialization_v1",
        "selected_python": selected_python,
        "runtime_binding": runtime_binding,
        "selected_count": len(rows),
        "full_collection_requested": full_collection_requested,
        "all_341_selected": len(rows) == 341,
        "full_collection_validated": (
            full_collection_requested
            and len(rows) == 341
            and len(validated) == 341
            and not failures
        ),
        "attempted_count": len(jobs),
        "resume_skipped_count": len(skipped),
        "validated_count": len(validated),
        "failed_count": len(failures),
        "scenario_counts": dict(sorted(selected_scenarios.items())),
        "validated_scenario_counts": dict(sorted(validated_scenarios.items())),
        "infrastructure_error": infrastructure_error,
        "claims": {
            "model_episode_executed": False,
            "gold_evaluator_executed": False,
            "task_scored": False,
            "native_checkpoint_validated": False,
        },
        "failures": failures,
    }
    atomic_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return (
        0 if rows and report["failed_count"] == 0 and len(validated) == len(rows) else 1
    )


def main() -> int:
    args = parse_args()
    batch_root = (ROOT / args.output).resolve()
    try:
        with exclusive_batch_output_lock(batch_root / ".batch.lock"):
            return run_batch(args)
    except BatchOutputLockUnavailable as exc:
        print(
            json.dumps(
                {
                    "status": "marble_collection_output_locked",
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
