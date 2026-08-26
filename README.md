# Coding Agents Leaderboard Scraper

Automated scraper for the [Artificial Analysis Coding Agents](https://artificialanalysis.ai/agents/coding-agents) leaderboard.

## How it works

The page is a Next.js app that embeds the full leaderboard dataset in its React
Server Components (RSC) flight payload (`self.__next_f.push` chunks). The scraper
fetches the raw HTML and extracts the `benchmarkRows` array directly — **no browser
or JavaScript rendering required**. This is lighter and faster than a headless
Chromium approach and runs cleanly in CI and on low-memory machines.

## Outputs

Two independent datasets are scraped and exported:

- **Coding Agents** (`artificial_analysis_coding_agents.csv/.xlsx`) — harness+model
  rows from the [Coding Agents](https://artificialanalysis.ai/agents/coding-agents)
  page. One row per harness/model combination, scored per benchmark.
- **Agentic Models** (`artificial_analysis_agentic_models.csv/.xlsx`) — capability
  rows from the [Agentic](https://artificialanalysis.ai/models/capabilities/agentic)
  models page. One row per model with capability + cost/time breakdowns.

Shared outputs:
- `data/scrape_meta.json` / `data/site_data.json` (unified multi-tab payload)
- `docs/` — static GitHub Pages site: `index.html` (agents) + `models.html`
  (models), cross-linked with a nav bar.

## Columns

**Coding Agents** — Harness, Model, Creator, Provider, Index Score, DeepSWE,
Terminal-Bench v2.1, SWE-Atlas-QnA, Cost per Task, Avg Execution Time, Token
Usage, plus derived value metrics (Score/$, Score/min, $/Score, Tokens/s).

**Agentic Models** — Model, Short Name, Creator, Agentic Index, Headline Value,
Reasoning flag, Release Date, Size Class, Open Weights flag, Cost per Task /
input / output / reasoning, Output/Answer/Reasoning tokens, Eval Cost, Avg
Execution Time, plus derived value metrics (Score/$, Score/min, $/Score,
Output Tok/s, Score/1k Output Tokens).

### Model vs Agent leaderboard metrics

The two tabs answer different questions:

| Metric | Coding Agents tab | Agentic Models tab |
|---|---|---|
| Granularity | harness × model combos | per-model capabilities |
| Core score | Index Score (benchmark avg) | Agentic Index (capability) |
| Benchmarks | DeepSWE, Terminal-Bench v2.1, SWE-Atlas-QnA | headline value, reasoning, open weights |
| Cost model | cost per task per combo | input/output/reasoning cost split |
| Token usage | total/input/output tokens | output/answer/reasoning token split |

Both export the same derived value ratios (Score/$, Score/min, $/Score) so the
cost-effectiveness framing is consistent across tabs; only the underlying score
and cost fields differ.

## Run locally

```bash
pip install -r requirements.txt
python main.py
python build_site.py   # optional: regenerate docs/ site
```

## Schedule

`workflow_dispatch` + weekly `cron: '0 0 * * 0'`. On change it commits via
`github-actions[bot]` and deploys `docs/` to GitHub Pages.
