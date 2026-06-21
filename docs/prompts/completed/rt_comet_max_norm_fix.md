# Implementer Prompt: Comet Max-Normalization Fix

**Agent**: Opus
**Context**: The operator explicitly **rejected** the exponential tail approach detailed in `docs/plans/active/rt_comet_smoothness_fix_spec.md`. Do not implement the exponential tail math. The operator prefers the exact original geometry/size of the comet (`width=0.8` dot).

**The Bug**:
Currently, the tiny comet (`width=0.8`) visibly "throbs" (pulses bright to dim to bright) as it travels across the LED strip. This is because `_comet_frame` in `govee_frame_renderer.py` uses `sum()` normalization:
```python
    total_head = sum(weight for _, weight in head_weights)
    if total_head > 0.0:
        for idx, weight in head_weights:
            amount = weight / total_head
```
When the comet sits exactly between two LEDs, the weight is split 50/50. Because human perception of brightness is non-linear, two LEDs at 50% brightness appear noticeably dimmer than one LED at 100%. This drop in peak brightness causes the throbbing.

**The Fix**:
Change the normalization logic in `_comet_frame` from sum-normalization to max-normalization. This forces the brightest LED in the comet's footprint to always reach exactly 100% (255), completely eliminating the throb while perfectly maintaining the intended size and shape of the comet.

## Task 1: Update `_comet_frame`
In `govee_frame_renderer.py`, modify `_comet_frame`:
```python
    # REPLACE THIS:
    # total_head = sum(weight for _, weight in head_weights)
    # if total_head > 0.0:
    #     for idx, weight in head_weights:
    #         amount = weight / total_head
    
    # WITH THIS:
    if head_weights:
        max_weight = max(weight for _, weight in head_weights)
        if max_weight > 0.0:
            for idx, weight in head_weights:
                amount = weight / max_weight
                acc[idx][0] += color[0] * amount
                acc[idx][1] += color[1] * amount
                acc[idx][2] += color[2] * amount
```

## Task 2: Update Tests
In `tests/test_govee_frame_renderer.py`, the test `test_comet_default_stays_compact` currently asserts the specific peak values of the old math. You will likely need to adjust the assertions to reflect that the peak pixel is now always fully saturated (1.0 weight) rather than divided. Run `python3 -m unittest discover tests` and fix any broken assertions related to `render_comet` peak brightness.

**Do not change `COMET_MIN_HEAD_SOFT` or add exponential tails.** Just implement the max-normalization fix, verify tests, and report back to the operator.
