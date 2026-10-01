# Est Time/Task fix

Replace the 5-suite mean-seconds estimator in intel_index_full_extract.py with the AA Intelligence Index v4.3.2 weighted-minutes method: per-eval output tokens divided by task count excluding repeats divided by median output speed, weighted by index weights over the 10 index evals, output in minutes to match AA Time per Task display; update build_index_tab.py label and score ratios to minutes.

## Acceptance Criteria
- [ ] Fresh extract gives muse-glimmer ~1.7 and mistral-medium-3-5 ~2.4 (±0.25) in est time column.
- [ ] All 679 scored rows preserved, extractor still stdlib plus cryptography only.
- [ ] models_full tab rebuilt with minutes label and calibrate_estimates.py re-run logged.
