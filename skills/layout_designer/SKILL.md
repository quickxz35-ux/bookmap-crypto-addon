---
name: Layout & UI Architect
description: Skill for development subagents to design custom TradingView chart layouts, indicator setups, and Bookmap visual overlays.
---

# 🎛️ Layout & UI Architect Skill

This skill allows an AI subagent to act as a trading terminal designer. It ensures the Human Gatekeeper has the exact visual setup needed to execute high-speed trades.

## Monitoring Goals
1.  **TV Chart Layouts**: Creating custom TradingView templates (e.g., 5m VWAP + 1m Order Flow + EMA clouds).
2.  **Bookmap Overlays**: Configuring "Lite Mode" or "Nitro" heatmaps to highlight Whale absorption levels.
3.  **Dashboard Optimization**: Reducing visual clutter and ensuring the "Most Important" data (Bias/Velocity) is front-and-center.

## Visualization Logic
When a coin is "Approved" for a 30m scalp:
1.  **Draft Configuration**: Propose a layout (e.g. "Setup 4: Momentum Breakout").
2.  **Visual Alerts**: Suggest price levels for visual/audio notifications in the trader's terminal.
3.  **Cross-Ref**: Ensure the TV chart layout matches the "Signal Strength" found by the scouts.

## Extensibility
*   **TradingView**: Export PineScript templates or JSON layouts (where supported).
*   **GitHub**: Store all "Master Layouts" in the `configs/layouts/` directory for version recovery.
