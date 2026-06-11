---
title: "rb_ss_bridge_v2 — Section-Correct Autoloop Selection"
status: "Planning — grounded against code + operator-confirmed SoundSwitch constraints, 2026-05-31"
repo: "bbuuuiiii04/PYTHON-BRIDGE"
supersedes: "Ultimate Autoloop Intelligence Plan (energy-first framing)"
---

# rb_ss_bridge_v2 — Section-Correct Autoloop Selection

## 1. The real problem

SoundSwitch's autoloop feature **must be on and cycling** for autoloops to play.
Its cycling is global and **ungateable** — only **random** or **sequential**
across the entire autoloop pool. Each autoloop is **8 bars**; when one ends, SS
immediately cycles to the next look on its own.

Consequence: SS can fire a high-intensity look (e.g. a drop autoloop) **during a
groove phrase**, because to SS every autoloop is one undifferentiated pool. That
is the bug — section-blind cycling.

The bridge **can** choose which autoloop fires by sending a MIDI note
(→ IAC Driver Bus 1 → SS). But that control lasts exactly one 8-bar loop; at the
next 8-bar boundary SS randomizes again.

## 2. Hard SoundSwitch constraints (operator-confirmed)

1. Autoloop cycling cannot be disabled — autoloops require it.
2. Cycling cannot be restricted to a bank — random or sequential across
   everything is the only choice.
3. A MIDI note selects *which* autoloop, but does **not** restart/realign SS's
   8-bar loop phase.
4. ⇒ every look-change is quantized to SS's fixed 8-bar grid. The bridge can
   control *which* look fills each 8-bar slot, not the slot timing itself.

## 3. The model

At every **8-bar boundary, on the downbeat**, the bridge re-fires the MIDI note
for a **section-appropriate** autoloop, so SS's random pick never surfaces. The
bridge becomes the selector; SS never freelances.

**Which** look is decided by the current **Rekordbox phrase section**, using the
bridge's existing phrase-following — not a fixed 32-beat assumption:

| Rekordbox section | Look |
|---|---|
| **up phrase** | **groove looks** — full span. "up" is a groove, NOT a build/escalate |
| **32 beats before a drop** | **buildup looks** — existing behavior, keep exactly as-is |
| **chorus / drop** | drop look (on the drop crossing) |
| **down / breakdown** | breakdown looks |
| intro / outro | groove / safe |

So a **128-beat up phrase after a drop = groove looks for ~96 beats, then buildup
looks for the final 32** before the drop. The up label does not mean escalate;
the only escalation is the 32-beat pre-drop window.

> ⚠️ Premise caveat (see §5.1): Rekordbox PSSI does **not** emit a generic "up"
> phrase marker — only buildup/drop/breakdown starts. So this clean up→groove span
> is only realized when a buildup marker actually exists; otherwise the region is
> `"other"` → default groove. The *outcome* is similar (groove), but don't assume
> the segment map distinguishes "up" from plain groove.

Phrase edges quantize to the 8-bar grid (SS limit, ≤8 bars of slop). Drops are
handled on the actual crossing by the existing Smart Drop path (see §4), off the
8-bar grid.

## 4. What already exists (grounded in code)

- **MIDI transport** → IAC Bus 1 → SS: `MidiOutput` (`midi_output.py`),
  `midi_output_port` in `config/laser_director.json`.
- **Laser Director role banks** groove/buildup/drop/breakdown, firing **live**
  (`dry_run=false` confirmed in `/tmp/bridge.log`, 2026-05-27).
- **Rekordbox phrase reading**: `_extract_pssi_phrases` (`anlz_reader.py:227`)
  → `anlz_buildups/drops/breakdowns`; `SmartPhrasingEngine`
  (`smart_phrasing.py`) builds **variable-length** phrase segments
  (each segment runs to the next marker).
- **Phrase re-anchor (beatgrid-locked, handles variable phrase length)**:
  `SmartRearmCoordinator` (`smart_rearm.py`) +
  `send_direct_autoloop_rearm` (`autoloop_controller.py:691`) re-anchor the
  autoloop to a target beat via the beatgrid (clear → reload at target elapsed).
  This is why variable phrase length is **not** a blocker.
- **32-beat pre-drop buildup**: `smart_buildup_active` fires within
  `phrase_lookahead_beats = 32` of the next drop (`smart_phrasing.py:258`;
  `state_manager.py:383` comment: "buildup = 32 beats before Smart Drop").
  **Keep unchanged.**

## 5. The gap (what to build)

**Code-review correction:** the 8-bar re-fire *timer* already exists —
`AUTOLOOP_ARM_PHRASE_BEATS = 32` raises `autoloop_tick_just_fired` every 32 beats
(track-absolute grid, `state_manager.py:1905-1916`), and the Laser Director fires
a fresh phrase-bank scene on that edge (`laser_executor.py:297-303`). **And
section→role→bank routing is also already complete** — `LaserDirector._decide`
emits the correct role per Rekordbox section (drop_crossing P9, post_drop hold
P10, buildup P11, else groove, `laser_director.py:410-495`) and
`LaserSceneExecutor._bank_for_role` / `_choose_bank_scene_locked`
(`laser_executor.py:310-338`) routes that role to the right personality bank. So
the only real code change needed:

1. **Make `same_scene_skip` boundary-aware + scene_type-gated**
   (`laser_executor.py:181-193`). Today it suppresses re-sending an unchanged
   scene — correct as a 200 Hz debounce for *held* roles, but it also suppresses
   the once-per-boundary **re-assertion** the autoloop fix needs (SS randomizes
   the look at each 8-bar end unless the bridge re-sends). Change the skip to
   allow a same-scene re-fire on an autoloop boundary, gated to autoloop-type
   scenes only:
   `skip if same_scene and not is_drop_crossing and not (ctx.autoloop_tick_just_fired and scene_def.scene_type == "autoloop")`.
   `scene_def` is already in scope at the skip block (looked up at `:149`,
   non-None past `:150-157`) — no wiring needed.

   **What "8-bar boundary" means here:** the track's absolute beat grid (beats
   32, 64, 96, … from the track's first beat per the Rekordbox beatgrid). The
   SoundSwitch 8-bar loop boundary coincides with this grid by design because the
   autoloop is armed on the same grid via `next_arm_phrase`
   (`autoloop_controller.py:495-503`, rounds the arm sync beat to a multiple of
   32). So the re-fire lands on SS's loop boundary (seamless), not mid-loop.

   **The `scene_type=="autoloop"` gate is mandatory.** Verified
   `drop_scene`/`post_drop_scene` = `house_drop_1` which is `scene_type:"static"`
   (held — re-firing would restart it). `house_groove_*`/`buildup_1`/
   `breakdown_1` are autoloop (cycle — need re-assertion).

   **Honest scope.** For the house `phrase_bank` (32 distinct entries), rotation
   advances the cursor every phrase tick → consecutive picks differ →
   `same_scene_skip` essentially never fires today, and MIDI is already
   re-asserted every 32 beats. For pure house-groove sections, the fix is a
   **no-op / safety net**. It is materially valuable for: **length-1 banks**
   (every personality's `buildup_bank` / `drop_bank` / `breakdown_bank`), **held
   autoloop roles** (breakdown), and **dubstep's 3-entry phrase_bank**. If
   wrong-section looks persist on house groove after this fix, the cause is
   probably a brief race at the 8-bar boundary (SS auto-advancing a few ms
   before the bridge's MIDI override) — a separate timing concern.

2. **Keep the 32-beat pre-drop buildup window as-is** (`smart_buildup_active` /
   `buildup_lookahead_beats`).

### 5.1 Blocking prerequisites (from code review)

- **Playlist-based personality resolution is entirely dead today, not just for
  dubstep** — `PlaylistCache(RB_DB_PATH)` at `__main__.py:693` uses the default
  `folder_name="PER GENRE"` (`personality_resolver.py:118`), but the real
  Rekordbox folder is **"BY GENRE"** (children: HOUSE, DUBSTEP, TECHNO,
  BASS HOUSE, …). With the wrong name, `PlaylistCache.refresh()` finds nothing →
  no playlist memberships → every track falls through to bpm-band (house 120–130)
  or default house. So everyone *appears* to be house regardless of playlist.
  Fix: `PlaylistCache(RB_DB_PATH, folder_name="BY GENRE")`.
- **`dubstep` also needs an alias.** It currently has `aliases:[]` and zeroed
  bpm band, so even after the folder fix the resolver has nothing to match. Add
  `"aliases": ["dubstep"]` in config; longest-first ordering ensures dubstep
  wins over `"house"` for a track in both. Note: dubstep's banks reference house
  scenes today, so dubstep tracks would get **house looks with dubstep timing**
  (`buildup_lookahead_beats=16`, `post_drop_hold_beats=8`); distinct dubstep
  looks are a later content task.
- **"up → groove" is not in the PSSI data.** `_extract_pssi_phrases`
  (`anlz_reader.py:227`) emits only buildup/drop/breakdown *start* beats — there is
  no generic "up/normal phrase" marker. A long up phrase after a drop is therefore
  not a segment; that region is label `"other"` and falls to default groove anyway.
  Behavior may be acceptable, but the §3 premise that the segment map encodes
  "up vs groove" is wrong — relabel as "default/groove fallback," or add a real
  phrase-kind read.

## 5.5 Timing comes from LaserPersonality — no parallel knobs

Every per-personality timing constant the section→look model needs **already
exists** in the laser personality config and is consumed at runtime. Do NOT
introduce parallel knobs (e.g. a separate `DROP_HOLD`) — they will diverge.

| Model concept | Existing field | house | dubstep | Consumer |
|---|---|---|---|---|
| groove re-fire cadence | `phrase_interval_beats` | 32 | 32 | `laser_director.py:370` |
| buildup window (before drop) | `buildup_lookahead_beats` | 32 | 16 | `laser_director.py:471`; **also** should drive `SmartPhrasingEngine` |
| **drop-look hold / "DROP_HOLD"** | `post_drop_hold_beats` | 16 | 8 | `laser_director.py:436-450` + `_sp_post_drop` |
| drop / transition window | `pre_drop_blackout_beats` | 4 | 8 | `_sp_drop_window`/`_sp_transition_window` |
| breakdown restore | `breakdown_default_restore_beats` | 64 | 64 | `_sp_breakdown_default_restore` |

Key reconciliations:

- **"DROP_HOLD" = `post_drop_hold_beats`.** The laser director already does
  drop → hold `post_drop_hold_beats` → fall through to the groove/phrase look
  (`_decide` P9→P10→`_decide_phrase_default`, `laser_director.py:421-495`;
  confirmed live: `…drop reason=post_drop_hold` then `…→groove reason=default`).
  So "drop look then decay to groove" is **existing behavior**, and this knob is
  **shared with the laser director** — retuning it (e.g. 16→32) changes both.
- **Buildup-window bug (pre-existing).** `SmartPhrasingEngine` uses a hardcoded
  `_sp_phrase_lookahead = 32` (`state_manager.py:383`) while the laser uses
  per-personality `buildup_lookahead_beats` (dubstep = **16**). For dubstep these
  already disagree. Fix: drive `_sp_phrase_lookahead` from
  `personality.buildup_lookahead_beats` so both systems use one source.
- **Tuning note (from sim on a 128-BPM house track):** at the current
  `post_drop_hold_beats = 16`, drop *clusters* (drops <16 beats apart) flicker
  drop↔groove every ~4 bars; `32` chains them smoothly; `64` fully sustains.
  Pick per personality, remembering it also moves the laser post-drop hold.
- **Caveat:** the section→look sim is the *policy* layer; the live executor
  additionally applies `minimum_scene_hold_beats`, phrase-boundary gating, and
  same-scene-skip, which dampen flicker (groove onsets quantize to the
  `phrase_interval_beats` grid).

## 6. Energy / intensity tiers — deferred, probably unnecessary

Choosing groove looks by "energy" is secondary and likely not needed:

- BPM already scales perceived intensity via beat-sync; faster = more frantic for
  free. No separate loops needed for that.
- Grooves are relatively steady; the big dynamics live on the drop/breakdown
  roles, not the groove.
- SS's ungateable cycle means the only control point is the per-8-bar MIDI
  re-fire anyway.

So treat groove looks as **variations**, picked deterministically (round-robin).
Energy-aware picking is optional/future, behind a shadow phase, and is **not**
part of the core fix.

## 7. Unknowns to verify

- Whether the look re-fire currently lands on the 8-bar boundary, or whether SS
  surfaces a random look *between* phrase events today (the core gap — confirm in
  `/tmp/bridge.log` + by watching SS live).
- Exact MIDI timing so the re-fire lands **on** the downbeat (on the grid — not
  early, which would desync the loop) and preempts SS's pick.
- Whether `_extract_pssi_phrases` captures all relevant up/down phrase kinds, or
  misses some `kind`/`mood` combinations.

## 8. Phase 0 — shadow (no behavior change)

At each 8-bar boundary, log: the current Rekordbox phrase section + the look that
*would* fire under the §3 map. Watch SS live for wrong-section looks. Confirms
(a) section detection is correct and (b) where/whether SS surfaces a random
wrong-section look today. Zero behavior change, no new SoundSwitch content
required.

## 9. Loop-design note (operator)

Because the bridge re-fires per 8-bar slot and SS can't be gated, the autoloops
you build should be **section-grouped, individually MIDI-triggerable looks** —
groove looks, buildup looks, drop looks, breakdown looks. Within the groove set,
build **variations**, not intensity tiers (BPM and the steady nature of grooves
make tiers low-value). The drop/buildup/breakdown looks are where deliberate
intensity matters, and those are bridge-fired on their sections.
