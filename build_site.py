#!/usr/bin/env python3
"""Build GH Pages site from data/site_data.json into docs/.

Each tab in site_data.json is rendered as its own static page (docs/index.html
for the first tab, docs/<id>.html for the rest) so the single-page design is
preserved per dataset. Pages link to each other via a small nav bar.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "site_data.json"
SITE_DIR = ROOT / "docs"
TEMPLATE = ROOT / "site_template.html"

# Per-tab presentation overrides. Keys are tab ids; values replace template
# tokens. ``txt_cols`` and ``filter_field`` drive the searchable/text columns.
TAB_PRESENTATION = {
    "agents": {
        "title": "Coding Agents Leaderboard",
        "entity": "agents",
        "txt_cols": ["harness", "model", "creator", "provider"],
        "filter_id": "harness-filter",
        "filter_field": "harness",
        "filter_placeholder": "Search harness, model, creator...",
        "footer_url": "https://artificialanalysis.ai/agents/coding-agents",
        "sort_buttons": [
            ("Cost vs Score", "score_per_cost"),
            ("Speed vs Score", "score_per_minute"),
            ("Token Efficiency", "token_efficiency"),
        ],
    },
    "models": {
        "title": "Agentic Models Leaderboard",
        "entity": "models",
        "txt_cols": ["short_name", "model", "creator"],
        "filter_id": "creator-filter",
        "filter_field": "creator",
        "filter_placeholder": "Search model, creator...",
        "footer_url": "https://artificialanalysis.ai/models/capabilities/agentic",
        "sort_buttons": [
            ("Score / $", "score_per_cost"),
            ("Score / min", "score_per_minute"),
            ("Output Tok/s", "tokens_per_sec"),
        ],
    },
}


def _render(tab_id: str, block: dict) -> Path:
    pres = TAB_PRESENTATION.get(tab_id, TAB_PRESENTATION["models"])
    html = TEMPLATE.read_text()

    nav_links = []
    payload = json.loads(DATA.read_text())
    for other in payload["tabs"]:
        if other["id"] == tab_id:
            continue
        label = TAB_PRESENTATION.get(other["id"], {}).get("entity", other["id"])
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
        "__SCRIPT_SRC__": f"{tab_id}.data.js?v={js_hash}",
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
    built = []
    for tab in payload["tabs"]:
        built.append(_render(tab["id"], tab["data"]))
    print(f"Site built: {', '.join(str(p) for p in built)}")


if __name__ == "__main__":
    build()