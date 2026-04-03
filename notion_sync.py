import requests
import json
import os

# --- CONFIGURATION (Confirmed GOOGLETOKEN) ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "MISSING")
NOTION_VERSION = "2022-06-28"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION
}

class NotionHub:
    def __init__(self):
        self.base_url = "https://api.notion.com/v1"

    def search_pages(self, query=""):
        """Search for pages/databases the integration has access to."""
        url = f"{self.base_url}/search"
        payload = {"query": query}
        response = requests.post(url, headers=HEADERS, json=payload)
        return response.json()

    def create_database(self, parent_page_id, title, properties):
        """Create a new database under a parent page."""
        url = f"{self.base_url}/databases"
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties
        }
        response = requests.post(url, headers=HEADERS, json=payload)
        return response.json()

    def add_row(self, database_id, data):
        """Add a row to a database."""
        url = f"{self.base_url}/pages"
        payload = {
            "parent": {"database_id": database_id},
            "properties": data
        }
        response = requests.post(url, headers=HEADERS, json=payload)
        return response.json()

# --- WORKSPACE MAPPING ---
PARENT_HUB_ID = "33565df45a5e808c943bebcc2d436f5c"

def setup_whale_registry():
    hub = NotionHub()
    print("🚀 [NOTION] Carving out 'Whale Registry'...")
    
    properties = {
        "Name": {"title": {}},
        "Address": {"rich_text": {}},
        "Balance (USD)": {"number": {"format": "dollar"}},
        "Chain": {"select": {"options": [
            {"name": "Ethereum", "color": "blue"},
            {"name": "Solana", "color": "purple"},
            {"name": "Bitcoin", "color": "orange"}
        ]}},
        "PnL Ratio": {"number": {"format": "percent"}},
        "Status": {"select": {"options": [
            {"name": "🟢 Active", "color": "green"},
            {"name": "🟡 Idle", "color": "yellow"},
            {"name": "🔴 Vetoed", "color": "red"}
        ]}},
        "Last Trade": {"date": {}}
    }
    
    result = hub.create_database(PARENT_HUB_ID, "🐋 Whale Registry (Spider Bubble)", properties)
    if "id" in result:
        print(f"✅ [SUCCESS] Whale Registry Created! ID: {result['id']}")
    else:
        print("❌ [FAILED] Check error:")
        print(json.dumps(result, indent=2))

def submit_test_request():
    hub = NotionHub()
    print("🚀 [NOTION] Submitting Sample Selection Request...")
    
    data = {
        "Idea": {"title": [{"text": {"content": "Test BTC Scalp (Manual Submission)"}}]},
        "Decision": {"select": {"name": "🟡 PENDING"}},
        "Coin Pick": {"rich_text": [{"text": {"content": "BTCUSDT"}}]},
        "Selection Category": {"select": {"name": "⚡ 30m Scalp"}},
        "Priority": {"select": {"name": "High"}},
        "Category": {"select": {"name": "Activation"}}
    }
    
    result = hub.add_row(BRAINSTORM_DB_ID, data)
    if "id" in result:
        print(f"✅ [SUCCESS] Request Submitted! ID: {result['id']}")
    else:
        print("❌ [FAILED] Check error:")
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    submit_test_request()
