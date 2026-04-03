# Draft Baseline Status

## Current Position

1. The project is past raw build.
2. The project is in draft-baseline review mode.
3. Parts `B`, `C`, and `E` are the weighted parts that have now been reviewed directly.
4. Current draft read: `B`, `C`, and `E` are all usable at the draft level without immediate additional weight changes.

## Draft-Stable Parts

### Part B: Liquidity

1. Status: `draft-stable`
2. Verification passed for:
3. `manual`
4. `mcp`
5. `no-source -> N/A`
6. Current draft conclusion:
7. `ltf` is more whale-sensitive by design.
8. `mtf` and `htf` correctly lean more on netflow and exchange-balance regime.
9. Strong bullish and bearish scenarios classify cleanly.
10. Conflict scenarios mostly stay neutral unless broader liquidity evidence is strong enough to override whale pressure.
11. No immediate Part B weight change is justified.

### Part C: Derivatives

1. Status: `draft-stable`
2. Working draft default: `profiled`
3. LS block: enabled
4. Current draft `ltf` weights:
5. `w_oi = 0.30`
6. `w_volume = 0.25`
7. `w_funding = 0.45`
8. `w_ls = 0.15`
9. `mtf` remains unchanged.
10. `htf` remains unchanged.
11. Current draft conclusion:
12. Part C is the weighted module where profile behavior matters most.
13. The `ltf` volume-dominance problem was corrected.
14. No new Part C weight change is justified from the latest pass.
15. Weak `htf` policy is now explicit:
16. baseline default = `na`
17. optional override = `downgrade_to_mtf`
18. honest live-review behavior should keep returning `N/A` by default when higher-timeframe data is genuinely weak.

### Part E: Liquidation Context

1. Status: `draft-stable`
2. Verification passed for:
3. `breakout_follow`
4. `fade_extreme`
5. `avoid`
6. `sweep_up_risk`
7. `sweep_down_risk`
8. `two_sided_chop`
9. Current draft conclusion:
10. Profile behavior is coherent.
11. `ltf` is correctly tighter around nearby liquidation magnets.
12. `mtf` and `htf` are correctly looser around the same setups.
13. No immediate Part E weight change is justified.

## Not Yet Locked Final

1. These parts are `draft-stable`, not permanently final.
2. Final lock should happen only after one more project-wide review against real trade-use expectations.
3. Unsupported symbols or unsupported data families should continue returning `N/A`, not hard failure, where practical.

## Current Recommended Baseline

1. Part B: keep current profiled weights
2. Part C: keep `profiled` default with LS enabled
3. Part C `ltf`: keep adjusted weights
4. Part C `mtf`: unchanged
5. Part C `htf`: unchanged
6. Part C weak-`htf` policy: keep baseline default on `na`
7. Part E: keep current profiled settings and thresholds

## Current Source Policy

1. Part A: `coinalyze`
2. Part B: `auto`
3. Part C: `auto`
4. Part D: `glassnode_mcp`
5. Part E: `glassnode_mcp`
6. Current fallback policy:
7. Part D: `none`
8. Part E: `none`
9. Honest missing-data policy:
10. return `N/A`
11. do not silently swap to fake/manual data during live review runs

## What Still Needs Decision

1. Whether to formally lock the current draft baseline as the default operating setup
2. Whether to update `timeframe_profiles.json` and runner defaults to reflect the current draft baseline more explicitly
3. Whether to do a real multi-part basket run next as the final draft review before lock

## Best Next Step

1. Run one clean project-wide review pass across the draft-stable baseline.
2. Compare outputs in actual tool usage terms, not just synthetic scenario terms.
3. If that looks coherent, lock the baseline and move toward integration-readiness.

## Updated Next Step

1. The project-wide review pass has been completed.
2. The next step is now `live-source integration readiness`.
3. Priority order:
4. make Part B easier to run in the live review path
5. make Part D easier to run in the live review path
6. make Part E easier to run in the live review path
7. keep the new Part C weak-`htf` policy explicit in the live path and baseline docs
8. Do not spend more time on weight tuning until this integration step is cleaner.
9. Progress update:
10. raw Glassnode MCP export files can now be passed directly into the runner for Part B, Part D, and Part E payload generation.
11. Part C now has an explicit weak-`htf` runtime policy and runner support.
12. A clean live rerun using raw Glassnode MCP inputs confirmed:
13. Part B now returns live readings in the baseline run.
14. Part D now returns live readings for supported heatmap-family symbols when raw MCP input is supplied.
15. Part E now returns live readings for supported heatmap-family symbols when raw MCP input is supplied.
16. Structure now returns live readings after moving off the Binance-only kline path.
17. Momentum now returns live readings after moving off the Binance-only kline/OI path.
18. Current remaining `N/A` behavior is mainly intentional:
19. unsupported heatmap-family symbols in Parts D and E
20. optional raw MCP dependency for the Glassnode-fed path
21. Progress update:
22. a draft interpretation layer now exists on top of the part outputs
23. it preserves separate part readings and adds:
24. `bias`
25. `environment`
26. `entry_posture`
27. `alignment_quality`
28. `setup_quality`
29. `candidate_rank`
30. `rank_type`
31. `action_status`
