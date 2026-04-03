import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from blackbox_reader import BlackBoxReader
from notion_workspace_client import NotionWorkspaceClient
from workspace_config import load_workspace_config


class ValidationScout:
    def __init__(self):
        self.reader = BlackBoxReader()
        self.config = load_workspace_config()
        self.notion = NotionWorkspaceClient(self.config)

    def _support_label(self, supported: bool, conflicting: bool = False) -> str:
        if conflicting:
            return "conflicting"
        return "supportive" if supported else "neutral"

    def _selected_assets_from_file(self) -> List[Dict[str, Any]]:
        path = Path(self.config.selected_assets_file)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload if isinstance(payload, list) else payload.get("assets", [])
        results = []
        for item in items:
            if isinstance(item, str):
                results.append({"asset": item, "source_board": "file", "priority": 50, "reason": "file_selected"})
            elif isinstance(item, dict) and item.get("asset"):
                results.append(
                    {
                        "asset": item["asset"],
                        "source_board": item.get("source_board", "file"),
                        "priority": int(item.get("priority", 50) or 50),
                        "reason": item.get("reason", "file_selected"),
                    }
                )
        return results

    def _selected_assets_from_notion(self) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        db_map = {
            "validation_queue": self.config.validation_queue_db_id,
            "scalp_board": self.config.scalp_board_db_id,
            "asset_library": self.config.asset_library_db_id,
        }
        for board_name, database_id in db_map.items():
            if not self.notion.is_ready(database_id):
                continue
            try:
                pages = self.notion.query_database(database_id, {"page_size": self.config.validation_batch_size})
            except Exception:
                continue
            for page in pages:
                properties = page.get("properties", {})
                coin_property = properties.get("Coin")
                title_items = (coin_property or {}).get("title", [])
                if not title_items:
                    continue
                asset = title_items[0].get("plain_text") or title_items[0].get("text", {}).get("content")
                if asset:
                    selected.append(
                        {
                            "asset": asset,
                            "source_board": board_name,
                            "priority": 50,
                            "reason": f"notion_{board_name}",
                        }
                    )
        return selected

    def get_selected_assets(self, limit: int | None = None) -> List[Dict[str, Any]]:
        source = self.config.selected_assets_source.strip().lower()
        if source == "file":
            selected = self._selected_assets_from_file()
        elif source in {"queue", "blackbox"}:
            selected = self.reader.fetch_selected_assets(limit=limit or self.config.validation_batch_size)
        else:
            selected = self._selected_assets_from_notion()
            if not selected:
                selected = self.reader.fetch_selected_assets(limit=limit or self.config.validation_batch_size)

        deduped: Dict[str, Dict[str, Any]] = {}
        for item in selected:
            asset = str(item.get("asset") or "").strip().upper()
            if not asset:
                continue
            current = deduped.get(asset)
            if current is None or int(item.get("priority", 0) or 0) >= int(current.get("priority", 0) or 0):
                deduped[asset] = item
        ranked = sorted(deduped.values(), key=lambda item: int(item.get("priority", 0) or 0), reverse=True)
        return ranked[: limit or self.config.validation_batch_size]

    def validate(self, asset: str, source_board: str) -> Dict[str, Any]:
        whales = self.reader.recent_whale_events(asset, limit=10)
        wallet_tx = self.reader.recent_wallet_transactions(asset, limit=20)
        deriv = self.reader.latest_derivatives(asset, limit=10)
        sentiment = self.reader.recent_sentiment(asset=asset, limit=25)

        support = {
            "whales": "neutral",
            "wallets": "neutral",
            "derivatives": "neutral",
            "volume": "neutral",
            "sentiment": "neutral",
        }
        supportive_factors: List[str] = []
        conflicting_factors: List[str] = []

        if not whales.empty:
            whale_flow = float(whales["usd_value"].fillna(0).sum()) if "usd_value" in whales else 0.0
            support["whales"] = self._support_label(whale_flow >= 0)
            supportive_factors.append("whale_activity")

        if not wallet_tx.empty:
            wallet_flow = (
                float(pd.to_numeric(wallet_tx["usd_value"], errors="coerce").fillna(0.0).sum())
                if "usd_value" in wallet_tx
                else 0.0
            )
            has_wallet_support = len(wallet_tx) >= 2 or wallet_flow > 0
            support["wallets"] = self._support_label(has_wallet_support)
            if has_wallet_support:
                supportive_factors.append("tracked_wallet_participation")

        if not deriv.empty:
            latest = deriv.iloc[0].to_dict()
            funding = self.reader.safe_float(latest, "funding_rate")
            open_interest = self.reader.safe_float(latest, "oi_raw")
            volume_relative = self.reader.safe_float(latest, "volume_relative")
            volume_change_pct = self.reader.safe_float(latest, "volume_change_pct")
            derivatives_support = open_interest > 0 and funding > -0.01
            support["derivatives"] = self._support_label(derivatives_support, conflicting=funding > 0.03)
            support["volume"] = self._support_label(volume_relative >= 1.0 or volume_change_pct > 0)
            if derivatives_support:
                supportive_factors.append("derivatives_open_interest")
            if support["volume"] == "supportive":
                supportive_factors.append("volume_confirmation")
            if funding > 0.03:
                conflicting_factors.append("crowded_funding")

        if not sentiment.empty:
            sentiment_score = float(sentiment["raw_sentiment_score"].fillna(0).mean())
            if sentiment_score > 0.15:
                support["sentiment"] = "supportive"
                supportive_factors.append("positive_narrative_shift")
            elif sentiment_score < -0.15:
                support["sentiment"] = "conflicting"
                conflicting_factors.append("negative_narrative_shift")
            else:
                support["sentiment"] = "neutral"

        supportive_count = sum(1 for value in support.values() if value == "supportive")
        conflicting_count = sum(1 for value in support.values() if value == "conflicting")
        confidence = max(0, min(100, (supportive_count * 20) - (conflicting_count * 10) + 30))
        if conflicting_count >= 2:
            status = "invalidating"
        elif supportive_count >= 4:
            status = "supportive"
        elif supportive_count >= 2:
            status = "mixed"
        elif supportive_count >= 1:
            status = "weak"
        else:
            status = "invalidating"

        output = {
            "agent": "validation_scout",
            "asset": asset,
            "source_board": source_board,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "validation_status": status,
            "confidence": confidence,
            "support": support,
            "supportive_factors": supportive_factors,
            "conflicting_factors": conflicting_factors,
            "coverage": {
                "whale_events": int(len(whales)),
                "wallet_transactions": int(len(wallet_tx)),
                "derivatives_snapshots": int(len(deriv)),
                "sentiment_rows": int(len(sentiment)),
            },
            "summary": f"{asset} validation is {status} with {supportive_count} supportive and {conflicting_count} conflicting pillars.",
        }
        self.reader.cache_output(
            asset=asset,
            agent_name="validation_scout",
            opportunity_type=source_board,
            lifecycle_state=status,
            confidence_score=confidence,
            summary_text=output["summary"],
            output=output,
            target_database="validation_queue",
        )
        self.reader.mark_selected_asset_checked(asset, source_board, status)
        return output

    def run_queue(self, limit: int | None = None) -> List[Dict[str, Any]]:
        results = []
        for item in self.get_selected_assets(limit=limit):
            results.append(self.validate(item["asset"], item.get("source_board", "queue")))
        return results

    def validate_selected_assets(self, limit: int | None = None) -> List[Dict[str, Any]]:
        return self.run_queue(limit=limit)
