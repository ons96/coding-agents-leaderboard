#!/usr/bin/env python3
"""Daily change gate for Artificial Analysis source pages.

Fetches the AA pages the leaderboard scrapes and hashes ONLY the embedded
dataset payload (RSC flight chunks / encrypted-dataset manifest), ignoring the
HTML shell (build IDs, timestamps, nonces) that changes on every deploy.

Modes:
  check  - compare live hashes vs data/aa_source_hashes.json, emit
           `changed=true|false` (and to $GITHUB_OUTPUT when present).
           Never fails the workflow: on network error prints a warning and
           reports changed=false so the next daily tick retries.
  record - (run AFTER a successful scrape) write current live hashes to
           data/aa_source_hashes.json so the next check has a fresh baseline.

Tracked pages (the 3 scrape inputs):
  1. coding agents leaderboard (feeds agents tab)
  2. intelligence-index base page manifest (feeds models_full tab via full extract)
  3. agentic_target_url from config.yaml (feeds models tab; best-effort, may 404)

Stdlib only. Usage:
  python check_aa_change.py --mode check
  python check_aa_change.py --mode record
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HASH_FILE = ROOT / "data" / "aa_source_hashes.json"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}

CODING_AGENTS_URL = "https://artificialanalysis.ai/agents/coding-agents"
INTEL_INDEX_URL = "https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index"


def _agentic_url() -> str | None:
    try:
        import yaml  # type: ignore
        cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    except Exception:
        # config.yaml is flat `key: "value"` — parse without PyYAML.
        cfg = {}
        for line in (ROOT / "config.yaml").read_text().splitlines():
            m = re.match(r'(\w+):\s*"(.*)"\s*$', line.strip())
            if m:
                cfg[m.group(1)] = m.group(2)
    return cfg.get("agentic_target_url")


def _get(url: str, timeout: int = 45) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=UA)
        return urllib.request.urlopen(req, timeout=timeout).read()
    except Exception as exc:  # network flakiness must not fail the gate
        print(f"WARNING: fetch failed for {url}: {exc}", file=sys.stderr)
        return None


def _payload_hash(body: bytes) -> str:
    """Hash dataset payload, not HTML shell. Falls back to full body."""
    text = body.decode("utf-8", errors="replace")
    # RSC flight data chunks (coding-agents + index pages are Next.js apps)
    pushes = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', text)
    if pushes:
        h = hashlib.sha256()
        for p in pushes:
            h.update(p.encode())
        return "rsc:" + h.hexdigest()
    # Full-extract manifest: {"path":"/data/<hash>.txt","key":"..."}
    m = re.search(r'\{"path":"(/data/[0-9a-f]+\.txt)","key":"[0-9a-f]+"\}', text)
    if m:
        return "manifest:" + hashlib.sha256(m.group(1).encode()).hexdigest()
    return "body:" + hashlib.sha256(body).hexdigest()


def live_hashes() -> dict[str, str | None]:
    urls = [CODING_AGENTS_URL, INTEL_INDEX_URL]
    agentic = _agentic_url()
    if agentic and agentic not in urls:
        urls.append(agentic)
    out: dict[str, str | None] = {}
    for u in urls:
        body = _get(u)
        out[u] = _payload_hash(body) if body is not None else None
    return out


def load_baseline() -> dict:
    if HASH_FILE.exists():
        try:
            return json.loads(HASH_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["check", "record"], required=True)
    args = ap.parse_args()

    live = live_hashes()
    if args.mode == "record":
        HASH_FILE.parent.mkdir(exist_ok=True)
        HASH_FILE.write_text(json.dumps(live, indent=2) + "\n")
        print(f"Recorded {len(live)} source hashes -> {HASH_FILE}")
        return 0

    # check mode
    base = load_baseline()
    if not base:
        changed = True  # first run: no baseline, scrape once
        reason = "no baseline file"
    else:
        diffs = [u for u, h in live.items() if h is not None and base.get(u) != h]
        failed = [u for u, h in live.items() if h is None]
        changed = bool(diffs)
        reason = f"changed={diffs} failed={failed}" if (diffs or failed) else "all match"
    print(f"AA change check: changed={str(changed).lower()} ({reason})")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"changed={str(changed).lower()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
