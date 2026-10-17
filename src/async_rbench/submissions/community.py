"""Local community results. Deliberately unrelated to paper result storage."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


class CommunityStore:
    def __init__(self, path):
        self.path = Path(path).resolve()
        published = Path(__file__).resolve().parents[3] / "docs/site/published"
        if self.path.is_relative_to(published.resolve()):
            raise ValueError("Community storage must be outside the paper site")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS community (
                    issue INTEGER PRIMARY KEY, source_updated TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, status TEXT NOT NULL, summary TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS community_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, issue INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL, status TEXT NOT NULL, record TEXT NOT NULL,
                    recorded_at TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, issue, source_updated, fingerprint, status, summary, audit):
        conflict = False
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM community WHERE issue=?", (issue,)).fetchone()
            if old and old["source_updated"] > source_updated:
                raise ValueError("An older GitHub snapshot cannot replace the current decision")
            if old and old["source_updated"] == source_updated:
                if old["status"] == "conflicted":
                    raise ValueError("GitHub snapshots conflict; add a fresh review decision")
                if old["fingerprint"] != fingerprint:
                    # GitHub timestamps have second precision. Ambiguity must not list.
                    conflict = True
                    status, summary = "conflicted", {}
                    audit = {**audit, "conflict_with": old["fingerprint"]}
            if old and old["fingerprint"] == fingerprint and old["status"] == status:
                # Even a no-op decision observed later advances the stale-read barrier.
                db.execute("UPDATE community SET source_updated=? WHERE issue=?", (source_updated, issue))
                return
            db.execute("INSERT INTO community VALUES(?,?,?,?,?) ON CONFLICT(issue) DO UPDATE SET source_updated=excluded.source_updated,fingerprint=excluded.fingerprint,status=excluded.status,summary=excluded.summary",
                       (issue, source_updated, fingerprint, status, json.dumps(summary, allow_nan=False)))
            db.execute("INSERT INTO community_history(issue,fingerprint,status,record,recorded_at) VALUES(?,?,?,?,?)",
                       (issue, fingerprint, status, json.dumps(audit, allow_nan=False), datetime.now(timezone.utc).isoformat()))
        if conflict:
            # Raise after commit so an ambiguous former approval stays unlisted.
            raise ValueError("GitHub snapshots conflict; add a fresh review decision")

    def entries(self):
        with self.connection() as db:
            rows = [json.loads(row["summary"]) for row in db.execute("SELECT summary FROM community WHERE status='approved'")]
        return sorted(rows, key=lambda r: (-r["metrics"]["drs"], r["issue"]))

    def history(self, issue):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT status,record,recorded_at FROM community_history WHERE issue=? ORDER BY id", (issue,))]
