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


class ScoreMeters(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meters = []

    def handle_starttag(self, tag, attrs):
        if tag == "meter":
            self.meters.append(dict(attrs))


class ResultTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = {}
        self.table = self.row = self.cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self.table = self.tables.setdefault(attrs.get("id", ""), [])
        elif tag == "tr" and self.table is not None:
            self.row = {"id": attrs.get("data-record"), "cells": []}
            self.table.append(self.row)
        elif tag in {"th", "td"} and self.row is not None:
            self.cell = {"text": "", "bold": False, **attrs}
            self.row["cells"].append(self.cell)
        elif tag == "strong" and self.cell is not None:
            self.cell["bold"] = True

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"] += data

    def handle_endtag(self, tag):
        if tag in {"td", "th"}:
            self.cell = None
        elif tag == "tr":
            self.row = None
        elif tag == "table":
            self.table = None


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

    def test_main_scores_have_accessible_fixed_scale_meters_on_both_leaderboards(self):
        output = self.build()
        for route in ("index.html", "leaderboard/index.html"):
            with self.subTest(route=route):
                parser = ScoreMeters()
                parser.feed((output / route).read_text(encoding="utf-8"))
                self.assertEqual([float(m["value"]) for m in parser.meters],
                                 [45.1, 39.7, 38.2, 33.4, 31.1, 30.6, 29.8, 26.1, 19.2, 32.6])
                for meter in parser.meters:
                    self.assertEqual((meter["min"], meter["max"]), ("0", "100"))
                    self.assertIn("DRS", meter["aria-label"])
                    self.assertEqual(meter.get("aria-valuetext"), f'{meter["value"]} / 100')

    def test_model_detail_exposes_the_same_drs_scale(self):
        output = self.build()
        parser = ScoreMeters()
        parser.feed((output / "runs/claude-sonnet-5/index.html").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(parser.meters), 1)
        meter = parser.meters[0]
        self.assertEqual((meter["value"], meter["min"], meter["max"]), ("45.1", "0", "100"))
        self.assertIn("DRS", meter["aria-label"])

    def test_main_table_matches_paper_scenarios_uncertainty_and_column_order(self):
        output = self.build()
        for route in ("index.html", "leaderboard/index.html"):
            parser = ResultTables()
            parser.feed((output / route).read_text(encoding="utf-8"))
            self.assertIn("main-results", parser.tables)
            rows = parser.tables["main-results"]
            self.assertEqual([c.get("data-column") for c in rows[0]["cells"]],
                             ["model", "delay", "stale", "conflict", "replay", "partial", "failure", "scope", "straggler", "calls", "drs"])
            self.assertEqual(len(rows), 11)  # Header, nine agents, paper mean.
            sonnet = next(r for r in rows if r["id"] == "claude-sonnet-5")
            self.assertEqual([c["text"] for c in sonnet["cells"][1:10]],
                             ["38.7 ±1.8", "53.4 ±1.2", "39.9 ±2.1", "15.5 ±1.2", "29.8 ±1.7", "35.8 ±1.3", "66.9 ±1.9", "80.5 ±1.5", "77.1"])
            self.assertEqual([c["bold"] for c in sonnet["cells"][1:9]],
                             [True, True, False, False, False, True, False, False])
            self.assertEqual([c["text"] for c in rows[-1]["cells"][1:10]],
                             ["29.1", "40.2", "31.2", "8.6", "21.3", "12.2", "57.5", "60.7", "85.7"])

    def test_task_success_is_a_separate_table_with_reported_deltas(self):
        output = self.build()
        parser = ResultTables()
        parser.feed((output / "leaderboard/index.html").read_text(encoding="utf-8"))
        self.assertIn("success-results", parser.tables)
        rows = parser.tables["success-results"]
        sonnet = next(r for r in rows if r["id"] == "claude-sonnet-5")
        self.assertEqual([c["text"] for c in sonnet["cells"]],
                         ["Claude Sonnet 5", "42.3", "38.2", "-4.2"])
        self.assertEqual([c["text"] for c in rows[-1]["cells"][1:]], ["29.7", "26.0", "-3.7"])

    def test_scenario_mean_row_and_csv_keep_paper_values(self):
        import csv
        output = self.build()
        data = json.loads((output / "data/leaderboard.json").read_text(encoding="utf-8"))
        self.assertEqual(data["mean"].get("scenarios"),
                         {"delay": 29.1, "stale": 40.2, "conflict": 31.2, "replay": 8.6,
                          "partial": 21.3, "failure": 12.2, "scope": 57.5, "straggler": 60.7})
        with (output / "data/leaderboard.csv").open(encoding="utf-8", newline="") as stream:
            sonnet = next(csv.DictReader(stream))
        self.assertEqual((sonnet.get("delay_mean"), sonnet.get("delay_sd")), ("38.7", "1.8"))
        self.assertEqual(sonnet["delta"], "-4.2")

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

    def test_task_catalog_precedes_scenario_reference(self):
        output = self.build()
        page = (output / "tasks/index.html").read_text(encoding="utf-8")
        self.assertTrue('id="scenarios"' in page, "Scenario reference is missing")
        self.assertLess(page.index('id="task-search"'), page.index('id="scenarios"'))

    def test_each_page_has_one_bilingual_main_heading(self):
        output = self.build()
        for path in output.rglob("*.html"):
            page = path.read_text(encoding="utf-8")
            self.assertEqual(page.count("<h1>"), 1, str(path))
            heading = page.split("<h1>")[1].split("</h1>")[0]
            # Proper model/project names are shared across languages.
            if 'class="i18n"' in heading:
                self.assertIn('lang="zh"', heading)
                self.assertIn('lang="en"', heading)

    def test_missing_page_and_historical_results_have_distinct_explanations(self):
        output = self.build()
        missing = (output / "404.html").read_text(encoding="utf-8")
        archived = (output / "runs/e87590fa970dc29a/index.html").read_text(encoding="utf-8")
        history_url = "https://github.com/pope8zdt/Async-RBench/tree/19e21e50fbea45812a3d845e1ade8c3a842ca9a9/website"
        self.assertTrue(history_url in archived, "Archived result must link to its original record")
        self.assertFalse(history_url in missing, "An unknown URL must not be described as an archived experiment")


if __name__ == "__main__":
    unittest.main()
