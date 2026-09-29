from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .evaluation.case_contract import assert_participant_safe
from .evaluation.public_result_validation import validate_public_contract_definition
from .evaluation.report_contract import render_validator_command
from .public_spec import PublicCaseSpec


CASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class JudgeCaseSpec:
    path: Path
    raw: dict[str, Any]
    verifier_dir: Path

    @property
    def case_id(self) -> str:
        return str(self.raw["case_id"])

    @property
    def case_dir(self) -> Path:
        return self.path.parent.parent


@dataclass(frozen=True)
class JudgeBundleProvider:
    root: Path
    expected_public_release_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve())

    @staticmethod
    def _validate_case_id(case_id: str) -> str:
        if not CASE_ID_RE.fullmatch(case_id):
            raise ValueError(f"invalid case_id for judge bundle lookup: {case_id!r}")
        return case_id

    def case_root(self, case_id: str, instance_id: str = "seed-1") -> Path:
        case_root = self.root / "cases" / self._validate_case_id(case_id)
        if instance_id != "seed-1":
            self._validate_case_id(instance_id)
            instance_root = case_root / "instances" / instance_id
            if instance_root.exists():
                return instance_root
        return case_root

    def evaluator_dir(self, case_id: str, instance_id: str = "seed-1") -> Path:
        return self.case_root(case_id, instance_id) / "evaluator"

    def verifier_dir(self, case_id: str, instance_id: str = "seed-1") -> Path:
        case_root = self.case_root(case_id, instance_id)
        if (case_root / "tests").is_dir() or (case_root / "run-tests.sh").is_file():
            return case_root
        # Explicit migration compatibility for the pre-split repository. This
        # never searches outside the supplied provider root and disappears
        # naturally once the private bundle is copied to its final layout.
        legacy = case_root / "task"
        if (legacy / "tests").is_dir() or (legacy / "run-tests.sh").is_file():
            return legacy
        return case_root

    def validate_release_binding(self) -> None:
        if self.expected_public_release_sha256 is None:
            return
        release_path = self.root / "release.json"
        if not release_path.is_file():
            raise FileNotFoundError(
                f"judge bundle release binding is missing: {release_path}"
            )
        payload = json.loads(release_path.read_text(encoding="utf-8"))
        actual = str(payload.get("public_release_sha256") or "")
        if actual != self.expected_public_release_sha256:
            raise ValueError(
                "public release digest mismatch: "
                f"expected {self.expected_public_release_sha256}, got {actual or '<missing>'}"
            )


def load_judge_case(
    public: PublicCaseSpec,
    provider: JudgeBundleProvider,
) -> JudgeCaseSpec:
    provider.validate_release_binding()
    case_root = provider.case_root(public.case_id)
    evaluator_dir = provider.evaluator_dir(public.case_id)
    contract_path = evaluator_dir / "case.yaml"
    if not contract_path.is_file():
        raise FileNotFoundError(
            f"missing private judge case {public.case_id!r} under provider {provider.root}: "
            f"{contract_path}"
        )

    verifier_dir = provider.verifier_dir(public.case_id)
    if not (verifier_dir / "tests").is_dir() or not (verifier_dir / "run-tests.sh").is_file():
        raise FileNotFoundError(
            f"missing private verifier bundle for case {public.case_id!r}: {verifier_dir}"
        )

    raw = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"private judge case contract must be a mapping: {contract_path}")
    if str(raw.get("case_id") or "") != public.case_id:
        raise ValueError(
            "public/private case_id mismatch: "
            f"public={public.case_id!r}, private={raw.get('case_id')!r}"
        )
    return JudgeCaseSpec(path=contract_path, raw=raw, verifier_dir=verifier_dir)


def _load_evaluator_injections(judge: JudgeCaseSpec) -> list[dict[str, Any]]:
    evaluator_root = judge.path.parent.resolve()
    injections: list[dict[str, Any]] = []
    for index, configured in enumerate(judge.raw.get("evaluator_injections") or []):
        if not isinstance(configured, dict):
            raise ValueError(
                f"evaluator_injections[{index}] must be a mapping: {judge.path}"
            )
        receipt_ref = str(configured.get("receipt_path") or "")
        receipt_path = (judge.case_dir / receipt_ref).resolve()
        try:
            receipt_path.relative_to(evaluator_root)
        except ValueError as exc:
            raise ValueError(
                f"evaluator_injections[{index}].receipt_path must remain under evaluator/: "
                f"{judge.path}"
            ) from exc
        if receipt_path.suffix.lower() != ".json" or not receipt_path.is_file():
            raise FileNotFoundError(
                "missing private evaluator receipt for injection "
                f"{configured.get('id')!r}: {receipt_path}"
            )
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert_participant_safe(
            payload,
            surface=f"evaluator injection {configured.get('id')!r}",
        )
        injections.append({
            "id": str(configured.get("id") or ""),
            "result_kind": str(configured.get("result_kind") or ""),
            "payload": payload,
        })
    return injections


def compose_runtime_case(
    public: PublicCaseSpec,
    judge: JudgeCaseSpec,
) -> dict[str, Any]:
    if public.case_id != judge.case_id:
        raise ValueError(
            "public/private case_id mismatch: "
            f"public={public.case_id!r}, private={judge.case_id!r}"
        )

    private = judge.raw
    bindings = dict(private.get("workstream_bindings") or {})
    workstreams: list[dict[str, Any]] = []
    initial_wave: list[dict[str, Any]] = []
    event_assets: dict[str, Any] = {}
    for item in public.raw.get("workstreams") or []:
        stream_id = str(item["id"])
        binding = dict(bindings.get(stream_id) or {})
        if "validator_stage" not in binding:
            raise ValueError(
                f"{judge.path}: workstream {stream_id!r}: validator_stage is required"
            )
        validator_stage = str(binding.get("validator_stage") or "")
        if validator_stage not in {"submission_contract", "semantic_evidence"}:
            raise ValueError(
                f"{judge.path}: workstream {stream_id!r}: unsupported validator_stage "
                f"{validator_stage!r}"
            )
        workstream = {
            "id": stream_id,
            "result_kind": binding.get("result_kind", stream_id),
            "required_evidence_fields": list(item.get("required_evidence_fields") or []),
            "evidence_schema": dict(binding.get("private_evidence_schema") or {}),
            "public_evidence_schema": dict(item.get("evidence_schema") or {}),
            "allowed_files": list(item.get("allowed_files") or []),
            "required_files": list(item.get("required_files") or []),
            "public_result_contract": dict(item.get("public_result_contract") or {}),
            "validator_command": str(binding.get("validator_command") or "true"),
            "validator_timeout_sec": int(binding.get("validator_timeout_sec") or 120),
            "validator_stage": validator_stage,
        }
        definition_errors = validate_public_contract_definition(workstream)
        if definition_errors:
            raise ValueError(
                f"{public.path}: workstream {stream_id!r}: " + "; ".join(definition_errors)
            )
        public_kind = workstream["public_result_contract"].get("kind")
        if validator_stage == "submission_contract":
            if public_kind != "report_file":
                raise ValueError(
                    f"{judge.path}: workstream {stream_id!r}: submission_contract "
                    "requires public_result_contract.kind=report_file"
                )
            required_files = workstream["required_files"]
            if not required_files:
                raise ValueError(
                    f"{public.path}: workstream {stream_id!r}: report_file requires a file"
                )
            expected_command = render_validator_command(
                workstream["public_result_contract"], required_files[0]
            )
            if workstream["validator_command"] != expected_command:
                raise ValueError(
                    f"{judge.path}: workstream {stream_id!r}: submission_contract "
                    "validator_command must equal the deterministic public render"
                )
        elif public_kind != "payload_only":
            raise ValueError(
                f"{judge.path}: workstream {stream_id!r}: semantic_evidence "
                "requires public_result_contract.kind=payload_only"
            )
        workstreams.append(workstream)
        initial_wave.append({
            "workstream_id": stream_id,
            "result_kind": binding.get("result_kind", stream_id),
            "task": str(item.get("task") or ""),
            "targets": list(item.get("targets") or []),
            "expected_output": str(item.get("expected_output") or ""),
            "priority": str(item.get("priority") or "normal"),
            "required_evidence_fields": list(item.get("required_evidence_fields") or []),
        })
        if binding.get("event_assets"):
            event_assets[stream_id] = binding["event_assets"]

    observers = dict(private.get("artifact_observers") or {})
    artifacts = []
    for item in public.raw.get("artifacts") or []:
        artifact = dict(item)
        if item.get("id") in observers:
            artifact["observer_command"] = observers[item["id"]]
        artifacts.append(artifact)

    legacy_metadata = dict(private.get("legacy_metadata") or {})
    return {
        "format_version": int(public.raw.get("format_version") or 2),
        "case_id": public.case_id,
        "title": public.raw.get("title", public.case_id),
        "source_tasks": public.raw.get("source_tasks", []),
        "milestones": public.raw.get("milestones", []),
        "artifacts": artifacts,
        "delegation_workstreams": workstreams,
        "initial_wave": initial_wave,
        "event_assets": event_assets,
        "evaluator_injections": _load_evaluator_injections(judge),
        "result_contract": private.get("result_contract", {}),
        "authoritative_result_kind": private.get("authoritative_result_kind"),
        "superseded_result_kind": private.get("superseded_result_kind"),
        "variants": dict(private.get("legacy_variants") or {}),
        "scenarios": dict(private.get("scenarios") or {}),
        "capabilities": list(private.get("capabilities") or []),
        "classification": dict(private.get("classification") or {}),
        "information_sufficiency": list(private.get("information_sufficiency") or []),
        "reverification_checks": list(public.raw.get("public_checks") or []),
        "reverification_commands": {},
        "hidden_reverification_commands": dict(private.get("hidden_checks") or {}),
        "reverification_anchors": private.get("reverification_anchors", {}),
        "stale_predicate": private.get("stale_predicate"),
        "stale_revalidation": private.get("stale_revalidation", {}),
        "metrics": legacy_metadata.get("metrics", {}),
        "implementation": legacy_metadata.get("implementation", {}),
        "upstream_commit": legacy_metadata.get("upstream_commit"),
        "asset_copies": legacy_metadata.get("asset_copies", []),
        "instruction": public.raw.get("instruction", ""),
        "difficulty": public.raw.get("difficulty", ""),
    }
