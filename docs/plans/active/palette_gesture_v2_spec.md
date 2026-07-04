---
doc_status: active-spec
truth_level: implementation-spec, code-grounded
last_verified_commit: 7aef68f
last_verified_date: 2026-07-04
validation_scope: spec only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — Palette gesture v2: tap-toggle + long-press take-and-hold (AWR-121)

Behavior contract: `docs/architecture/palette_control_authority.md` §Palette
Selection Rules v2 banner (rules 1-4, 7-10) and §Feedback & Iconography rule
22's v2 additions — the acceptance oracle. Operator approval 2026-07-04
evening. Supersedes the v1 gesture surface Package 2 shipped (two-tap
override + dedicated lock pad). **Do not implement during a live set; the
operator schedules the landing.**

## Part A — Context (verified at `7aef68f`; read, do not implement)

> **Parallel-work warning (2026-07-04):** a separate session is actively
> debugging/hardening `streamdeck/streamdeck_midi.py` and its tests. Re-verify
> every deck-side claim and line cite below at YOUR implementation HEAD before
> editing; if the deck script has structurally changed, stop and report
> instead of merging blind.

- [confirmed] The deck already sends BOTH edges: `key_to_message(key, pressed)`
  emits note_on at press and note_off at release
  (`streamdeck/streamdeck_midi.py:230-237`). No deck-side change is needed to
  signal press duration to the bridge.
- [confirmed] The bridge discards the release edge for pad kinds: the adapter
  fires `_emit_pad_event` on note-ON only; note-off for `palette_pad` falls to
  the "non-render kind (no-op)" branch (`soundswitch_midi_input.py`,
  note-on dispatch + note-off handler).
- [confirmed] Gesture v1 lives in `led_palette_control.py::_handle_palette`
  (lines 172-195: snapshot `queued_palette == name` → override, else queue) and
  `_handle_lock` (197-207, toggle); pad events carry no phase and an EMPTY
  `intent` string (`intent: ""` — see the test helper `_pad` in
  `tests/test_led_palette_control.py:79-85`). The engine has
  `queue_palette` (validated store, `led_color_engine.py:779`),
  `override_palette(name, start_beat, end_beat)` (fade + `_hold_track` +
  queue-consume, `:784`), `lock()`/`unlock()` (`:761/:765`), and
  `set_palette(name)` (instant apply: clears queue + fade, holds track, does
  NOT touch `_lock` — `:769-777`) — and NO unqueue method.
- [confirmed] The existing override path has a no-beat-authority branch: when
  `get_abs_beat()` returns None, `_handle_palette` applies via
  `engine.set_palette(name)` and RETURNS EARLY
  (`led_palette_control.py:180-187`). Task 3 must not reuse that early return
  blindly for long-press — it would skip the lock (see Task 3).
- [confirmed] `LedPaletteControl` is constructed in ONE place:
  `state_manager.py:521` (the `palette_control` config dict is in scope there
  as `palette_control_config`). Wiring `long_press_s` from config requires a
  constructor-argument change at that site — `state_manager.py` is an allowed
  file for that wiring ONLY.
- [confirmed] Lock pad plumbing to retire from the surface: config
  `lock_note: 57` → `palette_lock_pad` binding row; deck control row
  `(6, "lock", "Lock")` in `compose_layout`
  (`streamdeck/streamdeck_midi.py:184-196`, the lock row at `:185` and its
  `current_rgb` special-case at `:194-195`). v1 layout is ALSO asserted in
  `selftest()` (`:611-615`: key 6 → note 57, `layout[6]["rgb"]`) — those
  asserts must flip with the layout (Task 5.5). The runtime commands
  `led_palette_lock` / `led_palette_unlock` are a separate debug surface and
  STAY.
- [confirmed] The idle-swatch illegibility root cause (the old linear
  `max(12, int(part * 0.22))` crush) was FIXED EARLY on 2026-07-04 by the
  pad-rendering redesign (`d20a622` and follow-ups through `ca98d3f`):
  `_dim()` now dims by HSV value only (`streamdeck/streamdeck_midi.py:272-277`)
  and palette pads render their ramp through it (`:384`). Task 5.3 is
  verify-only. The feedback file's per-palette `rgb` values are correct
  (crimson serves (255,0,80)).
- [confirmed] The feedback writer heartbeats every 5 s (`PaletteFeedbackWriter
  heartbeat_s`), the deck polls at 0.5 s with `FEEDBACK_STALE_S = 10.0`, and
  the press-ack white flash is already deck-local. Precedent for deck-local
  press-time display exists; the deck still decides no state.
- [confirmed] Timing source: the coordinator runs on the state-manager thread
  and handles pad events within a tick of arrival; `time.monotonic()` at
  handle time is sufficient for a 0.5 s threshold (queue-drain jitter is
  milliseconds). Do NOT read the `__enqueue_mono` payload stamp — it is a
  logging concern (`logging_manager.py:203`).
- [confirmed] Baseline suite state at `7aef68f`: 2901 tests, **1 error** —
  `tests/test_streamdeck_midi.py::test_missing_partial_sidecar_keys_are_inactive_noops`
  errors because `ca98d3f` added `latched=` to the `render_key` call in
  `on_key` (`streamdeck/streamdeck_midi.py:477-478`) without updating that
  test's `render_key` mock lambda. 5 skipped / 1 expected failure are normal.
  Run the suite FROM THE REPO ROOT (`python3 -m unittest discover tests`) —
  running from the parent dir falsely fails a laser-color test on a
  cwd-relative config path.

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute Rules
- LED-surface only. Out of scope: laser/blackout files, `drop_presentation.py`,
  `soundswitch_laser_player.py`, `laser_color_engine.py`, the exporter/pack,
  Govee renderers.
- Behavior that must not change: mute pads, Laser Solo pad, Rainbow toggle,
  static-look pads, runtime commands (`led_palette_queue/override/lock/unlock`
  keep their explicit-intent semantics), the feedback heartbeat, automatic
  selection with no pads pressed.
- Expected error handling: unknown palette names no-op (as today); a missing
  press-down record for a release is treated as a tap; no broad try/except.
- The state-manager thread gains no I/O; press-duration math is arithmetic on
  `time.monotonic()` values.

### Task 0 — restore the green baseline (test harness only)
If (and only if) the Part A baseline error still reproduces at your HEAD, fix
the `render_key` mock in
`tests/test_streamdeck_midi.py::test_missing_partial_sidecar_keys_are_inactive_noops`
to accept the `latched` keyword `ca98d3f` introduced (match how the sibling
tests in that file stub it). No production-code change. If a parallel session
already fixed it, skip and note that. The suite must be fully green before
Task 1 starts.

### Task 1 — `soundswitch_midi_input.py`: release edge for palette pads
In `_process_note_off`, route `target_kind == "palette_pad"` to
`_emit_pad_event(binding, phase="up")`; extend `_emit_pad_event` to attach
`payload["phase"]` (`"down"` from note-on, `"up"` from note-off) for
`palette_pad` ONLY. Other pad kinds keep note-off as a no-op. Update the
`models.py` `Ev.LED_PALETTE_PAD` comment: payload
`{name: str, phase: "down"|"up", intent?: queue|override}`.

### Task 2 — `led_color_engine.py`: unqueue seam
Add `unqueue_palette(name: str) -> None`: clear `_queued_palette` iff it
equals `name`. Nothing else changes.

### Task 3 — `led_palette_control.py`: gesture v2 state machine
1. Constructor takes `long_press_s: float = 0.5` (wired from config in
   Task 4); keep a `_pad_down: dict[str, float]` of palette name →
   `time.monotonic()` at phase="down".
2. On `LED_PALETTE_PAD` — dispatch precedence (exact):
   - **Runtime-command events** = `intent` is a NON-EMPTY string (pad events
     carry `intent: ""` today and no `intent` after Task 1; both mean "no
     intent"). These keep today's explicit paths unchanged, including the
     no-beat `set_palette` fallback and the rainbow gate.
   - **Gesture events** = `phase` in `("down", "up")`. While Rainbow mode is
     on: drop both phases (pads inert; no `_pad_down` mutation).
   - **Legacy shape** (no non-empty intent, no phase — old adapter or stale
     test fixture): treat as a **tap**.
   - `phase == "down"`: record `_pad_down[name]`; no engine action.
   - `phase == "up"`: `held = now - _pad_down.pop(name, now)` (missing down →
     0.0 → tap).
     - `held >= long_press_s` → **take-and-hold**: if engine snapshot shows
       `lock` and `current_palette == name` → no-op (idempotent re-hold).
       Else if `get_abs_beat()` is None (no beat authority) →
       `engine.set_palette(name)` **then `engine.lock()`** — do NOT reuse the
       existing early return, which would take without locking. Else
       `engine.override_palette(name, …existing anchor derivation…)` then
       `engine.lock()` (rule 7: the mid-fade lock pins the fade target on
       completion — reuses the existing rule-6/9 behavior, no new fade code).
     - else **tap**: if `lock` and `current_palette == name` →
       `engine.unlock()`; elif `queued_palette == name` →
       `engine.unqueue_palette(name)`; else `engine.queue_palette(name)`.
   - **Accepted edges (document in code comment, no extra state):** a press
     straddling Rainbow-ON has its release eaten; the stale `_pad_down` entry
     is bounded (≤ palette count) and overwritten by the next down. A hold
     spanning a full Rainbow blip (down before ON, up after OFF) counts its
     full duration — matches physical intent. A track boundary landing inside
     a sub-0.5 s press can consume the queue so the tap re-queues instead of
     unqueueing — rare, operator-visible (pulsing pad), self-corrects with
     another tap.
3. `_handle_lock` stays for the runtime commands only.
4. Feedback payload additions: top-level `long_press_s` (the deck's display
   threshold — one shared number) and `gesture: 2` (lets the deck script
   assert it is rendering the surface the bridge speaks). The locked-pad
   display needs NO new field: the deck derives it from `lock` +
   `current_palette`.

### Task 4 — `led_config.py` + `config/led_look_director.example.json`
`palette_control` gains `long_press_s: 0.5` (float, 0.15-2.0 validated).
`lock_note` becomes OPTIONAL: absent → no `palette_lock_pad` binding row is
built (v2 surface); present → row still built (back-compat, harmless). The
example config drops `lock_note` and adds `long_press_s`. Note in the report
that the operator's live config should mirror both edits.

### Task 5 — `streamdeck/streamdeck_midi.py`: layout, padlock, legible dim
1. `compose_layout`: remove the `(6, "lock", "Lock")` control row — key 6
   renders dark (None). Controls keep 7/8/9/14.
2. Padlock glyph: when `feedback["lock"]` is true, draw the padlock over the
   ACTIVE palette's pad (the row whose name == `current_palette`), on top of
   its full-color fill.
3. Legible dim (authority rule 22 v2): LANDED EARLY 2026-07-04 in the
   pad-rendering redesign (`d20a622` — `_dim()` HSV value-only dim, plus the
   glyph-first no-text rendering). Verify it is present; do NOT re-implement.
   The old `0.22` linear crush no longer exists.
4. Deck-local long-press cue: while a palette key is physically held, once the
   local hold time crosses the feedback file's `long_press_s`, render the
   padlock-pulse on that key (display only — the bridge's own measurement
   decides the action; a rare threshold disagreement self-corrects at the
   next feedback poll).
5. `--selftest` additions: key 6 is None in a v2 layout; the dim function
   preserves hue ordering for the five journey swatches (pure function).

### Task 6 — tests
- Engine: `unqueue_palette` clears only a matching queue.
- Coordinator matrix (extend `tests/test_led_palette_control.py`): tap
  queues; tap-again unqueues; tap under lock on the active pad unlocks (no
  re-pick, color stays); tap a different pad under lock queues (lock
  untouched); long-press takes-and-locks (override called then lock);
  long-press consumes the queue; long-press on another palette transfers the
  lock; idempotent re-hold no-ops; sub-threshold release is a tap; missing
  down-record is a tap; rainbow inert on both phases; runtime-command intents
  unchanged.
- Adapter: palette_pad note-off emits phase="up"; other kinds' note-off still
  no-op.
- Deck: layout key-6-dark; padlock renders on the active pad iff lock;
  HSV-dim hue preservation.
- FLIP the v1 tests that encode second-tap-override and the lock pad
  (`test_queue_same_pad_overrides_consumes_queue_and_fades`, the lock-pad
  rows in layout tests) to the v2 contract — update, never delete coverage.

## Part C — Invariants That MUST Still Hold
- Manual always wins; lock-transfer laws (authority rules 8-9) unchanged in
  substance; unlock never re-picks (rule 10).
- The 200 Hz push loop / state-manager thread gains no file, HID, or network
  I/O; the feedback writer thread and its 5 s heartbeat are untouched.
- The deck script decides no lighting state (threshold CUE is display-only;
  the bridge's measurement is authoritative) and never emits on MIDI ch 1-2.
- Blackout systems, drop presentation, and laser color are untouched.
- LED hue-band invariant unchanged (dim math is display-side only).
- All AGENTS.md §6 invariants; no bridge restart authorized by this spec —
  the operator schedules the landing and the restart.

## Part D — Tests
Task 6. Pure seams: the tap/long-press decision given (held_s, snapshot) —
factor it so it is testable without threads or MIDI; the HSV dim function;
layout composition.

## Part E — Acceptance
1. Contract-first: extend the `streamdeck_palette` contract in
   `docs/agents/change_contracts.yml` (docs_update:
   `docs/architecture/palette_control_authority.md`,
   `docs/plans/active/streamdeck_palette_control_design_spec.md` (D.1 delta),
   `docs/subsystems/led_govee.md`, `docs/subsystems/runtime_commands.md`,
   `docs/status/active_work_registry.md`) BEFORE code.
2. Tasks 1-6 green; full suite green; the three AGENTS.md §8 hard checks pass.
3. No diff outside: `soundswitch_midi_input.py`, `models.py` (comment),
   `led_color_engine.py` (unqueue only), `led_palette_control.py`,
   `led_config.py`, example config, `streamdeck/streamdeck_midi.py`, tests,
   contract docs.
4. §10 status language only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## When You Finish
Report changed files, test counts, checks output, and the operator summary:
tap = queue/unqueue toggle; hold half a second = take this color now and lock
it (padlock shows on that pad); tap the padlocked pad to let automation
resume next track; key 6 is dark; idle pads now show their real colors dimmed
instead of near-black; live config needs `long_press_s` added and `lock_note`
removed; deck-in-hand validation remains the operator's gate.
