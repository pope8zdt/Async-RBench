"""Check the deployed artifact, not the implementation's source text."""
import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from html import unescape
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


class ModelIcons(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img" and "model-icon" in attrs.get("class", "").split():
            self.icons.append(attrs)


class RankedResults(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lists = {}
        self.items = {}
        self.list_id = self.item = self.field = None
        self.table_count = 0
        self.in_details = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self.table_count += 1
        if tag == "ol":
            self.list_id = attrs.get("id")
            self.lists[self.list_id] = []
        elif tag == "li" and self.list_id:
            self.item = {"rank": attrs.get("value"), "fields": {}, "icons": []}
            self.items[attrs["data-record"] + ":" + self.list_id] = self.item
            self.lists[self.list_id].append(attrs["data-record"])
        elif tag == "aside" and "data-summary" in attrs:
            self.item = {"fields": {}}
            self.items[attrs["data-summary"]] = self.item
        if tag == "details" and self.item is not None:
            self.in_details = True
            self.item["disclosure"] = {"open": "open" in attrs, "fields": [], "summaries": 0}
        elif tag == "summary" and self.in_details:
            self.item["disclosure"]["summaries"] += 1
        if tag == "img" and self.item is not None:
            self.item["icons"].append(attrs)
        if self.item is not None and "data-field" in attrs:
            self.field = {"text": "", "bold": False}
            self.item["fields"][attrs["data-field"]] = self.field
            if self.in_details:
                self.item["disclosure"]["fields"].append(attrs["data-field"])
        elif tag == "strong" and self.field is not None:
            self.field["bold"] = True

    def handle_data(self, data):
        if self.field is not None:
            self.field["text"] += data

    def handle_endtag(self, tag):
        if tag == "dd":
            self.field = None
        elif tag in {"li", "aside"}:
            self.item = None
        elif tag == "ol":
            self.list_id = None
        elif tag == "details":
            self.in_details = False


class WebsiteBuildTests(unittest.TestCase):
    def test_paper26_snapshot_and_main_table_values_are_locked(self):
        data = json.loads((SITE / "data/paper-results.json").read_text(encoding="utf-8"))
        self.assertEqual(data["source"]["sha256"],
                         "a715e6f55535b2f8e50dc3c4c8d9284e745e214fc17f6f1cd535c2db626458d9")
        self.assertEqual(data["source"]["task_success"], "Table 4, page 8")
        numeric_snapshot = json.dumps({"records": data["records"], "mean": data["mean"]},
                                      sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(numeric_snapshot).hexdigest(),
                         "ff345cfe9be663a4cec013192b882ec1a067a8a6ff8e9f89d89c34a2ab5a8954")

    def test_formal_cli_examples_select_runtime_and_external_judge(self):
        output = self.build()
        for path in (ROOT / "README.md", output / "evaluate/index.html"):
            text = unescape(path.read_text(encoding="utf-8"))
            command = text.split("async-rbench-eval run-manifest", 1)[1].split("\n\n", 1)[0]
            for option in ("--profile reference_scaffold_api", "--runtime-mode api_only",
                           "--config <profile.yaml>", "--official-track", "--judge-root <judge-root>"):
                self.assertIn(option, command, path)

    def test_evaluation_links_to_judge_request_form_and_setup_guide(self):
        output = self.build()
        page = (output / "evaluate/index.html").read_text(encoding="utf-8")
        links = Links()
        links.feed(page)
        self.assertIn(
            "https://github.com/pope8zdt/Async-RBench/issues/new?template=judge-access.yml",
            links.links,
        )
        self.assertIn(
            "https://github.com/pope8zdt/Async-RBench/blob/main/docs/judge-bundle.md",
            links.links,
        )

    def test_evaluation_describes_requirements_without_editorial_status_labels(self):
        output = self.build()
        page = (output / "evaluate/index.html").read_text(encoding="utf-8")
        for label in ("未认证", "未验证", "未复核", "待验收", "The maintainer has reviewed",
                      "This update standardizes", "not a reproduction claim"):
            self.assertNotIn(label, page)
        for requirement in ("external judge", "frozen ERC", "command endpoints",
                            "blocked before model calls"):
            self.assertIn(requirement, page)

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
                drs_meters = [m for m in parser.meters if "DRS" in m["aria-label"]]
                self.assertEqual([float(m["value"]) for m in drs_meters],
                                 [45.1, 39.7, 38.2, 33.4, 31.1, 30.6, 29.8, 26.1, 19.2, 32.6])
                for meter in drs_meters:
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

    def test_ranked_cards_keep_all_paper_scenarios_uncertainty_and_mean(self):
        output = self.build()
        for route in ("index.html", "leaderboard/index.html"):
            parser = RankedResults()
            parser.feed((output / route).read_text(encoding="utf-8"))
            self.assertEqual(parser.table_count, 0)
            self.assertEqual(len(parser.lists.get("result-rows", [])), 9)
            self.assertEqual(parser.lists["result-rows"][0], "claude-sonnet-5")
            sonnet = parser.items["claude-sonnet-5:result-rows"]
            self.assertEqual(sonnet["rank"], "1")
            fields = sonnet["fields"]
            keys = ["delay", "stale", "conflict", "replay", "partial", "failure", "scope", "straggler"]
            self.assertEqual([fields[k]["text"] for k in keys],
                             ["38.7 ±1.8", "53.4 ±1.2", "39.9 ±2.1", "15.5 ±1.2", "29.8 ±1.7", "35.8 ±1.3", "66.9 ±1.9", "80.5 ±1.5"])
            self.assertEqual(fields["calls"]["text"], "77.1")
            self.assertEqual([fields[k]["bold"] for k in keys],
                             [True, True, False, False, False, True, False, False])
            self.assertEqual([parser.items["drs-mean"]["fields"][k]["text"] for k in keys + ["calls"]],
                             ["29.1", "40.2", "31.2", "8.6", "21.3", "12.2", "57.5", "60.7", "85.7"])

    def test_success_ranked_list_keeps_reported_rates_deltas_and_mean(self):
        output = self.build()
        parser = RankedResults()
        parser.feed((output / "leaderboard/index.html").read_text(encoding="utf-8"))
        self.assertEqual(len(parser.lists.get("success-rows", [])), 9)
        sonnet = parser.items["claude-sonnet-5:success-rows"]["fields"]
        self.assertEqual([sonnet[k]["text"] for k in ("batched", "async", "delta")],
                         ["42.3", "38.2", "-4.2"])
        self.assertEqual([parser.items["success-mean"]["fields"][k]["text"] for k in ("batched", "async", "delta")], ["29.7", "26.0", "-3.7"])

    def test_all_scenario_scores_are_readable_without_expanding_any_entry(self):
        output = self.build()
        for route in ("index.html", "leaderboard/index.html"):
            parser = RankedResults()
            parser.feed((output / route).read_text(encoding="utf-8"))
            cards = [item for key, item in parser.items.items() if key.endswith(":result-rows") or key == "drs-mean"]
            self.assertEqual(len(cards), 10)
            for card in cards:
                self.assertNotIn("disclosure", card, "Scenario scores must not require an expand action")
                self.assertCountEqual(card["fields"],
                                      ["delay", "stale", "conflict", "replay", "partial", "failure", "scope", "straggler", "calls"])

    def test_every_ranked_model_and_detail_page_has_its_local_brand_icon(self):
        output = self.build()
        icons = {
            "claude-sonnet-5": "claude-color.svg", "gpt-5.6-terra": "openai.svg",
            "qwen3.7-plus": "qwen-color.svg", "glm-5.3-flash": "zai.svg",
            "gpt-5.6-luna": "openai.svg", "deepseek-v4-pro": "deepseek-color.svg",
            "qwen3.5-27b": "qwen-color.svg", "kimi-k2.5": "kimi-color.svg",
            "gemini-3-flash-preview-thinking-high": "gemini-color.svg",
        }
        for route, lists in (("index.html", ["result-rows"]),
                             ("leaderboard/index.html", ["result-rows", "success-rows"])):
            parser = RankedResults()
            parser.feed((output / route).read_text(encoding="utf-8"))
            for list_id in lists:
                for model, filename in icons.items():
                    images = parser.items[model + ":" + list_id]["icons"]
                    self.assertEqual(len(images), 1, (route, model))
                    self.assertEqual(images[0]["src"], f"/Async-RBench/assets/model-icons/{filename}")
                    self.assertEqual(images[0].get("alt"), "", "Adjacent model text supplies the accessible name")
        for model, filename in icons.items():
            parser = ModelIcons()
            parser.feed((output / f"runs/{model}/index.html").read_text(encoding="utf-8"))
            self.assertEqual([i["src"] for i in parser.icons], [f"/Async-RBench/assets/model-icons/{filename}"])
            self.assertTrue((output / "assets/model-icons" / filename).is_file())
        license_text = (output / "assets/model-icons/LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright", license_text)

    def test_model_scenarios_are_readable_without_a_table(self):
        output = self.build()
        page = (output / "runs/claude-sonnet-5/index.html").read_text(encoding="utf-8")
        self.assertNotIn("<table", page)
        self.assertIn('data-field="straggler"', page)
        self.assertIn("±1.5", page)

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
        # Exact paper26 Figure 6 extraction; Gemini Native subagent calls = 58.1.
        self.assertEqual(
            hashlib.sha256((output / "assets/full-rebuild.png").read_bytes()).hexdigest(),
            "24879dd1ad91d3599d67c0e0c17cef53c62967319e77368de841d88caac12dd0",
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
