---
doc_status: current
truth_level: code-verified for Packages 2-3 and AWR-121; design-intent for anything still unimplemented
last_verified_commit: daa8804
last_verified_date: 2026-07-04
validation_scope: Packages 2-3 plus AWR-121 gesture v2 software-tested; hardware-unvalidated
---

# Stream Deck Palette Control — Design Spec (pre-handoff)

> **Status: PACKAGES 2-3 + AWR-121 GESTURE v2 IMPLEMENTED / SOFTWARE-TESTED.**
> Roles: Claude authored this design (planning); **Codex implemented Package 2 bridge code; Claude
> implemented Package 3 (drop presentation policy, this-repo-instance, 2026-07-04) per an
> operator-sanctioned exception** — see `docs/architecture/drop_presentation_authority.md` for the
> current behavior authority (the acceptance oracle for Package 3) and
> `docs/plans/active/drop_presentation_impl_spec.md` for its implementation spec.
> **Fable reviewed (Phase 1) and expanded (Phase 2) this design on 2026-07-04**
> with operator answers folded in.
> Per AGENTS.md §1, **code wins over this doc** — verify every claim against current code.
> Claims are labelled **confirmed / assumed / unknown / operator-decided**.

This is current truth for Packages 2, 3, and AWR-121 gesture v2. Package 3
(Laser Solo pad, zero-RNG auto-solo tiers, finale guarantee, track personality,
learned-solo memory) is now implemented/software-tested — see
`docs/architecture/drop_presentation_authority.md` for the authoritative ladder and
`docs/subsystems/laser.md` / `docs/subsystems/led_govee.md` for the current code-verified summary.
Track personality and laser-color behavior beyond what those two cards describe remain design-intent
until implemented and software-tested.

---

## Part A — Goal & scope

Give the operator live palette control from the 15-pad Stream Deck (MIDI ch3), driving the **LED
color engine** now and the **laser color engine** when it exists. This is the **M3 "live control
surface"** the color-engine spec already designed (`docs/plans/completed/led_color_engine_spec.md`
§8 :343-356) — we are wiring an already-specified API, not inventing one.

In scope (LED):
- Top-row pads select **color palettes**. The current AWR-121 gesture is tap-toggle
  for queue/unqueue, and long-press (default 0.5 s) for take-and-hold: override-fade
  now plus lock. The old Package 2 v1 two-tap override and dedicated lock pad are
  retired on the physical deck surface.
- A manual-only **`white_sand`** palette (Stream-Deck-only, never auto-selected) that renders LEDs
  white/off-white and drives lasers white.
- **Mixer-style mute pads** (operator-directed 2026-07-04, naming accepted): two per-fixture
  toggles — **LED mute** and **Laser mute** — compose all three room states live: LED-only,
  LED+laser, laser-only (C.8).
- **Drop presentation policy + Laser Solo pad** (operator-directed 2026-07-04, converged via
  brainstorm): **a Laser Solo is never a dice roll** — it fires from the Solo pad, a **Rekordbox
  hotcue tag**, **learned history** of the operator's own presses, a **one-mix BPM gear-shift**
  (≥ +10), or the **night's record runway**; untagged tracks get a fixed **lighting personality**
  from their own structure (lasers on the track's biggest drops, dark on the rest; last true drop
  always at least LED+laser) (C.9). No energy model, zero RNG.
- **Rainbow mode pad** (operator-requested 2026-07-04, "fun crazy mode"): a toggle that remaps
  colors by section — breakdowns/buildups go white/off-white (`white_sand`), grooves/drops/
  post-drops go **rainbow** on LEDs and lasers alike (C.10).
- **Visual feedback**: each pad renders an icon reflecting its palette/action and live state.
- **Pinned pad layout** (operator 2026-07-04): palette pads stay on fixed keys; static-look pads
  move to the bottom row (replaces today's "waterfall" fill — see Part C.1).

Out of scope:
- The **laser color engine itself** (greenfield; deferred until built). This design is laser-*ready*
  but wires LED only in v1.
- The **Stream Deck Phase 2 generic input path** is a **prerequisite**, specced separately
  (`streamdeck_midi_bridge_integration_spec.md` Part F, plan-first / live-critical). This feature is
  the first *additional* binding type on that path, not the path itself.
- The final **`white_sand` LED color** — a Template Lab calibration follow-up, not fixed here.

**Scripted tracks (operator 2026-07-04):** scripted tracks run their own timeline; LEDs are active
only during **breakdown and buildup** windows there (scripted-mode role gating exists in
`led_look_director.py` `scripted_mode` config / `led_dispatch_policy.py:83-143` — *confirmed
mechanism; exact window behavior operator-stated*). Palette control therefore only colors those LED
windows during scripted tracks; lasers stay fully authored (see laser doc Part A).

## Part B — Confirmed evidence (code-grounded, re-verified at `bd96b32`)

- **LED live-control methods exist but are UNWIRED stubs** — *confirmed*. `led_color_engine.py`:
  `lock()` :728, `unlock()` :732, `set_palette(name)` :736 (immediate jump; comment "transport not
  yet wired; pure state mutation stub" :742), `queue_palette(name)` :744 (one-shot, applied on next
  track), `shift()` :749, `snapshot()` :759-768 (exposes `current_palette`/`queued_palette`/`lock`).
  State fields `_lock` / `_queued_palette` / `_current_palette`. Header comment :724-725:
  *"Operator-reserved future LED Pad / Stream Deck controls. Future callers outside StateManager
  must route through BridgeEvents/runtime commands."* No runtime caller; the only non-test caller is
  `tools/led_pad_web.py:528-529` (`set_palette`/`lock`) on its **own local preview engine instance**,
  not the runtime engine.
- **Exactly 5 palettes today**, string-named — *confirmed*. `config/led_look_director.json`
  `/color_engine/palettes` = `blue_cyan, deep_ocean, indigo, violet, crimson` (all `white: 0.0`).
  Identity = the string key into `config.palettes`; enumerated at `led_color_engine.py:283`
  (insertion order). No `white` palette exists.
- **Manual-only exclusion already works via weights** — *confirmed* (was open item 3, now closed).
  `Palette.weight` exists (`led_models.py:64`, default 1.0). ALL automatic selection routes through
  `_pick_palette` (`led_color_engine.py:293` init, `:389` dwell re-pick, `:414` drop-snap, `:751`
  shift) → `_weighted_choice` (:135), where weight 0 gets zero probability mass. `set_palette`
  bypasses weights entirely (:736-741). A 6th palette added to config flows into enumeration
  automatically (:283-286). **`white_sand` = a config entry with `weight: 0` — no engine change.**
- **No "1-track override" concept exists** — *confirmed*. Track-boundary hook = `begin_dispatch`
  (`led_color_engine.py:333`, new-track block **:351-399**); queued-apply is gated `if not
  self._lock` :370 (queue is kept, not consumed, while locked); drop-snap is gated on `not
  self._lock` :409. Caller: `led_dispatch_policy.py:731`. Engine stub facts the gesture design must
  absorb: `set_palette` ignores `_lock` and does **not** clear `_queued_palette`; `queue_palette`
  stores unvalidated names (validated on apply :377).
- **The bridge does NOT consume Stream Deck palette input today** — *confirmed*.
  `streamdeck/streamdeck_midi.py` is a standalone sender (ch3 `CHANNEL=2`, sidecar-driven notes,
  `mido.open_output(..., virtual=True)` only). The bridge's generic MIDI input
  (`SoundSwitchMidiInputGroup`/`Adapter`, `soundswitch_midi_input.py`) already listens per-device on
  pack-learned bindings — including device `"Stream Deck"` ch2 notes 36/37/43 (static looks) — but
  branches only on `static_look` and `blackout_mask` kinds (:259, :280); everything else no-ops.
- **The "waterfall" layout behavior** — *confirmed*. The deck script's sidecar loader keeps only
  `channel == 2, target_kind == "static_look"` rows, **sorts by note, and assigns keys by list
  index** (`streamdeck_midi.py:85-99, 118-122`) — that's why newly authored bindings fill pads from
  top-left instead of staying put. Non-ch2 rows (e.g. the sidecar's "BLACK OUT" ch0 row) are
  filtered out entirely and never appear on the deck. The sidecar is written by the exporter
  (`tools/export_soundswitch_pack.py`) as `local/soundswitch/.rbss_canonical_pack.midi_bindings.json`.
- **Feedback is one-way today** — *confirmed*. `render_key()` :147 / `set_key_image()` :211,239
  render from local press-state only. No bridge→Stream Deck feedback path exists. The script already
  has a 1 Hz supervision loop (:246-247) a state-file poll can ride on.
- **M3 precedence as specified** — *confirmed*. `docs/plans/completed/led_color_engine_spec.md:485`:
  `lock > queued > snap > drift` (amended by operator decision, Part C.3 below). §8 (:343-356) names
  exactly `shift/lock/unlock/set_palette/queue_palette` and MIDI as the intended transport.
- **Event/command wiring surface exists** — *confirmed*. `models.py` `Ev` block already defines
  LED events (`LED_SCENE`/`LED_BLACKOUT`/… :263-269) produced by any source and consumed by
  StateManager; `runtime_status.py:413-447` shows the matching runtime-command pattern. Palette
  control adds new `Ev.LED_PALETTE_*` kinds on the same rails.
- **Laser color engine is greenfield** — *confirmed*. Zero palette code in the laser modules. The
  laser side shares only the palette **name**; per-engine values (`laser_color_engine_design_spec.md`).

## Part C — Architecture & locked decisions

**1. Layout (LOCKED, operator 2026-07-04 — pinned rows, waterfall retired; AWR-121
gesture v2 removes the dedicated lock pad).** Stream Deck 3×5, ch3.
- **Top row (keys 0-4)** = the 5 auto palettes in config order:
  `blue_cyan · deep_ocean · indigo · violet · crimson`.
- **Row 2:** key 5 = `white_sand`, key 6 = dark/reserved, key 7 = LED mute (C.8),
  key 8 = Laser mute (C.8), key 9 = Laser Solo (C.9) — a mixer strip: mute, mute, solo.
- **Bottom row:** keys 10-13 = static looks, **filling left→right** sorted by note (today: 3
  bound; overflow beyond 4 dropped with a log line). **Key 14 (bottom-right) = Rainbow mode
  toggle** (C.10) — the party button gets the corner.
- **Palette/control pad notes are bridge-assigned, outside the 36-50 static-look range** so
  SS-learned bindings can never collide: ch2 notes **51-55** (palettes, config order), **56**
  (`white_sand`), **58** (LED mute), **59** (Laser mute), **60** (Laser Solo), and **61**
  (Rainbow mode). Note **57** was the Package 2 v1 lock pad; AWR-121 makes `lock_note`
  optional/back-compatible and leaves key 6 dark when it is absent.
  Declared once in bridge config (Part C.6) and carried to the deck via the feedback file
  (Part C.7) — the deck script hardcodes no palette names or notes.

**2. Gesture (LOCKED; state machine finalized 2026-07-04).** No timers, no double-press windows —
the gesture is pure state:
- Press palette pad `P` → **if the engine's queued palette == `P`, override now** (consume the
  queue, apply `P` to the current track, hold it for this track); **else queue `P`** (replacing any
  other queued palette).
- The "second press" therefore works any time before the queue is consumed at a track boundary or
  replaced by another pad. Pressing the currently-active palette's pad queues it (= "keep it next
  track too"); pressing it again overrides (= freeze it this track). No special-casing; `white_sand`
  follows the identical rules.
- **Override mechanics (operator spin 2026-07-04 — fade, not jump):** on the override press the
  LED color **fades from the current palette to the target as a beat-synced blend, completing at
  the next smart-phrasing phrase anchor, capped at 32 beats** (whichever comes sooner; if the
  anchor is unknown, the 32-beat cap alone applies). The blend interpolates the engine's anchor in
  p-space, which by construction stays inside the allowed hue band (`_p_to_rgb` maps p∈[0,1] onto
  the permitted stops only — no yellow/orange transit). After completion the target holds for the
  rest of the track (drop-snap suppressed via a new engine flag, cleared in the new-track block —
  see C.4-engine). The override **explicitly consumes the queue** (engine `set_palette` alone would
  leave a stale `_queued_palette` to re-apply at the boundary — :736-741 does not clear it).
  Interruption rules: any new manual action (queue, another override, `white_sand`, shift) restarts
  or replaces the fade from the current blended position; lock pressed mid-fade lets the fade
  complete, then locks the target. Laser side is unaffected — lasers are drop-visible only and
  sample at phrase anchors, so a drop landing mid-fade simply quantizes the blended color
  (acceptable; see laser doc Part B).

**3. Lock & precedence (LOCKED, operator-decided 2026-07-04 — supersedes the plain M3 line).**
**Manual input always wins; lock freezes only automatic selection.**
- Lock pins the currently-active palette across track boundaries (blocks dwell re-pick, drift, and
  drop-snap) until unlocked.
- **A queued palette applies at the track boundary even while locked, and the lock transfers to
  it** (stays locked on the new palette until unlock). This is the operator's queue-overrides-lock
  rule; it requires moving the engine's queued-apply out of the `if not self._lock` gate (:370).
- Override (`set_palette`) likewise applies under lock; the lock stays set on the new palette.
- Automatic precedence among the rest is unchanged: `lock > snap > drift` (and `queued` outranks
  them all at boundaries, locked or not).

**4. Durations (LOCKED).**
- **Override = a 1-track hold** — the chosen palette holds for the current track (no drop-snap),
  then the next track boundary resumes normal flow (queued if any, else dwell/drift — which may
  legitimately keep the same palette if dwell hasn't expired; `set_palette` does not reset dwell).
- **Lock = the same hold, indefinite and boundary-crossing**, per C.3.

**Engine changes required (small, testable):**
1. Move queued-apply out of the lock gate in `begin_dispatch`: apply `_queued_palette` first,
   unconditionally; only the dwell decrement + dwell re-pick stay gated on `not self._lock`
   (today :369-396). Lock state itself is untouched by the apply.
2. Add a one-track hold flag (e.g. `_hold_track`) set by override, checked alongside `not
   self._lock` in the drop-snap condition (:408-411), cleared in the new-track block.
3. `set_palette` on override path must clear `_queued_palette` (coordinator- or engine-side; pick
   one and test it).
4. `white_sand` config entry with `weight: 0` (config + example config; no engine code).
5. **Fade transition state** for override (C.2): `(from_anchor_p, to_anchor_p, start_beat,
   end_beat)` advanced per render tick, target palette becomes `_current_palette` at completion;
   cleared on new-track and replaced by any new manual action. Pure state + math — no I/O.

**5. `white_sand` palette (LOCKED shape; color TBD).**
- A 6th palette entry, **manual-only via `weight: 0`** (mechanism confirmed, Part B). Same gesture
  as any pad. **Per-engine value from one shared name:** LED maps `white_sand` → white/off-white
  ("sand"); laser maps `white_sand` → CH8 white (laser doc Part E). The LED color is a **Template
  Lab calibration** deliverable — "sand" is warm, the LED hue scale excludes yellow/orange, so it
  likely needs a fixed-RGB palette type (small engine addition, resolved during calibration; the
  control wiring is independent of the final color).
- On scripted tracks `white_sand` (like any palette) affects only the breakdown/buildup LED windows;
  lasers keep authored cues (operator-decided 2026-07-04).

**6. Wiring path (LOCKED).** Pad input rides the **generic MIDI input** the bridge already runs:
- **Bindings:** a new bridge-config block (proposed home: `config/led_look_director.json`
  `/color_engine/palette_control`: `{enabled, device: "Stream Deck", channel: 2, palette_notes:
  {name→note}, lock_note}`) is injected into `SoundSwitchMidiInputGroup` alongside the pack-loaded
  bindings, with new target kinds `palette_pad` / `palette_lock_pad`. Pack files and the exporter
  are untouched — palette bindings are bridge-native, **not** pack-authored (the pack's
  `PackMidiBinding`s come from SS-learned controls; palettes never appear there).
- **Events:** the MIDI worker classifies a palette note-on and enqueues a BridgeEvent —
  `Ev.LED_PALETTE_PAD {name}` / `Ev.LED_PALETTE_LOCK_PAD` (new constants in the `models.py` Ev LED
  block) — following the reader-threads-publish-events invariant. Matching runtime commands
  (`led_palette_queue <name>`, `led_palette_override <name>`, `led_palette_lock/unlock`) join the
  `runtime_status.py` command surface for the LED Pad web / debugging (the M3 surface).
- **Coordinator:** the two-tap decision (C.2) runs **StateManager-side in the event handler**
  (thread-safe by construction — engine state is only read/mutated on the owning thread), living in
  the LED dispatch mixin (`led_dispatch_policy.py`); it calls the engine stubs directly since it IS
  StateManager code (:724-725 note satisfied). It fans the resolved command to the laser color
  engine (by palette name) when that exists — no rework, per the coupling decision.

**7. Feedback (LOCKED shape; transport = file).**
- **The bridge writes a palette-state JSON** (proposed `local/state/streamdeck_palette_state.json`,
  gitignored path), atomically (`tmp` + `rename`), from a **dedicated writer thread** in the
  coordinator — event-driven on palette-state change, debounced ~50 ms. **Never from the 200 Hz
  push loop** (no-filesystem-I/O invariant, AGENTS §6).
- **Schema (v1):** `{v: 1, lock: bool, led_blackout: bool, laser_blackout: bool,
  laser_solo: "off"|"armed"|"active", rainbow: bool,
  palettes: [{name, note, rgb: [r,g,b], state: "active"|"queued"|"inactive"|"fading"}], seq: int}`
  — list order = display order (5 palettes then `white_sand`); `rgb` = representative swatch
  computed by the engine (`_palette_center`/`_p_to_rgb` derivation); `seq` monotonic for staleness
  checks.
- **The deck script reads + renders:** poll the file's mtime in its existing supervision loop
  (tightened to 0.5 s so pulses read as pulses) and immediately after its own presses. The file
  also carries the pad layout (names + notes), so the deck script needs no bridge config. File
  absent/stale → palette/control pads render blank (feature-off state); static-look pads are
  unaffected. Palette→color logic stays in the bridge; the script only draws.

**Pad iconography (operator-requested 2026-07-04 — intuitive, practical, state-visible).**
One universal state grammar across ALL pads, so every pad reads the same way at a glance:
- **Bright/solid = engaged/on. Dim = available/off. Pulsing = pending/armed (something will
  happen at the next boundary/drop — and on the Solo pad, pulsing means "press to cancel").**
- **Every physical press flashes the pad white for ~150 ms** (tactile ack, replaces today's
  blue tint), regardless of pad type.
- All icons are **drawn programmatically with PIL** (the deck script already renders with PIL —
  swatches, glyphs, and labels need no asset files, and palette colors come live from the
  feedback file). The existing `icons/<n>.png` override mechanism stays for custom art.

| Pad | Icon | Off/idle | On/engaged | Pending |
|---|---|---|---|---|
| Palettes (0-4) | color swatch + name | dim swatch | bright + white border (active) | pulsing (queued); override fade = pulse settling to bright |
| `white_sand` (5) | sand-white swatch + "SAND" | dim | bright + border | pulsing (queued) |
| Lock (6) | padlock drawn OVER the current palette's color | open padlock, dim | closed padlock, bright | — |
| LED mute (7) | bulb/strip glyph + "LED" | dim gray | **solid red + slash** (mixer convention: lit = muted) | — |
| Laser mute (8) | beam glyph + "LZR" | dim gray | **solid red + slash** | — |
| Laser Solo (9) | starburst glyph, **amber** (mixer solo color) | dim amber | solid amber (solo firing now) | **pulsing amber = armed** (manual, hotcue, learned, gear-shift, or record — press to veto) |
| Static looks (10-13) | look name label | dim | bright (held press / toggled on) | — |
| Rainbow (14) | rainbow arc | desaturated, dim | full-color bright | — |

Red is reserved for "a fixture is muted" (the two states worth noticing instantly), amber for
solo, white for acknowledgment — nothing else uses those colors, so a glance at row 2 reads the
whole room state.
- *(Alternative considered: MIDI-back to the script — lower latency but needs an input port added;
  deferred in favor of the file. 1 s icon latency accepted; press feedback stays instant/local.)*

**8. Room-state mute pads (LOCKED, operator-directed 2026-07-04; mixer naming accepted).** Two
per-fixture mutes compose all three room states live — LED-only (Laser mute on), LED+laser
(neither), laser-only (LED mute on) — with the presentation policy (C.9) running underneath
whenever the pads are untouched.
- **LED mute (key 7):** toggles the Govees off / back on. Wiring is nearly free:
  `Ev.LED_BLACKOUT` / `Ev.LED_CLEAR_BLACKOUT` and the matching runtime commands already exist
  (`models.py:267-268`, `runtime_status.py:427,440` — the LED Pad web takeover path). The pad's
  note-on flips a coordinator-held toggle that emits the corresponding event; the pad icon
  renders from `led_blackout` in the feedback file.
- **Laser mute (key 8):** toggles the laser frame dark / back. Rides the **existing**
  `blackout_mask` machinery end-to-end: one new bridge-config binding row (device "Stream Deck",
  ch2, note 59, kind `blackout_mask`, toggle interaction) joins the MIDI-input adapter's
  refcounted blackout bindings (`soundswitch_midi_input.py:280-314`) — a **second manual owner**
  alongside the laser-pad-web note, already OR'd correctly by the group merge (:621-635). Zero
  new code paths; pad icon renders from `laser_blackout` in the feedback file.
- **Owner discipline (lesson from the laser blackout review):** the manual LED mute and the
  Laser Solo window (C.9) both drive LED blackout — they must be **separate owners** (event
  payload `reason`), OR'd at the LED dispatch layer, so a solo's auto-restore can never clear a
  manually-held mute and vice versa. Same rule on the laser side: the mute pad's binding owner
  is distinct from the laser-pad-web owner by construction (per-binding refcount). Codex spec pins
  the exact seam + test.

**9. Drop presentation policy + Laser Solo pad (CONVERGED via operator brainstorm
2026-07-04 — supersedes the earlier weighted-deal draft; "Laser Solo" naming accepted).**

**Governing idea (operator's own words): a lasers-only drop is "the whole club saw it coming"
AND "the track everyone came for" — so a Laser Solo is NEVER a dice roll.** Every solo traces to
an operator signal — a live press, a hot cue, the learned history of his own presses, his own
mixing (a one-mix BPM gear-shift) — or to a night-relative superlative (the record runway).
Zero RNG anywhere in the policy. Untagged tracks get a fixed **lighting personality** derived
from their own structure. "True drop" reuses the bridge's existing qualification, unchanged:
Smart-Drop selection (`smart_phrasing.py:601`) + the drop-lifecycle tension-predecessor gate
(`drop_lifecycle.py:18` `impact_predecessors`). Breakdown/groove/buildup stay LEDs-only by pack
authoring, as today. **Deleted from the earlier draft:** presentation weights, the random
lasers-only tier, the ordinal-≥2 gate, the tracks-since-special budget, and the drought breaker
(operator: every track played has a true drop, nearly all have 2+ — a drought never occurs).

**Runway (definition, used throughout):** walk backward from a drop's impact beat, counting
consecutive beats whose smart-phrasing role is **breakdown or buildup** (the ANLZ phrase roles
the bridge already maps); stop at the first beat that is anything else. 32-beat breakdown +
16-beat buildup into the drop = 48-beat runway; a drop straight out of groove = 0.

**The ladder (first match wins, per drop; auto-solo tiers 4-6 fire at most ONCE per track):**
1. **Mute pads (C.8)** — manual room state, absolute, continuous.
2. **Laser Solo pad (key 9)** — one-shot: arms the **next true drop** (not immediate; a press
   during an already-playing drop arms the following one) as `lasers_only` (+ pre-dark). Pad
   pulses while armed; disarm = press again; auto-clears on track change. **The pad is also the
   veto:** whenever ANY lower tier (hotcue/learned/gear-shift/record) has a solo pending, the pad
   shows "armed" — pressing it cancels that solo, and cancelling a learned solo un-learns it.
3. **Hotcue tag (curation in Rekordbox)** — a hot cue named with the marker (default `LASER`,
   case-insensitive, config `hotcue_marker`) placed on the drop marks it: that drop is
   `lasers_only` (+ pre-dark). Matched to the nearest smart drop within ±2 beats. **No budget
   gate — tagging is deliberate; if two tagged anthems play back-to-back, that was the plan.**
   Mechanism (**corrected 2026-07-04 after ground-truth verification**): hot cues are read from
   Rekordbox's **`master.db`**, NOT the ANLZ files — a full library scan found every on-disk ANLZ
   cue tag empty (Rekordbox does not rewrite that cache on cue edits), while `master.db` holds
   413 named cue points (verified: `Cues` JSON blobs on `ContentCue` rows, `Comment` + `InMsec`
   per cue, keyed by `ContentID`). The bridge already reads this DB via
   `pyrekordbox.db6.Rekordbox6Database` (`filepath_resolver.py:244-246` pattern). Cues are read
   once per track load, off the push loop; ms→beat via the existing beat math. The operator
   already names cues `DROP`/`BUILDUP` for navigation — those must NEVER trigger solos; only the
   configured marker does.
4. **Learned solo (operator-accepted 2026-07-04; one-press learning per operator) — the pad
   teaches.** Every manual solo is recorded per `(content_id, drop_index)` in a small gitignored
   state file (`local/state/laser_solo_learned.json`). **One manual solo is enough** — solo a
   drop once and it auto-solos on every future play (`solo_learn_threshold: 1`), exactly like a
   hotcue tag. The pad arms on track load so the intent is visible; the veto press (tier 2)
   cancels AND un-learns (the recovery path for an impulsive press that shouldn't stick).
   Per-track memory only — generalizes nothing across tracks.
5. **Gear-shift solo (operator-accepted 2026-07-04, operator-tuned).** When a master handover
   jumps the live BPM by ≥ `gearshift_bpm_jump` (default **+10**) **within that single mix** —
   incoming master's BPM vs the outgoing master's live BPM at the transition, never a drift
   accumulated across several tracks — the incoming track's **first true drop** solos. Plain
   arithmetic on the master-change event.
6. **Record-breaker solo (operator-accepted 2026-07-04).** A drop whose runway **strictly beats
   the night's longest runway so far** solos — but only after `record_min_drops` (default 5)
   true drops have been observed tonight (a real baseline exists). No absolute threshold, so
   nothing to generalize: the night calibrates itself, and each record raises the bar, so it
   naturally rarifies as the set peaks. The record is crossed **mid-buildup** (the accruing
   runway passes the old record before impact), so the pad arms and pre-dark engages in time.
   Records are tracked even when the solo doesn't fire (e.g. during the damper).
7. **Opening damper** — the first `opening_tracks` (default 3) of a session force `leds_only`
   drops and block tiers 5-6 (save the night's first laser moment). Manual, hotcue, and learned
   solos are exempt — explicit curation fires even early.
8. **Finale guarantee (operator flip of the "finale drop" idea, 2026-07-04):** the **last true
   drop of a track, when actually reached, always renders at least `leds_plus_lasers`** — never
   `leds_only`. (It already ranks #1 in the personality tier; this makes the guarantee explicit
   and replaces the old single-drop coin: a single-drop track's drop is its last, so it gets
   LED+laser when reached, no coin flip.)
9. **Track personality (everything else — fully deterministic, zero RNG anywhere):** rank the
   track's true drops by its own dramaturgy — **last drop first, then longest runway**. The top
   `ceil(laser_ratio × N)` ranked drops (default ratio 0.4) render `leds_plus_lasers`; the rest
   `leds_only`. A pure function of track structure, so **every track keeps the same lighting
   identity every time it's played** — lasers land on its biggest drops, dark on the rest;
   predictable for the performer, consistent craft for the crowd.

**Presentation mechanics (unchanged from prior draft):**
- **`leds_only`:** lasers stay dark through the drop window via **base suppression, NOT the
  blackout mask** — the player already renders "no selection → zero base while a manually-held
  static override still stands alone" (`soundswitch_laser_player.py:428-443`); suppression
  withholds the drop base the same way, so a held static look survives automation.
- **`lasers_only`:** pre-drop full-dark — Govees join the lasers' existing smart-drop pre-window
  for the final `led_predark_beats` (default 4) → impact: Govees dark, lasers alone →
  auto-restore at window end.
- **Drop window** = drop impact → end of the smart-phrasing drop role (the shared phrase
  authority, neither side's private timer). A later true-drop impact inside an open window asserts
  its own planned presentation and re-stamps the cap from that impact. `drop_window_cap_beats`
  defaults to 192 and is a stuck-role backstop only, not the expected release. Known limit: a
  `lasers_only` solo that re-enters mid-window skips the LED pre-dark countdown and fires at impact.
- **Darkness guard (`lasers_only`, ALL solo sources — manual, tagged, learned, gear-shift,
  record):** before cutting the Govees at impact,
  verify lasers will actually be visible — pack player live and rendering a drop autoloop, no
  laser blackout mask held, laser output enabled. Otherwise **fall back to `leds_plus_lasers`**
  (only the beat-capped pre-dark may ever be fully dark, and it hard-restores at impact).
- **Fail-open rules:** restore LEDs (and release base suppression) on ANY of window end / role
  change / track change / stop / manual interaction / laser-output loss mid-window — the policy
  can never latch either fixture dark.
- **Config block** (proposed home `config/led_look_director.json` `/drop_presentation`):
  `{enabled: true, laser_ratio: 0.4, opening_tracks: 3, led_predark_beats: 4,
  drop_window_cap_beats: 192, hotcue_marker: "LASER", solo_learn_threshold: 1,
  gearshift_bpm_jump: 10, record_min_drops: 5, ws_handoff_enabled: false}`. All deterministic;
  `enabled: false` restores today's behavior exactly (every drop `leds_plus_lasers`; mute/solo
  pads still work). First live set validates the defaults.
- The `leds_only` base-suppression seam is laser-side plumbing (a per-drop selection withhold);
  the laser doc cross-references it. Everything else is zero laser code.

**10. Rainbow mode pad (operator-requested 2026-07-04 — "fun crazy mode"; toggle, key 14 /
note 61).** A section-mapped color override that rides machinery this design already builds:
- **Toggle on → colors remap by phrase role**, the palette journey suspends: breakdown/buildup →
  **`white_sand`** (the white/off-white palette this design already adds); groove/drop/post-drop
  → **rainbow**.
- **LED rainbow** = a new palette *type* `rainbow` cycling the **full hue wheel** — deliberately
  bypassing the journey palettes' yellow/orange band exclusion (crazy mode gets the whole wheel;
  flag: operator taste-check at Template Lab time). Small engine addition alongside the fixed-RGB
  type `white_sand` already needs.
- **Laser rainbow** = the CH8 **color-change / RGB color-change effect family** at a CH9 speed
  (the taxonomy the operator supplied) instead of the nearest-of-7 quantizer — exact values
  chart-gated (laser doc Part E #1/#10). Fires wherever lasers are already firing per the
  presentation ladder.
- **Mode changes COLORS, not presentation (default):** the ladder, mutes, solo, damper, and
  personality all still apply — a `leds_only` drop stays LEDs-only, just rainbow. (Alternative,
  operator's call later: "crazy = crazier" — mode forces LED+laser on all drops while on.)
- **While on:** palette, lock, and `white_sand` pads go inactive (dimmed icons); the engine's
  journey state is frozen untouched underneath and resumes exactly where it was on toggle-off.
- **Scripted tracks:** unchanged rules — LEDs render only breakdown/buildup windows (white/
  off-white under the mode); lasers stay authored (stand-down).
- Feedback file: `rainbow: bool`; the pad renders a bright rainbow icon when on.

## Part D — Open items

1. **`white_sand` LED color — Template Lab calibration** (unchanged; likely fixed-RGB palette type).
2. **Laser side (deferred until the laser color engine exists).** The two laser decisions are
   recorded in `laser_color_engine_design_spec.md` Part E: (a) white-moment mirroring, (b)
   `white_sand` → laser CH8 white. Both gated there on the CH8/CH9 encoding chart (operator will
   produce inputs later; gates laser-mapper implementation, not this LED feature).
3. **Phase 2 input path sequencing.** This feature depends on the Stream Deck Phase 2 generic
   dispatch (`streamdeck_midi_bridge_integration_spec.md` Part F, plan-first/live-critical);
   palette pads register as additional binding kinds on that path. Build order: Phase 2 compositor
   dispatch first (or alongside); palette control second.
4. **Closed this pass:** 1-track override mechanism (C.2/C.4), manual-only mechanism (weights,
   Part B), queue-vs-lock precedence (C.3, operator-decided), layout + notes + waterfall fix (C.1),
   feedback schema/cadence (C.7), binding source (C.6). **Feature-expansion round (operator picks
   2026-07-04):** override-as-phrase-fade (C.2), LED/Laser mute pads (C.8), Laser Solo pad +
   presentation policy (C.9), auto-solo tiers (learned / gear-shift / record-breaker, C.9);
   rejected: shift pad, per-drop laser hue variation as a feature (already emerges from existing
   behavior), laser contrast mode (fixed-color fixture — see laser doc), double-drop detection
   (operator doesn't do them), drought breaker (no droughts — every track has true drops),
   **star-rating curation** (operator's ratings mix "really like" with energy-level tags —
   semantics too polluted to drive solos; a dedicated Rekordbox playlist name remains the clean
   future option for bulk curation).
5. **white_sand handoff (operator: "flesh out more, then it could be added" — shipped DISABLED,
   `ws_handoff_enabled: false`).** Proposed flesh-out: holding `white_sand` continuously from
   inside a breakdown until the pre-dark point (≥ 16 beats of hold) makes the drop that ends it a
   Laser Solo — the ritual completes; max once per track. The hold is about the PALETTE staying
   active, not the roles underneath: a groove between the breakdown and the buildup does NOT
   break the ritual (its beats count toward the 16; the room stays visibly white throughout) —
   unlike the record-breaker runway, whose contiguity a groove deliberately resets (tension
   released = saw-it-coming clock restarts). **Firing frequency if enabled: exactly as often as
   the operator performs the full ritual — no hidden budget or cooldown; rarity is entirely his
   white_sand discipline** (an every-breakdown white_sand habit would solo nearly every track).
   Disabled by default; revisit after the other tiers are felt live.

## Part D.1 — Impl-spec deltas (adversarial review + operator rulings, 2026-07-04)

The Codex impl spec (`streamdeck_palette_control_impl_spec.md`) supersedes this doc on these
points — do not implement from the older text above:
- **Feedback file:** `/tmp/rb_ss_bridge_v2_palette_state.json`, debounce ≥100 ms (not
  `local/state/...` / ~50 ms as C.7 says).
- **Coordinator home:** NEW `led_palette_control.py` owned by StateManager (not the dispatch
  mixin as C.6 says).
- **Notes confirmed:** solo=60, rainbow=61 (C.1 was right; the impl spec's first draft had
  rainbow at 60 — fixed).
- **LED blackout owner seam pinned:** owner SET in `led_dispatch_policy.py` (impl Task 2 item
  4); web/legacy clear releases only its own hold (operator ruling).
- **Both mutes drop on pad-input loss** (operator ruling — LED mute mirrors the laser mute's
  overlay-trust release; C.8's implication that only automation can never clear stands).
- **Laser mute needs `blackout_mask` toggle-interaction support in the adapter** (impl Task 4
  item 3) — the "toggle interaction" C.8 assumed did not exist for this kind.
- **Queue waits out Rainbow mode** and applies at the first post-Rainbow boundary (operator
  ruling); boundary bookkeeping vs journey freeze pinned in impl Task 1.5.
- **Fail-open triggers are the authority's EIGHT** (adds active-deck change +
  predicted-impact-passed to C.9's six).
- **Learned-solo keys are beat-position** (`content_id:round(beat)`, ±2 lookup), not drop
  indices (operator ruling — safer under re-analysis).
- **`white_sand` color:** borrowed from the Dune Sand twinkle palette
  (`govee_frame_renderer.py:1758-1764`), Warm Ivory (255,235,200), Template Lab may refine.
- **Gesture v2 delta (AWR-121), 2026-07-04 — implemented/software-tested at `daa8804`,
  suite 2941 OK:** supersedes C.2/C.3's two-tap-override + dedicated-lock-pad surface: tap =
  queue/unqueue toggle; long-press (~0.5 s) = take-and-hold (override-fade + lock, padlock on the
  palette's own pad); tap the locked active pad = unlock; key 6 goes dark; idle swatches dim by
  HSV value only (hue stays readable). Current contract: `palette_control_authority.md` rules
  1-4/7-10 v2 banner; implementation: `docs/plans/active/palette_gesture_v2_spec.md` (AWR-121).
  Runtime commands still keep their explicit queue/override/lock/unlock command semantics for
  debugging and pad-web rails. The running bridge still serves v1 until the operator restarts
  the bridge and deck script; the deck-in-hand validation pass is the remaining gate.

## Part D.2 — Deck-surface hardening pass (2026-07-04 evening, post-incident debug)

Five live failures in one day drove a debug/hardening pass over the deck script and the
feedback producer (authority rules 25-27 record the resulting contract). Landed in
`streamdeck/streamdeck_midi.py`, `led_palette_control.py`, and tests:

- **on_key contains ALL exceptions** (was `TransportError`/`OSError` only): the HID library's
  read thread survives only `TransportError`; anything else escaping the callback killed all
  pad input silently. An rtmidi send failure is not an `OSError`.
- **Read-thread liveness check** in the 0.5 s supervision loop: the library swallows read-side
  `TransportError` by silently closing the device while `connected()` (a USB enumeration
  check) can stay True — pads rendered fine with input dead. A dead reader now forces a loud
  reconnect.
- **Watchdog** (`WATCHDOG_STALL_S` 20 s): a wedged main loop (e.g. hung `hid_write`, which also
  blocks the reader via the shared transport mutex) logs and hard-exits (`os._exit(70)`) so the
  watcher respawns the script; a shutdown stalled >10 s does the same.
- **`FeedbackWatch`**: logs feedback lost/restored and any gain/loss of bound keys with the
  live note range (incident 5's lying-by-omission boot banner), and detects bridge restart via
  feedback `seq` regression → clears deck-local toggle latches (which now deliberately survive
  USB reconnects, matching the bridge's held layers).
- **Projections pass-through-by-default** (`_palette_row`/`_control_row` start from
  `dict(row)`): unknown producer fields survive; a whitelist here silently ate `ramp` once.
  Pinned cross-module by `FeedbackProducerDeckContractTests`.
- **Writer transition logging** (`PaletteFeedbackWriter._write_once`): write-failure and
  recovery each log once per episode (a steady failure otherwise blanked every feedback pad
  with a single log line ever).
- **Redraw scope**: pulse ticks redraw only changed rows + pulse-dependent rows, not all 15
  keys every 0.5 s.
- **Retry-log rate limiting**: `waiting for Stream Deck`/open-error lines log once per outage
  episode (the 3 s retry loop once wrote 3000+ identical lines).
- **Real-caller-path tests**: `StreamDeckRealCallerPathTests` drives the REAL
  `make_on_key`/`on_key` → `render_key` → `set_key_image` chain over a composed layout — the
  class the old mock-based smoke tests missed (incident 4's frozen-white toggle pads shipped
  because the smoke test passed booleans straight into `render_key`).

Bridge-runtime siblings found in the same pass (adapter/state_manager/__main__ lanes — NOT
implemented here) are written up in
`docs/plans/active/streamdeck_surface_hardening_findings_2026_07_04.md`.

## Part D.3 — Bridge-side hardening landed (2026-07-04 night, F-B1/F-B3/F-B4)

The findings-doc riders were implemented per
`docs/plans/active/streamdeck_bridge_side_hardening_impl_spec.md` (Codex Tasks 1-8;
operator-sanctioned Sonnet-subagent fallback for Tasks 9-12 after a Codex quota stop).
Software-tested; suite 2954 OK. What changed:

- **F-B4** (`scripts/ss_bridge_watcher.sh` + new `tests/test_ss_bridge_watcher.py`): every
  intentional deck-script stop writes a reason line into `/tmp/streamdeck.log`; manual mode
  respawns the deck script during bridge gaps; `WATCHER_NO_LOOP=1` sources functions for tests.
- **F-B1** (`__main__.py`, `state_manager.py`): frame-sender construction/start failure no
  longer stops the MIDI input group (input and output start independently); the pack-reload
  path passes `event_sink`/`extra_midi_bindings` so palette pads survive reloads; a new
  `_update_pack_input_health` helper runs the RW-4 latch in BOTH active and inactive runtime
  states, so `input_degraded` is truthful (change-gated publish, fail-closed on error) even
  with pack output disabled.
- **F-B3** (`soundswitch_midi_input.py`, `led_palette_control.py`, `state_manager.py`,
  `streamdeck/streamdeck_midi.py`): `LayerEntry` carries binding channel+note; the feedback
  payload publishes `static_held`; the deck reconciles static-look latches from it each tick
  (pure helper `_reconcile_static_latches`, 2.0 s local-echo grace, old-payload no-op).
  Authority rule 28.

## Part D.4 — LIGHTING ENGINE v2 F1 overlay (AWR-128, 2026-07-06)

`docs/plans/active/lighting_engine_v2_f1_spec.md` supersedes this doc only for the v2-latched
Stream Deck color surface. Package 2/AWR-121 remains the v1 palette-control behavior.

F1 implemented surface:

- v2 engine latch is a temporary menubar checkbox plus runtime command `led_engine v1|v2`;
  there are no deck engine-switch pads.
- When v2 is active, keys 0-5 are zone pads (`GLACIER`, `DEEP_POOL`, `TWILIGHT`, `ION`, `VOLT`,
  `EMBERCORE`); key 6 is `white_sand`; keys 7-9 remain LED mute / Laser mute / Laser Solo; keys
  10-13 remain static looks; key 14 is the shift layer.
- Shift layer keys 0-2 are red/green/blue manual overrides, key 3 is max-energy arm, key 4 is
  Rainbow manual, keys 5-6 are dark, and keys 7-13 keep the existing control/static functions.
- Zone tap stages/unstages a phrase-boundary correction, long-press applies/corrects immediately,
  and tapping the active corrected zone clears the correction. Corrections are zone-only and
  content-keyed in `local/state/led_identity_v2.json`.
- `led_palette_queue` / `led_palette_override` keep v1 palette semantics for palette names, but
  may carry v2 zone names while the bridge is latched to v2. New runtime commands:
  `led_manual_override`, `led_manual_clear`, and `led_max_energy_toggle`.
- Max-energy is arm/consume/log only in F1; it intentionally does not change rendered frames until
  F2. All behavior remains SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## Part E — Evidence (file:line, HEAD `bd96b32`)

- LED live-control stubs + state + routing note: `led_color_engine.py:724-768`; non-test caller
  (local preview engine only): `tools/led_pad_web.py:528-529`.
- Palette config (5 named palettes): `config/led_look_director.json` `/color_engine/palettes`;
  enumeration `led_color_engine.py:283-286`; `Palette.weight`: `led_models.py:64`; weighted
  selection `_pick_palette`/`_weighted_choice`: `led_color_engine.py:774-786,135-165`; all auto
  call sites `:293,389,414,751`.
- Track-boundary hook / queued-apply / lock gates: `led_color_engine.py:333,351-399,370,408-411`;
  caller `led_dispatch_policy.py:731`.
- M3 live-control surface + precedence: `docs/plans/completed/led_color_engine_spec.md:343-356,485`.
- Stream Deck sender + waterfall/sidecar mechanics: `streamdeck/streamdeck_midi.py:32-38,64-99,
  118-137,147-168,193-215,235-247`; sidecar writer `tools/export_soundswitch_pack.py`.
- Generic MIDI input (per-device bindings, kind dispatch): `soundswitch_midi_input.py:259,280,
  346-374`; pack binding load `soundswitch_pack_loader.py:40-51,358-368`.
- Event + command rails: `models.py:147-154,235-269`; `runtime_status.py:413-447`.
- White sources context: `led_color_engine.py:33-38` (white_chance out of scope), `_blend_white`
  :105, reserved slot-5 :609,664; cue-mandated white effects `govee_frame_renderer.py`
  (`drop_white_aggressive`:505, `post_drop_white_shatter`:515, `buildup_white_*`:874-953).
- Scripted-mode LED gating (mechanism): `led_look_director.py:174-187`,
  `led_dispatch_policy.py:83-143`.
- Drop presentation inputs: Smart-Drop selection `smart_phrasing.py:601-617`; drop-lifecycle
  tension gate `drop_lifecycle.py:18`; hot-cue names from `master.db` via
  `pyrekordbox.db6.Rekordbox6Database` (`filepath_resolver.py:244-246` pattern; ANLZ cue tags
  verified empty/stale across the whole library 2026-07-04 — do not use them);
  base-suppression render state `soundswitch_laser_player.py:428-443`.

## Change-contract note

Package 2 implementation is covered by `docs/agents/change_contracts.yml` entries for `led_govee`
and `streamdeck_palette`. Keep `docs/subsystems/led_govee.md`,
`docs/subsystems/runtime_commands.md`, this design spec,
`docs/architecture/palette_control_authority.md`, and
`docs/status/active_work_registry.md` aligned with code before claiming more than
SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

AWR-136 (2026-07-07) is a `led_govee` reporting-only update adjacent to this
surface: mirror-strip cloud send failures/recoveries now log once per transition,
and stale `circuit_open` degraded status clears after a successful send. It does
not change palette input, feedback-file semantics, mutes, Solo, Rainbow, or light
output.
