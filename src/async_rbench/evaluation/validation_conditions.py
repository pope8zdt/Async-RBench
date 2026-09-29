from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from ..paths import registered_case_dir


CONDITIONS = ("oracle_replan", "native_agent", "frozen_plan")
ORACLE_CARD_VERSION = "drs-oracle-card-1.0"
FROZEN_BLOCKED_TOOLS = frozenset({"spawn_subagent", "cancel_subagent"})
_CARD_FIELDS = frozenset(
    {
        "schema_version",
        "instance_key",
        "authority",
        "affected_workstream_or_dependency",
        "required_change",
        "required_preservation",
        "prohibited_impact",
        "semantic_verification_obligation",
    }
)
_LIST_FIELDS = _CARD_FIELDS - {"schema_version", "instance_key", "authority"}
_FORBIDDEN_KEY_PARTS = (
    "check_id",
    "command",
    "final_artifact_payload",
    "hidden_check",
    "mutation_id",
    "outcome_anchor",
    "path",
    "probe",
    "pytest",
    "test_id",
)
_FORBIDDEN_TEXT_FRAGMENTS = (
    "/tests/",
    "task/tests",
    "test_control_flow.py",
    "python -m pytest",
    "python3 -c",
    ".mutation.",
    ".event.probes",
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _all_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield str(key)
            yield from _all_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _all_keys(nested)


def _card_body(card: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): copy.deepcopy(value) for key, value in card.items() if key != "card_sha256"}


def audit_oracle_card(
    card: Mapping[str, Any],
    *,
    forbidden_fragments: Iterable[str] = (),
) -> list[str]:
    """Validate one participant-visible oracle card and reject evaluator leakage."""
    body = _card_body(card)
    unknown = sorted(set(body) - _CARD_FIELDS)
    missing = sorted(_CARD_FIELDS - set(body))
    if unknown:
        raise ValueError("oracle card has forbidden or unknown fields: " + ", ".join(unknown))
    if missing:
        raise ValueError("oracle card is missing fields: " + ", ".join(missing))
    if body.get("schema_version") != ORACLE_CARD_VERSION:
        raise ValueError(f"oracle card schema_version must be {ORACLE_CARD_VERSION}")
    if not str(body.get("instance_key") or ""):
        raise ValueError("oracle card instance_key cannot be empty")
    if not str(body.get("authority") or "").strip():
        raise ValueError("oracle card authority cannot be empty")
    for field_name in sorted(_LIST_FIELDS):
        value = body.get(field_name)
        if not isinstance(value, list) or not value or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise ValueError(f"oracle card {field_name} must be a non-empty string list")

    for key in _all_keys(body):
        lowered = key.casefold()
        if any(part in lowered for part in _FORBIDDEN_KEY_PARTS):
            raise ValueError(f"oracle card contains forbidden evaluator field {key!r}")

    text = _canonical_json(body).decode("utf-8").casefold()
    candidates = [*_FORBIDDEN_TEXT_FRAGMENTS, *forbidden_fragments]
    for fragment in candidates:
        needle = str(fragment).strip().casefold()
        if len(needle) >= 8 and needle in text:
            raise ValueError(
                "oracle card contains forbidden evaluator fragment " + repr(fragment)
            )

    supplied_digest = card.get("card_sha256")
    if supplied_digest is not None and str(supplied_digest) != _sha256(body):
        raise ValueError("oracle card digest mismatch")
    return []


def seal_oracle_card(card: Mapping[str, Any]) -> dict[str, Any]:
    body = _card_body(card)
    audit_oracle_card(body)
    return {**body, "card_sha256": _sha256(body)}


def load_oracle_card(
    path: Path,
    *,
    forbidden_fragments: Iterable[str] = (),
) -> dict[str, Any]:
    card = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(card, dict):
        raise ValueError(f"{path} must contain one oracle card object")
    if not card.get("card_sha256"):
        raise ValueError(f"{path} is not a sealed oracle card")
    audit_oracle_card(card, forbidden_fragments=forbidden_fragments)
    return card


def collect_case_leakage_fragments(root: Path, instance_key: str) -> tuple[str, ...]:
    """Collect held-out identifiers, paths and verifier commands for leak scanning."""
    case_id, separator, _ = instance_key.partition("::")
    if not separator:
        raise ValueError(f"invalid instance key {instance_key!r}")
    case_root = registered_case_dir(root, case_id)
    private = yaml.safe_load(
        (case_root / "evaluator" / "case.yaml").read_text(encoding="utf-8")
    )
    controls = json.loads(
        (case_root / "task" / "tests" / "control_flow_checks.json").read_text(
            encoding="utf-8"
        )
    )
    fragments: set[str] = set()
    for key, command in dict(private.get("hidden_checks") or {}).items():
        fragments.add(str(key))
        fragments.add(str(command))
    for binding in dict(private.get("workstream_bindings") or {}).values():
        if isinstance(binding, Mapping) and binding.get("validator_command"):
            fragments.add(str(binding["validator_command"]))
        for asset in list(binding.get("event_assets") or []) if isinstance(binding, Mapping) else []:
            fragments.add(str(asset))
    for check in list(controls.get("checks") or []):
        for key in ("id", "independence_key", "mutation_id", "pytest_node"):
            if check.get(key):
                fragments.add(str(check[key]))
        fragments.update(str(item) for item in check.get("outcome_anchors") or [])
    return tuple(sorted(item for item in fragments if len(item.strip()) >= 8))


@dataclass
class ConditionApplication:
    condition: str
    role: str
    leaderboard_eligible: bool
    target_delivery: dict[str, Any]
    participant_messages: tuple[dict[str, str], ...]
    blocked_post_event_tools: frozenset[str]
    remaining_budget_policy: str = "inherit_checkpoint_exactly"
    termination_policy: str = "shared_validation_termination_v1"
    _private_audit: list[dict[str, Any]] = field(default_factory=list, repr=False)

    @property
    def target_delivery_bytes(self) -> bytes:
        return _canonical_json(self.target_delivery)

    @property
    def private_audit(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(self._private_audit))

    def tool_allowed(self, tool_name: str, *, after_target_delivery: bool) -> bool:
        return not (
            after_target_delivery and tool_name in self.blocked_post_event_tools
        )

    def record_denial(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        after_target_delivery: bool,
    ) -> None:
        if self.tool_allowed(tool_name, after_target_delivery=after_target_delivery):
            raise ValueError(f"tool {tool_name!r} is not denied by condition {self.condition}")
        self._private_audit.append(
            {
                "type": "validation_condition_tool_denied",
                "condition": self.condition,
                "tool": tool_name,
                "arguments_sha256": _sha256(dict(arguments)),
                "reason": "post_event_structural_plan_mutation_blocked",
            }
        )


def apply_condition(
    condition: str,
    *,
    target_delivery: dict[str, Any],
    oracle_card: dict[str, Any] | None,
    frozen_instruction: str,
) -> ConditionApplication:
    if condition not in CONDITIONS:
        raise ValueError(f"unknown validation condition {condition!r}")
    delivery = copy.deepcopy(target_delivery)
    if delivery.get("type") != "result_delivered":
        raise ValueError("target delivery must have type 'result_delivered'")
    delivery_message = {
        "role": "user",
        "content": "ASYNC_RBENCH_DELIVERY " + _canonical_json(delivery).decode("utf-8"),
    }

    if condition == "native_agent":
        return ConditionApplication(
            condition=condition,
            role="capability_measurement",
            leaderboard_eligible=True,
            target_delivery=delivery,
            participant_messages=(delivery_message,),
            blocked_post_event_tools=frozenset(),
        )

    if condition == "oracle_replan":
        if oracle_card is None:
            raise ValueError("oracle card is required for oracle_replan")
        audit_oracle_card(oracle_card)
        if not oracle_card.get("card_sha256"):
            raise ValueError("oracle card must be digest sealed")
        guidance = {
            "role": "user",
            "content": "ASYNC_RBENCH_ORACLE_REPLAN "
            + _canonical_json(oracle_card).decode("utf-8"),
        }
        return ConditionApplication(
            condition=condition,
            role="positive_control",
            leaderboard_eligible=False,
            target_delivery=delivery,
            participant_messages=(delivery_message, guidance),
            blocked_post_event_tools=frozenset(),
        )

    instruction = frozen_instruction.strip()
    if not instruction:
        raise ValueError("frozen-plan instruction cannot be empty")
    guidance = {
        "role": "user",
        "content": "ASYNC_RBENCH_FROZEN_PLAN " + instruction,
    }
    return ConditionApplication(
        condition=condition,
        role="negative_control",
        leaderboard_eligible=False,
        target_delivery=delivery,
        participant_messages=(delivery_message, guidance),
        blocked_post_event_tools=FROZEN_BLOCKED_TOOLS,
    )


def audit_fixed_oracle_cards(root: Path) -> None:
    experiment = root / "experiments" / "drs-validity-v1"
    cohort = json.loads((experiment / "cohort.json").read_text(encoding="utf-8"))
    expected = {str(item["instance_key"]) for item in cohort["instances"]}
    loaded: set[str] = set()
    for path in sorted((experiment / "oracle-cards").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        instance_key = str(raw.get("instance_key") or "")
        fragments = collect_case_leakage_fragments(root, instance_key)
        card = load_oracle_card(path, forbidden_fragments=fragments)
        loaded.add(str(card["instance_key"]))
    if loaded != expected:
        missing = sorted(expected - loaded)
        extra = sorted(loaded - expected)
        raise ValueError(f"oracle card set mismatch: missing={missing}, extra={extra}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit DRS validity oracle cards")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    audit_fixed_oracle_cards(args.root.resolve())
    print("DRS validity oracle cards OK: 16 sealed cards, no evaluator leakage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
