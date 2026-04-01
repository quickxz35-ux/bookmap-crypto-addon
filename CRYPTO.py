#!/usr/bin/env python3
"""Bootstrap Bookmap script that loads the local crypto orderflow project."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_DIR = Path(r"C:\Users\gssjr\OneDrive\Documents\New project")
BOOKMAP_RUNS_DIR = Path(r"C:\Bookmap\runs")
BOOKMAP_RUNS_DIR.mkdir(parents=True, exist_ok=True)
with (BOOKMAP_RUNS_DIR / "crypto_bootstrap_probe.txt").open("a", encoding="utf-8") as probe:
    probe.write("bootstrap start\n")
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

with (BOOKMAP_RUNS_DIR / "crypto_bootstrap_probe.txt").open("a", encoding="utf-8") as probe:
    probe.write("project path inserted\n")

from bookmap_addon_adapter import main

with (BOOKMAP_RUNS_DIR / "crypto_bootstrap_probe.txt").open("a", encoding="utf-8") as probe:
    probe.write("adapter import ok\n")


if __name__ == "__main__":
    with (BOOKMAP_RUNS_DIR / "crypto_bootstrap_probe.txt").open("a", encoding="utf-8") as probe:
        probe.write("calling main\n")
    main(
        alert_path=str(BOOKMAP_RUNS_DIR / "bookmap_alerts.jsonl"),
        snapshot_dir=str(BOOKMAP_RUNS_DIR / "bookmap_snapshots"),
        snapshot_history_path=str(BOOKMAP_RUNS_DIR / "bookmap_snapshots_history.jsonl"),
    )
