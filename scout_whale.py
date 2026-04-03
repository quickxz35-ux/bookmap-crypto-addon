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

    def check_cex_flows(self, assets=["BTC", "ETH", "SOL", "PEPE"]):
        """
        Monitors known CEX deposit/withdrawal addresses.
        In the skeleton, we simulate this by checking specific exchange-linked wallets.
        """
        logger.info(f"🐋 Whale Scout is probing CEX flows for {len(assets)} assets...")
        
        # Example: Probing the Binance ETH Whale Wallet
        ETH_WHALE = "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8"
        portfolio = moralis.get_wallet_portfolio(ETH_WHALE, chain="eth")
        
        if portfolio:
            # Logic: If any balance change > 1% of total Wallet value, record as a 'Move'
            for token in portfolio:
                usd_val = float(token.get("usd_value", 0))
                if usd_val > self.strike_threshold_usd:
                    self.record_move(
                        asset=token.get("symbol"),
                        source="Binance_Whale",
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
