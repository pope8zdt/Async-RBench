from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .evaluation.registry_audit import validate_semantic_registries
from .judge import JudgeBundleProvider, compose_runtime_case, load_judge_case
from .paths import registered_case_dir
from .release import build_judge_release, build_public_release, validate_paired_release
from .spec import discover_case_instances, discover_cases, load_case, validate_case


ROOT = Path(__file__).resolve().parents[2]


def _selected_root(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "root", None) or ROOT).resolve()


def cmd_list(args: argparse.Namespace) -> int:
    cases = discover_cases(_selected_root(args))
    print(json.dumps({"cases": [case.case_id for case in cases]}, ensure_ascii=False))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    root = _selected_root(args)
    path = registered_case_dir(root, args.case_id) / "public" / "case.yaml"
    try:
        case = load_case(path)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(case.raw, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_validate_public(args: argparse.Namespace) -> int:
    root = _selected_root(args)
    try:
        cases = discover_cases(root)
        instances = [instance.load() for instance in discover_case_instances(root)]
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    errors = [error for case in instances for error in validate_case(case)]
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(json.dumps({
        "valid": True,
        "case_count": len(cases),
        "instances": len(instances),
    }))
    return 0


cmd_validate = cmd_validate_public


def cmd_validate_judge(args: argparse.Namespace) -> int:
    root = _selected_root(args)
    provider = JudgeBundleProvider(Path(args.judge_root))
    errors: list[str] = []
    try:
        instances = discover_case_instances(root)
    except (OSError, ValueError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for instance in instances:
        try:
            public = instance.load()
            compose_runtime_case(public, load_judge_case(public, provider))
        except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
            errors.append(str(exc))
    if not errors:
        errors.extend(validate_semantic_registries(root, provider))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(json.dumps({
        "valid": True,
        "instances": len(instances),
        "judge_root": str(provider.root),
    }, ensure_ascii=False))
    return 0


def cmd_certify_release(args: argparse.Namespace) -> int:
    root = _selected_root(args)
    provider = JudgeBundleProvider(Path(args.judge_root))
    public_release = build_public_release(root)
    judge_release = build_judge_release(root, provider.root, public_release)
    errors = validate_paired_release(public_release, judge_release)
    if not errors:
        judge_args = argparse.Namespace(root=str(root), judge_root=str(provider.root))
        if cmd_validate_judge(judge_args) != 0:
            return 1
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    public_path = root / "data" / "async-rbench" / "release.json"
    judge_path = provider.root / "release.json"
    if getattr(args, "write_manifests", False):
        public_path.write_text(public_release.to_json(), encoding="utf-8")
        judge_path.write_text(judge_release.to_json(), encoding="utf-8")
    else:
        for path, expected, label in (
            (public_path, public_release.to_dict(), "public"),
            (judge_path, judge_release.to_dict(), "judge"),
        ):
            if path.is_file() and json.loads(path.read_text(encoding="utf-8")) != expected:
                print(
                    f"stored {label} release manifest differs from current corpus: {path}",
                    file=sys.stderr,
                )
                return 1

    print(json.dumps({
        "valid": True,
        "release_id": public_release.release_id,
        "case_count": public_release.stats.case_count,
        "initial_subtask_count": public_release.stats.initial_subtask_count,
        "source_counts": public_release.stats.source_counts,
        "difficulty_counts": public_release.stats.difficulty_counts,
        "subtask_histogram": public_release.stats.subtask_histogram,
        "scenario_counts": judge_release.scenario_counts,
        "target_event_count": judge_release.target_event_count,
        "manifests_written": bool(getattr(args, "write_manifests", False)),
    }, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="async-rbench")
    sub = parser.add_subparsers(dest="command", required=True)

    list_command = sub.add_parser("list", help="List public benchmark cases")
    list_command.add_argument("--root")
    list_command.set_defaults(func=cmd_list)

    inspect = sub.add_parser("inspect", help="Show one participant-visible case contract")
    inspect.add_argument("case_id")
    inspect.add_argument("--root")
    inspect.set_defaults(func=cmd_inspect)

    validate_public = sub.add_parser(
        "validate-public",
        help="Validate participant-visible contracts without a judge bundle",
    )
    validate_public.add_argument("--root")
    validate_public.set_defaults(func=cmd_validate_public)

    validate = sub.add_parser("validate", help="Compatibility alias for validate-public")
    validate.add_argument("--root")
    validate.set_defaults(func=cmd_validate_public)

    validate_judge = sub.add_parser(
        "validate-judge",
        help="Validate external scoring bundles against the public corpus",
    )
    validate_judge.add_argument("--root")
    validate_judge.add_argument("--judge-root", required=True)
    validate_judge.set_defaults(func=cmd_validate_judge)

    certify = sub.add_parser(
        "certify-release",
        help="Certify paper invariants and the explicitly supplied judge bundle",
    )
    certify.add_argument("--root")
    certify.add_argument("--judge-root", required=True)
    certify.add_argument("--write-manifests", action="store_true")
    certify.set_defaults(func=cmd_certify_release)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
