#!/usr/bin/env python3
"""Rules-based Bookmap signal engine built on normalized orderflow events.

Assumption for V1:
- `depth_add` and `depth_remove` events are treated as size deltas.
- `trade_*` events include `price_level` and `size`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from bookmap_signal_models import (
    AlertRecord,
    EngineConfig,
    FeatureSnapshot,
    NormalizedBookmapEvent,
    SessionState,
    SignalState,
    TrackedLevel,
    compute_aggression_ratio,
    compute_top_book_imbalance,
)


NANOSECONDS_PER_SECOND = 1_000_000_000


@dataclass(slots=True)
class EngineStepResult:
    alerts: List[AlertRecord] = field(default_factory=list)
    snapshot: Optional[FeatureSnapshot] = None
    signals: Dict[str, SignalState] = field(default_factory=dict)


class BookmapSignalEngine:
    """Maintains order book state, tracked levels, and signal output."""

    def __init__(self, config: EngineConfig):
        self.config = config
        self.session = SessionState(
            instrument=config.instrument,
            config=config,
            session_start_ns=0,
            last_clock_ns=0,
        )
        self.order_book: Dict[Tuple[str, int], float] = {}
        self.last_mid_level: Optional[float] = None
        self.last_long_bias_score = 0.0
        self.last_short_bias_score = 0.0
        self.last_snapshot_ns = 0

    def process_event(self, event: NormalizedBookmapEvent) -> EngineStepResult:
        if self.session.session_start_ns == 0:
            self.session.session_start_ns = event.timestamp_ns

        self.session.add_event(event)
        result = EngineStepResult()

        if event.event_type == "bbo_update":
            self._handle_bbo_update(event)
        elif event.event_type in {"depth_add", "depth_remove", "depth"}:
            result.alerts.extend(self._handle_depth_event(event))
        elif event.event_type in {"trade_buy_aggressor", "trade_sell_aggressor", "trade"}:
            self._handle_trade_event(event)
        elif event.event_type == "clock":
            self.session.last_clock_ns = event.timestamp_ns

        snapshot = self._maybe_build_snapshot(event.timestamp_ns)
        if snapshot is not None:
            result.snapshot = snapshot
            result.signals = self._update_signals(snapshot)
            result.alerts.extend(self._emit_signal_alerts(snapshot, result.signals))

        for alert in result.alerts:
            self.session.add_alert(alert)

        return result

    def _handle_bbo_update(self, event: NormalizedBookmapEvent) -> None:
        if event.best_bid_level is not None:
            self.session.best_bid_level = event.best_bid_level
        if event.best_ask_level is not None:
            self.session.best_ask_level = event.best_ask_level

    def _handle_depth_event(self, event: NormalizedBookmapEvent) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if event.side is None or event.price_level is None:
            return alerts

        size = max(0.0, event.size or 0.0)
        key = (event.side, event.price_level)
        
        # In Bookmap, we get the ABSOLUTE current size at that level.
        # So we set it directly instead of adding/subtracting deltas.
        current_size = max(0.0, event.size or 0.0)
        previous_size = self.order_book.get(key, 0.0)

        if current_size <= 0.0:
            self.order_book.pop(key, None)
        else:
            self.order_book[key] = current_size

        alerts.extend(self._update_tracked_level(event, previous_size, current_size))
        return alerts

    def _handle_trade_event(self, event: NormalizedBookmapEvent) -> None:
        if event.price_level is None or event.size is None:
            return

        for level in self.session.active_levels_by_price.values():
            if abs(level.price_level - event.price_level) > 1:
                continue
            level.last_trade_touch_ns = event.timestamp_ns
            level.trade_volume_near_level += event.size
            
            # Check if this trade is a buy or sell agressor
            is_buy = (event.event_type == "trade_buy_aggressor" or 
                     (event.event_type == "trade" and event.side == "buy"))
            
            if is_buy:
                level.buy_aggressive_volume_near_level += event.size
            else:
                level.sell_aggressive_volume_near_level += event.size

            if event.side is not None and event.side != level.side and event.side != "trade":
                level.times_tested += 1
                level.times_partially_hit += 1

            # Absorption detection logic:
            # If a level is being hit by the opposite side, we calculate the absorption score
            # (Aggressive volume relative to visible size)
            if level.current_size > 0:
                aggr_vol = level.sell_aggressive_volume_near_level if level.side == "bid" else level.buy_aggressive_volume_near_level
                level.absorption_score = aggr_vol / max(1.0, level.max_seen_size)
                
                # If absorption > 1.5x of its peak size, mark as Point of Interest
                if level.absorption_score >= 1.5:
                    level.is_poi = True

    def _update_tracked_level(
        self,
        event: NormalizedBookmapEvent,
        previous_size: float,
        current_size: float,
    ) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        if event.side is None or event.price_level is None:
            return alerts

        if not self._is_near_book(event.side, event.price_level):
            return alerts

        key = (event.side, event.price_level)
        level = self.session.active_levels_by_price.get(key)
        near_book_average = self._near_book_average_size()
        large_threshold = near_book_average * self.config.large_level_factor
        is_large = current_size > 0.0 and current_size >= large_threshold and large_threshold > 0.0

        if level is None and is_large and self._can_create_new_level(event.timestamp_ns, event.side, event.price_level):
            level = self._create_level(event, current_size, near_book_average)
            self.session.upsert_level(level)
            alerts.append(
                self._make_level_alert(
                    event.timestamp_ns,
                    "new_support_level" if event.side == "bid" else "new_resistance_level",
                    level,
                    f"New large {'bid' if event.side == 'bid' else 'ask'} detected at {level.price:.4f}",
                    priority=1,
                    reason_codes=["NEW_LEVEL"],
                )
            )

        if level is None:
            return alerts

        level.last_seen_ns = event.timestamp_ns
        level.current_size = current_size
        level.max_seen_size = max(level.max_seen_size, current_size)
        level.distance_ticks_from_market = self._distance_from_market(level.side, level.price_level)
        level.persistence_score = min(1.0, level.age_seconds(event.timestamp_ns) / max(1, self.config.persistence_seconds))
        level.context_correlation_score = self._context_correlation_score(level)

        if current_size >= large_threshold * 2.4 and large_threshold > 0.0:
            level.strength_tier = "major"
        elif current_size >= large_threshold * 1.4 and large_threshold > 0.0:
            level.strength_tier = "large"
        else:
            level.strength_tier = "notable"

        if self._is_reload(level, previous_size, current_size, event.timestamp_ns):
            level.times_reloaded += 1
            level.last_rebuild_ns = event.timestamp_ns
            alerts.append(
                self._make_level_alert(
                    event.timestamp_ns,
                    "support_reloaded" if level.side == "bid" else "resistance_reloaded",
                    level,
                    f"{'Support' if level.side == 'bid' else 'Resistance'} reloaded at {level.price:.4f}",
                    priority=1,
                    reason_codes=["LEVEL_RELOADED"],
                )
            )

        if level.is_poi and "POI_DETECTED" not in level.reason_codes:
            level.reason_codes.append("POI_DETECTED")
            alerts.append(
                self._make_level_alert(
                    event.timestamp_ns,
                    "point_of_interest_detected",
                    level,
                    f"🔥 POI DETECTED: {'Support' if level.side == 'bid' else 'Resistance'} is absorbing heavy volume at {level.price:.4f}",
                    priority=5,  # EXTREME PRIORITY
                    reason_codes=["POI_ABSORPTION", "HIDDEN_LIQUIDITY"],
                )
            )

        if self._is_pulled(level, previous_size, current_size):
            level.times_fully_pulled += 1
            level.status = "pulled"
            alerts.append(
                self._make_level_alert(
                    event.timestamp_ns,
                    "support_failed" if level.side == "bid" else "resistance_failed",
                    level,
                    f"{'Support' if level.side == 'bid' else 'Resistance'} pulled at {level.price:.4f}",
                    priority=2,
                    reason_codes=["LEVEL_PULLED"],
                )
            )

        if current_size <= 0.0:
            if self._is_failed_by_consumption(level, event.timestamp_ns):
                level.status = "failed"
                alerts.append(
                    self._make_level_alert(
                        event.timestamp_ns,
                        "support_failed" if level.side == "bid" else "resistance_failed",
                        level,
                        f"{'Support' if level.side == 'bid' else 'Resistance'} failed at {level.price:.4f}",
                        priority=2,
                        reason_codes=["LEVEL_FAILED"],
                    )
                )
            self.session.failed_level_ids.append(level.level_id)
            self.session.active_levels_by_price.pop(key, None)
            return alerts

        if level.status == "new" and level.age_seconds(event.timestamp_ns) >= self.config.persistence_seconds:
            level.status = "developing"
            alerts.append(
                self._make_level_alert(
                    event.timestamp_ns,
                    "support_building" if level.side == "bid" else "resistance_building",
                    level,
                    f"{'Support' if level.side == 'bid' else 'Resistance'} building at {level.price:.4f}",
                    priority=1,
                    reason_codes=["PERSISTENCE_MET"],
                )
            )

        return alerts

    def _maybe_build_snapshot(self, now_ns: int) -> Optional[FeatureSnapshot]:
        if self.last_snapshot_ns and now_ns - self.last_snapshot_ns < NANOSECONDS_PER_SECOND:
            return None
        if self.session.best_bid_level is None or self.session.best_ask_level is None:
            return None

        bid_sum, ask_sum = self._top_n_sums(self.config.top_n_levels)
        buy_aggr, sell_aggr = self._aggressive_volumes_in_window(self.config.fast_window_seconds)
        bid_add, ask_add, bid_remove, ask_remove = self._depth_flow_in_window(self.config.fast_window_seconds)
        long_buy_aggr, long_sell_aggr = self._aggressive_volumes_in_window(self.config.context_window_seconds)
        long_bid_add, long_ask_add, long_bid_remove, long_ask_remove = self._depth_flow_in_window(
            self.config.context_window_seconds
        )
        strongest_support = self._strongest_level_price("bid")
        strongest_resistance = self._strongest_level_price("ask")

        snapshot = FeatureSnapshot(
            timestamp_ns=now_ns,
            instrument=self.config.instrument,
            best_bid_level=self.session.best_bid_level,
            best_ask_level=self.session.best_ask_level,
            mid_level=(self.session.best_bid_level + self.session.best_ask_level) / 2,
            bid_sum_top_n=bid_sum,
            ask_sum_top_n=ask_sum,
            top_book_imbalance=compute_top_book_imbalance(bid_sum, ask_sum),
            bid_stack_rate=bid_add / max(1, self.config.fast_window_seconds),
            ask_stack_rate=ask_add / max(1, self.config.fast_window_seconds),
            bid_pull_rate=bid_remove / max(1, self.config.fast_window_seconds),
            ask_pull_rate=ask_remove / max(1, self.config.fast_window_seconds),
            buy_aggressive_volume=buy_aggr,
            sell_aggressive_volume=sell_aggr,
            aggression_delta=buy_aggr - sell_aggr,
            aggression_ratio=compute_aggression_ratio(buy_aggr, sell_aggr),
            long_bid_stack_rate=long_bid_add / max(1, self.config.context_window_seconds),
            long_ask_stack_rate=long_ask_add / max(1, self.config.context_window_seconds),
            long_bid_pull_rate=long_bid_remove / max(1, self.config.context_window_seconds),
            long_ask_pull_rate=long_ask_remove / max(1, self.config.context_window_seconds),
            long_buy_aggressive_volume=long_buy_aggr,
            long_sell_aggressive_volume=long_sell_aggr,
            long_aggression_delta=long_buy_aggr - long_sell_aggr,
            long_aggression_ratio=compute_aggression_ratio(long_buy_aggr, long_sell_aggr),
            active_support_count=sum(1 for level in self.session.active_levels_by_price.values() if level.side == "bid"),
            active_resistance_count=sum(1 for level in self.session.active_levels_by_price.values() if level.side == "ask"),
            strongest_support_price=strongest_support,
            strongest_resistance_price=strongest_resistance,
        )
        self.last_snapshot_ns = now_ns
        self.last_mid_level = snapshot.mid_level
        self.session.add_snapshot(snapshot)
        return snapshot

    def _update_signals(self, snapshot: FeatureSnapshot) -> Dict[str, SignalState]:
        signals: Dict[str, SignalState] = {}

        support_level = self._best_developing_level("bid")
        resistance_level = self._best_developing_level("ask")

        support_active = (
            support_level is not None
            and support_level.status in {"developing", "confirmed"}
            and snapshot.top_book_imbalance >= self.config.imbalance_support_threshold
            and snapshot.bid_stack_rate > snapshot.ask_stack_rate
        )
        resistance_active = (
            resistance_level is not None
            and resistance_level.status in {"developing", "confirmed"}
            and snapshot.top_book_imbalance <= self.config.imbalance_resistance_threshold
            and snapshot.ask_stack_rate > snapshot.bid_stack_rate
        )

        signals["support_building"] = SignalState(
            timestamp_ns=snapshot.timestamp_ns,
            instrument=self.config.instrument,
            signal_name="support_building",
            score_0_to_10=7.0 if support_active else 0.0,
            confidence_0_to_1=min(1.0, (support_level.confidence_score if support_level else 0.0) + 0.35),
            direction="long",
            reason_codes=self._support_reason_codes(snapshot, support_level, support_active),
            summary="Support building" if support_active else "No active support build",
        )

        signals["resistance_building"] = SignalState(
            timestamp_ns=snapshot.timestamp_ns,
            instrument=self.config.instrument,
            signal_name="resistance_building",
            score_0_to_10=7.0 if resistance_active else 0.0,
            confidence_0_to_1=min(1.0, (resistance_level.confidence_score if resistance_level else 0.0) + 0.35),
            direction="short",
            reason_codes=self._resistance_reason_codes(snapshot, resistance_level, resistance_active),
            summary="Resistance building" if resistance_active else "No active resistance build",
        )

        long_bias_score = self._score_long_bias(snapshot, support_level)
        short_bias_score = self._score_short_bias(snapshot, resistance_level)

        signals["long_bias"] = SignalState(
            timestamp_ns=snapshot.timestamp_ns,
            instrument=self.config.instrument,
            signal_name="long_bias",
            score_0_to_10=long_bias_score,
            confidence_0_to_1=min(1.0, long_bias_score / 10.0),
            direction="long",
            reason_codes=self._support_reason_codes(snapshot, support_level, long_bias_score >= 3.0),
            summary=f"Long bias score {long_bias_score:.1f}/10",
        )
        signals["short_bias"] = SignalState(
            timestamp_ns=snapshot.timestamp_ns,
            instrument=self.config.instrument,
            signal_name="short_bias",
            score_0_to_10=short_bias_score,
            confidence_0_to_1=min(1.0, short_bias_score / 10.0),
            direction="short",
            reason_codes=self._resistance_reason_codes(snapshot, resistance_level, short_bias_score >= 3.0),
            summary=f"Short bias score {short_bias_score:.1f}/10",
        )

        breakout_supported = self._detect_breakout_supported(snapshot, resistance_level, support_level)
        breakout_fade = self._detect_breakout_fade(snapshot, resistance_level, support_level)

        signals["breakout_supported"] = SignalState(
            timestamp_ns=snapshot.timestamp_ns,
            instrument=self.config.instrument,
            signal_name="breakout_supported",
            score_0_to_10=8.0 if breakout_supported else 0.0,
            confidence_0_to_1=0.8 if breakout_supported else 0.0,
            direction="either",
            reason_codes=["BREAKOUT_CONFIRMED"] if breakout_supported else [],
            summary="Breakout supported" if breakout_supported else "No supported breakout",
        )
        signals["breakout_fade_warning"] = SignalState(
            timestamp_ns=snapshot.timestamp_ns,
            instrument=self.config.instrument,
            signal_name="breakout_fade_warning",
            score_0_to_10=8.0 if breakout_fade else 0.0,
            confidence_0_to_1=0.8 if breakout_fade else 0.0,
            direction="either",
            reason_codes=["BREAKOUT_FADE"] if breakout_fade else [],
            summary="Breakout fade warning" if breakout_fade else "No fade warning",
        )

        stand_aside = max(long_bias_score, short_bias_score) < 3.0 and not breakout_supported
        signals["stand_aside"] = SignalState(
            timestamp_ns=snapshot.timestamp_ns,
            instrument=self.config.instrument,
            signal_name="stand_aside",
            score_0_to_10=7.0 if stand_aside else 0.0,
            confidence_0_to_1=0.7 if stand_aside else 0.0,
            direction="flat",
            reason_codes=["MIXED_ORDERFLOW"] if stand_aside else [],
            summary="Stand aside: mixed orderflow" if stand_aside else "Directional pressure present",
        )

        for signal in signals.values():
            self.session.set_signal(signal)
        return signals

    def _emit_signal_alerts(
        self,
        snapshot: FeatureSnapshot,
        signals: Dict[str, SignalState],
    ) -> List[AlertRecord]:
        alerts: List[AlertRecord] = []
        long_bias = signals["long_bias"].score_0_to_10
        short_bias = signals["short_bias"].score_0_to_10

        if long_bias >= 6.0 and self.last_long_bias_score < 6.0:
            alerts.append(
                AlertRecord(
                    timestamp_ns=snapshot.timestamp_ns,
                    instrument=self.config.instrument,
                    alert_type="long_bias_rising",
                    priority=1,
                    message="Long bias rising",
                    reason_codes=signals["long_bias"].reason_codes,
                )
            )
        if short_bias >= 6.0 and self.last_short_bias_score < 6.0:
            alerts.append(
                AlertRecord(
                    timestamp_ns=snapshot.timestamp_ns,
                    instrument=self.config.instrument,
                    alert_type="short_bias_rising",
                    priority=1,
                    message="Short bias rising",
                    reason_codes=signals["short_bias"].reason_codes,
                )
            )
        if signals["breakout_supported"].score_0_to_10 > 0.0:
            alerts.append(
                AlertRecord(
                    timestamp_ns=snapshot.timestamp_ns,
                    instrument=self.config.instrument,
                    alert_type="breakout_supported",
                    priority=1,
                    message="Breakout supported",
                    reason_codes=signals["breakout_supported"].reason_codes,
                )
            )
        if signals["breakout_fade_warning"].score_0_to_10 > 0.0:
            alerts.append(
                AlertRecord(
                    timestamp_ns=snapshot.timestamp_ns,
                    instrument=self.config.instrument,
                    alert_type="breakout_fade_warning",
                    priority=2,
                    message="Breakout fade warning",
                    reason_codes=signals["breakout_fade_warning"].reason_codes,
                )
            )

        self.last_long_bias_score = long_bias
        self.last_short_bias_score = short_bias
        return alerts

    def _score_long_bias(self, snapshot: FeatureSnapshot, support_level: Optional[TrackedLevel]) -> float:
        score = 0.0
        if support_level and support_level.status in {"developing", "confirmed"}:
            score += 2.0
        if snapshot.top_book_imbalance >= 0.15:
            score += 1.0
        if snapshot.top_book_imbalance >= 0.30:
            score += 1.0
        if snapshot.aggression_ratio >= 0.10:
            score += 1.0
        if snapshot.aggression_ratio >= 0.25:
            score += 1.0
        if snapshot.ask_pull_rate > snapshot.bid_pull_rate:
            score += 1.0
        if snapshot.long_aggression_ratio >= self.config.aggression_support_threshold:
            score += 1.0
        if snapshot.long_ask_pull_rate > snapshot.long_bid_pull_rate:
            score += 1.0
        if support_level and support_level.times_reloaded > 0:
            score += 2.0
        if support_level and support_level.absorption_score >= 1.0:
            score += 3.0  # Massive score for holding buys
        if support_level and support_level.sell_aggressive_volume_near_level > 0 and support_level.current_size > 0:
            score += 2.0
        if support_level and support_level.times_fully_pulled > 0:
            score -= 3.0
        return max(0.0, min(10.0, score))

    def _score_short_bias(self, snapshot: FeatureSnapshot, resistance_level: Optional[TrackedLevel]) -> float:
        score = 0.0
        if resistance_level and resistance_level.status in {"developing", "confirmed"}:
            score += 2.0
        if snapshot.top_book_imbalance <= -0.15:
            score += 1.0
        if snapshot.top_book_imbalance <= -0.30:
            score += 1.0
        if snapshot.aggression_ratio <= -0.10:
            score += 1.0
        if snapshot.aggression_ratio <= -0.25:
            score += 1.0
        if snapshot.bid_pull_rate > snapshot.ask_pull_rate:
            score += 1.0
        if snapshot.long_aggression_ratio <= self.config.aggression_resistance_threshold:
            score += 1.0
        if snapshot.long_bid_pull_rate > snapshot.long_ask_pull_rate:
            score += 1.0
        if resistance_level and resistance_level.times_reloaded > 0:
            score += 2.0
        if resistance_level and resistance_level.absorption_score >= 1.0:
            score += 3.0  # Massive score for holding sells
        if resistance_level and resistance_level.buy_aggressive_volume_near_level > 0 and resistance_level.current_size > 0:
            score += 2.0
        if resistance_level and resistance_level.times_fully_pulled > 0:
            score -= 3.0
        return max(0.0, min(10.0, score))

    def _detect_breakout_supported(
        self,
        snapshot: FeatureSnapshot,
        resistance_level: Optional[TrackedLevel],
        support_level: Optional[TrackedLevel],
    ) -> bool:
        mid_level = snapshot.mid_level
        if mid_level is None or self.last_mid_level is None:
            return False
        upside_break = resistance_level and self.last_mid_level <= resistance_level.price_level < mid_level
        downside_break = support_level and self.last_mid_level >= support_level.price_level > mid_level
        if upside_break:
            return snapshot.aggression_ratio >= self.config.aggression_support_threshold and snapshot.ask_pull_rate >= snapshot.bid_pull_rate
        if downside_break:
            return snapshot.aggression_ratio <= self.config.aggression_resistance_threshold and snapshot.bid_pull_rate >= snapshot.ask_pull_rate
        return False

    def _detect_breakout_fade(
        self,
        snapshot: FeatureSnapshot,
        resistance_level: Optional[TrackedLevel],
        support_level: Optional[TrackedLevel],
    ) -> bool:
        mid_level = snapshot.mid_level
        if mid_level is None or self.last_mid_level is None:
            return False
        upside_break = resistance_level and self.last_mid_level <= resistance_level.price_level < mid_level
        downside_break = support_level and self.last_mid_level >= support_level.price_level > mid_level
        if upside_break:
            return snapshot.aggression_ratio < 0.05 or snapshot.ask_stack_rate > snapshot.bid_stack_rate
        if downside_break:
            return snapshot.aggression_ratio > -0.05 or snapshot.bid_stack_rate > snapshot.ask_stack_rate
        return False

    def _top_n_sums(self, top_n_levels: int) -> Tuple[float, float]:
        best_bid = self.session.best_bid_level
        best_ask = self.session.best_ask_level
        if best_bid is None or best_ask is None:
            return 0.0, 0.0

        bid_sum = 0.0
        ask_sum = 0.0
        for offset in range(top_n_levels):
            bid_sum += self.order_book.get(("bid", best_bid - offset), 0.0)
            ask_sum += self.order_book.get(("ask", best_ask + offset), 0.0)
        return bid_sum, ask_sum

    def _near_book_average_size(self) -> float:
        best_bid = self.session.best_bid_level
        best_ask = self.session.best_ask_level
        if best_bid is None or best_ask is None:
            return 0.0

        sizes: List[float] = []
        for offset in range(self.config.near_book_ticks):
            sizes.append(self.order_book.get(("bid", best_bid - offset), 0.0))
            sizes.append(self.order_book.get(("ask", best_ask + offset), 0.0))
        non_zero = [size for size in sizes if size > 0.0]
        if not non_zero:
            return 0.0
        return sum(non_zero) / len(non_zero)

    def _depth_flow_in_window(self, seconds: int) -> Tuple[float, float, float, float]:
        cutoff = self._cutoff_ns(seconds)
        bid_add = ask_add = bid_remove = ask_remove = 0.0
        for event in self.session.recent_events:
            if event.timestamp_ns < cutoff or event.event_type not in {"depth_add", "depth_remove"}:
                continue
            if event.price_level is None or event.side is None or not self._is_near_book(event.side, event.price_level):
                continue
            amount = max(0.0, event.size or 0.0)
            if event.side == "bid" and event.event_type == "depth_add":
                bid_add += amount
            elif event.side == "ask" and event.event_type == "depth_add":
                ask_add += amount
            elif event.side == "bid":
                bid_remove += amount
            else:
                ask_remove += amount
        return bid_add, ask_add, bid_remove, ask_remove

    def _aggressive_volumes_in_window(self, seconds: int) -> Tuple[float, float]:
        cutoff = self._cutoff_ns(seconds)
        buy_aggr = 0.0
        sell_aggr = 0.0
        for event in self.session.recent_events:
            if event.timestamp_ns < cutoff:
                continue
            size = max(0.0, event.size or 0.0)
            if event.event_type == "trade_buy_aggressor":
                buy_aggr += size
            elif event.event_type == "trade_sell_aggressor":
                sell_aggr += size
        return buy_aggr, sell_aggr

    def _best_developing_level(self, side: str) -> Optional[TrackedLevel]:
        candidates = [
            level
            for level in self.session.active_levels_by_price.values()
            if level.side == side and level.status in {"developing", "confirmed"}
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda level: (level.confidence_score, level.max_seen_size, level.persistence_score))

    def _strongest_level_price(self, side: str) -> Optional[float]:
        level = self._best_developing_level(side)
        return None if level is None else level.price

    def _context_correlation_score(self, level: TrackedLevel) -> float:
        if not self.session.recent_feature_snapshots:
            return 0.0
        latest = self.session.recent_feature_snapshots[-1]
        score = 0.0
        if level.side == "bid":
            if latest.bid_stack_rate > latest.ask_stack_rate:
                score += 0.35
            if latest.ask_pull_rate > latest.bid_pull_rate:
                score += 0.25
            if latest.aggression_ratio >= self.config.aggression_support_threshold:
                score += 0.20
            if latest.top_book_imbalance >= self.config.imbalance_support_threshold:
                score += 0.20
        else:
            if latest.ask_stack_rate > latest.bid_stack_rate:
                score += 0.35
            if latest.bid_pull_rate > latest.ask_pull_rate:
                score += 0.25
            if latest.aggression_ratio <= self.config.aggression_resistance_threshold:
                score += 0.20
            if latest.top_book_imbalance <= self.config.imbalance_resistance_threshold:
                score += 0.20
        level.confidence_score = min(1.0, score)
        return level.confidence_score

    def _support_reason_codes(
        self,
        snapshot: FeatureSnapshot,
        level: Optional[TrackedLevel],
        active: bool,
    ) -> List[str]:
        if not active:
            return []
        reason_codes: List[str] = []
        if snapshot.bid_stack_rate > snapshot.ask_stack_rate:
            reason_codes.append("BID_STACKING")
        if snapshot.ask_pull_rate > snapshot.bid_pull_rate:
            reason_codes.append("ASK_PULLING")
        if snapshot.top_book_imbalance >= self.config.imbalance_support_threshold:
            reason_codes.append("IMBALANCE_BID_HEAVY")
        if snapshot.aggression_ratio >= self.config.aggression_support_threshold:
            reason_codes.append("BUYER_AGGRESSION")
        if snapshot.long_aggression_ratio >= self.config.aggression_support_threshold:
            reason_codes.append("LONG_WINDOW_BUYER_AGGRESSION")
        if level and level.times_reloaded > 0:
            reason_codes.append("SUPPORT_RELOADED")
        return reason_codes

    def _resistance_reason_codes(
        self,
        snapshot: FeatureSnapshot,
        level: Optional[TrackedLevel],
        active: bool,
    ) -> List[str]:
        if not active:
            return []
        reason_codes: List[str] = []
        if snapshot.ask_stack_rate > snapshot.bid_stack_rate:
            reason_codes.append("ASK_STACKING")
        if snapshot.bid_pull_rate > snapshot.ask_pull_rate:
            reason_codes.append("BID_PULLING")
        if snapshot.top_book_imbalance <= self.config.imbalance_resistance_threshold:
            reason_codes.append("IMBALANCE_ASK_HEAVY")
        if snapshot.aggression_ratio <= self.config.aggression_resistance_threshold:
            reason_codes.append("SELLER_AGGRESSION")
        if snapshot.long_aggression_ratio <= self.config.aggression_resistance_threshold:
            reason_codes.append("LONG_WINDOW_SELLER_AGGRESSION")
        if level and level.times_reloaded > 0:
            reason_codes.append("RESISTANCE_RELOADED")
        return reason_codes

    def _is_near_book(self, side: str, price_level: int) -> bool:
        best_bid = self.session.best_bid_level
        best_ask = self.session.best_ask_level
        if best_bid is None or best_ask is None:
            return False
        if side == "bid":
            return 0 <= (best_bid - price_level) < self.config.near_book_ticks
        return 0 <= (price_level - best_ask) < self.config.near_book_ticks

    def _distance_from_market(self, side: str, price_level: int) -> Optional[int]:
        best_bid = self.session.best_bid_level
        best_ask = self.session.best_ask_level
        if best_bid is None or best_ask is None:
            return None
        if side == "bid":
            return best_bid - price_level
        return price_level - best_ask

    def _can_create_new_level(self, now_ns: int, side: str, price_level: int) -> bool:
        cooldown_ns = self.config.new_level_cooldown_seconds * NANOSECONDS_PER_SECOND
        target_price = price_level * self.config.pips
        for alert in reversed(self.session.recent_alerts):
            if alert.side != side or alert.price is None:
                continue
            if abs(alert.price - target_price) >= self.config.pips:
                continue
            if now_ns - alert.timestamp_ns < cooldown_ns:
                return False
            break
        return True

    def _create_level(self, event: NormalizedBookmapEvent, current_size: float, near_book_average: float) -> TrackedLevel:
        assert event.side is not None
        assert event.price_level is not None
        price = event.price if event.price is not None else event.price_level * self.config.pips
        factor = current_size / max(near_book_average, 1e-9)
        if factor >= 6.0:
            strength_tier = "major"
        elif factor >= 4.0:
            strength_tier = "large"
        else:
            strength_tier = "notable"
        return TrackedLevel(
            level_id=f"{event.side}:{event.price_level}:{event.timestamp_ns}",
            instrument=self.config.instrument,
            side=event.side,
            price_level=event.price_level,
            price=price,
            status="new",
            strength_tier=strength_tier,
            first_seen_ns=event.timestamp_ns,
            last_seen_ns=event.timestamp_ns,
            max_seen_size=current_size,
            current_size=current_size,
            distance_ticks_from_market=self._distance_from_market(event.side, event.price_level),
            reason_codes=["NEW_LEVEL"],
        )

    def _is_reload(self, level: TrackedLevel, previous_size: float, current_size: float, now_ns: int) -> bool:
        if level.max_seen_size <= 0 or previous_size <= 0:
            return False
        dropped = previous_size < (level.max_seen_size * self.config.rebuild_ratio)
        rebuilt = current_size >= (level.max_seen_size * self.config.rebuild_ratio)
        if not dropped or not rebuilt:
            return False
        if level.last_rebuild_ns and now_ns - level.last_rebuild_ns < self.config.reload_seconds * NANOSECONDS_PER_SECOND:
            return False
        return True

    def _is_pulled(self, level: TrackedLevel, previous_size: float, current_size: float) -> bool:
        if previous_size <= 0:
            return False
        removed_ratio = (previous_size - current_size) / previous_size
        return removed_ratio >= self.config.pull_ratio and level.last_trade_touch_ns is None

    def _is_failed_by_consumption(self, level: TrackedLevel, now_ns: int) -> bool:
        if level.last_trade_touch_ns is None:
            return False
        recent_trade_touch = now_ns - level.last_trade_touch_ns <= 5 * NANOSECONDS_PER_SECOND
        return recent_trade_touch

    def _make_level_alert(
        self,
        timestamp_ns: int,
        alert_type: str,
        level: TrackedLevel,
        message: str,
        priority: int,
        reason_codes: List[str],
    ) -> AlertRecord:
        return AlertRecord(
            timestamp_ns=timestamp_ns,
            instrument=self.config.instrument,
            alert_type=alert_type,
            priority=priority,
            message=message,
            price=level.price,
            side=level.side,
            level_id=level.level_id,
            reason_codes=reason_codes,
            context={
                "status": level.status,
                "strength_tier": level.strength_tier,
                "times_reloaded": level.times_reloaded,
                "times_tested": level.times_tested,
                "confidence_score": level.confidence_score,
            },
        )

    def _cutoff_ns(self, seconds: int) -> int:
        now_ns = self.session.last_clock_ns or self.last_snapshot_ns or self.session.session_start_ns
        return now_ns - (seconds * NANOSECONDS_PER_SECOND)
