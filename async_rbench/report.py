from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


class CheckBook:
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self.checks: list[dict[str, Any]] = []

    def check(self, name: str, fn: Callable[[], Any]) -> None:
        try:
            detail = fn()
            self.checks.append({"name": name, "passed": True, "detail": detail})
        except Exception as exc:  # Verifiers must report every failed invariant.
            self.checks.append(
                {"name": name, "passed": False, "detail": f"{type(exc).__name__}: {exc}"}
            )

    def write(self, path: Path) -> dict[str, Any]:
        report = {
            "case_id": self.case_id,
            "success": all(item["passed"] for item in self.checks),
            "checks": self.checks,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
