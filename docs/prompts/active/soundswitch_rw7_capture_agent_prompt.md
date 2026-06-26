---
doc_status: active-review-prompt
truth_level: code-grounded
last_verified_commit: ceb6bb0
last_verified_date: 2026-06-26
validation_scope: one-shot operator-conducted capture agent prompt for RW-7 / T7d live autoloop-phase evidence; OBSERVER-ONLY except agent-owned passive tcpdump/hash/log collection; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no pack enable, no bridge restart, no fixture/Enttec/DMX/MIDI connection, no project mutation
---

# One-shot capture agent — RW-7 / T7d live autoloop-phase evidence

You are an **observer-and-conductor** agent in `/Users/bbui/rb_ss_bridge_v2`. Your job is
to run the remaining RW-7 (T7d) live autoloop-phase capture scenarios **by directing the
operator** and recording integrity-classified evidence. You **cannot perform any physical
action yourself** — every track load, transport, master switch, drop, BPM change, bridge
restart, and SoundSwitch action is the **operator's** to do. You **do** own passive
capture mechanics: start/stop `tcpdump`, hash files, copy logs, and validate artifacts
yourself. You **ping the operator and actively wait.** You never reinterpret missing
evidence.

## Authority (read first)
1. `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md` — the governing plan
   (scenarios, identity/BPM coverage, holdout method, safety preflight, classification).
2. `tools/t7d_capture_conductor.py` — the recorder/helper you drive. Use it; do not write a
   second capture harness during this session. Read its `SCENARIOS`, `classify_gate`,
   `cmd_run_scenario`, and the `main`/argparse block. Know its limits and compensate for them:
   the conductor's `ACCEPTED` is only a weak integrity result, not final RW-7 evidence. It copies
   only `bridge.log`, hard-codes `project_hash_matched=True` in `run-scenario`, does not prove
   nonempty hash files, does not copy AppLogs, and its scenario markers are not semantic enough
   for every scenario. **You** run the missing read-only evidence steps and final acceptance
   checks yourself. If your stricter checks disagree with the conductor, your stricter verdict wins.

## HARD SAFETY BOUNDARIES — never cross
- **Observer only for live behavior.** Never connect to or open Enttec/serial/MIDI/DMX, never enable the
  bridge-native pack backend, never mutate the SoundSwitch project bytes, never restart the
  bridge. Agent-owned passive `tcpdump` on loopback, file hashing, and log copying are allowed;
  they are evidence collection, not lighting output.
- **Pack output MUST stay disabled** for every capture (`soundswitch_pack` null/disabled in
  status). A capture taken with pack output enabled is a **FAIL** — the conductor enforces
  this; you must not work around it.
- Preserve **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED** and default-off posture.

## THE OPERATOR-PING + ACTIVE-WAIT LAW (the core of this task)
Every step that needs a human is an **active-wait gate, not a stop.** For each gate you:
1. **Ping the operator** — state in chat, in plain language, the *exact one physical action*
   needed. One action at a time. No "let me know how you'd like to proceed." Do not say vague
   labels like "drop-hold action now", "perform the scenario", or "do the buildup". Resolve the
   live deck/track/cue from bridge logs/status first, then say the actual action, for example:
   "Press Play on Deck 1 for `Route 94- My Love...`; leave Deck 1 as master; do not touch
   SoundSwitch or Stream Deck; keep it playing until I say stop."
2. **Actively wait** — poll the real state (status file, `pgrep`, growing pcap/session, bridge
   log markers, pcap frame count, and session phase rows) on an interval until the expected
   evidence appears or a hard timeout hits. Do **not** advance on assumption.
3. **On timeout → fail closed** — record `INCOMPLETE` (the conductor does this), tell the
   operator plainly what was missing, and offer to re-run. Never rubber-stamp.

**Never stop the chat at an operator gate.** After you ping, keep the tool/process running and
keep polling. A final response while capture is pending is a failure unless the user explicitly
interrupts or asks you to stop.

**Spoken pings are short.** Use `say` only for the short human action ("Press Play on Deck 1 now",
"Switch master to Deck 2 now", "Leave it playing"). Do not speak terminal commands, paths,
countdowns, or long scenario descriptions.

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
- **Bridge/process safety during a run.** The conductor proves the core-count/pack gate at
  baseline and again when `run-scenario` finalizes; it does not run `prepare` inside the
  active window. If the saved `run-scenario` summary records `bridge_process_count != 1`
  or `pack_output_disabled=false`, that run is `FAIL`, not `INCOMPLETE`. If a bridge or
  SoundSwitch restart only appears as timeout, recorder drops, a missing/dirty phase footer,
  missing markers, too few Universe-0 frames, or insufficient pcap-overlap beat span, keep
  the `INCOMPLETE` verdict. Either way, never accept the run; re-confirm one bridge + pack
  disabled and re-run the scenario from scratch.
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
- the chosen track/deck is at a cue or position that can actually reach the scenario's semantic
  markers inside the active recording window. For `drop-hold` and `buildup`, do not start from an
  arbitrary track beginning unless you have verified the buildup/drop markers occur soon enough.
  If you cannot identify a usable cue/position from logs, metadata, or operator confirmation,
  do not start the run.
**Before the first scenario, confirm the running bridge has the B1 schema-2 phase-trace
wiring.** Otherwise the session emits no `autoloop_phase` rows and every run burns its full
`--window-timeout-s` before failing INCOMPLETE — after the operator already performed the
action. Verify a recent `session.jsonl` under `tools/ssfmt/captures/` contains `autoloop_phase`
rows, or have the operator confirm the bridge is the current build; if it predates B1, stop the
capture attempt and request separate operator approval for the exact restart command. You do not
restart it. After the operator performs the approved restart, re-run `prepare` and the schema-2
pre-check from scratch.
Run `python3 tools/t7d_capture_conductor.py prepare` to machine-check the bridge-count +
pack-disabled gate; if it returns nonzero, **do not proceed** — ping and wait until green.

## Scenarios to capture (the work)
`arm` and `refire` already have **2 ACCEPTED** each. Capture the remaining four. Do **not**
drive the operator with the conductor's generic `operator_action` text verbatim; use it only as
the scenario definition. Before each run, resolve the actual deck, track, cue/position, master
state, BPM/pitch, and expected marker sequence from live bridge logs/status and say the concrete
one-step action.
- **`master-switch`** — two unscripted beatgrid-valid decks at similar BPM; switch master >1 s
  before the next 32-beat boundary; transports otherwise unchanged.
- **`drop-hold`** — reviewed `drop_mode` personality with nonzero `post_drop_hold_beats`;
  capture buildup entry, drop crossing, and the entire drop-hold window, identity unchanged.
- **`buildup`** — track with a curated Smart Drop + UP phrase; start >`buildup_lookahead_beats`
  before the drop.
- **`correction`** — master phrase-arm enabled; switch master 0.25–0.5 beat after a 32-beat
  boundary until the real logs show the correction sequence. Do **not** inject delay or edit
  code to force it.

Minimum concrete operator cue format:

```text
Operator action: <verb> <deck/control> for <track name or deck number>.
Keep <deck/master/transport> unchanged.
Do not touch <specific forbidden controls for this scenario>.
Keep it running until I say the window is complete.
```

Examples:
- `master-switch`: "Switch master to Deck 2 now. Leave both tracks playing. Do not load tracks,
  stop transport, press Stream Deck buttons, or touch SoundSwitch."
- `drop-hold` / `buildup`: "Press Play on Deck 1 for `<track>` from the current cue. Leave Deck
  1 as master. Do not touch anything else. Let it play through buildup, drop crossing, and the
  post-drop/hold section until I say stop."
- `correction`: "Switch master to Deck 2 immediately after this boundary. Leave both decks
  playing. Do not retry manually unless I give a new cue."

**Coverage targets (per plan §A4/§B6):** **two ACCEPTED repetitions per scenario**; across the
matrix, at least **three verified identities**, the same identity captured at **two materially
different BPM/pitch** values, and at least **one full holdout identity** reserved. The conductor
records **none** of this — its manifest/summary store only scenario, markers, and verdict, and
`summarize-corpus` tallies only by scenario/verdict. So it is on you: **before the first run,
designate the holdout identity**, and **for every accepted run record — in chat and in a sidecar
note — the run dir, the exact identity the operator used, and the BPM/pitch.** Maintain a running
coverage table; you cannot claim "3 identities / 2 BPM / 1 holdout" from ACCEPTED counts alone.
Tell the operator what is still missing after each accepted run.
Before the first new repetition, inventory the existing accepted `arm` and `refire` run dirs.
Add their run dirs, identities, BPM/pitch, AppLog proof, and holdout/train status to the same
coverage table. If any of that cannot be proven, mark it `UNKNOWN` and report it as remaining
B6 coverage; do not claim identity/BPM/holdout coverage from the four remaining scenarios alone.

## Run mechanics (drive the conductor, don't reimplement it)
**You (the agent) run passive mechanics yourself** — project hashes, `tcpdump`, AppLog copy,
artifact hashes, and final validation. They are read-only/passive evidence collection, not physical
lighting actions. If macOS needs admin for `tcpdump`, open the password prompt and let the operator
type the password; do not ask the operator to run terminal commands. Operator pings stay limited to
physical live actions (bridge up, SoundSwitch/fixtures confirmation, deck play/stop/master switch).

Two harness facts to respect: shell env vars do not persist between separate command calls, and
this machine may not support `C.UTF-8`. Prefer a small Python `hashlib.sha256` helper for project
and artifact hashes. If you use shell hashing anyway, force `LC_ALL=C LANG=C` and then prove the
hash files are nonempty. Empty hash files are `INCOMPLETE`, even if before/after compare equal.

Pick **one run-stamp per repetition** and reuse the exact same `<run-stamp>` and `<scenario>` for
every step. For each repetition:
1. Preflight (above) → ping → WAIT until green.
2. **Fix the run-stamp + before-hash.** Choose one stamp (e.g. `20260625_143012`), build the
   absolute dir (the conductor's own `mkdir` is `exist_ok`, so pre-creating is harmless), and hash
   the project into it. Then verify `project.before.sha256` exists and has nonzero size before
   any capture starts:

   ```bash
   cd /Users/bbui/rb_ss_bridge_v2
   RUN_DIR="/Users/bbui/rb_ss_bridge_v2/tools/ssfmt/captures/t7d/t7d_<scenario>_<run-stamp>"
   mkdir -p "$RUN_DIR/logs"
   python3 - "$RUN_DIR" project.before.sha256 <<'PY'
   import hashlib
   import sys
   from pathlib import Path
   project = Path.home() / "Music/SoundSwitch/default.ssproj"
   out = Path(sys.argv[1]) / sys.argv[2]
   rows = []
   for path in sorted(p for p in project.iterdir() if p.is_file()):
       h = hashlib.sha256()
       with path.open("rb") as fh:
           for chunk in iter(lambda: fh.read(1024 * 1024), b""):
               h.update(chunk)
       rows.append(f"{h.hexdigest()}  {path}\n")
   out.write_text("".join(rows), encoding="utf-8")
   if not rows:
       raise SystemExit("no project files hashed")
   PY
   test -s "$RUN_DIR/project.before.sha256"
   ```

3. **Start passive tcpdump yourself before the conductor recorder starts.** Open a Terminal
   command if admin is needed; the only human action is typing the password if prompted. Poll until
   `artnet.pcap` exists and grows. Do not speak the command.

   ```bash
   sudo /usr/sbin/tcpdump -i lo0 -s0 -U -w "$RUN_DIR/artnet.pcap" udp port 6454
   ```

4. Start the conductor:

   ```bash
   python3 tools/t7d_capture_conductor.py run-scenario <scenario> \
     --run-stamp <run-stamp> \
     --run-stamp-epoch "$(date +%s)"
   ```

   `--run-stamp` is required and must be the same `<run-stamp>` as `RUN_DIR`; `<scenario>` must
   match too. For `correction`, also pass a larger `--window-timeout-s` such as `900`.

   **Do not let the conductor decide when to stop tcpdump for final evidence.** Its markers are
   known to be too weak for some scenarios. Let it start the recorder and active-wait, but keep
   your own semantic stop gate below.

5. **Scenario semantic stop gate (your gate, not the conductor's).** Keep tcpdump running and do
   not stop the session until the scenario-specific required markers appear **after**
   `record-session-start` and before `record-session-stop`. If the conductor emits "window
   complete" before the semantic gate is satisfied, keep the run going if possible; otherwise
   mark it `INCOMPLETE` and do not count it.

   Required semantic markers:

   | scenario | required markers inside active session/pcap window |
   | --- | --- |
   | `master-switch` | `trigger=master_changed` for the new master deck, then `arm-autoloop`/`arm-immediate` for that deck, then a later `[LX] fired` for that deck |
   | `drop-hold` | `buildup_to_drop_window`, then `drop_crossing`, then at least one post-drop/hold indicator such as `role=post_drop`, `post_drop`, or a later drop/hold beat while the same deck/identity remains active |
   | `buildup` | `[LX] fired role=buildup` with `reason=buildup_to_drop_window`, and enough subsequent playing phase rows before the drop to prove the buildup window was captured |
   | `correction` | `arm-grace-late`, `arm-correction-pending`, `arm-correction-clear`, and the later correction lock/refire |

   Always verify marker timestamps against the current run's `record-session-start` and
   `record-session-stop` lines. Whole-log matches are not evidence.

6. **Stop capture only after your semantic gate passes or the run has timed out.** Stop tcpdump
   yourself, stop/settle the recorder, and let the conductor finish. If a conductor process already
   stopped the recorder too early, mark the run `INCOMPLETE` even if semantic markers appear later
   in `/tmp/bridge.log`.
7. **After-hash + AppLog copy (you run this, immediately after the window stops).** Re-declare the
   same absolute `RUN_DIR`:

   ```bash
   cd /Users/bbui/rb_ss_bridge_v2
   RUN_DIR="/Users/bbui/rb_ss_bridge_v2/tools/ssfmt/captures/t7d/t7d_<scenario>_<run-stamp>"
   python3 - "$RUN_DIR" project.after.sha256 <<'PY'
   import hashlib
   import sys
   from pathlib import Path
   project = Path.home() / "Music/SoundSwitch/default.ssproj"
   out = Path(sys.argv[1]) / sys.argv[2]
   rows = []
   for path in sorted(p for p in project.iterdir() if p.is_file()):
       h = hashlib.sha256()
       with path.open("rb") as fh:
           for chunk in iter(lambda: fh.read(1024 * 1024), b""):
               h.update(chunk)
       rows.append(f"{h.hexdigest()}  {path}\n")
   out.write_text("".join(rows), encoding="utf-8")
   if not rows:
       raise SystemExit("no project files hashed")
   PY
   test -s "$RUN_DIR/project.after.sha256"
   cp "$HOME/Library/Application Support/Onesixone/Soundswitch/Logs"/AppLog*.txt \
     "$RUN_DIR/logs/"
   cp "$RUN_DIR/summary.json" "$RUN_DIR/summary.run_scenario.json"
   ```

   Without these, the corpus has no valid project immutability proof or AppLog identity join.
8. `python3 tools/t7d_capture_conductor.py validate-scenario "/Users/bbui/rb_ss_bridge_v2/tools/ssfmt/captures/t7d/t7d_<scenario>_<run-stamp>"`
   for the conductor's post-hash verdict. Then hash final artifacts. Final acceptance requires all
   of the following after artifact hashing:
   - `summary.run_scenario.json` says `ACCEPTED`;
   - post-validation `summary.json` says `ACCEPTED`;
   - `project.before.sha256`, `project.after.sha256`, and `artifacts.sha256` exist and are
     nonempty;
   - `project.before.sha256` and `project.after.sha256` match exactly;
   - copied AppLogs exist;
   - your scenario semantic gate passed inside the active recording window.

   Then hash the final capture contents:

   ```bash
   cd /Users/bbui/rb_ss_bridge_v2
   RUN_DIR="/Users/bbui/rb_ss_bridge_v2/tools/ssfmt/captures/t7d/t7d_<scenario>_<run-stamp>"
   python3 - "$RUN_DIR" <<'PY'
   import hashlib
   import sys
   from pathlib import Path
   root = Path(sys.argv[1])
   out = root / "artifacts.sha256"
   rows = []
   for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "artifacts.sha256"):
       h = hashlib.sha256()
       with path.open("rb") as fh:
           for chunk in iter(lambda: fh.read(1024 * 1024), b""):
               h.update(chunk)
       rows.append(f"{h.hexdigest()}  {path}\n")
   out.write_text("".join(rows), encoding="utf-8")
   if not rows:
       raise SystemExit("no artifact files hashed")
   PY
   test -s "$RUN_DIR/artifacts.sha256"
   ```

   Run `python3 tools/t7d_capture_conductor.py summarize-corpus` after each accepted run to report
   remaining coverage. `summarize-corpus` takes **no path argument** — its default
   root is the t7d capture dir; `--capture-root` if ever needed is a global flag placed *before*
   the subcommand.

## Fail-closed discipline (do not soften)
- A run is `FAIL` if the saved `run-scenario` summary shows pack enabled or not exactly one
  bridge, or if the post-hash validation shows project bytes changed.
- `INCOMPLETE` on timeout, recorder drops, missing markers, too few Universe-0 frames,
  missing/dirty phase footer, too few playing `autoloop_phase` rows, insufficient pcap-overlap
  beat span, or SoundSwitch/bridge artifact loss during capture. **Never** reinterpret
  missing/contaminated evidence as accepted. Never edit code or inject timing to force a marker.
- `INCOMPLETE` if any required hash file is missing or 0 bytes, even if before/after compare
  equal. Empty matching hash files prove nothing.
- `INCOMPLETE` if the scenario's semantic marker sequence is absent, stale, appears only before
  `record-session-start`, or appears only after `record-session-stop`. This overrides a conductor
  `ACCEPTED`.
- `INCOMPLETE` if the run used the wrong live backend for the evidence claim, including a bridge
  MIDI backend that was `NoneBackend` during SoundSwitch/IAC evidence collection.
- `summarize-corpus` is a convenience counter only. It is not proof. Before claiming a scenario
  has accepted reps, independently inspect each counted run for nonempty hashes, matching hashes,
  AppLogs, bridge-count/pack-disabled gates, semantic marker window, phase footer, pcap frames,
  and identity/BPM sidecar rows.
- When a run is invalidated after the conductor wrote `ACCEPTED`, edit that run's `summary.json`
  to `INCOMPLETE` with `observations.rw7_evidence_valid=false` and an `invalidation_reason`, while
  preserving `summary.run_scenario.json` as the raw conductor result for audit.
- Do **not** attempt the derivation/holdout fit (plan §B5) — that is a separate later step.
  Your deliverable is the **accepted capture corpus**, not the phase contract.

## Report back (concise, plain language)
After the session: per-scenario `ACCEPTED`/`INCOMPLETE`/`FAIL` counts with run dirs; the
`summarize-corpus` output; the per-run identity + BPM/pitch table and which identity is the
reserved holdout; confirmation that each accepted run has matching
`project.before`/`project.after` hashes, copied AppLogs, `artifacts.sha256`, and both saved
`summary.run_scenario.json` + post-validation `summary.json` verdicts; exactly which coverage
targets remain (which scenarios still need a 2nd accepted rep, which existing or new run
identities/BPM/holdout are still missing or `UNKNOWN`); and any environment blocker
(bridge/SoundSwitch readiness) that interrupted a run.
Preserve **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.
