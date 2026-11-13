#!/usr/bin/env python3
"""Build GH Pages site from data/site_data.json into docs/.

Each tab in site_data.json is rendered as its own static page (docs/index.html
for the first tab, docs/<id>.html for the rest) so the single-page design is
preserved per dataset. Pages link to each other via a small nav bar.
"""

import csv
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
INDEX_CSV = ROOT / "data" / "artificial_analysis_intelligence_index_full.csv"

# Task families behind the "is it smart enough for every kind of task" check.
# The Index is an average, so a model can rank well and still be weak at one
# kind of task. The weakest measured family is a useful floor, so it gets its
# own columns; families with no measurement are skipped.
TASK_FAMILIES = (
    ("Terminal", ("terminalBench40", "terminalBench21")),
    ("SciCode", ("scicode",)),
    ("GPQA", ("gpqa",)),
    ("HLE", ("hle",)),
)

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
            ("Score/min", "score_per_minute"),
            ("Time/Task", "avg_execution_time_sec"),
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
            ("Score/min", "score_per_minute"),
            ("Time/Task", "avg_execution_time_sec"),
            ("Score/$", "score_per_cost"),
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
            ("Time/Task", "est_time_per_task_min"),
            ("Weakest family", "weak_task_pct"),
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
        "sort_buttons": [("Score/min", "score_per_minute"),
                         ("Weakest family", "weak_task_pct"),
                         ("Score", "intelligenceIndex")],
        "default_sort": "score_per_minute",
    },
    "search_apis": {
        "title": "Search APIs Leaderboard", "nav_label": "Search APIs", "entity": "Search API products",
        "txt_cols": ["provider"], "filter_id": "provider-filter", "filter_field": "provider",
        "filter_placeholder": "Search providers and products...",
        "footer_url": "https://artificialanalysis.ai/agents/search-api",
        "sort_buttons": [("Index / Time", "search_index_per_second"), ("Search Index", "artificial_analysis_search_index"), ("Time/Task", "time_per_task_seconds"), ("Search Cost", "search_cost_usd_per_1000_tasks")],
        "default_sort": "search_index_per_second",
    },
}


# --------------------------------------------------------------------------- #
# Pareto frontiers
#
# A row is Pareto-optimal when no other row is at least as good on every
# objective and strictly better on one. Objectives are per tab: maximize the
# Index, minimize estimated time per task, and optionally minimize cost per
# task. Rows missing any objective are never on a frontier and cannot dominate
# anything, so gaps in the source data never invent a winner.
#
# Two frontiers are published per leaderboard:
#   pareto       time vs Index         -- fastest row at each quality level
#   pareto_cost  time + cost vs Index  -- keeps a cheaper row alive when it is
#                                         dominated on time alone
# --------------------------------------------------------------------------- #
FRONTIER_SPEC = {
    "agents": {
        "score": "index_score",
        "time": "avg_execution_time_sec",
        "cost": "cost_per_task_usd",
        "complete": ("index_score", "score_per_minute"),
    },
    "models": {
        "score": "intelligence_index",
        "time": "avg_execution_time_sec",
        "cost": "cost_per_task_usd",
        "complete": ("intelligence_index", "score_per_minute"),
    },
    "models_full": {
        "score": "intelligenceIndex",
        "time": "est_time_per_task_min",
        "cost": "est_cost_per_task_usd",
        "complete": ("intelligenceIndex", "score_per_minute"),
    },
    "search_apis": {
        "score": "artificial_analysis_search_index",
        "time": "time_per_task_seconds",
        "cost": ("search_cost_usd_per_1000_tasks", "model_cost_usd_per_1000_tasks"),
        "complete": ("artificial_analysis_search_index", "search_index_per_second"),
    },
}
MAIN_TABS = ("agents", "models", "models_full")
PARETO_LABELS = {"pareto": "Pareto (fast/Index)",
                 "pareto_cost": "Pareto (fast+cheap)"}

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


def _num(row: dict, field):
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _cost_value(row: dict, cost):
    """Cost objective: sum whichever cost fields the tab publishes."""
    fields = cost if isinstance(cost, (tuple, list)) else (cost,)
    values = [v for v in (_num(row, f) for f in fields) if v is not None]
    return sum(values) if values else None


def _objective(row: dict, spec: dict, with_cost: bool):
    """Minimisation tuple (time, cost, -Index); None when not comparable."""
    score = _num(row, spec["score"])
    time = _num(row, spec["time"])
    if score is None or time is None:
        return None
    cost = 0.0
    if with_cost:
        cost = _cost_value(row, spec["cost"])
        if cost is None:
            return None
    return (time, cost, -score)


def _frontier_flags(rows: list, spec: dict, with_cost: bool) -> list:
    """Flag rows on the Pareto frontier of the tab's objectives.

    Only rows complete on every objective are compared. Ordering by the
    minimisation tuple puts any possible dominator first, so a forward pass is
    exact; identical points keep the first in deterministic (slug) order.
    """
    keys = [_objective(r, spec, with_cost) for r in rows]
    order = sorted(
        (i for i, key in enumerate(keys) if key is not None),
        key=lambda i: (keys[i], str(rows[i].get("slug") or rows[i].get("model") or i)),
    )
    flags = [False] * len(rows)
    for pos, i in enumerate(order):
        key = keys[i]
        dominated = False
        for prev in order[:pos]:
            other = keys[prev]
            if other == key or (all(b <= a for a, b in zip(key, other))
                                and any(b < a for a, b in zip(key, other))):
                dominated = True
                break
        flags[i] = not dominated
    return flags


def _place_columns(block: dict, cols: list, spec: dict) -> None:
    """Order frontier columns after the main ratio column and file a group."""
    columns = [c for c in block["columns"] if c not in cols]
    anchor = next((a for a in ("score_per_minute", spec["score"], spec["time"])
                   if a in columns), None)
    if anchor is None:
        columns.extend(cols)
    else:
        at = columns.index(anchor) + 1
        columns[at:at] = cols
    block["columns"] = columns

    groups = block.setdefault("col_groups", {})
    for members in groups.values():
        for col in cols:
            while col in members:
                members.remove(col)
    target = next((g for g, m in groups.items() if "score_per_minute" in m), None)
    if target is None:
        target = next((g for g, m in groups.items() if spec["score"] in m), None)
    if target is None:
        target = next(iter(groups), None)
    if target is not None:
        groups[target].extend(cols)

    block["labels"].update(PARETO_LABELS)
    block["highlights"].update({col: "higher" for col in cols})


def add_frontier_columns(block: dict, spec: dict, with_cost: bool = True) -> dict:
    """Write pareto/pareto_cost flags plus the frontier UI metadata."""
    rows = block["rows"]
    cols = ["pareto"]
    for row, keep in zip(rows, _frontier_flags(rows, spec, with_cost=False)):
        row["pareto"] = keep
    if with_cost and spec.get("cost"):
        cols.append("pareto_cost")
        for row, keep in zip(rows, _frontier_flags(rows, spec, with_cost=True)):
            row["pareto_cost"] = keep
    _place_columns(block, cols, spec)
    block["frontier"] = {
        "score": spec["score"],
        "time": spec["time"],
        "complete": list(spec["complete"]),
        "cost": len(cols) > 1,
    }
    return block


def _pct(value):
    """Benchmark cells are a mix of 0-1 fractions and 0-100 percentages."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number * 100 if number <= 1 else number


def _task_profiles() -> dict:
    """slug -> (weakest percentage, name of that family) from the index CSV."""
    if not INDEX_CSV.exists():
        return {}
    profiles = {}
    with open(INDEX_CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            slug = row.get("slug")
            if not slug:
                continue
            # AA writes 0.0 for "not run" on some evals: 68 of the 72 zeros on
            # terminalBench40 sit next to a healthy terminalBench21, so a
            # literal zero is no measurement rather than a total failure.
            scores = []
            for name, columns in TASK_FAMILIES:
                pct = next((p for column in columns
                            if (p := _pct(row.get(column))) is not None and p > 0), None)
                if pct is not None:
                    scores.append((name, pct))
            if not scores:
                continue
            name, pct = min(scores, key=lambda item: item[1])
            profiles[slug] = (round(pct, 1), name)
    return profiles


def add_task_columns(block: dict) -> None:
    """Attach the weakest family as a sortable number plus the family's name."""
    profiles = _task_profiles()
    if not profiles:
        return
    for row in block["rows"]:
        profile = profiles.get(row.get("slug"))
        if not profile:
            continue
        row["weak_task_pct"], row["weak_task_name"] = profile
    new_cols = [col for col in ("weak_task_pct", "weak_task_name")
                if col not in block["columns"]]
    block["columns"].extend(new_cols)
    block["labels"].setdefault("weak_task_pct", "Weakest family %")
    block["labels"].setdefault("weak_task_name", "Weakest family")
    block["highlights"].setdefault("weak_task_pct", "higher")
    derived = block.setdefault("col_groups", {}).setdefault("derived", [])
    for col in new_cols:
        if col not in derived:
            derived.append(col)


def enrich_main_tabs(payload: dict) -> dict:
    """Add pareto frontiers / has_free_api / free_access to the site tabs.

    Runs at build time on the in-memory payload (site_data.json on disk is
    unchanged). The agents tab has no slug, so models are matched by slugified
    base name against the verified free inventory.
    """
    slug_providers, base_providers = _free_lookup()
    for tab in payload.get("tabs", []):
        tid = tab.get("id")
        spec = FRONTIER_SPEC.get(tid)
        if spec is None:
            continue
        block = tab["data"]
        add_frontier_columns(block, spec, with_cost=bool(spec.get("cost")))
        if tid == "models_full":
            add_task_columns(block)
        if tid not in MAIN_TABS:
            continue
        for row in block["rows"]:
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
        for col in ("has_free_api", "free_access"):
            if col not in block["columns"]:
                block["columns"].append(col)
        block["labels"].setdefault("has_free_api", "Free API")
        block["labels"].setdefault("free_access", "Free base-model API")
        block["highlights"].setdefault("has_free_api", "higher")
        groups = block.setdefault("col_groups", {})
        for members in groups.values():
            for col in ("has_free_api", "free_access"):
                while col in members:
                    members.remove(col)
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
                      "est_time_per_task_min", "outputSpeed",
                      "weak_task_pct", "weak_task_name")})
        rows[-1]["free_access"] = ", ".join(source["provider"] for source in sources)
        for source in sources:
            evidence.append("<li>" + escape(row["model"]) + ": <a href=\"" +
                            escape(source["url"], quote=True) + "\">" +
                            escape(source["provider"] + " / " + source["model_id"]) +
                            "</a> - " + escape(source["note"]) + "</li>")
    rows.sort(key=lambda r: (-r["score_per_minute"], r["slug"]))
    columns = ["model", "creator", "score_per_minute", "intelligenceIndex",
               "weak_task_pct", "weak_task_name", "est_time_per_task_min", "outputSpeed",
               "free_access"]
    block = {
        "rows": rows, "columns": columns,
        "labels": {**index_block["labels"], "free_access": "Free base-model API"},
        "highlights": {"score_per_minute": "higher", "intelligenceIndex": "higher"},
        "col_groups": {"identity": ["model", "creator", "free_access"],
                       "derived": ["score_per_minute", "intelligenceIndex",
                                   "weak_task_pct", "weak_task_name",
                                   "est_time_per_task_min", "outputSpeed"]},
        "group_order": ["identity", "derived"],
        "group_labels": {"identity": "Identity & Access", "derived": "Quality & Speed"},
        "meta": {"row_count": len(rows), "scrape_date": index_block["meta"]["scrape_date"]},
    }
    # Free access means cost is zero for every row, so the cost-aware frontier
    # would be identical to the time/Index one; publish only the latter.
    block = add_frontier_columns(
        block,
        {"score": "intelligenceIndex", "time": "est_time_per_task_min",
         "cost": None, "complete": ("intelligenceIndex", "score_per_minute")},
        with_cost=False,
    )
    notice = ("<aside class=\"notice\"><strong>Base-model access verified; reasoning effort assumed.</strong> "
              "Listed hosted routes have free input and output, but their ability to serve each "
              "leaderboard reasoning-effort variant is not verified. Score/min uses Artificial "
              "Analysis Intelligence Index divided by estimated task time derived from canonical "
              "token counts and output speed; it does not measure free-provider latency. "
              "Rows without an Index or score/min estimate are omitted. Unknown availability "
              "is not paid. Free quotas and availability can change. Provider evidence checked "
              + escape(inventory["checked_date"]) + ". Pareto (fast/Index) keeps only rows "
              "no other eligible row beats on both estimated time and Index."
              "<details><summary>Source routes and effort assumptions</summary><ul>" +
              "".join(evidence) + "</ul></details></aside")
    return block, notice


def _frontier_controls(block: dict) -> str:
    """Row-filter select plus the sufficiency input, shared by every tab."""
    cols = block.get("columns", [])
    options = ['<option value="all">All rows</option>',
               '<option value="complete">Complete data only</option>']
    if "pareto" in cols:
        options.append('<option value="pareto_time">Pareto: fastest per Index</option>')
    if "pareto_cost" in cols:
        options.append('<option value="pareto_cost">Pareto: fastest + cheapest per Index</option>')
    controls = ('<select id="frontier" title="Hide incomplete or dominated rows">'
                + "".join(options) + "</select>")
    if (block.get("frontier") or {}).get("score"):
        controls += ('<input type="number" id="min-score" step="any" '
                     'placeholder="Min Index" title="Hide rows below this Index">')
    return controls


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
    js.append("const FRONTIER=" + json.dumps(block.get("frontier")) + ";")
    js_text = "\n".join(js) + "\n"
    # Content-addressed cache bust: the URL changes only when the data changes,
    # so the Pages CDN / browser cache is refreshed on every real update and
    # reused when the data is unchanged. Prevents stale data.js on mobile.
    js_hash = hashlib.sha1(js_text.encode()).hexdigest()[:8]

    pareto_controls = _frontier_controls(block) if has_pareto else ""
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
