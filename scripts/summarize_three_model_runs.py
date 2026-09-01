from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


CASE_ORDER = {
    "gaia2-stockholm-moveout": 0,
    "nginx-live-port-conflict": 1,
    "secure-release": 2,
}
MODEL_ORDER = {
    "qwen3-coder-480b-a35b-instruct": 0,
    "deepseek-v4-flash": 1,
    "gpt-5.4-2026-03-05": 2,
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt_score(value: Any) -> str:
    return "—" if value is None else f"{float(value):.3f}"


def _fmt_duration(milliseconds: Any) -> str:
    if milliseconds is None:
        return "—"
    seconds = float(milliseconds) / 1000
    return f"{seconds / 60:.2f} min"


def collect(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pair_path in sorted(root.rglob("pair-results.json")):
        pair = _read_json(pair_path)
        pair_dir = pair_path.parent
        scores = {item["execution_mode"]: item for item in pair.get("scores", [])}
        if set(scores) != {"linear", "async"}:
            raise ValueError(f"pair does not contain one linear and one async score: {pair_path}")
        details: dict[str, dict[str, Any]] = {}
        for mode, item in scores.items():
            score_path = pair_dir / "episodes" / item["episode_id"] / "score.json"
            if not score_path.is_file():
                raise FileNotFoundError(score_path)
            details[mode] = _read_json(score_path)

        async_row = scores["async"]
        async_detail = details["async"]
        failed_dynamic = [
            item["id"]
            for item in async_detail.get("control_flow_check_results", [])
            if item.get("status") == "fail"
        ]
        rows.append(
            {
                "case_id": pair["case_id"],
                "pilot_id": pair["pilot_id"],
                "model": pair["model"],
                "linear": scores["linear"],
                "async": async_row,
                "linear_duration_ms": details["linear"].get("episode_duration_ms"),
                "async_duration_ms": async_detail.get("episode_duration_ms"),
                "failed_dynamic_ids": failed_dynamic,
                "score_status_reason": async_detail.get("score_status_reason"),
                "dynamic_scenario_errors": async_detail.get("dynamic_scenario_errors") or [],
                "infrastructure_failures": async_detail.get("infrastructure_failures") or [],
                "resume_metadata": pair.get("resume_metadata"),
                "simulation_only": pair.get("simulation_only"),
                "official_track": pair.get("official_track"),
            }
        )
    rows.sort(key=lambda row: (CASE_ORDER.get(row["case_id"], 99), MODEL_ORDER.get(row["model"], 99)))
    return rows


def render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Three-model dynamic pilot results",
        "",
        "> Simulation-only development runs. An `unscored` async episode failed scenario qualification; it is not a dynamic score of zero and must not enter official aggregates.",
        "",
        "| Case | Model | Linear S | Async status | Async S | D | DT | Dynamic | Linear time | Async time |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        linear = row["linear"]
        async_row = row["async"]
        lines.append(
            "| {case} | {model} | {linear_s} | {status} | {async_s} | {d} | {dt} | {passed}/{total} | {linear_time} | {async_time} |".format(
                case=row["case_id"],
                model=row["model"],
                linear_s=_fmt_score(linear.get("semantic_task_score")),
                status=async_row.get("score_status"),
                async_s=_fmt_score(async_row.get("semantic_task_score")),
                d=_fmt_score(async_row.get("dynamic_control_score")),
                dt=_fmt_score(async_row.get("dt_score")),
                passed=async_row.get("dynamic_points_passed"),
                total=async_row.get("dynamic_points_applicable"),
                linear_time=_fmt_duration(row["linear_duration_ms"]),
                async_time=_fmt_duration(row["async_duration_ms"]),
            )
        )

    lines.extend(["", "## Dynamic-point outcomes", ""])
    for row in rows:
        async_row = row["async"]
        label = f"{row['case_id']} / {row['model']}"
        if async_row.get("score_status") == "scored":
            failed = ", ".join(row["failed_dynamic_ids"]) or "none"
            lines.append(
                f"- `{label}`: {async_row.get('dynamic_points_passed')}/{async_row.get('dynamic_points_applicable')} passed; failed: {failed}."
            )
        else:
            errors = "; ".join(row["dynamic_scenario_errors"]) or str(row["score_status_reason"])
            lines.append(f"- `{label}`: unscored — {errors}.")

    status_counts = Counter(row["async"].get("score_status") for row in rows)
    total_ms = sum(
        float(row[key] or 0)
        for row in rows
        for key in ("linear_duration_ms", "async_duration_ms")
    )
    lines.extend(
        [
            "",
            "## Run integrity",
            "",
            f"- Complete model-case pairs: {len(rows)}/9.",
            f"- Async score status: {status_counts.get('scored', 0)} scored, {status_counts.get('unscored', 0)} unscored.",
            f"- Recorded episode time: {total_ms / 3_600_000:.2f} hours across {len(rows) * 2} episodes.",
            f"- Infrastructure failures recorded in score artifacts: {sum(bool(row['infrastructure_failures']) for row in rows)}.",
            f"- Resumed pairs: {sum(row['resume_metadata'] is not None for row in rows)}.",
            "- These runs are development simulations and are not leaderboard-eligible.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    rows = collect(root)
    summary = {
        "schema_version": "three-model-dynamic-pilot-summary-1",
        "pair_count": len(rows),
        "expected_pair_count": 9,
        "complete": len(rows) == 9,
        "simulation_only": True,
        "official_track": False,
        "rows": rows,
    }
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "RESULTS.md").write_text(render_markdown(rows), encoding="utf-8")
    print(json.dumps({"pair_count": len(rows), "complete": len(rows) == 9}))
    return 0 if len(rows) == 9 else 2


if __name__ == "__main__":
    raise SystemExit(main())
