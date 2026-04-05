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

class OnChainDecisionRouter:
    """
    Specialized router for On-Chain Intelligence.
    Handles the delivery of Wallet Analyst rankings and Whale Scout strikes.
    """
    def __init__(self):
        self.config = load_workspace_config()
        self.reader = BlackBoxReader()
        self.notion = NotionWorkspaceClient(self.config)
        self.slack = SlackWorkspaceClient(self.config)
        self.outbox_dir = Path("runs") / "onchain_router"
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def _persist(self, kind: str, payload: Dict[str, Any], input_hash: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self.outbox_dir / f"{timestamp}_{kind}_{payload.get('asset', 'unknown')}_{input_hash[:10]}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def _build_input_hash(self, payload: Dict[str, Any]) -> str:
        ignored = {"generated_at", "created_at", "timestamp", "persisted_to", "delivered_at"}
        stable = {k: v for k, v in payload.items() if k not in ignored}
        return hashlib.sha1(json.dumps(stable, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _upsert_notion_page(self, database_id: str, title_property: str, title_value: str, properties: Dict[str, Any]) -> Dict[str, Any]:
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
            logger.error("Notion on-chain upsert failed for %s: %s", title_value, exc)
            return {"action": "failed", "page_id": None}

    def _maybe_send_slack(self, channel: str, text: str, should_send: bool) -> str:
        if not should_send or not channel: return "skipped"
        try:
            return "sent" if self.slack.send_message(channel, text) else "failed"
        except Exception as exc:
            logger.error("Slack on-chain send failed: %s", exc)
            return "failed"

    def route_wallet_stats(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Routes analyzed wallet metrics (from WalletAnalyst) to the Whale Registry database."""
        wallet_address = stats.get("wallet_address")
        if not wallet_address:
            return {"action": "error", "message": "Missing wallet_address"}

        input_hash = self._build_input_hash(stats)
        cache_id = self.reader.cache_output(
            asset=wallet_address,
            agent_name="onchain_router",
            opportunity_type="wallet_stats",
            lifecycle_state=stats.get("status", "unknown"),
            confidence_score=stats.get("wallet_score", 0),
            summary_text=f"Wallet {stats.get('alias')} ({stats.get('status')}) score: {stats.get('wallet_score')}",
            output=stats,
            target_database="whale_registry",
            input_hash=input_hash,
        )

        notion_result = self._upsert_notion_page(
            self.config.whale_registry_db_id,
            "Wallet",
            wallet_address,
            {
                "Wallet": title(wallet_address),
                "Alias": rich_text(stats.get("alias", "Unknown")),
                "Category": select(stats.get("category", "Unclassified")),
                "Status": select(stats.get("status", "watch")),
                "Score": number(stats.get("wallet_score", 0)),
                "Win Rate": number(stats.get("win_rate", 0)),
                "Tx Count": number(stats.get("tx_count", 0)),
                "Net Flow": number(stats.get("net_flow_proxy", 0)),
                "Last Seen": date_value(stats.get("generated_at", datetime.now(timezone.utc).isoformat())),
            },
        )
        
        self.reader.update_delivery_state(cache_id, f"notion_{notion_result['action']}")

        # Slack Alert for Elite Wallets
        should_alert = stats.get("status") == "elite"
        slack_result = self._maybe_send_slack(
            self.config.wallet_alerts_channel_id,
            f"🚨 *ELITE WALLET DETECTED* 🚨\nAlias: {stats.get('alias')}\nAddress: `{wallet_address}`\nScore: {stats.get('wallet_score')} | Win Rate: {stats.get('win_rate', 0):.2%}",
            should_alert
        )
        if slack_result == "sent":
            self.reader.update_delivery_state(cache_id, "notion_synced_slack_sent")

        return {"cache_id": cache_id, "notion": notion_result["action"], "slack": slack_result}

    def route_whale_strike(self, move: Dict[str, Any]) -> Dict[str, Any]:
        """Routes a single large Whale Move to the Whale Activity tracker."""
        asset = move.get("asset", "Unknown")
        database_id = getattr(self.config, "whale_activity_db_id", self.config.whale_registry_db_id)
        
        notion_result = self.notion.create_page(
            database_id,
            {
                "Event": title(f"WHALE STRIKE: {asset}"),
                "Asset": select(asset),
                "Source": rich_text(move.get("source", "Unknown")),
                "Type": select(move.get("move_type", "Unknown")),
                "USD Value": number(move.get("usd_value", 0)),
                "Amount": number(move.get("amount", 0)),
                "Timestamp": date_value(datetime.now(timezone.utc).isoformat()),
            }
        )
        
        slack_result = self._maybe_send_slack(
            self.config.wallet_alerts_channel_id,
            f"🐋 *WHALE STRIKE:* {asset} move of ${move.get('usd_value', 0):, .0f} detected from {move.get('source', 'Unknown')}.",
            move.get("usd_value", 0) > 1000000 
        )

        return {"notion": "created" if notion_result else "failed", "slack": slack_result}
