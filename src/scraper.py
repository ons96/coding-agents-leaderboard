"""Fetch + parse Artificial Analysis coding-agents leaderboard.

The page is a Next.js App Router app. The full leaderboard dataset is embedded
in the React Server Components (RSC) flight payload as ``self.__next_f.push([1,"..."])``
chunks. We extract the ``benchmarkRows`` array directly from that payload — no
browser/JS rendering required. This is faster, lighter, and works on any system.
"""

import json
import re
import time
from typing import Optional

import httpx

from .logger import setup_logger

logger = setup_logger()


def fetch_html(url: str, timeout: int = 30, retries: int = 3, backoff: int = 2,
               user_agent: str = "") -> Optional[str]:
    """Fetch raw page HTML with retry + exponential backoff."""
    headers = {
        "User-Agent": user_agent or "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    for attempt in range(retries + 1):
        try:
            resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Fetch attempt {attempt + 1} failed: {exc}")
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    logger.error("All fetch attempts failed")
    return None


def _extract_benchmark_rows(html: str) -> list[dict]:
    """Pull ``benchmarkRows`` objects from RSC flight payload."""
    pushes = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html)
    for block in pushes:
        decoded = block.encode().decode("unicode_escape")
        start = decoded.find('{"benchmarkRows"')
        if start < 0:
            continue
        depth = 0
        end = start
        for i, ch in enumerate(decoded[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        try:
            data = json.loads(decoded[start:end])
        except json.JSONDecodeError:
            continue
        rows = data.get("benchmarkRows")
        if isinstance(rows, list):
            return rows
    return []


def parse_agents(html: str) -> list[dict]:
    """Parse the raw HTML into a flat list of normalized agent records."""
    rows = _extract_benchmark_rows(html)
    if not rows:
        logger.error("No benchmarkRows found in page payload")
        return []

    agents = []
    for row in rows:
        if not isinstance(row, dict):
            # RSC $d reference placeholder — skip
            continue
        evals = {e["datasetIndexName"]: e for e in row.get("evals", [])}
        mean = row.get("mean") or {}

        def reward(name: str) -> Optional[float]:
            e = evals.get(name)
            return (e or {}).get("mean", {}).get("reward")

        agents.append(
            {
                "id": row.get("id"),
                "harness": row.get("agentName"),
                "model": (row.get("display") or {}).get("model"),
                "creator": ((row.get("display") or {}).get("creator") or {}).get("agent"),
                "provider": row.get("provider"),
                "index_score": row.get("indexScore"),
                "deepswe": reward("deep-swe"),
                "terminal_bench_v2_1": reward("terminal-bench-v2.1"),
                "swe_atlas_qna": reward("swe-atlas-qna"),
                "cost_per_task_usd": mean.get("costUsd"),
                "avg_execution_time_sec": mean.get("agentWallTimeSec"),
                "mean_steps": mean.get("steps"),
                "total_tokens": mean.get("totalTokens"),
                "input_tokens": mean.get("inputTokens"),
                "output_tokens": mean.get("outputTokens"),
                "cache_hit_rate": mean.get("cacheHitRate"),
            }
        )

    logger.info(f"Parsed {len(agents)} agent rows from leaderboard")
    return agents
