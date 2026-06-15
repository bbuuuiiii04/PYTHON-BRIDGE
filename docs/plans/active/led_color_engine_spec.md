# LED Color Engine — Design Spec

Status: **DESIGN (not yet approved to build)**. Author: planning pass 2026-06-15.
Implementation target: Codex (per repo convention). This doc is the source of truth for the model.

---

## 1. Goal & locked model

Decouple **color** from **look** (motion). Looks keep owning motion (comet, strobe, sparkle,
chase); color comes from an **automatic, key-independent color engine** that evolves across a set.

Decided behavior (settled — do not reopen):

- **Color is NOT derived from musical key.** Two tracks in the same key can look completely
  different. (Earlier key-driven / key-drift models were explicitly rejected.)
- **Automatic, zero mental load while DJing.** No required live input. The engine runs itself.
- **Slow drift = cohesion.** A drifting "anchor" hue moves slowly over the set, so runs of
  several tracks naturally share a color family ("a group of tracks, same palette") without any
  manual action.
- **Dramatic shifts snap to big drops.** Occasional larger jumps to a new family ride in on a
  detected big drop so the change lands on the impact and reads as intentional.
- **Per-cue variety.** Within a track, each cue rolls a random hue offset around the current
  anchor (some drops bluer, some greener, etc.), seeded so a single playback is stable but plays
  differ. Two-color effects pick two offsets.
- **White is an accent**, not a scale position. Occasional white accents + cue-mandated whites.
- **Future: full live control** for a dedicated lighting operator (see §8): shift color, lock /
  unlock the current palette, and **queue a palette** to take effect on the next track/drop.
- **Everything configurable** (see §7).

### Color space — the linear hue scale

Allowed hues lie on a single **linear** scale; **orange and yellow do not exist on it**, so any
fade or step physically cannot pass through them:

```
green —— cyan —— blue —— purple —— red      (white = separate accent channel)
```

A **palette** is the configurable, selectable unit: a named entry = a **point/range on the scale**
+ an optional **white blend** + a **weight** (how often it's picked). The engine maintains a
**library of palettes** (fully customizable, §7a) and selects among them by weight. "Pink" is
whitened magenta (the purple↔red region with white blended in) — still no orange/yellow.

Scale anchor RGBs (defaults, tunable in config):

| Stop | RGB |
|---|---|
| green | (0, 255, 0) |
| cyan | (0, 255, 255) |
| blue | (0, 0, 255) |
| purple | (160, 0, 255) |
| red | (255, 0, 0) |

Interpolation is along scale position `p ∈ [0,1]` (green=0 … red=1), converted to RGB by
piecewise-lerp between adjacent stops. **All fades/steps interpolate in `p`-space**, guaranteeing no
orange/yellow. White is injected as a separate decision (replace hue with (255,255,255)), never a
point on `p`.

---

## 2. The color engine (state + behavior)

A small stateful component owned by **state_manager** (it alone sees track changes, drop detection,
and beat position). Conceptually a new module `led_color_engine.py` with an instance held by the
state manager.

### Engine state
- `current_palette: str` — selected palette name from the library.
- `anchor_p: float` — center position of the current palette on the scale `[0,1]`.
- `dwell_remaining: int` — tracks left before re-selecting a palette.
- `set_seed: int` — seeds the set's color journey (random at startup / first track).
- `current_track_seed: int` — derived from `d.load_gen` (always present; per-play variety). Use
  `content_id` instead only if the same track should color identically across sessions.
- `lock: bool` + `queued_palette: str` — live-control state (§8), default unlocked / empty.

### Palette selection + dwell (Layer 1 — cohesion)
- The engine holds a **current palette** chosen from the weighted library (§7a). It **dwells** on
  it for a stretch (`palette_dwell_tracks`, e.g. ~3–5 tracks) so a run of tracks shares the palette
  — that's the "group of tracks, same palette" behavior, with zero input.
- On dwell expiry (track change), it re-selects a palette by **weight** (a high-weight palette like
  `blue_cyan`/`red` is likely; `purple_pink_white` very rarely). `anchor_p` becomes the selected
  palette's center; per-cue rolls stay inside that palette's range.
- When `lock=True`, the current palette is frozen (held across the group, dwell paused).

### Phrase-section model (CRITICAL — tracks have runs of repeated markers)
Real tracks fire **runs** of the same marker (multiple UP in a row, multiple CHORUS in a row). The
engine operates on **sections, not raw markers**. A `section` = a contiguous run of the same
resolved role; `section_id` increments only when the role changes:
- run of UP markers → role depends on the **existing resolver**: an UP is a `buildup` ONLY when a
  drop is ≤ `phrase_lookahead_beats` (~32) ahead (`smart_phrasing.py:357-360`, `smart_buildup_active`;
  fallback infers a 32-beat up before each Smart Drop, `:540-545`). An UP with **no drop within 32
  beats resolves to `groove`** and is colored normally by the palette. The engine NEVER re-decides
  buildup-vs-groove — it colors whatever role the resolver emits.
- run of CHORUS markers → per the existing lifecycle, the first 1–2 = a **DROP section**, the rest =
  a **POST_DROP section**.
Color is rolled **per section and held across its repeated markers**. The "section" is the existing
**`role_key`** (`state_manager.py:2211`, `f"{active}:{d.load_gen}:{role}:{marker}"`) — dispatch only
(re)triggers when it changes (`:1626`), so seeding the color roll on `role_key` holds one color
across a section and re-rolls only on a genuine transition. The 32-beat groove re-cycle is already
in `role_key` as `:c{cycle}`; per-track focus seeds on `d.load_gen`. So a drop slams **one** decisive
color for the whole impact instead of flickering on every CHORUS marker.
- **Groove re-cycle:** a groove section that runs past 32 beats **without** a new phrase marker
  re-cycles its look every 32 beats. The engine uses that 32-beat cycle as the groove's **step
  index** — so with `step_within_section.groove=true` the color gently re-rolls (within the track's
  focus window) on each 32-beat groove cycle, and holds otherwise. Phrase markers still take
  priority: entering a new section resets to that section's color.
- **Optional stepping:** `step_within_section` (config, per role) lets long runs gently re-roll per
  step where movement is wanted. Default: `drop=false` (hold the impact), `post_drop=true`,
  `groove=true` (steps on each 32-beat groove cycle), `buildup=n/a` (white).

### Drop-snap dramatic shift (Layer 2 — drama)
- Evaluated **once per DROP section** (at its first trigger), NOT per CHORUS marker — otherwise a
  4-marker chorus run would roll the dice 4× and snap almost every track.
- With probability `big_shift_chance` (config), **switch palette now** (re-select by weight,
  optionally biased toward rarer "dramatic" palettes via `big_shift_weight_bias`). The change rides
  in on that drop section. Otherwise the drop behaves normally.
- `lock=True` suppresses drop-snaps too.

### Per-track focus (Layer 1.5 — track character inside a palette)
When a track loads, the engine draws a **focus** inside the current palette's range, seeded by
`current_track_seed` — this gives each track its own character so two `blue_cyan` tracks don't look
identical, and **repeats are allowed** (a track can sit on one color all the way through):
- a focus **center** `fc` (a point inside the range) and **width** `fw` drawn from the palette's
  `focus_modes` weights:
  - `mono` → `fw≈0` at an end → **"only blue"** or **"only cyan"** (a single color, repeated)
  - `lean` → narrow `fw` near one end → **"mainly blue"** / **"mainly cyan"**
  - `full` → `fw` spans the whole range → **"perfectly mixed"**
Cues then roll within `[fc-fw, fc+fw] ∩ range`, not the whole palette. (For point palettes like
`red`, focus is a no-op — there's nothing to sub-divide.)

### Per-cue color resolution (Layer 1 spread + white)
At each cue trigger, for the look being dispatched:
1. If the look is **white-exempt** (see §5) → inject nothing; the effect renders its hardcoded white.
2. Else draw `p` inside the **track's focus window** (above), jittered by `spread` (widened for
   drops if `drama_by_role`), seeded by `(current_track_seed, section_id)` so repeated markers in a
   section hold one color — unless `step_within_section[role]` is true, which adds the marker index
   to the seed for gentle per-marker movement. Two-color effects draw `p2` similarly.
3. Blend in the palette's `white` amount (0..1) toward (255,255,255) — this is what makes
   `red_white` / `purple_pink_white` read as white-tinged.
4. Convert `p`→RGB; inject as `params["color"]` (+ `params["color2"]` / `color_a`/`color_b` for
   multi-color effects). For DIY scenes, color is not injected — eligibility is filtered instead (§6).

---

## 3. Integration points (verified against current code)

- **Injection seam:** in `state_manager`, after the director returns an `LEDLookDecision` and
  **before** `self._led_scene_adapter.trigger(decision)` (around the trigger sites near
  `state_manager.py:1345 / 1490`). Build a merged params dict = `{**decision.params, **computed}`
  and set it on the decision (rebuild via `dataclasses.replace` since `params` is a `Mapping`).
- **Renderer — generic effects:** already honor `params["color"]` / `color_a` / `color_b`
  (`govee_frame_renderer.py:193–283`). No change needed.
- **Renderer — EDM effects:** `_edm_color_for_look(name, beat)` (`govee_frame_renderer.py:289`) is
  hardcoded by name suffix and ignores params. **Change:** have it (or its call sites
  `:311,400,419`) prefer `params["color"]`/`params["color2"]` when present, else fall back to
  today's suffix logic. This keeps every existing look working when no color is injected.
- **Renderer — white effects:** `drop_white_aggressive`, `post_drop_white_shatter`,
  `buildup_white_*` hardcode white and read no color → exempt automatically. No change.
- **Decision params flow:** `LEDLookDecision.params` (`led_models.py:158`) → adapter → renderer
  `render(..., params=...)` (`govee_frame_renderer.py:958`). Unchanged.

---

## 4. Transition fade (phased)

User wants the palette to **fade ~4 beats after a master change**, not hard-cut.

**Architectural constraint (important):** the realtime adapter renders frames on its own loop
between cue triggers. A per-cue injected color is a *step* at trigger time; a smooth cross-track
fade requires interpolation *between* triggers.

- **Phase 1 (simpler, ship first):** per-cue color **stepping** only. Color changes at each cue
  trigger. Cross-track change appears at the next cue after the master change. No sub-cue fade.
  Fully delivers drift + drop-snap + variety; the only thing missing is the smooth glide.
- **Phase 2 (fade):** carry `color_from`, `color_to`, `fade_start_beat`, `fade_beats` (default 4) in
  params and have effects interpolate `p_from→p_to` over the fade window using their existing beat
  clock — OR move the interpolation into the realtime adapter's per-frame loop. Decide at Phase 2.

Recommend building Phase 1 first, validating the feel live, then Phase 2.

---

## 5. Color source per look (engine-colored vs self-colored)
Every look declares `color_source` (default `engine`):
- **`engine`** — the look defines *motion only* and reads injected color via `params["color"]`
  (and `params["color2"]`/`color_a`/`color_b` for multi-color motions). The engine injects the
  current palette's color(s) per §2. Use for chases, strobes, sparkles, comets that should follow
  the set's color journey. Multi-color looks receive two points (`p`,`p2`) from the track's focus
  window, so a "blue↔cyan strobe" renders blue↔cyan in `blue_cyan`, two reds in `red`, etc.
- **`baked`** — the look renders its **own authored colors**; the engine never touches it. This is
  the generalized exemption. Use for signature looks and anything that must keep a fixed identity.

**The no-orange/yellow constraint applies ONLY to engine-generated color.** A `baked` look may use
ANY colors the author bakes in — including orange/yellow — because it bypasses the engine.

`baked` looks (current + examples):
- `rt_drop_white_aggressive` / `rt_post_drop_white_shatter` (white impact pair).
- `buildup_white_*` and any cue-defined white buildup. **Buildups follow the cue** (no hue freeze).
- The freestyle **nebula** looks — keep `groove_freestyle_nebula` as `baked` (signature) AND add an
  `engine` variant that follows the palette. **BOTH exist** (operator decision). See §12.
- Any hand-authored signature (e.g. a "red→orange→white burst → red segmented pulsate" cue: must be
  `baked` because it contains orange; its two-phase animation is internal to the look).

NOTE: source is by **look**, not by UP marker. An UP that resolves to `groove` (no drop within ~32
beats — §2 Phrase-section model) fires a groove look; if that look is `engine` it **is colored** by
the palette. Only `baked` looks keep fixed color.


Mechanism: a config set `color_engine.exempt_looks` (or a per-look `"color_locked": true` flag).
Exempt looks are skipped in §2 step 1.

---

## 6. DIY (cloud) scenes — 27 in live config
DIY/cloud scenes (`action: diy_scene`, `backend: cloud_diy`) have **baked color** and cannot be
recolored. Handling:
- **Tag each DIY scene with its baked color** (a `p` value or named stop) via a new per-look field
  (e.g. `"diy_color": "blue"`), OR a config map `color_engine.diy_color_tags`.
- At selection, a DIY look is **eligible only if its tag is within the current allowed range**
  (anchor ± spread). On a green-anchored stretch, a red-baked DIY scene is simply not picked.
- **Needs from operator:** a color tag for each of the 27 DIY scene_refs (approve a proposed map).

---

## 7. Configurability (new config block)
All under a new top-level `color_engine` object in `config/led_look_director.json`:

```jsonc
"color_engine": {
  "enabled": true,
  "phase": 1,                      // 1 = per-cue step, 2 = + fades
  "scale_stops": {                 // RGB anchors for the linear scale (overridable)
    "green":  [0,255,0], "cyan":[0,255,255], "blue":[0,0,255],
    "purple": [160,0,255], "magenta":[255,0,160], "red":[255,0,0]
  },
  "palette_dwell_tracks": 4,       // avg tracks held on a palette (group size / cohesion)
  "big_shift_chance": 0.25,        // P(palette switch) on a detected big drop
  "big_shift_weight_bias": 1.0,    // >1 favors rarer "dramatic" palettes on a drop-snap
  "drama_by_role": true,           // wider per-cue spread for drops than grooves
  "role_spread": { "drop": 0.35, "groove": 0.12, "ambient": 0.10 },
  "step_within_section": { "drop": false, "post_drop": true, "groove": true },
                                   // hold color across a run, or re-roll per repeated marker
  "fade_beats": 4,                 // Phase 2 only
  "exempt_looks": ["rt_drop_white_aggressive","rt_post_drop_white_shatter","..."],
  "diy_color_tags": { "23259104": "blue", "...": "..." },
  "set_seed_mode": "random",       // random | fixed:<int>

  // §7a — the palette library. Fully customizable: add/remove/rename, set range,
  // white blend (0..1), per-cue spread, and weight (relative pick frequency).
  // Per palette: range, white blend, per-cue spread, weight (pick frequency),
  // optional dwell override (tracks held), and focus_modes (per-track character).
  "palettes": {
    "blue_cyan":         { "range": ["cyan","blue"],     "white": 0.0, "spread": 0.10, "weight": 14,
                           "dwell": 4, "focus_modes": { "mono": 3, "lean": 3, "full": 2 } },
    "red":               { "range": ["red","red"],       "white": 0.0, "spread": 0.10, "weight": 9,
                           "dwell": 6 },                                   // red lingers longer
    "green":             { "range": ["green","green"],   "white": 0.0, "spread": 0.08, "weight": 4,
                           "dwell": 5 },                                   // green can linger too
    "red_white":         { "range": ["red","red"],       "white": 0.4, "spread": 0.10, "weight": 3 },
    "cyan_blue_purple":  { "range": ["cyan","purple"],   "white": 0.0, "spread": 0.22, "weight": 3,
                           "focus_modes": { "mono": 2, "lean": 3, "full": 3 } },
    "purple_pink_white": { "range": ["purple","magenta"],"white": 0.5, "spread": 0.15, "weight": 1 }
  }
}
```
`dwell` defaults to the global `palette_dwell_tracks` when omitted. `focus_modes` defaults to
`full` (whole-range roam) when omitted.
Per-cue color = roll within the **current palette's** `range` (± its `spread`), then blend in
`white` (and the global `drama_by_role`/`role_spread` may widen drops). Weights are relative, so
`blue_cyan`(10) + `red`(10) dominate, the three `3`s show up occasionally, `purple_pink_white`(1)
very rarely — matching the stated distribution. Engine is fully **disable-able**
(`enabled:false` → inject nothing → current behavior preserved).

---

## 8. Live control surface (future — design hooks now, wire later)
For a dedicated lighting operator. Build the engine with a clean control API so the transport
(MIDI / menubar / IPC) bolts on without touching the color logic:

- `shift()` — retarget anchor to a new random distant palette **now** (manual dramatic shift).
- `lock()` / `unlock()` — freeze / release the current palette across the group (suppresses drift
  + drop-snap while locked).
- `set_palette(p_or_name)` — jump to a specific palette now.
- `queue_palette(p_or_name)` — **stage a palette** to take effect on the **next track change**
  (default) or next big drop (configurable). Cleared once applied. (Requested 2026-06-15.)

Transport options (later): MIDI pad/knob (fits existing LaserDirector MIDI path) or menubar. Not in
the first build — but the engine API and state (`lock`, `queued_palette`) are designed in from day
one so the live layer is additive.

---

## 9. Knowns / assumed / unknowns
- **CONFIRMED:** renderer generic effects honor `params["color"]`; EDM effects don't (need the
  prefer-injected change); white effects are hardcoded/exempt; injection seam is state_manager
  pre-trigger; `LEDLookDecision.params` is the carrier; 27 DIY scenes exist.
- **ASSUMED:** big-drop detection already available to state_manager at trigger time (smart_drop /
  anlz_drops) — **verify** the exact signal/flag before build.
- **ASSUMED:** `cue_index` / a stable per-cue counter is derivable in state_manager for seeding —
  **verify**; if not, derive from (role, beat bucket).
- **UNKNOWN / needs operator input:** (a) confirm scale-stop RGBs; (b) approve `diy_color_tags` for
  all 27 DIY scenes; (c) confirm default knob values feel right (tunable post-build).
- **UNKNOWN:** Phase 2 fade home (effect-side vs adapter-side) — defer to Phase 2.

## 10. Test plan (Phase 1)
- Engine unit tests: drift advances per track & bounces at ends; lock freezes; drop-snap retargets
  with seeded probability; per-cue offset deterministic for fixed seed, varies across cues/plays;
  white_chance produces white; p→RGB never yields orange/yellow (assert hue band) across the range.
- Injection tests: exempt looks receive no color; EDM effect prefers injected color and falls back
  to suffix logic when absent; DIY eligibility filters by tag vs anchor range.
- Regression: `enabled:false` reproduces current output exactly.
- Live: restart bridge (one process), play a set, confirm cohesion over a run, a drop-snapped
  dramatic shift, per-cue variety, white accents, and white-exempt buildups/aggressive drop.

## 12. Authoring cues against the engine

### Motion/color decouple — the renderer architecture (adopted 2026-06-15)
Engine effects **separate motion from color** so coloring is uniform and the structure invariant is
automatic. An `engine` effect returns a **motion field**, not RGB:
- per pixel: `(intensity: float 0..1, slot_id: int)`. `intensity` = the movement (comet shape,
  strobe envelope, sparkle brightness). `slot_id` = which color role the pixel belongs to (0,1,2…).
A single **universal colorizer** then maps `slot_id → color` and multiplies by `intensity`:
- **single color** → all slots = injected `color`.
- **dual** → slot 0 = `color`, slot 1 = `color2`.
- **multi (N)** → slot n = stop n of the injected stop list.
- **gradient** → slot encodes strip position → mapped through the palette range.

This makes the **structure invariant automatic** (color cannot alter intensity/geometry — they're
separate return channels) and **eliminates C1/C2**: no per-effect color classification, no param-key
mismatch — one motion→color contract. Existing messy effects map cleanly: the 3/4-blue·1/4-cyan
burst emits slot0 for the "blue" bursts and slot1 for the "cyan" ones (ratio/motion preserved;
colorizer paints slot0/slot1 from the palette → 3/4·1/4 of whatever two palette colors); the
cyan/white strobe (`:531`) → slot0/slot1.

A **`baked`** effect supplies its OWN slot→RGB map (or returns RGB directly) and bypasses the
colorizer — that's the opt-out for white/nebula/signature looks (and the only place orange may live).

> Cost: bigger upfront refactor (rewrite each `engine` effect to emit `(intensity, slot)` instead of
> RGB) vs. ~6 targeted tint edits. Adopted anyway — correct foundation, automatic invariant, and new
> cues become trivial (describe motion + slots, inherit all coloring).

### Recipe — a new `engine` cue
1. Write the effect to emit a **motion field** `(intensity, slot_id)` per pixel — geometry only,
   no color. Use slot 0 for single-color; add slots 1,2… for multi-color structure.
2. Register the name: add to `_edm_dispatch` (exact-name branch) or a prefix family, add to
   `EDM_BUILDS`, and to `REALTIME_STROBE_EFFECTS` if it strobes (so `allow_strobe` is enforced).
3. Add the config look with `backend: realtime_razer`, `action: realtime`, `scene_ref: <effect>`,
   `color_source: "engine"`, a `fallback`, and `safety_class`. The colorizer handles the rest.
4. Tests: **structure-invariant** (render at two injected colors → identical intensity/slot field,
   only RGB differs — automatic with this architecture but assert it) + determinism (same
   seed/frame/beat ⇒ same field).

### Recipe — a new `baked` cue
1. Paint whatever colors you want (including orange/yellow — the engine never touches baked looks).
2. Register the name as above; set the config look `color_source: "baked"`.
3. No color-injection test needed; just determinism + frame-shape tests.

### Multi-color & gradient looks
Looks aren't limited to one color.
- **Baked gradient:** author a fixed stop list (e.g. `params:{ "stops": [[0,0,255],[0,255,255]] }`),
  `color_source: "baked"`. Renderer interpolates across the strip. Always those colors. Any number
  of stops; may include orange/yellow (engine never touches baked looks).
- **Engine gradient:** `color_source: "engine"`; the engine injects the **current palette's
  focus-window range** as gradient endpoints (`color`=focus-low, `color2`=focus-high) — or N sampled
  stops via `params["gradient_stops"]` when `gradient_stop_count` > 2. The effect interpolates
  between them across the strip. Result: ONE gradient look renders blue↔cyan in `blue_cyan`,
  red↔pink in `red_white`, all-purples in `purple_pink_white`, etc. — your three gradient examples
  from a single cue. Per-track focus controls gradient width (full=wide, mono=near-single-color).
  Structure invariant holds: gradient positions are fixed; only the stop hues change with palette.

### Nebula (both variants — operator chose BOTH)
- Keep `groove_freestyle_nebula` as `baked` (signature purple/magenta + cyan/white moment).
- Add an `engine` variant (e.g. `rt_nebula_palette`) whose bg + comet hues read `params` so it
  follows the active palette. Both can live in the bank; director picks per role/bank as usual.

## 13. Failure modes & mitigations (adversarial review 2026-06-15)

### Critical (block/break on deploy)
- **C1 Per-effect tintability (CONFIRMED) — SUPERSEDED by the motion/color decouple (§12).** EDM
  effects are mixed: single-color (`groove_chase_blue`), dual-hardcoded
  (`_drop_center_burst_blue_cyan`/`_post_drop_center_comet_blue_cyan` = 3/4 blue·1/4 cyan;
  `_post_drop_chase` = cyan/white alt, `govee_frame_renderer.py:531`), white (baked). Rather than
  classify+tint each, **rewrite each `engine` effect to emit a `(intensity, slot)` motion field** and
  let the universal colorizer handle single/dual/multi/gradient (§12). The dual-hardcoded effects map
  to slot0/slot1; ratios/motion preserved. This is the chosen approach.
- **C2 Param-key contract — DISSOLVED by §12.** No more `color`/`color2` vs `color_a`/`color_b` vs
  `stops` per-effect mismatch: effects emit slots, the colorizer owns the single source of color
  truth. (Generic legacy effects can keep their param keys behind a baked tag if not refactored.)
- **C3 `color_source` default flips behavior (migration).** Default `engine` means every existing
  chase follows the palette the moment the engine turns on; whites/nebulas/aggressive break unless
  tagged `baked` first. → Keep `enabled:false` until §14 migration is complete.
- **C4 DIY eligibility can empty a bank (CONFIRMED).** Palette with no matching DIY tag → zero
  candidates for an all-DIY role. → Eligibility MUST guarantee ≥1 fallback (realtime fallback always
  eligible, or relax filter when the candidate set is empty).
- **C5 Config validation (CONFIRMED).** `load_..._from_dict` disables the WHOLE LED config on any
  error (`led_config.py:99-105`). A bad `color_engine` block, all-zero weights (div-by-zero), empty
  `palettes`, or unknown stop name must **disable only the engine**, not all LED automation. → Add
  `_validate_color_engine`; on error, run with engine off.

### High
- **H1 Role/section flap → flicker — RESOLVED (verified).** `_dispatch_led_automation` runs every
  tick but early-returns unless `role_key` changes (`state_manager.py:1626`). `role_key` =
  `f"{active}:{d.load_gen}:{role}:{marker}"` (`:2211-2293`), and `marker` already uses a monotonic
  `phrase_seq` (WI-1/WI-2) to neutralize A→B→A oscillation. → **Seed color on `role_key`**: the
  engine's "section_id" IS `role_key`; no separate debounce needed. The 32-beat groove cycle is
  already encoded as `:c{cycle}` (`LED_DEFAULT_GROOVE_CYCLE_BEATS`); per-track seed = `d.load_gen`
  (always present; `content_id` only needed for cross-session-identical coloring of the same track).
- **H2 Active-deck flips mid-blend.** Key focus on the active deck's filepath; decrement dwell only
  on genuine new-track load, not deck swaps (`self._os.active_deck`).
- **H3 Multiple drop sections/track → multiple snaps → cohesion loss.** Cap to one snap per track
  (or snap cooldown).
- **H4 Snap re-picks current palette = invisible.** Exclude current palette from snap re-selection.
- **H5 Missing content_id/beatgrid.** Seed fallback = filepath hash; no beats → hold (no stepping).

### Medium
- **M1** Bound `big_shift_weight_bias` so weight-1 stays rare even on snaps.
- **M2** Enforce min hue separation for dual-color looks (mono focus → identical colors → static).
- **M3** Live precedence: lock > queued > snap > drift.
- **M4** Assign breakdown/`low` role a calm color treatment.
- **M5** Separate RNG domain for color vs effect geometry.
- **M6** Bridge restart re-seeds mid-set (accept, or persist `set_seed`).
- **M7** White-blend + strobe: keep high-impact cooldown; cap brightness on white-blended strobes.

## 14. Migration checklist (do BEFORE enabling the engine)
1. Tag every existing look `engine` or `baked`. Tag all whites/nebulas/aggressive/signature `baked`.
2. Rewrite each `engine` effect to emit a `(intensity, slot)` motion field; wire the universal
   colorizer (§12). Dual-hardcoded effects → slot0/slot1. Leave un-refactored legacy effects `baked`.
3. Add `_validate_color_engine`; confirm a malformed block disables only the engine (C5).
4. Add DIY color tags for all 27 scenes; verify no palette can empty a bank (C4).
5. Ship with `color_engine.enabled=false`; flip on only after the above + structure-invariant tests
   (§12) pass and a live dry-run looks right.

## 11. Open decisions before build
1. Confirm the locked model (§1) is final.
2. Approve / edit the **palette library** (§7a) — names, ranges, white, weights.
3. Provide / approve the 27 DIY color tags (§6).
4. Approve default knob values (§7) or adjust.
5. Confirm Phase 1 first (step), Phase 2 (fade) after live validation.
