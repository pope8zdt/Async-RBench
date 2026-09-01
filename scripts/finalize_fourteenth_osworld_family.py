from __future__ import annotations

import finalize_fourth_osworld_family as family

family.SRC = family.ROOT / "candidate_cases/osw-dependency-unblock-2d1b650a2e"
family.OLD = "osw-dependency-unblock-2d1b650a2e"
family.CID = "osw-dependency-unblock-75855f9fc5"
family.OLDN = "osw_dependency_unblock_2d1b650a2e"
family.NEWN = "osw_dependency_unblock_75855f9fc5"
family.OLDP = "osw_dnt_13"
family.NEWP = "osw_bookmarks_14"
family.OLDS = "osworld:chrome:030eeff7-b492-4218-b312-701ec99ee0cc"
family.NEWS = "osworld:chrome:2ad9387a-65d8-4e33-ad5b-7580065a27ca"
family.CASE = family.ROOT / "candidate_cases" / family.CID
family.BP = family.ROOT / "candidate_cases/rebuild-to-100/blueprints" / family.CID
family.RT = family.ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / family.CID
family.CANONICAL_REPORT = family.VAL_ROOT / f"{family.CID}-canonical-r2/report.json"
family.FULL_REPORT = family.VAL_ROOT / f"{family.CID}-full/report.json"
family.SOURCE_INSTRUCTION = "Create a new folder named Favorites on Chrome's bookmarks bar."
family.ASYNC_EXTENSION = "After the bookmarks checkpoint is persisted, consume evaluator-owned bookmark evidence, incorporate any delayed authoritative profile state, and reverify that Favorites is the bookmarks bar folder after Chrome restarts without replaying completed work."
family.PUBLIC_KEYWORD = "Favorites"
family.THEME = "delayed_authoritative_result"

if __name__ == "__main__":
    family.main()
