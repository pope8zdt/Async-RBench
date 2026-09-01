from __future__ import annotations

import finalize_fourth_osworld_family as family

family.SRC = family.ROOT / "candidate_cases/osw-dependency-unblock-75855f9fc5"
family.OLD = "osw-dependency-unblock-75855f9fc5"
family.CID = "osw-dependency-unblock-af63091471"
family.OLDN = "osw_dependency_unblock_75855f9fc5"
family.NEWN = "osw_dependency_unblock_af63091471"
family.OLDP = "osw_bookmarks_14"
family.NEWP = "osw_font_15"
family.OLDS = "osworld:chrome:2ad9387a-65d8-4e33-ad5b-7580065a27ca"
family.NEWS = "osworld:chrome:af630914-714e-4a24-a7bb-f9af687d3b91"
family.CASE = family.ROOT / "candidate_cases" / family.CID
family.BP = family.ROOT / "candidate_cases/rebuild-to-100/blueprints" / family.CID
family.RT = family.ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / family.CID
family.CANONICAL_REPORT = family.VAL_ROOT / f"{family.CID}-canonical/report.json"
family.FULL_REPORT = family.VAL_ROOT / f"{family.CID}-full/report.json"
family.SOURCE_INSTRUCTION = "Set Chrome's default font size to the largest setting."
family.ASYNC_EXTENSION = "After the Chrome font-size checkpoint is persisted, consume evaluator-owned preference evidence, incorporate any delayed authoritative browser profile state, and reverify the largest default font size after Chrome restarts without replaying completed configuration work."
family.PUBLIC_KEYWORD = "font size"
family.THEME = "delayed_authoritative_result"

if __name__ == "__main__":
    family.main()
    import json
    report_path = family.CASE / "private/native_canonical_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    episodes = json.loads(family.FULL_REPORT.read_text(encoding="utf-8"))["episodes"]
    equivalent = next(item for item in episodes if item["episode"] == "equivalent")
    negatives = [item for item in episodes if item["negative_counterexample"]]
    report["equivalent"] = equivalent
    report["counterexamples"] = negatives
    report["passed"] = (
        report["canonical"]["official_score"] == 1.0
        and equivalent["official_score"] == 1.0
        and len(negatives) >= 2
        and all(item["official_score"] == 0.0 for item in negatives)
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    report_path.write_text(payload, encoding="utf-8")
    (family.CASE / "task/task_file/native_canonical_report.json").write_text(payload, encoding="utf-8")
