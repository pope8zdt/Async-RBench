from __future__ import annotations
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
