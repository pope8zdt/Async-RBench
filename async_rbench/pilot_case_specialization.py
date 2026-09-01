from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _semantic_subset(case_dir: Path, ids: list[str], prefix: str) -> None:
    path = case_dir / "task/tests/semantic_checks.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    by_id = {str(item["id"]): item for item in source.get("checks") or []}
    checks: list[dict[str, Any]] = []
    for source_id in ids:
        item = dict(by_id[source_id])
        item["id"] = prefix + source_id.removeprefix("sr")
        checks.append(item)
    path.write_text(
        json.dumps({"version": "4", "checks": checks}, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_instruction(case_dir: Path, instruction: str, category: str) -> None:
    path = case_dir / "task/task.yaml"
    task = _read_yaml(path)
    task["instruction"] = instruction.strip()
    task["category"] = category
    task["difficulty"] = "hard"
    _write_yaml(path, task)


def specialize_gaia_workflow(case_dir: Path) -> None:
    """Remove an impossible child that tried to observe future main-workspace state."""
    public_path = case_dir / "public_case.yaml"
    public = _read_yaml(public_path)
    public["workstreams"] = [
        item for item in public["workstreams"]
        if item.get("id") != "world_state_validator"
    ]
    _write_yaml(public_path, public)

    private_path = case_dir / "private/private_case.yaml"
    private = _read_yaml(private_path)
    private["workstream_bindings"].pop("world_state_validator", None)
    private["result_contract"]["allowed_result_kinds"] = [
        value for value in private["result_contract"]["allowed_result_kinds"]
        if value != "result_05"
    ]
    private["information_sufficiency"] = [
        item for item in private["information_sufficiency"]
        if item.get("workstream_id") != "world_state_validator"
    ]
    _write_yaml(private_path, private)


def specialize_nginx_workflow(case_dir: Path) -> None:
    """Give linear the authority first while async exposes config/content first."""
    public_path = case_dir / "public_case.yaml"
    public = _read_yaml(public_path)
    workstreams = {str(item["id"]): item for item in public["workstreams"]}
    workstreams["port_authority"]["task"] = (
        "Read the evaluator-provided /app/events/port-authority.json receipt in this "
        "isolated workstream. Confirm that a listener currently occupies port 8080, "
        "then report authority_receipt, observed_port, occupied, and the receipt's "
        "evaluator-normalized observed_service label exactly. Raw process names are "
        "only occupancy evidence and must not replace the normalized receipt label."
    )
    public["workstreams"] = [
        workstreams["port_authority"],
        workstreams["config_author"],
        workstreams["content_builder"],
    ]
    _write_yaml(public_path, public)
    task_path = case_dir / "task/task.yaml"
    task = _read_yaml(task_path)
    task["instruction"] = str(task["instruction"]).replace(
        "Results may complete in any order and\nbecome usable only after gateway delivery.",
        "Results may complete in any order and\nbecome usable only after gateway delivery. Bring up and record the service as soon as\nthe configuration and page candidates are usable; the independent port inspection\nmay still be running.",
    )
    task["instruction"] += r'''

Availability audit requirement: when the configuration and both page candidates
arrive before the port inspection, the first working service is an actual early
deliverable, not scratch work. Record versioned checkpoints for nginx_config,
site_content, runtime_state and access_log after its first HTTP/log probe while
the independent inspection is still pending. The inspection is downstream of
this availability audit and cannot publish its result until all four early
checkpoints are recorded, so do not wait for the inspection before checkpointing.
If a later observation changes the
valid runtime owner, retain that earlier checkpoint in the audit trail and record
new affected runtime/log versions after the final probe.
'''
    _write_yaml(task_path, task)
    private_path = case_dir / "private/private_case.yaml"
    private = _read_yaml(private_path)
    for event in private["scenarios"]["async"]["events"]:
        if event.get("id") == "np_a_port":
            event["max_hold_main_actions"] = 50
            # Make the late result a real live interruption in the main
            # workspace. The authority child starts from the initial decoy
            # snapshot; immediately before its result is delivered the
            # evaluator restores that same conflicting owner on the main port.
            # Private before/after observations prove the transition occurred.
            event["intervention"] = {
                "type": "main_workspace_live_dependency_change",
                "mutation_command": (
                    "set -eu; fuser -k 8080/tcp >/dev/null 2>&1 || true; "
                    "nohup python3 -m http.server 8080 --directory /tmp/decoy "
                    ">/tmp/decoy.log 2>&1 & echo $! >/run/async-rbench-decoy.pid; "
                    "for i in $(seq 1 50); do "
                    "curl -fsS http://127.0.0.1:8080/ 2>/dev/null | "
                    "grep -q 'decoy service' && exit 0; sleep 0.1; done; exit 1"
                ),
                "observer_commands": {
                    "runtime_state": (
                        "python3 -c \"import hashlib,urllib.request; "
                        "r=urllib.request.urlopen('http://127.0.0.1:8080/',timeout=3); "
                        "b=r.read(); s=r.headers.get('Server','').lower(); "
                        "print(hashlib.sha256(s.encode()+b'\\0'+b).hexdigest())\""
                    ),
                },
                "required_changed_artifacts": ["runtime_state"],
                "timeout_sec": 30,
            }
    _write_yaml(private_path, private)
    dockerfile_path = case_dir / "task/Dockerfile"
    dockerfile_path.write_text(
        dockerfile_path.read_text(encoding="utf-8").replace(
            "COPY events /app/events\n", ""
        ),
        encoding="utf-8",
    )
    oracle_path = case_dir / "task/oracle.sh"
    oracle_path.write_text(
        oracle_path.read_text(encoding="utf-8").replace(
            "json.load(open('/app/events/port-authority.json'))['authority_receipt']",
            "'np-port-authority-63f3b0c0921a4d7e'",
        ),
        encoding="utf-8",
    )


def specialize_multi_source_workflow(case_dir: Path) -> None:
    """Transform the locked Terminal-Bench merger into a late-schema case."""
    task_dir = case_dir / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "Dockerfile", "docker-compose.yaml", "run-tests.sh", "solution.sh",
        "task.yaml", "tests", "data",
    ):
        source = case_dir / name
        if not source.exists():
            continue
        target = task_dir / name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        shutil.move(str(source), str(target))

    public = {
        "format_version": 2,
        "case_id": "multi-source-late-schema",
        "title": "Merge three sources while reconciling a late authoritative schema result",
        "task_instruction_path": "task/task.yaml",
        "source_tasks": [{
            "id": "multi-source-data-merger",
            "upstream_path": "upstream/terminal-bench/original-tasks-locked/multi-source-data-merger",
            "benchmark": "terminal-bench",
        }],
        "milestones": [
            {"id": "profile_sources", "depends_on": []},
            {"id": "produce_provisional_merge", "depends_on": ["profile_sources"]},
            {"id": "consume_schema_authority", "depends_on": ["produce_provisional_merge"]},
            {"id": "repair_conflict_report", "depends_on": ["consume_schema_authority"]},
            {"id": "reverify_merge", "depends_on": ["repair_conflict_report"]},
        ],
        "artifacts": [
            {"id": "merged_dataset", "path": "/app/merged_users.parquet"},
            {"id": "conflict_report", "path": "/app/conflicts.json"},
            {"id": "merge_lineage", "path": "/app/merge-lineage.json"},
        ],
        "workstreams": [
            {
                "id": "schema_authority",
                "task": (
                    "Read /app/events/schema-authority.json and independently report its "
                    "authority_receipt, required_user_id_type and required_conflict_count."
                ),
                "targets": ["conflict_report", "merge_lineage"],
                "expected_output": "Receipt-bound authoritative conflict-report schema.",
                "priority": "high",
                "required_evidence_fields": [
                    "authority_receipt", "required_user_id_type", "required_conflict_count",
                ],
                "evidence_schema": {
                    "authority_receipt": {"type": "string", "pattern": "ms-schema-[0-9a-f]{16}"},
                    "required_user_id_type": {"type": "string", "const": "integer"},
                    "required_conflict_count": {"type": "integer", "const": 3},
                },
                "allowed_files": [], "required_files": [], "public_result_contract": {},
            },
            {
                "id": "source_profiler",
                "task": (
                    "Inspect all three public input sources, construct the priority-resolved "
                    "four-row dataset, and write it to /app/work/provisional-merged-users.parquet. "
                    "Report unique_user_count=4 and source_priority='source_a>source_b>source_c'."
                ),
                "targets": ["merged_dataset"],
                "expected_output": "Promotable provisional dataset plus source coverage evidence.",
                "priority": "normal",
                "required_evidence_fields": ["unique_user_count", "source_priority"],
                "evidence_schema": {
                    "unique_user_count": {"type": "integer", "const": 4},
                    "source_priority": {"type": "string", "const": "source_a>source_b>source_c"},
                },
                "allowed_files": ["/app/work/provisional-merged-users.parquet"],
                "required_files": ["/app/work/provisional-merged-users.parquet"],
                "public_result_contract": {},
            },
            {
                "id": "provisional_report_reviewer",
                "task": (
                    "Reproduce the source trajectory's provisional conflict-report observation "
                    "and report provisional_user_id_type='string' and provisional_conflict_count=3. "
                    "Copy the evaluator-provided /app/events/provisional-conflicts.json to "
                    "/app/work/provisional-conflicts.json. This is a promotable early artifact, "
                    "not final schema authority."
                ),
                "targets": ["conflict_report"],
                "expected_output": "A provisional schema observation that must later be arbitrated.",
                "priority": "normal",
                "required_evidence_fields": ["provisional_user_id_type", "provisional_conflict_count"],
                "evidence_schema": {
                    "provisional_user_id_type": {"type": "string", "const": "string"},
                    "provisional_conflict_count": {"type": "integer", "const": 3},
                },
                "allowed_files": ["/app/work/provisional-conflicts.json"],
                "required_files": ["/app/work/provisional-conflicts.json"],
                "public_result_contract": {},
            },
        ],
        "public_checks": [],
    }
    _write_yaml(case_dir / "public_case.yaml", public)

    private_dir = case_dir / "private"
    private_dir.mkdir(exist_ok=True)
    private = {
        "format_version": 2,
        "case_id": "multi-source-late-schema",
        "classification": {
            "primary_event_theme": "delayed_authoritative_result",
            "secondary_event_themes": ["conflicting_valid_results"],
            "async_scenario_class": "result_eventful",
        },
        "capabilities": ["late_revision_adoption", "selective_invalidation", "verification_reopen"],
        "workstream_bindings": {
            "source_profiler": {
                "result_kind": "result_01",
                "validator_command": (
                    "python3 -c \"import base64,json,os; "
                    "e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; "
                    "assert e['unique_user_count']==4 and e['source_priority']=='source_a>source_b>source_c'; "
                    "import pandas as pd; d=pd.read_parquet('/app/work/provisional-merged-users.parquet'); "
                    "assert set(d.user_id)=={101,102,103,104}\""
                ),
                "validator_timeout_sec": 120,
                "private_evidence_schema": public["workstreams"][1]["evidence_schema"],
                "event_assets": [],
            },
            "provisional_report_reviewer": {
                "result_kind": "result_02",
                "validator_command": (
                    "python3 -c \"import base64,json,os; "
                    "e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; "
                    "assert e['provisional_user_id_type']=='string' and e['provisional_conflict_count']==3; "
                    "r=json.load(open('/app/work/provisional-conflicts.json')); "
                    "assert r['total_conflicts']==3 and all(type(x['user_id']) is str for x in r['conflicts'])\""
                ),
                "validator_timeout_sec": 120,
                "private_evidence_schema": public["workstreams"][2]["evidence_schema"],
                "event_assets": ["/app/events/provisional-conflicts.json"],
            },
            "schema_authority": {
                "result_kind": "result_03",
                "validator_command": (
                    "python3 -c \"import base64,json,os; "
                    "e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; "
                    "a=json.load(open('/app/events/schema-authority.json')); "
                    "assert e['authority_receipt']==a['authority_receipt']; "
                    "assert e['required_user_id_type']=='integer' and e['required_conflict_count']==3\""
                ),
                "validator_timeout_sec": 120,
                "private_evidence_schema": public["workstreams"][0]["evidence_schema"],
                "event_assets": ["/app/events/schema-authority.json"],
            },
        },
        "result_contract": {
            "allowed_result_kinds": ["result_01", "result_02", "result_03"],
            "rule": "The schema receipt is evaluator-owned authority; provisional string typing is non-authoritative.",
        },
        "authoritative_result_kind": "result_03",
        "superseded_result_kind": "result_02",
        "scenarios": {"linear": {"events": []}, "async": {"events": [
            {"id": "ms_a_profile", "at": 2, "result": "result_01", "invalidates_artifacts": [], "reopens_milestones": []},
            {"id": "ms_a_provisional", "at": 3, "result": "result_02", "invalidates_artifacts": [], "reopens_milestones": []},
            {"id": "ms_a_authority", "result": "result_03",
             "invalidates_artifacts": ["conflict_report", "merge_lineage"],
             "reopens_milestones": ["repair_conflict_report", "reverify_merge"]},
        ]}},
        "artifact_observers": {
            "merged_dataset": "sha256sum /app/merged_users.parquet | awk '{print $1}'",
            "conflict_report": "sha256sum /app/conflicts.json | awk '{print $1}'",
            "merge_lineage": "sha256sum /app/merge-lineage.json | awk '{print $1}'",
        },
        "hidden_checks": {
            "merged_exact": "python3 -c \"import pandas as pd; d=pd.read_parquet('/app/merged_users.parquet'); assert set(d.user_id)=={101,102,103,104}\"",
            "conflict_schema": "python3 -c \"import json; r=json.load(open('/app/conflicts.json')); assert r['total_conflicts']==3 and all(type(x['user_id']) is int for x in r['conflicts'])\"",
            "authority_lineage": "python3 -c \"import json; x=json.load(open('/app/merge-lineage.json')); assert x['authority_receipt']=='ms-schema-71c4a29e8b16d053' and x['reverified_after_authority'] is True\"",
        },
        "reverification_anchors": {
            "merged_exact": ["result_01"],
            "conflict_schema": ["result_03"],
            "authority_lineage": ["result_03"],
        },
        "stale_predicate": None, "stale_revalidation": {},
        "information_sufficiency": [
            {"workstream_id": "source_profiler", "public_inputs": ["/data/source_a/users.json", "/data/source_b/users.csv", "/data/source_c/users.parquet"], "required_output_fields": ["unique_user_count", "source_priority"], "review_status": "reviewed"},
            {"workstream_id": "provisional_report_reviewer", "public_inputs": ["source trajectory evidence steps 9-13"], "required_output_fields": ["provisional_user_id_type", "provisional_conflict_count"], "review_status": "reviewed"},
            {"workstream_id": "schema_authority", "public_inputs": ["/app/events/schema-authority.json"], "required_output_fields": ["authority_receipt", "required_user_id_type", "required_conflict_count"], "review_status": "reviewed"},
        ],
        "legacy_metadata": {"implementation": "real-trajectory-derived"},
    }
    _write_yaml(private_dir / "private_case.yaml", private)

    events = task_dir / "events"
    events.mkdir(exist_ok=True)
    (events / "schema-authority.json").write_text(json.dumps({
        "authority_receipt": "ms-schema-71c4a29e8b16d053",
        "required_user_id_type": "integer",
        "required_conflict_count": 3,
    }, indent=2) + "\n", encoding="utf-8")
    (events / "provisional-conflicts.json").write_text(json.dumps({
        "total_conflicts": 3,
        "conflicts": [
            {
                "user_id": "101", "field": "name",
                "values": {"source_a": "John Doe", "source_c": "John D."},
                "selected": "John Doe",
            },
            {
                "user_id": "101", "field": "email",
                "values": {
                    "source_a": "john@a.com", "source_b": "john@b.com",
                    "source_c": "john@c.com",
                },
                "selected": "john@a.com",
            },
            {
                "user_id": "101", "field": "created_date",
                "values": {
                    "source_a": "2024-01-15", "source_b": "2024-01-10",
                    "source_c": "2024-01-20",
                },
                "selected": "2024-01-15",
            },
        ],
    }, indent=2) + "\n", encoding="utf-8")

    dockerfile = (task_dir / "Dockerfile").read_text(encoding="utf-8")
    dockerfile += (
        "\nRUN pip install --no-cache-dir pytest==8.4.1\n"
        # The evaluation runner launches the image directly (without Compose),
        # so a persistent default command is part of the runnable case contract.
        "CMD [\"/bin/sh\", \"-lc\", \"sleep infinity\"]\n"
    )
    (task_dir / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    # The upstream Compose file is a Terminal-Bench harness template whose
    # image/container/volume fields become empty without T_BENCH_* variables.
    # Production cases must be runnable by this benchmark's own preflight.
    (task_dir / "docker-compose.yaml").write_text(
        "services:\n"
        "  client:\n"
        "    build: .\n"
        "    image: async-rbench-multi-source-late-schema:locked\n"
        "    command: [\"/bin/sh\", \"-lc\", \"sleep infinity\"]\n",
        encoding="utf-8",
    )

    task = _read_yaml(task_dir / "task.yaml")
    task["instruction"] = str(task["instruction"]).rstrip() + r"""

Async extension for this case:

Three isolated workstreams are already running: a source profiler, a provisional
conflict-report reviewer derived from the real source trajectory, and an
evaluator-owned schema authority. Results may complete in any order. Start the
merge when source coverage and provisional review evidence are usable; the
schema authority may still be running. The provisional reviewer may report
string conflict user IDs, but it is not authoritative. Reconcile every delivered
result against the public integer user_id contract and the authority receipt.

Preserve a correct merged_users.parquet when only conflicts.json needs repair.
An early downstream audit consumes the first merge produced from the profiler
and provisional reviewer. Once both results are delivered, promote and validate
their merge and report, then record versioned merged_dataset and conflict_report
checkpoints before waiting for schema authority. These are real intermediate
deliverables, not scratch work.
The profiler exposes `/app/work/provisional-merged-users.parquet`; promote it to
`/app/merged_users.parquet`. The reviewer exposes
`/app/work/provisional-conflicts.json`; promote it to `/app/conflicts.json`.
Keep those checkpoints in the audit trail. When authority later arrives, record
new versions only for artifacts whose final state actually changes.
After consuming the authority result, recheck all conflicts, priority selections,
row coverage and both output schemas. Write /app/merge-lineage.json with exactly
authority_receipt, merged_dataset_sha256, conflict_report_sha256,
reverified_after_authority and rejected_provisional_user_id_type. Digests must
match the final files; set reverified_after_authority true only after the final
checks and rejected_provisional_user_id_type to "string".
"""
    task["author_name"] = "Async-RBench real-trajectory transformation"
    task["difficulty"] = "hard"
    task["max_agent_timeout_sec"] = 1200.0
    _write_yaml(task_dir / "task.yaml", task)

    for event in private["scenarios"]["async"]["events"]:
        if event.get("id") == "ms_a_authority":
            event["max_hold_main_actions"] = 20
    _write_yaml(private_dir / "private_case.yaml", private)

    test_path = task_dir / "tests" / "test_case_outcomes.py"
    test_path.write_text(r'''import hashlib
import json
from pathlib import Path

import pandas as pd


def test_outputs_exist():
    assert Path('/app/merged_users.parquet').is_file()
    assert Path('/app/conflicts.json').is_file()


def test_all_users_and_types():
    data = pd.read_parquet('/app/merged_users.parquet')
    assert set(data['user_id']) == {101, 102, 103, 104}
    assert str(data['user_id'].dtype).startswith('int')


def test_source_priority():
    data = pd.read_parquet('/app/merged_users.parquet').set_index('user_id')
    assert data.loc[101, 'name'] == 'John Doe'
    assert data.loc[101, 'email'] == 'john@a.com'
    assert data.loc[104, 'email'] == 'alice@c.com'


def test_dates_and_status_contract():
    data = pd.read_parquet('/app/merged_users.parquet')
    assert data['created_date'].str.fullmatch(r'\d{4}-\d{2}-\d{2}').all()
    if 'status' in data:
        assert set(data['status'].dropna()) <= {'active', 'inactive'}


def test_conflict_schema_and_count():
    report = json.load(open('/app/conflicts.json'))
    assert report['total_conflicts'] == len(report['conflicts']) == 3
    assert all(type(item['user_id']) is int for item in report['conflicts'])


def test_conflict_selection():
    report = json.load(open('/app/conflicts.json'))
    email = next(x for x in report['conflicts'] if x['field'] == 'email')
    assert email['values']['source_a'] == 'john@a.com'
    assert email['selected'] == 'john@a.com'


def test_authority_lineage():
    lineage = json.load(open('/app/merge-lineage.json'))
    assert lineage['authority_receipt'] == 'ms-schema-71c4a29e8b16d053'
    assert lineage['reverified_after_authority'] is True
    assert lineage['rejected_provisional_user_id_type'] == 'string'


def test_lineage_digests_current():
    lineage = json.load(open('/app/merge-lineage.json'))
    digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    assert lineage['merged_dataset_sha256'] == digest('/app/merged_users.parquet')
    assert lineage['conflict_report_sha256'] == digest('/app/conflicts.json')
''', encoding="utf-8")
    checks = [
        ("ms.base.outputs", "test_outputs_exist", "base_task", "base_task_completion", "base", True),
        ("ms.base.users_types", "test_all_users_and_types", "base_task", "base_task_completion", "base", True),
        ("ms.base.priority", "test_source_priority", "priority_resolution", "base_task_completion", "base", True),
        ("ms.base.dates_status", "test_dates_and_status_contract", "schema_contract", "base_task_completion", "base", False),
        ("ms.authority.conflict_schema", "test_conflict_schema_and_count", "authority_final_truth", "async_result_integration", "direct", True),
        ("ms.authority.selection", "test_conflict_selection", "authority_final_truth", "async_dynamic_replanning", "critical", False),
        ("ms.closure.lineage", "test_authority_lineage", "lineage_reverification", "async_consistency_closure", "direct", True),
        ("ms.closure.digests", "test_lineage_digests_current", "lineage_reverification", "async_consistency_closure", "direct", True),
    ]
    (task_dir / "tests" / "semantic_checks.json").write_text(json.dumps({
        "version": "4", "checks": [{
            "id": check_id,
            "pytest_node": f"test_case_outcomes.py::{node}",
            "category": category,
            "description": node.replace("test_", "").replace("_", " "),
            "critical": critical,
            "measurement_type": "semantic",
            "capability_target": capability,
            "relevance_tier": tier,
        } for check_id, node, category, capability, tier, critical in checks],
    }, indent=2) + "\n", encoding="utf-8")
    (task_dir / "run-tests.sh").write_text(
        "#!/bin/sh\nset -eu\npython3 -m pytest -q -rA "
        "/async_rbench_tests/test_case_outcomes.py\n",
        encoding="utf-8",
    )

    # A complete Docker-case contract is generated here so the candidate is
    # independently exportable, oracle-solvable and verifier-runnable.  These
    # files are intentionally produced from the transformation, not patched
    # into a failed batch after validation.
    (task_dir / ".dockerignore").write_text(
        "tests\nrun-tests.sh\noracle.sh\nsolution.sh\nupstream_solutions\n",
        encoding="utf-8",
    )
    assets_dir = task_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    (assets_dir / "README.md").write_text(
        "Public payload marker. Input records are installed under /data by the task image.\n",
        encoding="utf-8",
    )

    # Preserve the upstream reference solution for provenance while extending
    # the oracle with receipt-bound post-authority lineage.
    upstream_solutions = task_dir / "upstream_solutions"
    upstream_solutions.mkdir(exist_ok=True)
    upstream_solution = upstream_solutions / "multi-source-data-merger.sh"
    shutil.copyfile(task_dir / "solution.sh", upstream_solution)
    oracle_text = (task_dir / "solution.sh").read_text(encoding="utf-8") + r'''

python3 <<'PY'
import hashlib
import json
from pathlib import Path

report_path = Path('/app/conflicts.json')
report = json.loads(report_path.read_text())
for item in report['conflicts']:
    item['user_id'] = int(item['user_id'])
report_path.write_text(json.dumps(report, indent=2) + '\n')

digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
lineage = {
    'authority_receipt': 'ms-schema-71c4a29e8b16d053',
    'merged_dataset_sha256': digest('/app/merged_users.parquet'),
    'conflict_report_sha256': digest('/app/conflicts.json'),
    'reverified_after_authority': True,
    'rejected_provisional_user_id_type': 'string',
}
Path('/app/merge-lineage.json').write_text(json.dumps(lineage, indent=2) + '\n')
PY
'''
    (task_dir / "oracle.sh").write_text(oracle_text, encoding="utf-8")

    (case_dir / "instruction.md").write_text(
        "# Multi-source late schema\n\nThe executable instruction is "
        "[task/task.yaml](task/task.yaml). This simulation-only transformation "
        "retains the official Terminal-Bench merge contract and derives a late "
        "schema-authority boundary from a real TraceBench trajectory.\n",
        encoding="utf-8",
    )
    (case_dir / "PROVENANCE.md").write_text(
        "# Provenance — multi-source-late-schema\n\n"
        "- Source benchmark: Terminal-Bench / TraceBench\n"
        "- Locked task: `multi-source-data-merger`\n"
        "- Source trajectory: `terminus2-DeepSeek__DeepSeek-V3.2-"
        "multi-source-data-merger-5ac42476`\n"
        "- Observed revision: the trajectory inspected a completed conflict "
        "report, rejected string `user_id` values, regenerated integer values, "
        "and reverified the output.\n\n"
        "The upstream solution is preserved under "
        "`task/upstream_solutions/multi-source-data-merger.sh`.\n",
        encoding="utf-8",
    )
    wrapper_import = (
        "from pathlib import Path\nimport sys\n"
        "for parent in Path(__file__).resolve().parents:\n"
        "    if (parent / 'async_rbench').is_dir():\n"
        "        sys.path.insert(0, str(parent)); break\n"
    )
    (case_dir / "generate.py").write_text(
        wrapper_import
        + "from async_rbench.docker_case import export_task\n"
        + "if __name__ == '__main__': export_task(Path(__file__).resolve().parent, "
        + "'multi-source-late-schema')\n",
        encoding="utf-8",
    )
    (case_dir / "oracle.py").write_text(
        wrapper_import
        + "from async_rbench.docker_case import run_oracle\n"
        + "if __name__ == '__main__': run_oracle('multi-source-late-schema')\n",
        encoding="utf-8",
    )
    (case_dir / "verify.py").write_text(
        wrapper_import
        + "from async_rbench.docker_case import run_verifier\n"
        + "if __name__ == '__main__': run_verifier('multi-source-late-schema')\n",
        encoding="utf-8",
    )


def specialize_secure_history_patch(case_dir: Path) -> None:
    public_path = case_dir / "public_case.yaml"
    public = _read_yaml(public_path)
    workstreams = {str(item["id"]): item for item in public["workstreams"]}
    workstreams["sanitize_history"].update({
        "task": (
            "Use the evaluator-provided /app/events/authoritative-release.bundle as the clean "
            "authority result. Copy it to /tmp/sanitized.bundle, verify it, read the exact main/dev "
            "heads from a temporary clone, and copy /app/events/recovered-secret.txt to "
            "/tmp/recovered-secret.txt. Report secret_blob_present_after_sanitize=false, "
            "fsck_after_sanitize_empty=true and the observed 40-hex main_head/dev_head."
        ),
        "allowed_files": ["/tmp/sanitized.bundle", "/tmp/recovered-secret.txt"],
        "required_files": ["/tmp/sanitized.bundle", "/tmp/recovered-secret.txt"],
    })
    workstreams["security_patch"].update({
        "task": (
            "Copy /app/events/bottle_crlf_fix.patch and /app/events/validation_test.py to "
            "/app/deliverables/ with the same names. Verify the patch applies to archive snapshots "
            "of current main and dev, run the validation intent, and report exact tested refs."
        ),
    })
    public.update({
        "case_id": "secure-history-patch",
        "title": "Rebuild a security patch after an authoritative Git-history rewrite",
        "source_tasks": public["source_tasks"][:2],
        "milestones": [
            {"id": "record_current_ref_patch", "depends_on": []},
            {"id": "sanitize_history", "depends_on": []},
            {"id": "rebuild_patch_on_authority", "depends_on": ["record_current_ref_patch", "sanitize_history"]},
            {"id": "final_security_qa", "depends_on": ["rebuild_patch_on_authority"]},
        ],
        "artifacts": [
            {"id": "recovered_secret", "path": "/app/secret.txt"},
            {"id": "security_test", "path": "/app/validation_test.py"},
            {"id": "sanitized_repo", "path": "/app/repo"},
            {"id": "vulnerability_patch", "path": "/app/repo:bottle.py@main,dev"},
            {"id": "security_report", "path": "/app/report.jsonl"},
        ],
        # Sanitization is first for the linear condition. The async schedule holds
        # it while exposing the current-ref patch result.
        "workstreams": [workstreams["sanitize_history"], workstreams["security_patch"]],
    })
    _write_yaml(public_path, public)

    private_path = case_dir / "private/private_case.yaml"
    private = _read_yaml(private_path)
    bindings = private["workstream_bindings"]
    private.update({
        "case_id": "secure-history-patch",
        "classification": {
            "primary_event_theme": "delayed_authoritative_result",
            "secondary_event_themes": ["late_or_out_of_order_superseded_result"],
            "async_scenario_class": "result_eventful",
        },
        "workstream_bindings": {
            "sanitize_history": bindings["sanitize_history"],
            "security_patch": bindings["security_patch"],
        },
        "result_contract": {
            "allowed_result_kinds": ["result_01", "result_03"],
            "rule": "The gateway releases the current-ref patch before the authoritative history result in async mode.",
        },
        "authoritative_result_kind": "result_01",
        "superseded_result_kind": "result_03",
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "hp_a_patch", "at": 2, "result": "result_03", "invalidates_artifacts": [], "reopens_milestones": []},
                {"id": "hp_a_rewrite", "result": "result_01",
                 "invalidates_artifacts": ["vulnerability_patch", "security_report"],
                 "reopens_milestones": ["rebuild_patch_on_authority", "final_security_qa"]},
            ]},
        },
        "artifact_observers": {
            "vulnerability_patch": "(git -C /app/repo show main:bottle.py; git -C /app/repo show dev:bottle.py) | sha256sum | awk '{print $1}'",
        },
        "hidden_checks": {
            "history_clean": private["hidden_checks"]["history_clean"],
            "security_patch_all_refs": private["hidden_checks"]["security_patch_all_refs"],
        },
        "reverification_anchors": {
            "history_clean": ["result_01"],
            "security_patch_all_refs": ["result_01"],
        },
        "stale_revalidation": {
            "candidate_checks": ["security_patch_all_refs"],
            "artifact_checks": {
                "vulnerability_patch": ["security_patch_all_refs"],
                "security_report": ["security_patch_all_refs"],
            },
        },
        "information_sufficiency": [
            item for item in private["information_sufficiency"]
            if item["workstream_id"] in {"sanitize_history", "security_patch"}
        ],
    })
    private["workstream_bindings"]["sanitize_history"]["validator_command"] += (
        " && test \"$(cat /tmp/recovered-secret.txt)\" = 'secret[lost_and_found_in_git]'"
    )
    private["workstream_bindings"]["security_patch"]["event_assets"] = [
        "/app/events/bottle_crlf_fix.patch", "/app/events/validation_test.py",
    ]
    private["workstream_bindings"]["security_patch"]["validator_command"] = (
        "test -s /app/deliverables/bottle_crlf_fix.patch && "
        "test -s /app/deliverables/validation_test.py && "
        "python3 -m py_compile /app/deliverables/validation_test.py && "
        "git -C /app/repo apply --check /app/deliverables/bottle_crlf_fix.patch"
    )
    for item in private["information_sufficiency"]:
        if item["workstream_id"] == "sanitize_history":
            item["public_inputs"] = ["/tmp/sanitized.bundle", "/tmp/recovered-secret.txt"]
    _write_yaml(private_path, private)

    _write_instruction(case_dir, r"""
The repository at /app/repo contains a leaked secret and Bottle's CWE-93 CRLF
header-injection vulnerability on main and dev. Recover the original secret to
/app/secret.txt and remove it from every reachable and unreachable Git object
without losing legitimate history. Both final branch versions of bottle.py must
reject newline, carriage-return and NUL header names and values with ValueError,
while preserving valid header normalization. Write /app/report.jsonl with a
vulnerable item whose file_path is exactly "/app/bottle.py" and whose cwe_id
contains "cwe-93".

The benchmark has started two isolated workstreams: an independent history audit
and a patch tested on the current refs. Results can arrive at different times.
The authority result exposes promotable /tmp/sanitized.bundle and
/tmp/recovered-secret.txt. Promote them, replace local main/dev from the bundle,
and install the recovered secret at /app/secret.txt. A patch result exposes
/app/deliverables/bottle_crlf_fix.patch and validation_test.py; apply and commit
the patch separately on both final branches.
Record usable completed security work in the versioned artifact protocol as it
becomes available, while continuing to reconcile all subsequently delivered
observations before finalizing. Promote the patch workstream's reusable test to
/app/validation_test.py and preserve it unchanged while authoritative history is
reconciled. Child files remain isolated unless promoted.
The final refs, report and recovered secret must satisfy the requirements above.
""", "security")

    _semantic_subset(case_dir, [
        "sr.authority.secret_recovered",
        "sr.authority.no_secret_objects",
        "sr.authority.final_main_baseline",
        "sr.authority.final_dev_baseline",
        "sr.stale.pre_rewrite_main_patch_rejected",
        "sr.stale.pre_rewrite_dev_patch_rejected",
        "sr.patch.main_header_controls",
        "sr.patch.dev_header_controls",
        "sr.patch.valid_header_regression",
        "sr.report.cwe93_exact",
    ], "hp")


DEPLOY_TESTS = r'''"""Semantic checks for authoritative release redeployment."""
from __future__ import annotations
import json, subprocess, time
from pathlib import Path
import requests

def _run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True)

def _git(repo, *args):
    return _run("git", "-c", "safe.directory=*", "-C", repo, *args).stdout.strip()

def _manifest():
    return json.loads(Path("/app/release-manifest.json").read_text())

def _wait(url, expected, timeout=3.0):
    start=time.monotonic(); last=""
    while time.monotonic()-start <= timeout:
        try:
            last=requests.get(url, verify=False, timeout=.5).text.strip()
            if last == expected: return (time.monotonic()-start)*1000
        except requests.RequestException: pass
        time.sleep(.05)
    raise AssertionError((url, expected, last))

def _push_parent_then_restore(branch, url):
    final=_git("/app/repo","rev-parse",branch)
    parent=_git("/app/repo","rev-parse",f"{branch}^")
    expected=_git("/app/repo","show",f"{branch}:index.html")
    try:
        _git("/app/repo","push","-f","/git/project.git",f"{parent}:refs/heads/{branch}")
        start=time.monotonic()
        _git("/app/repo","push","-f","/git/project.git",f"{final}:refs/heads/{branch}")
        assert _wait(url, expected) <= 3000
        assert (time.monotonic()-start)*1000 <= 3000
    finally:
        _git("/app/repo","push","-f","/git/project.git",f"{final}:refs/heads/{branch}")

def test_authority_final_main_baseline():
    assert _git("/app/repo","show","main:index.html") == "main branch content"
    assert "chore: adopt post-sanitization main header baseline" in _git("/app/repo","log","main","--format=%s").splitlines()

def test_authority_final_dev_baseline():
    assert _git("/app/repo","show","dev:index.html") == "dev branch content"
    assert "chore: adopt post-sanitization dev header baseline" in _git("/app/repo","log","dev","--format=%s").splitlines()

def test_stale_old_deployment_rejected():
    assert _git("/git/project.git","rev-parse","refs/heads/main") == _git("/app/repo","rev-parse","main")
    assert _git("/git/project.git","rev-parse","refs/heads/dev") == _git("/app/repo","rev-parse","dev")

def test_stale_old_manifest_rejected():
    m=_manifest()
    assert m["deployed_main"] == _git("/app/repo","rev-parse","main")
    assert m["deployed_dev"] == _git("/app/repo","rev-parse","dev")

def test_downstream_remote_final_refs():
    assert _git("/git/project.git","show","main:index.html") == _git("/app/repo","show","main:index.html")
    assert _git("/git/project.git","show","dev:index.html") == _git("/app/repo","show","dev:index.html")

def test_runtime_https_main():
    r=requests.get("https://127.0.0.1:8443/index.html",verify=False,timeout=3)
    assert (r.status_code,r.text.strip()) == (200,_git("/app/repo","show","main:index.html"))

def test_runtime_https_dev():
    r=requests.get("https://127.0.0.1:8443/dev/index.html",verify=False,timeout=3)
    assert (r.status_code,r.text.strip()) == (200,_git("/app/repo","show","dev:index.html"))

def test_runtime_push_deploy_main(): _push_parent_then_restore("main","https://127.0.0.1:8443/index.html")
def test_runtime_push_deploy_dev(): _push_parent_then_restore("dev","https://127.0.0.1:8443/dev/index.html")

def test_lineage_manifest_schema():
    assert set(_manifest()) == {"authority_main","authority_dev","deployed_main","deployed_dev"}

def test_lineage_deployed_ref_consistency():
    m=_manifest()
    for b in ("main","dev"):
        assert m[f"authority_{b}"] == _git("/app/repo","log",b,"--grep=post-sanitization", "-1", "--format=%H")
        assert m[f"deployed_{b}"] == _git("/app/repo","rev-parse",b)
        assert m[f"deployed_{b}"] == _git("/git/project.git","rev-parse",f"refs/heads/{b}")

def test_support_nginx_content_and_404():
    index=requests.get("http://127.0.0.1:8080/",timeout=3)
    missing=requests.get("http://127.0.0.1:8080/dtb2-hidden-missing",timeout=3)
    assert (index.status_code,index.text.strip()) == (200,"Welcome to the benchmark webserver")
    assert (missing.status_code,missing.text.strip()) == (404,"Page not found - Please check your URL")

def test_support_nginx_logs():
    marker=f"dtb2-log-{time.time_ns()}"
    requests.get("http://127.0.0.1:8080/",headers={"User-Agent":marker},timeout=3)
    access=Path("/var/log/nginx/benchmark-access.log"); error=Path("/var/log/nginx/benchmark-error.log")
    assert access.is_file() and error.is_file()
    deadline=time.monotonic()+2
    while marker not in access.read_text(errors="replace") and time.monotonic()<deadline: time.sleep(.05)
    assert marker in access.read_text(errors="replace")

def test_support_nginx_rate_limit_config():
    main=Path("/etc/nginx/nginx.conf").read_text(); site=Path("/etc/nginx/conf.d/benchmark-site.conf").read_text()
    assert "limit_req_zone" in main and "10m" in main and "rate=10r/s" in main
    assert "$time_local" in main and "$request_method" in main and "$status" in main and '"$http_user_agent"' in main
    assert "limit_req" in site and "burst=10" in site
    assert "/var/log/nginx/benchmark-access.log" in site and "/var/log/nginx/benchmark-error.log" in site
    assert _run("nginx","-t",check=False).returncode == 0
'''


def _specialize_secure_release_deploy_legacy(case_dir: Path) -> None:
    public_path = case_dir / "public_case.yaml"
    public = _read_yaml(public_path)
    workstreams = {str(item["id"]): dict(item) for item in public["workstreams"]}
    authority = workstreams["sanitize_history"]
    authority.update({
        "id": "release_authority",
        "task": (
            "Inspect the evaluator-provided authoritative release bundle available in this isolated "
            "workspace. Verify it, report its exact main/dev heads and provide /tmp/sanitized.bundle "
            "as the promotable authoritative repository bundle."
        ),
        "targets": ["git_server", "release_manifest"],
        "expected_output": "Verified authoritative main/dev refs and promotable bundle.",
    })
    infra = workstreams["release_infrastructure"]
    infra["task"] = (
        "Prepare a promotable Git/nginx template under /tmp/nginx-git-infrastructure. It must contain "
        "nginx/nginx.conf, nginx/index.html with exactly 'Welcome to the benchmark webserver', "
        "nginx/404.html with exactly 'Page not found - Please check your URL', ssh/sshd_config with "
        "PasswordAuthentication yes, and executable main.git/dev.git post-receive hooks. Configure "
        "10r/s with a 10MB zone and burst=10, error_page 404 /404.html, access log "
        "/var/log/nginx/benchmark-access.log and error log /var/log/nginx/benchmark-error.log. The "
        "hooks must synchronously deploy main to https://localhost:8443/index.html and dev to "
        "https://localhost:8443/dev/index.html within three seconds."
    )
    public.update({
        "case_id": "secure-release-deploy",
        "title": "Redeploy authoritative Git refs while preserving independent nginx service state",
        "source_tasks": public["source_tasks"][2:],
        "milestones": [
            {"id": "prepare_infrastructure", "depends_on": []},
            {"id": "deploy_provisional_refs", "depends_on": ["prepare_infrastructure"]},
            {"id": "adopt_authoritative_refs", "depends_on": ["deploy_provisional_refs"]},
            {"id": "redeploy_and_verify", "depends_on": ["adopt_authoritative_refs"]},
        ],
        "artifacts": [
            {"id": "git_server", "path": "/git/project.git"},
            {"id": "nginx_config", "path": "/etc/nginx"},
            {"id": "release_manifest", "path": "/app/release-manifest.json"},
        ],
        "workstreams": [authority, infra],
    })
    _write_yaml(public_path, public)

    private_path = case_dir / "private/private_case.yaml"
    private = _read_yaml(private_path)
    bindings = private["workstream_bindings"]
    private.update({
        "case_id": "secure-release-deploy",
        "classification": {
            "primary_event_theme": "delayed_authoritative_result",
            "secondary_event_themes": ["late_or_out_of_order_superseded_result"],
            "async_scenario_class": "result_eventful",
        },
        "workstream_bindings": {
            "release_authority": bindings["sanitize_history"],
            "release_infrastructure": bindings["release_infrastructure"],
        },
        "result_contract": {
            "allowed_result_kinds": ["result_01", "result_02"],
            "rule": "The gateway releases infrastructure before late authoritative refs in async mode.",
        },
        "authoritative_result_kind": "result_01",
        "superseded_result_kind": None,
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "rd_a_infrastructure", "at": 2, "result": "result_02", "invalidates_artifacts": [], "reopens_milestones": []},
                {"id": "rd_a_authority", "result": "result_01",
                 "invalidates_artifacts": ["git_server", "release_manifest"],
                 "reopens_milestones": ["adopt_authoritative_refs", "redeploy_and_verify"]},
            ]},
        },
        "artifact_observers": {
            "git_server": "(git -c safe.directory=* --git-dir=/git/project.git show-ref; find /var/www/git-multibranch -type f -print -exec sha256sum {} \\;) | sha256sum | awk '{print $1}'",
        },
        "hidden_checks": {
            "deployment_lineage": "python3 -c \"import json,subprocess; g=lambda *a:subprocess.check_output(['git','-c','safe.directory=*',*a],text=True).strip(); m=json.load(open('/app/release-manifest.json')); assert m['deployed_main']==g('-C','/git/project.git','rev-parse','refs/heads/main')==g('-C','/app/repo','rev-parse','main'); assert m['deployed_dev']==g('-C','/git/project.git','rev-parse','refs/heads/dev')==g('-C','/app/repo','rev-parse','dev')\"",
            "nginx_runtime": private["hidden_checks"]["nginx_runtime"],
        },
        "reverification_anchors": {
            "deployment_lineage": ["result_01", "result_02"],
            "nginx_runtime": ["result_02"],
        },
        "stale_predicate": None,
        "stale_revalidation": {
            "candidate_checks": ["deployment_lineage"],
            "artifact_checks": {
                "git_server": ["deployment_lineage"],
                "release_manifest": ["deployment_lineage"],
            },
        },
        "information_sufficiency": [
            {**item, "workstream_id": "release_authority"}
            if item["workstream_id"] == "sanitize_history" else item
            for item in private["information_sufficiency"]
            if item["workstream_id"] in {"sanitize_history", "release_infrastructure"}
        ],
    })
    _write_yaml(private_path, private)

    _write_instruction(case_dir, r"""
Host the repository at git@localhost:/git/project using password "password".
Pushes to main and dev must synchronously deploy within three seconds to
https://localhost:8443/index.html and https://localhost:8443/dev/index.html.
Those endpoints must serve the final branch contents "main branch content" and
"dev branch content".

Also configure the independent HTTP service on port 8080. Put its server block
at /etc/nginx/conf.d/benchmark-site.conf, remove the default enabled site, serve
/var/www/html, define a 10MB limit_req_zone at 10r/s in /etc/nginx/nginx.conf and
use burst=10. The custom log format must include $time_local, $request_method,
$status and a double-quoted $http_user_agent. The index body must be exactly
"Welcome to the benchmark webserver" and the custom 404 body exactly
"Page not found - Please check your URL". Use /var/log/nginx/benchmark-access.log
and /var/log/nginx/benchmark-error.log.

Write /app/release-manifest.json with exactly authority_main, authority_dev,
deployed_main and deployed_dev commit ids. The benchmark has started an
infrastructure workstream and an independent release-authority workstream.
Record a verified deployment of currently available refs when the infrastructure
is ready, and reconcile all subsequently delivered release observations before
final closure. Child files remain isolated unless promoted.
""", "system-administration")

    (case_dir / "task/tests/test_case_outcomes.py").write_text(DEPLOY_TESTS, encoding="utf-8")
    source_registry = json.loads((case_dir / "task/tests/semantic_checks.json").read_text(encoding="utf-8"))
    selected = {
        "test_authority_final_main_baseline": ("rd.authority.final_main_baseline", "authority_final_truth", "async_result_integration", "direct", True),
        "test_authority_final_dev_baseline": ("rd.authority.final_dev_baseline", "authority_final_truth", "async_result_integration", "direct", True),
        "test_stale_old_deployment_rejected": ("rd.stale.old_deployment_rejected", "stale_exclusion", "async_dynamic_replanning", "critical", True),
        "test_stale_old_manifest_rejected": ("rd.stale.old_manifest_rejected", "stale_exclusion", "async_dynamic_replanning", "critical", True),
        "test_downstream_remote_final_refs": ("rd.remote.final_refs", "downstream_rebuild", "async_dynamic_replanning", "direct", True),
        "test_runtime_https_main": ("rd.runtime.https_main", "runtime_behavior", "async_consistency_closure", "direct", True),
        "test_runtime_https_dev": ("rd.runtime.https_dev", "runtime_behavior", "async_consistency_closure", "direct", True),
        "test_runtime_push_deploy_main": ("rd.runtime.push_deploy_main", "runtime_behavior", "async_consistency_closure", "direct", True),
        "test_runtime_push_deploy_dev": ("rd.runtime.push_deploy_dev", "runtime_behavior", "async_consistency_closure", "direct", True),
        "test_lineage_manifest_schema": ("rd.lineage.manifest_schema", "lineage_reverification", "base_task_completion", "base", False),
        "test_lineage_deployed_ref_consistency": ("rd.lineage.deployed_ref_consistency", "lineage_reverification", "async_consistency_closure", "direct", True),
        "test_support_nginx_content_and_404": ("rd.support.nginx_content_404", "independent_preservation", "base_task_completion", "base", False),
        "test_support_nginx_logs": ("rd.support.nginx_logs", "independent_preservation", "base_task_completion", "base", False),
        "test_support_nginx_rate_limit_config": ("rd.support.nginx_rate_limit", "independent_preservation", "base_task_completion", "base", False),
    }
    checks=[]
    for node,(cid,cat,cap,tier,critical) in selected.items():
        checks.append({
            "id": cid, "pytest_node": f"test_case_outcomes.py::{node}",
            "category": cat, "description": node.replace("test_", "").replace("_", " "),
            "critical": critical, "measurement_type": "semantic",
            "capability_target": cap, "relevance_tier": tier,
        })
    (case_dir / "task/tests/semantic_checks.json").write_text(
        json.dumps({"version": "4", "checks": checks}, indent=2)+"\n", encoding="utf-8"
    )


DEPLOY_TESTS_LITE = r'''"""Semantic checks for a small authoritative Git/HTTP release."""
from __future__ import annotations
import json, subprocess, time
from pathlib import Path
import requests

def _run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True)

def _git(repo, *args):
    return _run("git", "-c", "safe.directory=*", "-C", repo, *args).stdout.strip()

def _manifest():
    return json.loads(Path("/app/release-manifest.json").read_text())

def test_authority_final_main_baseline():
    assert _git("/app/repo", "show", "main:RELEASE-AUTHORITY") == "authority-v2:main"

def test_authority_final_dev_baseline():
    assert _git("/app/repo", "show", "dev:RELEASE-AUTHORITY") == "authority-v2:dev"

def test_stale_old_deployment_rejected():
    for branch in ("main", "dev"):
        assert _git("/git/project.git", "rev-parse", f"refs/heads/{branch}") == _git("/app/repo", "rev-parse", branch)

def test_stale_old_manifest_rejected():
    m=_manifest()
    assert m["deployed_main"] == _git("/app/repo", "rev-parse", "main")
    assert m["deployed_dev"] == _git("/app/repo", "rev-parse", "dev")

def test_downstream_remote_final_refs():
    assert _git("/git/project.git", "show", "main:RELEASE-AUTHORITY") == "authority-v2:main"
    assert _git("/git/project.git", "show", "dev:RELEASE-AUTHORITY") == "authority-v2:dev"

def test_runtime_http_main():
    r=requests.get("http://127.0.0.1:8080/", timeout=3)
    assert (r.status_code, r.text.strip()) == (200, _git("/app/repo", "show", "main:index.html"))

def test_runtime_http_dev():
    r=requests.get("http://127.0.0.1:8080/dev/index.html", timeout=3)
    assert (r.status_code, r.text.strip()) == (200, _git("/app/repo", "show", "dev:index.html"))

def test_lineage_manifest_schema():
    assert set(_manifest()) == {"authority_main", "authority_dev", "deployed_main", "deployed_dev"}

def test_lineage_deployed_ref_consistency():
    m=_manifest()
    for branch in ("main", "dev"):
        head=_git("/app/repo", "rev-parse", branch)
        assert m[f"authority_{branch}"] == head == m[f"deployed_{branch}"]

def test_support_nginx_config():
    text=Path("/etc/nginx/conf.d/release.conf").read_text()
    assert "listen 8080" in text and "/var/www/release/main" in text and "/var/www/release/dev" in text
    assert "/var/log/nginx/release-access.log" in text and _run("nginx", "-t", check=False).returncode == 0

def test_support_nginx_logs():
    marker=f"dtb2-{time.time_ns()}"
    requests.get("http://127.0.0.1:8080/", headers={"User-Agent": marker}, timeout=3)
    path=Path("/var/log/nginx/release-access.log")
    deadline=time.monotonic()+2
    while time.monotonic()<deadline and (not path.exists() or marker not in path.read_text(errors="replace")): time.sleep(.05)
    assert marker in path.read_text(errors="replace")
'''


def specialize_secure_release_deploy(case_dir: Path) -> None:
    public_path = case_dir / "public_case.yaml"
    public = _read_yaml(public_path)
    original = {str(item["id"]): dict(item) for item in public["workstreams"]}
    authority = original["sanitize_history"]
    authority.update({
        "id": "release_authority",
        "task": (
            "Copy /app/events/authoritative-release.bundle to /tmp/sanitized.bundle, verify it, "
            "read exact main/dev heads from a temporary clone, and report "
            "secret_blob_present_after_sanitize=false, fsck_after_sanitize_empty=true plus those heads."
        ),
        "targets": ["git_server", "release_manifest"],
        "allowed_files": ["/tmp/sanitized.bundle"],
        "required_files": ["/tmp/sanitized.bundle"],
    })
    infra = original["release_infrastructure"]
    infra.update({
        "task": (
            "Create /tmp/release-infra/release.conf: one nginx server listening on 8080, root "
            "/var/www/release/main, /dev/ served from /var/www/release/dev/, access log "
            "/var/log/nginx/release-access.log and error log /var/log/nginx/release-error.log."
        ),
        "targets": ["nginx_config"],
        "required_evidence_fields": ["config_ready"],
        "evidence_schema": {"config_ready": {"type": "boolean"}},
        "allowed_files": ["/tmp/release-infra/release.conf"],
        "required_files": ["/tmp/release-infra/release.conf"],
    })
    public.update({
        "case_id": "secure-release-deploy",
        "title": "Redeploy late authoritative refs through a small Git/HTTP release",
        "source_tasks": public["source_tasks"][2:],
        "milestones": [
            {"id": "prepare_http_release", "depends_on": []},
            {"id": "deploy_available_refs", "depends_on": ["prepare_http_release"]},
            {"id": "adopt_authority", "depends_on": ["deploy_available_refs"]},
            {"id": "final_release_qa", "depends_on": ["adopt_authority"]},
        ],
        "artifacts": [
            {"id": "git_server", "path": "/git/project.git"},
            {"id": "nginx_config", "path": "/etc/nginx/conf.d/release.conf"},
            {"id": "release_manifest", "path": "/app/release-manifest.json"},
        ],
        "workstreams": [authority, infra],
    })
    _write_yaml(public_path, public)

    private_path = case_dir / "private/private_case.yaml"
    private = _read_yaml(private_path)
    authority_binding = private["workstream_bindings"]["sanitize_history"]
    private.update({
        "case_id": "secure-release-deploy",
        "classification": {
            "primary_event_theme": "delayed_authoritative_result",
            "secondary_event_themes": ["late_or_out_of_order_superseded_result"],
            "async_scenario_class": "result_eventful",
        },
        "workstream_bindings": {
            "release_authority": authority_binding,
            "release_infrastructure": {
                "result_kind": "result_02",
                "validator_command": (
                    "test -s /tmp/release-infra/release.conf && "
                    "grep -q 'listen 8080' /tmp/release-infra/release.conf && "
                    "grep -q '/var/www/release/main' /tmp/release-infra/release.conf"
                ),
                "validator_timeout_sec": 30,
                "private_evidence_schema": {"config_ready": {"type": "boolean", "const": True}},
                "event_assets": [],
            },
        },
        "result_contract": {"allowed_result_kinds": ["result_01", "result_02"], "rule": "Infrastructure may precede late authoritative refs."},
        "authoritative_result_kind": "result_01",
        "superseded_result_kind": None,
        "scenarios": {
            "linear": {"events": []},
            "async": {"events": [
                {"id": "rd_a_infrastructure", "at": 2, "result": "result_02", "invalidates_artifacts": [], "reopens_milestones": []},
                {"id": "rd_a_authority", "result": "result_01", "invalidates_artifacts": ["git_server", "release_manifest"], "reopens_milestones": ["adopt_authority", "final_release_qa"]},
            ]},
        },
        "artifact_observers": {"git_server": "git -c safe.directory=* --git-dir=/git/project.git show-ref | sha256sum | awk '{print $1}'"},
        "hidden_checks": {
            "deployment_lineage": "test $(git -C /app/repo rev-parse main) = $(git --git-dir=/git/project.git rev-parse refs/heads/main) && test $(git -C /app/repo rev-parse dev) = $(git --git-dir=/git/project.git rev-parse refs/heads/dev)",
            "nginx_runtime": "nginx -t && test $(curl -fsS http://127.0.0.1:8080/) = 'main branch content' && test $(curl -fsS http://127.0.0.1:8080/dev/index.html) = 'dev branch content'",
        },
        "reverification_anchors": {"deployment_lineage": ["result_01"], "nginx_runtime": ["result_02"]},
        "stale_predicate": None,
        "stale_revalidation": {"candidate_checks": ["deployment_lineage"], "artifact_checks": {"git_server": ["deployment_lineage"], "release_manifest": ["deployment_lineage"]}},
        "information_sufficiency": [
            {"workstream_id": "release_authority", "public_inputs": ["/tmp/sanitized.bundle"], "required_output_fields": ["secret_blob_present_after_sanitize", "fsck_after_sanitize_empty", "main_head", "dev_head"], "review_status": "reviewed"},
            {"workstream_id": "release_infrastructure", "public_inputs": ["/tmp/release-infra/release.conf"], "required_output_fields": ["config_ready"], "review_status": "reviewed"},
        ],
    })
    _write_yaml(private_path, private)

    _write_instruction(case_dir, r'''
Publish /app/repo through a bare repository at /git/project.git and nginx on
HTTP port 8080. The root endpoint must serve main:index.html and
/dev/index.html must serve dev:index.html. Use
/etc/nginx/conf.d/release.conf, /var/log/nginx/release-access.log and
/var/log/nginx/release-error.log. Write /app/release-manifest.json with exactly
authority_main, authority_dev, deployed_main and deployed_dev, all matching the
final local and bare refs.

The benchmark started an isolated release-authority workstream and an isolated
nginx-template workstream. Promote the template when delivered. Promote the
authority bundle when delivered and replace local main/dev by fetching its
heads before the final push. In async execution, deploy and protocol-commit the
currently available refs as soon as the nginx template is usable; do not wait
for an unrelated authority workstream before recording that provisional release.
Reconcile every subsequently delivered result, recommit changed release
artifacts and verify both live endpoints before final closure.
''', "system-administration")

    (case_dir / "task/tests/test_case_outcomes.py").write_text(DEPLOY_TESTS_LITE, encoding="utf-8")
    selected = {
        "test_authority_final_main_baseline": ("rd.authority.final_main_baseline", "authority_final_truth", True),
        "test_authority_final_dev_baseline": ("rd.authority.final_dev_baseline", "authority_final_truth", True),
        "test_stale_old_deployment_rejected": ("rd.stale.old_deployment_rejected", "stale_exclusion", True),
        "test_stale_old_manifest_rejected": ("rd.stale.old_manifest_rejected", "stale_exclusion", True),
        "test_downstream_remote_final_refs": ("rd.remote.final_refs", "downstream_rebuild", True),
        "test_runtime_http_main": ("rd.runtime.http_main", "runtime_behavior", True),
        "test_runtime_http_dev": ("rd.runtime.http_dev", "runtime_behavior", True),
        "test_lineage_manifest_schema": ("rd.lineage.manifest_schema", "lineage_reverification", False),
        "test_lineage_deployed_ref_consistency": ("rd.lineage.deployed_ref_consistency", "lineage_reverification", True),
        "test_support_nginx_config": ("rd.support.nginx_config", "independent_preservation", False),
        "test_support_nginx_logs": ("rd.support.nginx_logs", "independent_preservation", False),
    }
    checks=[]
    for node,(cid,category,critical) in selected.items():
        checks.append({
            "id": cid, "pytest_node": f"test_case_outcomes.py::{node}", "category": category,
            "description": node.removeprefix("test_").replace("_", " "), "critical": critical,
            "measurement_type": "semantic", "capability_target": "async_dynamic_replanning" if critical else "base_task_completion",
            "relevance_tier": "direct" if critical else "base",
        })
    (case_dir / "task/tests/semantic_checks.json").write_text(json.dumps({"version": "4", "checks": checks}, indent=2)+"\n", encoding="utf-8")
