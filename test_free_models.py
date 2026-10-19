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
        import re
        inventory = json.loads(build_site.FREE_MODELS.read_text())
        index = json.loads(build_site.DATA.read_text())
        source = next(tab["data"] for tab in index["tabs"] if tab["id"] == "models_full")
        block, notice = build_site.free_tab(source)
        present = {row["slug"] for row in block["rows"]}
        # The dashboard documents that inventory entries without an Index or
        # score/min estimate are omitted, and upstream speed data appears and
        # disappears over time. Assert the exact rendered set for the current
        # snapshot rather than pinning slugs that may become unscored.
        scored = {row["slug"] for row in source["rows"]
                  if row.get("score_per_minute") and row.get("intelligenceIndex") is not None}
        self.assertEqual(present, scored & set(inventory["models"]))
        self.assertGreater(len(present), 4)
        # Effort variants of a base model must expand into separate rows rather
        # than collapsing into one base-model entry.
        families = {}
        for slug in present:
            base = re.sub(r"-(low|medium|high|xhigh|max|non-reasoning)$", "", slug)
            families.setdefault(base, []).append(slug)
        self.assertTrue(any(len(variants) > 1 for variants in families.values()))
        self.assertIn("reasoning effort assumed", notice.lower())


class MainTabsEnrichmentTests(unittest.TestCase):
    def test_pareto_keep_rule_matches_free_tab(self):
        rows = [
            {"slug": "fast", "model": "Fast", "creator": "C",
             "intelligence_index": 10, "score_per_minute": 100},
            {"slug": "dominated", "model": "Dominated", "creator": "C",
             "intelligence_index": 9, "score_per_minute": 90},
            {"slug": "smart", "model": "Smart", "creator": "C",
             "intelligence_index": 12, "score_per_minute": 80},
            {"slug": "unscored", "model": "Unscored", "creator": "C",
             "intelligence_index": None, "score_per_minute": None},
        ]
        payload = {"tabs": [{"id": "models", "data": {
            "rows": rows, "columns": ["slug", "model", "creator",
                                      "intelligence_index", "score_per_minute"],
            "labels": {}, "highlights": {}, "col_groups": {"core": ["score_per_minute"]},
            "group_order": ["core"], "group_labels": {"core": "Core"},
            "meta": {"row_count": 4, "scrape_date": "2026-10-01"}}}]}
        original = build_site.FREE_MODELS
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json
        with TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            path.write_text(json.dumps({"checked_date": "2026-10-01", "models": {}}))
            build_site.FREE_MODELS = path
            try:
                build_site.enrich_main_tabs(payload)
            finally:
                build_site.FREE_MODELS = original
        flags = [r["pareto"] for r in payload["tabs"][0]["data"]["rows"]]
        self.assertEqual(flags, [True, False, True, False])
        cols = payload["tabs"][0]["data"]["columns"]
        self.assertIn("pareto", cols)
        self.assertIn("has_free_api", cols)
        self.assertIn("free_access", cols)

    def test_agents_slugless_match_and_slug_match(self):
        payload = {"tabs": [
            {"id": "agents", "data": {
                "rows": [{"model": "Kimi K3", "creator": "M",
                          "index_score": 1.0, "score_per_minute": 1.0}],
                "columns": ["model", "creator", "index_score", "score_per_minute"],
                "labels": {}, "highlights": {},
                "col_groups": {"identity": ["model", "creator"]},
                "group_order": ["identity"], "group_labels": {"identity": "I"},
                "meta": {"row_count": 1, "scrape_date": "2026-10-01"}}},
            {"id": "models", "data": {
                "rows": [{"slug": "kimi-k3", "model": "Kimi K3", "creator": "M",
                          "intelligence_index": 1.0, "score_per_minute": 1.0},
                         {"slug": "paid-only", "model": "Paid", "creator": "M",
                          "intelligence_index": 2.0, "score_per_minute": 0.5}],
                "columns": ["slug", "model", "creator", "intelligence_index",
                            "score_per_minute"],
                "labels": {}, "highlights": {},
                "col_groups": {"identity": ["slug"]},
                "group_order": ["identity"], "group_labels": {"identity": "I"},
                "meta": {"row_count": 2, "scrape_date": "2026-10-01"}}},
        ]}
        original = build_site.FREE_MODELS
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json
        with TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            path.write_text(json.dumps({
                "checked_date": "2026-10-01",
                "models": {"kimi-k3": [{"provider": "Test", "model_id": "kimi-k3",
                                        "url": "https://example.org/", "note": "t"}]}}))
            build_site.FREE_MODELS = path
            try:
                build_site.enrich_main_tabs(payload)
            finally:
                build_site.FREE_MODELS = original
        agent = payload["tabs"][0]["data"]["rows"][0]
        self.assertTrue(agent["has_free_api"])
        self.assertIn("Test", agent["free_access"])
        mrows = payload["tabs"][1]["data"]["rows"]
        self.assertTrue(mrows[0]["has_free_api"])
        self.assertFalse(mrows[1]["has_free_api"])
        self.assertEqual(mrows[1]["free_access"], "")


if __name__ == "__main__":
    unittest.main()
