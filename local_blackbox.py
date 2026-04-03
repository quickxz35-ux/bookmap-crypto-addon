import sqlite3
import os
import psycopg2 # Postgres for Cloud
from psycopg2.extras import RealDictCursor
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LocalBlackBox:
    def __init__(self, db_path="local_blackbox.sqlite"):
        self.db_url = os.getenv("DATABASE_URL")
        self.is_cloud = self.db_url is not None
        if not self.is_cloud:
            self.db_path = db_path
            self.init_db()
        else:
            logger.info("🛰️ [CONFIG] Cloud Postgres detected. Shifting to Railway persistence.")

    def get_connection(self):
        """Returns a connection based on the available environment."""
        if self.is_cloud:
            # Postgres (psycopg2)
            return psycopg2.connect(self.db_url)
        else:
            # Local SQLite
            return sqlite3.connect(self.db_path)

    def init_db(self):
        """Initializes the SQLite database with all required Scout and Analyst tables."""
        logger.info(f"🚀 Initializing Local Black Box at {self.db_path}...")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # --- SCOUT TABLES (Raw Recorders) ---
            
            # 1. Whale Scout - CEX Flows & Bulk Moves
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scout_whale_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    asset TEXT NOT NULL,
                    source TEXT, -- Binance, Bybit, etc.
                    move_type TEXT, -- INFLOW, OUTFLOW, BULK_BUY
                    amount REAL,
                    usd_value REAL,
                    raw_payload TEXT
                )
            ''')
            
            # 2. Derivatives Scout - 10-Min Snapshots
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scout_deriv_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    asset TEXT NOT NULL,
                    oi_raw REAL,
                    funding_rate REAL,
                    liquidations_24h REAL,
                    long_short_ratio REAL,
                    net_position REAL,
                    volume_15m REAL,
                    volume_1h REAL,
                    volume_4h REAL,
                    volume_24h REAL
                )
            ''')
            
            # 3. Sentiment Scout - News Headlines
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scout_sentiment_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    asset TEXT,
                    source TEXT, -- CryptoPanic, X, etc.
                    headline TEXT,
                    url TEXT,
                    raw_sentiment_score REAL -- Optional placeholder
                )
            ''')
            
            # 4. Wallet Tracking Scout - Raw Trans/Balances
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scout_wallet_tx (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    wallet_address TEXT NOT NULL,
                    tx_hash TEXT UNIQUE,
                    asset TEXT,
                    amount REAL,
                    usd_value REAL,
                    tx_type TEXT, -- IN, OUT, SWAP
                    counterparty TEXT
                )
            ''')
            
            # 5. Wallet Registry (Mirror from Notion)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS wallet_watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallet_address TEXT UNIQUE,
                    alias TEXT,
                    category TEXT, -- Smart Money, VC, Exchange
                    is_active BOOLEAN DEFAULT 1,
                    last_balance_check DATETIME
                )
            ''')
            
            # --- ANALYST TABLES (Computed Intelligence) ---
            
            # P/L Cache for Wallets
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS analyst_wallet_stats (
                    wallet_address TEXT PRIMARY KEY,
                    win_rate REAL,
                    total_pnl_usd REAL,
                    best_trade_ticker TEXT,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(wallet_address) REFERENCES wallet_watchlist(wallet_address)
                )
            ''')
            
            conn.commit()
            logger.info("✅ Database Foundation established. Black Box is ready for recording.")

if __name__ == "__main__":
    # Test Init
    LocalBlackBox()
