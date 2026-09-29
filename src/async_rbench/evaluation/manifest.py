from __future__ import annotations

import hashlib
import json
import random
import uuid
from pathlib import Path
from typing import Any

from ..private_eval import verifier_bundle_sha256
from ..judge import JudgeBundleProvider
from ..spec import case_instance_key, discover_case_instances
from .case_bundle import public_case_bundle_sha256
from .version import EVALUATION_CONTRACT_VERSION


EXECUTION_MODES = ("linear", "async")
DATASET_SPLITS = ("calibration", "development", "test")


def create_manifest(
    case_ids: list[str], repetitions: int, guidance: str, seed: int,
    execution_modes: list[str] | None = None,
    instance_keys: list[str] | None = None,
    split: str | None = None,
    model: str | None = None,
    judge_root: Path | None = None,
) -> dict[str, Any]:
    """Build an experiment manifest for ``repetitions`` paired episodes.

    ``split`` (one of calibration / development / test) optionally filters the
    instance set for diagnostics and is stamped on every episode plus at the top
    level. The paper manifest omits this filter and evaluates the complete
    200-task registry. ``model`` is a single-model formal factor: a manifest
    must not combine different models, so it is recorded explicitly.
    """
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    if judge_root is None:
        raise ValueError("manifest creation requires an explicit judge_root")
    provider = JudgeBundleProvider(judge_root)
    judge_release_path = provider.root / "release.json"
    if not judge_release_path.is_file():
        raise FileNotFoundError(f"judge release manifest is missing: {judge_release_path}")
    root = Path(__file__).resolve().parents[3]
    evaluation_contract_sha256 = hashlib.sha256(
        (root / "configs" / "evaluation-contract.json").read_bytes()
    ).hexdigest()
    instances = discover_case_instances(root, case_ids)
    if instance_keys:
        if len(instance_keys) != len(set(instance_keys)):
            raise ValueError("instance keys must be unique")
        instances_by_key = {
            case_instance_key(instance.case_id, instance.instance_id): instance
            for instance in instances
        }
        unknown_instances = sorted(set(instance_keys) - set(instances_by_key))
        if unknown_instances:
            raise ValueError(f"unknown registered case instances: {unknown_instances}")
        instances = [instances_by_key[key] for key in instance_keys]
    if split is not None:
        if split not in DATASET_SPLITS:
            raise ValueError(f"split must be one of {sorted(DATASET_SPLITS)}")
        instances = [instance for instance in instances if instance.split == split]
    if not instances:
        raise ValueError("manifest selection contains no registered instances")
    verifier_bundles = {
        case_instance_key(instance.case_id, instance.instance_id):
            verifier_bundle_sha256(
                provider.verifier_dir(instance.case_id, instance.instance_id)
            )
        for instance in instances
    }
    case_bundles = {
        case_instance_key(instance.case_id, instance.instance_id):
            public_case_bundle_sha256(instance.case_dir)
        for instance in instances
    }
    modes = list(EXECUTION_MODES) if execution_modes is None else list(execution_modes)
    if len(modes) != len(set(modes)):
        raise ValueError("execution modes must be unique")
    if not modes or set(modes) - set(EXECUTION_MODES):
        raise ValueError(f"execution modes must be a non-empty subset of {EXECUTION_MODES}")
    rng = random.Random(seed); episodes = []
    for instance in instances:
        case_id = instance.case_id
        instance_id = instance.instance_id
        for repeat in range(repetitions):
            pair_seed = rng.randrange(1, 2**31)
            order = list(modes); rng.shuffle(order)
            for mode in order:
                episodes.append({
                    "episode_id": f"{case_id}-{repeat}-{mode}-{uuid.UUID(int=rng.getrandbits(128)).hex[:8]}",
                    "case_id": case_id,
                    "instance_id": instance_id,
                    "repeat": repeat,
                    "execution_mode": mode,
                    "guidance": guidance,
                    "agent_seed": pair_seed,
                    "counterfactual_pair_id": f"{case_id}-{instance_id}-{repeat}",
                    "split": instance.split,
                    "model": model,
                })
    return {
        "manifest_version": "4.0",
        "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
        "evaluation_contract_sha256": evaluation_contract_sha256,
        "judge_release_sha256": hashlib.sha256(judge_release_path.read_bytes()).hexdigest(),
        "verifier_bundle_sha256": verifier_bundles,
        "case_bundle_sha256": case_bundles,
        "design": "within-instance paired linear/async; randomized execution-mode order",
        "seed": seed,
        "repetitions": repetitions,
        "guidance": guidance,
        "split": split,
        "model": model,
        "episodes": episodes,
    }


def write_manifest(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
