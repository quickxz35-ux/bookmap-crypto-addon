# Crypto Workspace Finalization

This document is the finish-line checklist for `crypto-workspace` before we move into small tweaks and polish.

## Current Live Shape

- `wallet-analyst` ranks tracked wallets using Hyperscreener discovery data and stored wallet activity.
- `wallet-scout` ingests wallet activity from the public Hyperliquid `info` endpoint.
- `wallet-scout` also maintains a live websocket monitor for `userNonFundingLedgerUpdates`.
- `wallet-analyst` scores the tracked wallets, records discovery events, and keeps wallet state current.
- `hypertracker-scout` is now a separate wallet intelligence worker for authenticated HyperTracker snapshots.
- `sentiment-scout` is now patched for Railway Postgres compatibility.
- Postgres bootstrapping is working on Railway.
- Moralis is no longer required for the wallet-scout transaction path.

## Current Service Snapshot

- `wallet-analyst`: healthy
- `wallet-scout`: healthy
- `validation-scout`: healthy
- `sentiment-scout`: healthy
- `derivatives-scout`: healthy
- `council-analyst`: healthy
- `decision-router`: healthy
- `Postgres`: healthy
- `hypertracker-scout`: healthy and capturing authenticated snapshot rows

## Finalization Checklist

### Data Flow

- [x] Use Hyperscreener as the wallet discovery source.
- [x] Keep `wallet-scout` tracking the top 500 to 1000 wallets.
- [x] Keep transaction deduping so only new fills are stored.
- [x] Replace Moralis wallet history calls with the public Hyperliquid fills API.
- [x] Add websocket support for broader wallet activity (`userNonFundingLedgerUpdates`).
- [x] Confirm the transaction source handles backfill and live polling without rate pressure.
- [x] Add a dedicated HyperTracker worker path for authenticated snapshot enrichment.

### Wallet State

- [x] Preserve leaderboard metadata on tracked wallets.
- [x] Record new wallets when the top set changes.
- [x] Update wallet-level stats in `wallet-analyst`.
- [x] Make sure new-wallet discoveries are clearly separated from transaction updates.
- [ ] Confirm the watchlist only stores active wallets we actually care about.

### Storage and Reliability

- [x] Keep the shared Black Box/Postgres schema booting cleanly.
- [x] Fix the Postgres `DATETIME` migration issue.
- [x] Use cursor-based DB writes on Railway Postgres.
- [x] Fix the `sentiment-scout` SQLite placeholder crash on Postgres.
- [x] Add a lightweight smoke check for each worker at startup.
- [ ] Remove any stale Moralis-only environment variables once we are fully sure they are no longer used.
- [x] Verify `hypertracker-scout` is writing real snapshot rows after API-key activation.

### Notion Reporting

- [x] Ensure `wallet-analyst` writes wallet updates to Notion in a consistent format.
- [x] Separate “new wallet discovered” records from “new transaction found” records.
- [x] Keep a clear wallet identity field so every record lands under the correct wallet.
- [x] Confirm the reported payload includes source metadata for Hyperscreener and Hyperliquid.

### Cleanup Before Tweaks

- [x] Normalize naming across logs, comments, and docs.
- [x] Remove the last legacy underscored wallet worker references from user-facing docs and notes.
- [x] Decide whether the websocket layer becomes the default live mode or a later enhancement.
- [ ] Freeze the core pipeline before adding cosmetic or behavioral tweaks.
- [x] Add a final “trade candidate” readiness layer on top of scout and council outputs.

## Recommended Order

1. Lock in Notion output formatting and council-to-decision routing.
2. Clean up naming and docs.
3. Freeze the core pipeline.
4. Then start feature tweaks.

## Success Criteria

- `wallet-analyst` and `wallet-scout` stay `SUCCESS` on Railway.
- Wallet discovery comes from Hyperscreener.
- Wallet activity comes from the public Hyperliquid fills path plus websocket-ledger updates, not Moralis.
- HyperTracker enriches the workspace without destabilizing the live scouts.
- New wallets and new transactions are separated cleanly.
- Notion receives stable, wallet-scoped updates.
- The council can rank trade candidates from scout + analyst inputs instead of just storing observations.
- All core worker services stay healthy after a restart because startup smoke checks run before the loops begin.

## Safe Follow-Ups

- Leave optional Moralis-based whale-flow support in `validation-scout` alone until we choose a replacement provider.
- Remove stale Moralis-only environment variables only after we confirm no remaining worker depends on them.
