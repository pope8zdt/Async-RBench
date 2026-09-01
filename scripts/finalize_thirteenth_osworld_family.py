from __future__ import annotations

import finalize_fourth_osworld_family as family

family.SRC = family.ROOT / "candidate_cases/osw-dependency-unblock-1a3f65b5b8"
family.OLD = "osw-dependency-unblock-1a3f65b5b8"
family.CID = "osw-dependency-unblock-2d1b650a2e"
family.OLDN = "osw_dependency_unblock_1a3f65b5b8"
family.NEWN = "osw_dependency_unblock_2d1b650a2e"
family.OLDP = "osw_steam_12"
family.NEWP = "osw_dnt_13"
family.OLDS = "osworld:chrome:121ba48f-9e17-48ce-9bc6-a4fb17a7ebba"
family.NEWS = "osworld:chrome:030eeff7-b492-4218-b312-701ec99ee0cc"
family.CASE = family.ROOT / "candidate_cases" / family.CID
family.BP = family.ROOT / "candidate_cases/rebuild-to-100/blueprints" / family.CID
family.RT = family.ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / family.CID
family.CANONICAL_REPORT = family.VAL_ROOT / f"{family.CID}-canonical-r5/report.json"
family.FULL_REPORT = family.VAL_ROOT / f"{family.CID}-full/report.json"
family.SOURCE_INSTRUCTION = "Enable Chrome's Do Not Track feature to enhance browsing privacy."
family.ASYNC_EXTENSION = "After the Chrome preference checkpoint is persisted, consume evaluator-owned preference evidence, incorporate any delayed authoritative browser state, and reverify the Do Not Track value after Chrome restarts without replaying completed configuration work."
family.PUBLIC_KEYWORD = "Do Not Track"
family.THEME = "delayed_authoritative_result"

if __name__ == "__main__":
    family.main()
