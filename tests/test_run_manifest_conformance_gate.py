from __future__ import annotations

import asyncio
from argparse import Namespace
from pathlib import Path

import pytest

from async_rbench import eval_cli


def test_run_manifest_stops_before_episodes_when_conformance_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    eval_cli.write_manifest(
        manifest_path,
        eval_cli.create_manifest(
            ["tbn-partial-failure-recovery-0e92790bd0"],
            1,
            "incentive",
            7,
            ["async"],
            None,
        ),
    )

    async def failed_conformance(*args: object, **kwargs: object) -> dict[str, bool]:
        return {"conformance_passed": False}

    monkeypatch.setattr(eval_cli, "run_conformance", failed_conformance)
    args = Namespace(
        manifest=str(manifest_path),
        output=str(tmp_path / "run"),
        official_track=False,
        adapter_command=None,
        skip_conformance=False,
        no_container=False,
        profile="conformance_mock",
        runtime_mode=None,
        config=None,
        timeout=30,
        gateway_grace=5,
        no_progress=True,
        resume=False,
        keep_containers=False,
        progress_heartbeat=5,
    )

    with pytest.raises(ValueError, match="adapter conformance failed"):
        asyncio.run(eval_cli._run_manifest(args))
