import hashlib
import json
from pathlib import Path
import threading

import pytest

from async_rbench.submissions.github_server import make_server
from async_rbench.submissions.artifacts import export_receipt
from async_rbench.submissions.__main__ import main
from test_submission_server import Client
from submission_fixtures import runner_files


@pytest.fixture
def local_service(tmp_path):
    service = make_server(0, tmp_path / "community")
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    yield service
    service.shutdown()
    service.server_close()
    thread.join()


def test_main_page_has_only_public_participation_and_no_role_switch(local_service):
    client = Client(local_service)
    status, page = client.call("/benchmark/")
    assert status == 200
    from html.parser import HTMLParser
    class Controls(HTMLParser):
        def __init__(self):
            super().__init__()
            self.views, self.ids, self.assets = [], [], []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if "data-view" in attrs: self.views.append(attrs["data-view"])
            if "id" in attrs: self.ids.append(attrs["id"])
            url = attrs.get("src", attrs.get("href", ""))
            if url.startswith("/participate/"): self.assets.append(url)
    controls = Controls()
    controls.feed(page)
    assert controls.views == ["submit", "community"]
    assert "submission-identity" not in controls.ids
    assert len(controls.ids) == len(set(controls.ids))
    for url in controls.assets: assert client.call(url)[0] == 200
    for path in ["/api/session", "/api/demo-package", "/api/submissions", "/participate/app.mjs"]:
        assert client.call(path)[0] == 404


def test_prepare_is_stateless_and_community_starts_empty(local_service, tmp_path):
    client = Client(local_service)
    run, manifest, audit, meta, _ = runner_files(tmp_path)
    receipt = export_receipt(run, manifest, audit, meta)
    status, draft = client.call("/api/prepare", {"receipt": receipt})
    assert status == 200
    assert draft["url"].startswith("https://github.com/pope8zdt/Async-RBench/issues/new?")
    assert client.call("/api/community")[1]["entries"] == []
    assert list(local_service.store.path.parent.iterdir()) == [local_service.store.path]
    for headers in [{"Origin": "https://evil.example"}, {"Host": "evil.example"}, {"Content-Type": "text/plain"}]:
        assert client.call("/api/prepare", {"receipt": receipt}, headers)[0] in (403, 415)
    assert client.call("/api/prepare", raw='{"receipt":1,"receipt":2}')[0] == 400
    assert client.call("/api/submissions", {"role": "maintainer"})[0] == 404


def test_paper_bytes_are_unchanged(local_service):
    root = Path(__file__).resolve().parents[1]
    published = root / "docs/site/published"
    before = (published / "benchmark/index.html").read_bytes()
    assert Client(local_service).call("/benchmark/")[0] == 200
    assert (published / "benchmark/index.html").read_bytes() == before
    for name, fingerprint in json.loads((root / "docs/site/publication-integrity.json").read_text())["protected"].items():
        assert hashlib.sha256((published / name).read_bytes()).hexdigest() == fingerprint


def test_export_and_check_cli_do_not_need_github_or_models(tmp_path, capsys):
    run, manifest, audit, meta, _ = runner_files(tmp_path)
    output = tmp_path / "receipt.json"
    assert main(["export", "--run-root", str(run), "--manifest", str(manifest), "--audit", str(audit),
                 "--agent", meta["agent"], "--model", meta["model"], "--organization", meta["organization"],
                 "--code-revision", meta["code_revision"], "--output", str(output)]) == 0
    assert output.is_file()
    assert main(["check", str(output)]) == 0
    assert "PRIVATE-DO-NOT-EXPORT" not in capsys.readouterr().out
