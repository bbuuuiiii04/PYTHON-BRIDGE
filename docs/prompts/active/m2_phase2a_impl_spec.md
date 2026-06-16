# M2 Phase 2a — implementation spec (new cue effects in the renderer ONLY)

> Author: M2 orchestration session (Claude/Opus), 2026-06-15. Branch `m2-phase2-cues`.
> Builds on Phase 1 (resolve_slot_colors + universal_colorizer + empty SLOT_EFFECTS + render() slot
> hook, all in the tree). A reviewer (Claude) will adversarially check your work. Do NOT trust your
> own test PASS — assert real behavior.

## 0. Mission & HARD boundaries
Add the 6 prototype cues as renderer effects. **Renderer code + tests ONLY. ZERO live behavior change**
(no config look references these names yet, so nothing renders them until Phase 2b).

**DO (only these):**
- Edit `govee_frame_renderer.py`: add the cue effect functions + register them.
- New test file `tests/test_led_color_engine_m2_phase2a.py`.

**DO NOT (out of scope / will be rejected):**
- Do NOT edit `config/led_look_director.json` or ANY config file. (Phase 2b, operator-gated.)
- Do NOT edit `state_manager.py` / the injection seam / `govee_realtime_runner.py`. (Phase 2b/3.)
- Do NOT touch existing effects, `_comet_frame`, `render_comet`, or do any "de-snapping" of
  `_beat_chase`/`_bar_wipe`. Do NOT touch the comet-stutter code. Leave all existing render output
  byte-identical (re-run the Phase-1 byte-identical test to confirm).
- Do NOT run git add/commit/stash/checkout. Leave changes uncommitted.
- Do NOT introduce integer snapping. All moving positions stay fractional (see §3).

## 1. Source of truth for geometry (port VERBATIM)
`~/.gemini/antigravity-ide/brain/dfbaeb5b-bff1-4229-b752-205a92c40a78/scratch/motion_skeletons.py`.
The operator owns this math — **do not alter the geometric timing or constants** (e.g. the 0.05
firework distance check, comet_width ratios, breathing envelopes, sand palette RGB, 30% caps). You only
adapt signatures + slot model to the bridge. Re-read `docs/prompts/active/opus_m2_cue_wiring.md` for
intent, but where it lists `_blue/_cyan` firework variants it is SUPERSEDED (see §2: single look).

## 2. The 6 cues
Slot model (already in Phase 1): `MAX_SLOTS = 6`; indices 0-4 = gradient palette, index 5 = pure white.

ENGINE slot cues (return `MotionField`, register in `SLOT_EFFECTS`):
1. `groove_center_chase` — dual-head comet from center outward, gradient across slots 0-4. Port
   `groove_center_chase`.
2. `groove_center_burst_retract` — volume-bar burst out/retract, slots 0-4. Port
   `groove_center_burst_retract`.
3. `post_drop_firework_chase` — **single palette-driven look** (NOT a `_blue/_cyan` family; do NOT
   touch `post_drop_chase_*`). Comet base on slots 0-4 + pure-white firework bursts on **slot 5**,
   firing ONLY on the 4th beat of the 4-beat cycle (`beat % 4.0 >= 3.0`). Port
   `post_drop_center_chase` (rename to `post_drop_firework_chase`). STROBES → add to
   `REALTIME_STROBE_EFFECTS`.
4. `breakdown_full_breathing` — full-strip sine breathing + color drift across slots over 32 beats.
   Port `breakdown_full_breathing`.
5. `breakdown_star_twinkle` — per-pixel breathing stars across slots, 30% cap. Port
   `breakdown_star_twinkle`.

BAKED cue (returns `Frame`, register in `_EFFECTS` as a normal Frame effect — NOT in SLOT_EFFECTS):
6. `breakdown_star_twinkle_sand` — hardcoded Dune Sand RGB (the 5 warm tuples in the prototype),
   30% cap, BYPASSES the colorizer. Port `breakdown_star_twinkle_sand`. This look is deliberately warm
   (violates the cool corridor) and must NEVER be routed through the palette engine.

## 3. Signature & beat adaptation (the integration work)
- Add a type alias near `EffectFn`: `SlotEffectFn = Callable[[float, float, int, Mapping[str, Any], int, int], MotionField]`.
- Each ENGINE slot cue has signature `(beat, local_t, frame_index, params, segments, seed) -> MotionField`
  (same arg order as EffectFn, but returns MotionField). The prototype fns are `(beat, segments, params)`
  — adapt by reading `segments`/`params` from the new args and ignoring `local_t`/`frame_index`/`seed`
  UNLESS the cue needs determinism-by-seed (the twinkle/firework use `random.seed(idx ...)` — keep the
  prototype's exact seeding so output is deterministic; do NOT substitute the bridge seed).
- **Beat handling:** match the existing 32-beat EDM cue convention. `_edm_dispatch` computes
  `cue_beat = _edm_beat(beat, params)` (govee_frame_renderer.py:761) before calling each EDM cue. Do the
  SAME inside each new slot cue (compute `cue_beat = _edm_beat(beat, params)` first, then run the
  prototype's modulo math on `cue_beat`) so `sync_mode`/`beat_division`/`duration_beats` behave like the
  rest of the family. VERIFY `_edm_beat`'s signature/behavior before using it.
- **No int snapping:** keep `center = segments/2.0`, fractional `comet_head_dist`, sub-pixel AA exactly
  as the prototype. The only `int()` allowed is array indexing (`field[idx]`) and the prototype's
  existing `int(math.floor(...))` slot-coordinate splits — preserve those verbatim.

## 4. Registration (C5-aware — additive only)
- `SLOT_EFFECTS` (currently `{}`): add the 5 engine cues → their SlotEffectFn.
- `_EFFECTS`: add `breakdown_star_twinkle_sand` → its Frame fn (it's baked).
- `REALTIME_EFFECT_NAMES`: today `= frozenset(_EFFECTS.keys())`. Change to
  `frozenset(_EFFECTS.keys() | SLOT_EFFECTS.keys())` so Phase-2b config looks for slot cues validate.
- `REALTIME_STROBE_EFFECTS`: add `post_drop_firework_chase`.
- `REALTIME_EFFECT_PARAM_KEYS`: add an entry for EACH of the 6 new names = the standard
  `frozenset({"duration_beats"}) | _SYNC_PARAM_KEYS` (mirror what EDM_BUILDS effects get, :894-902), PLUS
  any per-cue runtime knob the cue reads from params (`burst_beats`, `breath_beats`, `drift_beats`). This
  is REQUIRED: a Phase-2b config look with an un-allowlisted static param disables ALL LED (C5). Do NOT
  add `slot_colors` to the allowlist (it is RUNTIME-injected, never a static config key).
- Do NOT add the slot cues to `EDM_BUILDS` (that registry is for Frame-returning `_edm_dispatch`
  effects; slot cues return MotionField and route via SLOT_EFFECTS).

## 5. Tests (`tests/test_led_color_engine_m2_phase2a.py`)
All pure — call effects directly; colorize with synthetic slot_colors to inspect output.
1. **Each engine cue returns a valid MotionField:** shape `[segments][MAX_SLOTS]`, all intensities ≥ 0,
   for several beats. `breakdown_star_twinkle_sand` returns a `Frame` (list of RGB), max channel ≤ 0.3*255
   rounded (the 30% cap).
2. **Structure-invariant:** for an engine cue, render the SAME beat with two different synthetic
   slot_colors via `universal_colorizer` → the set of non-zero pixel indices is identical (geometry is
   color-independent).
3. **Determinism:** same (beat, segments, params) → identical MotionField across calls (the twinkle/
   firework reseed per-pixel deterministically; assert byte-identical repeat).
4. **Smoothness (fractional motion, the operator's priority):** for `groove_center_chase`, sweep beats
   in small steps (e.g. 0.0, 0.05, 0.10 …) and assert the comet's intensity centroid (or leading lit
   index, fractionally weighted) advances by SMALL fractional amounts — i.e. it is NOT constant across
   sub-beat steps and does not jump only on integer indices. This guards the no-int-snap requirement.
5. **Firework timing:** `post_drop_firework_chase` has slot-5 energy ONLY when `cue_beat % 4 >= 3`; zero
   slot-5 elsewhere. Comet (slots 0-4) present throughout.
6. **post_drop_chase_* untouched:** assert `post_drop_chase_blue` still renders identically (reuse a
   golden frame) — proves the new family didn't disturb the old one.
7. **Phase-1 byte-identical gate still passes** (run the Phase-1 test file too).

## 6. Verify (paste actual output)
```
cd /Users/bbui/rb_ss_bridge_v2
/opt/homebrew/bin/python3 -m pytest tests/test_led_color_engine_m2_phase1.py \
  tests/test_led_color_engine_m2_phase2a.py tests/test_led_color_engine.py \
  tests/test_led_color_engine_integration.py -q
/opt/homebrew/bin/python3 -m pytest -q   # whole suite: pass count + any NEW failures
cd /Users/bbui && /opt/homebrew/bin/python3 -c "import rb_ss_bridge_v2.govee_frame_renderer as r; print('effects+slots:', len(r.REALTIME_EFFECT_NAMES)); print('slot_effects:', sorted(r.SLOT_EFFECTS))"
```
Pre-existing known failures (NOT regressions): the 3 in `test_led_config.py`. Whole-suite baseline ≈ 1634 passed.

## 7. Report back
Diff summary (only the 2 allowed files), full targeted pytest output, whole-suite pass count + any NEW
failures, confirm: no config/state_manager/runner/existing-effect edits; nothing committed; SLOT_EFFECTS
now has the 5 engine cues; REALTIME_EFFECT_PARAM_KEYS extended additively for the 6 names; Phase-1
byte-identical test still green. Call out any spec ambiguity or place the prototype math didn't map
cleanly — do not paper over it.
