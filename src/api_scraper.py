"""Search API leaderboard extraction and validation."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup

SEARCH_COLUMNS = ["provider", "artificial_analysis_search_index", "baseline_lift",
                  "deepsearchqa_f1", "browsecomp_accuracy", "omniscience_accuracy",
                  "search_cost_usd_per_1000_tasks", "model_cost_usd_per_1000_tasks",
                  "time_per_task_seconds"]
HEADER_MAP = {
    "provider": "provider", "artificial analysis search index": "artificial_analysis_search_index",
    "baseline lift": "baseline_lift", "deepsearchqa f1": "deepsearchqa_f1",
    "browsecomp accuracy": "browsecomp_accuracy", "omniscience accuracy": "omniscience_accuracy",
    "search $/1k usd / 1k tasks": "search_cost_usd_per_1000_tasks",
    "model $/1k usd / 1k tasks": "model_cost_usd_per_1000_tasks",
    "time per task seconds": "time_per_task_seconds",
}
MIN_PROVIDER_ROWS = 10

RSC_FIELDS = {
    "aaSearchQualityIndex": "artificial_analysis_search_index",
    "qualityIndexLiftVsModelOnly": "baseline_lift", "deepsearchqaAvgF1": "deepsearchqa_f1",
    "browsecompAccuracy": "browsecomp_accuracy", "omniscienceAccuracy": "omniscience_accuracy",
    "searchApiCostPer1000TasksUsd": "search_cost_usd_per_1000_tasks",
    "candidateModelCostPer1000TasksUsd": "model_cost_usd_per_1000_tasks",
    "avgLatencyS": "time_per_task_seconds",
}

def discover_provider_ids(html: str) -> list[str]:
    """Find every Search API product ID serialized anywhere in the page."""
    ids = re.findall(r'\\"id\\":\\"([^"\\]+-search-api)\\"', html)
    return list(dict.fromkeys(ids))


def all_provider_url(base_url: str, provider_ids: list[str] | None = None) -> str:
    # The canonical page embeds the complete provider catalog in its RSC
    # payload. Avoid a fixed query-string allowlist so newly added products are
    # discovered automatically.
    if not provider_ids:
        return base_url
    return base_url + "?search-api-providers=" + quote(",".join(provider_ids), safe="")

def _metric(value):
    text = str(value).strip().replace("\u2014", "-")
    if not text or text in {"-", "null", "N/A"}: return None
    if text.lower() == "baseline": return "baseline"
    match = re.search(r"[-+]?\d[\d,.]*", text.replace("$", ""))
    if not match: return None
    number = float(match.group(0).replace(",", ""))
    return int(number) if number.is_integer() else number

def _rsc_providers(html):
    """Decode all Next flight pushes and find the complete provider catalog."""
    for script in BeautifulSoup(html, "html.parser").find_all("script"):
        text = script.string or script.get_text()
        if "searchProviders" not in text or "__next_f.push" not in text:
            continue
        for match in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)", text, re.S):
            try:
                args = json.loads(match.group(1))
                payload = args[1] if isinstance(args, list) and len(args) > 1 else ""
                marker = '"searchProviders":'
                pos = payload.find(marker)
                if pos >= 0:
                    providers = json.JSONDecoder().raw_decode(payload[pos + len(marker):])[0]
                    if isinstance(providers, list):
                        return providers
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
    return None


def _rsc_rows(html):
    providers = _rsc_providers(html)
    if not isinstance(providers, list):
        return None
    providers = [p for p in providers if isinstance(p, dict) and str(p.get("id", "")).endswith("-search-api")]
    ids = [p["id"] for p in providers]
    if len(ids) < MIN_PROVIDER_ROWS or len(ids) != len(set(ids)):
        return None
    rows = []
    for p in providers:
        if not isinstance(p, dict) or any(p.get(k) is None for k in RSC_FIELDS):
            return None
        rows.append({"provider": p["id"], **{out: p[key] * (100 if key in {"aaSearchQualityIndex", "qualityIndexLiftVsModelOnly", "deepsearchqaAvgF1", "browsecompAccuracy", "omniscienceAccuracy"} else 1) for key, out in RSC_FIELDS.items()}})
    return rows


def parse_search_api_page(html: str, source_url: str, checked_date=None) -> dict:
    rsc = _rsc_rows(html)
    if rsc is not None:
        rows = rsc
    else:
        rows = _parse_semantic_table(html)
    if rows is None:
        raise ValueError("No valid 26-row Search API dataset found")
    providers = [r["provider"] for r in rows]
    if len(providers) < MIN_PROVIDER_ROWS or len(set(providers)) != len(providers):
        raise ValueError(f"Suspicious Search API row count or IDs: {len(providers)}")
    return {"rows": rows, "meta": {"url": source_url, "scrape_date": checked_date or datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows), "provider_row_count": len(providers), "evidence_url": "https://artificialanalysis.ai/methodology/search-api",
        "pricing_checked_date": checked_date or datetime.now(timezone.utc).date().isoformat()}}


def _parse_semantic_table(html: str):
    soup = BeautifulSoup(html, "html.parser")
    heading = next((h for h in soup.find_all(["h1", "h2", "h3", "h4"])
                    if "search api public leaderboard" in h.get_text(" ", strip=True).lower()), None)
    table = heading.find_next("table") if heading else None
    if table is None:
        return None
    headers = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).lower() for c in table.find_all("th")]
    mapped = [HEADER_MAP.get(h) for h in headers]
    if any(c not in mapped for c in SEARCH_COLUMNS):
        return None
    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) != len(mapped): continue
        raw = [c.get_text(" ", strip=True) for c in cells]
        row = {col: (raw[i] if col == "provider" else _metric(raw[i])) for i, col in enumerate(mapped)}
        if row["provider"]: rows.append(row)
    providers = [r["provider"] for r in rows if r["provider"].lower() != "model only"]
    return rows if len(providers) >= MIN_PROVIDER_ROWS and len(providers) == len(set(providers)) else None
