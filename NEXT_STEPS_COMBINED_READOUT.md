# Next Steps - Combined Readout Layer

## Purpose

1. The infrastructure and module baselines are now usable.
2. The next phase is not more source plumbing.
3. The next phase is to define how the separate parts combine into one practical trading readout.

## The 6 Next Steps

1. Define `trade bias`
2. Define `entry style`
3. Define `avoid / watch / active`
4. Define `best aligned coins`
5. Define the parts separately before combining them
6. Build the final combined readout layer after the separate definitions are locked

## Parts Defined Separately

### Part B: Liquidity

1. What it measures:
2. exchange flow / exchange balance / whale-to-exchange pressure
3. What it should contribute to the final readout:
4. background liquidity bias
5. whether flows support bullish, bearish, or neutral conditions
6. Whether it is a trigger part:
7. no
8. Current role:
9. context / backdrop part

### Part C: Derivatives

1. What it measures:
2. open interest change
3. perp volume change
4. funding
5. long/short pressure block
6. What it should contribute to the final readout:
7. main directional pressure
8. whether derivative positioning is supporting or fighting the move
9. Whether it is a trigger part:
10. partially
11. Current role:
12. primary directional part

### Part D: Liquidation Positioning / Event State

1. What it measures:
2. liquidation heatmap net
3. total liquidation volume
4. long vs short liquidation split
5. What it should contribute to the final readout:
6. event pressure
7. squeeze / flush / chop context
8. whether one side of the market is more vulnerable right now
9. Whether it is a trigger part:
10. yes, but only as event-state confirmation
11. Current role:
12. event-state part

### Part E: Liquidation Context / POI Mapping

1. What it measures:
2. liquidation cluster location
3. entry-position heatmap location
4. sweep risk around price
5. What it should contribute to the final readout:
6. where important POIs are on the chart
7. whether the coin is in breakout-follow, pullback-wait, fade-extreme, or avoid conditions
8. Whether it is a trigger part:
9. yes
10. Current role:
11. entry-context / POI part

### Structure

1. What it measures:
2. trend vs range context
3. break status
4. moving-average and slope context
5. volatility behavior
6. What it should contribute to the final readout:
7. whether the chart environment is trend-following or mean-reverting
8. whether continuation entries are structurally supported
9. Whether it is a trigger part:
10. no
11. Current role:
12. market-structure filter

### Momentum

1. What it measures:
2. short impulse strength
3. price + OI interaction
4. spot/perp volume expansion context
5. What it should contribute to the final readout:
6. whether the move has actual energy behind it
7. whether momentum confirms or weakens the setup
8. Whether it is a trigger part:
9. partially
10. Current role:
11. impulse confirmation filter

## What Needs To Be Defined Next

### 1. Trade Bias

1. Decide how each part contributes to:
2. `bullish`
3. `bearish`
4. `neutral`

### 2. Entry Style

1. Decide how the parts map into:
2. `breakout`
3. `pullback`
4. `mean reversion`
5. `no trade`

### 3. Avoid / Watch / Active

1. Decide what conditions mean:
2. `avoid`
3. `watch`
4. `active`

### 4. Best Aligned Coins

1. Decide what agreement level between parts is required
2. Define how to rank the cleanest setups in the basket

### 5. Separate-Part Rules

1. Lock the role of each part before combining them
2. Avoid letting one noisy part dominate the whole system without intent

### 6. Final Combined Readout Layer

1. After the separate-part rules are clear:
2. build the final combined review output
3. return one practical read per coin

## Correct Order

1. define the role of each part separately
2. define the output classes
3. define how the parts combine
4. then build the final combined readout layer
