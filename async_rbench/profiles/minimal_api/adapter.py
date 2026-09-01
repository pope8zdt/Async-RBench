from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from ...evaluation.protocol import canonical_digest
from ..reference_scaffold_api.gateway import ProtocolEmitter, DeliveryReader


LOGGER = logging.getLogger("async_rbench.profiles.minimal_api")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Async-RBench minimal-api adapter")
    parser.add_argument(
        "--workspace-mode", choices=["container_clone", "disabled"], default="disabled",
    )
    return parser


async def run_adapter(args: argparse.Namespace) -> int:
    start = DeliveryReader.receive_start()
    emitter = ProtocolEmitter()
    config = {
        "workspace_mode": args.workspace_mode,
        "main_model": "minimal-api-mock",
        "child_model": "minimal-api-mock",
    }
    # The minimal surface exposes terminal + submit + acknowledge + commit +
    # finish with no subagent manager, so it never spawns children or consumes
    # deliveries. It is a real (if minimal) policy profile, not a full scaffold.
    emitter.emit(
        "participant_metadata",
        backend="openai_compatible",
        main_model=config["main_model"],
        child_model=config["child_model"],
        workspace_mode=config["workspace_mode"],
        config_sha256=canonical_digest(config),
        scaffold="async_rbench-minimal-api",
    )
    emitter.emit("ready")
    emitter.emit("main_action", action_id="terminal", kind="terminal")
    emitter.emit("main_action", action_id="submit", kind="submit")
    emitter.emit("participant_runtime_metadata", model_observations=[
        {"resolved_model": config["main_model"], "tokens": 0},
    ])
    emitter.emit(
        "episode_ended",
        final_answer="minimal-api episode complete",
        local_status="completed",
        declared_task_success=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = build_parser().parse_args(argv)
    return asyncio.run(run_adapter(args))


if __name__ == "__main__":
    raise SystemExit(main())
