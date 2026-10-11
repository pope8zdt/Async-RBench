"""Check the deployed artifact, not the implementation's source text."""
import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[3]
SITE = ROOT / "docs" / "site"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for key, value in attrs if key in {"href", "src"})


class WebsiteBuildTests(unittest.TestCase):
    def build(self, base="/Async-RBench"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "site"
        result = subprocess.run(
            [sys.executable, str(SITE / "build.py"), "--output", str(output),
             "--base-path", base], capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return output

    def test_publication_contains_five_routes_and_no_broken_local_assets(self):
        for base in ("/Async-RBench", ""):
            with self.subTest(base=base):
                output = self.build(base)
                for route in ("", "tasks", "leaderboard", "evaluate", "docs"):
                    page = output / route / "index.html"
                    self.assertTrue(page.is_file(), route)
                for page in output.rglob("*.html"):
                    parser = Links()
                    parser.feed(page.read_text(encoding="utf-8"))
                    for link in parser.links:
                        parts = urlsplit(link)
                        if parts.scheme or parts.netloc or not parts.path:
                            continue
                        self.assertTrue(parts.path.startswith(base + "/"), (page, link))
                        relative = unquote(parts.path[len(base):]).lstrip("/")
                        target = output / relative
                        if parts.path.endswith("/"):
                            target /= "index.html"
                        self.assertTrue(target.is_file(), (page, link))

    def test_catalog_exports_only_public_registered_metadata(self):
        output = self.build()
        corpus = json.loads((output / "data/corpus.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "data/async-rbench/registry.json").read_text(encoding="utf-8"))
        self.assertEqual(len(corpus["tasks"]), 200)
        self.assertEqual({t["id"] for t in corpus["tasks"]}, {c["case_id"] for c in registry["case_families"]})
        self.assertEqual(sorted(Counter(t["source"] for t in corpus["tasks"]).values()), [40] * 5)
        self.assertEqual(Counter(t["difficulty"] for t in corpus["tasks"]), {"medium": 104, "hard": 96})
        self.assertEqual(sum(t["subtasks"] for t in corpus["tasks"]), 621)
        for task in corpus["tasks"]:
            self.assertEqual(set(task), {"id", "title", "source", "difficulty", "subtasks", "url"})
        self.assertFalse((output / "data/async-rbench").exists())
        self.assertFalse((output / "configs").exists())
        self.assertFalse(any(p.suffix == ".pdf" for p in output.rglob("*")))

    def test_paper_download_preserves_reported_scores_and_unrounded_deltas(self):
        output = self.build()
        data = json.loads((output / "data/leaderboard.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / "paper_artifacts/experiment_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({r["id"] for r in data["records"]}, set(manifest["model_identifiers"]))
        self.assertEqual(data["status"], "paper_reported")
        self.assertEqual(data["protocol"]["episodes"], 10800)
        sonnet = next(r for r in data["records"] if r["id"] == "claude-sonnet-5")
        self.assertEqual((sonnet["drs"], sonnet["batched"], sonnet["async"], sonnet["delta"]), (45.1, 42.3, 38.2, -4.2))
        for record in data["records"]:
            self.assertEqual(len(record["scenarios"]), 8)
            self.assertAlmostEqual(sum(s["mean"] for s in record["scenarios"].values()) / 8, record["drs"], delta=0.06)

    def test_builder_refuses_nonempty_output_instead_of_overwriting_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            marker = output / "keep.txt"
            marker.write_text("user data", encoding="utf-8")
            result = subprocess.run([sys.executable, str(SITE / "build.py"), "--output", str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(marker.read_text(encoding="utf-8"), "user data")

    def test_full_rebuild_figure_is_the_frozen_manuscript_render(self):
        output = self.build()
        # Figure 6 contains 55.5, not the older repository plot's 58.1.
        self.assertEqual(
            hashlib.sha256((output / "assets/full-rebuild.png").read_bytes()).hexdigest(),
            "c6779afabc2252bfb3abf8ddd24ac3e48efd16ef86520adcc45da1deb32218b3",
        )


if __name__ == "__main__":
    unittest.main()
