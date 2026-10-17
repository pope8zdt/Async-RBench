"""Loopback-only demo server. No model calls, Docker, public identity or deployment."""
from __future__ import annotations

import argparse
import base64
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import re
from pathlib import Path
import secrets
import time
from urllib.parse import unquote, urlsplit

from .demo import ROOT, demo_bundle, demo_policy
from .store import PARTICIPANTS, REVIEW_CHECKS, Store, WorkflowError
from .validation import validate_bundle

LIMIT = 2 * 1024 * 1024


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("Non-finite JSON number")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # Never log uploaded packages, cookies or CSRF tokens.

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def send(self, value, status=200, cookie=None, content_type="application/json; charset=utf-8", script_hashes=()):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() if isinstance(value, (dict, list)) else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        scripts = " ".join(["'self'", *script_hashes])
        self.send_header("Content-Security-Policy", f"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src {scripts}; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header("Set-Cookie", f"arbench_demo={cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600")
        self.end_headers()
        self.wfile.write(data)

    def guard(self):
        if self.headers.get("Host") != self.origin.split("//")[1] or self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise WorkflowError("Only this local preview origin is allowed.", 403)

    def session(self, required=True):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            pass
        token = cookie.get("arbench_demo")
        sid = token.value if token else ""
        session = self.server.sessions.get(sid)
        if session and session["expires"] > time.time():
            return sid, session
        if required:
            raise WorkflowError("Choose a local demo identity first.", 401)
        return None, None

    def new_session(self, role=None):
        now = time.time()
        for token, value in list(self.server.sessions.items()):
            if value["expires"] <= now:
                self.server.sessions.pop(token, None)
        if len(self.server.sessions) >= 100:
            raise WorkflowError("Too many local demo sessions.", 429)
        sid = secrets.token_urlsafe(32)
        session = {"role": role, "csrf": secrets.token_urlsafe(32), "expires": now + 3600}
        self.server.sessions[sid] = session
        return sid, session

    def do_GET(self):
        try:
            self.guard()
            path = urlsplit(self.path).path
            if path == "/api/session":
                sid, session = self.session(False)
                if session is None:
                    sid, session = self.new_session()
                return self.send({"role": session["role"], "csrf": session["csrf"], "demo": True}, cookie=sid)
            if path == "/api/demo-package":
                return self.send(demo_bundle(self.server.store.policy))
            if path == "/api/leaderboard":
                return self.send({"entries": self.server.store.leaderboard(), "simulated": True, "paper_unchanged": True})
            if path.startswith("/api/submissions"):
                _, session = self.session()
                actor = session["role"]
                if actor is None:
                    raise WorkflowError("Choose a demo identity.", 401)
                if path == "/api/submissions":
                    return self.send({"items": self.server.store.list(actor)})
                parts = path.strip("/").split("/")
                if len(parts) == 3:
                    return self.send(self.server.store.get(actor, parts[2]))
            if path.startswith("/api/"):
                raise WorkflowError("Route not found.", 404)
            if path in {"/participate", "/participate/", "/participate/index.html"}:
                self.send_response(302)
                self.send_header("Location", "/benchmark/#participate")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                return
            portal = path.startswith("/participate/")
            root = ROOT / ("docs/submissions/ui" if portal else "docs/site/published")
            relative = path.removeprefix("/participate/").lstrip("/") if portal else path.lstrip("/")
            relative = unquote(relative)
            if "\\" in relative or ".." in relative.split("/") or ":" in relative:
                raise WorkflowError("File not found.", 404)
            target = (root / relative).resolve()
            if target.is_dir():
                target /= "index.html"
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                raise WorkflowError("File not found.", 404)
            kind = "text/javascript" if target.suffix == ".mjs" else mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            content = target.read_bytes()
            if target == (ROOT / "docs/site/published/benchmark/index.html").resolve():
                # Local response overlay only: the committed site and paper assets stay byte-identical.
                content = content.replace(b'href="#sharing"', b'href="#participate"')
                section, stylesheet, script = getattr(self.server, "portal_assets", ("section.html", "embedded.css", "app.mjs"))
                fragment = (ROOT / "docs/submissions/ui" / section).read_bytes()
                content = content.replace(b"</main>", fragment + b"</main>", 1)
                overlay = f'<link rel="stylesheet" href="/participate/{stylesheet}"><script type="module" src="/participate/{script}"></script></head>'.encode()
                content = content.replace(b"</head>", overlay, 1)
            # Authorize exact trusted static bootstraps (language/theme restoration),
            # never arbitrary inline scripts or participant-supplied package data.
            script_hashes = []
            if not portal and target.suffix == ".html":
                for script in re.findall(rb"<script>(.*?)</script>", content, re.S):
                    normalized = script.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                    fingerprint = base64.b64encode(hashlib.sha256(normalized).digest()).decode()
                    script_hashes.append(f"'sha256-{fingerprint}'")
            return self.send(content, content_type=kind + ("; charset=utf-8" if kind.startswith("text/") else ""), script_hashes=script_hashes)
        except WorkflowError as e:
            self.send({"error": str(e), "details": e.details}, e.status)

    def do_POST(self):
        try:
            self.guard()
            if self.headers.get("Origin") != self.origin:
                raise WorkflowError("Cross-origin changes are not allowed.", 403)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise WorkflowError("Use application/json.", 415)
            sid, session = self.session()
            if not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
                raise WorkflowError("Invalid session token. Refresh the preview.", 403)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= LIMIT or self.headers.get("Transfer-Encoding"):
                raise WorkflowError("Package must be a JSON file smaller than 2 MB.", 413)
            self.connection.settimeout(10)
            body = strict_json(self.rfile.read(length))
            if not isinstance(body, dict):
                raise WorkflowError("Expected a JSON object.")
            path = urlsplit(self.path).path
            if path == "/api/session":
                role = body.get("role")
                if not isinstance(role, str) or role not in PARTICIPANTS | {"maintainer"}:
                    raise WorkflowError("Unknown demo identity.", 403)
                self.server.sessions.pop(sid, None)
                sid, session = self.new_session(role)
                return self.send({"role": role, "csrf": session["csrf"], "demo": True}, cookie=sid)
            actor = session["role"]
            if actor is None:
                raise WorkflowError("Choose a demo identity.", 401)
            if path == "/api/validate":
                return self.send(validate_bundle(body.get("bundle"), self.server.store.policy))
            if path == "/api/submissions":
                return self.send(self.server.store.submit(actor, body.get("bundle"), body.get("id"), body.get("version")), 201)
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "submissions"] and parts[3] == "review":
                return self.send(self.server.store.review(actor, parts[2], body.get("version"), body.get("action"), body.get("checks"), body.get("note")))
            raise WorkflowError("Route not found.", 404)
        except WorkflowError as e:
            self.send({"error": str(e), "details": e.details}, e.status)
        except (ValueError, TypeError, RecursionError):
            self.send({"error": "Invalid JSON or request fields."}, 400)
        except TimeoutError:
            self.send({"error": "Request timed out."}, 408)


def make_server(port, data_dir):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.store = Store(Path(data_dir) / "submissions.sqlite", demo_policy())
    server.sessions = {}
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", required=True, help="Acknowledge synthetic data and demo identities")
    parser.add_argument("--port", type=int, default=8773)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "dist/submission-demo")
    args = parser.parse_args()
    service = make_server(args.port, args.data_dir)
    print(f"Local simulation only: http://127.0.0.1:{args.port}/benchmark/#participate", flush=True)
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.server_close()


if __name__ == "__main__":
    main()
