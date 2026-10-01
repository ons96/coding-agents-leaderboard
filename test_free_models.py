"""Behavioral checks for the reviewed free-host dashboard."""
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


if __name__ == "__main__":
    unittest.main()
