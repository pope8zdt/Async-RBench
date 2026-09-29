"""Fail-closed OSWorld runtime qualification helpers.

The upstream OSWorld ``DesktopEnv`` is the authority for real GUI episodes.
This module deliberately does not emulate a desktop.  It provides a small,
dependency-free control-plane environment which can exercise task loading,
reset semantics, action-history state changes, and OSWorld's terminal ``FAIL``
evaluation branch for every source-native OSWorld case.

Anything which needs a screenshot, pyautogui execution, a VM getter, or a gold
metric raises :class:`RealVMRequiredError`.  Consequently an environment-smoke
qualification produced here is useful infrastructure evidence, but is never
evidence that a real VM, model episode, task setup, or gold evaluator ran.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from async_rbench.native_runtime_registry import (
    ENVIRONMENT_SMOKE_READY_STATUS,
    OSWORLD_SMOKE_PROFILE,
)
from async_rbench.source_native_v4 import NativeEventBroker, canonical_hash, file_hash


LOCAL_ADAPTER = "async_rbench.osworld_runtime.LocalOSWorldEnvironment"
LOCAL_RUNTIME_SCHEMA = "osworld-local-control-plane-v1"
QUALIFICATION_SCHEMA = "source-native-runtime-qualification-v2"
SPECIAL_ACTIONS = frozenset({"WAIT", "FAIL", "DONE"})
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
OFFICIAL_OSWORLD_QCOW2_SIZE = 24_460_197_888
OFFICIAL_OSWORLD_QCOW2_SHA256 = "6bf667a852b3c307f61d9f09c42559351f45e0607e428b4997becf534cf4d313"
OFFICIAL_OSWORLD_DOCKER_IMAGE = (
    "happysixd/osworld-docker@"
    "sha256:0e6497a9295647cf05bf2b2af522fdd79bdeba2737595259cab310a3bcf6baa9"
)
OFFICIAL_OSWORLD_DOCKER_IMAGE_ID = (
    "sha256:0e6497a9295647cf05bf2b2af522fdd79bdeba2737595259cab310a3bcf6baa9"
)


def osworld_provider_lock_path(vm_path: Path) -> Path:
    """Return the canonical cross-output lock for one resolved VM disk."""

    resolved = vm_path.resolve()
    identity = os.path.normcase(str(resolved)).encode("utf-8")
    suffix = hashlib.sha256(identity).hexdigest()[:16]
    return resolved.parent / f".{resolved.name}.{suffix}.provider.lock"


class OSWorldRuntimeError(RuntimeError):
    """Base error for the local OSWorld qualification runtime."""


class OSWorldCaseError(OSWorldRuntimeError):
    """The source-native case is not safely bound to an official task."""


class RealVMRequiredError(OSWorldRuntimeError):
    """The requested operation requires the upstream OSWorld VM."""


class RuntimePhase(str, Enum):
    STOPPED = "stopped"
    STARTED = "started"
    READY = "ready"
    TERMINAL = "terminal"
    CLOSED = "closed"


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise OSWorldCaseError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise OSWorldCaseError(f"manifest line {line_number} is not an object")
        rows.append(value)
    return rows


def _resolve_within(base: Path, relative: str, *, label: str) -> Path:
    base = base.resolve()
    target = (base / relative).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise OSWorldCaseError(f"{label} escapes {base}") from exc
    return target


def _exported_names(path: Path) -> frozenset[str]:
    """Read imported/defined public symbols without importing heavy deps."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            for imported in node.names:
                names.add(imported.asname or imported.name)
        elif isinstance(node, ast.Import):
            for imported in node.names:
                names.add(imported.asname or imported.name.split(".")[0])
    return frozenset(names)


def _setup_handlers(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "SetupController":
            return frozenset(
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name.startswith("_")
                and child.name.endswith("_setup")
            )
    raise OSWorldCaseError("upstream SetupController definition is missing")


@dataclass(frozen=True)
class DispatchResolution:
    metric_functions: tuple[str, ...]
    result_getters: tuple[str, ...]
    expected_getters: tuple[str, ...]
    setup_handlers: tuple[str, ...]
    evaluator_sha256: str


class OSWorldDispatchCatalog:
    """Static binding to the pinned upstream dispatch tables.

    Static resolution is intentional: importing upstream's monolithic metric
    package requires the full GUI/evaluator dependency set.  Real provider
    import and launch are checked separately by :func:`probe_real_vm_provider`.
    """

    def __init__(self, upstream_root: Path):
        self.upstream_root = upstream_root.resolve()
        evaluator_root = self.upstream_root / "desktop_env" / "evaluators"
        self.metrics_init = evaluator_root / "metrics" / "__init__.py"
        self.getters_init = evaluator_root / "getters" / "__init__.py"
        self.setup_source = self.upstream_root / "desktop_env" / "controllers" / "setup.py"
        self.desktop_env_source = self.upstream_root / "desktop_env" / "desktop_env.py"
        for source in (self.metrics_init, self.getters_init, self.setup_source, self.desktop_env_source):
            if not source.is_file():
                raise OSWorldCaseError(f"pinned OSWorld runtime source missing: {source}")
        self.metric_names = _exported_names(self.metrics_init)
        self.getter_names = _exported_names(self.getters_init)
        self.setup_names = _setup_handlers(self.setup_source)

    def source_identity(self) -> dict[str, str]:
        return {
            "desktop_env_sha256": file_hash(self.desktop_env_source),
            "metrics_dispatch_sha256": file_hash(self.metrics_init),
            "getters_dispatch_sha256": file_hash(self.getters_init),
            "setup_dispatch_sha256": file_hash(self.setup_source),
        }

    def _resolve_setup(self, steps: Any, *, label: str) -> list[str]:
        if steps is None:
            steps = []
        if not isinstance(steps, list):
            raise OSWorldCaseError(f"{label} must be a list")
        resolved: list[str] = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise OSWorldCaseError(f"{label}[{index}] must be an object")
            setup_type = step.get("type")
            parameters = step.get("parameters")
            if not isinstance(setup_type, str) or not setup_type:
                raise OSWorldCaseError(f"{label}[{index}] has no setup type")
            if not isinstance(parameters, dict):
                raise OSWorldCaseError(f"{label}[{index}] parameters must be an object")
            handler = f"_{setup_type}_setup"
            if handler not in self.setup_names:
                raise OSWorldCaseError(f"upstream setup handler is unresolved: {handler}")
            resolved.append(handler)
        return resolved

    @staticmethod
    def _getter_name(config: Any, *, label: str) -> str:
        if not isinstance(config, dict) or not isinstance(config.get("type"), str) or not config["type"]:
            raise OSWorldCaseError(f"{label} must contain a non-empty getter type")
        return f"get_{config['type']}"

    def validate_task(self, task: Mapping[str, Any]) -> DispatchResolution:
        if not isinstance(task.get("instruction"), str) or not task["instruction"].strip():
            raise OSWorldCaseError("official task instruction is empty")
        if not isinstance(task.get("snapshot"), str) or not task["snapshot"].strip():
            raise OSWorldCaseError("official task snapshot is empty")

        evaluator = task.get("evaluator")
        if not isinstance(evaluator, dict):
            raise OSWorldCaseError("official evaluator is missing")
        raw_funcs = evaluator.get("func")
        funcs = raw_funcs if isinstance(raw_funcs, list) else [raw_funcs]
        if not funcs or not all(isinstance(func, str) and func for func in funcs):
            raise OSWorldCaseError("official evaluator function list is empty or invalid")
        unresolved_metrics = sorted(set(funcs) - self.metric_names)
        if unresolved_metrics:
            raise OSWorldCaseError("unresolved upstream metric(s): " + ",".join(unresolved_metrics))

        conjunction = evaluator.get("conj", "and")
        if conjunction not in {"and", "or"}:
            raise OSWorldCaseError(f"unsupported evaluator conjunction: {conjunction}")

        result_getters: list[str] = []
        expected_getters: list[str] = []
        is_function_list = isinstance(raw_funcs, list)
        result = evaluator.get("result")
        if raw_funcs != "infeasible":
            if is_function_list:
                if not isinstance(result, list) or len(result) != len(funcs):
                    raise OSWorldCaseError("metric/result getter arity mismatch")
                result_configs: Sequence[Any] = result
            else:
                result_configs = [result]
            for index, config in enumerate(result_configs):
                getter = self._getter_name(config, label=f"evaluator.result[{index}]")
                if getter not in self.getter_names:
                    raise OSWorldCaseError(f"unresolved upstream result getter: {getter}")
                result_getters.append(getter)

        expected = evaluator.get("expected")
        if expected:
            if is_function_list:
                if not isinstance(expected, list) or len(expected) != len(funcs):
                    raise OSWorldCaseError("metric/expected getter arity mismatch")
                expected_configs: Sequence[Any] = expected
            else:
                expected_configs = [expected]
            for index, config in enumerate(expected_configs):
                if config is None:
                    expected_getters.append("")
                    continue
                getter = self._getter_name(config, label=f"evaluator.expected[{index}]")
                if getter not in self.getter_names:
                    raise OSWorldCaseError(f"unresolved upstream expected getter: {getter}")
                expected_getters.append(getter)

        options = evaluator.get("options")
        if is_function_list:
            if options is not None and (not isinstance(options, list) or len(options) != len(funcs)):
                raise OSWorldCaseError("metric/options arity mismatch")
            if isinstance(options, list) and not all(option is None or isinstance(option, dict) for option in options):
                raise OSWorldCaseError("metric options must be objects or null")
        elif options is not None and not isinstance(options, dict):
            raise OSWorldCaseError("single metric options must be an object")

        setup = self._resolve_setup(task.get("config", []), label="task.config")
        setup.extend(self._resolve_setup(evaluator.get("postconfig", []), label="evaluator.postconfig"))
        return DispatchResolution(
            metric_functions=tuple(funcs),
            result_getters=tuple(result_getters),
            expected_getters=tuple(expected_getters),
            setup_handlers=tuple(setup),
            evaluator_sha256=canonical_hash(evaluator),
        )


@dataclass(frozen=True)
class OSWorldCase:
    case_id: str
    source_task_id: str
    native_path: str
    spec_path: Path
    config_path: Path
    config_sha256: str
    upstream_revision: str
    task: dict[str, Any]
    dispatch: DispatchResolution

    @property
    def task_id(self) -> str:
        return str(self.task["id"])

    @property
    def is_infeasible(self) -> bool:
        return self.task["evaluator"].get("func") == "infeasible"


def load_osworld_cases(
    repo_root: Path,
    *,
    source_native_root: Path | None = None,
    upstream_root: Path | None = None,
) -> list[OSWorldCase]:
    """Load and fully bind every OSWorld row in the source-native manifest."""

    repo_root = repo_root.resolve()
    source_native_root = (source_native_root or repo_root / "artifacts" / "source-native-v4").resolve()
    upstream_root = (upstream_root or repo_root / "upstream" / "osworld").resolve()
    manifest_path = source_native_root / "native_manifest.jsonl"
    if not manifest_path.is_file():
        raise OSWorldCaseError(f"source-native manifest missing: {manifest_path}")
    catalog = OSWorldDispatchCatalog(upstream_root)
    cases: list[OSWorldCase] = []
    seen_case_ids: set[str] = set()
    seen_sources: set[str] = set()
    official_examples = (upstream_root / "evaluation_examples" / "examples").resolve()

    for row in _read_jsonl(manifest_path):
        if row.get("benchmark") != "OSWorld":
            continue
        case_id = str(row.get("case_id") or "")
        source_task_id = str(row.get("source_task_id") or "")
        native_path = str(row.get("native_path") or "")
        if not CASE_ID_PATTERN.fullmatch(case_id):
            raise OSWorldCaseError(f"invalid OSWorld case id: {case_id!r}")
        if case_id in seen_case_ids:
            raise OSWorldCaseError(f"duplicate OSWorld case id: {case_id}")
        if source_task_id in seen_sources:
            raise OSWorldCaseError(f"duplicate OSWorld source task: {source_task_id}")
        seen_case_ids.add(case_id)
        seen_sources.add(source_task_id)

        case_dir = _resolve_within(source_native_root, native_path, label="native_path")
        spec_path = case_dir / "native_case.json"
        if not spec_path.is_file():
            raise OSWorldCaseError(f"native case spec missing: {spec_path}")
        spec = _read_json(spec_path)
        if spec.get("benchmark") != "OSWorld" or spec.get("case_id") != case_id:
            raise OSWorldCaseError(f"manifest/spec identity mismatch: {case_id}")
        binding = spec.get("source_binding")
        if not isinstance(binding, dict):
            raise OSWorldCaseError(f"source binding missing: {case_id}")
        config_relative = str(binding.get("config_path") or "")
        config_path = _resolve_within(repo_root, config_relative, label="OSWorld config_path")
        try:
            config_path.relative_to(official_examples)
        except ValueError as exc:
            raise OSWorldCaseError(f"OSWorld config is outside official examples: {config_path}") from exc
        if not config_path.is_file():
            raise OSWorldCaseError(f"official OSWorld config missing: {config_path}")
        actual_hash = file_hash(config_path)
        expected_hash = str(binding.get("config_sha256") or "")
        if not expected_hash or actual_hash != expected_hash:
            raise OSWorldCaseError(f"official OSWorld config hash mismatch: {case_id}")

        task = _read_json(config_path)
        task_id = str(task.get("id") or "")
        if not task_id or task_id != str(binding.get("task_id") or "") or not source_task_id.endswith(f":{task_id}"):
            raise OSWorldCaseError(f"OSWorld source task identity mismatch: {case_id}")
        domain = str(binding.get("domain") or "")
        if not domain or config_path.parent.name != domain:
            raise OSWorldCaseError(f"OSWorld source domain mismatch: {case_id}")
        if canonical_hash(task.get("evaluator")) != canonical_hash(spec.get("native_evaluator")):
            raise OSWorldCaseError(f"OSWorld evaluator binding mismatch: {case_id}")
        native_runtime = spec.get("native_runtime") or {}
        if native_runtime.get("adapter") != "osworld.DesktopEnv" or native_runtime.get("snapshot") != task.get("snapshot"):
            raise OSWorldCaseError(f"OSWorld native runtime binding mismatch: {case_id}")
        upstream_revision = str(binding.get("upstream_revision") or "")
        if not upstream_revision:
            raise OSWorldCaseError(f"OSWorld upstream revision missing: {case_id}")
        dispatch = catalog.validate_task(task)
        cases.append(
            OSWorldCase(
                case_id=case_id,
                source_task_id=source_task_id,
                native_path=native_path,
                spec_path=spec_path,
                config_path=config_path,
                config_sha256=actual_hash,
                upstream_revision=upstream_revision,
                task=_json_copy(task),
                dispatch=dispatch,
            )
        )
    if not cases:
        raise OSWorldCaseError("source-native manifest contains no OSWorld cases")
    return sorted(cases, key=lambda item: item.case_id)


class LocalOSWorldEnvironment:
    """OSWorld control-plane smoke environment; never a desktop emulator."""

    def __init__(self, case: OSWorldCase, state_dir: Path):
        self.case = case
        self.state_dir = state_dir.resolve()
        self.state_path = self.state_dir / "state.json"
        self.phase = RuntimePhase.STOPPED
        self._state: dict[str, Any] | None = None
        self._revision: str | None = None

    @property
    def state_revision(self) -> str:
        if self._revision is None:
            raise OSWorldRuntimeError("environment has not been reset")
        return self._revision

    @property
    def action_history(self) -> list[Any]:
        if self._state is None:
            return []
        return _json_copy(self._state["action_history"])

    def _observation(self) -> dict[str, Any]:
        return {
            "screenshot": None,
            "accessibility_tree": None,
            "terminal": None,
            "instruction": self.case.task["instruction"],
        }

    def _persist(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        envelope = {
            "schema_version": LOCAL_RUNTIME_SCHEMA,
            "scope": "infrastructure_only",
            "real_vm": False,
            "model_episode": False,
            "phase": self.phase.value,
            "state_revision": self._revision,
            "state": self._state,
        }
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(self.state_path)

    def start(self) -> dict[str, Any]:
        if self.phase is not RuntimePhase.STOPPED:
            raise OSWorldRuntimeError("local environment can only start once")
        self.phase = RuntimePhase.STARTED
        self._persist()
        return self._observation()

    def reset(self) -> dict[str, Any]:
        if self.phase not in {RuntimePhase.STARTED, RuntimePhase.READY, RuntimePhase.TERMINAL}:
            raise OSWorldRuntimeError("reset requires a started environment")
        self._state = {
            "schema_version": LOCAL_RUNTIME_SCHEMA,
            "case_id": self.case.case_id,
            "source_task_id": self.case.source_task_id,
            "official_config_sha256": self.case.config_sha256,
            "snapshot": self.case.task["snapshot"],
            "setup_plan_sha256": canonical_hash(self.case.task.get("config", [])),
            "evaluator_sha256": self.case.dispatch.evaluator_sha256,
            "action_history": [],
        }
        self._revision = canonical_hash(self._state)
        self.phase = RuntimePhase.READY
        self._persist()
        return self._observation()

    @staticmethod
    def _special_action(action: Any) -> str:
        if isinstance(action, str) and action in SPECIAL_ACTIONS:
            return action
        if isinstance(action, dict) and set(action) == {"action_type"} and action.get("action_type") in SPECIAL_ACTIONS:
            return str(action["action_type"])
        raise RealVMRequiredError(
            "only OSWorld WAIT/FAIL/DONE control actions are available in the local smoke runtime; "
            "desktop and pyautogui actions require a real OSWorld VM"
        )

    def step(self, action: Any, pause: float = 0) -> tuple[dict[str, Any], float, bool, dict[str, bool]]:
        del pause  # The local control plane never sleeps or executes inside a VM.
        if self.phase is not RuntimePhase.READY or self._state is None:
            raise OSWorldRuntimeError("step requires a reset, non-terminal environment")
        special = self._special_action(action)
        self._state["action_history"].append(_json_copy(action))
        self._revision = canonical_hash(self._state)
        done = special in {"FAIL", "DONE"}
        info: dict[str, bool] = {"fail": True} if special == "FAIL" else {"done": True} if special == "DONE" else {}
        if done:
            self.phase = RuntimePhase.TERMINAL
        self._persist()
        return self._observation(), 0.0, done, info

    def evaluate(self) -> float:
        if self.phase not in {RuntimePhase.READY, RuntimePhase.TERMINAL} or self._state is None:
            raise OSWorldRuntimeError("evaluate requires a reset environment")
        history = self._state["action_history"]
        last = history[-1] if history else None
        last_kind = last if isinstance(last, str) else last.get("action_type") if isinstance(last, dict) else None

        # This is the exact dependency-free terminal branch in pinned
        # DesktopEnv.evaluate: infeasible+FAIL scores 1; every other task+FAIL
        # scores 0 before any getter or metric is called.
        if last_kind == "FAIL":
            return 1.0 if self.case.is_infeasible else 0.0
        if self.case.is_infeasible:
            return 0.0
        raise RealVMRequiredError(
            "task-success scoring requires the official OSWorld VM getters and gold metric; "
            "the local runtime only validates the terminal FAIL evaluator path"
        )

    score = evaluate

    def close(self) -> None:
        if self.phase is RuntimePhase.CLOSED:
            return
        if self.phase is RuntimePhase.STOPPED:
            raise OSWorldRuntimeError("cannot close an environment that was never started")
        self.phase = RuntimePhase.CLOSED
        self._persist()

    def __enter__(self) -> "LocalOSWorldEnvironment":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


def validate_audit_chain(audit: Iterable[Mapping[str, Any]]) -> bool:
    previous = "0" * 64
    seen = False
    for item in audit:
        record = dict(item)
        recorded_hash = record.pop("record_sha256", None)
        if record.get("previous_sha256") != previous or canonical_hash(record) != recorded_hash:
            return False
        previous = str(recorded_hash)
        seen = True
    return seen


@dataclass(frozen=True)
class RealVMProviderProbe:
    provider: str
    configuration_resolved: bool
    launch_ready: bool
    launch_attempted: bool
    launch_succeeded: bool
    blockers: tuple[str, ...]
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configuration_resolved": self.configuration_resolved,
            "launch_ready": self.launch_ready,
            "launch_attempted": self.launch_attempted,
            "launch_succeeded": self.launch_succeeded,
            "blockers": list(self.blockers),
            "details": _json_copy(self.details),
        }


def _command_ok(
    command: list[str], timeout: int = 10, *, cwd: Path | None = None
) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, type(exc).__name__
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or f"exit_{result.returncode}").strip()[-300:]
    return True, result.stdout.strip()[-300:]


def validate_osworld_asset_attestation(
    attestation_path: Path,
    vm_path: Path,
    *,
    digest_image_id: str,
    latest_image_id: str,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Validate fetcher evidence without rehashing the attested 23 GiB qcow2."""

    attestation_path = attestation_path.resolve()
    vm_path = vm_path.resolve()
    blockers: list[str] = []
    details: dict[str, Any] = {
        "asset_attestation_path": str(attestation_path),
        "asset_attestation_present": attestation_path.is_file(),
        "asset_attestation_sha256": (
            file_hash(attestation_path) if attestation_path.is_file() else ""
        ),
        "asset_attestation_verified": False,
    }
    if not attestation_path.is_file():
        return False, ["osworld_asset_attestation_missing"], details
    try:
        attestation = _read_json(attestation_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        details["asset_attestation_error"] = type(exc).__name__
        return False, ["osworld_asset_attestation_invalid"], details

    stat = vm_path.stat() if vm_path.is_file() else None
    recorded_path = attestation.get("qcow2_path")
    try:
        recorded_path_matches = (
            isinstance(recorded_path, str)
            and Path(recorded_path).resolve() == vm_path
        )
    except OSError:
        recorded_path_matches = False
    identity = attestation.get("docker_identity") or {}
    checks = {
        "schema_valid": attestation.get("schema_version") == "osworld-official-assets-v1",
        "assets_ready": attestation.get("assets_ready") is True,
        "qcow2_path_matches": recorded_path_matches,
        "qcow2_file_present": stat is not None,
        "qcow2_size_matches": (
            stat is not None
            and stat.st_size == OFFICIAL_OSWORLD_QCOW2_SIZE
            and attestation.get("qcow2_size") == stat.st_size
        ),
        "qcow2_mtime_matches": (
            stat is not None and attestation.get("qcow2_mtime_ns") == stat.st_mtime_ns
        ),
        "qcow2_hash_attested": (
            attestation.get("qcow2_sha256") == OFFICIAL_OSWORLD_QCOW2_SHA256
            and attestation.get("qcow2_sha256_verified") is True
        ),
        "docker_digest_attested": (
            attestation.get("docker_image") == OFFICIAL_OSWORLD_DOCKER_IMAGE
            and identity.get("digest_image_id") == OFFICIAL_OSWORLD_DOCKER_IMAGE_ID
            and identity.get("upstream_latest_image_id") == OFFICIAL_OSWORLD_DOCKER_IMAGE_ID
        ),
        "docker_digest_present": digest_image_id == OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
        "docker_latest_matches_digest": latest_image_id == OFFICIAL_OSWORLD_DOCKER_IMAGE_ID,
    }
    if not all(checks.values()):
        blockers.append("osworld_asset_attestation_mismatch")
    details.update({
        "asset_attestation_checks": checks,
        "attested_qcow2_sha256": attestation.get("qcow2_sha256", ""),
        "attested_qcow2_size": attestation.get("qcow2_size"),
        "attested_qcow2_mtime_ns": attestation.get("qcow2_mtime_ns"),
        "current_qcow2_size": stat.st_size if stat else None,
        "current_qcow2_mtime_ns": stat.st_mtime_ns if stat else None,
        "docker_digest_image_id": digest_image_id,
        "docker_latest_image_id": latest_image_id,
        "asset_attestation_verified": not blockers,
    })
    return not blockers, blockers, details


def validate_osworld_python_bootstrap(
    report_path: Path,
    lock_path: Path,
    upstream_root: Path,
    *,
    interpreter: Path | None = None,
    prefix: Path | None = None,
    base_prefix: Path | None = None,
    installed_distributions_snapshot: Mapping[str, Any] | None = None,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Bind the isolated interpreter to its checked lock and import report."""

    report_path = report_path.resolve()
    lock_path = lock_path.resolve()
    upstream_root = upstream_root.resolve()
    interpreter = (interpreter or Path(sys.executable)).resolve()
    prefix = (prefix or Path(sys.prefix)).resolve()
    base_prefix = (base_prefix or Path(sys.base_prefix)).resolve()
    details: dict[str, Any] = {
        "python_bootstrap_report_path": str(report_path),
        "python_bootstrap_report_present": report_path.is_file(),
        "python_bootstrap_report_sha256": (
            file_hash(report_path) if report_path.is_file() else ""
        ),
        "python_environment_lock_path": str(lock_path),
        "python_environment_lock_present": lock_path.is_file(),
        "python_environment_lock_sha256": (
            file_hash(lock_path) if lock_path.is_file() else ""
        ),
        "python_interpreter": str(interpreter),
        "python_environment_isolated": False,
        "python_bootstrap_verified": False,
    }
    if not report_path.is_file() or not lock_path.is_file():
        missing = []
        if not report_path.is_file():
            missing.append("osworld_python_bootstrap_report_missing")
        if not lock_path.is_file():
            missing.append("osworld_python_environment_lock_missing")
        return False, missing, details
    try:
        report = _read_json(report_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        details["python_bootstrap_error"] = type(exc).__name__
        return False, ["osworld_python_bootstrap_report_invalid"], details

    interpreter_report = report.get("interpreter") or {}
    isolation = report.get("isolation") or {}
    lock = report.get("lock") or {}
    pip_check = report.get("pip_check") or {}
    imports = report.get("imports") or {}
    desktop_import = imports.get("desktop_env") or {}
    psutil_import = imports.get("psutil") or {}
    docker_import = imports.get("docker_provider") or {}
    installer = report.get("installer") or {}
    runtime_versions = report.get("runtime_versions") or {}
    upstream_constraints = report.get("upstream_constraints") or {}
    constraint_sources = upstream_constraints.get("sources") or {}
    installed_report = lock.get("installed_distributions") or {}
    lock_check = lock.get("check") or {}
    pyvenv_cfg = prefix / "pyvenv.cfg"

    def same_path(left: Any, right: Path) -> bool:
        if not isinstance(left, str) or not left:
            return False
        try:
            return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(right))
        except OSError:
            return False

    def path_within(value: Any, parent: Path) -> bool:
        if not isinstance(value, str) or not value:
            return False
        try:
            Path(value).resolve().relative_to(parent)
        except (OSError, ValueError):
            return False
        return True

    if installed_distributions_snapshot is None:
        snapshot_code = (
            "import hashlib,importlib.metadata as m,json;"
            "from packaging.utils import canonicalize_name as c;"
            "d={c(x.metadata['Name']):x.version for x in m.distributions() "
            "if x.metadata.get('Name')};"
            "p=('\\n'.join(f'{k}=={d[k]}' for k in sorted(d))+'\\n').encode();"
            "print(json.dumps({'count':len(d),'sha256':hashlib.sha256(p).hexdigest()}))"
        )
        try:
            completed = subprocess.run(
                [str(interpreter), "-I", "-c", snapshot_code],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            installed_distributions_snapshot = (
                json.loads(completed.stdout.strip())
                if completed.returncode == 0 and completed.stdout.strip()
                else {}
            )
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            installed_distributions_snapshot = {}

    requirements_path = upstream_root / "requirements.txt"
    setup_path = upstream_root / "setup.py"
    requirements_source = constraint_sources.get("requirements.txt") or {}
    setup_source = constraint_sources.get("setup.py") or {}

    checks = {
        "schema_valid": report.get("schema_version") == "osworld-native-python-bootstrap-v1",
        "report_passed": report.get("passed") is True,
        "interpreter_matches": same_path(interpreter_report.get("executable"), interpreter),
        "interpreter_is_supported_cpython": (
            interpreter_report.get("implementation") == "CPython"
            and isinstance(interpreter_report.get("version"), str)
            and interpreter_report["version"].startswith("3.12.")
        ),
        "interpreter_prefix_matches": same_path(interpreter_report.get("prefix"), prefix),
        "interpreter_base_prefix_matches": same_path(
            interpreter_report.get("base_prefix"), base_prefix
        ),
        "venv_prefix_matches": same_path(report.get("venv_path"), prefix),
        "upstream_root_matches": same_path(report.get("upstream_root"), upstream_root),
        "venv_isolated": (
            prefix != base_prefix
            and isolation.get("include_system_site_packages") is False
            and pyvenv_cfg.is_file()
            and _valid_sha256(isolation.get("pyvenv_cfg_sha256"))
            and file_hash(pyvenv_cfg) == isolation.get("pyvenv_cfg_sha256")
        ),
        "lock_path_matches": same_path(lock.get("path"), lock_path),
        "lock_sha256_matches": (
            _valid_sha256(lock.get("sha256"))
            and file_hash(lock_path) == lock.get("sha256")
        ),
        "environment_fingerprint_valid": _valid_sha256(
            report.get("environment_fingerprint_sha256")
        ),
        "installer_configuration_valid": (
            isinstance(installer.get("uv_version"), str)
            and installer["uv_version"].startswith("uv ")
            and installer.get("torch_backend") == "cpu"
        ),
        "installed_distributions_match": (
            isinstance(installed_distributions_snapshot, Mapping)
            and isinstance(installed_report.get("count"), int)
            and installed_report.get("count")
            == installed_distributions_snapshot.get("count")
            and _valid_sha256(installed_report.get("sha256"))
            and installed_report.get("sha256")
            == installed_distributions_snapshot.get("sha256")
        ),
        "lock_installation_valid": (
            lock_check.get("passed") is True
            and isinstance(lock_check.get("checked"), int)
            and lock_check["checked"] > 0
            and lock_check.get("unexpected_distributions") == []
            and lock_check.get("violations") == []
            and installed_report.get("duplicate_distributions") == []
        ),
        "upstream_constraints_valid": (
            upstream_constraints.get("passed") is True
            and isinstance(upstream_constraints.get("checked"), int)
            and upstream_constraints["checked"] > 0
            and upstream_constraints.get("violations") == []
            and same_path(requirements_source.get("path"), requirements_path)
            and same_path(setup_source.get("path"), setup_path)
            and requirements_path.is_file()
            and setup_path.is_file()
            and _valid_sha256(requirements_source.get("sha256"))
            and _valid_sha256(setup_source.get("sha256"))
            and file_hash(requirements_path) == requirements_source.get("sha256")
            and file_hash(setup_path) == setup_source.get("sha256")
        ),
        "runtime_versions_authoritative": (
            runtime_versions.get("numpy") == "1.26.4"
            and runtime_versions.get("torch") == "2.5.1+cpu"
            and runtime_versions.get("opencv_python_headless") == "4.8.1"
            and runtime_versions.get("matplotlib") == "3.7.5"
            and runtime_versions.get("pandas") == "2.2.3"
            and runtime_versions.get("pillow") == "11.0.0"
            and runtime_versions.get("psutil") == "5.9.8"
        ),
        "pip_check_passed": (
            pip_check.get("passed") is True
            and isinstance(pip_check.get("output"), str)
            and bool(pip_check.get("output").strip())
        ),
        "desktop_env_import_bound": (
            desktop_import.get("module") == "desktop_env.desktop_env"
            and path_within(desktop_import.get("file"), upstream_root)
        ),
        "psutil_import_isolated": (
            psutil_import.get("version") == "5.9.8"
            and path_within(psutil_import.get("file"), prefix)
            and path_within(psutil_import.get("binary_file"), prefix)
            and str(psutil_import.get("binary_file", "")).lower().endswith(".pyd")
        ),
        "docker_provider_import_bound": (
            docker_import.get("manager_module")
            == "desktop_env.providers.docker.manager"
            and docker_import.get("provider_module")
            == "desktop_env.providers.docker.provider"
        ),
    }
    verified = all(checks.values())
    details.update({
        "python_bootstrap_checks": checks,
        "python_environment_isolated": checks["venv_isolated"],
        "python_pip_check_passed": checks["pip_check_passed"],
        "python_desktop_env_import_bound": checks["desktop_env_import_bound"],
        "python_docker_provider_import_bound": checks["docker_provider_import_bound"],
        "python_psutil_import_isolated": checks["psutil_import_isolated"],
        "python_bootstrap_verified": verified,
    })
    return (
        verified,
        [] if verified else ["osworld_python_bootstrap_report_mismatch"],
        details,
    )


def probe_real_vm_provider(
    upstream_root: Path,
    *,
    provider: str = "docker",
    path_to_vm: Path | None = None,
    docker_image: str = "happysixd/osworld-docker",
    asset_attestation: Path | None = None,
    bootstrap_report: Path | None = None,
    environment_lock: Path | None = None,
) -> RealVMProviderProbe:
    """Non-mutating prerequisite check for an official OSWorld VM provider.

    This never downloads a disk, starts a VM, or upgrades a local qualification
    into real-VM evidence.  ``launch_ready`` means the explicit prerequisites
    for a later upstream launch are present on this host.
    """

    upstream_root = upstream_root.resolve()
    provider = provider.lower().strip()
    supported = {
        "docker", "vmware", "virtualbox", "aws", "azure", "aliyun",
        "volcengine", "fastvm", "daytona", "modal", "pyromind",
    }
    blockers: list[str] = []
    factory = upstream_root / "desktop_env" / "providers" / "__init__.py"
    provider_source = upstream_root / "desktop_env" / "providers" / provider / "provider.py"
    manager_source = upstream_root / "desktop_env" / "providers" / provider / "manager.py"
    configuration_resolved = provider in supported and factory.is_file() and provider_source.is_file() and manager_source.is_file()
    if provider not in supported:
        blockers.append("provider_not_in_upstream_factory")
    if not factory.is_file() or not provider_source.is_file() or not manager_source.is_file():
        blockers.append("provider_source_missing")

    details: dict[str, Any] = {
        "factory_sha256": file_hash(factory) if factory.is_file() else "",
        "provider_source_sha256": file_hash(provider_source) if provider_source.is_file() else "",
        "manager_source_sha256": file_hash(manager_source) if manager_source.is_file() else "",
        "path_to_vm": str(path_to_vm.resolve()) if path_to_vm else "",
    }
    bootstrap_ok = True
    if bootstrap_report is not None or environment_lock is not None:
        if bootstrap_report is None or environment_lock is None:
            bootstrap_ok = False
            blockers.append("osworld_python_bootstrap_configuration_incomplete")
        else:
            bootstrap_ok, bootstrap_blockers, bootstrap_details = (
                validate_osworld_python_bootstrap(
                    bootstrap_report,
                    environment_lock,
                    upstream_root,
                )
            )
            blockers.extend(bootstrap_blockers)
            details.update(bootstrap_details)
    import_code = (
        "import importlib, sys; "
        "sys.path.insert(0, sys.argv[1]); "
        "from desktop_env.desktop_env import DesktopEnv; "
        "importlib.import_module('desktop_env.providers.' + sys.argv[2] + '.manager'); "
        "importlib.import_module('desktop_env.providers.' + sys.argv[2] + '.provider'); "
        "print(DesktopEnv.__name__)"
    )
    import_ok, import_detail = _command_ok(
        [sys.executable, "-c", import_code, str(upstream_root), provider],
        30,
        cwd=upstream_root,
    )
    details["upstream_desktop_env_importable"] = import_ok
    details["upstream_dependency_probe"] = import_detail
    if not import_ok:
        blockers.append("upstream_runtime_dependencies_missing")
    launch_ready = False
    if provider == "docker" and configuration_resolved:
        docker_cli = shutil.which("docker")
        details["docker_cli_found"] = bool(docker_cli)
        daemon_ok, daemon_identity = _command_ok([docker_cli, "version", "--format", "{{.Server.Version}}"], 10) if docker_cli else (False, "")
        image_ok, image_identity = _command_ok([docker_cli, "image", "inspect", docker_image, "--format", "{{.Id}}"], 10) if docker_cli and daemon_ok else (False, "")
        digest_ok, digest_identity = _command_ok(
            [docker_cli, "image", "inspect", OFFICIAL_OSWORLD_DOCKER_IMAGE, "--format", "{{.Id}}"], 10
        ) if docker_cli and daemon_ok else (False, "")
        latest_ok, latest_identity = _command_ok(
            [docker_cli, "image", "inspect", "happysixd/osworld-docker:latest", "--format", "{{.Id}}"], 10
        ) if docker_cli and daemon_ok else (False, "")
        vm_path = path_to_vm.resolve() if path_to_vm else (upstream_root / "docker_vm_data" / "Ubuntu.qcow2").resolve()
        disk_ok = vm_path.is_file()
        details.update({
            "daemon_reachable": daemon_ok,
            "daemon_identity": daemon_identity if daemon_ok else "",
            "docker_image": docker_image,
            "docker_image_present": image_ok,
            "docker_image_identity": image_identity if image_ok else "",
            "docker_digest_image_present": digest_ok,
            "docker_digest_image_identity": digest_identity if digest_ok else "",
            "docker_latest_image_present": latest_ok,
            "docker_latest_image_identity": latest_identity if latest_ok else "",
            "vm_disk_present": disk_ok,
            "vm_disk_path": str(vm_path),
        })
        if not docker_cli:
            blockers.append("docker_cli_missing")
        elif not daemon_ok:
            blockers.append("docker_daemon_unreachable")
        if not image_ok:
            blockers.append("osworld_docker_image_missing")
        if not disk_ok:
            blockers.append("osworld_vm_disk_missing")
        attestation_ok = True
        if asset_attestation is not None:
            attestation_ok, attestation_blockers, attestation_details = (
                validate_osworld_asset_attestation(
                    asset_attestation,
                    vm_path,
                    digest_image_id=digest_identity if digest_ok else "",
                    latest_image_id=latest_identity if latest_ok else "",
                )
            )
            blockers.extend(attestation_blockers)
            details.update(attestation_details)
        launch_ready = (
            daemon_ok and image_ok and digest_ok and latest_ok
            and disk_ok and import_ok and attestation_ok and bootstrap_ok
        )
    elif provider in {"vmware", "virtualbox"} and configuration_resolved:
        executable_name = "vmrun" if provider == "vmware" else "VBoxManage"
        executable = shutil.which(executable_name)
        vm_ok = path_to_vm is not None and path_to_vm.resolve().is_file()
        details.update({"provider_cli_found": bool(executable), "vm_definition_present": vm_ok})
        if not executable:
            blockers.append(f"{provider}_cli_missing")
        if not vm_ok:
            blockers.append("vm_definition_missing")
        launch_ready = bool(executable) and vm_ok and import_ok
    elif configuration_resolved:
        blockers.append("cloud_provider_runtime_preflight_requires_explicit_credentials")

    return RealVMProviderProbe(
        provider=provider,
        configuration_resolved=configuration_resolved,
        launch_ready=launch_ready,
        launch_attempted=False,
        launch_succeeded=False,
        blockers=tuple(dict.fromkeys(blockers)),
        details=details,
    )


def qualify_environment_smoke(
    case: OSWorldCase,
    state_dir: Path,
    *,
    provider_probe: RealVMProviderProbe,
    dispatch_identity: Mapping[str, str],
) -> dict[str, Any]:
    """Exercise one local lifecycle and return non-VM qualification evidence."""

    environment = LocalOSWorldEnvironment(case, state_dir)
    broker = NativeEventBroker(mode="async")
    environment.start()
    environment.reset()
    baseline = environment.state_revision
    environment.reset()
    repeat_baseline = environment.state_revision
    broker.launch(baseline)
    _, _, done, info = environment.step("FAIL")
    checkpoint = environment.state_revision
    broker.commit_checkpoint(checkpoint)
    observed_score = environment.evaluate()
    expected_score = 1.0 if case.is_infeasible else 0.0
    result = {
        "kind": "official_terminal_fail_control_path",
        "score": observed_score,
        "expected_score": expected_score,
        "done": done,
        "fail": info.get("fail") is True,
        "native_metric_executed": False,
        "real_vm_executed": False,
        "model_episode": False,
    }
    # The broker rejects keys prefixed with ``expected_`` as a general
    # answer-leak safeguard.  The reference score remains in host-owned smoke
    # evidence, never in the worker payload delivered to an agent.
    broker.complete_worker({key: value for key, value in result.items() if key != "expected_score"})
    broker.deliver()
    broker.finalize(checkpoint)
    environment.reset()
    restored = environment.state_revision
    environment.close()

    checks = {
        "official_config_bound": bool(case.config_sha256),
        "upstream_dispatch_bound": bool(dispatch_identity) and bool(case.dispatch.metric_functions),
        "provider_launch_configuration_resolved": provider_probe.configuration_resolved,
        "local_runtime_started": True,
        "reset_reproducible": baseline == repeat_baseline == restored,
        "local_state_changed": checkpoint != baseline,
        "evaluator_control_path_scored": observed_score == expected_score,
        "audit_chain_valid": validate_audit_chain(broker.audit),
        "real_vm_executed": False,
        "model_episode_executed": False,
        "official_task_setup_executed": False,
        "official_gold_metric_executed": False,
    }
    required = (
        "official_config_bound",
        "upstream_dispatch_bound",
        "provider_launch_configuration_resolved",
        "local_runtime_started",
        "reset_reproducible",
        "local_state_changed",
        "evaluator_control_path_scored",
        "audit_chain_valid",
    )
    status = ENVIRONMENT_SMOKE_READY_STATUS if all(checks[name] is True for name in required) else "validation_failed"
    environment_identity = {
        "adapter": LOCAL_ADAPTER,
        "kind": "local_evaluator_compatible_control_plane",
        "scope": "infrastructure_only",
        "real_vm": False,
        "model_episode": False,
        "official_task_setup_executed": False,
        "official_gold_metric_executed": False,
        "upstream_revision": case.upstream_revision,
        "official_config_sha256": case.config_sha256,
        "dispatch": dict(dispatch_identity),
        "identity_sha256": canonical_hash({
            "adapter": LOCAL_ADAPTER,
            "upstream_revision": case.upstream_revision,
            "official_config_sha256": case.config_sha256,
            "dispatch": dict(dispatch_identity),
        }),
    }
    return {
        "schema_version": QUALIFICATION_SCHEMA,
        "case_id": case.case_id,
        "benchmark": "OSWorld",
        "source_task_id": case.source_task_id,
        "status": status,
        "qualification_profile": OSWORLD_SMOKE_PROFILE,
        "execution_scope": "infrastructure_smoke",
        "checks": checks,
        "environment": environment_identity,
        "real_vm_provider_preflight": provider_probe.as_dict(),
        "score_probe": result,
        "checkpoint_smoke": {
            "scope": "infrastructure_smoke_not_a_model_episode",
            "baseline_revision": baseline,
            "checkpoint_revision": checkpoint,
            "restored_revision": restored,
            "audit": broker.audit,
        },
    }
