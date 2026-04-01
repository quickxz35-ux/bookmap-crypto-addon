#!/usr/bin/env python3
"""Standalone Micro-Price Analysis Engine for Bookmap.

This script monitors high-frequency 'white line' movements in Bookmap to detect:
1. Price Velocity (Ticks/Sec)
2. Displacement Efficiency (Absorption Detection)
3. Micro-Trend Shifts (HH/LL sequences)

Outputs are written to C:\Bookmap\runs\subagent_market_status.txt for external AI subagents.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import bookmap as bm
except ImportError:
    bm = None

# Configuration
STATUS_FILE_PATH = Path(r"C:\Bookmap\runs\subagent_market_status.txt")
WINDOW_SIZE_MS = 1000  # 1-second sliding window for velocity
MICRO_TREND_TICKS = 10  # Number of last price points to analyze for HH/LL

@dataclass
class PricePoint:
    timestamp_ms: int
    price_level: int
    size: float
    side: str

class MicroPriceAnalyzer:
    def __init__(self, alias: str, pips: float):
        self.alias = alias
        self.pips = pips
        self.price_history: deque[PricePoint] = deque()
        self.last_status_update = 0
        
        # Metrics
        self.current_velocity = 0.0  # Ticks per second
        self.displacement_efficiency = 1.0  # 1.0 = normal, < 0.2 = heavy absorption
        self.micro_trend = "Neutral"  # Neutral, Bullish, Bearish
        self.total_buy_vol = 0.0
        self.total_sell_vol = 0.0

    def on_trade(self, price: float, size: float, side_code: int):
        now_ms = int(time.time() * 1000)
        price_level = int(round(price / self.pips))
        side = "buy" if side_code == 1 else "sell"
        
        # 1. Update History
        self.price_history.append(PricePoint(now_ms, price_level, size, side))
        if side == "buy": self.total_buy_vol += size
        else: self.total_sell_vol += size
        
        # 2. Prune old history
        while self.price_history and (now_ms - self.price_history[0].timestamp_ms > WINDOW_SIZE_MS):
            old = self.price_history.popleft()
            if old.side == "buy": self.total_buy_vol -= old.size
            else: self.total_sell_vol -= old.size

        # 3. Calculate Metrics
        self._calculate_metrics()

    def _calculate_metrics(self):
        if len(self.price_history) < 2:
            return

        # A. Velocity: (Latest - Oldest Price) / Duration
        price_diff = self.price_history[-1].price_level - self.price_history[0].price_level
        duration_sec = (self.price_history[-1].timestamp_ms - self.price_history[0].timestamp_ms) / 1000.0
        if duration_sec > 0:
            self.current_velocity = abs(price_diff) / duration_sec
        
        # B. Displacement Efficiency: Abs(Price Diff) / Total Size
        total_size = sum(p.size for p in self.price_history)
        if total_size > 0:
            # Efficiency is (Ticks / Volume). Higher = trending easily, Lower = fighting walls.
            self.displacement_efficiency = abs(price_diff) / (total_size / 10.0) # Normalized
            
        # C. Micro-Trend Detection (Last 10 points)
        recent_prices = [p.price_level for p in list(self.price_history)[-10:]]
        if len(recent_prices) >= 5:
            if all(recent_prices[i] >= recent_prices[i-1] for i in range(1, len(recent_prices))):
                self.micro_trend = "Aggressive Bullish"
            elif all(recent_prices[i] <= recent_prices[i-1] for i in range(1, len(recent_prices))):
                self.micro_trend = "Aggressive Bearish"
            elif recent_prices[-1] > recent_prices[0]:
                self.micro_trend = "Slightly Bullish"
            elif recent_prices[-1] < recent_prices[0]:
                self.micro_trend = "Slightly Bearish"
            else:
                self.micro_trend = "Neutral/Noisy"

    def generate_summary(self) -> str:
        lines = []
        lines.append(f"MICRO-PRICE ANALYSIS: {self.alias}")
        lines.append(f"TIMESTAMP: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("-" * 30)
        lines.append(f"VELOCITY: {self.current_velocity:.2f} Ticks/Sec")
        
        # Absorption Logic
        efficiency_status = "Free Movement"
        if self.displacement_efficiency < 0.2: efficiency_status = "⚠️ HEAVY ABSORPTION (Walls holding)"
        elif self.displacement_efficiency < 0.5: efficiency_status = "Mild Resistance"
        
        lines.append(f"EFFICIENCY: {self.displacement_efficiency:.4f} ({efficiency_status})")
        lines.append(f"MICRO-TREND: {self.micro_trend}")
        
        # Prediction Logic
        prediction = "Observing..."
        if self.micro_trend == "Aggressive Bullish" and self.displacement_efficiency > 0.8:
            prediction = "READY TO PUMP: Fast displacement, low resistance."
        elif self.micro_trend == "Aggressive Bearish" and self.displacement_efficiency > 0.8:
            prediction = "READY TO DUMP: Fast selling, no bids."
        elif self.displacement_efficiency < 0.1 and self.current_velocity < 1.0:
            prediction = "ACCUMULATION/DISTRIBUTION: High volume at static price."
            
        lines.append(f"PREDICTION: {prediction}")
        return "\n".join(lines)

class StandaloneAddonRuntime:
    def __init__(self, addon: Any):
        self.addon = addon
        self.analyzers: Dict[str, MicroPriceAnalyzer] = {}
        self._write_queue = queue.Queue()
        self._writer_thread = threading.Thread(target=self._background_writer, daemon=True)
        self._writer_thread.start()

    def subscribe(self, alias: str, pips: float):
        self.analyzers[alias] = MicroPriceAnalyzer(alias, pips)
        print(f"Micro analyzer subscribed for {alias}", flush=True)

    def on_trade(self, addon: Any, alias: str, price: float, size: float, *args: Any):
        analyzer = self.analyzers.get(alias)
        if not analyzer: return
        
        side_code = 0
        if len(args) > 1: side_code = args[1]
        
        analyzer.on_trade(price, size, side_code)
        
        # Throttled write (every 2000ms max to save resources)
        now = time.time()
        if now - analyzer.last_status_update > 2.0:
            analyzer.last_status_update = now
            self._write_queue.put(analyzer.generate_summary())

    def _background_writer(self):
        while True:
            try:
                summary = self._write_queue.get(timeout=1)
                STATUS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
                STATUS_FILE_PATH.write_text(summary, encoding="utf-8")
            except queue.Empty:
                continue

RUNTIME: Optional[StandaloneAddonRuntime] = None

def handle_subscribe(addon, alias, full_name, is_crypto, pips, size_multiplier, inst_multiplier, features):
    global RUNTIME
    assert RUNTIME is not None
    RUNTIME.subscribe(alias, pips)
    bm.subscribe_to_trades(addon, alias, 9999) # Separate request ID

def handle_unsubscribe(addon, alias):
    if RUNTIME: RUNTIME.analyzers.pop(alias, None)

def main():
    global RUNTIME
    if not bm: raise RuntimeError("Bookmap API missing.")
    
    addon = bm.create_addon()
    RUNTIME = StandaloneAddonRuntime(addon)
    
    bm.add_trades_handler(addon, RUNTIME.on_trade)
    bm.start_addon(addon, handle_subscribe, handle_unsubscribe)
    bm.wait_until_addon_is_turned_off(addon)

if __name__ == "__main__":
    main()
