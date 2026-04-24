#!/usr/bin/env python3
"""Core data structures for the Bookmap signal engine."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple


@dataclass(slots=True)
class EngineConfig:
    instrument: str
    pips: float
    size_multiplier: float
    near_book_ticks: int = 200
    fast_window_seconds: int = 90
    context_window_seconds: int = 900
    new_level_cooldown_seconds: int = 60
    persistence_seconds: int = 60
    reload_seconds: int = 25
    rebuild_ratio: float = 0.80
    pull_ratio: float = 0.70
    large_level_factor: float = 2.0
    imbalance_support_threshold: float = 0.20
    imbalance_resistance_threshold: float = -0.20
    aggression_support_threshold: float = 0.15
    aggression_resistance_threshold: float = -0.15
    top_n_levels: int = 10


@dataclass(slots=True)
class NormalizedBookmapEvent:
    timestamp_ns: int
    instrument: str
    event_type: str
    side: Optional[str] = None
    price_level: Optional[int] = None
    size_level: Optional[int] = None
    price: Optional[float] = None
    size: Optional[float] = None
    best_bid_level: Optional[int] = None
    best_ask_level: Optional[int] = None
    distance_ticks_from_best: Optional[int] = None
    is_aggressive: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrackedLevel:
    level_id: str
    instrument: str
    side: str
    price_level: int
    price: float
    status: str = "new"
    strength_tier: str = "notable"
    first_seen_ns: int = 0
    last_seen_ns: int = 0
    last_trade_touch_ns: Optional[int] = None
    last_rebuild_ns: Optional[int] = None
    max_seen_size: float = 0.0
    current_size: float = 0.0
    distance_ticks_from_market: Optional[int] = None
    times_reloaded: int = 0
    times_partially_hit: int = 0
    times_fully_pulled: int = 0
    times_tested: int = 0
    trade_volume_near_level: float = 0.0
    buy_aggressive_volume_near_level: float = 0.0
    sell_aggressive_volume_near_level: float = 0.0
    absorption_score: float = 0.0
    is_poi: bool = False
    persistence_score: float = 0.0
    context_correlation_score: float = 0.0
    confidence_score: float = 0.0
    reason_codes: List[str] = field(default_factory=list)

    def age_seconds(self, now_ns: int) -> float:
        return max(0.0, (now_ns - self.first_seen_ns) / 1_000_000_000)

    def was_recently_seen(self, now_ns: int, max_age_seconds: int) -> bool:
        return (now_ns - self.last_seen_ns) <= max_age_seconds * 1_000_000_000


@dataclass(slots=True)
class FeatureSnapshot:
    timestamp_ns: int
    instrument: str
    best_bid_level: Optional[int] = None
    best_ask_level: Optional[int] = None
    mid_level: Optional[float] = None
    bid_sum_top_n: float = 0.0
    ask_sum_top_n: float = 0.0
    top_book_imbalance: float = 0.0
    bid_stack_rate: float = 0.0
    ask_stack_rate: float = 0.0
    bid_pull_rate: float = 0.0
    ask_pull_rate: float = 0.0
    buy_aggressive_volume: float = 0.0
    sell_aggressive_volume: float = 0.0
    aggression_delta: float = 0.0
    aggression_ratio: float = 0.0
    long_bid_stack_rate: float = 0.0
    long_ask_stack_rate: float = 0.0
    long_bid_pull_rate: float = 0.0
    long_ask_pull_rate: float = 0.0
    long_buy_aggressive_volume: float = 0.0
    long_sell_aggressive_volume: float = 0.0
    long_aggression_delta: float = 0.0
    long_aggression_ratio: float = 0.0
    active_support_count: int = 0
    active_resistance_count: int = 0
    strongest_support_price: Optional[float] = None
    strongest_resistance_price: Optional[float] = None


@dataclass(slots=True)
class SignalState:
    timestamp_ns: int
    instrument: str
    signal_name: str
    score_0_to_10: float
    confidence_0_to_1: float
    direction: str
    reason_codes: List[str] = field(default_factory=list)
    summary: str = ""


@dataclass(slots=True)
class AlertRecord:
    timestamp_ns: int
    instrument: str
    alert_type: str
    priority: int
    message: str
    price: Optional[float] = None
    side: Optional[str] = None
    level_id: Optional[str] = None
    reason_codes: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SessionState:
    instrument: str
    config: EngineConfig
    best_bid_level: Optional[int] = None
    best_ask_level: Optional[int] = None
    active_levels_by_price: Dict[Tuple[str, int], TrackedLevel] = field(default_factory=dict)
    active_support_ids: List[str] = field(default_factory=list)
    active_resistance_ids: List[str] = field(default_factory=list)
    failed_level_ids: List[str] = field(default_factory=list)
    recent_events: Deque[NormalizedBookmapEvent] = field(default_factory=lambda: deque(maxlen=5000))
    recent_feature_snapshots: Deque[FeatureSnapshot] = field(default_factory=lambda: deque(maxlen=14400))
    recent_alerts: Deque[AlertRecord] = field(default_factory=lambda: deque(maxlen=200))
    current_signals: Dict[str, SignalState] = field(default_factory=dict)
    session_start_ns: int = 0
    last_clock_ns: int = 0

    def level_key(self, side: str, price_level: int) -> Tuple[str, int]:
        return side, price_level

    def get_level(self, side: str, price_level: int) -> Optional[TrackedLevel]:
        return self.active_levels_by_price.get(self.level_key(side, price_level))

    def upsert_level(self, level: TrackedLevel) -> None:
        self.active_levels_by_price[self.level_key(level.side, level.price_level)] = level

    def add_event(self, event: NormalizedBookmapEvent) -> None:
        self.recent_events.append(event)
        if event.best_bid_level is not None:
            self.best_bid_level = event.best_bid_level
        if event.best_ask_level is not None:
            self.best_ask_level = event.best_ask_level

    def add_snapshot(self, snapshot: FeatureSnapshot) -> None:
        self.recent_feature_snapshots.append(snapshot)

    def add_alert(self, alert: AlertRecord) -> None:
        self.recent_alerts.append(alert)

    def set_signal(self, signal: SignalState) -> None:
        self.current_signals[signal.signal_name] = signal


def compute_top_book_imbalance(bid_sum_top_n: float, ask_sum_top_n: float) -> float:
    total = bid_sum_top_n + ask_sum_top_n
    if total <= 0:
        return 0.0
    return (bid_sum_top_n - ask_sum_top_n) / total


def compute_aggression_ratio(buy_aggressive_volume: float, sell_aggressive_volume: float) -> float:
    total = buy_aggressive_volume + sell_aggressive_volume
    if total <= 0:
        return 0.0
    return (buy_aggressive_volume - sell_aggressive_volume) / total
