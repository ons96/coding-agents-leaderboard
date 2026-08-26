"""Entrypoint: scrape -> derive -> export CSV/XLSX + site data."""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from .config import load_config
from .agentic_scraper import parse_models
from .formatter import save_agentic_outputs, save_outputs
from .logger import setup_logger
from .scraper import fetch_html, parse_agents

logger = setup_logger()


def run(config: dict | None = None) -> dict:
    config = config or load_config()
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
            mdf = pd.DataFrame(models)
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
    return meta


if __name__ == "__main__":
    run()
