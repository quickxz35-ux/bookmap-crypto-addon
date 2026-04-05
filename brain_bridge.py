#!/usr/bin/env python3
"""Local bridge for the Brain Remote UI.

This service exposes:
- POST /ask  -> returns a verdict/score using the latest Bookmap brain feed
- POST /log  -> appends operator notes
- GET  /health -> basic readiness probe

The bridge prefers the restored OpenVINO brain when it is available and falls
back to the heuristic scorer if the model stack cannot be loaded.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from openvino_brain import OpenVinoBrain


HOST = "127.0.0.1"
PORT = 5000
RUNS_DIR = Path(r"C:\Bookmap\Config\runs")
LATEST_FEED_PATH = RUNS_DIR / "brain_feed_latest.json"
FEED_HISTORY_PATH = RUNS_DIR / "brain_feed_history.jsonl"
BRIDGE_LOG_PATH = RUNS_DIR / "brain_bridge_log.jsonl"
OV_BRAIN = OpenVinoBrain()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _read_latest_feed() -> Tuple[Optional[Dict[str, Any]], str]:
    if not LATEST_FEED_PATH.exists():
        return None, f"Missing feed file: {LATEST_FEED_PATH}"

    try:
        with LATEST_FEED_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"Failed to read feed: {exc}"

    return payload, "Feed loaded"


def _recent_history_excerpt(limit: int = 5) -> list[dict[str, Any]]:
    if not FEED_HISTORY_PATH.exists():
        return []

    lines: list[str] = []
    try:
        with FEED_HISTORY_PATH.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if raw:
                    lines.append(raw)
    except Exception:
        return []

    excerpt: list[dict[str, Any]] = []
    for raw in lines[-limit:]:
        try:
            excerpt.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return excerpt


def _heuristic_score_from_feed(feed: Optional[Dict[str, Any]]) -> tuple[int, str, str, Dict[str, Any]]:
    if not feed:
        return 0, "Awaiting market sync", "No brain feed available yet", {
            "sentiment_label": "n/a",
            "sentiment_delta": 0.0,
            "sentiment_confidence": 0.0,
            "forecast_label": "n/a",
            "forecast_value": 0.0,
            "forecast_delta": 0.0,
        }

    market_state = feed.get("market_state", {})
    orderflow = feed.get("orderflow", {})
    display = feed.get("display_metrics", {})
    micro = feed.get("micro_price_analysis", {})

    net_bias = _safe_float(display.get("display_net_bias"))
    top_imbalance = _safe_float(display.get("display_top_book_imbalance"))
    aggression = _safe_float(orderflow.get("aggression_ratio"))
    micro_trend = _safe_text(micro.get("micro_trend"), "Neutral")
    velocity = _safe_float(micro.get("velocity_ticks_per_sec"))
    displacement_efficiency = _safe_float(micro.get("displacement_efficiency"), 1.0)
    buy_window = _safe_float(micro.get("buy_volume_window"))
    sell_window = _safe_float(micro.get("sell_volume_window"))
    volume_balance = 0.0
    total_window_volume = buy_window + sell_window
    if total_window_volume > 0:
        volume_balance = (buy_window - sell_window) / total_window_volume

    score = 50.0
    score += max(-20.0, min(20.0, net_bias * 2.0))
    score += max(-8.0, min(8.0, top_imbalance * 6.0))
    score += max(-8.0, min(8.0, aggression * 6.0))
    score += max(-6.0, min(6.0, volume_balance * 5.0))

    trend_lower = micro_trend.lower()
    if "bullish" in trend_lower:
        score += 12.0
    elif "bearish" in trend_lower:
        score -= 12.0

    if velocity < 0.3 and displacement_efficiency < 0.35:
        score -= 10.0
    elif velocity > 0.8 and displacement_efficiency > 0.8:
        score += 5.0

    if net_bias > 1.5 and "bearish" in trend_lower:
        score -= 12.0
    elif net_bias < -1.5 and "bullish" in trend_lower:
        score -= 12.0

    if abs(net_bias) < 1.0 and abs(top_imbalance) < 0.15 and abs(volume_balance) < 0.15:
        score = min(score, 58.0)

    score = int(max(0.0, min(100.0, round(score))))

    if score >= 80:
        verdict = "Strong confluence"
    elif score >= 65:
        verdict = "Bullish confluence"
    elif score >= 50:
        verdict = "Mixed / wait"
    else:
        verdict = "Bearish pressure"

    symbol = _safe_text(feed.get("instrument"), "Unknown")
    micro_price = market_state.get("micro_price")
    best_bid = market_state.get("best_bid_price")
    best_ask = market_state.get("best_ask_price")

    details = (
        f"{symbol} | net_bias={net_bias:.2f} | imbalance={top_imbalance:.2f} | "
        f"micro={micro_price if micro_price is not None else 'n/a'} | "
        f"bid={best_bid if best_bid is not None else 'n/a'} ask={best_ask if best_ask is not None else 'n/a'} | "
        f"trend={micro_trend}"
    )
    return score, verdict, details, {
        "sentiment_label": "heuristic",
        "sentiment_delta": 0.0,
        "sentiment_confidence": 0.0,
        "forecast_label": "heuristic",
        "forecast_value": 0.0,
        "forecast_delta": 0.0,
    }


def _brain_score_from_feed(feed: Optional[Dict[str, Any]], history: list[dict[str, Any]]) -> tuple[int, str, str, str, Dict[str, Any]]:
    if feed and OV_BRAIN.ready:
        try:
            result = OV_BRAIN.evaluate(feed, history)
            analysis = {
                "sentiment_label": result.sentiment_label,
                "sentiment_delta": result.sentiment_delta,
                "sentiment_confidence": result.sentiment_confidence,
                "forecast_label": result.forecast_label,
                "forecast_value": result.forecast_value,
                "forecast_delta": result.forecast_delta,
                "model_ready": result.model_ready,
            }
            return result.score, result.verdict, result.details, "openvino", analysis
        except Exception as exc:  # pragma: no cover - defensive fallback
            fallback_score, fallback_verdict, fallback_details, analysis = _heuristic_score_from_feed(feed)
            return (
                fallback_score,
                fallback_verdict,
                f"{fallback_details} | OpenVINO fallback: {exc}",
                "heuristic",
                analysis,
            )

    fallback_score, fallback_verdict, fallback_details, analysis = _heuristic_score_from_feed(feed)
    return fallback_score, fallback_verdict, fallback_details, "heuristic", analysis


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


@dataclass
class BridgeState:
    lock: threading.Lock = threading.Lock()
    last_query: str = ""
    last_response: Dict[str, Any] | None = None


STATE = BridgeState()


class BrainBridgeHandler(BaseHTTPRequestHandler):
    server_version = "BrainBridge/1.0"

    def _send_json(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            feed, status = _read_latest_feed()
            payload = {
                "ok": True,
                "status": status,
                "latest_feed": bool(feed),
                "brain_backend": "openvino" if OV_BRAIN.ready else "heuristic",
                "openvino_ready": OV_BRAIN.ready,
                "openvino_load_errors": OV_BRAIN.load_errors,
                "feed_path": str(LATEST_FEED_PATH),
                "history_path": str(FEED_HISTORY_PATH),
                "bridge_log_path": str(BRIDGE_LOG_PATH),
                "time": _now_iso(),
            }
            self._send_json(200, payload)
            return

        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(content_length) if content_length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}

        if path == "/ask":
            query = _safe_text(body.get("query"), "").strip()
            feed, status = _read_latest_feed()
            excerpt = _recent_history_excerpt(limit=60)
            score, verdict, details, backend, analysis = _brain_score_from_feed(feed, excerpt)
            response = {
                "verdict": verdict,
                "score": score,
                "logs": details if query else f"{details} | {status}",
                "analysis": analysis,
                "query": query,
                "query_note": "Query text is for display only and does not change the score.",
                "timestamp": _now_iso(),
                "brain_backend": backend,
                "latest_feed": feed,
                "recent_history": excerpt,
            }
            with STATE.lock:
                STATE.last_query = query
                STATE.last_response = response
            _append_jsonl(
                BRIDGE_LOG_PATH,
                {
                    "timestamp": _now_iso(),
                    "type": "ask",
                    "query": query,
                    "score": score,
                    "verdict": verdict,
                    "backend": backend,
                },
            )
            self._send_json(200, response)
            return

        if path == "/log":
            log_type = _safe_text(body.get("type"), "UNKNOWN").upper()
            record = {
                "timestamp": _now_iso(),
                "type": log_type,
                "payload": body,
            }
            _append_jsonl(BRIDGE_LOG_PATH, record)
            self._send_json(200, {"ok": True, "logged": log_type})
            return

        self._send_json(404, {"ok": False, "error": "not found"})


def main() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), BrainBridgeHandler)
    print(f"Brain bridge listening on http://{HOST}:{PORT}", flush=True)
    print(f"Latest feed: {LATEST_FEED_PATH}", flush=True)
    print(f"History feed: {FEED_HISTORY_PATH}", flush=True)
    print(f"OpenVINO brain ready: {OV_BRAIN.ready}", flush=True)
    if OV_BRAIN.load_errors:
        print("OpenVINO load issues:", flush=True)
        for item in OV_BRAIN.load_errors:
            print(f"  - {item}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Brain bridge shutting down", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
