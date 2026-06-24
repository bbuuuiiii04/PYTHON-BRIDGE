---
doc_status: active-review-prompt
truth_level: commit-scoped-review-instructions
last_verified_commit: 67c9b7a
last_verified_date: 2026-06-24
validation_scope: independent ChatGPT review of RW-5, non-Autoloop hardware-procedure implementation, and SoundSwitch document lifecycle; review-only; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# ChatGPT independent review - SoundSwitch RW-5 and hardware-validation procedure

You are the independent adversarial reviewer for `rb_ss_bridge_v2`. Review the
exact commit range below. Do not implement fixes.

```text
Base: 4138c619eb50282b9f1b7d661ddfab492f416ce5
Head: 67c9b7a9e0ac06aac93a388806ad3d82a175a7bc
Range: 4138c619eb50282b9f1b7d661ddfab492f416ce5..67c9b7a9e0ac06aac93a388806ad3d82a175a7bc
Branch: main
```

The range implements two previously `REVISE` specifications and then organizes
the SoundSwitch documentation lifecycle. Treat all prior review conclusions and
test claims as untrusted until reproduced.

## Hard boundary

This is review-only. Do not edit, commit, push, or mutate external state. Do not:

- read or edit ignored live configuration;
- start, stop, restart, signal, count, or otherwise inspect live bridge processes;
- append runtime commands or invoke menubar actions;
- open MIDI, serial, Enttec, or DMX interfaces;
- connect fixtures or perform hardware-visible tests;
- execute any `OPERATOR ACTION` from the hardware procedure.

Offline/read-only repository inspection and tests using fake/injected interfaces
are allowed. Do not review or propose implementation for T7d capture, phase
derivation, native Autoloop DMX, or roadmap-reconciliation scope.

## Source order

Use this order and re-resolve all line evidence at the review head:

1. executable code;
2. tests;
3. tracked example config;
4. runtime command/status surfaces;
5. current file tree;
6. current authoritative docs;
7. completed specs and old history only as historical evidence.

Start with:

- `AGENTS.md`;
- `docs/agents/change_contracts.yml`;
- `docs/plans/completed/soundswitch/soundswitch_rw5_operational_status_spec.md`;
- `docs/plans/completed/soundswitch/soundswitch_hardware_validation_harness_spec.md`;
- `docs/plans/active/soundswitch_README.md`;
- `docs/plans/active/soundswitch_exporter_remaining_work.md`.

Inspect the implementation surfaces:

- `soundswitch_pack_runtime.py`;
- `state_manager.py`;
- `runtime_status.py`;
- `scripts/bridge_menubar.py`;
- `tests/test_state_manager_pack_driver.py`;
- `tests/test_soundswitch_pack_commands.py`;
- `tests/test_runtime_status.py`;
- `tests/test_bridge_menubar.py`;
- `docs/validation/soundswitch_hardware_validation_procedure.md`;
- `docs/validation/soundswitch_hardware_runs/TEMPLATE.md`.

Use `git diff --find-renames <base>..<head>` to inspect the complete range,
including moved/deleted documents.

## Review surface A - hardware procedure safety

Try to disprove every item:

1. The documented process gate matches only a Python executable running optional
   `-u`, then `-m rb_ss_bridge_v2`, with anchors covering the full argv.
2. It explicitly excludes the menubar, watcher, exporter subprocesses, tests,
   shell/grep/pgrep commands, and unrelated argv containing the package name.
3. The detector is read-only and the procedure requires zero real bridge
   processes before live-config editing and exactly one after operator-approved
   startup.
4. Every config edit, process action, device open, fixture action, blackout, and
   emergency step is visibly marked `OPERATOR ACTION`.
5. Non-zero testing requires the physical kill path to be reachable first and a
   dark idle baseline to be observed.
6. Emergency restore keeps the physical kill engaged, attempts graceful stop/zero,
   restores ignored config to default-off first, and forbids direct physical-path
   restoration when zero is failed, unknown, or unverifiable.
7. A failed/unknown zero requires an Enttec/DMX reset, power-cycle, or equivalent
   operator-confirmed known-dark baseline before restoring the physical path;
   otherwise the run is FAIL or INCOMPLETE.
8. Status is never treated as proof of physical-kill reachability, released
   controller holds, in-room Rekordbox transport, fixture darkness, or Enttec
   physical darkness.
9. The template captures per-fixture expected versus observed behavior,
   timestamps, restore/rollback, incomplete/failure outcomes, remaining unknowns,
   and a setup-bounded `PASS_LOCAL_SETUP` only.
10. Procedure/template text does not expose local paths, ports, aliases, device
    names, fixture serials, project UUIDs, raw exceptions, config contents, or raw
    status files.

Any ambiguity that could allow stale non-zero Enttec output to be re-energized is
a BLOCKER.

## Review surface B - RW-5 status honesty and hot-path safety

Try to disprove every item:

1. `software_zero_frame` is defined only as `frame == _PACK_ZERO_FRAME`; no code,
   test, doc, or UI wording upgrades it to serial success, Enttec acceptance, or
   physical darkness.
2. `frame_count` is an attempted normal software-frame count, not confirmed
   serial sends.
3. Status is published before submitting the same rendered frame, and a later
   `submit_frame` exception neither leaks its raw error nor changes software
   intent into a false hardware claim.
4. A render exception publishes bounded software-zero state and attempts a zero
   submit without leaking raw errors.
5. `PackRuntime.sanitized_status()` is provider-free and calls no object method,
   including `backend.status()`.
6. `StateManager` builds a fresh dict and publishes it with one attribute
   assignment. Published dicts are never mutated or reused.
7. `get_pack_status()` returns only `dict(self._pack_status_snapshot)` and cannot
   call runtime/player/input/backend/sender/filesystem/subprocess/MIDI/serial or
   any provider.
8. `_drive_pack_output()` reuses already-computed tick authority and adds no
   blocking work, I/O, provider calls, filesystem reads, subprocesses, MIDI,
   serial, worker polling, or new lock acquisition to the 200 Hz path.
9. Initial disabled, enable/start, runtime swap, reload, disable, and shutdown
   snapshots are truthful. A newly active enabled runtime never first reports
   `operational_state=disabled`.
10. Operational precedence is exactly:
    `disabled -> blackout -> input_degraded -> static_held -> scripted_active -> autoloop_phase_blocked -> software_zero_frame`.
11. Companion booleans preserve simultaneous truths, especially
    `input_degraded=true` with `scripted_active=true` and a possibly non-zero
    software frame.
12. `autoloop_phase_blocked` never selects Autoloop and never calls
    `select_autoloop`.
13. Menubar code consumes only the copied status file, renders stale status as
    exactly `Pack: Unknown`, sanitizes before applying the 80-character row
    bound, and prevents an older background export-detection result from
    overwriting newer state.
14. The export/reload command remains exactly:
    `{"cmd": "set_soundswitch_pack", "action": "reload"}`.
15. The menubar never enables output, changes backend, or starts the bridge.
16. No local path, port, alias, identifier, UUID, raw frame/hash/error, config
    value, or raw status content enters status/UI output.

Treat a provider call or blocking/I/O regression on the 200 Hz path as a
BLOCKER. Treat any physical-darkness implication as at least HIGH severity.

## Review surface C - tests and lifecycle truth

Confirm tests fail if any of these regress:

- provider-free status or copied-snapshot isolation;
- fresh-dict publication and defensive-copy reads;
- precedence or simultaneous degraded/scripted truth;
- render/submit exception bounding;
- lifecycle snapshots for initial/enable/swap/reload/disable/shutdown;
- Autoloop selection remains uncalled;
- stale menubar status remains `Unknown`;
- export-generation race guard, sanitization, 80-character bound, and exact
  conservative reload command;
- private-data suppression.

Then inspect document lifecycle at the review head:

- the active route contains one current roadmap/index and one T7d execution
  prompt;
- implemented RW-1 through RW-5 and hardware-procedure specs live under
  `docs/plans/completed/soundswitch/` with historical metadata;
- redundant kickoffs, authoring prompts, and completed SoundSwitch review prompts
  are deleted rather than left active;
- research authority remains under `docs/research/soundswitch/`;
- the explicitly excluded reconciliation spec is not treated as current authority;
- authoritative docs agree that T7d/native Autoloop DMX remain incomplete and
  no real hardware run exists.

## Minimum verification

Run from the repository root:

```bash
python3 -m unittest \
  tests.test_state_manager_pack_driver \
  tests.test_soundswitch_pack_commands \
  tests.test_runtime_status \
  tests.test_bridge_menubar \
  tests.test_soundswitch_frame_sender \
  tests.test_enttec_dmx_pro \
  tests.test_soundswitch_pack_startup
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check 4138c619eb50282b9f1b7d661ddfab492f416ce5..67c9b7a9e0ac06aac93a388806ad3d82a175a7bc
```

If a command cannot run, report it as unverified; do not infer a pass. These
software checks do not authorize or substitute for a hardware run.

## Required response

Return one verdict: `APPROVE`, `REVISE`, or `REJECT`.

Then provide:

1. findings first, ordered BLOCKER/HIGH/MEDIUM/LOW, each with current
   `file:line`, evidence, impact, and the smallest required correction;
2. a requirement-by-requirement audit of surfaces A-C marked confirmed,
   contradicted, or unverified;
3. exact commands run and results;
4. scope-creep/private-data audit;
5. confirmation that no live/process/runtime-command/config/hardware action
   occurred;
6. operator summary: what should differ live, what must remain unchanged, healthy
   signals, what to watch in SoundSwitch/lasers/LEDs/Rekordbox/logs, and what
   remains hardware-unvalidated.

Absence of findings is not proof. Approve only if the current code, tests, and
documents independently satisfy every load-bearing claim. Never call this
hardware-validated, show-ready, production-ready, plug-and-play, broadly
compatible, generally supported, or stable.
