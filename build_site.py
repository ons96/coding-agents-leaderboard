#!/usr/bin/env python3
"""Build GH Pages site from data/site_data.json into docs/."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "site_data.json"
SITE_DIR = ROOT / "docs"
TEMPLATE = ROOT / "site_template.html"


def build():
    SITE_DIR.mkdir(exist_ok=True)
    payload = json.loads(DATA.read_text())
    lines = [
        "const TABLE_DATA=" + json.dumps(payload["rows"]) + ";",
        "const COLUMNS=" + json.dumps(payload["columns"]) + ";",
        "const LABELS=" + json.dumps(payload["labels"]) + ";",
        "const HIGHLIGHTS=" + json.dumps(payload["highlights"]) + ";",
        "const COL_GROUPS=" + json.dumps(payload["col_groups"]) + ";",
        "const GROUP_ORDER=" + json.dumps(payload["group_order"]) + ";",
        "const GROUP_LABELS=" + json.dumps(payload["group_labels"]) + ";",
        "const META=" + json.dumps(payload["meta"]) + ";",
    ]
    (SITE_DIR / "data.js").write_text("\n".join(lines) + "\n")
    html = TEMPLATE.read_text()
    (SITE_DIR / "index.html").write_text(html)
    print(f"Site built: {SITE_DIR / 'index.html'} ({len(payload['rows'])} rows)")


if __name__ == "__main__":
    build()
