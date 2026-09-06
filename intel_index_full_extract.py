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
    cols += sorted(extra)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in models:
            w.writerow({k: ("" if v is None else (json.dumps(v) if isinstance(v, (dict, list)) else v))
                        for k, v in r.items()})
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
