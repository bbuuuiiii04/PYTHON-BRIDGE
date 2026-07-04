---
doc_status: draft
truth_level: design-intent
last_verified_commit: bd96b32
last_verified_date: 2026-07-04
validation_scope: software-only
---

# Stream Deck Palette Control — Design Spec (pre-handoff)

> **Status: PLANNED / DESIGN-INTENT. Not implemented.**
> Roles: Claude authors this design (planning); **Codex implements the bridge code** once
> finalized. **Fable reviewed (Phase 1) and expanded (Phase 2) this design on 2026-07-04**
> with operator answers folded in; awaiting operator approval (gate 2) before the Codex spec.
> Per AGENTS.md §1, **code wins over this doc** — verify every claim against current code.
> Claims are labelled **confirmed / assumed / unknown / operator-decided**.

This is a forward-looking design doc. It is **not** current truth and is not in the active work
registry yet. It is the **LED-side** feature; the laser side is deferred (see Part D) and its two
laser-specific decisions are cross-referenced into `laser_color_engine_design_spec.md`.

---

## Part A — Goal & scope

Give the operator live palette control from the 15-pad Stream Deck (MIDI ch3), driving the **LED
color engine** now and the **laser color engine** when it exists. This is the **M3 "live control
surface"** the color-engine spec already designed (`docs/plans/completed/led_color_engine_spec.md`
§8 :343-356) — we are wiring an already-specified API, not inventing one.

In scope (v1, LED):
- Top-row pads select **color palettes**; a two-tap gesture **queues** (next track) then
  **overrides** (current track); a dedicated pad **locks/unlocks**.
- A manual-only **`white_sand`** palette (Stream-Deck-only, never auto-selected) that renders LEDs
  white/off-white and drives lasers white.
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

**1. Layout (LOCKED, operator 2026-07-04 — pinned rows, waterfall retired).** Stream Deck 3×5, ch3.
- **Top row (keys 0-4)** = the 5 auto palettes in config order:
  `blue_cyan · deep_ocean · indigo · violet · crimson`.
- **Row 2:** key 5 = `white_sand`, key 6 = lock/unlock. Keys 7-9 = spare (static-look overflow).
- **Bottom row (keys 10-14)** = static looks, **filling left→right** sorted by note (today: 3 bound).
  Overflow beyond 5 goes to spare keys 9→7; anything past that is dropped with a log line.
- **Palette pad notes are bridge-assigned, outside the 36-50 static-look range** so SS-learned
  bindings can never collide: ch2 notes **51-55** (palettes, config order), **56** (`white_sand`),
  **57** (lock). Declared once in bridge config (Part C.6) and carried to the deck via the feedback
  file (Part C.7) — the deck script hardcodes no palette names or notes.

**2. Gesture (LOCKED; state machine finalized 2026-07-04).** No timers, no double-press windows —
the gesture is pure state:
- Press palette pad `P` → **if the engine's queued palette == `P`, override now** (consume the
  queue, apply `P` to the current track, hold it for this track); **else queue `P`** (replacing any
  other queued palette).
- The "second press" therefore works any time before the queue is consumed at a track boundary or
  replaced by another pad. Pressing the currently-active palette's pad queues it (= "keep it next
  track too"); pressing it again overrides (= freeze it this track). No special-casing; `white_sand`
  follows the identical rules.
- **Override mechanics:** apply immediately (`set_palette`) + suppress drop-snap for the remainder
  of the current track (new engine flag, cleared in the new-track block — see C.4-engine). The
  override **explicitly consumes the queue** (engine `set_palette` alone would leave a stale
  `_queued_palette` to re-apply at the boundary — :736-741 does not clear it).

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
- **Schema (v1):** `{v: 1, lock: bool, palettes: [{name, note, rgb: [r,g,b], state:
  "active"|"queued"|"inactive"}], seq: int}` — list order = display order (5 palettes then
  `white_sand`); `rgb` = representative swatch computed by the engine (`_palette_center`/`_p_to_rgb`
  derivation); `seq` monotonic for staleness checks.
- **The deck script reads + renders:** poll the file's mtime in its existing 1 Hz loop (and
  immediately after its own presses); palette pads render swatch + name with state treatment
  **active = highlighted, queued = pulsing/dim, inactive = muted**; lock pad renders a lock/unlock
  glyph. The file also carries the pad layout (names + notes), so the deck script needs no bridge
  config. File absent/stale → palette pads render blank (feature-off state); static-look pads are
  unaffected. Palette→color logic stays in the bridge; the script only draws.
- *(Alternative considered: MIDI-back to the script — lower latency but needs an input port added;
  deferred in favor of the file. 1 s icon latency accepted; press feedback stays instant/local.)*

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
   feedback schema/cadence (C.7), binding source (C.6).

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

## Change-contract note

Design-only; changes no runtime behavior, so no `change_contracts.yml` entry yet. Per AGENTS.md §7,
**before** implementation begins, add/extend the `led_govee` (and a new `streamdeck_palette` /
`runtime_commands`) contract with its `docs_update` list, then edit code.
