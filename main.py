#!/usr/bin/env python3
"""Top-level launcher so CI can run `python main.py` from repo root."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.main import run

if __name__ == "__main__":
    run()
