import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List

import requests

from local_blackbox import LocalBlackBox
from symbol_utils import normalize_asset_symbol


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "YOUR_CRYPTOPANIC_KEY_HERE")
BASE_URL = "https://cryptopanic.com/api/v1/posts/"


class SentimentScout:
    def __init__(self):
        self.db = LocalBlackBox()
        self.api_key = CRYPTOPANIC_API_KEY
        self.session = requests.Session()

    def fetch_latest_news(self) -> List[Dict[str, object]]:
        if self.api_key == "YOUR_CRYPTOPANIC_KEY_HERE":
            logger.warning("CRYPTOPANIC_API_KEY not set. Sentiment Scout is idle.")
            return []

        params = {
            "auth_token": self.api_key,
            "public": "true",
            "metadata": "true",
        }
        try:
            response = self.session.get(BASE_URL, params=params, timeout=20)
            response.raise_for_status()
            return response.json().get("results", [])
        except Exception as exc:
            logger.error("Error fetching CryptoPanic news: %s", exc)
            return []

    def _extract_assets(self, story: Dict[str, object]) -> List[str]:
        currencies = story.get("currencies") or []
        assets = []
        for currency in currencies:
            code = currency.get("code") if isinstance(currency, dict) else None
            if code:
                assets.append(normalize_asset_symbol(str(code)))
        deduped = []
        for asset in assets:
            if asset and asset not in deduped:
                deduped.append(asset)
        return deduped

    def _topic_tags(self, story: Dict[str, object], assets: Iterable[str]) -> List[str]:
        tags = []
        kind = story.get("kind")
        domain = story.get("domain")
        if kind:
            tags.append(str(kind).lower())
        if domain:
            tags.append(str(domain).lower())
        tags.extend(asset for asset in assets if asset)
        return tags

    def _normalized_sentiment(self, story: Dict[str, object]) -> Dict[str, object]:
        votes = story.get("votes") or {}
        positive_votes = int(votes.get("positive", 0) or 0)
        negative_votes = int(votes.get("negative", 0) or 0)
        important_votes = int(votes.get("important", 0) or 0)
        total_votes = positive_votes + negative_votes + important_votes

        score = 0.0
        if total_votes:
            score = (positive_votes - negative_votes) / total_votes

        headline = str(story.get("title") or "").lower()
        bullish_terms = ("surge", "partnership", "approval", "launch", "breakout")
        bearish_terms = ("hack", "exploit", "delay", "lawsuit", "drop", "liquidation")
        if any(term in headline for term in bullish_terms):
            score += 0.15
        if any(term in headline for term in bearish_terms):
            score -= 0.15

        if score >= 0.2:
            label = "positive"
        elif score <= -0.2:
            label = "negative"
        else:
            label = "neutral"

        return {"label": label, "score": max(-1.0, min(1.0, score))}

    def _dedup_key(self, story: Dict[str, object]) -> str:
        url = str(story.get("url") or "").strip().lower()
        title = str(story.get("title") or "").strip().lower()
        domain = str(story.get("domain") or "").strip().lower()
        seed = url or f"{domain}|{title}"
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()

    def _story_rows(self, story: Dict[str, object]) -> List[Dict[str, object]]:
        assets = self._extract_assets(story)
        normalized = self._normalized_sentiment(story)
        dedup_key = self._dedup_key(story)
        published_at = story.get("published_at") or datetime.now(timezone.utc).isoformat()
        source_domain = story.get("domain") or ""
        url = story.get("url") or ""
        headline = story.get("title") or ""
        tags = self._topic_tags(story, assets)
        base_id = str(story.get("id") or dedup_key)
        target_assets = assets or [None]

        rows = []
        for asset in target_assets:
            story_id = f"{base_id}:{asset}" if asset else str(base_id)
            rows.append(
                {
                    "story_id": story_id,
                    "published_at": published_at,
                    "asset": asset,
                    "source_provider": "cryptopanic",
                    "source_domain": source_domain,
                    "headline": headline,
                    "url": url,
                    "sentiment_label_raw": normalized["label"],
                    "sentiment_score_raw": normalized["score"],
                    "topic_tags_json": json.dumps(tags),
                    "dedup_key": dedup_key,
                    "raw_payload_json": json.dumps(story, sort_keys=True),
                }
            )
        return rows

    def record_news(self, news_list: List[Dict[str, object]]) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            new_count = 0
            for story in news_list:
                for row in self._story_rows(story):
                    cursor.execute(
                        "SELECT story_id FROM sentiment_logs WHERE story_id = ?",
                        (row["story_id"],),
                    )
                    if cursor.fetchone():
                        continue
                    cursor.execute(
                        """
                        INSERT INTO sentiment_logs (
                            story_id, published_at, asset, source_provider, source_domain, headline, url,
                            sentiment_label_raw, sentiment_score_raw, topic_tags_json, dedup_key, raw_payload_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["story_id"],
                            row["published_at"],
                            row["asset"],
                            row["source_provider"],
                            row["source_domain"],
                            row["headline"],
                            row["url"],
                            row["sentiment_label_raw"],
                            row["sentiment_score_raw"],
                            row["topic_tags_json"],
                            row["dedup_key"],
                            row["raw_payload_json"],
                        ),
                    )
                    cursor.execute(
                        """
                        INSERT INTO scout_sentiment_log (
                            asset, source, headline, url, raw_sentiment_score, story_id, published_at,
                            source_domain, sentiment_label_raw, topic_tags_json, dedup_key, raw_payload_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["asset"],
                            row["source_provider"],
                            row["headline"],
                            row["url"],
                            row["sentiment_score_raw"],
                            row["story_id"],
                            row["published_at"],
                            row["source_domain"],
                            row["sentiment_label_raw"],
                            row["topic_tags_json"],
                            row["dedup_key"],
                            row["raw_payload_json"],
                        ),
                    )
                    new_count += 1

            conn.commit()
            if new_count > 0:
                logger.info("Recorded %s normalized sentiment rows", new_count)

    def run(self, interval: int = 300) -> None:
        logger.info("Sentiment Scout is online. Polling every %ss", interval)
        while True:
            news = self.fetch_latest_news()
            if news:
                self.record_news(news)
            time.sleep(interval)


if __name__ == "__main__":
    scout = SentimentScout()
    scout.run()
