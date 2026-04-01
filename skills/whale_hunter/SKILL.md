---
name: Forensic Whale-Hunter
description: Skill for on-chain subagents to track large wallet clusters, exchange inflows, and "Smart Money" movements.
---

# 🐋 Forensic Whale-Hunter Skill (3-Pillar Engine)

This skill allows an AI subagent to act as an on-chain detective. It monitors specific wallet addresses and large-scale inflows using a triple-redundant "Free Engine" architecture.

## Monitoring Goals
1.  **Individual Wallet Tracking**: Monitoring the balances, trades, and PnL of specific "Smart Money" wallets.
2.  **Real-Time Token Inflows**: Pinging the workspace the second a Whale moves > $100k of an asset.
3.  **Cross-Chain Portfolio Analysis**: Seeing the total Net Asset Value (NAV) of a Whale across 60+ chains (EVM, Solana, etc.).

## The 3-Pillar Data Engine (Interchangeable)
*   🧬 **HIVE Intelligence (The Backbone)**: Unified API for 60+ blockchains. Used for multi-chain portfolio aggregation and NAV history.
*   💹 **ZERION (The Analyst)**: Specialist in PnL, Unrealized Gains, and DeFi position decoding (LP Pools, Staking).
*   📡 **MORALIS (The Sentinel)**: Real-time "Streams" API. Used to get instant push-alerts the moment a watched wallet makes a move.

## Logic & Reporting Rules
A "Whale Alert" should be flagged to the **Master Data Log** if:
*   [ ] **High-Velocity Buy**: A watched wallet buys > $50k of a low-cap coin.
*   [ ] **Exchange Exit**: > 1,000 BTC leaves an exchange to a known "Diamond Hand" entity.
*   [ ] **Smart Money Consensus**: At least 3 high-PnL wallets are accumulating the same asset.

## Extensibility
*   **Slack**: Post Whale alerts to `#signals` with a "Bullish/Bearish" confidence score.
*   **Notion**: Log wallet profiles into the "Whale Registry" for 24/7 automated tracking.
