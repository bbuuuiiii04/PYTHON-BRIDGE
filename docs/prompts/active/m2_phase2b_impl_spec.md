# M2 Phase 2b — implementation spec (slot_colors injection + config looks)

> Author: M2 orchestration session (Claude/Opus), 2026-06-15. Branch `m2-phase2-cues`.
> Builds on Phase 1 (resolve_slot_colors, universal_colorizer) + Phase 2a (6 cue effects registered in
> SLOT_EFFECTS/_EFFECTS). This phase makes the cues SELECTABLE + PALETTE-COLORED. It touches the LIVE
> dispatch path and the LIVE config — implement carefully; Claude reviews adversarially.
> **DO NOT START until the weekly usage limit resets (operator instruction 2026-06-15).**

## 0. Mission
1. Inject `slot_colors` at the dispatch seam for slot-based looks (engine recolors them to the palette).
2. Add the 6 new looks to the live config + their bank membership, color_source, eligibility.

## 1. Live-safety invariants (NON-NEGOTIABLE)
- **`color_engine.enabled:false` (or no block) ⇒ byte-identical legacy behavior.** No slot injection.
- All new engine calls in `state_manager` are **try/except-guarded** exactly like the M1b `resolve_color`
  block (`state_manager.py:1722-1753`): any exception ⇒ set `self._led_last_error =
  "color_engine_error:..."` and leave the decision UNMODIFIED (engine-off for that tick, never crash).
- Colorizer/engine purity (N8): `slot_colors` flows BY VALUE through `decision.params`; the runner/
  colorizer never dereferences the live engine.
- **Config validation (C5):** a malformed `color_engine`/look block must disable ONLY the engine, not all
  LED. The Phase-2a `REALTIME_EFFECT_PARAM_KEYS` entries already allow the new looks' static params; the
  new looks must use ONLY allow-listed static keys. After editing config, run the bridge config load and
  confirm `led-config available=True enabled=True` (no validation failure).

## 2. State_manager seam change (state_manager.py, in `_dispatch_led_automation`)
At the M1b injection block (`:1722-1753`), branch on whether the decision's effect is slot-based:
```
slot_based = str(getattr(decision, "scene_ref", "")) in SLOT_EFFECTS   # import SLOT_EFFECTS from renderer
```
- **If slot_based:** call `engine.resolve_slot_colors(role=..., section_id=..., cycle=..., look_name=decision.look,
  color_source=getattr(decision,"color_source","engine"))` and merge its `{"slot_colors": [...]}` into
  `decision.params` (same `replace(decision, params={**decision.params, **computed})` pattern). Do NOT also
  call resolve_color for slot looks (slot looks are colored entirely by slot_colors).
- **Else (existing looks):** the EXISTING `resolve_color` path, unchanged.
- **Debug log:** extend the `[RGB] color-inject` line so slot looks log `slot_colors=<n colors>` (e.g. the
  first+last gradient rgb and confirm slot5 white) — the handoff requires M2 to log slot_colors for live
  observability. Keep the existing log for non-slot looks.
- `resolve_slot_colors` returns `{}` for exempt/baked/disabled ⇒ nothing injected ⇒ the look renders with
  the renderer's default white slot (so a baked slot look would be wrong — that's why sand is a Frame
  effect in `_EFFECTS`, NOT a slot effect; confirm sand's scene_ref is NOT in SLOT_EFFECTS so it takes the
  plain render path untouched).

## 3. Config additions (config/led_look_director.json — REQUIRES OPERATOR APPROVAL TO APPLY)
Add 6 looks under `looks` (mirror the shape of existing realtime looks — `target: room_perimeter`,
`action: realtime`, `backend: realtime_razer`, `scene_ref: <effect>`, `fallback`, `safety_class`,
`brightness`, `allow_strobe`, plus new `color_source`). Locked role mapping (NO ambient):

| look name | scene_ref | bank role | color_source | allow_strobe |
|---|---|---|---|---|
| `rt_groove_center_chase` | groove_center_chase | groove | engine | false |
| `rt_groove_center_burst_retract` | groove_center_burst_retract | groove | engine | false |
| `rt_post_drop_firework_chase` | post_drop_firework_chase | post_drop | engine | **true** |
| `rt_breakdown_full_breathing` | breakdown_full_breathing | breakdown | engine | false |
| `rt_breakdown_star_twinkle` | breakdown_star_twinkle | breakdown | engine | false |
| `rt_breakdown_star_twinkle_sand` | breakdown_star_twinkle_sand | breakdown | **baked** | false |

- Add each look name to `banks.default.<role>`. Weights: parity with existing looks in that bank unless
  the operator specifies otherwise.
- `color_source` per table. Baked sand → add to `color_engine.exempt_looks` too (belt-and-suspenders so
  the engine never colors it) and do NOT give it a `diy_color_tags` entry.
- The 5 engine slot looks always recolor to the active palette → they're always eligible (no diy tag
  needed; diy_eligible governs DIY looks, not realtime looks).
- **Optional (operator decided separately):** bump `color_engine.palettes.blue_cyan.spread` 0.1→0.2 to add
  green to blue_cyan breakdowns. Only if operator confirms.

## 4. LIVE-ROTATION GATING (raise with operator before adding to banks)
Adding a look to a bank makes it **selectable during a live show immediately on bridge restart**. M1 is
NOT yet live-validated. Recommend: implement injection + define the looks, but get explicit operator
sign-off (and ideally a dry-run watch) before adding them to the live `banks` rotation — or add behind a
config the operator can toggle. The reviewer must confirm this gate with the operator.

## 5. Tests
- State_manager: with engine enabled + a slot-based decision, `decision.params["slot_colors"]` is a
  length-6 list, slot5 == (255,255,255); with `enabled:false` or exempt/baked look, no `slot_colors`
  injected (byte-identical). Engine exception ⇒ decision unmodified + `_led_last_error` set.
- A slot look renders palette-colored end-to-end: inject slot_colors, render via the slot path, assert
  non-white palette colors appear (not the default-white fallback).
- Config-load test: the 6 new looks load, `available=True`, no validation error; a deliberately bad new
  look param disables ONLY the engine (C5).
- `enabled:false` regression: whole existing behavior byte-identical.

## 6. Verify + report
Run the LED suites + whole suite (baseline ~1658 passed, 3 pre-existing test_led_config failures). Confirm:
slot injection only for slot looks; enabled:false byte-identical; config still loads; sand stays baked/
exempt; nothing committed. Flag any place the seam or config didn't map cleanly. Report the live-rotation
gate decision explicitly.
