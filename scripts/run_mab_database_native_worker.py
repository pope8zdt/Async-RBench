from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import msvcrt
import psycopg2


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class FileLock:
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        deadline = time.time() + 120
        while True:
            try:
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                return self
            except OSError:
                if time.time() >= deadline:
                    raise TimeoutError("postgres runtime lock timeout")
                time.sleep(.2)

    def __exit__(self, *_args):
        self.handle.seek(0)
        msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        self.handle.close()


def connect():
    return psycopg2.connect(dbname="sysbench", user="test", password="Test123_456", host="127.0.0.1", port=5432)


def scalar(cur, sql, params=None):
    cur.execute(sql, params); return cur.fetchone()[0]


def reset_and_initialize(native):
    conn = connect(); conn.autocommit = True; cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public; CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    init_sql = native["native_runtime"]["environment"].get("init_sql") or ""
    init_error = None
    if init_sql.strip():
        try: cur.execute(init_sql)
        except Exception as exc: init_error = type(exc).__name__ + ":" + str(exc)[:200]
    return conn, cur, init_error


def execute_anomaly(cur, anomaly, case_slug):
    table = "dtb_" + case_slug[-10:].replace("-", "_")
    if anomaly == "INSERT_LARGE_DATA":
        cur.execute("CREATE TABLE %s(id bigint, payload text)" % table)
        cur.execute("INSERT INTO %s SELECT i, repeat(md5(i::text), 8) FROM generate_series(1,5000) i" % table)
        return {"row_count": scalar(cur, "SELECT count(*) FROM %s" % table), "bytes": scalar(cur, "SELECT pg_total_relation_size(%s)", (table,))}
    if anomaly == "FETCH_LARGE_DATA":
        cur.execute("CREATE TABLE %s(id bigint, payload text)" % table)
        cur.execute("INSERT INTO %s SELECT i, repeat(md5(i::text), 8) FROM generate_series(1,5000) i" % table)
        cur.execute("SELECT * FROM %s" % table); rows = cur.fetchall()
        return {"fetched_rows": len(rows), "payload_bytes": sum(len(r[1]) for r in rows)}
    if anomaly == "VACUUM":
        cur.execute("CREATE TABLE %s(id bigint, payload text) WITH (autovacuum_enabled=false)" % table)
        cur.execute("INSERT INTO %s SELECT i, md5(i::text) FROM generate_series(1,5000) i" % table)
        cur.execute("DELETE FROM %s WHERE id <= 4500" % table); cur.execute("VACUUM FULL %s" % table)
        return {"remaining_rows": scalar(cur, "SELECT count(*) FROM %s" % table), "vacuum_full_executed": True}
    if anomaly == "REDUNDANT_INDEX":
        cur.execute("CREATE TABLE %s(id bigint, key_value text)" % table)
        cur.execute("CREATE INDEX %s_a ON %s(key_value)" % (table, table)); cur.execute("CREATE INDEX %s_b ON %s(key_value)" % (table, table))
        return {"same_column_indexes": scalar(cur, "SELECT count(*) FROM pg_indexes WHERE tablename=%s AND indexdef LIKE '%%(key_value)'", (table,))}
    if anomaly == "LOCK_CONTENTION":
        cur.execute("CREATE TABLE %s(id bigint primary key, payload text)" % table); cur.execute("INSERT INTO %s VALUES (1,'seed')" % table)
        blocker = connect(); waiter = connect(); blocker.autocommit = False; waiter.autocommit = False
        b = blocker.cursor(); w = waiter.cursor(); b.execute("UPDATE %s SET payload='held' WHERE id=1" % table)
        w.execute("SET statement_timeout='250ms'"); timeout_observed = False
        try: w.execute("UPDATE %s SET payload='waiter' WHERE id=1" % table)
        except psycopg2.errors.QueryCanceled: timeout_observed = True; waiter.rollback()
        lock_rows = scalar(cur, "SELECT count(*) FROM pg_locks WHERE pid=%s", (blocker.get_backend_pid(),))
        blocker.rollback(); blocker.close(); waiter.close()
        return {"waiter_timeout_observed": timeout_observed, "blocker_lock_rows": lock_rows}
    raise ValueError(anomaly)


def main():
    p = argparse.ArgumentParser(); p.add_argument("--spec", required=True); p.add_argument("--native-case", required=True); p.add_argument("--output", required=True); p.add_argument("--lock", required=True); a=p.parse_args()
    spec=json.loads(Path(a.spec).read_text(encoding="utf-8")); native=json.loads(Path(a.native_case).read_text(encoding="utf-8")); errors=[]
    with FileLock(a.lock):
        conn, cur, init_error = reset_and_initialize(native)
        before={"tables": scalar(cur,"SELECT count(*) FROM pg_tables WHERE schemaname='public'"), "txid": scalar(cur,"SELECT txid_current()")}
        try: anomaly_evidence=execute_anomaly(cur,spec["anomaly"],spec["case_id"])
        except Exception as exc: anomaly_evidence={}; errors.append("anomaly_execution:"+type(exc).__name__+":"+str(exc)[:200])
        after={"tables":scalar(cur,"SELECT count(*) FROM pg_tables WHERE schemaname='public'"), "txid":scalar(cur,"SELECT txid_current()"), "pg_version":scalar(cur,"SHOW server_version")}
        checkpoint={"owner":"host_runtime", "before":before, "after":after, "anomaly_evidence":anomaly_evidence}
        checkpoint["sha256"]=digest(checkpoint)
        # This is the actual upstream MARBLE evaluator. Its DB method records predictions but does not itself compute correctness.
        try:
            from marble.evaluator.evaluator import Evaluator
            evaluator=Evaluator({"evaluate_llm":{"model":"offline/canonical"}})
            prediction=spec["anomaly"]
            evaluator.evaluate_task_db("canonical database diagnosis", prediction, [spec["anomaly"]], 1, [spec["anomaly"]])
            native_metrics=evaluator.metrics["task_evaluation"]
            evaluator_binding_score=1.0 if native_metrics.get("predicted")==spec["anomaly"] and native_metrics.get("root_cause")==[spec["anomaly"]] else 0.0
        except Exception as exc:
            native_metrics={}; evaluator_binding_score=0.0; errors.append("native_evaluator:"+type(exc).__name__+":"+str(exc)[:200])
        conn.close()
    anomaly_valid = bool(anomaly_evidence) and all(value is not False and value != 0 for value in anomaly_evidence.values())
    if not anomaly_valid: errors.append("anomaly_evidence_invalid")
    report={"schema_version":"async-rbench-mab-db-native-canonical-v1", "case_id":spec["case_id"], "source_task_id":spec["source_task_id"],
            "passed":not errors and evaluator_binding_score==1.0, "errors":errors, "postgres_environment_reset":True,
            "source_init_sql_attempted":bool(native["native_runtime"]["environment"].get("init_sql")), "source_init_sql_error":init_error,
            "anomaly":spec["anomaly"], "anomaly_driver":"bounded PostgreSQL workload matching MARBLE anomaly semantics",
            "upstream_marble_evaluator":"marble.evaluator.evaluator.Evaluator.evaluate_task_db", "native_evaluator_metrics":native_metrics,
            "evaluator_binding_score":evaluator_binding_score, "host_checkpoint":checkpoint,
            "source_native_marble_verified":not errors and anomaly_valid, "native_evaluator_verified":not errors and evaluator_binding_score==1.0,
            "model_episode_executed":False, "canonical_episode_owner":"evaluator", "resource_lock":"exclusive_serial_postgres"}
    report["evidence_sha256"]=digest(report)
    Path(a.output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,sort_keys=True)); return 0 if report["passed"] else 1

if __name__=="__main__": raise SystemExit(main())
