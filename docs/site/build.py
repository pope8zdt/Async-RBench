"""Build the paper website from public, explicitly allowlisted inputs."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import shutil

import yaml

from pages import render_pages

SITE = Path(__file__).resolve().parent
ROOT = SITE.parents[1]
REPOSITORY = "https://github.com/pope8zdt/Async-RBench"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_public_data(root: Path):
    release = read_json(root / "data/async-rbench/release.json")
    registry = read_json(root / "data/async-rbench/registry.json")
    manifest = read_json(root / "paper_artifacts/experiment_manifest.json")
    policy = read_json(root / "configs/dataset-policy.json")
    families = registry["case_families"]
    registered = {case["case_id"] for case in families}
    if len(families) != 200 or len(registered) != 200 or any(len(c["instances"]) != 1 for c in families):
        raise ValueError("Expected 200 cases with one instance each")
    if registered != {c["case_id"] for c in release["cases"]} or registered != set(manifest["case_ids"]):
        raise ValueError("Registry, release and paper manifest populations differ")
    tasks = []
    for case in release["cases"]:
        case_id = case["case_id"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", case_id):
            raise ValueError("Unsafe case identifier")
        public = yaml.safe_load((root / "data/async-rbench/cases" / case_id / "public/case.yaml").read_text(encoding="utf-8"))
        tasks.append({
            "id": case_id, "title": public["title"], "source": case["source"],
            "difficulty": case["difficulty"], "subtasks": case["initial_subtasks"],
            "url": f"{REPOSITORY}/tree/main/data/async-rbench/cases/{case_id}",
        })
    sources = dict(sorted(Counter(t["source"] for t in tasks).items()))
    difficulty = dict(Counter(t["difficulty"] for t in tasks))
    subtasks = sum(t["subtasks"] for t in tasks)
    histogram = dict(Counter(str(t["subtasks"]) if t["subtasks"] < 4 else "4_plus" for t in tasks))
    if list(sources.values()) != [40] * 5 or difficulty != {"medium": 104, "hard": 96} or subtasks != 621:
        raise ValueError("Public corpus no longer matches the paper snapshot; review before publication")
    scenarios = policy["primary_event_theme_targets"]
    if len(scenarios) != 8 or set(scenarios.values()) != {25}:
        raise ValueError("Scenario totals differ from the paper")
    corpus = {
        "release": release["release_id"], "task_count": len(tasks),
        "initial_subtasks": subtasks, "source_counts": sources,
        "difficulty_counts": difficulty, "subtask_histogram": histogram,
        "scenario_counts": scenarios, "registry_sha256": release["registry_sha256"],
        "tasks": sorted(tasks, key=lambda t: t["id"]),
    }
    paper = read_json(SITE / "data/paper-results.json")
    if len(paper["records"]) != 9 or {r["id"] for r in paper["records"]} != set(manifest["model_identifiers"]):
        raise ValueError("Paper table and experiment manifest name different models")
    if paper["protocol"] != {"tasks": len(tasks), "agents": len(manifest["model_identifiers"]),
                             "modes": len(manifest["execution_modes"]), "repetitions": len(manifest["repetitions"]),
                             "episodes": manifest["episode_count_total"]}:
        raise ValueError("Paper experiment counts differ from the manifest")
    for record in paper["records"]:
        means, sds = record.pop("scenario_means"), record.pop("scenario_sds")
        if len(means) != 8 or len(sds) != 8:
            raise ValueError("Incomplete scenario scores")
        record["scenarios"] = {key: {"mean": mean, "sd": sd}
                               for key, mean, sd in zip(paper["scenario_order"], means, sds, strict=True)}
    return corpus, paper


def build_site(repo_root: Path, output: Path, base_path: str):
    if base_path and not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+", base_path):
        raise ValueError("Base path must be empty or a slash-prefixed project path without a trailing slash")
    output = output.resolve()
    # Never delete, merge into, or overwrite an existing directory's contents.
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output must be a new or empty directory")
    corpus, paper = load_public_data(repo_root)
    pages = render_pages(base_path, corpus, paper)
    output.mkdir(parents=True, exist_ok=True)
    for relative, contents in pages.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
    assets = output / "assets"
    assets.mkdir()
    for name in ("site.css", "site.mjs", "logic.mjs"):
        shutil.copyfile(SITE / name, assets / name)
    for name in ("overview.png", "benchmark-mechanism.png", "drs-validation.png", "full-rebuild.png"):
        shutil.copyfile(repo_root / "assets" / name, assets / name)
    data_dir = output / "data"
    data_dir.mkdir()
    for name, data in (("corpus.json", corpus), ("leaderboard.json", paper)):
        (data_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (data_dir / "leaderboard.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["model", "drs", "calls", "batched", "async", "delta"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(paper["records"])
    shutil.copyfile(repo_root / "configs/model-profiles/experiment-profile.template.yaml", data_dir / "experiment-profile.template.yaml")
    (output / ".nojekyll").touch()
    return {"pages": len(pages), "tasks": len(corpus["tasks"]), "paper_models": len(paper["records"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/site")
    parser.add_argument("--base-path", default="/Async-RBench")
    args = parser.parse_args()
    print(json.dumps(build_site(ROOT, args.output, args.base_path)))
