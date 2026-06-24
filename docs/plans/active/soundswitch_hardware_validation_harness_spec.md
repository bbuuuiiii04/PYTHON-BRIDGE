---
doc_status: active-spec
truth_level: code-grounded
last_verified_commit: f6910f9
last_verified_date: 2026-06-24
validation_scope: non-Autoloop SoundSwitch pack hardware-validation procedure and evidence schema; no hardware action authorized by this document; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec - Non-Autoloop SoundSwitch Hardware-Validation Harness

## Part A - Context & root cause (verified; read, do not implement)

- [confirmed] The bridge already constructs the pack player, controller input, frame sender,
  and `PackOutputBackend` from the ignored local config (`__main__.py:438-528`). It starts the
  controller input before the Enttec sender and requires the serial port to open before pack mode
  becomes live (`__main__.py:532-543`).
- [confirmed] The 200 Hz path expands CH1-CH19 into a 512-byte universe and only enqueues the
  newest frame; serial I/O remains on the worker thread (`soundswitch_frame_sender.py:38-65`,
  `soundswitch_frame_sender.py:72-85`, `enttec_dmx_pro.py:92-101`).
- [confirmed] Graceful stop writes a 518-byte zero packet before closing, but `kill -9`, host
  death, or power loss can leave the Enttec retransmitting its last non-zero frame. Only a physical
  kill/power path covers that failure (`enttec_dmx_pro.py:8-25`, `enttec_dmx_pro.py:220-239`).
- [confirmed] The current tracked example is safe by default: `enabled=false`, `dry_run=true`,
  `output_backend=none`; it requires an explicit CH1-CH19 fixture map and Enttec port
  (`config/soundswitch_pack_player.example.json:1-32`).
- [unknown] Current live process, ignored-config, output, and device state were deliberately not
  inspected or changed during this offline revision. The procedure uses the menubar's exact
  bridge-only process pattern as an operator gate rather than inferring state from a broad argv
  substring.
- [confirmed] The repo has no repeatable SoundSwitch hardware record. HW-001 says the reviewed
  procedure/template exist but no run is logged, and
  ROAD-003 still asks for repeatable logs (`docs/status/active_work_registry.md:43-45`,
  `docs/status/active_work_registry.md:60-64`). The current hardware log contains only pending rows
  and points to the procedure/template (`docs/validation/hardware_validation_log.md:25-54`).
- [confirmed] A healthy held blackout resolves the pack frame to zero; a degraded controller drops
  only the manual overlay and leaves the scripted base running (`state_manager.py:3383-3435`). A
  malformed controller snapshot reaches the bounded software-zero path (`state_manager.py:3523-3542`).
- [confirmed] The direct-DMX driver never calls `select_autoloop`; native Autoloop DMX therefore
  stays zero by design (`state_manager.py:3479-3522`,
  `tests/test_state_manager_pack_driver.py:532-540`).
- [confirmed] The separate OS2L connection exposes bounded connectivity and send/drop/error
  counters, while socket writes stay on its sender thread (`osl_output.py:53-93`,
  `osl_output.py:120-149`). The hardware record can compare those counters without recording the
  endpoint.
- [unknown] The physical fixture models, real DMX addresses, Enttec alias, controller aliases,
  fixture-safe test look, and physical emergency-kill method are local operator facts. They must be
  supplied at the live gate and recorded without committing private paths, ports, or device names.

**Root cause [confirmed].** The software and wire-format lane exists, but the repo has no fixed
operator sequence or run-specific expected-versus-observed record. Repeating an ad hoc test cannot
close HW-001 or ROAD-003.

## Part B - Tasks (implement exactly, in order)

### Absolute rules

- Do not change runtime code, tests, config schema, output behavior, or the tracked example config.
- Do not create a hardware-driving script. Reuse the menubar, existing config loader, status file,
  proof tool, and physical controls. The harness is the reviewed procedure plus its evidence record.
- No agent may create/edit the ignored live config, start/stop/restart the bridge, append a runtime
  command, open MIDI/serial/Enttec/DMX, connect fixtures, or enable output. Every such step is an
  `OPERATOR ACTION` and requires explicit approval in the live session immediately before it runs.
- Do not use `kill -9` as a safety test. It is a documented unsafe state, not a blackout control.
- Test one known scripted track and manual overlays only. Do not run T7d capture, derive phase,
  select an Autoloop, or claim native-Autoloop DMX behavior.
- Existing SoundSwitch OS2L, laser MIDI, LEDs/Govee, Rekordbox readers, and menubar controls must
  remain unchanged. Record observations; do not tune those subsystems during this pass.

### Task 1 - Add the reusable procedure and run template

Create:

- `docs/validation/soundswitch_hardware_validation_procedure.md`
- `docs/validation/soundswitch_hardware_runs/TEMPLATE.md`

The procedure must use these gates in this order:

1. **Offline software gate (agent-safe).** Record `git rev-parse HEAD`; run the focused pack,
   controller, frame-sender, Enttec, menubar, and StateManager tests; run the current-project proof
   gate to `/tmp`; run the hard docs checks. A software failure stops the procedure before any
   operator action.
2. **Operator setup gate.** Record that the canonical pack exists, the ignored config exists, and
   its redacted SHA-256 is captured. Do not print or commit its contents. Require the operator to
   confirm the physical fixture map, exclusive Enttec ownership, SoundSwitch 2.10.3 project/profile,
   controller mapping, fixture-safe static look, and reachable physical kill path.
3. **Safe stopped-state gate.** Rekordbox transport is stopped, no Static Look or blackout is held,
   fixtures are in the agreed safe state, and the physical kill is reachable. The operator stops
   the bridge from the menubar and verifies zero matching processes before changing live config.
4. **Explicit enable gate.** Only the operator may set the ignored config to the already-supported
   `enabled=true`, `dry_run=false`, `output_backend=pack` values and fill the verified local map and
   Enttec alias. Immediately before clicking the menubar start action, ask for explicit approval.
5. **Post-start gate.** Run the exact single-process check below. Require `1`, a fresh status file,
   `soundswitch_pack.enabled=true`, `backend=pack`, and physically dark fixtures while transport and
   overlays remain idle. The status fields prove only copied software state. Physical-kill
   reachability, released controller holds, stopped in-room transport, fixture darkness, and Enttec
   output darkness are separate `OPERATOR OBSERVATION` rows. More than one process or any unexpected
   light is an immediate physical-kill and stop condition.
6. **Fixture/OS2L sequence.** Exercise, one action at a time: safe zero; one known Static Look;
   Static release; one known scripted track; healthy held blackout; blackout release; controller
   degradation while a Static Look is held; scripted stop; graceful menubar stop. For the scripted
   play/stop rows, also record only the OS2L `connected` flag and before/after deltas for sent,
   send-error, and drop counters; never record its endpoint. Record every row before continuing. A
   failure stops the sequence; do not improvise another stimulus.
7. **Emergency rehearsal.** With a deliberately low-risk non-zero look active, the operator uses
   the physical kill path and confirms all affected fixtures dark. Keep the kill engaged, then stop
   the bridge gracefully so the owned sender attempts its zero. While the physical kill remains
   engaged, restore the ignored config to `enabled=false`, `dry_run=true`,
   `output_backend=none`. A graceful stop or software status cannot prove that the zero write reached
   the Enttec. If that write failed, is unknown, or cannot be verified, do not restore the physical
   output path. First power-cycle/reset the Enttec/DMX path or perform an equivalent operator-confirmed
   known-dark verification, then require separate operator approval before restoring the physical
   path. If a known-dark baseline cannot be proven, record `FAIL` or `INCOMPLETE`. Do not use the
   menubar laser emergency item as proof of pack-DMX emergency masking: the pack driver currently
   passes `emergency=False` (`state_manager.py:3429`).
8. **Closeout.** Restore the ignored config to `enabled=false`, `dry_run=true`,
   `output_backend=none`; start/leave stopped only as the operator requests; if restarted, verify
   exactly one process. Record final fixture darkness and the sanitized status/log watchpoints.

Exact process check:

```bash
pgrep -f '^[^[:space:]]*(python3|Python)[^[:space:]]*([[:space:]]+-u)?[[:space:]]+-m[[:space:]]+rb_ss_bridge_v2$' | wc -l
```

This is the exact anchored pattern used by `scripts/bridge_menubar.py:35,219-221`. It matches only a
Python executable running optional `-u` followed by `-m rb_ss_bridge_v2`. It must explicitly exclude
`bridge_menubar.py`, `ss_bridge_watcher.sh`, exporter subprocesses, tests, shell/grep/pgrep commands,
and unrelated argv that merely contains the repository/package name. Run it before and after any
approved restart. Require `0` before live-config editing and exactly `1` after start; otherwise do
not proceed.

### Task 2 - Define the run evidence schema

Each real run is copied from the template to:

```text
docs/validation/soundswitch_hardware_runs/YYYY-MM-DD_<sha7>_<short-slug>.md
```

The template must contain:

- commit/date/time, operator initials, macOS/Rekordbox/SoundSwitch versions;
- fixture/interface model categories and redacted config SHA-256;
- physical-kill description that is useful but contains no local port, serial number, device ID,
  path, or secret;
- preflight results: process count, pack proof, focused tests, status freshness, pack enabled/backend;
- a per-fixture map table:

| Fixture label | Logical CH range | Redacted DMX range | Stimulus | Expected | Observed | Pass/fail | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |

- a sequence table:

| Step | Operator action | Expected direct-DMX result | Expected unchanged behavior | Observed | Pass/fail | Timestamp/evidence |
| --- | --- | --- | --- | --- | --- | --- |

- dedicated rows for safe zero, static hold/release, scripted play/stop, healthy blackout/release,
  degraded-controller overlay release with scripted base continuing, physical emergency kill,
  graceful stop zero, and disabled-config closeout;
- sanitized watchpoints: menubar pack/export line, SoundSwitch OS2L connection plus send/error/drop
  deltas (no endpoint), frame count, bridge log category, lasers, LEDs/Govee, and Rekordbox-reader
  state;
- separate `OPERATOR ACTION` / `OPERATOR OBSERVATION` fields for physical-kill reachability,
  controller holds physically released, Rekordbox transport stopped in the room, fixture darkness,
  Enttec/DMX known-dark verification, and physical-path restore approval; none may be inferred from
  the copied status file;
- deviations, remaining unknowns, rollback/restore result, and a bounded verdict:
  `PASS_LOCAL_SETUP`, `FAIL`, or `INCOMPLETE`.

No raw status file, config body, local path, port, alias, device name, fixture serial, project UUID,
or raw exception may be pasted into the committed record.

### Task 3 - Wire completed evidence into HW-001 / ROAD-003

After—and only after—a real operator-run record exists:

- add its row to `docs/validation/hardware_validation_log.md`;
- update HW-001 in `docs/status/active_work_registry.md` with the exact bounded result and evidence
  path;
- update ROAD-003 only to say that the SoundSwitch local-setup slice has a repeatable record;
- update `docs/status/validation_matrix.md` for this one setup/path only.

A partial or failed run stays `HARDWARE-UNVALIDATED`. A passing local run must not imply other
SoundSwitch versions, profiles, computers, fixture maps, lasers, LEDs/Govee, or native Autoloop DMX.

## Part C - Invariants that MUST still hold (live safety)

- The 200 Hz push loop stays unchanged, lockless with respect to this work, and free of new I/O.
- `StateManager` remains the only `DeckState` writer and sole per-tick pack-frame submit owner.
- RW-1A graceful shutdown zero, RW-2 pause/stop handling, RW-3 scripted authority, RW-4 unified
  overlay-degradation latch/Option B swap behavior, and manual Static Override precedence remain
  unchanged.
- Degraded controller input releases only the manual overlay; it does not black the scripted base.
  Malformed input still resolves the whole pack frame to zero.
- Pack mode remains default-off outside the operator-approved test window.
- Native Autoloop DMX remains safe-zero and untested in this workstream.
- A physical kill path remains mandatory because software cannot cover hard process/host death.

## Part D - Verification

No new algorithm or production code is authorized, so no new unit-test framework or device mock is
needed. Before the procedure can be handed to the operator, run:

```bash
python3 -m unittest \
  tests.test_state_manager_pack_driver \
  tests.test_soundswitch_pack_commands \
  tests.test_bridge_menubar \
  tests.test_soundswitch_frame_sender \
  tests.test_enttec_dmx_pro \
  tests.test_soundswitch_pack_startup
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

The real procedure must record the current-project proof gate result as software evidence, but that
result never substitutes for the fixture observations.

## Part E - Acceptance

- [x] The reusable procedure and run template exist at the exact paths above.
- [x] Every output-opening, restart, config, fixture, blackout, and emergency step is visibly marked
      `OPERATOR ACTION` with an immediate approval gate.
- [x] The safe enable/disable sequence requires one bridge process after start and zero before live
      config editing.
- [x] The run template captures per-fixture expected versus observed behavior and all required
      sequence rows without private data.
- [x] The emergency rehearsal uses the physical kill path and explicitly rejects `kill -9` as a test.
- [x] No Autoloop capture, phase selection, native-Autoloop DMX, or T7d work entered the spec.
- [x] HW-001/ROAD-003/status claims remain hardware-unvalidated until a committed real-run record supports a bounded result.
- [x] Focused tests and docs gates pass; `git diff --check` is clean.

## Pre-handoff checklist

1. Claims are labeled confirmed/unknown; local hardware facts remain unknown until the operator gate.
2. All file/line claims were rechecked at `f6910f9`.
3. Same-tick output composition is not changed.
4. Enable, failure, emergency, shutdown, and restore transitions all have explicit cleanup gates.
5. The existing menubar/config/status/Enttec sequence is named exactly; no invented API is used.
6. Existing output ownership is reused.
7. No algorithm was added; the evidence tables are the repeatable seam.
8. Live safety, process count, physical kill, room-visible watchpoints, and restart approval are explicit.
9. Adversarial case: a non-zero Enttec frame survives `kill -9`; the physical kill stays engaged
   through graceful stop, default-off config restore, and an operator-confirmed known-dark Enttec/DMX
   baseline before physical output can be restored.

## When you finish

Report the two procedure/template files, offline check results, and whether a real hardware run was
performed. If not, say `HARDWARE-UNVALIDATED`; do not ask an agent to perform the live steps. The
operator summary must name expected fixture behavior, unchanged SoundSwitch/laser/LED/Rekordbox
behavior, healthy status/log watchpoints, unverified hardware facts, and the exact approval gate for
the first live restart.
