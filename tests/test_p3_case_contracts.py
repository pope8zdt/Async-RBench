from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _public(case_id: str) -> dict:
    return yaml.safe_load(
        (ROOT / "cases" / case_id / "public_case.yaml").read_text(encoding="utf-8")
    )


def _private(case_id: str) -> dict:
    return yaml.safe_load(
        (ROOT / "cases" / case_id / "private" / "private_case.yaml").read_text(
            encoding="utf-8"
        )
    )


def test_backend_recommendation_has_public_non_answer_vocabulary() -> None:
    workstream = next(
        item for item in _public("distributed-model-runtime")["workstreams"]
        if item["id"] == "select_backend"
    )
    assert workstream["evidence_schema"]["recommended_backend"]["enum"] == [
        "tensor", "pipeline", "data",
    ]


def test_git_authority_workstreams_name_the_public_generators() -> None:
    workstreams = {
        item["id"]: item for item in _public("git-conflict-and-cleanup-closure")["workstreams"]
    }
    assert "/app/task_file/scripts/scan_objects.py" in workstreams[
        "object_database_scanner"
    ]["task"]
    assert "/app/task_file/scripts/recover_secret.py" in workstreams[
        "secret_recovery"
    ]["task"]


def test_release_infrastructure_contract_covers_every_claimed_surface() -> None:
    public = next(
        item for item in _public("secure-release")["workstreams"]
        if item["id"] == "release_infrastructure"
    )
    required = set(public["required_files"])
    assert {
        "/tmp/nginx-git-infrastructure/nginx/nginx.conf",
        "/tmp/nginx-git-infrastructure/nginx/index.html",
        "/tmp/nginx-git-infrastructure/nginx/404.html",
        "/tmp/nginx-git-infrastructure/ssh/sshd_config",
        "/tmp/nginx-git-infrastructure/git/repositories/main.git/hooks/post-receive",
        "/tmp/nginx-git-infrastructure/git/repositories/dev.git/hooks/post-receive",
    } <= required
    command = _private("secure-release")["workstream_bindings"][
        "release_infrastructure"
    ]["validator_command"]
    for marker in (
        "PasswordAuthentication", "rate=10r/s", "burst=10",
        "benchmark-access.log", "benchmark-error.log", "error_page",
    ):
        assert marker in command
