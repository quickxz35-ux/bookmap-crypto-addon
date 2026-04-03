from typing import Dict, Iterable


SCALP_STATES = (
    "new",
    "watch",
    "near_entry",
    "triggered",
    "strengthening",
    "weakening",
    "invalid",
    "expired",
    "archived",
)

LONG_TERM_STATES = (
    "watch",
    "promote",
    "accumulation",
    "breakout",
    "continuation",
    "weakening",
    "remove",
)


SCALP_TRANSITIONS: Dict[str, Iterable[str]] = {
    "new": {"watch", "near_entry", "invalid", "archived"},
    "watch": {"near_entry", "weakening", "invalid", "expired", "archived"},
    "near_entry": {"triggered", "watch", "weakening", "invalid", "expired", "archived"},
    "triggered": {"strengthening", "weakening", "invalid", "expired", "archived"},
    "strengthening": {"weakening", "invalid", "expired", "archived"},
    "weakening": {"watch", "near_entry", "invalid", "expired", "archived"},
    "invalid": {"archived"},
    "expired": {"archived"},
    "archived": set(),
}

LONG_TERM_TRANSITIONS: Dict[str, Iterable[str]] = {
    "watch": {"promote", "accumulation", "remove"},
    "promote": {"accumulation", "breakout", "weakening", "remove"},
    "accumulation": {"promote", "breakout", "continuation", "weakening", "remove"},
    "breakout": {"continuation", "weakening", "remove"},
    "continuation": {"weakening", "remove"},
    "weakening": {"watch", "accumulation", "remove"},
    "remove": set(),
}

TERMINAL_SCALP_STATES = {"invalid", "expired", "archived"}
TERMINAL_LONG_TERM_STATES = {"remove"}


def _normalize_state(value: str, valid_states: Iterable[str], default_state: str) -> str:
    candidate = str(value or "").strip().lower().replace(" ", "_")
    if candidate in valid_states:
        return candidate
    return default_state


def normalize_scalp_state(value: str, default_state: str = "new") -> str:
    return _normalize_state(value, SCALP_STATES, default_state)


def normalize_long_term_state(value: str, default_state: str = "watch") -> str:
    return _normalize_state(value, LONG_TERM_STATES, default_state)


def transition_scalp_state(current: str, proposed: str) -> str:
    current_state = normalize_scalp_state(current)
    proposed_state = normalize_scalp_state(proposed, current_state)
    if current_state == proposed_state:
        return current_state
    if current_state in TERMINAL_SCALP_STATES:
        return current_state
    if proposed_state in {"invalid", "expired", "archived"}:
        return proposed_state
    allowed = set(SCALP_TRANSITIONS.get(current_state, set()))
    return proposed_state if proposed_state in allowed else current_state


def transition_long_term_state(current: str, proposed: str) -> str:
    current_state = normalize_long_term_state(current)
    proposed_state = normalize_long_term_state(proposed, current_state)
    if current_state == proposed_state:
        return current_state
    if current_state in TERMINAL_LONG_TERM_STATES:
        return current_state
    if proposed_state == "remove":
        return proposed_state
    allowed = set(LONG_TERM_TRANSITIONS.get(current_state, set()))
    return proposed_state if proposed_state in allowed else current_state


def initial_scalp_state(confidence: float, volume_state: str) -> str:
    normalized_volume = str(volume_state or "").strip().lower()
    if confidence >= 75 and normalized_volume in {"expanding", "surging"}:
        return "near_entry"
    if confidence >= 45:
        return "watch"
    return "new"


def initial_long_term_state(conviction: float, regime: str, volume_quality: str) -> str:
    normalized_regime = str(regime or "").strip().lower()
    normalized_volume = str(volume_quality or "").strip().lower()
    if conviction >= 80 and normalized_regime in {"trend_continuation", "breakout"}:
        return "breakout"
    if conviction >= 70 and normalized_volume in {"healthy", "expanding"}:
        return "promote"
    if conviction >= 55 and "accumulation" in normalized_regime:
        return "accumulation"
    return "watch"
