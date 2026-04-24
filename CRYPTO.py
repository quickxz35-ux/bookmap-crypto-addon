#!/usr/bin/env python3
"""Bootstrap Bookmap script that loads the local crypto orderflow project."""

from __future__ import annotations
import sys
from pathlib import Path

# Explicit project directory for the Bookmap loader
PROJECT_DIR = Path(r"C:\Users\gssjr\OneDrive\Documents\New project")
# Unified telemetry directory used by both the adapter and the brain bridge
BOOKMAP_RUNS_DIR = Path(r"C:\Bookmap\Config\runs")
BOOKMAP_RUNS_DIR.mkdir(parents=True, exist_ok=True)

# Add project to sys.path if not present
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

with (BOOKMAP_RUNS_DIR / "crypto_bootstrap_probe.txt").open("a", encoding="utf-8") as probe:
    probe.write(f"bootstrap start at {BOOKMAP_RUNS_DIR}\n")

from bookmap_addon_adapter import main

if __name__ == "__main__":
    main(
        alert_path=str(BOOKMAP_RUNS_DIR / "bookmap_alerts.jsonl"),
        snapshot_dir=str(BOOKMAP_RUNS_DIR / "bookmap_snapshots"),
        snapshot_history_path=str(BOOKMAP_RUNS_DIR / "bookmap_snapshots_history.jsonl"),
        brain_latest_path=str(BOOKMAP_RUNS_DIR / "brain_feed_latest.json"),
        brain_history_path=str(BOOKMAP_RUNS_DIR / "brain_feed_history.jsonl"),
    )
