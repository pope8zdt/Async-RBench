"""Read existing runner artifacts. No execution, network, or model calls.

A receipt is private review material, not an authenticity certificate. The only
public material is the small allowlisted summary built by github_flow.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re

from ..evaluation.event_store import event_source_integrity_digest
from ..evaluation.weighting import SCORE_POLICY_VERSION
from ..evaluation.version import EVALUATION_CONTRACT_VERSION
from ..spec import case_instance_key, discover_case_instances
from .validation import digest

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "async-rbench-community-receipt-1"
IDENTITY = ("episode_id", "case_id", "instance_id", "repeat", "execution_mode", "guidance", "agent_seed", "split", "model")
SCORE_FIELDS = (*IDENTITY, "score_policy_version", "score_status", "async_drs", "base_task_score",
                "conformance_passed", "leaderboard_eligible", "execution_tier", "manifest_sha256",
                "event_source_integrity", "evaluation_contract_version", "evaluation_contract_sha256",
                "verifier_bundle_sha256", "case_sha256", "resource_policy_sha256",
                "scaffold_and_protocol_sha256", "event_theme", "resource_safety_abort")
GATES = {"contract_fixtures_passed", "episodes_present", "artifact_digests_match_current",
         "manifest_complete", "manifest_digest_match", "no_contract_fixture_failure",
         "no_hidden_submission_constraint", "no_private_submission_rejection",
         "no_unknown_child_terminal", "no_official_linear_zero_main_tokens"}
HEX = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,199}\Z")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        obj = {}
        for k, v in items:
            if k in obj:
                raise ValueError("Duplicate JSON field")
            obj[k] = v
        return obj
    def constant(_):
        raise ValueError("Non-finite JSON number")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def _read(path, limit=64 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Missing, linked, or oversized artifact")
    return path.read_bytes()


def _metadata(value):
    if not isinstance(value, dict) or set(value) != {"agent", "model", "organization", "code_revision"}:
        raise ValueError("Supply agent, model, organization and code_revision only")
    for key in ("agent", "model", "organization"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[\w .:/()-]{1,100}", value[key]) or not value[key].strip():
            raise ValueError("Use short plain-text public names")
    if not isinstance(value["code_revision"], str) or not re.fullmatch(r"[0-9a-f]{40}", value["code_revision"]):
        raise ValueError("A full code commit is required")
    return dict(value)


def export_receipt(run_root, manifest_path, audit_path, metadata):
    metadata = _metadata(metadata)
    root = Path(run_root).resolve()
    manifest_bytes = _read(manifest_path)
    manifest = strict_json(manifest_bytes)
    audit_bytes = _read(audit_path)
    original_audit = strict_json(audit_bytes)
    if not isinstance(manifest, dict) or not isinstance(original_audit, dict):
        raise ValueError("Manifest and audit must be JSON objects")
    scores, evidence = [], []
    observed = list(root.glob("*/score.json"))
    episodes = manifest.get("episodes") or []
    if not isinstance(episodes, list) or any(not isinstance(slot, dict) for slot in episodes):
        raise ValueError("Invalid manifest episodes")
    expected_dirs = set()
    for slot in episodes:
        episode = slot.get("episode_id")
        if not isinstance(episode, str) or not NAME.fullmatch(episode):
            raise ValueError("Invalid episode identity")
        folder = root / episode
        if folder.is_symlink() or not folder.resolve().is_relative_to(root):
            raise ValueError("Invalid episode artifact path")
        expected_dirs.add(folder.resolve())
        score_bytes = _read(folder / "score.json")
        score = strict_json(score_bytes)
        if not isinstance(score, dict):
            raise ValueError("Score must be a JSON object")
        event_bytes = _read(folder / "event_source.jsonl", 256 * 1024 * 1024)
        events = [strict_json(line) for line in event_bytes.splitlines() if line.strip()]
        if not events or any(not isinstance(e, dict) or e.get("episode_id") != episode for e in events):
            raise ValueError("Invalid event source membership")
        if any(type(e.get("seq")) is not int for e in events) or len({e["seq"] for e in events}) != len(events):
            raise ValueError("Invalid event sequence")
        integrity = event_source_integrity_digest(events)
        if score.get("event_source_integrity") != integrity:
            raise ValueError("Score and event source digest differ")
        scores.append({key: score.get(key) for key in SCORE_FIELDS})
        evidence.append({"episode_id": episode, "score_sha256": sha(score_bytes),
                         "event_source_sha256": sha(event_bytes), "event_source_integrity": integrity,
                         "event_count": len(events)})
    if {p.parent.resolve() for p in observed} != expected_dirs:
        raise ValueError("Unexpected or missing score artifacts")
    receipt = {"schema": SCHEMA, "metadata": metadata, "manifest_json": manifest_bytes.decode("utf-8"),
               "scores": scores, "evidence": evidence, "audit_sha256": sha(audit_bytes),
               "audit": {key: original_audit.get(key) for key in ("episode_count", "hard_fail", "hard_fail_reasons", "gates", "manifest_audit")}}
    result = validate_receipt(receipt)
    if not result["valid"]:
        raise ValueError("; ".join(result["errors"]))
    return receipt


def validate_receipt(receipt, policy=None):
    result = {"valid": False, "rankable": False, "errors": [], "metrics": None}
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    try:
        require(isinstance(receipt, dict) and set(receipt) == {"schema", "metadata", "manifest_json", "scores", "evidence", "audit_sha256", "audit"}, "Use a runner-exported community receipt")
        require(receipt["schema"] == SCHEMA, "Demo packages are not result submissions")
        metadata = _metadata(receipt["metadata"])
        digest(receipt)  # Reject NaN, infinity and non-JSON values before use.
        require(isinstance(receipt["manifest_json"], str), "Missing original manifest")
        manifest = strict_json(receipt["manifest_json"])
        require(isinstance(manifest, dict), "Invalid manifest")
        manifest_hash = sha(receipt["manifest_json"].encode("utf-8"))
        require(manifest.get("manifest_version") == "4.0", "Unsupported manifest version")
        require(manifest.get("evaluation_contract_version") == EVALUATION_CONTRACT_VERSION, "Incompatible evaluation contract")
        contract_hash = sha((ROOT / "configs/evaluation-contract.json").read_bytes())
        require(manifest.get("evaluation_contract_sha256") == (policy or {}).get("contract_sha256", contract_hash), "Evaluation contract digest mismatch")
        require(manifest.get("model") == metadata["model"], "Manifest model does not match metadata")
        require(type(manifest.get("repetitions")) is int and 1 <= manifest["repetitions"] <= 10, "Invalid repetitions")
        require(manifest.get("guidance") == "incentive", "Use the incentive protocol")
        require(isinstance(manifest.get("judge_release_sha256"), str) and HEX.fullmatch(manifest["judge_release_sha256"]), "Missing judge release binding")
        slots = manifest.get("episodes")
        require(isinstance(slots, list) and 0 < len(slots) <= 2000, "Invalid manifest episode count")
        scores, evidence = receipt["scores"], receipt["evidence"]
        require(isinstance(scores, list) and isinstance(evidence, list), "Missing scores or evidence")
        def by_id(rows):
            require(all(isinstance(row, dict) and isinstance(row.get("episode_id"), str) and NAME.fullmatch(row["episode_id"]) for row in rows), "Invalid episode identity")
            mapped = {row["episode_id"]: row for row in rows}
            require(len(mapped) == len(rows), "Duplicate episode identity")
            return mapped
        slot_map, score_map, evidence_map = by_id(slots), by_id(scores), by_id(evidence)
        require(set(slot_map) == set(score_map) == set(evidence_map), "Episode coverage differs from the manifest")
        audit = receipt["audit"]
        require(isinstance(audit, dict) and set(audit) == {"episode_count", "hard_fail", "hard_fail_reasons", "gates", "manifest_audit"}, "Incomplete audit")
        require(audit.get("hard_fail") is False and audit.get("hard_fail_reasons") == [], "Audit failed")
        require(type(audit.get("episode_count")) is int and audit["episode_count"] == len(slots), "Audit coverage mismatch")
        require(isinstance(audit.get("gates"), dict) and GATES <= set(audit["gates"]) and all(v is True for v in audit["gates"].values()), "Missing or failed audit gates")
        ma = audit.get("manifest_audit")
        require(isinstance(ma, dict) and all(ma.get(k) == [] for k in ("missing_case_ids", "missing_episode_ids", "unexpected_episode_ids")) and ma.get("planned_episode_count") == len(slots) and ma.get("observed_episode_count") == len(slots), "Incomplete manifest audit")
        require(isinstance(receipt["audit_sha256"], str) and HEX.fullmatch(receipt["audit_sha256"]), "Missing audit digest")
        groups = defaultdict(list)
        identities = set()
        resources, sources = set(), set()
        for eid, slot in slot_map.items():
            row, evidence_row = score_map[eid], evidence_map[eid]
            require(set(row) == set(SCORE_FIELDS), "Unexpected score fields")
            require(all(type(row[k]) is type(slot.get(k)) and row[k] == slot.get(k) for k in IDENTITY), "Score identity differs from manifest")
            require(all(isinstance(slot.get(k), str) and NAME.fullmatch(slot[k]) for k in ("case_id", "instance_id")), "Invalid case identity")
            require(type(slot.get("repeat")) is int and 0 <= slot["repeat"] < manifest["repetitions"], "Invalid repetition")
            require(type(slot.get("agent_seed")) is int and slot["agent_seed"] > 0, "Invalid agent seed")
            require(slot["execution_mode"] == "async" and slot["guidance"] == "incentive" and slot["model"] == metadata["model"], "Use a single-model Async manifest")
            require(slot.get("split") in {"calibration", "development", "test"}, "Invalid registered split")
            key = case_instance_key(slot["case_id"], slot["instance_id"])
            ident = (key, slot["repeat"])
            require(ident not in identities, "Duplicate task repetition")
            identities.add(ident)
            require(row["score_policy_version"] == SCORE_POLICY_VERSION and row["score_status"] == "scored", "Incompatible or unscored result")
            require(row["conformance_passed"] is True and row["leaderboard_eligible"] is True and row["execution_tier"] == "official_track_a" and row["resource_safety_abort"] is False, "Run does not meet the evaluation protocol")
            require(row["manifest_sha256"] == manifest_hash and row["evaluation_contract_sha256"] == manifest["evaluation_contract_sha256"] and row["evaluation_contract_version"] == EVALUATION_CONTRACT_VERSION, "Score manifest or contract binding mismatch")
            for field in ("verifier_bundle_sha256", "case_sha256", "resource_policy_sha256", "scaffold_and_protocol_sha256"):
                require(isinstance(row[field], str) and HEX.fullmatch(row[field]), "Missing artifact provenance")
            require(row["verifier_bundle_sha256"] == manifest.get("verifier_bundle_sha256", {}).get(key) and row["case_sha256"] == manifest.get("case_bundle_sha256", {}).get(key), "Case or verifier binding mismatch")
            require(set(evidence_row) == {"episode_id", "score_sha256", "event_source_sha256", "event_source_integrity", "event_count"}, "Unexpected evidence fields")
            require(all(isinstance(evidence_row[k], str) and HEX.fullmatch(evidence_row[k]) for k in ("score_sha256", "event_source_sha256", "event_source_integrity")), "Invalid evidence hash")
            require(evidence_row["event_source_integrity"] == row["event_source_integrity"] and type(evidence_row["event_count"]) is int and evidence_row["event_count"] > 0, "Evidence binding mismatch")
            require(type(row["async_drs"]) in (int, float) and 0 <= row["async_drs"] <= 1 and type(row["base_task_score"]) in (int, float) and row["base_task_score"] in (0, 1), "Invalid score range")
            theme = row["event_theme"]
            require(isinstance(theme, str) and bool(theme), "Missing event theme")
            if policy:
                trusted = policy["cases"].get(key)
                require(trusted is not None and theme == trusted["theme"] and row["case_sha256"] == trusted["public_sha256"] and row["verifier_bundle_sha256"] == trusted["verifier_sha256"], "Trusted case, theme or verifier differs")
                require(row["scaffold_and_protocol_sha256"] == policy["source_sha256"], "Runtime source revision differs")
                require(row["resource_policy_sha256"] == policy["resource_sha256"], "Frozen resource policy differs")
            groups[(theme, slot["repeat"])].append((row["async_drs"], row["base_task_score"]))
            resources.add(row["resource_policy_sha256"])
            sources.add(row["scaffold_and_protocol_sha256"])
        require(len(resources) == len(sources) == 1, "Mixed runtime settings")
        if policy:
            require(manifest["judge_release_sha256"] == policy["judge_sha256"], "Trusted judge release differs")
            expected = {(key, r) for key in policy["cases"] for r in range(policy["repetitions"])}
            result["rankable"] = identities == expected and manifest["repetitions"] == policy["repetitions"]
        result["valid"] = True
        result["coverage"] = {"tasks": len({k for k, _ in identities}), "episodes": len(slots), "repetitions": manifest["repetitions"]}
        if result["rankable"]:
            means = [tuple(sum(x[i] for x in values) / len(values) for i in (0, 1)) for values in groups.values()]
            result["metrics"] = {"drs": round(100 * sum(x[0] for x in means) / len(means), 2), "success": round(100 * sum(x[1] for x in means) / len(means), 2), **result["coverage"]}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
        result.update(valid=False, rankable=False, metrics=None)
        result["errors"] = [str(exc) if isinstance(exc, ValueError) else "Malformed receipt fields"]
    return result


def verify_evidence(receipt, run_root, manifest_path, audit_path):
    rebuilt = export_receipt(run_root, manifest_path, audit_path, receipt["metadata"])
    if digest(rebuilt) != digest(receipt):
        raise ValueError("Original evidence no longer matches the receipt")


def trusted_policy(judge_root):
    """Pin local maintainer-owned benchmark and judge bytes; never run them."""
    import yaml
    from ..judge import JudgeBundleProvider
    from ..private_eval import verifier_bundle_sha256
    from ..evaluation.case_bundle import public_case_bundle_sha256
    from ..evaluation.runner import _source_digest
    from ..evaluation.resource_policy import load_resource_policy
    provider = JudgeBundleProvider(Path(judge_root))
    release_raw = _read(provider.root / "release.json")
    release = strict_json(release_raw)
    cases = {}
    for instance in discover_case_instances(ROOT):
        raw = yaml.safe_load(_read(provider.evaluator_dir(instance.case_id, instance.instance_id) / "case.yaml"))
        theme = raw.get("classification", {}).get("primary_event_theme")
        if not isinstance(theme, str) or not theme:
            raise ValueError("Judge is missing a registered event theme")
        cases[case_instance_key(instance.case_id, instance.instance_id)] = {
            "theme": theme, "public_sha256": public_case_bundle_sha256(instance.case_dir),
            "verifier_sha256": verifier_bundle_sha256(provider.verifier_dir(instance.case_id, instance.instance_id))}
    contract_raw = (ROOT / "configs/evaluation-contract.json").read_bytes()
    contract = strict_json(contract_raw)
    themes = {row["theme"] for row in cases.values()}
    if contract.get("status") != "frozen" or len(cases) != 200 or themes != set(contract["case_event_themes"]) or any(sum(v["theme"] == t for v in cases.values()) != 25 for t in themes):
        raise ValueError("Expected the frozen 200-task, eight-scenario registry")
    # The explicit local judge is the trust root, not a release claimed by an upload.
    if not release.get("public_release_sha256"):
        raise ValueError("Judge release has no public release binding")
    return {"contract_sha256": sha(contract_raw), "judge_sha256": sha(release_raw),
            "source_sha256": _source_digest(ROOT), "resource_sha256": load_resource_policy(ROOT)[1],
            "cases": cases, "repetitions": 3}
