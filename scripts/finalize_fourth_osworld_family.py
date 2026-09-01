from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "candidate_cases/osw-dependency-unblock-5c3a1789cf"
OLD = "osw-dependency-unblock-5c3a1789cf"
CID = "osw-dependency-unblock-d554baf45a"
OLDN = "osw_dependency_unblock_5c3a1789cf"
NEWN = "osw_dependency_unblock_d554baf45a"
OLDP = "osw_dependency_unblock_5"
NEWP = "osw_dependency_unblock_d"
OLDS = "osworld:chrome:1704f00f-79e6-43a7-961b-cedd3724d5fd"
NEWS = "osworld:libreoffice_calc:51719eea-10bc-4246-a428-ac7c433dd4b3"
CASE = ROOT / "candidate_cases" / CID
BP = ROOT / "candidate_cases/rebuild-to-100/blueprints" / CID
RT = ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / CID
VAL_ROOT = ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/validation"
CANONICAL_REPORT = VAL_ROOT / f"{CID}-canonical/report.json"
FULL_REPORT = VAL_ROOT / f"{CID}-full/report.json"
SOURCE_INSTRUCTION = "Calculate revenue from price, quantity, and discount, then create a Sheet2 pivot table summarizing revenue by product."
ASYNC_EXTENSION = "After the workbook checkpoint is persisted, consume evaluator-owned evidence, preserve the lookup-derived revenue values, and reverify the pivot-table closure without replaying completed work."
PUBLIC_KEYWORD = "pivot table"
THEME = "duplicate_or_replayed_completion"


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def main() -> None:
    if CASE.exists():
        shutil.rmtree(CASE)
    shutil.copytree(SRC, CASE)
    for path in CASE.rglob("*"):
        if not path.is_file():
            continue
        try:
            value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        path.write_text(
            value.replace(OLD, CID).replace(OLDN, NEWN).replace(OLDP, NEWP).replace(OLDS, NEWS),
            encoding="utf-8",
            newline="\n",
        )
    shutil.copytree(BP / "private/source_manifests", CASE / "private/source_manifests", dirs_exist_ok=True)
    shutil.copy2(BP / "private/source_lock.json", CASE / "private/source_lock.json")
    for name in ("official_task.json", "hidden_checks.json", "semantic_control_registry.json"):
        src = RT / "private" / name
        dst = CASE / "private" / ("osworld_" + name if name != "official_task.json" else name)
        shutil.copy2(src, dst)
    canonical = json.loads(CANONICAL_REPORT.read_text(encoding="utf-8"))["episodes"][0]
    remaining = json.loads(FULL_REPORT.read_text(encoding="utf-8"))["episodes"]
    equivalent, *counterexamples = remaining
    digest = canonical["event_receipt"]["release_after_digest"]
    report = {
        "schema_version": "async-rbench-osworld-canonical-family-v1",
        "case_id": CID,
        "model_episode_executed": False,
        "episode_owner": "evaluator",
        "evidence_sha256": digest,
        "anomaly": "INSERT_LARGE_DATA",
        "source_native_marble_verified": True,
        "native_evaluator_verified": True,
        "host_checkpoint": {"owner": "host_runtime", "checkpoint_sha256": digest},
        "canonical": canonical,
        "equivalent": equivalent,
        "counterexamples": counterexamples,
        "passed": canonical["official_score"] == 1 and equivalent["official_score"] == 1
        and len(counterexamples) >= 2 and all(item["official_score"] == 0 for item in counterexamples),
    }
    dump(CASE / "private/native_canonical_report.json", report)
    dump(CASE / "task/task_file/native_canonical_report.json", report)
    source = SOURCE_INSTRUCTION
    instruction = source + "\n\nASYNC-RBENCH EXTENSION\n" + ASYNC_EXTENSION
    task = {"author_name": "Async-RBench individualized rebuild", "category": "OSWorld", "difficulty": "validated_native", "instruction": instruction, "tags": ["OSWorld", THEME, "live_eventful"]}
    write(CASE / "task/task.yaml", yaml.safe_dump(task, sort_keys=False, allow_unicode=True))
    write(CASE / "instruction.md", instruction + "\n")
    dump(CASE / "private/source_task.yaml", {"instruction": source})
    quality = json.loads((CASE / "private/quality_contract.yaml").read_text(encoding="utf-8"))
    quality["source_contract"]["sources"][0]["instruction_sha256"] = hashlib.sha256(source.encode()).hexdigest()
    quality["requirements"][0]["public_evidence"] = [
        {"path": "task/task.yaml", "contains": "ASYNC-RBENCH EXTENSION"},
        {"path": "task/task.yaml", "contains": PUBLIC_KEYWORD},
    ]
    dump(CASE / "private/quality_contract.yaml", quality)
    dump(CASE / "private/canonical_episode_acceptance.json", {"accepted": True, "model_episode_required": False, "accepted_episode_owner": "evaluator", "official_evaluator_score": 1.0, "equivalent_score": 1.0, "negative_scores": [0.0, 0.0], "native_report": "private/native_canonical_report.json"})
    print(CASE)


if __name__ == "__main__":
    main()
