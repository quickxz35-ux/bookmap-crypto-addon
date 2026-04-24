import os
import httpx
from fastmcp import FastMCP
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# HyperTracker API Configuration
API_KEY = os.getenv("HYPERTRACKER_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOjUxODcsIm1pZCI6MTIwNDgxLCJpYXQiOjE3NzI4MzA1NDB9.Rb3fC9bb_hUQUiqyp0dHRZk-vVFrNZsi3jJstel0kYA")
BASE_URL = "https://ht-api.coinmarketman.com"

# Initialize FastMCP
mcp = FastMCP("HyperTracker")

def get_headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json"
    }

@mcp.tool()
async def get_perp_pnl_leaderboard(period: str = "daily") -> Dict[str, Any]:
    """
    Fetches the Perp PnL leaderboard for a specific period.
    
    Args:
        period: The time period (daily, weekly, monthly, yearly, all). Defaults to daily.
    """
    url = f"{BASE_URL}/api/external/leaderboards/perp-pnl"
    params = {"period": period}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_headers(), params=params)
        response.raise_for_status()
        return response.json()

@mcp.tool()
async def get_all_pnl_leaderboard() -> Dict[str, Any]:
    """
    Fetches the overall PnL leaderboard.
    """
    url = f"{BASE_URL}/api/external/leaderboards/all-pnl"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_headers())
        response.raise_for_status()
        return response.json()

@mcp.tool()
async def get_hype_holders() -> Dict[str, Any]:
    """
    Fetches HYPE token holder statistics.
    """
    url = f"{BASE_URL}/api/external/hype/holders"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_headers())
        response.raise_for_status()
        return response.json()

@mcp.tool()
async def get_wallets(
    limit: int = 50,
    orderBy: str = "perpPnl",
    order: str = "desc",
    hasOpenPositions: Optional[bool] = None,
    address: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieves a paginated list of all wallets with flexible filtering and sorting options.
    
    Args:
        limit: The maximum number of items to return (max 500).
        orderBy: Field to order results by (address, totalEquity, perpPnl, perpEquity, perpBias, openValue, etc.).
        order: Order direction (asc or desc).
        hasOpenPositions: Filter wallets that currently have open positions.
        address: Filter by one or more wallet addresses.
    """
    url = f"{BASE_URL}/api/external/wallets"
    params = {
        "limit": limit,
        "orderBy": orderBy,
        "order": order
    }
    if hasOpenPositions is not None:
        params["hasOpenPositions"] = str(hasOpenPositions).lower()
    if address:
        params["address"] = address
        
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_headers(), params=params)
        response.raise_for_status()
        return response.json()

@mcp.tool()
async def get_fills(
    wallet: Optional[str] = None,
    coin: Optional[str] = None,
    limit: int = 50,
    start: Optional[str] = None,
    end: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns trade fills (executions) within a selected time window for requested filters.
    
    Args:
        wallet: Filter by one or more wallet addresses.
        coin: Filter by one or more coin symbols (e.g. ETH, BTC).
        limit: Maximum number of rows to return.
        start: Start of the time window (ISO8601).
        end: End of the time window (ISO8601).
    """
    url = f"{BASE_URL}/api/external/fills"
    params = {"limit": limit}
    if wallet:
        params["address"] = wallet
    if coin:
        params["coin"] = coin
    if start:
        params["start"] = start
    if end:
        params["end"] = end
        
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_headers(), params=params)
        response.raise_for_status()
        return response.json()

if __name__ == "__main__":
    mcp.run()
