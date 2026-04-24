"""HyperTracker snapshot collector.

This worker is intentionally standalone. It reads a read-only HyperTracker
endpoint configured entirely by environment variables, normalizes compact
wallet/leaderboard snapshots into the existing Black Box tables, and emits
only meaningful wallet discovery changes to the analyst cache when enabled.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests

from blackbox_reader import BlackBoxReader
from local_blackbox import LocalBlackBox


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _is_enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_json_env(name: str, default: Any) -> Any:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return json.loads(raw)
    except Exception:
        logger.warning("Unable to parse %s as JSON; using default.", name)
        return default


def _coerce_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return default
    return text


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        numeric = float(value)
        if numeric != numeric:  # NaN
            return default
        return numeric
    except Exception:
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        return int(float(value))
    except Exception:
        return default


def _short_wallet(wallet_address: str, size: int = 10) -> str:
    return wallet_address[:size] if wallet_address else ""


class HyperTrackerScout:
    def __init__(self) -> None:
        self.db = LocalBlackBox()
        self.reader = BlackBoxReader()

        self.source_provider = _env("HYPERTRACKER_SOURCE_PROVIDER", "hypertracker")
        self.collection_kind = _env("HYPERTRACKER_COLLECTION_KIND", "leaderboard").strip().lower() or "leaderboard"
        self.base_url = _env("HYPERTRACKER_BASE_URL", "https://ht-api.coinmarketman.com").rstrip("/")
        self.endpoint = _env(
            "HYPERTRACKER_ENDPOINT",
            "/api/external/leaderboards/perp-pnl"
            if self.collection_kind == "leaderboard"
            else "/api/external/segments",
        ).strip()
        self.method = _env("HYPERTRACKER_METHOD", "GET").strip().upper() or "GET"
        self.timeout_seconds = _coerce_int(_env("HYPERTRACKER_TIMEOUT_SECONDS", "45"), 45)
        self.poll_interval_seconds = _coerce_int(_env("HYPERTRACKER_POLL_INTERVAL_SECONDS", "600"), 600)
        self.backoff_seconds = _coerce_int(_env("HYPERTRACKER_BACKOFF_SECONDS", "15"), 15)
        self.max_backoff_seconds = _coerce_int(_env("HYPERTRACKER_MAX_BACKOFF_SECONDS", "300"), 300)
        self.max_rows = _coerce_int(_env("HYPERTRACKER_MAX_ROWS", "500"), 500)
        self.emit_change_outputs = _is_enabled(_env("HYPERTRACKER_EMIT_CHANGE_OUTPUTS", "true"))
        self.request_delay_seconds = float(_env("HYPERTRACKER_REQUEST_DELAY_SECONDS", "0") or 0)

        self.api_key = _env("HYPERTRACKER_API_KEY", "").strip()
        self.extra_headers = _parse_json_env("HYPERTRACKER_HEADERS_JSON", {})
        self.query_json = _parse_json_env("HYPERTRACKER_QUERY_JSON", {})
        self.body_json = _parse_json_env("HYPERTRACKER_BODY_JSON", {})
        self.target_wallets = _parse_json_env("HYPERTRACKER_TARGET_WALLETS_JSON", [])
        self.default_category = _env("HYPERTRACKER_WALLET_CATEGORY", "hypertracker_top")

        self.source_url = self._build_url(self.endpoint)
        self.auth_required = "coinmarketman.com" in (self.source_url or "").lower()

    def _build_url(self, endpoint: str) -> str:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _request_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for key, value in (self.extra_headers or {}).items():
            if value is None:
                continue
            headers[str(key)] = str(value)
        return headers

    def _request_payload(self, wallet_address: Optional[str] = None) -> Dict[str, Any]:
        payload = dict(self.body_json or {})
        query = dict(self.query_json or {})

        if wallet_address:
            query.setdefault("wallet_address", wallet_address)
            query.setdefault("wallet", wallet_address)
            query.setdefault("user", wallet_address)
            payload.setdefault("wallet_address", wallet_address)
            payload.setdefault("wallet", wallet_address)
            payload.setdefault("user", wallet_address)
            payload.setdefault("address", wallet_address)

        return {"query": query, "body": payload}

    def _looks_like_wallet_row(self, row: Any) -> bool:
        if not isinstance(row, dict):
            return False
        keys = {
            "wallet_address",
            "walletAddress",
            "ethAddress",
            "address",
            "user",
            "wallet",
            "displayName",
            "display_name",
            "rank",
            "accountValue",
            "account_value",
        }
        return any(key in row for key in keys)

    def _extract_rows(self, payload: Any) -> List[Dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []

        if self._looks_like_wallet_row(payload):
            return [payload]

        candidate_keys = (
            "leaderboardRows",
            "leaderboard_rows",
            "wallets",
            "rows",
            "results",
            "items",
            "data",
            "segments",
            "entries",
            "positions",
            "snapshots",
        )
        for key in candidate_keys:
            value = payload.get(key)
            if isinstance(value, list) and value and any(isinstance(item, dict) for item in value):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested_rows = self._extract_rows(value)
                if nested_rows:
                    return nested_rows

        for value in payload.values():
            if isinstance(value, list) and value and any(isinstance(item, dict) for item in value):
                return [item for item in value if isinstance(item, dict)]

        return []

    def _find_value(self, row: Dict[str, Any], keys: Sequence[str], default: Any = None) -> Any:
        for key in keys:
            if key in row and row[key] not in (None, "", "null"):
                return row[key]
        return default

    def _normalize_row(self, row: Dict[str, Any], rank: int, observed_at: str) -> Optional[Dict[str, Any]]:
        wallet_address = _coerce_text(
            self._find_value(
                row,
                ("wallet_address", "walletAddress", "ethAddress", "address", "user", "wallet"),
                "",
            ),
            "",
        ).lower()
        if not wallet_address:
            return None

        display_name = _coerce_text(
            self._find_value(
                row,
                ("display_name", "displayName", "alias", "name", "label", "username"),
                "",
            ),
            _short_wallet(wallet_address),
        )
        account_value = _coerce_float(
            self._find_value(
                row,
                ("account_value", "accountValue", "equity", "balance", "value", "pnl", "profit", "netValue", "aum"),
                0.0,
            ),
            0.0,
        )
        row_rank = _coerce_int(
            self._find_value(row, ("rank", "position", "place", "current_rank", "currentRank", "leaderboardRank"), rank),
            rank,
        )

        normalized = {
            "wallet_address": wallet_address,
            "display_name": display_name,
            "rank": row_rank,
            "account_value": account_value,
            "observed_at": observed_at,
            "source_provider": self.source_provider,
            "source_url": self.source_url,
            "raw_payload": row,
        }
        return normalized

    def _previous_leaderboard_state(self) -> Dict[str, int]:
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
            rows = cursor.fetchall()
        return {str(row["wallet_address"]).lower(): _coerce_int(row["rank"], 0) for row in rows}

    def _upsert_watchlist(self, rows: List[Dict[str, Any]], observed_at: str) -> None:
        ph = self.db.qmark
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for row in rows:
                wallet_address = row["wallet_address"]
                display_name = row["display_name"]
                alias = display_name or _short_wallet(wallet_address)
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
                        self.default_category,
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

    def _record_snapshots(
        self,
        rows: List[Dict[str, Any]],
        observed_at: str,
        previous_state: Optional[Dict[str, int]] = None,
    ) -> None:
        ph = self.db.qmark
        previous_state = previous_state or {}
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for row in rows:
                snapshot_id = hashlib.sha1(
                    f"{self.source_provider}|{observed_at}|{row['wallet_address']}|{row['rank']}".encode("utf-8")
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
                        self.source_url,
                        row["wallet_address"],
                        row["display_name"],
                        row["rank"],
                        row["account_value"],
                        1 if row["wallet_address"] not in previous_state else 0,
                        json.dumps(row["raw_payload"], default=str),
                    ),
                )
            conn.commit()

    def _record_changes(self, rows: List[Dict[str, Any]], observed_at: str, previous_state: Dict[str, int]) -> List[Dict[str, Any]]:
        current_state = {row["wallet_address"]: row["rank"] for row in rows}
        changes: List[Dict[str, Any]] = []

        for row in rows:
            wallet_address = row["wallet_address"]
            previous_rank = previous_state.get(wallet_address)
            current_rank = row["rank"]
            if previous_rank is None:
                change_type = "NEW_WALLET"
            elif previous_rank != current_rank:
                change_type = "RANK_CHANGE"
            else:
                continue

            change_id = hashlib.sha1(
                f"{self.source_provider}|{observed_at}|{wallet_address}|{change_type}|{previous_rank}|{current_rank}".encode(
                    "utf-8"
                )
            ).hexdigest()
            raw_payload = {
                "wallet_address": wallet_address,
                "display_name": row["display_name"],
                "previous_rank": previous_rank,
                "current_rank": current_rank,
                "rank_delta": None if previous_rank is None else previous_rank - current_rank,
                "account_value": row["account_value"],
                "change_type": change_type,
                "source_provider": self.source_provider,
                "observed_at": observed_at,
            }
            changes.append(
                {
                    "change_id": change_id,
                    "wallet_address": wallet_address,
                    "display_name": row["display_name"],
                    "previous_rank": previous_rank,
                    "current_rank": current_rank,
                    "change_type": change_type,
                    "account_value": row["account_value"],
                    "observed_at": observed_at,
                    "raw_payload": raw_payload,
                }
            )

        removed_wallets = sorted(set(previous_state) - set(current_state))
        for wallet_address in removed_wallets:
            previous_rank = previous_state.get(wallet_address)
            change_type = "REMOVED_FROM_SNAPSHOT"
            change_id = hashlib.sha1(
                f"{self.source_provider}|{observed_at}|{wallet_address}|{change_type}|{previous_rank}".encode("utf-8")
            ).hexdigest()
            raw_payload = {
                "wallet_address": wallet_address,
                "previous_rank": previous_rank,
                "current_rank": None,
                "rank_delta": None,
                "change_type": change_type,
                "source_provider": self.source_provider,
                "observed_at": observed_at,
            }
            changes.append(
                {
                    "change_id": change_id,
                    "wallet_address": wallet_address,
                    "display_name": _short_wallet(wallet_address),
                    "previous_rank": previous_rank,
                    "current_rank": None,
                    "change_type": change_type,
                    "account_value": 0.0,
                    "observed_at": observed_at,
                    "raw_payload": raw_payload,
                }
            )

        if not changes:
            return []

        ph = self.db.qmark
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for change in changes:
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
                        change["change_id"],
                        observed_at,
                        self.source_provider,
                        change["wallet_address"],
                        change["display_name"],
                        change["previous_rank"],
                        change["current_rank"],
                        change["change_type"],
                        json.dumps(change["raw_payload"], default=str),
                    ),
                )
            conn.commit()

        return changes

    def _emit_change_outputs(self, changes: List[Dict[str, Any]], observed_at: str) -> int:
        if not self.emit_change_outputs:
            return 0

        emitted = 0
        for change in changes:
            if change["change_type"] not in {"NEW_WALLET", "RANK_CHANGE"}:
                continue

            wallet_address = change["wallet_address"]
            input_hash = change["change_id"]
            existing = self.reader.get_cached_output(
                wallet_address,
                "hypertracker_scout",
                "wallet_discovery",
                input_hash=input_hash,
            )
            if existing:
                continue

            alias = change["display_name"] or _short_wallet(wallet_address)
            summary_text = f"{alias} {change['change_type'].lower().replace('_', ' ')} at rank {change['current_rank']}"
            output = {
                "agent": "hypertracker_scout",
                "wallet_address": wallet_address,
                "display_name": alias,
                "source_provider": self.source_provider,
                "change_id": change["change_id"],
                "change_type": change["change_type"],
                "previous_rank": change["previous_rank"],
                "current_rank": change["current_rank"],
                "rank_delta": None
                if change["previous_rank"] is None or change["current_rank"] is None
                else int(change["previous_rank"]) - int(change["current_rank"]),
                "account_value": change["account_value"],
                "observed_at": observed_at,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.reader.cache_output(
                asset=wallet_address,
                agent_name="hypertracker_scout",
                opportunity_type="wallet_discovery",
                lifecycle_state=change["change_type"].lower(),
                confidence_score=100.0 if change["change_type"] == "NEW_WALLET" else 70.0,
                summary_text=summary_text,
                output=output,
                target_database="wallet_activity",
                input_hash=input_hash,
            )
            emitted += 1

        return emitted

    def _fetch_payload(self, wallet_address: Optional[str] = None) -> Any:
        url = self._build_url(self.endpoint)
        payload = self._request_payload(wallet_address=wallet_address)
        request_kwargs: Dict[str, Any] = {
            "headers": self._request_headers(),
            "timeout": self.timeout_seconds,
        }

        if self.method == "GET":
            request_kwargs["params"] = payload["query"]
        else:
            request_kwargs["json"] = payload["body"] or payload["query"] or {}

        response = requests.request(self.method, url, **request_kwargs)
        response.raise_for_status()
        return response.json()

    def _collect_rows(self) -> List[Dict[str, Any]]:
        if self.collection_kind == "wallet_snapshot" and self.target_wallets:
            rows: List[Dict[str, Any]] = []
            for wallet in self.target_wallets:
                wallet_address = _coerce_text(wallet, "").lower()
                if not wallet_address:
                    continue
                payload = self._fetch_payload(wallet_address=wallet_address)
                rows.extend(self._extract_rows(payload))
                if self.request_delay_seconds > 0:
                    time.sleep(self.request_delay_seconds)
            return rows

        payload = self._fetch_payload()
        return self._extract_rows(payload)

    def run_cycle(self) -> Dict[str, Any]:
        observed_at = datetime.now(timezone.utc).isoformat()
        raw_rows = self._collect_rows()
        normalized_rows: List[Dict[str, Any]] = []

        for index, row in enumerate(raw_rows, start=1):
            normalized = self._normalize_row(row, index, observed_at)
            if normalized:
                normalized_rows.append(normalized)
            if len(normalized_rows) >= self.max_rows:
                break

        if not normalized_rows:
            logger.info("ℹ️ HyperTracker returned no wallet rows.")
            return {
                "observed_at": observed_at,
                "rows": 0,
                "new_rows": 0,
                "changed_rows": 0,
                "removed_rows": 0,
            }

        previous_state = self._previous_leaderboard_state()
        self._upsert_watchlist(normalized_rows, observed_at)
        self._record_snapshots(normalized_rows, observed_at, previous_state)
        changes = self._record_changes(normalized_rows, observed_at, previous_state)
        emitted = self._emit_change_outputs(changes, observed_at)

        new_count = sum(1 for change in changes if change["change_type"] == "NEW_WALLET")
        changed_count = sum(1 for change in changes if change["change_type"] == "RANK_CHANGE")
        removed_count = sum(1 for change in changes if change["change_type"] == "REMOVED_FROM_SNAPSHOT")

        logger.info(
            "🛰️ HyperTracker snapshot captured %s rows (%s new, %s changed, %s removed). Emitted %s discovery outputs.",
            len(normalized_rows),
            new_count,
            changed_count,
            removed_count,
            emitted,
        )
        return {
            "observed_at": observed_at,
            "rows": len(normalized_rows),
            "new_rows": new_count,
            "changed_rows": changed_count,
            "removed_rows": removed_count,
            "emitted_rows": emitted,
        }

    def start(self) -> None:
        logger.info(
            "🏎️ HyperTracker Scout is online. kind=%s endpoint=%s interval=%ss",
            self.collection_kind,
            self.source_url,
            self.poll_interval_seconds,
        )

        backoff = self.backoff_seconds
        while True:
            try:
                if self.auth_required and not self.api_key:
                    logger.warning(
                        "⚠️ HyperTracker scout is configured for CoinMarketMan but HYPERTRACKER_API_KEY is missing. Waiting for configuration."
                    )
                    time.sleep(self.poll_interval_seconds)
                    continue
                self.run_cycle()
                backoff = self.backoff_seconds
                time.sleep(self.poll_interval_seconds)
            except requests.HTTPError as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                logger.warning("⚠️ HyperTracker HTTP error (%s): %s", status_code, exc)
                time.sleep(min(max(backoff, self.backoff_seconds), self.max_backoff_seconds))
                backoff = min(backoff * 2, self.max_backoff_seconds)
            except Exception as exc:
                logger.exception("❌ HyperTracker scout cycle failed: %s", exc)
                time.sleep(min(max(backoff, self.backoff_seconds), self.max_backoff_seconds))
                backoff = min(backoff * 2, self.max_backoff_seconds)


if __name__ == "__main__":
    from worker_smoke import run_worker_smoke_check

    run_worker_smoke_check(
        "hypertracker-scout",
        required_tables=(
            "wallet_watchlist",
            "wallet_leaderboard_snapshots",
            "wallet_leaderboard_changes",
            "analyst_output_cache",
        ),
        required_env=("HYPERTRACKER_API_KEY",),
    )
    HyperTrackerScout().start()
