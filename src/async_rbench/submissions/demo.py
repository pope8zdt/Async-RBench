"""Deterministic synthetic packages, not model runs or paper results."""
from pathlib import Path
from copy import deepcopy
import json

from ..evaluation.weighting import SCORE_POLICY_VERSION
from .validation import digest

ROOT = Path(__file__).resolve().parents[3]


def demo_policy():
    corpus = json.loads((ROOT / "docs/site/published/data/corpus.json").read_text(encoding="utf-8"))
    themes = sorted(corpus["scenario_counts"])
    # Scenario assignments are deliberately synthetic, not reconstructed private labels.
    episodes = [dict(episode_id=f"demo-{task['id']}-async-0", case_id=task["id"], instance_id="seed-1",
                     repeat=0, execution_mode="async", event_theme=themes[i % len(themes)])
                for i, task in enumerate(corpus["tasks"])]
    return {"id": "local-synthetic-200-v1", "score_policy_version": SCORE_POLICY_VERSION, "episodes": episodes}


def demo_bundle(policy=None, variant=0):
    policy = policy or demo_policy()
    manifest = {"policy_id": policy["id"], "score_policy_version": policy["score_policy_version"], "episodes": deepcopy(policy["episodes"])}
    evidence, scores = [], []
    for i, slot in enumerate(policy["episodes"]):
        content = {"episode_id": slot["episode_id"], "events": [
            {"seq": 1, "kind": "task_started"}, {"seq": 2, "kind": "result_presented"},
            {"seq": 3, "kind": "revision_checked"}, {"seq": 4, "kind": "task_ended"}]}
        evidence.append({"episode_id": slot["episode_id"], "content": content, "sha256": digest(content)})
        scores.append({**slot, "model": "Synthetic model", "score_policy_version": policy["score_policy_version"],
                       "manifest_sha256": digest(manifest), "conformance_passed": True,
                       "async_drs": ((i + variant) % 6 + 4) / 10, "base_task_score": int(i % 4 != 0),
                       "evidence_sha256": digest(content)})
    return {"schema": "async-rbench-submission-demo-1", "simulated": True,
            "metadata": {"agent": "Demo agent", "model": "Synthetic model", "organization": "Local evaluation lab", "code_revision": "a" * 40},
            "manifest": manifest, "scores": scores, "evidence": evidence,
            "audit": {"passed": True, "manifest_sha256": digest(manifest), "scores_sha256": digest(scores), "evidence_sha256": digest(evidence)}}
