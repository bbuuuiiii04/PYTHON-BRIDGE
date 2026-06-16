# M2 Phase 2b — implementation spec (slot_colors injection + config looks)

> Author: M2 orchestration session (Claude/Opus), 2026-06-15. Branch `m2-phase2-cues`.
> Builds on Phase 1 (resolve_slot_colors, universal_colorizer) + Phase 2a (6 cue effects registered in
> SLOT_EFFECTS/_EFFECTS). This phase makes the cues SELECTABLE + PALETTE-COLORED. It touches the LIVE
> dispatch path and the LIVE config — implement carefully; Claude reviews adversarially.
> **DO NOT START until the weekly usage limit resets (operator instruction 2026-06-15).**

## REVIEWER PATCHES — APPLY THESE BEFORE IMPLEMENTING (Claude review, 2026-06-15, grounded vs merge/main 214e206)
These supersede the body where they conflict. Code citations verified against the merged tree.
1. **Config-validation claim in §1 was WRONG — split it.** A bad realtime *look* param does NOT
   "disable only the engine." `_validate` -> `_validate_look` appends look-param errors to the shared
   `errors` list (`led_config.py:104-111`, `:393-396`); a non-empty `errors` returns
   `available=False` => **the WHOLE LED config fails to load** (LEDs go dark, not just the engine).
   Only a malformed `color_engine` block is engine-only (`_parse_color_engine` returns `None`,
   `led_config.py:1069-1087`). Rule for the agent: new looks MUST use ONLY allow-listed static keys
   (`REALTIME_EFFECT_PARAM_KEYS`, set in Phase 2a) or the bridge won't load any LED config at all.
2. **"Weights: parity" in §3 is WRONG — banks have no weights.** `banks.default.<role>` is an ordered
   JSON list consumed by cursor rotation: `look_names[cursor % len(look_names)]`
   (`led_look_director.py:334-335`). There is no weight field. Add each new look name to its role list
   EXACTLY ONCE. A duplicate entry multiplies that look's rotation frequency — only duplicate if the
   operator explicitly asks for higher frequency, and then state the exact count.
3. **Separate "define looks" from "add to banks" (§3).** Defining the 6 looks under `looks` is safe.
   Adding any of them to `banks.default.<role>` makes them live-selectable on the next bridge restart
   (§4). Do these as TWO steps; do NOT add bank entries without explicit operator sign-off (see §4).
4. **`slot_count` is coupled to the renderer.** `resolve_slot_colors(..., slot_count=6)` MUST equal
   `govee_frame_renderer.MAX_SLOTS` (=6). Slot index 5 is the reserved pure-white firework/twinkle slot.
   Do NOT pass a different `slot_count` — a mismatch breaks the slot-5 white reservation.
5. **`rt_post_drop_firework_chase` strobe gate.** Its scene_ref is in `REALTIME_STROBE_EFFECTS`, so the
   look needs `allow_strobe:true` AND `safety.allow_strobe:true`, or config load fails
   (`led_config.py` realtime-strobe cross-check, ~:584-588). The table already sets the look's
   `allow_strobe:true`; confirm the config's `safety.allow_strobe` is also true.
6. **BIG_DROP_SIGNATURE is still an OPEN M1 risk — do not claim M1 palette filtering is fixed.**
   `diy_eligible` still treats the `BIG_DROP_SIGNATURE` (and `white`/`TODO`/compound `+`) tag as
   always-eligible (`led_color_engine.py:438`); it is NOT gated by actual big-drop context. The 6 new
   realtime looks do NOT use `diy_color_tags` so they are unaffected — but Phase 2b must NOT assert M1
   filtering is complete, and must NOT tag any new look `BIG_DROP_SIGNATURE`.
7. **Stale baseline.** The "~1658 passed / 3 pre-existing test_led_config failures" line in §6 is stale.
   Current merged baseline: **1661 passed, 3 skipped, 1 xfailed, 0 failed**; `test_led_config.py` passes
   clean (the 3 failures cited are resolved). Use this as the regression baseline.

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
- **Config validation (C5) — CORRECTED (see Reviewer Patch 1):** a malformed `color_engine` block is
  engine-only (`_parse_color_engine` returns `None`, `led_config.py:1069-1087`). A bad *look* param is
  NOT engine-only — `_validate_look` errors fail the WHOLE LED config load (`available=False`,
  `led_config.py:104-111`, `:393-396`), so the LEDs go dark, not just the engine. The Phase-2a
  `REALTIME_EFFECT_PARAM_KEYS` entries already allow the new looks' static params; the new looks must use
  ONLY allow-listed static keys. After editing config, run the bridge config load and confirm
  `led-config available=True enabled=True` (no validation failure).

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

- **OPERATOR-GATED, SEPARATE STEP (see §4 + Reviewer Patches 2-3):** add each look name to
  `banks.default.<role>` EXACTLY ONCE. Banks are ordered lists rotated by cursor
  (`led_look_director.py:334-335`); there is NO weight field. A duplicate entry multiplies that look's
  rotation frequency — only duplicate if the operator explicitly requests higher frequency, and then
  state the exact count. Do NOT add bank entries without operator sign-off; defining the looks (above)
  is the safe, non-gated part of this phase.
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
  look param **fails config load** (`available=False`, NOT engine-only — corrected per Reviewer Patch 1);
  and separately, a malformed `color_engine` block disables ONLY the engine (`available=True`).
- **MANDATORY baked-sand negative tests (all six assertions, Reviewer Patch 4 from review):** for
  `rt_breakdown_star_twinkle_sand` —
  (a) its scene_ref `breakdown_star_twinkle_sand` is NOT in `SLOT_EFFECTS`;
  (b) the look's `color_source == "baked"`;
  (c) the look name is in `color_engine.exempt_looks`;
  (d) there is NO `diy_color_tags` entry for it;
  (e) the dispatch seam injects NO `slot_colors` (and no `color`) into its decision.params;
  (f) it renders through the normal Frame path (`_EFFECTS`), not the slot colorizer path.
- `enabled:false` regression: whole existing behavior byte-identical (no `color`, no `slot_colors`).

## 6. Verify + report
Run the LED suites + whole suite (CORRECTED baseline: 1661 passed, 3 skipped, 1 xfailed, 0 failed;
`test_led_config.py` passes clean — the "3 pre-existing failures" cited elsewhere are stale). Confirm:
slot injection only for slot looks; enabled:false byte-identical; config still loads; sand stays baked/
exempt; nothing committed. Flag any place the seam or config didn't map cleanly. Report the live-rotation
gate decision explicitly.
