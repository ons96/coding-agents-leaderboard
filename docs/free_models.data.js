const TABLE_DATA=[];
const COLUMNS=["model", "creator", "score_per_minute", "intelligenceIndex", "est_time_per_task_min", "medianCanonicalAnswerOutputSpeed", "free_access"];
const LABELS={"slug": "Slug", "model": "Model", "creator": "Creator", "releaseDate": "Released", "sizeClass": "Size Class", "isReasoning": "Reasoning", "isOpenWeights": "Open Weights", "intelligenceIndex": "Index", "price1mInputTokens": "Price/1M In ($)", "price1mOutputTokens": "Price/1M Out ($)", "medianCanonicalAnswerOutputSpeed": "Median Out Tok/s", "est_cost_per_task_usd": "Est Cost/Task ($)", "est_time_per_task_min": "Est Time/Task (min)", "score_per_cost": "Score/$", "score_per_minute": "Score/min", "score_per_sec": "Score/sec", "pareto": "Pareto", "has_free_api": "Free API", "free_access": "Free base-model API"};
const HIGHLIGHTS={"score_per_minute": "higher", "intelligenceIndex": "higher"};
const COL_GROUPS={"identity": ["model", "creator", "free_access"], "derived": ["score_per_minute", "intelligenceIndex", "est_time_per_task_min", "medianCanonicalAnswerOutputSpeed"]};
const GROUP_ORDER=["identity", "derived"];
const GROUP_LABELS={"identity": "Identity & Access", "derived": "Quality & Speed"};
const META={"row_count": 0, "scrape_date": "2026-11-04T14:16:36.335773+00:00"};
