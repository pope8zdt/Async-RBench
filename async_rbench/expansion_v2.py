"""Evidence contracts and source adapters for the scalable v2 expansion.

The module deliberately separates source artifacts, semantic task candidates,
and promoted benchmark cases.  In particular, an official task configuration
or a final answer is never labelled as a model execution trajectory.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


REAL_TRACE = "real_model_execution_trace"
OFFICIAL_SCENARIO = "official_scenario_configuration"
FINAL_OUTPUT = "public_model_final_output"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def stable_hash(*parts: object, length: int = 12) -> str:
    raw = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def clip(value: object, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _step_excerpt(steps: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    if len(steps) <= limit:
        chosen = steps
    else:
        half = limit // 2
        chosen = steps[:half] + steps[-half:]
    return [
        {
            "step_id": step.get("step_id"),
            "role": step.get("role"),
            "kind": step.get("kind"),
            "content": clip(step.get("content") or step.get("command"), 520),
        }
        for step in chosen
    ]


def collect_osworld(source_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    artifacts: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    for row in read_jsonl(source_path):
        if str(row.get("benchmark")) != "OSWorld":
            continue
        metadata = row.get("source_metadata") or {}
        steps = list(row.get("steps") or [])
        task_id = str(row.get("task_name") or row.get("review_id"))
        source_id = str(row.get("review_id"))
        artifacts.append({
            "artifact_id": source_id,
            "benchmark": "OSWorld",
            "evidence_class": REAL_TRACE,
            "task_id": task_id,
            "source_url": row.get("source_url"),
            "source_revision": row.get("source_revision"),
            "source_sha256": row.get("source_sha256"),
            "eligible_as_trace": True,
        })
        tasks.append({
            "candidate_id": f"osw-{stable_hash(task_id, source_id)}",
            "benchmark": "OSWorld",
            "task_id": task_id,
            "source_record_ids": [source_id],
            "evidence_class": REAL_TRACE,
            "instruction": clip(row.get("instruction"), 1600),
            "source_kind": row.get("source_kind"),
            "source_url": row.get("source_url"),
            "source_revision": row.get("source_revision"),
            "source_sha256": row.get("source_sha256"),
            "features": {
                "domain": metadata.get("domain"),
                "related_apps": metadata.get("related_apps") or [],
                "trace_step_count": metadata.get("trace_step_count") or len(steps),
                "possibility_of_env_change": metadata.get("possibility_of_env_change"),
            },
            "evidence_excerpt": _step_excerpt(steps),
            "source_payload": row,
        })
    return artifacts, tasks


def _swe_rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
    return (
        int(bool(row.get("manifest_solved"))),
        int(row.get("rule_candidate_count") or 0),
        int(row.get("normalized_step_count") or 0),
        str(row.get("review_id") or ""),
    )


def collect_swe(dossier_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = read_jsonl(dossier_path)
    artifacts: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row.get("benchmark")) != "SWE-bench":
            continue
        task_id = str(row.get("task_name") or row.get("review_id"))
        source_id = str(row.get("review_id"))
        grouped[task_id].append(row)
        artifacts.append({
            "artifact_id": source_id,
            "benchmark": "SWE-bench",
            "evidence_class": REAL_TRACE,
            "task_id": task_id,
            "agent": row.get("source_agent"),
            "model": row.get("source_model"),
            "source_failure": row.get("source_failure") or "",
            "eligible_as_trace": not bool(row.get("source_failure")),
        })
    tasks: list[dict[str, Any]] = []
    for task_id, candidates in sorted(grouped.items()):
        usable = [row for row in candidates if not row.get("source_failure")]
        representative = max(usable or candidates, key=_swe_rank)
        proposals = list(representative.get("rule_proposals") or [])
        evidence: list[dict[str, Any]] = []
        for proposal in proposals[:3]:
            evidence.extend(list(proposal.get("evidence") or []))
        evidence.extend(list(representative.get("tail") or [])[-3:])
        tasks.append({
            "candidate_id": f"swe-{stable_hash(task_id)}",
            "benchmark": "SWE-bench",
            "task_id": task_id,
            "source_record_ids": [str(row.get("review_id")) for row in candidates],
            "representative_record_id": representative.get("review_id"),
            "evidence_class": REAL_TRACE,
            "instruction": clip(representative.get("instruction"), 1600),
            "source_kind": "official_public_reasoning_and_execution_trace",
            "source_url": "https://github.com/SWE-bench/experiments",
            "features": {
                "run_count": len(candidates),
                "usable_run_count": len(usable),
                "representative_solved": bool(representative.get("manifest_solved")),
                "normalized_step_count": representative.get("normalized_step_count"),
                "rule_candidate_count": representative.get("rule_candidate_count"),
                "agents": sorted({str(row.get("source_agent")) for row in candidates}),
                "models": sorted({str(row.get("source_model")) for row in candidates}),
            },
            "evidence_excerpt": _step_excerpt(evidence, limit=10),
            "source_payload": representative,
        })
    return artifacts, tasks


def _marble_domain(path: Path) -> str:
    return path.parent.name.lower()


def _marble_task_id(row: dict[str, Any], fallback: int) -> str:
    environment = row.get("environment") or {}
    value = row.get("task_id", environment.get("task_id", fallback))
    # Some Minecraft records contain a constant environment task_id.  The
    # source line remains the stable instance identity in that case.
    return str(value if value not in (None, "") else fallback)


def collect_multiagentbench(
    official_root: Path, public_results_root: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    result_index: dict[tuple[str, str], list[Path]] = defaultdict(list)
    result_artifacts: list[dict[str, Any]] = []
    if public_results_root and public_results_root.exists():
        for path in sorted(public_results_root.rglob("task_*.json")):
            try:
                # The public result repository contains a mixture of plain
                # UTF-8 and UTF-8-with-BOM JSON files.  ``utf-8-sig`` accepts
                # both and prevents valid runs from being silently dropped.
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, OSError):
                continue
            domain = str(payload.get("domain") or path.parent.name).lower()
            task_id = str(payload.get("task_id") or path.stem.removeprefix("task_"))
            result_index[(domain, task_id)].append(path)
            result_artifacts.append({
                "artifact_id": f"mab-output-{stable_hash(path.as_posix())}",
                "benchmark": "MultiAgentBench",
                "evidence_class": FINAL_OUTPUT,
                "task_id": f"{domain}:{task_id}",
                "source_path": path.as_posix(),
                "eligible_as_trace": False,
                "disclosure": "Final output only; no action/interleaving trace.",
            })

    artifacts = list(result_artifacts)
    tasks: list[dict[str, Any]] = []
    for source_file in sorted(official_root.rglob("*_main.jsonl")):
        domain = _marble_domain(source_file)
        for line_number, row in enumerate(read_jsonl(source_file), 1):
            source_task_id = _marble_task_id(row, line_number)
            stable_task_id = f"{domain}:{line_number:03d}"
            official_id = f"mab-config-{domain}-{line_number:03d}"
            artifacts.append({
                "artifact_id": official_id,
                "benchmark": "MultiAgentBench",
                "evidence_class": OFFICIAL_SCENARIO,
                "task_id": stable_task_id,
                "source_path": source_file.as_posix(),
                "source_line": line_number,
                "eligible_as_trace": False,
            })
            matches = result_index.get((domain, source_task_id), [])
            output_preview = ""
            selected_result = None
            if matches:
                selected_result = sorted(matches, key=lambda p: ("aligned_rerun" not in p.as_posix(), p.as_posix()))[0]
                result_payload = json.loads(selected_result.read_text(encoding="utf-8-sig"))
                output_preview = clip(result_payload.get("output"), 900)
            task = row.get("task") or {}
            agents = list(row.get("agents") or [])
            tasks.append({
                "candidate_id": f"mab-{stable_hash(stable_task_id, source_file.as_posix())}",
                "benchmark": "MultiAgentBench",
                "task_id": stable_task_id,
                "official_task_id": source_task_id,
                "source_record_ids": [official_id] + [
                    f"mab-output-{stable_hash(path.as_posix())}" for path in matches
                ],
                "evidence_class": OFFICIAL_SCENARIO,
                "instruction": clip(task.get("content") or row.get("task_content"), 1600),
                "source_kind": "official_multiagent_scenario_with_optional_public_final_output",
                "source_url": "https://github.com/ulab-uiuc/MARBLE",
                "features": {
                    "domain": domain,
                    "coordinate_mode": row.get("coordinate_mode"),
                    "agent_count": len(agents),
                    "relationships": len(row.get("relationships") or []),
                    "public_output_count": len(matches),
                    "has_execution_trace": False,
                },
                "evidence_excerpt": ([{
                    "step_id": "scenario",
                    "role": "benchmark",
                    "kind": "task_configuration",
                    "content": clip(task.get("content"), 650),
                }] + ([{
                    "step_id": "public_output",
                    "role": "agent_system",
                    "kind": "final_output_only",
                    "content": output_preview,
                }] if output_preview else [])),
                "source_payload": row,
                "selected_public_result": selected_result.as_posix() if selected_result else None,
            })
    return artifacts, tasks


def structural_screen(task: dict[str, Any]) -> dict[str, Any]:
    """Apply auditable evidence gates before expensive semantic review."""
    benchmark = str(task["benchmark"])
    features = task.get("features") or {}
    reasons: list[str] = []
    decision = "semantic_review"
    if not str(task.get("instruction") or "").strip():
        return {"decision": "reject", "reasons": ["missing_task_instruction"]}
    if benchmark == "OSWorld":
        if int(features.get("trace_step_count") or 0) < 8:
            decision, reasons = "reject", ["trace_too_short_for_causal_boundary"]
        else:
            reasons.append("real_execution_trace_with_action_observation_history")
            if str(features.get("domain")) == "multi_apps":
                reasons.append("cross_application_dependency")
    elif benchmark == "SWE-bench":
        if int(features.get("usable_run_count") or 0) == 0:
            decision, reasons = "reject", ["no_usable_execution_trace"]
        elif int(features.get("normalized_step_count") or 0) < 10:
            decision, reasons = "reject", ["trace_too_short_for_pre_and_post_result_work"]
        else:
            reasons.extend(["real_execution_trace", "source_task_has_runnable_evaluator"])
    elif benchmark == "MultiAgentBench":
        if int(features.get("agent_count") or 0) < 2:
            decision, reasons = "reject", ["not_a_multiagent_scenario"]
        elif int(features.get("public_output_count") or 0) == 0:
            decision, reasons = "expand_evidence", ["official_task_but_no_public_run_output"]
        else:
            reasons.extend(["official_multiagent_task", "public_final_output_available"])
            reasons.append("full_interleaving_trace_absent_requires_strict_review")
    else:
        decision, reasons = "reject", ["unsupported_benchmark"]
    return {"decision": decision, "reasons": reasons}


def source_report(artifacts: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    screens = [task.get("structural_screen") or {} for task in tasks]
    return {
        "schema_version": "async-rbench-expansion-source-report-v2",
        "artifact_count": len(artifacts),
        "semantic_task_count": len(tasks),
        "artifact_benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in artifacts).items())),
        "task_benchmark_counts": dict(sorted(Counter(row["benchmark"] for row in tasks).items())),
        "evidence_class_counts": dict(sorted(Counter(row["evidence_class"] for row in artifacts).items())),
        "structural_decision_counts": dict(sorted(Counter(row.get("decision") for row in screens).items())),
        "disclosure": {
            "OSWorld": "Officially published real AutoGLM execution trajectories.",
            "SWE-bench": "Public model reasoning/execution traces distributed from SWE-bench experiment records.",
            "MultiAgentBench": "Official task configurations plus public third-party final outputs; final outputs are not action trajectories.",
        },
    }
