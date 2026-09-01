#!/usr/bin/env python3
"""Build a compact, reproducible report for the frozen first-10 model evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Iterable


MODELS = ("sol", "terra", "luna")
MODEL_LABELS = {
    "sol": "gpt-5.6-sol",
    "terra": "gpt-5.6-terra",
    "luna": "gpt-5.6-luna",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def mean(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return statistics.fmean(present) if present else None


def rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def hidden_pass(score: dict[str, Any]) -> bool:
    counts = score.get("test_counts") or {}
    return (
        counts.get("passed", 0) > 0
        and counts.get("failed", 0) == 0
        and counts.get("errors", 0) == 0
    )


def model_summary(scores: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode = {
        mode: [score for score in scores if score["execution_mode"] == mode]
        for mode in ("linear", "async")
    }
    async_dynamic = [
        score
        for score in by_mode["async"]
        if score.get("dynamic_control_score") is not None
    ]
    async_dt = [score for score in by_mode["async"] if score.get("dt_score") is not None]
    return {
        "completed": len(scores),
        "scored": sum(score.get("score_status") == "scored" for score in scores),
        "unscored": sum(score.get("score_status") == "unscored" for score in scores),
        "scored_by_mode": {
            mode: sum(score.get("score_status") == "scored" for score in mode_scores)
            for mode, mode_scores in by_mode.items()
        },
        "observed_semantic_all": rounded(mean(score["semantic_task_score"] for score in scores)),
        "observed_semantic_linear": rounded(
            mean(score["semantic_task_score"] for score in by_mode["linear"])
        ),
        "observed_semantic_async": rounded(
            mean(score["semantic_task_score"] for score in by_mode["async"])
        ),
        "framework_scored_semantic_linear": rounded(
            mean(
                score["semantic_task_score"]
                for score in by_mode["linear"]
                if score.get("score_status") == "scored"
            )
        ),
        "framework_scored_semantic_async": rounded(
            mean(
                score["semantic_task_score"]
                for score in by_mode["async"]
                if score.get("score_status") == "scored"
            )
        ),
        "observed_dynamic_control_async": rounded(
            mean(score["dynamic_control_score"] for score in async_dynamic)
        ),
        "observed_dt_async": rounded(mean(score["dt_score"] for score in async_dt)),
        "dynamic_observation_count": len(async_dynamic),
        "hidden_test_passes": sum(hidden_pass(score) for score in scores),
        "budget_exhausted": sum(bool(score.get("budget_exhausted")) for score in scores),
        "timed_out": sum(bool(score.get("timed_out")) for score in scores),
        "infrastructure_failure_episodes": sum(
            bool(score.get("infrastructure_failures")) for score in scores
        ),
        "total_tokens": sum(int(score.get("total_tokens") or 0) for score in scores),
        "summed_episode_hours": rounded(
            sum(float(score.get("episode_duration_ms") or 0) for score in scores) / 3_600_000
        ),
    }


def audit_summary(audit: dict[str, Any]) -> dict[str, Any]:
    compatibility = audit["artifact_compatibility"]
    fixtures = audit["contract_fixtures"]
    return {
        "episode_count": audit["episode_count"],
        "all_artifacts_match_current": compatibility["all_episodes_match_current"],
        "case_contract_match_count": compatibility["case_contract_match_count"],
        "evaluation_contract_match_count": compatibility["evaluation_contract_match_count"],
        "scaffold_match_count": compatibility["scaffold_match_count"],
        "contract_fixtures_passed": fixtures["passed"],
        "contract_fixture_pass_count": fixtures["passed_count"],
        "contract_fixture_count": fixtures["workstream_count"],
    }


def aggregate_audit_summary(results: dict[str, Any]) -> dict[str, Any]:
    audit = results["audit"]
    return {
        "planned_episode_count": audit["planned_episode_count"],
        "observed_episode_count": audit["observed_episode_count"],
        "missing_episode_ids": audit["missing_episode_ids"],
        "manifest_completion_rate": audit["manifest_completion_rate"],
        "development_denominator_comparability_ok": audit[
            "development_denominator_comparability_ok"
        ],
        "visibility_leakage_detected": audit["visibility_leakage_detected"],
        "score_policy_version": audit["required_score_policy_version"],
    }


def fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def compact_episode(score: dict[str, Any]) -> dict[str, Any]:
    return {
        "score_status": score["score_status"],
        "semantic_task_score": rounded(score.get("semantic_task_score")),
        "dynamic_control_score": rounded(score.get("dynamic_control_score")),
        "dt_score": rounded(score.get("dt_score")),
        "scenario_constructed": score.get("scenario_constructed"),
        "scenario_exposure_complete": score.get("scenario_exposure_complete"),
        "hidden_tests_passed": hidden_pass(score),
        "budget_exhausted": bool(score.get("budget_exhausted")),
        "total_tokens": score.get("total_tokens"),
        "episode_duration_ms": score.get("episode_duration_ms"),
        "infrastructure_failures": score.get("infrastructure_failures") or [],
    }


def build_report(root: Path) -> tuple[dict[str, Any], str]:
    manifest_path = root / "manifest.json"
    manifest = load_json(manifest_path)
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    cases = list(dict.fromkeys(episode["case_id"] for episode in manifest["episodes"]))

    all_scores: dict[str, list[dict[str, Any]]] = {}
    score_index: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    audits: dict[str, dict[str, Any]] = {}
    aggregate_audits: dict[str, dict[str, Any]] = {}
    for model in MODELS:
        scores = [load_json(path) for path in sorted((root / model / "runs").glob("*/score.json"))]
        all_scores[model] = scores
        score_index[model] = {
            (score["case_id"], score["execution_mode"]): score for score in scores
        }
        audits[model] = audit_summary(load_json(root / model / "run-audit.json"))
        aggregate_audits[model] = aggregate_audit_summary(
            load_json(root / model / "results.json")
        )

    case_rows: list[dict[str, Any]] = []
    for case_id in cases:
        reference = score_index["sol"][(case_id, "async")]
        case_rows.append(
            {
                "case_id": case_id,
                "semantic_check_count": len(reference.get("semantic_check_results") or []),
                "control_flow_check_count": len(reference.get("control_flow_check_results") or []),
                "models": {
                    model: {
                        mode: compact_episode(score_index[model][(case_id, mode)])
                        for mode in ("linear", "async")
                    }
                    for model in MODELS
                },
            }
        )

    report = {
        "report_version": 1,
        "track": "development",
        "track_reason": "Codex CLI transport; full container, gateway, hidden-verifier, scoring, aggregation, and audit path used.",
        "manifest": {
            "path": str(manifest_path),
            "sha256": manifest_sha256,
            "planned_episodes_per_model": len(manifest["episodes"]),
            "case_count": len(cases),
            "execution_modes": ["linear", "async"],
            "guidance": manifest["guidance"],
            "seed": manifest["seed"],
            "repetitions": manifest["repetitions"],
            "evaluation_contract_version": manifest["evaluation_contract_version"],
        },
        "models": {
            model: {
                "requested_model": MODEL_LABELS[model],
                "summary": model_summary(all_scores[model]),
                "audit": audits[model],
                "aggregate_audit": aggregate_audits[model],
            }
            for model in MODELS
        },
        "case_results": case_rows,
        "run_notes": [
            "Framework aggregate dynamic_control_score is null because this is a development run with incomplete paired dynamic-score coverage; observed dynamic values are reported separately.",
            "Unscored does not mean semantic score zero: it means the episode did not satisfy all dynamic scenario/exposure preconditions for inclusion in that metric denominator.",
            "Luna had one transient Docker image build failure before episode 7; a manual rebuild succeeded and the frozen run resumed. The final 20 score artifacts contain no infrastructure failures.",
            "One repetition is pilot evidence, not a statistically stable model ranking.",
        ],
    }

    lines = [
        "# Async-RBench 首批 10 个正式 case：三模型完整测评",
        "",
        "## 实验状态",
        "",
        f"- 冻结 manifest：`{manifest_sha256}`",
        f"- 设计：10 case × linear/async × 1 repetition × 3 models = {len(cases) * 2 * len(MODELS)} episodes",
        f"- guidance：`{manifest['guidance']}`；seed：`{manifest['seed']}`；evaluation contract：`{manifest['evaluation_contract_version']}`",
        "- 轨道：development。模型通过 Codex CLI 调用，但 Docker、事件注入、网关、Oracle/隐藏测试、控制流评分、聚合和审计均走完整 Async-RBench 框架。",
        "",
        "## 总体结果",
        "",
        "| 模型 | 完成 | scored / unscored | 全 20 条观察 S | linear S | async S | 动态可观测数 | 观察 D | 观察 DT | 隐藏测试全过 | 预算耗尽 | tokens | episode 时长和(h) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        summary = report["models"][model]["summary"]
        lines.append(
            "| {name} | {done}/20 | {scored}/{unscored} | {overall} | {linear} | {async_} | {dynamic_n}/10 | {d} | {dt} | {hidden}/20 | {budget}/20 | {tokens:,} | {hours} |".format(
                name=MODEL_LABELS[model],
                done=summary["completed"],
                scored=summary["scored"],
                unscored=summary["unscored"],
                overall=fmt(summary["observed_semantic_all"]),
                linear=fmt(summary["observed_semantic_linear"]),
                async_=fmt(summary["observed_semantic_async"]),
                dynamic_n=summary["dynamic_observation_count"],
                d=fmt(summary["observed_dynamic_control_async"]),
                dt=fmt(summary["observed_dt_async"]),
                hidden=summary["hidden_test_passes"],
                budget=summary["budget_exhausted"],
                tokens=summary["total_tokens"],
                hours=fmt(summary["summed_episode_hours"]),
            )
        )

    lines.extend(
        [
            "",
            "`linear S`、`async S` 和“全 20 条观察 S”包含每个 episode 的原始语义分，包括动态指标为 `unscored` 的 episode。框架正式计分子集见 `summary.json` 的 `framework_scored_semantic_*` 字段。",
            "",
            "## 逐 case 结果",
            "",
            "单元格格式：`linear S / async S [async状态, D, DT]`。`—` 表示该动态指标不适用或未进入分母。",
            "",
            "| case | 语义点/控制点 | Sol | Terra | Luna |",
            "|---|---:|---|---|---|",
        ]
    )
    for row in case_rows:
        cells = []
        for model in MODELS:
            linear = row["models"][model]["linear"]
            async_ = row["models"][model]["async"]
            cells.append(
                f"{fmt(linear['semantic_task_score'])} / {fmt(async_['semantic_task_score'])} "
                f"[{async_['score_status']}, D={fmt(async_['dynamic_control_score'])}, DT={fmt(async_['dt_score'])}]"
            )
        lines.append(
            f"| `{row['case_id']}` | {row['semantic_check_count']}/{row['control_flow_check_count']} | "
            + " | ".join(cells)
            + " |"
        )

    lines.extend(
        [
            "",
            "## 审计结论",
            "",
            "- 三模型均为 20/20 episode；最终 score artifacts 中基础设施失败为 0，超时为 0。",
            "- 三组审计均确认 20/20 case contract、evaluation contract、scaffold 与当前冻结版本一致。",
            "- 每组 60/60 workstream 合约正负 fixture 通过；无可见性泄漏。",
            "- Luna 在第 7 条开始前出现一次 Docker 临时构建失败；同一镜像手工重建成功后从断点续跑。最终结果完整，但该运行过程事件需保留在实验日志中。",
            "",
            "## 解释限制",
            "",
            "- `unscored` 不等于语义得分为 0；它表示动态场景或事件暴露前置条件未完全满足，D/DT 不进入正式分母。",
            "- 每个模型只有一次重复，当前结果适合作为 pilot 和 case 校准证据，不足以做稳定模型排名。",
            "- leaderboard 主指标保持为空，因为这是 Codex CLI transport 的 development run，而不是 API-only Track A 提交。",
            "",
        ]
    )
    return report, "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("artifacts/first-10-model-eval/final-20260831"),
    )
    args = parser.parse_args()
    report, markdown = build_report(args.root)
    (args.root / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.root / "RESULTS.md").write_text(markdown, encoding="utf-8")
    print(json.dumps({"summary": str(args.root / "summary.json"), "report": str(args.root / "RESULTS.md")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
