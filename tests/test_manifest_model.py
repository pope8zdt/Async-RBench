from __future__ import annotations

import json
from pathlib import Path

from async_rbench import eval_cli
from async_rbench.evaluation.manifest import create_manifest


def test_manifest_model_stamps_top_level_and_every_episode() -> None:
    manifest = create_manifest(
        ["secure-release"], 1, "incentive", 2026,
        instance_keys=["secure-release::seed-1"],
        model="some-model",
    )
    assert manifest["model"] == "some-model"
    assert manifest["episodes"]
    for episode in manifest["episodes"]:
        assert episode["model"] == "some-model"


def test_manifest_model_remains_none_when_omitted() -> None:
    """The model factor is optional: omitting it keeps episodes at model: None."""
    manifest = create_manifest(
        ["secure-release"], 1, "incentive", 2026,
        instance_keys=["secure-release::seed-1"],
    )
    assert manifest["model"] is None
    assert manifest["episodes"]
    for episode in manifest["episodes"]:
        assert episode["model"] is None


def test_make_manifest_cli_stamps_model_flag(tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"
    args = eval_cli.build_parser().parse_args([
        "make-manifest",
        "--output", str(output),
        "--repetitions", "1",
        "--model", "m1",
        "--instances", "secure-release::seed-1",
    ])
    assert args.model == "m1"
    assert args.func(args) == 0
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["model"] == "m1"
    assert manifest["episodes"]
    for episode in manifest["episodes"]:
        assert episode["model"] == "m1"
