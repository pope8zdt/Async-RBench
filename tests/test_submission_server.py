from __future__ import annotations

import http.client
import json
import threading
import hashlib
import base64
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from async_rbench.submissions.server import make_server
from async_rbench.submissions.store import REVIEW_CHECKS


@pytest.fixture
def server(tmp_path):
    service = make_server(0, tmp_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    yield service
    service.shutdown()
    service.server_close()
    thread.join()


class Client:
    def __init__(self, server):
        self.port = server.server_address[1]
        self.cookie, self.csrf = "", ""

    def call(self, path, data=None, headers=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        h = {"Cookie": self.cookie, "Origin": f"http://127.0.0.1:{self.port}",
             "X-CSRF-Token": self.csrf, "Content-Type": "application/json"}
        h.update(headers or {})
        c.request("POST" if data is not None or raw is not None else "GET", path,
                  body=raw if raw is not None else json.dumps(data) if data is not None else None, headers=h)
        r = c.getresponse()
        if r.getheader("Set-Cookie"):
            self.cookie = r.getheader("Set-Cookie").split(";")[0]
        content = r.read()
        self.response_headers = dict(r.getheaders())
        kind = r.getheader("Content-Type")
        status = r.status
        c.close()
        return status, json.loads(content) if "json" in kind else content.decode()

    def login(self, role):
        status, data = self.call("/api/session")
        self.csrf = data["csrf"]
        status, data = self.call("/api/session", {"role": role})
        assert status == 200
        self.csrf = data["csrf"]


def test_http_submit_review_and_list(server):
    user, reviewer = Client(server), Client(server)
    user.login("participant")
    _, bundle = user.call("/api/demo-package")
    status, item = user.call("/api/submissions", {"bundle": bundle})
    assert status == 201
    assert user.call("/api/leaderboard")[1]["entries"] == []
    reviewer.login("maintainer")
    assert reviewer.call("/api/submissions")[1]["items"][0]["id"] == item["id"]
    status, approved = reviewer.call(f"/api/submissions/{item['id']}/review", {
        "version": 1, "action": "approve", "checks": REVIEW_CHECKS, "note": "Synthetic evidence inspected"})
    assert status == 200 and approved["status"] == "approved"
    assert user.call("/api/leaderboard")[1]["entries"][0]["metrics"]["drs"] == 64.8
    assert "bundle" not in user.call("/api/leaderboard")[1]["entries"][0]


def test_http_auth_csrf_origin_host_and_validation(server):
    c = Client(server)
    assert c.call("/api/submissions")[0] == 401
    c.login("participant")
    _, bundle = c.call("/api/demo-package")
    for headers in [{"Origin": "https://evil.example"}, {"X-CSRF-Token": "bad"}, {"Host": "evil.example"}]:
        assert c.call("/api/submissions", {"bundle": bundle}, headers)[0] == 403
    assert c.call("/api/submissions", {"bundle": bundle}, {"Content-Type": "text/plain"})[0] == 415
    assert c.call("/api/submissions", raw='{"bundle":1,"bundle":2}')[0] == 400
    assert c.call("/api/submissions", raw='{"bundle": NaN}')[0] == 400
    bundle["scores"].pop()
    assert c.call("/api/submissions", {"bundle": bundle})[0] == 422
    assert c.call("/api/submissions")[1]["items"] == []


def test_cannot_read_other_submission_or_approve_as_participant(server):
    a, b = Client(server), Client(server)
    a.login("participant")
    _, bundle = a.call("/api/demo-package")
    _, item = a.call("/api/submissions", {"bundle": bundle})
    b.login("other-participant")
    assert b.call(f"/api/submissions/{item['id']}")[0] == 404
    assert a.call(f"/api/submissions/{item['id']}/review", {"version": 1, "action": "approve", "checks": REVIEW_CHECKS, "note": "self"})[0] == 403


def test_serves_local_portal_and_readonly_paper_site(server):
    c = Client(server)
    for path in ("/participate/", "/participate/index.html"):
        assert c.call(path)[0] == 302
        assert c.response_headers["Location"] == "/benchmark/#participate"
    assert c.call("/")[0] == 200
    assert c.call("/benchmark/")[0] == 200
    assert c.call("/../pyproject.toml")[0] == 404
    assert c.call("/api/not-a-route")[0] == 404
    c.login("participant")
    assert c.call("/api/session", {"role": "administrator"})[0] == 403


def test_existing_share_link_enters_local_flow_without_modifying_site(server):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.targets = []
            self.ids = []
            self.main_depth = 0
            self.section_in_main = False
            self.assets = []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "main":
                self.main_depth += 1
            if "id" in attrs:
                self.ids.append(attrs["id"])
            if attrs.get("id") == "participate":
                self.section_in_main = self.main_depth == 1
            if tag == "a":
                self.targets.append(attrs.get("href"))
            if tag == "script" and attrs.get("src", "").startswith("/participate/"):
                self.assets.append(attrs["src"])
            if tag == "link" and attrs.get("href", "").startswith("/participate/"):
                self.assets.append(attrs["href"])
        def handle_endtag(self, tag):
            if tag == "main":
                self.main_depth -= 1
    root = Path(__file__).resolve().parents[1]
    file = root / "docs/site/published/benchmark/index.html"
    before = file.read_bytes()
    parser = Links()
    client = Client(server)
    parser.feed(client.call("/benchmark/")[1])
    assert "#participate" in parser.targets
    assert parser.section_in_main
    assert parser.ids.count("main") == 1
    assert len(parser.ids) == len(set(parser.ids))
    assert client.call('/benchmark/')[1].count('data-paper-record=') == 9
    assert client.call('/data/community.json')[1]['entries'] == []
    assert len(parser.assets) == 2
    for asset in parser.assets:
        assert client.call(asset)[0] == 200
    assert file.read_bytes() == before
    protected = json.loads((root / "docs/site/publication-integrity.json").read_text())["protected"]
    for name, expected in protected.items():
        assert hashlib.sha256((root / "docs/site/published" / name).read_bytes()).hexdigest() == expected


def test_bad_submission_identifier_returns_error_not_broken_connection(server):
    c = Client(server)
    c.login("participant")
    _, bundle = c.call("/api/demo-package")
    status, data = c.call("/api/submissions", {"bundle": bundle, "id": ["bad"], "version": 1})
    assert status == 400
    assert "error" in data


def test_local_preview_allows_only_trusted_inline_preference_bootstrap(server):
    client = Client(server)
    _, page = client.call("/benchmark/")
    bootstrap = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    fingerprint = base64.b64encode(hashlib.sha256(bootstrap.encode()).digest()).decode()
    policy = client.response_headers["Content-Security-Policy"]
    script_policy = next(part for part in policy.split(";") if part.strip().startswith("script-src"))
    assert f"'sha256-{fingerprint}'" in script_policy
    assert "'unsafe-inline'" not in script_policy
    client.call("/api/demo-package")
    assert fingerprint not in client.response_headers["Content-Security-Policy"]
