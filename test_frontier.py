"""Checks for the three published Pareto columns."""
import unittest

import build_site

SPEC = {"score": "index", "time": "minutes", "cost": "cost", "complete": ("index",)}


def make_block(rows):
    return {"rows": rows,
            "columns": ["slug", "model", "index", "score_per_minute", "minutes", "cost"],
            "labels": {}, "highlights": {},
            "col_groups": {"core": ["score_per_minute"]},
            "group_order": ["core"], "group_labels": {"core": "Core"},
            "meta": {}}


class FrontierColumnsTests(unittest.TestCase):
    def setUp(self):
        rows = [
            # cheapest per Index + fastest, so it is on all three frontiers
            {"slug": "fast", "model": "Fast", "index": 10, "score_per_minute": 1,
             "minutes": 1, "cost": 5},
            # cheap but slower: loses the fast/Index and cheap/Index frontiers
            {"slug": "cheap-fast", "model": "Cheap Fast", "index": 10,
             "score_per_minute": 0.5, "minutes": 5, "cost": 0.5},
            # cheapest at Index 10, so the cheap/Index frontier keeps it
            {"slug": "cheap-slow", "model": "Cheap Slow", "index": 10,
             "score_per_minute": 0.2, "minutes": 20, "cost": 0.2},
            # top Index: on all three
            {"slug": "smart", "model": "Smart", "index": 12, "score_per_minute": 0.4,
             "minutes": 2, "cost": 9},
            # beaten on time, cost and Index
            {"slug": "meh", "model": "Meh", "index": 9, "score_per_minute": 0.1,
             "minutes": 5, "cost": 6},
        ]
        self.block = build_site.add_frontier_columns(make_block(rows), SPEC)

    def flags(self, col):
        return {row["slug"] for row in self.block["rows"] if row[col]}

    def test_fast_frontier(self):
        self.assertEqual(self.flags("pareto"), {"fast", "smart"})

    def test_time_and_cost_frontier(self):
        self.assertEqual(self.flags("pareto_cost"),
                         {"fast", "smart", "cheap-fast", "cheap-slow"})

    def test_cost_only_frontier_ignores_time(self):
        self.assertEqual(self.flags("pareto_cheap"), {"cheap-slow", "smart"})

    def test_filter_metadata_matches_columns(self):
        cols = self.block["columns"]
        frontier = self.block["frontier"]
        self.assertEqual([f["col"] for f in frontier["filters"]],
                         ["pareto", "pareto_cost", "pareto_cheap"])
        for filter_spec in frontier["filters"]:
            self.assertIn(filter_spec["col"], cols)
            self.assertIn(filter_spec["col"], self.block["labels"])

    def test_missing_cost_never_joins_cost_frontiers(self):
        rows = [{"slug": "nofee", "model": "No fee", "index": 99,
                 "score_per_minute": 99, "minutes": 99, "cost": None}]
        block = build_site.add_frontier_columns(make_block(rows), SPEC)
        self.assertEqual([r["pareto"] for r in block["rows"]], [True])
        self.assertEqual([r["pareto_cost"] for r in block["rows"]], [False])
        self.assertEqual([r["pareto_cheap"] for r in block["rows"]], [False])


if __name__ == "__main__":
    unittest.main()
