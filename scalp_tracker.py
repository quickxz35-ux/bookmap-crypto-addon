from datetime import datetime, timezone
from typing import Any, Dict

from blackbox_reader import BlackBoxReader
from lifecycle import transition_scalp_state


class ScalpTracker:
    def __init__(self):
        self.reader = BlackBoxReader()

    def refresh(self, setup: Dict[str, Any]) -> Dict[str, Any]:
        asset = setup["asset"]
        whales = self.reader.recent_whale_events(asset, limit=5)
        wallet_tx = self.reader.recent_wallet_transactions(asset, limit=10)
        deriv = self.reader.latest_derivatives(asset, limit=5)

        current_status = setup.get("status", "watch")
        update = {
            "agent": "scalp_tracker",
            "asset": asset,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "previous_status": current_status,
            "new_status": current_status,
            "confidence": setup.get("confidence", 0),
            "volume_state": setup.get("volume_state", "unavailable"),
            "what_changed": [],
        }

        proposed_status = current_status
        if not deriv.empty and len(deriv) >= 2:
            latest = deriv.iloc[0].to_dict()
            previous = deriv.iloc[1].to_dict()
            latest_oi = self.reader.safe_float(latest, "oi_raw")
            previous_oi = self.reader.safe_float(previous, "oi_raw")
            latest_volume = self.reader.safe_float(latest, "volume_absolute") or self.reader.safe_float(latest, "volume_24h")
            previous_volume = self.reader.safe_float(previous, "volume_absolute") or self.reader.safe_float(previous, "volume_24h")

            if previous_volume and latest_volume > previous_volume:
                update["volume_state"] = "expanding"
            elif previous_volume and latest_volume < previous_volume:
                update["volume_state"] = "cooling"

            if previous_oi and latest_oi > previous_oi and update["volume_state"] == "expanding":
                if current_status == "near_entry":
                    proposed_status = "triggered"
                elif current_status in {"triggered", "strengthening"}:
                    proposed_status = "strengthening"
                else:
                    proposed_status = "near_entry"
                update["confidence"] += 7
                update["what_changed"].append("Open interest and volume are still pushing higher.")
            elif previous_oi and latest_oi < previous_oi:
                proposed_status = "weakening"
                update["confidence"] -= 7
                update["what_changed"].append("Open interest has cooled since the last read.")

        if len(whales) > 0:
            update["what_changed"].append("Fresh whale evidence remains in play.")
            update["confidence"] += 5
        if len(wallet_tx) == 0:
            update["what_changed"].append("No recent tracked wallet participation.")
            update["confidence"] -= 3

        update["confidence"] = max(0, min(100, update["confidence"]))
        if update["confidence"] < 35:
            proposed_status = "invalid"

        update["new_status"] = transition_scalp_state(current_status, proposed_status)
        self.reader.cache_output(
            asset=asset,
            agent_name="scalp_tracker",
            opportunity_type="scalp",
            lifecycle_state=update["new_status"],
            confidence_score=update["confidence"],
            summary_text=" | ".join(update["what_changed"][:2]) or f"Tracker refreshed {asset}",
            output=update,
            target_database="scalp_updates",
        )
        return update
