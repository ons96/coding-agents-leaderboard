# Coding Agents Leaderboard Scraper

Automated scraper for the [Artificial Analysis Coding Agents](https://artificialanalysis.ai/agents/coding-agents) leaderboard.

## How it works

The page is a Next.js app that embeds the full leaderboard dataset in its React
Server Components (RSC) flight payload (`self.__next_f.push` chunks). The scraper
fetches the raw HTML and extracts the `benchmarkRows` array directly — **no browser
or JavaScript rendering required**. This is lighter and faster than a headless
Chromium approach and runs cleanly in CI and on low-memory machines.

## Outputs

- `data/artificial_analysis_coding_agents.csv`
- `data/artificial_analysis_coding_agents.xlsx`
- `data/scrape_meta.json` / `data/site_data.json`
- `docs/` — static GitHub Pages site (one big sortable table)

## Columns

Harness, Model, Creator, Provider, Index Score, DeepSWE, Terminal-Bench v2.1,
SWE-Atlas-QnA, Cost per Task, Avg Execution Time, Token Usage, plus derived
value metrics (Score/$, Score/min, $/Score, Tokens/s).

## Run locally

```bash
pip install -r requirements.txt
python main.py
python build_site.py   # optional: regenerate docs/ site
```

## Schedule

`workflow_dispatch` + weekly `cron: '0 0 * * 0'`. On change it commits via
`github-actions[bot]` and deploys `docs/` to GitHub Pages.
