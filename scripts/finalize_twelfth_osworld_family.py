from __future__ import annotations

import finalize_fourth_osworld_family as family

family.SRC = family.ROOT / "candidate_cases/osw-dependency-unblock-be02b29e4b"
family.OLD = "osw-dependency-unblock-be02b29e4b"
family.CID = "osw-dependency-unblock-1a3f65b5b8"
family.OLDN = "osw_dependency_unblock_be02b29e4b"
family.NEWN = "osw_dependency_unblock_1a3f65b5b8"
family.OLDP = "osw_writer_11"
family.NEWP = "osw_steam_12"
family.OLDS = "osworld:libreoffice_writer:8472fece-c7dd-4241-8d65-9b3cd1a0b568"
family.NEWS = "osworld:chrome:121ba48f-9e17-48ce-9bc6-a4fb17a7ebba"
family.CASE = family.ROOT / "candidate_cases" / family.CID
family.BP = family.ROOT / "candidate_cases/rebuild-to-100/blueprints" / family.CID
family.RT = family.ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / family.CID
family.CANONICAL_REPORT = family.VAL_ROOT / f"{family.CID}-local-canonical-r2/report.json"
family.FULL_REPORT = family.VAL_ROOT / f"{family.CID}-local-full/report.json"
family.SOURCE_INSTRUCTION = "Find Dota 2 and add all DLC to the cart, including The Dota 2 Official Soundtrack."
family.ASYNC_EXTENSION = "After the Steam cart checkpoint is persisted, consume evaluator-owned cart evidence, incorporate any delayed authoritative cart state, and reverify that the official soundtrack remains a cart member without replaying completed additions."
family.PUBLIC_KEYWORD = "Dota 2 Official Soundtrack"
family.THEME = "delayed_authoritative_result"

if __name__ == "__main__":
    family.main()
