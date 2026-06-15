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
piecewise-lerp between adjacent stops. White is injected as a separate decision (replace hue with
(255,255,255)), never a point on `p`.

> **RELAXED (operator 2026-06-15): orange/yellow as a brief transition pass-through is acceptable.**
> Palettes still never *choose* orange/yellow as resting colors, but fades/gradients/slot-blends MAY
> cross them. So interpolation can be plain **RGB lerp** — no position-space routing required, no
> no-orange-band test. (Position-space interpolation remains optional if a smoother perceptual path
> is ever wanted, but it is no longer a correctness requirement.)

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
Color is rolled per section, keyed on the existing **`role_key`** (`state_manager.py:2211`,
`f"{active}:{d.load_gen}:{role}:{marker}"`) — dispatch only (re)triggers when it changes (`:1626`).
NOTE: for groove/post_drop the `marker` embeds `:c{cycle}`, so seeding on the WHOLE key auto-steps
every 32-beat cycle. To honor `step_within_section=false` (hold), the engine must **decompose
`role_key`** into a stable section part (drop+role+anchor/seq → hold) and the cycle part (→ step),
not hash the whole string. Lucky alignment: drop has no `:c{cycle}` → naturally holds; groove/
post_drop have it → naturally step (matches the defaults), but the config flag needs the split. The 32-beat groove re-cycle is already
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
- "Big drop" = the **Nth drop section of the track**, where N ∈ `snap_eligible_drop_indices`
  (default `[2,3]` — the 2nd/3rd UP→CHORUS). A per-track drop-section counter increments on each new
  DROP section and resets on track load (`load_gen` change). The 1st drop is never a snap target;
  the later drop is chosen because the track is being mixed out, so the shift sets up the next track.
  No drop-energy signal needed (supersedes A11).
- Evaluated **once per eligible DROP section** (at its first trigger), NOT per CHORUS marker.
- Fires **rarely** even when eligible: probability `big_shift_chance` (default low, e.g. 0.25), so
  it does NOT always hit the 2nd/3rd drop. Re-select by weight, biased toward rarer palettes via
  `big_shift_weight_bias`; exclude current palette (H4). The new palette's color **slams** on that
  drop (drops snap, `fade_beats=0`); subsequent low-energy cues then fade within it.
- `lock=True` suppresses drop-snaps.

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

> **CORRECTED 2026-06-15 (code-grounded review). §15 is authoritative where it differs from
> the bullets below — several line numbers and the "EDM change" / "render unchanged" claims here
> were wrong or incomplete. Read §15.0 before implementing.**

- **Injection seam:** in `state_manager._dispatch_led_automation`, after `decision` is finalized
  (from `_led_look_director.tick` OR `_consume_led_committed_drop_decision`) and **before**
  `self._led_scene_adapter.trigger(decision)` at **`state_manager.py:1688`**. (The earlier
  `:1345 / :1490` refs were WRONG — those are the *manual* and *smart-drop-blackout* dispatchers
  and must NOT be engine-colored. See §15.0.) Build a merged params dict
  `{**decision.params, **computed}` and rebuild via `dataclasses.replace` (`params` is a frozen
  `Mapping`). MERGE — never replace — so `sync_mode`/`beat_division` survive (`_spec_from_decision`
  reads them from params, `led_dispatch_coordinator.py:211-212`).
- **Renderer — generic effects:** already honor `params["color"]` / `color_a` / `color_b`
  (`govee_frame_renderer.py:192–283`). No change needed.
- **Renderer — `groove_chase_*`:** ALREADY honor injected `params["color"]` — they render via the
  comet/overlap path (`render_comet`, `govee_frame_renderer.py:938`; allowlisted at `:902`). No
  change needed (this corrects the original "all EDM effects ignore params" claim).
- **Renderer — `drop_chase_*` / `post_drop_chase_*`:** ignore params (`_edm_color_for_look` inside
  `_drop_chase`/`_post_drop_chase`, `:399/:418`). **M1 change (the ONLY M1 renderer edit):** prefer
  `params["color"]` when present, else fall back to suffix logic.
- **Renderer — fully-hardcoded duals** (`drop_center_burst_blue_cyan` `:337`,
  `post_drop_center_comet_blue_cyan` `:361`): do NOT call `_edm_color_for_look`; color is woven into
  per-pixel math. NOT tintable by the M1 fix → **baked in M1**, converted via the slot refactor in
  **M2** (§15.1).
- **Renderer — white effects:** `drop_white_aggressive`, `post_drop_white_shatter`,
  `buildup_white_*` hardcode white and read no color → exempt automatically. No change.
- **Decision params flow:** `LEDLookDecision.params` (`led_models.py:158`) → `_spec_from_decision`
  (`led_dispatch_coordinator.py:208-215`) → `EffectSpec.params` → renderer. CONFIRMED for
  `realtime_razer`. NOTE: `render()`'s signature is **unchanged in M1** but **gains an `abs_beat`
  kwarg in M2** for fades (§15.4) — the original "Unchanged" was wrong for Phase-2.

---

## 4. Transition fade (phased)

User wants the palette to **fade ~4 beats after a master change**, not hard-cut.

**Fade is role-dependent and CORE (operator requirement 2026-06-15).** Color transitions interpolate
over `fade_beats_by_role`, where `0` = instant snap. Same mechanism for within-track cue transitions
AND cross-track transitions:
- **Low-energy roles fade** — breakdown (matters most: breathing/slow looks make hard jumps
  obvious), ambient, groove, post_drop. e.g. breakdown blue→cyan glides.
- **Drops snap** (`fade_beats=0`) — the impact must slam, not fade in.
- **Strobe/fast looks** — a hue fade is imperceptible at speed, so they just fade too; no
  special-casing needed.

**Mechanism — feasible but the "no architectural change / one wiring detail" was an
UNDERSTATEMENT (corrected — see §15.4).** `govee_realtime_runner._tick_once` computes a true
absolute beat `abs_pos = anchor.abs_beat_pos + …` (`:268`) every frame, BUT it does NOT pass it to
the renderer — `_compose_frame` hands `render(beat_pos=ir.local_beat …)` (`:342-347`), and
`ir.local_beat` **resets to ~0 on every retrigger/spawn** (`beat_sync_engine.py:193-194`). A fade
keyed on a stamped absolute `fade_start_beat` vs this instance-local clock would start at the wrong
time. **Resolution (§15.4):** do NOT stamp an absolute `fade_start_beat`. Stamp only
`(color_from, color_to, fade_beats)`; the colorizer SELF-ANCHORS by capturing the runner's
`abs_pos` at spec-configure time (already available — passed to `_engine.configure(abs_beat=abs_pos)`
at `:288`) and interpolates `t=(abs_pos−applied_abs_beat)/fade_beats`. This needs `abs_pos` threaded
into `_compose_frame`→`render`/`render_comet` (a real, modest signature change — NOT zero). Also:
color/fade params MUST be excluded from the dedup `_signature` (`:404`) or every color update resets
motion (H1/§15.4). Orange-crossing allowed (§1) → plain RGB lerp. **M2 only.**

**Phasing reconsidered:** because low-energy fades (breakdown) are a stated requirement, the fade is
NOT optional polish — recommend building it into v1 rather than shipping stepping-only. (If a smaller
first cut is still wanted, stepping-only is valid but will hard-cut breakdown color, which the
operator specifically does not want.)

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
**Default rule: a buildup DIY is `white` unless its name says otherwise** (operator 2026-06-15).
The rainbow DIY (`drop_diy_rainbow_sparkle`) is a **big-drop signature** — a baked look eligible on
the 2nd/3rd drop moment (§2 Drop-snap), not palette-colored.

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
  "snap_eligible_drop_indices": [2, 3], // which Nth drop section of a track can snap ("big drop")
  "big_shift_chance": 0.25,        // P(palette switch) on an ELIGIBLE drop section (rare even so)
  "big_shift_weight_bias": 1.0,    // >1 favors rarer "dramatic" palettes on a drop-snap
  "drama_by_role": true,           // wider per-cue spread for drops than grooves
  "role_spread": { "drop": 0.35, "groove": 0.12, "ambient": 0.10 },
  "step_within_section": { "drop": false, "post_drop": true, "groove": true },
                                   // hold color across a run, or re-roll per repeated marker
  "fade_beats_by_role": { "drop": 0, "buildup": 0, "breakdown": 4, "post_drop": 2,
                          "groove": 2, "ambient": 4 },  // 0 = snap; low-energy roles fade
  "exempt_looks": ["rt_drop_white_aggressive","rt_post_drop_white_shatter","..."],
  // DIY color tags (eligibility = tag fits current palette range). Keyed by look name.
  // ✅ inferred from name; ⚠️ guess; ❌ NEEDS OPERATOR INPUT.
  "diy_color_tags": {
    "groove_diy_red_chasing": "red", "groove_diy_blue_sparkle": "blue",
    "groove_diy_bright_white_chase": "white", "buildup_diy_white_sparse": "white",
    "buildup_diy_3_white_chase": "white", "buildup_diy_white_chasing": "white",
    "buildup_diy_red_sparkle_dim": "red", "drop_diy_1_red_white_chase": "red+white",
    "drop_diy_2_cyan": "cyan", "drop_diy_4_blue_cyan": "blue+cyan", "drop_diy_5_red": "red",
    "drop_diy_green_sparkle": "green", "drop_diy_pink_red_sparkle": "pink+red",
    "breakdown_1_red": "red", "breakdown_cyan_stack": "cyan", "breakdown_green_snake": "green",
    "ambient_pb_halves": "purple+blue",        // ✅ confirmed
    "buildup_diy_sparse": "white", "buildup_diy_2": "white", "buildup_diy_b1": "white", // ✅ confirmed
    "drop_diy_rainbow_sparkle": "BIG_DROP_SIGNATURE", // ✅ baked signature, eligible on big-drop moment
    "groove_diy_groove": "TODO", "groove_diy_groove_2": "TODO", "groove_diy_groove_3": "TODO",
    "groove_diy_groove_5": "TODO", "drop_diy_3": "TODO"   // ❌ operator can't access looks yet
    // room_blackout: excluded (blackout fallback, always available)
  },
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

### Audit additions (self-review 2026-06-15)
- **A6 p-space interpolation — DROPPED (operator OK with orange pass-through 2026-06-15).** Plain
  RGB lerp is fine for fades/gradients/slot-blends; palettes still don't pick orange/yellow as
  resting colors. No no-orange-band test needed.
- **A7 role_key decomposition for hold-vs-step.** See §2 — split `role_key`, don't hash whole.
- **A8 Fade is CORE & role-dependent (RESOLVED §4).** Low-energy roles (breakdown/ambient/groove/
  post_drop) fade via `fade_beats_by_role`; drops snap (0). Build fade into v1 (not deferred).
- **A9 Refactor scope — QUANTIFIED.** 39 named realtime effects (29 EDM + 10 generic). Breakdown:
  ~10 generic ALREADY read `params["color"]`/`color_a`/`color_b` (minimal change); ~10 baked (white
  buildups/aggressive pair + 4 nebulas + signatures → tag only, no color rewrite); ~15–19 actual
  `(intensity, slot)` rewrites (groove/drop/post_drop chases, bursts, comets). Smaller than the
  earlier "~30+".
- **A10 DIY tagging is partly inferable.** Many DIY looks carry color in their name
  (`groove_diy_red_chasing`, `groove_diy_blue_sparkle`, `..._bright_white_chase`,
  `buildup_diy_white_sparse`) → pre-fillable. Opaque ones (`groove_diy_groove`, `ambient_pb_halves`,
  raw-ID names) need operator input.
- **A11 "Big drop" snap — RESOLVED.** "Big drop" = the Nth drop section of the track
  (`snap_eligible_drop_indices` default [2,3]), counted per-track (reset on `load_gen`). No
  drop-energy signal needed. Fires rarely even when eligible. See §2 Drop-snap.
- **A12 Manual override + color (UNDEFINED).** Decide whether a manually-forced look is colored by
  the engine or honored as-authored (likely: honor its own `color_source`).
- **A13 Dwell "new track" hook — SUPERSEDED by §15.2 (the `_on_track_loaded` hook was WRONG).**
  `_on_track_loaded` fires on the **idle** deck during a normal mix (next track is loaded on deck B
  while deck A is still audible), and the audience-facing switch happens later via
  `_on_master_changed` (`:2297`) which fires **no** load event. So an active-deck-gated
  `_on_track_loaded` hook would essentially never advance the journey during real mixing (B2).
  **Resolution (§15.2):** the engine is DISPATCH-DRIVEN — it detects a new audible track from the
  `(active, d.load_gen)` pair visible at the injection seam (`:1688`), with a small recent-keys
  deque to absorb master flaps. No event hook needed.

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

---

## 15. Implementation-Readiness Amendments (2026-06-15, post code-grounded review)

This section RESOLVES the blockers found in adversarial code review and is **AUTHORITATIVE where it
conflicts with §1–§14**. Verified against the live tree: `state_manager.py` (3853L),
`govee_frame_renderer.py` (991L), `govee_realtime_runner.py` (406L), `led_dispatch_coordinator.py`,
`led_config.py`, `led_models.py`. Line numbers are as of this commit; treat them as anchors, not
guarantees — match on symbol names.

### 15.0 Verified integration facts (ground truth)
- **decision.params → renderer is REAL** for `realtime_razer`: `_spec_from_decision`
  (`led_dispatch_coordinator.py:208-215`) does `params = dict(decision.params or {})` →
  `EffectSpec(params=params)`. The renderer honors it. BUT `EffectSpec.seed` derives from the LOOK
  NAME (`:216`), not params — so the engine must compute FINAL colors itself and inject them; it
  cannot rely on the renderer's per-look seed for per-cue variety.
- **Injection seam = `state_manager.py:1688`** (in `_dispatch_led_automation`, before
  `self._led_scene_adapter.trigger(decision)`). `decision` may come from the director (`:1643`) OR
  `_consume_led_committed_drop_decision` (`:1640`) — inject AFTER it's finalized, covering both.
  The `:1345`/`:1490` refs in earlier sections are the **manual** and **smart-drop-blackout**
  dispatchers and must never be engine-colored.
- **4 trigger sites:** manual `:1345`, blackout `:1490`, automation `:1688` (THE seam),
  idle_ambient `:1825`. idle_ambient uses its own role namespace; **M1 does not color it** (baked);
  revisit in M2.
- **Renderer color reality:** generic effects (`:192-283`) and `groove_chase_*` (via
  `render_comet`, `:938`) ALREADY honor injected color. Only `drop_chase_*`/`post_drop_chase_*`
  need the M1 prefer-params fix. The two fully-hardcoded duals (`drop_center_burst_blue_cyan` `:337`,
  `post_drop_center_comet_blue_cyan` `:361`) are baked in M1, slot-refactored in M2.
- **Config strictness:** static look `params` are allowlisted (`led_config.py:387-390`); ANY unknown
  key → `_validate` error → the WHOLE LED config disabled (`:99-105`). Runtime-injected params are
  NOT validated (validation is config-load only). LEDLook (`led_models.py:42-53`) carries no
  `color_source`/`diy_color` today.

### 15.1 — B1 RESOLVED: motion field is a per-pixel SLOT-INTENSITY VECTOR (not a scalar pair)
§12's `(intensity, slot_id)` scalar is lossy under additive folding (two different-slot comets on
one pixel collapse to one). Replace with: an `engine` effect returns, per pixel, a fixed-width
vector `intensity[slot]` for slots `0..K-1` (`MAX_SLOTS`, default 4).
- Fold: `fold_additive` sums per-slot intensities (unclamped).
- Colorize: `rgb[px] = clamp( Σ_slot slot_color[slot] · intensity[px][slot] )`.
- This EQUALS today's "colorize-then-additively-fold" because each slot color is constant and both
  ops are linear → single-slot effects are **bit-identical**; multi-slot match within ±1/channel
  (clamp order), proven by golden tests (15.4 / §10 H4).
- **Both** render paths (`render`, `render_comet`) route through the SAME colorizer; `_comet_frame`
  emits slot-intensity (slot from caller, e.g. spawn-index parity) instead of pre-multiplied RGB.
- **M2 ONLY.** M0/M1 do not touch the motion field.

### 15.2 — B2/B3 RESOLVED: engine is dispatch-driven; track + drop-section detection self-contained
The engine advances ONLY from the automation dispatch (`:1688`), which already carries `active`
(the audible deck), `d.load_gen`, and `d.meta.content_id`. It does NOT hook `_on_track_loaded`
(fires on the idle deck — B2) and does NOT reuse `_led_drop_impact_count` (reset mid-track by
`_clear_led_drop_lifecycle` — B3).
- **Audible-track key** `= (active, d.load_gen)`. Keep `current_track_key` + a recent-keys deque
  (len 3) to absorb A→B→A master flaps. On a key not recently seen: decrement `dwell_remaining`,
  reseed per-track focus, reset `drop_section_index = 0`, and re-select palette if `dwell ≤ 0`.
- **drop_section_index** per `current_track_key`: increment when a drop-role injection arrives whose
  structured `section_id` (15.6) differs from the last drop section seen for this track. Snap
  eligibility (`snap_eligible_drop_indices`) reads this index. Survives mid-track lifecycle clears.

### 15.3 — H2 RESOLVED: seeds are hashed, never raw `load_gen`
`current_track_seed = blake2b(f"{set_seed}:{active}:{content_id or filepath or load_gen}")` (stable
64-bit). Raw `load_gen` is forbidden (deck1#3 == deck2#3 → identical focus; low entropy). Prefer
`content_id` (cross-session-stable), then `filepath`, last resort `load_gen`. Per-cue seed
`= hash((current_track_seed, section_id[, step_index]))`. Color RNG is a SEPARATE domain from
effect-geometry RNG (M5/N8).

### 15.4 — B4/H1 RESOLVED: a DEDICATED color-anchor clock; color excluded from the motion signature
> Review correction: `applied_abs_beat` is NOT retrievable today (the runner stores only
> `_active_applied_monotonic`, a monotonic *time*, at `:279`; `configure` consumes `abs_beat` into
> the clock and discards it). AND because we exclude color from the motion signature (below), a
> color-only fade never reaches `configure` — so "configure time" is the WRONG anchor. Resolved with
> a separate color-anchor clock:
- **Two signatures in the runner (M2):**
  - *motion signature* = `_signature` (`:404`) with color/fade keys EXCLUDED →
    `{color, color2, color_a, color_b, color_from, color_to, fade_beats, gradient_stops,
    slot_colors}` (NOTE: `color_a`/`color_b` included — M1 injects them into the two generic dual
    effects, `:248-249`). Gates `_engine.configure` (motion reset). Color-only changes do NOT reset
    motion.
  - *color signature* = those excluded keys only. When the color signature changes, the runner
    captures `self._color_applied_abs_beat = abs_pos` (the live abs beat at the moment the new color
    took effect). This is the fade anchor.
- **Fade clock:** colorizer interpolates `t = clamp((abs_pos − color_applied_abs_beat)/fade_beats,
  0, 1)`. The engine stamps only `color_from, color_to, fade_beats` (no absolute `fade_start_beat`,
  avoiding cross-component frame mismatch). The colorizer stays PURE — it receives `(abs_pos,
  color_applied_abs_beat)` as inputs; the runner owns the tiny capture state. Requires threading
  `abs_pos` + `color_applied_abs_beat` into `_compose_frame`→`render`/`render_comet`.
- **`set_desired`** already propagates new params to the colorizer each tick regardless of the motion
  signature (`:89-91`, read at `:233`), so color updates render without a motion reconfigure.
- **Coordinator dwell-gate note (M2):** the coordinator's WI-3 min-dwell gate is role-keyed and
  suppresses same-role re-dispatch within `min_look_dwell_s` (1.5s, `led_dispatch_coordinator.py:74-87`).
  Discrete `step_within_section` re-rolls ride on `role_key`'s `:c{cycle}` (≥32-beat cadence ≫ 1.5s)
  so they are NOT suppressed; fades do not re-dispatch at all (single trigger, colorizer-interpolated).
  Benign, but M2 must keep step cadence > `min_look_dwell_s`.
- **M1 ships `step_within_section` all FALSE and no fades**, so M1 needs NONE of the above (no second
  signature, no abs_pos plumbing, no anchor capture). All M2.

### 15.5 — B5 RESOLVED: model/config plumbing (M0) — exact contract
- **LEDLook fields:** add `color_source: str = "engine"` and `diy_color: str = ""` to `LEDLook`
  (`led_models.py:42-53`, `compare`-irrelevant); populate in `_build_config` where each `LEDLook` is
  constructed (`led_config.py:893-906`). Unknown look-level keys are already ignored by `_validate`
  (it reads named keys via `look.get`), so adding them won't trip validation — but the dataclass +
  builder MUST be extended to CARRY them, else they're silently dropped.
- **`color_engine` placement (DECIDED):** parse into a new frozen `ColorEngineConfig` dataclass and
  hang it off `LEDConfig` as `color_engine: Optional[ColorEngineConfig] = None` (`led_models.py:109`).
  Parse it **non-fatally** inside `_build_config` via `_parse_color_engine(data) ->
  Optional[ColorEngineConfig]` that runs `_validate_color_engine` internally, and on ANY error logs +
  returns `None` (engine off). `color_engine` errors are kept ENTIRELY OUT of the fatal `errors`
  list that `_validate` feeds (`led_config.py:99-105`), so a malformed block disables ONLY the
  engine, never LED automation. `data.get("color_engine")` is invisible to `_validate` (it reads
  only named keys), so an absent/garbage block cannot disable LED. State_manager reads
  `config.color_engine`; `None` ⇒ inject nothing ⇒ current behavior.
- **`_validate_color_engine` rules (enumerated):** `enabled` bool; `palettes` non-empty dict;
  every palette `weight` ≥ 0 with `Σ weight > 0` (else div-by-zero); every `range` endpoint ∈
  `scale_stops` keys; `white` ∈ [0,1]; `spread` ≥ 0; `focus_modes` weights ≥ 0 with positive sum if
  present; `snap_eligible_drop_indices` list of ints ≥ 1; `big_shift_chance` ∈ [0,1];
  `palette_dwell_tracks` ≥ 1; type-check every field. Any failure ⇒ whole engine off (not partial).
- **`scale_stops` (PINNED — resolves §1-vs-§7 mismatch):** the canonical set is the **6 stops in §7**
  — `green, cyan, blue, purple, magenta, red` (`magenta=[255,0,160]`). §1's 5-row table is
  illustrative; `magenta` is required because `purple_pink_white` ranges `["purple","magenta"]`. The
  validator's allowed-stop set = `scale_stops` keys (config-driven), so range endpoints validate
  against whatever the operator configures.
- **`REALTIME_EFFECT_PARAM_KEYS` (M2, not M0):** extend for any NEW *static* param keys used by
  baked gradient/multi-color looks (`stops`, `color2`, `gradient_stops`, `gradient_stop_count`,
  `slot_colors`) on the effects that accept them — else C5 disables ALL LED. M0/M1 add NO static
  color params, so no allowlist change in M0/M1.

### 15.6 — M1/M6/M2 control & eligibility resolutions
- **role_key decomposition (do NOT string-parse, A7):** `_led_automation_role_key` already computes
  `cycle` as an int before formatting (`:2236/:2269/:2280`). Expose a structured
  `(section_id, cycle)` alongside the string key and have the engine consume the fields — immune to
  `RBSS_LED_PHRASE_MONOTONIC` format toggling (which changes the marker text).
- **Live precedence (M2):** one `resolve_palette_for_event(event, state)` applying
  `lock > queued > snap > drift` in a single place. `queued` is consumed on the next audible-track
  change; if a snap fires while a queue is pending, the queue wins (snap suppressed); `lock`
  suppresses drift + snap + queue-apply. Defaults unlocked/empty in M1.
- **DIY eligibility hooks the DIRECTOR's selection, NOT the `:1688` injection seam (CRITICAL —
  these are two different locations).** Color INJECTION happens at `:1688` AFTER the director has
  already chosen a look. DIY eligibility must filter the candidate set DURING selection inside
  `led_look_director._dispatch_role` (`led_look_director.py:257-305`), at the bank-name list (`:273`).
  Wiring: the engine's current allowed-color predicate must reach the director — add an optional
  `diy_eligible: Optional[Callable[[str], bool]]` (or the current palette range) to `LEDContext`
  (`led_models.py:135-144`), set by state_manager from the engine before/at `tick`. The director
  filters `look_names` by `diy_eligible` for DIY looks (realtime looks always pass — they're
  recolored), reusing the EXISTING empty-subset→full-bank fallback already present for WI-7
  transport-stickiness (`:287-291`).
- **C4 breakdown (CONFIRMED concrete):** the breakdown bank is 3 DIY looks (red/cyan/green) with
  ZERO realtime fallback; a purple/blue palette would empty it. The director filter MUST guarantee
  ≥1 candidate: when the palette filter empties a bank, fall back to the UNFILTERED bank (the same
  `:287-291` pattern). Durable fix (operator follow-up): add a realtime breakdown look. (`pre_drop`
  bank is empty — pre-existing, out of scope.)
- **Concurrency invariant (M5/N8):** the colorizer is PURE over `(params, abs_beat, seed)` and never
  dereferences a live engine object; all color flows by value through `decision.params` (computed on
  the state_manager thread, published to the runner via `set_desired` under lock).

### 15.7 — Milestone decomposition (supersedes §7's `phase` field; reconciles §3 vs §12/§14)
- **M0 — plumbing (low risk, no behavior change).** LEDLook fields + loader + validator (15.5);
  `color_engine` config block + `_validate_color_engine` (engine-only disable). Acceptance:
  config-validation tests (good/bad/empty/all-zero blocks → engine-off, LED still up);
  `enabled:false` is a byte-identical no-op (existing LED tests unchanged).
- **M1 — engine + cheap injection (visible value, NO renderer refactor).** New pure module
  `led_color_engine.py` (palette/dwell/snap/focus; dispatch-driven track+drop detection 15.2; hashed
  seeds 15.3; structured role_key 15.6). Inject `params["color"]` (+`color_a`/`color_b` for the two
  generic dual effects) at `:1688` into `engine`-tagged looks only. Renderer edits: ONLY
  `_drop_chase` and `_post_drop_chase` prefer `params["color"]` — NOTE `_post_drop_chase`
  (`govee_frame_renderer.py:418`) does NOT currently receive `params`, so its signature AND its
  call site (`:767`) must be changed to thread `params` through (slightly more than `_drop_chase`,
  which already has `params`). Director wiring: add `diy_eligible` to `LEDContext` and filter DIY
  looks in `_dispatch_role` with full-bank fallback (15.6). `step_within_section`=hold, no fades.
  Baked: whites, nebulas, both center duals, `twinkle_blue`, all DIY. Acceptance: engine unit tests
  (drift advances per audible track & holds within dwell; lock freezes; snap retargets with seeded
  prob and excludes current palette; per-cue determinism for fixed seed + varies across cues/plays;
  white accents; p→RGB never RESTS on orange/yellow); injection tests (exempt/baked looks uncolored;
  `drop_chase`/`post_drop_chase` prefer injected, fall back to suffix when absent; merge preserves
  `sync_mode`/`beat_division`); director DIY-eligibility always returns ≥1 candidate; `enabled:false`
  regression byte-identical.
- **M2 — motion/slot refactor + fades (risky, gated).** Slot-vector motion field + universal
  colorizer for both render paths (15.1); `abs_pos` plumbing + self-anchoring fades + signature
  exclusion (15.4); `step_within_section` + `fade_beats_by_role`; engine gradient/multi-color looks;
  nebula engine variant. Acceptance: structure-invariant (two injected colors → identical
  slot/intensity field, only RGB differs); golden-frame parity vs the M1 baseline (single-slot
  bit-exact, multi-slot ±1/channel documented); fade interpolation determinism.

**Gate between milestones:** each ships behind `color_engine.enabled`, its own tests green, one live
dry-run OK. M2 starts only after M1 is validated live.
