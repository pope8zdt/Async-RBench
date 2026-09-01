from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

from async_rbench.evaluation.pair_qualification import pair_qualification_errors


ROOT = Path(__file__).resolve().parents[1]
INTAKE = ROOT / "artifacts" / "async-bench-intake"
READY = INTAKE / "ready.jsonl"
STATE = INTAKE / "consumer-state.json"
EVENTS = INTAKE / "consumer-events.jsonl"
ISSUES = INTAKE / "issues.jsonl"
ISSUES_MD = INTAKE / "issues.md"
SUMMARY = INTAKE / "summary.json"
LOCK = INTAKE / "consumer.lock"
RUNS = INTAKE / "runs"
STATUS_CORRECTIONS = INTAKE / "consumer-status-corrections.jsonl"
CANDIDATES = ROOT / "candidate_cases"
DEFAULT_CONFIG = ROOT / "configs" / "model-profiles" / "gpt-5.6-luna-validation-codex-cli.yaml"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

TERMINAL = {"passed", "completed_with_findings", "failed", "rejected"}
REQUIRED = {
    "case_id", "absolute_path", "source_category", "completed_at",
    "static_checks", "status", "revision", "bundle_sha256", "control_prefix",
}
CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = str(path.relative_to(root)).replace("\\", "/")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def parse_ready() -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    if not READY.is_file():
        return records, errors
    for line_number, line in enumerate(READY.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"ready.jsonl line {line_number}: {exc}")
            continue
        missing = sorted(REQUIRED - set(record))
        if missing:
            errors.append(f"ready.jsonl line {line_number}: missing {missing}")
            continue
        records.append(record)
    return records, errors


def record_key(record: dict[str, Any]) -> str:
    return f"{record['case_id']}@r{int(record['revision'])}"


def apply_status_corrections(state: dict[str, dict[str, Any]]) -> None:
    if not STATUS_CORRECTIONS.is_file():
        return
    for line in STATUS_CORRECTIONS.read_text(encoding="utf-8").splitlines():
        try:
            correction = json.loads(line)
        except (ValueError, TypeError):
            continue
        key = str(correction.get("key") or "")
        if key not in state:
            continue
        entry = state[key]
        corrected_status = correction.get("corrected_status")
        if corrected_status not in TERMINAL:
            continue
        if "historical_recorded_status" not in entry:
            entry["historical_recorded_status"] = correction.get("recorded_status")
        entry["status"] = corrected_status
        entry["status_correction"] = {
            "corrected_at": correction.get("corrected_at"),
            "qualification_errors": correction.get("qualification_errors") or [],
            "results_evidence": correction.get("results_evidence"),
            "command_evidence": correction.get("command_evidence"),
        }


class IntakeConsumer:
    def __init__(self, *, config: Path, timeout: int, workers: int) -> None:
        self.config = config.resolve()
        self.timeout = timeout
        self.workers = workers
        self.guard = threading.RLock()
        self.case_locks: dict[str, threading.Lock] = {}
        self.reported_parse_errors: set[str] = set()
        loaded = load_json(STATE, {})
        self.state: dict[str, dict[str, Any]] = loaded if isinstance(loaded, dict) else {}
        apply_status_corrections(self.state)
        self.futures: dict[Future[None], str] = {}
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="async-bench-intake")
        self._initialize_files()

    def _initialize_files(self) -> None:
        INTAKE.mkdir(parents=True, exist_ok=True)
        RUNS.mkdir(parents=True, exist_ok=True)
        READY.touch(exist_ok=True)
        EVENTS.touch(exist_ok=True)
        ISSUES.touch(exist_ok=True)
        if not ISSUES_MD.is_file():
            ISSUES_MD.write_text(
                "# Async-Bench case intake issues\n\n"
                "This ledger separates package/runtime defects from ordinary model scores.\n\n",
                encoding="utf-8",
            )
        for key, item in self.state.items():
            if item.get("status") not in TERMINAL:
                item["status"] = "queued"
                item["recovered_at"] = utc_now()
        self._save_state()

    def _save_state(self) -> None:
        with self.guard:
            apply_status_corrections(self.state)
            atomic_json(STATE, self.state)
            statuses: dict[str, int] = {}
            issue_classifications: dict[str, int] = {}
            issue_severities: dict[str, int] = {}
            for item in self.state.values():
                status = str(item.get("status") or "unknown")
                statuses[status] = statuses.get(status, 0) + 1
                for issue in item.get("issues") or []:
                    classification = str(issue.get("classification") or "unknown")
                    severity = str(issue.get("severity") or "unknown")
                    issue_classifications[classification] = issue_classifications.get(classification, 0) + 1
                    issue_severities[severity] = issue_severities.get(severity, 0) + 1
            atomic_json(SUMMARY, {
                "schema_version": "async-bench-intake-summary-v1",
                "updated_at": utc_now(),
                "ready_record_count": len(self.state),
                "status_counts": dict(sorted(statuses.items())),
                "issue_count": sum(issue_classifications.values()),
                "issue_classification_counts": dict(sorted(issue_classifications.items())),
                "issue_severity_counts": dict(sorted(issue_severities.items())),
                "active_worker_limit": self.workers,
                "model_config": str(self.config),
                "issues_jsonl": str(ISSUES),
            })

    def _event(self, event: str, key: str, **extra: Any) -> None:
        payload = {"at": utc_now(), "event": event, "key": key, **extra}
        with self.guard:
            append_jsonl(EVENTS, payload)

    def _issue(
        self, record: dict[str, Any], *, stage: str, severity: str,
        code: str, message: str, evidence: str | None = None,
        classification: str | None = None,
    ) -> None:
        payload = {
            "at": utc_now(),
            "case_id": record.get("case_id"),
            "revision": record.get("revision"),
            "source_category": record.get("source_category"),
            "stage": stage,
            "severity": severity,
            "code": code,
            "message": message,
            "evidence": evidence,
            "classification": classification or "case_or_package_problem",
        }
        safe_message = " ".join(message.splitlines())
        markdown = (
            f"- {payload['at']} | `{payload['case_id']}` r{payload['revision']} | "
            f"**{severity} / {stage} / {code}** | {safe_message}"
            + (f" | Evidence: `{evidence}`" if evidence else "") + "\n"
        )
        with self.guard:
            append_jsonl(ISSUES, payload)
            with ISSUES_MD.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(markdown)
            key = record_key(record)
            self.state.setdefault(key, {}).setdefault("issues", []).append(payload)
            self._save_state()

    def _set(self, key: str, **values: Any) -> None:
        with self.guard:
            self.state.setdefault(key, {}).update(values)
            self._save_state()

    def _validate_record(self, record: dict[str, Any]) -> str | None:
        case_id = str(record.get("case_id") or "")
        if not CASE_ID.fullmatch(case_id):
            return f"unsafe or invalid case_id: {case_id!r}"
        if record.get("status") != "ready":
            return f"handoff status is not ready: {record.get('status')!r}"
        if int(record.get("revision") or 0) < 1:
            return "revision must be at least 1"
        digest = str(record.get("bundle_sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            return "bundle_sha256 is invalid"
        checks = record.get("static_checks")
        if not isinstance(checks, dict) or not checks or any(value != "passed" for value in checks.values()):
            return "every published static check must equal 'passed'"
        for required_check in ("candidate_family_pair_smoke", "case_promote_dry_run"):
            if checks.get(required_check) != "passed":
                return f"required publication check is missing: {required_check}=passed"
        if not str(record.get("control_prefix") or "").strip():
            return "control_prefix must be non-empty"
        return None

    def discover(self) -> None:
        records, parse_errors = parse_ready()
        for message in parse_errors:
            if message in self.reported_parse_errors:
                continue
            self.reported_parse_errors.add(message)
            synthetic = {
                "case_id": "ready-manifest", "revision": 0,
                "source_category": "handoff",
            }
            self._issue(
                synthetic, stage="handoff", severity="high",
                code="invalid_ready_record", message=message, evidence=str(READY),
            )
        for record in records:
            key = record_key(record)
            with self.guard:
                current = self.state.get(key)
                if current and current.get("bundle_sha256") == record.get("bundle_sha256"):
                    if current.get("status") not in TERMINAL and key not in self.futures.values():
                        self._event("requeued", key, case_id=record["case_id"])
                        future = self.pool.submit(self._process_safely, record)
                        self.futures[future] = key
                    continue
                if current:
                    self._issue(
                        record, stage="handoff", severity="critical",
                        code="immutable_record_changed",
                        message="The same case revision was republished with a different bundle digest.",
                        evidence=str(READY),
                    )
                    continue
                self.state[key] = {
                    "case_id": record["case_id"],
                    "revision": int(record["revision"]),
                    "source_category": record["source_category"],
                    "absolute_path": record["absolute_path"],
                    "bundle_sha256": record["bundle_sha256"],
                    "published_at": record["completed_at"],
                    "received_at": utc_now(),
                    "status": "queued",
                    "issues": [],
                }
                self._save_state()
                self._event("queued", key, case_id=record["case_id"])
                future = self.pool.submit(self._process_safely, record)
                self.futures[future] = key

    def reap(self) -> None:
        for future, key in list(self.futures.items()):
            if not future.done():
                continue
            try:
                future.result()
            except Exception as exc:  # final fail-closed boundary for the service
                record = self.state.get(key, {})
                synthetic = {
                    "case_id": record.get("case_id", key),
                    "revision": record.get("revision", 0),
                    "source_category": record.get("source_category", "unknown"),
                }
                self._issue(
                    synthetic, stage="consumer", severity="critical",
                    code="unhandled_consumer_error", message=repr(exc),
                )
                self._set(key, status="failed", completed_at=utc_now())
            del self.futures[future]

    def _process_safely(self, record: dict[str, Any]) -> None:
        case_id = str(record["case_id"])
        with self.guard:
            case_lock = self.case_locks.setdefault(case_id, threading.Lock())
        with case_lock:
            self._process(record)

    def _stage(self, record: dict[str, Any], run_dir: Path) -> Path | None:
        key = record_key(record)
        source = Path(str(record["absolute_path"])).resolve()
        if not source.is_dir():
            self._issue(
                record, stage="handoff", severity="critical", code="bundle_missing",
                message=f"Published bundle directory does not exist: {source}",
            )
            return None
        actual = tree_digest(source)
        (run_dir / "source-digest.txt").write_text(actual + "\n", encoding="utf-8")
        if actual != record["bundle_sha256"]:
            self._issue(
                record, stage="handoff", severity="critical", code="bundle_digest_mismatch",
                message=f"Published {record['bundle_sha256']}, observed {actual}.",
                evidence=str(run_dir / "source-digest.txt"),
            )
            return None
        candidate = (CANDIDATES / str(record["case_id"])).resolve()
        if source == candidate:
            return candidate
        if candidate.exists():
            existing = tree_digest(candidate) if candidate.is_dir() else "not-a-directory"
            if existing != actual:
                self._issue(
                    record, stage="staging", severity="critical",
                    code="candidate_path_collision",
                    message=(
                        f"{candidate} already exists with digest {existing}; the ready bundle "
                        f"has digest {actual}. No existing files were overwritten."
                    ),
                    evidence=str(candidate),
                )
                return None
            return candidate
        shutil.copytree(source, candidate)
        copied = tree_digest(candidate)
        if copied != actual:
            self._issue(
                record, stage="staging", severity="critical", code="staged_digest_mismatch",
                message=f"Copy digest {copied} differs from source digest {actual}.",
                evidence=str(candidate),
            )
            return None
        self._event("staged", key, candidate=str(candidate))
        return candidate

    @staticmethod
    def _control_prefix(record: dict[str, Any], candidate: Path) -> str:
        supplied = str(record.get("control_prefix") or "").strip()
        if supplied:
            return supplied
        plan = load_json(candidate / "private" / "score_plan.json", {})
        points = plan.get("points") or plan.get("control_points") or []
        for point in points:
            point_id = str((point or {}).get("id") or "")
            if ".cf." in point_id:
                return point_id.split(".cf.", 1)[0]
        raise ValueError("cannot derive control_prefix from private/score_plan.json")

    @staticmethod
    def _run_command(command: list[str], cwd: Path, prefix: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command, cwd=cwd, text=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
        prefix.with_suffix(".stdout.log").write_text(result.stdout, encoding="utf-8")
        prefix.with_suffix(".stderr.log").write_text(result.stderr, encoding="utf-8")
        atomic_json(prefix.with_suffix(".command.json"), {
            "command": command,
            "cwd": str(cwd),
            "exit_code": result.returncode,
        })
        return result

    def _inspect_episode_scores(
        self, record: dict[str, Any], pair_output: Path,
    ) -> list[dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        score_paths = sorted(pair_output.glob("episodes/*/score.json"))
        if not score_paths:
            self._issue(
                record, stage="runtime", severity="critical",
                code="episode_scores_missing",
                message="The paired command produced no episode score.json files.",
                evidence=str(pair_output), classification="runtime_problem",
            )
            return observations
        for score_path in score_paths:
            score = load_json(score_path, {})
            mode = str(score.get("execution_mode") or "unknown")
            observation = {
                "episode_id": score.get("episode_id"),
                "execution_mode": mode,
                "score_status": score.get("score_status"),
                "score_status_reason": score.get("score_status_reason"),
                "scenario_constructed": score.get("scenario_constructed"),
                "scenario_exposure_complete": score.get("scenario_exposure_complete"),
                "scenario_entry": score.get("scenario_entry"),
                "timed_out": score.get("timed_out"),
                "protocol_valid": score.get("protocol_valid"),
                "gateway_control_valid": score.get("gateway_control_valid"),
                "semantic_task_score": score.get("semantic_task_score"),
                "dynamic_control_score": score.get("dynamic_control_score"),
                "test_point_pass_rate": score.get("test_point_pass_rate"),
                "infrastructure_failures": score.get("infrastructure_failures") or [],
                "score_path": str(score_path),
            }
            observations.append(observation)
            construction_errors = score.get("scenario_construction_errors") or []
            exposure_errors = score.get("scenario_exposure_errors") or []
            dynamic_errors = score.get("dynamic_scenario_errors") or []
            infrastructure = score.get("infrastructure_failures") or []
            if score.get("scenario_constructed") is not True:
                self._issue(
                    record, stage="scenario", severity="critical",
                    code=f"{mode}_scenario_not_constructed",
                    message=json.dumps(construction_errors or ["scenario_constructed=false"], ensure_ascii=False),
                    evidence=str(score_path), classification="case_or_package_problem",
                )
            if infrastructure:
                self._issue(
                    record, stage="infrastructure", severity="high",
                    code=f"{mode}_infrastructure_failure",
                    message=json.dumps(infrastructure, ensure_ascii=False),
                    evidence=str(score_path), classification="infrastructure_problem",
                )
            if score.get("scenario_exposure_complete") is not True:
                self._issue(
                    record, stage="scenario", severity="medium",
                    code=f"{mode}_scenario_exposure_incomplete",
                    message=json.dumps(exposure_errors or dynamic_errors or ["scenario_exposure_complete=false"], ensure_ascii=False),
                    evidence=str(score_path), classification="needs_triage",
                )
            if score.get("score_status") != "scored":
                detail = {
                    "reason": score.get("score_status_reason"),
                    "construction_errors": construction_errors,
                    "exposure_errors": exposure_errors,
                    "dynamic_scenario_errors": dynamic_errors,
                }
                self._issue(
                    record, stage="scoring", severity="medium",
                    code=f"{mode}_episode_unscored",
                    message=json.dumps(detail, ensure_ascii=False),
                    evidence=str(score_path), classification="needs_triage",
                )
            if score.get("timed_out") is True:
                self._issue(
                    record, stage="model_score", severity="low",
                    code=f"{mode}_participant_timeout",
                    message="The participant reached the episode timeout; no automatic retry was made.",
                    evidence=str(score_path), classification="model_observation",
                )
            if score.get("protocol_valid") is False or score.get("gateway_control_valid") is False:
                self._issue(
                    record, stage="protocol", severity="medium",
                    code=f"{mode}_protocol_invalid",
                    message=json.dumps({
                        "protocol_valid": score.get("protocol_valid"),
                        "gateway_control_valid": score.get("gateway_control_valid"),
                        "gateway_notes": score.get("gateway_notes") or [],
                    }, ensure_ascii=False),
                    evidence=str(score_path), classification="participant_or_protocol_observation",
                )
        return observations

    def _process(self, record: dict[str, Any]) -> None:
        key = record_key(record)
        run_dir = RUNS / str(record["case_id"]) / f"r{int(record['revision'])}"
        run_dir.mkdir(parents=True, exist_ok=True)
        self._set(key, status="validating_handoff", started_at=utc_now(), run_dir=str(run_dir))
        problem = self._validate_record(record)
        if problem:
            self._issue(
                record, stage="handoff", severity="critical",
                code="invalid_handoff_contract", message=problem, evidence=str(READY),
            )
            self._set(key, status="rejected", completed_at=utc_now())
            return
        self._set(key, status="staging")
        candidate = self._stage(record, run_dir)
        if candidate is None:
            self._set(key, status="failed", completed_at=utc_now())
            return
        try:
            control_prefix = self._control_prefix(record, candidate)
        except ValueError as exc:
            self._issue(
                record, stage="preflight", severity="critical",
                code="control_prefix_missing", message=str(exc),
                evidence=str(candidate / "private" / "score_plan.json"),
            )
            self._set(key, status="failed", completed_at=utc_now())
            return
        self._set(key, status="preflight", candidate=str(candidate), control_prefix=control_prefix)
        preflight = self._run_command(
            [
                str(PYTHON), "-m", "async_rbench.cli", "case-promote",
                "--candidate", str(record["case_id"]),
                "--control-prefix", control_prefix, "--dry-run",
            ], ROOT, run_dir / "preflight", max(600, self.timeout),
        )
        if preflight.returncode != 0:
            detail = (preflight.stderr or preflight.stdout).strip()[-8000:]
            self._issue(
                record, stage="preflight", severity="critical",
                code="candidate_preflight_failed", message=detail or "preflight exited nonzero",
                evidence=str(run_dir / "preflight.stderr.log"),
            )
            self._set(key, status="failed", completed_at=utc_now())
            return
        quality_output = run_dir / "quality-preflight"
        self._set(key, status="quality_preflight", quality_output=str(quality_output))
        try:
            quality = self._run_command(
                [
                    str(PYTHON), "-m", "async_rbench.cli", "candidate-quality-preflight",
                    "--candidate", str(record["case_id"]),
                    "--control-prefix", control_prefix,
                    "--output", str(quality_output),
                    "--seed", str(2026000 + int(record["revision"])),
                ], ROOT, run_dir / "quality-preflight-command", self.timeout * 3,
            )
        except subprocess.TimeoutExpired as exc:
            self._issue(
                record, stage="quality_preflight", severity="critical",
                code="quality_preflight_timeout",
                message=f"Independent quality preflight exceeded {exc.timeout} seconds.",
                evidence=str(run_dir), classification="case_or_runtime_problem",
            )
            self._set(key, status="failed", completed_at=utc_now())
            return
        quality_report = load_json(quality_output / "quality-execution-report.json", {})
        if quality.returncode != 0 or quality_report.get("passed") is not True:
            detail = {
                "errors": quality_report.get("errors") or [],
                "variants": quality_report.get("variants") or [],
                "negative_mutations": quality_report.get("negative_mutations") or [],
                "stderr_tail": (quality.stderr or "")[-4000:],
            }
            self._issue(
                record, stage="quality_preflight", severity="critical",
                code="independent_quality_gate_failed",
                message=json.dumps(detail, ensure_ascii=False),
                evidence=str(quality_output / "quality-execution-report.json"),
                classification="case_or_package_problem",
            )
            self._set(key, status="failed", completed_at=utc_now())
            return
        current_digest = tree_digest(candidate)
        if current_digest != record["bundle_sha256"]:
            self._issue(
                record, stage="bundle_integrity", severity="critical",
                code="bundle_changed_during_quality_preflight",
                message=f"Expected {record['bundle_sha256']}, observed {current_digest}.",
                evidence=str(candidate), classification="case_or_consumer_integrity_problem",
            )
            self._set(key, status="failed", completed_at=utc_now())
            return
        if not self.config.is_file():
            self._issue(
                record, stage="launch", severity="critical", code="model_config_missing",
                message=f"Configured model profile does not exist: {self.config}",
            )
            self._set(key, status="failed", completed_at=utc_now())
            return
        pair_output = run_dir / "model-pair"
        self._set(key, status="running", launched_at=utc_now(), pair_output=str(pair_output))
        self._event("model_pair_started", key, case_id=record["case_id"])
        try:
            pair = self._run_command(
                [
                    str(PYTHON), "-m", "async_rbench.cli", "candidate-family-pair-smoke",
                    "--candidate", str(record["case_id"]),
                    "--control-prefix", control_prefix,
                    "--output", str(pair_output),
                    "--seed", str(2026000 + int(record["revision"])),
                    "--timeout", str(self.timeout),
                    "--config", str(self.config),
                ], ROOT, run_dir / "model-pair", self.timeout * 2 + 1800,
            )
        except subprocess.TimeoutExpired as exc:
            self._issue(
                record, stage="runtime", severity="high", code="pair_command_timeout",
                message=f"Paired run exceeded the consumer ceiling: {exc.timeout} seconds.",
                evidence=str(run_dir),
            )
            self._set(key, status="failed", completed_at=utc_now())
            return
        results = load_json(pair_output / "pair-results.json", {})
        if pair.returncode != 0:
            detail = (pair.stderr or pair.stdout).strip()[-8000:]
            if results:
                self._issue(
                    record, stage="scenario", severity="medium",
                    code="pair_not_qualified",
                    message="The paired development run completed but did not qualify both scenarios.",
                    evidence=str(pair_output / "pair-results.json"), classification="needs_triage",
                )
            else:
                self._issue(
                    record, stage="runtime", severity="high", code="pair_command_failed",
                    message=detail or "paired run exited nonzero without pair-results.json",
                    evidence=str(run_dir / "model-pair.stderr.log"), classification="runtime_problem",
                )
        episode_scores = self._inspect_episode_scores(record, pair_output)
        final_digest = tree_digest(candidate)
        integrity_ok = final_digest == record["bundle_sha256"]
        if not integrity_ok:
            self._issue(
                record, stage="bundle_integrity", severity="critical",
                code="bundle_changed_during_model_pair",
                message=f"Expected {record['bundle_sha256']}, observed {final_digest}; run invalidated.",
                evidence=str(candidate), classification="case_or_consumer_integrity_problem",
            )
        qualification_errors = pair_qualification_errors(pair.returncode, results)
        passed = not qualification_errors
        if qualification_errors:
            self._issue(
                record, stage="scenario", severity="high",
                code="strict_pair_qualification_failed",
                message=json.dumps(qualification_errors, ensure_ascii=False),
                evidence=str(pair_output / "pair-results.json"),
                classification="case_or_model_pair_problem",
            )
        completed = bool(results) and bool(episode_scores) and integrity_ok
        self._set(
            key,
            status=(
                "passed" if passed else
                "completed_with_findings" if completed else
                "failed"
            ),
            completed_at=utc_now(),
            pair_exit_code=pair.returncode,
            pair_passed=results.get("passed"),
            strict_pair_qualification_passed=passed,
            strict_pair_qualification_errors=qualification_errors,
            postrun_bundle_sha256=final_digest,
            bundle_integrity_passed=integrity_ok,
            quality_preflight_passed=True,
            scores=episode_scores,
        )
        self._event("completed", key, passed=passed, completed=completed, case_id=record["case_id"])

    def close(self, *, wait: bool) -> None:
        self.pool.shutdown(wait=wait, cancel_futures=False)
        self._save_state()


def acquire_singleton() -> int:
    INTAKE.mkdir(parents=True, exist_ok=True)
    try:
        handle = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"consumer already appears to be running: {LOCK}") from exc
    os.write(handle, f"pid={os.getpid()} started={utc_now()}\n".encode("utf-8"))
    return handle


def release_singleton(handle: int) -> None:
    os.close(handle)
    LOCK.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Consume current records, then exit after workers finish")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=2400)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 8:
        parser.error("--workers must be between 1 and 8")
    if args.poll_seconds < 0.25:
        parser.error("--poll-seconds must be at least 0.25")
    if not PYTHON.is_file():
        parser.error(f"benchmark Python runtime is missing: {PYTHON}")
    handle = acquire_singleton()
    consumer = IntakeConsumer(config=args.config, timeout=args.timeout, workers=args.workers)
    try:
        while True:
            consumer.discover()
            consumer.reap()
            if args.once:
                break
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        return 130
    finally:
        consumer.close(wait=args.once)
        release_singleton(handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
