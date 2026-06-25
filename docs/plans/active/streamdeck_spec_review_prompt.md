# Strict Review Prompt — Stream Deck spec (Opus 4.8, subagents authorized)

You are a senior adversarial reviewer. Your job is to **try to break** this spec before Codex builds
it, not to bless it. This drives a **live lighting rig**; a wrong call here causes a bad show.

**Target:** `/Users/bbui/rb_ss_bridge_v2/docs/plans/active/streamdeck_midi_bridge_integration_spec.md`
**Repo:** `/Users/bbui/rb_ss_bridge_v2` (read the code; do not modify anything).

## Authorization
You are **authorized to dispatch subagents** and should, to parallelize and deepen the review.
Suggested split (adapt as useful): (1) verify every `[confirmed]` file:line claim against current
code; (2) Phase 1 — script robustness + watcher lifecycle; (3) Phase 2 — the layered compositor
live-safety and model correctness. Read-only; verify load-bearing claims yourself before trusting a
subagent's conclusion.

## Rules of engagement
- **Code wins over the spec.** Open every file:line the spec cites and confirm it says what's claimed.
  List any claim that is stale, wrong, or unverifiable. Per repo `AGENTS.md`: source-of-truth order is
  code > tests > config > docs.
- Label findings **BLOCKER / MAJOR / MINOR**, each with exact `file:line`, why it breaks, and a
  concrete fix. No vague "consider".
- Force a specific failure scenario for each risk. "Looks fine" is not review.

## Phase 1 — must attack
- SIGTERM handling: does the watcher's `kill`/`pkill` (default SIGTERM) actually run the deck
  reset + device release? Verify only SIGINT is handled today.
- `fcntl.flock` single-instance guard: race with the watcher relaunching every loop; double-open;
  stale lock after crash.
- Supervisor loop: device absent / held by Elgato app / mid-run unplug — no crash, no CPU spin,
  `deck.connected()` actually detects disconnect; transport errors caught at the right import path.
- Watcher wiring: does `stop_streamdeck` fire on **every** teardown path — auto `stop_bridge`,
  `cleanup`/EXIT/INT/TERM traps, manual-terminal-closed branch — in `/Users/bbui/ss_bridge_watcher.sh`?
  Does `start_streamdeck` only run while the bridge is up, in both manual and auto modes?
- Channel-3 safety assertion: does the selftest actually guard `CHANNEL ∉ {0,1}` (lasers' MIDI ch 1-2)?

## Phase 2 — the layered compositor (the live-critical core) — attack hardest
Locked model to enforce: base = live autoloop/scripted; static looks = **sparse** per-channel patches
stacked by **execution recency** (toggle = persistent, press = transient/pops on `note_off`); absent
channel transparent, explicit 0 overrides; **topmost wins**; **nothing auto-untoggles**;
emergency/blackout > whole stack; hold until `note_off`/input-disconnect (the 2 s
`controller_hold_timeout_ms` cutoff removed); clear stack on input disconnect.
- Verify the gap is real: `soundswitch_laser_player.py:143-163,186` (opaque fill, full-frame replace,
  single `_active_static_slot`) and `soundswitch_midi_input.py` `_held_static_slot` are single-slot.
- Verify the data supports transparency: `generic_attributes` is sparse (`soundswitch_pack_loader.py:586`).
- **Purity / push-loop safety:** the spec requires the render to be a pure function read by the 200 Hz
  loop with stack mutation on the worker thread (AGENTS §6: no blocking I/O in the push loop). Does the
  proposed design actually keep it pure? Find any place it wouldn't.
- **Precedence:** confirm emergency/blackout still blacks the whole stack; confirm static layers sit
  over autoloop without clobbering it when transparent.
- **Edge cases — enumerate failures:** simultaneous press+toggle ordering; re-press moves to top;
  two toggles overlapping one channel; press-over-toggle revert target on release; removing a
  mid-stack layer; disconnect mid-hold; blackout while layers held; **pack reload while layers held**
  (`on_pack_reload` exists — does the spec address it?); dropped/!overflowed notes (`mail_drop_count`)
  desyncing the stack; controller LED vs bridge stack divergence (spec claims "correct by
  construction" — stress it: mailbox drops, bridge clears stack on disconnect but controller stays lit).
- **"No Stream Deck in the bridge" invariant:** confirm the design keeps all device-aware logic out of
  `rb_ss_bridge_v2/*.py` (generic compositor + MIDI input only; device logic in controller + sidecar).

## Cross-cutting
- Run the codex-spec 9-point pre-handoff checklist (claims labeled; verified vs current code;
  pending-state guards; mode-transition cleanup; third-party API completeness; cross-checked vs
  existing code; pure-function test seam; live-safety explicit; adversarial self-review).
- **Implementability:** can Codex build **Task 5** with no guessing? Are symbols/locations precise?
  Name anything underspecified.
- Test seams: are the pure-function compositor + LED-mapping tests sufficient to catch regressions?

## Output
1. **Verdict:** `APPROVED` / `REVISE-AND-APPROVE` / `REJECT`.
2. **Failed-verification list:** every spec claim that did not hold against code (with file:line).
3. **Findings:** BLOCKER → MAJOR → MINOR, each `file:line` + failure scenario + concrete fix.
4. **Top 3 things most likely to cause a bad show**, ranked.
Be terse and specific. Evidence over assertion.
