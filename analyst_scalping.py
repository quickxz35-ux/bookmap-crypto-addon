from datetime import datetime, timezone
from typing import Any, Dict

from blackbox_reader import BlackBoxReader
from lifecycle import initial_scalp_state, normalize_scalp_state


class ScalpingAnalyst:
    def __init__(self):
        self.reader = BlackBoxReader()

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
            self.reader.cache_output(
                asset=asset,
                agent_name="scalping_analyst",
                opportunity_type="scalp",
                lifecycle_state=result["status"],
                confidence_score=result["confidence"],
                summary_text=result["notes"][0],
                output=result,
            )
            return result

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

        if len(whales) > 0:
            result["support"]["whales"] = "supportive"
            result["confidence"] += 10
            result["notes"].append("Recent whale activity exists for this coin.")

        if len(wallet_tx) > 0:
            result["support"]["wallets"] = "supportive"
            result["confidence"] += 5
            result["notes"].append("Tracked wallet activity exists for this coin.")

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
