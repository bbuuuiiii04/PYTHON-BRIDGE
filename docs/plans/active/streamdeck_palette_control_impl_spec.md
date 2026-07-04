---
doc_status: active-spec
truth_level: implementation-spec, code-grounded
last_verified_commit: bd96b32
last_verified_date: 2026-07-04
validation_scope: spec only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — Stream Deck palette control + deck surface (Package 2 of AWR-119)

Behavior contract: `docs/architecture/palette_control_authority.md` — its rules
are the acceptance oracle. Design evidence:
`docs/plans/active/streamdeck_palette_control_design_spec.md` Parts B-C.8, C.10.
Package 1 (`laser_blackout_rewire_spec.md`) should land first but only the
Laser-mute config row depends on it conceptually; there is no code dependency.

## Part A — Context (verified at `bd96b32`; read, do not implement)

- [confirmed] Engine stubs exist, unwired: `led_color_engine.py` `lock()` :728,
  `unlock()` :732, `set_palette` :736-742 (ignores `_lock`, does NOT clear
  `_queued_palette`), `queue_palette` :744-747 (stores unvalidated),
  `shift()` :749, `snapshot()` :759-768. Header :724-725: outside callers must
  route through BridgeEvents/runtime commands.
- [confirmed] Track-boundary block: `begin_dispatch` :333, new-track block
  :351-399; queued-apply is gated `if not self._lock:` :370 (queue kept, not
  consumed, while locked); dwell decrement :371; queued apply :374-386; dwell
  re-pick :387-396; drop-snap gate `not self._lock` :408-411. Caller:
  `led_dispatch_policy.py:731` inside `_dispatch_led_automation` (:637),
  invoked from `_push_tick_inner` (`state_manager.py:3029`) — i.e. **the
  state-manager thread IS the 200 Hz push loop thread**
  (`state_manager.py:586,643,657,666`). No file I/O may be added anywhere on
  this path.
- [confirmed] Weights: `Palette.weight` (`led_models.py:64`, default 1.0);
  all auto selection routes `_pick_palette` (:293,389,414,751) →
  `_weighted_choice` (:135-165); weight 0 = zero mass; `set_palette` bypasses.
  Palettes enumerated from config insertion order (:283-286).
- [confirmed] Event rail: producers enqueue `BridgeEvent` onto `event_queue`
  (`state_manager.py:342`); `_drain_events` :911 → `_handle_event` :947
  (if/elif on `Ev.*`); LED events route via :1208-1214 to `_handle_led_event`
  (`led_dispatch_policy.py:370`). Command rail: `runtime_status.py:413,427`
  branches call constructor-injected callbacks (:271-272, stored :289-290),
  provided by `__main__.py:1510-1511` as thin closures (:1401,:1419) that just
  enqueue BridgeEvents. **Copy these two patterns exactly.**
- [confirmed] MIDI input: `SoundSwitchMidiInputGroup` opens one adapter per
  bound device; bindings today come only from the pack loader
  (`soundswitch_pack_loader.py:40-51,358-368`); the adapter branches on kinds
  `static_look` :259 and `blackout_mask` :280 (note-off :295-316); match key
  is (device, type, zero-based channel, data byte) :346-374. Device
  `"Stream Deck"` is already bound (ch2 notes 36/37/43 → static looks).
- [confirmed] Deck script: `streamdeck/streamdeck_midi.py` sends every pad on
  `CHANNEL = 2` (:32,:136); sidecar loader filters to ch2 static_look rows,
  sorts by note, assigns keys by index (:77-107) — the "waterfall" to retire;
  `render_key` :147-168 draws with PIL; supervision loop polls 1 Hz :246-247;
  `--selftest` :268-285 asserts channel safety.
- [confirmed] Atomic-write + writer-thread precedent to copy:
  `atomic_write_json` (`runtime_status.py:631-636`, tmp + `os.replace`) and
  `StatusWriter(threading.Thread)` (:105, loop :138-145) writing
  `/tmp/rb_ss_bridge_v2_status.json` (:16), already polled by
  `tools/led_pad_web.py` / `tools/laser_pad_web.py`.
- [confirmed] Govee frames render on a separate `GoveeRealtimeRunner` thread
  (`govee_realtime_runner.py:138-147`); LED cue colors are resolved at
  dispatch time on the state-manager thread.

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute Rules
- Out of scope: `soundswitch_laser_player.py`, `laser_executor.py`,
  `smart_*`, `drop_lifecycle.py`, `anlz_reader.py`, the drop presentation
  policy (Package 3), and the laser color engine (Package 4). No laser
  behavior changes beyond the ONE config binding row in Task 5.
- Behavior that must not change: automatic palette selection when no pads are
  used (drift/dwell/drop-snap outputs identical when `_queued_palette` is
  empty and `_lock`/fade/mode are off); Govee rendering; static-look pads;
  existing runtime commands.
- **No file/network/HID I/O on the state-manager thread.** The feedback file
  is written ONLY by the new writer thread.
- Error handling: propagate or fail closed; no broad try/except; a malformed
  config block disables palette control with one logged error (bridge runs on).

### Task 1 — `led_models.py` + `led_color_engine.py`: engine semantics
1. `Palette` gains `type: str = "journey"` (allowed: `journey`, `fixed_rgb`,
   `rainbow`) and `rgb: tuple[int,int,int] | None = None` (required iff
   `fixed_rgb`). Config parse + validation in the existing palette load path.
2. **Queue-overrides-lock reorder** in the new-track block: apply
   `_queued_palette` FIRST, unconditionally (validated against config as
   today :377); only the dwell decrement and dwell re-pick stay under
   `if not self._lock:`. Lock state itself is untouched by the apply
   (authority rules 8-10). Clear `_hold_track` and any active fade here too.
3. **One-track hold**: new field `_hold_track: bool = False`; add
   `and not self._hold_track` to the drop-snap condition (:408-411).
4. **Override + fade**: new method
   `override_palette(name, *, start_beat: float, end_beat: float)` —
   validates `name in self._config.palettes`, clears `_queued_palette`, sets
   `_hold_track = True`, and starts a fade: `_fade_from_p = self._anchor_p`,
   `_fade_target = name`, `_fade_start/_end_beat` as given. New method
   `advance_fade(abs_beat: float)`: while fading, linearly interpolate
   `_anchor_p` from `_fade_from_p` toward `_palette_center(_fade_target)` in
   p-space; at `abs_beat >= _fade_end_beat`, set `_current_palette =
   _fade_target`, `_anchor_p = center`, clear fade. Any manual action
   (queue/override/shift/set) replaces the fade from the current blended
   position; a new track cancels it (item 2). `snapshot()` gains
   `fading: bool` and `fade_target`.
5. **Mode override (Rainbow)**: new field `_mode_override:
   dict[str, str] | None = None` + setters `set_mode_override(mapping)` /
   `clear_mode_override()`. When set, color resolution uses
   `mapping.get(role, mapping.get("*", …))` to choose the palette for that
   cue instead of `_current_palette`; ALL journey state (current, queued,
   lock, dwell, fade — fade completes instantly at freeze per authority rule
   18) is untouched while set. `rainbow`-type palettes resolve as a full-hue
   wheel cycle (hue advances per cycle/section, full 0-360 range — the
   yellow/orange exclusion deliberately does not apply); `fixed_rgb` resolves
   to its constant.
6. Caller wiring: in `_dispatch_led_automation` (`led_dispatch_policy.py:637`),
   call `engine.advance_fade(abs_beat)` immediately before
   `engine.begin_dispatch(...)` (:731). Source `abs_beat` from the beat
   authority already in scope in `_push_tick_inner` around :3029 —
   [assumed: a beat/elapsed value is in scope there; Codex verifies and, if
   not, threads it from `_push_tick_inner`'s existing beat state. Do NOT
   invent a new beat computation.]

### Task 2 — `models.py` + `runtime_status.py` + `__main__.py`: rails
1. New `Ev` constants (LED block, deck 0):
   `LED_PALETTE_PAD = "led_palette_pad"` (payload `{name}`),
   `LED_PALETTE_LOCK_PAD = "led_palette_lock_pad"`,
   `LED_MUTE_PAD = "led_mute_pad"`,
   `LED_RAINBOW_PAD = "led_rainbow_pad"`.
2. New runtime commands mirroring them (for LED Pad web/debug):
   `led_palette_queue <name>`, `led_palette_override <name>`,
   `led_palette_lock`, `led_palette_unlock`, `led_rainbow_toggle` — same
   callback-injection pattern as `led_scene` (`runtime_status.py:271-290,
   413-447`; closures in `__main__.py` beside :1401-1419 that enqueue the
   events; registration beside :1510-1511). The two explicit queue/override
   commands bypass the two-tap gesture (they state intent directly); the pad
   event uses the gesture.
3. `_handle_event` (`state_manager.py:947`): route the four new kinds to the
   coordinator (Task 3).

### Task 3 — NEW `led_palette_control.py`: coordinator + feedback writer
A plain object owned by StateManager (constructed with the engine, the LED
blackout entry points, and a config block), invoked ONLY on the state-manager
thread from `_handle_event`. Contents:
1. **Gesture** (authority rules 1-6): on `LED_PALETTE_PAD {name}` — if
   `engine.snapshot()["queued_palette"] == name` → override:
   `engine.override_palette(name, start_beat=…, end_beat=min(next_phrase, start+32))`
   (next phrase anchor beat from the smart-phrasing state already surfaced to
   StateManager; unknown → start+32); else → `engine.queue_palette(name)`.
2. **Lock pad**: toggle `engine.lock()`/`unlock()` per current snapshot.
3. **LED mute pad**: coordinator-held toggle emitting the EXISTING
   `Ev.LED_BLACKOUT` / `Ev.LED_CLEAR_BLACKOUT` handling path with an
   owner-tagged payload `{reason: "led_mute_pad"}` — distinct owner from any
   future automation owner (authority rules 13-14; Package 3 adds the
   spotlight owner). The mute state is coordinator state, surfaced in the
   feedback file.
4. **Rainbow pad**: toggle. On:
   `engine.set_mode_override({"breakdown": "white_sand", "buildup":
   "white_sand", "*": "rainbow"})`; off: `clear_mode_override()`. While on,
   palette/lock/white_sand pad events are ignored (feedback shows them dim).
5. **Feedback writer**: a dedicated daemon thread (copy the `StatusWriter`
   shape, `runtime_status.py:105-145`), event-signaled with a ≥100 ms
   debounce, writing `/tmp/rb_ss_bridge_v2_palette_state.json` via
   `atomic_write_json`. Payload = authority §Observability + design spec C.7
   schema v1 (`lock`, `led_blackout`, `laser_blackout` [from the MIDI-input
   snapshot the pack driver already reads], `laser_solo: "off"` [static until
   Package 3], `rainbow`, `palettes[]` with per-pad `name/note/rgb/state`,
   `seq`). State-manager thread only ENQUEUES a snapshot dict; the writer
   thread serializes and writes.

### Task 4 — `soundswitch_midi_input.py`: pad-event binding kinds
1. Extend the adapter's note-on dispatch (:259-288) with kinds
   `palette_pad`, `palette_lock_pad`, `led_mute_pad`, `rainbow_pad`: each
   enqueues the matching BridgeEvent via a new constructor-injected
   `event_sink: Callable[[BridgeEvent], None] | None` (the group passes it
   through; `__main__.py` supplies `event_queue.put`). Note-off for these
   kinds: no-op. No snapshot/overlay changes — these kinds never appear in
   `held_layers`.
2. Bindings source: a new optional constructor argument
   `extra_bindings: Sequence[PackMidiBinding]` on the group, merged with the
   pack's loaded bindings at adapter construction. `PackMidiBinding.target_kind`
   literal (`soundswitch_pack_loader.py:48-51`) gains the four new kinds plus
   a `target_name: str | None` field carrying the palette name.

### Task 5 — config: `led_config.py` + `config/led_look_director.example.json`
1. New `/color_engine/palette_control` block: `{enabled: bool, device:
   "Stream Deck", channel: 2, palette_notes: {name: note, …} (51-55),
   white_sand_note: 56, lock_note: 57, led_mute_note: 58, laser_mute_note: 59,
   rainbow_note: 60}`. Loader builds the `extra_bindings` rows (palette pads →
   `palette_pad` with `target_name`; lock/mute/rainbow → their kinds;
   `laser_mute_note` → an existing-kind `blackout_mask` row — zero new laser
   code, per `laser_blackout_authority.md` rule 5).
2. Example config gains the block, the `white_sand` palette entry
   (`weight: 0, type: fixed_rgb, rgb: [placeholder]`, comment: Template Lab
   calibrates), and a `rainbow` palette entry (`weight: 0, type: rainbow`).
   The live config is the operator's to mirror — note it in the report.

### Task 6 — `streamdeck/streamdeck_midi.py`: pinned layout + icons
1. Layout per authority §The Deck Surface: keys 0-5 palettes+white_sand and
   6-9 control pads are driven by the FEEDBACK FILE (names, notes, states);
   keys 10-13 static looks from the sidecar (sorted by note, overflow logged
   + dropped); key 14 rainbow. `key_to_message` sends the per-key note from
   this composed layout (still `CHANNEL = 2`).
2. Poll `/tmp/rb_ss_bridge_v2_palette_state.json` mtime in the supervision
   loop, tightened to 0.5 s; re-render changed pads. File absent/stale (`seq`
   unchanged > 10 s is fine — only mtime matters) → palette/control pads
   render blank; static-look pads unaffected.
3. Icons per authority §Feedback & Iconography: programmatic PIL — swatch +
   name for palettes (state: bright/dim/pulsing via alternate-tick render),
   padlock over current-palette color, red slash mutes, amber starburst solo
   (renders from `laser_solo` field; stays "off" until Package 3), rainbow
   arc, ~150 ms white press flash. Keep `icons/<n>.png` override support.
4. Extend `--selftest`: channel safety unchanged; add layout composition and
   feedback-file → pad-state mapping assertions (pure functions).

### Task 7 — tests: `tests/test_led_palette_control.py` (+ engine test extensions)
- Engine: queue-applies-under-lock with lock transfer; override consumes
  queue; `_hold_track` suppresses snap and clears at boundary; fade
  interpolation stays in p-space, completes at end_beat, caps at 32, cancels
  on new track, restarts from blended position on manual action; mode
  override maps roles, leaves journey untouched, freeze/restore exact;
  weight-0 exclusion for `white_sand`/`rainbow` across a large seeded run.
- Coordinator: full gesture matrix (authority Required Tests 1-4), mute
  toggle owner isolation, rainbow pad-inertness, feedback payload correctness.
- Writer: atomic write (tmp+replace), debounce, no writes from the calling
  thread (assert via thread identity in a test hook).
- MIDI input: new kinds → events with correct payloads; note-off no-ops;
  extra_bindings merge; existing static_look/blackout_mask behavior unchanged.
- Deck script selftest additions green.

## Part C — Invariants That MUST Still Hold
- 200 Hz push loop / state-manager thread gains NO file, network, or HID I/O
  (feedback writes on the writer thread only).
- StateManager remains the engine's only runtime mutator; deck/web reach it
  only through BridgeEvents/runtime commands (`led_color_engine.py:724-725`).
- LED hue-band invariant (no yellow/orange) everywhere except rainbow-type
  resolution.
- Manual always wins; automation can never un-mute (authority rules 12-15).
- Deck script never emits on MIDI channels 1-2 (`--selftest` guard stays).
- Static-look pads and the Phase-2 compositor path are byte-identical in
  behavior.
- All AGENTS.md §6 invariants; no bridge restart authorized.

## Part D — Tests
Task 7. Pure seams: fade math, gesture decision, layout composition, icon
state mapping, feedback payload — all testable without hardware, files
(writer tested against a tmpdir), or MIDI devices (feed messages directly,
per existing `soundswitch_midi_input` tests).

## Part E — Acceptance
1. Contract-first: extend `led_govee` and add a `streamdeck_palette` entry in
   `docs/agents/change_contracts.yml` (docs_update: subsystem cards
   `led_govee.md` + `runtime_commands.md`, `palette_control_authority.md`,
   the design spec, `active_work_registry.md`) BEFORE code.
2. Tasks 1-7 green; full suite green; docs checks pass; contract docs updated
   with §10 status language (`implemented`/`software-tested` at most).
3. No diff outside: the two engine files, `models.py`, `runtime_status.py`,
   `__main__.py`, `soundswitch_midi_input.py`, `soundswitch_pack_loader.py`
   (binding fields only), `led_config.py`, example config,
   `led_palette_control.py`, `streamdeck/streamdeck_midi.py`, tests, and the
   contract-mandated docs.

## When You Finish
Report: changed files, test counts, checks output, and the operator summary:
what each pad now does live, that automatic color behavior is unchanged until
pads are pressed, that the live config needs his `palette_control` +
`white_sand`/`rainbow` mirror, and that everything is
SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED pending his deck-in-hand pass.
