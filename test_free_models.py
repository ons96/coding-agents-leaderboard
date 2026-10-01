"""Behavioral checks for the free hosted base-model dashboard."""
import unittest

import build_site


class FreeDashboardTests(unittest.TestCase):
    def test_frontier_and_unfiltered_rows(self):
        source = {
            "rows": [
                {"slug": "fast", "model": "Fast", "intelligenceIndex": 10,
                 "score_per_minute": 100},
                {"slug": "dominated", "model": "Dominated", "intelligenceIndex": 9,
                 "score_per_minute": 90},
                {"slug": "smart", "model": "Smart", "intelligenceIndex": 12,
                 "score_per_minute": 80},
                {"slug": "unscored", "model": "Unscored", "intelligenceIndex": None,
                 "score_per_minute": None},
            ],
            "labels": {}, "meta": {"scrape_date": "2026-10-01"},
        }
        original = build_site.FREE_MODELS
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json
        try:
            with TemporaryDirectory() as directory:
                path = Path(directory) / "inventory.json"
                path.write_text(json.dumps({"checked_date": "2026-10-01",
                                            "models": {slug: [{"provider": "Test",
                                                              "model_id": slug,
                                                              "url": "https://example.org/" + slug,
                                                              "note": "Test route"}]
                                                       for slug in ("fast", "dominated", "smart", "unscored")}}))
                build_site.FREE_MODELS = path
                block, notice = build_site.free_tab(source)
        finally:
            build_site.FREE_MODELS = original
        self.assertEqual([row["slug"] for row in block["rows"]],
                         ["fast", "dominated", "smart"])
        self.assertEqual([row["pareto"] for row in block["rows"]],
                         [True, False, True])
        self.assertIn("estimated", notice.lower())
        self.assertIn("reasoning effort assumed", notice.lower())

    def test_inventory_expands_scored_effort_variants(self):
        import json
        inventory = json.loads(build_site.FREE_MODELS.read_text())
        index = json.loads(build_site.DATA.read_text())
        rows = next(tab["data"] for tab in index["tabs"] if tab["id"] == "models_full")
        block, notice = build_site.free_tab(rows)
        present = {row["slug"] for row in block["rows"]}
        self.assertTrue({"gemini-3-7-flash-low", "gemini-3-7-flash-medium",
                         "gemini-3-7-flash", "qwen3-8-27b-medium",
                         "qwen3-8-27b-non-reasoning"} <= present)
        self.assertGreater(len(block["rows"]), 4)
        self.assertTrue(present <= inventory["models"].keys())
        self.assertIn("reasoning effort assumed", notice.lower())


if __name__ == "__main__":
    unittest.main()
