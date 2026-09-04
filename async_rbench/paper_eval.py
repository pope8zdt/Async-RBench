from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .evaluation.manifest import create_manifest, write_manifest
from .spec import resolve_case_instance


DEFAULT_EXISTING_SELECTION = Path(
    "research/experiment-design/paper-eval-existing-61.csv"
)
COHORT_ID = "paper-eval-existing-61"
ALLOWED_READINESS = {
    "ready",
    "migration_audit_false_positive",
    "normalization_required",
}


@dataclass(frozen=True)
class ExistingSelectionRow:
    selection_order: int
    case_id: str
    instance_id: str
    theme: str
    source: str
    difficulty: str
    difficulty_score: int
    split: str
    readiness: str

    @property
    def instance_key(self) -> str:
        return f"{self.case_id}::{self.instance_id}"


def load_existing_selection(
    path: Path,
    *,
    root: Path | None = None,
) -> list[ExistingSelectionRow]:
    """Load and fail closed on the frozen, runnable existing-case cohort."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        raw_rows = list(csv.DictReader(handle))

    rows: list[ExistingSelectionRow] = []
    for line_number, raw in enumerate(raw_rows, start=2):
        try:
            row = ExistingSelectionRow(
                selection_order=int(raw["selection_order"]),
                case_id=raw["case_id"].strip(),
                instance_id=raw["instance_id"].strip(),
                theme=raw["theme"].strip(),
                source=raw["source"].strip(),
                difficulty=raw["difficulty"].strip(),
                difficulty_score=int(raw["difficulty_score"]),
                split=raw["split"].strip(),
                readiness=raw["readiness"].strip(),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid selection row at line {line_number}: {exc}") from exc
        if not row.case_id or not row.instance_id:
            raise ValueError(f"blank case identity at line {line_number}")
        if row.readiness not in ALLOWED_READINESS:
            raise ValueError(
                f"unsupported readiness {row.readiness!r} at line {line_number}"
            )
        rows.append(row)

    if len(rows) != 61:
        raise ValueError(f"{COHORT_ID} must contain exactly 61 rows, got {len(rows)}")
    if len({row.case_id for row in rows}) != len(rows):
        raise ValueError("selection contains duplicate case_id")
    if len({row.instance_key for row in rows}) != len(rows):
        raise ValueError("selection contains duplicate case instance")
    if "gaia2-stockholm-moveout" in {row.case_id for row in rows}:
        raise ValueError("retired GAIA2 case must not appear in the runnable cohort")
    if [row.selection_order for row in rows] != sorted(
        row.selection_order for row in rows
    ):
        raise ValueError("selection rows must be ordered by selection_order")

    if root is not None:
        for row in rows:
            instance = resolve_case_instance(root, row.case_id, row.instance_id)
            if instance.split != row.split:
                raise ValueError(
                    f"split mismatch for {row.instance_key}: "
                    f"selection={row.split}, registry={instance.split}"
                )
            required = (
                instance.contract_path,
                instance.case_dir / "task/tests/semantic_checks.json",
                instance.case_dir / "task/tests/control_flow_checks.json",
            )
            missing = [str(item) for item in required if not item.is_file()]
            if missing:
                raise ValueError(
                    f"{row.instance_key} is not directly runnable; missing {missing}"
                )
    return rows


def create_selection_manifest(
    root: Path,
    rows: Sequence[ExistingSelectionRow],
    *,
    repetitions: int,
    guidance: str,
    seed: int,
    model: str,
) -> dict[str, object]:
    """Create the standard immutable manifest for the frozen 61-case cohort."""
    package_root = Path(__file__).resolve().parents[1]
    if root.resolve() != package_root.resolve():
        raise ValueError("manifest creation must target this repository root")
    manifest = create_manifest(
        [row.case_id for row in rows],
        repetitions,
        guidance,
        seed,
        execution_modes=["linear", "async"],
        instance_keys=[row.instance_key for row in rows],
        model=model,
    )
    manifest["paper_eval_selection"] = {
        "cohort": COHORT_ID,
        "case_count": len(rows),
        "selection_file": DEFAULT_EXISTING_SELECTION.as_posix(),
    }
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m async_rbench.paper_eval",
        description="Validate or materialize the frozen runnable 61-case cohort.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Validate all 61 registered instances")
    check.add_argument("--root", type=Path, default=Path.cwd())

    make = sub.add_parser(
        "make-manifest", help="Create a standard paired Linear/Async manifest"
    )
    make.add_argument("--root", type=Path, default=Path.cwd())
    make.add_argument("--output", type=Path, required=True)
    make.add_argument("--repetitions", type=int, default=1)
    make.add_argument("--guidance", choices=("none", "protocol", "incentive"), default="incentive")
    make.add_argument("--seed", type=int, default=2026)
    make.add_argument("--model", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    rows = load_existing_selection(root / DEFAULT_EXISTING_SELECTION, root=root)
    if args.command == "check":
        print(json.dumps({"cohort": COHORT_ID, "case_count": len(rows)}))
        return 0
    manifest = create_selection_manifest(
        root,
        rows,
        repetitions=args.repetitions,
        guidance=args.guidance,
        seed=args.seed,
        model=args.model,
    )
    write_manifest(args.output.resolve(), manifest)
    print(json.dumps({
        "cohort": COHORT_ID,
        "case_count": len(rows),
        "episodes": len(manifest["episodes"]),
        "output": str(args.output.resolve()),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
