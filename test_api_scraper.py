import unittest

import json
from src.api_scraper import parse_search_api_page, MIN_PROVIDER_ROWS, discover_provider_ids


HEAD = "<h2>Search API Public Leaderboard</h2><table><tr>" + "".join(
    f"<th>{x}</th>" for x in ["Provider", "Artificial Analysis Search Index", "Baseline Lift", "DeepSearchQA F1", "BrowseComp Accuracy", "Omniscience Accuracy", "Search $/1k USD / 1k tasks", "Model $/1k USD / 1k tasks", "Time per Task Seconds"]
) + "</tr>"


class SearchApiParserTests(unittest.TestCase):
    def test_discovers_ids_from_page(self):
        html = r'\"id\":\"alpha-search-api\" blah \"id\":\"beta-search-api\"'
        self.assertEqual(discover_provider_ids(html), ["alpha-search-api", "beta-search-api"])
    def test_typed_metrics_and_baseline(self):
        rows = "".join(f"<tr><td>Provider {i}</td><td>80</td><td>47</td><td>81</td><td>87</td><td>72</td><td>$62.30</td><td>$8.04</td><td>26.8s</td></tr>" for i in range(MIN_PROVIDER_ROWS))
        html = HEAD + rows + '</table>'
        result = parse_search_api_page(html, "https://example.test")
        self.assertEqual(result["rows"][0]["search_cost_usd_per_1000_tasks"], 62.3)
        self.assertEqual(result["rows"][-1]["baseline_lift"], 47)
        self.assertAlmostEqual(result["rows"][0]["search_index_per_second"], 80 / 26.8)

    def test_incomplete_data_rejected(self):
        with self.assertRaises(ValueError):
            parse_search_api_page("<h2>Search API Public Leaderboard</h2><table></table>", "x")

    def test_zero_time_has_no_efficiency_value(self):
        rows = "".join(f"<tr><td>Provider {i}</td><td>80</td><td>47</td><td>81</td><td>87</td><td>72</td><td>$62.30</td><td>$8.04</td><td>0s</td></tr>" for i in range(MIN_PROVIDER_ROWS))
        result = parse_search_api_page(HEAD + rows + "</table>", "x")
        self.assertIsNone(result["rows"][0]["search_index_per_second"])

    def test_escaped_rsc_payload_is_preferred_and_normalized(self):
        providers = [{"id": f"provider-{i}-search-api", "aaSearchQualityIndex": .8, "qualityIndexLiftVsModelOnly": .4,
                      "deepsearchqaAvgF1": .81, "browsecompAccuracy": .87,
                      "omniscienceAccuracy": .72, "avgLatencyS": 26.8,
                      "searchApiCostPer1000TasksUsd": 62.3,
                      "candidateModelCostPer1000TasksUsd": 8.04} for i in range(26)]
        payload = '37:["$","div",null,{"data":{"searchProviders":' + json.dumps(providers, separators=(",", ":")) + '}}]'
        html = '<script>self.__next_f.push(' + json.dumps([1, payload]) + ')</script>'
        result = parse_search_api_page(html, "x")
        self.assertEqual(len(result["rows"]), 26)
        self.assertEqual(result["rows"][0]["artificial_analysis_search_index"], 80)
        self.assertEqual(result["rows"][0]["search_cost_usd_per_1000_tasks"], 62.3)
        self.assertAlmostEqual(result["rows"][0]["search_index_per_second"], 80 / 26.8)

    def test_short_rsc_does_not_fall_back_to_short_table(self):
        html = '<script>self.__next_f.push(' + json.dumps([1, '{"searchProviders":[] }']) + ')</script>' + HEAD + '</table>'
        with self.assertRaises(ValueError):
            parse_search_api_page(html, "x")


if __name__ == "__main__":
    unittest.main()
