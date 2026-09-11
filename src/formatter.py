"""Derived metrics + CSV/XLSX export for coding-agent leaderboard.

Derived columns let you compare cost / time / score across harnesses and models:

Cost-aware:
- score_per_cost        = index_score / cost_per_task   (higher = better value)
- score_per_1000_tokens = index_score / (total_tokens/1000)
- cost_per_score        = cost_per_task / index_score   (lower = better value)

Time / perf ratio (the index-score-to-execution-time family):
- score_per_minute      = index_score / (avg_exec_time/60)   [Score/min]
- score_per_sec         = index_score / avg_exec_time         [Score/sec, raw ratio]

Throughput:
- token_efficiency      = total_tokens / avg_exec_time
                          NOTE: total_tokens includes cache reads (cache-hit rate is
                          ~97%), so this is not pure generation speed.
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
    # cost-aware derived
    "score_per_cost": "Score/$",
    "score_per_1000_tokens": "Score/1k Tok",
    "score_per_minute": "Score/min",
    "cost_per_score": "$/Score",
    # index/time ratio
    "score_per_sec": "Score/sec",
    # throughput
    "token_efficiency": "Tokens/s (incl. cache)",
}

HIGHLIGHT = {
    "index_score": "higher", "deepswe": "higher", "terminal_bench_v2_1": "higher",
    "swe_atlas_qna": "higher", "cost_per_task_usd": "lower",
    "avg_execution_time_sec": "lower", "total_tokens": "lower",
    "score_per_cost": "higher", "score_per_minute": "higher", "score_per_sec": "higher",
    "cost_per_score": "lower", "token_efficiency": "higher",
}

COL_GROUPS = {
    "identity": ["harness", "model", "creator", "provider"],
    "core": ["index_score", "deepswe", "terminal_bench_v2_1", "swe_atlas_qna"],
    "cost_time": ["cost_per_task_usd", "avg_execution_time_sec", "mean_steps",
                  "total_tokens", "input_tokens", "output_tokens", "cache_hit_rate"],
    "derived": ["score_per_cost", "score_per_1000_tokens", "score_per_minute",
                "score_per_sec", "cost_per_score", "token_efficiency"],
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
    df["score_per_sec"] = df.apply(
        lambda r: _safe_div(r["index_score"], r["avg_execution_time_sec"]), axis=1)
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

    meta_path = output_dir / "scrape_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    agents_site = {
        "columns": ordered_columns(),
        "labels": DERIVED_LABELS,
        "highlights": HIGHLIGHT,
        "col_groups": COL_GROUPS,
        "group_order": GROUP_ORDER,
        "group_labels": GROUP_LABELS,
        "meta": meta,
        "rows": df.where(pd.notnull(df), None).to_dict(orient="records"),
    }
    # Emit a unified (multi-tab) site payload. The agentic-models tab is added
    # later by save_agentic_outputs if that scrape succeeds; if it does not run,
    # the site still renders the agents tab standalone.
    unified = {"tabs": [{"id": "agents", "label": "Coding Agents", "data": agents_site}]}
    (output_dir / "site_data.json").write_text(json.dumps(unified, indent=2))

    logger.info(f"Wrote {csv_path} ({len(df)} rows, {len(df.columns)} cols)")
    logger.info(f"Wrote {xlsx_path}")
    return csv_path, xlsx_path

# --------------------------------------------------------------------------- #
# Agentic *models* (capabilities) dataset — separate from agents leaderboard
# --------------------------------------------------------------------------- #

# These mirror the agent leaderboard so the two tabs read consistently, but
# the models dataset has no harness/provider/eval-reward columns; instead it
# carries per-model capability metrics (intelligence index, cost/time/token
# breakdowns) straight from the capabilities/agentic page.
MODEL_LABELS = {
    "id": "ID",
    "slug": "Slug",
    "model": "Model",
    "short_name": "Short Name",
    "creator": "Creator",
    "creator_slug": "Creator Slug",
    "intelligence_index": "Agentic Index",
    "headline_value": "Headline Value",
    "is_reasoning": "Reasoning",
    "release_date": "Released",
    "size_class": "Size Class",
    "is_open_weights": "Open Weights",
    "cost_per_task_usd": "Cost per Task ($)",
    "cost_input_usd": "Input Cost ($)",
    "cost_output_usd": "Output Cost ($)",
    "cost_reasoning_usd": "Reasoning Cost ($)",
    "output_tokens": "Output Tokens",
    "answer_tokens": "Answer Tokens",
    "reasoning_tokens": "Reasoning Tokens",
    "eval_cost_usd": "Eval Cost ($)",
    "avg_execution_time_sec": "Avg Exec Time (s)",
    # derived value metrics (parallel to agents)
    "score_per_cost": "Score/$",
    "score_per_minute": "Score/min",
    "score_per_sec": "Score/sec",
    "cost_per_score": "$/Score",
    "tokens_per_sec": "Output Tok/s",
    "score_per_1k_output_tokens": "Score/1k Out Tok",
}

MODEL_HIGHLIGHT = {
    "intelligence_index": "higher", "headline_value": "higher",
    "is_reasoning": "higher", "is_open_weights": "higher",
    "cost_per_task_usd": "lower", "cost_input_usd": "lower",
    "cost_output_usd": "lower", "cost_reasoning_usd": "lower",
    "avg_execution_time_sec": "lower", "eval_cost_usd": "lower",
    "score_per_cost": "higher", "score_per_minute": "higher", "score_per_sec": "higher",
    "cost_per_score": "lower", "tokens_per_sec": "higher",
    "score_per_1k_output_tokens": "higher",
}

MODEL_COL_GROUPS = {
    "identity": ["slug", "model", "short_name", "creator", "creator_slug",
                 "release_date", "size_class", "is_reasoning", "is_open_weights"],
    "core": ["intelligence_index", "headline_value"],
    "cost_time": ["cost_per_task_usd", "cost_input_usd", "cost_output_usd",
                  "cost_reasoning_usd", "avg_execution_time_sec", "output_tokens",
                  "answer_tokens", "reasoning_tokens", "eval_cost_usd"],
    "derived": ["score_per_cost", "score_per_minute", "score_per_sec",
                "cost_per_score", "tokens_per_sec", "score_per_1k_output_tokens"],
}
MODEL_GROUP_ORDER = ["identity", "core", "cost_time", "derived"]
MODEL_GROUP_LABELS = {"identity": "Identity", "core": "Capability",
                       "cost_time": "Cost & Time", "derived": "Derived Value"}


def add_model_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["score_per_cost"] = df.apply(
        lambda r: _safe_div(r["intelligence_index"], r["cost_per_task_usd"]), axis=1)
    df["score_per_minute"] = df.apply(
        lambda r: _safe_div(r["intelligence_index"], (r["avg_execution_time_sec"] or 0) / 60), axis=1)
    df["score_per_sec"] = df.apply(
        lambda r: _safe_div(r["intelligence_index"], r["avg_execution_time_sec"]), axis=1)
    df["cost_per_score"] = df.apply(
        lambda r: _safe_div(r["cost_per_task_usd"], r["intelligence_index"]), axis=1)
    df["tokens_per_sec"] = df.apply(
        lambda r: _safe_div(r["output_tokens"], r["avg_execution_time_sec"]), axis=1)
    df["score_per_1k_output_tokens"] = df.apply(
        lambda r: _safe_div(r["intelligence_index"], (r["output_tokens"] or 0) / 1000), axis=1)
    return df


def model_ordered_columns() -> list[str]:
    cols = []
    for g in MODEL_GROUP_ORDER:
        cols.extend(MODEL_COL_GROUPS[g])
    return cols


def _site_block(df, columns, labels, highlights, col_groups, group_order,
                group_labels, meta):
    # astype(object) first: DataFrame.where(cond, None) coerces None back to
    # NaN in float columns, which json.dumps then writes as a literal NaN
    # (invalid strict JSON). Object dtype lets None survive.
    rows = (
        [] if df is None
        else df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")
    )
    return {
        "columns": columns,
        "labels": labels,
        "highlights": highlights,
        "col_groups": col_groups,
        "group_order": group_order,
        "group_labels": group_labels,
        "meta": meta,
        "rows": rows,
    }


def save_agentic_outputs(df: pd.DataFrame, output_dir: Path, csv_name: str,
                         xlsx_name: str, meta: dict, agents_meta: dict) -> tuple[Path, Path]:
    """Export the agentic-models dataset and merge into a unified site payload.

    ``agents_meta`` is the agents-leaderboard scrape meta; we keep both datasets
    in one ``site_data.json`` so the single-page site can render two tabs.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    df = add_model_derived(df)
    cols = model_ordered_columns()
    df = df[cols]

    csv_path = output_dir / csv_name
    df.to_csv(csv_path, index=False)

    xlsx_path = output_dir / xlsx_name
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Agentic Models")

    # agents tab default; overwritten by the tab written by save_outputs
    agents_site = _site_block(
        None, ordered_columns(), DERIVED_LABELS, HIGHLIGHT, COL_GROUPS,
        GROUP_ORDER, GROUP_LABELS, agents_meta)
    existing = output_dir / "site_data.json"
    extra_tabs = []
    if existing.exists():
        prior = json.loads(existing.read_text())
        if "tabs" in prior:
            for t in prior["tabs"]:
                if t.get("id") == "agents":
                    agents_site = t["data"]
                elif t.get("id") != "models":
                    extra_tabs.append(t)
        else:
            # legacy flat payload (older save_outputs)
            agents_site.update({k: prior.get(k, agents_site.get(k)) for k in agents_site})

    models_site = _site_block(
        df, cols, MODEL_LABELS, MODEL_HIGHLIGHT, MODEL_COL_GROUPS,
        MODEL_GROUP_ORDER, MODEL_GROUP_LABELS, meta)

    unified = {
        "tabs": [
            {"id": "agents", "label": "Coding Agents", "data": agents_site},
            {"id": "models", "label": "Agentic Models", "data": models_site},
            *extra_tabs,
        ],
    }
    (output_dir / "site_data.json").write_text(json.dumps(unified, indent=2))

    logger.info(f"Wrote {csv_path} ({len(df)} rows, {len(df.columns)} cols)")
    logger.info(f"Wrote {xlsx_path}")
    return csv_path, xlsx_path
