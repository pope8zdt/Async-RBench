from __future__ import annotations

import finalize_fourth_osworld_family as family

family.SRC = family.ROOT / "candidate_cases/osw-cross-app-artifact-81b4557778"
family.OLD = "osw-cross-app-artifact-81b4557778"
family.CID = "osw-dependency-unblock-4bfe607faa"
family.OLDN = "osw_cross_app_artifact_81b4557778"
family.NEWN = "osw_dependency_unblock_4bfe607faa"
family.OLDP = "osw_multiext_8"
family.NEWP = "osw_nba_9"
family.OLDS = "osworld:multi_apps:a74b607e-6bb5-4ea8-8a7c-5d97c7bbcd2a"
family.NEWS = "osworld:chrome:9f3f70fc-5afc-4958-a7b7-3bb4fcb01805"
family.CASE = family.ROOT / "candidate_cases" / family.CID
family.BP = family.ROOT / "candidate_cases/rebuild-to-100/blueprints" / family.CID
family.RT = family.ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / family.CID
family.CANONICAL_REPORT = family.VAL_ROOT / f"{family.CID}-canonical-data/report.json"
family.FULL_REPORT = family.VAL_ROOT / f"{family.CID}-full-data/report.json"
family.SOURCE_INSTRUCTION = "Browse women's Nike jerseys and retain only listings priced over $60."
family.ASYNC_EXTENSION = "After the browser-result checkpoint is persisted, consume evaluator-owned page evidence, preserve the women/Nike/jerseys constraints, and reverify the $60 threshold without replaying completed filtering."
family.PUBLIC_KEYWORD = "Nike jerseys"
family.THEME = "delayed_authoritative_result"

if __name__ == "__main__":
    family.main()
