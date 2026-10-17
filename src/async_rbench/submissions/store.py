"""Immutable revisions, transactional reviews, and a separate community listing."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import re
import uuid

from .validation import digest, validate_bundle

REVIEW_CHECKS = ["identity_and_settings", "coverage_and_scores", "evidence_inspected", "simulation_acknowledged"]
PARTICIPANTS = {"participant", "other-participant"}


class WorkflowError(ValueError):
    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.status, self.details = status, details


class Store:
    def __init__(self, path, policy):
        self.path, self.policy = Path(path), policy
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, status TEXT NOT NULL,
                    revision INTEGER NOT NULL, version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (
                    submission_id TEXT NOT NULL REFERENCES submissions(id), revision INTEGER NOT NULL,
                    hash TEXT NOT NULL, bundle TEXT NOT NULL, validation TEXT NOT NULL,
                    PRIMARY KEY(submission_id, revision));
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
                    note TEXT NOT NULL, checks TEXT NOT NULL, created TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _row(self, db, sid, actor):
        if not isinstance(sid, str) or not re.fullmatch(r"[0-9a-f]{32}", sid):
            raise WorkflowError("Invalid submission identifier.")
        row = db.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if row is None or (actor != "maintainer" and row["owner"] != actor):
            raise WorkflowError("Submission not found.", 404)
        return dict(row)

    def _history(self, db, sid, rev, actor, action, note="", checks=()):
        db.execute("INSERT INTO history(submission_id,revision,actor,action,note,checks,created) VALUES(?,?,?,?,?,?,?)",
                   (sid, rev, actor, action, note, json.dumps(checks), datetime.now(timezone.utc).isoformat()))

    def submit(self, actor, bundle, sid=None, version=None):
        if actor not in PARTICIPANTS:
            raise WorkflowError("Only a participant can submit a package.", 403)
        if sid is not None and (not isinstance(sid, str) or not re.fullmatch(r"[0-9a-f]{32}", sid)):
            raise WorkflowError("Invalid submission identifier.")
        validation = validate_bundle(bundle, self.policy)
        if not validation["valid"]:
            raise WorkflowError("Package validation failed.", 422, validation)
        package_hash = digest(bundle)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if sid:
                row = self._row(db, sid, actor)
                if type(version) is not int or row["version"] != version:
                    raise WorkflowError("This submission changed. Refresh before continuing.", 409)
                if row["status"] != "changes_requested":
                    raise WorkflowError("A new revision is allowed only after changes are requested.", 409)
                rev = row["revision"] + 1
                db.execute("UPDATE submissions SET status='pending',revision=?,version=version+1 WHERE id=?", (rev, sid))
            else:
                prior = db.execute("SELECT s.id FROM submissions s JOIN revisions r ON r.submission_id=s.id AND r.revision=s.revision WHERE s.owner=? AND r.hash=?", (actor, package_hash)).fetchone()
                if prior:
                    sid = prior["id"]
                    return self._detail(db, actor, sid)
                sid, rev = uuid.uuid4().hex, 1
                db.execute("INSERT INTO submissions VALUES(?,?,'pending',1,1)", (sid, actor))
            db.execute("INSERT INTO revisions VALUES(?,?,?,?,?)", (sid, rev, package_hash, json.dumps(bundle, allow_nan=False), json.dumps(validation)))
            self._history(db, sid, rev, actor, "submitted")
            return self._detail(db, actor, sid)

    def _detail(self, db, actor, sid):
        row = self._row(db, sid, actor)
        revision = db.execute("SELECT * FROM revisions WHERE submission_id=? AND revision=?", (sid, row["revision"])).fetchone()
        row.update(bundle=json.loads(revision["bundle"]), validation=json.loads(revision["validation"]), hash=revision["hash"])
        row["history"] = [dict(r) for r in db.execute("SELECT revision,actor,action,note,checks,created FROM history WHERE submission_id=? ORDER BY id", (sid,))]
        row["revisions"] = [dict(r) for r in db.execute("SELECT revision,hash FROM revisions WHERE submission_id=? ORDER BY revision", (sid,))]
        return row

    def get(self, actor, sid):
        with self.connection() as db:
            return self._detail(db, actor, sid)

    def list(self, actor):
        if actor not in PARTICIPANTS | {"maintainer"}:
            raise WorkflowError("Sign in using a local demo role.", 401)
        with self.connection() as db:
            rows = db.execute("SELECT id FROM submissions WHERE owner=? OR ?='maintainer' ORDER BY rowid DESC", (actor, actor))
            return [self._summary(self._detail(db, actor, r["id"])) for r in rows]

    def _summary(self, row):
        return {k: row[k] for k in ("id", "owner", "status", "revision", "version", "hash")} | {
            "metadata": row["bundle"]["metadata"], "metrics": row["validation"]["metrics"], "simulated": True}

    def review(self, actor, sid, version, action, checks, note):
        if actor != "maintainer":
            raise WorkflowError("Maintainer access required.", 403)
        if action not in ("approve", "reject", "changes_requested", "withdraw"):
            raise WorkflowError("Unknown review decision.")
        if not isinstance(note, str) or not note.strip() or len(note) > 2000:
            raise WorkflowError("Add a review reason (up to 2,000 characters).")
        if not isinstance(checks, list) or any(not isinstance(c, str) for c in checks):
            raise WorkflowError("Invalid review checklist.")
        if action == "approve" and set(checks) != set(REVIEW_CHECKS):
            raise WorkflowError("Complete every evidence check before approval.")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._detail(db, actor, sid)
            if type(version) is not int or row["version"] != version:
                raise WorkflowError("A newer revision or decision exists. Refresh and review it.", 409)
            if row["owner"] == actor or row["status"] != ("approved" if action == "withdraw" else "pending"):
                raise WorkflowError("This decision is not allowed in the current state.", 409)
            if action == "approve":
                valid = validate_bundle(row["bundle"], self.policy)
                if not valid["valid"] or digest(row["bundle"]) != row["hash"]:
                    raise WorkflowError("Stored evidence failed revalidation.", 422)
            status = {"approve": "approved", "reject": "rejected", "withdraw": "withdrawn"}.get(action, action)
            db.execute("UPDATE submissions SET status=?,version=version+1 WHERE id=?", (status, sid))
            self._history(db, sid, row["revision"], actor, action, note.strip(), checks)
            return self._detail(db, actor, sid)

    def leaderboard(self):
        with self.connection() as db:
            entries = []
            for r in db.execute("SELECT id FROM submissions WHERE status='approved'"):
                row = self._detail(db, "maintainer", r["id"])
                valid = validate_bundle(row["bundle"], self.policy)
                if valid["valid"] and digest(row["bundle"]) == row["hash"]:
                    row["validation"] = valid
                    entries.append(self._summary(row))
            return sorted(entries, key=lambda row: (-row["metrics"]["drs"], row["id"]))
