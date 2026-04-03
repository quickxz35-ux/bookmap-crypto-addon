import time
import requests
import json
import os
import sys
from pathlib import Path

LOCK_FILE = Path("bridge.pid")

if LOCK_FILE.exists():
    try:
        old_pid = int(LOCK_FILE.read_text())
        # Check if process is still running (Windows specific)
        import os
        try:
            os.kill(old_pid, 0)
            print(f"--- ⚠️ BRIDGE CONTROLLER ALREADY RUNNING (PID {old_pid}) ---")
            sys.exit(0)
        except OSError:
            # PID not found, stale lock
            LOCK_FILE.unlink()
    except Exception:
        LOCK_FILE.unlink()

LOCK_FILE.write_text(str(os.getpid()))

import atexit
atexit.register(lambda: LOCK_FILE.unlink() if LOCK_FILE.exists() else None)

# --- AUTH CONFIGURATION ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "MISSING")
SLACK_TOKEN = os.environ.get("SLACK_TOKEN", "MISSING")
ALERTS_CHANNEL = "C0A8D93VA72" # #alerts
BRAINSTORM_DB_ID = "33565df4-5a5e-80c2-8bcd-e3d5eb6952e8"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

SLACK_HEADERS = {
    "Authorization": f"Bearer {SLACK_TOKEN}",
    "Content-Type": "application/json"
}

class SpiderBridge:
    def __init__(self):
        self.processed_pings = set()

    def get_pending_requests(self):
        """Query Notion for PENDING Decision status."""
        url = f"https://api.notion.com/v1/databases/{BRAINSTORM_DB_ID}/query"
        payload = {
            "filter": {
                "property": "Decision",
                "select": {"equals": "🟡 PENDING"}
            }
        }
        res = requests.post(url, headers=NOTION_HEADERS, json=payload)
        return res.json().get("results", [])

    def get_approved_requests(self):
        """Query Notion for OK Decision status."""
        url = f"https://api.notion.com/v1/databases/{BRAINSTORM_DB_ID}/query"
        payload = {
            "filter": {
                "property": "Decision",
                "select": {"equals": "🟢 OK"}
            }
        }
        res = requests.post(url, headers=NOTION_HEADERS, json=payload)
        return res.json().get("results", [])

    def slack_ping(self, text):
        """Send a message to the Slack #alerts channel."""
        url = "https://slack.com/api/chat.postMessage"
        payload = {"channel": ALERTS_CHANNEL, "text": text}
        requests.post(url, headers=SLACK_HEADERS, json=payload)

    def trigger_intel_nitro(self, coin, category):
        """LOCAL COMMAND: Triggers your Intel Nitro (OpenVINO) engine for the approved coin."""
        print(f"🏎️  [NITRO EXECUTE] Approved: {coin} Category: {category}")
        # Here we could update a local trigger.json or run a specific analyzer.
        self.slack_ping(f"🏎️  *Intel Nitro Brain:* Triggering high-performance analysis for *{coin}* ({category}) now.")

    def check_local_blackbox(self):
        """Checks the local SQLite database for new strikes and promotions."""
        try:
            import sqlite3
            conn = sqlite3.connect("local_blackbox.sqlite")
            cursor = conn.cursor()

            # 1. Check for Whale Strikes ($500k+)
            cursor.execute("SELECT id, asset, usd_value, source FROM scout_whale_log WHERE id > ?", (self.last_whale_id,))
            strikes = cursor.fetchall()
            for s_id, asset, usd_val, source in strikes:
                msg = f"🐋  *Whale Strike!* {asset} movement of *${usd_val:,.0f}* from {source}."
                self.slack_ping(msg)
                self.last_whale_id = s_id

            # 2. Check for Elite Wallet Promotions (Win Rate > 70%)
            cursor.execute("SELECT wallet_address, win_rate FROM analyst_wallet_stats WHERE win_rate > 0.70")
            elites = cursor.fetchall()
            for addr, wr in elites:
                # Logic to add to Notion Whale Registry would go here.
                print(f"🌿 [PROMOTION] Elite Wallet Detected: {addr} ({wr*100:.0f}%)")

            conn.close()
        except Exception as e:
            print(f"⚠️ [DATABASE] SQLite Bridge Error: {e}")

    def run_bridge_loop(self):
        print("🚦 [BRIDGE] Starting Notion-to-Slack watcher (Control Room Active)...")
        self.last_whale_id = 0
        while True:
            try:
                # 1. Local Black Box Check (Whales & Elites)
                self.check_local_blackbox()

                # 2. Check for Pending (Wait for Captain's OK)
                pendings = self.get_pending_requests()
                for item in pendings:
                    item_id = item["id"]
                    if item_id not in self.processed_pings:
                        coin = item["properties"]["Coin Pick"]["rich_text"][0]["text"]["content"]
                        category = item["properties"]["Selection Category"]["select"]["name"]
                        self.slack_ping(f"📢  *Captain!* New Scout Request:\n*Coin:* {coin}\n*Category:* {category}\n*Status:* {item_id}\n👉 Approve in Notion: https://www.notion.so/{item_id.replace('-', '')}")
                        self.processed_pings.add(item_id)

                # 2. Check for Approval (Trigger NITRO)
                approved = self.get_approved_requests()
                for item in approved:
                    item_id = item["id"]
                    # If it was previously pending/processed, and is now OK, trigger NITRO
                    # (Note: In a real loop, you'd track the state shift)
                    coin = item["properties"]["Coin Pick"]["rich_text"][0]["text"]["content"]
                    category = item["properties"]["Selection Category"]["select"]["name"]
                    
                    # Simulating the trigger logic
                    print(f"✅ [CONTROL] Approved: {coin}. Firing Nitro Engine...")
                    self.trigger_intel_nitro(coin, category)
                    # Once triggered, we'd mark it 'Processed' so it doesn't loop.

                time.sleep(10) # 10s Poll Rate
            except Exception as e:
                print(f"❌ [BRIDGE ERROR] {e}")
                time.sleep(5)

if __name__ == "__main__":
    bridge = SpiderBridge()
    bridge.run_bridge_loop()
