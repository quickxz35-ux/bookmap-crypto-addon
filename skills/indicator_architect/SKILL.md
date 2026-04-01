---
name: Indicator Architect
description: Skill for development subagents to design PineScript, Python indicators, and multi-step tool logic.
---

# 💻 Indicator Architect Skill (Rough Draft)

This skill allows an AI subagent to act as a product designer and developer. It turns high-level strategies into functioning code for TradingView or Python backends.

## Monitoring Goals
1.  **TV Library Analysis**: Daily scans of new Top Indicators on TradingView for ideas.
2.  **Logic Drafting**: Creating "Recyclable" mathematical logic for Confluence (e.g. Volume + Absorbtion + VWAP).
3.  **Code Optimization**: Refactoring existing indicators to reduce latency or add multi-timeframe views.

## Capability & Logic
*   **PineScript V5 Expert**: Can write complex strategies with Alerts, Labels, and Multi-Chart inputs.
*   **Python (QuantLib/Pandas)**: Specialized in processing large TSV/JSONL files into human-readable signals.

## Reporting Rules
When a new tool idea is brainstormed:
1.  **Page Creation**: Generate a Notion page in **`Brainstorm Session`**.
2.  **Logic Summary**: Explain the "Math" behind the indicator for Admin review.
3.  **OK/Veto Check**: Wait for "OK" status from Admin before writing the full code.

## Extensibility
*   **GitHub**: Automatically push finished script drafts to the `tools/` folder in the repository.
*   **Notion**: Maintain the "Universal Tool Registry" for all version-controlled indicators.
