import json
import tempfile
import unittest
from pathlib import Path

from async_rbench.native_runtime_registry import (
    ENVIRONMENT_SMOKE_READY_STATUS,
    OSWORLD_SMOKE_PROFILE,
    READY_STATUS,
    environment_smoke_qualification,
    qualification,
    read_registry,
    write_registry,
)


class NativeRuntimeRegistryTests(unittest.TestCase):
    def test_daemon_availability_alone_never_qualifies_a_case(self):
        self.assertEqual(qualification(None, benchmark="SWE-bench", source_task_id="x"), (False, "case_runtime_not_validated"))

    def test_all_native_checks_are_required(self):
        entry = {
            "case_id": "c1",
            "benchmark": "SWE-bench",
            "source_task_id": "x",
            "status": READY_STATUS,
            "schema_version": "source-native-runtime-qualification-v1",
            "checks": {
                "immutable_environment_bound": True,
                "gold_evaluator_resolved": True,
                "native_reproduction_executed": True,
                "native_checkpoint_changed_state": True,
                "audit_chain_valid": False,
            },
        }
        self.assertEqual(qualification(entry, benchmark="SWE-bench", source_task_id="x"), (False, "case_runtime_validation_incomplete"))
        entry["checks"]["audit_chain_valid"] = True
        self.assertEqual(qualification(entry, benchmark="SWE-bench", source_task_id="x"), (True, None))

    def test_legacy_gold_status_is_restricted_to_swe_schema(self):
        entry = {
            "case_id": "c1",
            "benchmark": "OSWorld",
            "source_task_id": "x",
            "status": READY_STATUS,
            "schema_version": "source-native-runtime-qualification-v1",
            "checks": {name: True for name in (
                "immutable_environment_bound", "gold_evaluator_resolved",
                "native_reproduction_executed", "native_checkpoint_changed_state",
                "audit_chain_valid",
            )},
        }
        self.assertEqual(
            qualification(entry, benchmark="OSWorld", source_task_id="x"),
            (False, "case_runtime_validation_incomplete"),
        )
        entry["benchmark"] = "SWE-bench"
        entry["schema_version"] = "untrusted-schema"
        self.assertEqual(
            qualification(entry, benchmark="SWE-bench", source_task_id="x"),
            (False, "case_runtime_validation_incomplete"),
        )

    def test_registry_round_trip_and_duplicate_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.jsonl"
            write_registry(path, [{"case_id": "b"}, {"case_id": "a"}])
            self.assertEqual(list(read_registry(path)), ["a", "b"])
            path.write_text(json.dumps({"case_id": "a"}) + "\n" + json.dumps({"case_id": "a"}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                read_registry(path)

    def test_osworld_environment_smoke_is_valid_but_not_runtime_ready(self):
        entry = {
            "case_id": "osw-c1",
            "benchmark": "OSWorld",
            "source_task_id": "OSWorld:chrome:x",
            "status": ENVIRONMENT_SMOKE_READY_STATUS,
            "qualification_profile": OSWORLD_SMOKE_PROFILE,
            "execution_scope": "infrastructure_smoke",
            "checks": {
                "official_config_bound": True,
                "upstream_dispatch_bound": True,
                "provider_launch_configuration_resolved": True,
                "local_runtime_started": True,
                "reset_reproducible": True,
                "local_state_changed": True,
                "evaluator_control_path_scored": True,
                "audit_chain_valid": True,
                "real_vm_executed": False,
                "model_episode_executed": False,
                "official_task_setup_executed": False,
                "official_gold_metric_executed": False,
            },
            "environment": {
                "adapter": "async_rbench.osworld_runtime.LocalOSWorldEnvironment",
                "scope": "infrastructure_only",
                "real_vm": False,
                "model_episode": False,
            },
            "score_probe": {
                "kind": "official_terminal_fail_control_path",
                "score": 0.0,
                "expected_score": 0.0,
                "native_metric_executed": False,
                "real_vm_executed": False,
                "model_episode": False,
            },
            "checkpoint_smoke": {
                "baseline_revision": "baseline",
                "checkpoint_revision": "changed",
                "restored_revision": "baseline",
            },
        }
        self.assertEqual(
            environment_smoke_qualification(
                entry, benchmark="OSWorld", source_task_id="OSWorld:chrome:x"
            ),
            (True, None),
        )
        self.assertEqual(
            qualification(entry, benchmark="OSWorld", source_task_id="OSWorld:chrome:x"),
            (False, "environment_smoke_only_not_native_runtime"),
        )
        self.assertEqual(
            qualification(entry, benchmark="MultiAgentBench", source_task_id="OSWorld:chrome:x"),
            (False, "runtime_registry_source_mismatch"),
        )
        entry["environment"]["real_vm"] = True
        self.assertEqual(
            qualification(entry, benchmark="OSWorld", source_task_id="OSWorld:chrome:x"),
            (False, "case_runtime_validation_incomplete"),
        )


if __name__ == "__main__":
    unittest.main()
