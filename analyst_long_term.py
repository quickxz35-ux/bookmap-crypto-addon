from datetime import datetime, timezone
from typing import Any, Dict

from blackbox_reader import BlackBoxReader
from lifecycle import initial_long_term_state, normalize_long_term_state


class LongTermCoinAnalyst:
    def __init__(self):
        self.reader = BlackBoxReader()

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

        if deriv.empty:
            result["notes"].append("No derivatives history yet for long-term review.")
            self.reader.cache_output(
                asset=asset,
                agent_name="long_term_coin_analyst",
                opportunity_type="long_term",
                lifecycle_state=result["status"],
                confidence_score=result["conviction"],
                summary_text=result["notes"][0],
                output=result,
                target_database="asset_library",
            )
            return result

        oi_avg = float(deriv["oi_raw"].fillna(0).astype(float).mean()) if "oi_raw" in deriv else 0.0
        funding_avg = float(deriv["funding_rate"].fillna(0).astype(float).mean()) if "funding_rate" in deriv else 0.0
        volume_avg = float(deriv["volume_absolute"].fillna(0).astype(float).mean()) if "volume_absolute" in deriv else float(deriv["volume_24h"].fillna(0).astype(float).mean())
        volume_relative_avg = float(deriv["volume_relative"].fillna(0).astype(float).mean()) if "volume_relative" in deriv else 0.0
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
            sentiment_score = float(sentiment["raw_sentiment_score"].fillna(0).mean())
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
