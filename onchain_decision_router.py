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
    Handles the delivery of wallet intelligence rankings and whale-flow alerts.
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

    def _wallet_activity_database_id(self) -> str:
        return self.config.wallet_activity_db_id or self.config.whale_registry_db_id

    def _normalize_wallet_address(self, value: Any) -> str:
        text = self._coerce_text(value, "")
        return text.lower()

    def _short_wallet(self, wallet_address: str, size: int = 10) -> str:
        if not wallet_address:
            return ""
        return wallet_address[:size]

    def _coerce_number(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            if isinstance(value, str) and not value.strip():
                return default
            numeric = float(value)
            if numeric != numeric:  # NaN check
                return default
            return numeric
        except Exception:
            return default

    def _coerce_text(self, value: Any, default: str = "") -> str:
        if value is None:
            return default
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none"}:
            return default
        return text

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
        """Routes analyzed wallet metrics (from Hyperscreener) to the Whale Registry database."""
        wallet_address = self._normalize_wallet_address(stats.get("wallet_address"))
        if not wallet_address:
            return {"action": "error", "message": "Missing wallet_address"}

        input_hash = self._build_input_hash(stats)
        wallet_score = self._coerce_number(stats.get("wallet_score", 0))
        cache_id = self.reader.cache_output(
            asset=wallet_address,
            agent_name="onchain_router",
            opportunity_type="wallet_stats",
            lifecycle_state=stats.get("status", "unknown"),
            confidence_score=wallet_score,
            summary_text=f"Wallet {self._coerce_text(stats.get('alias'), 'Unknown')} ({self._coerce_text(stats.get('status'), 'watch')}) score: {wallet_score}",
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
                "Alias": rich_text(self._coerce_text(stats.get("alias"), "Unknown")),
                "Category": select(self._coerce_text(stats.get("category"), "Unclassified")),
                "Status": select(self._coerce_text(stats.get("status"), "watch")),
                "Score": number(wallet_score),
                "Win Rate": number(self._coerce_number(stats.get("win_rate", 0))),
                "Tx Count": number(self._coerce_number(stats.get("tx_count", 0))),
                "Net Flow": number(self._coerce_number(stats.get("net_flow_proxy", 0))),
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

    def route_wallet_discovery(self, discovery: Dict[str, Any]) -> Dict[str, Any]:
        """Routes a new or changed wallet leaderboard entry to the wallet activity database."""
        wallet_address = self._normalize_wallet_address(discovery.get("wallet_address"))
        if not wallet_address:
            return {"action": "error", "message": "Missing wallet_address"}

        change_type = str(discovery.get("change_type") or "NEW_WALLET").upper()
        input_hash = str(discovery.get("change_id") or self._build_input_hash(discovery))
        short_wallet = self._short_wallet(wallet_address)
        current_rank_value = int(self._coerce_number(discovery.get("current_rank", 0), 0))
        cache_id = self.reader.cache_output(
            asset=wallet_address,
            agent_name="onchain_router",
            opportunity_type="wallet_discovery",
            lifecycle_state=change_type.lower(),
            confidence_score=100.0 if change_type == "NEW_WALLET" else 70.0,
            summary_text=f"Discovery event for {wallet_address} ({change_type})",
            output=discovery,
            target_database="wallet_activity",
            input_hash=input_hash,
        )

        rank_label = str(current_rank_value) if current_rank_value > 0 else "n/a"
        title_value = f"WALLET DISCOVERY: {short_wallet} #{rank_label} {change_type} ({input_hash[:8]})"
        notion_result = self._upsert_notion_page(
            self._wallet_activity_database_id(),
            "Event",
            title_value,
            {
                "Event": title(title_value),
                "Wallet": rich_text(wallet_address),
                "Alias": rich_text(self._coerce_text(discovery.get("display_name"), short_wallet)),
                "Source": rich_text(self._coerce_text(discovery.get("source_provider"), "hyperscreener")),
                "Type": select("Wallet Discovery"),
                "Change Type": select(change_type),
                "Status": select("new" if change_type == "NEW_WALLET" else "updated"),
                "Current Rank": number(current_rank_value),
                "Previous Rank": number(self._coerce_number(discovery.get("previous_rank", 0))),
                "Rank Delta": number(self._coerce_number(discovery.get("rank_delta", 0))),
                "Account Value": number(self._coerce_number(discovery.get("account_value", 0))),
                "Timestamp": date_value(discovery.get("observed_at", datetime.now(timezone.utc).isoformat())),
            },
        )

        self.reader.update_delivery_state(cache_id, f"notion_{notion_result['action']}")
        return {"cache_id": cache_id, "notion": notion_result["action"]}

    def route_wallet_update(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """Routes a wallet transaction update to the wallet activity database."""
        wallet_address = self._normalize_wallet_address(update.get("wallet_address"))
        tx_hash = self._coerce_text(update.get("tx_hash"), "")
        if not wallet_address:
            return {"action": "error", "message": "Missing wallet_address"}
        if not tx_hash:
            return {"action": "error", "message": "Missing tx_hash"}

        tx_type = self._coerce_text(update.get("tx_type"), "TX").upper()
        input_hash = str(tx_hash)
        amount_usd_value = self._coerce_number(update.get("amount_usd", update.get("usd_value", 0)), 0.0)
        amount_value = self._coerce_number(update.get("amount", 1.0), 1.0)
        asset = self._coerce_text(update.get("asset"), "UNKNOWN")
        short_wallet = self._short_wallet(wallet_address)
        cache_id = self.reader.cache_output(
            asset=wallet_address,
            agent_name="onchain_router",
            opportunity_type="wallet_update",
            lifecycle_state=tx_type.lower(),
            confidence_score=min(100.0, abs(amount_usd_value) or abs(amount_value)),
            summary_text=f"Update event for {wallet_address} ({tx_type})",
            output=update,
            target_database="wallet_activity",
            input_hash=input_hash,
        )

        title_value = f"WALLET UPDATE: {short_wallet} {asset} {tx_type} ({tx_hash[:8]})"
        notion_result = self._upsert_notion_page(
            self._wallet_activity_database_id(),
            "Event",
            title_value,
            {
                "Event": title(title_value),
                "Wallet": rich_text(wallet_address),
                "Alias": rich_text(self._coerce_text(update.get("wallet_alias"), short_wallet)),
                "Source": rich_text(self._coerce_text(update.get("source_provider"), "hyperliquid")),
                "Type": select(tx_type),
                "Asset": select(asset),
                "USD Value": number(amount_usd_value),
                "Amount": number(self._coerce_number(update.get("amount", 0))),
                "Tx Hash": rich_text(tx_hash),
                "Counterparty": rich_text(self._coerce_text(update.get("counterparty"))),
                "Rank": number(self._coerce_number(update.get("wallet_rank", 0))),
                "Timestamp": date_value(update.get("observed_at", datetime.now(timezone.utc).isoformat())),
            },
        )

        self.reader.update_delivery_state(cache_id, f"notion_{notion_result['action']}")
        return {"cache_id": cache_id, "notion": notion_result["action"]}

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
