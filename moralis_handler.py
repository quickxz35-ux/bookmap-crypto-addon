import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("MORALIS_API_KEY", "")
BASE_URL = "https://deep-index.moralis.io/api/v2.2"
HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}


def _ensure_api_key() -> None:
    if not API_KEY:
        raise RuntimeError("MORALIS_API_KEY is not set")


def _request(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    _ensure_api_key()
    response = requests.get(
        f"{BASE_URL}{path}",
        headers=HEADERS,
        params=params or {},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def get_wallet_portfolio(address: str, chain: str = "eth") -> List[Dict[str, Any]]:
    """Return token balances with price context for an EVM wallet."""
    payload = _request(f"/wallets/{address}/tokens", params={"chain": chain})
    return payload.get("result", [])


def get_wallet_history(address: str, chain: str = "eth") -> List[Dict[str, Any]]:
    """Return decoded wallet history when a deeper review is needed."""
    payload = _request(f"/wallets/{address}/history", params={"chain": chain})
    return payload.get("result", [])


def get_wallet_net_worth(address: str, chain: str = "eth") -> Dict[str, Any]:
    """Return a simple wallet net-worth snapshot for ranking or profiling."""
    return _request(f"/wallets/{address}/net-worth", params={"chain": chain})
