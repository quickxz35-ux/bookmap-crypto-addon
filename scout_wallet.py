import requests
import time
import sqlite3
import os
import logging
from local_blackbox import LocalBlackBox
import cryptoapis_handler as capi # Reuse existing handler

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WalletScout:
    def __init__(self):
        self.db = LocalBlackBox()
        self.base_url = "https://rest.cryptoapis.io/blockchain-data/evm/ethereum/mainnet"

    def get_active_watchlist(self):
        """Fetches the currently active wallet addresses from the Black Box."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT wallet_address, alias FROM wallet_watchlist WHERE is_active = 1")
            return cursor.fetchall()

    def fetch_transactions(self, address):
        """Fetches recent transactions for a specific address from CryptoAPIs."""
        url = f"{self.base_url}/addresses/{address}/transactions"
        params = {"limit": 10} # Get last 10 transactions
        
        try:
            response = requests.get(url, headers=capi.HEADERS, params=params)
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("items", [])
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching transactions for {address}: {e}")
            return []

    def record_transactions(self, address, tx_list):
        """Saves new transactions to the Local Black Box."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            new_count = 0
            
            for tx in tx_list:
                tx_hash = tx.get("transactionHash")
                timestamp = tx.get("timestamp")
                
                # Simplified parsing for the skeleton
                amount = float(tx.get("value", {}).get("amount", 0))
                asset = tx.get("value", {}).get("unit", "ETH")
                
                try:
                    cursor.execute('''
                        INSERT INTO scout_wallet_tx (wallet_address, tx_hash, asset, amount, tx_type)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (address, tx_hash, asset, amount, "TRANSFER"))
                    new_count += 1
                except sqlite3.IntegrityError:
                    continue # Skip duplicates
            
            conn.commit()
            if new_count > 0:
                logger.info(f"✅ Recorded {new_count} new transactions for {address}.")

    def run_sync_cycle(self):
        """Perform one full transaction sync for the entire watchlist."""
        watchlist = self.get_active_watchlist()
        if not watchlist:
            logger.info("⏳ Watchlist is empty. Add wallets in Notion to begin tracking.")
            return

        for address, alias in watchlist:
            logger.info(f"🛰️ Syncing {alias or address}...")
            txs = self.fetch_transactions(address)
            if txs:
                self.record_transactions(address, txs)

    def start(self, interval=300):
        """Infinite loop to poll for watchlist activity every 5 minutes."""
        logger.info(f"🏎️ Wallet Scout is online. Polling Watchlist every {interval}s.")
        while True:
            self.run_sync_cycle()
            time.sleep(interval)

if __name__ == "__main__":
    scout = WalletScout()
    # Test with a dummy address if DB empty
    scout.run_sync_cycle()
