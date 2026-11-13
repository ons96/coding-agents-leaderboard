# Pareto frontiers and completeness filter

Replace the score/min keep-rule (`pareto` = "Index beats every faster row's
Index", computed off `score_per_minute`) with a real Pareto dominance test over
estimated time, optional cost, and Index; add a row filter so incomplete or
dominated rows can be hidden without losing them from the table.

## Why

`score_per_minute` already divides the Index by time, so ranking by it and then
comparing Index values again double-counts quality. The decision a reader
actually makes is "cheapest/fastest model that is still good enough", which is
a dominance question over (time, cost, Index), not a single ratio.

## Columns

- `pareto` (`Pareto (fast/Index)`) — minimize estimated time per task, maximize
  Index.
- `pareto_cost` (`Pareto (fast+cheap)`) — minimize time, minimize cost per
  task, maximize Index.

A row is non-dominated when no other row is at least as good on every objective
and strictly better on at least one. Identical objective tuples keep the first
row in deterministic (slug/model) order. Rows missing any objective are neither
flagged nor allowed to dominate, so missing data cannot manufacture a winner.
Cost is the sum of the tab's cost fields (Search APIs: search + model cost per
1k tasks). The free-hosted tab is all zero-cost, so it publishes only `pareto`.

## Filter

`#frontier` select: `All rows`, `Complete data only`, `Pareto: fastest per
Index`, `Pareto: fastest + cheapest per Index`. `Complete data only` requires
every field in the tab's `complete` list to be a finite positive number.
`#min-score` (number input) hides rows below a capability bar. Selecting a
Pareto option sets the sort to the tab's time field ascending.

## Acceptance criteria

- [ ] `build_site.py` emits `FRONTIER` metadata and the two flag columns on
      agents, models, models_full, free_models, and search_apis.
- [ ] Frontier counts stable for the committed data: models_full 13
      (`pareto`) / 26 (`pareto_cost`), agents 12/16, models 8/12,
      free_models 7, search_apis 3/4.
- [ ] `Complete data only` on models_full yields 115 rows (Index and
      Score/min present).
- [ ] Inline scripts and `docs/*.data.js` pass `node --check`.
