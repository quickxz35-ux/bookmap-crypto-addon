import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

import feedparser
import requests

from local_blackbox import LocalBlackBox
from symbol_utils import normalize_asset_symbol

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# List of free crypto RSS feeds
RSS_FEEDS = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/feed",
    "decrypt": "https://decrypt.co/feed"
}


class SentimentScout:
    """
    Zero-Cost Sentiment Scouter: Replaced paid CryptoPanic API with 
    free RSS aggregators for CoinDesk, Cointelegraph, and Decrypt.
    """
    def __init__(self):
        self.db = LocalBlackBox()
        self.session = requests.Session()
        self.bullish_keywords = ["surge", "partnership", "approval", "launch", "breakout", "buy", "bullish"]
        self.bearish_keywords = ["hack", "exploit", "delay", "lawsuit", "drop", "liquidation", "sell", "bearish"]

    def fetch_rss_news(self) -> List[Dict[str, object]]:
        """Aggregates latest stories from all defined RSS feeds."""
        all_results = []
        for provider, url in RSS_FEEDS.items():
            try:
                logger.info(f"📡 Polling RSS feed: {provider}...")
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    all_results.append({
                        "id": entry.get("id", entry.get("link")),
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "published_at": entry.get("published", datetime.now(timezone.utc).isoformat()),
                        "domain": provider,
                        "summary": entry.get("summary", ""),
                        "category": entry.get("tags", [{}])[0].get("term", "news") if entry.get("tags") else "news"
                    })
            except Exception as exc:
                logger.error(f"Error fetching {provider} RSS: {exc}")
        
        return all_results

    def _extract_assets(self, story: Dict[str, object]) -> List[str]:
        """Simple extraction based on keywords in title and summary."""
        text = (str(story.get("title", "")) + " " + str(story.get("summary", ""))).upper()
        # We'll use a common set of assets to check for
        common_assets = ["BTC", "ETH", "SOL", "PEPE", "SHIB", "DOGE", "XRP", "ADA", "AVAX"]
        found = []
        for asset in common_assets:
            if f" {asset} " in f" {text} " or f"({asset})" in text:
                found.append(normalize_asset_symbol(asset))
        
        return list(set(found))

    def _normalized_sentiment(self, story: Dict[str, object]) -> Dict[str, object]:
        """Keyword-based sentiment scoring on both headline and summary."""
        text = (str(story.get("title", "")) + " " + str(story.get("summary", ""))).lower()
        
        bull_matches = [kw for kw in self.bullish_keywords if kw in text]
        bear_matches = [kw for kw in self.bearish_keywords if kw in text]
        
        # Simple score based on match count
        score = 0.0
        if bull_matches or bear_matches:
            score = (len(bull_matches) - len(bear_matches)) / max(1, (len(bull_matches) + len(bear_matches)))
        
        # Dampen score slightly as it's purely keyword-based
        score = score * 0.8

        if score >= 0.2:
            label = "positive"
        elif score <= -0.2:
            label = "negative"
        else:
            label = "neutral"

        return {"label": label, "score": max(-1.0, min(1.0, score))}

    def _dedup_key(self, story: Dict[str, object]) -> str:
        url = str(story.get("url") or "").strip().lower()
        return hashlib.sha1(url.encode("utf-8")).hexdigest()

    def _story_rows(self, story: Dict[str, object]) -> List[Dict[str, object]]:
        assets = self._extract_assets(story)
        normalized = self._normalized_sentiment(story)
        dedup_key = self._dedup_key(story)
        
        rows = []
        target_assets = assets or [None]
        
        for asset in target_assets:
            story_id = f"{dedup_key}:{asset}" if asset else dedup_key
            rows.append({
                "story_id": story_id,
                "published_at": story["published_at"],
                "asset": asset,
                "source_provider": story["domain"],
                "source_domain": story["domain"],
                "headline": story["title"],
                "url": story["url"],
                "sentiment_label_raw": normalized["label"],
                "sentiment_score_raw": normalized["score"],
                "topic_tags_json": json.dumps([story["domain"], "rss"]),
                "dedup_key": dedup_key,
                "raw_payload_json": json.dumps(story, sort_keys=True)
            })
        return rows

    def record_news(self, news_list: List[Dict[str, object]]) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            new_count = 0
            for story in news_list:
                for row in self._story_rows(story):
                    cursor.execute("SELECT story_id FROM sentiment_logs WHERE story_id = ?", (row["story_id"],))
                    if cursor.fetchone():
                        continue
                    
                    # Log to both normalized and legacy tables for backward compatibility
                    cursor.execute("""
                        INSERT INTO sentiment_logs (
                            story_id, published_at, asset, source_provider, source_domain, headline, url,
                            sentiment_label_raw, sentiment_score_raw, topic_tags_json, dedup_key, raw_payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row["story_id"], row["published_at"], row["asset"], row["source_provider"],
                        row["source_domain"], row["headline"], row["url"], row["sentiment_label_raw"],
                        row["sentiment_score_raw"], row["topic_tags_json"], row["dedup_key"], row["raw_payload_json"]
                    ))
                    
                    cursor.execute("""
                        INSERT INTO scout_sentiment_log (
                            asset, source, headline, url, raw_sentiment_score, story_id, published_at,
                            source_domain, sentiment_label_raw, topic_tags_json, dedup_key, raw_payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row["asset"], row["source_provider"], row["headline"], row["url"],
                        row["sentiment_score_raw"], row["story_id"], row["published_at"],
                        row["source_domain"], row["sentiment_label_raw"], row["topic_tags_json"],
                        row["dedup_key"], row["raw_payload_json"]
                    ))
                    new_count += 1
            conn.commit()
            if new_count > 0:
                logger.info(f"✅ Recorded {new_count} new news stories from RSS.")

    def run(self, interval: int = 300) -> None:
        logger.info(f"🏎️ RSS Sentiment Scout is online. Pulse: {interval}s.")
        while True:
            news = self.fetch_rss_news()
            if news:
                self.record_news(news)
            time.sleep(interval)


if __name__ == "__main__":
    scout = SentimentScout()
    scout.run()
