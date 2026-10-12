"""Create a separate runtime judge from existing private task checks.

No reference answer, event schedule, or task outcome test is generated. Existing
list requirements are frozen with their existing uniform aggregation rule; an
unregistered target is bound only when its schedule and outcome checks agree.
The destination must be new and outside the public repository.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import yaml

from async_rbench.judge import runtime_event_contract, runtime_verifier_script, JudgeBundleProvider
from async_rbench.release import build_public_release, build_judge_release, validate_paired_release


def prepare(root: Path, source: Path, output: Path) -> dict:
    root, source, output = root.resolve(), source.resolve(), output.resolve()
    if output == root or root in output.parents or output == source or source in output.parents:
        raise ValueError("judge output must be separate from the public repository and source bundle")
    if output.exists():
        raise FileExistsError(f"destination already exists: {output}")
    public_release = build_public_release(root)
    prepared = []
    for row in public_release.cases:
        case_id = row["case_id"]
        evaluator = source / "cases" / case_id / "evaluator"
        public = yaml.safe_load((root / "data/async-rbench/cases" / case_id / "public/case.yaml").read_text(encoding="utf-8"))
        private = yaml.safe_load((evaluator / "case.yaml").read_text(encoding="utf-8"))
        control = json.loads((evaluator / "control_flow_checks.json").read_text(encoding="utf-8"))
        semantic = json.loads((evaluator / "semantic_checks.json").read_text(encoding="utf-8"))
        contract = runtime_event_contract(public, private, control, semantic)
        prepared.append((case_id, private, control, contract))
    # Do not create a partial destination when contract preparation fails.
    output.mkdir(parents=True)
    for case_id, private, control, contract in prepared:
        destination = output / "cases" / case_id
        shutil.copytree(source / "cases" / case_id, destination,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        evaluator = destination / "evaluator"
        runner = JudgeBundleProvider(output).verifier_dir(case_id) / "run-tests.sh"
        original = runner.read_text(encoding="utf-8")
        repaired = runtime_verifier_script(original)
        if repaired != original:
            runner.write_text(repaired, encoding="utf-8", newline="\n")
        private["event_contracts"] = [contract]
        control["event_contracts"] = [contract]
        (evaluator / "case.yaml").write_text(yaml.safe_dump(private, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n")
        (evaluator / "control_flow_checks.json").write_text(json.dumps(control, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        plan_path = evaluator / "dynamic_point_plan.json"
        if plan_path.is_file():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["event_contracts"] = [contract]
            plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    release = build_judge_release(root, output, public_release)
    errors = validate_paired_release(public_release, release)
    if errors:
        raise ValueError("; ".join(errors))
    (output / "release.json").write_text(release.to_json(), encoding="utf-8", newline="\n")
    policy = {"runtime_contract_version": "command-boundaries-v1",
              "purpose": "new_runs", "case_count": len(prepared),
              "process_observation_scope": "command_boundaries",
              "paper_result_data_modified": False}
    (output / "runtime-policy.json").write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {"judge_root": str(output), "case_count": len(prepared),
            "target_event_count": release.target_event_count, "scenario_counts": release.scenario_counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
