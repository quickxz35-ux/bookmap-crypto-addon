# Crypto Workspace Operating Model (Final)

Updated: 2026-04-03 (America/Chicago)

## Purpose

This document is the final operating contract for the crypto intelligence workspace. It replaces older drafts that allowed raw scout intake into Notion and locks the system into a local-first, Black-Box-centered architecture with optional Railway/Postgres mirroring.

## Non-Negotiable Rules

- Raw scouts write only to the `Local Black Box` or its Railway/Postgres mirror.
- Raw scouts do not write directly to Notion.
- Analysts read from the Black Box.
- Analysts write structured intelligence to Notion.
- Slack is reserved for high-signal alerts, material status changes, and ops failures.
- OpenVINO belongs in the analyst layer, never in the raw scout layer.
- Broad market discovery stays separate from focused validation of selected coins.
- Secrets stay in env/config only and must never be hardcoded.
- The local SQLite Black Box remains the primary development path even when Railway mirroring is enabled.

## Final Layer Model

### Layer 1: Raw Discovery

Purpose:
- collect broad-market evidence
- normalize provider responses into stable event records
- preserve raw payloads and provenance

Services:
- `Whale Scout`
- `Wallet Scout`
- `Derivatives Scout`
- `Sentiment Scout`

Allowed writes:
- `Local Black Box`
- optional mirror to Railway/Postgres

Forbidden writes:
- Notion
- Slack, except ops failures routed through a separate ops notifier

### Layer 2: Focused Follow-Up

Purpose:
- refresh evidence for assets that already matter
- deepen conviction or invalidate active ideas

Services:
- `Validation Scout`

Allowed reads:
- selected assets from Notion or local routing outbox
- Black Box historical and recent evidence
- targeted provider refreshes for selected assets only

Allowed writes:
- Black Box analyst cache tables
- structured output handed to analysts/router

Forbidden behavior:
- broad market scanning
- direct raw provider dumping into Notion

### Layer 3: Intelligence

Purpose:
- transform evidence into trade and watchlist intelligence
- maintain setup and asset lifecycles
- produce deterministic summaries before any model scoring

Services:
- `Scalping Analyst`
- `Scalp Tracker`
- `Longer-Term Coin Analyst`
- `Wallet Analyst`
- `Correlation Analyst`
- `Decision Router`

Allowed writes:
- analyst cache tables
- Notion structured intelligence
- Slack high-signal alerts through router policy

## Final Responsibility Map

### Whale Scout

Scope:
- broad market discovery of large exchange-linked and whale-linked asset movements

Primary responsibilities:
- detect large inflows, outflows, balance swings, concentration spikes, and transfer clusters
- classify the move as `exchange_inflow`, `exchange_outflow`, `whale_accumulation`, `whale_distribution`, `treasury_move`, or `unknown_large_transfer`
- record wallet/entity label when known
- preserve provider payload and source timestamps

Must not:
- score trade setups
- decide whether a coin should go to Notion

### Wallet Scout

Scope:
- broad watchlist monitoring for tracked wallets

Primary responsibilities:
- ingest tracked-wallet transactions
- classify wallet actions as `buy`, `sell`, `send`, `receive`, `swap_in`, `swap_out`, `bridge`, `lp`, or `unknown`
- maintain coin participation history by wallet
- preserve transaction hash uniqueness and source chain/network

Must not:
- estimate wallet skill beyond deterministic metrics
- promote coins to the board layer

### Derivatives Scout

Scope:
- broad market derivatives discovery

Primary responsibilities:
- snapshot open interest, funding, long-short skew, liquidations, and volume
- treat `absolute volume`, `relative volume`, and `volume acceleration` as first-class fields
- separate market-wide volume ranking from selected-coin validation

Must not:
- infer trade direction beyond deterministic tags like `oi_expanding`, `funding_positive`, `volume_spike`
- own coin promotion decisions

### Sentiment Scout

Scope:
- broad headline and narrative discovery

Primary responsibilities:
- ingest headlines, source metadata, timestamps, URL uniqueness, and optional source sentiment labels
- attach assets when deterministically resolvable
- preserve raw story payloads for later analyst parsing

Must not:
- summarize final thesis for Notion
- alert Slack directly on raw headlines

### Validation Scout

Scope:
- focused follow-up only for assets already present in `Scalp Board`, `Asset Library`, `Decision Queue`, or a local selected-assets file/outbox

Primary responsibilities:
- re-read latest whale, wallet, derivatives, volume, and sentiment evidence for selected assets
- run targeted provider refreshes for the selected asset only
- return a structured validation result with supportive and conflicting factors
- cache validation results in the Black Box for downstream analysts

Must not:
- act as a broad market screener
- create new asset candidates on its own

### Scalping Analyst

Scope:
- short-horizon setup identification

Primary responsibilities:
- interpret recent derivatives, whale, wallet, validation, and execution-layer context
- define `entry_zone`, `invalidation`, `targets`, `urgency`, and `volume_state`
- produce the initial scalp lifecycle state

Must not:
- own lifecycle maintenance after the initial setup
- write directly to Slack

### Scalp Tracker

Scope:
- lifecycle maintenance for active scalp ideas

Primary responsibilities:
- refresh a scalp after creation
- compare new evidence versus the prior setup snapshot
- update lifecycle state and explain what changed
- explicitly judge whether volume is strengthening, fading, or failing

Must not:
- create new scalp ideas from scratch

### Longer-Term Coin Analyst

Scope:
- serious watchlist maintenance

Primary responsibilities:
- judge higher-timeframe structure, participation quality, derivatives backdrop, narrative strength, and wallet/whale support
- classify long-term lifecycle state
- define key levels, risk flags, and next review cadence

Must not:
- behave like a scalp engine

### Wallet Analyst

Scope:
- wallet intelligence ranking

Primary responsibilities:
- score wallets using Black Box wallet history and normalized outcomes
- classify wallets as `elite`, `watch`, or `ignore`
- produce coin clusters and overlap intelligence

Must not:
- own transaction ingestion

### Correlation Analyst

Scope:
- cross-signal confluence

Primary responsibilities:
- combine analyst outputs with validation evidence
- list supportive factors and conflicting factors
- produce final confluence class and confidence score

Must not:
- replace specialist analysts with one generic score blob

### Decision Router

Scope:
- workspace routing and alert gating

Primary responsibilities:
- decide which Notion databases receive which analyst outputs
- decide which results qualify for Slack
- archive low-signal items to local outbox/history only

Must not:
- generate core analysis

## Final Data Flow Map

1. Providers -> raw scouts
2. Raw scouts -> `Local Black Box` SQLite
3. Optional mirror job -> Railway/Postgres
4. Analysts and validation -> read from Black Box, optionally perform targeted refreshes
5. Analysts -> write structured outputs to analyst cache tables
6. Decision Router -> writes approved structured outputs to Notion
7. Decision Router -> posts only high-signal updates to Slack

Important separation:
- `Derivatives Scout`, `Whale Scout`, `Wallet Scout`, and `Sentiment Scout` are for discovery.
- `Validation Scout` is for already-selected assets only.

## Black Box Architecture

### Storage Model

Primary local store:
- `SQLite` at `LOCAL_BLACKBOX_PATH`

Optional mirror:
- `Postgres` via `DATABASE_URL`

Recommendation:
- keep local SQLite as the write-ahead operational store for local-first resilience
- mirror asynchronously to Railway/Postgres instead of switching primary persistence based only on env presence
- use a dedicated mirror worker so local collection still works if cloud is unavailable

### Required Schema Changes

The current schema in [local_blackbox.py](/Users/gssjr/OneDrive/Documents/New project/local_blackbox.py) is functional but too shallow for production. The final schema should move toward event tables plus normalization dimensions.

#### 1. `whale_events`

Purpose:
- normalized whale and exchange-flow events

Recommended fields:
- `event_id` text primary key
- `observed_at` timestamptz
- `ingested_at` timestamptz
- `asset`
- `chain`
- `source_provider`
- `entity_label`
- `wallet_address`
- `counterparty_address`
- `event_type`
- `flow_direction`
- `amount_native`
- `amount_usd`
- `price_at_event`
- `exchange_name`
- `confidence_raw`
- `tags_json`
- `raw_payload_json`

Indexes:
- `(asset, observed_at desc)`
- `(wallet_address, observed_at desc)`
- `(event_type, observed_at desc)`

#### 2. `wallet_transactions`

Purpose:
- normalized tracked-wallet activity

Recommended fields:
- `tx_id` text primary key
- `observed_at`
- `ingested_at`
- `wallet_address`
- `wallet_alias`
- `chain`
- `network`
- `asset`
- `action_type`
- `amount_native`
- `amount_usd`
- `price_at_event`
- `counterparty_address`
- `protocol_name`
- `tx_hash`
- `block_number`
- `fee_native`
- `source_provider`
- `raw_payload_json`

Indexes:
- `(wallet_address, observed_at desc)`
- `(asset, observed_at desc)`
- `(action_type, observed_at desc)`

#### 3. `derivatives_snapshots`

Purpose:
- time-series market snapshots

Recommended fields:
- `snapshot_id` text primary key
- `observed_at`
- `ingested_at`
- `asset`
- `venue`
- `timeframe`
- `open_interest`
- `open_interest_change_pct`
- `funding_rate`
- `long_short_ratio`
- `liquidations_long_usd`
- `liquidations_short_usd`
- `liquidations_total_usd`
- `volume_absolute`
- `volume_relative`
- `volume_change_pct`
- `volume_baseline_window`
- `basis`
- `mark_price`
- `tags_json`
- `raw_payload_json`

Indexes:
- `(asset, observed_at desc)`
- `(asset, timeframe, observed_at desc)`

#### 4. `sentiment_logs`

Purpose:
- normalized narrative evidence

Recommended fields:
- `story_id` text primary key
- `published_at`
- `ingested_at`
- `asset`
- `source_provider`
- `source_domain`
- `headline`
- `url`
- `sentiment_label_raw`
- `sentiment_score_raw`
- `topic_tags_json`
- `language`
- `raw_payload_json`

Indexes:
- `(asset, published_at desc)`
- `(source_domain, published_at desc)`

#### 5. `analyst_output_cache`

Purpose:
- normalized analyst and tracker outputs before Notion routing

Recommended fields:
- `cache_id` text primary key
- `generated_at`
- `asset`
- `agent_name`
- `opportunity_type`
- `lifecycle_state`
- `confidence_score`
- `summary_text`
- `input_hash`
- `output_json`
- `target_database`
- `delivery_status`
- `delivered_at`

Indexes:
- `(asset, generated_at desc)`
- `(agent_name, generated_at desc)`
- `(delivery_status, generated_at desc)`

#### 6. Future normalization dimensions

Add dimension tables once volumes grow:
- `dim_assets`
- `dim_wallets`
- `dim_exchanges`
- `dim_providers`
- `dim_tags`

This keeps raw events append-only while allowing analysts to join enriched metadata.

## Analyst Input Contracts

All analysts should read a stable contract assembled from the Black Box instead of raw provider payloads.

### Shared input fields

- `asset`
- `generated_at`
- `price_context`
- `whale_summary`
- `wallet_summary`
- `derivatives_summary`
- `sentiment_summary`
- `validation_summary` when available
- `history_window`

### Whale summary contract

- `event_count_1h`
- `event_count_24h`
- `net_flow_usd_1h`
- `net_flow_usd_24h`
- `exchange_inflow_usd_24h`
- `exchange_outflow_usd_24h`
- `largest_event_type`
- `largest_event_usd`
- `recent_entity_labels`

### Wallet summary contract

- `tracked_wallet_tx_count_1h`
- `tracked_wallet_tx_count_24h`
- `buy_count_24h`
- `sell_count_24h`
- `net_tracked_flow_usd_24h`
- `elite_wallet_participation`
- `wallet_cluster_labels`
- `top_wallets`

### Derivatives summary contract

- `snapshot_count`
- `oi_latest`
- `oi_change_pct_15m`
- `oi_change_pct_1h`
- `funding_latest`
- `long_short_ratio_latest`
- `liquidations_total_usd_1h`
- `volume_absolute_latest`
- `volume_relative_latest`
- `volume_change_pct_latest`
- `volume_state`

### Sentiment summary contract

- `headline_count_6h`
- `headline_count_24h`
- `positive_headline_count`
- `negative_headline_count`
- `neutral_headline_count`
- `sentiment_score_avg`
- `dominant_topics`
- `latest_headlines`

### Validation summary contract

- `validation_status`
- `supportive_factors`
- `conflicting_factors`
- `volume_support`
- `last_validated_at`

### Analyst-specific requirements

#### Scalping Analyst input

- shared input contract
- shortest derivatives window
- current relative volume
- near-term liquidation state
- execution context placeholder for Bookmap/order flow when local

#### Scalp Tracker input

- prior scalp setup output
- latest shared input contract
- latest validation result

#### Longer-Term Coin Analyst input

- shared input contract
- higher-timeframe derivatives aggregates
- rolling participation trends over 7d and 30d
- narrative persistence, not just latest headline count

#### Wallet Analyst input

- wallet transaction history
- realized and proxy performance history
- coin overlap and recurrence

#### Correlation Analyst input

- latest primary analyst output
- latest validation result
- optional wallet analyst summary

## Analyst Output Contracts

Every analyst should emit a structured payload before any Notion write.

### Common output fields

- `agent`
- `asset`
- `generated_at`
- `opportunity_type`
- `confidence_score`
- `summary`
- `supportive_factors`
- `conflicting_factors`
- `source_snapshot_ids`
- `version`

### Scalping Analyst output

- `status`
- `direction`
- `setup_type`
- `timeframe`
- `entry_zone`
- `invalidation`
- `stop`
- `target_1`
- `target_2`
- `urgency`
- `volume_state`
- `thesis_points`

### Scalp Tracker output

- `previous_status`
- `new_status`
- `change_reason`
- `volume_state`
- `confidence_delta`
- `refresh_due_at`

### Longer-Term Coin Analyst output

- `bias`
- `regime`
- `status`
- `trend_quality`
- `volume_quality`
- `wallet_support`
- `whale_support`
- `narrative_support`
- `key_levels`
- `risk_flags`
- `next_review_at`

### Wallet Analyst output

- `wallet_address`
- `alias`
- `status`
- `wallet_score`
- `win_rate`
- `net_flow_proxy`
- `coin_clusters`
- `notes`

### Correlation Analyst output

- `confluence_status`
- `supporting_factors`
- `conflicting_factors`
- `confidence_score`
- `alignment_summary`

### Decision Router output

- `target_database`
- `write_action`
- `slack_action`
- `delivery_summary`

## Volume as a First-Class Signal

Volume must exist as an explicit field, not just a note.

### Required measures

- `volume_absolute`
- `volume_relative`
- `volume_change_pct`
- `volume_baseline`
- `volume_state`
- `volume_confirmation`

### Required ownership

`Derivatives Scout`
- captures market-wide absolute and relative volume

`Validation Scout`
- refreshes selected-asset volume context only

`Scalping Analyst`
- uses breakout and reversal volume confirmation

`Scalp Tracker`
- judges sustain/fade after trigger using post-trigger volume

`Longer-Term Coin Analyst`
- uses sustained participation and breakout volume quality

`Correlation Analyst`
- treats volume as an independent confluence pillar, not a derivative subfield

## Final Lifecycle Models

### Scalp lifecycle

Locked states:
- `new`
- `watch`
- `near_entry`
- `triggered`
- `strengthening`
- `weakening`
- `invalid`
- `expired`
- `archived`

State intent:
- `new`: first analyst output, not yet routed
- `watch`: promising but not close enough
- `near_entry`: close to entry conditions
- `triggered`: entry conditions hit
- `strengthening`: still improving after trigger
- `weakening`: thesis still alive but degrading
- `invalid`: thesis broken before or after trigger
- `expired`: time-window ended without valid trigger
- `archived`: no longer operational, kept for history

### Longer-term coin lifecycle

Locked states:
- `watch`
- `promote`
- `accumulation`
- `breakout`
- `continuation`
- `weakening`
- `remove`

State intent:
- `watch`: early interest
- `promote`: deserves active attention
- `accumulation`: constructive base or stealth participation
- `breakout`: decisive move with confirmation
- `continuation`: trend remains healthy
- `weakening`: trend quality or support is slipping
- `remove`: no longer belongs in the serious library

## Notion Architecture

### Database set

#### `Scalp Board`

Owner agents:
- `Scalping Analyst`
- `Scalp Tracker`
- `Decision Router`

Purpose:
- active scalp record, one page per live or recently active scalp

Core fields:
- `Coin`
- `Direction`
- `Timeframe`
- `Setup Type`
- `Entry Zone`
- `Invalidation`
- `Stop`
- `Target 1`
- `Target 2`
- `Confidence`
- `Confluence`
- `Status`
- `Urgency`
- `Thesis`
- `Last Update`
- `Expires At`

#### `Scalp Updates`

Owner agents:
- `Scalp Tracker`
- `Decision Router`

Purpose:
- append-only status history for scalp changes

Core fields:
- `Scalp`
- `Timestamp`
- `Previous Status`
- `New Status`
- `What Changed`
- `Volume State`
- `Validation Status`
- `Confidence Delta`

#### `Asset Library`

Owner agents:
- `Longer-Term Coin Analyst`
- `Decision Router`

Purpose:
- serious watchlist and long-term lifecycle tracking

Core fields:
- `Coin`
- `Bias`
- `Regime`
- `Status`
- `Conviction`
- `Trend Quality`
- `Volume Quality`
- `Wallet Support`
- `Whale Support`
- `Narrative Support`
- `Key Levels`
- `Risk Flags`
- `Next Review`

#### `Whale Registry`

Owner agents:
- `Wallet Analyst`
- `Decision Router`

Purpose:
- tracked entity and wallet intelligence, not raw events

Core fields:
- `Wallet Address`
- `Alias`
- `Wallet Type`
- `Chain`
- `Wallet Score`
- `Win Rate`
- `Main Coins`
- `Last Major Move`
- `Status`
- `Notes`

#### `Wallet Activity Log`

Owner agents:
- `Decision Router`
- `Wallet Analyst` for enriched wallet events only

Purpose:
- high-value wallet events tied to tracked entities

Core fields:
- `Wallet`
- `Coin`
- `Action`
- `Value USD`
- `Signal Strength`
- `Timestamp`
- `Notes`

#### `Validation Queue`

Owner agents:
- `Decision Router`
- `Validation Scout`

Purpose:
- selected coins awaiting focused refresh

Core fields:
- `Coin`
- `Source Board`
- `Reason Added`
- `Priority`
- `Last Checked`
- `Validation Status`
- `Assigned Agent`

#### `Correlation Board`

Owner agents:
- `Correlation Analyst`
- `Decision Router`

Purpose:
- confluence summary for promoted ideas

Core fields:
- `Coin`
- `Opportunity Type`
- `Confluence Status`
- `Confidence`
- `Supporting Factors`
- `Conflicting Factors`
- `Volume Alignment`
- `Wallet Alignment`
- `Whale Alignment`
- `Derivatives Alignment`
- `Sentiment Alignment`
- `Decision`
- `Last Updated`

#### `Decision Queue`

Owner agents:
- `Decision Router`

Purpose:
- final human review and escalation layer

Core fields:
- `Coin`
- `Opportunity Type`
- `Recommended Action`
- `Urgency`
- `Confidence`
- `Summary`
- `Status`
- `Timestamp`

### Notion write permissions

- Raw scouts: no Notion write permissions
- `Validation Scout`: may update `Validation Queue` status only through router-approved actions
- `Scalping Analyst`: may create or update `Scalp Board`
- `Scalp Tracker`: may update `Scalp Board` and append to `Scalp Updates`
- `Longer-Term Coin Analyst`: may create or update `Asset Library`
- `Wallet Analyst`: may update `Whale Registry` and write enriched `Wallet Activity Log`
- `Correlation Analyst`: may update `Correlation Board`
- `Decision Router`: may write to every decision-facing database and is the only agent allowed to write `Decision Queue`

## Slack Alert Policy

### Send to Slack

`#signals`
- new scalp with `confluence_status = confirmed`
- scalp moves to `triggered`
- scalp strengthens materially after trigger

`#scalp-updates`
- `near_entry -> triggered`
- `triggered -> strengthening`
- `triggered/strengthening -> invalid`
- major target or expiry events if you later track realized outcomes

`#watchlist-updates`
- long-term asset moves to `promote`, `breakout`, or `continuation` with strong confluence
- long-term asset moves to `remove` only when it was previously high conviction

`#wallet-alerts`
- elite wallet cluster enters or exits a tracked asset
- major whale event aligns with an active scalp or promoted long-term coin

`#ops`
- provider failure
- Notion failure
- Slack failure
- mirror lag
- schema/migration failure

### Notion only, no Slack

- weak or mixed validation that does not change lifecycle
- routine tracker refreshes
- low-confidence headlines
- raw scout events without active board relevance

## Confluence / Correlation Model

### Required outputs

- `supportive_factors`
- `conflicting_factors`
- `confidence_score`
- `confluence_status`

### Confluence classes

- `confirmed`: confidence >= 80 and no major conflicting factor
- `mixed`: confidence 55-79 or balanced support/conflict
- `weak`: confidence 35-54 with partial support
- `rejected`: confidence < 35 or hard invalidation present

### Factor buckets

Supportive factors can include:
- `whale_accumulation`
- `elite_wallet_support`
- `oi_expansion_with_volume`
- `breakout_volume_confirmation`
- `positive_narrative_shift`
- `validation_supportive`

Conflicting factors can include:
- `exchange_inflow_risk`
- `wallet_distribution`
- `funding_overcrowded`
- `volume_failure`
- `negative_narrative_shift`
- `validation_invalidating`

## OpenVINO Placement

OpenVINO starts only after deterministic feature assembly is complete.

### Allowed analyst usage

`Scalping Analyst`
- use model inference for short-horizon setup quality scoring after deterministic features are built

`Longer-Term Coin Analyst`
- use model inference for regime classification and conviction ranking after deterministic evidence summary is prepared

`Correlation Analyst`
- use model inference for evidence weighting only after supportive/conflicting factors have been deterministically enumerated

`Sentiment Analyst` if added later
- use the existing optimized sentiment model for headline scoring in the analyst layer, not in the raw scout

### Recommended model features

For `Scalping Analyst`:
- OI change
- funding
- absolute and relative volume
- liquidation imbalance
- whale event density
- wallet participation
- recent validation status

For `Longer-Term Coin Analyst`:
- rolling OI/funding profile
- breakout volume quality
- wallet and whale support persistence
- sentiment persistence
- volatility regime

For `Correlation Analyst`:
- primary analyst score
- validation status
- factor counts
- presence of hard conflicts
- volume confirmation state

### Deterministic boundary

Deterministic logic should:
- normalize provider data
- calculate summary features
- classify hard invalidations
- assign lifecycle states and factor labels

Inference should begin only when the input is already a stable feature vector or factor set.

## Railway Deployment Architecture

### Service order

#### Phase 1: raw discovery workers

Deploy first:
- `whale-scout`
- `wallet-scout`
- `derivatives-scout`
- `sentiment-scout`

Reason:
- they create the evidence base everything else depends on

#### Phase 2: focused intelligence workers

Deploy next:
- `validation-scout`
- `wallet-analyst`
- `long-term-coin-analyst`

Reason:
- these enrich the signal base after raw collection is stable

#### Phase 3: setup lifecycle and routing

Deploy after that:
- `scalping-analyst`
- `scalp-tracker`
- `correlation-analyst`
- `decision-router`

Reason:
- they depend on both raw evidence and selected-asset state

### Local / hybrid services

Keep local or hybrid:
- Bookmap-dependent execution logic
- latency-sensitive microstructure tools
- OpenVINO-heavy experimentation until cloud resource sizing is proven

### Cloud-first services

Prefer cloud-first:
- raw scouts
- validation scout
- long-term analyst
- router and correlation worker

### Mirroring strategy

Recommended:
- raw scouts write locally first
- mirror worker batches SQLite changes to Railway/Postgres
- Railway readers can consume mirrored data for cloud analytics
- if Railway is unavailable, local collection continues and replay happens later

## Final Config Architecture

### Provider env groups

#### Moralis

- `MORALIS_API_KEY`

#### CryptoAPIs

- `CRYPTOAPIS_API_KEY`
- `CRYPTOAPIS_BLOCKCHAIN`
- `CRYPTOAPIS_NETWORK`

#### Binance

- `BINANCE_FUTURES_BASE_URL`
- `BINANCE_API_KEY` optional
- `BINANCE_API_SECRET` optional

#### CryptoPanic

- `CRYPTOPANIC_API_KEY`

### Workspace env groups

#### Notion

- `NOTION_TOKEN`
- `SCALP_BOARD_DB_ID`
- `SCALP_UPDATES_DB_ID`
- `ASSET_LIBRARY_DB_ID`
- `WHALE_REGISTRY_DB_ID`
- `WALLET_ACTIVITY_DB_ID`
- `VALIDATION_QUEUE_DB_ID`
- `CORRELATION_BOARD_DB_ID`
- `DECISION_QUEUE_DB_ID`

#### Slack

- `SLACK_TOKEN`
- `ALERTS_CHANNEL_ID`
- `SIGNALS_CHANNEL_ID`
- `SCALP_UPDATES_CHANNEL_ID`
- `WATCHLIST_UPDATES_CHANNEL_ID`
- `WALLET_ALERTS_CHANNEL_ID`
- `OPS_CHANNEL_ID`

### Black Box / mirror env groups

- `BLACKBOX_MODE` with `local_first` as default
- `LOCAL_BLACKBOX_PATH`
- `DATABASE_URL`
- `RAILWAY_MIRROR_ENABLED`
- `RAILWAY_MIRROR_BATCH_SIZE`

### Runtime env groups

- `SELECTED_ASSETS_SOURCE`
- `VALIDATION_BATCH_SIZE`
- `ENABLE_OPENVINO_ANALYSTS`
- `ANALYST_CACHE_TTL_SECONDS`

## Missing Pieces / Gap Report

### Complete enough now

- Local Black Box exists and is writing live data from whale and wallet scouts through [local_blackbox.py](/Users/gssjr/OneDrive/Documents/New project/local_blackbox.py), [scout_whale.py](/Users/gssjr/OneDrive/Documents/New project/scout_whale.py), and [scout_wallet.py](/Users/gssjr/OneDrive/Documents/New project/scout_wallet.py)
- Provider handlers exist for Moralis and CryptoAPIs in [moralis_handler.py](/Users/gssjr/OneDrive/Documents/New project/moralis_handler.py) and [cryptoapis_handler.py](/Users/gssjr/OneDrive/Documents/New project/cryptoapis_handler.py)
- MVP analyst/routing path exists in [workspace_pipeline.py](/Users/gssjr/OneDrive/Documents/New project/workspace_pipeline.py), [decision_router.py](/Users/gssjr/OneDrive/Documents/New project/decision_router.py), and the analyst modules
- Notion/Slack clients already guard against placeholder values in [workspace_config.py](/Users/gssjr/OneDrive/Documents/New project/workspace_config.py)

### Partly stubbed

- `Derivatives Scout` captures only a thin subset of the needed fields and currently leaves `volume_24h` effectively stubbed in [scout_derivatives.py](/Users/gssjr/OneDrive/Documents/New project/scout_derivatives.py)
- `Sentiment Scout` ingests headlines but does not yet attach stable asset mapping, narrative tags, or deduplicated sentiment scoring in [scout_sentiment.py](/Users/gssjr/OneDrive/Documents/New project/scout_sentiment.py)
- `Validation Scout` currently reads broad Black Box slices but does not yet enforce selected-asset-only routing from Notion/queue state in [validation_scout.py](/Users/gssjr/OneDrive/Documents/New project/validation_scout.py)
- `Wallet Analyst` uses placeholder scoring logic instead of normalized realized performance in [analyst_wallet.py](/Users/gssjr/OneDrive/Documents/New project/analyst_wallet.py)
- `Decision Router` writes directly to Notion pages but does not yet enforce database-specific idempotency, update-vs-create behavior, or delivery tracking in [decision_router.py](/Users/gssjr/OneDrive/Documents/New project/decision_router.py)

### Still needs to be built

- async or batched Railway mirror worker
- normalized event IDs and durable schema migrations
- analyst cache tables
- lifecycle-aware Notion updates instead of create-only writes
- selected-assets feed for `Validation Scout`
- confluence factor taxonomy and hard conflict rules in code
- OpenVINO analyst inference integration behind a feature flag

### Needs refactoring before production

- persistence layer should stop mixing SQLite placeholder SQL with Postgres mode; database adapters should be explicit
- raw and structured schemas should use JSON payload columns and stable IDs
- router should separate routing policy from transport clients
- `.env` architecture should be grouped by provider and runtime domain
- Railway process model should move from one `Procfile` to one service per worker or scheduler target

## Recommended Next Implementation Order

1. Upgrade the Black Box schema and add explicit migrations plus mirror-worker design.
2. Expand `Derivatives Scout` so volume, liquidations, and snapshot IDs are first-class.
3. Normalize `Sentiment Scout` and wallet event classification.
4. Build the selected-asset input path for `Validation Scout` from `Validation Queue` and local outbox.
5. Add analyst cache tables and write every analyst output there before Notion routing.
6. Refactor `Decision Router` into idempotent create/update behavior per Notion database.
7. Lock lifecycle transitions in code for scalp and longer-term asset states.
8. Add confluence factor taxonomy and confidence rules to `Correlation Analyst`.
9. Add OpenVINO inference behind `ENABLE_OPENVINO_ANALYSTS` after deterministic features are stable.
10. Deploy Railway services in the phase order defined above.

## Final Summary

The final architecture is a Black-Box-centered intelligence system:
- raw scouts discover and store evidence
- validation deepens only selected assets
- specialist analysts produce structured intelligence
- correlation decides whether the evidence actually lines up
- the router controls what reaches Notion and what deserves Slack

That separation keeps discovery broad, validation focused, model inference contained, and the local-first workflow intact while still allowing Railway to host the always-on parts.
