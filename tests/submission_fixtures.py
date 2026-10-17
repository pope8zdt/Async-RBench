"""Synthetic runner-shaped records; never used by the application or public board."""
import hashlib
import json
from pathlib import Path

from async_rbench.evaluation.event_store import event_source_integrity_digest
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def runner_files(tmp_path):
    run = tmp_path / "runs"
    run.mkdir()
    keys = ["secure-release", "scheduler-selective-replan"]
    contract = sha((ROOT / "configs/evaluation-contract.json").read_bytes())
    episodes = [dict(episode_id=f"{case}-{repeat}-async", case_id=case, instance_id="seed-1",
                     repeat=repeat, execution_mode="async", guidance="incentive", agent_seed=42,
                     split="test", model="test-model") for case in keys for repeat in range(3)]
    manifest = dict(manifest_version="4.0", evaluation_contract_version="11.0.0",
                    evaluation_contract_sha256=contract, judge_release_sha256="a" * 64,
                    verifier_bundle_sha256={f"{c}::seed-1": "b" * 64 for c in keys},
                    case_bundle_sha256={f"{c}::seed-1": "c" * 64 for c in keys},
                    repetitions=3, guidance="incentive", seed=2026, model="test-model", episodes=episodes)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for slot in episodes:
        folder = run / slot["episode_id"]
        folder.mkdir()
        events = [{"type": "episode_started", "episode_id": slot["episode_id"], "seq": 1,
                   "event_id": slot["episode_id"] + ":1", "actor": "benchmark", "visibility": "kernel_private"},
                  {"type": "episode_ended", "episode_id": slot["episode_id"], "seq": 2,
                   "event_id": slot["episode_id"] + ":2", "actor": "benchmark", "visibility": "kernel_private"}]
        raw = "".join(json.dumps(e) + "\n" for e in events)
        (folder / "event_source.jsonl").write_text(raw, encoding="utf-8")
        score = dict(slot, score_policy_version=SCORE_POLICY_VERSION, score_status="scored",
                     async_drs=0.5 if slot["case_id"] == keys[0] else 0.75,
                     base_task_score=1 if slot["case_id"] == keys[0] else 0,
                     conformance_passed=True, leaderboard_eligible=True, execution_tier="official_track_a",
                     manifest_sha256=sha(manifest_path.read_bytes()), event_source_integrity=event_source_integrity_digest(events),
                     evaluation_contract_version="11.0.0", evaluation_contract_sha256=contract,
                     verifier_bundle_sha256="b" * 64, case_sha256="c" * 64,
                     resource_policy_sha256="d" * 64, scaffold_and_protocol_sha256="e" * 64,
                     event_theme="theme-a" if slot["case_id"] == keys[0] else "theme-b",
                     resource_safety_abort=False, participant_metadata={"api_key": "PRIVATE-DO-NOT-EXPORT"})
        (folder / "score.json").write_text(json.dumps(score), encoding="utf-8")
    audit = {"episode_count": 6, "hard_fail": False, "hard_fail_reasons": [],
             "gates": {name: True for name in ["contract_fixtures_passed", "episodes_present",
                 "artifact_digests_match_current", "manifest_complete", "manifest_digest_match",
                 "no_contract_fixture_failure", "no_hidden_submission_constraint", "no_private_submission_rejection",
                 "no_unknown_child_terminal", "no_official_linear_zero_main_tokens"]},
             "manifest_audit": {"planned_episode_count": 6, "observed_episode_count": 6,
                                "missing_case_ids": [], "missing_episode_ids": [], "unexpected_episode_ids": []}}
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    metadata = dict(agent="Local test agent", model="test-model", organization="Test only", code_revision="f" * 40)
    policy = dict(contract_sha256=contract, judge_sha256="a" * 64, source_sha256="e" * 64, resource_sha256="d" * 64,
                  cases={f"{c}::seed-1": {"theme": f"theme-{'a' if i == 0 else 'b'}", "public_sha256": "c" * 64,
                         "verifier_sha256": "b" * 64} for i, c in enumerate(keys)}, repetitions=3)
    return run, manifest_path, audit_path, metadata, policy
