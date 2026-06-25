---
doc_status: active-review-prompt
truth_level: code-grounded
last_verified_commit: d37a472
last_verified_date: 2026-06-25
validation_scope: one-shot operator-conducted capture agent prompt for RW-7 / T7d live autoloop-phase evidence; OBSERVER-ONLY; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no pack enable, no bridge restart, no fixture/Enttec/DMX/MIDI connection, no project mutation
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
   code. Read its `SCENARIOS`, `classify_gate`, `cmd_run_scenario`, and the `main`/argparse
   block (for the exact invocation flags) so your coordination matches its real active-wait
   gates and fail-closed rules. Know its limits: the conductor copies only `bridge.log` and
   hard-codes `project_hash_matched=True` in `run-scenario` — it does **not** hash the
   SoundSwitch project or copy AppLogs. **You** run those yourself (read-only evidence collection
   into the ignored capture dir — not a physical action; see Run mechanics), or `validate-scenario`
   will fail closed and the corpus will be unusable for the later identity join.

## HARD SAFETY BOUNDARIES — never cross
- **Observer only.** Never connect to or open Enttec/serial/MIDI/DMX, never enable the
  bridge-native pack backend, never mutate the SoundSwitch project bytes, never restart the
  bridge. The conductor only writes an ignored capture dir + a runtime command file; keep it
  that way.
- **Pack output MUST stay disabled** for every capture (`soundswitch_pack` null/disabled in
  status). A capture taken with pack output enabled is a **FAIL** — the conductor enforces
  this; you must not work around it.
- Preserve **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED** and default-off posture.

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
- **Bridge not running / wrong count.** The authority for the bridge count is the conductor's
  own core-process check (`prepare` / `core_bridge_process_count`), which excludes the menubar,
  the `| tee` wrapper, the laser pad, and this conductor. A bare `pgrep -f rb_ss_bridge_v2 |
  wc -l` over-counts in this repo — use it only as a rough hint, never as the gate. Before
  *and* during every scenario, require `prepare` to report exactly one core bridge with status
  present and pack disabled. If it is 0, >1, or status is missing: **ping the operator to bring
  up exactly one bridge and WAIT** — re-run `prepare` until it is green. Do **not** start a
  scenario, and do **not** restart the bridge yourself.
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
- exactly one core bridge running (confirmed via `prepare` / `core_bridge_process_count`, not a
  bare `pgrep`) and pack output **disabled** in status;
- SoundSwitch open on the **saved bounded project** (project bytes unchanged);
- all physical lasers/DMX fixtures and Enttec output **disconnected/powered off**, no live
  audience;
- the chosen autoloop **identity is verified/bridge-used** (per plan §A4/§B6), and you are
  using the planned BPM/pitch for this repetition.
**Before the first scenario, confirm the running bridge has the B1 schema-2 phase-trace
wiring.** Otherwise the session emits no `autoloop_phase` rows and every run burns its full
`--window-timeout-s` before failing INCOMPLETE — after the operator already performed the
action. Verify a recent `session.jsonl` under `tools/ssfmt/captures/` contains `autoloop_phase`
rows, or have the operator confirm the bridge is the current build; if it predates B1, ping the
operator to restart into the current build and WAIT (you do not restart it).
Run `python3 tools/t7d_capture_conductor.py prepare` to machine-check the bridge-count +
pack-disabled gate; if it returns nonzero, **do not proceed** — ping and wait until green.

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
different BPM/pitch** values, and at least **one full holdout identity** reserved. The conductor
records **none** of this — its manifest/summary store only scenario, markers, and verdict, and
`summarize-corpus` tallies only by scenario/verdict. So it is on you: **before the first run,
designate the holdout identity**, and **for every accepted run record — in chat and in a sidecar
note — the run dir, the exact identity the operator used, and the BPM/pitch.** Maintain a running
coverage table; you cannot claim "3 identities / 2 BPM / 1 holdout" from ACCEPTED counts alone.
Tell the operator what is still missing after each accepted run.

## Run mechanics (drive the conductor, don't reimplement it)
**You (the agent) run the hash + AppLog steps yourself** — they are read-only reads of the project
and logs written into the ignored capture dir, not physical actions, so they are not the
operator's to do, and routing them through the operator's terminal is fragile. Operator pings stay
limited to physical actions (bridge up, SoundSwitch/fixtures confirm, tcpdump start/stop, the
scenario action). Two harness facts to respect: shell **env vars do not persist between separate
command calls** (only the working dir does), so **re-declare `RUN_DIR` at the top of every block**
using one **absolute** literal; and the conductor names the run dir `t7d_<scenario>_<run-stamp>`,
so pick **one run-stamp per repetition** and reuse the exact same `<run-stamp>` and `<scenario>`
literals in steps 2–5. For each repetition:
1. Preflight (above) → ping → WAIT until green.
2. **Fix the run-stamp + before-hash (you run this; the conductor does NOT hash).** Choose one
   stamp (e.g. `20260625_143012`), build the absolute dir (the conductor's own `mkdir` is
   `exist_ok`, so pre-creating is harmless), and hash the project into it:

   ```bash
   cd /Users/bbui/rb_ss_bridge_v2
   RUN_DIR="/Users/bbui/rb_ss_bridge_v2/tools/ssfmt/captures/t7d/t7d_<scenario>_<run-stamp>"
   mkdir -p "$RUN_DIR/logs"
   find "$HOME/Music/SoundSwitch/default.ssproj" -maxdepth 1 -type f \
     -exec shasum -a 256 {} + | LC_ALL=C sort > "$RUN_DIR/project.before.sha256"
   ```
3. `python3 tools/t7d_capture_conductor.py run-scenario <scenario> --run-stamp <run-stamp> --run-stamp-epoch "$(date +%s)"`
   (`--run-stamp` is **required** and must be the **same** `<run-stamp>` as step 2's `RUN_DIR`;
   `<scenario>` must match too) — it pings the operator to start `tcpdump` and perform the single
   action, then active-waits for: capture-start (pcap+session growing), playback through
   `min_window_beats` while tcpdump runs + required markers, artifact settle, and finally
   **classifies** (`ACCEPTED` / `INCOMPLETE` / `FAIL`) via `classify_gate`. Relay its pings to the
   operator and wait with it. For **`correction`**, also pass a larger `--window-timeout-s`
   (e.g. `900`) and warn the operator it usually takes several attempts to induce the
   `arm-grace-late`, `arm-correction-pending`, `arm-correction-clear` sequence. Its verdict is an
   **integrity** verdict only, **not** a phase contract — and its ACCEPTED does **not** yet prove
   project immutability (it hard-codes that check); step 5 does.
4. **After-hash + AppLog copy (you run this, immediately after the window stops).** Re-declare the
   same absolute `RUN_DIR`:

   ```bash
   cd /Users/bbui/rb_ss_bridge_v2
   RUN_DIR="/Users/bbui/rb_ss_bridge_v2/tools/ssfmt/captures/t7d/t7d_<scenario>_<run-stamp>"
   find "$HOME/Music/SoundSwitch/default.ssproj" -maxdepth 1 -type f \
     -exec shasum -a 256 {} + | LC_ALL=C sort > "$RUN_DIR/project.after.sha256"
   cp "$HOME/Library/Application Support/Onesixone/Soundswitch/Logs"/AppLog*.txt \
     "$RUN_DIR/logs/"
   ```

   Without these, `project.before`/`project.after` are missing (so `validate-scenario` fails
   closed) and the corpus has no AppLog to join identity offline.
5. `python3 tools/t7d_capture_conductor.py validate-scenario "/Users/bbui/rb_ss_bridge_v2/tools/ssfmt/captures/t7d/t7d_<scenario>_<run-stamp>"`
   for the real verdict (it verifies `project.before == project.after` and fails closed if either
   is missing), then `python3 tools/t7d_capture_conductor.py summarize-corpus` after each accepted
   run to report remaining coverage. `summarize-corpus` takes **no path argument** — its default
   root is the t7d capture dir; `--capture-root` if ever needed is a global flag placed *before*
   the subcommand.

## Fail-closed discipline (do not soften)
- A run is `FAIL` if pack was enabled, not exactly one bridge, or project bytes changed.
- `INCOMPLETE` on timeout, recorder drops, missing markers, too few Universe-0 frames, or
  SoundSwitch/bridge down during capture. **Never** reinterpret missing/contaminated evidence
  as accepted. Never edit code or inject timing to force a marker.
- Do **not** attempt the derivation/holdout fit (plan §B5) — that is a separate later step.
  Your deliverable is the **accepted capture corpus**, not the phase contract.

## Report back (concise, plain language)
After the session: per-scenario `ACCEPTED`/`INCOMPLETE`/`FAIL` counts with run dirs; the
`summarize-corpus` output; the per-run identity + BPM/pitch table and which identity is the
reserved holdout; confirmation that each accepted run has matching
`project.before`/`project.after` hashes and copied AppLogs; exactly which coverage targets
remain (which scenarios still need a 2nd accepted rep, which identities/BPM/holdout are still
missing); and any environment blocker (bridge/SoundSwitch readiness) that interrupted a run.
Preserve **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.
