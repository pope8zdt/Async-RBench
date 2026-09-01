from __future__ import annotations

import finalize_fourth_osworld_family as family

family.SRC = family.ROOT / "candidate_cases/osw-dependency-unblock-4bfe607faa"
family.OLD = "osw-dependency-unblock-4bfe607faa"
family.CID = "osw-late-constraint-5bfd71e4af"
family.OLDN = "osw_dependency_unblock_4bfe607faa"
family.NEWN = "osw_late_constraint_5bfd71e4af"
family.OLDP = "osw_nba_9"
family.NEWP = "osw_booking_10"
family.OLDS = "osworld:chrome:9f3f70fc-5afc-4958-a7b7-3bb4fcb01805"
family.NEWS = "osworld:chrome:da46d875-6b82-4681-9284-653b0c7ae241"
family.CASE = family.ROOT / "candidate_cases" / family.CID
family.BP = family.ROOT / "candidate_cases/rebuild-to-100/blueprints" / family.CID
family.RT = family.ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / family.CID
family.CANONICAL_REPORT = family.VAL_ROOT / f"{family.CID}-canonical-v6/report.json"
family.FULL_REPORT = family.VAL_ROOT / f"{family.CID}-full-v2/report.json"
family.SOURCE_INSTRUCTION = "Prepare a TAP CharlieCard appointment for James Smith on the first Monday eight months later between 9 AM and noon, leaving it ready for review."
family.ASYNC_EXTENSION = "After the appointment checkpoint is persisted, consume evaluator-owned form evidence, preserve the selected service and identity fields, and reverify the relative-date constraint without submitting the booking."
family.PUBLIC_KEYWORD = "TAP CharlieCard"
family.THEME = "delayed_authoritative_result"

if __name__ == "__main__":
    family.main()
