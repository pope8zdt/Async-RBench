from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
import argparse


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINTS = ROOT / "candidate_cases" / "rebuild-to-100" / "blueprints"
OUTPUT = ROOT / "candidate_cases" / "rebuild-to-100" / "runtime-mab-db"


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def selected_database_rows() -> list[dict]:
    manifest = json.loads((OUTPUT.parent / "selection-manifest.json").read_text(encoding="utf-8"))
    audit = json.loads((OUTPUT.parent / "selection-audit.json").read_text(encoding="utf-8"))
    audited = {row["case_id"]: row for row in audit["cases"]}
    rows = [row for row in manifest["cases"] if row["source_task_id"].startswith("database:")]
    for row in rows:
        if not audited.get(row["case_id"], {}).get("passed"):
            raise ValueError(f"selection audit did not pass: {row['case_id']}")
    if len(rows) != 11:
        raise ValueError(f"expected 11 selected database rows, got {len(rows)}")
    return rows


def sql_tables(sql: str) -> list[str]:
    return sorted(set(re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][\w]*)", sql, re.I)))


RUNTIME = r'''from __future__ import annotations
import hashlib, json, sqlite3, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE / "case_spec.json").read_text(encoding="utf-8"))

def emit(kind, evidence, logical_clock):
    payload = {"receipt_id": f"{SPEC['case_id']}:{logical_clock}", "result_kind": kind,
               "released_at": logical_clock, "logical_clock": logical_clock,
               "evidence": evidence, "source_task_id": SPEC["source_task_id"]}
    with (HERE / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")
    return payload

def initialize():
    db = HERE / "runtime.db"
    db.unlink(missing_ok=True)
    conn = sqlite3.connect(db, timeout=.05)
    conn.executescript("CREATE TABLE runtime_seed(id INTEGER PRIMARY KEY, payload TEXT); INSERT INTO runtime_seed(payload) VALUES ('source-bound');")
    conn.commit()
    return conn

def run():
    (HERE / "events.jsonl").unlink(missing_ok=True)
    conn = initialize()
    anomaly = SPEC["anomaly"]
    provisional = emit("provisional_specialist_result", {"diagnosis": SPEC["decoy"], "probe": "role_profile"}, 1)
    checkpoint = {"logical_clock": 2, "db_digest_before": hashlib.sha256((HERE / "runtime.db").read_bytes()).hexdigest()}
    if anomaly == "INSERT_LARGE_DATA":
        conn.execute("CREATE TABLE load_probe(id INTEGER PRIMARY KEY, payload TEXT)")
        conn.executemany("INSERT INTO load_probe(payload) VALUES (?)", [("x" * SPEC["bounded_payload_size"],)] * SPEC["bounded_rows"])
        conn.commit(); evidence = {"inserted_rows": conn.execute("SELECT COUNT(*) FROM load_probe").fetchone()[0], "table": "load_probe"}
    elif anomaly == "FETCH_LARGE_DATA":
        conn.execute("CREATE TABLE fetch_probe(id INTEGER PRIMARY KEY, payload TEXT)")
        conn.executemany("INSERT INTO fetch_probe(payload) VALUES (?)", [("y" * SPEC["bounded_payload_size"],)] * SPEC["bounded_rows"])
        conn.commit(); rows = conn.execute("SELECT * FROM fetch_probe").fetchall()
        evidence = {"fetched_rows": len(rows), "payload_bytes": sum(len(r[1]) for r in rows)}
    elif anomaly == "VACUUM":
        conn.execute("CREATE TABLE vacuum_probe(id INTEGER PRIMARY KEY, payload TEXT)")
        conn.executemany("INSERT INTO vacuum_probe(payload) VALUES (?)", [("z" * 40,)] * SPEC["bounded_rows"])
        conn.commit(); conn.execute("VACUUM")
        evidence = {"vacuum_completed": True, "page_count": conn.execute("PRAGMA page_count").fetchone()[0]}
    elif anomaly == "REDUNDANT_INDEX":
        conn.execute("CREATE TABLE index_probe(id INTEGER PRIMARY KEY, key_value TEXT)")
        conn.execute("CREATE INDEX idx_probe_a ON index_probe(key_value)")
        conn.execute("CREATE INDEX idx_probe_b ON index_probe(key_value)")
        conn.commit(); indexes = [r[1] for r in conn.execute("PRAGMA index_list(index_probe)")]
        evidence = {"same_column_index_count": len(indexes), "indexes": sorted(indexes)}
    elif anomaly == "LOCK_CONTENTION":
        conn.execute("CREATE TABLE lock_probe(id INTEGER PRIMARY KEY, value TEXT)"); conn.execute("INSERT INTO lock_probe VALUES (1, 'a')"); conn.commit()
        blocker = sqlite3.connect(HERE / "runtime.db", timeout=.05); waiter = sqlite3.connect(HERE / "runtime.db", timeout=.05)
        blocker.execute("BEGIN EXCLUSIVE"); blocker.execute("UPDATE lock_probe SET value='blocked' WHERE id=1")
        observed = False
        try: waiter.execute("UPDATE lock_probe SET value='waiter' WHERE id=1")
        except sqlite3.OperationalError as exc: observed = "locked" in str(exc).lower()
        blocker.rollback(); blocker.close(); waiter.close()
        evidence = {"lock_error_observed": observed, "probe": "exclusive_writer"}
    else: raise ValueError(anomaly)
    checkpoint["db_digest_after"] = hashlib.sha256((HERE / "runtime.db").read_bytes()).hexdigest()
    checkpoint["state_changed"] = checkpoint["db_digest_before"] != checkpoint["db_digest_after"]
    dump = lambda p, x: p.write_text(json.dumps(x, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    dump(HERE / "checkpoint.json", checkpoint)
    authoritative = emit("authoritative_environment_result", {"diagnosis": anomaly, **evidence}, 3)
    report = {"case_id": SPEC["case_id"], "environment_initialized": True, "adapter_executed": True,
              "source_native_marble_executed": False, "anomaly_probe_executed": True,
              "native_evaluator_executed": False, "runtime_evaluator": "source-bound sqlite adapter",
              "checkpoint": checkpoint, "receipts": [provisional, authoritative]}
    dump(HERE / "runtime_report.json", report)
    conn.close()
    return report

if __name__ == "__main__": print(json.dumps(run(), sort_keys=True))
'''


VERIFY = r'''from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
spec = json.loads((HERE / "case_spec.json").read_text(encoding="utf-8"))
candidate = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "resolution.json"
errors=[]
try: answer=json.loads(candidate.read_text(encoding="utf-8"))
except Exception as exc: answer={}; errors.append(f"invalid_resolution:{exc.__class__.__name__}")
try: report=json.loads((HERE / "runtime_report.json").read_text(encoding="utf-8"))
except Exception: report={}; errors.append("runtime_report_missing")
receipts=report.get("receipts", [])
auth=next((r for r in receipts if r.get("result_kind")=="authoritative_environment_result"), None)
if not report.get("adapter_executed"): errors.append("adapter_not_executed")
if not report.get("anomaly_probe_executed"): errors.append("anomaly_probe_not_executed")
if report.get("source_native_marble_executed"): errors.append("false_native_execution_claim")
if not report.get("checkpoint",{}).get("state_changed"): errors.append("missing_state_change")
if not auth: errors.append("authoritative_receipt_missing")
if answer.get("diagnosis") != spec["anomaly"]: errors.append("wrong_diagnosis")
if auth and answer.get("adopted_receipt_id") != auth.get("receipt_id"): errors.append("authoritative_receipt_not_adopted")
if answer.get("superseded_diagnosis") != spec["decoy"]: errors.append("conflict_not_reconciled")
if answer.get("finalized_after_logical_clock", -1) < 3: errors.append("premature_finalization")
result={"case_id":spec["case_id"],"passed":not errors,"errors":errors,
        "qualification":"adapter_verified" if not errors else "failed",
        "source_native_marble_executed":False,"native_evaluator_executed":False}
print(json.dumps(result, sort_keys=True)); raise SystemExit(0 if not errors else 1)
'''


def materialize(row: dict) -> dict:
    case_id = row["case_id"]
    blueprint = BLUEPRINTS / case_id
    native_path = blueprint / "private" / "source_manifests" / "01-native_case.json"
    native = json.loads(native_path.read_text(encoding="utf-8"))
    anomaly = native["native_runtime"]["environment"]["anomalies"][0]["anomaly"]
    profiles = {r["agent_id"]: r["profile"] for r in native["native_runtime"]["roles"]}
    correct_role = next((k for k, v in profiles.items() if anomaly in v), "agent1")
    decoy = next((a for a in ["LOCK_CONTENTION", "FETCH_LARGE_DATA", "VACUUM", "REDUNDANT_INDEX", "INSERT_LARGE_DATA"] if a != anomaly), "UNKNOWN")
    out = OUTPUT / case_id
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(blueprint, out)
    spec = {
        "schema_version": "async-rbench-mab-db-runtime-v1",
        "case_id": case_id,
        "source_task_id": row["source_task_id"],
        "source_record_sha256": native["source_binding"]["record_sha256"],
        "anomaly": anomaly,
        "decoy": decoy,
        "authoritative_role": correct_role,
        "tables": sql_tables(native["native_runtime"]["environment"]["init_sql"]),
        "bounded_rows": 160 + int(row["source_task_id"].split(":")[1]),
        "bounded_payload_size": 32 + row["shard"] * 8,
        "event_design": "conflicting specialist result resolved by post-checkpoint environment evidence",
    }
    dump(out / "runtime" / "case_spec.json", spec)
    write(out / "runtime" / "adapter.py", RUNTIME)
    write(out / "runtime" / "verify.py", VERIFY)
    correct = {"diagnosis": anomaly, "superseded_diagnosis": decoy,
               "adopted_receipt_id": f"{case_id}:3", "finalized_after_logical_clock": 3,
               "remediation": f"Apply bounded remediation for {anomaly} after checking {correct_role} environment evidence."}
    dump(out / "runtime" / "oracle_resolution.json", correct)
    equivalent = dict(correct)
    equivalent["remediation"] = f"Use the authoritative {anomaly} probe; invalidate only the provisional {decoy} branch."
    dump(out / "runtime" / "equivalent_resolution.json", equivalent)
    wrong = dict(correct); wrong["diagnosis"] = decoy
    ignored = dict(correct); ignored["adopted_receipt_id"] = f"{case_id}:1"
    dump(out / "runtime" / "negative_wrong_diagnosis.json", wrong)
    dump(out / "runtime" / "negative_ignored_authority.json", ignored)
    semantic = {"version": "1", "checks": [
        {"id": f"{case_id}.diagnosis", "weight": 0.35, "kind": "exact", "expected": anomaly},
        {"id": f"{case_id}.authority", "weight": 0.35, "kind": "receipt_adoption", "clock": 3},
        {"id": f"{case_id}.state", "weight": 0.30, "kind": "runtime_probe", "anomaly": anomaly},
    ]}
    control = {"version": "1", "event_contracts": [{"event_id": f"{case_id}:3", "release_after_checkpoint": 2}], "checks": [
        {"id": f"{case_id}.checkpoint_before_authority", "weight": 0.5},
        {"id": f"{case_id}.reconcile_conflict", "weight": 0.5},
    ]}
    dump(out / "task" / "tests" / "semantic_checks.json", semantic)
    dump(out / "task" / "tests" / "control_flow_checks.json", control)
    dump(out / "private" / "runtime_qualification.json", {
        "environment_initialization": "implemented",
        "bounded_anomaly_probe": "implemented",
        "source_native_marble_execution": "not_executed",
        "native_evaluator_execution": "not_executed",
        "promotion_ready": False,
    })
    return {"case_id": case_id, "source_task_id": row["source_task_id"], "anomaly": anomaly,
            "status": "materialized_unverified", "output": str(out.relative_to(ROOT)).replace("\\", "/")}


def main() -> None:
    from candidate_write_guard import guard_for_root
    parser=argparse.ArgumentParser(description="Materialize the selected MAB database batch safely")
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--confirm-materialize",action="store_true")
    parser.add_argument("--case-local-repair",action="store_true")
    args=parser.parse_args()
    selected=selected_database_rows()
    guards=[guard_for_root(ROOT,row["case_id"],case_local_repair=args.case_local_repair) for row in selected]
    if args.dry_run:
        print(json.dumps({"dry_run":True,"writes_performed":False,"guards":guards})); return
    if not args.confirm_materialize:
        parser.error("writing requires --confirm-materialize; use --dry-run to inspect")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = [materialize(row) for row in selected]
    dump(OUTPUT / "batch_manifest.json", {"schema_version": "async-rbench-mab-db-batch-v1", "cases": rows})
    print(json.dumps({"materialized": len(rows), "output": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
