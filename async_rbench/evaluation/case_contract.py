from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .event_taxonomy import (
    ASYNC_SCENARIO_CLASSES,
    EVENT_THEME_IDS,
    validate_case_classification,
)


EXECUTION_MODES = ("linear", "async")
# Fixed harness resource ceiling for benchmark-owned initial work. Recovery
# children use the participant profile's separate concurrency budget.
MAX_INITIAL_WORKSTREAMS = 8

CAPABILITY_CATEGORIES = frozenset({
    "late_revision_adoption",
    "stale_result_rejection",
    "inflight_cancellation",
    "selective_invalidation",
    "cascading_replan",
    "verification_reopen",
    "failure_redelegation",
    "conflict_arbitration",
})

PUBLIC_RESULT_REJECTION_CODES = frozenset({
    "payload_not_object",
    "evidence_not_object",
    "missing_required_evidence",
    "files_not_string_list",
    "duplicate_files",
    "unexpected_files",
    "missing_required_files",
})


class ContractError(ValueError):
    """Raised when public and private benchmark data cross their boundary."""


@dataclass(frozen=True)
class PublicWorkstream:
    id: str
    task: str
    targets: tuple[str, ...]
    expected_output: str
    priority: str = "normal"
    required_evidence_fields: tuple[str, ...] = ()
    evidence_schema: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    allowed_files: tuple[str, ...] = ()
    required_files: tuple[str, ...] = ()
    public_result_contract: Mapping[str, Any] = field(default_factory=dict)

    def as_message(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "targets": list(self.targets),
            "expected_output": self.expected_output,
            "priority": self.priority,
            "required_evidence_fields": list(self.required_evidence_fields),
            "evidence_schema": {
                name: dict(spec) for name, spec in self.evidence_schema.items()
            },
            "allowed_files": list(self.allowed_files),
            "required_files": list(self.required_files),
            "public_result_contract": dict(self.public_result_contract),
        }


@dataclass(frozen=True)
class PublicCaseContract:
    format_version: int
    case_id: str
    title: str
    instruction: str
    workstreams: tuple[PublicWorkstream, ...]
    artifacts: tuple[str, ...]
    public_checks: tuple[str, ...] = ()

    def as_episode_start(self) -> dict[str, Any]:
        return {
            "contract_version": self.format_version,
            "case_id": self.case_id,
            "instruction": self.instruction,
            "workstreams": [item.as_message() for item in self.workstreams],
            "artifacts": list(self.artifacts),
            "public_checks": list(self.public_checks),
        }


@dataclass(frozen=True)
class PrivateCaseContract:
    format_version: int
    case_id: str
    capabilities: frozenset[str]
    workstream_bindings: Mapping[str, Mapping[str, Any]]
    scenarios: Mapping[str, Mapping[str, Any]]
    classification: Mapping[str, Any] = field(default_factory=dict)
    dependency_graph: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    hidden_checks: Mapping[str, str] = field(default_factory=dict)
    information_sufficiency: tuple[Mapping[str, Any], ...] = ()

    def validate(self) -> list[str]:
        errors: list[str] = []
        unknown = set(self.capabilities) - CAPABILITY_CATEGORIES
        if unknown:
            errors.append(f"unknown capability categories: {sorted(unknown)}")
        modes = set(self.scenarios)
        if modes != set(EXECUTION_MODES):
            errors.append(
                "private scenarios must define exactly linear and async; "
                f"observed={sorted(modes)}"
            )
        errors.extend(validate_case_classification(self.classification))
        return errors


# Fields whose mere presence discloses evaluator-owned control truth.  These
# names are forbidden recursively on every model-visible protocol object.
PRIVATE_FIELD_NAMES = frozenset({
    "condition",
    "authoritative_result_kind",
    "superseded_result_kind",
    "workstream_result_kinds",
    "allowed_result_kinds",
    "result_tagging_rule",
    "reverification_commands",
    "validator_command",
    "benchmark_event_id",
    "controlled_order",
    "stale",
    "stale_visibility",
    "evaluator_stale",
    "evaluator_stale_measurable",
    "evaluator_stale_reason",
    "invalidates_artifacts",
    "reopens_milestones",
    "capabilities",
    "classification",
    "primary_event_theme",
    "secondary_event_themes",
    "async_scenario_class",
    "event_theme",
    "source_evidence",
    "replayed",
    "replay_of_completion_id",
    "scoring_gates",
    "dependency_graph",
})


def find_private_fields(value: Any, path: str = "$") -> list[str]:
    """Return paths of evaluator-private keys in a participant-visible value."""
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key) in PRIVATE_FIELD_NAMES:
                hits.append(child_path)
            hits.extend(find_private_fields(child, child_path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            hits.extend(find_private_fields(child, f"{path}[{index}]"))
    return hits


def assert_participant_safe(value: Any, *, surface: str) -> None:
    hits = find_private_fields(value)
    if hits:
        raise ContractError(
            f"{surface} exposes evaluator-private fields: {', '.join(hits)}"
        )


def public_delivery(
    delivery: Mapping[str, Any], *, workstream_id: str | None = None,
) -> dict[str, Any]:
    """Construct the only result-delivery shape that may reach a model."""
    result = {
        "type": "result_delivered",
        "child_id": str(delivery.get("child_id", "")),
        "completion_id": str(delivery.get("completion_id", "")),
        "workstream_id": workstream_id,
        "payload": delivery.get("payload"),
        "payload_sha256": str(delivery.get("payload_sha256", "")),
    }
    assert_participant_safe(result, surface="public delivery")
    return result


def public_rejection(
    rejection: Mapping[str, Any], *, workstream_id: str | None = None,
) -> dict[str, Any]:
    """Project a result-contract rejection without exposing semantic roles."""
    private_codes = [str(item) for item in rejection.get("reason_codes") or []]
    reason_codes = [code for code in private_codes if code in PUBLIC_RESULT_REJECTION_CODES]
    if any(code not in PUBLIC_RESULT_REJECTION_CODES for code in private_codes):
        reason_codes.append("result_contract_rejected")
    result = {
        "type": "result_rejected",
        "child_id": str(rejection.get("child_id", "")),
        "completion_id": str(rejection.get("completion_id", "")),
        "workstream_id": workstream_id,
        "reason_codes": reason_codes,
    }
    assert_participant_safe(result, surface="public rejection")
    return result
