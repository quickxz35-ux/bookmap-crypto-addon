# Bookmap Crypto Addon

A high-performance Python addon for Bookmap that calculates and visualizes advanced orderbook metrics, including bias and imbalance signals.

## Features
- **Signal Engine**: Advanced Buy/Sell bias calculation using orderbook depth and aggressive volume.
- **Subcharts**: 4 real-time indicators rendered in the Bookmap subchart (Long Bias, Short Bias, Imbalance, Net Bias).
- **Redundancy**: Robust BBO (Best Bid/Offer) tracking for market-aware analysis.
- **POI Detection**: Automated alerts for Point of Interest (POI) and major absorption levels.

## Installation
1. Copy the contents of this repository to your computer.
2. In Bookmap, go to **Settings** -> **Python** -> **Edit script**.
3. Choose **Build** and select `CRYPTO.py` as your launcher.
4. Load the generated `.jar` file through Bookmap's **Configure Addons** menu.

## Tuning Guide
Use the settings sliders in Bookmap to adjust:
- **Imbalance Window**: Timeframe for top-of-book pressure analysis.
- **Bias Window**: Smoothing period for buying/selling pressure signals.
- **Thresholds**: Sensitivity for imbalance and aggressive pressure detection.

---
*Created with ANTIGRAVITY*
