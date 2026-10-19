# Search API efficiency

The Search APIs leaderboard exposes a derived Search Index per second value, calculated by dividing each product's Artificial Analysis Search Index by its Time/Task in seconds, so users can compare search quality and speed in one higher-is-better metric; products without a valid positive task time remain visible with an empty derived value and sort last.

## Acceptance criteria

1. The Search APIs table includes a clearly labeled Search Index / Time (per s) column.
2. The table defaults to descending Search Index per second and still supports sorting by the existing metrics.
3. Missing or zero task times do not break scraping or rendering and produce no efficiency value.
