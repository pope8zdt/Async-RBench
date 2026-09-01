from __future__ import annotations

import finalize_fourth_osworld_family as family

family.SRC = family.ROOT / "candidate_cases/osw-dependency-unblock-dd5b6417f3"
family.OLD = "osw-dependency-unblock-dd5b6417f3"
family.CID = "osw-cross-app-artifact-c3093402e5"
family.OLDN = "osw_impress_5d5b6417f3"
family.NEWN = "osw_cross_app_artifact_c3093402e5"
family.OLDP = "osw_impress_5"
family.NEWP = "osw_audio_6"
family.OLDS = "osworld:libreoffice_impress:a53f80cd-4a90-4490-8310-097b011433f6"
family.NEWS = "osworld:multi_apps:778efd0a-153f-4842-9214-f05fc176b877"
family.CASE = family.ROOT / "candidate_cases" / family.CID
family.BP = family.ROOT / "candidate_cases/rebuild-to-100/blueprints" / family.CID
family.RT = family.ROOT / "candidate_cases/rebuild-to-100/runtime-osworld/cases" / family.CID
family.CANONICAL_REPORT = family.VAL_ROOT / f"{family.CID}-canonical/report.json"
family.FULL_REPORT = family.VAL_ROOT / f"{family.CID}-full/report.json"
family.SOURCE_INSTRUCTION = "Extract the soundtrack from planet.mp4 as planet.wav and use it as background audio in the first slide of the presentation."
family.ASYNC_EXTENSION = "After the presentation artifact is persisted, consume evaluator-owned evidence, preserve the extracted audio identity, and reverify the embedded slide-audio relationship without replaying completed work."
family.PUBLIC_KEYWORD = "background audio"
family.THEME = "task_scope_or_dependency_change"

if __name__ == "__main__":
    family.main()
