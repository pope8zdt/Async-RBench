from __future__ import annotations

import finalize_fourth_osworld_family as family

family.SRC = family.ROOT / "candidate_cases/osw-late-constraint-5bfd71e4af"
family.OLD = "osw-late-constraint-5bfd71e4af"
family.CID = "osw-dependency-unblock-be02b29e4b"
family.OLDN = "osw_late_constraint_5bfd71e4af"
family.NEWN = "osw_dependency_unblock_be02b29e4b"
family.OLDP = "osw_booking_10"
family.NEWP = "osw_writer_11"
family.OLDS = "osworld:chrome:da46d875-6b82-4681-9284-653b0c7ae241"
family.NEWS = "osworld:libreoffice_writer:8472fece-c7dd-4241-8d65-9b3cd1a0b568"
family.CASE = family.ROOT / "candidate_cases" / family.CID
family.BP = family.ROOT / "candidate_cases/rebuild-to-100/blueprints" / family.CID
family.RT = family.ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / family.CID
family.CANONICAL_REPORT = family.VAL_ROOT / f"{family.CID}-fixed-canonical/report.json"
family.FULL_REPORT = family.VAL_ROOT / f"{family.CID}-fixed-full/report.json"
family.SOURCE_INSTRUCTION = "Color table words beginning with vowels red and words beginning with non-vowels blue throughout the primer document."
family.ASYNC_EXTENSION = "After the Writer checkpoint is persisted, consume evaluator-owned document evidence, preserve text and table structure, and reverify every non-empty run's first-character color without replaying completed edits."
family.PUBLIC_KEYWORD = "non-vowels blue"
family.THEME = "partial_then_complete_result"

if __name__ == "__main__":
    family.main()
