# Status Report 2026-03-26

## Project State

1. The core crypto tool is operational.
2. The combined readout layer is operational.
3. The review workflow is operational.
4. The screener is operational.
5. The local dashboard is operational.

## Core Modules

1. `Part B: Liquidity` is built and integrated.
2. `Part C: Derivatives` is built and integrated.
3. `Structure` is built and integrated.
4. `Momentum` is built and integrated.
5. `Part D/Part E` live-source paths are usable in the wider tool where supported.

## Combined Readout

1. Separate part readings are preserved.
2. The interpretation layer returns:
   - `bias`
   - `environment`
   - `entry_posture`
   - `alignment_quality`
   - `setup_quality`
   - `candidate_rank`
   - `rank_type`
   - `action_status`

## Screener

1. The screener supports configurable stage order.
2. Active stage set:
   - `part_c`
   - `momentum`
   - `structure`
   - `part_b`
   - `none`

3. The screener supports runtime controls:
   - preset
   - profile
   - basket/custom symbols
   - side filter
   - max final survivors
   - neutral inclusion

4. Working screener presets:
   - `balanced`
   - `trend_strict`
   - `mean_reversion_scalp`

5. Final screener candidates now carry:
   - `side`
   - `display_score`
   - `display_score_bar`
   - `final_rank_score`
   - `final_rank_bar`

## Dashboard

1. The local dashboard can run the screener from the UI.
2. The dashboard can load saved runs.
3. The dashboard shows:
   - final candidates
   - stage waterfall
   - detailed pass/drop reasons

4. The dashboard run flow is non-blocking.
5. Larger basket runs now work from the dashboard.

## Speed Improvements

1. The screener no longer runs twice per snapshot.
2. Markdown reports are now rendered from saved JSON instead of triggering a second full screener run.
3. Large-basket dashboard runs are materially faster than before.

## Locked Profile Roles

1. `MTF`
2. primary screener profile
3. main shortlist generator

4. `LTF`
5. execution refinement profile
6. useful after `MTF`, not as the main discovery layer

7. `HTF`
8. high-conviction bias / context confirmation
9. useful for scalping because it confirms or challenges the larger directional backdrop
10. not swing-only

## Current Operational Routine

1. Run `MTF` first to generate the main shortlist.
2. Use `HTF` to confirm or challenge that shortlist.
3. Use `LTF` only for execution refinement.
4. Use TradingView for chart review.
5. Use Bookmap for actual entry confirmation.

## What Is Finished Enough To Use

1. The screener is finished enough for real live use.
2. The dashboard is finished enough for real local use.
3. The current workflow is finished enough to start building a repeatable trading process around it.

## What Still Needs Building

1. A more guided dashboard workflow around the trading routine.
2. Better session-oriented views:
   - `MTF shortlist`
   - `HTF confirmation`
   - `LTF execution queue`

3. Better candidate comparison tools inside the dashboard.
4. Later:
   - automation
   - persistent data/cache layer
   - hosted deployment if needed

## Recommended Next Build Phase

1. Build the dashboard around the pinned trading routine.
2. Make the UI support this exact flow:
   - generate `MTF` shortlist
   - check `HTF` agreement
   - promote names into an `LTF` execution queue
   - mark which names are still active/watch/skip

## Current Conclusion

1. The project is no longer in raw construction mode.
2. The project is now in operational workflow build mode.
3. The next work should focus on making the dashboard support the actual trading routine, not on rebuilding the screener core.
