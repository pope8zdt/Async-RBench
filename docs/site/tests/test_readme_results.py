"""Keep the README's numeric result tables aligned with the paper data."""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class ReadmeResultsTests(unittest.TestCase):
    def test_main_results_include_all_paper_scores_without_rerounding_deltas(self):
        paper = json.loads((ROOT / "docs/site/data/paper-results.json").read_text(encoding="utf-8"))
        results = (ROOT / "README.md").read_text(encoding="utf-8").split("## Main results", 1)[1].split("## Dataset", 1)[0]
        rows = [[cell.strip().replace("**", "") for cell in line.strip("|").split("|")]
                for line in results.splitlines() if line.startswith("|")]
        drs = [row for row in rows if len(row) == 11 and row[0] not in {"Model", "Mean"} and not row[0].startswith("---")]
        success = [row for row in rows if len(row) == 4 and row[0] not in {"Model", "Mean"} and not row[0].startswith("---")]
        self.assertEqual(len(drs), 9, "README must show all nine models from Table 3")
        self.assertEqual(len(success), 9, "README must show all nine models from Table 4")
        for record, drs_row, success_row in zip(paper["records"], drs, success, strict=True):
            label = record.get("paper_label", record["model"])
            self.assertEqual(drs_row[0], label)
            self.assertEqual(success_row[0], label)
            expected_scenarios = [f"{mean:.1f} ± {sd:.1f}" for mean, sd in
                                  zip(record["scenario_means"], record["scenario_sds"], strict=True)]
            self.assertEqual(drs_row[1:], expected_scenarios + [f'{record["drs"]:.1f}', f'{record["calls"]:.1f}'])
            self.assertEqual(success_row[1:], [f'{record[key]:.1f}' for key in ("batched", "async", "delta")])
        mean = paper["mean"]
        mean_rows = [row for row in rows if row[0] == "Mean"]
        self.assertEqual(mean_rows, [
            ["Mean"] + [f'{mean["scenarios"][key]:.1f}' for key in paper["scenario_order"]]
            + [f'{mean["drs"]:.1f}', f'{mean["calls"]:.1f}'],
            ["Mean"] + [f'{mean[key]:.1f}' for key in ("batched", "async", "delta")],
        ])


if __name__ == "__main__":
    unittest.main()
