"""Aggregate-only public packages for participant-run Track B measurements."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


_ENVELOPE_FIELDS = {
    "schemaVersion", "track", "submissionId", "contentSha256",
    "benchmarkCommit", "manifestSha256", "configSha256", "record",
}
_RECORD_FIELDS = {
    "framework", "model", "evaluationContractVersion", "scorePolicyVersion",
    "caseCount", "repetitions", "plannedEpisodes", "completedEpisodes",
    "validEpisodes", "validPairs", "pairedComplete", "coverageStatus",
    "metrics", "runtime", "components", "developmentOnly",
    "leaderboardEligible", "sourceSha256",
}
_METRIC_FIELDS = {"linearBts", "asyncBts", "btsAsyncMinusLinear", "asyncDrs"}
_RUNTIME_FIELDS = {
    "type", "imageId", "os", "cpus", "memory", "timeoutSec",
}
_PAIR_BINDING_FIELDS = {
    "case_id", "instance_id", "requested_model", "case_sha256",
    "verifier_bundle_sha256", "agent_seed", "participant_image_id",
}


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Track B package must contain finite JSON") from exc


def _identity(package: dict[str, Any]) -> str:
    body = {
        key: value for key, value in package.items()
        if key not in {"submissionId", "contentSha256"}
    }
    return hashlib.sha256(_canonical(body)).hexdigest()


def _digest(value: Any, *, length: int = 64, label: str = "digest") -> None:
    if not isinstance(value, str) or re.fullmatch(f"[0-9a-f]{{{length}}}", value) is None:
        raise ValueError(f"invalid {label}")


def _image_id(value: Any, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ValueError("invalid immutable runtime image ID")


def _metric(value: Any, *, signed: bool = False) -> None:
    if value is None:
        return
    low = -1 if signed else 0
    if type(value) not in {int, float} or not math.isfinite(value) or not low <= value <= 1:
        raise ValueError("invalid Track B metric")


def _object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"unexpected or missing fields in {label}")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"Track B input cannot be a symlink: {path}")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=unique,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {token}")
            ),
        )
    except OSError as exc:
        raise ValueError(f"cannot read Track B input: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Track B input must be a JSON object: {path}")
    return value


def _valid_episode(score: dict[str, Any]) -> bool:
    return (
        score.get("score_status") == "scored"
        and score.get("protocol_valid") is True
        and score.get("scenario_constructed") is True
        and score.get("conformance_passed") is True
        and not score.get("infrastructure_failures")
        and not score.get("child_terminal_counts", {}).get(
            "infrastructure_failure", 0
        )
    )


def _uniform(rows: list[dict[str, Any]], getter, label: str) -> Any:
    values = [_canonical(getter(row)) for row in rows]
    if len(set(values)) != 1:
        raise ValueError(f"Track B scores disagree on {label}")
    return getter(rows[0])


def _score_for_episode(runs: Path, episode: dict[str, Any]) -> dict[str, Any] | None:
    episode_id = episode.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        raise ValueError("manifest episode_id is invalid")
    directory = runs / episode_id
    path = directory / "score.json"
    if not path.exists():
        return None
    if directory.is_symlink() or path.is_symlink() or path.resolve().parent != directory.resolve():
        raise ValueError("Track B score path escapes its episode directory")
    score = _read_json(path)
    for key in {
        "episode_id", "case_id", "instance_id", "repeat",
        "execution_mode", "counterfactual_pair_id",
    }:
        if score.get(key) != episode.get(key):
            raise ValueError(f"score does not match manifest field: {key}")
    return score


def package_run(
    runs: Path | str,
    manifest_path: Path | str,
    *,
    benchmark_commit: str,
) -> dict[str, Any]:
    """Build a deterministic package without traces, case IDs or credentials."""
    runs = Path(runs).resolve()
    manifest_path = Path(manifest_path).resolve()
    _digest(benchmark_commit, length=40, label="benchmark commit")
    manifest = _read_json(manifest_path)
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if manifest.get("official_track") is True or manifest.get("track") == "A":
        raise ValueError("Track A manifests cannot be packaged as Track B")
    episodes = manifest.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        raise ValueError("Track B manifest has no episodes")

    ids = [episode.get("episode_id") for episode in episodes if isinstance(episode, dict)]
    if len(ids) != len(episodes) or len(set(ids)) != len(ids):
        raise ValueError("Track B manifest episode IDs must be unique")

    planned_pairs: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for episode in episodes:
        pair_id = episode.get("counterfactual_pair_id")
        mode = episode.get("execution_mode")
        if not isinstance(pair_id, str) or mode not in {"linear", "async"}:
            raise ValueError("Track B manifest must declare paired Linear/Async episodes")
        if mode in planned_pairs[pair_id]:
            raise ValueError("Track B manifest repeats an execution mode within a pair")
        planned_pairs[pair_id][mode] = episode
    if any(set(modes) != {"linear", "async"} for modes in planned_pairs.values()):
        raise ValueError("Track B manifest contains an incomplete pair")

    completed: list[dict[str, Any]] = []
    by_pair: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    score_bytes: list[bytes] = []
    for episode in episodes:
        score = _score_for_episode(runs, episode)
        if score is None:
            continue
        if (
            score.get("manifest_sha256") != manifest_sha
            or score.get("manifest_episode_count") != len(episodes)
        ):
            raise ValueError("Track B score does not match the manifest digest")
        completed.append(score)
        by_pair[episode["counterfactual_pair_id"]][episode["execution_mode"]] = score
        score_bytes.append(_canonical(score))

    if not completed:
        raise ValueError("Track B run has no completed score records")

    metadata = [
        row.get("participant_metadata")
        for row in completed
        if isinstance(row.get("participant_metadata"), dict)
    ]
    if len(metadata) != len(completed):
        raise ValueError("Track B score is missing participant metadata")
    framework = _uniform(metadata, lambda item: item.get("framework"), "framework")
    model = _uniform(completed, lambda item: item.get("requested_model"), "model")
    config_sha = _uniform(metadata, lambda item: item.get("config_sha256"), "config digest")
    contract_version = _uniform(
        completed, lambda item: item.get("evaluation_contract_version"),
        "evaluation contract version",
    )
    policy_version = _uniform(
        completed, lambda item: item.get("score_policy_version"), "score policy"
    )
    agent_runtime = _uniform(
        metadata, lambda item: item.get("agent_runtime") or {},
        "agent runtime image",
    )
    runtime = _uniform(metadata, lambda item: item.get("runtime") or {}, "runtime")
    components = _uniform(
        metadata, lambda item: sorted((item.get("components") or {}).keys()),
        "component set",
    )
    for value, label in [
        (framework, "framework"), (model, "model"),
        (contract_version, "evaluation contract version"),
        (policy_version, "score policy version"),
    ]:
        if not isinstance(value, str) or not value:
            raise ValueError(f"Track B score has invalid {label}")
    _digest(config_sha, label="config digest")

    runtime_type = runtime.get("type", "host")
    if runtime_type not in {"host", "docker"}:
        raise ValueError("Track B score has invalid runtime type")
    runtime_image = agent_runtime.get("image_id")
    runtime_os = agent_runtime.get("os")
    if runtime_type == "docker":
        _image_id(runtime_image)
        if runtime.get("image") != runtime_image:
            raise ValueError("Track B runtime image does not match agent runtime image")
    else:
        _image_id(runtime_image, optional=True)
    if runtime_os is not None and (not isinstance(runtime_os, str) or not runtime_os):
        raise ValueError("Track B score has invalid runtime OS")

    valid_count = sum(_valid_episode(row) for row in completed)
    valid_pairs: list[dict[str, Any]] = []
    for pair_id, modes in by_pair.items():
        if set(modes) != {"linear", "async"} or not all(
            _valid_episode(row) for row in modes.values()
        ):
            continue
        linear, asynchronous = modes["linear"], modes["async"]
        for field in _PAIR_BINDING_FIELDS:
            if linear.get(field) != asynchronous.get(field):
                label = "agent runtime image" if field == "participant_image_id" else field
                raise ValueError(f"Track B pair disagrees on {label}")
        linear_runtime = linear["participant_metadata"].get("agent_runtime", {}).get("image_id")
        async_runtime = asynchronous["participant_metadata"].get("agent_runtime", {}).get("image_id")
        if linear_runtime != async_runtime:
            raise ValueError("Track B pair disagrees on agent runtime image")
        values = {
            "linearBts": linear.get("base_task_score"),
            "asyncBts": asynchronous.get("base_task_score"),
            "asyncDrs": asynchronous.get("async_drs"),
        }
        for value in values.values():
            _metric(value)
            if value is None:
                raise ValueError("valid Track B pair is missing a metric")
        valid_pairs.append({
            **values,
            "btsAsyncMinusLinear": values["asyncBts"] - values["linearBts"],
        })

    if valid_pairs:
        metrics = {
            key: mean(pair[key] for pair in valid_pairs)
            for key in _METRIC_FIELDS
        }
    else:
        metrics = {key: None for key in _METRIC_FIELDS}
    case_instances = {
        (episode.get("case_id"), episode.get("instance_id"))
        for episode in episodes
    }
    repetitions = manifest.get("repetitions")
    if type(repetitions) is not int or repetitions < 1:
        repetitions = max(int(episode.get("repeat", 0)) for episode in episodes) + 1
    paired_complete = (
        len(completed) == len(episodes)
        and valid_count == len(episodes)
        and len(valid_pairs) == len(planned_pairs)
    )
    source_sha = hashlib.sha256(b"\n".join(sorted(score_bytes))).hexdigest()
    record = {
        "framework": framework,
        "model": model,
        "evaluationContractVersion": contract_version,
        "scorePolicyVersion": policy_version,
        "caseCount": len(case_instances),
        "repetitions": repetitions,
        "plannedEpisodes": len(episodes),
        "completedEpisodes": len(completed),
        "validEpisodes": valid_count,
        "validPairs": len(valid_pairs),
        "pairedComplete": paired_complete,
        "coverageStatus": "complete" if paired_complete else "incomplete",
        "metrics": metrics,
        "runtime": {
            "type": runtime_type,
            "imageId": runtime_image,
            "os": runtime_os,
            "cpus": runtime.get("cpus"),
            "memory": runtime.get("memory"),
            "timeoutSec": runtime.get("timeout_sec"),
        },
        "components": components,
        "developmentOnly": True,
        "leaderboardEligible": False,
        "sourceSha256": source_sha,
    }
    package = {
        "schemaVersion": 1,
        "track": "B",
        "benchmarkCommit": benchmark_commit,
        "manifestSha256": manifest_sha,
        "configSha256": config_sha,
        "record": record,
    }
    package["submissionId"] = package["contentSha256"] = _identity(package)
    validate_package(package)
    return package


def validate_package(package: dict[str, Any]) -> None:
    """Validate package shape and self-consistency, not score authenticity."""
    _object(package, _ENVELOPE_FIELDS, "Track B package")
    if package["schemaVersion"] != 1 or package["track"] != "B":
        raise ValueError("unsupported Track B package version or track")
    _digest(package["benchmarkCommit"], length=40, label="benchmark commit")
    _digest(package["manifestSha256"], label="manifest digest")
    _digest(package["configSha256"], label="config digest")
    identity = _identity(package)
    for key in {"submissionId", "contentSha256"}:
        _digest(package[key], label=key)
        if package[key] != identity:
            raise ValueError("Track B package content digest mismatch")

    record = _object(package["record"], _RECORD_FIELDS, "Track B record")
    for key in {
        "framework", "model", "evaluationContractVersion",
        "scorePolicyVersion", "sourceSha256",
    }:
        if not isinstance(record[key], str) or not record[key]:
            raise ValueError(f"invalid Track B record field: {key}")
    _digest(record["sourceSha256"], label="source digest")
    for key in {
        "caseCount", "repetitions", "plannedEpisodes", "completedEpisodes",
        "validEpisodes", "validPairs",
    }:
        if type(record[key]) is not int or record[key] < 0:
            raise ValueError(f"invalid Track B counter: {key}")
    if record["caseCount"] < 1 or record["repetitions"] < 1:
        raise ValueError("Track B package requires at least one case and repetition")
    planned = record["plannedEpisodes"]
    if (
        planned != record["caseCount"] * record["repetitions"] * 2
        or record["completedEpisodes"] > planned
        or record["validEpisodes"] > record["completedEpisodes"]
        or record["validPairs"] > planned // 2
    ):
        raise ValueError("inconsistent Track B coverage counters")
    complete = (
        record["completedEpisodes"] == planned
        and record["validEpisodes"] == planned
        and record["validPairs"] == planned // 2
    )
    if (
        type(record["pairedComplete"]) is not bool
        or record["pairedComplete"] != complete
        or record["coverageStatus"] != ("complete" if complete else "incomplete")
    ):
        raise ValueError("inconsistent Track B coverage status")
    if record["developmentOnly"] is not True or record["leaderboardEligible"] is not False:
        raise ValueError("Track B v1 packages are development-only")

    metrics = _object(record["metrics"], _METRIC_FIELDS, "Track B metrics")
    for key, value in metrics.items():
        _metric(value, signed=key == "btsAsyncMinusLinear")
    if record["validPairs"] == 0:
        if any(value is not None for value in metrics.values()):
            raise ValueError("Track B metrics require a valid pair")
    elif any(value is None for value in metrics.values()):
        raise ValueError("valid Track B pairs require all aggregate metrics")
    if metrics["linearBts"] is not None and not math.isclose(
        metrics["asyncBts"] - metrics["linearBts"],
        metrics["btsAsyncMinusLinear"],
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError("inconsistent Track B BTS difference")

    runtime = _object(record["runtime"], _RUNTIME_FIELDS, "Track B runtime")
    if runtime["type"] not in {"host", "docker"}:
        raise ValueError("invalid Track B runtime type")
    _image_id(runtime["imageId"], optional=runtime["type"] == "host")
    if runtime["os"] is not None and (
        not isinstance(runtime["os"], str) or not runtime["os"]
    ):
        raise ValueError("invalid Track B runtime OS")
    if runtime["type"] == "docker":
        if (
            type(runtime["cpus"]) not in {int, float}
            or not math.isfinite(runtime["cpus"])
            or runtime["cpus"] <= 0
        ):
            raise ValueError("invalid Track B runtime CPU limit")
        if (
            not isinstance(runtime["memory"], str)
            or re.fullmatch(r"[1-9][0-9]*(?:[kmgt]i?b?)?", runtime["memory"], re.I)
            is None
        ):
            raise ValueError("invalid Track B runtime memory limit")
        if (
            type(runtime["timeoutSec"]) is not int
            or not 1 <= runtime["timeoutSec"] <= 86400
        ):
            raise ValueError("invalid Track B runtime timeout")
    elif any(runtime[key] is not None for key in {"cpus", "memory", "timeoutSec"}):
        raise ValueError("host Track B runtime cannot claim container limits")
    components = record["components"]
    if (
        not isinstance(components, list)
        or components != sorted(set(components))
        or any(not isinstance(item, str) or not item for item in components)
    ):
        raise ValueError("invalid Track B component list")


def load_package(path: Path | str) -> dict[str, Any]:
    """Read and validate a Track B public package with strict JSON parsing."""
    package = _read_json(Path(path))
    validate_package(package)
    return package
