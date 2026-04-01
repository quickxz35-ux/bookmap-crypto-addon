---
name: Macro Sentinel
description: Skill for sentry subagents to monitor news, sentiment, SEC filings, and global market-moving events.
---

# 🌍 Macro Sentinel Skill (Rough Draft)

This skill allows an AI subagent to act as a global monitor. It ensures the "Spider Bubble" is aware of exogenous events that could override technical signals.

## Monitoring Goals
1.  **News Filtering**: 24/7 scanning for SEC filings (ETF approvals), Exchange listings, and Central Bank news.
2.  **Sentiment Scanning**: Identifying "Fear Levels" on X (Twitter) and Telegram for specific coins.
3.  **Calendar Alerts**: Pinging the workspace for scheduled FOMC / CPI releases.

## Data Sources (Interchangeable)
*   **LunarCrush / Santiment**: Sentiment and social dominance metrics.
*   **Financial News APIs**: Reuters, Bloomberg, and CoinDesk feeds.
*   **X (Twitter) API**: Real-time following of a curated list of "Market Movers."

## Logic & Reporting Rules
A "Macro Alert" should be triggered to **Slack `#general`** if:
*   [ ] **News Flash**: High-confidence report of an ETF approval or major exchange hack.
*   [ ] **Fear Peak**: Social sentiment for a held asset drops into the "Extreme Fear" zone.
*   [ ] **TDM Event**: (T-Minus 1 Hour) Alert before CPI/FOMC releases.

## Extensibility
*   **Slack**: Post priority "Red News" alerts in bold (overrides standard scalping signals).
*   **Notion**: Log significant "Sentiment Shifts" to the "Master Data Log" as context for the Whale Hunter.
