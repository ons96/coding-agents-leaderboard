"""Checks for the cost/time/score combination columns."""
import unittest

import build_site

SPEC = {"score": "index", "time": "minutes", "time_unit": "min",
        "cost": "cost", "complete": ("index",)}


def make_block():
    return {"rows": [{"model": "A", "index": 10, "minutes": 2, "cost": 4}],
            "columns": ["model", "index", "minutes", "cost", "score_per_cost"],
            "labels": {}, "highlights": {},
            "col_groups": {"identity": ["model"], "derived": ["score_per_cost"]},
            "group_order": ["identity", "derived"], "group_labels": {}, "meta": {}}


class ComboColumnsTests(unittest.TestCase):
    def setUp(self):
        self.block = make_block()
        self.assertIs(build_site.add_combo_columns(self.block, SPEC), self.block)

    def test_columns_land_after_score_per_cost(self):
        cols = self.block["columns"]
        at = cols.index("score_per_cost")
        self.assertEqual(cols[at + 1:at + 4],
                         ["cost_per_min", "cost_plus_time", "score_per_all"])

    def test_labels_and_sort_direction(self):
        labels = self.block["labels"]
        for col in ("cost_per_min", "cost_plus_time", "score_per_all"):
            self.assertIn(col, labels)
            self.assertIn(col, self.block["highlights"])
        self.assertEqual(self.block["highlights"]["cost_per_min"], "lower")
        self.assertEqual(self.block["highlights"]["score_per_all"], "higher")

    def test_group_follows_score_per_cost(self):
        self.assertIn("cost_per_min", self.block["col_groups"]["derived"])
        self.assertEqual([g for g, m in self.block["col_groups"].items()
                          if "score_per_all" in m], ["derived"])

    def test_browser_metadata(self):
        self.assertEqual(self.block["combos"],
                         {"cost": ["cost"], "cost_scale": 1, "time": "minutes",
                          "time_unit": "min", "score": "index"})

    def test_cost_pair_has_a_scale(self):
        spec = dict(SPEC, cost=("a", "b"), cost_scale=1000)
        block = make_block()
        build_site.add_combo_columns(block, spec)
        self.assertEqual(block["combos"]["cost"], ["a", "b"])
        self.assertEqual(block["combos"]["cost_scale"], 1000)

    def test_no_cost_means_no_combo_columns(self):
        spec = {k: v for k, v in SPEC.items() if k != "cost"}
        original = make_block()
        self.assertIs(build_site.add_combo_columns(original, spec), original)
        self.assertNotIn("cost_per_min", original["columns"])
        self.assertNotIn("combos", original)


if __name__ == "__main__":
    unittest.main()
