from typing import Iterable


COMMON_QUOTES: Iterable[str] = (
    "USDT",
    "USDC",
    "BUSD",
    "FDUSD",
    "USD",
    "PERP",
)


def normalize_asset_symbol(symbol: str) -> str:
    value = (symbol or "").upper().strip()
    for separator in (":", "/", "-", "_"):
        if separator in value:
            value = value.split(separator, 1)[0]
    for quote in COMMON_QUOTES:
        if value.endswith(quote) and len(value) > len(quote):
            value = value[: -len(quote)]
            break
    return value.strip()
