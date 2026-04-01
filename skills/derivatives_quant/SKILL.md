---
name: Derivatives Quant
description: Skill for market data subagents to analyze Funding Rates, Open Interest (OI), and Liquidation Heatmaps.
---

# 📈 Derivatives Quant Skill (Rough Draft)

This skill allows an AI subagent to act as a quant analyst. It monitors derivatives data to identify "Over-Leverage" zones and potential "Short Squeeze" setups.

## Monitoring Goals
1.  **Funding Rate Scans**: Detecting extreme positive/negative funding across BTC/ETH pairs.
2.  **Open Interest (OI) Analysis**: Tracking when new contracts are being opened/closed during a trend move.
3.  **Liquidation Heatmaps**: Predicting where "Price Cascades" (forced liquidations) are likely to trigger.

## Data Sources (Interchangeable)
*   **Glassnode API**: `/v1/metrics/derivatives/futures_funding_rate_weighted_by_volume`
*   **Binance/Bybit Public API**: Real-time OI and Liquidation feeds.
*   **Coinalyze/Velo Data**: Aggregated heatmaps of taker flow.

## Logic & Reporting Rules
A "Quant Alert" should be flagged if:
*   [ ] **Funding Extremes**: > 0.01% (Aggressive Longs) or < -0.01% (Aggressive Shorts).
*   [ ] **OI Spike**: > 15% increase in Open Interest within a 1-hour window.
*   [ ] **Liquidation Magnet**: Price is within 0.5% of "Major Liquidation Level" (Cluster of stop-losses).

## Extensibility
*   **Slack**: Post alerts to `#signals` with: "SQUEEZE POTENTIAL: HIGH."
*   **Notion**: Sync OI/Funding charts to the "Market Status" page.
