import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from blackbox_reader import BlackBoxReader
from notion_workspace_client import NotionWorkspaceClient, date_value, number, rich_text, select, title
from slack_workspace_client import SlackWorkspaceClient
from workspace_config import load_workspace_config


logger = logging.getLogger(__name__)


class DecisionRouter:
    def __init__(self):
        self.config = load_workspace_config()
        self.reader = BlackBoxReader()
        self.notion = NotionWorkspaceClient(self.config)
        self.slack = SlackWorkspaceClient(self.config)
        self.outbox_dir = Path("runs") / "workspace_router"
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def _persist(self, kind: str, payload: Dict[str, Any], input_hash: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self.outbox_dir / f"{timestamp}_{kind}_{payload['asset']}_{input_hash[:10]}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def _stable_payload(self, value: Any) -> Any:
        if isinstance(value, dict):
            ignored = {"generated_at", "created_at", "timestamp", "persisted_to", "delivered_at"}
            return {key: self._stable_payload(item) for key, item in value.items() if key not in ignored}
        if isinstance(value, list):
            return [self._stable_payload(item) for item in value]
        return value

    def _build_input_hash(self, payload: Dict[str, Any]) -> str:
        stable_payload = self._stable_payload(payload)
        return hashlib.sha1(json.dumps(stable_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _upsert_notion_page(
        self,
        database_id: str,
        title_property: str,
        title_value: str,
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self.notion.is_ready(database_id):
            return {"action": "skipped", "page_id": None}

        try:
            existing = self.notion.find_page_by_title(database_id, title_property, title_value)
            if existing:
                page_id = existing.get("id")
                self.notion.update_page(page_id, properties)
                return {"action": "updated", "page_id": page_id}

            created = self.notion.create_page(database_id, properties)
            return {"action": "created", "page_id": created.get("id") if created else None}
        except Exception as exc:
            logger.error("Notion upsert failed for %s in %s: %s", title_value, database_id, exc)
            return {"action": "failed", "page_id": None, "error": str(exc)}

    def _maybe_send_slack(self, channel: str, text: str, should_send: bool) -> str:
        if not should_send or not channel:
            return "skipped"
        try:
            return "sent" if self.slack.send_message(channel, text) else "failed"
        except Exception as exc:
            logger.error("Slack send failed: %s", exc)
            return "failed"

    def route_scalp(self, setup: Dict[str, Any], tracker: Dict[str, Any], correlation: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"setup": setup, "tracker": tracker, "correlation": correlation}
        input_hash = self._build_input_hash(payload)
        existing = self.reader.get_cached_output(setup["asset"], "decision_router", "scalp", input_hash=input_hash)
        duplicate = existing is not None and str(existing.get("delivery_status", "")).startswith("notion_")
        path = None if duplicate else self._persist("scalp", {"asset": setup["asset"], **payload}, input_hash)
        cache_id = self.reader.cache_output(
            asset=setup["asset"],
            agent_name="decision_router",
            opportunity_type="scalp",
            lifecycle_state=tracker.get("new_status", setup.get("status")),
            confidence_score=float(correlation.get("confidence", setup.get("confidence", 0)) or 0),
            summary_text=correlation.get("summary", ""),
            output={"asset": setup["asset"], **payload, "persisted_to": str(path) if path else None},
            target_database="scalp_board",
            input_hash=input_hash,
        )

        notion_result = {"action": "duplicate" if duplicate else "skipped", "page_id": None}
        if not duplicate:
            notion_result = self._upsert_notion_page(
                self.config.scalp_board_db_id,
                "Coin",
                setup["asset"],
                {
                    "Coin": title(setup["asset"]),
                    "Direction": select(setup["direction"]),
                    "Timeframe": select(setup["timeframe"]),
                    "Setup Type": select(setup["setup_type"]),
                    "Confidence": number(setup["confidence"]),
                    "Confluence": select(correlation["confluence_status"]),
                    "Status": select(tracker["new_status"]),
                    "Thesis": rich_text(" | ".join(setup.get("notes", [])[:3])),
                    "Last Update": date_value(setup["generated_at"]),
                },
            )
            self.reader.update_delivery_state(cache_id, f"notion_{notion_result['action']}")
        else:
            self.reader.update_delivery_state(cache_id, "duplicate")

        self.reader.upsert_selected_asset(
            asset=setup["asset"],
            source_board="scalp_board",
            opportunity_type="scalp",
            priority="high" if correlation.get("confidence", 0) >= 75 else "normal",
            status="active",
            requested_by="decision_router",
            payload={"asset": setup["asset"], **payload},
        )

        should_alert = (
            correlation["confluence_status"] == "confirmed"
            and tracker["new_status"] in {"near_entry", "triggered", "strengthening"}
        )
        slack_result = "duplicate" if duplicate else self._maybe_send_slack(
            self.config.signals_channel_id,
            (
                f"*{setup['asset']}* scalp {setup['direction']} | "
                f"{setup['setup_type']} | confidence {correlation['confidence']} | "
                f"status {tracker['new_status']}"
            ),
            should_alert,
        )
        if slack_result == "sent":
            self.reader.update_delivery_state(cache_id, "notion_synced_slack_sent")

        return {
            "cache_id": cache_id,
            "persisted_to": str(path) if path else None,
            "notion_action": notion_result["action"],
            "page_id": notion_result.get("page_id"),
            "slack_action": slack_result,
            "duplicate": duplicate,
        }

    def route_long_term(self, coin_view: Dict[str, Any], validation: Dict[str, Any], correlation: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"coin_view": coin_view, "validation": validation, "correlation": correlation}
        input_hash = self._build_input_hash(payload)
        existing = self.reader.get_cached_output(coin_view["asset"], "decision_router", "long_term", input_hash=input_hash)
        duplicate = existing is not None and str(existing.get("delivery_status", "")).startswith("notion_")
        path = None if duplicate else self._persist("long_term", {"asset": coin_view["asset"], **payload}, input_hash)
        cache_id = self.reader.cache_output(
            asset=coin_view["asset"],
            agent_name="decision_router",
            opportunity_type="long_term",
            lifecycle_state=coin_view.get("status"),
            confidence_score=float(correlation.get("confidence", coin_view.get("conviction", 0)) or 0),
            summary_text=correlation.get("summary", ""),
            output={"asset": coin_view["asset"], **payload, "persisted_to": str(path) if path else None},
            target_database="asset_library",
            input_hash=input_hash,
        )

        notion_result = {"action": "duplicate" if duplicate else "skipped", "page_id": None}
        if not duplicate:
            notion_result = self._upsert_notion_page(
                self.config.asset_library_db_id,
                "Coin",
                coin_view["asset"],
                {
                    "Coin": title(coin_view["asset"]),
                    "Bias": select(coin_view["bias"]),
                    "Regime": select(coin_view["regime"]),
                    "Conviction": number(coin_view["conviction"]),
                    "Status": select(coin_view["status"]),
                    "Thesis": rich_text(" | ".join(coin_view.get("notes", [])[:3])),
                    "Next Review": date_value(coin_view["generated_at"]),
                },
            )
            self.reader.update_delivery_state(cache_id, f"notion_{notion_result['action']}")
        else:
            self.reader.update_delivery_state(cache_id, "duplicate")

        self.reader.upsert_selected_asset(
            asset=coin_view["asset"],
            source_board="asset_library",
            opportunity_type="long_term",
            priority="high" if correlation.get("confidence", 0) >= 75 else "normal",
            status="active" if coin_view["status"] != "remove" else "archived",
            requested_by="decision_router",
            payload={"asset": coin_view["asset"], **payload},
        )

        should_alert = (
            correlation["confluence_status"] == "confirmed"
            and coin_view["status"] in {"promote", "breakout", "continuation"}
        )
        slack_result = "duplicate" if duplicate else self._maybe_send_slack(
            self.config.watchlist_updates_channel_id,
            (
                f"*{coin_view['asset']}* watchlist update | "
                f"{coin_view['bias']} {coin_view['regime']} | "
                f"conviction {correlation['confidence']} | status {coin_view['status']}"
            ),
            should_alert,
        )
        if slack_result == "sent":
            self.reader.update_delivery_state(cache_id, "notion_synced_slack_sent")

        return {
            "cache_id": cache_id,
            "persisted_to": str(path) if path else None,
            "notion_action": notion_result["action"],
            "page_id": notion_result.get("page_id"),
            "slack_action": slack_result,
            "duplicate": duplicate,
        }
