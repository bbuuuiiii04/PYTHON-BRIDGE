# M2 Phase 1 — implementation spec (A1 resolve_slot_colors + A2-core universal_colorizer)

> Author: M2 orchestration session (Claude/Opus), 2026-06-15. Code-grounded against the live tree
> on branch `codex/led-doc-cleanup-gates`. Line numbers are anchors — **match on symbol names and
> re-verify before editing.** You are an implementation subagent; Claude will adversarially review
> your output. Do NOT trust your own test PASS at face value — assert real behavior, not vacuities.

## 0. Mission & hard boundaries
Build the M2 slot-color foundation as **pure, behind-the-flag, ZERO live-path behavior change**.
This is the keystone the Phase-2 cues + comet refactor build on. Two deliverables only:
- **A1** — `LedColorEngine.resolve_slot_colors(...)` (pure engine method).
- **A2-core** — `MAX_SLOTS`, `MotionField`, `universal_colorizer` in the renderer + a `render()`
  dispatch hook gated on an EMPTY slot-effect registry (so existing output is unchanged).

**OUT OF SCOPE for Phase 1 (do NOT do these — they are Phase 2/3):**
- Do **NOT** refactor `_comet_frame` to emit slot-intensity, and do NOT route `render_comet`
  through the colorizer. (Phase 2, gated by golden-frame parity.)
- Do **NOT** add any new cues / looks / `_edm_dispatch` branches / `EDM_BUILDS` entries. (Phase 2.)
- Do **NOT** touch fades, `abs_pos`, `step_within_section`, signatures, or `govee_realtime_runner`. (Phase 3.)
- Do **NOT** add any new STATIC config param key (no `slot_colors`/`gradient_stops` in any config
  look). `slot_colors` is RUNTIME-injected only in Phase 1, so `REALTIME_EFFECT_PARAM_KEYS`
  (`govee_frame_renderer.py:882`) MUST NOT change (runtime params are not validated; static keys are
  — an unlisted static key disables ALL LED per C5).

## 1. Authoritative context (read before coding)
- `docs/plans/active/led_color_engine_spec.md` §15.1 (slot-intensity vector), §15.3 (seeds: separate
  color RNG domain), §15.5 (scale_stops = green,cyan,blue,purple,magenta,red), §15.7 (milestones).
- `docs/prompts/active/opus_m2_cue_wiring.md` + the prototype
  `~/.gemini/antigravity-ide/brain/dfbaeb5b-bff1-4229-b752-205a92c40a78/scratch/motion_skeletons.py`
  — for the slot model only (slots 0-4 = gradient, slot 5 = pure white). The prototype's
  `universal_colorizer` is the formula reference, **but see §3 clamp warning.**

## 2. A1 — `LedColorEngine.resolve_slot_colors`
File: `led_color_engine.py`. Add a method mirroring `resolve_color` (`:463`) but returning slot colors.

Signature:
```python
def resolve_slot_colors(
    self, *, role: str, section_id: str, cycle: int, look_name: str,
    color_source: str, slot_count: int = 6,
) -> dict[str, Any]:
```
Behavior:
- Same early-returns as `resolve_color`: return `{}` if `not self._config.enabled`, if
  `color_source != "engine"`, or if `look_name in self._config.exempt_looks`.
- Compute the SAME focus window `[focus_lo, focus_hi]` as `resolve_color` (`:495-513`), including the
  `drama_by_role`/`role_spread` widening. **Factor the focus-window computation out of `resolve_color`
  into a private helper** (e.g. `_focus_window(role) -> tuple[float, float]`) and call it from BOTH
  `resolve_color` and `resolve_slot_colors` — do not duplicate the math (cross-check gap #4).
  `resolve_color`'s observable output MUST be unchanged by this extraction (regression test).
- Sample `slot_count - 1` gradient points EVENLY across `[focus_lo, focus_hi]` into slots `0..slot_count-2`
  (for slot_count=6 → slots 0-4), each via `_p_to_rgb(p, scale_stops, stop_positions)` then
  `_blend_white(rgb, palette.white)`. Slot `slot_count-1` (slot 5) = pure white `(255,255,255)` —
  NOT white-blended, NOT palette-derived (it is the reserved firework/twinkle white).
  - Edge case: if `focus_lo == focus_hi` (mono focus), all gradient slots collapse to the same color —
    that is correct (mono palettes render near-single-color). Do not special-case.
  - Determinism: this is a pure function of `(current palette/focus state, slot_count)`. It does NOT
    consume the per-cue RNG (slot sampling is deterministic linear sampling, not random). Do not advance
    or depend on any RNG here.
- Return `{"slot_colors": [rgb0, rgb1, ..., white]}` (length `slot_count`).

## 3. A2-core — renderer colorizer (govee_frame_renderer.py)
Add near the top-level types (after `Frame = list[RGB]`, `:10`):
```python
MAX_SLOTS = 6
MotionField = list[list[float]]   # [segment][slot] intensity 0..1+ (unclamped pre-colorize)
```
Add the colorizer (place near `fold_additive`):
```python
def universal_colorizer(field: MotionField, slot_colors: list[RGB]) -> Frame:
    # rgb[px] = clamp( Σ_slot slot_color[slot] · intensity[px][slot] )
```
**CRITICAL — clamp semantics (gap #4 cross-check):** use the bridge's `_clamp_channel` (`:16`, which
does `int(round(...))`) for the final per-channel clamp. **Do NOT** copy the prototype's `clamp()`
(it truncates via `int(val)`); truncation breaks bit-exactness vs every existing renderer path.
- Pad `slot_colors` shorter than `MAX_SLOTS` with `(0,0,0)`; ignore slots ≥ len(slot_colors) or ≥ MAX_SLOTS.
- Accumulate per-channel in float, clamp once at the end with `_clamp_channel`.
- Skip the multiply when `intensity <= 0` (perf; must not change result).

### render() dispatch hook — MUST be a no-op in Phase 1
- Add a module-level `SLOT_EFFECTS: dict[str, EffectFn] = {}` (EMPTY in Phase 1). These are effects
  that return a `MotionField` instead of a `Frame`.
- In `render()` (`:962`): if `str(name) in SLOT_EFFECTS`, call the slot effect → `MotionField`, then
  `universal_colorizer(field, slot_colors)` where `slot_colors = _slots(safe_params.get("slot_colors"))`
  with a sane default when absent (default to a single white slot list, so a misconfigured slot effect
  fails bright-white, never crashes), then clamp/pad exactly as the existing path does. Else: the
  EXISTING `_EFFECTS` path, byte-for-byte unchanged.
- Because `SLOT_EFFECTS` is empty in Phase 1, `render()` and `render_comet()` output for every current
  effect is **byte-identical**. Prove it (see tests).
- Add a small validator `_slots(value) -> list[RGB] | None` mirroring `_color` (`:24`): accept a list
  of 3-int triples, clamp each via `_clamp_channel`, reject malformed → return None (caller uses default).

## 4. Tests (new file: `tests/test_led_color_engine_m2_phase1.py`)
Pure seams make this fully unit-testable; no hardware, no I/O.
1. **universal_colorizer correctness:** single slot `[(R,G,B)]` with intensity vector → equals
   `[_clamp_channel(R*i), _clamp_channel(G*i), _clamp_channel(B*i)]` per pixel (assert against
   `_clamp_channel`, proving round-not-truncate). Multi-slot additive sum. Padding/short slot_colors.
   Intensity > 1.0 clamps. Empty field → empty frame.
2. **structure-invariant:** identical `MotionField` + two different `slot_colors` → ONLY rgb differs;
   feed the SAME field, assert geometry (which pixels are non-zero) is colorizer-independent (trivially
   true here, but assert it as the contract Phase-2 cues rely on).
3. **resolve_slot_colors:** returns `{}` for disabled / non-engine / exempt looks; returns length-6
   list; slot 5 == `(255,255,255)` exactly; slots 0-4 are palette colors within the current focus
   window; mono-focus → slots 0-4 equal; deterministic across repeated calls (no RNG advance). Use a
   small synthetic `ColorEngineConfig` like the existing `test_led_color_engine.py` fixtures.
4. **resolve_color regression:** after the `_focus_window` extraction, `resolve_color` output is
   identical to a captured baseline for a fixed engine state (golden dict).
5. **renderer byte-identical regression (THE Phase-1 gate):** for a representative set
   (`groove_chase_blue`, `drop_chase_blue`, `post_drop_chase_blue`, `solid`, `breathe`,
   `gradient_sweep`) render N frames across beats {0,1,2,3,3.5,8,16} via BOTH `render` and (for comet
   effects) `render_comet`, and assert the output equals the SAME call on a pre-change reference. Since
   `SLOT_EFFECTS` is empty, simplest robust form: assert outputs are unchanged by capturing golden
   fixtures generated by the current code BEFORE your edit (commit the fixtures or generate-in-test
   against an unmodified import path). At minimum, assert no exception and stable shape; ideally exact.

## 5. Invariants to preserve (verify, don't assume)
- **N8 / purity:** `universal_colorizer` and `resolve_slot_colors` are PURE over their args; no global
  state, no engine deref from the render path. (Colorizer runs on the 40fps runner thread.)
- **`enabled:false` / no `color_engine`:** byte-identical legacy behavior. resolve_slot_colors returns
  `{}`; SLOT_EFFECTS empty.
- **C5:** no new static config param key (§0). `REALTIME_EFFECT_PARAM_KEYS` unchanged.
- **No new dependencies, no import cycles** (engine imports only `led_models`; renderer imports nothing
  from the engine).

## 6. Verification (run and PASTE output in your report)
```
cd /Users/bbui/rb_ss_bridge_v2
/opt/homebrew/bin/python3 -m pytest tests/test_led_color_engine.py \
  tests/test_led_color_engine_integration.py tests/test_led_color_engine_m2_phase1.py -q
/opt/homebrew/bin/python3 -m pytest -q   # whole suite: report pass count + any NEW failures
/opt/homebrew/bin/python3 -c "import rb_ss_bridge_v2.govee_frame_renderer, rb_ss_bridge_v2.led_color_engine; print('import OK')"
```
Pre-existing known failures (do NOT count as regressions): the 3 in `test_led_config.py`
(ExampleConfig/LiveMode). Whole-suite baseline before your change ≈ 1604 passed.

## 7. Report back (for Claude's review)
- Exact diff summary (files + line counts) and the new test file.
- Full pytest output for the targeted suite + whole-suite pass count + any new failures.
- Any place you deviated from this spec or found it wrong/ambiguous (call it out — do not silently
  paper over it).
- Confirm explicitly: SLOT_EFFECTS is empty; no static param key added; no comet/fade/runner edits.
