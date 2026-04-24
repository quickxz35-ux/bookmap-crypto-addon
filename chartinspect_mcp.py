import os
import requests
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("ChartInspect")

BASE_URL = "https://chartinspect.com/api/v1"

def get_headers():
    api_key = os.environ.get("CHARTINSPECT_API_KEY")
    if not api_key:
        raise ValueError("CHARTINSPECT_API_KEY environment variable is not set. Please set it to use the ChartInspect API.")
    return {"x-api-key": api_key}

@mcp.tool()
def get_chartinspect_chains() -> list[str]:
    """Get a list of blockchains supported by ChartInspect."""
    try:
        response = requests.get(f"{BASE_URL}/chains", headers=get_headers())
        response.raise_for_status()
        data = response.json()
        if data.get("success"):
            return data.get("data", [])
    except Exception:
        pass
    
    # Fallback to known supported chains if the API call fails or isn't available
    return ["bitcoin", "ethereum", "cardano", "dogecoin", "litecoin", "chainlink"]

@mcp.tool()
def fetch_chartinspect_metric(metric: str, chain: str, days: int = 30) -> dict:
    """Fetch on-chain metric data for a specific blockchain from ChartInspect.
    
    Args:
        metric: The on-chain metric (e.g., 'mvrv', 'nupl', 'sopr', 'exchange-inflow').
        chain: The blockchain (e.g., 'bitcoin', 'ethereum', 'dogecoin').
        days: Number of days of historical data to fetch (default 30).
    """
    url = f"{BASE_URL}/onchain/{metric}"
    params = {
        "chain": chain,
        "days": days
    }
    
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def fetch_chartinspect_crypto_price(symbol: str) -> dict:
    """Fetch the latest crypto price from ChartInspect.
    
    Args:
        symbol: The symbol of the crypto (e.g., 'btc', 'eth', 'doge').
    """
    url = f"{BASE_URL}/crypto/prices/{symbol}"
    
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    # Run the server using stdio transport for MCP
    mcp.run()
