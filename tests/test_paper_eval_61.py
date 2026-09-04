from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from async_rbench.paper_eval import (
    DEFAULT_EXISTING_SELECTION,
    create_selection_manifest,
    load_existing_selection,
    main,
)


ROOT = Path(__file__).resolve().parents[1]


def test_formal_experiment_assets_have_one_canonical_location() -> None:
    assert DEFAULT_EXISTING_SELECTION == Path(
        "experiments/formal-61/paper-eval-existing-61.csv"
    )
    assert (ROOT / "experiments/formal-61/run.ps1").is_file()
    assert (ROOT / "experiments/formal-61/README.md").is_file()
    assert not (ROOT / "run_paper_eval_61.ps1").exists()
    assert not (
        ROOT / "research/experiment-design/paper-eval-existing-61.csv"
    ).exists()


def test_existing_selection_is_exactly_61_runnable_registered_instances() -> None:
    rows = load_existing_selection(ROOT / DEFAULT_EXISTING_SELECTION, root=ROOT)

    assert len(rows) == 61
    assert len({row.case_id for row in rows}) == 61
    assert len({row.instance_key for row in rows}) == 61
    assert "gaia2-stockholm-moveout" not in {row.case_id for row in rows}
    assert [row.selection_order for row in rows] == [
        *range(1, 48),
        *range(49, 63),
    ]
    assert Counter(row.readiness for row in rows) == {
        "ready": 41,
        "migration_audit_false_positive": 16,
        "normalization_required": 4,
    }


def test_selection_manifest_contains_every_case_in_frozen_order() -> None:
    rows = load_existing_selection(ROOT / DEFAULT_EXISTING_SELECTION, root=ROOT)
    manifest = create_selection_manifest(
        ROOT,
        rows,
        repetitions=1,
        guidance="incentive",
        seed=2026,
        model="example-model",
    )

    first_episode_positions: dict[str, int] = {}
    for position, episode in enumerate(manifest["episodes"]):
        first_episode_positions.setdefault(episode["case_id"], position)

    assert list(first_episode_positions) == [row.case_id for row in rows]
    assert len(manifest["episodes"]) == 61 * 2
    assert set(manifest["case_bundle_sha256"]) == {
        row.instance_key for row in rows
    }
    assert manifest["paper_eval_selection"] == {
        "cohort": "paper-eval-existing-61",
        "case_count": 61,
        "selection_file": DEFAULT_EXISTING_SELECTION.as_posix(),
    }


def test_manifest_cli_writes_a_directly_runnable_manifest(tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"

    assert main([
        "make-manifest",
        "--root", str(ROOT),
        "--output", str(output),
        "--repetitions", "1",
        "--seed", "7",
        "--model", "example-model",
    ]) == 0

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert len(manifest["episodes"]) == 122
    assert {episode["execution_mode"] for episode in manifest["episodes"]} == {
        "linear", "async",
    }
    assert manifest["paper_eval_selection"]["case_count"] == 61
