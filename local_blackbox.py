import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import psycopg2
except ImportError:  # pragma: no cover - optional in some local environments
    psycopg2 = None


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _is_real(value: str) -> bool:
    return bool(value) and not value.startswith("replace_with_")


def _is_enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class LocalBlackBox:
    def __init__(self, db_path: Optional[str] = None):
        configured_path = db_path or os.getenv("LOCAL_BLACKBOX_PATH") or "local_blackbox.sqlite"
        self.db_path = str(Path(configured_path))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.mode = (os.getenv("BLACKBOX_MODE", "local_first") or "local_first").strip().lower()
        self.db_url = os.getenv("DATABASE_URL", "")
        self.mirror_enabled = (
            _is_enabled(os.getenv("RAILWAY_MIRROR_ENABLED", "false"))
            and _is_real(self.db_url)
            and psycopg2 is not None
        )
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_mirror_connection(self):
        if not self.mirror_enabled:
            return None
        return psycopg2.connect(self.db_url)

    def init_db(self) -> None:
        logger.info("Initializing Local Black Box at %s", self.db_path)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._create_schema_meta(cursor)
            self._create_legacy_tables(cursor)
            self._migrate_legacy_tables(cursor)
            self._create_normalized_tables(cursor)
            self._create_operational_tables(cursor)
            conn.commit()

    def _create_schema_meta(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name TEXT PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _create_legacy_tables(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scout_whale_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                asset TEXT NOT NULL,
                source TEXT,
                move_type TEXT,
                amount REAL,
                usd_value REAL,
                raw_payload TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scout_deriv_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                asset TEXT NOT NULL,
                oi_raw REAL,
                funding_rate REAL,
                liquidations_24h REAL,
                long_short_ratio REAL,
                net_position REAL,
                volume_15m REAL,
                volume_1h REAL,
                volume_4h REAL,
                volume_24h REAL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scout_sentiment_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                asset TEXT,
                source TEXT,
                headline TEXT,
                url TEXT,
                raw_sentiment_score REAL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scout_wallet_tx (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                wallet_address TEXT NOT NULL,
                tx_hash TEXT UNIQUE,
                asset TEXT,
                amount REAL,
                usd_value REAL,
                tx_type TEXT,
                counterparty TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS wallet_watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT UNIQUE,
                alias TEXT,
                category TEXT,
                is_active BOOLEAN DEFAULT 1,
                last_balance_check DATETIME
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS analyst_wallet_stats (
                wallet_address TEXT PRIMARY KEY,
                win_rate REAL,
                total_pnl_usd REAL,
                best_trade_ticker TEXT,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _migrate_legacy_tables(self, cursor: sqlite3.Cursor) -> None:
        legacy_deriv_columns = {
            "snapshot_id": "TEXT",
            "raw_symbol": "TEXT",
            "venue": "TEXT DEFAULT 'binance_futures'",
            "timeframe": "TEXT DEFAULT '10m'",
            "volume_absolute": "REAL",
            "volume_relative": "REAL",
            "volume_change_pct": "REAL",
            "liquidations_long_usd": "REAL",
            "liquidations_short_usd": "REAL",
            "observation_bucket": "TEXT",
        }
        legacy_sentiment_columns = {
            "story_id": "TEXT",
            "published_at": "DATETIME",
            "source_domain": "TEXT",
            "sentiment_label_raw": "TEXT",
            "topic_tags_json": "TEXT",
            "dedup_key": "TEXT",
            "raw_payload_json": "TEXT",
        }
        legacy_wallet_columns = {
            "action_type": "TEXT",
            "chain": "TEXT",
            "network": "TEXT",
            "price_at_event": "REAL",
            "protocol_name": "TEXT",
            "source_provider": "TEXT",
            "raw_payload_json": "TEXT",
        }
        for column, ddl in legacy_deriv_columns.items():
            self._ensure_column(cursor, "scout_deriv_snapshots", column, ddl)
        for column, ddl in legacy_sentiment_columns.items():
            self._ensure_column(cursor, "scout_sentiment_log", column, ddl)
        for column, ddl in legacy_wallet_columns.items():
            self._ensure_column(cursor, "scout_wallet_tx", column, ddl)

        self._ensure_column(cursor, "analyst_wallet_stats", "status", "TEXT")
        self._ensure_column(cursor, "analyst_wallet_stats", "score", "REAL")
        self._ensure_column(cursor, "analyst_wallet_stats", "tx_count", "INTEGER")
        self._ensure_column(cursor, "analyst_wallet_stats", "asset_count", "INTEGER")
        self._ensure_column(cursor, "analyst_wallet_stats", "active_days", "INTEGER")

    def _create_normalized_tables(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS whale_events (
                event_id TEXT PRIMARY KEY,
                observed_at DATETIME NOT NULL,
                ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                asset TEXT NOT NULL,
                chain TEXT,
                source_provider TEXT NOT NULL,
                entity_label TEXT,
                wallet_address TEXT,
                counterparty_address TEXT,
                event_type TEXT NOT NULL,
                flow_direction TEXT,
                amount_native REAL,
                amount_usd REAL,
                price_at_event REAL,
                exchange_name TEXT,
                confidence_raw REAL,
                tags_json TEXT,
                raw_payload_json TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS whale_events_asset_observed_idx ON whale_events (asset, observed_at DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS whale_events_wallet_observed_idx ON whale_events (wallet_address, observed_at DESC)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS wallet_transactions (
                tx_id TEXT PRIMARY KEY,
                observed_at DATETIME NOT NULL,
                ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                wallet_address TEXT NOT NULL,
                wallet_alias TEXT,
                chain TEXT,
                network TEXT,
                asset TEXT,
                action_type TEXT NOT NULL,
                amount_native REAL,
                amount_usd REAL,
                price_at_event REAL,
                counterparty_address TEXT,
                protocol_name TEXT,
                tx_hash TEXT,
                block_number INTEGER,
                fee_native REAL,
                source_provider TEXT NOT NULL,
                raw_payload_json TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS wallet_transactions_wallet_observed_idx ON wallet_transactions (wallet_address, observed_at DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS wallet_transactions_asset_observed_idx ON wallet_transactions (asset, observed_at DESC)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS derivatives_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                observed_at DATETIME NOT NULL,
                ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                asset TEXT NOT NULL,
                raw_symbol TEXT,
                venue TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_interest REAL,
                open_interest_change_pct REAL,
                funding_rate REAL,
                long_short_ratio REAL,
                liquidations_long_usd REAL,
                liquidations_short_usd REAL,
                liquidations_total_usd REAL,
                volume_absolute REAL,
                volume_relative REAL,
                volume_change_pct REAL,
                volume_baseline_window TEXT,
                basis REAL,
                mark_price REAL,
                trade_count_24h REAL,
                tags_json TEXT,
                raw_payload_json TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS derivatives_snapshots_asset_observed_idx ON derivatives_snapshots (asset, observed_at DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS derivatives_snapshots_asset_timeframe_idx ON derivatives_snapshots (asset, timeframe, observed_at DESC)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sentiment_logs (
                story_id TEXT PRIMARY KEY,
                published_at DATETIME NOT NULL,
                ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                asset TEXT,
                source_provider TEXT NOT NULL,
                source_domain TEXT,
                headline TEXT NOT NULL,
                url TEXT,
                sentiment_label_raw TEXT,
                sentiment_score_raw REAL,
                topic_tags_json TEXT,
                language TEXT,
                dedup_key TEXT,
                raw_payload_json TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS sentiment_logs_asset_published_idx ON sentiment_logs (asset, published_at DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS sentiment_logs_dedup_idx ON sentiment_logs (dedup_key)"
        )

    def _create_operational_tables(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS analyst_output_cache (
                cache_id TEXT PRIMARY KEY,
                generated_at DATETIME NOT NULL,
                asset TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                opportunity_type TEXT NOT NULL,
                lifecycle_state TEXT,
                confidence_score REAL,
                summary_text TEXT,
                input_hash TEXT,
                output_json TEXT NOT NULL,
                target_database TEXT,
                delivery_status TEXT NOT NULL DEFAULT 'pending',
                delivered_at DATETIME
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS analyst_output_cache_asset_idx ON analyst_output_cache (asset, generated_at DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS analyst_output_cache_agent_idx ON analyst_output_cache (agent_name, generated_at DESC)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS selected_asset_queue (
                queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                source_board TEXT NOT NULL,
                priority INTEGER DEFAULT 50,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_checked_at DATETIME,
                last_validation_status TEXT,
                UNIQUE(asset, source_board)
            )
            """
        )
        self._ensure_column(cursor, "selected_asset_queue", "queue_key", "TEXT")
        self._ensure_column(cursor, "selected_asset_queue", "opportunity_type", "TEXT")
        self._ensure_column(cursor, "selected_asset_queue", "requested_by", "TEXT")
        self._ensure_column(cursor, "selected_asset_queue", "payload_json", "TEXT")
        self._ensure_column(cursor, "selected_asset_queue", "last_validated_at", "DATETIME")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS selected_asset_queue_status_idx ON selected_asset_queue (status, priority DESC, updated_at DESC)"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS selected_asset_queue_queue_key_idx ON selected_asset_queue (queue_key)"
        )

    def _ensure_column(self, cursor: sqlite3.Cursor, table_name: str, column_name: str, column_ddl: str) -> None:
        columns = {row["name"] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}")

    def cache_analyst_output(
        self,
        *,
        asset: str,
        agent_name: str,
        opportunity_type: str,
        lifecycle_state: Optional[str],
        confidence_score: float,
        summary_text: str,
        output: Dict[str, Any],
        target_database: str = "",
        input_hash: str = "",
    ) -> str:
        normalized_json = json.dumps(output, sort_keys=True, default=str)
        cache_id = hashlib.sha1(normalized_json.encode("utf-8")).hexdigest()
        generated_at = output.get("generated_at") or output.get("created_at") or output.get("timestamp")
        generated_at = generated_at or datetime.utcnow().isoformat()

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO analyst_output_cache (
                    cache_id, generated_at, asset, agent_name, opportunity_type, lifecycle_state,
                    confidence_score, summary_text, input_hash, output_json, target_database, delivery_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                    (SELECT delivery_status FROM analyst_output_cache WHERE cache_id = ?), 'cached'
                ))
                ON CONFLICT(cache_id) DO UPDATE SET
                    generated_at = excluded.generated_at,
                    lifecycle_state = excluded.lifecycle_state,
                    confidence_score = excluded.confidence_score,
                    summary_text = excluded.summary_text,
                    input_hash = excluded.input_hash,
                    output_json = excluded.output_json,
                    target_database = excluded.target_database
                """,
                (
                    cache_id,
                    generated_at,
                    asset,
                    agent_name,
                    opportunity_type,
                    lifecycle_state,
                    confidence_score,
                    summary_text,
                    input_hash,
                    normalized_json,
                    target_database,
                    cache_id,
                ),
            )
            conn.commit()
        return cache_id

    def update_cache_delivery(self, cache_id: str, delivery_status: str) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE analyst_output_cache
                SET delivery_status = ?, delivered_at = CURRENT_TIMESTAMP
                WHERE cache_id = ?
                """,
                (delivery_status, cache_id),
            )
            conn.commit()

    def get_cached_output(
        self,
        asset: str,
        agent_name: str,
        opportunity_type: str,
        input_hash: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        query = """
            SELECT *
            FROM analyst_output_cache
            WHERE asset = ? AND agent_name = ? AND opportunity_type = ?
        """
        params: List[Any] = [asset, agent_name, opportunity_type]
        if input_hash:
            query += " AND input_hash = ?"
            params.append(input_hash)
        query += " ORDER BY generated_at DESC LIMIT 1"

        with self.get_connection() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        if not row:
            return None
        record = dict(row)
        if record.get("output_json"):
            record["output_json"] = json.loads(record["output_json"])
        return record

    def upsert_analyst_output(
        self,
        *,
        cache_id: str,
        generated_at: str,
        asset: str,
        agent_name: str,
        opportunity_type: str,
        lifecycle_state: Optional[str],
        confidence_score: float,
        summary_text: str,
        input_hash: str,
        output_json: Dict[str, Any],
        target_database: str,
        delivery_status: str = "pending",
        delivered_at: Optional[str] = None,
    ) -> None:
        normalized_json = json.dumps(output_json, sort_keys=True, default=str)
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO analyst_output_cache (
                    cache_id, generated_at, asset, agent_name, opportunity_type, lifecycle_state,
                    confidence_score, summary_text, input_hash, output_json, target_database,
                    delivery_status, delivered_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_id) DO UPDATE SET
                    generated_at = excluded.generated_at,
                    lifecycle_state = excluded.lifecycle_state,
                    confidence_score = excluded.confidence_score,
                    summary_text = excluded.summary_text,
                    input_hash = excluded.input_hash,
                    output_json = excluded.output_json,
                    target_database = excluded.target_database,
                    delivery_status = excluded.delivery_status,
                    delivered_at = excluded.delivered_at
                """,
                (
                    cache_id,
                    generated_at,
                    asset,
                    agent_name,
                    opportunity_type,
                    lifecycle_state,
                    confidence_score,
                    summary_text,
                    input_hash,
                    normalized_json,
                    target_database,
                    delivery_status,
                    delivered_at,
                ),
            )
            conn.commit()

    def enqueue_selected_asset(
        self,
        asset: str,
        source_board: str,
        reason: str = "",
        priority: int = 50,
        status: str = "pending",
    ) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO selected_asset_queue (asset, source_board, priority, reason, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(asset, source_board) DO UPDATE SET
                    priority = excluded.priority,
                    reason = excluded.reason,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (asset, source_board, priority, reason, status),
            )
            conn.commit()

    def upsert_selected_asset(
        self,
        *,
        asset: str,
        source_board: str,
        opportunity_type: str,
        priority: str = "normal",
        status: str = "pending",
        requested_by: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        queue_key = f"{asset.lower()}::{source_board}::{opportunity_type}"
        priority_value = {
            "critical": 100,
            "high": 75,
            "normal": 50,
            "low": 25,
        }.get(priority, 50)
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO selected_asset_queue (
                    queue_key, asset, source_board, opportunity_type, priority, status,
                    requested_by, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset, source_board) DO UPDATE SET
                    queue_key = excluded.queue_key,
                    opportunity_type = excluded.opportunity_type,
                    priority = excluded.priority,
                    status = excluded.status,
                    requested_by = excluded.requested_by,
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    queue_key,
                    asset,
                    source_board,
                    opportunity_type,
                    priority_value,
                    status,
                    requested_by,
                    json.dumps(payload or {}, sort_keys=True, default=str),
                ),
            )
            conn.commit()
        return queue_key

    def fetch_selected_assets(self, limit: int = 25, statuses: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
        status_values = tuple(statuses or ("pending", "active"))
        placeholders = ",".join("?" for _ in status_values)
        query = f"""
            SELECT
                queue_key,
                asset,
                source_board,
                opportunity_type,
                priority,
                reason,
                status,
                requested_by,
                payload_json,
                created_at,
                updated_at,
                last_checked_at,
                last_validation_status,
                last_validated_at
            FROM selected_asset_queue
            WHERE status IN ({placeholders})
            ORDER BY priority DESC, updated_at DESC
            LIMIT ?
        """
        with self.get_connection() as conn:
            rows = conn.execute(query, (*status_values, limit)).fetchall()
        return [dict(row) for row in rows]

    def mark_selected_asset_checked(self, asset: str, source_board: str, validation_status: str) -> None:
        next_status = "active" if validation_status in {"supportive", "mixed", "weak"} else "archived"
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE selected_asset_queue
                SET last_checked_at = CURRENT_TIMESTAMP,
                    last_validation_status = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE asset = ? AND source_board = ?
                """,
                (validation_status, next_status, asset, source_board),
            )
            conn.commit()

    def mark_selected_asset_validated(self, queue_key: str, status: str = "validated") -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE selected_asset_queue
                SET last_checked_at = CURRENT_TIMESTAMP,
                    last_validated_at = CURRENT_TIMESTAMP,
                    last_validation_status = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE queue_key = ?
                """,
                (status, status, queue_key),
            )
            conn.commit()

    def mark_output_delivered(self, cache_id: str, delivery_status: str = "delivered") -> None:
        self.update_cache_delivery(cache_id, delivery_status)


if __name__ == "__main__":
    LocalBlackBox()
