---
doc_status: completed-spec
truth_level: code-and-capture-grounded
last_verified_commit: 3f4bcc0
last_verified_date: 2026-06-29
validation_scope: capture-evidence plan only; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# SoundSwitch T7d capture-evidence plan

> **T7d status: planned, BLOCKED on capture evidence.** This plan does not implement
> autoloop pack/DMX output and does not choose a beat-to-animation phase mapping.
> Accepted repo status remains **SOFTWARE/WIRE-VALIDATED ONLY /
> HARDWARE-UNVALIDATED**.

> **SCOPE UPDATE 2026-06-22 — six scenarios, not seven.** `phrase-anchor` was
> dropped from the capture pass: `_phrase_anchor` only fires when
> `RBSS_SMART_REARM_EXPERIMENT=1` **and** `RBSS_PHRASE_ANCHOR=1`
> (`state_manager.py:481`; `PHRASE_ANCHOR_ENV` default `"0"`), and the operator's
> live launch sets REARM but not PHRASE_ANCHOR — the transition never fires in
> production, so its phase origin is not part of the current runtime contract.
> This plan has been normalized to the six active scenarios. This also removes
> the only startup-flag restart from the pass. Re-add phrase-anchor only if the
> live rig turns `RBSS_PHRASE_ANCHOR` on.

> **CORPUS UPDATE 2026-06-23.** The conductor reports `arm` 2 ACCEPTED / 1
> FAIL and `refire` 2 ACCEPTED / 0 FAIL. `master-switch`, `drop-hold`,
> `buildup`, and `correction` remain at zero attempts. ACCEPTED is an integrity
> classification, not a phase-contract verdict. Identity/holdout reconciliation
> and the real-capture oracle are still incomplete.

> **GHIDRAMCP UPDATE 2026-06-29.** Read-only SoundSwitch 2.10.3 arm64 GhidraMCP
> evidence confirms Autoloop beatgrid/beat-window/index machinery and the shared
> playback/cache path. It does not prove the T7d phase contract. GhidraMCP may
> be used before or after a capture to answer a static binary question if it
> materially helps interpretation, but it must not consume the live operator
> window, mutate app/project state, or replace passive Art-Net evidence.

## Part A - Context and blocker (verified; read, do not implement T7d)

### A1. Scope and authority

- [confirmed] The implementation authority is
  `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md`,
  Task 7 (`:534`), Task 8 (`:574`), Task 9 (`:605`), and live-safety
  invariants (`:699`).
- [confirmed] Current task status and dependencies are maintained in
  `docs/plans/active/soundswitch_exporter_remaining_work.md`, RW-7/RW-8.
- [confirmed] This document plans the evidence pass only. It authorizes no bridge
  restart, project mutation, MIDI/serial/Enttec/DMX device open, physical output,
  or T7d runtime edit.
- [assumed] The capture program will use the current bounded SoundSwitch 2.10.3
  RAVE project/profile. A different SoundSwitch version or project profile is a
  separate evidence boundary and cannot inherit this result.

### A2. Current executable facts

| Claim | Current evidence | Status |
| --- | --- | --- |
| The loaded autoloop cycle is 19,200 animation ticks. | `soundswitch_pack_loader.py:26`; `soundswitch_laser_player.py:135-140` wraps `phase_tick % loop.cycle_ticks`. | [confirmed] |
| `render_autoloop_frame` starts each cycle from zero, applies signed negative pre-roll, then records through the wrapped phase. | `soundswitch_laser_player.py:118-140`. | [confirmed] |
| The bridge phrase-arm period is 32 beats. | `config.py:8` (`AUTOLOOP_ARM_PHRASE_BEATS = 32`). | [confirmed] |
| `19_200 / 32 = 600` is the candidate ticks/beat value. | Arithmetic over two independently named constants. The code does not prove that the bridge arm phrase equals one SoundSwitch animation cycle. | [unknown] |
| Initial arm stores a future phrase target in `autoloop_arm_sync_beat`; master correction can replace it; successful lock clears it back to zero. | `autoloop_controller.py:231-239`, `:488-498`, `:603-704`. | [confirmed] |
| Mapping tick zero to `autoloop_arm_sync_beat` for every arm/refire path is correct. | No current capture covers every transition class. `autoloop_arm_sync_beat` is transient, while marker/interval refires use `midi_refire_origin_beat` in `state_manager.py:3703-3755`. | [unknown] |
| Current beat authority prefers the ANLZ beat grid in autoloop mode and otherwise uses the tempo anchor/fallback. | `state_manager.py:3425-3458`; `autoloop_controller.py:419-440`. | [confirmed] |
| The future pack backend has a single accepted-identity read seam. | `PackOutputBackend.last_accepted_identity`, `laser_output_backend.py:162-176`. | [confirmed] |
| The reference MIDI path directly exposes that pack identity today. | It exposes the actual accepted scene/note in `[LX] fired` and retains `last_scene` in executor status (`laser_executor.py:256-266`, `:346-373`); identity must be joined offline through the freshly verified scene-to-identity map and confirmed by AppLog. | [unknown until joined] |
| Current T7c runtime never calls `select_autoloop`; its non-scripted automatic base clears to zero while a held manual static may remain. | `state_manager.py:3209-3272`; `tests/test_state_manager_pack_driver.py:229-238`. | [confirmed] |
| The existing research oracle can prove the T7d scale. | `tools/ssfmt/re/validate_autoloop_capture.py:184` hard-codes `rate = bpm * 10.0`, equivalent to 600 ticks/beat, and `fit_phase` permits a fitted offset. It is useful historical render evidence but is circular for this blocker. | [unknown; not accepted] |
| Existing passive evidence is available. | `tools/ssfmt/captures/bridge_driven_autoloops_20260619.pcap`, copied bridge/AppLogs, and the frozen `snap/` files exist locally. | [confirmed] |
| The schema-2 recorder captures the planned T7d phase authority. | `session_phase_trace.py` defines the primitive phase row; `StateManager` emits it through a bounded nonblocking tracer; accepted captures contain thousands of `autoloop_phase` rows plus clean integrity footers. Executor scene/note fields were null in the inspected accepted rows, so identity must still be joined offline. | [confirmed seam; identity join pending] |
| GhidraMCP can replace the remaining passive capture scenarios. | The 2026-06-29 arm64 pass bounds Autoloop as beatgrid/beat-window/index based, but it does not expose emitted Universe-0 phase/origin/reset/snap behavior for the six bridge transition classes. | [rejected] |

### A3. Questions the evidence must answer

1. [unknown] **Scale:** which `TICKS_PER_BEAT` makes the immutable pack renderer
   reproduce SoundSwitch's captured CH1-CH19 frames? The fit must explicitly test
   and be able to reject 600.
2. [unknown] **Origin/reset contract:** for each of arm, refire, master-switch,
   drop-hold, buildup, and correction, does animation phase reset,
   continue, or snap to a phrase target?
3. [unknown] **Quantization:** whether the integer phase uses floor/truncation,
   rounding, or another boundary convention. The answer must come from captures
   that cross discriminating event ticks; it cannot be selected for convenience.
4. [unknown] **Hold behavior:** whether a `drop_hold` decision leaves an already
   running animation advancing, freezes it, or causes an unlogged re-trigger.

### A4. Decisions made for this plan

- [assumed] Passive Universe-0 Art-Net on loopback is the primary output oracle.
  It records SoundSwitch's actual CH1-CH19 wire frames without opening the bridge's
  direct Enttec/DMX path. AppLogs prove SoundSwitch selection identity; bridge logs
  and a phase trace prove the Rekordbox/bridge input side.
- [assumed] OS2L packets are supporting timing evidence only. They do not replace
  DMX frame parity because SoundSwitch advances its own animation in the existing
  path.
- [assumed] Use at least three verified, bridge-used IAC/bank-4 autoloop identities
  whose immutable timelines have distinct transition spacing. Do not select by
  display name. Resolve the identities from the freshly verified pack
  `selection_map.json`, then rank them by number and uniqueness of event times.
- [assumed] Historical local memory says all 16 bank-4 looks are bridge-used, but
  this is not sufficient authority. The capture preflight must confirm each chosen
  scene against the current verified pack and current executor mapping.
- [assumed] Every scenario needs two accepted repetitions. Across the matrix, the
  same identity must also be captured at two materially different live BPM/pitch
  values so a wall-clock fit cannot masquerade as a beat-domain fit.

## Part B - Evidence tasks (execute in order; stop before T7d implementation)

### B0. Absolute rules

- [confirmed] Captures are verifier oracles only. Production pack input and player
  state may never be seeded from a pcap, AppLog, fitted offset, or captured frame.
- [confirmed] Do not mutate the SoundSwitch project. Hash its saved inputs before
  and after every run; any drift invalidates that run.
- [confirmed] Do not enable the bridge-native pack backend for this evidence pass.
  The current OS2L/IAC-to-SoundSwitch path supplies the reference behavior; direct
  pack/DMX stays disabled.
- [confirmed] Do not connect fixtures, open Enttec/serial output, or restart the
  bridge without a separate explicit operator approval for the exact command.
- [confirmed] One run contains one named scenario/action. Establish a fresh
  baseline before asking for the next action. Never overwrite a prior capture.

### B1. Add the non-circular capture seam before requesting live evidence

Implement and review an evidence-only phase trace used by `session_recorder` /
`session_replayer`. This is preparatory tooling, not T7d.

- [assumed] Add an optional schema-2 `autoloop_phase` row. Capture the following
  primitive fields in the StateManager tick that owns the transition:
  `epoch_ns`, `mono_ns`, `active_deck`, `load_gen`, `playing`, `position_stale`,
  `elapsed_ms`, `bpm`, `abs_beat_pos`, `beatgrid_source`, `lighting_mode`,
  `autoloop_arm_pending`, `autoloop_arm_sync_beat`,
  `autoloop_arm_target_elapsed_ms`, `pending_autoloop_arm_reason`,
  `midi_refire_origin_beat`, `last_autoloop_status_phrase_beat`,
  `phrase_anchor_last_beat`, `drop_cut_armed`, executor decision `role`/`reason`,
  `autoloop_tick_just_fired`, and the executor's actual accepted scene/note plus a
  monotonically increasing accepted-trigger generation. Map scene to pack identity
  offline; do not swap the reference MIDI backend for `PackOutputBackend`.
- [assumed] Emit on any relevant state/identity/edge change and at a fixed maximum
  50 Hz between edges. A bounded `put_nowait` mailbox and capture-writer thread
  perform file I/O; `_push_tick` performs only primitive reads plus a nonblocking
  enqueue. Dropped samples are counted and invalidate a segment spanning the gap.
- [confirmed] Do not call `backend.status()`, executor `status()`, filesystem,
  network, MIDI, serial, subprocess, sleep, or blocking locks from `_push_tick`.
- [assumed] Extend replay parsing so schema 1 remains byte-compatible and schema 2
  exposes phase rows without changing historical event/position/live-BPM replay.
- [assumed] Unit tests must prove timestamp ordering, bounded-drop accounting,
  schema-1 compatibility, schema-2 round trip, and that the tick-side emitter
  performs no file/device I/O.

The capture request is blocked until this seam and its tests are reviewed. A
2 Hz status-file scrape or inferred log timestamp is not precise enough to prove
same-tick reset behavior.

> **B1 implementation status (software-only; wired and captured).**
> The schema-2 seam is built, unit-tested, and wired:
> `session_phase_trace.py` (`build_autoloop_phase_row` pure builder +
> `AutoloopPhaseTracer` bounded `put_nowait` mailbox and writer thread with
> dropped-sample accounting), schema-2 support in `session_recorder.py`
> (`write_phase_row`, `schema=` header) and `session_replayer.py`
> (`SUPPORTED_SCHEMAS = (1, 2)`, `autoloop_phase` rows; schema 1 byte-compatible).
> Tests: `tests/replay/test_phase_trace.py` (ordering, bounded-drop accounting,
> hot-path `emit()` performs no file I/O even with `open` patched to raise,
> schema-2 round trip, schema-1 compatibility). The 200 Hz
> `StateManager._push_tick` call site reads only the planned primitive scalars
> and performs the bounded nonblocking enqueue; its writer thread owns file I/O.
> Existing accepted artifacts contain phase rows and clean footers, which proves
> the capture seam ran. This is evidence tooling only, not native Autoloop DMX.

### B2. Replace the circular autoloop oracle with a falsifiable T7d mode

`tools/ssfmt/re/validate_autoloop_capture.py` already exists, so extend or replace
its phase-fit path rather than adding a second similarly named authority.

- [assumed] Inputs: pcap, schema-2 phase trace, copied bridge/AppLogs, frozen
  verified pack, scenario manifest, project/Venue hashes, and explicit owner deck.
- [confirmed] Continue using `parse_artnet_pcap.universe_frames` for passive
  Universe-0 extraction and immutable pack events for predicted frames.
- [assumed] Add pure functions equivalent to:
  `phase_tick_for_beat(beat, origin, ticks_per_beat, quantizer)`,
  `fit_phase_contract(samples, events, hypotheses)`, and
  `compare_wire_frames(predicted, observed, timing_tolerance)`.
- [confirmed] Remove `rate = bpm * 10.0` as an implicit premise. The candidate 600
  must be one reported hypothesis among a broad data-derived/rational search, not
  a default that the oracle silently assumes.
- [assumed] Test origin hypotheses using recorded state, not an arbitrary fitted
  phase offset: accepted-selection beat, pending arm-sync beat, last accepted
  MIDI/refire beat, phrase-anchor target, correction target, and continuous
  previous phase. A single run-wide clock-latency term is allowed only if measured
  from the dual timestamps; per-segment free phase offsets are forbidden.
- [assumed] Test floor/truncation and nearest-integer boundary conventions. Report
  all passing candidates and the margin to the next candidate; ambiguity is FAIL.
- [assumed] Oracle verdicts are `PASS_T7D_PHASE_CONTRACT`,
  `FAIL_T7D_PHASE_CONTRACT`, or `INCOMPLETE_T7D_EVIDENCE`. Only the first can
  unblock a T7d implementation spec.

> **B2 implementation status (software-only; verified on synthetic data).**
> The falsifiable core is built and unit-tested as a pure module:
> `tools/ssfmt/re/t7d_phase_contract.py` (`phase_tick_for_beat`,
> `predicted_frame_at`, `compare_wire_frames`, `fit_phase_contract`). The
> circular `rate = bpm * 10.0` premise is gone; ticks/beat is a searched
> hypothesis set (600 always included, never assumed) and the result states
> whether 600 passed. Origins come only from recorded-state hypotheses; there is
> no free-offset code path. Value parity is byte-exact; wire-timing tolerance is
> separate (`compare_wire_frames`). Verdicts: PASS (unique scale+quantizer+origin
> with >=4 discriminating transitions), FAIL (>=2 contracts reproduce, or rich
> data nothing reproduces -- includes blackout/zero contamination), INCOMPLETE
> (too few frames/transitions). Tests: `tests/test_t7d_phase_contract.py` (16
> cases incl. true-600, true-non-600 rejecting 600, two-BPM beat-domain
> invariance, continuous/snap/arm-sync origin selection, floor-vs-round
> quantizer determination, integer-beat aliasing -> FAIL, blackout -> mismatch,
> too-few/missing-sample -> INCOMPLETE). The capture-side CLI
> (`validate_autoloop_capture.py --t7d`, with `--phase-trace`/`--t7d-ssfile`)
> wires real pcap + schema-2 trace into the pure oracle; that I/O glue is
> exercised only against real captures and does not upgrade hardware status.
> Documented limitation: at realistic Art-Net sample spacing the quantizer and
> any two origins separated by a 32-beat multiple at tpb=600 may be
> undetermined; the oracle reports such ambiguity as FAIL rather than guessing.

### B3. Capture matrix

Each accepted scenario segment includes at least eight stable beats before the
named edge and 40 beats after it, unless the row requires a longer window. Capture
at least two repetitions per row. A run that lacks its named bridge log/phase-trace
marker is incomplete, not negative evidence.

| Scenario | Operator reproduction after baseline | What the capture must reveal |
| --- | --- | --- |
| **arm** | [assumed] From stopped/unloaded output, load and play a known unscripted track whose chosen verified IAC autoloop is stable; continue through the first pending/locked phrase and at least one later phrase. | [unknown] Whether tick zero occurs at deck-load/accepted selection, at `autoloop_arm_sync_beat`, at the later lock, or on a continuous/global phase; whether the event is 32-beat quantized. |
| **refire** | [assumed] Hold the same accepted identity while playback crosses one phrase-marker refire and one subsequent 32-beat interval refire; require `[SM] midi-refire` and, when applicable, `[LX] same-scene-refire`/`[LX] fired`. | [unknown] Whether re-sending the same autoloop resets, continues, or snaps; whether marker and interval refires share the same origin rule. |
| **master-switch** | [assumed] Play two unscripted, beatgrid-valid decks at a controlled similar BPM; switch master more than one second before the next 32-beat boundary so the scheduled master-arm path is exercised. Keep both transports otherwise unchanged. | [unknown] Whether the previous deck's animation is cut/held, where the new identity starts, whether phase waits for the scheduled boundary, and whether ownership contaminates Universe 0. |
| **drop-hold** | [assumed] Use a reviewed `drop_mode` personality with nonzero `post_drop_hold_beats`; capture buildup entry, drop crossing, and the entire `drop_hold` window while the accepted drop identity remains unchanged. | [unknown] Whether the held drop animation advances continuously, freezes, or restarts. A same-scene skip without a wire reset falsifies “every decision resets.” |
| **buildup** | [assumed] Use a track with a curated Smart Drop and an UP phrase. Start more than `buildup_lookahead_beats` before the drop; require `buildup_to_drop_window` and `[LX] fired role=buildup`. | [unknown] Whether the new buildup identity starts at selection beat, snaps to the current global phrase, or inherits the previous animation phase. |
| ~~**phrase-anchor**~~ | **DROPPED 2026-06-22** — `_phrase_anchor` is gated on `RBSS_PHRASE_ANCHOR=1` (`state_manager.py:481`), which the operator's live rig does not set, so the transition never fires in production and is not part of the runtime contract. | n/a |
| **correction** | [assumed] With master phrase-arm enabled, switch master within 0.25-0.5 beat after a 32-beat boundary until the real logs show `arm-grace-late`, `arm-correction-pending`, `arm-correction-clear`, and the later correction lock. Do not inject delay or edit code to force it. | [unknown] Whether the late immediate arm and later correction each reset/continue/snap, and which recorded target is the phase origin after correction. |

### B4. Operator-only capture protocol

The operator performs these steps only after B1/B2 are implemented, reviewed, and
green. The agent prepares one scenario at a time and never starts `sudo tcpdump`,
playback, a bridge restart, or a hardware action.

1. [assumed operator action] Create a fresh ignored directory and prove exactly
   one bridge process:

   ```bash
   cd /Users/bbui/rb_ss_bridge_v2
   RUN_ID="t7d_<scenario>_$(date +%Y%m%d_%H%M%S)"
   CAP="tools/ssfmt/captures/t7d/$RUN_ID"
   mkdir -p "$CAP/logs"
   test "$(pgrep -f '[r]b_ss_bridge_v2' | wc -l | tr -d ' ')" = "1"
   jq '{process: .process.state, pack: .soundswitch_pack}' /tmp/rb_ss_bridge_v2_status.json
   ```

2. **OPERATOR ACTION:** confirm SoundSwitch is open on the saved bounded project;
   all physical lasers/DMX fixtures and Enttec output are disconnected or powered
   safe; bridge-native `soundswitch_pack.enabled` is false; no live audience is
   exposed. Then speak the same gate:

   ```bash
   say "Operator action: confirm SoundSwitch is ready, all fixtures are disconnected, direct pack output is disabled, and exactly one bridge is running."
   ```

3. [assumed operator action] Hash saved project inputs and begin the bridge phase
   trace. `dedup=false` is required; the schema-2 phase rows perform their own
   bounded sampling:

   ```bash
   find "$HOME/Music/SoundSwitch/default.ssproj" -maxdepth 1 -type f \
     -exec shasum -a 256 {} + | LC_ALL=C sort > "$CAP/project.before.sha256"
   printf '{"cmd":"toggle_record_session","path":"%s","dedup":false}\n' \
     "$CAP/session.jsonl" >> /tmp/rb_ss_bridge_v2_commands.jsonl
   ```

4. **OPERATOR ACTION:** start the passive capture in the operator terminal, then
   perform only the named scenario action after the agent supplies its baseline:

   ```bash
   sudo tcpdump -i lo0 -s0 -U -w "$CAP/artnet.pcap" udp port 6454
   ```

   ```bash
   say "Operator action: start the named T7d scenario now and make no other lighting or transport change until the completion prompt."
   ```

5. **OPERATOR ACTION:** after the requested window, stop `tcpdump` with Ctrl-C,
   stop the session recorder, copy rotating logs immediately, and hash the result:

   ```bash
   printf '%s\n' '{"cmd":"toggle_record_session"}' \
     >> /tmp/rb_ss_bridge_v2_commands.jsonl
   cp /tmp/bridge.log "$CAP/logs/"
   cp "$HOME/Library/Application Support/Onesixone/Soundswitch/Logs"/AppLog*.txt \
     "$CAP/logs/"
   find "$HOME/Music/SoundSwitch/default.ssproj" -maxdepth 1 -type f \
     -exec shasum -a 256 {} + | LC_ALL=C sort > "$CAP/project.after.sha256"
   find "$CAP" -type f ! -name artifacts.sha256 -exec shasum -a 256 {} + \
     | LC_ALL=C sort > "$CAP/artifacts.sha256"
   diff -u "$CAP/project.before.sha256" "$CAP/project.after.sha256"
   ```

6. [confirmed approval gate] If the process count is not one, pack output is not
   disabled, fixtures are not physically safe, required startup flags are absent,
   project hashes change, recorder drops occur, or AppLog/phase markers are missing,
   stop. Do not restart, toggle, repair, or reinterpret the run. Record it as
   `INCOMPLETE_T7D_EVIDENCE` and obtain separate approval for the exact live change.

### B4.5 Operator ping + active-wait automation workflow

The manual back-and-forth of §B4 is automated by the **T7d capture conductor**
(`tools/t7d_capture_conductor.py`). The conductor is an observer and an
operator-instruction emitter only: it never connects fixtures, opens
Enttec/serial/DMX, enables the bridge-native pack backend, mutates the
SoundSwitch project, or restarts the bridge. The only things it writes are an
ignored per-run capture directory, a scenario manifest, sanitized summaries, and
the safe `toggle_record_session` runtime command.

**Cardinal rule: "OPERATOR ACTION" is an active-wait gate, not a stopping
point.** When the conductor needs a physical action it cannot perform safely, it
**pings** the operator (audible `say` + a desktop notification + a printed
instruction), then **keeps running and polls** for the expected
artifact/marker/state until the condition is detected or a hard timeout is
reached. The agent driving the conductor MUST NOT end its turn at a gate, MUST
NOT print "awaiting operator action" and stop, MUST NOT ask the operator to paste
any intermediate instruction back into the agent, and MUST NOT mark the task
complete because an operator action is pending. It resumes automatically the
instant the polled condition appears, and it pings again only when *another*
physical action is required.

Conductor subcommands:

```bash
python3 tools/t7d_capture_conductor.py prepare
python3 tools/t7d_capture_conductor.py run-scenario <name> --run-stamp <YYYYmmdd_HHMMSS>
python3 tools/t7d_capture_conductor.py validate-scenario <run_dir>
python3 tools/t7d_capture_conductor.py summarize-corpus
```

Per-scenario conductor protocol (one named scenario per run):

1. **Manifest + run dir (automated).** Create the ignored run directory under
   `tools/ssfmt/captures/t7d/<run_id>` and write `manifest.json` (scenario,
   required markers, min window, restart/startup-flag requirements,
   `pack_output_enabled=false`, hardware-unvalidated status).
2. **Baseline verification (automated, fail-closed).** Confirm exactly one core
   bridge process and that the pack backend is disabled (`soundswitch_pack` null
   or `enabled=false`/`backend in {none, midi}`). If either fails, ping the
   operator and stop the run *for this scenario* with an INCOMPLETE/FAIL record;
   do not start a capture against an unsafe baseline.
3. **Restart gate (automated ping; operator-approved).** No active scenario
   needs a special startup flag. If the phase-trace smoke test proves the running
   bridge predates B1 wiring, the conductor pings the operator with the exact
   ordinary restart reason and does **not** restart. It waits for the operator to
   approve + perform the exact restart, then re-runs. A stale-process run is
   recorded INCOMPLETE, never substituted with a synthetic event.
4. **Safety ping (automated).** Audibly/visibly ping: SoundSwitch open on the
   saved bounded project, all fixtures/Enttec disconnected and safe, no live
   audience, pack disabled, one bridge.
5. **Recorder start (automated, safe).** Append `toggle_record_session` to the
   runtime command file (records inputs only; not an output path).
6. **Operator action + capture start (ping, then ACTIVE WAIT).** Ping the
   operator to start `sudo tcpdump -i lo0 ... udp port 6454` and perform the one
   named scenario action. The conductor then **polls** until both the pcap and
   the session file are growing (`--start-timeout-s`, default 180 s).
7. **Window completion (ACTIVE WAIT).** Poll the bridge log until the scenario's
   required markers appear (`--window-timeout-s`, default 420 s).
8. **Stop + settle (ping, then ACTIVE WAIT).** Ping the operator to stop tcpdump
   (Ctrl-C — the conductor cannot stop a `sudo` process it did not own), stop
   the recorder itself (`toggle_record_session`), and poll until the pcap size
   settles.
9. **Artifact validation + classification (automated).** Copy the bridge log,
   count Universe-0 frames, check markers, check project before/after hashes,
   and classify the gate as **ACCEPTED / INCOMPLETE / FAIL** via fail-closed
   rules (FAIL = pack enabled, not exactly one bridge, or project bytes changed;
   INCOMPLETE = timeout, recorder drops, missing markers, or too few Universe-0
   frames; ACCEPTED = all green). Write a sanitized `summary.json`.
10. **Continue (automated).** Move to the next required repetition/scenario.
    `summarize-corpus` reports which scenarios have the two accepted repetitions
    and which still block. Two accepted repetitions per scenario, plus the
    identity/BPM coverage of §A4/§B6, are required before B6 can pass.

**Timeout policy.** Every active wait fails closed: on timeout the conductor
records an INCOMPLETE capture and never reinterprets the missing artifact as
negative or positive evidence. The agent re-pings and re-runs the scenario if an
operator action can correct it; otherwise it records the precise hard blocker.

### B5. Derivation and holdout method

1. [assumed] Canonicalize pcap frames to timestamped Universe-0 CH1-CH19 states;
   preserve repeated frames for timing and separately derive changed-frame edges.
2. [assumed] Use dual timestamps to align phase rows to pcap epoch time. Report
   clock residual and drift. If the required timing tolerance would exceed 50 ms,
   classify the run incomplete.
3. [assumed] Segment by executor-accepted scene/note and scenario edge, join it to
   the frozen pack's verified scene-to-identity map, then confirm the selection in
   AppLog. Never infer identity from frame similarity or display name. A mapping or
   owner disagreement invalidates the segment.
4. [assumed] Fit scale/quantizer on one repetition from arm, buildup, and refire;
   hold out the other repetition, all correction segments, and at least one entire
   identity. Then reverse the train/holdout split. A rule that needs retraining on
   the holdout fails.
5. [assumed] Evaluate origin/reset hypotheses independently for all six active rows.
   If classes legitimately differ, record an explicit transition-state contract;
   do not force a false “universal” formula. T7d remains blocked until every class
   is deterministic.
6. [assumed] Frame values must be byte-exact (zero channel-value tolerance).
   Outside transition uncertainty windows, 100% of stable observed frames must
   equal `render_autoloop_frame`. Every predicted/observed change must match
   one-to-one within `one observed ArtDmx frame interval + measured clock residual`,
   capped at 50 ms. Unexplained zero/blackout frames are mismatches, not free skips.
7. [assumed] Each accepted segment must contain at least four discriminating
   immutable timeline transitions. A constant/zero interval cannot prove scale or
   origin even if all frames compare equal.

### B6. Falsifiable T7d unblock criteria

T7d may move from `planned, blocked` to implementation-ready only when all are true:

- [ ] [unknown until captured] One ticks/beat value and one integer-boundary rule
      pass both cross-validation directions; every alternative is rejected with a
      reported margin. The report explicitly states whether 600 passed or failed.
- [ ] [unknown until captured] Reset/continue/snap behavior is pinned for arm,
      refire, master-switch, drop-hold, buildup, and correction,
      with two accepted repetitions per class and no per-segment fitted phase offset.
- [ ] [unknown until captured] At least three current verified bridge-used IAC/
      bank-4 identities and two BPM/pitch values are represented; at least one
      identity is a full holdout.
- [ ] [unknown until captured] `validate_autoloop_capture` returns
      `PASS_T7D_PHASE_CONTRACT`; value parity is byte-exact and transition timing is
      within the measured/capped tolerance for every accepted segment.
- [ ] [unknown until captured] Project before/after hashes match, all oracle inputs
      and reports are hashed, no recorder drops span accepted segments, and capture
      ownership/identity is unambiguous.
- [ ] [confirmed required gate] A fresh T7d implementation spec maps the proven
      transition contract into pure code/tests and receives adversarial review.
      The capture result itself does not authorize runtime or hardware output.

Any unchecked item means T7d stays blocked and `_drive_pack_output` continues to
clear the automatic autoloop base to zero (or allows only the existing independently
held static override).

## Part C - Invariants that MUST still hold (live safety)

- [confirmed] `StateManager` remains the only `DeckState` writer. Capture threads
  consume immutable primitive samples; they do not mutate bridge state.
- [confirmed] The 200 Hz push loop gains no blocking filesystem, network, socket,
  MIDI, serial, Enttec, subprocess, retry, sleep, or contended-lock work.
- [confirmed] Existing OS2L output and SoundSwitch animation remain unchanged when
  pack mode is off. The evidence pass observes this path; it does not replace it.
- [confirmed] Bridge-native direct DMX and physical MIDI-laser output remain
  mutually exclusive. The reference capture uses passive loopback Art-Net with
  direct pack output disabled and physical fixtures safe.
- [confirmed] Pack mode remains default-off/dry-run. Missing/stale beat, missing
  identity, recorder gaps, ambiguous ownership, or an unproved transition resolves
  T7d to blocked/safe-zero, never a guessed phase.
- [confirmed] Scripted/static/blackout behavior, Laser Director policy, LEDs/Govee,
  Rekordbox reader authority, and status sanitization remain unchanged by the plan.
- [confirmed] Captures, project bytes, local paths, device identifiers, ports, and
  live config remain ignored/uncommitted. Only sanitized evidence summaries and
  plans may be committed.
- [confirmed] No software/wire pass upgrades the hardware validation status.

## Part D - Tests and evidence gates

### D1. Preparatory tooling tests (before live capture)

- [assumed] `tests/replay/` covers schema-1 compatibility and schema-2 phase-row
  replay/round-trip behavior.
- [assumed] A focused oracle test module uses synthetic timelines/captures with
  known non-600 scale, 600 scale, reset, continuous, snap, clock skew, missing
  samples, ambiguous identity, and blackout contamination. Each wrong hypothesis
  must fail for the intended reason.
- [assumed] A hot-path test patches file/socket/MIDI/serial operations to raise and
  proves phase sampling performs only bounded nonblocking enqueue.
- [confirmed] Existing renderer tests remain the pure explicit-`phase_tick` seam:
  `tests/test_soundswitch_laser_player.py`.

### D2. Required commands at the evidence-tooling checkpoint

```bash
python3 -m unittest tests.test_soundswitch_laser_player tests.test_state_manager_pack_driver
python3 -m unittest tests.replay.test_replay_format tests.replay.test_replay_smoke
python3 -m unittest <new validate_autoloop_capture test module>
python3 tools/prove_soundswitch_pack_generation.py \
  --project ~/Music/SoundSwitch/default.ssproj \
  --output-dir artifacts/soundswitch_pack_generation_proof
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

- [confirmed] These commands are software gates. They open no physical output and
  do not validate hardware.
- [assumed] After captures, run the revised oracle once per scenario and once over
  the full corpus. Preserve each JSON report plus hashes; do not summarize away
  candidate ambiguity or rejected segments.

## Part E - Acceptance for this plan and future handoff

### E1. This planning session

- [x] [confirmed] Both unknowns remain explicitly unknown; no phase mapping or
      `TICKS_PER_BEAT` value is selected.
- [x] [confirmed] All six active transition scenarios have a reproducible operator
      action and a falsifiable question.
- [x] [confirmed] The plan defines the capture surface, beat/arm/identity sources,
      a non-circular derivation, exact tolerance policy, and safe-zero boundary.
- [x] [confirmed] Operator actions preserve fixtures-safe, pack-default-off,
      single-process, no-restart-without-approval, and capture-as-oracle rules.

### E2. Future evidence-pass completion

- [x] [confirmed] B1/B2 tooling is implemented, reviewed, and green in software.
- [x] [confirmed] The conductor accepted two `arm` and two `refire` repetitions
      with unchanged project hashes and clean trace integrity.
- [ ] [unknown] The operator has supplied two accepted repetitions of the four
      remaining scenarios with hashed, unchanged project inputs.
- [ ] [unknown] The full oracle returns `PASS_T7D_PHASE_CONTRACT` with unique scale,
      quantization, and complete transition-origin rules.
- [ ] [confirmed required gate] The ledger and a short sanitized evidence report
      record both passing and falsified hypotheses. Raw captures stay uncommitted.
- [ ] [confirmed required gate] Only then is a separate T7d implementation spec
      authored. T7d is not implemented or hardware-approved by this plan.

## Open evidence and operator action items

1. **OPERATOR ACTION (next capture session):** provide a fixtures-disconnected
   live SoundSwitch reference session and run `master-switch`, `drop-hold`,
   `buildup`, and `correction` one scenario at a time.
2. **OPERATOR ACTION (only if needed):** explicitly approve an exact bridge restart
   command if the running core does not contain the verified phase-trace wiring.
   No active scenario requires a special startup flag.
3. [unknown] The actual ticks/beat, integer quantizer, and per-transition origin/
   reset behavior remain unknown until B6 passes.
4. [unknown] Whether one universal origin exists. A deterministic class-specific
   reset contract is acceptable evidence, but a free fitted offset is not.

## Pre-handoff checklist and adversarial self-review

1. [confirmed] Every factual claim is labeled confirmed/assumed/unknown.
2. [confirmed] Current status and implementation anchors were rechecked at
   `b2ce63d`; exact line numbers remain secondary to executable symbols.
3. [confirmed] Pending arm, smart-drop mask, held drop, same-scene refire, and
   accepted-identity interactions are explicit.
4. [confirmed] Arm, refire, master-switch, drop-hold, buildup, correction,
   stop/incomplete, and project-drift paths all fail closed.
5. [confirmed] The only third-party command surface here is operator-owned
   `tcpdump`; interface, filter, output path, stop action, AppLog copy, and hashes
   are explicit. No external API payload is assumed.
6. [confirmed] Existing `abs_beat_pos`, arm/refire fields, executor decision, and
   `last_accepted_identity` are reused; no second deck/transport authority is added.
7. [confirmed] Scale/origin fitting and frame comparison have pure-function seams.
8. [confirmed] Hot-path, device, single-process, LEDs/lasers, restart, and
   hardware-status constraints are explicit.
9. [confirmed] Adversarial risks and preventions:
   - hard-coded 600 creates circular proof -> remove it and include non-600 tests;
   - a free phase offset hides the wrong origin -> forbid per-segment offsets;
   - zero/blackout frames create false parity -> require discriminating transitions
     and count unexplained zero as mismatch;
   - AppLog deck selection may not own Universe 0 -> require phase-trace owner plus
     single-variable master scenarios and reject ambiguity;
   - clock skew can look like a phase reset -> use dual timestamps and a measured,
     capped timing tolerance;
   - same-state cycle points can hide a restart -> select dense, uniquely spaced
     timelines and require transition matching, not frame-ratio alone.

## When the capture pass finishes

Report the exact accepted/rejected capture set and hashes, the unique or ambiguous
scale/quantizer result, the reset/continue/snap rule for every scenario, oracle
verdicts/tolerances, recorder drops, project-hash result, and any remaining unknown.
Then provide an operator summary stating what direct pack autoloops would do, what
OS2L/MIDI/LED/Govee/Rekordbox behavior remains unchanged, what logs/status/frames
to watch, and that hardware remains unvalidated. Do not enable, restart, or request
physical output until a separate reviewed T7d implementation and live gate exist.
