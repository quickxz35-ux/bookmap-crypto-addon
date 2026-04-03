import requests
import time
import os
import logging
from local_blackbox import LocalBlackBox

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Try to get key from environment, fallback to None
CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "YOUR_CRYPTOPANIC_KEY_HERE")
BASE_URL = "https://cryptopanic.com/api/v1/posts/"

class SentimentScout:
    def __init__(self):
        self.db = LocalBlackBox()
        self.api_key = CRYPTOPANIC_API_KEY

    def fetch_latest_news(self):
        """Fetches the latest news headlines from CryptoPanic."""
        if self.api_key == "YOUR_CRYPTOPANIC_KEY_HERE":
            logger.warning("⚠️ CRYPTOPANIC_API_KEY not set. Please add it to your .env file.")
            return []

        params = {
            "auth_token": self.api_key,
            "public": "true",
            "metadata": "true"
        }

        try:
            response = requests.get(BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except Exception as e:
            logger.error(f"❌ Error fetching news: {e}")
            return []

    def record_news(self, news_list):
        """Saves new headlines to the Local Black Box."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            new_count = 0
            
            for story in news_list:
                headline = story.get("title")
                url = story.get("url")
                source = story.get("domain")
                published_at = story.get("published_at")
                
                # Check uniqueness via URL
                cursor.execute("SELECT id FROM scout_sentiment_log WHERE url = ?", (url,))
                if not cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO scout_sentiment_log (asset, source, headline, url)
                        VALUES (?, ?, ?, ?)
                    ''', (None, source, headline, url))
                    new_count += 1
            
            conn.commit()
            if new_count > 0:
                logger.info(f"✅ Recorded {new_count} new headlines to the Black Box.")

    def run(self, interval=300):
        """Infinite loop to poll for news."""
        logger.info(f"🛰️ Sentiment Scout (CryptoPanic) is online. Polling every {interval}s...")
        while True:
            news = self.fetch_latest_news()
            if news:
                self.record_news(news)
            time.sleep(interval)

if __name__ == "__main__":
    scout = SentimentScout()
    scout.run()
