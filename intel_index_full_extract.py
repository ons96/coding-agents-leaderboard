"""Full Artificial Analysis Intelligence Index extractor (no API key needed).

Method (reverse-engineered from AA Next.js chunks):
1. Fetch page HTML, find encrypted-dataset manifest: {"path":"/data/<hash>.txt","key":"<64hex>"}
2. GET the .txt blob (AES-256-GCM, high entropy)
3. IV = SHA256(key_bytes)[:12]  (NOT prepended — derived; see chunk 71794 l.O hook)
4. AES-256-GCM decrypt -> gzip -> JSON {"models":[...630 scored...], "fallbackPriceByModelSlug":{...}}
5. Flatten to CSV (all fields; sparse evals left empty).

Usage: python3 aa-intel-full-extract.py [--page-url URL] [--out csv_path]
Deps: stdlib + `cryptography` (pip install cryptography).
"""
import csv
import gzip
import hashlib
import json
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
DEFAULT_URL = "https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=60).read()


# AA Intelligence Index v4.3.2: (weight, tasks excluding repeats).
# Methodology: artificialanalysis.ai/methodology/intelligence-benchmarking
# Time per Task = weighted avg decode minutes per task; Cost/Task weighted same way.
AA_INDEX_V432 = {
    "briefcase": (0.15, 91),
    "gdpval": (0.10, 220),
    "automationBench": (0.05, 657),
    "terminalBench40": (0.10, 66),  # 66x3 with repeats
    "scicode": (0.10, 288),  # 288x3 with repeats
    "omniscience": (0.15, 6000),
    "gdpPdf": (0.10, 100),  # 100x5 with repeats
    "lcr": (0.05, 100),  # 100x3 with repeats
    "hle": (0.10, 2158),
    "critpt": (0.10, 70),  # 70x5 with repeats
}


def est_metrics(m: dict) -> dict:
    """Per-task cost/time/token estimates from canonical token counts + pricing.

    Weighted over AA_INDEX_V432 of (suite_tokens*price/N)*weight.
    cost = sum_w (input*pIn + (answer+reasoning)*pOut)/1e6/N, split into
    input/output/reasoning parts. time_min = sum_w (answer+reasoning)/speed/N/60.
    tokens = sum_w (answer+reasoning)/N. Rough: ignores prefill speed,
    retries, infra variance, caching. Empty strings when no data.
    """
    out = {"cost": "", "input": "", "output": "", "reasoning": "", "time": "",
           "out_tok": "", "ans_tok": "", "rea_tok": ""}
    try:
        pin = float(m.get("price1mInputTokens") or 0)
        pout = float(m.get("price1mOutputTokens") or 0)
        spd = float(m.get("medianCanonicalAnswerOutputSpeed") or 0)
    except (TypeError, ValueError):
        return out
    if not (pin or pout):
        return out
    tc = m.get("canonicalEvalTokenCounts") or {}
    cost = inp = outp = rea = tsec = otok = atok = rtok = 0.0
    hit = False
    for ev_name, (w, n) in AA_INDEX_V432.items():
        ev = tc.get(ev_name)
        if not isinstance(ev, dict):
            continue
        try:
            i = float(ev.get("input") or 0)
            a = float(ev.get("answer") or 0)
            r = float(ev.get("reasoning") or 0)
        except (TypeError, ValueError):
            continue
        if not (i or a or r):
            continue
        hit = True
        cost += w * (i * pin + (a + r) * pout) / 1e6 / n
        inp += w * i * pin / 1e6 / n
        outp += w * a * pout / 1e6 / n
        rea += w * r * pout / 1e6 / n
        otok += w * (a + r) / n
        atok += w * a / n
        rtok += w * r / n
        if spd > 0 and (a or r):
            tsec += w * (a + r) / spd / n
    if not hit:
        return out
    out["cost"] = round(cost, 6)
    out["input"] = round(inp, 6)
    out["output"] = round(outp, 6)
    out["reasoning"] = round(rea, 6)
    out["out_tok"] = round(otok, 1)
    out["ans_tok"] = round(atok, 1)
    out["rea_tok"] = round(rtok, 1)
    if tsec > 0:
        # ponytail: minutes to match AA Time per Task display (was seconds)
        out["time"] = round(tsec / 60, 2)
    return out


def main() -> None:
    page_url = sys.argv[sys.argv.index("--page-url") + 1] if "--page-url" in sys.argv else DEFAULT_URL
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "/tmp/opencode/aa-intel-630.csv"
    html = get(page_url).decode("utf-8", errors="replace").replace('\\"', '"')
    m = re.search(r'"manifest":\{"path":"([^"]+\.txt)","key":"([0-9a-f]{64})"\}', html)
    if not m:
        sys.exit("ERROR: manifest not found in page HTML (site changed?)")
    path, keyhex = m.group(1), m.group(2)
    print(f"manifest: {path} key={keyhex[:12]}...", file=sys.stderr)
    blob = get("https://artificialanalysis.ai" + path)
    print(f"blob bytes: {len(blob)}", file=sys.stderr)

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = bytes.fromhex(keyhex)
    iv = hashlib.sha256(key).digest()[:12]
    raw = gzip.decompress(AESGCM(key).decrypt(iv, blob, None))
    data = json.loads(raw)
    models = data["models"]
    print(f"models: {len(models)} ({sum(1 for r in models if r.get('intelligenceIndex') is not None)} scored)", file=sys.stderr)

    cols = ["id", "slug", "name", "shortName", "creator", "releaseDate", "sizeClass",
            "isReasoning", "isOpenWeights", "deprecated",
            "intelligenceIndex", "intelligenceIndexIsEstimated"]
    seen, extra = set(cols), []
    for r in models:
        for k in r:
            if k not in seen:
                seen.add(k)
                extra.append(k)
    cols += sorted(extra) + [
        "est_cost_per_task_usd", "est_cost_input_usd", "est_cost_output_usd",
        "est_cost_reasoning_usd", "est_time_per_task_min",
        "est_output_tokens_per_task", "est_answer_tokens_per_task",
        "est_reasoning_tokens_per_task",
    ]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in models:
            est = est_metrics(r)
            row = {k: ("" if v is None else (json.dumps(v) if isinstance(v, (dict, list)) else v))
                   for k, v in r.items()}
            row["est_cost_per_task_usd"] = est["cost"]
            row["est_cost_input_usd"] = est["input"]
            row["est_cost_output_usd"] = est["output"]
            row["est_cost_reasoning_usd"] = est["reasoning"]
            row["est_time_per_task_min"] = est["time"]
            row["est_output_tokens_per_task"] = est["out_tok"]
            row["est_answer_tokens_per_task"] = est["ans_tok"]
            row["est_reasoning_tokens_per_task"] = est["rea_tok"]
            w.writerow(row)
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
