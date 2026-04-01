#!/usr/bin/env python3
"""Bookmap Python API adapter for the local Bookmap signal engine.

This module is meant to run inside Bookmap's Python addon environment.
It subscribes to depth and trade data, translates callbacks into normalized
events, feeds the local signal engine, and emits alerts through:

1. Bookmap message log
2. Python stdout
3. JSONL file on disk
"""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from bookmap_signal_engine import BookmapSignalEngine
from bookmap_signal_models import AlertRecord, EngineConfig, NormalizedBookmapEvent, TrackedLevel, FeatureSnapshot
from bookmap_signal_engine import EngineStepResult

try:
    import bookmap as bm
    from bookmap import bookmap as bm_core
except ImportError:  # pragma: no cover
    bm = None
    bm_core = None


# Desktop popups in Bookmap are driven by send_user_message. Keep this off by
# default so alerts still flow to files/indicators without spamming the
# desktop corner, but allow per-instrument override in the settings panel.
DEFAULT_ENABLE_BOOKMAP_ALERT_POPUPS = False
PRELOAD_SNAPSHOT_HISTORY_ON_STARTUP = False
TYPEABLE_SETTING_SUFFIX = "\u200b"
DISPLAY_SMOOTHING_ALPHA_BIAS = 0.35
DISPLAY_SMOOTHING_ALPHA_IMBALANCE = 0.25
DEFAULT_LONG_BIAS_COLOR = (0, 255, 0)
DEFAULT_SHORT_BIAS_COLOR = (255, 64, 64)
DEFAULT_TOP_BOOK_IMBALANCE_COLOR = (64, 160, 255)
DEFAULT_NET_BIAS_COLOR = (255, 215, 0)

SETTING_ENABLE_POPUPS = "SHOW ALERT POPUPS"
SETTING_NEAR_BOOK_TICKS = ">> HOW FAR FROM PRICE TO SCAN FOR S/R ACTIVITY" + TYPEABLE_SETTING_SUFFIX
SETTING_FAST_WINDOW_SECONDS = ">> HOW MANY RECENT SECONDS TO MEASURE BUYING, SELLING, STACKING, AND PULLING" + TYPEABLE_SETTING_SUFFIX
SETTING_CONTEXT_WINDOW_MINUTES = ">> HOW MANY RECENT MINUTES TO MEASURE BUYING, SELLING, STACKING, AND PULLING" + TYPEABLE_SETTING_SUFFIX
SETTING_PERSISTENCE_SECONDS = ">> HOW LONG A LEVEL MUST REMAIN MEANINGFUL IN SIZE TO COUNT AS S/R" + TYPEABLE_SETTING_SUFFIX
SETTING_RELOAD_SECONDS = ">> HOW FAST A LEVEL MUST REFILL TO COUNT AS DEFENDED AGAIN" + TYPEABLE_SETTING_SUFFIX
SETTING_LARGE_LEVEL_FACTOR = ">> HOW MUCH BIGGER THAN NEARBY LEVELS TO COUNT AS S/R" + TYPEABLE_SETTING_SUFFIX
SETTING_IMBALANCE_THRESHOLD = ">> SCANNED ORDER BOOK IMBALANCE SENSITIVITY" + TYPEABLE_SETTING_SUFFIX
SETTING_AGGRESSION_THRESHOLD = ">> HOW STRONG MARKET BUYING/SELLING PRESSURE MUST BE TO AFFECT BIAS" + TYPEABLE_SETTING_SUFFIX
SETTING_LONG_BIAS_TIMEFRAME_MINUTES = ">> LONG BIAS WINDOW (MIN)" + TYPEABLE_SETTING_SUFFIX
SETTING_SHORT_BIAS_TIMEFRAME_MINUTES = ">> SHORT BIAS WINDOW (MIN)" + TYPEABLE_SETTING_SUFFIX
SETTING_NET_BIAS_TIMEFRAME_MINUTES = ">> NET BIAS WINDOW (MIN)" + TYPEABLE_SETTING_SUFFIX
SETTING_TOP_BOOK_IMBALANCE_TIMEFRAME_MINUTES = ">> TOP BOOK IMBALANCE WINDOW (MIN)" + TYPEABLE_SETTING_SUFFIX


def _add_string_setting_parameter(addon: Any, alias: str, parameter_name: str, default_value: str, reload_if_change: bool = False) -> None:
    if bm_core is None:
        raise RuntimeError("Bookmap core module is unavailable for string settings")

    msg = bm_core.FIELD_SEPARATOR.join(
        (
            bm_core.ADD_SETTING_FIELD,
            alias,
            "STRING",
            parameter_name,
            "1" if reload_if_change else "0",
            str(default_value),
        )
    )
    bm_core._push_msg_to_event_queue(addon, msg)


def _parse_int_setting(value: Any, minimum: int, maximum: int, fallback: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, parsed))


def _parse_float_setting(value: Any, minimum: float, maximum: float, fallback: float) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, parsed))


def _parse_color_setting(value: Any, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        return fallback
    try:
        return tuple(max(0, min(255, int(channel))) for channel in value)
    except (TypeError, ValueError):
        return fallback


@dataclass(slots=True)
class ConsoleAlertSink:
    def emit(self, alert: AlertRecord) -> None:
        print(f"[{alert.instrument}] {alert.alert_type}: {alert.message}", flush=True)


@dataclass(slots=True)
class JsonlAlertSink:
    path: Path

    def emit(self, alert: AlertRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "timestamp_ns": alert.timestamp_ns,
                        "instrument": alert.instrument,
                        "alert_type": alert.alert_type,
                        "priority": alert.priority,
                        "message": alert.message,
                        "price": alert.price,
                        "side": alert.side,
                        "level_id": alert.level_id,
                        "reason_codes": alert.reason_codes,
                        "context": alert.context,
                    }
                )
                + "\n"
            )


@dataclass(slots=True)
class JsonStateSink:
    latest_dir: Path
    history_path: Path

    def emit(self, alias: str, payload: Dict[str, Any]) -> None:
        self.latest_dir.mkdir(parents=True, exist_ok=True)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

        latest_path = self.latest_dir / f"{alias}_latest.json"
        latest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")


@dataclass(slots=True)
class InstrumentRuntime:
    alias: str
    pips: float
    size_multiplier: float
    engine: BookmapSignalEngine
    order_book: Any
    current_sizes: Dict[str, Dict[int, int]] = field(default_factory=lambda: {"bid": {}, "ask": {}})
    indicator_ids: Dict[str, int] = field(default_factory=dict)
    request_ids: Dict[str, int] = field(default_factory=dict)
    supported_features: Dict[str, object] = field(default_factory=dict)
    bookmap_alert_popups_enabled: bool = True
    initialized: bool = False  # True after first on_interval fires
    last_ui_update_time: float = 0.0  # Per-instrument throttling
    smoothed_indicator_values: Dict[str, float] = field(default_factory=dict)
    indicator_colors: Dict[str, tuple[int, int, int]] = field(
        default_factory=lambda: {
            "long_bias": DEFAULT_LONG_BIAS_COLOR,
            "short_bias": DEFAULT_SHORT_BIAS_COLOR,
            "top_book_imbalance": DEFAULT_TOP_BOOK_IMBALANCE_COLOR,
            "net_bias": DEFAULT_NET_BIAS_COLOR,
        }
    )
    long_bias_timeframe_minutes: int = 5
    short_bias_timeframe_minutes: int = 5
    net_bias_timeframe_minutes: int = 5
    top_book_imbalance_timeframe_minutes: int = 1


class BookmapAddonRuntime:
    def __init__(
        self,
        addon: Any,
        alert_path: str = "runs/bookmap_alerts.jsonl",
        snapshot_dir: str = "runs/bookmap_snapshots",
        snapshot_history_path: str = "runs/bookmap_snapshots_history.jsonl",
    ):
        self.addon = addon
        self.instruments: Dict[str, InstrumentRuntime] = {}
        self.console_sink = ConsoleAlertSink()
        self.jsonl_sink = JsonlAlertSink(Path(alert_path))
        self.state_sink = JsonStateSink(Path(snapshot_dir), Path(snapshot_history_path))
        self.pending_indicator_requests: Dict[int, tuple[str, str]] = {}
        self.pending_response_requests: Dict[int, tuple[str, str]] = {}
        self.callback_counts: Dict[str, int] = {"depth": 0, "trade": 0, "interval": 0}
        self.active_log_file = None
        self.last_snapshot_time = 0
        self._next_request_id_value = 1000
        self._subscribe_lock = threading.Lock()  # Serialize concurrent instrument subscriptions

        # Background writer: all disk I/O runs here so Bookmap callbacks never block
        self._write_queue: queue.Queue = queue.Queue(maxsize=200)
        self._writer_thread = threading.Thread(
            target=self._background_writer, daemon=True, name="BM-Writer"
        )
        self._writer_thread.start()

    def subscribe_instrument(
        self,
        alias: str,
        full_name: str,
        is_crypto: bool,
        pips: float,
        size_multiplier: float,
        instrument_multiplier: float,
        supported_features: Dict[str, object],
    ) -> None:
        del full_name, is_crypto, instrument_multiplier
        with self._subscribe_lock:  # One instrument at a time
            self._subscribe_instrument_locked(
                alias, pips, size_multiplier, supported_features
            )

    def _subscribe_instrument_locked(
        self,
        alias: str,
        pips: float,
        size_multiplier: float,
        supported_features: Dict[str, object],
    ) -> None:
        engine = BookmapSignalEngine(
            EngineConfig(
                instrument=alias,
                pips=pips,
                size_multiplier=size_multiplier,
            )
        )
        runtime = InstrumentRuntime(
            alias=alias,
            pips=pips,
            size_multiplier=size_multiplier,
            engine=engine,
            order_book=bm.create_order_book(),
            supported_features=supported_features,
        )
        runtime.long_bias_timeframe_minutes = max(1, int(round(engine.config.context_window_seconds / 60)))
        runtime.short_bias_timeframe_minutes = max(1, int(round(engine.config.context_window_seconds / 60)))
        runtime.net_bias_timeframe_minutes = 5
        runtime.top_book_imbalance_timeframe_minutes = 1
        if PRELOAD_SNAPSHOT_HISTORY_ON_STARTUP:
            self._preload_snapshot_history(runtime)
        self.instruments[alias] = runtime

        depth_request_id = self._next_request_id()
        trades_request_id = self._next_request_id()
        runtime.request_ids["depth"] = depth_request_id
        runtime.request_ids["trades"] = trades_request_id
        self.pending_response_requests[depth_request_id] = (alias, "depth")
        self.pending_response_requests[trades_request_id] = (alias, "trades")

        # Settings MUST be registered here in subscribe_instrument — Bookmap
        # requires it during the instrument info callback, not deferred.
        self._register_settings(alias)

        # Force subscribe to feeds. Some bridges report depth as unsupported
        # even when it's available. 
        bm.subscribe_to_depth(self.addon, alias, depth_request_id)
        bm.subscribe_to_trades(self.addon, alias, trades_request_id)

        # Register indicators IMMEDIATELY during initialization
        # Bookmap forbids registration outside of CustomModule#initialize
        self._register_indicators(alias)

        # Disk write only — safe on background thread
        self._enqueue_write(self._emit_heartbeat_snapshot, runtime, "instrument subscribed")

    def unsubscribe_instrument(self, alias: str) -> None:
        self.instruments.pop(alias, None)
        self.pending_indicator_requests = {
            request_id: pending
            for request_id, pending in self.pending_indicator_requests.items()
            if pending[0] != alias
        }
        self.pending_response_requests = {
            request_id: pending
            for request_id, pending in self.pending_response_requests.items()
            if pending[0] != alias
        }

    def on_response_data(self, addon: Any, req_id: int) -> None:
        del addon
        pending = self.pending_response_requests.get(req_id)
        if pending is None:
            print(f"Bookmap subscription confirmed for request {req_id}", flush=True)
            return
        alias, request_type = pending
        print(f"[{alias}] Bookmap subscription confirmed for {request_type} request {req_id}", flush=True)

    def on_indicator_response(self, addon: Any, *args: Any) -> None:
        # UNIVERSAL DIAGNOSTIC: Log EXACTLY what Bookmap bridge sends
        # and 'addon' are already positional arguments, so 'args' contains the rest.
        if len(args) == 2: # (request_id, indicator_id)
            request_id, indicator_id = args
        elif len(args) == 3: # (alias, request_id, indicator_id)
            alias, request_id, indicator_id = args
        else:
            write_runtime_probe(f"DIAGNOSTIC FACT: Unknown signature for on_indicator_response! Args: {args}")
            return
            
        pending = self.pending_indicator_requests.get(request_id)
        if pending is None:
            return
            
        alias_p, indicator_name = pending
        runtime = self.instruments.get(alias_p)
        if runtime is not None:
            if indicator_id == -1:
                write_runtime_probe(f"CRITICAL: indicator {indicator_name} for {alias_p} REFUSED by Bookmap")
            else:
                runtime.indicator_ids[indicator_name] = indicator_id
                write_runtime_probe(f"SUCCESS: indicator {indicator_name} for {alias_p} registered (id: {indicator_id})")

    def on_setting_change(self, addon: Any, alias: str, setting_name: str, field_type: str, new_value: Any) -> None:
        del addon, field_type
        runtime = self.instruments.get(alias)
        if runtime is None:
            return

        config = runtime.engine.config

        if setting_name == SETTING_ENABLE_POPUPS:
            runtime.bookmap_alert_popups_enabled = bool(new_value)
        elif setting_name == SETTING_NEAR_BOOK_TICKS:
            config.near_book_ticks = _parse_int_setting(new_value, 1, 50, config.near_book_ticks)
        elif setting_name == SETTING_FAST_WINDOW_SECONDS:
            config.fast_window_seconds = _parse_int_setting(new_value, 1, 300, config.fast_window_seconds)
        elif setting_name == SETTING_CONTEXT_WINDOW_MINUTES:
            config.context_window_seconds = _parse_int_setting(
                new_value,
                1,
                120,
                max(1, int(round(config.context_window_seconds / 60))),
            ) * 60
        elif setting_name == SETTING_PERSISTENCE_SECONDS:
            config.persistence_seconds = _parse_int_setting(new_value, 1, 300, config.persistence_seconds)
        elif setting_name == SETTING_RELOAD_SECONDS:
            config.reload_seconds = _parse_int_setting(new_value, 1, 300, config.reload_seconds)
        elif setting_name == SETTING_LARGE_LEVEL_FACTOR:
            config.large_level_factor = _parse_float_setting(new_value, 1.0, 10.0, config.large_level_factor)
        elif setting_name == SETTING_IMBALANCE_THRESHOLD:
            threshold = _parse_float_setting(new_value, 0.01, 0.95, abs(config.imbalance_support_threshold))
            config.imbalance_support_threshold = threshold
            config.imbalance_resistance_threshold = -threshold
        elif setting_name == SETTING_AGGRESSION_THRESHOLD:
            threshold = _parse_float_setting(new_value, 0.01, 0.95, abs(config.aggression_support_threshold))
            config.aggression_support_threshold = threshold
            config.aggression_resistance_threshold = -threshold
        elif setting_name == SETTING_LONG_BIAS_TIMEFRAME_MINUTES:
            runtime.long_bias_timeframe_minutes = _parse_int_setting(
                new_value,
                1,
                180,
                runtime.long_bias_timeframe_minutes,
            )
        elif setting_name == SETTING_SHORT_BIAS_TIMEFRAME_MINUTES:
            runtime.short_bias_timeframe_minutes = _parse_int_setting(
                new_value,
                1,
                180,
                runtime.short_bias_timeframe_minutes,
            )
        elif setting_name == SETTING_NET_BIAS_TIMEFRAME_MINUTES:
            runtime.net_bias_timeframe_minutes = _parse_int_setting(
                new_value,
                1,
                180,
                runtime.net_bias_timeframe_minutes,
            )
        elif setting_name == SETTING_TOP_BOOK_IMBALANCE_TIMEFRAME_MINUTES:
            runtime.top_book_imbalance_timeframe_minutes = _parse_int_setting(
                new_value,
                1,
                180,
                runtime.top_book_imbalance_timeframe_minutes,
            )
        else:
            return

        write_runtime_probe(
            f"setting changed {alias} {setting_name}={new_value}"
        )
        
        # Force an immediate UI update so the user sees the change in the subchart
        self._update_indicators(runtime)

    def on_depth(self, addon: Any, alias: str, is_bid: bool, price: float, size: float) -> None:
        runtime = self.instruments.get(alias)
        if runtime is None:
            return

        # Calculate the integer price level (ticks) correctly
        price_level = int(round(price / runtime.pips))

        # Update the native Bookmap order book so get_bbo/get_bbos works
        # CRITICAL: Native Bookmap API expects price_level (ticks), NOT float price.
        bm.on_depth(runtime.order_book, is_bid, price_level, size)
        
        # Periodic debugging log (sampled even less in Lite Mode)
        self.callback_counts["depth"] += 1
        if self.callback_counts["depth"] % 50000 == 0:
            write_runtime_probe(f"[{alias}] on_depth sample {self.callback_counts['depth']}: ticks={price_level} size={size} is_bid={is_bid}")
        
        # [NEW LITE MODE] Depth Decimation: Skip processing updates far from BBO
        # This saves massive CPU by ignoring depth changes at levels the price won't hit soon.
        best_bid, best_ask = self._get_bbo_levels(runtime)
        if best_bid is not None and best_ask is not None:
            # Check if price is within 'near_book_ticks' range (default 100-200)
            mid = (best_bid + best_ask) // 2
            if abs(price_level - mid) > runtime.engine.config.near_book_ticks:
                # Still update the internal Bookmap book so Heatmap looks okay
                # but skip our expensive signal engine processing
                return

        # Update our local tracking map for fallback BBO calculation
        side_key = "bid" if is_bid else "ask"
        if size > 0:
            runtime.current_sizes[side_key][price_level] = size
        else:
            runtime.current_sizes[side_key].pop(price_level, None)

        # Get current BBO to include in the depth event
        best_bid_level, best_ask_level = self._get_bbo_levels(runtime)

        event = NormalizedBookmapEvent(
            event_type="depth_add" if size > 0 else "depth_remove",
            instrument=alias,
            timestamp_ns=self._now_ns(),
            price_level=price_level,
            price=price,
            size=size,
            side=side_key,
            best_bid_level=best_bid_level,
            best_ask_level=best_ask_level
        )
        result = runtime.engine.process_event(event)

        if result.alerts:
            for alert in result.alerts:
                self._handle_alert(alert)

        if result.snapshot is not None:
            self._update_indicators_throttled(runtime, result)

    def on_trade(self, addon: Any, alias: str, price: float, size: float, *args: Any) -> None:
        runtime = self.instruments.get(alias)
        if runtime is None:
            return

        # Optimization: Filter out 'dust' trades to reduce processing load
        if size < 0.01:
            return

        # Bookmap usually provides the side in args[1]
        # 1 = Buy (Aggressive Buyer), 2 = Sell (Aggressive Seller)
        side = "trade"
        if len(args) > 1:
            side_val = args[1]
            if side_val == 1:
                side = "buy"
            elif side_val == 2:
                side = "sell"

        # Calculate integer price level for trades
        price_level = int(round(price / runtime.pips))

        # Get current BBO to include in the trade event
        best_bid_level, best_ask_level = self._get_bbo_levels(runtime)

        result = runtime.engine.process_event(
            NormalizedBookmapEvent(
                event_type="trade_buy_aggressor" if side == "buy" else ("trade_sell_aggressor" if side == "sell" else "trade"),
                instrument=alias,
                timestamp_ns=self._now_ns(),
                price=price,
                price_level=price_level,
                size=size,
                side=side,
                best_bid_level=best_bid_level,
                best_ask_level=best_ask_level
            )
        )
        
        if result.alerts:
            for alert in result.alerts:
                self._handle_alert(alert)

        self._update_indicators_throttled(runtime, result)

    def on_interval(self, addon: Any, alias: str) -> None:
        del addon
        runtime = self.instruments.get(alias)
        if runtime is None:
            return

        self.callback_counts["interval"] += 1
        if self.callback_counts["interval"] % 50 == 0:
            write_runtime_probe(f"on_interval {alias} (count: {self.callback_counts['interval']})")
        
        best_bid_level, best_ask_level = self._get_bbo_levels(runtime)
        if self.callback_counts["interval"] % 50 == 0:
            write_runtime_probe(f"interval bbo {alias} bid={best_bid_level} ask={best_ask_level}")
        event = NormalizedBookmapEvent(
            timestamp_ns=self._now_ns(),
            instrument=alias,
            event_type="clock",
            best_bid_level=best_bid_level,
            best_ask_level=best_ask_level,
        )
        result = self._process_event(runtime, event)
        if result.alerts:
            for alert in result.alerts:
                self._handle_alert(alert)
        if result.snapshot is not None:
            self._update_indicators_throttled(runtime, result)

    def _handle_alert(self, alert: AlertRecord) -> None:
        # Priority 1 (Standard) and Priority 5 (POI/Absorption) are shown to the user
        if alert.priority in {1, 5}:
            if alert.priority == 5:
                # Big bold message in the technical logs for the AI/User
                print(f"\n[!!! POI DETECTED !!!] {alert.message} | Price: {alert.price}\n", flush=True)
            
            self.console_sink.emit(alert)
            self.jsonl_sink.emit(alert)
        
        if alert.priority in {1, 5} and bm is not None:
            # Special prefix for extreme priority alerts in Bookmap message log
            prefix = "🔥 POI: " if alert.priority == 5 else ""
            bm.send_user_message(self.addon, alert.instrument, f"{prefix}{alert.message}")

    def _process_event(self, runtime: InstrumentRuntime, event: NormalizedBookmapEvent):
        # This was redundant since on_depth/on_trade handle their own engine calls now
        return runtime.engine.process_event(event)

    def _register_indicators(self, alias: str) -> None:
        runtime = self.instruments[alias]
        
        # Guard: If all indicators are registered, do nothing
        if len(runtime.indicator_ids) >= 4:
            return
            
        long_bias_request_id = self._next_request_id()
        short_bias_request_id = self._next_request_id()
        imbalance_request_id = self._next_request_id()
        net_bias_request_id = self._next_request_id()

        runtime.request_ids["long_bias_indicator"] = long_bias_request_id
        runtime.request_ids["short_bias_indicator"] = short_bias_request_id
        runtime.request_ids["top_book_imbalance_indicator"] = imbalance_request_id
        runtime.request_ids["net_bias_indicator"] = net_bias_request_id

        self.pending_indicator_requests[long_bias_request_id] = (alias, "long_bias")
        self.pending_indicator_requests[short_bias_request_id] = (alias, "short_bias")
        self.pending_indicator_requests[imbalance_request_id] = (alias, "top_book_imbalance")
        self.pending_indicator_requests[net_bias_request_id] = (alias, "net_bias")

        # CRITICAL PROTOCOL HARDENING:
        # 1. Location strings MUST be "bottom", "top", or "primary" (lowercase).
        # 2. Line style MUST be "solid", "dashed", or "dot" (lowercase).
        # 3. Colors must be tuples of 3 integers.
        # 4. request_id must be a unique integer.
        
        write_runtime_probe(f"REGISTERING indicators for {alias}... (Req: {long_bias_request_id}-{net_bias_request_id})")

        bm.register_indicator(
            self.addon,
            alias,
            long_bias_request_id,
            f"Long Bias ({runtime.long_bias_timeframe_minutes}m)",
            "BOTTOM",
            color=runtime.indicator_colors["long_bias"],
            is_modifiable=True,
        )
        bm.register_indicator(
            self.addon,
            alias,
            short_bias_request_id,
            f"Short Bias ({runtime.short_bias_timeframe_minutes}m)",
            "BOTTOM",
            color=runtime.indicator_colors["short_bias"],
            is_modifiable=True,
        )
        bm.register_indicator(
            self.addon,
            alias,
            imbalance_request_id,
            f"Imbalance ({runtime.top_book_imbalance_timeframe_minutes}m)",
            "BOTTOM",
            color=runtime.indicator_colors["top_book_imbalance"],
            is_modifiable=True,
        )
        bm.register_indicator(
            self.addon,
            alias,
            net_bias_request_id,
            f"Net Bias ({runtime.net_bias_timeframe_minutes}m)",
            "BOTTOM",
            color=runtime.indicator_colors["net_bias"],
            is_modifiable=True,
        )

    def _register_settings(self, alias: str) -> None:
        runtime = self.instruments.get(alias)
        if runtime is None:
            return

        # Use bm.add_number_settings_parameter(addon, alias, name, default, min, max, step)
        # and bm.add_boolean_settings_parameter(addon, alias, name, default)
        # These must be called during subscribe_instrument, not deferred.
        try:
            bm.add_boolean_settings_parameter(
                self.addon, alias, SETTING_ENABLE_POPUPS,
                runtime.bookmap_alert_popups_enabled,
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_NEAR_BOOK_TICKS,
                str(int(runtime.engine.config.near_book_ticks)),
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_FAST_WINDOW_SECONDS,
                str(int(runtime.engine.config.fast_window_seconds)),
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_CONTEXT_WINDOW_MINUTES,
                str(int(round(runtime.engine.config.context_window_seconds / 60))),
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_PERSISTENCE_SECONDS,
                str(int(runtime.engine.config.persistence_seconds)),
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_RELOAD_SECONDS,
                str(int(runtime.engine.config.reload_seconds)),
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_LARGE_LEVEL_FACTOR,
                str(float(runtime.engine.config.large_level_factor)),
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_IMBALANCE_THRESHOLD,
                str(float(abs(runtime.engine.config.imbalance_support_threshold))),
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_AGGRESSION_THRESHOLD,
                str(float(abs(runtime.engine.config.aggression_support_threshold))),
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_LONG_BIAS_TIMEFRAME_MINUTES,
                str(int(runtime.long_bias_timeframe_minutes)),
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_SHORT_BIAS_TIMEFRAME_MINUTES,
                str(int(runtime.short_bias_timeframe_minutes)),
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_NET_BIAS_TIMEFRAME_MINUTES,
                str(int(runtime.net_bias_timeframe_minutes)),
            )
            _add_string_setting_parameter(
                self.addon, alias, SETTING_TOP_BOOK_IMBALANCE_TIMEFRAME_MINUTES,
                str(int(runtime.top_book_imbalance_timeframe_minutes)),
            )
        except Exception as exc:
            print(f"[CRYPTO] settings registration failed for {alias}: {exc}", flush=True)


    def _preload_snapshot_history(self, runtime: InstrumentRuntime) -> None:
        history_path = self.state_sink.history_path
        if not history_path.exists():
            return

        try:
            matching_payloads: List[Dict[str, Any]] = []
            with history_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        payload = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("instrument") != runtime.alias:
                        continue
                    if payload.get("heartbeat"):
                        continue
                    if "features" not in payload or "market_state" not in payload:
                        continue
                    matching_payloads.append(payload)
        except OSError:
            return

        if not matching_payloads:
            return

        latest_timestamp_ns = max(int(payload.get("timestamp_ns", 0) or 0) for payload in matching_payloads)
        if latest_timestamp_ns <= 0:
            return

        max_window_minutes = 180
        cutoff_ns = latest_timestamp_ns - (max_window_minutes * 60 * 1_000_000_000)
        restored_count = 0
        for payload in matching_payloads:
            timestamp_ns = int(payload.get("timestamp_ns", 0) or 0)
            if timestamp_ns < cutoff_ns:
                continue
            snapshot = self._snapshot_from_history_payload(runtime.alias, payload)
            if snapshot is None:
                continue
            runtime.engine.session.add_snapshot(snapshot)
            restored_count += 1

        if restored_count == 0:
            return

        latest_snapshot = runtime.engine.session.recent_feature_snapshots[-1]
        runtime.engine.session.best_bid_level = latest_snapshot.best_bid_level
        runtime.engine.session.best_ask_level = latest_snapshot.best_ask_level
        runtime.smoothed_indicator_values["top_book_imbalance"] = latest_snapshot.top_book_imbalance
        write_runtime_probe(
            f"preloaded {restored_count} history snapshots for {runtime.alias} from {history_path}"
        )

    def _snapshot_from_history_payload(self, alias: str, payload: Dict[str, Any]) -> Optional[Any]:
        try:
            from bookmap_signal_models import FeatureSnapshot

            market_state = payload.get("market_state", {})
            features = payload.get("features", {})
            return FeatureSnapshot(
                timestamp_ns=int(payload.get("timestamp_ns", 0) or 0),
                instrument=alias,
                best_bid_level=market_state.get("best_bid_level"),
                best_ask_level=market_state.get("best_ask_level"),
                mid_level=market_state.get("mid_level"),
                top_book_imbalance=float(features.get("top_book_imbalance", 0.0) or 0.0),
                bid_stack_rate=float(features.get("bid_stack_rate", 0.0) or 0.0),
                ask_stack_rate=float(features.get("ask_stack_rate", 0.0) or 0.0),
                bid_pull_rate=float(features.get("bid_pull_rate", 0.0) or 0.0),
                ask_pull_rate=float(features.get("ask_pull_rate", 0.0) or 0.0),
                buy_aggressive_volume=float(features.get("buy_aggressive_volume", 0.0) or 0.0),
                sell_aggressive_volume=float(features.get("sell_aggressive_volume", 0.0) or 0.0),
                aggression_delta=float(features.get("aggression_delta", 0.0) or 0.0),
                aggression_ratio=float(features.get("aggression_ratio", 0.0) or 0.0),
                long_bid_stack_rate=float(features.get("long_bid_stack_rate", 0.0) or 0.0),
                long_ask_stack_rate=float(features.get("long_ask_stack_rate", 0.0) or 0.0),
                long_bid_pull_rate=float(features.get("long_bid_pull_rate", 0.0) or 0.0),
                long_ask_pull_rate=float(features.get("long_ask_pull_rate", 0.0) or 0.0),
                long_buy_aggressive_volume=float(features.get("long_buy_aggressive_volume", 0.0) or 0.0),
                long_sell_aggressive_volume=float(features.get("long_sell_aggressive_volume", 0.0) or 0.0),
                long_aggression_delta=float(features.get("long_aggression_delta", 0.0) or 0.0),
                long_aggression_ratio=float(features.get("long_aggression_ratio", 0.0) or 0.0),
            )
        except (TypeError, ValueError):
            return None

    def _background_writer(self) -> None:
        """Drain the write queue on a private thread so callbacks never block."""
        while True:
            try:
                fn, args = self._write_queue.get(timeout=5)
                try:
                    fn(*args)
                except Exception as exc:
                    print(f"[BM-Writer] error: {exc}", flush=True)
            except queue.Empty:
                continue

    def _enqueue_write(self, fn, *args) -> None:
        """Non-blocking enqueue; drop the item if the queue is full."""
        try:
            self._write_queue.put_nowait((fn, args))
        except queue.Full:
            pass  # Never block the Bookmap thread

    def _update_indicators_throttled(self, runtime: InstrumentRuntime, result: EngineStepResult) -> None:
        now = time.time()
        # Increased to 1.0s to reduce UI thread load
        if now - runtime.last_ui_update_time < 1.0:
            return
        runtime.last_ui_update_time = now
        self._update_indicators(runtime)  # RPC call – fast, stays on this thread

        # Disk writes go to the background thread (Reduced to 2.0s as approved)
        if now - self.last_snapshot_time > 2.0:
            self.last_snapshot_time = now
            if result is not None and result.snapshot is not None:
                self._enqueue_write(self._emit_state_snapshot, runtime, result)
            else:
                self._enqueue_write(self._emit_heartbeat_snapshot, runtime, "throttled heartbeat")

    def _update_indicators(self, runtime: InstrumentRuntime) -> None:
        signals = runtime.engine.session.current_signals
        long_indicator_id = runtime.indicator_ids.get("long_bias")
        short_indicator_id = runtime.indicator_ids.get("short_bias")
        imbalance_indicator_id = runtime.indicator_ids.get("top_book_imbalance")
        net_bias_indicator_id = runtime.indicator_ids.get("net_bias")
        snapshot = runtime.engine.session.recent_feature_snapshots[-1] if runtime.engine.session.recent_feature_snapshots else None
        if long_indicator_id is not None:
            long_bias_display = self._windowed_bias_strength(runtime, runtime.long_bias_timeframe_minutes, "long")
            bm.add_point(self.addon, runtime.alias, long_indicator_id, long_bias_display)
        if short_indicator_id is not None:
            short_bias_display = self._windowed_bias_strength(runtime, runtime.short_bias_timeframe_minutes, "short")
            bm.add_point(self.addon, runtime.alias, short_indicator_id, short_bias_display)
        if imbalance_indicator_id is not None and snapshot is not None:
            imbalance_display = self._windowed_top_book_imbalance(
                runtime,
                runtime.top_book_imbalance_timeframe_minutes,
            )
            smoothed_imbalance = self._smooth_display_value(
                runtime,
                "top_book_imbalance",
                imbalance_display,
                DISPLAY_SMOOTHING_ALPHA_IMBALANCE,
            )
            bm.add_point(self.addon, runtime.alias, imbalance_indicator_id, smoothed_imbalance)
        if net_bias_indicator_id is not None:
            net_bias_display = self._windowed_net_bias(runtime, runtime.net_bias_timeframe_minutes)
            bm.add_point(self.addon, runtime.alias, net_bias_indicator_id, net_bias_display)
            # Add a zero line reference for the net bias oscillation
            # This helps the user see if they are actually crossing zero in the subchart
            bm.add_point(self.addon, runtime.alias, net_bias_indicator_id, 0.0)

    def _windowed_bias_strength(self, runtime: InstrumentRuntime, minutes: int, direction: str) -> float:
        if direction == "long":
            return max(0.0, min(10.0, self._average_buyer_pressure(runtime, minutes) * 10.0))
        return max(0.0, min(10.0, self._average_seller_pressure(runtime, minutes) * 10.0))

    def _windowed_net_bias(self, runtime: InstrumentRuntime, minutes: int) -> float:
        return max(-10.0, min(10.0, self._average_directional_pressure(runtime, minutes) * 10.0))

    def _windowed_top_book_imbalance(self, runtime: InstrumentRuntime, minutes: int) -> float:
        snapshots = self._snapshots_in_window(runtime, minutes)
        if not snapshots:
            return 0.0
        total_imbalance = 0.0
        for snapshot in snapshots:
            total_imbalance += snapshot.top_book_imbalance
        return total_imbalance / len(snapshots)

    def _average_directional_pressure(self, runtime: InstrumentRuntime, minutes: int) -> float:
        snapshots = self._snapshots_in_window(runtime, minutes)
        if not snapshots:
            return 0.0
        total_pressure = 0.0
        for snapshot in snapshots:
            total_pressure += self._snapshot_directional_pressure(snapshot)
        return total_pressure / len(snapshots)

    def _average_buyer_pressure(self, runtime: InstrumentRuntime, minutes: int) -> float:
        snapshots = self._snapshots_in_window(runtime, minutes)
        if not snapshots:
            return 0.0
        total_pressure = 0.0
        for snapshot in snapshots:
            total_pressure += self._snapshot_buyer_pressure(snapshot)
        return total_pressure / len(snapshots)

    def _average_seller_pressure(self, runtime: InstrumentRuntime, minutes: int) -> float:
        snapshots = self._snapshots_in_window(runtime, minutes)
        if not snapshots:
            return 0.0
        total_pressure = 0.0
        for snapshot in snapshots:
            total_pressure += self._snapshot_seller_pressure(snapshot)
        return total_pressure / len(snapshots)

    def _snapshots_in_window(self, runtime: InstrumentRuntime, minutes: int) -> List[Any]:
        if not runtime.engine.session.recent_feature_snapshots:
            return []
        latest_timestamp_ns = runtime.engine.session.recent_feature_snapshots[-1].timestamp_ns
        cutoff_ns = latest_timestamp_ns - (max(1, minutes) * 60 * 1_000_000_000)
        return [
            snapshot
            for snapshot in runtime.engine.session.recent_feature_snapshots
            if snapshot.timestamp_ns >= cutoff_ns
        ]

    def _snapshot_directional_pressure(self, snapshot: Any) -> float:
        pressure = self._snapshot_buyer_pressure(snapshot) - self._snapshot_seller_pressure(snapshot)
        return max(-1.0, min(1.0, pressure))

    def _snapshot_buyer_pressure(self, snapshot: Any) -> float:
        book_component = max(0.0, snapshot.top_book_imbalance)
        aggression_component = max(0.0, snapshot.aggression_ratio)
        stack_component = max(0.0, self._rate_balance(snapshot.bid_stack_rate, snapshot.ask_stack_rate))
        pull_component = max(0.0, self._rate_balance(snapshot.ask_pull_rate, snapshot.bid_pull_rate))
        pressure = (
            (book_component * 0.35)
            + (aggression_component * 0.35)
            + (stack_component * 0.15)
            + (pull_component * 0.15)
        )
        return max(0.0, min(1.0, pressure))

    def _snapshot_seller_pressure(self, snapshot: Any) -> float:
        book_component = max(0.0, -snapshot.top_book_imbalance)
        aggression_component = max(0.0, -snapshot.aggression_ratio)
        stack_component = max(0.0, self._rate_balance(snapshot.ask_stack_rate, snapshot.bid_stack_rate))
        pull_component = max(0.0, self._rate_balance(snapshot.bid_pull_rate, snapshot.ask_pull_rate))
        pressure = (
            (book_component * 0.35)
            + (aggression_component * 0.35)
            + (stack_component * 0.15)
            + (pull_component * 0.15)
        )
        return max(0.0, min(1.0, pressure))

    def _rate_balance(self, positive_rate: float, negative_rate: float) -> float:
        total = positive_rate + negative_rate
        if total <= 0.0:
            return 0.0
        return (positive_rate - negative_rate) / total

    def _smooth_display_value(self, runtime: InstrumentRuntime, key: str, raw_value: float, alpha: float) -> float:
        previous_value = runtime.smoothed_indicator_values.get(key)
        if previous_value is None:
            smoothed_value = raw_value
        else:
            smoothed_value = (alpha * raw_value) + ((1.0 - alpha) * previous_value)
        runtime.smoothed_indicator_values[key] = smoothed_value
        return smoothed_value

    def _emit_state_snapshot(self, runtime: InstrumentRuntime, result: Any) -> None:
        snapshot = result.snapshot
        if snapshot is None:
            return

        active_levels = list(runtime.engine.session.active_levels_by_price.values())
        strongest_support = self._best_level_for_export(active_levels, "bid")
        strongest_resistance = self._best_level_for_export(active_levels, "ask")

        recent_alerts = [
            {
                "timestamp_ns": alert.timestamp_ns,
                "alert_type": alert.alert_type,
                "priority": alert.priority,
                "message": alert.message,
                "price": alert.price,
                "side": alert.side,
                "reason_codes": alert.reason_codes,
            }
            for alert in list(runtime.engine.session.recent_alerts)[-10:]
        ]

        payload = {
            "timestamp_ns": snapshot.timestamp_ns,
            "instrument": runtime.alias,
            "market_state": {
                "best_bid_level": snapshot.best_bid_level,
                "best_ask_level": snapshot.best_ask_level,
                "mid_level": snapshot.mid_level,
                "best_bid_price": None if snapshot.best_bid_level is None else snapshot.best_bid_level * runtime.pips,
                "best_ask_price": None if snapshot.best_ask_level is None else snapshot.best_ask_level * runtime.pips,
            },
            "features": {
                "top_book_imbalance": snapshot.top_book_imbalance,
                "bid_stack_rate": snapshot.bid_stack_rate,
                "ask_stack_rate": snapshot.ask_stack_rate,
                "bid_pull_rate": snapshot.bid_pull_rate,
                "ask_pull_rate": snapshot.ask_pull_rate,
                "buy_aggressive_volume": snapshot.buy_aggressive_volume,
                "sell_aggressive_volume": snapshot.sell_aggressive_volume,
                "aggression_delta": snapshot.aggression_delta,
                "aggression_ratio": snapshot.aggression_ratio,
                "long_bid_stack_rate": snapshot.long_bid_stack_rate,
                "long_ask_stack_rate": snapshot.long_ask_stack_rate,
                "long_bid_pull_rate": snapshot.long_bid_pull_rate,
                "long_ask_pull_rate": snapshot.long_ask_pull_rate,
                "long_buy_aggressive_volume": snapshot.long_buy_aggressive_volume,
                "long_sell_aggressive_volume": snapshot.long_sell_aggressive_volume,
                "long_aggression_delta": snapshot.long_aggression_delta,
                "long_aggression_ratio": snapshot.long_aggression_ratio,
            },
            "display_metrics": {
                "long_bias_timeframe_minutes": runtime.long_bias_timeframe_minutes,
                "short_bias_timeframe_minutes": runtime.short_bias_timeframe_minutes,
                "net_bias_timeframe_minutes": runtime.net_bias_timeframe_minutes,
                "top_book_imbalance_timeframe_minutes": runtime.top_book_imbalance_timeframe_minutes,
                "display_long_bias": self._windowed_bias_strength(runtime, runtime.long_bias_timeframe_minutes, "long"),
                "display_short_bias": self._windowed_bias_strength(runtime, runtime.short_bias_timeframe_minutes, "short"),
                "display_net_bias": self._windowed_net_bias(runtime, runtime.net_bias_timeframe_minutes),
                "display_top_book_imbalance": self._windowed_top_book_imbalance(
                    runtime,
                    runtime.top_book_imbalance_timeframe_minutes,
                ),
            },
            "signals": {
                name: {
                    "score_0_to_10": signal.score_0_to_10,
                    "confidence_0_to_1": signal.confidence_0_to_1,
                    "direction": signal.direction,
                    "reason_codes": signal.reason_codes,
                    "summary": signal.summary,
                }
                for name, signal in result.signals.items()
            },
            "levels": {
                "strongest_support": self._serialize_level(strongest_support),
                "strongest_resistance": self._serialize_level(strongest_resistance),
                "active_supports": [
                    self._serialize_level(level)
                    for level in active_levels
                    if level.side == "bid"
                ],
                "active_resistances": [
                    self._serialize_level(level)
                    for level in active_levels
                    if level.side == "ask"
                ],
            },
            "recent_alerts": recent_alerts,
            "ai_summary_prompt_fields": {
                "what_is_building": self._what_is_building(
                    result.signals,
                    strongest_support,
                    strongest_resistance,
                    recent_alerts,
                ),
                "bias_state": self._bias_state(result.signals),
                "top_reasons": self._top_reasons(result.signals),
            },
        }
        self.state_sink.emit(runtime.alias, payload)

    def _emit_heartbeat_snapshot(self, runtime: InstrumentRuntime, note: str) -> None:
        payload = {
            "timestamp_ns": self._now_ns(),
            "instrument": runtime.alias,
            "heartbeat": True,
            "note": note,
            "market_state": {
                "best_bid_level": runtime.engine.session.best_bid_level,
                "best_ask_level": runtime.engine.session.best_ask_level,
            },
            "features": {},
            "signals": {},
            "levels": {
                "strongest_support": None,
                "strongest_resistance": None,
                "active_supports": [],
                "active_resistances": [],
            },
            "recent_alerts": [],
            "ai_summary_prompt_fields": {
                "what_is_building": "No dominant level build detected",
                "bias_state": "Mixed",
                "top_reasons": [],
            },
        }
        self.state_sink.emit(runtime.alias, payload)

    def _serialize_level(self, level: Optional[TrackedLevel]) -> Optional[Dict[str, Any]]:
        if level is None:
            return None
        return {
            "level_id": level.level_id,
            "side": level.side,
            "price_level": level.price_level,
            "price": level.price,
            "status": level.status,
            "strength_tier": level.strength_tier,
            "current_size": level.current_size,
            "max_seen_size": level.max_seen_size,
            "times_reloaded": level.times_reloaded,
            "times_tested": level.times_tested,
            "times_fully_pulled": level.times_fully_pulled,
            "persistence_score": level.persistence_score,
            "context_correlation_score": level.context_correlation_score,
            "confidence_score": level.confidence_score,
            "reason_codes": level.reason_codes,
        }

    def _best_level_for_export(self, levels: List[TrackedLevel], side: str) -> Optional[TrackedLevel]:
        candidates = [level for level in levels if level.side == side]
        if not candidates:
            return None
        return max(candidates, key=lambda level: (level.confidence_score, level.max_seen_size, level.persistence_score))

    def _what_is_building(
        self,
        signals: Dict[str, Any],
        strongest_support: Optional[TrackedLevel],
        strongest_resistance: Optional[TrackedLevel],
        recent_alerts: List[Dict[str, Any]],
    ) -> str:
        recent_alert_types = {alert["alert_type"] for alert in recent_alerts}
        support_active = (
            (
                signals.get("support_building")
                and signals["support_building"].score_0_to_10 > 0
            )
            or "support_building" in recent_alert_types
            or "support_reloaded" in recent_alert_types
            or (
                strongest_support is not None
                and strongest_support.status == "developing"
            )
        )
        resistance_active = (
            (
                signals.get("resistance_building")
                and signals["resistance_building"].score_0_to_10 > 0
            )
            or "resistance_building" in recent_alert_types
            or "resistance_reloaded" in recent_alert_types
            or (
                strongest_resistance is not None
                and strongest_resistance.status == "developing"
            )
        )

        if support_active and resistance_active and strongest_support and strongest_resistance:
            return f"Support near {strongest_support.price:.4f}; resistance near {strongest_resistance.price:.4f}"
        if support_active and strongest_support:
            return f"Support building near {strongest_support.price:.4f}"
        if resistance_active and strongest_resistance:
            return f"Resistance building near {strongest_resistance.price:.4f}"
        return "No dominant level build detected"

    def _bias_state(self, signals: Dict[str, Any]) -> str:
        long_bias = signals.get("long_bias")
        short_bias = signals.get("short_bias")
        if long_bias and short_bias:
            if long_bias.score_0_to_10 >= short_bias.score_0_to_10 and long_bias.score_0_to_10 >= 6.0:
                return "Long bias dominant"
            if short_bias.score_0_to_10 > long_bias.score_0_to_10 and short_bias.score_0_to_10 >= 6.0:
                return "Short bias dominant"
        if signals.get("stand_aside") and signals["stand_aside"].score_0_to_10 > 0:
            return "Stand aside"
        return "Mixed"

    def _top_reasons(self, signals: Dict[str, Any]) -> List[str]:
        ordered: List[str] = []
        for key in ("long_bias", "short_bias", "support_building", "resistance_building"):
            signal = signals.get(key)
            if signal is None:
                continue
            for reason in signal.reason_codes:
                if reason not in ordered:
                    ordered.append(reason)
        return ordered[:5]

    def _get_bbo_levels(self, runtime: InstrumentRuntime) -> tuple[Optional[int], Optional[int]]:
        best_bid_level: Optional[int] = None
        best_ask_level: Optional[int] = None

        # Redundancy 1: Native Bookmap Object (most accurate)
        try:
            bbo = bm.get_bbo(runtime.order_book)
            if bbo and bbo[0] and bbo[0][0] is not None:
                best_bid_level = int(bbo[0][0])
            if bbo and bbo[1] and bbo[1][0] is not None:
                best_ask_level = int(bbo[1][0])
        except Exception:
            pass

        # Redundancy 2: Fallback to the get_bbos legacy call
        if best_bid_level is None or best_ask_level is None:
            try:
                bbos = bm.get_bbos(runtime.order_book)
                if bbos and bbos[0]: best_bid_level = int(bbos[0][0])
                if bbos and bbos[1]: best_ask_level = int(bbos[1][0])
            except Exception:
                pass

        # Redundancy 3: Our local tracking map (manual fallback)
        if best_bid_level is None:
            bid_levels = [int(level) for level, size in runtime.current_sizes["bid"].items() if size > 0]
            best_bid_level = max(bid_levels) if bid_levels else None
        if best_ask_level is None:
            ask_levels = [int(level) for level, size in runtime.current_sizes["ask"].items() if size > 0]
            best_ask_level = min(ask_levels) if ask_levels else None

        return best_bid_level, best_ask_level

    def _now_ns(self) -> int:
        # Bookmap timestamps aren't exposed by Python depth callbacks, so V1 uses local wall-clock ns.
        import time

        return time.time_ns()

    def _next_request_id(self) -> int:
        self._next_request_id_value += 1
        return self._next_request_id_value


def write_runtime_probe(message: str) -> None:
    probe_path = Path(r"C:\Bookmap\runs\adapter_runtime_probe.txt")
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    with probe_path.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


RUNTIME: Optional[BookmapAddonRuntime] = None


def handle_subscribe_instrument(
    addon: Any,
    alias: str,
    full_name: str,
    is_crypto: bool,
    pips: float,
    size_multiplier: float,
    instrument_multiplier: float,
    supported_features: Dict[str, object],
) -> None:
    assert RUNTIME is not None
    RUNTIME.subscribe_instrument(
        alias,
        full_name,
        is_crypto,
        pips,
        size_multiplier,
        instrument_multiplier,
        supported_features,
    )


def handle_unsubscribe_instrument(addon: Any, alias: str) -> None:
    del addon
    assert RUNTIME is not None
    RUNTIME.unsubscribe_instrument(alias)


def main(
    alert_path: str = "runs/bookmap_alerts.jsonl",
    snapshot_dir: str = "runs/bookmap_snapshots",
    snapshot_history_path: str = "runs/bookmap_snapshots_history.jsonl",
) -> None:
    write_runtime_probe("main entered")
    global RUNTIME
    if bm is None:
        write_runtime_probe("bm import missing")
        raise RuntimeError("Bookmap Python API library is not available in this environment.")

    addon = bm.create_addon()
    write_runtime_probe("addon created")
    RUNTIME = BookmapAddonRuntime(
        addon,
        alert_path=alert_path,
        snapshot_dir=snapshot_dir,
        snapshot_history_path=snapshot_history_path,
    )
    write_runtime_probe("runtime created")

    bm.add_depth_handler(addon, RUNTIME.on_depth)
    write_runtime_probe("depth handler added")
    bm.add_trades_handler(addon, RUNTIME.on_trade)
    write_runtime_probe("trade handler added")
    bm.add_on_interval_handler(addon, RUNTIME.on_interval)
    write_runtime_probe("interval handler added")
    bm.add_indicator_response_handler(addon, RUNTIME.on_indicator_response)
    write_runtime_probe("indicator handler added")
    bm.add_on_setting_change_handler(addon, RUNTIME.on_setting_change)
    write_runtime_probe("settings handler added")

    if hasattr(bm, "add_response_data_handler"):
        bm.add_response_data_handler(addon, RUNTIME.on_response_data)
        write_runtime_probe("response data handler added")
    elif hasattr(bm, "on_response_data_handler"):
        bm.on_response_data_handler(addon, RUNTIME.on_response_data)
        write_runtime_probe("legacy response data handler added")

    write_runtime_probe("starting addon")
    bm.start_addon(addon, handle_subscribe_instrument, handle_unsubscribe_instrument)
    write_runtime_probe("addon started")
    bm.wait_until_addon_is_turned_off(addon)


if __name__ == "__main__":
    main()
