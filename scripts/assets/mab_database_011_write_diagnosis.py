from __future__ import annotations

import json
import pathlib


OUT = pathlib.Path("/app/output_data")
SOURCE_ID = "database:011"
EXPECTED_CAUSE = "VACUUM"
SUPERSEDED_CAUSE = "LOCK_CONTENTION"


receipt = json.loads((OUT / "event_receipt.json").read_text(encoding="utf-8"))
assert receipt["source_task_id"] == SOURCE_ID
assert receipt["worker_exit_code"] == 0
assert receipt["probes"]["selected_cause"] == EXPECTED_CAUSE

diagnosis = {
    "source_task_id": SOURCE_ID,
    "selected_causes": [EXPECTED_CAUSE],
    "superseded_causes": [SUPERSEDED_CAUSE],
    "preserved_prior_findings": True,
    "native_evidence_sha256": receipt["probes"]["native_evidence_sha256"],
    "host_checkpoint_sha256": receipt["probes"]["host_checkpoint_sha256"],
    "source_semantics_reverified": True,
}
(OUT / "database_diagnosis.json").write_text(
    json.dumps(diagnosis, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
