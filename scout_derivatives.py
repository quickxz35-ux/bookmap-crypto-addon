import requests
import time
import sqlite3
import os
import logging
from local_blackbox import LocalBlackBox

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DerivativesScout:
    def __init__(self):
        self.db = LocalBlackBox()
        self.base_url = "https://fapi.binance.com/fapi/v1"

    def fetch_top_assets(self, limit=1000):
        """Fetches the Top X assets by 24h volume from Binance Futures."""
        logger.info(f"🔍 Discovering Top {limit} Assets by Volume...")
        try:
            url = f"{self.base_url}/ticker/24hr"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Sort by quoteVolume (USDT)
            sorted_assets = sorted(data, key=lambda x: float(x.get('quoteVolume', 0)), reverse=True)
            top_symbols = [a['symbol'] for a in sorted_assets if a['symbol'].endswith('USDT')][:limit]
            
            logger.info(f"✅ Found {len(top_symbols)} assets for the Snapshot Watchlist.")
            return top_symbols
        except Exception as e:
            logger.error(f"❌ Error fetching top assets: {e}")
            return []

    def fetch_snapshot_batch(self, symbols):
        """Fetches raw derivatives metrics for a batch of symbols."""
        snapshots = []
        
        # 1. Fetch ALL Tickers for Volume/Funding in one go if possible
        # (Binance /ticker/24hr returns all, but funding/OI often needs individual calls)
        
        # For simplicity in this skeleton, we fetch them sequentially with small delays 
        # or use the /premiumIndex for funding.
        
        logger.info(f"🛰️ Capturing Snapshots for {len(symbols)} assets...")
        
        # Batch Fetching Logic (Optimized for Binance)
        # Note: In a production 'Nitro' version, we would use async/aiohttp for speed.
        for symbol in symbols:
            try:
                # Mock/Simplified pull for the skeleton - Fetching OI and Funding
                # In real use, we'd loop several endpoints.
                
                # Fetch Funding Rate
                f_url = f"{self.base_url}/premiumIndex?symbol={symbol}"
                f_data = requests.get(f_url).json()
                
                # Fetch Open Interest
                oi_url = f"{self.base_url}/openInterest?symbol={symbol}"
                oi_data = requests.get(oi_url).json()

                snapshot = {
                    "asset": symbol,
                    "oi_raw": float(oi_data.get("openInterest", 0)),
                    "funding_rate": float(f_data.get("lastFundingRate", 0)),
                    "volume_24h": 0.0, # Pulled earlier in discovery
                    "timestamp": time.time()
                }
                snapshots.append(snapshot)
                
            except Exception:
                continue # Skip failed symbols
                
        return snapshots

    def record_snapshots(self, snapshots):
        """Saves snapshots to the Local Black Box."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for s in snapshots:
                cursor.execute('''
                    INSERT INTO scout_deriv_snapshots (asset, oi_raw, funding_rate, volume_24h)
                    VALUES (?, ?, ?, ?)
                ''', (s['asset'], s['oi_raw'], s['funding_rate'], s['volume_24h']))
            conn.commit()
            logger.info(f"✅ Recorded {len(snapshots)} snapshots to the Black Box.")

    def run_snapshot_cycle(self):
        """Perform one full 10-minute snapshot cycle."""
        top_assets = self.fetch_top_assets(limit=100) # Reduced to 100 for skeleton speed/demo
        snapshots = self.fetch_snapshot_batch(top_assets)
        if snapshots:
            self.record_snapshots(snapshots)

    def start(self, interval=600):
        """Infinite loop for the 10-minute heartbeat."""
        logger.info(f"🏎️ Derivatives Scout is online. Heartbeat: {interval}s.")
        while True:
            self.run_snapshot_cycle()
            time.sleep(interval)

if __name__ == "__main__":
    scout = DerivativesScout()
    scout.run_snapshot_cycle()
