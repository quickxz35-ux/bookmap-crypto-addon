import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict
import re
import pandas as pd

from blackbox_reader import BlackBoxReader
from lifecycle import initial_long_term_state, normalize_long_term_state


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class LongTermCoinAnalyst:
    def __init__(self):
        self.reader = BlackBoxReader()

    def _asset_universe(self) -> list[str]:
        candidates: set[str] = set()
        with self.reader.db.get_connection() as conn:
            cursor = conn.cursor()
            queries = [
                "SELECT DISTINCT asset FROM derivatives_snapshots WHERE asset IS NOT NULL",
                "SELECT DISTINCT asset FROM scout_wallet_tx WHERE asset IS NOT NULL",
                "SELECT DISTINCT asset FROM sentiment_logs WHERE asset IS NOT NULL",
                "SELECT DISTINCT asset FROM selected_asset_queue WHERE asset IS NOT NULL",
            ]
            for query in queries:
                try:
                    cursor.execute(query)
                    for row in cursor.fetchall():
                        if isinstance(row, dict):
                            value = row.get("asset")
                        else:
                            value = row[0] if row else None
                        asset = str(value or "").strip().upper()
                        if asset and asset != "UNKNOWN" and ":" not in asset and re.fullmatch(r"[A-Z0-9]{2,15}", asset):
                            candidates.add(asset)
                except Exception:
                    continue
        return sorted(candidates)

    def analyze(self, asset: str) -> Dict[str, Any]:
        deriv = self.reader.latest_derivatives(asset, limit=30)
        whales = self.reader.recent_whale_events(asset, limit=20)
        wallet_tx = self.reader.recent_wallet_transactions(asset, limit=40)
        sentiment = self.reader.recent_sentiment(asset=asset, limit=50)

        result = {
            "agent": "long_term_coin_analyst",
            "asset": asset,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "bias": "neutral",
            "regime": "range",
            "status": "watch",
            "conviction": 35,
            "trend_quality": "developing",
            "volume_quality": "unavailable",
            "support": {
                "whales": "neutral",
                "wallets": "neutral",
                "narrative": "neutral",
            },
            "notes": [],
        }

        oi_avg = 0.0
        funding_avg = 0.0
        volume_avg = 0.0
        volume_relative_avg = 0.0

        if deriv.empty:
            result["notes"].append("No derivatives history yet for long-term review.")
            if len(whales) > 0:
                result["support"]["whales"] = "supportive"
                result["conviction"] += 15
                result["notes"].append("Recent whale activity exists for this coin.")
            if len(wallet_tx) >= 5:
                result["support"]["wallets"] = "supportive"
                result["conviction"] += 10
                result["notes"].append("Tracked holder activity exists for this coin.")
            if not sentiment.empty:
                series = sentiment["raw_sentiment_score"].iloc[:, 0] if isinstance(sentiment.get("raw_sentiment_score"), pd.DataFrame) else sentiment.get("raw_sentiment_score")
                sentiment_score = float(pd.to_numeric(series, errors="coerce").fillna(0).mean()) if series is not None else 0.0
                if sentiment_score > 0:
                    result["support"]["narrative"] = "supportive"
                    result["conviction"] += 8
                elif sentiment_score < 0:
                    result["support"]["narrative"] = "mixed"
            result["notes"].append("Using fallback long-term read until derivatives history arrives.")
        else:
            def _safe_mean(df_obj, col_name):
                if col_name not in df_obj:
                    return 0.0
                series = df_obj[col_name]
                if isinstance(series, pd.DataFrame):
                    series = series.iloc[:, 0]
                return float(pd.to_numeric(series, errors="coerce").fillna(0).mean())

            oi_avg = _safe_mean(deriv, "oi_raw")
            funding_avg = _safe_mean(deriv, "funding_rate")
            volume_avg = _safe_mean(deriv, "volume_absolute") if "volume_absolute" in deriv else _safe_mean(deriv, "volume_24h")
            volume_relative_avg = _safe_mean(deriv, "volume_relative")
            if volume_avg > 0 and volume_relative_avg >= 1:
                result["volume_quality"] = "healthy"
            elif volume_avg > 0:
                result["volume_quality"] = "stable"
            else:
                result["volume_quality"] = "unknown"

            if len(whales) > 0:
                result["support"]["whales"] = "supportive"
                result["conviction"] += 15
            if len(wallet_tx) >= 5:
                result["support"]["wallets"] = "supportive"
                result["conviction"] += 10
            if not sentiment.empty:
                series = sentiment["raw_sentiment_score"].iloc[:, 0] if isinstance(sentiment.get("raw_sentiment_score"), pd.DataFrame) else sentiment.get("raw_sentiment_score")
                sentiment_score = float(pd.to_numeric(series, errors="coerce").fillna(0).mean()) if series is not None else 0.0
                if sentiment_score > 0:
                    result["support"]["narrative"] = "supportive"
                    result["conviction"] += 8
                elif sentiment_score < 0:
                    result["support"]["narrative"] = "mixed"

            if oi_avg > 0 and funding_avg >= 0 and volume_relative_avg >= 1:
                result["bias"] = "bullish"
                result["regime"] = "trend_continuation"
                result["trend_quality"] = "strong"
                result["conviction"] += 20
            elif oi_avg > 0 and funding_avg < 0:
                result["bias"] = "bullish"
                result["regime"] = "accumulation"
                result["trend_quality"] = "constructive"
                result["conviction"] += 12
            elif funding_avg > 0.03:
                result["bias"] = "neutral"
                result["regime"] = "overheated"
                result["trend_quality"] = "fragile"
                result["conviction"] -= 5

        result["conviction"] = max(0, min(100, result["conviction"]))
        result["status"] = normalize_long_term_state(
            initial_long_term_state(result["conviction"], result["regime"], result["volume_quality"])
        )
        result["notes"].append(f"Average funding {funding_avg:.5f} with average OI {oi_avg:.2f}.")
        if volume_relative_avg:
            result["notes"].append(f"Average relative volume is {volume_relative_avg:.2f}x baseline.")

        self.reader.cache_output(
            asset=asset,
            agent_name="long_term_coin_analyst",
            opportunity_type="long_term",
            lifecycle_state=result["status"],
            confidence_score=result["conviction"],
            summary_text=" | ".join(result["notes"][:2]),
            output=result,
            target_database="asset_library",
        )
        return result

    def start(self, interval: int = 3600) -> None:
        """Pulse the long-term analyst cycle 24/7."""
        logger.info(f"🏎️ Long-Term Analyst is online. Audit cycle: {interval}s.")
        while True:
            assets = self._asset_universe()

            if not assets:
                logger.info("⏳ Waiting for asset activity to populate the workspace...")
            
            for asset in assets:
                try:
                    self.analyze(asset)
                except Exception as e:
                    logger.error(f"Error analyzing {asset}: {e}")
            
            time.sleep(interval)


if __name__ == "__main__":
    from worker_smoke import run_worker_smoke_check

    run_worker_smoke_check(
        "analyst-long-term",
        required_tables=("derivatives_snapshots", "sentiment_logs", "analyst_output_cache"),
    )
    analyst = LongTermCoinAnalyst()
    analyst.start()
