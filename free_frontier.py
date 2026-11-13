#!/usr/bin/env python3
"""Pareto frontier restricted to models this machine can actually call.

The site's free filter uses data/verified_free_models.json, a hand-reviewed
list that goes stale as providers add and drop routes. This script instead
reads an opencode config (provider -> models) and intersects it with the
scraped Intelligence Index rows, so every frontier row is a route you hold.

Usage:
  python free_frontier.py
  python free_frontier.py --config ~/CodingProjects/opencode.json
  python free_frontier.py --providers logfare,freetheai,tokeness --min-index 30
  python free_frontier.py --csv my_frontier.csv

Matching is exact on the normalized slug (vendor prefix, ":free" and
punctuation removed). Ids that omit a size or reasoning-effort token fall back
to a looser key and are marked with "~". A leaderboard row without an Index or
a time estimate cannot be ranked, so unmatched or unscored models simply do
not appear; the count is printed at the end.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX_CSV = ROOT / "data" / "artificial_analysis_intelligence_index_full.csv"
DEFAULT_CONFIG = Path.home() / "CodingProjects" / "opencode.json"

EFFORT = ("low", "medium", "high", "xhigh", "max", "minimal", "lite",
          "reasoning", "thinking", "non-reasoning")
NOISE = ("preview", "instruct", "it", "chat", "latest", "standard", "exp",
         "beta", "free", "default")
VENDOR = ("google", "openai", "anthropic", "meta-llama", "meta", "deepseek-ai",
          "deepseek", "moonshotai", "moonshot", "z-ai", "zai", "nvidia",
          "mistralai", "mistral", "cohere", "sakana", "bytedance", "meituan",
          "thinkingmachines", "liquid", "x-ai", "xai", "amazon", "microsoft",
          "ai21", "baidu", "minimax", "01-ai", "allenai", "ibm", "tencent",
          "stepfun", "baichuan", "internlm", "thudm", "qwen")
SIZE_TOKEN = re.compile(r"^(?:\d+b|b\d+|a\d+b|\d+x\d+b)$")

# Weakest of these is the answer to "is it smart enough for every task?" The
# terminal family falls back to the 21-task set when the 40-task set has no run.
TASK_FAMILIES = (("T", ("terminalBench40", "terminalBench21")),
                 ("C", ("scicode",)), ("G", ("gpqa",)), ("H", ("hle",)))


def norm_slug(raw: str) -> str:
    """Vendor prefix, ':free', punctuation and case normalized; size and
    reasoning effort kept, because they identify a leaderboard row."""
    s = (raw or "").strip().lower()
    s = s.split("/")[-1]              # provider/model -> model
    s = re.sub(r":.*$", "", s)        # :free, :nitro
    s = re.sub(r"\(.*?\)", "", s)
    s = s.replace(".", "-").replace("_", "-")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    for prefix in sorted(VENDOR, key=len, reverse=True):
        if s.startswith(prefix + "-") and len(s) > len(prefix) + 1:
            return s[len(prefix) + 1:]
    return s


def fuzzy_slug(raw: str) -> str:
    """Looser key for ids that omit a size or effort token; marked "~" in output."""
    parts = norm_slug(raw).split("-")
    while len(parts) > 1 and parts[-1] in EFFORT:
        parts.pop()
    while len(parts) > 2 and (parts[-1] in NOISE or SIZE_TOKEN.match(parts[-1])):
        parts.pop()
    return "-".join(parts)


def load_config(path: Path) -> dict:
    data = json.loads(path.read_text())
    providers = data.get("provider")
    if not isinstance(providers, dict):
        raise SystemExit(f"{path}: no top-level 'provider' object")
    return {name: list((pv or {}).get("models") or {}) for name, pv in providers.items()}


def load_leaderboard(path: Path) -> tuple[dict, dict]:
    """Return (normalized slug -> scored rows, fuzzy slug -> normalized slugs)."""
    by_key: dict[str, list] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not row.get("slug"):
                continue
            idx = num(row.get("intelligenceIndex"))
            mins = num(row.get("est_time_per_task_min"))
            if idx is None or mins is None:
                continue
            key = norm_slug(row["slug"])
            weak, profile = task_profile(row)
            by_key.setdefault(key, []).append({
                "weak": weak,
                "profile": profile,
                "slug": row["slug"],
                "key": key,
                "model": row.get("shortName") or row.get("name"),
                "index": idx,
                "minutes": mins,
                "cost": num(row.get("est_cost_per_task_usd")),
            })
    by_fuzzy: dict[str, list] = {}
    for key in by_key:
        by_fuzzy.setdefault(fuzzy_slug(key), []).append(key)
    return by_key, by_fuzzy


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value):
    """Benchmark cells are a mix of 0-1 fractions and 0-100 percentages."""
    number = num(value)
    if number is None:
        return None
    return number * 100 if number <= 1 else number


def task_profile(row: dict) -> tuple[str, str]:
    """(weakest 'T12.0', full 'T12 C43 G82 H17') from the benchmark columns."""
    # AA writes 0.0 for "not run" on some evals: 68 of the 72 zeros on
    # terminalBench40 sit next to a healthy terminalBench21. A literal zero is
    # therefore treated as no measurement, never as a total failure.
    scores = []
    for letter, columns in TASK_FAMILIES:
        pct = next((p for column in columns
                    if (p := _pct(row.get(column))) is not None and p > 0), None)
        if pct is not None:
            scores.append((letter, pct))
    if not scores:
        return "-", "-"
    letter, pct = min(scores, key=lambda item: item[1])
    return f"{letter}{pct:.1f}", " ".join(f"{l}{p:.0f}" for l, p in scores)


def frontier(rows: list, with_cost: bool) -> set:
    """Slugs of non-dominated rows; objectives are min time/cost, max Index."""
    def key(r):
        return (r["minutes"], r["cost"] if with_cost else 0.0, -r["index"])

    pts = [r for r in rows if not (with_cost and r["cost"] is None)]
    order = sorted(pts, key=lambda r: (key(r), r["slug"]))
    keep, seen = set(), set()
    for pos, row in enumerate(order):
        k = key(row)
        if k in seen:
            continue
        seen.add(k)
        dominated = any(
            all(b <= a for a, b in zip(k, key(other)))
            and any(b < a for a, b in zip(k, key(other)))
            for other in order[:pos]
        )
        if not dominated:
            keep.add(row["slug"])
    return keep


def match(config: dict, by_key: dict, by_fuzzy: dict) -> tuple[dict, set]:
    """Return slug -> routes, plus config ids that matched nothing.

    An exact slug match wins outright, so a model whose name merely ends in an
    effort word ("qwen3.8-max") is not confused with an effort variant of a
    differently sized model.
    """
    routes: dict[str, set] = {}
    unmatched = set()
    for provider, model_ids in config.items():
        for model_id in model_ids:
            label = f"{'openrouter' if provider == 'openrouter2' else provider}/{model_id}"
            key = norm_slug(model_id)
            if key in by_key:
                for row in by_key[key]:
                    routes.setdefault(row["slug"], set()).add(label)
                continue
            loose = by_fuzzy.get(fuzzy_slug(model_id))
            if loose:
                for match_key in loose:
                    for row in by_key[match_key]:
                        routes.setdefault(row["slug"], set()).add(label + "~")
                continue
            unmatched.add(model_id)
    return routes, unmatched


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--index-csv", type=Path, default=INDEX_CSV)
    ap.add_argument("--providers", default="", help="comma-separated provider names to keep")
    ap.add_argument("--min-index", type=float, default=None)
    ap.add_argument("--csv", type=Path, default=None, help="write the frontier here")
    args = ap.parse_args(argv)

    if not args.config.exists():
        raise SystemExit(f"config not found: {args.config}")
    if not args.index_csv.exists():
        raise SystemExit(f"index CSV not found: {args.index_csv} (run intel_index_full_extract.py)")

    config = load_config(args.config)
    wanted = {p.strip() for p in args.providers.split(",") if p.strip()}
    if wanted:
        config = {k: v for k, v in config.items() if k in wanted}
        if not config:
            raise SystemExit(f"no matching providers in config: {sorted(wanted)}")

    by_key, by_fuzzy = load_leaderboard(args.index_csv)
    routes, unmatched = match(config, by_key, by_fuzzy)

    rows = [r for base in by_key.values() for r in base if r["slug"] in routes]
    if args.min_index is not None:
        rows = [r for r in rows if r["index"] >= args.min_index]
    rows.sort(key=lambda r: r["minutes"])

    fast = frontier(rows, with_cost=False)
    cheap = frontier(rows, with_cost=True)

    matched_bases = {r["key"] for r in rows}
    print(f"config: {args.config}")
    print(f"providers: {len(config)}  configured model ids: {sum(len(v) for v in config.values())}")
    print(f"leaderboard rows reachable from config (Index + time): {len(rows)}"
          f"  base models: {len(matched_bases)}")
    print()
    print("worst = weakest task-family % (T terminal, C SciCode, G GPQA, H HLE)")
    print()
    header = (f"{'min':>7} {'Index':>6} {'worst':>6} {'$/task':>9}  "
              f"{'fast':>4} {'cheap':>5}  model | routes")
    print(header)
    print("-" * len(header))
    for r in rows:
        cost = "-" if r["cost"] is None else f"{r['cost']:.3f}"
        print(f"{r['minutes']:7.2f} {r['index']:6.1f} {r['weak']:>6} {cost:>9}  "
              f"{'yes' if r['slug'] in fast else '':>4} "
              f"{'yes' if r['slug'] in cheap else '':>5}  "
              f"{r['model'][:40]} | {', '.join(sorted(routes[r['slug']]))[:70]}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["model", "slug", "index", "weakest_task", "task_profile",
                             "est_time_per_task_min", "est_cost_per_task_usd",
                             "pareto_time", "pareto_cost", "routes"])
            for r in rows:
                writer.writerow([r["model"], r["slug"], r["index"], r["weak"],
                                 r["profile"], r["minutes"], r["cost"],
                                 r["slug"] in fast, r["slug"] in cheap,
                                 "; ".join(sorted(routes[r["slug"]]))])
        print(f"\nwrote {args.csv} ({len(rows)} rows)")

    print(f"\nunmatched config model ids (no AA row): {len(unmatched)}"
          f" of {sum(len(v) for v in config.values())}")
    print("A model needs an AA Index and a time estimate to be ranked; "
          "routes absent from the leaderboard cannot be compared.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
