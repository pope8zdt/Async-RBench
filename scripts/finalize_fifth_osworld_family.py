from __future__ import annotations

import finalize_fourth_osworld_family as family

family.SRC = family.ROOT / "candidate_cases/osw-dependency-unblock-d554baf45a"
family.OLD = "osw-dependency-unblock-d554baf45a"
family.CID = "osw-dependency-unblock-dd5b6417f3"
family.OLDN = "osw_dependency_unblock_d554baf45a"
family.NEWN = "osw_dependency_unblock_dd5b6417f3"
family.OLDP = "osw_dependency_unblock_d"
family.NEWP = "osw_impress_5"
family.OLDS = "osworld:libreoffice_calc:51719eea-10bc-4246-a428-ac7c433dd4b3"
family.NEWS = "osworld:libreoffice_impress:a53f80cd-4a90-4490-8310-097b011433f6"
family.CASE = family.ROOT / "candidate_cases" / family.CID
family.BP = family.ROOT / "candidate_cases/rebuild-to-100/blueprints" / family.CID
family.RT = family.ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / family.CID
family.CANONICAL_REPORT = family.VAL_ROOT / f"{family.CID}-canonical-v2/report.json"
family.FULL_REPORT = family.VAL_ROOT / f"{family.CID}-full-v2/report.json"
family.SOURCE_INSTRUCTION = "Make slide titles 2 and 3 black and bold, then remove all personal information and its icons from slide 4."
family.ASYNC_EXTENSION = "After the presentation checkpoint is persisted, consume evaluator-owned evidence, preserve completed slide edits, and reverify title formatting and personal-information removal without replaying completed work."
family.PUBLIC_KEYWORD = "slide titles"

if __name__ == "__main__":
    family.main()
