from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .. import eval_cli
from .config import TrackBConfig
from .frameworks import doctor_framework, public_frameworks


def run_eval_cli(argv: list[str]) -> int:
    return eval_cli.main(argv)


def _is_formal_output(path: Path) -> bool:
    parts = [part.lower() for part in path.resolve().parts]
    for index in range(len(parts) - 2):
        if (
            parts[index] == "artifacts"
            and parts[index + 1] == "experiments"
            and parts[index + 2].startswith("formal-")
        ):
            return True
    return False


def _load_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a JSON object")
    if payload.get("official_track") is True or payload.get("track") == "A":
        raise ValueError("Track B cannot run an official Track A manifest")
    return payload


def cmd_list_frameworks(_args: argparse.Namespace) -> int:
    print(json.dumps({"frameworks": list(public_frameworks())}, indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    config = TrackBConfig.from_file(Path(args.config))
    report = doctor_framework(config.framework, config)
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0 if report.ready else 1


def cmd_validate_config(args: argparse.Namespace) -> int:
    config = TrackBConfig.from_file(Path(args.config))
    print(json.dumps(config.public_metadata(), indent=2, sort_keys=True))
    return 0


def cmd_make_manifest(args: argparse.Namespace) -> int:
    argv = [
        "make-manifest", "--output", str(Path(args.output).resolve()),
        "--repetitions", str(args.repetitions),
        "--guidance", "incentive", "--seed", str(args.seed),
        "--execution-modes", "linear", "async",
        "--instances", *args.instances,
    ]
    if args.model:
        argv.extend(["--model", args.model])
    return run_eval_cli(argv)


def cmd_conformance(args: argparse.Namespace) -> int:
    config = TrackBConfig.from_file(Path(args.config))
    argv = [
        "conformance", "--profile", "track_b", "--config", str(config.source_path),
        "--output", str(Path(args.output).resolve()),
    ]
    if args.cases:
        argv.extend(["--cases", *args.cases])
    return run_eval_cli(argv)


def cmd_run(args: argparse.Namespace) -> int:
    config = TrackBConfig.from_file(Path(args.config))
    manifest_path = Path(args.manifest).resolve()
    _load_manifest(manifest_path)
    output = Path(args.output).resolve()
    if _is_formal_output(output):
        raise ValueError("Track B output cannot be inside a formal experiment directory")
    argv = [
        "run-manifest", "--manifest", str(manifest_path),
        "--profile", "track_b", "--config", str(config.source_path),
        "--output", str(output),
    ]
    if args.no_container:
        argv.append("--no-container")
    return run_eval_cli(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m async_rbench.track_b")
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list-frameworks")
    listing.set_defaults(func=cmd_list_frameworks)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--config", required=True)
    doctor.set_defaults(func=cmd_doctor)

    validate = sub.add_parser("validate-config")
    validate.add_argument("--config", required=True)
    validate.set_defaults(func=cmd_validate_config)

    make = sub.add_parser("make-manifest")
    make.add_argument("--instances", nargs="+", required=True)
    make.add_argument("--output", required=True)
    make.add_argument("--model")
    make.add_argument("--repetitions", type=int, default=1)
    make.add_argument("--seed", type=int, default=2026)
    make.set_defaults(func=cmd_make_manifest)

    conformance = sub.add_parser("conformance")
    conformance.add_argument("--config", required=True)
    conformance.add_argument("--output", required=True)
    conformance.add_argument("--cases", nargs="*")
    conformance.set_defaults(func=cmd_conformance)

    run = sub.add_parser("run")
    run.add_argument("--config", required=True)
    run.add_argument("--manifest", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--no-container", action="store_true")
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
