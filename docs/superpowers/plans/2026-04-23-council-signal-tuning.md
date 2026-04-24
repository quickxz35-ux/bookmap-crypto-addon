# Council Signal Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the upstream analysts produce usable trade signals even when derivatives data is sparse, so `council-analyst` stops defaulting to `wait` on empty windows.

**Architecture:** Keep the current worker pipeline intact. Fix the weakest upstream workers first by removing hard early returns that drop wallet/whale/sentiment context when derivatives snapshots are missing. Preserve conservative council thresholds for now, then verify that richer upstream rows flow through Black Box into council and the decision router.

**Tech Stack:** Python, pandas, Railway Postgres, Black Box cache tables, existing worker smoke check helper.

---

### Task 1: Keep `analyst-scalping` emitting a real row when derivatives are missing

**Files:**
- Modify: `analyst_scalping.py`
- Test: `python -m py_compile analyst_scalping.py`

- [ ] **Step 1: Remove the empty-derivatives early return**

Current behavior:

```python
if deriv.empty:
    result["notes"].append("Insufficient derivatives snapshots for a scalp read.")
    self.reader.cache_output(...)
    return result
```

Replace it with a fallback path that still:
- keeps `status = "new"`
- keeps `direction = "neutral"`
- keeps `setup_type = "no_setup"`
- records wallet and whale support if either source exists
- writes the row to `analyst_output_cache` instead of exiting immediately

- [ ] **Step 2: Preserve a low-confidence scalp row with fallback evidence**

When `deriv.empty` is true:
- append a note that derivatives are missing
- if `whales` is non-empty, set `support["whales"] = "supportive"` and add confidence
- if `wallet_tx` is non-empty, set `support["wallets"] = "supportive"` and add confidence
- keep the final confidence in the low range unless at least one real derivatives snapshot exists

- [ ] **Step 3: Compile the file**

Run:

```bash
python -m py_compile analyst_scalping.py
```

Expected:
- no syntax errors

### Task 2: Keep `analyst-long-term` emitting a real row when derivatives are missing

**Files:**
- Modify: `analyst_long_term.py`
- Test: `python -m py_compile analyst_long_term.py`

- [ ] **Step 1: Remove the empty-derivatives early return**

Current behavior:

```python
if deriv.empty:
    result["notes"].append("No derivatives history yet for long-term review.")
    self.reader.cache_output(...)
    return result
```

Replace it with a fallback path that still:
- keeps `status = "watch"`
- keeps `bias = "neutral"`
- keeps `regime = "range"`
- records whale, wallet, and sentiment support if present
- writes the row to `analyst_output_cache`

- [ ] **Step 2: Let non-derivatives evidence contribute**

When `deriv.empty` is true:
- if `whales` exists, mark whale support and add conviction
- if `wallet_tx` has enough rows, mark wallet support and add conviction
- if sentiment is positive, mark narrative support and add conviction
- append a note that the analyst is operating in fallback mode, not silence

- [ ] **Step 3: Compile the file**

Run:

```bash
python -m py_compile analyst_long_term.py
```

Expected:
- no syntax errors

### Task 3: Verify the council now has upstream material to score

**Files:**
- Modify: `workspace_worker_audit.py` if needed
- Inspect: `council_analyst.py`
- Inspect: `decision_router.py`

- [ ] **Step 1: Confirm the latest rows are no longer empty**

Check the latest worker outputs and make sure `scalp` and `long_term` rows now exist even when derivatives are sparse.

- [ ] **Step 2: Confirm council receives those rows**

Check that `council-analyst` can see the new outputs in its recent analyst window and that it stops reporting only `wait | confidence=0.0 | top coin=n/a`.

- [ ] **Step 3: Validate the handoff**

Run the existing smoke/compile checks and then confirm the decision router still accepts:
- `scalp`
- `long_term`
- `council_thesis`
- `trade_candidate`

Expected:
- the upstream analysts are no longer silent
- council has enough evidence to emit meaningful non-wait decisions when the market supports them

