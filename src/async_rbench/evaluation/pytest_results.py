from __future__ import annotations

import re
from typing import Any


_DURATION_SUFFIX = re.compile(r"\bin\s+\d+(?:\.\d+)?s(?:\s+\([^)]*\))?\s*(?:=+)?$")
_COUNT = re.compile(
    r"(\d+)\s+"
    r"(passed|failed|errors?|skipped|deselected|warnings?|xfailed|xpassed)\b"
)
_COMPONENT_BEGIN = re.compile(r"^ASYNC_RBENCH_COMPONENT_BEGIN\s+([a-z0-9_]+)\s*$")
_COMPONENT_END = re.compile(
    r"^ASYNC_RBENCH_COMPONENT_END\s+([a-z0-9_]+)\s+exit_code=(\d+)\s*$"
)
_SEMANTIC_OUTCOME = re.compile(
    r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+(.+?)(?:\s+-\s+.*)?$"
)


def parse_pytest_summary(output: str) -> dict[str, Any]:
    """Return counted pytest outcomes across one or more invocations.

    Skipped, deselected, and expected-failure outcomes remain diagnostic only.
    The pass fraction denominator is passed + failed + collection/runtime errors.
    """
    totals = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "deselected": 0,
        "warnings": 0,
        "xfailed": 0,
        "xpassed": 0,
    }
    summary_lines = 0
    for raw_line in (output or "").splitlines():
        line = raw_line.strip()
        if not _DURATION_SUFFIX.search(line):
            continue
        matches = _COUNT.findall(line)
        if not matches or not any(
            status in {"passed", "failed", "error", "errors"}
            for _, status in matches
        ):
            continue
        summary_lines += 1
        for raw_count, status in matches:
            normalized = {
                "error": "errors",
                "warning": "warnings",
            }.get(status, status)
            totals[normalized] += int(raw_count)

    counted = totals["passed"] + totals["failed"] + totals["errors"]
    return {
        **totals,
        "counted": counted,
        "summary_lines": summary_lines,
        "test_pass_fraction": totals["passed"] / counted if counted else None,
    }


def parse_component_summaries(output: str) -> dict[str, dict[str, Any]]:
    """Parse independently delimited verifier component pytest results."""
    sections: dict[str, list[str]] = {}
    exit_codes: dict[str, int] = {}
    current: str | None = None
    for raw_line in (output or "").splitlines():
        line = raw_line.strip()
        begin = _COMPONENT_BEGIN.match(line)
        if begin:
            current = begin.group(1)
            sections.setdefault(current, [])
            continue
        end = _COMPONENT_END.match(line)
        if end:
            name = end.group(1)
            exit_codes[name] = int(end.group(2))
            if current == name:
                current = None
            continue
        if current is not None:
            sections[current].append(raw_line)

    results: dict[str, dict[str, Any]] = {}
    for name, lines in sections.items():
        summary = parse_pytest_summary("\n".join(lines))
        exit_code = exit_codes.get(name)
        results[name] = {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "completed": exit_code is not None,
            **summary,
        }
    return results


def parse_semantic_check_results(
    output: str, registry: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Map pytest reporting output onto a frozen semantic-check registry.

    Pytest functions and parameterization remain execution details.  Every
    registered semantic id contributes exactly one denominator item; a missing,
    skipped, xfailed, or errored item is not a pass.
    """
    if not registry:
        return None
    checks = list(registry.get("checks") or [])
    observed: dict[str, str] = {}
    for raw_line in (output or "").splitlines():
        match = _SEMANTIC_OUTCOME.match(raw_line.strip())
        if not match:
            continue
        status, node = match.groups()
        normalized_node = node.replace("\\", "/")
        for item in checks:
            expected = str(item["pytest_node"]).replace("\\", "/")
            if normalized_node.endswith(expected):
                observed[str(item["id"])] = status.lower()
                break

    results = []
    for item in checks:
        check_id = str(item["id"])
        status = observed.get(check_id, "missing")
        results.append({
            "id": check_id,
            "category": str(item.get("category", "task_outcome")),
            "measurement_type": str(item.get("measurement_type", "semantic")),
            "capability_target": str(item.get("capability_target", "")),
            "relevance_tier": str(item.get("relevance_tier", "")),
            "score_domain": str(item.get("score_domain") or ""),
            "event_id": str(item.get("event_id") or ""),
            "pytest_node": str(item["pytest_node"]),
            "status": status,
            "passed": status == "passed",
        })
    passed = sum(bool(item["passed"]) for item in results)
    total = len(results)
    return {
        "registry_version": str(registry.get("version", "1")),
        "results": results,
        "passed": passed,
        "total": total,
        "test_point_pass_rate": passed / total if total else None,
    }
