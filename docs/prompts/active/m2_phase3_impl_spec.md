# M2 Phase 3 — implementation spec (§15.4 self-anchoring fades + step_within_section)

> Author: M2 orchestration session (Claude/Opus), 2026-06-15. Branch `m2-phase2-cues`.
> Builds on Phase 1/2a/2b. This is the RISKIEST phase: it modifies `govee_realtime_runner` (the 40fps
> live thread) and makes color fades + per-section color stepping live. Claude reviews adversarially.
> **DO NOT START until the weekly usage limit resets AND Phase 2b is reviewed/merged.**

## 0. Mission (§15.4 + §15.7 M2 tail)
1. A DEDICATED color-anchor clock in the runner so color-only changes can fade without a motion reset.
2. Thread `abs_pos` + the anchor into the colorize path; make the colorizer fade-aware (pure).
3. Turn on `step_within_section` (per-role) + `fade_beats_by_role` (config already carries both).

## 1. The §15.4 correction (read TWICE — the naive approach is WRONG)
`applied_abs_beat` is NOT retrievable today: the runner stores `_active_applied_monotonic` (a monotonic
*time*, ~`govee_realtime_runner.py:279`); `configure` consumes `abs_beat` and discards it. AND a
color-only change must NOT reach `configure` (it would reset motion). So **"configure time" is the wrong
fade anchor.** Resolution = a SEPARATE color-anchor clock (below).

## 2. Runner: two signatures (govee_realtime_runner.py)
- **Motion signature** = the existing `_signature` (~:404) with color/fade keys EXCLUDED:
  `{color, color2, color_a, color_b, color_from, color_to, fade_beats, gradient_stops, slot_colors}`.
  (NOTE color_a/color_b ARE excluded — M1 injects them into the two generic dual effects.) This gates
  `self._engine.configure` (motion reset). Color-only changes no longer reset motion.
- **Color signature** = ONLY those excluded keys. Maintain `self._color_signature`. When it changes,
  capture `self._color_applied_abs_beat = abs_pos` (the live abs beat at the moment the new color took
  effect). This is the fade anchor. Initialize to the first abs_pos seen; reset semantics in §5.
- `set_desired` already propagates new params each tick regardless of motion signature (~:89-91, read
  ~:233), so color updates render every tick without a motion reconfigure — keep that.

## 3. Plumb abs_pos + anchor into the colorize path
`_tick_once` computes `abs_pos` and calls `frame = self._compose_frame(spec, instances)` (~:306).
- Pass `abs_pos` and `self._color_applied_abs_beat` into `_compose_frame` (~:318) and on into BOTH
  `render(...)` and `render_comet(...)` (the two branches at ~:330 and ~:342).
- `render`/`render_comet`/`universal_colorizer` gain optional `abs_pos`/`color_applied_abs_beat` kwargs;
  when absent (Phase 1/2 callers, tests) behavior is unchanged (no fade). The colorizer stays PURE — it
  receives the two scalars as inputs; the runner owns the tiny capture state.

## 4. Fade-aware colorizer (pure)
When `decision.params` carries `color_from`/`color_to`/`fade_beats` (slot variant: `slot_colors_from`/
`slot_colors_to`), the colorizer computes `t = clamp((abs_pos - color_applied_abs_beat)/fade_beats, 0, 1)`
and lerps each (slot) color `from→to` by `t` (plain RGB lerp via `_clamp_channel`, orange pass-through OK
per A6) BEFORE the existing `Σ slot_color·intensity`. `fade_beats<=0` ⇒ instant (t=1) ⇒ identical to
Phase 2 (drops snap; low-energy roles fade). No absolute `fade_start_beat` is ever stamped (avoids
cross-component frame mismatch).

## 5. Engine: emit fade params + previous-color tracking (led_color_engine.py)
- The engine must remember the PREVIOUS resolved color/slot_colors (per role or per section) to emit
  `color_from` (previous) + `color_to` (new) + `fade_beats` (= `fade_beats_by_role[role]`, default 0).
  Keep this PURE-by-value: the engine computes both endpoints; the colorizer interpolates.
- `step_within_section`: already wired in `resolve_color`/`resolve_slot_colors` via
  `step_index = cycle if use_step else 0`. Turning a role TRUE makes color re-roll each cycle; the fade
  then smooths the re-roll. Drops stay step=False/fade=0 (snap).
- **gap #2 — every transition path:** define where `_color_applied_abs_beat` and the engine's
  previous-color memory reset (new audible track? role change? section change?). A stale anchor =
  a fade that never completes or starts mid-way. Enumerate: track change resets memory; a new color
  signature re-stamps the anchor; effect (motion) change does NOT by itself reset the color anchor.

## 6. Coordinator cadence (do not fight WI-3)
The coordinator's WI-3 min-dwell gate (`led_dispatch_coordinator.py:74-87`, 1.5s) suppresses same-role
re-dispatch. Discrete `step_within_section` re-rolls ride on `role_key`'s `:c{cycle}` (≥32-beat cadence
≫ 1.5s) so they are NOT suppressed; fades do not re-dispatch at all (single trigger, colorizer-
interpolated). Keep any step cadence > `min_look_dwell_s`.

## 7. Tests (§15.7 M2 acceptance)
- **Fade determinism:** for fixed (color_from, color_to, fade_beats, anchor), the colorizer output at a
  given abs_pos is exact and monotonic from→to across the interval; t clamps at the ends.
- **fade_beats=0 ⇒ instant**, byte-identical to Phase 2 (no-fade) output.
- **Dual-signature:** a color-only param change does NOT trigger `configure` (motion not reset); a motion
  param change does. Assert via a spy/counter on configure.
- **Anchor capture:** changing the color signature stamps `_color_applied_abs_beat = abs_pos`; verify the
  reset-path matrix from §5.
- **step_within_section:** with a role TRUE, color varies per cycle (different `step_index`); with FALSE,
  holds (M1 behavior). Determinism preserved for fixed seed.
- **enabled:false / no fades configured ⇒ byte-identical** to Phase 2.

## 8. Verify + report
LED suites + whole suite green (baseline ~1658 + Phase 2b additions; 3 pre-existing test_led_config
failures). Confirm: motion bit-exactness preserved when no fade; colorizer still pure; 40fps path has no
new per-frame allocation/locking regressions; nothing committed. Call out any §15.4 ambiguity. Recommend
a live dry-run watch (color-inject + no stutter) before enabling fades on the rig.
```
```
