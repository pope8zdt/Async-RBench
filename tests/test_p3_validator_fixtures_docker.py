from __future__ import annotations

import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import uuid

import pytest
import yaml

from async_rbench.evaluation.result_contract import validate_payload_contract
from async_rbench.spec import load_case


ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.getenv("ASYNC_RBENCH_RUN_DOCKER_TESTS") != "1",
        reason="opt-in Docker validator fixture tests",
    ),
]


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), check=check, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


@contextmanager
def _case_container(case_id: str):
    tag = f"async_rbench-p3-{case_id}:fixture"
    name = f"dtb2-p3-{case_id[:24]}-{uuid.uuid4().hex[:8]}"
    task = ROOT / "cases" / case_id / "task"
    _run("docker", "build", "-t", tag, str(task))
    _run("docker", "run", "-d", "--name", name, tag)
    try:
        yield name
    finally:
        _run("docker", "rm", "-f", name, check=False)


def _private(case_id: str) -> dict:
    return yaml.safe_load(
        (ROOT / "cases" / case_id / "private" / "private_case.yaml").read_text(
            encoding="utf-8"
        )
    )


def _workstream(case_id: str, workstream_id: str) -> dict:
    case = load_case(ROOT / "cases" / case_id / "public_case.yaml").raw
    return next(
        item for item in case["delegation_workstreams"] if item["id"] == workstream_id
    )


def _payload(evidence: dict, files: list[str]) -> dict:
    return {"summary": "validator fixture", "evidence": evidence, "files": files}


def _validator(container: str, case_id: str, workstream_id: str, payload: dict) -> int:
    command = _private(case_id)["workstream_bindings"][workstream_id]["validator_command"]
    encoded = base64.b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).decode()
    return _run(
        "docker", "exec", "-e", f"ASYNC_RBENCH_RESULT_PAYLOAD_B64={encoded}",
        container, "bash", "-lc", command, check=False,
    ).returncode


def _json(container: str, path: str) -> dict | list:
    return json.loads(_run("docker", "exec", container, "cat", path).stdout)


def _assert_positive_and_structural_negative(
    container: str, case_id: str, workstream_id: str, payload: dict,
) -> None:
    workstream = _workstream(case_id, workstream_id)
    positive_codes, _ = validate_payload_contract(workstream, {"payload": payload})
    assert positive_codes == []
    assert _validator(container, case_id, workstream_id, payload) == 0
    negative = json.loads(json.dumps(payload))
    first_field = workstream["required_evidence_fields"][0]
    negative["evidence"].pop(first_field)
    negative_codes, _ = validate_payload_contract(workstream, {"payload": negative})
    assert "missing_required_evidence" in negative_codes


def test_data_recovery_wal_validator_fixture() -> None:
    case_id = "data-recovery-service"
    with _case_container(case_id) as container:
        solution = ROOT / "cases" / case_id / "task" / "upstream_solutions" / "db-wal-recovery.sh"
        _run("docker", "cp", str(solution), f"{container}:/tmp/solve.sh")
        _run("docker", "exec", container, "bash", "/tmp/solve.sh")
        payload = _payload({
            "final_row_count": 11,
            "wal_file_initially_present": True,
            "wal_file_consumed_during_recovery": True,
        }, ["/app/recovered.json"])
        _assert_positive_and_structural_negative(container, case_id, "wal_recovery", payload)
        _run(
            "docker", "exec", container, "python3", "-c",
            "import json; p='/app/recovered.json'; d=json.load(open(p)); "
            "json.dump(d[:-1],open(p,'w'))",
        )
        assert _validator(container, case_id, "wal_recovery", payload) != 0


def test_distributed_runtime_validator_fixtures() -> None:
    case_id = "distributed-model-runtime"
    with _case_container(case_id) as container:
        solution = ROOT / "cases" / case_id / "task" / "upstream_solutions" / "torch-tensor-parallelism.sh"
        _run("docker", "cp", str(solution), f"{container}:/tmp/solve.sh")
        _run("docker", "exec", container, "bash", "/tmp/solve.sh")
        implement = _payload({
            "profile_version": "v1", "backend": "gloo", "world_size": 4,
            "verification_passed": True,
        }, ["/app/parallel_linear.py"])
        _assert_positive_and_structural_negative(
            container, case_id, "implement_tp", implement,
        )
        _run(
            "docker", "exec", container, "bash", "-lc",
            "printf 'raise RuntimeError(\"corrupt fixture\")\n' > /app/parallel_linear.py",
        )
        assert _validator(container, case_id, "implement_tp", implement) != 0
        backend = _payload({
            "profile_version": "v2", "world_size": 2,
            "tensor_parallel_supported": False,
            "pipeline_parallel_supported": True,
            "recommended_backend": "pipeline",
        }, [])
        _assert_positive_and_structural_negative(
            container, case_id, "select_backend", backend,
        )
        wrong_backend = json.loads(json.dumps(backend))
        wrong_backend["evidence"]["recommended_backend"] = "gloo"
        assert _validator(container, case_id, "select_backend", wrong_backend) != 0


def test_git_secret_recovery_validator_fixture() -> None:
    case_id = "git-conflict-and-cleanup-closure"
    with _case_container(case_id) as container:
        _run(
            "docker", "exec", container, "python3",
            "/app/task_file/scripts/scan_objects.py",
        )
        _run(
            "docker", "exec", container, "python3",
            "/app/task_file/scripts/recover_secret.py", "--report",
            "/app/output_data/scan_reports/object_db.json",
        )
        recovery = _json(container, "/app/output_data/recovery_report.json")
        payload = _payload({
            **recovery,
            "report_path": "/app/output_data/recovery_report.json",
        }, ["/app/output_data/recovery_report.json", "/app/secret.txt"])
        _assert_positive_and_structural_negative(
            container, case_id, "secret_recovery", payload,
        )
        _run(
            "docker", "exec", container, "bash", "-lc",
            "printf 'wrong-secret\n' > /app/secret.txt",
        )
        assert _validator(container, case_id, "secret_recovery", payload) != 0


def test_scheduler_validator_fixtures() -> None:
    case_id = "scheduler-selective-replan"
    with _case_container(case_id) as container:
        _run(
            "docker", "exec", container, "python3",
            "/app/task_file/scripts/baseline_packer.py",
        )
        _run(
            "docker", "exec", container, "bash", "-lc",
            "python3 /app/task_file/scripts/validate_plan.py "
            "--requests-bucket1 /app/task_file/input_data/requests_bucket_1.jsonl "
            "--requests-bucket2 /app/task_file/input_data/requests_bucket_2.jsonl "
            "--plan-b1 /app/task_file/output_data/plan_b1.jsonl "
            "--plan-b2 /app/task_file/output_data/plan_b2.jsonl --shape-budget 8 "
            "--out /tmp/combined.json || true",
        )
        report = _json(container, "/tmp/combined.json")
        for number, item in enumerate(report["results"], start=1):
            report_path = f"/app/task_file/output_data/validator_reports/bucket{number}.json"
            encoded = base64.b64encode(json.dumps(item).encode()).decode()
            _run(
                "docker", "exec", container, "bash", "-lc",
                f"mkdir -p /app/task_file/output_data/validator_reports && "
                f"echo {encoded} | base64 -d > {report_path}",
            )
            prefix = f"bucket{number}"
            evidence = {
                f"{prefix}_passes": item["passes"],
                f"{prefix}_plan_revision": item["plan_revision"],
                f"{prefix}_pad_ratio": item["metrics"]["pad_ratio"],
                f"{prefix}_cost": item["metrics"]["cost"],
            }
            if number == 2:
                evidence["source_receipt"] = item["authority_receipt"]
            payload = _payload(evidence, [report_path])
            _assert_positive_and_structural_negative(
                container, case_id, f"bucket{number}_validator", payload,
            )
            _run(
                "docker", "exec", container, "python3", "-c",
                f"import json; p={report_path!r}; d=json.load(open(p)); "
                "d['plan_revision']='0'*64; json.dump(d,open(p,'w'))",
            )
            assert _validator(
                container, case_id, f"bucket{number}_validator", payload,
            ) != 0


def test_secure_release_validator_fixtures() -> None:
    case_id = "secure-release"
    with _case_container(case_id) as container:
        setup = r'''
set -e
root=/tmp/nginx-git-infrastructure
mkdir -p "$root/nginx" "$root/ssh" "$root/git/repositories/main.git/hooks" "$root/git/repositories/dev.git/hooks"
printf 'Welcome to the benchmark webserver\n' > "$root/nginx/index.html"
printf 'Page not found - Please check your URL\n' > "$root/nginx/404.html"
printf 'PasswordAuthentication yes\n' > "$root/ssh/sshd_config"
cat > "$root/nginx/nginx.conf" <<'EOF'
http { limit_req_zone $binary_remote_addr zone=req:10m rate=10r/s; log_format detailed '$time_local $request_method $status "$http_user_agent"'; server { limit_req zone=req burst=10; access_log /var/log/nginx/benchmark-access.log detailed; error_log /var/log/nginx/benchmark-error.log; error_page 404 /404.html; } }
EOF
printf '#!/bin/sh\ncp index.html /var/www/release-main/index.html\n' > "$root/git/repositories/main.git/hooks/post-receive"
printf '#!/bin/sh\ncp index.html /var/www/release-dev/index.html\n' > "$root/git/repositories/dev.git/hooks/post-receive"
chmod +x "$root"/git/repositories/*/hooks/post-receive
'''
        _run("docker", "exec", container, "bash", "-lc", setup)
        files = [
            "/tmp/nginx-git-infrastructure/nginx/nginx.conf",
            "/tmp/nginx-git-infrastructure/nginx/index.html",
            "/tmp/nginx-git-infrastructure/nginx/404.html",
            "/tmp/nginx-git-infrastructure/ssh/sshd_config",
            "/tmp/nginx-git-infrastructure/git/repositories/main.git/hooks/post-receive",
            "/tmp/nginx-git-infrastructure/git/repositories/dev.git/hooks/post-receive",
        ]
        payload = _payload({
            "git_repositories_created": True,
            "post_receive_hooks_configured": True,
            "rate_limiting_enabled": True,
            "detailed_logging_enabled": True,
            "custom_404_enabled": True,
            "password_ssh_auth_enabled": True,
        }, files)
        _assert_positive_and_structural_negative(
            container, case_id, "release_infrastructure", payload,
        )
        _run(
            "docker", "exec", container, "bash", "-lc",
            "printf 'wrong content\n' > /tmp/nginx-git-infrastructure/nginx/index.html",
        )
        assert _validator(
            container, case_id, "release_infrastructure", payload,
        ) != 0

        fixed = r'''def _hkey(key):
    key = touni(key)
    if "\n" in key or "\r" in key or "\0" in key:
        raise ValueError("Header names must not contain control characters: %r" % key)
    return key.title().replace('_', '-')


def _hval(value):
    value = touni(value)
    if "\n" in value or "\r" in value or "\0" in value:
        raise ValueError("Header value must not contain control characters: %r" % value)
    return value


'''
        edit_code = (
            "from pathlib import Path; "
            "p=Path('/app/repo/bottle.py'); s=p.read_text(); "
            "start=s.index('def _hkey(key):'); "
            "end=s.index('class HeaderProperty:',start); "
            f"fixed={fixed!r}; "
            "Path('/tmp/bottle.fixed.py').write_text(s[:start]+fixed+s[end:])"
        )
        _run("docker", "exec", container, "python3", "-c", edit_code)
        _run(
            "docker", "exec", container, "bash", "-lc",
            "mkdir -p /app/deliverables; "
            "diff -u --label a/bottle.py --label b/bottle.py "
            "/app/repo/bottle.py /tmp/bottle.fixed.py > "
            "/app/deliverables/bottle_crlf_fix.patch || test $? -eq 1; "
            "printf 'def test_contract_fixture():\n    assert True\n' > "
            "/app/deliverables/validation_test.py",
        )
        heads = _run(
            "docker", "exec", container, "bash", "-lc",
            "git -C /app/repo rev-parse main; git -C /app/repo rev-parse dev",
        ).stdout.splitlines()
        patch_payload = _payload({
            "tested_main_head": heads[0],
            "tested_dev_head": heads[1],
            "crlf_test_result": "passed",
            "patch_status": "applies to main and dev",
        }, [
            "/app/deliverables/bottle_crlf_fix.patch",
            "/app/deliverables/validation_test.py",
        ])
        _assert_positive_and_structural_negative(
            container, case_id, "security_patch", patch_payload,
        )
        _run(
            "docker", "exec", container, "bash", "-lc",
            "printf 'not a patch\n' > /app/deliverables/bottle_crlf_fix.patch",
        )
        assert _validator(
            container, case_id, "security_patch", patch_payload,
        ) != 0
