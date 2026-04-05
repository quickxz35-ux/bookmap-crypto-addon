from datetime import datetime, timezone
from typing import Any, Dict, List

from blackbox_reader import BlackBoxReader


class CorrelationAnalyst:
    def __init__(self):
        self.reader = BlackBoxReader()

    def correlate(self, primary_view: Dict[str, Any], validation_view: Dict[str, Any]) -> Dict[str, Any]:
        supporting: List[str] = list(validation_view.get("supportive_factors", []))
        conflicting: List[str] = list(validation_view.get("conflicting_factors", []))

        for pillar, state in validation_view.get("support", {}).items():
            if state in {"supportive", "active"} and pillar not in supporting:
                supporting.append(pillar)
            elif state in {"invalidating", "missing", "conflicting"} and pillar not in conflicting:
                conflicting.append(pillar)

        score = int(primary_view.get("confidence", primary_view.get("conviction", 0)))
        score += len(supporting) * 5
        score -= len(conflicting) * 7
        score = max(0, min(100, score))

        if score >= 80 and len(conflicting) == 0:
            status = "confirmed"
        elif score >= 55:
            status = "mixed"
        elif score >= 35:
            status = "weak"
        else:
            status = "rejected"

        output = {
            "agent": "correlation_analyst",
            "asset": primary_view["asset"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "opportunity_type": primary_view.get("agent", "unknown"),
            "confluence_status": status,
            "confidence": score,
            "supporting_factors": supporting,
            "conflicting_factors": conflicting,
            "summary": f"Confluence is {status} with {len(supporting)} supporting and {len(conflicting)} conflicting factors.",
        }
        self.reader.cache_output(
            asset=primary_view["asset"],
            agent_name="correlation_analyst",
            opportunity_type=output["opportunity_type"],
            lifecycle_state=status,
            confidence_score=score,
            summary_text=output["summary"],
            output=output,
            target_database="correlation_board",
        )
        return output
