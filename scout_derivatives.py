import hashlib
import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from blackbox_reader import BlackBoxReader
from local_blackbox import LocalBlackBox
from symbol_utils import normalize_asset_symbol
from workspace_config import load_workspace_config


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class DerivativesScout:
    def __init__(self):
        self.db = LocalBlackBox()
        self.reader = BlackBoxReader()
        self.config = load_workspace_config()
        self.base_url = self.config.binance_futures_base_url.rstrip("/")
        self.session = requests.Session()

    def _request(self, endpoint: str, params: Optional[Dict[str, object]] = None):
        response = self.session.get(f"{self.base_url}/{endpoint.lstrip('/')}", params=params or {}, timeout=20)
        response.raise_for_status()
        return response.json()

    def _snapshot_bucket(self, observed_epoch: float, interval_seconds: int = 600) -> str:
        bucket = int(math.floor(observed_epoch / interval_seconds) * interval_seconds)
        return datetime.fromtimestamp(bucket, tz=timezone.utc).isoformat()

    def _snapshot_id(self, asset: str, raw_symbol: str, bucket_iso: str) -> str:
        seed = f"{asset}|{raw_symbol}|binance_futures|10m|{bucket_iso}"
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()

    def _previous_volume_context(self, asset: str) -> Dict[str, float]:
        history = self.reader.latest_derivatives(asset, limit=20)
        if history.empty:
            return {"previous_volume": 0.0, "average_volume": 0.0}
        volume_series = history["volume_absolute"] if "volume_absolute" in history else history.get("volume_24h")
        if volume_series is None:
            return {"previous_volume": 0.0, "average_volume": 0.0}
        volume_series = volume_series.fillna(0).astype(float)
        return {
            "previous_volume": float(volume_series.iloc[0]) if len(volume_series) >= 1 else 0.0,
            "average_volume": float(volume_series.mean()) if len(volume_series) >= 1 else 0.0,
        }

    def fetch_top_assets(self, limit: int = 100) -> List[Dict[str, float]]:
        logger.info("Discovering top %s derivatives symbols by quote volume", limit)
        try:
            ticker_rows = self._request("ticker/24hr")
        except Exception as exc:
            logger.error("Error fetching top derivatives assets: %s", exc)
            return []

        sorted_assets = sorted(
            (
                row
                for row in ticker_rows
                if str(row.get("symbol", "")).endswith("USDT")
            ),
            key=lambda row: float(row.get("quoteVolume", 0) or 0),
            reverse=True,
        )
        results: List[Dict[str, float]] = []
        for row in sorted_assets[:limit]:
            raw_symbol = str(row.get("symbol", "")).upper()
            results.append(
                {
                    "raw_symbol": raw_symbol,
                    "asset": normalize_asset_symbol(raw_symbol),
                    "quote_volume_24h": float(row.get("quoteVolume", 0) or 0),
                    "base_volume_24h": float(row.get("volume", 0) or 0),
                    "trade_count_24h": float(row.get("count", 0) or 0),
                    "mark_price": float(row.get("lastPrice", 0) or 0),
                }
            )
        logger.info("Found %s assets for derivatives snapshots", len(results))
        return results

    def fetch_liquidation_structure(self, raw_symbol: str) -> Dict[str, float]:
        try:
            now_ms = int(time.time() * 1000)
            rows = self._request(
                "allForceOrders",
                {
                    "symbol": raw_symbol,
                    "startTime": now_ms - (15 * 60 * 1000),
                    "limit": 50,
                },
            )
        except Exception:
            return {
                "liquidations_long_usd": 0.0,
                "liquidations_short_usd": 0.0,
                "liquidations_total_usd": 0.0,
            }

        long_liq = 0.0
        short_liq = 0.0
        for row in rows or []:
            avg_price = float(row.get("averagePrice") or row.get("price") or 0)
            quantity = float(row.get("executedQty") or row.get("origQty") or 0)
            usd_value = avg_price * quantity
            side = str(row.get("side", "")).upper()
            if side == "SELL":
                long_liq += usd_value
            elif side == "BUY":
                short_liq += usd_value

        return {
            "liquidations_long_usd": long_liq,
            "liquidations_short_usd": short_liq,
            "liquidations_total_usd": long_liq + short_liq,
        }

    def fetch_long_short_ratio(self, raw_symbol: str) -> float:
        try:
            rows = self._request(
                "globalLongShortAccountRatio",
                {"symbol": raw_symbol, "period": "5m", "limit": 1},
            )
            if isinstance(rows, list) and rows:
                return float(rows[0].get("longShortRatio", 0) or 0)
        except Exception:
            pass
        return 0.0

    def fetch_snapshot_batch(self, symbols: List[Dict[str, float]]) -> List[Dict[str, float]]:
        logger.info("Capturing derivatives snapshots for %s assets", len(symbols))
        snapshots: List[Dict[str, float]] = []
        for item in symbols:
            raw_symbol = item["raw_symbol"]
            asset = item["asset"]
            try:
                funding_data = self._request("premiumIndex", {"symbol": raw_symbol})
                oi_data = self._request("openInterest", {"symbol": raw_symbol})
            except Exception as exc:
                logger.debug("Skipping %s because derivatives endpoints failed: %s", raw_symbol, exc)
                continue

            observed_epoch = time.time()
            bucket_iso = self._snapshot_bucket(observed_epoch)
            previous_volume = self._previous_volume_context(asset)
            volume_absolute = float(item.get("quote_volume_24h", 0) or 0)
            previous_abs = previous_volume["previous_volume"]
            average_abs = previous_volume["average_volume"]
            volume_change_pct = ((volume_absolute - previous_abs) / previous_abs * 100.0) if previous_abs else 0.0
            volume_relative = (volume_absolute / average_abs) if average_abs else 1.0
            liquidations = self.fetch_liquidation_structure(raw_symbol)
            long_short_ratio = self.fetch_long_short_ratio(raw_symbol)

            snapshot = {
                "snapshot_id": self._snapshot_id(asset, raw_symbol, bucket_iso),
                "observed_at": datetime.fromtimestamp(observed_epoch, tz=timezone.utc).isoformat(),
                "observation_bucket": bucket_iso,
                "asset": asset,
                "raw_symbol": raw_symbol,
                "venue": "binance_futures",
                "timeframe": "10m",
                "oi_raw": float(oi_data.get("openInterest", 0) or 0),
                "funding_rate": float(funding_data.get("lastFundingRate", 0) or 0),
                "long_short_ratio": long_short_ratio,
                "volume_absolute": volume_absolute,
                "volume_relative": volume_relative,
                "volume_change_pct": volume_change_pct,
                "base_volume_24h": float(item.get("base_volume_24h", 0) or 0),
                "trade_count_24h": float(item.get("trade_count_24h", 0) or 0),
                "mark_price": float(funding_data.get("markPrice", item.get("mark_price", 0)) or 0),
                **liquidations,
            }
            snapshots.append(snapshot)
        return snapshots

    def record_snapshots(self, snapshots: List[Dict[str, float]]) -> None:
        if not snapshots:
            return
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for snapshot in snapshots:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO derivatives_snapshots (
                        snapshot_id, observed_at, asset, raw_symbol, venue, timeframe,
                        open_interest, funding_rate, long_short_ratio,
                        liquidations_long_usd, liquidations_short_usd, liquidations_total_usd,
                        volume_absolute, volume_relative, volume_change_pct, volume_baseline_window,
                        mark_price, trade_count_24h, raw_payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot["snapshot_id"],
                        snapshot["observed_at"],
                        snapshot["asset"],
                        snapshot["raw_symbol"],
                        snapshot["venue"],
                        snapshot["timeframe"],
                        snapshot["oi_raw"],
                        snapshot["funding_rate"],
                        snapshot["long_short_ratio"],
                        snapshot["liquidations_long_usd"],
                        snapshot["liquidations_short_usd"],
                        snapshot["liquidations_total_usd"],
                        snapshot["volume_absolute"],
                        snapshot["volume_relative"],
                        snapshot["volume_change_pct"],
                        "rolling_20_snapshots",
                        snapshot["mark_price"],
                        snapshot["trade_count_24h"],
                        json.dumps(snapshot, sort_keys=True),
                    ),
                )
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO scout_deriv_snapshots (
                        id, timestamp, asset, oi_raw, funding_rate, liquidations_24h, long_short_ratio,
                        volume_24h, snapshot_id, raw_symbol, venue, timeframe, volume_absolute,
                        volume_relative, volume_change_pct, liquidations_long_usd, liquidations_short_usd,
                        observation_bucket
                    )
                    VALUES (
                        COALESCE((SELECT id FROM scout_deriv_snapshots WHERE snapshot_id = ?), NULL),
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        snapshot["snapshot_id"],
                        snapshot["observed_at"],
                        snapshot["asset"],
                        snapshot["oi_raw"],
                        snapshot["funding_rate"],
                        snapshot["liquidations_total_usd"],
                        snapshot["long_short_ratio"],
                        snapshot["volume_absolute"],
                        snapshot["snapshot_id"],
                        snapshot["raw_symbol"],
                        snapshot["venue"],
                        snapshot["timeframe"],
                        snapshot["volume_absolute"],
                        snapshot["volume_relative"],
                        snapshot["volume_change_pct"],
                        snapshot["liquidations_long_usd"],
                        snapshot["liquidations_short_usd"],
                        snapshot["observation_bucket"],
                    ),
                )
            conn.commit()
        logger.info("Recorded %s derivatives snapshots", len(snapshots))

    def run_snapshot_cycle(self) -> None:
        top_assets = self.fetch_top_assets(limit=50)
        snapshots = self.fetch_snapshot_batch(top_assets)
        self.record_snapshots(snapshots)

    def start(self, interval: int = 600) -> None:
        logger.info("Derivatives Scout is online. Heartbeat: %ss", interval)
        while True:
            self.run_snapshot_cycle()
            time.sleep(interval)


if __name__ == "__main__":
    scout = DerivativesScout()
    scout.run_snapshot_cycle()
