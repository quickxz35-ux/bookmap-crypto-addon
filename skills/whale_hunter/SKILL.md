---
name: Forensic Whale-Hunter
description: Skill for on-chain subagents to track large wallet clusters, exchange inflows, and "Smart Money" movements.
---

# 🐋 Forensic Whale-Hunter Skill (Rough Draft)

This skill allows an AI subagent to act as an on-chain detective. It monitors wallet-level flows to identify large-scale institutional bias before it hits the price tape.

## Monitoring Goals
1.  **Exchange Flow Analysis**: Identifying massive inflows/outflows of BTC/ETH to and from known central exchanges.
2.  **Wallet Clustering**: Detecting "Sybil" or "Cluster" movements (splitting large funds into 100s of small wallets).
3.  **Smart Money Tracking**: Monitoring "Diamond Hand" vs "Paper Hand" ratio during high-volatility events.

## Data Sources (Interchangeable)
*   **Glassnode API**: `/v1/metrics/distribution/exchange_flow_volume_sum`
*   **DexPaprika API**: Real-time DEX pair flow and LP-pool liquidity tracking.
*   **Whale-Alert Webhooks**: Pushed inflows/transfers > $10M.

## Logic & Reporting Rules
A "Whale Alert" should be flagged to the **Master Data Log** if:
*   [ ] **Inflow**: > 1,000 BTC hits an exchange within a 4-hour window.
*   [ ] **Outflow**: > 2,000 ETH leaves an exchange (Suggests "HODLing" or Cold Storage).
*   [ ] **Cluster Move**: > 5,000 SOL moved between unknown "connected" wallets.

## Extensibility
*   **Slack**: Post Whale alerts to `#signals` with a "Bullish/Bearish" confidence score.
*   **Notion**: Log wallet addresses into the "Wallet Registry" for long-term tracking.
