"""Collect versioned authoritative traces and dynamic event graphs for screening.

The collector deliberately distinguishes real model execution traces from official
scenario/event graphs.  Both are useful discovery evidence, but the latter is never
reported as a model trajectory.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import struct
import subprocess
import sys
import urllib.request
import zipfile
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.gaia2_curation import read_gaia2_parquet  # noqa: E402
from async_rbench.multi_source import normalize_gaia2_scenario  # noqa: E402
from async_rbench.trajectory_curation import write_jsonl  # noqa: E402


OSWORLD_DATASET = "xlangai/ubuntu_osworld_verified_trajs"
OSWORLD_ZIP = "autoglm_15steps.zip"
OSWORLD_URL = (
    f"https://huggingface.co/datasets/{OSWORLD_DATASET}/resolve/main/{OSWORLD_ZIP}"
)
GAIA2_REVISION = "78ea3bdbdeec2bdcd6afa542091"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_text(value: str) -> str:
    return _sha_bytes(value.encode("utf-8"))


def _json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def _task_configs(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    output: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in (root / "evaluation_examples" / "examples").glob("*/*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        task_id = str(row.get("id") or path.stem)
        output[task_id] = (path, row)
    return output


def _osworld_steps(instruction: str, payload: bytes) -> list[dict[str, Any]]:
    steps = [{
        "step_id": 1, "role": "user", "kind": "task", "content": instruction,
        "source_ref": "osworld_task:instruction",
    }]
    for raw in payload.decode("utf-8", "replace").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        step_num = int(row.get("step_num") or len(steps))
        response = str(row.get("response") or "")
        action = str(row.get("action") or "")
        steps.append({
            "step_id": len(steps) + 1, "role": "agent", "kind": "action",
            "content": response, "command": action,
            "source_ref": f"osworld_trace:step:{step_num}",
        })
        if row.get("info") or row.get("reward") is not None:
            steps.append({
                "step_id": len(steps) + 1, "role": "environment",
                "kind": "observation",
                "content": json.dumps({
                    "reward": row.get("reward"), "done": row.get("done"),
                    "info": row.get("info") or {},
                }, ensure_ascii=False),
                "source_ref": f"osworld_trace:result:{step_num}",
            })
    return steps


def collect_osworld(repo: Path, limit: int) -> list[dict[str, Any]]:
    import fsspec
    import requests

    configs = _task_configs(repo)
    dataset = _json_url(f"https://huggingface.co/api/datasets/{OSWORLD_DATASET}")
    remote = fsspec.open(OSWORLD_URL, "rb", block_size=512 * 1024).open()
    archive = zipfile.ZipFile(remote)
    info_by_name = {item.filename: item for item in archive.infolist()}
    names = sorted(name for name in info_by_name if name.endswith("/traj.jsonl"))[:limit]
    probe = requests.get(OSWORLD_URL, headers={"Range": "bytes=0-0"}, timeout=60)
    probe.raise_for_status()
    signed_url = probe.url

    def read_member(info: zipfile.ZipInfo) -> bytes:
        # One bounded HTTP request contains the local ZIP header and compressed member.
        # This avoids downloading screenshots/video located between the text members.
        start = int(info.header_offset)
        end = start + 30 + int(info.compress_size) + 8192
        response = requests.get(
            signed_url, headers={"Range": f"bytes={start}-{end}"}, timeout=90,
        )
        response.raise_for_status()
        if response.status_code != 206:
            raise RuntimeError(f"remote ZIP server ignored byte range for {info.filename}")
        header = response.content[:30]
        values = struct.unpack("<IHHHHHIIIHH", header)
        if values[0] != 0x04034B50:
            raise RuntimeError(f"invalid local ZIP header for {info.filename}")
        name_length, extra_length = values[-2:]
        offset = 30 + name_length + extra_length
        compressed = response.content[offset:offset + info.compress_size]
        if len(compressed) != info.compress_size:
            raise RuntimeError(f"short range response for {info.filename}")
        if info.compress_type == zipfile.ZIP_STORED:
            return compressed
        if info.compress_type == zipfile.ZIP_DEFLATED:
            return zlib.decompress(compressed, -15)
        raise RuntimeError(f"unsupported ZIP compression for {info.filename}")

    def fetch(name: str) -> tuple[str, bytes]:
        return name, read_member(info_by_name[name])

    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        payloads = list(pool.map(fetch, names))
    remote.close()
    records = []
    for name, trajectory in payloads:
        parts = name.split("/")
        if len(parts) < 3:
            continue
        domain, task_id = parts[0], parts[1]
        match = configs.get(task_id)
        if match is None:
            continue
        task_path, task = match
        instruction = str(task.get("instruction") or "").strip()
        steps = _osworld_steps(instruction, trajectory)
        records.append({
            "review_id": f"osworld-autoglm15:{task_id}",
            "task_name": f"osworld:{domain}:{task_id}",
            "benchmark": "OSWorld",
            "source_kind": "real_model_execution_trace",
            "model": "AutoGLM",
            "agent": "OSWorld official AutoGLM runner",
            "source_url": f"https://huggingface.co/datasets/{OSWORLD_DATASET}",
            "source_revision": str(dataset.get("sha") or "main"),
            "source_artifact": OSWORLD_ZIP + ":" + name,
            "source_sha256": _sha_bytes(trajectory),
            "source_task_path": str(task_path.resolve()),
            "source_task_sha256": _sha_bytes(task_path.read_bytes()),
            "instruction": instruction,
            "steps": steps,
            # The compact collector intentionally skips result.txt to halve remote
            # range requests. Source outcome is not used to promote async evidence.
            "solved": None,
            "source_metadata": {
                "domain": domain, "related_apps": task.get("related_apps") or [],
                "possibility_of_env_change": task.get("possibility_of_env_change"),
                "trace_step_count": sum(step.get("kind") == "action" for step in steps),
            },
        })
    return records


def _gaia2_bridge(scenario: dict[str, Any]) -> dict[str, Any] | None:
    events = [event for event in scenario.get("events") or [] if isinstance(event, dict)]
    by_id = {str(event.get("event_id") or ""): event for event in events}
    oracle = [
        event for event in events
        if event.get("class_name") == "OracleEvent" and event.get("event_type") == "AGENT"
    ]
    candidates = []
    for event in events:
        if event.get("class_name") != "Event" or event.get("event_type") != "ENV":
            continue
        prior = [
            by_id[item] for item in event.get("dependencies") or []
            if item in by_id and by_id[item].get("class_name") == "OracleEvent"
        ]
        affected = [
            item for item in oracle
            if str(event.get("event_id") or "") in (item.get("dependencies") or [])
        ]
        if prior and affected:
            candidates.append((event, prior, affected))
    if not candidates:
        return None
    event, prior, affected = max(candidates, key=lambda item: len(item[2]))
    return {
        "prior_event_ids": [str(item.get("event_id") or "") for item in prior],
        "late_event_id": str(event.get("event_id") or ""),
        "affected_event_ids": [str(item.get("event_id") or "") for item in affected],
    }


def collect_gaia2(paths: list[Path]) -> list[dict[str, Any]]:
    records = []
    for path in paths:
        for row in read_gaia2_parquet(path):
            raw = str(row.get("data") or "")
            scenario = json.loads(raw)
            bridge = _gaia2_bridge(scenario)
            if bridge is None:
                continue
            steps = normalize_gaia2_scenario(scenario)
            instruction = next(
                (str(step.get("content") or "") for step in steps if step.get("kind") == "task"),
                "",
            )
            scenario_id = str(row.get("scenario_id") or row.get("id") or "")
            records.append({
                "review_id": f"gaia2:{scenario_id}",
                "task_name": f"gaia2:{scenario_id}",
                "benchmark": "GAIA2",
                "source_kind": "official_dynamic_event_graph",
                "model": None, "agent": None,
                "source_url": "https://huggingface.co/datasets/meta-agents-research-environments/gaia2",
                "source_revision": GAIA2_REVISION,
                "source_artifact": path.parent.name + "/" + path.name,
                "source_sha256": _sha_text(raw),
                "instruction": instruction,
                "steps": steps,
                "solved": None,
                "source_metadata": {
                    "category": str(row.get("category") or path.parent.name),
                    "split": str(row.get("split") or "validation"),
                    "event_count": len(scenario.get("events") or []),
                    "bridge": bridge,
                    "trajectory_disclosure": "oracle DAG and ENV events; not a model execution trace",
                },
            })
    return records


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, encoding="utf-8",
    )


def collect_sentinel(repo: Path) -> list[dict[str, Any]]:
    revision = _git(repo, "rev-parse", "HEAD").strip()
    names = _git(repo, "ls-tree", "-r", "--name-only", "HEAD", "scenarios").splitlines()
    records = []
    for name in sorted(item for item in names if item.endswith(".json") and not item.endswith("/dev.json")):
        raw = _git(repo, "show", f"HEAD:{name}")
        scenario = json.loads(raw)
        events = list(scenario.get("events") or [])
        condition_at = scenario.get("condition_at")
        if condition_at is None:
            continue
        target_index = next(
            (index for index, event in enumerate(events) if event.get("time") == condition_at),
            None,
        )
        if target_index is None:
            continue
        steps = [{
            "step_id": 1, "role": "user", "kind": "task",
            "content": str(scenario.get("prompt") or ""),
            "source_ref": f"sentinel:{scenario.get('id')}:prompt",
        }]
        for index, event in enumerate(events):
            steps.append({
                "step_id": len(steps) + 1, "role": "environment", "kind": "observation",
                "content": json.dumps(event, ensure_ascii=False),
                "source_ref": f"sentinel:{scenario.get('id')}:event:{index}",
            })
        scenario_id = str(scenario.get("id") or Path(name).stem)
        records.append({
            "review_id": f"sentinel:{scenario_id}",
            "task_name": f"sentinel:{scenario_id}",
            "benchmark": "SentinelBench",
            "source_kind": "official_dynamic_event_timeline",
            "model": None, "agent": None,
            "source_url": "https://github.com/microsoft/sentinel_environments",
            "source_revision": revision,
            "source_artifact": name,
            "source_sha256": _sha_text(raw),
            "instruction": str(scenario.get("prompt") or ""),
            "steps": steps,
            "solved": None,
            "source_metadata": {
                "environment": scenario.get("environment"),
                "condition_at": condition_at, "kill_at": scenario.get("kill_at"),
                "event_timeline_end": scenario.get("event_timeline_end"),
                "target_event_index": target_index,
                "eval_sql": scenario.get("eval_sql"),
                "taxonomy": scenario.get("taxonomy") or {},
                "trajectory_disclosure": "official event timeline; not a model execution trace",
            },
        })
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--osworld-repo", required=True)
    parser.add_argument("--sentinel-repo", required=True)
    parser.add_argument("--gaia2-parquet", action="append", default=[])
    parser.add_argument("--osworld-limit", type=int, default=400)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    records = []
    records.extend(collect_osworld(Path(args.osworld_repo).resolve(), args.osworld_limit))
    records.extend(collect_gaia2([Path(item).resolve() for item in args.gaia2_parquet]))
    records.extend(collect_sentinel(Path(args.sentinel_repo).resolve()))
    records.sort(key=lambda row: (str(row["benchmark"]), str(row["review_id"])))
    ids = [str(row["review_id"]) for row in records]
    if len(ids) != len(set(ids)):
        raise ValueError("collected source records contain duplicate review ids")
    write_jsonl(output / "source_records.jsonl", records)
    report = {
        "schema_version": "authoritative-multibench-source-1",
        "record_count": len(records),
        "benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in records).items())),
        "source_kind_counts": dict(sorted(Counter(row["source_kind"] for row in records).items())),
        "real_model_execution_trace_count": sum(
            row["source_kind"] == "real_model_execution_trace" for row in records
        ),
        "official_event_graph_count": sum(
            row["source_kind"].startswith("official_dynamic") for row in records
        ),
        "model_api_calls": 0,
        "source_disclosure": (
            "OSWorld rows are real public model runs. GAIA2 and SentinelBench rows are "
            "official dynamic event structures and are never represented as model runs."
        ),
    }
    (output / "collection_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
