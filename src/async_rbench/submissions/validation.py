"""Treat participant packages as untrusted data, not proof of a genuine run."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def validate_bundle(bundle, policy):
    errors = []

    def fail(code, message):
        if not any(e["code"] == code for e in errors):
            errors.append({"code": code, "message": message})

    result = {"valid": False, "errors": errors, "metrics": {}, "verification": "synthetic-local-only"}
    if not isinstance(bundle, dict):
        fail("schema", "Upload a JSON result package.")
        return result
    if set(bundle) != {"schema", "simulated", "metadata", "manifest", "scores", "evidence", "audit"}:
        fail("schema", "Package fields do not match the local submission format.")
        return result
    if bundle["schema"] != "async-rbench-submission-demo-1":
        fail("schema", "Unsupported submission format.")
    if bundle["simulated"] is not True:
        fail("simulation_only", "This local preview accepts synthetic packages only.")
    meta, manifest, scores, evidence, audit = (bundle[k] for k in ("metadata", "manifest", "scores", "evidence", "audit"))
    if not all(isinstance(v, dict) for v in (meta, manifest, audit)) or not all(isinstance(v, list) for v in (scores, evidence)):
        fail("schema", "Metadata, manifest, scores, evidence or audit has an invalid shape.")
        return result
    if set(meta) != {"agent", "model", "organization", "code_revision"} or any(
        not isinstance(v, str) or not v.strip() or len(v) > 100 or any(ord(c) < 32 for c in v)
        for v in meta.values()
    ):
        fail("schema", "Provide agent, model, organization and code revision only; do not upload credentials.")
    if not re.fullmatch(r"[0-9a-f]{40}", str(meta.get("code_revision", ""))):
        fail("identity", "Code revision must be a full 40-character commit ID.")
    if set(manifest) != {"policy_id", "score_policy_version", "episodes"}:
        fail("schema", "Unexpected manifest fields.")
    if manifest.get("policy_id") != policy["id"] or manifest.get("score_policy_version") != policy["score_policy_version"]:
        fail("policy", "The package must use this preview's pinned evaluation policy.")
    try:
        exact_manifest = digest(manifest.get("episodes")) == digest(policy["episodes"])
    except (ValueError, TypeError):
        exact_manifest = False
    if not exact_manifest:
        fail("manifest_coverage", "Manifest must cover exactly the registered 200 synthetic episode slots.")
    if len(scores) > 1000 or len(evidence) > 1000:
        fail("schema", "Too many records.")
        return result
    score_keys = {"episode_id", "case_id", "instance_id", "repeat", "execution_mode", "event_theme",
                  "model", "score_policy_version", "manifest_sha256", "conformance_passed",
                  "async_drs", "base_task_score", "evidence_sha256"}
    if any(not isinstance(row, dict) or set(row) != score_keys for row in scores):
        fail("schema", "Every score must contain the documented fields, with no private payloads.")
        return result
    if any(not isinstance(row, dict) or set(row) != {"episode_id", "content", "sha256"} for row in evidence):
        fail("schema", "Evidence records have an invalid shape.")
        return result
    if any(not isinstance(r["episode_id"], str) for r in scores + evidence):
        fail("identity", "Episode identifiers must be strings.")
        return result
    try:
        manifest_digest = digest(manifest)
        scores_digest = digest(scores)
    except (ValueError, TypeError):
        fail("score_range", "All scores must be finite JSON numbers.")
        return result
    expected = {row["episode_id"]: row for row in policy["episodes"]}
    ids = [row["episode_id"] for row in scores]
    if len(ids) != len(set(ids)):
        fail("duplicate_episode", "Each episode can be submitted only once.")
    if set(ids) != set(expected):
        fail("coverage", "Missing or unexpected episodes: complete exact coverage is required.")
    evidence_ids = [row["episode_id"] for row in evidence]
    if Counter(evidence_ids) != Counter(expected.keys()):
        fail("evidence_binding", "Provide exactly one evidence record for each episode.")
    evidence_map = {}
    for row in evidence:
        content = row["content"]
        if (not isinstance(content, dict) or set(content) != {"episode_id", "events"}
                or content.get("episode_id") != row["episode_id"] or not isinstance(content.get("events"), list)
                or not 1 <= len(content.get("events", [])) <= 20):
            fail("schema", "Evidence must contain a bounded, sanitized event list.")
            continue
        for event in content["events"]:
            if (not isinstance(event, dict) or set(event) != {"kind", "seq"}
                    or event.get("kind") not in ("task_started", "result_presented", "revision_checked", "task_ended")
                    or type(event.get("seq")) is not int or event["seq"] < 0):
                fail("schema", "Evidence contains unsupported or unsanitized event data.")
        try:
            if digest(content) != row["sha256"]:
                fail("evidence_binding", "Evidence content does not match its hash.")
        except (ValueError, TypeError):
            fail("schema", "Invalid evidence data.")
        evidence_map[row["episode_id"]] = row["sha256"]
    grouped = defaultdict(list)
    for row in scores:
        slot = expected.get(row["episode_id"])
        if slot and any(row.get(key) != value or type(row.get(key)) != type(value) for key, value in slot.items()):
            fail("identity", "Task, instance, repetition, scenario or execution mode does not match the registered slot.")
        if row["model"] != meta.get("model"):
            fail("identity", "All scores must belong to the declared model.")
        if row["score_policy_version"] != policy["score_policy_version"]:
            fail("policy", "Mixed or outdated score policies are not accepted.")
        if row["manifest_sha256"] != manifest_digest:
            fail("manifest_binding", "A score is not bound to this exact manifest.")
        if row["conformance_passed"] is not True:
            fail("conformance", "Every episode must pass conformance checks.")
        if row["evidence_sha256"] != evidence_map.get(row["episode_id"]):
            fail("evidence_binding", "Score and evidence hashes do not match.")
        drs, success = row["async_drs"], row["base_task_score"]
        if type(drs) not in (int, float) or not 0 <= drs <= 1 or type(success) not in (int, float) or success not in (0, 1):
            fail("score_range", "DRS must be in [0, 1]; task success must be 0 or 1.")
        elif slot:
            grouped[slot["event_theme"]].append((drs, success))
    if set(audit) != {"passed", "manifest_sha256", "scores_sha256", "evidence_sha256"} or audit.get("passed") is not True:
        fail("audit", "A passing, complete audit report is required.")
    try:
        bound = (audit.get("manifest_sha256") == manifest_digest and audit.get("scores_sha256") == scores_digest
                 and audit.get("evidence_sha256") == digest(evidence))
    except (ValueError, TypeError):
        bound = False
    if not bound:
        fail("audit_binding", "The audit report must bind to the uploaded scores and evidence.")
    if not errors:
        means = [tuple(sum(row[i] for row in rows) / len(rows) for i in (0, 1)) for rows in grouped.values()]
        result["metrics"] = {"episodes": len(scores), "scenarios": len(grouped),
                             "drs": round(100 * sum(x[0] for x in means) / len(means), 2),
                             "success": round(100 * sum(x[1] for x in means) / len(means), 2)}
        result["valid"] = True
    return result
