"""Calibrate intel estimates vs measured coding-agent values by model match.

Usage:
    python calibrate_estimates.py [intel_csv] [coding_csv]

Defaults assume repo layout (run from repo root):
    data/artificial_analysis_intelligence_index_full.csv  (must have est_* columns)
    data/artificial_analysis_coding_agents.csv

Rerun after any fresh scrape (new models, price or benchmark-suite changes)
to confirm the reported factors still hold.
"""
import csv
import re
import sys
from difflib import SequenceMatcher

intel_path = sys.argv[1] if len(sys.argv) > 1 else "data/artificial_analysis_intelligence_index_full.csv"
coding_path = sys.argv[2] if len(sys.argv) > 2 else "data/artificial_analysis_coding_agents.csv"

intel = {r["slug"]: r for r in csv.DictReader(open(intel_path, encoding="utf-8"))}
coding = list(csv.DictReader(open(coding_path, encoding="utf-8")))
print("coding rows:", len(coding))


def norm(s):
    s = s.lower()
    s = re.sub(r"\((.*?)\)", r"-\1", s)  # GPT-5.5 (xhigh) -> gpt-5.5 -xhigh
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


slugs = set(intel)
pairs = []
for r in coding:
    cand = norm(r["model"])
    tried = [cand, norm(r["harness"] + " " + r["model"])]
    match = None
    for t in tried:
        if t in slugs:
            match = t
            break
    if not match:
        best, bs = None, 0.0
        for s in slugs:
            sc = SequenceMatcher(None, cand, s).ratio()
            if sc > bs:
                best, bs = s, sc
        if bs >= 0.8:
            match = best + f" (~{bs:.2f})"
    if match:
        pairs.append((r, match))

print("matched:", len(pairs), "/", len(coding))
cost_ratios, time_ratios, cost_both = [], [], []
for r, m in pairs:
    slug = m.split(" ")[0]
    e = intel[slug]
    try:
        mc, ec = float(r["cost_per_task_usd"]), float(e["est_cost_per_task_usd"])
        mt, et = float(r["avg_execution_time_sec"]), float(e["est_time_per_task_sec"])
    except (ValueError, TypeError, KeyError):
        continue
    if ec > 0 and mc > 0:
        cost_ratios.append(mc / ec)
        cost_both.append((slug, mc, ec))
    if et > 0 and mt > 0:
        time_ratios.append(mt / et)


def stats(xs):
    xs = sorted(xs)
    n = len(xs)
    return n, xs[n // 2], xs[int(n * 0.25)], xs[int(n * 0.75)], min(xs), max(xs)


if cost_ratios:
    n, med, q1, q3, lo, hi = stats(cost_ratios)
    print(f"COST measured/est: n={n} median={med:.1f}x IQR=[{q1:.1f},{q3:.1f}] range=[{lo:.1f},{hi:.1f}]")
    for slug, mc, ec in sorted(cost_both, key=lambda t: t[1] / t[2])[:5]:
        print(f"  low {slug}: measured=${mc:.2f} est=${ec:.3f} ratio={mc/ec:.1f}x")
    for slug, mc, ec in sorted(cost_both, key=lambda t: t[1] / t[2])[-3:]:
        print(f"  high {slug}: measured=${mc:.2f} est=${ec:.3f} ratio={mc/ec:.1f}x")
if time_ratios:
    n, med, q1, q3, lo, hi = stats(time_ratios)
    print(f"TIME measured/est: n={n} median={med:.1f}x IQR=[{q1:.1f},{q3:.1f}] range=[{lo:.1f},{hi:.1f}]")
# rank agreement: do cheapest-by-est land cheapest measured?
if len(cost_both) >= 10:
    by_est = sorted(cost_both, key=lambda t: t[2])
    by_meas = sorted(cost_both, key=lambda t: t[1])
    rk = {s: i for i, (s, _, _) in enumerate(by_meas)}
    n = len(by_est)
    d2 = sum((i - rk[s]) ** 2 for i, (s, _, _) in enumerate(by_est))
    spear = 1 - 6 * d2 / (n * (n * n - 1))
    print(f"cost rank Spearman est-vs-measured: {spear:.2f} (n={n})")
