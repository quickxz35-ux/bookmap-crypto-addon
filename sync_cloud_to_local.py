import sqlite3
import psycopg2
import os
import logging
from local_blackbox import LocalBlackBox

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FullMirrorSync:
    def __init__(self, cloud_url):
        self.cloud_url = cloud_url
        self.local_db = LocalBlackBox() # Uses SQLite by default since no URL in local ENV

    def sync_table(self, table_name, cloud_conn, local_conn):
        """Pulls missing rows from the Cloud table into the Local table."""
        try:
            cloud_cursor = cloud_conn.cursor()
            local_cursor = local_conn.cursor()
            
            # 1. Get last Local ID
            local_cursor.execute(f"SELECT MAX(id) FROM {table_name}")
            last_id = local_cursor.fetchone()[0] or 0
            
            # 2. Fetch new rows from Cloud
            logger.info(f"🚚 [SYNC] Polling {table_name} for records after ID {last_id}...")
            cloud_cursor.execute(f"SELECT * FROM {table_name} WHERE id > %s", (last_id,))
            rows = cloud_cursor.fetchall()
            
            if not rows:
                logger.debug(f"✅ {table_name} is already in sync.")
                return 0

            # 3. Batch Insert into Local
            placeholders = ",".join(["?" for _ in range(len(rows[0]))])
            local_cursor.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", rows)
            
            local_conn.commit()
            logger.info(f"✅ Synchronized {len(rows)} records for {table_name}.")
            return len(rows)
            
        except Exception as e:
            logger.error(f"❌ Error syncing {table_name}: {e}")
            return 0

    def run_full_mirror(self):
        """Mirrors all tracked tables from Cloud to Local."""
        logger.info("🏎️  Starting Full Mirror Sync (Cloud -> Local)...")
        
        try:
            cloud_conn = psycopg2.connect(self.cloud_url)
            local_conn = self.local_db.get_connection()
            
            tables = ["scout_whale_log", "scout_sentiment_log", "scout_deriv_snapshots", "scout_wallet_tx"]
            total_synced = 0
            
            for table in tables:
                total_synced += self.sync_table(table, cloud_conn, local_conn)
            
            logger.info(f"🏁 Full Mirror Complete. Total synchronized rows: {total_synced}.")
            
            cloud_conn.close()
            local_conn.close()
            
        except Exception as e:
            logger.error(f"❌ Bridge Failure: {e}")

if __name__ == "__main__":
    # To run: Set 'DATABASE_URL' in your Local environment pointing to Railway then run this script.
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ ERROR: Please set the 'DATABASE_URL' (Railway Postgres URL) in your local environment first.")
    else:
        sync = FullMirrorSync(db_url)
        sync.run_full_mirror()
