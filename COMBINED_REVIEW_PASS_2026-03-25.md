# Combined Review Pass - 2026-03-25

## Basket

1. `BTC`
2. `LINK`
3. `XRP`
4. `HYPE`
5. `SOL`
6. `PUMP`

## Profiles Reviewed

1. `ltf`
2. `mtf`
3. `htf`

## Reference Runs

1. `runs/20260325_015825_ltf/summary.json`
2. `runs/20260325_015914_mtf/summary.json`
3. `runs/20260325_020040_htf/summary.json`

## Baseline Conditions

1. `WeightMode = profiled`
2. `PartCWeakHtfPolicy = na`
3. `Part B` raw Glassnode MCP input supplied
4. `Part D` raw Glassnode MCP input supplied by reuse of the `Part E` raw file
5. `Part E` raw Glassnode MCP input supplied

## Project-Wide Read

1. `Part B` stayed `neutral` across all three profiles.
2. `Part C` is the main directional driver in the current system.
3. `Part D` and `Part E` add useful liquidation-side context for supported heatmap-family symbols.
4. `Structure` currently reads as `Range / Mean Revert` across the whole basket.
5. `Momentum` is mostly `neutral`, with only `BTC ltf` reaching clear `bearish / Avoid`.
6. Current system behavior is coherent, but interpretation is still module-by-module rather than fused into one final trading readout.

## Part B

1. `ltf`: `neutral`
2. `mtf`: `neutral`
3. `htf`: `neutral`
4. Reason stayed effectively the same in all profiles:
5. `net=82008610 out/in=0.60 bal_regime=0.33 whale=20038478`
6. Current interpretation:
7. liquidity backdrop is not giving a strong directional edge right now
8. Part B is acting as a stabilizer, not a signal leader

## Part C

### LTF

1. `HYPE`: `bullish`
2. `SOL`: `bearish`
3. `BTC`, `LINK`, `XRP`, `PUMP`: `neutral`
4. Current interpretation:
5. short-term derivatives are mixed, not broad-market aligned
6. LTF is selective, not one-way

### MTF

1. `PUMP`: `bullish`
2. `BTC`, `HYPE`, `SOL`, `XRP`: `bearish`
3. `LINK`: `neutral`
4. Current interpretation:
5. medium timeframe derivatives are the most clearly risk-off layer in this pass
6. strongest negative pressure sits on `BTC`, `HYPE`, and `SOL`

### HTF

1. `XRP`: `bearish`
2. `BTC`, `LINK`, `HYPE`, `SOL`, `PUMP`: `neutral`
3. Current interpretation:
4. higher timeframe derivatives are mostly flat to soft, not broadly supportive
5. only `XRP` keeps a clean bearish higher-timeframe read here

## Part D

Supported symbols only:

1. `BTC`: `bearish_watch`
2. `SOL`: `bearish_watch`
3. `XRP`: `bullish_watch`
4. `LINK`, `HYPE`, `PUMP`: unsupported heatmap family -> intentional `N/A`

Current interpretation:

1. `BTC` and `SOL` have liquidation-event pressure favoring downside risk / short-side dominance
2. `XRP` has liquidation-event pressure favoring upside squeeze risk
3. Part D is now adding useful event-state context, not placeholder values

## Part E

Supported symbols only:

1. `BTC`: `pullback_wait`, `sweep_up_risk`
2. `SOL`: `pullback_wait`, `sweep_down_risk`
3. `XRP`: `pullback_wait`, `sweep_up_risk`
4. `LINK`, `HYPE`, `PUMP`: unsupported heatmap family -> intentional `N/A`

Current interpretation:

1. supported coins are not in clean breakout-follow mode right now
2. all supported names are saying `pullback_wait`
3. `BTC` and `XRP` show upside sweep risk
4. `SOL` shows downside sweep risk

## Structure

1. Entire basket came back `Range`
2. Entire basket bias came back `Mean Revert`
3. Current interpretation:
4. structure does not support trend-chasing right now
5. chart backdrop is mostly range behavior, not confirmed trend continuation

## Momentum

### LTF

1. `BTC`: `bearish`, bias `Avoid`
2. all others: `neutral`, bias `Mean Revert`

### MTF

1. all six: `neutral`, bias `Mean Revert`

### HTF

1. all six: `neutral`, bias `Mean Revert`

Current interpretation:

1. momentum is not broadly trending in favor of aggressive continuation entries
2. the only clear warning signal here is `BTC ltf`

## Practical Read By Symbol

### BTC

1. `Part C`: neutral -> bearish -> neutral
2. `Part D`: bearish_watch
3. `Part E`: pullback_wait + sweep_up_risk
4. `Structure`: Range / Mean Revert
5. `Momentum`: bearish on `ltf`, neutral after that
6. Current read: noisy, conflict-heavy, not a clean continuation long; more caution than conviction

### LINK

1. `Part C`: neutral -> neutral -> neutral
2. `Part D/E`: unsupported for heatmap family
3. `Structure`: Range / Mean Revert
4. `Momentum`: neutral across all profiles
5. Current read: low-conviction, low-information name in this pass

### XRP

1. `Part C`: neutral -> bearish -> bearish
2. `Part D`: bullish_watch
3. `Part E`: pullback_wait + sweep_up_risk
4. `Structure`: Range / Mean Revert
5. `Momentum`: neutral across profiles
6. Current read: derivatives lean bearish, but liquidation context still says upside squeeze risk; strong conflict, so not clean

### HYPE

1. `Part C`: bullish -> bearish -> neutral
2. `Part D/E`: unsupported for heatmap family
3. `Structure`: Range / Mean Revert
4. `Momentum`: neutral across profiles
5. Current read: unstable and timeframe-dependent; not clean enough yet

### SOL

1. `Part C`: bearish -> bearish -> neutral
2. `Part D`: bearish_watch
3. `Part E`: pullback_wait + sweep_down_risk
4. `Structure`: Range / Mean Revert
5. `Momentum`: neutral across profiles
6. Current read: one of the cleaner bearish-leaning names in the pass, but still not a trend-confirmation environment

### PUMP

1. `Part C`: neutral -> bullish -> neutral
2. `Part D/E`: unsupported for heatmap family
3. `Structure`: Range / Mean Revert
4. `Momentum`: neutral across profiles
5. Current read: selective MTF strength only; not enough supporting agreement elsewhere

## Draft Conclusion

1. The baseline is now operational and informative.
2. The tool is producing usable module-level reads across the basket.
3. The current market read from this pass is mostly:
4. `range / mean-revert backdrop`
5. `mixed-to-bearish derivatives pressure`
6. `selective liquidation-side asymmetry on supported symbols`
7. This is not yet a fused final trading-decision layer.
8. The next project step should focus on how to combine module outputs into one practical review/output framework.

## Recommended Next Step

1. Define the final combined readout layer.
2. Decide how `Part B`, `Part C`, `Part D`, `Part E`, `Structure`, and `Momentum` should combine into:
3. `trade bias`
4. `entry style`
5. `avoid / watch / active` status
6. `best aligned coins`
