from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from local_blackbox import LocalBlackBox
from symbol_utils import normalize_asset_symbol


class BlackBoxReader:
    def __init__(self):
        self.db = LocalBlackBox()

    def _read_df(self, query: str, params: Optional[tuple] = None) -> pd.DataFrame:
        query = query.replace("?", self.db.qmark)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            rows = cursor.fetchall()
            if not rows:
                return pd.DataFrame()
            try:
                return pd.DataFrame(rows)
            except Exception:
                columns = [desc[0] for desc in cursor.description or []]
                return pd.DataFrame([tuple(row) for row in rows], columns=columns)

    def _ensure_columns(self, frame: pd.DataFrame, defaults: Dict[str, Any]) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame([defaults])
        for column_name, default in defaults.items():
            if column_name not in frame.columns:
                frame[column_name] = default
            elif isinstance(default, float):
                frame[column_name] = pd.to_numeric(frame[column_name], errors="coerce").fillna(0.0)
            elif isinstance(default, int) and not isinstance(default, bool):
                frame[column_name] = pd.to_numeric(frame[column_name], errors="coerce").fillna(0).astype(int)
        return frame

    def latest_derivatives(self, asset: str, limit: int = 20) -> pd.DataFrame:
        normalized = normalize_asset_symbol(asset)
        try:
            normalized_df = self._read_df(
                """
                SELECT *
                FROM derivatives_snapshots
                WHERE asset = ?
                ORDER BY observed_at DESC
                LIMIT ?
                """,
                (normalized, limit),
            )
        except Exception:
            normalized_df = pd.DataFrame()
        if not normalized_df.empty:
            normalized_df = normalized_df.copy()
            normalized_df = self._ensure_columns(
                normalized_df,
                {
                    "snapshot_id": "",
                    "observed_at": None,
                    "asset": normalized,
                    "raw_symbol": "",
                    "venue": "",
                    "timeframe": "",
                    "open_interest": 0.0,
                    "open_interest_change_pct": 0.0,
                    "funding_rate": 0.0,
                    "long_short_ratio": 0.0,
                    "liquidations_total_usd": 0.0,
                    "liquidations_long_usd": 0.0,
                    "liquidations_short_usd": 0.0,
                    "volume_absolute": 0.0,
                    "volume_relative": 0.0,
                    "volume_change_pct": 0.0,
                    "mark_price": 0.0,
                    "trade_count_24h": 0.0,
                    "raw_payload_json": "{}",
                },
            )
            normalized_df = normalized_df.rename(
                columns={
                    "observed_at": "timestamp",
                    "open_interest": "oi_raw",
                    "liquidations_total_usd": "liquidations_24h",
                }
            )
            if "volume_24h" not in normalized_df.columns:
                normalized_df["volume_24h"] = pd.to_numeric(normalized_df.get("volume_absolute", 0.0), errors="coerce").fillna(0.0)
            return normalized_df
        try:
            fallback_df = self._read_df(
                """
                SELECT *
                FROM scout_deriv_snapshots
                WHERE asset = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (normalized, limit),
            )
            if not fallback_df.empty:
                fallback_df = fallback_df.copy()
                fallback_df = self._ensure_columns(
                    fallback_df,
                    {
                        "snapshot_id": "",
                        "observed_at": None,
                        "asset": normalized,
                        "raw_symbol": "",
                        "venue": "",
                        "timeframe": "",
                        "open_interest": 0.0,
                        "open_interest_change_pct": 0.0,
                        "funding_rate": 0.0,
                        "long_short_ratio": 0.0,
                        "liquidations_total_usd": 0.0,
                        "liquidations_long_usd": 0.0,
                        "liquidations_short_usd": 0.0,
                        "volume_absolute": 0.0,
                        "volume_relative": 0.0,
                        "volume_change_pct": 0.0,
                        "mark_price": 0.0,
                        "trade_count_24h": 0.0,
                        "raw_payload_json": "{}",
                    },
                )
                fallback_df = fallback_df.rename(
                    columns={
                        "observed_at": "timestamp",
                        "open_interest": "oi_raw",
                        "liquidations_total_usd": "liquidations_24h",
                    }
                )
                if "volume_24h" not in fallback_df.columns:
                    fallback_df["volume_24h"] = pd.to_numeric(fallback_df.get("volume_absolute", 0.0), errors="coerce").fillna(0.0)
                return fallback_df
            return pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    def recent_whale_events(self, asset: str, limit: int = 20) -> pd.DataFrame:
        normalized = normalize_asset_symbol(asset)
        try:
            normalized_df = self._read_df(
                """
                SELECT
                    event_id,
                    observed_at AS timestamp,
                    asset,
                    source_provider AS source,
                    event_type AS move_type,
                    amount_native AS amount,
                    amount_usd AS usd_value,
                    wallet_address,
                    counterparty_address,
                    entity_label,
                    raw_payload_json AS raw_payload
                FROM whale_events
                WHERE asset = ?
                ORDER BY observed_at DESC
                LIMIT ?
                """,
                (normalized, limit),
            )
        except Exception:
            normalized_df = pd.DataFrame()
        if not normalized_df.empty:
            return normalized_df
        try:
            return self._read_df(
                """
                SELECT *
                FROM scout_whale_log
                WHERE asset = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (normalized, limit),
            )
        except Exception:
            return pd.DataFrame()
            normalized = normalize_asset_symbol(asset)
            normalized_df = self._read_df(
                """
                SELECT
                    tx_id,
                    observed_at AS timestamp,
                    wallet_address,
                    wallet_alias,
                    tx_hash,
                    asset,
                    amount_native AS amount,
                    amount_usd AS usd_value,
                    action_type AS tx_type,
                    counterparty_address AS counterparty,
                    protocol_name,
                    chain,
                    network,
                    source_provider
                FROM wallet_transactions
                WHERE asset = ?
                ORDER BY observed_at DESC
                LIMIT ?
                """,
                (normalized, limit),
            )
            if not normalized_df.empty:
                return normalized_df
            return self._read_df(
                """
                SELECT *
                FROM scout_wallet_tx
                WHERE asset = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (normalized, limit),
            )

        normalized_df = self._read_df(
            """
            SELECT
                tx_id,
                observed_at AS timestamp,
                wallet_address,
                wallet_alias,
                tx_hash,
                asset,
                amount_native AS amount,
                amount_usd AS usd_value,
                action_type AS tx_type,
                counterparty_address AS counterparty,
                protocol_name,
                chain,
                network,
                source_provider
            FROM wallet_transactions
            ORDER BY observed_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        if not normalized_df.empty:
            return normalized_df
        return self._read_df(
            """
            SELECT *
            FROM scout_wallet_tx
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )

    def recent_sentiment(self, asset: Optional[str] = None, limit: int = 50) -> pd.DataFrame:
        if asset:
            normalized = normalize_asset_symbol(asset)
            try:
                normalized_df = self._read_df(
                    """
                    SELECT *
                    FROM sentiment_logs
                    WHERE asset = ?
                    ORDER BY published_at DESC
                    LIMIT ?
                    """,
                    (normalized, limit),
                )
            except Exception:
                normalized_df = pd.DataFrame()
            if not normalized_df.empty:
                normalized_df = normalized_df.copy()
                normalized_df = self._ensure_columns(
                    normalized_df,
                    {
                        "story_id": "",
                        "published_at": None,
                        "asset": normalized,
                        "source_provider": "",
                        "source_domain": "",
                        "headline": "",
                        "url": "",
                        "sentiment_label_raw": "",
                        "sentiment_score_raw": 0.0,
                        "topic_tags_json": "[]",
                        "dedup_key": "",
                        "raw_payload_json": "{}",
                    },
                )
                normalized_df = normalized_df.rename(
                    columns={
                        "published_at": "timestamp",
                        "source_provider": "source",
                        "sentiment_score_raw": "raw_sentiment_score",
                    }
                )
                return normalized_df
        try:
            normalized_df = self._read_df(
                """
                SELECT *
                FROM sentiment_logs
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        except Exception:
            normalized_df = pd.DataFrame()
        if not normalized_df.empty:
            normalized_df = normalized_df.copy()
            normalized_df = self._ensure_columns(
                normalized_df,
                {
                    "story_id": "",
                    "published_at": None,
                    "asset": "",
                    "source_provider": "",
                    "source_domain": "",
                    "headline": "",
                    "url": "",
                    "sentiment_label_raw": "",
                    "sentiment_score_raw": 0.0,
                    "topic_tags_json": "[]",
                    "dedup_key": "",
                    "raw_payload_json": "{}",
                },
            )
            normalized_df = normalized_df.rename(
                columns={
                    "published_at": "timestamp",
                    "source_provider": "source",
                    "sentiment_score_raw": "raw_sentiment_score",
                }
            )
            return normalized_df
        if asset:
            normalized = normalize_asset_symbol(asset)
            try:
                return self._read_df(
                    """
                    SELECT *
                    FROM scout_sentiment_log
                    WHERE asset = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (normalized, limit),
                )
            except Exception:
                return pd.DataFrame()
        try:
            return self._read_df(
                """
                SELECT *
                FROM scout_sentiment_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
        except Exception:
            return pd.DataFrame()

    def wallet_rank_inputs(self) -> pd.DataFrame:
        normalized_df = self._read_df(
            """
            SELECT
                w.wallet_address,
                w.alias,
                w.category,
                w.source_provider,
                w.display_name,
                w.top_rank,
                w.account_value,
                w.first_seen_at,
                w.last_seen_at,
                t.asset,
                t.amount_native AS amount,
                t.amount_usd,
                t.action_type,
                t.observed_at AS timestamp,
                t.chain,
                t.network,
                t.price_at_event
            FROM wallet_watchlist w
            LEFT JOIN wallet_transactions t
                ON w.wallet_address = t.wallet_address
            ORDER BY t.observed_at DESC
            """
        )
        if not normalized_df.empty:
            return normalized_df
        return self._read_df(
            """
            SELECT
                w.wallet_address,
                w.alias,
                w.category,
                w.source_provider,
                w.display_name,
                w.top_rank,
                w.account_value,
                w.first_seen_at,
                w.last_seen_at,
                t.asset,
                t.amount,
                t.usd_value AS amount_usd,
                COALESCE(t.action_type, t.tx_type) AS action_type,
                t.timestamp,
                t.chain,
                t.network,
                t.price_at_event
            FROM wallet_watchlist w
            LEFT JOIN scout_wallet_tx t
                ON w.wallet_address = t.wallet_address
            ORDER BY t.id DESC
            """
        )

    def recent_wallet_leaderboard_changes(
        self, limit: int = 200, change_types: Optional[Iterable[str]] = None
    ) -> pd.DataFrame:
        if change_types:
            change_type_values = list(change_types)
            placeholders = ",".join(["?"] * len(change_type_values))
            params: List[Any] = change_type_values + [limit]
            return self._read_df(
                f"""
                SELECT
                    change_id,
                    observed_at,
                    source_provider,
                    wallet_address,
                    display_name,
                    previous_rank,
                    current_rank,
                    change_type,
                    raw_payload_json
                FROM wallet_leaderboard_changes
                WHERE change_type IN ({placeholders})
                ORDER BY observed_at DESC
                LIMIT ?
                """,
                tuple(params),
            )

        return self._read_df(
            """
            SELECT
                change_id,
                observed_at,
                source_provider,
                wallet_address,
                display_name,
                previous_rank,
                current_rank,
                change_type,
                raw_payload_json
            FROM wallet_leaderboard_changes
            ORDER BY observed_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    def latest_cached_output(self, asset: str, agent_name: Optional[str] = None) -> pd.DataFrame:
        normalized = normalize_asset_symbol(asset)
        if agent_name:
            return self._read_df(
                """
                SELECT *
                FROM analyst_output_cache
                WHERE asset = ? AND agent_name = ?
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                (normalized, agent_name),
            )
        return self._read_df(
            """
            SELECT *
            FROM analyst_output_cache
            WHERE asset = ?
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            (normalized,),
        )

    def recent_analyst_outputs(
        self,
        limit: int = 200,
        opportunity_types: Optional[Iterable[str]] = None,
    ) -> pd.DataFrame:
        if opportunity_types:
            opportunity_values = list(opportunity_types)
            placeholders = ",".join(["?"] * len(opportunity_values))
            params: List[Any] = opportunity_values + [limit]
            return self._read_df(
                f"""
                SELECT
                    cache_id,
                    generated_at,
                    asset,
                    agent_name,
                    opportunity_type,
                    lifecycle_state,
                    confidence_score,
                    summary_text,
                    output_json,
                    target_database,
                    delivery_status
                FROM analyst_output_cache
                WHERE opportunity_type IN ({placeholders})
                ORDER BY generated_at DESC
                LIMIT ?
                """,
                tuple(params),
            )

        return self._read_df(
            """
            SELECT
                cache_id,
                generated_at,
                asset,
                agent_name,
                opportunity_type,
                lifecycle_state,
                confidence_score,
                summary_text,
                output_json,
                target_database,
                delivery_status
            FROM analyst_output_cache
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    def get_cached_output(
        self,
        asset: str,
        agent_name: str,
        opportunity_type: str,
        input_hash: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.db.get_cached_output(
            asset=normalize_asset_symbol(asset),
            agent_name=agent_name,
            opportunity_type=opportunity_type,
            input_hash=input_hash,
        )

    def cache_output(
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
        return self.db.cache_analyst_output(
            asset=normalize_asset_symbol(asset),
            agent_name=agent_name,
            opportunity_type=opportunity_type,
            lifecycle_state=lifecycle_state,
            confidence_score=confidence_score,
            summary_text=summary_text,
            output=output,
            target_database=target_database,
            input_hash=input_hash,
            delivery_status=delivery_status,
        )

    def update_delivery_state(self, cache_id: str, delivery_status: str) -> None:
        self.db.update_cache_delivery(cache_id, delivery_status)

    def enqueue_selected_asset(
        self,
        asset: str,
        source_board: str,
        reason: str = "",
        priority: int = 50,
        status: str = "pending",
    ) -> None:
        self.db.enqueue_selected_asset(
            asset=normalize_asset_symbol(asset),
            source_board=source_board,
            reason=reason,
            priority=priority,
            status=status,
        )

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
        return self.db.upsert_selected_asset(
            asset=normalize_asset_symbol(asset),
            source_board=source_board,
            opportunity_type=opportunity_type,
            priority=priority,
            status=status,
            requested_by=requested_by,
            payload=payload,
        )

    def fetch_selected_assets(
        self, limit: int = 25, statuses: Optional[Iterable[str]] = None
    ) -> List[Dict[str, Any]]:
        return self.db.fetch_selected_assets(limit=limit, statuses=statuses)

    def mark_selected_asset_checked(self, asset: str, source_board: str, validation_status: str) -> None:
        self.db.mark_selected_asset_checked(normalize_asset_symbol(asset), source_board, validation_status)

    def safe_float(self, row: Dict[str, Any], key: str) -> float:
        value = row.get(key, 0) if isinstance(row, dict) else 0
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0
