# M2 Phase 3 — implementation spec (§15.4 self-anchoring fades + step_within_section)

## ⛔ GEMINI SCOPE LOCK (read this + the REVIEWER PATCHES below before the body)
> Read `m2_continuation_handoff.md` FIRST. **Do NOT start Phase 3 until Phase 2b is implemented, reviewed,
> and the suite is green.** The REVIEWER PATCHES block (below) OVERRIDES the body. This edits the 40fps
> render thread — **if you cannot guarantee an invariant below, STOP and report. Never guess.**

- **GOAL:** deterministic color fades + per-section color stepping, with **NO motion reset** on color-only
  changes.
- **NON-GOALS (do NOT do):** do not change chase/comet/breathing motion geometry; do not call
  `BeatSyncEngine.configure` on color-only changes; do not reset motion on color changes; do not enable
  nonzero fades in live config in the same patch (that is Patch 2, gated); do not touch baked sand,
  cloud/DIY, laser, RB, or SoundSwitch.
- **MANDATORY TWO-PATCH SPLIT:** Patch 1 = code + tests, `fade_beats` stays 0 in config (inert). Patch 2 =
  nonzero `fade_beats_by_role`/`step_within_section` activation — ONLY after a rig dry-run + operator
  sign-off. Ship them separately.
- **EXACT FILES THAT MAY CHANGE (Patch 1) — see ROUND-2 PATCH 8:** `govee_realtime_runner.py` (motion/
  color signature split via key-filter in `_signature`; anchor capture; call `resolve_fade` in
  `_compose_frame` at BOTH call sites :252/:306), `govee_frame_renderer.py` (add ONE pure helper
  `resolve_fade(params, abs_pos, anchor_beat)` next to `_lerp`/`_color` — do NOT change `render_comet`,
  `_comet_frame`, or `universal_colorizer` signatures), `led_color_engine.py` (emit
  `color_from`/`color_to`/`fade_beats` + slot variants + previous-color memory), NEW test file. Nothing
  else.
- **PARTITION (exact):** motion signature = everything EXCEPT the 11 color keys; color signature = EXACTLY
  `{color, color2, color_a, color_b, color_from, color_to, fade_beats, gradient_stops, slot_colors,
  slot_colors_from, slot_colors_to}`. They must partition cleanly. Only motion-signature changes call
  `configure` (`_signature` at `govee_realtime_runner.py:403`).
- **PREVIOUS-COLOR MEMORY KEY (exact):** `(track_key, role, section_id, look_name, color_shape)` —
  `cycle` EXCLUDED (so consecutive cycles chain target→target). `color_shape ∈ {color, color_a/color_b,
  slot_colors}`. A smaller key ONLY with tests proving no cross-look contamination.
- **RESET MATRIX (exact):** reset `_color_signature` + `_color_applied_abs_beat` + engine previous-color
  memory on: `_idle_tick` deactivation (`:368`), `_emergency_teardown` (`:389`), `force_deactivate`
  (`:117`), `stop` (`:153`), new audible track, and color-SHAPE change. NOT on mere motion/effect change.
- **DETERMINISM:** `t = clamp((abs_pos - color_applied_abs_beat)/fade_beats, 0, 1)`; `fade_beats<=0` ⇒ t=1
  (instant, byte-identical to Phase 2). `step_within_section` uses `step_index = cycle` (already wired) —
  NO wall-clock randomness. `fade_beats_by_role[role]` MUST be < the role's re-dispatch cadence (≥32-beat
  sections ≫ fade 2-4) so no fade is interrupted mid-flight; assert this at the boundary.
- **TESTS:** color-only change does NOT call `configure`; motion change DOES; `slot_colors_from/to`
  excluded from motion signature; `fade_beats=0` and `enabled:false` byte-identical; deterministic
  interpolation; full reset matrix; `step_within_section` deterministic progression; no motion reset on
  color-only change. Targeted + full suite (baseline 1661 + Phase 2b additions).
- **REPORT:** per handoff §5.

> Author: M2 orchestration session (Claude/Opus), 2026-06-15. Branch `m2-phase2-cues`.
> Builds on Phase 1/2a/2b. This is the RISKIEST phase: it modifies `govee_realtime_runner` (the 40fps
> live thread) and makes color fades + per-section color stepping live. Claude reviews adversarially.
> **DO NOT START until the weekly usage limit resets AND Phase 2b is reviewed/merged.**

## REVIEWER PATCHES — APPLY THESE BEFORE IMPLEMENTING (Claude review, 2026-06-15, grounded vs merge/main 214e206)
These supersede the body where they conflict. Code citations verified against the merged tree.
1. **Motion-signature exclusion in §2 is INCOMPLETE.** §4 introduces the slot fade endpoints
   `slot_colors_from`/`slot_colors_to`, but §2's exclusion list omits them — so a slot-color fade would
   change `_signature` and reset motion every endpoint change. Exclude ALL of, and the COLOR signature is
   EXACTLY this set: `{color, color2, color_a, color_b, color_from, color_to, fade_beats, gradient_stops,
   slot_colors, slot_colors_from, slot_colors_to}` (11 keys). The two signatures must partition cleanly:
   motion = everything NOT in this set; color = exactly this set.
2. **Previous-color memory key (§5) must be exact, not "per role or per section."** Use
   `(track_key, role, section_id, look_name, color_shape)` — and DELIBERATELY exclude `cycle` so
   consecutive cycles share the key and the previous cycle's color is available as `color_from`. Include
   `look_name` + `color_shape` to prevent cross-look contamination (two looks in the same role/section
   must not feed each other's `color_from`). A smaller key is allowed ONLY with tests proving no
   cross-look contamination. `color_shape` ∈ {single `color`, dual `color_a/color_b`, `slot_colors`}.
3. **Reset matrix (§5) must be enumerated exactly.** Reset BOTH `_color_signature` and
   `_color_applied_abs_beat` (and the engine's previous-color memory) on: idle deactivation
   (`_idle_tick` ~:368-385), emergency teardown (`_emergency_teardown` ~:389-401), force_deactivate /
   cloud-fallback transition (`force_deactivate` ~:117-139), runner stop/shutdown (`stop` ~:153-161),
   new audible track (engine memory reset; runner re-stamps via color-signature change), and color-shape
   change. Do NOT reset merely because effect/motion changes — only if the color SHAPE changes. A new
   color signature stamps a fresh `_color_applied_abs_beat = abs_pos`.
4. **Fade must complete before the next color resolves.** The engine emits `color_from` = the PREVIOUS
   resolved color (the previous TARGET/`color_to`), so fades chain target->target. This is only correct
   when `fade_beats` < the step/section re-roll cadence. Enforce: `fade_beats_by_role[role]` must be less
   than the role's re-dispatch cadence (≥32-beat sections ≫ fade 2-4) so no fade is interrupted mid-flight
   by a new endpoint. State this invariant and add a test at the boundary.
5. **Keep BeatSyncEngine ownership clean (already in §2/§5, reaffirmed).** Color params are render-owned;
   they update via the latest `spec.params` each tick (`set_desired`/`_tick_once` read at ~:233-234) WITHOUT
   calling `BeatSyncEngine.configure`. Only motion-signature changes call `configure` (~:281).
6. **Two-patch split is MANDATORY (reaffirm §8).** Patch 1 = code support + tests, fades stay 0 in live
   config. Patch 2 = nonzero `fade_beats_by_role` / `step_within_section` activation, ONLY after a dry-run
   watch + operator sign-off. Do not ship both in one change.
7. **Stale baseline.** "~1658 + Phase 2b additions; 3 pre-existing test_led_config failures" is stale.
   Pre-Phase-3 merged baseline: **1661 passed, 3 skipped, 1 xfailed, 0 failed**; `test_led_config.py`
   passes clean. Use that + Phase 2b's additions as the regression baseline.

## REVIEWER PATCHES — ROUND 2 (Opus 4.8, 2026-06-16, grounded vs `main` function bodies)
These are DECISIVE and supersede §3/§4, the body, AND the GEMINI SCOPE LOCK where they conflict.
8. **🔴 `render_comet` does NOT use the colorizer — resolve fades into `params`, do NOT thread abs_pos
   into the colorizer.** Verified: `render_comet` (`govee_frame_renderer.py:1416`) builds one
   `color = _color(safe.get("color"), …)` and calls `_comet_frame(...)`; it never calls
   `universal_colorizer`. So the "colorizer interpolates the fade" plan (§3/§4) would NOT fade comet looks
   (`groove_chase_*`). REPLACEMENT PLAN: add ONE pure helper `resolve_fade(params, abs_pos, anchor_beat)
   -> params'` that, when `*_from`/`*_to`/`fade_beats` are present, computes
   `t = clamp((abs_pos-anchor_beat)/fade_beats, 0, 1)` and writes the lerped CURRENT value into
   `params["color"]` (and `color_a`/`color_b`, and `slot_colors`). Call it in `_compose_frame` just before
   the `render`/`render_comet` calls. Then ALL three render paths consume already-faded params
   transparently — **NO `render_comet` edit, NO `_comet_frame` edit, NO colorizer-signature change.** This
   shrinks the renderer change in the SCOPE LOCK to ~nothing (the engine + runner do the work).
9. **`_signature` hashes the WHOLE params dict — exclusion is an exact key-filter, and must cover the
   RESOLVED keys.** Verified: `_signature` (`:403`) =
   `tuple(sorted((str(k),repr(v)) for k,v in dict(spec.params).items()))` + effect_name/seed/sync_mode/
   beat_division. So motion signature = that comprehension with `if k not in _COLOR_SIG_KEYS`.
   `_COLOR_SIG_KEYS` MUST include the resolved-color keys the fade WRITES — `color, color_a, color_b,
   slot_colors` — AND the endpoints — `color2, color_from, color_to, fade_beats, gradient_stops,
   slot_colors_from, slot_colors_to`. (Patch 1's 11-key list omitted the standalone resolved `color` —
   include it; a per-frame faded `color` would otherwise flip the motion signature and reset motion every
   tick.) Color signature = `_COLOR_SIG_KEYS ∩ spec.params`.
10. **Two `_compose_frame` call sites; respect `abs_pos` ordering.** Verified: `_compose_frame` is called
   at `:252` AND `:306`; `abs_pos` (a BEAT: `float(anchor.abs_beat_pos)+…`) is computed at `:268`, i.e.
   AFTER `:252`. Thread `abs_pos`+anchor_beat into BOTH sites. The `:252` site has no `abs_pos` yet → pass
   `anchor_beat=None` ⇒ `resolve_fade` is a no-op (instant, no fade) there. Do NOT recompute `abs_pos`
   twice or reorder unless proven safe.

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
- **Motion signature** = the existing `_signature` (~:403-406) with color/fade keys EXCLUDED. CORRECTED
  full list (Reviewer Patch 1 — `slot_colors_from`/`slot_colors_to` were missing):
  `{color, color2, color_a, color_b, color_from, color_to, fade_beats, gradient_stops, slot_colors,
  slot_colors_from, slot_colors_to}` (11 keys).
  (NOTE color_a/color_b ARE excluded — M1 injects them into the two generic dual effects.) This gates
  `self._engine.configure` (motion reset). Color-only changes no longer reset motion.
- **Color signature** = ONLY those 11 excluded keys (must partition cleanly vs the motion signature).
  Maintain `self._color_signature`. When it changes,
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
- The engine must remember the PREVIOUS resolved color/slot_colors — keyed
  `(track_key, role, section_id, look_name, color_shape)`, `cycle` EXCLUDED (Reviewer Patch 2) — to emit
  `color_from` (previous TARGET) + `color_to` (new) + `fade_beats` (= `fade_beats_by_role[role]`, default 0).
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
interpolated). The min-dwell gate is keyed on `role` (NOT role_key) with `min_look_dwell_s` default 1.5s
(`led_dispatch_coordinator.py:74-87`): a `step_within_section` re-roll IS a new same-role dispatch, so its
cadence MUST exceed 1.5s or it is silently dwell-suppressed (and the color update never propagates). At
≥32-beat section cadence this holds at every realistic BPM. Add a test asserting a step re-roll is NOT
dwell-suppressed and that no per-frame re-dispatch occurs (fades are single-trigger, colorizer-interpolated).

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
LED suites + whole suite green (CORRECTED baseline: 1661 passed, 3 skipped, 1 xfailed, 0 failed +
Phase 2b additions; `test_led_config.py` passes clean — the "3 pre-existing failures" are stale).
Confirm: motion bit-exactness preserved when no fade; colorizer still pure; 40fps path has no
new per-frame allocation/locking regressions; nothing committed. Call out any §15.4 ambiguity. Recommend
a live dry-run watch (color-inject + no stutter) before enabling fades on the rig.
```
```
