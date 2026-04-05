import sqlite3
import pandas as pd
import logging
import time
from local_blackbox import LocalBlackBox

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TechnicalAnalyst:
    def __init__(self):
        self.db = LocalBlackBox()

    def run_technical_audit(self, asset):
        """
        Analyzes the derivatives snapshots for a specific asset.
        Identifies Trend, Price Velocity, and OI/Funding Traps.
        """
        logger.info(f"🧠 Technical Analyst is auditing chart confluence for {asset}...")
        
        with self.db.get_connection() as conn:
            # 1. Load Last 20 Snapshots into Dataframe
            query = f"SELECT * FROM scout_deriv_snapshots WHERE asset = '{asset}' ORDER BY timestamp DESC LIMIT 20"
            df = pd.read_sql_query(query, conn)
            
            if df.empty or len(df) < 2:
                logger.warning(f"⏳ Insufficient data for {asset}. Need more 10-minute snapshots.")
                return "INSUFFICIENT_DATA"

            # 2. Trend Identification (OI vs Funding)
            # Latest vs. Previous
            latest = df.iloc[0]
            prev = df.iloc[1]
            
            oi_change = ((latest['oi_raw'] - prev['oi_raw']) / prev['oi_raw']) * 100 if prev['oi_raw'] != 0 else 0
            funding = latest['funding_rate']
            
            # 3. Verdict Logic (Simple Skeleton)
            if oi_change > 5 and funding > 0.0001:
                verdict = "BULLISH_AGGRESSIVE" # Rising OI + Positive Funding
            elif oi_change > 5 and funding < -0.0001:
                verdict = "SHORT_SQUEEZE_RISK" # Rising OI + Negative Funding
            elif oi_change < -5:
                verdict = "TREND_FADING" # Falling OI
            else:
                verdict = "NEUTRAL_CHOP"
                
            logger.info(f"✅ TECHNICAL VERDICT ({asset}): {verdict} (OI Chg: {oi_change:.2f}%)")
            return verdict

    def start_loop(self, interval: int = 900) -> None:
        """Audit all newly flagged coin picks every 15 minutes."""
        logger.info(f"🏎️ Technical Analyst is online. Heartbeat: {interval}s.")
        while True:
            # Get a list of assets from the Black Box to analyze
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT asset FROM derivatives_snapshots")
                assets = [row[0] for row in cursor.fetchall()]

            if not assets:
                logger.info("⏳ Waiting for derivatives snapshots to populate database...")
            
            for asset in assets:
                try:
                    self.run_technical_audit(asset)
                except Exception as e:
                    logger.error(f"Error auditing {asset}: {e}")
            
            time.sleep(interval)


if __name__ == "__main__":
    analyst = TechnicalAnalyst()
    analyst.start_loop()
