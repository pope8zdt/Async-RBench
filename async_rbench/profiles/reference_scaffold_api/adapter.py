from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from .config import ScaffoldConfig, build_backends
from .gateway import DeliveryReader, ProtocolEmitter
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
    if config.backend == "scripted_test":
        main_backend = ScriptedTestBackend()
        child_backend = ScriptedTestBackend()
    else:
        # Dual provider backends (spec §8): the main agent and the fixed child
        # pool each get a role-scoped backend with provider identity, concurrency
        # semaphore and child_pool_id recorded separately.
        main_backend, child_backend = build_backends(config)
    workspace = CapabilityRuntimeProxy(emitter.write)
    reader.set_capability_handler(workspace.handle_response)
    # ReferenceScaffold.run() calls start() again — idempotent.
    reader.start()
    scaffold = ReferenceScaffold(
        start=start,
        config=config,
        main_backend=main_backend,
        child_backend=child_backend,
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
        # An unhandled adapter exception is benchmark tooling failing (the
        # scaffold process died), never a model decision.  Emit an
        # infrastructure crash so the episode is unscored instead of X=0.
        emitter.emit("infrastructure_failure", component="adapter_crash", detail=f"scaffold failure: {exc}")
        scaffold.finish_status = "incomplete"
        scaffold.final_summary = f"scaffold failure: {exc}"
    finally:
        await scaffold.shutdown()
    combined_observations: list[dict[str, Any]] = []
    for runtime_backend in (main_backend, child_backend):
        metadata = getattr(runtime_backend, "runtime_metadata", lambda: {"model_observations": []})()
        combined_observations.extend((metadata or {}).get("model_observations") or [])
    emitter.emit(
        "participant_runtime_metadata",
        model_observations=combined_observations,
        child_pool_id=config.child_pool_id,
    )
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
