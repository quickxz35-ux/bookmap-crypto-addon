# Data Provider Map

Updated: 2026-04-03 (America/Chicago)

## Purpose

This file maps each data provider to the scout or analyst layer that should use it. Raw providers feed the `Local Black Box`. Analysts read from the Black Box and write structured intelligence into Notion and Slack.

## Storage Rule

- Raw data scouts write to the `Local Black Box`
- The `Local Black Box` can be mirrored to Railway/Postgres through `DATABASE_URL`
- Analysts read from the Black Box
- Analysts write structured outputs to Notion
- Alert logic writes high-signal outputs to Slack

## Providers

### Moralis

Use for:
- wallet holdings
- wallet portfolio context
- wallet history
- whale tracking support

Primary consumers:
- `Whale Scout`
- `Wallet Scout`

Auth:
- env var: `MORALIS_API_KEY`
- header: `X-API-Key`

Local handler:
- [moralis_handler.py](/Users/gssjr/OneDrive/Documents/New project/moralis_handler.py)

## CryptoAPIs

Use for:
- wallet transaction history
- address activity
- tracked wallet follow-up

Primary consumers:
- `Wallet Scout`
- future `Validation Scout` when wallet transaction confirmation is needed

Auth:
- env var: `CRYPTOAPIS_API_KEY`
- header: `X-API-Key`

Local handler:
- [cryptoapis_handler.py](/Users/gssjr/OneDrive/Documents/New project/cryptoapis_handler.py)

## Binance Futures API

Use for:
- open interest
- funding
- futures activity
- derivatives volume

Primary consumers:
- `Derivatives Scout`

Auth:
- current public endpoints in this repo do not require an API key

## CryptoPanic

Use for:
- headline feed
- narrative shift context
- sentiment support

Primary consumers:
- `Sentiment Scout`

Auth:
- env var: `CRYPTOPANIC_API_KEY`

## Glassnode MCP

Use for:
- on-chain and market context through MCP access
- curated raw exports used by the broader machine

Primary consumers:
- `Validation Scout`
- `Longer-Term Coin Analyst`
- future confluence layers

Auth:
- handled through MCP configuration, not a repo env var

## Notion

Use for:
- workspace intelligence
- scalp board
- asset library
- validation queue
- correlation board

Primary consumers:
- analyst layer only

Auth:
- env var: `NOTION_TOKEN`

## Slack

Use for:
- alerts
- setup changes
- watchlist promotions
- ops notices

Primary consumers:
- analyst and routing layers only

Auth:
- env var: `SLACK_TOKEN`

## Railway / Cloud Black Box

Use for:
- cloud copy of raw scout storage
- always-on persistence for deployed scouts

Auth:
- env var: `DATABASE_URL`

## Quick Mapping

- `Whale Scout` -> Moralis -> Local Black Box
- `Wallet Scout` -> CryptoAPIs + Moralis -> Local Black Box
- `Derivatives Scout` -> Binance -> Local Black Box
- `Sentiment Scout` -> CryptoPanic -> Local Black Box
- `Validation Scout` -> reads selected coins, then uses Black Box plus targeted provider refresh
- `Analyst layer` -> reads Black Box -> writes Notion
- `Router / alert layer` -> reads analyst outputs -> writes Slack
