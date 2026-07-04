---
doc_status: current
truth_level: code-verified findings; design-intent for the proposed riders
last_verified_commit: cb9b081
last_verified_date: 2026-07-04
validation_scope: read-only analysis of bridge-runtime code + live logs; nothing here is implemented
---

# Stream Deck Surface — Bridge-Side Findings & Proposed Riders (2026-07-04)

Companion to the deck-side hardening pass (design spec Part D.2, authority rules 25-27).
These findings live in bridge-runtime lanes (`__main__.py`, `state_manager.py`,
`soundswitch_midi_input.py`, `scripts/ss_bridge_watcher.sh`) and were **not** implemented in
that pass — each needs an operator go and its own implementation handoff.

## F-B1 — Pack-runtime teardown still kills pad input (incident 1 architecture wart) — HIGH

`__main__.py` (`worker_start_failed` paths, lines ~549-641): a frame-sender/laser OUTPUT
failure (e.g. Enttec serial absent) disables the whole pack bundle, stopping the
`SoundSwitchMidiInputGroup` with it — LED-side pads die as collateral. With the runtime
disabled, `midi_input` is `None`, so `input_degraded` (`state_manager.py`, pack driver tick)
computes vacuously False: pads dead, status green.

**Proposed rider:** split input-worker lifecycle from output-worker lifecycle — keep the MIDI
input group (and the palette/control pad events it feeds) alive when only the output side
fails, and make `input_degraded` reflect "inputs configured but not serving" whenever the
group is stopped/absent for any reason other than "no inputs configured".

## F-B2 — Never-seen input port retries log WARNING every 5 s forever — MEDIUM (log health)

`soundswitch_midi_input.py:524-527`: for a device that has never appeared (the absent
DDJ-800), every 5 s retry logs `[SS-MIDI] input port gone; retrying exact port` — 83 lines in
the first 6 minutes of the current live session, ~17k/day steady state. Repo log policy
(operator feedback): high-frequency diagnostics belong at DEBUG; INFO/WARNING are for
outcomes/transitions.

**Proposed rider:** log the outage once per episode (and the recovery), demote per-retry lines
to DEBUG.

## F-B3 — Static-look layer state is not in the feedback file — MEDIUM

The deck-local toggle latch is display-only double-tracking; the true held-layer state lives
in `SoundSwitchMidiInputAdapter._layers`. The deck-side pass makes the latch survive USB
reconnects and clear on bridge restart (feedback `seq` regression), which closes the observed
drift windows — but the deck still cannot *display* bridge truth for static looks.

**Proposed rider:** publish held static slots (slot + toggle/press kind) into the palette
feedback payload (StateManager already snapshots the adapter each pack tick; hand
`LedPaletteControl` a getter like the existing `get_laser_blackout` pull) and render
static-look latches from feedback like every other pad. Deletes the deck-local latch model.

## F-B4 — Watcher leaves the deck script unsupervised during bridge gaps — MEDIUM

`scripts/ss_bridge_watcher.sh` manual mode: `start_streamdeck` runs only while `bridge_pids`
is non-empty, and when the manual terminal closes the watcher itself exits (after
`stop_streamdeck`). Observed 2026-07-04: deck dead 16:24:43 → 16:36:47 (12 min) because the
watcher session ended; the next watcher started it again. Also explains the "USB write-error
flakiness": both `Failed to write out report (-1)` events (16:24:43, 17:24:10) are
`stop_streamdeck`'s SIGTERM landing mid-`hid_write` during intentional teardown — same-second
`shutdown` lines prove `stop` was already set — not spontaneous device faults.

**Proposed rider:** in manual mode keep respawning the deck script while the watcher lives
(static pads are useful without the bridge), or log the intentional stop reason into
`/tmp/streamdeck.log` so a teardown is never mistaken for flakiness.

## Operator notes (no rider)

- The current live session's bridge.log shows continuous OS2L `connect-fail ... Connection
  refused` — SoundSwitch simply wasn't accepting OS2L during this dev window. Benign if SS was
  closed; worth a glance before the next live set.
- Watcher-driven bridge restarts take >10 s end-to-end, so every such restart crosses
  `FEEDBACK_STALE_S` and boots the deck static-only for ~1 s until the new heartbeat lands.
  This is now loudly logged deck-side (boot degraded line + heal line with note ranges); no
  bridge-side change proposed.
