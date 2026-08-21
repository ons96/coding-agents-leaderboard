"""Derived metrics + CSV/XLSX export for coding-agent leaderboard.

Derived columns let you compare cost / time / score across harnesses and models:

- score_per_cost        = index_score / cost_per_task   (higher = better value)
- score_per_1000_tokens = index_score / (total_tokens/1000)
- score_per_minute      = index_score / (avg_exec_time/60)
- cost_per_score        = cost_per_task / index_score   (lower = better value)
- token_efficiency      = total_tokens / avg_exec_time  (throughput)
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .logger import setup_logger

logger = setup_logger()

DERIVED_LABELS = {
    "id": "ID",
    "harness": "Harness",
    "model": "Model",
    "creator": "Creator",
    "provider": "Provider",
    "index_score": "Index Score",
    "deepswe": "DeepSWE",
    "terminal_bench_v2_1": "Terminal-Bench v2.1",
    "swe_atlas_qna": "SWE-Atlas-QnA",
    "cost_per_task_usd": "Cost per Task ($)",
    "avg_execution_time_sec": "Avg Exec Time (s)",
    "mean_steps": "Mean Steps",
    "total_tokens": "Total Tokens",
    "input_tokens": "Input Tokens",
    "output_tokens": "Output Tokens",
    "cache_hit_rate": "Cache Hit Rate",
    # derived
    "score_per_cost": "Score/$",
    "score_per_1000_tokens": "Score/1k Tok",
    "score_per_minute": "Score/min",
    "cost_per_score": "$/Score",
    "token_efficiency": "Tokens/s",
}

HIGHLIGHT = {
    "index_score": "higher", "deepswe": "higher", "terminal_bench_v2_1": "higher",
    "swe_atlas_qna": "higher", "cost_per_task_usd": "lower",
    "avg_execution_time_sec": "lower", "total_tokens": "lower",
    "score_per_cost": "higher", "score_per_minute": "higher",
    "cost_per_score": "lower", "token_efficiency": "higher",
}

COL_GROUPS = {
    "identity": ["harness", "model", "creator", "provider"],
    "core": ["index_score", "deepswe", "terminal_bench_v2_1", "swe_atlas_qna"],
    "cost_time": ["cost_per_task_usd", "avg_execution_time_sec", "mean_steps",
                  "total_tokens", "input_tokens", "output_tokens", "cache_hit_rate"],
    "derived": ["score_per_cost", "score_per_1000_tokens", "score_per_minute",
                "cost_per_score", "token_efficiency"],
}
GROUP_ORDER = ["identity", "core", "cost_time", "derived"]
GROUP_LABELS = {"identity": "Identity", "core": "Benchmarks",
                "cost_time": "Cost & Time", "derived": "Derived Value"}


def _safe_div(a, b):
    try:
        if a is None or b in (None, 0):
            return None
        return a / b
    except (TypeError, ZeroDivisionError):
        return None


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["score_per_cost"] = df.apply(
        lambda r: _safe_div(r["index_score"], r["cost_per_task_usd"]), axis=1)
    df["score_per_1000_tokens"] = df.apply(
        lambda r: _safe_div(r["index_score"], (r["total_tokens"] or 0) / 1000), axis=1)
    df["score_per_minute"] = df.apply(
        lambda r: _safe_div(r["index_score"], (r["avg_execution_time_sec"] or 0) / 60), axis=1)
    df["cost_per_score"] = df.apply(
        lambda r: _safe_div(r["cost_per_task_usd"], r["index_score"]), axis=1)
    df["token_efficiency"] = df.apply(
        lambda r: _safe_div(r["total_tokens"], r["avg_execution_time_sec"]), axis=1)
    return df


def ordered_columns() -> list[str]:
    cols = []
    for g in GROUP_ORDER:
        cols.extend(COL_GROUPS[g])
    return cols


def save_outputs(df: pd.DataFrame, output_dir: Path, csv_name: str, xlsx_name: str,
                 meta: dict) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    df = add_derived(df)
    df = df[ordered_columns()]

    csv_path = output_dir / csv_name
    df.to_csv(csv_path, index=False)

    xlsx_path = output_dir / xlsx_name
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Coding Agents")

    # Machine-readable metadata + chart-ready JSON for the site
    meta_path = output_dir / "scrape_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    site_data = {
        "columns": ordered_columns(),
        "labels": DERIVED_LABELS,
        "highlights": HIGHLIGHT,
        "col_groups": COL_GROUPS,
        "group_order": GROUP_ORDER,
        "group_labels": GROUP_LABELS,
        "meta": meta,
        "rows": df.where(pd.notnull(df), None).to_dict(orient="records"),
    }
    (output_dir / "site_data.json").write_text(json.dumps(site_data, indent=2))

    logger.info(f"Wrote {csv_path} ({len(df)} rows, {len(df.columns)} cols)")
    logger.info(f"Wrote {xlsx_path}")
    return csv_path, xlsx_path
