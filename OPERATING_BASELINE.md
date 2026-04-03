# Operating Baseline

## Status

1. This file records the current `draft operating baseline`.
2. It is the baseline we should use for normal project review runs unless we explicitly change it.
3. It is not the same as a permanently final baseline.

## Locked Draft Defaults

1. Weight mode default: `profiled`
2. Part C weak-`htf` policy default: `na`
3. Main test basket:
4. `BTC`
5. `LINK`
6. `XRP`
7. `HYPE`
8. `SOL`
9. `PUMP`

## Source Defaults

1. Part A: `coinalyze`
2. Part B: `auto`
3. Part C: `auto`
4. Part D: `glassnode_mcp`
5. Part E: `glassnode_mcp`
6. Part D fallback: `none`
7. Part E fallback: `none`

## Part Defaults

### Part B

1. Keep current profiled weights.
2. Keep honest missing-data behavior:
3. return structured `N/A`
4. do not hard-fail whole-run output

### Part C

1. Keep `profiled` as the default.
2. Keep LS enabled.
3. Keep current draft `ltf` weights:
4. `w_oi = 0.30`
5. `w_volume = 0.25`
6. `w_funding = 0.45`
7. `w_ls = 0.15`
8. Keep `mtf` unchanged.
9. Keep `htf` unchanged.
10. Keep weak-`htf` default policy on `na`.
11. Keep `downgrade_to_mtf` available only as an explicit override.

### Part E

1. Keep current profiled settings and thresholds.
2. Supported heatmap-family symbols should return live readings when raw Glassnode MCP input is provided.
3. Unsupported heatmap-family symbols should return `N/A`.

## Current Live-Read Expectations

1. Part B: live
2. Part C: live
3. Part D: live for supported heatmap-family symbols when raw Glassnode MCP input is supplied
4. Part E: live for supported heatmap-family symbols when raw MCP input is supplied
5. Structure: live
6. Momentum: live

## Intentional `N/A` Cases

1. Unsupported heatmap-family symbols in Parts D and E:
2. `LINK`
3. `HYPE`
4. `PUMP`
5. Missing raw Glassnode MCP input for Parts B, D, and E when those paths are required

## Current Runner Inputs That Matter

1. `-WeightMode profiled`
2. `-PartCWeakHtfPolicy na`
3. `-PartBRawMcpInputFile <raw-json>`
4. `-PartDRawMcpInputFile <raw-json>`
5. `-PartERawMcpInputFile <raw-json>`
6. `-GlassnodeLiquidityRawInputFile <raw-json>`
7. `-GlassnodeHeatmapRawInputFile <raw-json>`
8. If `-PartDRawMcpInputFile` is omitted and `-PartERawMcpInputFile` is supplied, the runner can reuse the Part E raw file to build the Part D payload.
9. If `-GlassnodeHeatmapRawInputFile` is supplied, it can feed both Part D and Part E automatically unless explicit per-part raw paths are provided.
10. The runner now also writes `combined_readout.json` for each run.
11. The runner now also writes:
9. `review_report.json`
10. `review_report.md`

## Current Combined Readout Defaults

1. Bias model:
2. `Part B = 0.35`
3. `Part C = 0.45`
4. `Structure = 0.10`
5. `Momentum = 0.05`
6. `Part E event = 0.05`
7. Environment model:
8. `Structure` sets the base environment
9. `Part E event` only modifies it
10. `Range / Mean Revert` remains `range`
11. Entry posture model:
12. `pullback_wait -> wait` by default
13. Setup quality:
14. separate from `alignment_quality`
15. Candidate rank:
16. present on every combined readout
17. Rank type:
18. current weak-basket outputs should show `watchlist_rank`, not `trade_rank`
19. Current weak-basket ranking behavior:
20. stronger penalty for missing `Part E` context
21. supported heatmap-family names should sort above unsupported ones when the basket is broadly weak
22. Final status rule:
23. `active` requires:
24. clear bias
25. medium/high setup quality
26. `trade_rank`
27. non-`wait` posture
28. no missing critical `Part E` context
29. otherwise the coin stays `watch`

## Current Review Output Baseline

1. The first review-style output layer is now live through `review_report.py`.
2. It reads `combined_readout.json` and emits:
3. `review_report.json`
4. `review_report.md`
5. Current default review settings in the runner:
6. `mode = custom_coin_mode`
7. `side_filter = both`
8. `status_filter = all`
9. `result_limit = 25`
10. `include_neutral = false`
11. Bullish names print first, bearish names second, and neutral/conflicted names stay hidden unless explicitly requested.
12. The review output shows:
13. quick review rows
14. alignment/setup bars
15. expanded part-by-part details
16. missing/unsupported context
17. Default-basket mode now loads symbols from `review_baskets.json` when `-ReviewMode default_basket_mode` is used without `-Symbols`.
18. Part A now degrades gracefully on provider errors such as Coinalyze `429`; larger basket runs should return structured per-symbol errors instead of crashing the whole run.

## Reference Runs

1. `runs/20260325_013834_ltf/summary.json`
2. `runs/20260325_015201_mtf/summary.json`
3. `runs/20260325_013834_htf/summary.json`

## Next Decision Layer

1. Use this baseline in real review work.
2. Observe where it behaves well or poorly.
3. Decide later whether to promote this `draft operating baseline` into a fully final baseline.
