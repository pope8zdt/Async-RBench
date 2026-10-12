import asyncio
from pathlib import Path

from async_rbench.conformance import runner
from async_rbench import eval_cli


def test_conformance_passes_explicit_judge_to_each_episode(tmp_path, monkeypatch):
    received = []
    async def capture(root, config):
        received.append(config.judge_root)
        config.output_dir.mkdir(parents=True)
        (config.output_dir / "trace.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(runner, "run_episode", capture)
    judge = tmp_path / "private"
    asyncio.run(runner.run_conformance(
        Path(__file__).resolve().parents[1], adapter_command=["no-model"],
        output_dir=tmp_path / "out", case_ids=["gaia2-stockholm-moveout"], judge_root=judge,
    ))
    assert received == [judge]


def test_standalone_conformance_accepts_explicit_judge():
    args = eval_cli.build_parser().parse_args([
        "conformance", "--output", "report.json", "--judge-root", "private"])
    assert args.judge_root == "private"
