import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from blackbox_reader import BlackBoxReader


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerExpectation:
    worker_name: str
    opportunity_types: tuple[str, ...]
    lookback_hours: int = 24


class WorkspaceWorkerAudit:
    def __init__(self) -> None:
        self.reader = BlackBoxReader()

    def _parse_time(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None

    def _normalize_output(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        result = frame.copy()
        if "generated_at" not in result.columns and "timestamp" in result.columns:
            result["generated_at"] = result["timestamp"]
        if "generated_at" not in result.columns:
            result["generated_at"] = None
        return result

    def _latest_for_types(self, opportunity_types: Iterable[str], limit: int = 200) -> pd.DataFrame:
        frame = self.reader.recent_analyst_outputs(limit=limit, opportunity_types=opportunity_types)
        if frame.empty:
            return frame
        frame = self._normalize_output(frame)
        frame["generated_at_dt"] = frame["generated_at"].apply(self._parse_time)
        return frame

    def _summarize_expectation(self, expectation: WorkerExpectation) -> Dict[str, Any]:
        frame = self._latest_for_types(expectation.opportunity_types, limit=500)
        if frame.empty:
            return {
                "worker": expectation.worker_name,
                "status": "missing",
                "latest_age_hours": None,
                "latest_asset": None,
                "latest_type": None,
                "delivery_status": None,
                "latest_confidence": None,
                "fallback_mode": None,
                "count": 0,
            }

        cutoff = datetime.now(timezone.utc) - timedelta(hours=expectation.lookback_hours)
        fresh = frame[frame["generated_at_dt"].notna() & (frame["generated_at_dt"] >= cutoff)]
        latest = frame.sort_values("generated_at_dt", ascending=False).iloc[0]
        latest_dt = latest.get("generated_at_dt")
        age_hours = None
        if isinstance(latest_dt, datetime):
            age_hours = round((datetime.now(timezone.utc) - latest_dt).total_seconds() / 3600.0, 2)

        delivered = fresh[
            fresh.get("delivery_status", pd.Series(dtype=str)).astype(str).str.startswith("notion_")
        ]
        return {
            "worker": expectation.worker_name,
            "status": "healthy" if not fresh.empty else "stale",
            "latest_age_hours": age_hours,
            "latest_asset": str(latest.get("asset") or ""),
            "latest_type": str(latest.get("opportunity_type") or ""),
            "delivery_status": str(latest.get("delivery_status") or ""),
            "latest_confidence": round(float(latest.get("confidence_score") or 0.0), 2),
            "fallback_mode": "fallback" in str(latest.get("summary_text") or "").lower(),
            "count": int(len(fresh)),
            "delivered_count": int(len(delivered)),
        }

    def run(self) -> Dict[str, Any]:
        expectations = [
            WorkerExpectation("wallet-scout", ("wallet_discovery", "wallet_update")),
            WorkerExpectation("wallet-analyst", ("wallet_ranking", "wallet_discovery", "wallet_update")),
            WorkerExpectation("analyst-scalping", ("scalp",)),
            WorkerExpectation("analyst-long-term", ("long_term",)),
            WorkerExpectation("sentiment-scout", ("sentiment",)),
            WorkerExpectation("derivatives-scout", ("derivatives",)),
            WorkerExpectation("validation-scout", ("whale_strike",)),
            WorkerExpectation("hypertracker-scout", ("wallet_discovery",)),
            WorkerExpectation("council-analyst", ("council_thesis", "trade_candidate")),
            WorkerExpectation("decision-router", ("council_thesis", "trade_candidate", "scalp", "long_term", "wallet_stats", "wallet_discovery", "wallet_update")),
        ]

        summaries = [self._summarize_expectation(item) for item in expectations]
        healthy = [item for item in summaries if item["status"] == "healthy"]
        stale = [item for item in summaries if item["status"] == "stale"]
        missing = [item for item in summaries if item["status"] == "missing"]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "healthy": healthy,
            "stale": stale,
            "missing": missing,
            "summaries": summaries,
        }

    def print_report(self) -> None:
        report = self.run()
        logger.info("Workspace worker audit generated at %s", report["generated_at"])
        for item in report["summaries"]:
            logger.info(
                "%s | %s | latest=%s | type=%s | conf=%s | fallback=%s | age=%s h | delivery=%s | fresh_rows=%s | delivered=%s",
                item["worker"],
                item["status"],
                item.get("latest_asset"),
                item.get("latest_type"),
                item.get("latest_confidence"),
                item.get("fallback_mode"),
                item.get("latest_age_hours"),
                item.get("delivery_status"),
                item.get("count"),
                item.get("delivered_count", 0),
            )
        logger.info(
            "Totals | healthy=%d | stale=%d | missing=%d",
            len(report["healthy"]),
            len(report["stale"]),
            len(report["missing"]),
        )
        print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    WorkspaceWorkerAudit().print_report()
