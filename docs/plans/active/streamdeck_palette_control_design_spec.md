---
doc_status: draft
truth_level: design-intent
last_verified_commit: a1e2f4e
last_verified_date: 2026-07-04
validation_scope: software-only
---

# Stream Deck Palette Control — Design Spec (pre-handoff)

> **Status: PLANNED / DESIGN-INTENT. Not implemented.**
> Roles: Claude authors this design (planning); **Codex implements the bridge code** once
> finalized. **Fable will review and expand this design before handoff** (same flow as
> `laser_color_engine_design_spec.md`). Per AGENTS.md §1, **code wins over this doc** — verify
> every claim against current code. Claims are labelled **confirmed / assumed / unknown**.

This is a forward-looking design doc. It is **not** current truth and is not in the active work
registry yet. It is the **LED-side** feature; the laser side is deferred (see Part D) and its two
laser-specific decisions are cross-referenced into `laser_color_engine_design_spec.md`.

---

## Part A — Goal & scope

Give the operator live palette control from the 15-pad Stream Deck (MIDI ch3), driving the **LED
color engine** now and the **laser color engine** when it exists. This is the **M3 "live control
surface"** the color-engine spec already designed (`led_color_engine_spec.md:343-356`, §8) — we are
wiring an already-specified API, not inventing one.

In scope (v1, LED):
- Top-row pads select **color palettes**; a two-tap gesture **queues** (next track) then
  **overrides** (current track); a dedicated pad **locks/unlocks**.
- A manual-only **`white_sand`** palette (Stream-Deck-only, never auto-selected) that renders LEDs
  white/off-white and drives lasers white.
- **Visual feedback**: each pad renders an icon reflecting its palette/action and live state.

Out of scope:
- The **laser color engine itself** (greenfield; deferred until built). This design is laser-*ready*
  but wires LED only in v1.
- The **Stream Deck Phase 2 generic input path** is a **prerequisite**, specced separately
  (`streamdeck_midi_bridge_integration_spec.md`, plan-first / live-critical). This feature is the
  first *consumer* of that path, not the path itself.
- The final **`white_sand` LED color** — a Template Lab calibration follow-up, not fixed here.

## Part B — Confirmed evidence (code-grounded)

- **LED live-control methods exist but are UNWIRED stubs** — *confirmed*. `led_color_engine.py`:
  `lock()` :728, `unlock()` :732, `set_palette(name)` :736 (immediate jump; docstring "transport not
  yet wired; pure state mutation stub" :742), `queue_palette(name)` :744 (one-shot, applied on next
  track), `shift()` :749, `snapshot()` :759-768 (exposes `current_palette`/`queued_palette`/`lock`).
  State fields `_lock` / `_queued_palette` / `_current_palette`. Nothing in the repo calls them
  except tests. Header comment :724-725: *"Operator-reserved future LED Pad / Stream Deck controls.
  Future callers outside StateManager must route through BridgeEvents/runtime commands."*
- **Exactly 5 palettes today**, string-named — *confirmed*. `config/led_look_director.json`
  `/color_engine/palettes` = `blue_cyan, deep_ocean, indigo, violet, crimson` (all `white: 0.0`).
  Identity = the string key into `config.palettes`; enumerate via `list(config.palettes.keys())`
  (insertion order, no numeric index). No `white` palette exists.
- **No "N-track override / expiry" concept exists** — *confirmed*. `set_palette`/`shift` are
  permanent until the next drift/dwell re-pick; only `queue_palette` has a one-shot next-track
  semantic. Track-boundary hook = `begin_dispatch` (`led_color_engine.py:333`, new-track block
  :349-395, queued-apply gated `if not self._lock` :370). A 1-track override needs a counter added
  next to `_queued_palette`, decremented in that block. *(begin_dispatch's `active_deck`/`load_gen`
  trace to the dispatch coordinator `led_dispatch_policy.py:731`; the upstream TRACK_LOADED origin in
  `state_manager.py` is [assumed], not re-walked.)*
- **The bridge does NOT consume Stream Deck MIDI today** — *confirmed*. `streamdeck/streamdeck_midi.py`
  is a **standalone process outside the bridge package**; it only *sends* (ch3 `CHANNEL=2`, notes
  36–50 `NOTE_BASE=36`), pad→message via a JSON sidecar whose `target_kind` is hardcoded
  `"static_look"`. No bridge Python opens the `"Stream Deck"` input port. The closest generic
  note→action dispatch is `soundswitch_midi_input.py` (`PackMidiBinding.target_kind`), which Phase 2
  plans to extend — **not yet built**, flagged live-critical/plan-first.
- **Feedback is one-way today** — *confirmed*. `streamdeck_midi.py` renders its own pads
  (`render_key()` :147, `set_key_image()` :211,239) from **local press-state only**, not bridge/engine
  state. No bridge→Stream Deck feedback path exists.
- **M3 precedence is already specified** — *confirmed*. `led_color_engine_spec.md:485`:
  **`lock > queued > snap > drift`.** §8 (:343-356) specifies exactly `shift/lock/unlock/set_palette/
  queue_palette` and names MIDI as the intended transport.
- **Laser color engine is greenfield** — *confirmed*. Zero palette code in the laser modules. A future
  laser engine cannot reuse LED palette objects (LED-config-scoped RGB); it shares the palette **name**
  and needs its own name→CH8/CH9 mapping (`reference_ss_laser_channels`: CH8 color, CH9 speed).

## Part C — Architecture & locked decisions

**1. Layout (LOCKED).** Stream Deck 3×5, ch3.
- **Top row (5 pads)** = the 5 palettes, one each: `blue_cyan · deep_ocean · indigo · violet · crimson`.
- **Row 2** = `white_sand` pad + lock/unlock pad. (Exact note numbers live in the sidecar; lock-pad
  placement is Fable's to finalize.)

**2. Gesture (LOCKED).**
- **First press** of a palette pad → **queue** it (applies at the next track boundary).
- **Second press of the same pad** (while queued) → **override now** — apply to the current track,
  **held for the current track** (no mid-track drift).
- Pressing a **different** palette pad → a fresh queue (replaces the prior queued).
- Honors M3 precedence **lock > queued > snap > drift**.

**3. Durations (LOCKED).**
- **Override = a 1-track freeze** — the chosen palette holds for the current track, then releases at
  the next track boundary back to automatic selection.
- **Lock = the same freeze, indefinite** — pins the **currently-active** palette across track
  boundaries until unlocked. (Override and Lock are the same "hold" mechanism; override just carries a
  1-track timer.)

**4. `white_sand` palette (LOCKED shape; color TBD).**
- A 6th palette entry, **manual-only**: excluded from automatic selection (weight 0 / manual-only flag
  — `set_palette` still reaches it, drift/dwell/drop-snap never do). Same queue/override/lock gesture
  as any pad; no special-casing on the control side.
- **Per-engine value from one shared name:** LED maps `white_sand` → white/off-white ("sand");
  laser maps `white_sand` → CH8 white. The LED color is a **Template Lab calibration** deliverable
  (see Part D), not fixed here.

**5. Coupling (LOCKED).** One shared palette **name** is the coordination signal. A small
**palette-control coordinator** owns the two-tap gesture, the 1-track override timer, and lock, and
fans the resolved command out to the LED engine now and the laser engine when it exists — **both
follow the same name**. LED ships v1; laser inherits with no coordinator rework.

**6. Wiring path (LOCKED).** The coordinator drives the engine through **runtime commands /
BridgeEvents**, not by calling the stub methods directly, so `StateManager` stays the engine's owner
(per `led_color_engine.py:724-725` and the runtime invariant that StateManager is the only DeckState
writer). Pad input rides the **Stream Deck Phase 2** generic note→action dispatch — palette-control is
its first binding type, so there is one Stream Deck input path in the bridge, not a throwaway listener.

**7. Feedback (LOCKED shape; transport = file).** Each pad renders an **icon reflecting its
palette/action + live state**:
- Palette pads: a **color swatch + name** (`crimson` → red, `white_sand` → white …), with state
  treatment **active = highlighted, queued = pulsing/dim, inactive = muted**.
- Lock pad: a **lock/unlock glyph** reflecting locked vs. unlocked.
- **Transport:** the bridge writes a small **palette-state file** (per pad: name + representative RGB
  computed by the engine + role active/queued/inactive/locked; plus lock state). The standalone deck
  script **reads and renders** it. Palette→color logic stays in the bridge (it has the engine); the
  script only draws. *(Alternative considered: MIDI-back to the script — lower latency but needs an
  input port added; deferred in favor of the file.)*

## Part D — Open items for Fable

1. **1-track override mechanism.** Reuse the engine's existing freeze (`_lock` suppresses
   drift/drop-snap/queued-apply) with a 1-track timer, vs. a separate `_override_tracks_remaining`
   counter — Fable picks; both hook `begin_dispatch` :349-395. Define how override/lock/queue map onto
   the `lock > queued > snap > drift` precedence.
2. **`white_sand` LED color — Template Lab calibration.** "Sand" is a *warm* off-white, but the LED hue
   scale deliberately excludes yellow/orange (hue-band invariant) and the palette schema has only
   green/cyan/blue/purple/red stops — so a true warm sand may need a **fixed-RGB palette type** (small
   engine addition) rather than a hue journey. Resolve during Template Lab calibration; the
   control-wiring is independent of the final color.
3. **`white_sand` manual-only mechanism.** Confirm the engine's `_pick_palette` cleanly excludes a
   weight-0 palette from auto-selection while `set_palette` still reaches it — *unknown, verify*.
4. **Laser side (deferred).** The laser color engine doesn't exist. Two laser decisions from this
   design are recorded in `laser_color_engine_design_spec.md` (Part E there): (a) **white-moment
   mirroring** — lasers go white during the LED's cue-mandated white moments (drop white-strobe, white
   buildups, slot-5 firework), requiring an LED→laser "white now" signal; (b) **`white_sand` → laser
   white** on CH8 (exact value from the CH8/CH9 encoding chart, that doc's open item #1).
5. **Phase 2 input path.** This feature depends on the Stream Deck Phase 2 generic dispatch
   (`streamdeck_midi_bridge_integration_spec.md`, plan-first/live-critical). Sequence: Phase 2 dispatch
   exists (or is built alongside) → palette-control registers as its first binding type.
6. **Feedback file schema + read cadence.** Define the state-file format and how the deck script polls
   it (render-tick read). MIDI-back remains the fallback transport if latency matters.
7. **Sidecar/layout finalize.** Exact note→pad numbers and lock-pad placement in the streamdeck
   sidecar; representative-swatch RGB derivation (engine `_palette_center`/`_p_to_rgb`).

## Part E — Evidence (file:line, HEAD `a1e2f4e` / prior read)

- LED live-control stubs + state + routing note: `led_color_engine.py:724-768`.
- Palette config (5 named palettes): `config/led_look_director.json` `/color_engine/palettes`;
  enumeration `led_color_engine.py:283`.
- Track-boundary hook / queued-apply / lock gate: `led_color_engine.py:333,349-395,370`; caller
  `led_dispatch_policy.py:731`.
- M3 live-control surface + precedence: `led_color_engine_spec.md:343-356,485`.
- Stream Deck sender (standalone, output-only, sidecar): `streamdeck/streamdeck_midi.py` (`CHANNEL=2`,
  `NOTE_BASE=36`, `render_key()`:147, `set_key_image()`:211,239).
- Closest generic note→action dispatch to extend: `soundswitch_midi_input.py` /
  `PackMidiBinding.target_kind` (`soundswitch_pack_loader.py:48-51`); Phase 2 plan
  `streamdeck_midi_bridge_integration_spec.md`.
- Laser coupling (name-only, greenfield): `laser_color_engine_design_spec.md`;
  `reference_ss_laser_channels` (CH8 color / CH9 speed).
- White sources context: `led_color_engine.py:33-38` (white_chance out of scope), per-palette blend
  `_blend_white` :105, reserved slot-5 :609,664; cue-mandated white effects `govee_frame_renderer.py`
  (`drop_white_aggressive`:505, `post_drop_white_shatter`:515).

## Change-contract note

Design-only; changes no runtime behavior, so no `change_contracts.yml` entry yet. Per AGENTS.md §7,
**before** implementation begins, add/extend the `led_govee` (and a new `streamdeck_palette` /
`runtime_commands`) contract with its `docs_update` list, then edit code.
