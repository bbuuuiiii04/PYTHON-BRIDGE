---
doc_status: active-prompt
truth_level: spec-authoring-instructions
last_verified_commit: f822f4c
last_verified_date: 2026-06-25
validation_scope: prompt that directs an agent to AUTHOR a Codex implementation spec for bridge-native static-override TOGGLE support; spec-authoring only, no implementation; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Authoring prompt — Codex spec for static-override toggle mode

You are a senior planning analyst for `rb_ss_bridge_v2`. **Author a Codex
implementation spec**, do not implement. Invoke the `codex-spec` skill and follow
its Part A-E skeleton and its 9-point pre-handoff checklist exactly. Output the
spec to `docs/plans/active/soundswitch_static_toggle_spec.md`. The only file you
write is that spec (plus, if needed, one classification line in
`docs/architecture/doc_index.md`); everything else is read-only verification.

## Plain-language goal

The bridge-native CH1-19 player drives static looks as **momentary only** (a static
is lit only while the controller note is held). The operator's rig uses **mixed**
pads — some momentary (flash), some **toggle** (tap on, walk away, tap off). The
operator is switching to direct-DMX with autoloops on day one, so toggle behavior
can no longer be deferred. The spec must let the bridge-native path reproduce
**both** pad behaviors, without ever letting a latched-on static get stuck on live.

## Hard boundary (read-only authoring)

Do **not** implement, edit runtime/test code, read or edit ignored live config,
start/stop/count the bridge, open MIDI/serial/Enttec/DMX, or connect fixtures. You
may read code/tests and run the read-only software gates to verify claims. Writing
the spec `.md` (and one `doc_index.md` classification line) is the only mutation.

## Source-of-truth order (AGENTS.md §1)

Code → tests → config examples → `runtime_status.py` → file tree → docs → history.
**If a doc conflicts with code, code wins.** Label every claim
**confirmed / assumed / unknown** with `file:line`. Re-verify every reference below
at HEAD before trusting it — these were read at `f822f4c` and may have moved.

## Verified starting facts (re-verify, don't assume)

- **Momentary-only model.** `soundswitch_midi_input.py:214-256`
  (`_process_note_on` / `_process_note_off`): note-on holds the slot, **repeated
  note-on of the same slot is idempotent** (no toggle-off), note-off releases only
  if current, velocity-0 note-on is normalized to note-off
  (`_feed_raw_message:267-269`). [confirmed]
- **Stale-hold timeout collides with toggle.** `soundswitch_midi_input.py:104-115`:
  `_static_held_at` is set on note-on and **never refreshed**, so `snapshot()`
  clears the held slot after `stale_timeout_ms` (default 2000) as `stale_hold`. A
  toggle pad emits exactly one note-on, so it would auto-release ~2 s after being
  toggled on — fatal to toggle. [confirmed]
- **Safety clears that MUST keep working for toggles.** `_clear_held`
  (`:201-212`) is called on `stop`, `panic`, `on_pack_reload`, and worker death
  (`:354-362`); it clears `_held_static_slot` regardless of interaction. [confirmed]
- **The binding carries no mode field.** `PackMidiBinding`
  (`soundswitch_pack_loader.py:40-51`) has only `target_kind` + `target_slot`. The
  exporter does not record toggle-vs-momentary. [confirmed]
- **The consumer is interaction-agnostic.** `state_manager.py:3405-3435` reads
  `snapshot().held_static_slot` and calls `player.hold_static`/`release_static`
  only when `slot != self._pack_last_static_slot`. **Hypothesis to confirm:** a
  toggle that flips `held_static_slot` None↔slot needs **no** StateManager change —
  the existing transition consumer already handles it. [assumed — confirm]
- **Degrade-latch interaction.** `state_manager.py:3418-3428`: a degraded input
  forces `slot=None`; the latch only auto-clears on a clean tick where
  `held_slot is None and not blackout_held` (`:3423`). So a *currently latched-on*
  toggle keeps the degrade latch from clearing until released. Decide whether that
  is acceptable (safe but the toggle stays released after a transient blip until
  re-tapped). [unknown — resolve in spec]
- **Runtime-swap reset.** `set_pack_runtime` (`state_manager.py:3284-3312`) resets
  `_pack_last_static_slot=None` and a swapped bundle boots a fresh input group
  (`held=None`). Any new latch state must reset the same way. [confirmed]
- **Group snapshot conflict rule.** `SoundSwitchMidiInputGroup.snapshot`
  (`:443-460`) returns `held_static_slot=None` on conflicting holds across devices.
  Toggle must not break this. [confirmed]
- **Where toggle mode is declared.** The RE does **not** document a controller
  pad-mode field in the saved SoundSwitch project (only the engine-level override
  is known-momentary, `soundswitch_ghidra_addendum.md:85`). So the exporter most
  likely **cannot auto-extract** toggle-vs-momentary. [assumed — confirm by RE-doc
  read] **Recommended approach:** operator declares toggle slot numbers in bridge
  config; the pack loader stamps an `interaction` field onto each `static_look`
  binding from that set. Confirm the exact config seam (`config.py`,
  `config/*.example.json`, how the `soundswitch_pack` config block is loaded) and
  pick the minimal wiring. Only propose RE'ing the project bytes if config-declared
  slots are genuinely unworkable.
- **Tests today.** `tests/test_soundswitch_midi_input.py`
  (`test_repeated_note_on_idempotent`, `test_note_off_releases_current`,
  `test_vel0_treated_as_note_off`), `tests/test_static_looks.py`. [confirmed]

## What the spec must design (the two real problems)

1. **Per-binding interaction mode.** Add `interaction: momentary | toggle` to the
   binding (default `momentary` so nothing else changes), sourced from
   config-declared toggle slots. Momentary path stays byte-for-byte as today.
2. **Toggle state machine + stale-timeout exemption.** For a `toggle` binding:
   note-on **flips** held (None→slot, or slot→None); note-off is ignored; the
   inactivity stale-timeout does **not** auto-release it; but `_clear_held` (stop /
   panic / pack reload / worker death) and the StateManager degrade path **still**
   release it. A latched-on static must safe-zero on input degradation, pack reload,
   panic, and shutdown — never get stuck on.

## Adversarial scenarios the spec must answer

- A toggled-on static, then the controller disconnects → must release (worker death
  → `_clear_held`).
- A toggled-on static held across a pack runtime swap → must reset, not bleed
  through with a stale slot.
- Mixed momentary + toggle bindings active in the same group/tick → no cross-talk;
  conflict rule preserved.
- A toggle note-on while a *different* slot is already toggled on → define the
  rule (replace vs ignore) and keep it deterministic.
- Velocity-0 note-on on a toggle pad → must not be miscounted as a release that
  silently flips the latch the wrong way.

## Live-safety invariants for Part C

Roadmap invariants 8 and 11 (`soundswitch_exporter_remaining_work.md`): automatic
base resolves software-zero on stale/degraded/swap/shutdown, and a held static loses
to blackout/emergency. The 200 Hz push loop gains no blocking work. No paths, ports,
aliases, device names, or UUIDs in status/logs. The new latch is a new state field —
checklist items 3 (pending-state guard) and 4 (cleanup on **every** transition path)
apply directly to it.

## Before you call the spec ready

Run the `codex-spec` 9-point pre-handoff checklist and an explicit adversarial
self-review (attack the spec; force a stuck-on failure and show the spec prevents
it). Run the read-only gates to ground claims:

```bash
python3 -m unittest tests.test_soundswitch_midi_input tests.test_static_looks tests.test_state_manager_pack_driver
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
git diff --check
```

Then print a short copy-paste **kickstart** in chat (not a file) that points Codex
at the finished spec — per the operator's two-file workflow. Do not implement; do
not enable any output; this is software authoring only and upgrades no hardware
status.
