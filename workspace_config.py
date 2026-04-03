import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv


load_dotenv(dotenv_path=Path(".env"))


def _is_real(value: str) -> bool:
    return bool(value) and not value.startswith("replace_with_")


def _as_bool(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class WorkspaceConfig:
    notion_token: str
    slack_token: str
    scalp_board_db_id: str
    scalp_updates_db_id: str
    asset_library_db_id: str
    whale_registry_db_id: str
    wallet_activity_db_id: str
    validation_queue_db_id: str
    correlation_board_db_id: str
    decision_queue_db_id: str
    alerts_channel_id: str
    signals_channel_id: str
    scalp_updates_channel_id: str
    watchlist_updates_channel_id: str
    wallet_alerts_channel_id: str
    ops_channel_id: str
    blackbox_mode: str
    local_blackbox_path: str
    railway_mirror_enabled: bool
    railway_mirror_batch_size: int
    selected_assets_source: str
    selected_assets_file: str
    validation_batch_size: int
    enable_openvino_analysts: bool
    analyst_cache_ttl_seconds: int
    binance_futures_base_url: str
    cryptoapis_blockchain: str
    cryptoapis_network: str

    @property
    def notion_enabled(self) -> bool:
        return _is_real(self.notion_token)

    @property
    def slack_enabled(self) -> bool:
        return _is_real(self.slack_token)

    @property
    def databases(self) -> Dict[str, str]:
        return {
            "scalp_board": self.scalp_board_db_id,
            "scalp_updates": self.scalp_updates_db_id,
            "asset_library": self.asset_library_db_id,
            "whale_registry": self.whale_registry_db_id,
            "wallet_activity": self.wallet_activity_db_id,
            "validation_queue": self.validation_queue_db_id,
            "correlation_board": self.correlation_board_db_id,
            "decision_queue": self.decision_queue_db_id,
        }


def load_workspace_config() -> WorkspaceConfig:
    return WorkspaceConfig(
        notion_token=os.getenv("NOTION_TOKEN", ""),
        slack_token=os.getenv("SLACK_TOKEN", ""),
        scalp_board_db_id=os.getenv("SCALP_BOARD_DB_ID", ""),
        scalp_updates_db_id=os.getenv("SCALP_UPDATES_DB_ID", ""),
        asset_library_db_id=os.getenv("ASSET_LIBRARY_DB_ID", ""),
        whale_registry_db_id=os.getenv("WHALE_REGISTRY_DB_ID", ""),
        wallet_activity_db_id=os.getenv("WALLET_ACTIVITY_DB_ID", ""),
        validation_queue_db_id=os.getenv("VALIDATION_QUEUE_DB_ID", ""),
        correlation_board_db_id=os.getenv("CORRELATION_BOARD_DB_ID", ""),
        decision_queue_db_id=os.getenv("DECISION_QUEUE_DB_ID", ""),
        alerts_channel_id=os.getenv("ALERTS_CHANNEL_ID", ""),
        signals_channel_id=os.getenv("SIGNALS_CHANNEL_ID", ""),
        scalp_updates_channel_id=os.getenv("SCALP_UPDATES_CHANNEL_ID", ""),
        watchlist_updates_channel_id=os.getenv("WATCHLIST_UPDATES_CHANNEL_ID", ""),
        wallet_alerts_channel_id=os.getenv("WALLET_ALERTS_CHANNEL_ID", ""),
        ops_channel_id=os.getenv("OPS_CHANNEL_ID", ""),
        blackbox_mode=os.getenv("BLACKBOX_MODE", "local_first"),
        local_blackbox_path=os.getenv("LOCAL_BLACKBOX_PATH", "local_blackbox.sqlite"),
        railway_mirror_enabled=_as_bool(os.getenv("RAILWAY_MIRROR_ENABLED", "false")),
        railway_mirror_batch_size=int(os.getenv("RAILWAY_MIRROR_BATCH_SIZE", "250") or 250),
        selected_assets_source=os.getenv("SELECTED_ASSETS_SOURCE", "queue"),
        selected_assets_file=os.getenv("SELECTED_ASSETS_FILE", "runs/selected_assets.json"),
        validation_batch_size=int(os.getenv("VALIDATION_BATCH_SIZE", "25") or 25),
        enable_openvino_analysts=_as_bool(os.getenv("ENABLE_OPENVINO_ANALYSTS", "false")),
        analyst_cache_ttl_seconds=int(os.getenv("ANALYST_CACHE_TTL_SECONDS", "900") or 900),
        binance_futures_base_url=os.getenv("BINANCE_FUTURES_BASE_URL", "https://fapi.binance.com/fapi/v1"),
        cryptoapis_blockchain=os.getenv("CRYPTOAPIS_BLOCKCHAIN", "ethereum"),
        cryptoapis_network=os.getenv("CRYPTOAPIS_NETWORK", "mainnet"),
    )
