"""Re-produce OSWorld, SWE-bench and MultiAgentBench cases as native specs."""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
import jsonschema
import yaml
from huggingface_hub import hf_hub_download, list_repo_files

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.source_native_v4 import common_protocol, file_hash  # noqa: E402
from async_rbench.native_runtime_registry import qualification, read_registry  # noqa: E402
from async_rbench.unified_case_v3 import read_json, read_jsonl  # noqa: E402


TARGETS = {"OSWorld", "SWE-bench", "MultiAgentBench"}
REMOTE_ONLY_MULTI_SWE_FILES = {
    "ts/mui__material-ui_dataset.jsonl",
    "ts/vuejs__core_dataset.jsonl",
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    decoded = json.loads(value)
    return decoded if isinstance(decoded, list) else [decoded]


def git_revision(path: Path) -> str | None:
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def structured(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value


def test_names(value: Any) -> list[str]:
    parsed = structured(value)
    if isinstance(parsed, dict):
        return list(parsed)
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def official_swe(target_ids: set[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    sources = (
        ("princeton-nlp/SWE-bench", ("train", "dev", "test")),
        ("SWE-bench/SWE-bench_Verified", ("test",)),
        ("SWE-bench/SWE-bench_Multilingual", ("test",)),
        ("princeton-nlp/SWE-bench_Multimodal", ("dev", "test")),
    )
    for dataset, splits in sources:
        for split in splits:
            local = hf_hub_download(dataset, f"data/{split}-00000-of-00001.parquet", repo_type="dataset")
            columns = {row[0] for row in duckdb.execute("DESCRIBE SELECT * FROM read_parquet(?)", [local]).fetchall()}
            required = ["instance_id", "repo", "base_commit", "problem_statement", "FAIL_TO_PASS", "PASS_TO_PASS"]
            if not set(required).issubset(columns):
                continue
            query = "SELECT " + ",".join(required) + " FROM read_parquet(?)"
            for values in duckdb.execute(query, [local]).fetchall():
                record = dict(zip(required, values))
                record.update({"dataset": dataset, "split": split, "variant": "swe_bench", "harness": "swebench.harness.run_evaluation"})
                result[str(record["instance_id"])] = record

    pro_dataset = "ScaleAI/SWE-bench_Pro"
    pro_path = hf_hub_download(pro_dataset, "data/test-00000-of-00001.parquet", repo_type="dataset")
    pro_columns = [
        "instance_id", "repo", "base_commit", "problem_statement", "requirements", "interface",
        "fail_to_pass", "pass_to_pass", "dockerhub_tag", "selected_test_files_to_run",
    ]
    pro_query = "SELECT " + ",".join(pro_columns) + " FROM read_parquet(?)"
    for values in duckdb.execute(pro_query, [pro_path]).fetchall():
        record = dict(zip(pro_columns, values))
        instance_id = str(record["instance_id"])
        if instance_id not in target_ids:
            continue
        record["problem_statement"] = "\n\n".join(
            str(record.get(key) or "") for key in ("problem_statement", "requirements", "interface")
        ).strip()
        record["FAIL_TO_PASS"] = test_names(record.pop("fail_to_pass"))
        record["PASS_TO_PASS"] = test_names(record.pop("pass_to_pass"))
        record.update({"dataset": pro_dataset, "split": "test", "variant": "swe_bench_pro", "harness": "swe_bench_pro_eval.py"})
        result[instance_id] = record

    multi_dataset = "ByteDance-Seed/Multi-SWE-bench"
    unresolved_prefixes = {task_id.rsplit("-", 1)[0] for task_id in target_ids if task_id not in result and not task_id.startswith("instance_")}
    dataset_files = [path for path in list_repo_files(multi_dataset, repo_type="dataset") if path.endswith(".jsonl")]
    selected_files = []
    remote_only_prefixes = {Path(path).stem.removesuffix("_dataset") for path in REMOTE_ONLY_MULTI_SWE_FILES}
    for path in dataset_files:
        stem = Path(path).stem.removesuffix("_dataset")
        if path in REMOTE_ONLY_MULTI_SWE_FILES:
            continue
        if stem in unresolved_prefixes or (path == "python/multi_swe_bench_python.jsonl" and any(prefix not in {Path(p).stem.removesuffix("_dataset") for p in dataset_files} for prefix in unresolved_prefixes)):
            selected_files.append(path)
    for instance_id in target_ids:
        if instance_id.rsplit("-", 1)[0] in remote_only_prefixes:
            result[instance_id] = {"binding_blocker": "official_multi_swe_source_snapshot_not_materialized"}
    for dataset_file in selected_files:
        local = hf_hub_download(multi_dataset, dataset_file, repo_type="dataset")
        for line in Path(local).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            instance_id = str(payload.get("instance_id", ""))
            if instance_id not in target_ids or instance_id in result:
                continue
            base = structured(payload.get("base")) or {}
            problem = "\n\n".join(str(payload.get(key) or "") for key in ("title", "body", "resolved_issues")).strip()
            result[instance_id] = {
                "instance_id": instance_id,
                "repo": f"{payload.get('org')}/{payload.get('repo')}",
                "base_commit": base.get("sha") if isinstance(base, dict) else None,
                "problem_statement": problem,
                "FAIL_TO_PASS": test_names(payload.get("f2p_tests")),
                "PASS_TO_PASS": test_names(payload.get("p2p_tests")),
                "dataset": multi_dataset,
                "split": dataset_file,
                "variant": "multi_swe_bench",
                "harness": "multi_swe_bench.harness.run_evaluation",
                "dataset_file": dataset_file,
            }
    return result


def marble_tasks() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    result = {}
    invalid = []
    root = ROOT / "upstream" / "marble" / "multiagentbench"
    for scenario in ("bargaining", "coding", "database", "minecraft", "research"):
        path = root / scenario / f"{scenario}_main.jsonl"
        for line_number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                invalid.append({"scenario": scenario, "line_number": line_number, "reason": f"invalid_json:{exc.msg}"})
                continue
            if "task_id" not in payload or payload.get("scenario") != scenario:
                invalid.append({"scenario": scenario, "line_number": line_number, "reason": "missing_task_id_or_scenario_mismatch"})
                continue
            key = f"{scenario}:{int(payload['task_id']):03d}"
            result[key] = {"payload": payload, "path": path, "line_number": line_number}
    return result, invalid


def marble_semantic_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    agents = payload.get("agents") or []
    agent_ids = [agent.get("agent_id") for agent in agents if isinstance(agent, dict)]
    if len(agents) < 2 or len(set(agent_ids)) != len(agent_ids) or None in agent_ids:
        errors.append("invalid_or_duplicate_agents")
    valid_ids = set(agent_ids)
    for relationship in payload.get("relationships") or []:
        if not isinstance(relationship, list) or len(relationship) < 3 or relationship[0] not in valid_ids or relationship[1] not in valid_ids:
            errors.append("relationship_references_unknown_agent")
            break
    task = payload.get("task") or {}
    if len(str(task.get("content") or "").strip()) < 80:
        errors.append("task_content_missing_or_truncated")
    if not isinstance(payload.get("metrics"), dict) or not payload.get("metrics"):
        errors.append("metrics_missing")
    if payload.get("scenario") not in {"bargaining", "coding", "database", "minecraft", "research"}:
        errors.append("unsupported_scenario")
    return errors


def hydrated_marble_config(payload: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    """Apply the defaults required by MARBLE's own jsonl2yaml launcher."""
    scenario = str(payload["scenario"])
    environment_types = {
        "bargaining": "WorldSimulation",
        "coding": "Coding",
        "database": "DB",
        "minecraft": "Minecraft",
        "research": "Research",
    }
    config = json.loads(json.dumps(payload))
    config["coordinate_mode"] = config.get("coordinate_mode") or "graph"
    config["llm"] = config.get("llm") or "${MARBLE_MODEL}"
    environment = config.setdefault("environment", {})
    environment["type"] = environment.get("type") or environment_types[scenario]
    environment["name"] = environment.get("name") or f"{scenario.title()} Environment"
    environment["max_iterations"] = environment.get("max_iterations") or 5
    if scenario == "coding":
        environment["workspace_dir"] = str((case_dir / "workspace").resolve())
    memory = config.setdefault("memory", {})
    memory["type"] = memory.get("type") or "BaseMemory"
    metrics = config.setdefault("metrics", {})
    metrics["evaluate_llm"] = metrics.get("evaluate_llm") or "${MARBLE_EVALUATOR_MODEL}"
    output = config.setdefault("output", {})
    output["file_path"] = str((case_dir / "result" / "native_output.jsonl").resolve())
    return config


def write_native_assets(
    case_dir: Path,
    spec: dict[str, Any],
    benchmark: str,
    source_payload: dict[str, Any],
) -> None:
    if benchmark == "OSWorld":
        binding = spec["source_binding"]
        write_json(case_dir / "task_meta.json", {binding["domain"]: [binding["task_id"]]})
        write_json(case_dir / "participant_task.json", {
            "case_id": spec["case_id"],
            "benchmark": benchmark,
            "instruction": source_payload["instruction"],
        })
    elif benchmark == "SWE-bench":
        evaluator = spec["native_evaluator"]
        write_json(case_dir / "evaluation_binding.json", {
            "dataset_name": evaluator["dataset"],
            "instance_ids": evaluator["instance_id"],
            "run_id": spec["case_id"],
            "max_workers": 1,
        })
        write_json(case_dir / "participant_task.json", {
            "case_id": spec["case_id"],
            "benchmark": benchmark,
            "problem_statement": source_payload["problem_statement"],
        })
    else:
        write_json(case_dir / "official_task.json", source_payload)
        write_json(case_dir / "participant_task.json", {
            "case_id": spec["case_id"],
            "benchmark": benchmark,
            "task": source_payload["task"],
        })
        hydrated = hydrated_marble_config(source_payload, case_dir)
        (case_dir / "native_config.yaml").write_text(
            yaml.safe_dump(hydrated, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )


def prune_stale_case_directories(output: Path, ready: list[dict[str, Any]]) -> int:
    cases_root = (output / "cases").resolve()
    if not cases_root.is_dir():
        return 0
    expected = {(output / row["native_path"]).resolve() for row in ready}
    removed = 0
    for benchmark_dir in cases_root.iterdir():
        if not benchmark_dir.is_dir():
            continue
        for case_dir in benchmark_dir.iterdir():
            resolved = case_dir.resolve()
            if not resolved.is_relative_to(cases_root):
                raise RuntimeError(f"refusing to prune path outside cases root: {resolved}")
            if case_dir.is_dir() and resolved not in expected:
                shutil.rmtree(resolved)
                removed += 1
    return removed


def osworld_spec(row: dict[str, Any], public: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    parts = str(row["source_task_id"]).split(":")
    if len(parts) < 3:
        return None, "invalid_osworld_task_id"
    domain, task_uuid = parts[-2], parts[-1]
    config = ROOT / "upstream" / "osworld" / "evaluation_examples" / "examples" / domain / f"{task_uuid}.json"
    if not config.is_file():
        return None, "official_osworld_config_missing"
    task = read_json(config)
    if not (task.get("evaluator") or {}).get("func"):
        return None, "official_osworld_evaluator_missing"
    protocol = common_protocol()
    return {
        "schema_version": "async-rbench-source-native-case-v4",
        "case_id": row["case_id"],
        "benchmark": "OSWorld",
        "source_binding": {
            "task_id": task_uuid, "domain": domain, "config_path": str(config.relative_to(ROOT)).replace("\\", "/"),
            "config_sha256": file_hash(config), "upstream_revision": git_revision(ROOT / "upstream" / "osworld"),
        },
        "native_runtime": {"adapter": "osworld.DesktopEnv", "snapshot": task.get("snapshot"), "provider": "vmware_or_docker", "final_state": "persisted VM state"},
        "event_protocol": {
            "producer": "read-only worker on a snapshot clone executes the delegable extraction/reproduction subtask",
            "payload": "raw extracted artifact, observation, or verifier output; never expected actions",
            "release_predicate": "official setup completed and main VM state differs from reset snapshot",
            "rollback": "main agent must repair the already-mutated VM state after delivery",
        },
        "state_attestation": {
            "baseline_probe": "OSWorld reset snapshot id plus native evaluator target-state digest",
            "checkpoint_probe": "harness-owned VM observation/artifact digest after an actual pyautogui action",
            "change_required": True,
            "journal_owner": "host harness outside the model-visible VM",
        },
        "modes": protocol,
        "native_evaluator": task["evaluator"],
        "quality_gates": {"official_config_bound": True, "native_evaluator_bound": True, "answer_catalogue_removed": True, "runtime_executed": False},
    }, None


def swe_spec(row: dict[str, Any], public: dict[str, Any], official: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    instance_id = str(row["source_task_id"])
    record = official.get(instance_id)
    if record is None:
        return None, "official_swe_instance_unresolved"
    if record.get("binding_blocker"):
        return None, str(record["binding_blocker"])
    fail_to_pass = json_list(record["FAIL_TO_PASS"])
    if not fail_to_pass:
        return None, "official_swe_fail_to_pass_empty"
    protocol = common_protocol()
    variant = record.get("variant", "swe_bench")
    harness_revisions = {
        "swe_bench": git_revision(ROOT / "upstream" / "swe-bench-harness"),
        "multi_swe_bench": git_revision(ROOT / "upstream" / "multi-swe-bench"),
        "swe_bench_pro": git_revision(ROOT / "upstream" / "swe-bench-pro"),
    }
    return {
        "schema_version": "async-rbench-source-native-case-v4",
        "case_id": row["case_id"],
        "benchmark": "SWE-bench",
        "source_binding": {
            "instance_id": instance_id, "repo": record["repo"], "base_commit": record["base_commit"],
            "dataset": record["dataset"], "split": record["split"], "variant": variant,
            "problem_statement_sha256": __import__("hashlib").sha256(str(record["problem_statement"]).encode()).hexdigest(),
            "harness_revision": harness_revisions[variant],
        },
        "native_runtime": {"adapter": record["harness"], "isolation": "official Docker instance image", "final_state": "git working tree patch"},
        "event_protocol": {
            "producer": "independent reproduction/test worker in a clean clone of the same base commit",
            "payload": "raw command, exit status, and bounded stdout/stderr from selected reproduction tests",
            "release_predicate": "main working tree has a non-empty persisted diff while worker is running",
            "rollback": "post-result patch history remains; the agent must amend/revert real files",
        },
        "state_attestation": {
            "baseline_probe": "git HEAD plus clean index/worktree digest",
            "checkpoint_probe": "git diff --binary plus untracked-file content digest",
            "change_required": True,
            "journal_owner": "host harness outside /testbed",
        },
        "modes": protocol,
        "native_evaluator": {
            "entrypoint": record["harness"], "dataset": record["dataset"],
            "instance_id": instance_id, "FAIL_TO_PASS": fail_to_pass,
            "PASS_TO_PASS": json_list(record["PASS_TO_PASS"]),
            "docker_image": record.get("dockerhub_tag"),
            "selected_test_files": structured(record.get("selected_test_files_to_run")),
        },
        "quality_gates": {"official_instance_bound": True, "native_tests_bound": True, "answer_catalogue_removed": True, "runtime_executed": False},
    }, None


def marble_spec(row: dict[str, Any], public: dict[str, Any], tasks: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    task_id = str(row["source_task_id"])
    record = tasks.get(task_id)
    if record is None:
        return None, "official_marble_task_missing"
    payload = record["payload"]
    semantic_errors = marble_semantic_errors(payload)
    if semantic_errors:
        return None, "official_marble_semantic_gate:" + ",".join(semantic_errors)
    protocol = common_protocol()
    return {
        "schema_version": "async-rbench-source-native-case-v4",
        "case_id": row["case_id"],
        "benchmark": "MultiAgentBench",
        "source_binding": {
            "task_id": task_id, "scenario": payload["scenario"],
            "jsonl_path": str(record["path"].relative_to(ROOT)).replace("\\", "/"), "line_number": record["line_number"],
            "record_sha256": __import__("hashlib").sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            "upstream_revision": git_revision(ROOT / "upstream" / "marble"),
        },
        "native_runtime": {"adapter": "marble.engine.Engine", "environment": payload.get("environment"), "roles": payload.get("agents"), "final_state": "MARBLE environment and tool transcript"},
        "event_protocol": {
            "producer": "an actual MARBLE role executes with its declared profile and tools",
            "payload": "the role's native message/tool result with provenance and logical clock",
            "release_predicate": "coordinator committed at least one environment action after launching the role",
            "rollback": "messages and tool calls remain in the native transcript; correction is additive and auditable",
        },
        "state_attestation": {
            "baseline_probe": "serialized MARBLE environment state and transcript sequence zero",
            "checkpoint_probe": "environment digest plus strictly increased native tool/action sequence",
            "change_required": True,
            "journal_owner": "MARBLE engine logger, not an agent workspace file",
        },
        "modes": protocol,
        "native_evaluator": {"metrics": payload.get("metrics"), "agreement_or_environment_state": True},
        "quality_gates": {"official_scenario_bound": True, "native_roles_bound": True, "answer_catalogue_removed": True, "runtime_executed": False},
    }, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild-manifest", default="artifacts/unified-case-set-v3/03-unified-production/rebuild_manifest.jsonl")
    parser.add_argument("--unified-root", default="artifacts/unified-case-set-v3/03-unified-production")
    parser.add_argument("--output", default="artifacts/source-native-v4")
    parser.add_argument("--runtime-registry", default="artifacts/native-runtime-v4/runtime_registry.jsonl")
    args = parser.parse_args()
    rows = [row for row in read_jsonl(Path(args.rebuild_manifest).resolve()) if row["benchmark"] in TARGETS]
    unified_root = Path(args.unified_root).resolve()
    output = Path(args.output).resolve()
    schema = read_json(ROOT / "schemas" / "source_native_case_v4.schema.json")
    swe_ids = {str(row["source_task_id"]) for row in rows if row["benchmark"] == "SWE-bench"}
    official = official_swe(swe_ids)
    marble, invalid_marble_sources = marble_tasks()
    ready, blocked = [], []
    runtime_registry = read_registry(Path(args.runtime_registry).resolve())
    for row in rows:
        public = read_json(unified_root / row["path"] / "case.json")
        if row["benchmark"] == "OSWorld":
            spec, reason = osworld_spec(row, public)
        elif row["benchmark"] == "SWE-bench":
            spec, reason = swe_spec(row, public, official)
        else:
            spec, reason = marble_spec(row, public, marble)
        if spec is None:
            blocked.append({**row, "native_status": "source_blocked", "blocker": reason})
            continue
        runtime_ready, runtime_blocker = qualification(
            runtime_registry.get(str(row["case_id"])),
            benchmark=str(row["benchmark"]),
            source_task_id=str(row["source_task_id"]),
        )
        jsonschema.validate(spec, schema)
        case_dir = output / "cases" / row["benchmark"].lower().replace("-", "_") / row["case_id"]
        write_json(case_dir / "native_case.json", spec)
        if row["benchmark"] == "MultiAgentBench":
            source_payload = marble[str(row["source_task_id"])]["payload"]
        elif row["benchmark"] == "SWE-bench":
            source_payload = official[str(row["source_task_id"])]
        else:
            source_payload = read_json(ROOT / spec["source_binding"]["config_path"])
        write_native_assets(case_dir, spec, row["benchmark"], source_payload)
        record = {**row, "native_path": str(case_dir.relative_to(output)).replace("\\", "/"), "native_status": "spec_ready", "runtime_ready": runtime_ready, "runtime_blocker": runtime_blocker}
        ready.append(record)
    pruned_stale_case_count = prune_stale_case_directories(output, ready)
    write_jsonl(output / "native_manifest.jsonl", ready)
    write_jsonl(output / "blocked_manifest.jsonl", blocked)
    report = {
        "schema_version": "source-native-production-v4", "input_rebuild_count": len(rows),
        "spec_ready_count": len(ready), "source_blocked_count": len(blocked),
        "spec_ready_benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in ready).items())),
        "spec_ready_swe_variant_counts": dict(sorted(Counter(
            read_json(output / row["native_path"] / "native_case.json")["source_binding"].get("variant", "")
            for row in ready if row["benchmark"] == "SWE-bench"
        ).items())),
        "source_blocker_counts": dict(sorted(Counter(row["blocker"] for row in blocked).items())),
        "runtime_ready_count": sum(row["runtime_ready"] for row in ready),
        "runtime_blocker_counts": dict(sorted(Counter(row["runtime_blocker"] for row in ready if row["runtime_blocker"]).items())),
        "runtime_executed_count": 0,
        "formal_promotion_ready_count": 0,
        "pruned_stale_case_count": pruned_stale_case_count,
        "unindexable_upstream_marble_record_count": len(invalid_marble_sources),
        "unindexable_upstream_marble_records": invalid_marble_sources,
        "upstream_revisions": {
            "OSWorld": git_revision(ROOT / "upstream" / "osworld"),
            "SWE_harness": git_revision(ROOT / "upstream" / "swe-bench-harness"),
            "Multi_SWE_harness": git_revision(ROOT / "upstream" / "multi-swe-bench"),
            "SWE_Pro_harness": git_revision(ROOT / "upstream" / "swe-bench-pro"),
            "MARBLE": git_revision(ROOT / "upstream" / "marble"),
        },
    }
    write_json(output / "production_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
