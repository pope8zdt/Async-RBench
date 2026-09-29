"""Build the publication-safe manifest for the paper's main experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PAPER_MODELS = [
    {"display_name": "Claude Sonnet 5", "model_identifier": "claude-sonnet-5"},
    {"display_name": "GPT-5.6 Terra", "model_identifier": "gpt-5.6-terra"},
    {"display_name": "Qwen3.7 Plus", "model_identifier": "qwen3.7-plus"},
    {"display_name": "GLM5.3 Flash", "model_identifier": "glm-5.3-flash"},
    {"display_name": "GPT-5.6 Luna", "model_identifier": "gpt-5.6-luna"},
    {"display_name": "DeepSeek V4 Pro", "model_identifier": "deepseek-v4-pro"},
    {"display_name": "Qwen3.5 27B", "model_identifier": "qwen3.5-27b"},
    {"display_name": "Kimi K2.5", "model_identifier": "kimi-k2.5"},
    {
        "display_name": "Gemini 3 Flash High",
        "model_identifier": "gemini-3-flash-preview-thinking-high",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-root", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("paper_artifacts/experiment_manifest.json"),
    )
    args = parser.parse_args()

    public_release_path = Path("data/async-rbench/release.json")
    evaluation_contract_path = Path("configs/evaluation-contract.json")
    judge_release_path = args.judge_root / "release.json"
    public_release = json.loads(public_release_path.read_text(encoding="utf-8"))
    judge_release = json.loads(judge_release_path.read_text(encoding="utf-8"))
    case_ids = [entry["case_id"] for entry in public_release["cases"]]
    if len(case_ids) != 200 or len(set(case_ids)) != 200:
        raise SystemExit("expected exactly 200 unique public cases")
    if {entry["case_id"] for entry in judge_release["cases"]} != set(case_ids):
        raise SystemExit("public and judge release case sets do not match")

    document = {
        "schema_version": "1.0",
        "release_id": "v11.0-paper",
        "protocol_version": "11.0.0",
        "public_release_sha256": sha256(public_release_path),
        "judge_release_sha256": sha256(judge_release_path),
        "evaluation_contract_sha256": sha256(evaluation_contract_path),
        "framework_source_sha256": tree_sha256(Path("src/async_rbench")),
        "model_identifiers": [item["model_identifier"] for item in PAPER_MODELS],
        "model_configurations": [
            {
                **item,
                "main_model": item["model_identifier"],
                "child_model": item["model_identifier"],
                "provider_endpoint": "omitted_from_public_release",
            }
            for item in PAPER_MODELS
        ],
        "model_identifier_note": (
            "Paper-reported model labels; endpoints, account routing, and credentials omitted."
        ),
        "execution_modes": [
            {"label": "Batched", "internal_key": "linear"},
            {"label": "Async", "internal_key": "async"},
        ],
        "manifest_seed": 2026,
        "guidance": "incentive",
        "repetitions": [1, 2, 3],
        "case_ids": case_ids,
        "run_id_template": "{model_id}/{execution_mode}/{case_id}/rep-{repetition}",
        "episode_count_per_model_per_mode": 600,
        "episode_count_per_model": 1200,
        "episode_count_total": 10800,
        "shared_resource_limits": {
            "max_main_steps": 100,
            "max_child_steps": 40,
            "max_output_tokens": 16384,
            "max_concurrent_children": 3,
            "max_total_child_spawns": 5,
        },
        "private_artifact_policy": (
            "Judge contents and run traces are external; this manifest binds their release file by digest."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {args.output} ({document['episode_count_total']} episodes)")


if __name__ == "__main__":
    main()
