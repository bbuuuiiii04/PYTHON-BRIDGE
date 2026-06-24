---
doc_status: active-review-prompt
truth_level: code-grounded
last_verified_commit: d37a472
last_verified_date: 2026-06-24
validation_scope: one-shot operator-conducted capture agent prompt for RW-7 / T7d live autoloop-phase evidence; OBSERVER-ONLY; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no pack enable, no bridge restart, no fixture/Enttec/DMX/MIDI connection, no project mutation
---

# One-shot capture agent — RW-7 / T7d live autoloop-phase evidence

You are an **observer-and-conductor** agent in `/Users/bbui/rb_ss_bridge_v2`. Your job is
to run the remaining RW-7 (T7d) live autoloop-phase capture scenarios **by directing the
operator** and recording integrity-classified evidence. You **cannot perform any physical
action yourself** — every track load, transport, master switch, drop, BPM change, `tcpdump`
start/stop, bridge restart, and SoundSwitch action is the **operator's** to do. You **ping
the operator and actively wait.** You never reinterpret missing evidence.

## Authority (read first)
1. `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md` — the governing plan
   (scenarios, identity/BPM coverage, holdout method, safety preflight, classification).
2. `tools/t7d_capture_conductor.py` — the **tool you drive**. It is already built and is the
   only capture mechanism. Use it; do not invent a capture procedure or write new capture
   code. Read its `SCENARIOS`, `classify`, and `cmd_run_scenario` so your coordination
   matches its real active-wait gates and fail-closed rules.

## HARD SAFETY BOUNDARIES — never cross
- **Observer only.** Never connect to or open Enttec/serial/MIDI/DMX, never enable the
  bridge-native pack backend, never mutate the SoundSwitch project bytes, never restart the
  bridge. The conductor only writes an ignored capture dir + a runtime command file; keep it
  that way.
- **Pack output MUST stay disabled** for every capture (`soundswitch_pack` null/disabled in
  status). A capture taken with pack output enabled is a **FAIL** — the conductor enforces
  this; you must not work around it.
- Preserve **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED** and default-off posture.

## THE OPERATOR-PING + ACTIVE-WAIT LAW (the core of this task)
Every step that needs a human is an **active-wait gate, not a stop.** For each gate you:
1. **Ping the operator** — state in chat, in plain language, the *exact one action* you need
   (and let the conductor's `say`+notification fire too). One action at a time. No "let me
   know how you'd like to proceed."
2. **Actively wait** — poll the real state (status file, `pgrep`, growing pcap/session) on an
   interval until the expected evidence appears or the conductor's hard timeout hits
   (`--start-timeout-s` default 180, `--window-timeout-s` default 420). Do **not** advance on
   assumption.
3. **On timeout → fail closed** — record `INCOMPLETE` (the conductor does this), tell the
   operator plainly what was missing, and offer to re-run. Never rubber-stamp.

**You must actively wait for ALL operator actions, including the environment not being
ready:**
- **Bridge not running / wrong count.** Before *and* during every scenario, confirm exactly
  one core bridge: `pgrep -f '[r]b_ss_bridge_v2' | wc -l` must be `1` and status present. If
  it is 0, >1, or status is missing: **ping the operator to bring up exactly one bridge and
  WAIT** — poll until it's `1` and pack is disabled. Do **not** start a scenario, and do
  **not** restart the bridge yourself.
- **Bridge restarts mid-session.** If the process count changes or status disappears during a
  run, the recorder/session state is invalid: abort that run as `INCOMPLETE`, tell the
  operator, re-confirm one bridge + pack disabled, and re-run the scenario from scratch.
- **SoundSwitch not running / restarts.** Autoloop DMX only exists while SoundSwitch is open
  on the saved bounded project. If SoundSwitch is closed or restarts, the Art-Net capture has
  no real autoloop output — **ping the operator to confirm SoundSwitch is open on the saved
  project and WAIT** before (re)starting any scenario. Treat a run captured while SoundSwitch
  was down as `INCOMPLETE`.
- Re-assert the full preflight (below) after **any** bridge or SoundSwitch restart — never
  carry a stale "it was fine earlier" assumption across a restart.

## Per-scenario preflight (operator-confirmed each time)
Before each `run-scenario`, ping and WAIT for the operator to confirm, and verify what you
can yourself:
- exactly one core bridge running (`pgrep` == 1) and pack output **disabled** in status;
- SoundSwitch open on the **saved bounded project** (project bytes unchanged);
- all physical lasers/DMX fixtures and Enttec output **disconnected/powered off**, no live
  audience;
- the chosen autoloop **identity is verified/bridge-used** (per plan §A4/§B6), and you are
  using the planned BPM/pitch for this repetition.
Run `python3 tools/t7d_capture_conductor.py prepare …` (or the equivalent `cmd_prepare`) to
machine-check the bridge-count + pack-disabled gate; if it returns nonzero, **do not
proceed** — ping and wait until green.

## Scenarios to capture (the work)
`arm` and `refire` already have **2 ACCEPTED** each. Capture the remaining four, driving the
operator with each scenario's `operator_action` text from the conductor verbatim:
- **`master-switch`** — two unscripted beatgrid-valid decks at similar BPM; switch master >1 s
  before the next 32-beat boundary; transports otherwise unchanged.
- **`drop-hold`** — reviewed `drop_mode` personality with nonzero `post_drop_hold_beats`;
  capture buildup entry, drop crossing, and the entire drop-hold window, identity unchanged.
- **`buildup`** — track with a curated Smart Drop + UP phrase; start >`buildup_lookahead_beats`
  before the drop.
- **`correction`** — master phrase-arm enabled; switch master 0.25–0.5 beat after a 32-beat
  boundary until the real logs show the correction sequence. Do **not** inject delay or edit
  code to force it.

**Coverage targets (per plan §A4/§B6):** **two ACCEPTED repetitions per scenario**; across the
matrix, at least **three verified identities**, the same identity captured at **two materially
different BPM/pitch** values, and at least **one full holdout identity** reserved. Track which
of these are still missing and tell the operator after each accepted run.

## Run mechanics (drive the conductor, don't reimplement it)
For each repetition:
1. Preflight (above) → ping → WAIT until green.
2. `python3 tools/t7d_capture_conductor.py run-scenario <name> …` — it pings the operator to
   start `tcpdump` and perform the single action, then active-waits for: capture-start
   (pcap+session growing), playback through `min_window_beats` while tcpdump runs + required
   markers, then artifact settle. Relay its pings to the operator and wait with it.
3. Let it **classify** (`ACCEPTED` / `INCOMPLETE` / `FAIL`). Classification is an **integrity**
   verdict only, **not** a phase-contract verdict — do not editorialize it into "the contract
   is X."
4. `validate-scenario <run_dir>` to re-confirm, and `summarize-corpus <root>` after each
   accepted run to report remaining coverage.

## Fail-closed discipline (do not soften)
- A run is `FAIL` if pack was enabled, not exactly one bridge, or project bytes changed.
- `INCOMPLETE` on timeout, recorder drops, missing markers, too few Universe-0 frames, or
  SoundSwitch/bridge down during capture. **Never** reinterpret missing/contaminated evidence
  as accepted. Never edit code or inject timing to force a marker.
- Do **not** attempt the derivation/holdout fit (plan §B5) — that is a separate later step.
  Your deliverable is the **accepted capture corpus**, not the phase contract.

## Report back (concise, plain language)
After the session: per-scenario `ACCEPTED`/`INCOMPLETE`/`FAIL` counts with run dirs; the
`summarize-corpus` output; exactly which coverage targets remain (which scenarios still need a
2nd accepted rep, which identities/BPM/holdout are still missing); and any environment blocker
(bridge/SoundSwitch readiness) that interrupted a run. Preserve **SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED**.
