"""Stateless receipt preparation and read-only community preview on loopback."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .server import Handler
from .store import WorkflowError
from .artifacts import strict_json
from .github_flow import prepare_submission
from .community import CommunityStore

LIMIT = 8 * 1024 * 1024


class GitHubPortalHandler(Handler):
    def do_GET(self):
        try:
            self.guard()
            path = urlsplit(self.path).path
            if path == '/data/community.json':
                from .publication import public_board
                return self.send(public_board(self.server.store))
            if path == "/api/community":
                return self.send({"entries": self.server.store.entries(), "verification": "maintainer-reviewed"})
            if path.startswith("/api/"):
                raise WorkflowError("Route not found.", 404)
            if path.startswith("/participate/") and path not in {
                "/participate/", "/participate/index.html", "/participate/github-app.mjs", "/participate/github-static.mjs", "/participate/github-style.css"}:
                raise WorkflowError("File not found.", 404)
            return super().do_GET()
        except WorkflowError as exc:
            self.send({"error": str(exc)}, exc.status)

    def do_POST(self):
        try:
            self.guard()
            if urlsplit(self.path).path != "/api/prepare":
                raise WorkflowError("Route not found.", 404)
            if self.headers.get("Origin") != self.origin:
                raise WorkflowError("Cross-origin requests are not allowed.", 403)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise WorkflowError("Use application/json.", 415)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= LIMIT or self.headers.get("Transfer-Encoding"):
                raise WorkflowError("Choose a receipt smaller than 8 MB.", 413)
            self.connection.settimeout(10)
            body = strict_json(self.rfile.read(length))
            if not isinstance(body, dict) or set(body) != {"receipt"}:
                raise ValueError("Expected a receipt")
            # This endpoint stores nothing and invokes no external transport.
            return self.send(prepare_submission(body["receipt"]))
        except WorkflowError as exc:
            self.send({"error": str(exc)}, exc.status)
        except (ValueError, TypeError, RecursionError):
            self.send({"error": "The receipt is invalid or incomplete. Re-export the original run artifacts."}, 400)
        except TimeoutError:
            self.send({"error": "Request timed out."}, 408)


def make_server(port, data_dir):
    store = CommunityStore(Path(data_dir) / "community.sqlite")
    service = ThreadingHTTPServer(("127.0.0.1", port), GitHubPortalHandler)
    service.store = store
    service.portal_assets = ("github-section.html", "github-style.css", "github-app.mjs")
    return service
