"""Materialize a distinct, source-pinned Chrome font-size replacement family."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CID = "osw-dependency-unblock-af63091471"
SOURCE_ID = "af630914-714e-4a24-a7bb-f9af687d3b91"
SOURCE_TASK = f"osworld:chrome:{SOURCE_ID}"
SOURCE_CONFIG = ROOT / "upstream/osworld/evaluation_examples/examples/chrome" / f"{SOURCE_ID}.json"
BP_SOURCE = ROOT / "candidate_cases/rebuild-to-100/blueprints/osw-dependency-unblock-75855f9fc5"
RT_SOURCE = ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases/osw-dependency-unblock-75855f9fc5"
BP = ROOT / "candidate_cases/rebuild-to-100/blueprints" / CID
RT = ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / CID


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def replace_text_tree(path: Path) -> None:
    replacements = {
        "osw-dependency-unblock-75855f9fc5": CID,
        "osw_dependency_unblock_75855f9fc5": "osw_dependency_unblock_af63091471",
        "osw_bookmarks_14": "osw_font_15",
        "osworld:chrome:2ad9387a-65d8-4e33-ad5b-7580065a27ca": SOURCE_TASK,
        "2ad9387a-65d8-4e33-ad5b-7580065a27ca": SOURCE_ID,
        "Favorites": "largest default font size",
        "bookmarks": "font-size preference",
    }
    for file in path.rglob("*"):
        if not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for old, new in replacements.items():
            text = text.replace(old, new)
        file.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    if BP.exists() or RT.exists():
        raise SystemExit(f"refusing to overwrite existing replacement target {CID}")
    if not SOURCE_CONFIG.is_file():
        raise SystemExit(f"missing official source config: {SOURCE_CONFIG}")
    official_bytes = SOURCE_CONFIG.read_bytes()
    official = json.loads(official_bytes)
    config_sha = hashlib.sha256(official_bytes).hexdigest()
    if official.get("id") != SOURCE_ID or official.get("evaluator", {}).get("func") != "check_font_size":
        raise SystemExit("official source identity/evaluator mismatch")
    if official["evaluator"].get("expected", {}).get("rules", {}).get("min") != 16:
        raise SystemExit("official source range is not the expected maximum-font-size scorer")

    shutil.copytree(BP_SOURCE, BP)
    shutil.copytree(RT_SOURCE, RT)
    replace_text_tree(BP)
    replace_text_tree(RT)

    binding = {
        "task_id": SOURCE_ID,
        "domain": "chrome",
        "config_path": f"upstream/osworld/evaluation_examples/examples/chrome/{SOURCE_ID}.json",
        "config_sha256": config_sha,
        "upstream_revision": "fc31a9049664292fcb35d6e501ee1dc839f2cf6d",
    }
    native_case = json.loads((BP / "private/source_manifests/01-native_case.json").read_text(encoding="utf-8"))
    native_case["case_id"] = CID
    native_case["source_binding"] = binding
    native_case["native_evaluator"] = official["evaluator"]
    dump(BP / "private/source_manifests/01-native_case.json", native_case)
    dump(BP / "private/source_lock.json", {
        "instruction_chars": len(official["instruction"]),
        "instruction_sha256": hashlib.sha256(official["instruction"].encode()).hexdigest(),
        "native_oracle_anchors": ["evaluator:check_font_size", "expected:range:16:99999", "result:chrome_font_size"],
        "source_files": [binding["config_path"]],
        "source_file_sha256": {binding["config_path"]: config_sha},
    })
    adapter_path = BP / "private/source_adapter.json"
    adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
    adapter["source_task_id"] = SOURCE_TASK
    adapter["runtime_plan"]["native_runtime_ref"] = {"adapter": "osworld.DesktopEnv", "snapshot": "chrome", "provider": "vmware_or_docker", "final_state": "persisted VM state"}
    adapter["runtime_plan"]["oracle"] = "replay evaluator-owned Chrome preference change and score with check_font_size"
    adapter["private_source_manifests"][0]["source"] = binding["config_path"]
    adapter["private_source_manifests"][0]["sha256"] = config_sha
    dump(adapter_path, adapter)

    # Runtime package binds the unmodified official evaluator and gives its own traceable contract.
    dump(RT / "private/official_task.json", official)
    contract = json.loads((RT / "runtime_contract.json").read_text(encoding="utf-8"))
    contract.update({"case_id": CID, "source_task_id": SOURCE_TASK, "snapshot": "chrome", "official_config_path": binding["config_path"], "official_config_sha256": config_sha})
    contract["official_evaluator_sha256"] = hashlib.sha256(json.dumps(official["evaluator"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    dump(RT / "runtime_contract.json", contract)
    hidden = json.loads((RT / "private/hidden_checks.json").read_text(encoding="utf-8"))
    hidden["checks"] = [
        {"id": "official_metric_01", "kind": "official_osworld_metric", "metric": "check_font_size", "expected": official["evaluator"]["expected"]},
        {"id": "persisted_target_state", "kind": "checkpoint_state_digest"},
        {"id": "post_event_reverification", "kind": "event_to_evaluator_order"},
    ]
    hidden["required_semantic_checks"] = [item["id"] for item in hidden["checks"]]
    dump(RT / "private/hidden_checks.json", hidden)
    manifest_path = ROOT / "candidate_cases/rebuild-to-100/selection-manifest.json"
    selection = json.loads(manifest_path.read_text(encoding="utf-8"))
    old = "osw-dependency-unblock-e89ce4db78"
    rows = selection["cases"]
    if sum(row["case_id"] == old for row in rows) != 1:
        raise SystemExit("expected one infeasible third replacement target in selection manifest")
    for row in rows:
        if row["case_id"] == old:
            row.update({"case_id": CID, "source_task_id": SOURCE_TASK, "requires_authored_private_oracle": False})
    dump(manifest_path, selection)
    print(CID)


if __name__ == "__main__":
    main()
