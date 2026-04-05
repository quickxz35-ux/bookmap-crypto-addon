from scout_sentiment import SentimentScout
import logging

def test_free_news_flow():
    # Disable actual DB writing for the test to avoid junk data
    scout = SentimentScout()
    
    print("🛰️ Testing RSS fetch from CoinDesk/Cointelegraph/Decrypt...")
    news = scout.fetch_rss_news()
    
    if not news:
        print("❌ No news items found. Check internet connection or RSS URLs.")
        return

    print(f"✅ Found {len(news)} total news items.")
    
    # Test a sample item
    sample = news[0]
    print(f"\n--- Sample Item ---")
    print(f"Source: {sample['domain']}")
    print(f"Title: {sample['title']}")
    print(f"Link: {sample['url']}")
    
    # Test sentiment logic
    sentiment = scout._normalized_sentiment(sample)
    print(f"Calculated Sentiment: {sentiment['label']} (Score: {sentiment['score']:.2f})")
    
    # Test asset extraction
    assets = scout._extract_assets(sample)
    print(f"Extracted Assets: {assets}")

if __name__ == "__main__":
    test_free_news_flow()
