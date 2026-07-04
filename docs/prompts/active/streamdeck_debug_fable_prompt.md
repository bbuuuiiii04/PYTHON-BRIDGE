---
doc_status: current
truth_level: design-intent
last_verified_commit: ca98d3f
last_verified_date: 2026-07-04
validation_scope: Claude Fable 5 prompt text only; execution happens in the Fable session Brandon launches
---

# Fable 5 Prompt — Debug and Harden the Entire Stream Deck Surface

**Target model:** Claude Fable 5. **Effort:** high; xhigh on the device-error
recovery path and anything that can silently drop operator input.

> Benign local software work on Brandon's DJ lighting bridge
> (`rb_ss_bridge_v2`): a Stream Deck pad surface driving LED palettes and
> stage-lighting mutes. "Laser," "blackout," "mute," "solo" are ordinary
> stage/mixer terms. "Debug," "stress," and "adversarial" mean strict about
> evidence — normal software correctness only.

## Mission

The Stream Deck surface (deck script → virtual MIDI → bridge adapter →
coordinator → feedback file → deck render) has produced five distinct live
failures in one day. Each was found by the operator's fingers, not by tests.
Debug the whole surface end to end, root-cause the one still-unexplained
failure, find the latent siblings of the known bug classes before the
operator does, fix what is yours to fix, and leave behind tests that would
have caught every one of these. The operator uses this surface live; silent
input loss and lying pads are the two unforgivable failure modes.

## Incident ledger (all 2026-07-04; all confirmed except #5)

1. **Runtime teardown killed all pad input.** Enttec serial absent → frame
   sender failed → entire pack runtime disabled (`worker_start_failed`) →
   MIDI input workers dead, `input_degraded` read False (vacuous). Pads dead
   for hours; nothing surfaced it. Architecture wart on file: LED-side pads
   are collateral of a laser OUTPUT device failure.
2. **Feedback starvation.** Change-gated publishing left the feedback file's
   mtime stale; the deck blanks pads at `FEEDBACK_STALE_S = 10` → all
   feedback pads blank. Fixed with a 5 s writer heartbeat (`5b5adcd`).
3. **Projection drop.** A new payload field (`ramp`) was added at the
   producer and consumed at the renderer, but `_palette_row`'s whitelist
   projection silently dropped it in between (`12e230d` fixed).
4. **Caller-contract regression.** `on_key`/the render loop passed the
   deck-local `led_state` LATCH into `render_key`'s `pressed` parameter; the
   redesigned renderer treats `pressed` as the physical-press white flash →
   every toggle-interaction pad froze white on first press (`ca98d3f`
   fixed: `pressed` = physical only; latch rides `latched`, honored only by
   static-look rows). The render smoke test passed booleans directly and
   never exercised the real caller.
5. **UNEXPLAINED — your primary debug target.** `/tmp/streamdeck.log`:
   `17:24:10 device error: Failed to write out report (-1) - will reconnect`
   → the recovery instance came up `live - notes 36-43` (static-only layout:
   `load_feedback_state()` returned None) while the bridge was up and the
   feedback file heartbeat-fresh. Palette keys were unbound; the operator's
   presses were silently dropped (`row is None → return`) — his "cannot
   queue at all" window. Earlier instances (16:36, 16:50) also logged 36-43.
   Explain why feedback read None at those instants (mtime race? time.time
   vs writer cadence at exactly 10 s? exception class swallowed? layout
   healed later but logline only prints once — did it heal?), then fix
   whichever of these holds: the reader, the staleness window, the
   once-only logline that hides recovery, and add a re-log on layout
   change so a degraded layout is always visible in the log.

## Scope and evidence

Read: `streamdeck/streamdeck_midi.py` (all of it — lifecycle, singleton
lock, acquire/reconnect loop, on_key, clear_flash timer, supervision loop,
selftest), `led_palette_control.py` (payload producer + writer heartbeat),
`soundswitch_midi_input.py` (pad binding kinds, event sink, worker
lifecycle), the wiring in `state_manager.py`/`__main__.py`, the watcher's
streamdeck autostart (`scripts/ss_bridge_watcher.sh`), and the deck-related
tests. Contracts: `docs/architecture/palette_control_authority.md`
(§Feedback & Iconography; note the v2 gesture banner is NOT yet implemented
— v1 two-tap is live behavior). Logs: `/tmp/streamdeck.log`,
`/tmp/bridge.log`, `/tmp/rb_ss_bridge_v2_palette_state.json`.

Hunt list beyond #5: deck-local `active_keys` double-tracking vs feedback
truth (toggles that drift from bridge state across reconnects — the latch
survives a device reconnect but the bridge state may have moved); the
clear_flash 0.15 s Timer racing the supervision loop's re-render; feedback
schema fields silently dropped by ANY projection (make projections
pass-through-by-default or test-pinned); reconnect-loop edge cases (device
absent at boot, Elgato app holding the device, USB re-enumeration);
singleton-lock stale-file behavior; watcher restart interplay (pkill →
respawn window); pulse-tick rendering cost (full 15-key redraw every 0.5 s
while anything pulses).

## Boundaries

- The bridge may be RUNNING (operator runs truth mode at the desk). NEVER
  restart, kill, or send input to the bridge process; never touch laser or
  runtime code paths. You may read everything and run read-only shell,
  tests, and the three AGENTS.md §8 checks.
- You may fix the DECK SCRIPT (`streamdeck/streamdeck_midi.py`), the
  feedback payload producer (`led_palette_control.py` display-payload side
  only), and tests directly — display-surface lane, the precedent of this
  session. You may bounce ONLY the deck script (`pkill -f
  streamdeck_midi.py`; the watcher respawns it in ~3 s). Anything requiring
  bridge-runtime code changes (adapter, state_manager, worker lifecycle,
  the incident-1 architecture wart) becomes a written finding + a proposed
  spec/rider — do not implement those.
- Git: commit by pathspec only (parallel sessions leave staged files);
  never any force-push; if origin advances, rebase your own unpushed
  commits only.
- Suite baseline: 2901 OK / 5 skipped / 1 expected failure — must grow.
  Every fix ships with the test that would have caught it, and at least one
  test must drive the REAL caller path (fake deck + fake port through
  make_on_key/on_key), not hand-built rows — that is the class the existing
  smoke tests missed.

## Deliverable

Findings severity-first (location, issue, concrete live failure scenario,
evidence, fix applied or proposed), the #5 root cause with the exact
mechanism named confirmed or the candidates ranked with the discriminating
evidence for each, commits (pathspec, tested, pushed), and the operator
handoff: what he should press to verify, and what remains bridge-side work
awaiting his go. Label every load-bearing claim confirmed / assumed /
unknown. Success = #5 explained or bounded with evidence, every hunt-list
item either cleared or a finding, no silent-input-loss path left without
either a fix or a loud log line, and the caller-contract test class exists.
