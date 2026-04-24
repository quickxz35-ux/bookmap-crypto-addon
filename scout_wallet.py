import requests
import time
import sqlite3
import os
import logging
import json
import hashlib
import threading
from datetime import datetime, timedelta, timezone
from local_blackbox import LocalBlackBox

try:
    import websocket
except ImportError:  # pragma: no cover - optional locally until requirements install
    websocket = None

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WalletScout:
    def __init__(self):
        self.db = LocalBlackBox()
        self.source_provider = "hyperscreener"
        self.leaderboard_url = os.getenv(
            "HYPERSCREENER_LEADERBOARD_URL",
            "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard",
        )
        self.top_wallet_limit = int(os.getenv("HYPERSCREENER_TOP_WALLETS", "1000"))
        self.hyperliquid_info_url = os.getenv("HYPERLIQUID_INFO_URL", "https://api.hyperliquid.xyz/info")
        self.hyperliquid_lookback_days = int(os.getenv("HYPERLIQUID_LOOKBACK_DAYS", "7"))
        self.hyperliquid_ws_url = os.getenv("HYPERLIQUID_WS_URL", "wss://api.hyperliquid.xyz/ws")
        self.hyperliquid_ws_enabled = os.getenv("HYPERLIQUID_WS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        self.hyperliquid_ws_wallet_limit = int(os.getenv("HYPERLIQUID_WS_WALLET_LIMIT", "50"))
        self.hyperliquid_backfill_wallet_limit = int(os.getenv("HYPERLIQUID_BACKFILL_WALLET_LIMIT", "50"))
        self.hyperliquid_rotation_seconds = int(os.getenv("HYPERLIQUID_ROTATION_SECONDS", "300"))
        self._ws_stop = threading.Event()
        self._ws_thread = None
        self._ws_app = None
        self._ws_target_wallets = tuple()
        self._ws_wallet_meta = {}

    def get_active_watchlist(self):
        """Fetches the currently active wallet addresses from the Black Box."""
        ph = self.db.qmark
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT wallet_address, alias, display_name, top_rank, account_value
                FROM wallet_watchlist
                WHERE is_active = 1 AND COALESCE(source_provider, {ph}) = {ph}
                ORDER BY COALESCE(top_rank, 999999) ASC, wallet_address ASC
                """,
                (self.source_provider, self.source_provider),
            )
            return cursor.fetchall()

    def _select_live_wallets(self, watchlist):
        live_rows = list(watchlist[: self.hyperliquid_ws_wallet_limit])
        wallet_meta = {row["wallet_address"]: row for row in live_rows}
        target_wallets = tuple(sorted(wallet_meta))
        return target_wallets, wallet_meta

    def _select_backfill_wallets(self, watchlist):
        remaining = list(watchlist[self.hyperliquid_ws_wallet_limit :])
        if not remaining:
            return []
        batch_size = min(self.hyperliquid_backfill_wallet_limit, len(remaining))
        cycle_index = int(datetime.now(timezone.utc).timestamp() // max(1, self.hyperliquid_rotation_seconds))
        offset = (cycle_index * batch_size) % len(remaining)
        selected = remaining[offset : offset + batch_size]
        if len(selected) < batch_size:
            selected.extend(remaining[: batch_size - len(selected)])
        return selected

    def _touch_wallet_watchlist(self, address):
        ph = self.db.qmark
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                UPDATE wallet_watchlist
                SET last_balance_check = CURRENT_TIMESTAMP,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE wallet_address = {ph}
                """,
                (address,),
            )
            conn.commit()

    def _coerce_amount(self, value):
        try:
            if value in (None, "", "null"):
                return 0.0
            return float(value)
        except Exception:
            return 0.0

    def _normalize_ws_event(self, event, subscribed_wallet):
        if not isinstance(event, dict):
            return None

        wallet_address = (
            (event.get("user") or event.get("wallet") or event.get("address") or subscribed_wallet or "").strip().lower()
        )
        if not wallet_address:
            return None

        timestamp = event.get("time") or event.get("timestamp")
        if isinstance(timestamp, int):
            timestamp = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat()
        elif not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        raw_hash = event.get("hash") or event.get("txHash") or event.get("transactionHash")
        tx_hash = raw_hash or hashlib.sha1(json.dumps(event, sort_keys=True, default=str).encode("utf-8")).hexdigest()

        asset = event.get("coin") or event.get("asset") or event.get("symbol") or event.get("token") or "USDC"
        counterparty = event.get("counterparty") or event.get("to") or event.get("from") or event.get("address")
        tx_type = (event.get("type") or event.get("eventType") or event.get("action") or event.get("dir") or "LEDGER_UPDATE")
        amount = event.get("amount")
        if amount is None:
            amount = event.get("sz") or event.get("size") or event.get("usdValue") or event.get("value")

        delta = event.get("delta")
        if isinstance(delta, dict):
            for key in ("deposit", "withdraw", "transfer", "liquidation", "delegate", "undelegate"):
                if key in delta:
                    tx_type = key.upper()
                    nested = delta.get(key)
                    if isinstance(nested, dict):
                        asset = nested.get("coin") or nested.get("asset") or asset
                        amount = nested.get("amount") or nested.get("value") or amount
                        counterparty = nested.get("to") or nested.get("from") or nested.get("validator") or counterparty
                    break
            if "coin" in delta:
                asset = delta.get("coin") or asset
            if amount in (None, ""):
                amount = delta.get("amount") or delta.get("value") or amount

        normalized = {
            "timestamp": timestamp,
            "wallet_address": wallet_address,
            "tx_hash": tx_hash,
            "asset": asset,
            "amount": self._coerce_amount(amount),
            "tx_type": str(tx_type).upper(),
            "source_provider": "hyperliquid_ws",
            "counterparty": counterparty,
            "raw_payload_json": json.dumps(event, default=str),
        }
        return normalized

    def fetch_leaderboard(self):
        """Fetch the public Hyperliquid trader leaderboard from Hyperscreener."""
        response = requests.get(self.leaderboard_url, timeout=45)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("leaderboardRows", [])
        normalized_rows = []
        for index, row in enumerate(rows[: self.top_wallet_limit], start=1):
            wallet_address = (row.get("ethAddress") or "").strip().lower()
            if not wallet_address:
                continue
            normalized_rows.append(
                {
                    "wallet_address": wallet_address,
                    "display_name": row.get("displayName") or None,
                    "account_value": float(row.get("accountValue") or 0),
                    "rank": index,
                    "raw_payload": row,
                }
            )
        return normalized_rows

    def _get_previous_leaderboard_state(self):
        ph = self.db.qmark
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT wallet_address, rank
                FROM wallet_leaderboard_snapshots
                WHERE source_provider = {ph}
                  AND observed_at = (
                    SELECT MAX(observed_at)
                    FROM wallet_leaderboard_snapshots
                    WHERE source_provider = {ph}
                  )
                """,
                (self.source_provider, self.source_provider),
            )
            return {row["wallet_address"]: row["rank"] for row in cursor.fetchall()}

    def _upsert_watchlist(self, rows, observed_at):
        ph = self.db.qmark
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for row in rows:
                wallet_address = row["wallet_address"]
                display_name = row["display_name"]
                alias = display_name or wallet_address[:10]
                cursor.execute(
                    f"""
                    INSERT INTO wallet_watchlist (
                        wallet_address,
                        alias,
                        category,
                        is_active,
                        last_balance_check,
                        source_provider,
                        display_name,
                        top_rank,
                        account_value,
                        first_seen_at,
                        last_seen_at
                    )
                    VALUES ({ph}, {ph}, {ph}, 1, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    ON CONFLICT(wallet_address) DO UPDATE SET
                        alias = excluded.alias,
                        category = excluded.category,
                        is_active = 1,
                        last_balance_check = excluded.last_balance_check,
                        source_provider = excluded.source_provider,
                        display_name = excluded.display_name,
                        top_rank = excluded.top_rank,
                        account_value = excluded.account_value,
                        first_seen_at = COALESCE(wallet_watchlist.first_seen_at, excluded.first_seen_at),
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        wallet_address,
                        alias,
                        "hyperscreener_top",
                        observed_at,
                        self.source_provider,
                        display_name,
                        row["rank"],
                        row["account_value"],
                        observed_at,
                        observed_at,
                    ),
                )
            conn.commit()

    def _record_leaderboard_audit(self, rows, observed_at, previous_state):
        ph = self.db.qmark
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for row in rows:
                wallet_address = row["wallet_address"]
                previous_rank = previous_state.get(wallet_address)
                current_rank = row["rank"]
                change_type = "NEW_WALLET" if previous_rank is None else "RANK_CHANGE" if previous_rank != current_rank else "UNCHANGED"
                snapshot_id = hashlib.sha1(
                    f"{observed_at}|{wallet_address}|{current_rank}".encode("utf-8")
                ).hexdigest()
                cursor.execute(
                    f"""
                    INSERT INTO wallet_leaderboard_snapshots (
                        snapshot_id,
                        observed_at,
                        source_provider,
                        source_url,
                        wallet_address,
                        display_name,
                        rank,
                        account_value,
                        is_new_wallet,
                        raw_payload_json
                    )
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    ON CONFLICT(snapshot_id) DO UPDATE SET
                        observed_at = excluded.observed_at,
                        source_provider = excluded.source_provider,
                        source_url = excluded.source_url,
                        wallet_address = excluded.wallet_address,
                        display_name = excluded.display_name,
                        rank = excluded.rank,
                        account_value = excluded.account_value,
                        is_new_wallet = excluded.is_new_wallet,
                        raw_payload_json = excluded.raw_payload_json
                    """,
                    (
                        snapshot_id,
                        observed_at,
                        self.source_provider,
                        self.leaderboard_url,
                        wallet_address,
                        row["display_name"],
                        current_rank,
                        row["account_value"],
                        1 if previous_rank is None else 0,
                        json.dumps(row["raw_payload"], default=str),
                    ),
                )
                if change_type != "UNCHANGED":
                    change_id = hashlib.sha1(
                        f"{observed_at}|{wallet_address}|{change_type}|{current_rank}".encode("utf-8")
                    ).hexdigest()
                    cursor.execute(
                        f"""
                        INSERT INTO wallet_leaderboard_changes (
                            change_id,
                            observed_at,
                            source_provider,
                            wallet_address,
                            display_name,
                            previous_rank,
                            current_rank,
                            change_type,
                            raw_payload_json
                        )
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                        ON CONFLICT(change_id) DO UPDATE SET
                            observed_at = excluded.observed_at,
                            source_provider = excluded.source_provider,
                            wallet_address = excluded.wallet_address,
                            display_name = excluded.display_name,
                            previous_rank = excluded.previous_rank,
                            current_rank = excluded.current_rank,
                            change_type = excluded.change_type,
                            raw_payload_json = excluded.raw_payload_json
                        """,
                        (
                            change_id,
                            observed_at,
                            self.source_provider,
                            wallet_address,
                            row["display_name"],
                            previous_rank,
                            current_rank,
                            change_type,
                            json.dumps(
                                {
                                    "wallet_address": wallet_address,
                                    "display_name": row["display_name"],
                                    "previous_rank": previous_rank,
                                    "current_rank": current_rank,
                                    "account_value": row["account_value"],
                                },
                                default=str,
                            ),
                        ),
                    )
            conn.commit()

    def fetch_transactions(self, address, limit=10):
        """Fetch recent fills for a specific address from the public Hyperliquid info API."""
        try:
            address = (address or "").strip().lower()
            if not address:
                return []
            transactions = []
            start_time = int(
                (datetime.now(timezone.utc) - timedelta(days=self.hyperliquid_lookback_days)).timestamp() * 1000
            )
            while len(transactions) < limit:
                body = {
                    "type": "userFillsByTime",
                    "user": address,
                    "startTime": start_time,
                    "endTime": int(datetime.now(timezone.utc).timestamp() * 1000),
                    "aggregateByTime": True,
                }

                response = requests.post(self.hyperliquid_info_url, json=body, timeout=45)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list) or not payload:
                    break
                transactions.extend(payload)
                oldest_time = None
                for item in payload:
                    item_time = item.get("time")
                    if isinstance(item_time, int):
                        oldest_time = item_time if oldest_time is None else min(oldest_time, item_time)
                if oldest_time is None:
                    break
                start_time = max(0, oldest_time - 1)
                if len(payload) < 2000:
                    break
            return transactions[:limit]
        except Exception as e:
            logger.error(f"❌ Error fetching transactions for {address}: {e}")
            return []

    def _handle_websocket_message(self, message):
        try:
            payload = json.loads(message) if isinstance(message, str) else message
        except Exception:
            return

        if not isinstance(payload, dict):
            return

        if payload.get("isSnapshot") or (isinstance(payload.get("data"), dict) and payload["data"].get("isSnapshot")):
            return

        channel = payload.get("channel")
        if channel not in {"userNonFundingLedgerUpdates", "userNonFundingLedgerUpdate"}:
            return

        subscribed_wallet = (
            payload.get("user")
            or payload.get("wallet")
            or (payload.get("subscription") or {}).get("user")
            or (payload.get("data") or {}).get("user")
            or ""
        ).strip().lower()
        if not subscribed_wallet:
            return

        data = payload.get("data")
        if data is None:
            return
        events = data if isinstance(data, list) else [data]
        normalized = []
        for event in events:
            item = self._normalize_ws_event(event, subscribed_wallet)
            if item:
                wallet_meta = self._ws_wallet_meta.get(subscribed_wallet, {})
                item["wallet_rank"] = wallet_meta.get("top_rank")
                item["leaderboard_snapshot_at"] = wallet_meta.get("last_seen_at") or datetime.now(timezone.utc).isoformat()
                normalized.append(item)

        if not normalized:
            return

        self.record_transactions(subscribed_wallet, normalized)

    def _run_websocket_monitor(self):
        if not self.hyperliquid_ws_enabled or websocket is None:
            return

        backoff = 5
        while not self._ws_stop.is_set():
            target_wallets = tuple(self._ws_target_wallets)
            if not target_wallets:
                if self._ws_stop.wait(15):
                    break
                continue

            try:
                wallet_count = len(target_wallets)

                def on_open(app):
                    logger.info("🔌 Hyperliquid websocket online for %s wallets", wallet_count)
                    for wallet in target_wallets:
                        app.send(
                            json.dumps(
                                {
                                    "method": "subscribe",
                                    "subscription": {
                                        "type": "userNonFundingLedgerUpdates",
                                        "user": wallet,
                                    },
                                }
                            )
                        )

                def on_message(app, message):
                    self._ws_app = app
                    self._handle_websocket_message(message)

                def on_error(app, error):
                    logger.warning("⚠️ Hyperliquid websocket error: %s", error)

                def on_close(app, close_status_code, close_msg):
                    logger.info("🔌 Hyperliquid websocket closed (%s, %s)", close_status_code, close_msg)

                self._ws_app = websocket.WebSocketApp(
                    self.hyperliquid_ws_url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                )
                self._ws_app.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as exc:
                logger.warning("⚠️ Hyperliquid websocket reconnecting after error: %s", exc)

            if self._ws_stop.wait(backoff):
                break
            backoff = min(backoff * 2, 60)

    def ensure_websocket_monitor(self, watchlist):
        if not self.hyperliquid_ws_enabled or websocket is None:
            if websocket is None:
                logger.info("ℹ️ websocket-client is unavailable; live Hyperliquid monitoring is disabled.")
            return

        target_wallets, wallet_meta = self._select_live_wallets(watchlist)
        if target_wallets == self._ws_target_wallets and self._ws_thread and self._ws_thread.is_alive():
            self._ws_wallet_meta = wallet_meta
            return

        self._ws_wallet_meta = wallet_meta
        self._ws_target_wallets = target_wallets

        self._ws_stop.set()
        if self._ws_app is not None:
            try:
                self._ws_app.close()
            except Exception:
                pass

        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5)

        self._ws_stop = threading.Event()
        self._ws_thread = threading.Thread(target=self._run_websocket_monitor, daemon=True)
        self._ws_thread.start()

    def record_transactions(self, address, tx_list):
        """Saves new transactions to the Local Black Box."""
        ph = self.db.qmark
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            new_count = 0
            
            for tx in tx_list:
                tx_hash = tx.get("transactionHash")
                if not tx_hash:
                    tx_hash = tx.get("hash") or tx.get("txHash") or hashlib.sha1(
                        json.dumps(tx, sort_keys=True, default=str).encode("utf-8")
                    ).hexdigest()
                timestamp = tx.get("block_timestamp") or tx.get("timestamp")
                if not timestamp and isinstance(tx.get("time"), int):
                    timestamp = datetime.fromtimestamp(tx["time"] / 1000, tz=timezone.utc).isoformat()
                timestamp = timestamp or datetime.now(timezone.utc).isoformat()

                value_formatted = tx.get("value_formatted")
                if value_formatted is not None:
                    amount = float(value_formatted)
                else:
                    raw_value = tx.get("value")
                    try:
                        amount = float(raw_value) / 1e18 if raw_value not in (None, "") else 0.0
                    except Exception:
                        amount = 0.0

                asset = (
                    tx.get("asset")
                    or tx.get("coin")
                    or tx.get("token_symbol")
                    or tx.get("symbol")
                    or tx.get("summary")
                    or "ETH"
                )
                wallet_rank = tx.get("wallet_rank")
                leaderboard_snapshot_at = tx.get("leaderboard_snapshot_at")
                tx_type = (tx.get("tx_type") or tx.get("dir") or tx.get("category") or tx.get("summary") or "FILL").upper()
                counterparty = tx.get("to_address") or tx.get("from_address")
                source_provider = tx.get("source_provider") or self.source_provider
                raw_payload_json = tx.get("raw_payload_json") or json.dumps(tx, default=str)
                
                try:
                    cursor.execute(f'''
                        INSERT INTO scout_wallet_tx (
                            timestamp,
                            wallet_address,
                            tx_hash,
                            asset,
                            amount,
                            tx_type,
                            source_provider,
                            wallet_rank,
                            leaderboard_snapshot_at,
                            counterparty,
                            raw_payload_json
                        )
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                        ON CONFLICT(tx_hash) DO NOTHING
                    ''', (
                        timestamp,
                        address,
                        tx_hash,
                        asset,
                            amount,
                            tx_type,
                            source_provider,
                            wallet_rank,
                            leaderboard_snapshot_at,
                            counterparty,
                            raw_payload_json,
                        ))
                    if cursor.rowcount:
                        new_count += 1
                except Exception as exc:
                    logger.warning("⚠️ Failed to save tx %s for %s: %s", tx_hash, address, exc)
                    continue

            conn.commit()
            if new_count > 0:
                logger.info(f"✅ Recorded {new_count} new transactions for {address}.")

    def run_sync_cycle(self):
        """Refresh the Hyperscreener top-wallet set and sync tracked wallet transactions."""
        observed_at = datetime.now(timezone.utc).isoformat()
        try:
            leaderboard_rows = self.fetch_leaderboard()
        except Exception as exc:
            logger.error("❌ Failed to fetch Hyperscreener leaderboard: %s", exc)
            leaderboard_rows = []

        previous_state = self._get_previous_leaderboard_state() if leaderboard_rows else {}
        if leaderboard_rows:
            self._upsert_watchlist(leaderboard_rows, observed_at)
            self._record_leaderboard_audit(leaderboard_rows, observed_at, previous_state)

        watchlist = self.get_active_watchlist()
        if not watchlist:
            logger.info("⏳ Watchlist is empty. Waiting for Hyperscreener wallets to populate.")
            return

        self.ensure_websocket_monitor(watchlist)

        logger.info(
            "🛰️ Hyperscreener discovered %s wallets (%s new). Tracking %s active wallets; backfilling %s and live-monitoring %s.",
            len(leaderboard_rows),
            sum(1 for row in leaderboard_rows if row["wallet_address"] not in previous_state),
            len(watchlist),
            min(len(watchlist), self.hyperliquid_backfill_wallet_limit),
            min(len(watchlist), self.hyperliquid_ws_wallet_limit),
        )

        backfill_rows = self._select_backfill_wallets(watchlist)
        if backfill_rows:
            logger.info("🔁 Rotating %s wallets through backfill", len(backfill_rows))

        for row in backfill_rows:
            address = row["wallet_address"]
            alias = row["display_name"] or row["alias"] or address
            logger.info("🛰️ Syncing %s...", alias)
            txs = self.fetch_transactions(address)
            self._touch_wallet_watchlist(address)
            if txs:
                for tx in txs:
                    tx["wallet_rank"] = row["top_rank"]
                    tx["leaderboard_snapshot_at"] = observed_at
                self.record_transactions(address, txs)

    def start(self, interval=300):
        """Infinite loop to poll for watchlist activity every 5 minutes."""
        logger.info(f"🏎️ Wallet Scout is online. Polling Hyperscreener and Watchlist every {interval}s.")
        while True:
            self.run_sync_cycle()
            time.sleep(interval)

if __name__ == "__main__":
    from worker_smoke import run_worker_smoke_check

    run_worker_smoke_check(
        "wallet-scout",
        required_tables=(
            "wallet_watchlist",
            "scout_wallet_tx",
            "wallet_leaderboard_snapshots",
            "wallet_leaderboard_changes",
        ),
    )
    scout = WalletScout()
    scout.start()


# Backward compatibility for older imports and local scripts.
Mobula = WalletScout
