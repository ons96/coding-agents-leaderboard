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
  (models), `search_apis.html` (Search API benchmark), cross-linked with a nav bar.

### Search APIs

The Search APIs tab extracts the 26 provider records from the embedded Next.js
RSC payload, with the semantic public leaderboard table as a validated fallback.
It rejects missing schemas, duplicate providers, or incomplete provider sets
before writing. A failed fetch retains the committed
last-known-good tab. Search/API costs are measured separately from model costs;
access labels and official pricing evidence are recorded in
`data/search_api_pricing.json`, with the checked date. Labels such as recurring
free quota, trial credits, and paid only are observations as of that date, not
claims that access is permanent.

The Search APIs table includes Search Index / Time (per s), calculated as the
Artificial Analysis Search Index divided by Time/Task in seconds. It is the
default descending sort so the most quality-efficient products appear first;
rows without a positive task time remain visible but have no derived value.

### Free hosted base models

The [Free Hosted Models dashboard](https://ons96.github.io/coding-agents-leaderboard/free_models.html) lists Intelligence Index rows whose base models have reviewed hosted zero-cost API routes. **Reasoning effort is assumed available, not verified:** the free provider may not support the exact high, medium, low, minimal, or non-reasoning configuration used in a leaderboard row. Different releases and specialized model variants are not treated as interchangeable. The default table shows every eligible scored row ordered by estimated Score/min; the row filter's **Pareto: fastest per Index** view keeps only rows no other eligible row beats on both estimated time and Index. Search and sort never recompute that global frontier.

### Which of *my* models are Pareto-optimal

The site's free filter is a curated list and goes stale. `free_frontier.py`
answers the narrower question: the frontier over models you can actually call.
It reads an opencode config (provider -> models), matches model IDs to
leaderboard rows (exact normalized slug first; ids missing a size or effort
token fall back to a looser match marked `~`), and prints the time/Index and
time/cost/Index frontiers with the route that serves each row. Rerun it
whenever providers change.

```bash
python free_frontier.py                               # ~/CodingProjects/opencode.json
python free_frontier.py --providers logfare,tokeness   # only the gateways you want
python free_frontier.py --min-index 30 --csv my_frontier.csv
```

A model with no AA Index or no time estimate cannot be ranked, so it never
appears; the script prints how many configured model IDs were unmatched. This
is availability from your config, not proof of free quota: narrow with
`--providers` to the gateways you use for zero-cost calls.

`data/verified_free_models.json` records leaderboard slugs, provider route IDs, evidence URLs, effort-assumption notes, and the review date. Add a row only after verifying free hosted input/output for the same base model; matching the leaderboard's effort is not required. Rows without an Index or score/min estimate are omitted. Unknown availability is not evidence of paid access; open weights alone do not qualify. Run `python build_site.py` to regenerate `docs/` after reviewing the inventory. The scheduled scrape also rebuilds the page from the committed inventory. Free quotas, prices, and availability can change between reviews.

Score/min uses estimated task duration from Artificial Analysis canonical token counts and output speed, **not measured task runtime or the free host's response speed**. See [Estimate calibration](#estimate-calibration) for the limitations.

## Pareto frontiers

Ranking by Score/min already divides by time, so comparing those scores again
double-counts quality and hides the real question: *what is the least model
that still clears the bar, and how long does it take?* Each leaderboard now
carries two Pareto flags and a row filter:

| Column | Objectives | Reads as |
|---|---|---|
| `Pareto (fast/Index)` (`pareto`) | min estimated time, max Index | fastest row at each quality level |
| `Pareto (fast+cheap)` (`pareto_cost`) | min time, min cost, max Index | same, but a much cheaper row survives even when something slightly faster exists |

A row is kept only when no other row is at least as good on every objective
and strictly better on one. Objectives per tab: Coding Agents and Agentic
Models use Index, `avg_execution_time_sec`, and `cost_per_task_usd`;
Intelligence Index uses `est_time_per_task_min` and `est_cost_per_task_usd`;
Search APIs use Search Index, `time_per_task_seconds`, and combined search +
model cost. Rows missing any objective are never on a frontier and cannot
dominate anything, so incomplete source data cannot invent a winner.

The controls (`All rows` / `Complete data only` / `Pareto: fastest per Index` /
`Pareto: fastest + cheapest per Index`) filter rows without recomputing the
frontier, and selecting a Pareto view also sorts by Time/Task ascending.
`Complete data only` drops rows lacking the tab's Index or its per-time ratio
(the Intelligence Index tab has 739 rows but only 126 Scored models and 115
with a Score/min value). The `Min Index` box hides rows below a capability bar,
which is the practical "this task needs at least X" cutoff: combine it with
`Pareto: fastest per Index` to get the fastest sufficient model.

Caveats: estimated time is derived from canonical token counts and output
speed, not measured task runtime (see [Estimate calibration](#estimate-calibration));
use the ordering, treat differences under a few percent as ties, and do not
compare absolute minutes across tabs. The cost axis is list price per task, not
a free-tier quota or model multiplier; quota-aware frontiers need that data
added to `data/verified_free_models.json` first.

### Task families (is it smart enough?)

The Index is an average, so a model can rank well and still be weak at one
kind of task. The Intelligence Index and Free Hosted tables therefore also show
`Weakest Task` (lowest measured family score, e.g. `T12.0`) and the full
profile as percentages: T = `terminalBench40` (falling back to
`terminalBench21` when the 40-task set was not run), C = `scicode`,
G = `gpqa`, H = `hle`.

Only evals the model actually ran count. The source writes `0.0` for "not run"
on some columns (66 of the 72 zeros on `terminalBench40` belong to models with
a healthy `terminalBench21`), so a literal zero is treated as missing; a model
with no terminal eval gets no T entry rather than a fake 0%. A non-reasoning
variant still often lands far below its reasoning sibling on the same
benchmark. Rows with no measured family keep blank cells.

## Columns

All tabs also expose the `Pareto (fast/Index)` / `Pareto (fast+cheap)` flags,
the Free API markers (Coding Agents, Agentic Models, Intelligence Index), and
the row filter described above.

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

Daily `cron: '0 6 * * *'` runs `check_aa_change.py --mode check`, which hashes
only the embedded dataset payload of the 3 AA source pages (ignores HTML-shell
churn like build IDs). The full scrape + Pages deploy runs only when the hash
differs from `data/aa_source_hashes.json` — so new-model releases land on the
site within ~24h instead of waiting for Sunday. Weekly Sunday cron + manual
`workflow_dispatch` (with `force_full` to bypass the gate) remain as backstop.
On change it commits via `github-actions[bot]` (data + new baseline hashes)
and deploys `docs/` to GitHub Pages.

## Estimate calibration

`est_cost_per_task_usd` / `est_time_per_task_min` in
`data/artificial_analysis_intelligence_index_full.csv` are ESTIMATES from
public suite token totals x list pricing, not AA-measured values (AA ships no
measured per-task cost/time for these models). Calibrated 2026-09-06 against
measured coding-agents values (`python calibrate_estimates.py`, n=40 matched
models): cost measured/est median 34.4x (IQR 23.5-55.6), time 13.0x (IQR
7.7-18.9), cost-rank Spearman 0.80. Rule of thumb: multiply est cost by ~30
for agentic-task spend; ranking models by est cost is reliable. Rerun
`calibrate_estimates.py` after any fresh scrape (new models, price or suite
changes) to confirm the factors still hold.
