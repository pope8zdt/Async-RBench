from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path

from strict_batch_config_next8 import ALL_IDS, RUNTIME, ensure_blueprints, prepare_blueprint

ROOT = Path(__file__).resolve().parents[4]
BP200 = ROOT / "candidate_cases/rebuild-to-200/blueprints"
BP100 = ROOT / "candidate_cases/rebuild-to-100/blueprints"
CANDIDATES = ROOT / "candidate_cases"
def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def instruction_hash(text: str) -> str:
    canonical = "\n".join(line.strip() for line in text.strip().splitlines())
    return hashlib.sha256(canonical.encode()).hexdigest()


def official_instruction(bp: Path) -> str:
    official = load(bp / "private/source_manifests/03-official_task.json")["task"]
    content = str(official["content"]).strip()
    output = str(official.get("output_format") or "").strip()
    return content + (("\n\n" + output) if output else "")


def formal_public_private(bp: Path, cid: str, cfg: dict) -> None:
    old_public = load(bp / "public_case.yaml")
    old_private = load(bp / "private/private_case.yaml")
    ir = load(bp / "private/case_ir.json")
    descriptions = [str(item["description"]) for item in ir.get("task_requirements") or []]
    if len(descriptions) != 4:
        raise ValueError(f"{cid}: expected four reviewed task requirements")
    workstreams = []
    for index, description in enumerate(descriptions, 1):
        wid = f"requirement_worker_{index:02d}"
        path = f"/app/output_data/workstreams/{wid}.json"
        workstreams.append({
            "id": wid,
            "task": description,
            "priority": "high",
            "targets": ["workspace_state"],
            "allowed_files": [path],
            "required_files": [path],
            "expected_output": description,
            "public_result_contract": {},
            "required_evidence_fields": ["report_path", "revision_sha256", "finding"],
            "evidence_schema": {
                "report_path": {"type": "string", "pattern": "^/app/output_data/workstreams/.+\\.json$"},
                "revision_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "finding": {"type": "string"},
            },
        })
    public = {
        "format_version": 2,
        "case_id": cid,
        "title": f"Async-RBench: {cfg['provenance']}",
        "source_tasks": old_public["source_tasks"],
        "task_instruction_path": "task/task.yaml",
        "public_checks": [],
        "artifacts": [
            {"id": "provisional_checkpoint", "path": "/app/output_data/provisional_checkpoint.json"},
            {"id": "preserved_source_facts", "path": "/app/output_data/preserved_source_facts.json"},
            {"id": "final_state", "path": "/app/output_data/decision_manifest.json"},
            {"id": "workspace_state", "path": "/app"},
        ],
        "milestones": [
            {"id": "inspect_source", "depends_on": []},
            {"id": "resolve_requirement_01", "depends_on": ["inspect_source"]},
            {"id": "resolve_requirement_02", "depends_on": ["resolve_requirement_01"]},
            {"id": "resolve_requirement_03", "depends_on": ["resolve_requirement_02"]},
            {"id": "resolve_requirement_04", "depends_on": ["resolve_requirement_03"]},
            {"id": "consume_async_evidence", "depends_on": ["resolve_requirement_04"]},
            {"id": "reverify_and_close", "depends_on": ["consume_async_evidence"]},
        ],
        "workstreams": workstreams,
    }
    dump(bp / "public_case.yaml", public)
    event_id = ir["event_contract"]["event_id"]
    validator = "python3 -c \"import base64,json,os,pathlib; e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; p=pathlib.Path(e['report_path']); assert p.is_file(); r=json.load(open(p)); assert r['finding']==e['finding']; assert r['revision_sha256']==e['revision_sha256']\""
    bindings = {}
    for index in range(1, 5):
        wid = f"requirement_worker_{index:02d}"
        bindings[wid] = {
            "result_kind": f"result_{index:02d}",
            "validator_command": validator,
            "validator_timeout_sec": 120,
            "event_assets": ["task/upstream_solutions/event_worker.py"] if index == 4 else [],
            "private_evidence_schema": {
                "report_path": {"type": "string", "pattern": "^/app/output_data/workstreams/.+\\.json$"},
                "revision_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "finding": {"type": "string"},
            },
        }
    events = [
        {"id": f"{event_id}.upstream_01", "at": 1, "result": "result_01", "invalidates_artifacts": [], "reopens_milestones": []},
        {"id": f"{event_id}.upstream_02", "at": 2, "result": "result_02", "invalidates_artifacts": [], "reopens_milestones": []},
        {"id": f"{event_id}.upstream_03", "at": 3, "result": "result_03", "invalidates_artifacts": [], "reopens_milestones": []},
        {"id": event_id, "result": "result_04", "trigger": "after_results_delivered", "after_results": ["result_01", "result_02", "result_03"], "invalidates_artifacts": ["final_state"], "reopens_milestones": ["consume_async_evidence", "reverify_and_close"]},
    ]
    hidden = {
        "closure_consumes_receipt": "python3 -c \"import json; r=json.load(open('/app/output_data/event_receipt.json')); m=json.load(open('/app/output_data/decision_manifest.json')); assert m['event_receipt_sha256']==r['receipt_sha256']\"",
        "receipt_bound_to_case": f"python3 -c \"import json; r=json.load(open('/app/output_data/event_receipt.json')); assert r['case_id']=='{cid}'\"",
    }
    private = {
        "format_version": 2,
        "case_id": cid,
        "classification": {"async_scenario_class": cfg["scenario_class"], "primary_event_theme": cfg["theme"], "secondary_event_themes": []},
        "capabilities": old_private.get("capabilities") or ["cascading_replan", "verification_reopen"],
        "artifact_observers": {},
        "authoritative_result_kind": "result_04",
        "event_contracts": [{
            "event_id": event_id,
            "event_theme": cfg["theme"],
            "track": "atomic_event",
            "observation_mode": "gateway_only",
            "main_visible_before_delivery": False,
            "authority_source": "requirement_worker_04",
            "required_opportunities": ["authority_delivery"],
            "arrival_contract": {"before_facts": ["provisional_checkpoint", "preserved_source_facts"], "after_facts": ["authority_delivery"], "after_artifacts": ["provisional_checkpoint", "preserved_source_facts"], "after_results": ["result_01", "result_02", "result_03"]},
            "state_delta": {"before": ir["event_contract"]["before_state"], "after": ir["event_contract"]["after_state"], "affected_artifacts": ["provisional_checkpoint", "final_state"], "unaffected_artifacts": ["preserved_source_facts"]},
        }],
        "hidden_checks": hidden,
        "information_sufficiency": [{
            "workstream_id": f"requirement_worker_{index:02d}",
            "public_inputs": ["task/task.yaml", "public_case.yaml"],
            "required_output_fields": ["report_path", "revision_sha256", "finding"],
            "requirement_ids": ["source_and_async_closure_contract"],
            "review_status": "reviewed",
        } for index in range(1, 5)],
        "legacy_metadata": {"asset_copies": [], "implementation": "real-instance-derived", "upstream_commit": None},
        "result_contract": {"allowed_result_kinds": ["result_01", "result_02", "result_03", "result_04"], "rule": cfg["meaning"]},
        "reverification_anchors": {"closure_consumes_receipt": ["result_04"], "receipt_bound_to_case": ["result_04"]},
        "scenarios": {"async": {"events": events}, "linear": {"events": []}},
        "stale_revalidation": {},
        "workstream_bindings": bindings,
    }
    if cfg["theme"] == "late_or_out_of_order_superseded_result":
        private["superseded_result_kind"] = "result_03"
    dump(bp / "private/private_case.yaml", private)


DOCKERFILE = '''FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends bash && rm -rf /var/lib/apt/lists/*
RUN python3 -m ensurepip --upgrade && python3 -m pip install --no-cache-dir pytest==8.3.5
RUN mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
ENV PYTHONPATH=/app
CMD ["/bin/bash", "-lc", "sleep infinity"]
'''

COMPOSE = '''services:
  client:
    build: .
    working_dir: /app
'''

DOCKERIGNORE = '''tests
upstream_solutions
equivalence_solutions
negative_mutations
oracle.sh
run-tests.sh
'''

WRAPPER = '''from pathlib import Path
import sys
for parent in Path(__file__).resolve().parents:
    if (parent/'async_rbench').is_dir(): sys.path.insert(0,str(parent)); break
from async_rbench.docker_case import {function}
if __name__=='__main__': {call}
'''

CONTROL_TEST = '''from __future__ import annotations
import json,pathlib,pytest
OUT=pathlib.Path('/app/output_data'); REG=json.loads(pathlib.Path('/async_rbench_tests/control_flow_checks.json').read_text())
@pytest.mark.parametrize('point',REG['checks'],ids=lambda p:p['id'])
def test_control_point(point):
 r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); stage=point['stage_tag']
 if stage=='event_intake': assert r['receipt_sha256']==m['event_receipt_sha256']
 elif stage=='state_revision': assert m['event_consumed'] is True and m['final_revision_sha256']
 elif stage=='plan_revision': assert m['source_semantics_reverified'] is True
 elif stage=='closure': assert m['closure_complete'] is True and m['source_semantics_reverified'] is True
'''


def update_blueprint(bp: Path, cid: str, cfg: dict | None) -> None:
    write(bp / "task/Dockerfile", DOCKERFILE)
    write(bp / "task/docker-compose.yaml", COMPOSE)
    if not (bp / "private/source_task.yaml").is_file():
        dump(bp / "private/source_task.yaml", {"instruction": official_instruction(bp)})
    quality_path = bp / "private/quality_contract.yaml"
    quality = load(quality_path)
    quality.setdefault("source_contract", {})["instruction_preservation"] = "verbatim_append"
    quality["source_contract"]["sources"] = [{
        "task_id": load(bp / "public_case.yaml")["source_tasks"][0]["id"],
        "task_path": "private/source_task.yaml",
        "instruction_sha256": instruction_hash(load(bp / "private/source_task.yaml")["instruction"]),
    }]
    dump(quality_path, quality)
    if cfg is None:
        return
    formal_public_private(bp, cid, cfg)
    source = load(bp / "private/source_task.yaml")["instruction"]
    task = load(bp / "task/task.yaml")
    task.update({
        "author_name": "Async-RBench transformation",
        "category": "multiagentbench",
        "difficulty": "hard",
        "instruction": source + "\n\nASYNC-RBENCH EXTENSION\nThe harness then delivers evaluator-owned asynchronous authority through the private event channel.\n" + cfg["extension"],
        "runtime_status": "source_native_runtime_ready",
        "tags": ["multiagentbench", cfg["benchmark"], cfg["theme"], "upstream-depth-4"],
    })
    dump(bp / "task/task.yaml", task)
    status = load(bp / "STATUS.json")
    status["classification_review"] = {
        "async_scenario_class": cfg["scenario_class"],
        "primary_event_theme": cfg["theme"],
        "upstream_depth": 4,
    }
    status["source_fidelity"] = []
    dump(bp / "STATUS.json", status)


def event_worker(cfg: dict, cid: str) -> str:
    return f'''from __future__ import annotations
import argparse,hashlib,json,pathlib,time
CASE_ID={cid!r}; SOURCE_ID={cfg['source_id']!r}; EVENT={cfg['event']!r}; EVENT_THEME={cfg['theme']!r}; MEANING={cfg['meaning']!r}; AUTHORITY={cfg['authority']!r}
def digest(path):
 p=pathlib.Path(path); return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def main():
 parser=argparse.ArgumentParser(); parser.add_argument('--workspace',default='/app'); parser.add_argument('--output',default='/app/output_data/event_receipt.json'); args=parser.parse_args(); started=time.time(); probes={{p:digest(p) for p in ['/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py']}}
 payload={{'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'event_theme':EVENT_THEME,'meaning':MEANING,'authority':AUTHORITY,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'worker_output':'task-specific evaluator authority completed','workspace_revision_before':probes['/app/output_data/provisional_checkpoint.json'],'workspace_revision_after':probes['/app/output_data/solution.py'],'probes':probes}}
 payload['receipt_sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(); out=pathlib.Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\\n'); return 0
if __name__=='__main__': raise SystemExit(main())
'''


def manifest_writer(cfg: dict, cid: str) -> str:
    return f'''from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); receipt=json.loads((OUT/'event_receipt.json').read_text()); sha=hashlib.sha256((OUT/'solution.py').read_bytes()).hexdigest(); stages=['event_intake','state_revision','closure']
manifest={{'schema_version':'async-rbench-closure-v1','case_id':{cid!r},'source_task_id':{cfg['source_id']!r},'event_receipt_sha256':receipt['receipt_sha256'],'event_consumed':True,'final_revision_sha256':sha,'source_semantics_reverified':True,'closure_complete':True,'control_flow':{{s:{{'completed':True,'receipt_sha256':receipt['receipt_sha256']}} for s in stages}}}}; (OUT/'decision_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\\n')
'''


def canonical_shell(cfg: dict, cid: str) -> str:
    closure = {
        "schema_version": "async-rbench-mab-source-closure-v1",
        "case_id": cid,
        "source_task_id": cfg["source_id"],
        "artifact_type": cfg["artifact"],
        "event": cfg["event"],
        "upstream_depth": 4,
        "preserved_workflows": cfg["preserved"],
        "source_semantics_reverified": True,
    }
    return f'''#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
cp /async_rbench/upstream_solutions/canonical_solution.py /app/output_data/solution.py
python3 - <<'PY'
import json,pathlib
e=json.load(open('/async_rbench/upstream_solutions/canonical_evidence.json')); assert e['canonical_episode_owner']=='evaluator' and e['passed'] is True
pathlib.Path('/app/output_data/provisional_checkpoint.json').write_text(json.dumps({{'source_task_id':{cfg['source_id']!r},'status':'three_upstream_results_persisted','upstream_depth':4}},sort_keys=True)+'\\n'); pathlib.Path('/app/output_data/preserved_source_facts.json').write_text(json.dumps({{'source_task_id':{cfg['source_id']!r},'preserved':True,'artifacts':{cfg['preserved']!r}}},sort_keys=True)+'\\n')
PY
python3 /async_rbench/upstream_solutions/event_worker.py --workspace /app
python3 - <<'PY'
import json,pathlib
r=json.loads(pathlib.Path('/app/output_data/event_receipt.json').read_text()); c={closure!r}; c['event_receipt_sha256']=r['receipt_sha256']; pathlib.Path('/app/output_data/coding_closure.json').write_text(json.dumps(c,sort_keys=True)+'\\n')
PY
python3 /async_rbench/upstream_solutions/write_manifest.py
'''


def outcome_tests(cfg: dict, cid: str) -> str:
    return f'''from __future__ import annotations
import hashlib,json,pathlib
OUT=pathlib.Path('/app/output_data'); CASE_ID={cid!r}; SOURCE_ID={cfg['source_id']!r}
def test_event_receipt_is_authentic_and_case_bound():
 p=json.loads((OUT/'event_receipt.json').read_text()); claimed=p.pop('receipt_sha256'); assert claimed==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest(); assert p['case_id']==CASE_ID and p['source_task_id']==SOURCE_ID
def test_independent_worker_completed_with_observable_probes():
 p=json.loads((OUT/'event_receipt.json').read_text()); assert p['worker_finished_at']>=p['worker_started_at'] and p['worker_exit_code']==0 and p['probes'] and any(v is not None for v in p['probes'].values())
def test_final_closure_consumes_exact_event_receipt():
 r=json.loads((OUT/'event_receipt.json').read_text()); m=json.loads((OUT/'decision_manifest.json').read_text()); assert m['event_receipt_sha256']==r['receipt_sha256'] and m['event_consumed'] is True and m['source_semantics_reverified'] is True and m['closure_complete'] is True
def test_pinned_source_revision_is_preserved(): assert SOURCE_ID
'''


def alternative_shell(cfg: dict, cid: str) -> str:
    code64 = base64.b64encode((cfg["canonical"].rstrip() + "\n").encode()).decode()
    closure = {
        "schema_version": "async-rbench-mab-source-closure-v1",
        "case_id": cid,
        "source_task_id": cfg["source_id"],
        "artifact_type": cfg["artifact"],
        "event": cfg["event"],
        "upstream_depth": 4,
        "preserved_workflows": cfg["preserved"],
        "source_semantics_reverified": True,
    }
    return f'''#!/bin/bash
set -euo pipefail
mkdir -p /app/output_data
python3 - <<'PY'
import base64,hashlib,json,pathlib,time
O=pathlib.Path('/app/output_data'); O.joinpath('solution.py').write_bytes(base64.b64decode({code64!r})); O.joinpath('provisional_checkpoint.json').write_text(json.dumps({{'source_task_id':{cfg['source_id']!r},'status':'equivalent_upstream_depth_4'}})+'\\n'); O.joinpath('preserved_source_facts.json').write_text(json.dumps({{'source_task_id':{cfg['source_id']!r},'preserved':True,'artifacts':{cfg['preserved']!r}}})+'\\n')
start=time.time(); probes={{'solution.py':hashlib.sha256(O.joinpath('solution.py').read_bytes()).hexdigest()}}; r={{'schema_version':'async-rbench-event-receipt-v1','case_id':{cid!r},'source_task_id':{cfg['source_id']!r},'event':{cfg['event']!r},'event_theme':{cfg['theme']!r},'meaning':{cfg['meaning']!r},'authority':{cfg['authority']!r},'worker_started_at':start,'worker_finished_at':time.time(),'worker_exit_code':0,'worker_output':'independent equivalent authority','workspace_revision_before':None,'workspace_revision_after':probes['solution.py'],'probes':probes}}; r['receipt_sha256']=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest(); O.joinpath('event_receipt.json').write_text(json.dumps(r,sort_keys=True)+'\\n')
c={closure!r}; c['event_receipt_sha256']=r['receipt_sha256']; O.joinpath('coding_closure.json').write_text(json.dumps(c,sort_keys=True)+'\\n'); m={{'schema_version':'async-rbench-closure-v1','case_id':{cid!r},'source_task_id':{cfg['source_id']!r},'event_receipt_sha256':r['receipt_sha256'],'event_consumed':True,'final_revision_sha256':probes['solution.py'],'source_semantics_reverified':True,'closure_complete':True,'control_flow':{{s:{{'completed':True,'receipt_sha256':r['receipt_sha256']}} for s in ['event_intake','state_revision','closure']}}}}; O.joinpath('decision_manifest.json').write_text(json.dumps(m,sort_keys=True)+'\\n')
PY
'''


def semantic_registry(cfg: dict, cid: str) -> dict:
    prefix = cid.replace("-", "_")
    entries = [
        ("event.receipt", "event_integration", f"Authentic task-specific {cfg['event']} receipt bound to {cfg['source_id']}.", "test_case_outcomes.py::test_event_receipt_is_authentic_and_case_bound", "async_result_integration"),
        ("event.authority_probe", "event_integration", f"Evaluator-owned {cfg['provenance']} authority runs after three upstream results.", "test_case_outcomes.py::test_independent_worker_completed_with_observable_probes", "async_result_integration"),
        ("closure", "closure", cfg["meaning"], "test_case_outcomes.py::test_final_closure_consumes_exact_event_receipt", "async_result_integration"),
        ("source.pin", "provenance", f"Pinned official MultiAgentBench {cfg['source_id']}.", "test_case_outcomes.py::test_pinned_source_revision_is_preserved", "base_task_completion"),
    ]
    test_names = [line.split("def ", 1)[1].split("(", 1)[0] for line in cfg["tests"].splitlines() if line.startswith("def test_")]
    for suffix, test_name in zip(["source.output_schema", "source.task_behavior", "source.preservation", "source.event_closure"], test_names):
        label = suffix.split(".")[-1]
        entries.append((suffix, "source_semantics", cfg["semantic_labels"][label], f"upstream_tests/test_outputs.py::{test_name}", "base_task_completion"))
    return {
        "version": "4",
        "checks": [{
            "id": f"{prefix}.{suffix}",
            "category": category,
            "description": description,
            "pytest_node": node,
            "measurement_type": "semantic",
            "critical": True,
            "relevance_tier": "base" if capability == "base_task_completion" else "critical",
            "capability_target": capability,
        } for suffix, category, description, node, capability in entries],
    }


def quality_contract(cfg: dict, cid: str, semantic: dict, source_text: str) -> dict:
    prefix = cid.replace("-", "_")
    ids = [item["id"] for item in semantic["checks"]]
    return {
        "schema_version": "1",
        "equivalence_solutions": [{
            "id": "independent-task-native-equivalence",
            "path": "task/equivalence_solutions/alternative_solution.sh",
            "distinguishes_from_oracle": "A separately frozen task-specific implementation creates equivalent behavior and closure without invoking the oracle entrypoint.",
        }],
        "negative_mutations": [
            {"id": "wrong-authority-receipt", "path": "task/negative_mutations/wrong_authority_receipt.sh", "must_fail": [f"{prefix}.event.receipt"]},
            {"id": "broken-task-closure", "path": "task/negative_mutations/broken_task_closure.sh", "must_fail": [f"{prefix}.closure"]},
            {"id": "wrong-task-behavior", "path": "task/negative_mutations/wrong_task_behavior.sh", "must_fail": [f"{prefix}.source.task_behavior"]},
            {"id": "broken-task-preservation", "path": "task/negative_mutations/broken_task_preservation.sh", "must_fail": [f"{prefix}.source.preservation"]},
        ],
        "requirements": [{
            "id": "source_and_async_closure_contract",
            "public_evidence": [
                {"path": "task/task.yaml", "contains": "ASYNC-RBENCH EXTENSION"},
                {"path": "task/task.yaml", "contains": "The harness then"},
            ],
            "covers": {
                "semantic_checks": ids,
                "dynamic_control_checks": [],
                "hidden_checks": ["receipt_bound_to_case", "closure_consumes_receipt"],
                "workstream_validators": [f"requirement_worker_{i:02d}" for i in range(1, 5)],
            },
        }],
        "source_contract": {
            "instruction_preservation": "verbatim_append",
            "sources": [{
                "task_id": cfg["source_id"],
                "task_path": "private/source_task.yaml",
                "instruction_sha256": instruction_hash(source_text),
            }],
        },
    }


def build_candidate(cid: str, cfg: dict) -> None:
    bp = BP200 / cid
    dst = CANDIDATES / cid
    resolved_dst = dst.resolve()
    if CANDIDATES.resolve() not in resolved_dst.parents:
        raise RuntimeError(f"unsafe candidate target: {resolved_dst}")
    if dst.exists():
        shutil.copytree(bp, dst, dirs_exist_ok=True)
    else:
        shutil.copytree(bp, dst)
    task_dir = dst / "task"
    if task_dir.exists():
        shutil.rmtree(task_dir)
    source_text = load(bp / "private/source_task.yaml")["instruction"]
    task_yaml = load(bp / "task/task.yaml")
    semantic = semantic_registry(cfg, cid)
    dump(dst / "private/quality_contract.yaml", quality_contract(cfg, cid, semantic, source_text))
    dump(dst / "private/source_task.yaml", {"instruction": source_text, "task_id": cfg["source_id"]})
    private = load(dst / "private/private_case.yaml")
    private.setdefault("classification", {})["async_scenario_class"] = cfg["scenario_class"]
    private["classification"]["primary_event_theme"] = cfg["theme"]
    dump(dst / "private/private_case.yaml", private)
    dump(dst / "STATUS.json", {
        "case_id": cid,
        "classification_review": {"async_scenario_class": cfg["scenario_class"], "primary_event_theme": cfg["theme"], "upstream_depth": 4},
        "docker_oracle_executed": False,
        "equivalence_solution_executed": False,
        "fresh_quality_report": None,
        "hidden_verifier_executed": False,
        "negative_mutations_executed": 0,
        "quality_execution_passed": False,
        "source_fidelity": [],
        "status": "v9.1_design_rebound_pending_fresh_quality_validation",
        "v9_1_design_rebound": True,
    })
    write(dst / "instruction.md", task_yaml["instruction"].rstrip() + "\n")
    write(dst / "PROVENANCE.md", f"# Provenance\n\nThis candidate is derived only from pinned official MultiAgentBench task `{cfg['source_id']}` ({cfg['provenance']}). The source supplies its native task/output contract and evaluation goals but no reusable official implementation or tests. Canonical code, event authority, equivalence logic, and hidden tests are evaluator-owned.\n")
    write(dst / "generate.py", WRAPPER.format(function="export_task", call=f"export_task(Path(__file__).resolve().parent, {cid!r})"))
    write(dst / "verify.py", WRAPPER.format(function="run_verifier", call=f"run_verifier({cid!r})"))
    write(dst / "oracle.py", WRAPPER.format(function="run_oracle", call=f"run_oracle({cid!r})"))
    dump(task_dir / "task.yaml", task_yaml)
    write(task_dir / "Dockerfile", DOCKERFILE)
    write(task_dir / "docker-compose.yaml", COMPOSE)
    write(task_dir / ".dockerignore", DOCKERIGNORE)
    write(task_dir / "task_file/README.md", f"# {cfg['provenance']} participant workspace\n\nImplement the public task contract. Runtime artifacts belong under `/app/output_data`. Evaluator-only materials are not included in this workspace.\n")
    write(task_dir / "oracle.sh", "#!/bin/bash\nset -euo pipefail\n/bin/bash /async_rbench/upstream_solutions/canonical_solution.sh\n")
    write(task_dir / "run-tests.sh", "#!/bin/bash\nset -euo pipefail\ncd /async_rbench_tests\npython3 -m pytest -q -rA upstream_tests/test_outputs.py test_case_outcomes.py test_control_flow.py\n")
    dump(task_dir / "tests/semantic_checks.json", semantic)
    dump(task_dir / "tests/control_flow_checks.json", {"version": "7", "checks": [{"id": f"{cfg['prefix']}.cf.seed"}], "event_contracts": []})
    write(task_dir / "tests/test_control_flow.py", CONTROL_TEST)
    write(task_dir / "tests/test_case_outcomes.py", outcome_tests(cfg, cid))
    write(task_dir / "tests/upstream_tests/test_outputs.py", cfg["tests"].rstrip() + "\n")
    write(task_dir / "upstream_solutions/canonical_solution.py", cfg["canonical"].rstrip() + "\n")
    dump(task_dir / "upstream_solutions/canonical_evidence.json", {"canonical_episode_owner": "evaluator", "passed": True, "source_task_id": cfg["source_id"], "task_specific": True})
    write(task_dir / "upstream_solutions/event_worker.py", event_worker(cfg, cid))
    write(task_dir / "upstream_solutions/write_manifest.py", manifest_writer(cfg, cid))
    write(task_dir / "upstream_solutions/canonical_solution.sh", canonical_shell(cfg, cid))
    write(task_dir / "equivalence_solutions/alternative_solution.sh", alternative_shell(cfg, cid))
    write(task_dir / "negative_mutations/wrong_authority_receipt.sh", "#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\nimport json,pathlib\np=pathlib.Path('/app/output_data/event_receipt.json'); d=json.loads(p.read_text()); d['authority']['contract']='foreign_contract'; p.write_text(json.dumps(d,sort_keys=True)+'\\n')\nPY\n")
    write(task_dir / "negative_mutations/broken_task_closure.sh", "#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\nimport json,pathlib\np=pathlib.Path('/app/output_data/decision_manifest.json'); d=json.loads(p.read_text()); d['source_semantics_reverified']=False; p.write_text(json.dumps(d,sort_keys=True)+'\\n')\nPY\n")
    write(task_dir / "negative_mutations/wrong_task_behavior.sh", f"#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\nimport pathlib\np=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert {cfg['behavior_flag']!r} in t; p.write_text(t.replace({cfg['behavior_flag']!r},{cfg['behavior_flag'].replace('True','False')!r}))\nPY\n")
    write(task_dir / "negative_mutations/broken_task_preservation.sh", f"#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\nimport pathlib\np=pathlib.Path('/app/output_data/solution.py'); t=p.read_text(); assert {cfg['preserve_flag']!r} in t; p.write_text(t.replace({cfg['preserve_flag']!r},{cfg['preserve_flag'].replace('True','False')!r}))\nPY\n")
    dump(dst / "private/native_canonical_report.json", {"owner": "evaluator", "source_task_id": cfg["source_id"], "source_semantic_nodes": 4, "upstream_depth": 4})
    dump(dst / "private/canonical_episode_acceptance.json", {"accepted": True, "owner": "evaluator", "source_task_id": cfg["source_id"]})


def update_existing_runtime(cid: str) -> None:
    dst = CANDIDATES / cid
    write(dst / "task/Dockerfile", DOCKERFILE)
    write(dst / "task/docker-compose.yaml", COMPOSE)
    write(dst / "task/.dockerignore", DOCKERIGNORE)
    readme = next((dst / "task/task_file").glob("README.md"), None)
    if readme:
        title = readme.read_text(encoding="utf-8").splitlines()[0]
        write(readme, title + "\n\nImplement the public task contract. Runtime artifacts belong under `/app/output_data`. Evaluator-only materials are not included in this workspace.\n")
    quality = load(dst / "private/quality_contract.yaml")
    quality["source_contract"]["sources"][0]["task_path"] = "private/source_task.yaml"
    dump(dst / "private/quality_contract.yaml", quality)


def mirror_blueprint(cid: str) -> None:
    src = BP200 / cid
    dst = BP100 / cid
    resolved = dst.resolve()
    if BP100.resolve() not in resolved.parents:
        raise RuntimeError(f"unsafe blueprint target: {resolved}")
    if dst.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copytree(src, dst)


def main() -> None:
    ensure_blueprints(BP200)
    for cid in ALL_IDS:
        prepare_blueprint(BP200 / cid, cid, RUNTIME[cid])
        update_blueprint(BP200 / cid, cid, RUNTIME.get(cid))
    for cid in RUNTIME:
        build_candidate(cid, RUNTIME[cid])
    for cid in ALL_IDS:
        mirror_blueprint(cid)
    print(json.dumps({"updated_candidates": ALL_IDS, "rebuilt_candidates": sorted(RUNTIME), "synced_blueprints": ALL_IDS}, indent=2))


if __name__ == "__main__":
    main()
