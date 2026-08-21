"""Configuration loader for the Artificial Analysis coding-agents scraper."""

import os
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: Path | None = None) -> dict:
    """Load YAML config with environment-variable overrides.

    Env overrides: AA_TARGET_URL, AA_OUTPUT_DIR, AA_OUTPUT_CSV, AA_OUTPUT_XLSX
    """
    cfg_path = path or DEFAULT_CONFIG_PATH
    with open(cfg_path) as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError(f"Invalid config format in {cfg_path}")

    config.setdefault("target_url", "https://artificialanalysis.ai/agents/coding-agents")
    config.setdefault("output_dir", "data")
    config.setdefault("output_csv_name", "artificial_analysis_coding_agents.csv")
    config.setdefault("output_xlsx_name", "artificial_analysis_coding_agents.xlsx")
    config.setdefault("request_timeout_seconds", 30)
    config.setdefault("request_retries", 3)
    config.setdefault("request_backoff_seconds", 2)
    config.setdefault(
        "user_agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )

    env_map = {
        "target_url": "AA_TARGET_URL",
        "output_dir": "AA_OUTPUT_DIR",
        "output_csv_name": "AA_OUTPUT_CSV",
        "output_xlsx_name": "AA_OUTPUT_XLSX",
    }
    for key, env_var in env_map.items():
        val = os.environ.get(env_var)
        if val:
            config[key] = val

    config["request_timeout_seconds"] = int(config["request_timeout_seconds"])
    config["request_retries"] = int(config["request_retries"])
    config["request_backoff_seconds"] = int(config["request_backoff_seconds"])

    return config
