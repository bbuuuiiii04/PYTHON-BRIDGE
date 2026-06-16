# ChatGPT Review Checklist — M2 Phase 2b (after Gemini implements)

Purpose: catch over-edit / scope-creep / weakened tests on the slot_colors injection work. Review the
DIFF against `main`, not the whole codebase. Demand actual test output, don't trust claims.

## Files that should appear in the diff (and ONLY these)
- `state_manager.py` — the injection seam region only (~`:1722-1755`, around `resolve_color` `:1728`).
- `tests/test_led_color_engine_m2_phase2b.py` — new.
- (Step B only, if sign-off given) `config/led_look_director.example.json`.
RED FLAG if the diff touches: `govee_realtime_runner.py`, renderer cues, `led_dispatch_coordinator.py`,
cloud/DIY code, laser/RB/SoundSwitch, the live `config/led_look_director.json`, or BeatSyncEngine.

## Invariants to verify in the code
- Slot branch keys off `str(getattr(decision,"scene_ref","")) in SLOT_EFFECTS` — NOT off look name or a
  hardcoded list.
- Slot looks get `resolve_slot_colors` and do NOT also get `resolve_color` (no double-injection).
- Merge uses `replace(decision, params={**decision.params, **computed})` — never replaces the whole params
  dict (must preserve sync_mode/beat_division/etc.).
- The try/except guard is intact: exception ⇒ `_led_last_error` set + decision UNMODIFIED (engine-off),
  never raises into dispatch.
- `resolve_slot_colors` called with `slot_count` == `MAX_SLOTS` (6). Slot 5 is pure white.
- `enabled:false` / no `color_engine` block ⇒ no slot injection, byte-identical legacy behavior.

## Tests to demand (and confirm they assert real behavior, not vacuously)
- slot look → `slot_colors` present, length 6, `slot_colors[5] == (255,255,255)`, slots 0-4 are palette
  colors (not all white/default).
- non-slot look → still `color` path, no `slot_colors`.
- exempt / baked / disabled → no `slot_colors`.
- engine exception → decision unchanged + `_led_last_error`.
- sand scene_ref NOT in `SLOT_EFFECTS`.
- cloud/DIY decision → no slot coloring.
- Full suite: **1661 + new tests, 0 failed.** A `test_led_config.py` failure now = a real regression (those
  were resolved); do not accept "pre-existing."

## Diff / config / runtime red flags
- Any test deleted, `@skip`/`xfail` added, or an assertion loosened to make the suite pass.
- New STATIC config look param NOT in `REALTIME_EFFECT_PARAM_KEYS` → would fail the WHOLE LED config load
  (LEDs dark), not just the engine. Confirm new looks use only allow-listed keys.
- Banks edited with weights or duplicate entries (banks are ordered cursor-rotation lists; each look once).
- `rt_post_drop_firework_chase` added without BOTH look `allow_strobe:true` AND `safety.allow_strobe:true`.
- Sand cue routed through the colorizer or added to `SLOT_EFFECTS`.

## Claims Gemini is NOT allowed to make
- "M1 BIG_DROP_SIGNATURE palette filtering is fixed." (It is not; out of scope.)
- "Looks are live in rotation." (Defining looks ≠ adding to banks; bank adds are operator-gated.)
- "Fades / step_within_section implemented." (That's Phase 3.)
- "Reviewed on hardware." (M1 live-validation is a separate gate.)
