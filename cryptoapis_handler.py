import os
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("CRYPTOAPIS_API_KEY", "")
HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}
BASE_URL = "https://rest.cryptoapis.io"


def _ensure_api_key() -> None:
    if not API_KEY:
        raise RuntimeError("CRYPTOAPIS_API_KEY is not set")


def get_address_transactions(
    address: str,
    blockchain: str = "ethereum",
    network: str = "mainnet",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return recent address transactions for the configured chain/network."""
    _ensure_api_key()
    url = f"{BASE_URL}/addresses-latest/evm/{blockchain}/{network}/{address}/transactions"
    response = requests.get(url, headers=HEADERS, params={"limit": limit}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    return payload.get("data", {}).get("items", [])
