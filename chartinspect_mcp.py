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

@mcp.tool()
def get_chartinspect_onchain_status(chain: str) -> dict:
    """Get the current on-chain status and latest block info for a blockchain.
    
    Args:
        chain: The blockchain (e.g., 'bitcoin', 'ethereum').
    """
    url = f"{BASE_URL}/onchain/status"
    params = {"chain": chain}
    
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def fetch_chartinspect_economic(indicator: str, days: int = 30) -> dict:
    """Fetch macroeconomic data from ChartInspect (e.g., interest rates, CPI).
    
    Args:
        indicator: The economic indicator (e.g., 'cpi', 'interest-rates').
        days: Number of days of historical data to fetch (default 30).
    """
    url = f"{BASE_URL}/economic/{indicator}"
    params = {"days": days}
    
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def fetch_chartinspect_market_indicator(indicator: str, days: int = 30) -> dict:
    """Fetch market-wide indicators from ChartInspect (e.g., altcoin season index).
    
    Args:
        indicator: The market indicator.
        days: Number of days of historical data to fetch (default 30).
    """
    url = f"{BASE_URL}/market-indicators/{indicator}"
    params = {"days": days}
    
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def fetch_chartinspect_exchange_etf(dataset: str, days: int = 30) -> dict:
    """Fetch exchange reserves or ETF holdings data.
    
    Args:
        dataset: The dataset name (e.g., 'reserves', 'etf-holdings').
        days: Number of days of historical data to fetch (default 30).
    """
    url = f"{BASE_URL}/exchange-etf/{dataset}"
    params = {"days": days}
    
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json()

@mcp.tool()
def fetch_chartinspect_derivatives(metric: str, chain: str = "bitcoin", days: int = 30) -> dict:
    """Fetch futures open interest, funding rates, or other derivatives data.
    
    Args:
        metric: The derivatives metric (e.g., 'open-interest', 'funding-rate').
        chain: The blockchain context (default 'bitcoin').
        days: Number of days of historical data to fetch (default 30).
    """
    url = f"{BASE_URL}/derivatives/{metric}"
    params = {"chain": chain, "days": days}
    
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json()
if __name__ == "__main__":
    # Run the server using stdio transport for MCP
    mcp.run()
