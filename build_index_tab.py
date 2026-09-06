#!/usr/bin/env python3
"""Merge the 630-model Intelligence Index CSV into data/site_data.json.

Reads data/artificial_analysis_intelligence_index_full.csv (written by
intel_index_full_extract.py), coerces CSV strings to typed scalars
(template sorts lexicographically otherwise), adds perf-per-cost/time
ratio columns, and appends a `models_full` tab to the site payload.

Run after intel_index_full_extract.py, before build_site.py.
"""
import csv
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.formatter import _safe_div, _site_block  # noqa: E402

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "data" / "artificial_analysis_intelligence_index_full.csv"
SITE = ROOT / "data" / "site_data.json"

TAB_ID = "models_full"

COLUMNS = [
    "slug", "model", "creator", "releaseDate", "sizeClass",
    "isReasoning", "isOpenWeights", "intelligenceIndex",
    "price1mInputTokens", "price1mOutputTokens",
    "medianCanonicalAnswerOutputSpeed",
    "est_cost_per_task_usd", "est_time_per_task_sec",
    "idx_per_dollar", "idx_per_min", "idx_per_sec",
]

LABELS = {
    "slug": "Slug",
    "model": "Model",
    "creator": "Creator",
    "releaseDate": "Released",
    "sizeClass": "Size Class",
    "isReasoning": "Reasoning",
    "isOpenWeights": "Open Weights",
    "intelligenceIndex": "Index",
    "price1mInputTokens": "Price/1M In ($)",
    "price1mOutputTokens": "Price/1M Out ($)",
    "medianCanonicalAnswerOutputSpeed": "Median Out Tok/s",
    "est_cost_per_task_usd": "Est Cost/Task ($)",
    "est_time_per_task_sec": "Est Time/Task (s)",
    "idx_per_dollar": "Index/$ (est)",
    "idx_per_min": "Index/min (est)",
    "idx_per_sec": "Index/sec (est)",
}

HIGHLIGHTS = {
    "intelligenceIndex": "higher",
    "medianCanonicalAnswerOutputSpeed": "higher",
    "est_cost_per_task_usd": "lower",
    "est_time_per_task_sec": "lower",
    "price1mInputTokens": "lower",
    "price1mOutputTokens": "lower",
    "idx_per_dollar": "higher",
    "idx_per_min": "higher",
    "idx_per_sec": "higher",
}

GROUPS = {
    "identity": ["slug", "model", "creator", "releaseDate", "sizeClass",
                 "isReasoning", "isOpenWeights"],
    "core": ["intelligenceIndex"],
    "price": ["price1mInputTokens", "price1mOutputTokens",
              "medianCanonicalAnswerOutputSpeed"],
    "est": ["est_cost_per_task_usd", "est_time_per_task_sec"],
    "derived": ["idx_per_dollar", "idx_per_min", "idx_per_sec"],
}
ORDER = ["identity", "core", "price", "est", "derived"]
GROUP_LABELS = {"identity": "Identity", "core": "Benchmark",
                "price": "Pricing & Speed", "est": "Per-Task Estimates",
                "derived": "Perf-per-Cost/Time"}


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def boolean(v):
    if isinstance(v, bool):
        return v
    return {"true": True, "false": False}.get(str(v).strip().lower())


def main() -> None:
    rows_out, scored = [], 0
    with open(CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            idx = num(r.get("intelligenceIndex"))
            cost = num(r.get("est_cost_per_task_usd"))
            secs = num(r.get("est_time_per_task_sec"))
            if idx is not None:
                scored += 1
            rows_out.append({
                "slug": r.get("slug") or None,
                "model": r.get("shortName") or r.get("name"),
                "creator": r.get("creator") or None,
                "releaseDate": r.get("releaseDate") or None,
                "sizeClass": r.get("sizeClass") or None,
                "isReasoning": boolean(r.get("isReasoning")),
                "isOpenWeights": boolean(r.get("isOpenWeights")),
                "intelligenceIndex": idx,
                "price1mInputTokens": num(r.get("price1mInputTokens")),
                "price1mOutputTokens": num(r.get("price1mOutputTokens")),
                "medianCanonicalAnswerOutputSpeed":
                    num(r.get("medianCanonicalAnswerOutputSpeed")),
                "est_cost_per_task_usd": cost,
                "est_time_per_task_sec": secs,
                "idx_per_dollar": _safe_div(idx, cost),
                "idx_per_min": _safe_div(idx, secs / 60 if secs else None),
                "idx_per_sec": _safe_div(idx, secs),
            })
    payload = json.loads(SITE.read_text())
    tabs = [t for t in payload.get("tabs", []) if t.get("id") != TAB_ID]
    df = pd.DataFrame(rows_out, columns=COLUMNS)
    meta = {
        "row_count": len(rows_out),
        "scored": scored,
        "estimates_note": "est_* are per-task estimates (x~30 rule, see README); "
                          "idx_per_* ratios derive from them, not AA-measured values",
    }
    tabs.append({"id": TAB_ID, "label": "Index 630",
                 "data": _site_block(df, COLUMNS, LABELS, HIGHLIGHTS,
                                     GROUPS, ORDER, GROUP_LABELS, meta)})
    payload["tabs"] = tabs
    SITE.write_text(json.dumps(payload, indent=2))
    print(f"models_full tab: {len(rows_out)} rows ({scored} scored)")


if __name__ == "__main__":
    main()
