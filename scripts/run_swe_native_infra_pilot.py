"""Validate one SWE case's image, gold evaluator, and async state checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.native_runtime_registry import READY_STATUS, read_registry, write_registry  # noqa: E402
from async_rbench.source_native_v4 import NativeEventBroker, canonical_hash, file_hash  # noqa: E402


def run(command: list[str], *, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command, capture_output=True, check=False, timeout=timeout)
    if check and result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{stderr}")
    return result


def docker_text(*args: str, timeout: int = 120) -> str:
    return run(["docker", *args], timeout=timeout).stdout.decode("utf-8", errors="replace").strip()


def container_state_revision(container: str) -> str:
    """Hash HEAD, tracked changes, and every untracked file's content."""
    head = run(["docker", "exec", container, "git", "-C", "/testbed", "rev-parse", "HEAD"]).stdout
    diff = run(["docker", "exec", container, "git", "-C", "/testbed", "diff", "--binary", "HEAD"]).stdout
    untracked_raw = run([
        "docker", "exec", container, "git", "-C", "/testbed", "ls-files", "--others", "--exclude-standard", "-z"
    ]).stdout
    digest = hashlib.sha256()
    digest.update(b"HEAD\0" + head + b"DIFF\0" + diff)
    for raw_name in sorted(part for part in untracked_raw.split(b"\0") if part):
        name = raw_name.decode("utf-8", errors="surrogateescape")
        posix = PurePosixPath("/testbed") / PurePosixPath(name)
        content_hash = run(["docker", "exec", container, "sha256sum", "--", str(posix)]).stdout
        digest.update(b"UNTRACKED\0" + raw_name + b"\0" + content_hash)
    return digest.hexdigest()


def validate_audit_chain(audit: list[dict[str, Any]]) -> bool:
    previous = "0" * 64
    for item in audit:
        record = dict(item)
        recorded_hash = record.pop("record_sha256", None)
        if record.get("previous_sha256") != previous or canonical_hash(record) != recorded_hash:
            return False
        previous = str(recorded_hash)
    return bool(audit)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def image_identity(image: str) -> dict[str, str]:
    payload = json.loads(docker_text("image", "inspect", image))
    if len(payload) != 1:
        raise RuntimeError(f"image inspect returned {len(payload)} records")
    item = payload[0]
    repo_digests = item.get("RepoDigests") or []
    return {"reference": image, "image_id": item["Id"], "repo_digest": repo_digests[0] if repo_digests else ""}


def load_official_test_patch(dataset: str, split: str, instance_id: str) -> str:
    """Load private evaluator tests for the isolated worker, never the participant prompt."""
    import duckdb
    from huggingface_hub import hf_hub_download

    parquet = hf_hub_download(dataset, f"data/{split}-00000-of-00001.parquet", repo_type="dataset")
    row = duckdb.execute(
        "SELECT test_patch FROM read_parquet(?) WHERE instance_id = ?",
        [parquet, instance_id],
    ).fetchone()
    if row is None or not str(row[0] or "").strip():
        raise RuntimeError(f"official test_patch missing for {instance_id}")
    return str(row[0])


def load_official_test_command(dataset: str, split: str, instance_id: str) -> str:
    """Ask the pinned official harness for the repository-native test command."""
    harness_python = ROOT / ".venv-swe-native" / "Scripts" / "python.exe"
    code = (
        "import json,sys; "
        "from swebench.harness.utils import load_swebench_dataset,make_test_spec; "
        "d,s,i=sys.argv[1:4]; t=make_test_spec(load_swebench_dataset(d,s,[i])[0]); "
        "lines=t.eval_script_list; marker=next(n for n,x in enumerate(lines) if 'Start Test Output' in x); "
        "print(json.dumps(lines[marker+1]))"
    )
    result = run([str(harness_python), "-c", code, dataset, split, instance_id], timeout=120)
    return str(json.loads(result.stdout.decode("utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--gold-report", required=True)
    parser.add_argument("--registry", default="artifacts/native-runtime-v4/runtime_registry.jsonl")
    parser.add_argument("--output", default="artifacts/native-runtime-v4/checkpoint-pilots")
    args = parser.parse_args()

    manifest_path = ROOT / "artifacts/source-native-v4/native_manifest.jsonl"
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    row = next((item for item in rows if item["case_id"] == args.case_id), None)
    if row is None or row["benchmark"] != "SWE-bench":
        raise SystemExit(f"unknown SWE case: {args.case_id}")
    case_spec = load_json(ROOT / "artifacts/source-native-v4" / row["native_path"] / "native_case.json")
    instance_id = str(case_spec["source_binding"]["instance_id"])
    gold_path = Path(args.gold_report).resolve()
    gold = load_json(gold_path)
    gold_resolved = (
        instance_id in gold.get("resolved_ids", [])
        and gold.get("infra_failure_instances") == 0
        and gold.get("error_instances") == 0
    )
    if not gold_resolved:
        raise SystemExit("gold evaluator has not resolved this instance cleanly")

    docker_text("info", timeout=30)
    identity = image_identity(args.image)
    suffix = uuid.uuid4().hex[:10]
    main_name = f"dtbench-main-{suffix}"
    worker_name = f"dtbench-worker-{suffix}"
    broker = NativeEventBroker(mode="async")
    worker: subprocess.Popen[bytes] | None = None
    test_patch_path: Path | None = None
    started_at = time.time()
    try:
        for name in (main_name, worker_name):
            docker_text("create", "--name", name, args.image, "sleep", "600")
            docker_text("start", name)
        test_patch = load_official_test_patch(
            str(case_spec["native_evaluator"]["dataset"]),
            str(case_spec["source_binding"]["split"]),
            instance_id,
        )
        native_test_command = load_official_test_command(
            str(case_spec["native_evaluator"]["dataset"]),
            str(case_spec["source_binding"]["split"]),
            instance_id,
        )
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", suffix=".patch", delete=False) as handle:
            handle.write(test_patch)
            test_patch_path = Path(handle.name)
        docker_text("cp", str(test_patch_path), f"{worker_name}:/tmp/dtbench-test.patch")
        baseline = container_state_revision(main_name)
        broker.launch(baseline)
        tests = case_spec["native_evaluator"]["FAIL_TO_PASS"]
        worker_command = (
            "source /opt/miniconda3/bin/activate && conda activate testbed && "
            f"cd /testbed && git apply /tmp/dtbench-test.patch && sleep 2 && {native_test_command}"
        )
        worker = subprocess.Popen(
            ["docker", "exec", worker_name, "bash", "-lc", worker_command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        run(["docker", "exec", main_name, "touch", "/testbed/.dtbench_checkpoint_probe"])
        checkpoint = container_state_revision(main_name)
        broker.commit_checkpoint(checkpoint)
        stdout, stderr = worker.communicate(timeout=300)
        worker_result = {
            "command_kind": "native_fail_to_pass_reproduction",
            "exit_code": worker.returncode,
            "stdout": stdout.decode("utf-8", errors="replace")[-12000:],
            "stderr": stderr.decode("utf-8", errors="replace")[-12000:],
            "selected_test_count": len(tests),
        }
        broker.complete_worker(worker_result)
        broker.deliver()
        final_revision = container_state_revision(main_name)
        broker.finalize(final_revision)
    finally:
        if worker is not None and worker.poll() is None:
            worker.kill()
        for name in (main_name, worker_name):
            run(["docker", "rm", "-f", name], check=False, timeout=30)
        if test_patch_path is not None:
            test_patch_path.unlink(missing_ok=True)

    chain_valid = validate_audit_chain(broker.audit)
    checkpoint_changed = broker.baseline_revision != checkpoint
    reproduction_executed = worker_result["exit_code"] in {0, 1} and any(
        marker in (worker_result["stdout"] + worker_result["stderr"]).lower()
        for marker in ("failed", "passed", "failures=", " ran ", "ok")
    )
    entry = {
        "schema_version": "source-native-runtime-qualification-v1",
        "case_id": row["case_id"],
        "benchmark": row["benchmark"],
        "source_task_id": row["source_task_id"],
        "status": READY_STATUS if gold_resolved and reproduction_executed and checkpoint_changed and chain_valid else "validation_failed",
        "checks": {
            "immutable_environment_bound": bool(identity["image_id"]),
            "gold_evaluator_resolved": gold_resolved,
            "native_reproduction_executed": reproduction_executed,
            "native_checkpoint_changed_state": checkpoint_changed,
            "audit_chain_valid": chain_valid,
        },
        "environment": identity,
        "gold_report": {"path": str(gold_path), "sha256": file_hash(gold_path)},
        "checkpoint_smoke": {
            "scope": "infrastructure_only_not_a_model_episode",
            "baseline_revision": broker.baseline_revision,
            "checkpoint_revision": checkpoint,
            "final_revision": final_revision,
            "worker_exit_code": worker_result["exit_code"],
            "worker_payload_sha256": canonical_hash(worker_result),
            "worker_output_tail": (worker_result["stdout"] + worker_result["stderr"])[-4000:],
            "audit": broker.audit,
        },
        "duration_seconds": round(time.time() - started_at, 3),
    }
    registry_path = (ROOT / args.registry).resolve()
    registry = read_registry(registry_path)
    registry[entry["case_id"]] = entry
    write_registry(registry_path, registry.values())
    output_path = (ROOT / args.output / f"{args.case_id}.json").resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(entry, ensure_ascii=True, indent=2))
    return 0 if entry["status"] == READY_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
