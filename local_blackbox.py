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
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover - optional in some local environments
    psycopg2 = None
    RealDictCursor = None


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _is_real(value: str) -> bool:
    return bool(value) and not value.startswith("replace_with_")


def _is_enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class LocalBlackBox:
    def __init__(self, db_path: Optional[str] = None):
        # Database URL detection (Primary for Railway)
        self.db_url = os.getenv("DATABASE_URL", "")
        self.is_postgres = _is_real(self.db_url) and psycopg2 is not None
        self._pg_conn = None
        
        # Fallback to SQLite for local development
        configured_path = db_path or os.getenv("LOCAL_BLACKBOX_PATH") or "local_blackbox.sqlite"
        self.db_path = str(Path(configured_path))
        if not self.is_postgres:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.init_db()

    def get_connection(self):
        """Returns a connection to Postgres on Railway or SQLite locally."""
        if self.is_postgres:
            if self._pg_conn is None or self._pg_conn.closed:
                self._pg_conn = psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)
            return self._pg_conn
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @property
    def qmark(self) -> str:
        """Returns the correct parameter placeholder for the active database."""
        return "%s" if self.is_postgres else "?"

    def init_db(self) -> None:
        """Creates the necessary tables in either Postgres or SQLite."""
        db_type = "Postgres" if self.is_postgres else "SQLite"
        logger.info(f"Initializing Shared Brain via {db_type}")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Universal Schema (Compatible with both)
            auto_inc = "SERIAL PRIMARY KEY" if self.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
            text_type = "TEXT"
            ts_type = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if self.is_postgres else "DATETIME DEFAULT CURRENT_TIMESTAMP"

            # 🐋 Whale Log
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS scout_whale_log (
                    id {auto_inc},
                    timestamp {ts_type},
                    asset {text_type} NOT NULL,
                    source {text_type},
                    move_type {text_type},
                    amount REAL,
                    usd_value REAL,
                    raw_payload {text_type}
                )
            """)

            # 📈 Derivatives Snapshots
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS derivatives_snapshots (
                    snapshot_id {text_type} PRIMARY KEY,
                    observed_at {ts_type},
                    asset {text_type} NOT NULL,
                    venue {text_type} NOT NULL,
                    timeframe {text_type} NOT NULL,
                    open_interest REAL,
                    funding_rate REAL,
                    long_short_ratio REAL,
                    liquidations_total_usd REAL,
                    volume_change_pct REAL,
                    raw_payload_json {text_type} NOT NULL
                )
            """)

            # 📰 Sentiment Logs
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS sentiment_logs (
                    story_id {text_type} PRIMARY KEY,
                    published_at {ts_type},
                    asset {text_type},
                    source_provider {text_type} NOT NULL,
                    headline {text_type} NOT NULL,
                    url {text_type},
                    sentiment_score_raw REAL,
                    raw_payload_json {text_type} NOT NULL
                )
            """)
            
            # 📬 Analyst Output Cache (The Output Bulletin Board)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS analyst_output_cache (
                    cache_id {text_type} PRIMARY KEY,
                    generated_at {ts_type},
                    asset {text_type} NOT NULL,
                    agent_name {text_type} NOT NULL,
                    opportunity_type {text_type} NOT NULL,
                    lifecycle_state {text_type},
                    confidence_score REAL,
                    summary_text {text_type},
                    output_json {text_type} NOT NULL,
                    delivery_status {text_type} NOT NULL DEFAULT 'pending'
                )
            """)

            # 🛰️ Hyperscreener wallet discovery snapshots
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS wallet_leaderboard_snapshots (
                    snapshot_id {text_type} PRIMARY KEY,
                    observed_at {ts_type},
                    source_provider {text_type} NOT NULL,
                    source_url {text_type},
                    wallet_address {text_type} NOT NULL,
                    display_name {text_type},
                    rank INTEGER,
                    account_value REAL,
                    is_new_wallet INTEGER DEFAULT 0,
                    raw_payload_json {text_type} NOT NULL
                )
            """)

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS wallet_leaderboard_changes (
                    change_id {text_type} PRIMARY KEY,
                    observed_at {ts_type},
                    source_provider {text_type} NOT NULL,
                    wallet_address {text_type} NOT NULL,
                    display_name {text_type},
                    previous_rank INTEGER,
                    current_rank INTEGER,
                    change_type {text_type} NOT NULL,
                    raw_payload_json {text_type} NOT NULL
                )
            """)

            # Existing watchlist store, extended with Hyperscreener metadata.
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS wallet_watchlist (
                    id {auto_inc},
                    wallet_address {text_type} UNIQUE,
                    alias {text_type},
                    category {text_type},
                    is_active INTEGER DEFAULT 1,
                    last_balance_check {ts_type}
                )
            """)

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS scout_wallet_tx (
                    id {auto_inc},
                    timestamp {ts_type},
                    wallet_address {text_type} NOT NULL,
                    tx_hash {text_type} UNIQUE,
                    asset {text_type},
                    amount REAL,
                    usd_value REAL,
                    tx_type {text_type},
                    counterparty {text_type}
                )
            """)

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS analyst_wallet_stats (
                    wallet_address {text_type} PRIMARY KEY,
                    win_rate REAL,
                    total_pnl_usd REAL,
                    best_trade_ticker {text_type},
                    last_updated {ts_type}
                )
            """)

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS selected_asset_queue (
                    queue_id {auto_inc},
                    queue_key {text_type},
                    asset {text_type} NOT NULL,
                    source_board {text_type} NOT NULL,
                    opportunity_type {text_type},
                    priority INTEGER DEFAULT 50,
                    reason {text_type},
                    status {text_type} NOT NULL DEFAULT 'pending',
                    requested_by {text_type},
                    payload_json {text_type},
                    created_at {ts_type},
                    updated_at {ts_type},
                    last_checked_at TIMESTAMP,
                    last_validation_status {text_type},
                    last_validated_at TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS selected_asset_queue_asset_source_idx ON selected_asset_queue (asset, source_board)"
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS selected_asset_queue_queue_key_idx ON selected_asset_queue (queue_key)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS selected_asset_queue_status_idx ON selected_asset_queue (status, priority DESC, updated_at DESC)"
            )

            for table_name, columns in {
                "wallet_watchlist": {
                    "source_provider": "TEXT",
                    "display_name": "TEXT",
                    "top_rank": "INTEGER",
                    "account_value": "REAL",
                    "first_seen_at": "DATETIME",
                    "last_seen_at": "DATETIME",
                },
                "scout_wallet_tx": {
                    "source_provider": "TEXT",
                    "wallet_rank": "INTEGER",
                    "leaderboard_snapshot_at": "DATETIME",
                    "raw_payload_json": "TEXT",
                },
                "analyst_wallet_stats": {
                    "status": "TEXT",
                    "score": "REAL",
                    "tx_count": "INTEGER",
                    "asset_count": "INTEGER",
                    "active_days": "INTEGER",
                },
            }.items():
                for column_name, column_ddl in columns.items():
                    self._ensure_column(cursor, table_name, column_name, column_ddl)

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
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS selected_asset_queue_asset_source_idx ON selected_asset_queue (asset, source_board)"
        )

    def _ensure_column(self, cursor: sqlite3.Cursor, table_name: str, column_name: str, column_ddl: str) -> None:
        if self.is_postgres:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
                """,
                (table_name,),
            )
            columns = {row["column_name"] for row in cursor.fetchall()}
        else:
            columns = {row["name"] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}
        if column_name not in columns:
            ddl = column_ddl
            if self.is_postgres:
                # SQLite-style migrations use DATETIME, which Postgres does not accept.
                # Normalize those additions to a native timestamp type while preserving defaults.
                ddl = ddl.replace("DATETIME", "TIMESTAMP")
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")

    def _placeholder(self) -> str:
        return "%s" if self.is_postgres else "?"

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
        delivery_status: str = "cached",
    ) -> str:
        normalized_json = json.dumps(output, sort_keys=True, default=str)
        cache_id = hashlib.sha1(normalized_json.encode("utf-8")).hexdigest()
        generated_at = output.get("generated_at") or output.get("created_at") or output.get("timestamp")
        generated_at = generated_at or datetime.utcnow().isoformat()
        ph = self._placeholder()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                INSERT INTO analyst_output_cache (
                    cache_id, generated_at, asset, agent_name, opportunity_type, lifecycle_state,
                    confidence_score, summary_text, input_hash, output_json, target_database, delivery_status
                )
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, COALESCE(
                    (SELECT delivery_status FROM analyst_output_cache WHERE cache_id = {ph}), {ph}
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
                    delivery_status,
                ),
            )
            conn.commit()
        return cache_id

    def update_cache_delivery(self, cache_id: str, delivery_status: str) -> None:
        ph = self._placeholder()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                UPDATE analyst_output_cache
                SET delivery_status = {ph}, delivered_at = CURRENT_TIMESTAMP
                WHERE cache_id = {ph}
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
        ph = self._placeholder()
        query = f"""
            SELECT *
            FROM analyst_output_cache
            WHERE asset = {ph} AND agent_name = {ph} AND opportunity_type = {ph}
        """
        params: List[Any] = [asset, agent_name, opportunity_type]
        if input_hash:
            query += f" AND input_hash = {ph}"
            params.append(input_hash)
        query += " ORDER BY generated_at DESC LIMIT 1"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            row = cursor.fetchone()
        if not row:
            return None
        record = dict(row)
        output_json = record.get("output_json")
        if isinstance(output_json, str):
            record["output_json"] = json.loads(output_json)
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
        ph = self._placeholder()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                INSERT INTO analyst_output_cache (
                    cache_id, generated_at, asset, agent_name, opportunity_type, lifecycle_state,
                    confidence_score, summary_text, input_hash, output_json, target_database,
                    delivery_status, delivered_at
                )
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
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
        ph = self._placeholder()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                INSERT INTO selected_asset_queue (asset, source_board, priority, reason, status)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
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
        ph = self._placeholder()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                INSERT INTO selected_asset_queue (
                    queue_key, asset, source_board, opportunity_type, priority, status,
                    requested_by, payload_json
                )
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
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
        ph = self._placeholder()
        placeholders = ",".join(ph for _ in status_values)
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
            LIMIT {ph}
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (*status_values, limit))
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def mark_selected_asset_checked(self, asset: str, source_board: str, validation_status: str) -> None:
        next_status = "active" if validation_status in {"supportive", "mixed", "weak"} else "archived"
        ph = self._placeholder()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                UPDATE selected_asset_queue
                SET last_checked_at = CURRENT_TIMESTAMP,
                    last_validation_status = {ph},
                    status = {ph},
                    updated_at = CURRENT_TIMESTAMP
                WHERE asset = {ph} AND source_board = {ph}
                """,
                (validation_status, next_status, asset, source_board),
            )
            conn.commit()

    def mark_selected_asset_validated(self, queue_key: str, status: str = "validated") -> None:
        ph = self._placeholder()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                UPDATE selected_asset_queue
                SET last_checked_at = CURRENT_TIMESTAMP,
                    last_validated_at = CURRENT_TIMESTAMP,
                    last_validation_status = {ph},
                    status = {ph},
                    updated_at = CURRENT_TIMESTAMP
                WHERE queue_key = {ph}
                """,
                (status, status, queue_key),
            )
            conn.commit()

    def mark_output_delivered(self, cache_id: str, delivery_status: str = "delivered") -> None:
        self.update_cache_delivery(cache_id, delivery_status)


if __name__ == "__main__":
    LocalBlackBox()
