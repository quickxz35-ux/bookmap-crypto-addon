from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from local_blackbox import LocalBlackBox
from symbol_utils import normalize_asset_symbol


class BlackBoxReader:
    def __init__(self):
        self.db = LocalBlackBox()

    def _read_df(self, query: str, params: Optional[tuple] = None) -> pd.DataFrame:
        with self.db.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params or ())

    def latest_derivatives(self, asset: str, limit: int = 20) -> pd.DataFrame:
        normalized = normalize_asset_symbol(asset)
        normalized_df = self._read_df(
            """
            SELECT
                snapshot_id,
                observed_at AS timestamp,
                asset,
                raw_symbol,
                venue,
                timeframe,
                open_interest AS oi_raw,
                open_interest_change_pct,
                funding_rate,
                long_short_ratio,
                liquidations_total_usd AS liquidations_24h,
                liquidations_long_usd,
                liquidations_short_usd,
                volume_absolute AS volume_24h,
                volume_absolute,
                volume_relative,
                volume_change_pct,
                mark_price,
                trade_count_24h,
                raw_payload_json
            FROM derivatives_snapshots
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
            FROM scout_deriv_snapshots
            WHERE asset = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (normalized, limit),
        )

    def recent_whale_events(self, asset: str, limit: int = 20) -> pd.DataFrame:
        normalized = normalize_asset_symbol(asset)
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
        if not normalized_df.empty:
            return normalized_df
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

    def recent_wallet_transactions(self, asset: Optional[str] = None, limit: int = 50) -> pd.DataFrame:
        if asset:
            normalized = normalize_asset_symbol(asset)
            normalized_df = self._read_df(
                """
                SELECT
                    tx_id,
                    observed_at AS timestamp,
                    wallet_address,
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
            normalized_df = self._read_df(
                """
                SELECT
                    story_id,
                    published_at AS timestamp,
                    asset,
                    source_provider AS source,
                    source_domain,
                    headline,
                    url,
                    sentiment_label_raw,
                    sentiment_score_raw AS raw_sentiment_score,
                    topic_tags_json,
                    dedup_key,
                    raw_payload_json
                FROM sentiment_logs
                WHERE asset = ?
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (normalized, limit),
            )
            if not normalized_df.empty:
                return normalized_df
        normalized_df = self._read_df(
            """
            SELECT
                story_id,
                published_at AS timestamp,
                asset,
                source_provider AS source,
                source_domain,
                headline,
                url,
                sentiment_label_raw,
                sentiment_score_raw AS raw_sentiment_score,
                topic_tags_json,
                dedup_key,
                raw_payload_json
            FROM sentiment_logs
            ORDER BY published_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        if not normalized_df.empty:
            return normalized_df
        if asset:
            normalized = normalize_asset_symbol(asset)
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
        return self._read_df(
            """
            SELECT *
            FROM scout_sentiment_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )

    def wallet_rank_inputs(self) -> pd.DataFrame:
        normalized_df = self._read_df(
            """
            SELECT
                w.wallet_address,
                w.alias,
                w.category,
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
