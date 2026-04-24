import logging
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any

from local_blackbox import LocalBlackBox
from decision_router import DecisionRouter
from onchain_decision_router import OnChainDecisionRouter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OutboxProcessor:
    """
    The Postman: Responsible for picking up cached signals from the database
    and delivering them to Notion/Slack via the specialized Routers.
    """
    def __init__(self):
        self.db = LocalBlackBox()
        self.market_router = DecisionRouter()
        self.onchain_router = OnChainDecisionRouter()

    def _field(self, row, key: str, index: int):
        if isinstance(row, dict):
            return row.get(key)
        return row[index]

    def _parse_output(self, output_json):
        if isinstance(output_json, dict):
            return output_json
        if not output_json:
            return {}
        return json.loads(output_json)

    def process_pending_signals(self):
        """Polls the database for pending signals and delivers them."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # We look for 'pending' signals in the analyst_output_cache
            cursor.execute("""
                SELECT cache_id, asset, agent_name, opportunity_type, output_json, target_database
                FROM analyst_output_cache
                WHERE delivery_status = 'pending'
                ORDER BY generated_at ASC
            """)
            rows = cursor.fetchall()

        if not rows:
            return

        logger.info(f"📬 Found {len(rows)} pending signals to deliver...")

        for row in rows:
            cache_id = self._field(row, "cache_id", 0)
            asset = self._field(row, "asset", 1)
            agent_name = self._field(row, "agent_name", 2)
            opp_type = self._field(row, "opportunity_type", 3)
            output_json = self._field(row, "output_json", 4)
            target_db = self._field(row, "target_database", 5)
            output = self._parse_output(output_json)
            
            try:
                # Routing Logic based on Opportunity Type
                result = None
                
                # 🛠️ ON-CHAIN DATA (Wallet/Whale Intelligence)
                if opp_type in ["wallet_ranking", "wallet_stats", "wallet_discovery", "wallet_update", "whale_strike"]:
                    logger.info(f"🚚 Delivering ON-CHAIN signal for {asset} via OnChainDecisionRouter...")
                    if opp_type == "whale_strike":
                        result = self.onchain_router.route_whale_strike(output)
                    elif opp_type == "wallet_discovery":
                        result = self.onchain_router.route_wallet_discovery(output)
                    elif opp_type == "wallet_update":
                        result = self.onchain_router.route_wallet_update(output)
                    else:
                        result = self.onchain_router.route_wallet_stats(output)
                
                # 🧠 COUNCIL SYNTHESIS (Shared verdict from scouts + analysts)
                elif opp_type == "council_thesis":
                    logger.info(f"🚚 Delivering COUNCIL signal for {asset} via DecisionRouter...")
                    result = self.market_router.route_council_thesis(output)

                elif opp_type == "trade_candidate":
                    logger.info(f"🚚 Delivering TRADE CANDIDATE for {asset} via DecisionRouter...")
                    result = self.market_router.route_trade_candidate(output)

                # 📈 MARKET SIGNALS (Trade Setups)
                elif opp_type in ["scalp", "long_term"]:
                    logger.info(f"🚚 Delivering MARKET signal for {asset} via DecisionRouter...")
                    if opp_type == "scalp":
                        setup = output.get("setup", output)
                        tracker = output.get("tracker", {"new_status": output.get("status", "new")})
                        correlation = output.get("correlation", {"confluence_status": "pending", "confidence": output.get("confidence", 50)})
                        result = self.market_router.route_scalp(setup, tracker, correlation)
                    else:
                        coin_view = output.get("coin_view", output)
                        validation = output.get("validation", {"status": "valid"})
                        correlation = output.get("correlation", {"confidence": output.get("conviction", 35)})
                        result = self.market_router.route_long_term(coin_view, validation, correlation)
                
                else:
                    logger.warning(f"❓ Unknown opportunity type: {opp_type}. Marking as skipped.")
                    self.db.update_cache_delivery(cache_id, "skipped_unknown_type")
                    continue

                if result:
                    action = result.get("notion", result.get("notion_action", "routed"))
                    self.db.update_cache_delivery(cache_id, f"router_{action}")
                    logger.info(f"✅ Delivered {opp_type} signal for {asset}. Action: {action}")
            
            except Exception as e:
                logger.error(f"❌ Failed to deliver signal {cache_id}: {e}")
                self.db.update_cache_delivery(cache_id, f"error: {str(e)[:100]}")

    def start(self, interval=30):
        """Infinite loop to process the outbox (Pulse of the workspace)."""
        logger.info(f"🛰️ Outbox Processor (The Postman) is online. Pulse: {interval}s.")
        while True:
            try:
                self.process_pending_signals()
            except Exception as e:
                logger.error(f"CRITICAL: Outbox loop encountered error: {e}")
            
            time.sleep(interval)

if __name__ == "__main__":
    from worker_smoke import run_worker_smoke_check

    run_worker_smoke_check(
        "decision-router",
        required_tables=("analyst_output_cache",),
    )
    processor = OutboxProcessor()
    processor.start()
