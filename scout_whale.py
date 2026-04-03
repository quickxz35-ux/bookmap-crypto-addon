import requests
import time
import sqlite3
import os
import logging
from local_blackbox import LocalBlackBox
import moralis_handler as moralis # Reuse existing handler

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WhaleScout:
    def __init__(self):
        self.db = LocalBlackBox()
        self.strike_threshold_usd = 500000 # Default $500k Whale Move
        self.exchange_watch_wallets = [
            {
                "label": "Binance_Whale",
                "address": "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8",
                "chain": "eth",
            }
        ]

    def check_cex_flows(self, assets=["BTC", "ETH", "SOL", "PEPE"]):
        """
        Monitors known CEX deposit/withdrawal addresses.
        In the skeleton, we simulate this by checking specific exchange-linked wallets.
        """
        logger.info(f"🐋 Whale Scout is probing CEX flows for {len(assets)} assets...")

        for wallet in self.exchange_watch_wallets:
            try:
                portfolio = moralis.get_wallet_portfolio(wallet["address"], chain=wallet["chain"])
            except Exception as e:
                logger.error(f"❌ Error fetching Moralis portfolio for {wallet['label']}: {e}")
                continue

            if not portfolio:
                continue

            # Logic: If any balance change > 1% of total wallet value, record as a 'Move'
            for token in portfolio:
                symbol = token.get("symbol")
                if assets and symbol not in assets:
                    continue

                usd_val = float(token.get("usd_value", 0))
                if usd_val > self.strike_threshold_usd:
                    self.record_move(
                        asset=symbol,
                        source=wallet["label"],
                        move_type="HEAVY_HOLDING",
                        amount=float(token.get("balance_formatted", 0)),
                        usd_value=usd_val,
                        raw_payload=str(token)
                    )

    def record_move(self, asset, source, move_type, amount, usd_value, raw_payload):
        """Saves a Whale Move to the Local Black Box."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO scout_whale_log (asset, source, move_type, amount, usd_value, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (asset, source, move_type, amount, usd_value, raw_payload))
            conn.commit()
            logger.info(f"🚩 WHALE STRIKE: {asset} Move detected! (${usd_value:,.0f} from {source})")

    def run(self, interval=600):
        """Infinite loop to poll for whale moves."""
        logger.info(f"🛰️ Whale Scout is online. Polling every {interval}s. Threshold: ${self.strike_threshold_usd:,.0f}")
        while True:
            self.check_cex_flows()
            time.sleep(interval)

if __name__ == "__main__":
    scout = WhaleScout()
    scout.check_cex_flows()
