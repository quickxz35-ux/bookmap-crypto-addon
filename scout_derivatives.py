import hashlib
import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
import pandas as pd

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
        self.info_url = os.getenv("HYPERLIQUID_INFO_URL", "https://api.hyperliquid.xyz/info").rstrip("/")
        self.session = requests.Session()
        self.candidate_pool_limit = int(os.getenv("DERIVATIVES_CANDIDATE_POOL_LIMIT", "150"))

    def _request(self, endpoint: str, params: Optional[Dict[str, object]] = None):
        response = self.session.get(f"{self.base_url}/{endpoint.lstrip('/')}", params=params or {}, timeout=20)
        response.raise_for_status()
        return response.json()

    def _info_request(self, payload: Dict[str, object]):
        response = self.session.post(self.info_url, json=payload, timeout=20)
        response.raise_for_status()
        return response.json()

    def _snapshot_bucket(self, observed_epoch: float, interval_seconds: int = 600) -> str:
        bucket = int(math.floor(observed_epoch / interval_seconds) * interval_seconds)
        return datetime.fromtimestamp(bucket, tz=timezone.utc).isoformat()

    def _snapshot_id(self, asset: str, raw_symbol: str, bucket_iso: str) -> str:
        seed = f"{asset}|{raw_symbol}|hyperliquid_perps|10m|{bucket_iso}"
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()

    def _previous_volume_context(self, asset: str) -> Dict[str, float]:
        history = self.reader.latest_derivatives(asset, limit=20)
        if history.empty:
            return {"previous_volume": 0.0, "average_volume": 0.0}
        volume_series = history["volume_absolute"] if "volume_absolute" in history else history.get("volume_24h")
        if volume_series is None:
            return {"previous_volume": 0.0, "average_volume": 0.0}
        volume_series = pd.to_numeric(volume_series, errors="coerce").fillna(0.0).astype(float)
        return {
            "previous_volume": float(volume_series.iloc[0]) if len(volume_series) >= 1 else 0.0,
            "average_volume": float(volume_series.mean()) if len(volume_series) >= 1 else 0.0,
        }

    def _previous_open_interest_context(self, asset: str) -> Dict[str, float]:
        history = self.reader.latest_derivatives(asset, limit=20)
        if history.empty or "oi_raw" not in history:
            return {"previous_open_interest": 0.0, "open_interest_change_pct": 0.0}
        oi_series = pd.to_numeric(history["oi_raw"], errors="coerce").fillna(0.0).astype(float)
        previous_oi = float(oi_series.iloc[1]) if len(oi_series) >= 2 else 0.0
        current_oi = float(oi_series.iloc[0]) if len(oi_series) >= 1 else 0.0
        change_pct = ((current_oi - previous_oi) / previous_oi * 100.0) if previous_oi else 0.0
        return {
            "previous_open_interest": previous_oi,
            "open_interest_change_pct": change_pct,
        }

    def _current_open_interest(self, raw_symbol: str) -> float:
        return 0.0

    def fetch_top_assets(self, limit: int = 100) -> List[Dict[str, float]]:
        logger.info(
            "Discovering derivatives symbols from Hyperliquid top volume, high OI, and strong OI change (base pool %s, final limit %s)",
            self.candidate_pool_limit,
            limit,
        )
        try:
            response = self._info_request({"type": "metaAndAssetCtxs"})
        except Exception as exc:
            logger.error("Error fetching Hyperliquid derivatives assets: %s", exc)
            return []

        if not isinstance(response, list) or len(response) < 2:
            logger.error("Unexpected Hyperliquid perps response shape: %r", type(response))
            return []

        meta = response[0] or {}
        asset_ctxs = response[1] or []
        universe = meta.get("universe", []) if isinstance(meta, dict) else []
        paired_rows = list(zip(universe, asset_ctxs))
        if not paired_rows:
            logger.warning("Hyperliquid perps response returned no assets")
            return []

        enriched_rows: List[Dict[str, float]] = []
        for asset_meta, ctx in paired_rows:
            raw_symbol = str(asset_meta.get("name", "")).upper()
            if not raw_symbol:
                continue
            asset = normalize_asset_symbol(raw_symbol)
            current_oi = float(ctx.get("openInterest", 0) or 0)
            oi_context = self._previous_open_interest_context(asset)
            oi_change_pct = oi_context["open_interest_change_pct"]
            enriched_rows.append(
                {
                    "raw_symbol": raw_symbol,
                    "asset": asset,
                    "quote_volume_24h": float(ctx.get("dayNtlVlm", 0) or 0),
                    "base_volume_24h": float(ctx.get("dayBaseVlm", 0) or 0),
                    "trade_count_24h": float(ctx.get("trades", 0) or 0),
                    "mark_price": float(ctx.get("markPx", 0) or 0),
                    "funding_rate": float(ctx.get("funding", 0) or 0),
                    "open_interest_24h": current_oi,
                    "open_interest_change_pct": oi_change_pct,
                }
            )

        top_by_volume = sorted(enriched_rows, key=lambda row: row.get("quote_volume_24h", 0.0), reverse=True)[:limit]
        top_by_oi = sorted(enriched_rows, key=lambda row: row.get("open_interest_24h", 0.0), reverse=True)[:limit]
        top_by_oi_change = sorted(
            enriched_rows,
            key=lambda row: abs(row.get("open_interest_change_pct", 0.0)),
            reverse=True,
        )[:limit]

        combined: Dict[str, Dict[str, float]] = {}
        for source_name, rows in (
            ("volume", top_by_volume),
            ("open_interest", top_by_oi),
            ("open_interest_change", top_by_oi_change),
        ):
            for row in rows:
                raw_symbol = row["raw_symbol"]
                existing = combined.get(raw_symbol)
                if existing is None:
                    combined[raw_symbol] = {**row, "selection_sources": [source_name]}
                    continue
                existing_sources = set(existing.get("selection_sources", []))
                if source_name not in existing_sources:
                    existing_sources.add(source_name)
                    existing["selection_sources"] = sorted(existing_sources)
                existing["quote_volume_24h"] = max(existing.get("quote_volume_24h", 0.0), row.get("quote_volume_24h", 0.0))
                existing["open_interest_24h"] = max(existing.get("open_interest_24h", 0.0), row.get("open_interest_24h", 0.0))
                existing["open_interest_change_pct"] = row.get("open_interest_change_pct", existing.get("open_interest_change_pct", 0.0))
                existing["trade_count_24h"] = max(existing.get("trade_count_24h", 0.0), row.get("trade_count_24h", 0.0))
                existing["mark_price"] = row.get("mark_price", existing.get("mark_price", 0.0))

        results = list(combined.values())
        results.sort(
            key=lambda row: (
                len(row.get("selection_sources", [])),
                row.get("quote_volume_24h", 0.0),
                row.get("open_interest_24h", 0.0),
                abs(row.get("open_interest_change_pct", 0.0)),
            ),
            reverse=True,
        )

        logger.info(
            "Found %s assets for derivatives snapshots (%s volume, %s OI, %s OI-change candidates, %s unique)",
            len(top_by_volume),
            len(top_by_volume),
            len(top_by_oi),
            len(top_by_oi_change),
            len(results),
        )
        return results[:limit]

    def fetch_liquidation_structure(self, raw_symbol: str) -> Dict[str, float]:
        return {
            "liquidations_long_usd": 0.0,
            "liquidations_short_usd": 0.0,
            "liquidations_total_usd": 0.0,
        }

    def fetch_long_short_ratio(self, raw_symbol: str) -> float:
        return 0.0

    def fetch_snapshot_batch(self, symbols: List[Dict[str, float]]) -> List[Dict[str, float]]:
        logger.info("Capturing derivatives snapshots for %s assets", len(symbols))
        snapshots: List[Dict[str, float]] = []
        for item in symbols:
            raw_symbol = item["raw_symbol"]
            asset = item["asset"]
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
                "venue": "hyperliquid_perps",
                "timeframe": "10m",
                "oi_raw": float(item.get("open_interest_24h", 0) or 0),
                "funding_rate": float(item.get("funding_rate", 0) or 0),
                "long_short_ratio": long_short_ratio,
                "volume_absolute": volume_absolute,
                "volume_relative": volume_relative,
                "volume_change_pct": volume_change_pct,
                "base_volume_24h": float(item.get("base_volume_24h", 0) or 0),
                "trade_count_24h": float(item.get("trade_count_24h", 0) or 0),
                "mark_price": float(item.get("mark_price", 0) or 0),
                **liquidations,
            }
            snapshots.append(snapshot)
        return snapshots

    def record_snapshots(self, snapshots: List[Dict[str, float]]) -> None:
        if not snapshots:
            return
        ph = self.db.qmark
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for snapshot in snapshots:
                cursor.execute(
                    f"""
                    INSERT INTO derivatives_snapshots (
                        snapshot_id, observed_at, asset, venue, timeframe,
                        open_interest, funding_rate, long_short_ratio,
                        liquidations_total_usd, volume_change_pct, raw_payload_json
                    )
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    ON CONFLICT(snapshot_id) DO UPDATE SET
                        observed_at = excluded.observed_at,
                        asset = excluded.asset,
                        venue = excluded.venue,
                        timeframe = excluded.timeframe,
                        open_interest = excluded.open_interest,
                        funding_rate = excluded.funding_rate,
                        long_short_ratio = excluded.long_short_ratio,
                        liquidations_total_usd = excluded.liquidations_total_usd,
                        volume_change_pct = excluded.volume_change_pct,
                        raw_payload_json = excluded.raw_payload_json
                    """,
                    (
                        snapshot["snapshot_id"],
                        snapshot["observed_at"],
                        snapshot["asset"],
                        snapshot["venue"],
                        snapshot["timeframe"],
                        snapshot["oi_raw"],
                        snapshot["funding_rate"],
                        snapshot["long_short_ratio"],
                        snapshot["liquidations_total_usd"],
                        snapshot["volume_change_pct"],
                        json.dumps(snapshot, sort_keys=True),
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
    from worker_smoke import run_worker_smoke_check

    run_worker_smoke_check(
        "derivatives-scout",
        required_tables=("derivatives_snapshots",),
    )
    scout = DerivativesScout()
    scout.start()
