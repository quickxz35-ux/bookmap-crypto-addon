#!/usr/bin/env python3
"""OpenVINO-backed brain for the Bookmap tape feed.

This module loads the restored sentiment and forecaster models and turns the
latest Bookmap telemetry into a verdict/score. If either model cannot be
loaded, callers can fall back to a heuristic scorer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import numpy as np
from openvino import Core
from optimum.intel.openvino import OVModelForSequenceClassification
from transformers import AutoTokenizer


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exp = np.exp(shifted)
    denom = np.sum(exp)
    if denom <= 0:
        return np.full_like(values, 1.0 / max(1, values.size), dtype=np.float32)
    return exp / denom


@dataclass
class OpenVinoBrainResult:
    score: int
    verdict: str
    details: str
    sentiment_label: str
    sentiment_delta: float
    sentiment_confidence: float
    forecast_value: float
    forecast_delta: float
    forecast_label: str
    model_ready: bool


class OpenVinoBrain:
    def __init__(self, models_root: Optional[Path] = None):
        self.models_root = models_root or Path(__file__).resolve().parent / "models"
        self.sentiment_dir = self.models_root / "sentiment-optimized"
        self.forecaster_dir = self.models_root / "forecaster" / "openvino_ir"

        self.sentiment_model: Optional[OVModelForSequenceClassification] = None
        self.sentiment_tokenizer = None
        self.forecaster = None
        self.id2label: Dict[int, str] = {}
        self.ready = False
        self.load_errors: list[str] = []
        self._load_models()

    def _load_models(self) -> None:
        try:
            if self.sentiment_dir.exists():
                self.sentiment_model = OVModelForSequenceClassification.from_pretrained(
                    self.sentiment_dir,
                    device="CPU",
                )
                self.sentiment_tokenizer = AutoTokenizer.from_pretrained(self.sentiment_dir)
                raw_id2label = getattr(self.sentiment_model.config, "id2label", {}) or {}
                self.id2label = {int(key): str(value) for key, value in raw_id2label.items()}
            else:
                self.load_errors.append(f"Missing sentiment model dir: {self.sentiment_dir}")
        except Exception as exc:  # pragma: no cover - defensive runtime loader
            self.load_errors.append(f"Sentiment load failed: {exc}")
            self.sentiment_model = None
            self.sentiment_tokenizer = None

        try:
            forecaster_xml = self.forecaster_dir / "forecaster.xml"
            if forecaster_xml.exists():
                core = Core()
                self.forecaster = core.compile_model(core.read_model(str(forecaster_xml)), "CPU")
            else:
                self.load_errors.append(f"Missing forecaster model: {forecaster_xml}")
        except Exception as exc:  # pragma: no cover - defensive runtime loader
            self.load_errors.append(f"Forecaster load failed: {exc}")
            self.forecaster = None

        self.ready = self.sentiment_model is not None and self.sentiment_tokenizer is not None and self.forecaster is not None

    def _build_sentiment_text(self, feed: Dict[str, Any]) -> str:
        instrument = str(feed.get("instrument") or "Unknown")
        market_state = feed.get("market_state", {})
        orderflow = feed.get("orderflow", {})
        display = feed.get("display_metrics", {})
        micro = feed.get("micro_price_analysis", {})

        net_bias = _safe_float(display.get("display_net_bias"))
        top_imbalance = _safe_float(display.get("display_top_book_imbalance"))
        aggression = _safe_float(orderflow.get("aggression_ratio"))
        velocity = _safe_float(micro.get("velocity_ticks_per_sec"))
        efficiency = _safe_float(micro.get("displacement_efficiency"), 1.0)
        micro_trend = str(micro.get("micro_trend") or "Neutral")
        buy_window = _safe_float(micro.get("buy_volume_window"))
        sell_window = _safe_float(micro.get("sell_volume_window"))
        micro_price = market_state.get("micro_price")

        if net_bias > 1.5 or aggression > 0.65 or "bullish" in micro_trend.lower():
            stance = "bullish"
        elif net_bias < -1.5 or aggression < -0.65 or "bearish" in micro_trend.lower():
            stance = "bearish"
        else:
            stance = "mixed"

        return (
            f"{instrument} tape looks {stance}. "
            f"Net bias {net_bias:.2f}. Order book imbalance {top_imbalance:.2f}. "
            f"Aggression ratio {aggression:.2f}. Micro trend {micro_trend}. "
            f"Velocity {velocity:.2f}. Efficiency {efficiency:.2f}. "
            f"Buy window {buy_window:.1f}. Sell window {sell_window:.1f}. "
            f"Micro price {micro_price if micro_price is not None else 'unknown'}."
        )

    def _build_forecast_sequence(self, feed: Dict[str, Any], history: Iterable[Dict[str, Any]]) -> np.ndarray:
        prices: list[float] = []
        for row in history:
            market_state = row.get("market_state", {}) if isinstance(row, dict) else {}
            value = market_state.get("micro_price")
            if value is None:
                value = market_state.get("best_bid_price") or market_state.get("best_ask_price")
            price = _safe_float(value, default=np.nan)
            if not np.isnan(price):
                prices.append(price)

        current_market = feed.get("market_state", {}) if isinstance(feed, dict) else {}
        current_price = _safe_float(current_market.get("micro_price"), default=np.nan)
        if not np.isnan(current_price):
            prices.append(current_price)

        if not prices:
            prices = [0.0]

        prices = prices[-60:]
        if len(prices) < 60:
            prices = [prices[0]] * (60 - len(prices)) + prices

        arr = np.asarray(prices, dtype=np.float32)
        min_value = float(np.min(arr))
        max_value = float(np.max(arr))
        if max_value > min_value:
            arr = (arr - min_value) / (max_value - min_value)
        else:
            arr = np.zeros_like(arr, dtype=np.float32)
        return arr.reshape(1, 60, 1)

    def _forecast_label(self, raw_value: float) -> tuple[str, float]:
        forecast_delta = float(np.clip((raw_value - 0.5) * 2.0, -1.0, 1.0))
        if forecast_delta >= 0.35:
            label = "bullish"
        elif forecast_delta <= -0.35:
            label = "bearish"
        else:
            label = "neutral"
        return label, forecast_delta

    def evaluate(self, feed: Dict[str, Any], history: Iterable[Dict[str, Any]]) -> OpenVinoBrainResult:
        if not self.ready:
            details = "; ".join(self.load_errors) if self.load_errors else "OpenVINO brain unavailable"
            return OpenVinoBrainResult(
                score=0,
                verdict="Awaiting market sync",
                details=details,
                sentiment_label="unavailable",
                sentiment_delta=0.0,
                sentiment_confidence=0.0,
                forecast_value=0.0,
                forecast_delta=0.0,
                forecast_label="unavailable",
                model_ready=False,
            )

        sentiment_text = self._build_sentiment_text(feed)
        encoded = self.sentiment_tokenizer(
            sentiment_text,
            return_tensors="pt",
            truncation=True,
            max_length=256,
        )
        sentiment_outputs = self.sentiment_model(**encoded)
        logits = np.asarray(sentiment_outputs.logits.detach().cpu().numpy(), dtype=np.float32)[0]
        probs = _softmax(logits)
        best_index = int(np.argmax(probs))
        sentiment_label = self.id2label.get(best_index, str(best_index))
        bullish_prob = float(probs[2]) if probs.size > 2 else 0.0
        bearish_prob = float(probs[0]) if probs.size > 0 else 0.0
        neutral_prob = float(probs[1]) if probs.size > 1 else 0.0
        sentiment_delta = bullish_prob - bearish_prob
        sentiment_confidence = float(np.max(probs))

        forecast_input = self._build_forecast_sequence(feed, history)
        forecast_output = self.forecaster([forecast_input])
        forecast_tensor = np.asarray(next(iter(forecast_output.values())), dtype=np.float32).reshape(-1)
        forecast_value = float(forecast_tensor[0]) if forecast_tensor.size else 0.0
        forecast_label, forecast_delta = self._forecast_label(forecast_value)

        market_state = feed.get("market_state", {})
        orderflow = feed.get("orderflow", {})
        display = feed.get("display_metrics", {})
        micro = feed.get("micro_price_analysis", {})

        net_bias = _safe_float(display.get("display_net_bias"))
        top_imbalance = _safe_float(display.get("display_top_book_imbalance"))
        aggression = _safe_float(orderflow.get("aggression_ratio"))
        velocity = _safe_float(micro.get("velocity_ticks_per_sec"))
        efficiency = _safe_float(micro.get("displacement_efficiency"), 1.0)
        buy_window = _safe_float(micro.get("buy_volume_window"))
        sell_window = _safe_float(micro.get("sell_volume_window"))
        total_window = buy_window + sell_window
        volume_balance = (buy_window - sell_window) / total_window if total_window > 0 else 0.0
        micro_trend = str(micro.get("micro_trend") or "Neutral")

        score = 50.0
        score += sentiment_delta * 24.0
        score += forecast_delta * 18.0
        score += max(-10.0, min(10.0, net_bias * 2.0))
        score += max(-8.0, min(8.0, top_imbalance * 6.0))
        score += max(-8.0, min(8.0, aggression * 6.0))
        score += max(-6.0, min(6.0, volume_balance * 5.0))

        trend_lower = micro_trend.lower()
        if "bullish" in trend_lower:
            score += 8.0
        elif "bearish" in trend_lower:
            score -= 8.0

        if velocity < 0.3 and efficiency < 0.35:
            score -= 8.0
        elif velocity > 0.8 and efficiency > 0.8:
            score += 4.0

        if net_bias > 1.5 and "bearish" in trend_lower:
            score -= 8.0
        elif net_bias < -1.5 and "bullish" in trend_lower:
            score -= 8.0

        score = int(max(0.0, min(100.0, round(score))))

        if score >= 80:
            verdict = "Strong confluence"
        elif score >= 65:
            verdict = "Bullish confluence"
        elif score >= 50:
            verdict = "Mixed / wait"
        else:
            verdict = "Bearish pressure"

        instrument = str(feed.get("instrument") or "Unknown")
        micro_price = market_state.get("micro_price")
        best_bid = market_state.get("best_bid_price")
        best_ask = market_state.get("best_ask_price")
        details = (
            f"{instrument} | sentiment={sentiment_label}({sentiment_delta:+.2f}, conf={sentiment_confidence:.2f}) | "
            f"forecast={forecast_label}({forecast_value:.3f}) | imbalance={top_imbalance:.2f} | "
            f"micro={micro_price if micro_price is not None else 'n/a'} | "
            f"bid={best_bid if best_bid is not None else 'n/a'} ask={best_ask if best_ask is not None else 'n/a'} | "
            f"trend={micro_trend} | readiness={'ready' if self.ready else 'not_ready'}"
        )

        return OpenVinoBrainResult(
            score=score,
            verdict=verdict,
            details=details,
            sentiment_label=sentiment_label,
            sentiment_delta=sentiment_delta,
            sentiment_confidence=sentiment_confidence,
            forecast_value=forecast_value,
            forecast_delta=forecast_delta,
            forecast_label=forecast_label,
            model_ready=True,
        )
