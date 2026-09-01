from __future__ import annotations

import finalize_fourth_osworld_family as family

family.SRC = family.ROOT / "candidate_cases/osw-cross-app-artifact-c3093402e5"
family.OLD = "osw-cross-app-artifact-c3093402e5"
family.CID = "osw-dependency-unblock-ba52abb8a2"
family.OLDN = "osw_cross_app_artifact_c3093402e5"
family.NEWN = "osw_dependency_unblock_ba52abb8a2"
family.OLDP = "osw_audio_6"
family.NEWP = "osw_extension_7"
family.OLDS = "osworld:multi_apps:778efd0a-153f-4842-9214-f05fc176b877"
family.NEWS = "osworld:chrome:6766f2b8-8a72-417f-a9e5-56fcaa735837"
family.CASE = family.ROOT / "candidate_cases" / family.CID
family.BP = family.ROOT / "candidate_cases/rebuild-to-100/blueprints" / family.CID
family.RT = family.ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / family.CID
family.CANONICAL_REPORT = family.VAL_ROOT / f"{family.CID}-canonical/report.json"
family.FULL_REPORT = family.VAL_ROOT / f"{family.CID}-full/report.json"
family.SOURCE_INSTRUCTION = "Unzip helloExtension on the Desktop and configure that unpacked directory in Chrome extensions."
family.ASYNC_EXTENSION = "After the Chrome configuration checkpoint is persisted, consume evaluator-owned evidence, preserve the extracted extension directory, and reverify the exact unpacked-extension path without replaying completed setup."
family.PUBLIC_KEYWORD = "Chrome extensions"
family.THEME = "delayed_authoritative_result"

if __name__ == "__main__":
    family.main()
