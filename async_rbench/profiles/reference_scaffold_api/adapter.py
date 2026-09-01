from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .config import ScaffoldConfig
from .gateway import DeliveryReader, ProtocolEmitter
from ...evaluation.model_backend import build_backend
from ..conformance_mock.scripted_backend import ScriptedTestBackend
from .runtime import ReferenceScaffold
from ...protocol_sdk.capability import CapabilityRuntimeProxy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Async-RBench thin reference participant scaffold")
    parser.add_argument("--config", type=Path, help="YAML scaffold configuration")
    parser.add_argument(
        "--backend", choices=["openai_compatible", "codex_cli", "scripted_test"],
        help="Override backend",
    )
    parser.add_argument("--workspace-mode", choices=["container_clone", "disabled"], help="Override workspace mode")
    return parser


async def run_adapter(args: argparse.Namespace) -> int:
    start = DeliveryReader.receive_start()
    config = ScaffoldConfig.from_file(args.config, {
        "backend": args.backend,
        "workspace_mode": args.workspace_mode,
    })

    emitter = ProtocolEmitter()
    reader = DeliveryReader()
    backend = (
        ScriptedTestBackend()
        if config.backend == "scripted_test"
        else build_backend(config)
    )
    workspace = CapabilityRuntimeProxy(emitter.write)
    reader.set_capability_handler(workspace.handle_response)
    # ReferenceScaffold.run() calls start() again — idempotent.
    reader.start()
    scaffold = ReferenceScaffold(
        start=start,
        config=config,
        backend=backend,
        workspace=workspace,
        emitter=emitter,
        delivery_reader=reader,
    )
    emitter.emit("participant_metadata", **config.public_metadata(), scaffold="async-rbench-reference")
    emitter.emit("ready")
    try:
        await scaffold.run()
    except Exception as exc:
        logging.getLogger("async_rbench.profiles.reference_scaffold_api").exception("reference scaffold failed")
        scaffold.finish_status = "incomplete"
        scaffold.final_summary = f"scaffold failure: {exc}"
    finally:
        await scaffold.shutdown()
    runtime_metadata = getattr(backend, "runtime_metadata", lambda: {"model_observations": []})()
    emitter.emit("participant_runtime_metadata", **runtime_metadata)
    emitter.emit(
        "episode_ended",
        final_answer=scaffold.final_summary,
        local_status=scaffold.finish_status,
        declared_task_success=scaffold.finish_status == "completed",
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
