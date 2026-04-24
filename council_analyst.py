import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from blackbox_reader import BlackBoxReader


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class CouncilAnalyst:
    COIN_OPPORTUNITIES = {"scalp", "long_term"}
    WALLET_OPPORTUNITIES = {"wallet_ranking", "wallet_discovery", "wallet_update", "wallet_stats"}
    FLOW_OPPORTUNITIES = {"whale_strike"}
    ALL_OPPORTUNITIES = COIN_OPPORTUNITIES | WALLET_OPPORTUNITIES | FLOW_OPPORTUNITIES

    def __init__(self) -> None:
        self.reader = BlackBoxReader()

    def _clean_text(self, value: Any, default: str = "") -> str:
        if value is None:
            return default
        try:
            if pd.isna(value):
                return default
        except Exception:
            pass
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none"}:
            return default
        return text

    def _coerce_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None or pd.isna(value):
                return default
            if isinstance(value, str) and not value.strip():
                return default
            numeric = float(value)
            if numeric != numeric:
                return default
            return numeric
        except Exception:
            return default

    def _parse_output_json(self, payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if not payload:
            return {}
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def _parse_timestamp(self, value: Any) -> Optional[datetime]:
        text = self._clean_text(value, "")
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None

    def _recent_rows(self, limit: int = 250, lookback_hours: int = 24) -> List[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        rows: List[Dict[str, Any]] = []
        seen_cache_ids: set[str] = set()
        families = (
            self.COIN_OPPORTUNITIES,
            self.WALLET_OPPORTUNITIES,
            self.FLOW_OPPORTUNITIES,
        )
        family_limit = max(10, limit // len(families))

        for opportunity_types in families:
            df = self.reader.recent_analyst_outputs(limit=family_limit, opportunity_types=opportunity_types)
            if df.empty:
                continue
            for _, row in df.iterrows():
                cache_id = self._clean_text(row.get("cache_id"), "")
                if cache_id and cache_id in seen_cache_ids:
                    continue
                generated_at = self._parse_timestamp(row.get("generated_at"))
                if generated_at and generated_at < cutoff:
                    continue

                output = self._parse_output_json(row.get("output_json"))
                output.setdefault("asset", self._clean_text(row.get("asset"), ""))
                output.setdefault("agent", self._clean_text(row.get("agent_name"), ""))
                output.setdefault("opportunity_type", self._clean_text(row.get("opportunity_type"), ""))
                output.setdefault("summary_text", self._clean_text(row.get("summary_text"), ""))
                output.setdefault("generated_at", self._clean_text(row.get("generated_at"), datetime.now(timezone.utc).isoformat()))
                output.setdefault("confidence_score", self._coerce_float(row.get("confidence_score"), 0.0))
                output.setdefault("lifecycle_state", self._clean_text(row.get("lifecycle_state"), ""))
                output.setdefault("target_database", self._clean_text(row.get("target_database"), ""))
                output.setdefault("cache_id", cache_id)
                rows.append(output)
                if cache_id:
                    seen_cache_ids.add(cache_id)

        rows.sort(key=lambda item: self._parse_timestamp(item.get("generated_at")) or datetime.now(timezone.utc), reverse=True)
        return rows

    def _summarize_coin_signal(self, payload: Dict[str, Any]) -> Tuple[float, str, Dict[str, Any]]:
        opportunity_type = self._clean_text(payload.get("opportunity_type"))
        confidence = self._coerce_float(payload.get("confidence_score"), 0.0)
        status = self._clean_text(payload.get("lifecycle_state"), "unknown")
        asset = self._clean_text(payload.get("asset"), "UNKNOWN")
        summary = self._clean_text(payload.get("summary_text"), "")

        if opportunity_type == "scalp":
            confidence = max(confidence, self._coerce_float(payload.get("confidence"), confidence))
            signal = {
                "asset": asset,
                "kind": "scalp",
                "status": status,
                "confidence": round(confidence, 2),
                "summary": summary,
            }
            return confidence, f"{asset} scalp {status}", signal

        if opportunity_type == "long_term":
            confidence = max(confidence, self._coerce_float(payload.get("conviction"), confidence))
            signal = {
                "asset": asset,
                "kind": "long_term",
                "status": status,
                "confidence": round(confidence, 2),
                "summary": summary,
            }
            return confidence, f"{asset} long-term {status}", signal

        return confidence, f"{asset} {opportunity_type or 'signal'}", {
            "asset": asset,
            "kind": opportunity_type or "unknown",
            "status": status,
            "confidence": round(confidence, 2),
            "summary": summary,
        }

    def _summarize_wallet_signal(self, payload: Dict[str, Any]) -> Tuple[float, str, Dict[str, Any]]:
        opportunity_type = self._clean_text(payload.get("opportunity_type"))
        confidence = self._coerce_float(payload.get("confidence_score"), 0.0)
        wallet_address = self._clean_text(payload.get("wallet_address"), "UNKNOWN")
        alias = self._clean_text(payload.get("display_name"), self._clean_text(payload.get("alias"), wallet_address[:10]))
        status = self._clean_text(payload.get("status"), self._clean_text(payload.get("lifecycle_state"), "unknown"))
        summary = self._clean_text(payload.get("summary_text"), "")

        if opportunity_type == "wallet_ranking":
            confidence = max(confidence, self._coerce_float(payload.get("wallet_score"), confidence))
        elif opportunity_type == "wallet_discovery":
            confidence = max(confidence, self._coerce_float(payload.get("confidence_score"), confidence))
        elif opportunity_type == "wallet_update":
            confidence = max(confidence, min(100.0, self._coerce_float(payload.get("amount_usd"), 0.0) / 10000.0))
        elif opportunity_type == "wallet_stats":
            confidence = max(confidence, self._coerce_float(payload.get("wallet_score"), confidence))

        signal = {
            "wallet_address": wallet_address,
            "alias": alias,
            "kind": opportunity_type or "wallet",
            "status": status,
            "confidence": round(confidence, 2),
            "summary": summary,
        }
        return confidence, f"{alias} {opportunity_type or 'wallet'} {status}", signal

    def _summarize_whale_signal(self, payload: Dict[str, Any]) -> Tuple[float, str, Dict[str, Any]]:
        asset = self._clean_text(payload.get("asset"), "UNKNOWN")
        confidence = max(
            self._coerce_float(payload.get("confidence_score"), 0.0),
            min(100.0, self._coerce_float(payload.get("usd_value"), 0.0) / 10000.0),
        )
        signal = {
            "asset": asset,
            "kind": "whale_strike",
            "confidence": round(confidence, 2),
            "summary": self._clean_text(payload.get("summary_text"), ""),
        }
        return confidence, f"{asset} whale flow", signal

    def _collect_signal_context(
        self,
        rows: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[str], List[str]]:
        coin_signals: List[Dict[str, Any]] = []
        wallet_signals: List[Dict[str, Any]] = []
        whale_signals: List[Dict[str, Any]] = []
        supporting_signals: List[str] = []
        conflicting_signals: List[str] = []

        for payload in rows:
            opportunity_type = self._clean_text(payload.get("opportunity_type"))
            if opportunity_type in self.COIN_OPPORTUNITIES:
                _, label, signal = self._summarize_coin_signal(payload)
                signal["label"] = label
                signal["generated_at"] = payload.get("generated_at")
                coin_signals.append(signal)
                supporting_signals.append(label)
            elif opportunity_type in self.WALLET_OPPORTUNITIES:
                _, label, signal = self._summarize_wallet_signal(payload)
                signal["label"] = label
                signal["generated_at"] = payload.get("generated_at")
                wallet_signals.append(signal)
                supporting_signals.append(label)
            elif opportunity_type in self.FLOW_OPPORTUNITIES:
                _, label, signal = self._summarize_whale_signal(payload)
                signal["label"] = label
                signal["generated_at"] = payload.get("generated_at")
                whale_signals.append(signal)
                supporting_signals.append(label)
            else:
                conflicting_signals.append(
                    self._clean_text(payload.get("summary_text"), self._clean_text(opportunity_type, "unknown signal"))
                )

        coin_signals.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
        wallet_signals.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
        whale_signals.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
        return coin_signals, wallet_signals, whale_signals, supporting_signals, conflicting_signals

    def build_council_thesis(
        self,
        limit: int = 250,
        lookback_hours: int = 24,
        rows: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        rows = rows if rows is not None else self._recent_rows(limit=limit, lookback_hours=lookback_hours)
        if not rows:
            return {
                "agent": "crypto_council",
                "asset": "COUNCIL",
                "best_action": "wait",
                "confidence": 0.0,
                "supporting_signals": [],
                "conflicting_signals": [],
                "top_coins": [],
                "top_wallets": [],
                "risk_notes": ["No recent analyst outputs were found."],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_window_hours": lookback_hours,
            }

        coin_signals, wallet_signals, whale_signals, supporting_signals, conflicting_signals = self._collect_signal_context(rows)

        top_coin_score = coin_signals[0]["confidence"] if coin_signals else 0.0
        top_wallet_score = wallet_signals[0]["confidence"] if wallet_signals else 0.0
        top_whale_score = whale_signals[0]["confidence"] if whale_signals else 0.0

        if top_coin_score >= 75 and top_coin_score >= top_wallet_score - 5:
            best_action = "enter_setup"
        elif top_wallet_score >= 70 and top_wallet_score > top_coin_score:
            best_action = "follow_wallets"
        elif top_coin_score >= 55:
            best_action = "watch_setup"
        elif top_whale_score >= 60:
            best_action = "watch_flow"
        else:
            best_action = "wait"

        confidence = round(min(100.0, (top_coin_score * 0.55) + (top_wallet_score * 0.35) + (top_whale_score * 0.10)), 2)
        if best_action == "wait":
            confidence = min(confidence, 35.0)

        top_coins = [
            {
                "asset": signal.get("asset"),
                "kind": signal.get("kind"),
                "status": signal.get("status"),
                "confidence": signal.get("confidence"),
                "summary": signal.get("summary"),
            }
            for signal in coin_signals[:5]
        ]
        top_wallets = [
            {
                "wallet_address": signal.get("wallet_address"),
                "alias": signal.get("alias"),
                "kind": signal.get("kind"),
                "status": signal.get("status"),
                "confidence": signal.get("confidence"),
                "summary": signal.get("summary"),
            }
            for signal in wallet_signals[:5]
        ]

        risk_notes: List[str] = []
        if not coin_signals:
            risk_notes.append("No coin setups were available in the recent window.")
        if not wallet_signals:
            risk_notes.append("No wallet signals were available in the recent window.")
        if not whale_signals:
            risk_notes.append("No whale-flow confirmation was available in the recent window.")
        if top_coin_score and top_wallet_score and abs(top_coin_score - top_wallet_score) > 25:
            risk_notes.append("Coin and wallet signals are uneven; avoid over-committing.")

        if not risk_notes:
            risk_notes.append("Council view is internally consistent across available signals.")

        dominant_coin = top_coins[0]["asset"] if top_coins else "COUNCIL"
        summary = (
            f"Council recommends {best_action.replace('_', ' ')} on {dominant_coin}. "
            f"Top coin score {top_coin_score:.1f}, wallet score {top_wallet_score:.1f}, whale score {top_whale_score:.1f}."
        )

        payload = {
            "agent": "crypto_council",
            "asset": "COUNCIL",
            "best_action": best_action,
            "confidence": confidence,
            "supporting_signals": supporting_signals[:10],
            "conflicting_signals": conflicting_signals[:10],
            "top_coins": top_coins,
            "top_wallets": top_wallets,
            "risk_notes": risk_notes,
            "summary": summary,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_window_hours": lookback_hours,
        }
        return payload

    def _recent_derivatives_context(self, asset: str) -> Tuple[float, str]:
        df = self.reader.latest_derivatives(asset, limit=3)
        if df.empty:
            return 0.0, "No derivatives context."

        row = df.iloc[0]
        volume_change = abs(self._coerce_float(row.get("volume_change_pct"), 0.0))
        oi_change = abs(self._coerce_float(row.get("open_interest_change_pct"), 0.0))
        liquidations = abs(self._coerce_float(row.get("liquidations_24h"), 0.0))
        score = min(100.0, (volume_change * 1.2) + (oi_change * 1.1) + min(25.0, liquidations / 100000.0))
        note = (
            f"Derivatives context: volume change {self._coerce_float(row.get('volume_change_pct'), 0.0):.1f}%, "
            f"OI change {self._coerce_float(row.get('open_interest_change_pct'), 0.0):.1f}%."
        )
        return round(score, 2), note

    def _recent_sentiment_context(self, asset: str) -> Tuple[float, str]:
        df = self.reader.recent_sentiment(asset, limit=8)
        if df.empty:
            return 0.0, "No sentiment context."

        scores = [self._coerce_float(value, 0.0) for value in df.get("raw_sentiment_score", [])]
        if not scores:
            return 0.0, "No sentiment context."

        avg_score = sum(scores) / len(scores)
        if -1.0 <= avg_score <= 1.0:
            normalized = max(0.0, min(100.0, (avg_score + 1.0) * 50.0))
        else:
            normalized = max(0.0, min(100.0, avg_score))
        note = f"Sentiment context: average raw score {avg_score:.2f} across {len(scores)} stories."
        return round(normalized, 2), note

    def build_trade_candidates(
        self,
        rows: List[Dict[str, Any]],
        *,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        coin_signals, _, whale_signals, _, _ = self._collect_signal_context(rows)
        if not coin_signals and not whale_signals:
            return []

        by_asset: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: {"coin": [], "whale": []})
        for signal in coin_signals:
            asset = self._clean_text(signal.get("asset"), "")
            if asset and asset != "COUNCIL":
                by_asset[asset]["coin"].append(signal)
        for signal in whale_signals:
            asset = self._clean_text(signal.get("asset"), "")
            if asset and asset != "COUNCIL":
                by_asset[asset]["whale"].append(signal)

        candidates: List[Dict[str, Any]] = []
        generated_at = datetime.now(timezone.utc).isoformat()
        for asset, groups in by_asset.items():
            top_coin = groups["coin"][0] if groups["coin"] else {}
            top_whale = groups["whale"][0] if groups["whale"] else {}
            coin_score = self._coerce_float(top_coin.get("confidence"), 0.0)
            whale_score = self._coerce_float(top_whale.get("confidence"), 0.0)
            derivatives_score, derivatives_note = self._recent_derivatives_context(asset)
            sentiment_score, sentiment_note = self._recent_sentiment_context(asset)

            trade_score = round(
                min(
                    100.0,
                    (coin_score * 0.5)
                    + (whale_score * 0.2)
                    + (derivatives_score * 0.2)
                    + (sentiment_score * 0.1),
                ),
                2,
            )
            if trade_score >= 75:
                recommended_action = "ready"
            elif trade_score >= 60:
                recommended_action = "watch"
            else:
                recommended_action = "hold"

            supporting_reasons = [
                reason
                for reason in (
                    top_coin.get("summary"),
                    top_whale.get("summary"),
                    derivatives_note,
                    sentiment_note,
                )
                if self._clean_text(reason, "")
            ]
            risk_notes: List[str] = []
            if not groups["coin"]:
                risk_notes.append("No coin setup is backing this candidate yet.")
            if not groups["whale"]:
                risk_notes.append("No whale-flow confirmation is backing this candidate yet.")
            if derivatives_score < 20:
                risk_notes.append("Derivatives participation is still light.")
            if sentiment_score < 35:
                risk_notes.append("News and social sentiment are not confirming strongly.")

            candidate = {
                "agent": "crypto_council",
                "asset": asset,
                "recommended_action": recommended_action,
                "trade_score": trade_score,
                "coin_score": round(coin_score, 2),
                "whale_score": round(whale_score, 2),
                "derivatives_score": derivatives_score,
                "sentiment_score": sentiment_score,
                "supporting_reasons": supporting_reasons[:6],
                "risk_notes": risk_notes[:4] or ["Signals are aligned enough to keep tracking this candidate."],
                "top_coin_signal": top_coin,
                "top_whale_signal": top_whale,
                "generated_at": generated_at,
                "summary": (
                    f"{asset} trade score {trade_score:.1f}. "
                    f"Coin {coin_score:.1f}, whale {whale_score:.1f}, derivatives {derivatives_score:.1f}, sentiment {sentiment_score:.1f}."
                ),
            }
            candidates.append(candidate)

        candidates.sort(key=lambda item: item.get("trade_score", 0.0), reverse=True)
        return candidates[:limit]

    def _cache_trade_candidates(self, candidates: List[Dict[str, Any]]) -> List[str]:
        cache_ids: List[str] = []
        for candidate in candidates:
            input_hash = hashlib.sha1(json.dumps(candidate, sort_keys=True, default=str).encode("utf-8")).hexdigest()
            cache_id = self.reader.cache_output(
                asset=str(candidate.get("asset") or ""),
                agent_name="crypto_council",
                opportunity_type="trade_candidate",
                lifecycle_state=str(candidate.get("recommended_action") or "hold"),
                confidence_score=float(candidate.get("trade_score", 0.0) or 0.0),
                summary_text=str(candidate.get("summary") or ""),
                output=candidate,
                target_database="decision_queue",
                input_hash=input_hash,
                delivery_status="pending",
            )
            cache_ids.append(cache_id)
        return cache_ids

    def run(self, limit: int = 250, lookback_hours: int = 24) -> Dict[str, Any]:
        rows = self._recent_rows(limit=limit, lookback_hours=lookback_hours)
        thesis = self.build_council_thesis(limit=limit, lookback_hours=lookback_hours, rows=rows)
        trade_candidates = self.build_trade_candidates(rows)
        cache_id = self.reader.cache_output(
            asset="COUNCIL",
            agent_name="crypto_council",
            opportunity_type="council_thesis",
            lifecycle_state=thesis.get("best_action", "wait"),
            confidence_score=float(thesis.get("confidence", 0.0) or 0.0),
            summary_text=thesis.get("summary", ""),
            output=thesis,
            target_database="decision_queue",
            input_hash=hashlib.sha1(json.dumps(thesis, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
            delivery_status="pending",
        )
        candidate_cache_ids = self._cache_trade_candidates(trade_candidates)
        thesis["cache_id"] = cache_id
        thesis["top_trade_candidates"] = trade_candidates
        thesis["trade_candidate_cache_ids"] = candidate_cache_ids
        return thesis

    def start(self, interval: int = 900) -> None:
        logger.info("Crypto Council is online. Audit cycle: %ss", interval)
        while True:
            try:
                thesis = self.run()
                logger.info(
                    "Council verdict: %s | confidence=%.1f | top coin=%s",
                    thesis.get("best_action"),
                    float(thesis.get("confidence", 0.0) or 0.0),
                    thesis.get("top_coins", [{}])[0].get("asset") if thesis.get("top_coins") else "n/a",
                )
            except Exception:
                logger.exception("Crypto Council audit cycle failed; retrying after backoff.")
                time.sleep(min(60, interval))
                continue
            time.sleep(interval)


if __name__ == "__main__":
    from worker_smoke import run_worker_smoke_check

    run_worker_smoke_check(
        "council-analyst",
        required_tables=("analyst_output_cache", "selected_asset_queue"),
    )
    CouncilAnalyst().start()
