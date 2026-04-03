# Crypto Workspace Blueprint

Updated: 2026-04-03 (America/Chicago)

## Purpose

This document defines the operating structure for the crypto workspace built around Notion, Slack, scouts, analysts, trackers, and a correlation layer. The goal is to separate broad market discovery from focused coin investigation, then route only the highest-signal outputs into active decision boards and alerts.

## Core Operating Model

The workspace has three layers:

1. Scouts collect raw evidence.
2. Analysts and trackers turn evidence into living coin and setup intelligence.
3. Correlation and routing decide what gets promoted, updated, alerted, or ignored.

The system should support two distinct opportunity types:

- fast `scalp` opportunities
- stronger `longer-term` coin opportunities

The system should also maintain a parallel smart-money layer:

- wallet discovery
- wallet scoring
- coin-specific wallet participation

## Team Structure

### Broad Scouts

These run across the market and feed raw evidence into the workspace.

#### Whale Scout

Purpose:
- detect exchange inflows and outflows
- detect large transfers
- detect whale accumulation or distribution
- flag coin-specific large-money movement

Core outputs:
- flow direction
- transfer size
- source and destination context
- coin relevance

#### Wallet Scout

Purpose:
- track known and high-priority wallets
- detect wallet buys, sells, rotations, exits, and unusual participation
- log wallet interaction with specific coins

Core outputs:
- wallet action
- wallet-coin association
- size and timing of activity
- repeat participation flags

#### Derivatives Scout

Purpose:
- track leveraged market behavior
- track large volume and relative volume shifts
- monitor open interest, funding, liquidations, and long/short pressure

Core outputs:
- OI regime
- funding regime
- liquidation pressure
- volume expansion or contraction
- derivatives support or warning state

#### Sentiment Scout

Purpose:
- track news, headline flow, and sentiment changes
- detect positive or negative narrative pressure around coins

Core outputs:
- headline count
- sentiment bias
- narrative change notes

### Focused Follow-Up Scout

This does not scan the whole market. It only investigates coins already selected by the analysts.

#### Validation Scout

Purpose:
- pull fresh support data for coins on the `Scalp Board` and `Asset Library`
- deepen evidence for selected coins only
- confirm or weaken active trade and watchlist ideas

Reads:
- selected scalp coins
- selected longer-term coins
- latest whale, wallet, derivatives, sentiment, and volume context

Core outputs:
- validation status: `supportive`, `mixed`, `weak`, `invalidating`
- updated whale support
- updated wallet support
- updated derivatives support
- updated volume support
- updated sentiment support
- short reason summary

### Analysts and Trackers

#### Scalping Analyst

Purpose:
- find short-term scalp setups
- define entry, stop, targets, invalidation, and urgency

Reads:
- short-term price action
- short-term volume and relative volume
- derivatives state
- liquidation signals
- order-flow or Bookmap context when available
- immediate sentiment reaction

Core outputs:
- setup type
- direction
- timeframe
- entry zone
- stop
- targets
- confidence
- invalidation
- thesis summary

Main question:
- Is there a short-term trade here right now?

#### Scalp Tracker

Purpose:
- maintain scalp setups after they are found
- keep active scalp ideas current until they trigger, expire, fail, or complete

Reads:
- active scalp setups
- updated price action
- updated volume
- updated validation results
- wallet and whale participation tied to the coin

Core outputs:
- status update: `watch`, `near entry`, `triggered`, `strengthening`, `weakening`, `target hit`, `invalid`, `expired`
- what changed since last review
- refreshed confidence

Main question:
- Is this scalp still valid and worth attention?

#### Longer-Term Coin Analyst

Purpose:
- maintain the serious watchlist
- identify accumulation, breakout, continuation, weakening, or removal candidates

Reads:
- higher-timeframe trend structure
- sustained volume and breakout volume
- relative strength
- on-chain and derivatives context
- wallet and whale support
- narrative quality

Core outputs:
- coin bias
- regime classification
- conviction score
- key levels
- risk flags
- review date

Main question:
- Is this coin worth staying on the serious watchlist?

#### Wallet Analyst

Purpose:
- score wallets, not just their raw activity
- identify which wallets deserve attention

Reads:
- wallet transaction history
- wallet timing quality
- repeat profitability patterns
- coin concentration and overlap

Core outputs:
- wallet score
- wallet status: `elite`, `watch`, `ignore`
- wallet notes
- coin clusters supported by strong wallets

Main question:
- Which wallets actually matter?

### Correlation and Decision Layer

#### Correlation Analyst

Purpose:
- combine scout, analyst, tracker, and validation evidence into a confluence read

Reads:
- scalp setups
- scalp updates
- longer-term coin updates
- wallet analyst output
- whale, wallet, derivatives, volume, and sentiment evidence

Core outputs:
- confluence status: `confirmed`, `mixed`, `weak`, `rejected`
- confidence upgrade or downgrade
- alignment summary
- top supporting factors
- top conflicting factors

Main question:
- Does the evidence across the system actually line up?

#### Decision Router

Purpose:
- decide what gets posted to Notion
- decide what gets posted to Slack
- decide what stays internal

Core outputs:
- alert dispatch
- board updates
- review queue updates
- archive decisions

## Volume Policy

Volume is a first-class signal and must be tracked across scouts and analysts.

Required volume concepts:

- absolute volume
- relative volume versus baseline
- breakout volume
- exhaustion volume
- volume with OI expansion
- volume without follow-through
- volume decay after trigger

Usage by role:

- `Derivatives Scout` tracks broad volume and abnormal volume shifts.
- `Scalping Analyst` uses volume for breakout and reversal confirmation.
- `Scalp Tracker` uses volume to judge whether a setup is strengthening or failing.
- `Longer-Term Coin Analyst` uses sustained and breakout volume to judge trend quality.
- `Validation Scout` refreshes volume context on selected coins only.
- `Correlation Analyst` includes volume as a core confluence pillar.

## Notion Workspace Structure

### 1. Master Data Log

Purpose:
- raw intake for all scout events

Suggested fields:
- Event ID
- Timestamp
- Source Scout
- Coin
- Event Type
- Direction
- Size
- Value USD
- Wallet
- Exchange
- Raw Summary
- Priority
- Linked Setup

### 2. Scalp Board

Purpose:
- active home for scalp setups

Suggested fields:
- Coin
- Direction
- Timeframe
- Setup Type
- Entry Zone
- Stop
- Target 1
- Target 2
- Confidence
- Confluence Status
- Status
- Priority
- Thesis
- Last Update
- Expiration Time

### 3. Scalp Updates

Purpose:
- running log of scalp setup changes

Suggested fields:
- Setup Relation
- Timestamp
- Previous Status
- New Status
- What Changed
- Volume Update
- Validation Status
- Analyst Note

### 4. Asset Library

Purpose:
- serious watchlist for swing and longer-term names

Suggested fields:
- Coin
- Bias
- Regime
- Conviction
- Trend Quality
- Volume Quality
- Wallet Support
- Whale Support
- Narrative Support
- Key Levels
- Risk Flags
- Next Review Date
- Status

### 5. Whale Registry

Purpose:
- tracked high-profile wallets and entities

Suggested fields:
- Wallet Address
- Alias
- Wallet Type
- Chain
- Score
- Win Rate
- Main Coins
- Last Major Move
- Status
- Notes

### 6. Wallet Activity Log

Purpose:
- log all important wallet-related actions

Suggested fields:
- Wallet Relation
- Coin
- Action
- Size
- Value USD
- Source
- Destination
- Timestamp
- Signal Strength
- Notes

### 7. Validation Queue

Purpose:
- list of coins needing focused follow-up

Suggested fields:
- Coin
- Source Board
- Reason Added
- Priority
- Last Checked
- Validation Status
- Assigned Scout

### 8. Correlation Board

Purpose:
- final confluence summary for promoted ideas

Suggested fields:
- Coin
- Opportunity Type
- Confluence Status
- Confidence
- Bullish Factors
- Bearish Factors
- Wallet Alignment
- Whale Alignment
- Derivatives Alignment
- Volume Alignment
- Sentiment Alignment
- Decision
- Last Updated

### 9. Decision Queue

Purpose:
- human approval and promotion layer

Suggested fields:
- Coin
- Opportunity Type
- Recommended Action
- Urgency
- Confidence
- Summary
- Status
- Approved By
- Timestamp

## Slack Channel Structure

### `#signals`

Use for:
- high-quality scalp alerts
- urgent trade-ready updates

### `#scalp-updates`

Use for:
- scalp status changes
- trigger notices
- invalidations
- target hits

### `#watchlist-updates`

Use for:
- longer-term coin promotions
- removals
- major conviction changes

### `#wallet-alerts`

Use for:
- elite wallet actions
- major whale flow
- wallet cluster signals

### `#ops`

Use for:
- scout failures
- analyst failures
- Railway health
- sync and integration issues

## Run Cadence

### Continuous or Frequent

- `Whale Scout`
- `Wallet Scout`
- `Derivatives Scout`
- `Sentiment Scout`
- `Scalping Analyst`
- `Scalp Tracker`

### Scheduled or Slower Cadence

- `Longer-Term Coin Analyst`
- `Wallet Analyst`

### Triggered by Selection

- `Validation Scout`
- `Correlation Analyst`
- `Decision Router`

## Trigger Logic

### When a new scalp is found

1. Add to `Scalp Board`
2. Add to `Validation Queue`
3. Run `Validation Scout`
4. Run `Correlation Analyst`
5. If strong enough, post to `#signals`
6. Hand off to `Scalp Tracker`

### When a longer-term coin is promoted

1. Add or update in `Asset Library`
2. Add to `Validation Queue`
3. Run `Validation Scout`
4. Run `Correlation Analyst`
5. If meaningful, post to `#watchlist-updates`

### When a wallet or whale event hits a tracked coin

1. Log to `Master Data Log`
2. Update `Wallet Activity Log` or `Whale Registry` if needed
3. Check if the coin is on `Scalp Board` or `Asset Library`
4. If yes, trigger `Validation Scout`
5. Refresh confluence via `Correlation Analyst`

## Railway Deployment Plan

### Phase 1: Always-On Broad Scouts

Deploy first:

- Whale Scout
- Wallet Scout
- Derivatives Scout
- Sentiment Scout

Reason:
- these create the raw evidence foundation
- they benefit most from 24/7 uptime

### Phase 2: Focused Investigation

Deploy next:

- Validation Scout
- Wallet Analyst

Reason:
- these enrich selected coins and refine smart-money quality

### Phase 3: Living Setup Maintenance

Deploy after that:

- Scalp Tracker
- Correlation Analyst
- Decision Router

Reason:
- these depend on stable upstream evidence and active boards

### Local or Hybrid Layer

Keep local or hybrid when needed:

- Bookmap-dependent scalp context
- any low-latency local addon logic
- any hardware-specific OpenVINO paths until cloud runtime is stabilized

## OpenVINO Targeting Guidance

OpenVINO models should support analyst inference, not broad raw data scraping.

Suggested usage:

- `Scalping Analyst`: pattern and short-horizon setup scoring
- `Longer-Term Coin Analyst`: regime and conviction scoring
- `Correlation Analyst`: final evidence alignment scoring

Scouts should remain mostly deterministic and data-collection focused.
Analysts are where model inference adds the most value.

## MVP Recommendation

Build the first live workspace around:

1. `Whale Scout`
2. `Wallet Scout`
3. `Derivatives Scout`
4. `Sentiment Scout`
5. `Scalping Analyst`
6. `Scalp Tracker`
7. `Validation Scout`
8. `Correlation Analyst`

Then add:

9. `Longer-Term Coin Analyst`
10. `Wallet Analyst`
11. `Decision Router`

## One-Line Summary

The workspace should use broad scouts to discover signals, focused scouts to deepen selected coins, analysts to judge opportunity quality, trackers to keep ideas alive, and a correlation layer to decide when evidence is strong enough to matter.
