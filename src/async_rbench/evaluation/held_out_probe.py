from __future__ import annotations

import argparse
import ast
import base64
import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Mapping


PROBE_BUNDLE_VERSION = "drs-held-out-probe-1.0"
PROBE_RESULT_VERSION = "drs-held-out-probe-result-1.0"
EXPERIMENT_RELATIVE = Path("experiments") / "drs-validity-v1"
_CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_FORBIDDEN_IMPORT_ROOTS = frozenset({"async_rbench"})
_FORBIDDEN_SCRIPT_NAMES = frozenset(
    {"condition", "model_id", "score_episode", "score_trace"}
)
_ALLOWED_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "instance_key",
        "script",
        "script_sha256",
        "criteria_type",
        "checks",
        "excluded_check_sets",
        "independence",
        "calibration_fixtures",
    }
)
_ALLOWED_CHECK_FIELDS = frozenset({"id", "kind", "contract", "inputs"})
_ALLOWED_CHECK_KINDS = frozenset({"behavior_contract"})
_EXCLUDED_SET_FIELDS = frozenset(
    {"role", "source", "source_sha256", "id_count", "ids_sha256"}
)
_EXPECTED_CONTRACTS = {
    "git-conflict-and-cleanup-closure": ("git.object_consumer", "downstream_consumer_read"),
    "mab-dependency-unblock-031ed6f5bc": ("data.idempotent_runtime", "idempotent_replay"),
    "mab-dependency-unblock-09f3ab60d7": ("macao.unseen_runtime", "unseen_input_variant"),
    "mab-dependency-unblock-720c69400a": ("price.second_order_runtime", "second_order_dependency_call"),
    "mab-late-constraint-88206c382b": ("negotiation.version_consumer", "updated_version_consumer"),
    "mab-late-test-evidence-7d09ace3d3": ("language.idempotent_runtime", "idempotent_replay"),
    "osw-cross-app-artifact-2a25ab8769": ("osw.mp3_metadata_consumer", "downstream_consumer_read"),
    "osw-cross-app-artifact-725ceaa05e": ("osw.pdf_render_consumer", "downstream_consumer_read"),
    "osw-cross-app-artifact-81b4557778": ("osw.extension_manifest_consumer", "downstream_consumer_read"),
    "osw-cross-app-artifact-c3093402e5": ("osw.audio_decoder_consumer", "downstream_consumer_read"),
    "scheduler-selective-replan": ("scheduler.reconsume", "preservation_of_unaffected_path"),
    "secure-release": ("release.revision_consumer", "updated_version_consumer"),
    "swe-dependency-unblock-3361c7af50": ("matplotlib.roundtrip_driver", "second_order_dependency_call"),
    "swe-dependency-unblock-3f6d310987": ("sympy.unseen_driver", "unseen_input_variant"),
    "swe-late-constraint-acaa77b306": ("zstd.stable_buffer_driver", "unseen_input_variant"),
    "tbn-late-test-evidence-9685a54f22": ("tbn.reconsume", "resource_pressure_downstream_read"),
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _discover_root(bundle_path: Path) -> Path:
    resolved = bundle_path.resolve()
    for parent in resolved.parents:
        if (parent / "experiments" / "drs-validity-v1" / "cohort.json").is_file():
            return parent
    raise ValueError(f"could not discover repository root from {bundle_path}")


def _instrument_name(instance_key: str) -> str:
    case_id, separator, instance_id = instance_key.partition("::")
    if not separator or not case_id or not instance_id:
        raise ValueError(f"invalid instance key {instance_key!r}")
    return f"{case_id}--{instance_id}.json"


def _safe_bundle_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe probe bundle path {value!r}")
    return path


def _safe_workspace_path(root: Path, logical_path: str) -> Path:
    logical = PurePosixPath(logical_path)
    if ".." in logical.parts or not logical.parts:
        raise ValueError(f"unsafe probe workspace path {logical_path!r}")
    parts = list(logical.parts)
    if parts and parts[0] == "/":
        parts = parts[1:]
    elif logical.is_absolute():
        parts = parts[1:]
    target = root.joinpath(*parts).resolve()
    workspace_root = root.resolve()
    if target != workspace_root and workspace_root not in target.parents:
        raise ValueError(f"probe fixture escapes workspace: {logical_path!r}")
    return target


def _ids_from_check_source(path: Path) -> list[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return sorted(
        str(item["id"])
        for item in value.get("checks", [])
        if isinstance(item, Mapping) and item.get("id")
    )


def _audit_probe_script(source: str) -> None:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        roots: list[str] = []
        if isinstance(node, ast.Import):
            roots = [item.name.partition(".")[0] for item in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots = [node.module.partition(".")[0]]
        if _FORBIDDEN_IMPORT_ROOTS.intersection(roots):
            raise ValueError("probe script imports the benchmark scorer")
        if isinstance(node, ast.Name) and node.id.casefold() in _FORBIDDEN_SCRIPT_NAMES:
            raise ValueError("probe script references scorer or treatment data")


@dataclass(frozen=True)
class HeldOutProbeBundle:
    repository_root: Path
    path: Path
    manifest: dict[str, Any]
    script_path: Path
    script_source: str
    script_sha256: str
    bundle_sha256: str

    @property
    def instance_key(self) -> str:
        return str(self.manifest["instance_key"])


@dataclass(frozen=True)
class HeldOutProbeResult:
    instance_key: str
    held_out_probe_pass: bool
    held_out_probe_fraction: float
    evidence: tuple[dict[str, Any], ...]
    probe_bundle_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROBE_RESULT_VERSION,
            "instance_key": self.instance_key,
            "held_out_probe_pass": self.held_out_probe_pass,
            "held_out_probe_fraction": self.held_out_probe_fraction,
            "evidence": [copy.deepcopy(item) for item in self.evidence],
            "probe_bundle_sha256": self.probe_bundle_sha256,
        }


def load_probe_bundle(path: Path, *, root: Path | None = None) -> HeldOutProbeBundle:
    path = path.resolve()
    repository_root = (root or _discover_root(path)).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"{path} must contain a probe manifest object")
    unknown = sorted(set(manifest) - _ALLOWED_MANIFEST_FIELDS)
    missing = sorted(_ALLOWED_MANIFEST_FIELDS - set(manifest))
    if unknown or missing:
        raise ValueError(f"invalid probe manifest fields: unknown={unknown}, missing={missing}")
    if manifest.get("schema_version") != PROBE_BUNDLE_VERSION:
        raise ValueError(f"probe schema_version must be {PROBE_BUNDLE_VERSION}")
    instance_key = str(manifest.get("instance_key") or "")
    if path.name != _instrument_name(instance_key):
        raise ValueError("probe filename does not match instance_key")
    case_id = instance_key.split("::", 1)[0]
    if case_id not in _EXPECTED_CONTRACTS:
        raise ValueError(f"no fixed held-out contract for {case_id!r}")
    expected_contract, expected_criteria = _EXPECTED_CONTRACTS[case_id]
    if manifest.get("criteria_type") != expected_criteria:
        raise ValueError("probe criteria_type does not match the fixed case contract")

    script_relative = _safe_bundle_relative(str(manifest.get("script") or ""))
    script_path = path.parent.joinpath(*script_relative.parts).resolve()
    if path.parent.resolve() not in script_path.parents:
        raise ValueError("probe script escapes bundle directory")
    script_source = script_path.read_text(encoding="utf-8")
    script_sha256 = _file_sha256(script_path)
    if script_sha256 != str(manifest.get("script_sha256") or ""):
        raise ValueError("probe script digest mismatch")
    _audit_probe_script(script_source)

    checks = list(manifest.get("checks") or [])
    if not checks:
        raise ValueError("probe bundle must declare at least one downstream check")
    probe_ids: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError("probe checks must be objects")
        unknown_check = sorted(set(check) - _ALLOWED_CHECK_FIELDS)
        if unknown_check:
            raise ValueError(f"unknown probe check fields: {unknown_check}")
        check_id = str(check.get("id") or "")
        if not check_id:
            raise ValueError("probe check id cannot be empty")
        probe_ids.append(check_id)
        if check.get("kind") not in _ALLOWED_CHECK_KINDS:
            raise ValueError(f"unsupported probe check kind {check.get('kind')!r}")
        kind = str(check["kind"])
        required = {"id", "kind", "contract", "inputs"}
        allowed = set(required)
        missing_check = sorted(required - set(check))
        extra_check = sorted(set(check) - allowed)
        if missing_check:
            raise ValueError(f"{kind} is missing required fields: {missing_check}")
        if extra_check:
            raise ValueError(f"{kind} has inapplicable fields: {extra_check}")
        if not str(check.get("contract") or "").strip():
            raise ValueError("behavior_contract requires a non-empty contract")
        if check.get("contract") != expected_contract:
            raise ValueError("probe behavior contract does not match the fixed case contract")
        inputs = check.get("inputs")
        if not isinstance(inputs, Mapping) or not inputs:
            raise ValueError("behavior_contract inputs must be a non-empty object")
        for logical_path in inputs.values():
            if not isinstance(logical_path, str):
                raise ValueError("behavior_contract input paths must be strings")
            _safe_workspace_path(Path.cwd(), logical_path)
    if len(probe_ids) != len(set(probe_ids)):
        raise ValueError("duplicate held-out probe check id")

    excluded_ids: set[str] = set()
    excluded_sets = list(manifest.get("excluded_check_sets") or [])
    if len(excluded_sets) != 2:
        raise ValueError("probe must pin the DRS and Outcome excluded check sets")
    expected_sources = {
        "drs_process": (
            f"data/async-rbench/cases/{case_id}/evaluator/control_flow_checks.json"
        ),
        "outcome": f"data/async-rbench/cases/{case_id}/evaluator/semantic_checks.json",
    }
    roles = [str(item.get("role") or "") for item in excluded_sets]
    if set(roles) != set(expected_sources) or len(roles) != len(set(roles)):
        raise ValueError("excluded check roles must be exactly drs_process and outcome")
    for item in excluded_sets:
        if not isinstance(item, Mapping):
            raise ValueError("excluded check set must be an object")
        if set(item) != _EXCLUDED_SET_FIELDS:
            raise ValueError("excluded check set has invalid fields")
        role = str(item["role"])
        if str(item.get("source") or "").replace("\\", "/") != expected_sources[role]:
            raise ValueError(f"excluded check role {role!r} does not use canonical source")
        source = repository_root / str(item.get("source") or "")
        if _file_sha256(source) != str(item.get("source_sha256") or ""):
            raise ValueError(f"excluded check source digest mismatch: {source}")
        ids = _ids_from_check_source(source)
        if len(ids) != int(item.get("id_count", -1)):
            raise ValueError(f"excluded check id count mismatch: {source}")
        if _sha256_bytes(_canonical_json(ids)) != str(item.get("ids_sha256") or ""):
            raise ValueError(f"excluded check id digest mismatch: {source}")
        excluded_ids.update(ids)
    overlap = sorted(set(probe_ids) & excluded_ids)
    if overlap:
        raise ValueError("held-out probe ids overlap scored checks: " + ", ".join(overlap))

    independence = manifest.get("independence")
    if not isinstance(independence, Mapping):
        raise ValueError("probe independence declaration is required")
    if not str(independence.get("evidence_source") or "").strip():
        raise ValueError("probe independence evidence_source is required")
    if not str(independence.get("why_independent") or "").strip():
        raise ValueError("probe independence why_independent is required")
    fixtures = manifest.get("calibration_fixtures")
    if not isinstance(fixtures, Mapping) or set(fixtures) != {
        "oracle_reference", "frozen_plan_reference"
    }:
        raise ValueError("probe must declare oracle and frozen-plan calibration fixtures")

    bundle_sha256 = _sha256_bytes(
        _canonical_json(
            {
                "manifest": manifest,
                "scripts": {str(script_relative): script_sha256},
            }
        )
    )
    return HeldOutProbeBundle(
        repository_root=repository_root,
        path=path,
        manifest=manifest,
        script_path=script_path,
        script_source=script_source,
        script_sha256=script_sha256,
        bundle_sha256=bundle_sha256,
    )


def materialize_calibration_fixture(
    bundle: HeldOutProbeBundle,
    workspace_root: Path,
    fixture_name: str,
) -> None:
    fixtures = dict(bundle.manifest["calibration_fixtures"])
    if fixture_name not in fixtures:
        raise ValueError(f"unknown calibration fixture {fixture_name!r}")
    fixture = fixtures[fixture_name]
    allowed_fixture_fields = {"basis", "files", "copies", "replacements", "basis_sources"}
    if not isinstance(fixture, Mapping) or not {"basis", "files", "basis_sources"}.issubset(fixture) or set(fixture) - allowed_fixture_fields:
        raise ValueError(f"invalid calibration fixture {fixture_name!r}")
    expected_basis = {
        "oracle_reference": "oracle_reference",
        "frozen_plan_reference": "frozen_plan_reference",
    }[fixture_name]
    if fixture.get("basis") != expected_basis:
        raise ValueError(f"fixture {fixture_name!r} has the wrong basis")
    basis_sources = fixture.get("basis_sources")
    if not isinstance(basis_sources, list) or not basis_sources:
        raise ValueError(f"fixture {fixture_name!r} must bind repository basis sources")
    for source in basis_sources:
        if not isinstance(source, Mapping) or set(source) != {"role", "path", "sha256"}:
            raise ValueError("invalid calibration basis source")
        relative = _safe_bundle_relative(str(source["path"]))
        source_path = bundle.repository_root.joinpath(*relative.parts)
        if _file_sha256(source_path) != str(source["sha256"]):
            raise ValueError(f"calibration basis source digest mismatch: {source_path}")
    workspace_root.mkdir(parents=True, exist_ok=True)
    copied: dict[str, Path] = {}
    for logical_path, source_relative in dict(fixture.get("copies") or {}).items():
        relative = _safe_bundle_relative(str(source_relative))
        source = bundle.repository_root.joinpath(*relative.parts)
        target = _safe_workspace_path(workspace_root, str(logical_path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        copied[str(logical_path)] = target
    for logical_path, replacements in dict(fixture.get("replacements") or {}).items():
        target = copied.get(str(logical_path))
        if target is None or not isinstance(replacements, list):
            raise ValueError("fixture replacements require a copied text file")
        text = target.read_text(encoding="utf-8")
        for replacement in replacements:
            if not isinstance(replacement, Mapping) or set(replacement) != {"old", "new"}:
                raise ValueError("invalid fixture replacement")
            old = str(replacement["old"])
            if old not in text:
                raise ValueError(f"fixture replacement source not found in {logical_path}")
            text = text.replace(old, str(replacement["new"]), 1)
        target.write_text(text, encoding="utf-8")
    for logical_path, content in dict(fixture["files"]).items():
        target = _safe_workspace_path(workspace_root, str(logical_path))
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            target.write_text(
                json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        elif isinstance(content, str):
            target.write_text(content, encoding="utf-8")
        else:
            raise ValueError(f"unsupported fixture content for {logical_path!r}")


def _parse_probe_output(
    completed: subprocess.CompletedProcess[str],
    bundle: HeldOutProbeBundle,
) -> HeldOutProbeResult:
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "probe failed")[-2000:]
        raise RuntimeError(f"held-out probe runner failed: {detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("held-out probe returned invalid JSON") from exc
    allowed = {
        "schema_version", "instance_key", "held_out_probe_pass",
        "held_out_probe_fraction", "evidence",
    }
    if not isinstance(value, dict) or set(value) != allowed:
        raise ValueError("held-out probe result has invalid fields")
    if value.get("schema_version") != PROBE_RESULT_VERSION:
        raise ValueError("held-out probe result schema_version mismatch")
    if value.get("instance_key") != bundle.instance_key:
        raise ValueError("held-out probe result instance_key mismatch")
    passed = value.get("held_out_probe_pass")
    if type(passed) is not bool:
        raise ValueError("held_out_probe_pass must be a strict boolean")
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("held-out probe evidence must be a non-empty list")
    expected_ids = [str(item["id"]) for item in bundle.manifest["checks"]]
    actual_ids: list[str] = []
    passed_count = 0
    normalized_evidence: list[dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"id", "passed", "evidence"}:
            raise ValueError("held-out probe evidence item has invalid fields")
        if type(item.get("passed")) is not bool:
            raise ValueError("held-out probe evidence passed must be a strict boolean")
        actual_ids.append(str(item["id"]))
        passed_count += int(item["passed"])
        normalized_evidence.append(copy.deepcopy(item))
    if actual_ids != expected_ids:
        raise ValueError("held-out probe evidence ids do not match manifest order")
    expected_fraction = passed_count / len(evidence)
    fraction = value.get("held_out_probe_fraction")
    if type(fraction) not in {int, float} or float(fraction) != expected_fraction:
        raise ValueError("held_out_probe_fraction does not match evidence")
    if passed != (passed_count == len(evidence)):
        raise ValueError("held_out_probe_pass does not match evidence")
    return HeldOutProbeResult(
        instance_key=bundle.instance_key,
        held_out_probe_pass=passed,
        held_out_probe_fraction=float(fraction),
        evidence=tuple(normalized_evidence),
        probe_bundle_sha256=bundle.bundle_sha256,
    )


def run_held_out_probe(
    workspace_container: str,
    probe_bundle: Path,
    *,
    timeout_sec: int,
) -> HeldOutProbeResult:
    """Run one private probe without exposing treatment or model metadata."""
    if timeout_sec <= 0:
        raise ValueError("timeout_sec must be positive")
    bundle = load_probe_bundle(probe_bundle)
    spec = {
        "schema_version": PROBE_BUNDLE_VERSION,
        "instance_key": bundle.instance_key,
        "checks": bundle.manifest["checks"],
    }
    encoded_spec = base64.b64encode(_canonical_json(spec)).decode("ascii")
    if workspace_container.startswith("local://"):
        workspace_root = Path(workspace_container.removeprefix("local://")).resolve()
        environment = {
            "ASYNC_RBENCH_PROBE_SPEC_B64": encoded_spec,
            "ASYNC_RBENCH_PROBE_ROOT": str(workspace_root),
            "PYTHONIOENCODING": "utf-8",
        }
        if os.name == "nt" and os.environ.get("SystemRoot"):
            environment["SystemRoot"] = os.environ["SystemRoot"]
        completed = subprocess.run(
            [sys.executable, "-I", "-"],
            input=bundle.script_source,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            cwd=workspace_root,
            env=environment,
            check=False,
        )
    else:
        if not _CONTAINER_NAME.fullmatch(workspace_container):
            raise ValueError("invalid workspace container name")
        completed = subprocess.run(
            [
                "docker", "exec", "-i", workspace_container,
                "env", "-i",
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG=C.UTF-8",
                f"ASYNC_RBENCH_PROBE_SPEC_B64={encoded_spec}",
                "ASYNC_RBENCH_PROBE_ROOT=/",
                "python3", "-I", "-",
            ],
            input=bundle.script_source,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    return _parse_probe_output(completed, bundle)


def audit_fixed_probe_bundles(root: Path) -> None:
    root = root.resolve()
    experiment = root / EXPERIMENT_RELATIVE
    cohort = json.loads((experiment / "cohort.json").read_text(encoding="utf-8"))
    expected = {str(item["instance_key"]) for item in cohort["instances"]}
    loaded: dict[str, HeldOutProbeBundle] = {}
    all_probe_ids: set[str] = set()
    for instance_key in sorted(expected):
        bundle = load_probe_bundle(
            experiment / "held-out-probes" / _instrument_name(instance_key),
            root=root,
        )
        probe_ids = {str(item["id"]) for item in bundle.manifest["checks"]}
        overlap = sorted(probe_ids & all_probe_ids)
        if overlap:
            raise ValueError("probe ids reused across cases: " + ", ".join(overlap))
        all_probe_ids.update(probe_ids)
        loaded[instance_key] = bundle
    actual_files = {
        item.name for item in (experiment / "held-out-probes").glob("*.json")
    }
    expected_files = {_instrument_name(item) for item in expected}
    if actual_files != expected_files or set(loaded) != expected:
        raise ValueError("held-out probe bundle set does not match frozen cohort")

    for instance_key, bundle in loaded.items():
        card = experiment / "oracle-cards" / _instrument_name(instance_key)
        card_text = card.read_text(encoding="utf-8").casefold()
        hidden = [
            *(str(item["id"]) for item in bundle.manifest["checks"]),
            *(
                path
                for item in bundle.manifest["checks"]
                for path in item["inputs"].values()
            ),
            *(str(item["contract"]) for item in bundle.manifest["checks"]),
            str(bundle.manifest["script"]),
        ]
        leaked = [item for item in hidden if item.casefold() in card_text]
        if leaked:
            raise ValueError(f"oracle card leaks held-out probe internals: {leaked}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit DRS validity held-out probes")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    audit_fixed_probe_bundles(args.root)
    print("DRS held-out probes structurally OK: 16 digest-bound bundles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
