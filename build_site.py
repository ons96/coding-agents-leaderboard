#!/usr/bin/env python3
"""Build GH Pages site from data/site_data.json into docs/.

Each tab in site_data.json is rendered as its own static page (docs/index.html
for the first tab, docs/<id>.html for the rest) so the single-page design is
preserved per dataset. Pages link to each other via a small nav bar.
"""

import hashlib
from html import escape
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "site_data.json"
SITE_DIR = ROOT / "docs"
TEMPLATE = ROOT / "site_template.html"
FREE_MODELS = ROOT / "data" / "verified_free_models.json"

# Per-tab presentation overrides. Keys are tab ids; values replace template
# tokens. ``txt_cols`` and ``filter_field`` drive the searchable/text columns.
TAB_PRESENTATION = {
    "agents": {
        "title": "Coding Agents Leaderboard",
        "nav_label": "Coding Agents",
        "entity": "agents",
        "txt_cols": ["harness", "model", "creator", "provider"],
        "filter_id": "harness-filter",
        "filter_field": "harness",
        "filter_placeholder": "Search harness, model, creator...",
        "footer_url": "https://artificialanalysis.ai/agents/coding-agents",
        "sort_buttons": [
            ("Score / min", "score_per_minute"),
            ("Cost vs Score", "score_per_cost"),
            ("Token Efficiency", "token_efficiency"),
        ],
        "default_sort": "score_per_minute",
    },
    "models": {
        "title": "Agentic Models Leaderboard",
        "nav_label": "Agentic Models",
        "entity": "models",
        "txt_cols": ["short_name", "model", "creator"],
        "filter_id": "creator-filter",
        "filter_field": "creator",
        "filter_placeholder": "Search model, creator...",
        "footer_url": "https://artificialanalysis.ai/models/capabilities/agentic",
        "sort_buttons": [
            ("Score / min", "score_per_minute"),
            ("Score / $", "score_per_cost"),
            ("Output Tok/s", "tokens_per_sec"),
        ],
        "default_sort": "score_per_minute",
    },
    "models_full": {
        "title": "Intelligence Index — All Models",
        "nav_label": "Intelligence Index (All)",
        "entity": "index models",
        "txt_cols": ["model", "creator", "slug"],
        "filter_id": "creator-filter",
        "filter_field": "creator",
        "filter_placeholder": "Search model, creator, slug...",
        "footer_url": "https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index",
        "sort_buttons": [
            ("Score/min", "score_per_minute"),
            ("Score/$", "score_per_cost"),
            ("Score", "intelligenceIndex"),
        ],
        "default_sort": "score_per_minute",
    },
    "free_models": {
        "title": "Free Hosted Base Models - Score/min",
        "nav_label": "Free Hosted Models",
        "entity": "free hosted model rows",
        "txt_cols": ["model", "creator", "slug", "free_access"],
        "filter_id": "creator-filter",
        "filter_field": "creator",
        "filter_placeholder": "Search models, providers, identifiers...",
        "footer_url": "https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index",
        "sort_buttons": [("Score/min", "score_per_minute"), ("Score", "intelligenceIndex")],
        "default_sort": "score_per_minute",
    },
}


# Score field per main tab for the Pareto keep-rule: rows are ordered by
# score_per_minute desc and a row is kept only when its score exceeds every
# faster row's score (same rule as the free_models tab).
PARETO_SCORE_FIELD = {
    "agents": "index_score",
    "models": "intelligence_index",
    "models_full": "intelligenceIndex",
}
MAIN_TABS = ("agents", "models", "models_full")

# Effort suffixes that may trail a leaderboard slug without changing the base
# model identity (e.g. gemini-3-8-flash-high -> gemini-3-8-flash).
EFFORT_SUFFIXES = ("low", "medium", "high", "xhigh", "max", "minimal", "lite",
                   "reasoning", "non-reasoning")


def _slugify(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def _strip_effort(slug: str) -> str:
    parts = slug.split("-")
    while len(parts) > 1 and parts[-1] in EFFORT_SUFFIXES:
        parts.pop()
    return "-".join(parts)


def _agent_base_slug(model: str) -> str:
    base = (model or "").split("+")[0]
    base = re.sub(r"\(.*?\)", "", base)
    return _slugify(base)


def _free_lookup() -> tuple[dict, dict]:
    """Return (slug -> providers string, base slug -> providers string)."""
    inventory = json.loads(FREE_MODELS.read_text())
    slug_providers = {}
    base_providers: dict[str, set] = {}
    for slug, sources in inventory.get("models", {}).items():
        provs = ", ".join(source["provider"] for source in sources)
        slug_providers[slug] = provs
        for provider in provs.split(", "):
            base_providers.setdefault(_strip_effort(slug), set()).add(provider)
    base_joined = {base: ", ".join(sorted(p)) for base, p in base_providers.items()}
    return slug_providers, base_joined


def _agent_free_match(base_slug: str, slug_providers: dict, base_providers: dict) -> str:
    """Return provider string for an agents-table model, else ""."""
    if not base_slug:
        return ""
    if base_slug in slug_providers:
        return slug_providers[base_slug]
    stripped = _strip_effort(base_slug)
    if stripped in slug_providers:
        return slug_providers[stripped]
    if base_slug in base_providers:
        return base_providers[base_slug]
    return base_providers.get(stripped, "")


def _pareto_flags(rows: list, score_field: str) -> list:
    """Keep-rule shared with free_tab: order by score_per_minute desc, keep a
    row only when its score exceeds every faster row's score."""
    def key(item):
        _i, r = item
        spm = r.get("score_per_minute")
        tie = str(r.get("slug") or r.get("model") or _i)
        return (spm is None, -(spm or 0), tie)

    flags: dict = {}
    best = float("-inf")
    for i, r in sorted(enumerate(rows), key=key):
        spm = r.get("score_per_minute")
        score = r.get(score_field)
        keep = bool(spm) and score is not None and score > best
        flags[i] = keep
        if keep:
            best = score
    return [flags[i] for i in range(len(rows))]


def enrich_main_tabs(payload: dict) -> dict:
    """Add pareto / has_free_api / free_access to agents, models, models_full.

    Runs at build time on the in-memory payload (site_data.json on disk is
    unchanged). The agents tab has no slug, so models are matched by slugified
    base name against the verified free inventory.
    """
    slug_providers, base_providers = _free_lookup()
    for tab in payload.get("tabs", []):
        tid = tab.get("id")
        if tid not in MAIN_TABS:
            continue
        block = tab["data"]
        rows = block["rows"]
        score_field = PARETO_SCORE_FIELD[tid]
        flags = _pareto_flags(rows, score_field)
        for row, pareto in zip(rows, flags):
            row["pareto"] = pareto
            if tid == "agents":
                match = _agent_free_match(_agent_base_slug(row.get("model") or ""),
                                          slug_providers, base_providers)
                row["free_access"] = match
                row["has_free_api"] = bool(match)
            else:
                slug = row.get("slug")
                provs = slug_providers.get(slug, "")
                row["free_access"] = provs
                row["has_free_api"] = slug in slug_providers
        for col in ("pareto", "has_free_api", "free_access"):
            if col not in block["columns"]:
                block["columns"].append(col)
        block["labels"].setdefault("pareto", "Pareto")
        block["labels"].setdefault("has_free_api", "Free API")
        block["labels"].setdefault("free_access", "Free base-model API")
        block["highlights"].setdefault("pareto", "higher")
        block["highlights"].setdefault("has_free_api", "higher")
        groups = block.setdefault("col_groups", {})
        for cols in groups.values():
            for col in ("pareto", "has_free_api", "free_access"):
                if col in cols:
                    cols.remove(col)
        score_group = next((g for g, cols in groups.items()
                            if "score_per_minute" in cols), None)
        if score_group is not None:
            cols = groups[score_group]
            cols.insert(cols.index("score_per_minute") + 1, "pareto")
        elif groups:
            next(iter(groups.values())).append("pareto")
        if "identity" in groups:
            groups["identity"].extend(["has_free_api", "free_access"])
        else:
            groups.setdefault("identity", []).extend(["has_free_api", "free_access"])
    return payload


def free_tab(index_block: dict) -> tuple[dict, str]:
    inventory = json.loads(FREE_MODELS.read_text())
    known = {row["slug"]: row for row in index_block["rows"]}
    rows = []
    evidence = []
    for slug, sources in inventory["models"].items():
        if slug not in known:
            raise ValueError(f"Verified free model missing from index: {slug}")
        row = known[slug]
        if not row.get("score_per_minute") or row.get("intelligenceIndex") is None:
            continue
        rows.append({key: row.get(key) for key in
                     ("slug", "model", "creator", "intelligenceIndex", "score_per_minute",
                      "est_time_per_task_min", "medianCanonicalAnswerOutputSpeed")})
        rows[-1]["free_access"] = ", ".join(source["provider"] for source in sources)
        for source in sources:
            evidence.append("<li>" + escape(row["model"]) + ": <a href=\"" +
                            escape(source["url"], quote=True) + "\">" +
                            escape(source["provider"] + " / " + source["model_id"]) +
                            "</a> - " + escape(source["note"]) + "</li>")
    rows.sort(key=lambda r: (-r["score_per_minute"], r["slug"]))
    best_index = float("-inf")
    for row in rows:
        row["pareto"] = row["intelligenceIndex"] > best_index
        if row["pareto"]:
            best_index = row["intelligenceIndex"]
    columns = ["model", "creator", "score_per_minute", "intelligenceIndex",
               "est_time_per_task_min", "medianCanonicalAnswerOutputSpeed", "free_access"]
    block = {
        "rows": rows, "columns": columns,
        "labels": {**index_block["labels"], "free_access": "Free base-model API"},
        "highlights": {"score_per_minute": "higher", "intelligenceIndex": "higher"},
        "col_groups": {"identity": ["model", "creator", "free_access"],
                       "derived": ["score_per_minute", "intelligenceIndex",
                                   "est_time_per_task_min", "medianCanonicalAnswerOutputSpeed"]},
        "group_order": ["identity", "derived"],
        "group_labels": {"identity": "Identity & Access", "derived": "Quality & Speed"},
        "meta": {"row_count": len(rows), "scrape_date": index_block["meta"]["scrape_date"]},
    }
    notice = ("<aside class=\"notice\"><strong>Base-model access verified; reasoning effort assumed.</strong> "
              "Listed hosted routes have free input and output, but their ability to serve each "
              "leaderboard reasoning-effort variant is not verified. Score/min uses Artificial "
              "Analysis Intelligence Index divided by estimated task time derived from canonical "
              "token counts and output speed; it does not measure free-provider latency. "
              "Rows without an Index or score/min estimate are omitted. Unknown availability "
              "is not paid. Free quotas and availability can change. Provider evidence checked "
              + escape(inventory["checked_date"]) + ". Pareto retains a row only when its "
              "Index exceeds every faster eligible row's Index."
              "<details><summary>Source routes and effort assumptions</summary><ul>" +
              "".join(evidence) + "</ul></details></aside")
    return block, notice


def _render(tab_id: str, block: dict, payload: dict, free_notice: str = "") -> Path:
    pres = TAB_PRESENTATION.get(tab_id, TAB_PRESENTATION["models"])
    html = TEMPLATE.read_text()
    has_pareto = "pareto" in block.get("columns", [])
    has_free = "has_free_api" in block.get("columns", [])

    nav_links = []
    for other in payload["tabs"]:
        if other["id"] == tab_id:
            continue
        label = TAB_PRESENTATION.get(other["id"], {}).get("nav_label") or TAB_PRESENTATION.get(other["id"], {}).get("entity", other["id"])
        href = "index.html" if other["id"] == payload["tabs"][0]["id"] else f"{other['id']}.html"
        nav_links.append(f'<a class="nav-link" href="{href}">{label}</a>')
    nav = '<div class="nav">' + " | ".join(nav_links) + "</div>"

    sort_btns_html = "".join(
        f'<button id="sb-{i}" class="sort-btn">{label}</button>'
        for i, (label, _col) in enumerate(pres["sort_buttons"])
    )
    sort_actions = "[\n" + ",\n".join(
        f'["sb-{i}", "{col}"]' for i, (_label, col) in enumerate(pres["sort_buttons"])
    ) + "\n]"

    js = []
    js.append("const TABLE_DATA=" + json.dumps(block["rows"]) + ";")
    js.append("const COLUMNS=" + json.dumps(block["columns"]) + ";")
    js.append("const LABELS=" + json.dumps(block["labels"]) + ";")
    js.append("const HIGHLIGHTS=" + json.dumps(block["highlights"]) + ";")
    js.append("const COL_GROUPS=" + json.dumps(block["col_groups"]) + ";")
    js.append("const GROUP_ORDER=" + json.dumps(block["group_order"]) + ";")
    js.append("const GROUP_LABELS=" + json.dumps(block["group_labels"]) + ";")
    js.append("const META=" + json.dumps(block["meta"]) + ";")
    js_text = "\n".join(js) + "\n"
    # Content-addressed cache bust: the URL changes only when the data changes,
    # so the Pages CDN / browser cache is refreshed on every real update and
    # reused when the data is unchanged. Prevents stale data.js on mobile.
    js_hash = hashlib.sha1(js_text.encode()).hexdigest()[:8]

    if free_notice:
        pareto_controls = ""
        free_controls = ('<button id="pareto-toggle" aria-pressed="false">'
                         "Pareto only</button>")
    else:
        pareto_controls = ('<button id="pareto-toggle" aria-pressed="false">'
                           "Pareto only</button>") if has_pareto else ""
        free_controls = ('<button id="free-toggle" aria-pressed="false">'
                         "Free API only</button>") if has_free else ""

    replace = {
        "__TITLE__": pres["title"],
        "__ENTITY_LABEL__": json.dumps(pres["entity"]),
        "__NAV__": nav,
        "__TXT_COLS__": json.dumps(pres["txt_cols"]),
        "__FILTER_ID__": pres["filter_id"],
        "__FILTER_FIELD__": json.dumps(pres["filter_field"]),
        "__FILTER_PLACEHOLDER__": pres["filter_placeholder"],
        "__FOOTER_URL__": pres["footer_url"],
        "__SORT_BUTTONS__": sort_btns_html,
        "__SORT_ACTIONS__": sort_actions,
        "__PARETO_CONTROLS__": pareto_controls,
        "__FREE_CONTROLS__": free_controls,
        "__FREE_NOTICE__": free_notice,
        "__IS_FREE_TAB__": "true" if free_notice else "false",
        "__SCRIPT_SRC__": f"{tab_id}.data.js?v={js_hash}",
        "DEFAULT_SORT": json.dumps(pres["default_sort"]),
    }
    for tok, val in replace.items():
        html = html.replace(tok, val)

    first = tab_id == payload["tabs"][0]["id"]
    out_name = "index.html" if first else f"{tab_id}.html"
    out_path = SITE_DIR / out_name
    (SITE_DIR / f"{tab_id}.data.js").write_text(js_text)
    out_path.write_text(html)
    print(f"Built {out_path} ({len(block['rows'])} rows)")
    return out_path


def build():
    SITE_DIR.mkdir(exist_ok=True)
    payload = json.loads(DATA.read_text())
    payload = enrich_main_tabs(payload)
    index = next(tab["data"] for tab in payload["tabs"] if tab["id"] == "models_full")
    free_block, free_notice = free_tab(index)
    payload["tabs"].append({"id": "free_models", "data": free_block})
    built = [_render(tab["id"], tab["data"], payload,
                     free_notice if tab["id"] == "free_models" else "")
             for tab in payload["tabs"]]
    print(f"Site built: {', '.join(str(p) for p in built)}")


if __name__ == "__main__":
    build()