import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pandas as pd

from blackbox_reader import BlackBoxReader


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class WalletAnalyst:
    def __init__(self):
        self.reader = BlackBoxReader()

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
        logger.info("Wallet Analyst is ranking tracked wallets")
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
                alias = next((value for value in wallet_frame["alias"].tolist() if value), address)
                category = next((value for value in wallet_frame["category"].tolist() if value), "Unclassified")
                features = self._score_wallet(wallet_frame)
                status = self._status_for_score(features)

                output = {
                    "agent": "wallet_analyst",
                    "wallet_address": address,
                    "alias": alias,
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
                    """
                    INSERT OR REPLACE INTO analyst_wallet_stats (
                        wallet_address, win_rate, total_pnl_usd, best_trade_ticker,
                        last_updated, status, score, tx_count, asset_count, active_days
                    )
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?)
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
                    agent_name="wallet_analyst",
                    opportunity_type="wallet_ranking",
                    lifecycle_state=status,
                    confidence_score=output["wallet_score"],
                    summary_text=f"{alias} classified as {status} with wallet score {output['wallet_score']}",
                    output=output,
                    target_database="whale_registry",
                )
                results.append(output)

                if status == "elite":
                    logger.info("Elite wallet detected: %s (%s)", alias, address)

        return sorted(results, key=lambda item: item["wallet_score"], reverse=True)

    def run_performance_audit(self):
        return self.rank_wallets()

    def start(self, interval: int = 3600) -> None:
        logger.info("Wallet Analyst is online. Audit cycle: %ss", interval)
        while True:
            self.rank_wallets()
            time.sleep(interval)


if __name__ == "__main__":
    analyst = WalletAnalyst()
    analyst.start()
