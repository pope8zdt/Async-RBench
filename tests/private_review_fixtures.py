"""Full-size synthetic evidence. Never real benchmark results."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

from async_rbench.evaluation.event_store import event_source_integrity_digest
from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION
from async_rbench.submissions.artifacts import GATES, export_receipt


def full_evidence(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    runs = root / "runs"
    runs.mkdir()
    sha = lambda b: hashlib.sha256(b).hexdigest()
    project = Path(__file__).resolve().parents[1]
    contract = sha((project / "configs/evaluation-contract.json").read_bytes())
    cases = {f"case-{i:03}::seed-1": {"theme": f"theme-{i % 8}", "public_sha256": "c" * 64,
                                     "verifier_sha256": "b" * 64} for i in range(200)}
    slots = [dict(episode_id=f"case-{i:03}-{r}-async", case_id=f"case-{i:03}", instance_id="seed-1",
                  repeat=r, execution_mode="async", guidance="incentive", agent_seed=42,
                  split="test", model="simulation-model") for i in range(200) for r in range(3)]
    manifest = dict(manifest_version="4.0", evaluation_contract_version="11.0.0",
                    evaluation_contract_sha256=contract, judge_release_sha256="a" * 64,
                    verifier_bundle_sha256={k: "b" * 64 for k in cases},
                    case_bundle_sha256={k: "c" * 64 for k in cases}, repetitions=3,
                    guidance="incentive", model="simulation-model", episodes=slots)
    mp = root / "manifest.json"
    mp.write_text(json.dumps(manifest), encoding="utf-8")
    mh = sha(mp.read_bytes())
    for i, slot in enumerate(slots):
        folder = runs / slot["episode_id"]
        folder.mkdir()
        events = [{"episode_id": slot["episode_id"], "seq": 1, "type": "episode_ended",
                   "event_id": slot["episode_id"] + ":1", "visibility": "kernel_private",
                   "note": "PRIVATE_EVIDENCE_NOT_PUBLIC"}]
        (folder / "event_source.jsonl").write_text(json.dumps(events[0]) + "\n", encoding="utf-8")
        score = dict(slot, score_policy_version=SCORE_POLICY_VERSION, score_status="scored",
                     async_drs=.625, base_task_score=1 if i % 2 == 0 else 0,
                     conformance_passed=True, leaderboard_eligible=True, execution_tier="official_track_a",
                     manifest_sha256=mh, event_source_integrity=event_source_integrity_digest(events),
                     evaluation_contract_version="11.0.0", evaluation_contract_sha256=contract,
                     verifier_bundle_sha256="b" * 64, case_sha256="c" * 64,
                     resource_policy_sha256="d" * 64, scaffold_and_protocol_sha256="e" * 64,
                     event_theme=f"theme-{(i // 3) % 8}", resource_safety_abort=False)
        (folder / "score.json").write_text(json.dumps(score), encoding="utf-8")
    ap = root / "audit.json"
    ap.write_text(json.dumps(dict(episode_count=600, hard_fail=False, hard_fail_reasons=[],
        gates={k: True for k in GATES}, manifest_audit=dict(planned_episode_count=600,
        observed_episode_count=600, missing_case_ids=[], missing_episode_ids=[], unexpected_episode_ids=[]))), encoding="utf-8")
    metadata = dict(agent="Simulation agent", model="simulation-model", organization="Local test only", code_revision="f" * 40)
    policy = dict(contract_sha256=contract, judge_sha256="a" * 64, source_sha256="e" * 64,
                  resource_sha256="d" * 64, cases=cases, repetitions=3)
    return runs, mp, ap, metadata, policy


def archive_files(evidence):
    runs, manifest, audit, meta, _ = evidence
    files = {"manifest.json": manifest.read_bytes(), "audit.json": audit.read_bytes(),
             "receipt.json": json.dumps(export_receipt(runs, manifest, audit, meta)).encode()}
    for p in runs.glob("*/*"):
        files["runs/" + p.relative_to(runs).as_posix()] = p.read_bytes()
    return files


def zip_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        for path, raw in files.items():
            z.writestr(path, raw)
    return stream.getvalue()
