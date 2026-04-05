import sqlite3
import pandas as pd
import logging
import time
from local_blackbox import LocalBlackBox

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NarrativeEngine:
    def __init__(self):
        self.db = LocalBlackBox()
        self.bullish_keywords = ["listing", "partnership", "breakout", "bullish", "moon", "pumping", "listed"]
        self.bearish_keywords = ["exploit", "hack", "dump", "fud", "bearish", "regulated", "lawsuit"]

    def run_narrative_audit(self, asset=None):
        """
        Analyzes the sentiment log to find the 'Why' behind a move.
        Scans headlines for bullish/bearish keywords.
        """
        logger.info(f"🧠 Narrative Engine is scanning for headlines relating to {asset if asset else 'all assets'}...")
        
        with self.db.get_connection() as conn:
            # 1. Load Headlines from the last 24h
            query = "SELECT * FROM scout_sentiment_log"
            df = pd.read_sql_query(query, conn)
            
            if df.empty:
                logger.warning("⏳ No headlines found in the Black Box. Waiting for the Sentiment Scout...")
                return "NEUTRAL_SKELETON"

            # 2. Keyword Filter
            headlines = df['headline'].str.lower().tolist()
            bull_matches = [h for h in headlines if any(kw in h for kw in self.bullish_keywords)]
            bear_matches = [h for h in headlines if any(kw in h for kw in self.bearish_keywords)]
            
            score = 50 + (len(bull_matches) * 5) - (len(bear_matches) * 5)
            # Clamp 0-100
            score = max(0, min(100, score))
            
            verdict = "NARRATIVE_BULLISH" if score > 60 else ("NARRATIVE_BEARISH" if score < 40 else "NARRATIVE_NEUTRAL")
            
            logger.info(f"✅ NARRATIVE VERDICT: {verdict} (Score: {score}/100 based on {len(headlines)} headlines)")
            return verdict

    def start_loop(self, interval=3600):
        """Every hour, re-scan the news for narrative shifts."""
        logger.info(f"🏎️ Narrative Engine is online. Audit cycle: {interval}s.")
        while True:
            self.run_narrative_audit()
            time.sleep(interval)

if __name__ == "__main__":
    analyst = NarrativeEngine()
    analyst.start_loop()
