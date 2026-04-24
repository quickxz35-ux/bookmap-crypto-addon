import json
import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from blackbox_reader import BlackBoxReader


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class Hyperscreener:
    def __init__(self):
        self.reader = BlackBoxReader()

    def _clean_text(self, value: Any, default: Optional[str] = None) -> Optional[str]:
        if value is None:
            return default
        try:
            if pd.isna(value):
                return default
        except Exception:
            pass
        text = str(value).strip()
        if text.lower() in {"", "nan", "none"}:
            return default
        return text

    def _coerce_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None or pd.isna(value):
                return default
            if isinstance(value, str) and not value.strip():
                return default
            numeric = float(value)
            if numeric != numeric:
                return default
            return numeric
        except Exception:
            return default

    def _first_value(self, frame: pd.DataFrame, column_name: str, default: Any = None) -> Any:
        if column_name not in frame:
            return default
        for value in frame[column_name].tolist():
            if value is None:
                continue
            try:
                if pd.isna(value):
                    continue
            except Exception:
                pass
            if value not in (None, "", "nan"):
                return value
        return default

    def _safe_series_sum(self, frame: pd.DataFrame, column: str) -> float:
        if column not in frame:
            return 0.0
        return float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).sum())

    def _score_wallet(self, wallet_frame: pd.DataFrame) -> Dict[str, float]:
        tx_count = len(wallet_frame)
        asset_count = int(wallet_frame["asset"].fillna("").astype(str).nunique()) if "asset" in wallet_frame else 0
        active_days = (
            int(pd.to_datetime(wallet_frame["timestamp"], utc=True, errors="coerce").dt.date.nunique())
            if "timestamp" in wallet_frame
            else 0
        )
        amount_usd = self._safe_series_sum(wallet_frame, "amount_usd")
        abs_flow_usd = (
            float(pd.to_numeric(wallet_frame["amount_usd"], errors="coerce").fillna(0.0).abs().sum())
            if "amount_usd" in wallet_frame
            else 0.0
        )
        buy_count = int(wallet_frame["action_type"].fillna("").astype(str).str.contains("buy|receive|swap_in", case=False).sum()) if "action_type" in wallet_frame else 0
        sell_count = int(wallet_frame["action_type"].fillna("").astype(str).str.contains("sell|send|swap_out", case=False).sum()) if "action_type" in wallet_frame else 0

        timestamps = pd.to_datetime(wallet_frame["timestamp"], utc=True, errors="coerce") if "timestamp" in wallet_frame else pd.Series(dtype="datetime64[ns, UTC]")
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent_tx_count = int((timestamps >= recent_cutoff).sum()) if not timestamps.empty else 0

        flow_quality = min(25.0, abs_flow_usd / 10000.0)
        consistency = min(20.0, active_days * 2.5)
        breadth = min(15.0, asset_count * 2.5)
        participation = min(15.0, tx_count * 1.5)
        recency = min(15.0, recent_tx_count * 3.0)
        directional_edge = 10.0 if buy_count > sell_count else 4.0 if buy_count == sell_count else 2.0

        score = round(min(100.0, flow_quality + consistency + breadth + participation + recency + directional_edge), 2)
        win_rate_proxy = round(min(0.95, max(0.15, (buy_count + 1) / max(1, tx_count + 2))), 2)
        return {
            "score": score,
            "win_rate_proxy": win_rate_proxy,
            "tx_count": tx_count,
            "asset_count": asset_count,
            "active_days": active_days,
            "recent_tx_count": recent_tx_count,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "net_flow_proxy": round(amount_usd, 2),
            "abs_flow_usd": round(abs_flow_usd, 2),
        }

    def _status_for_score(self, features: Dict[str, float]) -> str:
        if features["score"] >= 75 and features["tx_count"] >= 8 and features["recent_tx_count"] >= 2:
            return "elite"
        if features["score"] >= 45 and features["tx_count"] >= 3:
            return "watch"
        return "ignore"

    def rank_wallets(self) -> List[Dict[str, Any]]:
        logger.info("Hyperscreener is ranking tracked wallets")
        df = self.reader.wallet_rank_inputs()
        if df.empty:
            logger.info("No wallet logs found in the Black Box")
            return []

        results = []
        wallets = df["wallet_address"].dropna().unique()
        with self.reader.db.get_connection() as conn:
            cursor = conn.cursor()
            for address in wallets:
                wallet_frame = df[df["wallet_address"] == address].copy()
                alias = self._clean_text(self._first_value(wallet_frame, "alias", address), address) or address
                category = self._clean_text(self._first_value(wallet_frame, "category", "Unclassified"), "Unclassified") or "Unclassified"
                display_name = self._clean_text(self._first_value(wallet_frame, "display_name", alias), alias) or alias
                source_provider = self._clean_text(self._first_value(wallet_frame, "source_provider", "legacy"), "legacy") or "legacy"
                top_rank = self._first_value(wallet_frame, "top_rank")
                account_value = self._first_value(wallet_frame, "account_value")
                first_seen_at = self._first_value(wallet_frame, "first_seen_at")
                last_seen_at = self._first_value(wallet_frame, "last_seen_at")
                features = self._score_wallet(wallet_frame)
                status = self._status_for_score(features)
                ph = self.reader.db.qmark

                output = {
                    "agent": "hyperscreener",
                    "wallet_address": address,
                    "alias": alias,
                    "display_name": display_name,
                    "source_provider": source_provider,
                    "top_rank": top_rank,
                    "account_value": account_value,
                    "first_seen_at": first_seen_at,
                    "last_seen_at": last_seen_at,
                    "category": category,
                    "status": status,
                    "wallet_score": features["score"],
                    "win_rate": features["win_rate_proxy"],
                    "tx_count": features["tx_count"],
                    "asset_count": features["asset_count"],
                    "active_days": features["active_days"],
                    "recent_tx_count": features["recent_tx_count"],
                    "buy_count": features["buy_count"],
                    "sell_count": features["sell_count"],
                    "net_flow_proxy": features["net_flow_proxy"],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }

                cursor.execute(
                    f"""
                    INSERT INTO analyst_wallet_stats (
                        wallet_address, win_rate, total_pnl_usd, best_trade_ticker,
                        last_updated, status, score, tx_count, asset_count, active_days
                    )
                    VALUES ({ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP, {ph}, {ph}, {ph}, {ph}, {ph})
                    ON CONFLICT(wallet_address) DO UPDATE SET
                        win_rate = excluded.win_rate,
                        total_pnl_usd = excluded.total_pnl_usd,
                        best_trade_ticker = excluded.best_trade_ticker,
                        last_updated = CURRENT_TIMESTAMP,
                        status = excluded.status,
                        score = excluded.score,
                        tx_count = excluded.tx_count,
                        asset_count = excluded.asset_count,
                        active_days = excluded.active_days
                    """,
                    (
                        address,
                        output["win_rate"],
                        output["net_flow_proxy"],
                        None,
                        status,
                        output["wallet_score"],
                        output["tx_count"],
                        output["asset_count"],
                        output["active_days"],
                    ),
                )
                conn.commit()

                self.reader.cache_output(
                    asset=address,
                    agent_name="hyperscreener",
                    opportunity_type="wallet_ranking",
                    lifecycle_state=status,
                    confidence_score=output["wallet_score"],
                    summary_text=f"{alias} classified as {status} with wallet score {output['wallet_score']} (rank {top_rank or 'n/a'})",
                    output=output,
                    target_database="whale_registry",
                )
                results.append(output)

                if status == "elite":
                    logger.info("Elite wallet detected: %s (%s)", alias, address)

        return sorted(results, key=lambda item: item["wallet_score"], reverse=True)

    def record_wallet_discoveries(self, limit: int = 200) -> List[Dict[str, Any]]:
        logger.info("Hyperscreener is recording wallet discovery changes")
        changes = self.reader.recent_wallet_leaderboard_changes(limit=limit)
        if changes.empty:
            logger.info("No wallet leaderboard changes found in the Black Box")
            return []

        results: List[Dict[str, Any]] = []
        for _, change in changes.iterrows():
            change_type = str(change.get("change_type") or "").upper()
            if not change_type or change_type == "UNCHANGED":
                continue

            wallet_address = str(change.get("wallet_address") or "").strip().lower()
            if not wallet_address:
                continue

            display_name = self._clean_text(change.get("display_name"), wallet_address[:10]) or wallet_address[:10]
            previous_rank = self._coerce_float(change.get("previous_rank"), 0.0)
            current_rank = self._coerce_float(change.get("current_rank"), 0.0)
            observed_at = change.get("observed_at") or datetime.now(timezone.utc).isoformat()
            change_id = str(change.get("change_id") or "").strip()
            raw_payload = {}
            raw_payload_json = change.get("raw_payload_json")
            if raw_payload_json:
                try:
                    raw_payload = json.loads(raw_payload_json)
                except Exception:
                    raw_payload = {}
            input_hash = change_id or hashlib.sha1(
                f"{wallet_address}|{change_type}|{previous_rank}|{current_rank}|{observed_at}".encode("utf-8")
            ).hexdigest()

            existing = self.reader.get_cached_output(
                wallet_address,
                "hyperscreener",
                "wallet_discovery",
                input_hash=input_hash,
            )
            if existing:
                continue

            rank_delta = None
            try:
                if previous_rank is not None and current_rank is not None:
                    rank_delta = int(previous_rank) - int(current_rank)
            except Exception:
                rank_delta = None

            output = {
                "agent": "hyperscreener",
                "wallet_address": wallet_address,
                "display_name": display_name,
                "source_provider": self._clean_text(change.get("source_provider"), "hyperscreener") or "hyperscreener",
                "change_id": change_id,
                "change_type": change_type,
                "previous_rank": previous_rank,
                "current_rank": current_rank,
                "rank_delta": rank_delta,
                "account_value": self._coerce_float(raw_payload.get("account_value"), 0.0),
                "observed_at": observed_at,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            summary_text = f"{display_name} {change_type.lower().replace('_', ' ')} at rank {current_rank if current_rank else 'n/a'}"
            cache_id = self.reader.cache_output(
                asset=wallet_address,
                agent_name="hyperscreener",
                opportunity_type="wallet_discovery",
                lifecycle_state=change_type.lower(),
                confidence_score=100.0 if change_type == "NEW_WALLET" else 70.0,
                summary_text=summary_text,
                output=output,
                target_database="wallet_activity",
                input_hash=input_hash,
            )
            results.append({"cache_id": cache_id, **output})

        return results

    def record_wallet_updates(self, limit: int = 500) -> List[Dict[str, Any]]:
        logger.info("Hyperscreener is recording wallet transaction updates")
        txs = self.reader.recent_wallet_transactions(limit=limit)
        if txs.empty:
            logger.info("No wallet transactions found in the Black Box")
            return []

        results: List[Dict[str, Any]] = []
        for _, tx in txs.iterrows():
            wallet_address = str(tx.get("wallet_address") or "").strip().lower()
            tx_hash = str(tx.get("tx_hash") or "").strip()
            if not wallet_address or not tx_hash:
                continue

            existing = self.reader.get_cached_output(
                wallet_address,
                "hyperscreener",
                "wallet_update",
                input_hash=tx_hash,
            )
            if existing:
                continue

            observed_at = tx.get("timestamp") or datetime.now(timezone.utc).isoformat()
            asset = str(tx.get("asset") or "UNKNOWN")
            tx_type = str(tx.get("tx_type") or tx.get("action_type") or "TX").upper()
            amount = self._coerce_float(tx.get("amount") or 0.0)
            amount_usd = self._coerce_float(tx.get("amount_usd") or tx.get("usd_value") or 0.0)
            wallet_alias = self._clean_text(tx.get("wallet_alias") or tx.get("alias"), wallet_address[:10]) or wallet_address[:10]
            summary_text = f"{wallet_alias} {tx_type.lower().replace('_', ' ')} {asset} {amount_usd:,.2f} USD"

            output = {
                "agent": "hyperscreener",
                "wallet_address": wallet_address,
                "wallet_alias": wallet_alias,
                "source_provider": tx.get("source_provider") or "hyperliquid",
                "tx_hash": tx_hash,
                "asset": asset,
                "amount": amount,
                "amount_usd": amount_usd,
                "tx_type": tx_type,
                "counterparty": tx.get("counterparty"),
                "chain": tx.get("chain"),
                "network": tx.get("network"),
                "wallet_rank": tx.get("wallet_rank"),
                "leaderboard_snapshot_at": tx.get("leaderboard_snapshot_at"),
                "observed_at": observed_at,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            cache_id = self.reader.cache_output(
                asset=wallet_address,
                agent_name="hyperscreener",
                opportunity_type="wallet_update",
                lifecycle_state=tx_type.lower(),
                confidence_score=min(100.0, abs(amount_usd) or abs(amount) or 1.0),
                summary_text=summary_text,
                output=output,
                target_database="wallet_activity",
                input_hash=tx_hash,
            )
            results.append({"cache_id": cache_id, **output})

        return results

    def run_performance_audit(self):
        return {
            "wallet_ranking": self.rank_wallets(),
            "wallet_discovery": self.record_wallet_discoveries(),
            "wallet_update": self.record_wallet_updates(),
        }

    def start(self, interval: int = 3600) -> None:
        logger.info("Hyperscreener is online. Audit cycle: %ss", interval)
        while True:
            try:
                self.run_performance_audit()
            except Exception:
                logger.exception("wallet-analyst audit cycle failed; retrying after backoff.")
                time.sleep(min(60, interval))
                continue
            time.sleep(interval)


if __name__ == "__main__":
    from worker_smoke import run_worker_smoke_check

    run_worker_smoke_check(
        "wallet-analyst",
        required_tables=(
            "wallet_watchlist",
            "analyst_output_cache",
            "wallet_leaderboard_changes",
            "scout_wallet_tx",
        ),
    )
    analyst = Hyperscreener()
    analyst.start()


# Backward compatibility for older imports and local scripts.
WalletAnalyst = Hyperscreener
