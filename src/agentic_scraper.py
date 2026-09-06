"""Fetch + parse Artificial Analysis agentic *models* capability page.

The models/capabilities/agentic page (unlike the agents leaderboard) embeds a
top-level ``initialModels`` array in the RSC flight payload. Each entry is a
single model (not a harness+model combination) with capability metrics:
intelligence index, cost-per-task, time-per-task, output tokens, etc.

We reuse ``fetch_html`` from the agents scraper so retry/backoff logic stays in
one place.
"""

import json
import re
from typing import Optional

from .logger import setup_logger
from .scraper import fetch_html

logger = setup_logger()


def _extract_initial_models(html: str) -> list[dict]:
    """Pull the ``initialModels`` array from the RSC flight payload.

    This function specifically handles the key used in:
    https://artificialanalysis.ai/models/capabilities/agentic
    AND
    https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index
    """
    pushes = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html)
    for block in pushes:
        decoded = block.encode().decode("unicode_escape")
        # Check for 'initialModels' or 'models' as the primary data array key
        for key in ["initialModels", "models"]:
            for m in re.finditer(f'"{key}":\\s*\\[', decoded):
                start = m.end() - 1
                depth = 0
                end = start
                for i, ch in enumerate(decoded[start:], start):
                    if ch == "[":
                        depth += 1
                    elif ch == "]":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                try:
                    arr = json.loads(decoded[start:end])
                except json.JSONDecodeError:
                    continue
                if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                    # The intelligence index models might not have 'costPerTask'
                    # but they will have 'id' and 'slug'.
                    # We'll accept any array of dicts with 'id' and 'slug'.
                    if "id" in arr[0] and "slug" in arr[0]:
                        return arr
    return []


def parse_models(html: str) -> list[dict]:
    """Parse the raw HTML into a flat list of normalized model records.

    Handles both 'capabilities' pages (with cost/token metrics)
    and 'intelligence-index' pages (which may have less detailed metrics).
    """
    raw = _extract_initial_models(html)
    if not raw:
        logger.error("No model rows found in page payload")
        return []

    models = []
    for row in raw:
        # Intelligence index might not have these nested objects.
        # We use .get() with empty dict fallback.
        cost = row.get("costPerTask") or {}
        tokens = row.get("outputTokensPerTask") or {}

        # Intelligence index might use 'intelligenceIndex' directly or in a different field.
        # We attempt to normalize.
        models.append(
            {
                "id": row.get("id"),
                "slug": row.get("slug"),
                "model": row.get("name"),
                "short_name": row.get("shortName"),
                "creator": (row.get("creator") or {}).get("name"),
                "creator_slug": (row.get("creator") or {}).get("slug"),
                "intelligence_index": row.get("intelligenceIndex"),
                "headline_value": row.get("headlineValue"),
                "is_reasoning": row.get("isReasoning"),
                "release_date": row.get("releaseDate"),
                "size_class": row.get("sizeClass"),
                "is_open_weights": row.get("isOpenWeights"),
                "cost_per_task_usd": cost.get("total"),
                "cost_input_usd": cost.get("input"),
                "cost_output_usd": cost.get("output"),
                "cost_reasoning_usd": cost.get("reasoning"),
                "output_tokens": tokens.get("output"),
                "answer_tokens": tokens.get("answer"),
                "reasoning_tokens": tokens.get("reasoning"),
                "eval_cost_usd": (row.get("evalCost") or {}).get("total"),
                "avg_execution_time_sec": row.get("timePerTaskSeconds"),
            }
        )

    logger.info(f"Parsed {len(models)} model rows from page payload")
    return models


