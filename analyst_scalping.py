import logging
from datetime import datetime, timezone
import time
from typing import Any, Dict
import re

from blackbox_reader import BlackBoxReader
from lifecycle import initial_scalp_state, normalize_scalp_state


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class ScalpingAnalyst:
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

    def analyze(self, asset: str, timeframe: str = "15m") -> Dict[str, Any]:
        deriv = self.reader.latest_derivatives(asset, limit=20)
        whales = self.reader.recent_whale_events(asset, limit=10)
        wallet_tx = self.reader.recent_wallet_transactions(asset, limit=20)

        result = {
            "agent": "scalping_analyst",
            "asset": asset,
            "timeframe": timeframe,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "new",
            "direction": "neutral",
            "setup_type": "no_setup",
            "entry_zone": "TBD",
            "invalidation": "Recent structure failure",
            "stop": "TBD",
            "target_1": "TBD",
            "target_2": "TBD",
            "confidence": 25,
            "volume_state": "unavailable",
            "support": {
                "whales": "neutral",
                "wallets": "neutral",
            },
            "notes": [],
        }

        if deriv.empty:
            result["notes"].append("Insufficient derivatives snapshots for a scalp read.")
            if len(whales) > 0:
                result["support"]["whales"] = "supportive"
                result["confidence"] += 10
                result["notes"].append("Recent whale activity exists for this coin.")
            if len(wallet_tx) > 0:
                result["support"]["wallets"] = "supportive"
                result["confidence"] += 5
                result["notes"].append("Tracked holder activity exists for this coin.")
            result["notes"].append("Using fallback scalp read until derivatives snapshots arrive.")
        else:
            latest = deriv.iloc[0].to_dict()
            previous = deriv.iloc[1].to_dict() if len(deriv) >= 2 else {}
            oi_now = self.reader.safe_float(latest, "oi_raw")
            oi_prev = self.reader.safe_float(previous, "oi_raw")
            funding = self.reader.safe_float(latest, "funding_rate")
            oi_change_pct = ((oi_now - oi_prev) / oi_prev * 100) if oi_prev else self.reader.safe_float(latest, "open_interest_change_pct")

            volume_now = self.reader.safe_float(latest, "volume_absolute") or self.reader.safe_float(latest, "volume_24h")
            volume_prev = self.reader.safe_float(previous, "volume_absolute") or self.reader.safe_float(previous, "volume_24h")
            volume_relative = self.reader.safe_float(latest, "volume_relative")
            if volume_relative >= 1.5 or (volume_now > 0 and volume_now >= volume_prev and volume_prev > 0):
                result["volume_state"] = "expanding"
            elif volume_now > 0 and volume_prev > 0 and volume_now < volume_prev:
                result["volume_state"] = "cooling"

            result["notes"].append(f"OI change {oi_change_pct:.2f}% with funding {funding:.5f}.")
            if volume_relative:
                result["notes"].append(f"Relative volume is {volume_relative:.2f}x baseline.")

            if oi_change_pct > 3 and funding >= 0 and result["volume_state"] == "expanding":
                result["direction"] = "long"
                result["setup_type"] = "momentum_continuation"
                result["confidence"] += 30
            elif oi_change_pct > 3 and funding < 0:
                result["direction"] = "long"
                result["setup_type"] = "short_squeeze_watch"
                result["confidence"] += 20
            elif oi_change_pct < -3 and result["volume_state"] in {"expanding", "cooling"}:
                result["direction"] = "short"
                result["setup_type"] = "trend_fade_or_flush"
                result["confidence"] += 18
            else:
                result["notes"].append("Derivatives profile is still choppy.")

            if result["volume_state"] == "expanding":
                result["confidence"] += 10

        result["confidence"] = max(0, min(100, result["confidence"]))
        result["status"] = normalize_scalp_state(initial_scalp_state(result["confidence"], result["volume_state"]))
        result["entry_zone"] = "Use micro pullback / trigger from execution layer"
        result["stop"] = "Recent structure low/high"
        result["target_1"] = "1R"
        result["target_2"] = "2R+"

        self.reader.cache_output(
            asset=asset,
            agent_name="scalping_analyst",
            opportunity_type="scalp",
            lifecycle_state=result["status"],
            confidence_score=result["confidence"],
            summary_text=" | ".join(result["notes"][:2]),
            output=result,
            target_database="scalp_board",
        )
        return result

    def start(self, interval: int = 900) -> None:
        """Pulse the scalping analyst cycle 24/7."""
        logger.info(f"🏎️ Scalping Analyst is online. Heartbeat: {interval}s.")
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
        "analyst-scalping",
        required_tables=("derivatives_snapshots", "analyst_output_cache"),
    )
    analyst = ScalpingAnalyst()
    analyst.start()
