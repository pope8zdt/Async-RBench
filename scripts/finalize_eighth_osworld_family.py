from __future__ import annotations

import finalize_fourth_osworld_family as family

family.SRC = family.ROOT / "candidate_cases/osw-dependency-unblock-ba52abb8a2"
family.OLD = "osw-dependency-unblock-ba52abb8a2"
family.CID = "osw-cross-app-artifact-81b4557778"
family.OLDN = "osw_dependency_unblock_ba52abb8a2"
family.NEWN = "osw_cross_app_artifact_81b4557778"
family.OLDP = "osw_extension_7"
family.NEWP = "osw_multiext_8"
family.OLDS = "osworld:chrome:6766f2b8-8a72-417f-a9e5-56fcaa735837"
family.NEWS = "osworld:multi_apps:a74b607e-6bb5-4ea8-8a7c-5d97c7bbcd2a"
family.CASE = family.ROOT / "candidate_cases" / family.CID
family.BP = family.ROOT / "candidate_cases/rebuild-to-100/blueprints" / family.CID
family.RT = family.ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / family.CID
family.CANONICAL_REPORT = family.VAL_ROOT / f"{family.CID}-canonical-pref-v4/report.json"
family.FULL_REPORT = family.VAL_ROOT / f"{family.CID}-full-pref/report.json"
family.SOURCE_INSTRUCTION = "Install the self-developed unpacked Chrome extension from the Desktop directory into Chrome."
family.ASYNC_EXTENSION = "After the cross-application setup checkpoint is persisted, consume evaluator-owned evidence, preserve the unpacked artifact, and reverify Chrome's exact extension path without replaying the completed installation."
family.PUBLIC_KEYWORD = "unpacked Chrome extension"
family.THEME = "task_scope_or_dependency_change"

if __name__ == "__main__":
    family.main()
