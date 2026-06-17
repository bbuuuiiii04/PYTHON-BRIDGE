# M2.5 — Legacy Cue Slotization + Random Palette Slot Fill (SPEC ONLY)

**Status:** SPEC — code-grounded, verified against current tree (M2 Phase 2b/3 committed). Sub-agent reviewed.
**Implementation:** NOT STARTED. Do not edit code or config except as the patch you are told to do.
**Validation gate:** `SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED` until §7 passes.

---

## RULES FOR THE IMPLEMENTING AGENT (read first; non-negotiable)

1. **Implement EXACTLY ONE patch per session, in order A → B → C → D → E → F.** Do not start the next
   patch until the current one's accept-list passes. If unsure which patch, STOP and ask.
2. **The slot model is ALWAYS 6 slots.** Index 5 is ALWAYS pure `(255, 255, 255)`. Never produce a 5-slot
   field. Every `slot_colors` list has length 6. "slot_count - 1" palette slots = indices 0,1,2,3,4 = **5**
   draws; then append index 5 white. If you compute anything other than 5 palette draws + 1 white, you are wrong.
3. **Implement ONLY two strategies:** `gradient_even` (existing, untouched) and `random_with_replacement`.
   Do NOT add `mono`, `weighted_random`, or any other branch — not even a stub or a `# TODO`. Config
   validation MUST reject any strategy string other than these two.
4. **Do NOT change, under any circumstances:** `resolve_slot_colors`'s 6-kwarg signature; the injection
   seam call site (`state_manager.py:1724-1761`); the fade memo key; `self._journey_rng`; any existing
   `_slot_*` fn or `SLOT_EFFECTS` entry; `_COLOR_SIG_KEYS`; `exempt_looks`; baked Dune-Sand; lasers / RB / SS.
5. **Pseudocode receiver names are literal.** `config` in pseudocode means `self._config`. Reuse the EXACT
   existing helpers/locals — `_blake2b_int`, `_rng_from_seed`, `_p_to_rgb`, `_blend_white`,
   `self._stop_positions`, `self._current_track_seed`, `focus_lo`, `focus_hi`, `palette`. Do not recompute,
   rename, or re-derive them, and do not add a `config` local or a new parameter.
6. **The fill RNG MUST be a fresh local RNG** seeded EXACTLY with
   `f"{self._current_track_seed}:{section_id}:{step_index}:slotfill:v1"`. Never call `self._journey_rng`.
   Never drop the `:slotfill:v1` salt. Do NOT reuse `resolve_color`'s un-salted seed string.
7. **When `gradient_even` is selected, construct NO RNG** and run the existing `:635-647` path unchanged
   (byte-identical, zero new statements before it).
8. **Adding the new config fields (`slot_fill_strategy_by_look`/`_by_role`) requires THREE file edits in
   order** (§2.D). Skipping `led_models.py` or `led_config.py` will crash the bridge or silently drop the
   key. `slot_fill_strategy_by_role` MUST stay EMPTY/absent for ALL of M2.5 — only `_by_look` gets entries.
9. **Every `_slot_*` fn has the EXACT signature**
   `def _slot_x(beat: float, local_t: float, frame_index: int, params: Mapping[str, Any], segments: int, seed: int) -> MotionField`
   (= `SlotEffectFn`, `govee_frame_renderer.py:19`). The legacy fns you convert have DIFFERENT signatures —
   you are REWRITING, not copy-pasting their `def` line. It returns a `segments × 6` MotionField via
   `_empty_motion_field(segments)`, never a `Frame`, never a hardcoded RGB. Verify shape against
   `_slot_groove_center_chase` (`:1043`).
10. **Within a conversion patch, order is:** (a) write the `_slot_*` fn; (b) register it in `SLOT_EFFECTS`
    AND in `_M2_PHASE2A_PARAM_KEYS` (motion/sync keys only — NEVER `slot_colors`); (c) confirm
    `REALTIME_EFFECT_NAMES` contains the new key; (d) ONLY THEN add the bank look. Never commit a bank look
    whose `scene_ref` is not yet a registered slot effect — that disables ALL LED live.
11. **After EVERY file edit:** run `tests/test_led_color_engine.py` (determinism) AND load the live
    `config/led_look_director.json` through the config loader — both must pass with zero errors before you
    declare the step done.
12. **Do not delete or rename any legacy `rt_*_{color}` look or its fn before Patch F.** They must keep
    resolving (regression test, §6). If anything is ambiguous or a cue's slot mapping is unclear, STOP and
    report — do NOT invent motion or "simplify."

---

This spec supersedes the operator's M2.5 draft where they conflict. The draft was written as if
`resolve_slot_colors`, `MotionField`, and the fade pipeline did not exist. **They do** — see §0. M2.5 is a
*smaller, additive* change: add one fill strategy, convert a set of Frame cues into slot cues, adjust banks.
Palette/focus/dwell/drop-snap is **untouched**.

---

## 0. Current state (verified in code — do NOT rebuild these)

| Capability | Where | Note |
|---|---|---|
| 6-slot model, slot 5 = pure white | `govee_frame_renderer.py:15` (`MAX_SLOTS=6`); `led_color_engine.py:647` | slot 5 hardcoded `(255,255,255)`, not palette-derived |
| `MotionField` type + builder | `govee_frame_renderer.py:993` (`universal_colorizer`); `_empty_motion_field` `:1040` | `MotionField = list[list[float]]`, shape `segments × MAX_SLOTS` |
| `SlotEffectFn` type | `govee_frame_renderer.py:19` | `Callable[[beat, local_t, frame_index, params, segments, seed], MotionField]` |
| `resolve_slot_colors` | `led_color_engine.py:588` | TODAY: **gradient-even only** (`:635-647`); pure, consumes **no RNG** |
| Slot-color fade pipeline | engine `led_color_engine.py:649-659`; renderer `govee_frame_renderer.py:92-96` | `slot_colors_from`/`_to`/`fade_beats` already wired (Phase 3) |
| Slot effects already live | `SLOT_EFFECTS`, `govee_frame_renderer.py:1385` | `groove_center_chase`, `groove_center_burst_retract`, `post_drop_firework_chase`, `breakdown_full_breathing`, `breakdown_star_twinkle` |
| **Slot-effect param-key registry** | `_M2_PHASE2A_PARAM_KEYS` `govee_frame_renderer.py:1415-1428` (merged into `REALTIME_EFFECT_PARAM_KEYS` at `:1427`) | every slot effect IS registered here (motion/sync keys). Comment `:1411-1413`: **`slot_colors` is runtime-injected and deliberately NOT allowlisted** |
| Strobe registry | `REALTIME_STROBE_EFFECTS` `:914`, extended `:1408` (`post_drop_firework_chase`) | white-burst/firework cues register here |
| Default slot fallback | `govee_frame_renderer.py:~1430` | a slot effect with no injected palette fails to a single white slot (fails bright, never crashes) |
| Injection seam | `state_manager.py:1724-1761` | calls `resolve_slot_colors` **iff** `scene_ref in SLOT_EFFECTS` (`:1727`); merges result into `decision.params` (`:1758-1761`) |
| Config-time param validation | `led_config.py:393` | validates ONLY *static* params authored in bank JSON against `REALTIME_EFFECT_PARAM_KEYS.get(scene_ref)`. **Injected `slot_colors` bypass it** (merged at runtime, post-validation) |
| Runtime color/motion split | `_COLOR_SIG_KEYS` `govee_realtime_runner.py:21` (incl. `slot_colors`/`_from`/`_to` at `:27`) | already separates color from motion ⇒ color change does NOT reset motion (no new work) |
| Exempt looks | `led_color_engine.py:620` | engine returns `{}` (injects nothing) for `exempt_looks` (keyed on LOOK name) |
| Strategy config fields | **DO NOT EXIST YET** | `slot_fill_strategy_by_look`/`_by_role` are absent from `led_models.py`, `led_config.py`, and live config — they must be ADDED (§2.D) |

### Conversion = 4 steps per cue (CORRECTED)

`slotizing` a cue is **4 steps**, all in the same patch:
  (a) write a `_slot_<name>` fn returning a `MotionField` (exact `SlotEffectFn` signature — Rule 9);
  (b) register it in `SLOT_EFFECTS` (`:1385`) — this also adds it to `REALTIME_EFFECT_NAMES` (`:1405`);
  (c) register its scene_ref in `_M2_PHASE2A_PARAM_KEYS` (`:1415`) with `frozenset({"duration_beats"}) |
      _SYNC_PARAM_KEYS` (plus any per-cue motion knob the fn reads) — **NEVER `slot_colors`** (it is
      runtime-injected). Firework/white-burst cues ALSO get added to `REALTIME_STROBE_EFFECTS` (`:1408`);
  (d) add a **new** bank look (new generic name) with `scene_ref` = the slot key, `color_source: "engine"`,
      and an empty `params: {}` — see §3 for the worked look example.

> Why (c) even with empty `params`: existing slot effects (e.g. `groove_center_chase`) carry `params: {}`
> in the bank AND have a registry entry — registration is the established convention and lets the look
> safely carry sync params later. An un-allowlisted *static* param disables ALL LED (C5), so register the
> motion keys; just never list `slot_colors`.

**Do NOT** edit `exempt_looks` — new generic look names are non-exempt by default; old color-suffix looks
stay exempt/baked and are orphaned to the legacy bank in Patch F.

---

## 1. Locked operator decisions (2026-06-17)

1. **Reroll → slide, drop → snap.** Implemented purely via existing knobs (§2.C) — no memo-key change.
2. **Frequency: keep it more varied.** Collapsing N color variants → 1 generic cue is accepted to *reduce*
   that motion family's rotation share. Do NOT re-add duplicate entries to preserve old chase dominance.
3. **Strategy is config-resolved inside the engine.** Engine reads `slot_fill_strategy_by_look`/`_by_role`.
   The seam call site (`state_manager.py:1730`) is NOT changed — no `fill_strategy` kwarg. Opt in BY LOOK
   first; `_by_role` stays empty for all of M2.5 (§2.A blast-radius).
4. **Palette/focus/dwell/drop-snap unchanged.** M2.5 only changes how slots 0–4 are filled *within* the
   current focus window.

---

## 2. Engine changes (Patch A)

### A. Add a fill strategy to `resolve_slot_colors` — config-resolved, signature-FROZEN

The 6-kwarg signature (`role, section_id, cycle, look_name, color_source, slot_count`) is FROZEN (Rule 4).
Resolve the strategy *inside* the method:

```
# `config` == self._config
strategy = (self._config.slot_fill_strategy_by_look.get(look_name)
            or self._config.slot_fill_strategy_by_role.get(role)
            or "gradient_even")
if strategy == "gradient_even":
    ... existing :635-647 path, UNCHANGED, no RNG ...
elif strategy == "random_with_replacement":
    ... §2.B ...
# no other branch exists; unknown strings are rejected at config-validation time (§2.D)
```

> ⚠ **BLAST RADIUS (B3) — by-role flips already-live cues.** `slot_fill_strategy_by_role["groove"]`
> applies to the **existing** live slot cues `groove_center_chase` / `groove_center_burst_retract` (role
> `groove`), not just newly converted cues. So `_by_role` MUST stay empty during M2.5; opt in via
> `slot_fill_strategy_by_look` for the one converted look. Promote a role only after EVERY slot cue in it
> is hardware-validated.

Slot 5 (`slot_count-1`) remains `(255,255,255)` for **every** strategy (Rule 2).

### B. `random_with_replacement` — isolated RNG (RESOLVES Gap #1)

`resolve_slot_colors` is documented pure / RNG-free (`:611-614`). The new branch MUST build a *fresh local*
RNG, mirroring the *structure* of `resolve_color`'s per-cue pattern (`led_color_engine.py:542-547`) but with
the salted seed, and MUST NOT touch `self._journey_rng`:

```
use_step   = self._config.step_within_section.get(role, False)
step_index = cycle if use_step else 0
fill_seed  = _blake2b_int(f"{self._current_track_seed}:{section_id}:{step_index}:slotfill:v1")
fill_rng   = _rng_from_seed(fill_seed)            # fresh, local — NEVER self._journey_rng
slots = []
for i in range(slot_count - 1):                   # exactly 5 palette draws for slot_count=6
    p   = fill_rng.uniform(focus_lo, focus_hi)
    p   = max(0.0, min(1.0, p))
    rgb = _p_to_rgb(p, self._config.scale_stops, self._stop_positions)
    rgb = _blend_white(rgb, palette.white)        # palette.white is a FLOAT in [0,1]; identical to :643
    slots.append(rgb)
slots.append((255, 255, 255))                     # slot 5 reserved white — NOT blended
# then the SAME memo/fade tail as the gradient path (:649-659), unchanged
```

- **E4 white-blend parity:** `_blend_white(rgb, palette.white)` is mandatory and identical to the gradient
  path (`led_color_engine.py:643`; `_blend_white` sig at `:105`, second arg is a float). Omitting it makes
  random slots read brighter/more saturated.
- **E3 degenerate focus:** when `focus_lo == focus_hi` (mono/narrow), `uniform(x,x)=x` ⇒ all slots one
  color. Acceptable; assert as an explicit test.
- The `:slotfill:v1` salt makes the slot stream independent of the un-salted `resolve_color` seed
  (`:545`). `v1` = `slot_fill_variant`; bump only to intentionally reshuffle.

Guarantees to test: same `(set_seed, track, role, section_id, look, cycle)` ⇒ identical fill; different
`cycle` with `step_within_section[role]=true` ⇒ may reroll; `gradient_even` byte-identical + RNG-free;
existing `resolve_color` determinism asserts (`tests/test_led_color_engine.py`) byte-identical (proves no
stream perturbation).

### C. Reroll slide vs drop snap (RESOLVES Gap #2) — no memo-key change

The fade memo (`:650`) compares each fill against the last fill for `(track, role, section, look)`. So:
- `step_within_section[role]=true` + `random_with_replacement` ⇒ cycle N fill ≠ N-1 ⇒ `slot_colors_from`/
  `_to` differ ⇒ renderer fades **iff** `fade_beats_by_role[role] > 0`. → **slide.**
- `fade_beats_by_role["drop"] = 0` ⇒ no `fade_beats` key ⇒ renderer **snaps.**
- `step_within_section[role]=false` ⇒ identical fill across cycles ⇒ `from == to` ⇒ no fade.

The seed already carries `cycle` via `step_index`. **No `cycle` in the memo key.** Keep memo key + seam byte-stable.

- **E1 — knobs already set live (verified 2026-06-17):** `step_within_section = {groove:true,
  post_drop:true, drop:false, ambient:false, buildup:false, breakdown:false}`; `fade_beats_by_role =
  {drop:0.0, post_drop:2.0, groove:2.0, ambient:4.0, buildup:0.0, breakdown:4.0}`. Slide/snap is already the
  live single-color behavior; slot fill inherits it with **no config change**. ⚠ Consequence:
  `random_with_replacement` on groove rerolls all 5 slots **every groove cycle** with a 2-beat crossfade —
  TUNING risk of a busy look. Validate on hardware before promoting; do NOT add a damping knob in M2.5.
- **E2 — first cycle of a section snaps.** Memo keys on `section_id`, clears per track (`:367,650`); cycle-0
  has no `prev` ⇒ no fade. Slide applies cycle-1 onward within a section. Expected, not a bug.

### D. Config field plumbing — THREE files, in order (DO NOT SKIP)

`slot_fill_strategy_by_look`/`_by_role` do not exist. To add them, mirror exactly how `step_within_section`
is wired (it is the template):

1. **`led_models.py:98`** (the `ColorEngineConfig` dataclass, beside `step_within_section`/
   `fade_beats_by_role`): add
   `slot_fill_strategy_by_look: Dict[str, str] = field(default_factory=dict)` and
   `slot_fill_strategy_by_role: Dict[str, str] = field(default_factory=dict)`.
2. **`led_config.py:946`** (validation block, mirror the `step_within_section` validator at `:946-953`):
   each must be an object; **every value MUST be `gradient_even` or `random_with_replacement`** — append an
   error for any other string (this is how Rule 3 is enforced).
3. **`led_config.py:1125`/`:1149`** (build block): parse with `.get(key, {})`, coerce keys/values to str,
   and pass `slot_fill_strategy_by_look=...`, `slot_fill_strategy_by_role=...` into the dataclass
   constructor alongside `step_within_section=...`.

Verify after step 2: the current live config (which has NO strategy keys) still validates and loads with
empty-dict defaults. ONLY add the JSON entry (§4) AFTER all three code edits land.

---

## 3. Cue conversion (Patches B–E)

Follow the 4 steps in §0 + Rule 10 ordering. Reference template (schematic — model real internals on
`_slot_groove_center_chase` `:1043`):

```
def _slot_<name>(beat, local_t, frame_index, params, segments, seed) -> MotionField:
    cue_beat = _edm_beat(beat, params)
    field = _empty_motion_field(segments)        # segments × 6, all 0.0
    # ... compute motion in SEGMENT space (positions/intensities) ...
    # map a 0..1 palette position onto slots 0-4:
    slot_coord = relative_pos * 4.0              # 4.0 == MAX_SLOTS-2; NOT 5.0. slot 5 is white-only
    # floor/ceil interpolate intensity into field[idx][slot_lo] / field[idx][slot_hi]
    # write field[idx][5] ONLY for an intended white accent (firework/spark); else leave 0.0
    return field
```

Acceptance for a real conversion (Rule 12 / §5): intensity spreads across slots 0-4 (via `relative_pos *
4.0`); a field that only ever sets `field[idx][0]` is wrong ("slot-0-everywhere" fails Patch B).

**Worked bank-look (step d):** COPY the existing `rt_groove_center_chase` look object from
`config/led_look_director.json` verbatim, then change ONLY `name` → new generic name and `scene_ref` → the
new slot key. Keep its `action`, `backend`, `color_source: "engine"`, `params: {}`, `safety_class`,
`brightness` exactly. Do not invent field names/casing. Add the look to `.example.json` too.

### Classification (verified against current Frame effects)

**Convert → 6-slot MotionField:**

| Current look(s) | Current fn (signature) | Color source today | Target generic |
|---|---|---|---|
| `rt_groove_chase_{red,blue,cyan,green,cyan_white}` | `_groove_chase(name, beat, segments)` `:367` | color from **look NAME** via `_edm_color_for_look` (NOT `params["color"]`) | `rt_groove_chase` |
| `rt_post_drop_chase_{red,blue,cyan,green,cyan_white}` | `_post_drop_chase(name, beat, params, segments)` `:477` | name-derived, optional `params["color"]` override | `rt_post_drop_chase` |
| `rt_drop_chase_{red,blue,cyan,green,cyan_white}` | `_drop_chase(name, beat, local_t, frame_index, params, segments, seed)` `:456` (leading `name` ⇒ still NOT `SlotEffectFn`) | name-derived | `rt_drop_chase` |
| `rt_drop_center_burst_blue_cyan` | `_drop_center_burst_blue_cyan` `:394` | baked blue/cyan | `rt_drop_center_burst` |
| `rt_post_drop_center_comet_blue_cyan` | `_post_drop_center_comet_blue_cyan` `:418` | baked blue/cyan | `rt_post_drop_center_comet` |
| `rt_twinkle_blue` | `_twinkle_blue` `:765` | baked blue | `rt_twinkle` |
| `rt_{groove,drop,post_drop}_freestyle_nebula` | `_groove_nebula`/`_drop_nebula`/`_post_drop_nebula` | baked | `rt_{...}_nebula` (operator visual review) |

> ⚠ **Naming trap:** `rt_groove_chase` (NEW slot cue) is a DIFFERENT motion from the existing
> `groove_center_chase` slot effect. Do not merge, overwrite, or edit the latter.
> ⚠ **Exempt trap:** `rt_twinkle_blue`, `rt_*_center_*`, and the three `_freestyle_nebula` looks are
> currently in `exempt_looks`. You are NOT recoloring them — you create NEW non-exempt generic looks and
> leave the old exempt looks alone (orphaned in Patch F). The legacy fns also have different signatures than
> `SlotEffectFn` — rewrite, don't copy the `def` line (Rule 9).

**Keep baked / exempt (do NOT convert):** `rt_breakdown_star_twinkle_sand` (baked warm Dune-Sand, in
`_EFFECTS` not `SLOT_EFFECTS`), `rt_room_blackout`, all `rt_buildup_*` white ramps/strobes,
`rt_drop_white_aggressive`, `rt_post_drop_white_shatter`, any signature/utility/safety look.

**Cloud/DIY scenes** (`breakdown_1_red`, `breakdown_cyan_stack`, `breakdown_green_snake`, …): CANNOT be
per-slot runtime-colored. Leave on the existing `diy_color_tags` cohesion path. Do not pretend they are slot effects.

---

## 4. Config additions (minimum viable)

Only AFTER §2.D's three code edits land. Add under the `color_engine` object in
`config/led_look_director.json` AND `config/led_look_director.example.json`:

```jsonc
// inside "color_engine": { ... existing keys ..., add:
  "slot_fill_strategy_by_look": {
    "rt_groove_chase": "random_with_replacement"
  }
  // slot_fill_strategy_by_role: OMIT entirely for all of M2.5
```

Do NOT add `slot_fill_strategy_by_role`, `slot_repeat_bias`, or `allow_adjacent_palette_drift` — nothing
consumes them in M2.5 (Rule 3, §8).

Role/look keys are case-sensitive. Verified live role strings: `groove/drop/post_drop/breakdown/buildup/
ambient`. `fade_beats_by_role`/`step_within_section` are ALREADY set correctly (E1) — do not touch them.

---

## 5. Patch sequencing (one per session; accept-list gates the next)

- **A — engine strategy + RNG + config plumbing (no cue conversion).** §2.A–D. Accept: `gradient_even`
  byte-identical + RNG-free; `random_with_replacement` determinism guarantees proven; engine-OFF
  byte-identical; existing `test_led_color_engine.py` byte-identical; config validation rejects unknown
  strategy strings; **with NO strategy config entries, existing live slot cues render byte-identical**
  (B3 closed); live config loads clean.
- **B — convert groove chase family** (`rt_groove_chase_*` → `rt_groove_chase`). Lowest risk; testbed.
  Accept: returns MotionField shape `segments × 6`; intensity spreads across slots 0-4; slide on reroll
  observed; legacy `rt_groove_chase_*` still resolve.
- **C — convert post_drop chase family.** Accept: multi-slot use; firework white = slot 5 only; new cue in
  `REALTIME_STROBE_EFFECTS` if it strobes.
- **D — convert drop family** (`rt_drop_chase_*`, `rt_drop_center_burst_blue_cyan`). Accept: snaps
  (`fade_beats=0`), motion does not fade in.
- **E — convert twinkle / nebula / center-comet** (design-sensitive; operator visual review each; STOP if
  mapping unclear).
- **F — bank cleanup.** Only after B–E validated. Move color-suffix looks to a legacy/fallback bank (do NOT
  delete definitions). Collapse to single generic entries; accept the flatter rotation (decision #2).

Do not convert multiple families in one patch.

---

## 6. Test plan (§T)

**Engine:** 6 slots returned; slot 5 always `(255,255,255)` for every strategy; `random_with_replacement`
allows repeats and applies `_blend_white` to slots 0-4; same seed/context ⇒ identical fill; reroll only when
`step_within_section[role]=true`; `focus_lo==focus_hi` ⇒ all palette slots one color (E3); `gradient_even`
byte-identical + RNG-free; `enabled:false` byte-identical; **`resolve_color` determinism asserts unchanged**
(no `_journey_rng`/per-cue perturbation); **with no strategy config entries, existing slot cues unchanged**
(B3).

**Config:** new fields default to empty dict; validation accepts `{gradient_even, random_with_replacement}`
and **rejects any other string**; current live config still validates/loads.

**Renderer (per converted cue):** `_slot_*` returns MotionField shape `segments × MAX_SLOTS`; no hardcoded
RGB (slot 5 white intensity is a float, not an RGB); `universal_colorizer` produces expected Frame; slot 5
nonzero only at intended white accents; new scene_ref present in `REALTIME_EFFECT_NAMES`; bank look passes
`led_config` validation; NO `slot_colors*` in `_M2_PHASE2A_PARAM_KEYS`.

**Regression:** legacy `rt_*_{color}` names still resolve during compatibility phase; engine-OFF param dict
byte-identical; seam call site + fade memo key unchanged; `exempt_looks` untouched; no existing `_slot_*`/
`SLOT_EFFECTS` entry modified.

**Golden / visual:** same MotionField + different `slot_colors` ⇒ same motion, different RGB. (The
"color change does NOT reset motion" guarantee is ALREADY provided by `_COLOR_SIG_KEYS`
`govee_realtime_runner.py:27` — regression assertion, not new behavior.) Single-slot fill ≈ old single-color cue.

---

## 7. Hardware dry-run (gate to lift HARDWARE-UNVALIDATED)

Per converted family, on hardware:
- engine starts clean, no `color_engine_error`;
- `grep color-inject /tmp/bridge.log` and `grep slot_colors /tmp/bridge.log` show injection for slotized cues;
- groove + post_drop chase visibly use multiple palette slots (not one color);
- slot-5 white accents appear only where intended;
- drop cues snap (no fade-in); groove/post_drop reroll slides without restarting motion;
- legacy fallback cues still render if selected.
Bridge-restart safety: `pgrep -f rb_ss_bridge_v2 | wc -l` must be `1` after restart.

---

## 8. Hard limits / non-goals

- `MAX_SLOTS = 6`; slot 5 stays pure white. No "5 slot" simplification (Rule 2).
- Implement only `gradient_even` + `random_with_replacement` (Rule 3). No `mono`/`weighted_random`/stub.
- Do not touch: seam call site, fade memo key, `self._journey_rng`, `_COLOR_SIG_KEYS`, existing `_slot_*`/
  `SLOT_EFFECTS` entries, `exempt_looks`, baked Dune-Sand.
- Do not add `slot_colors*` to any param-key registry (it is runtime-injected).
- `slot_fill_strategy_by_role` stays empty for all of M2.5 (B3) — opt in by look.
- Do not add `slot_repeat_bias`, `allow_adjacent_palette_drift`, or any config knob nothing consumes.
- Do not change laser, Rekordbox, SoundSwitch, palette/focus/dwell/drop-snap, or DIY/cloud behavior.
- Do not delete legacy cue definitions before Patch F.
- Do not convert white utility/strobe/buildup cues.
- Do not claim live-ready / hardware-validated until §7 passes.
