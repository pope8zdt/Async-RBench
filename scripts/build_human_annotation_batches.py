"""Build fixed-choice task/run annotation batches and an academic review UI."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from async_rbench.human_review import (  # noqa: E402
    RUN_REVIEW_QUESTIONS,
    TASK_REVIEW_QUESTIONS,
    run_review_decision,
    run_review_recommendation,
    run_review_template,
    task_review_decision,
    task_review_recommendation,
    task_review_template,
)
from async_rbench.trajectory_curation import read_jsonl, write_jsonl  # noqa: E402


def _round_robin(rows: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    buckets: dict[tuple[str, ...], list[dict]] = {}
    for row in rows:
        screen = row.get("codex_screen") or {}
        values = {
            "decision": str(screen.get("decision") or ""),
            "family": str(screen.get("family") or ""),
            "benchmark": str(row.get("benchmark") or ""),
            "agent": str(row.get("source_agent") or ""),
            "model": str(row.get("source_model") or ""),
        }
        key = tuple(values[field] for field in key_fields)
        buckets.setdefault(key, []).append(row)
    for bucket in buckets.values():
        bucket.sort(key=lambda row: str(row.get("review_id") or row.get("task_name") or ""))
    output: list[dict] = []
    keys = sorted(buckets)
    while keys:
        next_keys = []
        for key in keys:
            output.append(buckets[key].pop(0))
            if buckets[key]:
                next_keys.append(key)
        keys = next_keys
    return output


def _representatives(rows: list[dict], limit: int = 3) -> list[dict]:
    chosen: list[dict] = []
    used_agents: set[str] = set()
    used_models: set[str] = set()
    remaining = list(rows)
    while remaining and len(chosen) < limit:
        best = max(remaining, key=lambda row: (
            int((row.get("codex_screen") or {}).get("decision") == "promote_to_human"),
            int(str(row.get("source_agent") or "") not in used_agents),
            int(str(row.get("source_model") or "") not in used_models),
            int(bool((row.get("codex_screen") or {}).get("evidence_step_ids"))),
            int(row.get("normalized_step_count") or 0),
            str(row.get("review_id") or ""),
        ))
        remaining.remove(best)
        chosen.append(best)
        used_agents.add(str(best.get("source_agent") or ""))
        used_models.add(str(best.get("source_model") or ""))
    return chosen


def _anonymous_id(value: object) -> str:
    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]
    return f"SRC-{digest.upper()}"


def _anonymous_task_id(value: object) -> str:
    digest = hashlib.sha256(("task:" + str(value or "")).encode("utf-8")).hexdigest()[:12]
    return f"TASK-{digest.upper()}"


def _blind_source_kind(value: object) -> str:
    return {
        "real_model_execution_trace": "execution record",
        "official_dynamic_event_graph": "dynamic event graph",
        "official_dynamic_event_timeline": "event timeline",
    }.get(str(value or ""), "source record")


def _clean_evidence_content(value: object) -> str:
    text = re.sub(r"<think>.*?</think>", "", str(value or ""), flags=re.DOTALL | re.IGNORECASE)
    return text.strip()[:1400]


def _evidence_excerpt(row: dict) -> list[dict]:
    """Return reviewer-visible source evidence without screening commentary."""
    evidence_ids = {
        int(value) for value in (row.get("codex_screen") or {}).get("evidence_step_ids") or []
        if str(value).isdigit()
    }
    tail = list(row.get("tail") or [])
    chosen = [item for item in tail if int(item.get("step_id") or -1) in evidence_ids]
    if not chosen:
        chosen = tail
    return [
        {
            "step_id": item.get("step_id"),
            "kind": item.get("kind"),
            "content": _clean_evidence_content(item.get("content")),
        }
        for item in chosen[-4:]
    ]


def _recommended_review(kind: str, answers: dict[str, str]) -> tuple[dict, dict]:
    review = task_review_template() if kind == "task" else run_review_template()
    review["answers"] = dict(answers)
    decision_fn = task_review_decision if kind == "task" else run_review_decision
    review["computed_decision"] = decision_fn(review)
    review["review_status"] = "pending_confirmation"
    review["confirmed"] = False
    recommendation = {
        "source": "codex_initial_screen",
        "rubric_version": "codex-assisted-fixed-choice-v1",
        "answers": dict(answers),
        "computed_decision": review["computed_decision"],
    }
    return review, recommendation


def _blind_run(row: dict) -> dict:
    """Strip model identity and raw screening output while retaining answer defaults."""
    review, recommendation = _recommended_review("run", run_review_recommendation(row))
    return {
        "review_id": _anonymous_id(row.get("review_id")),
        "task_name": _anonymous_task_id(row.get("task_name")),
        "benchmark": row.get("benchmark"),
        "source_kind": _blind_source_kind(row.get("source_kind") or row.get("trajectory_format")),
        "instruction": row.get("instruction"),
        "normalized_step_count": row.get("normalized_step_count"),
        "evidence_excerpt": _evidence_excerpt(row),
        "recommendation": recommendation,
        "human_review": review,
    }


def _blind_task(task: dict) -> dict:
    answers = dict(task.get("recommended_answers") or task_review_recommendation([]))
    review, recommendation = _recommended_review("task", answers)
    return {
        "task_name": _anonymous_task_id(task["task_name"]),
        "benchmark": task.get("benchmark"),
        "run_count": task.get("run_count"),
        "representative_runs": [
            {
                "review_id": _anonymous_id(row.get("review_id")),
                "source_kind": _blind_source_kind(row.get("source_kind")),
                "instruction": row.get("instruction"),
                "evidence_excerpt": list(row.get("evidence_excerpt") or []),
            }
            for row in task.get("representative_runs") or []
        ],
        "recommendation": recommendation,
        "human_review": review,
    }


def _assign_annotators(
    tasks: list[dict], runs: list[dict], annotator_count: int, calibration_count: int,
) -> tuple[list[dict], list[dict]]:
    """Assign whole tasks, with a small shared set for agreement measurement."""
    if annotator_count < 1:
        raise ValueError("annotator_count must be positive")
    calibration_count = max(0, min(calibration_count, len(tasks)))
    calibration_names = {row["task_name"] for row in tasks[:calibration_count]}
    run_load = Counter(str(row.get("task_name") or "") for row in runs)
    owned = [[] for _ in range(annotator_count)]
    loads = [0] * annotator_count
    remaining = [row for row in tasks if row["task_name"] not in calibration_names]
    for row in sorted(remaining, key=lambda item: (-run_load[item["task_name"]], item["task_name"])):
        owner = min(range(annotator_count), key=lambda index: (loads[index], index))
        owned[owner].append(row["task_name"])
        loads[owner] += 1 + run_load[row["task_name"]]
    assignments: list[dict] = []
    task_lookup = {row["task_name"]: row for row in tasks}
    for index in range(annotator_count):
        annotator_id = f"annotator-{index + 1}"
        task_names = list(calibration_names) + owned[index]
        task_names.sort(key=lambda name: next(
            offset for offset, row in enumerate(tasks) if row["task_name"] == name
        ))
        assigned_tasks = []
        for name in task_names:
            row = deepcopy(task_lookup[name])
            row["annotator_id"] = annotator_id
            row["assignment_role"] = "calibration" if name in calibration_names else "primary"
            assigned_tasks.append(row)
        assigned_runs = []
        for source in runs:
            name = str(source.get("task_name") or "")
            if name not in task_names:
                continue
            row = deepcopy(source)
            row["annotator_id"] = annotator_id
            row["assignment_role"] = "calibration" if name in calibration_names else "primary"
            assigned_runs.append(row)
        assignments.append({
            "annotator_id": annotator_id,
            "tasks": assigned_tasks,
            "runs": assigned_runs,
            "primary_task_count": len(owned[index]),
            "calibration_task_count": len(calibration_names),
        })
    return assignments, sorted(calibration_names)


def _render_workspace(
    tasks: list[dict], runs: list[dict], output: Path, annotator_id: str,
) -> None:
    task_payload = json.dumps(tasks, ensure_ascii=False).replace("</", "<\\/")
    run_payload = json.dumps(runs, ensure_ascii=False).replace("</", "<\\/")
    catalogs = json.dumps({
        "task": TASK_REVIEW_QUESTIONS, "run": RUN_REVIEW_QUESTIONS,
    }, ensure_ascii=False)
    output.write_text(_WORKSPACE_HTML.replace("__TASKS__", task_payload)
                      .replace("__RUNS__", run_payload)
                      .replace("__CATALOGS__", catalogs)
                      .replace("__ANNOTATOR__", annotator_id)
                      .replace("__STORAGE_KEY__", f"async-rbench-assisted-v1-{annotator_id}")
                      .replace("__LEGACY_STORAGE_KEY__", f"async-rbench-blind-v1-{annotator_id}")
                      .replace("__TASK_EXPORT__", f"{annotator_id}.task-reviews.jsonl")
                      .replace("__RUN_EXPORT__", f"{annotator_id}.run-reviews.jsonl"),
                      encoding="utf-8")


def _render_landing(assignments: list[dict], output: Path) -> None:
    cards = "".join(
        f'<a href="{item["annotator_id"]}/review_workspace.html">'
        f'<strong>{item["annotator_id"]}</strong>'
        f'<span>{len(item["tasks"])} tasks · {len(item["runs"])} records</span></a>'
        for item in assignments
    )
    output.write_text(
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>人工复核分配</title>"
        "<style>body{margin:0;background:#f3f5f8;color:#172033;font:14px/1.5 Segoe UI,Arial}"
        "main{max-width:900px;margin:70px auto;background:white;border:1px solid #d9dee7;padding:42px}"
        "h1{font:600 28px Georgia,serif}.note{color:#637083}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:28px}"
        "a{border:1px solid #aeb8c6;padding:22px;text-decoration:none;color:#142b4a;background:#fafbfc}"
        "a:hover{background:#eef2f7}strong,span{display:block}span{margin-top:7px;color:#637083}</style>"
        "<main><h1>人工复核任务分配</h1><p class='note'>请选择对应标注员入口。三份进度和导出文件相互独立。</p>"
        f"<div class='grid'>{cards}</div></main></html>", encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workspace-output")
    parser.add_argument("--task-batch-size", type=int, default=25)
    parser.add_argument("--run-batch-size", type=int, default=50)
    parser.add_argument("--annotators", type=int, default=1)
    parser.add_argument("--calibration-count", type=int, default=0)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = read_jsonl(Path(args.queue).resolve())
    mapping_rows = [
        {
            "record_type": "task",
            "blind_id": _anonymous_task_id(task_name),
            "internal_id": task_name,
        }
        for task_name in sorted({str(row.get("task_name") or "") for row in rows})
    ] + [
        {
            "record_type": "source",
            "blind_id": _anonymous_id(row.get("review_id")),
            "internal_id": row.get("review_id"),
        }
        for row in sorted(rows, key=lambda item: str(item.get("review_id") or ""))
    ]
    write_jsonl(output / "blind_id_mapping.pipeline-only.jsonl", mapping_rows)
    by_task: dict[str, list[dict]] = {}
    for row in rows:
        by_task.setdefault(str(row.get("task_name") or ""), []).append(row)
    task_rows = []
    for task, task_runs in sorted(by_task.items()):
        reps = _representatives(task_runs)
        task_rows.append({
            "task_name": task,
            "benchmark": task_runs[0].get("benchmark"),
            "family": (task_runs[0].get("codex_screen") or {}).get("family"),
            "run_count": len(task_runs),
            "decision_counts": dict(sorted(Counter(
                str((row.get("codex_screen") or {}).get("decision") or "") for row in task_runs
            ).items())),
            "representative_runs": [{
                "review_id": row.get("review_id"),
                "source_kind": row.get("source_kind") or row.get("trajectory_format"),
                "instruction": row.get("instruction"),
                "evidence_excerpt": _evidence_excerpt(row),
            } for row in reps],
            "recommended_answers": task_review_recommendation(task_runs),
        })
    task_order = _round_robin([
        {**row, "codex_screen": {"decision": "task_review", "family": row["family"]},
         "source_agent": "", "source_model": "", "review_id": row["task_name"]}
        for row in task_rows
    ], ("family", "benchmark"))
    task_order = [{key: value for key, value in row.items()
                   if key not in {"codex_screen", "source_agent", "source_model", "review_id"}}
                  for row in task_order]
    task_order = [_blind_task(row) for row in task_order]
    task_dir, run_dir = output / "task_batches", output / "run_batches"
    task_dir.mkdir(exist_ok=True)
    run_dir.mkdir(exist_ok=True)
    task_batches = []
    for offset in range(0, len(task_order), args.task_batch_size):
        batch = task_order[offset:offset + args.task_batch_size]
        batch_id = f"task-batch-{offset // args.task_batch_size + 1:03d}"
        for row in batch:
            row["annotation_batch_id"] = batch_id
        name = batch_id + ".jsonl"
        write_jsonl(task_dir / name, batch)
        task_batches.append({"name": name, "count": len(batch)})
    write_jsonl(output / "task_review_queue.jsonl", task_order)
    run_order = [
        _blind_run(row)
        for row in _round_robin(rows, ("decision", "family", "benchmark", "agent", "model"))
    ]
    run_batches = []
    for offset in range(0, len(run_order), args.run_batch_size):
        batch = run_order[offset:offset + args.run_batch_size]
        batch_id = f"run-batch-{offset // args.run_batch_size + 1:03d}"
        for row in batch:
            row["annotation_batch_id"] = batch_id
        name = batch_id + ".jsonl"
        write_jsonl(run_dir / name, batch)
        run_batches.append({"name": name, "count": len(batch)})
    write_jsonl(output / "run_review_queue.jsonl", run_order)
    assignments, calibration_tasks = _assign_annotators(
        task_order, run_order, args.annotators, args.calibration_count,
    )
    annotator_reports = []
    for assignment in assignments:
        annotator_id = assignment["annotator_id"]
        annotator_dir = output / annotator_id
        annotator_dir.mkdir(exist_ok=True)
        assigned_tasks = assignment["tasks"]
        assigned_runs = assignment["runs"]
        write_jsonl(annotator_dir / "task_review_queue.jsonl", assigned_tasks)
        write_jsonl(annotator_dir / "run_review_queue.jsonl", assigned_runs)
        annotator_workspace = annotator_dir / "review_workspace.html"
        _render_workspace(assigned_tasks, assigned_runs, annotator_workspace, annotator_id)
        annotator_reports.append({
            "annotator_id": annotator_id,
            "primary_task_count": assignment["primary_task_count"],
            "calibration_task_count": assignment["calibration_task_count"],
            "assigned_task_count": len(assigned_tasks),
            "assigned_run_count": len(assigned_runs),
            "workspace": str(annotator_workspace),
        })
    workspace = Path(args.workspace_output).resolve() if args.workspace_output else output / "annotation_workspace.html"
    if len(assignments) == 1:
        _render_workspace(task_order, run_order, workspace, "annotator-1")
    else:
        _render_landing(assignments, workspace)
        if workspace != output / "annotation_workspace.html":
            _render_landing(assignments, output / "annotation_workspace.html")
    report = {
        "review_contract": "fixed-choice-assisted-v1", "free_text_fields": 0,
        "reviewer_blinding": {
            "model_identity_removed": True,
            "agent_identity_removed": True,
            "screening_labels_removed": True,
            "screening_rationale_removed": True,
            "recommendations_removed": False,
            "raw_screening_rationale_removed": True,
        },
        "recommendation_defaults": {
            "enabled": True,
            "source": "codex_initial_screen",
            "reviewer_must_confirm_each_record": True,
            "reviewer_can_override_any_choice": True,
        },
        "computed_disposition": True,
        "task_review_count": len(task_order), "run_review_count": len(rows),
        "task_question_count": len(TASK_REVIEW_QUESTIONS),
        "run_question_count": len(RUN_REVIEW_QUESTIONS),
        "task_batch_size": args.task_batch_size, "run_batch_size": args.run_batch_size,
        "task_batches": task_batches, "run_batches": run_batches,
        "annotator_count": args.annotators,
        "calibration_task_count": len(calibration_tasks),
        "calibration_tasks": calibration_tasks,
        "annotators": annotator_reports,
        "workspace": str(workspace) if len(assignments) == 1 else None,
        "workflow": [
            "Initial screening recommendations preselect all fixed-choice answers.",
            "Human confirms or corrects the defaults, then advances with one action.",
            "Only accepted tasks unlock their run-level fixed-choice review.",
            "Case production remains blocked until accepted runs pass both layers.",
        ],
    }
    (output / "annotation_batch_index.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


_WORKSPACE_HTML = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Async-RBench Review Console</title>
<style>
:root{--ink:#172033;--navy:#142b4a;--blue:#284d78;--line:#d9dee7;--paper:#fff;--wash:#f3f5f8;--muted:#637083;--good:#235d4a;--warn:#8a5a16;--bad:#8a3030;--recommend:#fff3cd}*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:14px/1.55 Inter,"Segoe UI",Arial,sans-serif}button,select{font:inherit}.mast{background:var(--navy);color:white;border-bottom:4px solid #9aa8ba;padding:21px 32px 18px}.mast .series{font-size:11px;letter-spacing:.18em;text-transform:uppercase;opacity:.72}.mast h1{margin:5px 0 3px;font:600 25px/1.2 Georgia,"Times New Roman",serif}.mast p{margin:0;opacity:.78;font-size:12px}.toolbar{position:sticky;top:0;z-index:8;display:flex;align-items:center;gap:14px;padding:10px 24px;background:rgba(255,255,255,.97);border-bottom:1px solid var(--line);box-shadow:0 1px 4px #17203312}.tabs{display:flex;border:1px solid #aeb8c6}.tabs button{border:0;border-right:1px solid #aeb8c6;background:white;padding:7px 14px;color:var(--navy);cursor:pointer}.tabs button:last-child{border-right:0}.tabs button.active{background:var(--navy);color:white}.toolbar select,.toolbar button.action{border:1px solid #aeb8c6;background:white;color:var(--ink);padding:7px 10px}.toolbar .spacer{flex:1}.progress-wrap{min-width:180px}.progress-meta{display:flex;justify-content:space-between;font-size:11px;color:var(--muted)}.progress{height:4px;background:#e5e9ef;margin-top:4px}.progress i{display:block;height:100%;background:var(--blue);width:0}.layout{display:grid;grid-template-columns:285px minmax(0,1fr);max-width:1440px;margin:auto;min-height:calc(100vh - 128px)}.index{border-right:1px solid var(--line);background:#fafbfc;padding:18px 14px;overflow:auto;height:calc(100vh - 128px);position:sticky;top:49px}.index h2{font:600 13px Georgia,serif;margin:0 8px 12px}.index button{width:100%;text-align:left;border:0;border-left:3px solid transparent;background:transparent;padding:8px 9px;margin:1px 0;color:#344054;cursor:pointer}.index button:hover{background:#eef1f5}.index button.active{background:#e8edf4;border-left-color:var(--navy);color:var(--navy)}.index button.done:after{content:'✓';float:right;color:var(--good)}.index small{display:block;color:#7b8798;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.paper{padding:30px 38px 60px}.sheet{max-width:980px;margin:auto;background:var(--paper);border:1px solid #d3d9e2;box-shadow:0 8px 28px #26364d12}.paper-head{padding:30px 38px 23px;border-bottom:1px solid var(--line)}.kicker{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--blue)}h1.title{font:600 27px/1.24 Georgia,"Times New Roman",serif;margin:7px 0 10px}.meta-table{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);margin-top:16px}.meta-table div{padding:8px 10px;border-right:1px solid var(--line)}.meta-table div:last-child{border:0}.meta-table b{display:block;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.section{padding:24px 38px;border-bottom:1px solid var(--line)}.section h2{font:600 16px Georgia,serif;margin:0 0 12px}.abstract{border-left:3px solid #8395aa;padding:10px 14px;background:#f8f9fb;white-space:pre-wrap;max-height:230px;overflow:auto}.hypothesis{display:grid;grid-template-columns:160px 1fr;gap:8px 16px;font-size:13px}.hypothesis dt{font-weight:600;color:#49566a}.hypothesis dd{margin:0}.rep{border-top:1px solid #e4e7ec;padding:13px 0}.rep:first-of-type{border-top:0}.rep-head{display:flex;justify-content:space-between;gap:12px;font-size:12px}.rep code{font-size:11px;color:var(--blue);max-width:60%;text-align:right;word-break:break-all}details summary{cursor:pointer;color:var(--blue);font-weight:600}.recommendation-note{margin:18px 38px 0;padding:11px 14px;border-left:3px solid #c48a00;background:#fff9e8;color:#684d00}.criteria{padding:5px 38px 25px}.criterion{display:grid;grid-template-columns:minmax(250px,1fr) 390px;gap:22px;align-items:center;padding:15px 0;border-bottom:1px solid #e6e9ee}.criterion:last-child{border-bottom:0}.criterion b{display:block;font-size:13px}.criterion span.help{display:block;color:var(--muted);font-size:12px;margin-top:2px}.choices{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;border:1px solid #aeb8c6}.choices label{position:relative;text-align:center;border-right:1px solid #aeb8c6;cursor:pointer}.choices label:last-child{border:0}.choices input{position:absolute;opacity:0;pointer-events:none}.choices span{display:block;padding:8px 5px;background:white;font-size:12px;min-height:49px}.choices small{display:block;color:#8a5a16;font-size:9px;line-height:1.1}.choices label.recommended span{background:var(--recommend)}.choices input:checked+span{background:var(--navy);color:white}.choices input:checked+span small{color:#ffe39a}.decision{margin:0 38px 18px;padding:15px 18px;border:1px solid #aeb8c6;background:#f7f8fa;display:flex;align-items:center;justify-content:space-between}.decision b{font:600 16px Georgia,serif}.decision .result{font-weight:700;letter-spacing:.06em;text-transform:uppercase}.decision.accept .result{color:var(--good)}.decision.expand_trace .result{color:var(--warn)}.decision.reject .result{color:var(--bad)}.nav{display:flex;justify-content:space-between;padding:0 38px 30px;gap:12px}.nav button{border:1px solid #98a4b4;background:white;padding:9px 16px;color:var(--navy);cursor:pointer}.nav button.confirm{margin-left:auto;background:var(--navy);color:white;border-color:var(--navy);min-width:190px}.empty{max-width:760px;margin:80px auto;background:white;border:1px solid var(--line);padding:38px;text-align:center}.empty h2{font:600 21px Georgia,serif}.method-note{font-size:11px;color:var(--muted);padding:12px 24px;border-top:1px solid var(--line);background:#fafbfc}@media(max-width:900px){.layout{grid-template-columns:1fr}.index{position:static;height:220px;border-right:0;border-bottom:1px solid var(--line)}.paper{padding:16px}.criterion{grid-template-columns:1fr}.meta-table{grid-template-columns:1fr 1fr}.toolbar{flex-wrap:wrap}.progress-wrap{min-width:120px}}
</style></head><body><header class="mast"><div class="series">Async-RBench · Human Review</div><h1>异步重规划证据复核</h1><p>固定选择题、两阶段复核 · 标注员 __ANNOTATOR__</p></header>
<div class="toolbar"><div class="tabs"><button id="taskTab" class="active">Stage I · Task</button><button id="runTab">Stage II · Run</button></div><select id="batch"></select><button class="action" id="nextIncomplete">下一未完成</button><button class="action" id="exportProgress">导出当前进度</button><div class="spacer"></div><div class="progress-wrap"><div class="progress-meta"><span id="progressLabel"></span><span id="progressCount"></span></div><div class="progress"><i id="progressBar"></i></div></div></div>
<main class="layout"><aside class="index"><h2 id="indexTitle"></h2><div id="index"></div></aside><section class="paper" id="paper"></section></main>
<script>const initialTasks=__TASKS__,initialRuns=__RUNS__,catalogs=__CATALOGS__,storageKey='__STORAGE_KEY__',legacyStorageKey='__LEGACY_STORAGE_KEY__',annotatorId='__ANNOTATOR__';
const labels={pending:'未选择',yes:'是',no:'否',uncertain:'证据不足',exact:'完全匹配',instruction_only:'仅指令匹配',mismatch:'不匹配',unknown:'未知',usable:'可用',partial:'部分可用',unusable:'不可用',model:'执行侧',benchmark:'Benchmark侧',infrastructure:'基础设施侧',not_failure:'非失败记录'};
const taskQ={independent_result_producer:['独立结果生产者','结果是否可由独立工作单元、验证器或外部进程产生？'],affected_work_started_before_arrival:['受影响工作已启动','结果返回前，主分支是否能合理开始会受其影响的工作？'],arrival_order_changes_plan:['到达顺序影响计划','相同结果在不同到达时刻是否会导致不同的有效动作？'],plan_change_required:['必须改变计划','迟到或冲突结果是否要求撤销、重做、取消或重新验证？'],executable_consequence_observable:['后果可执行观测','是否存在测试、探针、哈希或状态机明确暴露陈旧整合？'],source_semantics_preserved:['保持源任务语义','异步变换后是否仍在测试原任务，而不是另造无关难题？'],environment_reproducible:['环境可复现','依赖、服务和时序注入是否可在评测环境稳定重放？'],prompt_leakage_risk:['存在提示泄漏风险','任务文字是否直接泄漏异步事件、正确分支或评分点？']};
const runQ={task_version_match:['任务与版本匹配','该轨迹是否对应目标任务及可复现版本？'],trajectory_quality:['轨迹质量','步骤、工具结果与完成状态是否足以支持复核？'],trigger_is_independent_result:['触发项是独立结果','标注的触发步骤是否能被外部化为独立异步结果？'],evidence_boundary_valid:['证据边界有效','证据步骤是否真实覆盖触发→响应，而非普通相邻报错？'],causal_plan_change_visible:['因果重规划可见','响应是否因新结果发生实质计划变化？'],arrival_order_observable:['顺序效应可观测','轨迹是否支持“先整合/后整合”会产生不同结果？'],executable_consequence_supported:['可执行后果有支撑','现有测试或状态是否能实现该差异的稳定计分？'],failure_attribution:['失败归因','轨迹中的关键失败最主要属于哪一侧？']};
let saved={},savedFromLegacy=false;try{const currentSaved=localStorage.getItem(storageKey),legacySaved=localStorage.getItem(legacyStorageKey);saved=JSON.parse(currentSaved||legacySaved||'{}');savedFromLegacy=!currentSaved&&!!legacySaved}catch{};const clone=x=>JSON.parse(JSON.stringify(x));let tasks=clone(initialTasks),runs=clone(initialRuns),mode='task',current=0;
function restoreReview(base,prior){if(!prior)return base;const restored={...base,...prior,answers:{...base.answers}};for(const [key,value] of Object.entries(prior.answers||{}))if(value&&value!=='pending')restored.answers[key]=value;if(savedFromLegacy){restored.confirmed=prior.computed_decision&&prior.computed_decision!=='pending';restored.review_status=restored.confirmed?'confirmed':'pending_confirmation'}return restored}for(const t of tasks)t.human_review=restoreReview(t.human_review,saved.tasks?.[t.task_name]);for(const r of runs)r.human_review=restoreReview(r.human_review,saved.runs?.[r.review_id]);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function taskDecision(a){const vals=Object.values(a);if(vals.includes('pending'))return'pending';const pos=['independent_result_producer','affected_work_started_before_arrival','arrival_order_changes_plan','plan_change_required','executable_consequence_observable','source_semantics_preserved','environment_reproducible'];if(pos.some(k=>a[k]==='no')||a.prompt_leakage_risk==='yes')return'reject';if(vals.includes('uncertain'))return'expand_trace';return'accept'}
function runDecision(a){const vals=Object.values(a);if(vals.includes('pending'))return'pending';if(a.task_version_match==='mismatch'||a.trajectory_quality==='unusable')return'reject';const pos=['trigger_is_independent_result','evidence_boundary_valid','causal_plan_change_visible','arrival_order_observable','executable_consequence_supported'];if(pos.some(k=>a[k]==='no')||['benchmark','infrastructure'].includes(a.failure_attribution))return'reject';if(['instruction_only','unknown'].includes(a.task_version_match)||a.trajectory_quality==='partial'||a.failure_attribution==='uncertain'||pos.some(k=>a[k]==='uncertain'))return'expand_trace';return'accept'}
function decision(row){const d=mode==='task'?taskDecision(row.human_review.answers):runDecision(row.human_review.answers);row.human_review.computed_decision=d;return d}function persist(){localStorage.setItem(storageKey,JSON.stringify({tasks:Object.fromEntries(tasks.map(x=>[x.task_name,x.human_review])),runs:Object.fromEntries(runs.map(x=>[x.review_id,x.human_review]))}))}
function acceptedTasks(){return new Set(tasks.filter(t=>t.human_review.confirmed&&taskDecision(t.human_review.answers)==='accept').map(t=>t.task_name))}function activeRows(){const b=batch.value;if(mode==='task')return tasks.filter(x=>b==='all'||x.annotation_batch_id===b);const ok=acceptedTasks();return runs.filter(x=>ok.has(x.task_name)&&(b==='all'||x.annotation_batch_id===b))}
function completed(row){return row.human_review.confirmed===true}function setupBatches(){const rows=mode==='task'?tasks:runs,ids=[...new Set(rows.map(x=>x.annotation_batch_id))];batch.innerHTML='<option value="all">全部批次</option>'+ids.map(x=>`<option>${esc(x)}</option>`).join('');current=0;render()}
function questionRows(row,kind){const q=kind==='task'?taskQ:runQ,cat=catalogs[kind];return Object.entries(q).map(([key,text])=>`<div class="criterion"><div><b>${esc(text[0])}</b><span class="help">${esc(text[1])}</span></div><div class="choices">${cat[key].filter(v=>v!=='pending').map(v=>`<label><input type="radio" name="${key}" value="${v}" ${row.human_review.answers[key]===v?'checked':''}><span>${esc(labels[v]||v)}</span></label>`).join('')}</div></div>`).join('')}
function evidence(items){return (items||[]).map(x=>`<div class="rep"><div class="rep-head"><b>Step ${esc(x.step_id)}</b><code>${esc(x.kind)}</code></div><div class="abstract">${esc(x.content)}</div></div>`).join('')||'<p class="note">当前记录未提供可显示的步骤摘要，请依据任务语义完成判断。</p>'}
function taskPaper(t){const reps=t.representative_runs.map((r,i)=>`<div class="rep"><div class="rep-head"><b>来源记录 ${i+1}</b><code>${esc(r.review_id)}</code></div><p>${esc(r.source_kind)}</p><details><summary>查看任务与证据摘要</summary><div class="abstract">${esc(r.instruction)}</div>${evidence(r.evidence_excerpt)}</details></div>`).join('');return `<article class="sheet"><header class="paper-head"><div class="kicker">Stage I · Task-level semantic eligibility</div><h1 class="title">${esc(t.task_name)}</h1><div class="meta-table"><div><b>Benchmark</b>${esc(t.benchmark)}</div><div><b>标注员</b>${esc(t.annotator_id)}</div><div><b>来源记录数</b>${t.run_count}</div><div><b>分配类型</b>${esc(t.assignment_role)}</div></div></header><section class="section"><h2>来源证据摘要</h2>${reps}</section><section class="section"><h2>复核方法</h2><p>仅依据任务语义与来源证据，判断是否同时满足独立结果生产、受影响工作提前启动、到达顺序效应和可执行后果。不要把普通报错、重试或相邻步骤误判为异步因果边界。</p></section><section class="criteria">${questionRows(t,'task')}</section>${decisionBox(t)}${nav(t)}</article>`}
function runPaper(r){return `<article class="sheet"><header class="paper-head"><div class="kicker">Stage II · Run-level causal evidence</div><h1 class="title">${esc(r.task_name)}</h1><div class="meta-table"><div><b>Benchmark</b>${esc(r.benchmark)}</div><div><b>来源编号</b>${esc(r.review_id)}</div><div><b>记录类型</b>${esc(r.source_kind)}</div><div><b>步骤数</b>${r.normalized_step_count}</div></div></header><section class="section"><h2>源任务指令</h2><div class="abstract">${esc(r.instruction)}</div></section><section class="section"><h2>来源证据摘要</h2>${evidence(r.evidence_excerpt)}</section><section class="criteria">${questionRows(r,'run')}</section>${decisionBox(r)}${nav(r)}</article>`}
function decisionBox(row){const d=decision(row),txt={pending:'等待完成全部选择',accept:'Accept · 可进入任务生产',expand_trace:'Expand · 补充来源证据',reject:'Reject · 不进入生产'}[d],state=completed(row)?'已由审核员确认':'待审核员确认';return `<div class="decision ${d}"><span>固定规则计算结果 · ${state}</span><b class="result">${txt}</b></div>`}function nav(row){return `<div class="nav"><button id="prev">← 上一项</button><button class="confirm" id="confirmNext">${completed(row)?'已确认 · 下一条 →':'确认并下一条 →'}</button></div>`}
function confirmAndAdvance(row,rows){decision(row);row.human_review.confirmed=true;row.human_review.review_status='confirmed';row.human_review.reviewer_id=annotatorId;row.human_review.confirmed_at=new Date().toISOString();persist();const i=rows.findIndex((r,n)=>n>current&&!completed(r));current=i>=0?i:Math.min(current+1,rows.length-1);render()}
function render(){const rows=activeRows();if(current>=rows.length)current=Math.max(0,rows.length-1);const done=rows.filter(completed).length;progressLabel.textContent=mode==='task'?'Task review':'Run review';progressCount.textContent=`${done}/${rows.length}`;progressBar.style.width=(rows.length?done/rows.length*100:0)+'%';indexTitle.textContent=mode==='task'?'Task index':'Confirmed-task run index';index.innerHTML=rows.map((x,i)=>`<button data-i="${i}" class="${i===current?'active ':''}${completed(x)?'done':''}">${i+1}. ${esc(x.task_name)}<small>${esc(x.benchmark)} · ${esc(x.assignment_role)}</small></button>`).join('');if(!rows.length){paper.innerHTML=`<div class="empty"><h2>尚无可复核记录</h2><p>Stage II 仅显示 Stage I 已确认且规则判定为 Accept 的任务。请先完成任务级复核。</p></div>`;return}const row=rows[current];paper.innerHTML=mode==='task'?taskPaper(row):runPaper(row);paper.querySelectorAll('input[type=radio]').forEach(el=>el.onchange=()=>{row.human_review.answers[el.name]=el.value;row.human_review.confirmed=false;row.human_review.review_status='pending_confirmation';delete row.human_review.confirmed_at;decision(row);persist();render()});index.querySelectorAll('button').forEach(el=>el.onclick=()=>{current=Number(el.dataset.i);render()});prev.onclick=()=>{current=Math.max(0,current-1);render()};confirmNext.onclick=()=>confirmAndAdvance(row,rows)}
function switchMode(next){mode=next;taskTab.classList.toggle('active',mode==='task');runTab.classList.toggle('active',mode==='run');setupBatches()}taskTab.onclick=()=>switchMode('task');runTab.onclick=()=>switchMode('run');batch.onchange=()=>{current=0;render()};nextIncomplete.onclick=()=>{const rows=activeRows(),i=rows.findIndex((r,n)=>n>current&&!completed(r));current=i>=0?i:Math.max(0,rows.findIndex(r=>!completed(r)));render()};
function download(rows,name){rows.forEach(decision);const blob=new Blob([rows.map(x=>JSON.stringify(x)).join('\n')+'\n'],{type:'application/jsonl'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}exportProgress.onclick=()=>download(mode==='task'?tasks:runs,mode==='task'?'__TASK_EXPORT__':'__RUN_EXPORT__');setupBatches();
</script><footer class="method-note">复核信息不包含执行系统身份、原始初筛标签或初筛理由。审核员可修改任一答案，最终结论由固定规则计算。</footer></body></html>'''


if __name__ == "__main__":
    raise SystemExit(main())
