---
name: Strategy Selection
description: Skill for specialized subagents to cross-reference data sources and pick high-probability coins based on whale, exchange, and derivatives data.
---

# 🎯 Strategy Selection Skill (The "Coin Picker")

This skill allows an AI subagent to act as a Portfolio Manager. It cross-references all "Scout" pipes (Whale, Quant, Macro) to identify the best coins to monitor for specific timeframes.

## Monitoring Goals
1.  **Scalp Targets (30m window)**: High-speed absorption or velocity breakouts (Bookmap/Nitro data).
2.  **Daily Favorites (24h trend)**: Identifying consistent daily bias and macro shifts (Glassnode data).
3.  **Whale Clusters**: Spotting multi-wallet accumulation of low-cap or emerging coins (Hive/Zerion data).
4.  **Exchange Flows**: Confirming institutional accumulation via net exchange outflows.
5.  **Smart Money Positions**: Copy-tracking top traders opening derivatives positions in certain directions.

## Decision & Approval Logic
A "Selection Request" must be submitted to the **Notion HUB** before any action:
*   [ ] **The Pitch**: Explain the data (e.g. "Whale bought + Exchange Outflow + Positive Funding").
*   [ ] **The Target**: Define the timeframe (30m scalp vs. 24h trend).
*   [ ] **The Status**: Set to "PENDING" and wait for "ADMIN OK."

## Extensibility
*   **Slack**: Post "Pending Requests" to `#brainstorm` for quick user feedback.
*   **Notion**: Log all "Picks" into the "Watchlist" database with a history of win/loss for backtesting.
