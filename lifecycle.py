from typing import Optional


def normalize_scalp_state(state: Optional[str]) -> str:
    normalized = str(state or "").strip().lower()
    if normalized in {"triggered", "near_entry", "strengthening", "watch", "new"}:
        return normalized
    return "watch"


def initial_scalp_state(confidence: float, volume_state: str) -> str:
    volume = str(volume_state or "").strip().lower()
    if confidence >= 80:
        return "triggered"
    if confidence >= 65 and volume == "expanding":
        return "near_entry"
    if confidence >= 50:
        return "strengthening"
    if confidence >= 30:
        return "watch"
    return "new"


def normalize_long_term_state(state: Optional[str]) -> str:
    normalized = str(state or "").strip().lower()
    if normalized in {"promote", "breakout", "continuation", "watch", "remove"}:
        return normalized
    return "watch"


def initial_long_term_state(conviction: float, regime: str, volume_quality: str) -> str:
    regime_text = str(regime or "").strip().lower()
    volume = str(volume_quality or "").strip().lower()
    if conviction >= 80:
        return "promote"
    if conviction >= 70 and regime_text in {"trend_continuation", "accumulation"}:
        return "breakout"
    if conviction >= 55 and volume in {"healthy", "stable"}:
        return "continuation"
    if conviction <= 20:
        return "remove"
    return "watch"
