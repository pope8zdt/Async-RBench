from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from ...protocol_sdk.capability import CapabilityRuntimeProxy
from ..conformance_mock.scripted_backend import ScriptedTestBackend
from ..reference_scaffold_api.config import ScaffoldConfig
from ..reference_scaffold_api.gateway import DeliveryReader, ProtocolEmitter
from ..reference_scaffold_api.runtime import ReferenceScaffold


LOGGER = logging.getLogger("async_rbench.profiles.native_agent")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Async-RBench native-agent reference adapter")
    parser.add_argument(
        "--workspace-mode", choices=["container_clone", "disabled"], default="disabled",
    )
    return parser


async def run_adapter(args: argparse.Namespace) -> int:
    start = DeliveryReader.receive_start()
    # A native agent is the participant's own full system. The built-in
    # reference drives the same deterministic scripted protocol loop for the
    # no-container smoke path, but identifies itself as an independent
    # participant-style adapter rather than the official scaffold.
    config = ScaffoldConfig.from_file(
        None,
        {"backend": "scripted_test", "workspace_mode": args.workspace_mode},
    )
    emitter = ProtocolEmitter()
    reader = DeliveryReader()
    backend = ScriptedTestBackend()
    workspace = CapabilityRuntimeProxy(emitter.write)
    reader.set_capability_handler(workspace.handle_response)
    reader.start()
    scaffold = ReferenceScaffold(
        start=start,
        config=config,
        backend=backend,
        workspace=workspace,
        emitter=emitter,
        delivery_reader=reader,
    )
    emitter.emit("participant_metadata", **config.public_metadata(), scaffold="async_rbench-native-agent")
    emitter.emit("ready")
    try:
        await scaffold.run()
    except Exception as exc:
        LOGGER.exception("native-agent adapter failed")
        scaffold.finish_status = "incomplete"
        scaffold.final_summary = f"native-agent failure: {exc}"
    finally:
        await scaffold.shutdown()
    emitter.emit("participant_runtime_metadata", **backend.runtime_metadata())
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
