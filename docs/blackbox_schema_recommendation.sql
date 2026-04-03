-- Crypto workspace schema recommendation
-- Documentation-only reference for the next migration pass.

CREATE TABLE whale_events (
    event_id TEXT PRIMARY KEY,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    asset TEXT NOT NULL,
    chain TEXT,
    source_provider TEXT NOT NULL,
    entity_label TEXT,
    wallet_address TEXT,
    counterparty_address TEXT,
    event_type TEXT NOT NULL,
    flow_direction TEXT,
    amount_native NUMERIC,
    amount_usd NUMERIC,
    price_at_event NUMERIC,
    exchange_name TEXT,
    confidence_raw NUMERIC,
    tags_json JSONB,
    raw_payload_json JSONB NOT NULL
);

CREATE INDEX whale_events_asset_observed_idx ON whale_events (asset, observed_at DESC);
CREATE INDEX whale_events_wallet_observed_idx ON whale_events (wallet_address, observed_at DESC);

CREATE TABLE wallet_transactions (
    tx_id TEXT PRIMARY KEY,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    wallet_address TEXT NOT NULL,
    wallet_alias TEXT,
    chain TEXT,
    network TEXT,
    asset TEXT,
    action_type TEXT NOT NULL,
    amount_native NUMERIC,
    amount_usd NUMERIC,
    price_at_event NUMERIC,
    counterparty_address TEXT,
    protocol_name TEXT,
    tx_hash TEXT,
    block_number BIGINT,
    fee_native NUMERIC,
    source_provider TEXT NOT NULL,
    raw_payload_json JSONB NOT NULL
);

CREATE INDEX wallet_transactions_wallet_observed_idx ON wallet_transactions (wallet_address, observed_at DESC);
CREATE INDEX wallet_transactions_asset_observed_idx ON wallet_transactions (asset, observed_at DESC);

CREATE TABLE derivatives_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    asset TEXT NOT NULL,
    venue TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_interest NUMERIC,
    open_interest_change_pct NUMERIC,
    funding_rate NUMERIC,
    long_short_ratio NUMERIC,
    liquidations_long_usd NUMERIC,
    liquidations_short_usd NUMERIC,
    liquidations_total_usd NUMERIC,
    volume_absolute NUMERIC,
    volume_relative NUMERIC,
    volume_change_pct NUMERIC,
    volume_baseline_window TEXT,
    basis NUMERIC,
    mark_price NUMERIC,
    tags_json JSONB,
    raw_payload_json JSONB NOT NULL
);

CREATE INDEX derivatives_snapshots_asset_observed_idx ON derivatives_snapshots (asset, observed_at DESC);
CREATE INDEX derivatives_snapshots_asset_timeframe_observed_idx ON derivatives_snapshots (asset, timeframe, observed_at DESC);

CREATE TABLE sentiment_logs (
    story_id TEXT PRIMARY KEY,
    published_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    asset TEXT,
    source_provider TEXT NOT NULL,
    source_domain TEXT,
    headline TEXT NOT NULL,
    url TEXT UNIQUE,
    sentiment_label_raw TEXT,
    sentiment_score_raw NUMERIC,
    topic_tags_json JSONB,
    language TEXT,
    raw_payload_json JSONB NOT NULL
);

CREATE INDEX sentiment_logs_asset_published_idx ON sentiment_logs (asset, published_at DESC);

CREATE TABLE analyst_output_cache (
    cache_id TEXT PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL,
    asset TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    opportunity_type TEXT NOT NULL,
    lifecycle_state TEXT,
    confidence_score NUMERIC,
    summary_text TEXT,
    input_hash TEXT,
    output_json JSONB NOT NULL,
    target_database TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending',
    delivered_at TIMESTAMPTZ
);

CREATE INDEX analyst_output_cache_asset_generated_idx ON analyst_output_cache (asset, generated_at DESC);
CREATE INDEX analyst_output_cache_agent_generated_idx ON analyst_output_cache (agent_name, generated_at DESC);
