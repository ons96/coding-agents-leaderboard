"""Entrypoint: scrape -> derive -> export CSV/XLSX + site data."""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from .config import load_config
from .agentic_scraper import parse_models
from .formatter import save_agentic_outputs, save_outputs
from .logger import setup_logger
from .scraper import fetch_html, parse_agents
from .api_scraper import all_provider_url, discover_provider_ids, parse_search_api_page, SEARCH_COLUMNS

logger = setup_logger()


def _backfill_models_from_index(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing agentic cost/time/token columns from the intelligence-index
    full extract.

    The old source page (models/capabilities/agentic) is gone (404); the
    fallback page carries no costPerTask/timePerTaskSeconds. We estimate them
    from the encrypted-dataset canonical token counts + published pricing
    (same x~30 methodology as intel_index_full_extract.py, see README).
    """
    csv_path = Path("data/artificial_analysis_intelligence_index_full.csv")
    if not csv_path.exists():
        logger.warning("No intelligence-index CSV; models tab stays estimate-free")
        return df
    idx = pd.read_csv(csv_path, low_memory=False)
    est_cols = {
        "cost_per_task_usd": "est_cost_per_task_usd",
        "cost_input_usd": "est_cost_input_usd",
        "cost_output_usd": "est_cost_output_usd",
        "cost_reasoning_usd": "est_cost_reasoning_usd",
        "avg_execution_time_sec": "est_time_per_task_min",
        "output_tokens": "est_output_tokens_per_task",
        "answer_tokens": "est_answer_tokens_per_task",
        "reasoning_tokens": "est_reasoning_tokens_per_task",
    }
    filled = df.copy()
    matched = 0
    for i, row in filled.iterrows():
        if any(pd.notna(row.get(c)) for c in est_cols):
            continue  # real measured values win over estimates
        src = idx.loc[idx["slug"] == row.get("slug")]
        if src.empty:
            continue
        s = src.iloc[0]
        for col, est_col in est_cols.items():
            v = s.get(est_col)
            if col in filled.columns and pd.notna(v) and v != "":
                f = float(v)
                # ponytail: intel est is minutes-per-task, models tab expects seconds
                filled.at[i, col] = f * 60 if col == "avg_execution_time_sec" else f
        matched += 1
    logger.info(f"Backfilled {matched}/{len(filled)} model rows from intelligence-index estimates")
    return filled


def run(config: dict | None = None) -> dict:
    config = config or load_config()
    site_path = Path(config["output_dir"]) / "site_data.json"
    prior_search_tab = _load_search_api_tab(site_path)
    url = config["target_url"]
    logger.info(f"Fetching {url}")
    html = fetch_html(
        url,
        timeout=config["request_timeout_seconds"],
        retries=config["request_retries"],
        backoff=config["request_backoff_seconds"],
        user_agent=config["user_agent"],
    )
    if not html:
        raise SystemExit("Failed to fetch page")

    agents = parse_agents(html)
    if not agents:
        raise SystemExit("No agent rows parsed from page")

    df = pd.DataFrame(agents)
    scrape_date = datetime.now(timezone.utc).isoformat()
    meta = {
        "url": url,
        "scrape_date": scrape_date,
        "row_count": len(df),
        "column_count": len(df.columns),
    }
    csv_path, xlsx_path = save_outputs(
        df, Path(config["output_dir"]), config["output_csv_name"], config["output_xlsx_name"], meta
    )
    print("\n=== Artificial Analysis Coding Agents — scrape summary ===")
    print(f"Rows: {len(df)}  Columns: {len(df.columns)}")
    print(f"CSV:  {csv_path}")
    print(f"XLSX: {xlsx_path}")
    print(f"Scraped: {scrape_date}")
    print("\nTop 5 by Index Score:")
    top = df.sort_values("index_score", ascending=False).head(5)
    for _, r in top.iterrows():
        print(f"  {r['harness']:16s} | {r['model']:24s} | score={r['index_score']:.4f}"
              f" | $/task={r['cost_per_task_usd']:.2f} | t={r['avg_execution_time_sec']:.0f}s")
    print()
    # Agentic models (capabilities) scrape — best-effort; a failure here must
    # not take down the agents leaderboard. If it succeeds we merge a second
    # tab into the unified site payload.
    agentic_url = config.get("agentic_target_url", "https://artificialanalysis.ai/models/capabilities/agentic")
    logger.info(f"Fetching {agentic_url}")
    a_html = fetch_html(
        agentic_url,
        timeout=config["request_timeout_seconds"],
        retries=config["request_retries"],
        backoff=config["request_backoff_seconds"],
        user_agent=config["user_agent"],
    )
    if not a_html:
        logger.warning("Agentic models page fetch failed; site keeps agents tab only")
    else:
        models = parse_models(a_html)
        if not models:
            logger.warning("No model rows parsed from agentic page; site keeps agents tab only")
        else:
            mdf = _backfill_models_from_index(pd.DataFrame(models))
            a_meta = {
                "url": agentic_url,
                "scrape_date": scrape_date,
                "row_count": len(mdf),
                "column_count": len(mdf.columns),
            }
            save_agentic_outputs(
                mdf, Path(config["output_dir"]),
                config["agentic_output_csv_name"], config["agentic_output_xlsx_name"],
                a_meta, meta,
            )
            print("\n=== Artificial Analysis Agentic Models — scrape summary ===")
            print(f"Rows: {len(mdf)}  Columns: {len(mdf.columns)}")
            print("\nTop 5 by Agentic Index:")
            mtop = mdf.sort_values("intelligence_index", ascending=False).head(5)
            for _, r in mtop.iterrows():
                c = r.get('cost_per_task_usd')
                t = r.get('avg_execution_time_sec')
                idx = r.get('intelligence_index')
                name = str(r.get('short_name'))
                cstr = f" | $/task={c:.2f}" if isinstance(c, (int, float)) else ""
                tstr = f" | t={t:.0f}s" if isinstance(t, (int, float)) else ""
                print(f"  {name:42s} | idx={idx:.2f}{cstr}{tstr}")
    # Search APIs tab: best effort, with strict validation and last-known-good
    # preservation.  This runs after the normal formatter has written the
    # unified payload, so a transient source failure cannot blank other tabs.
    search_url = all_provider_url(config["search_api_target_url"]) if config.get("search_api_target_url") else None
    if search_url:
        logger.info(f"Fetching {search_url}")
        s_html = fetch_html(config["search_api_target_url"], timeout=config["request_timeout_seconds"],
                            retries=config["request_retries"], backoff=config["request_backoff_seconds"],
                            user_agent=config["user_agent"])
        if s_html:
            try:
                provider_ids = discover_provider_ids(s_html)
                if len(provider_ids) > 13:
                    search_url = all_provider_url(config["search_api_target_url"], provider_ids)
                    s_html = fetch_html(search_url, timeout=config["request_timeout_seconds"],
                                        retries=config["request_retries"], backoff=config["request_backoff_seconds"],
                                        user_agent=config["user_agent"])
                if not s_html:
                    raise ValueError("expanded Search API provider fetch failed")
                parsed = parse_search_api_page(s_html, search_url)
                _merge_search_api_tab(Path(config["output_dir"]) / "site_data.json", parsed)
                logger.info("Search APIs tab updated with %d rows", len(parsed["rows"]))
            except (ValueError, TypeError) as exc:
                logger.warning("Search APIs scrape rejected; retaining last-known-good data: %s", exc)
        else:
            logger.warning("Search APIs fetch failed; retaining last-known-good data")
    if prior_search_tab and not _load_search_api_tab(site_path):
        _restore_search_api_tab(site_path, prior_search_tab)
    # Full intelligence index (630 models) extraction
    # This runs the separate intelligence extractor and tab builder
    # to ensure the site includes the full intelligence index dataset.
    import subprocess
    import sys

    extract_script = Path(__file__).parent.parent / "intel_index_full_extract.py"
    tab_builder = Path(__file__).parent.parent / "build_index_tab.py"
    out_csv = Path(config["output_dir"]) / "artificial_analysis_intelligence_index_full.csv"

    if extract_script.exists() and tab_builder.exists():
        logger.info("Running full intelligence index extractor...")
        subprocess.run([sys.executable, str(extract_script), "--out", str(out_csv)], check=True)
        logger.info("Building models_full tab...")
        subprocess.run([sys.executable, str(tab_builder)], check=True)
    else:
        logger.warning("Full intelligence index scripts not found; skipping full index tab")
    return meta


def _merge_search_api_tab(path: Path, parsed: dict) -> None:
    """Validate and merge a typed Search APIs block into site_data.json."""
    import json
    payload = json.loads(path.read_text())
    rows = parsed["rows"]
    labels = {"provider": "Provider", "artificial_analysis_search_index": "Search Index",
              "baseline_lift": "Baseline Lift", "deepsearchqa_f1": "DeepSearchQA F1",
              "browsecomp_accuracy": "BrowseComp Accuracy", "omniscience_accuracy": "Omniscience Accuracy",
              "search_cost_usd_per_1000_tasks": "Search $/1k Tasks", "model_cost_usd_per_1000_tasks": "Model $/1k Tasks",
              "time_per_task_seconds": "Time/Task (s)", "search_index_per_second": "Search Index / Time (per s)"}
    block = {"columns": SEARCH_COLUMNS, "labels": labels,
             "highlights": {"artificial_analysis_search_index": "higher", "baseline_lift": "higher",
                            "deepsearchqa_f1": "higher", "browsecomp_accuracy": "higher", "omniscience_accuracy": "higher",
                            "search_cost_usd_per_1000_tasks": "lower", "model_cost_usd_per_1000_tasks": "lower",
                            "time_per_task_seconds": "lower", "search_index_per_second": "higher"},
             "col_groups": {"identity": ["provider"], "quality": SEARCH_COLUMNS[1:6], "cost_speed": SEARCH_COLUMNS[6:]},
             "group_order": ["identity", "quality", "cost_speed"],
             "group_labels": {"identity": "Provider", "quality": "Quality", "cost_speed": "Cost & Speed"},
             "meta": {**parsed["meta"], "pricing_evidence": "data/search_api_pricing.json"}, "rows": rows}
    tabs = [t for t in payload.get("tabs", []) if t.get("id") != "search_apis"]
    tabs.append({"id": "search_apis", "label": "Search APIs", "data": block})
    path.write_text(json.dumps({"tabs": tabs}, indent=2))


def _load_search_api_tab(path: Path):
    import json
    if not path.exists():
        return None
    try:
        return next((t for t in json.loads(path.read_text()).get("tabs", [])
                     if t.get("id") == "search_apis"), None)
    except (OSError, ValueError, TypeError):
        return None


def _restore_search_api_tab(path: Path, tab: dict) -> None:
    import json
    payload = json.loads(path.read_text())
    tabs = [t for t in payload.get("tabs", []) if t.get("id") != "search_apis"]
    tabs.append(tab)
    path.write_text(json.dumps({"tabs": tabs}, indent=2))


if __name__ == "__main__":
    run()
