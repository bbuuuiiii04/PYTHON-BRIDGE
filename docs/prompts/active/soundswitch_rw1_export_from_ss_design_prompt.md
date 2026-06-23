---
doc_status: active-prompt
truth_level: code-test-and-current-roadmap-grounded
last_verified_commit: 0c2ba07
last_verified_date: 2026-06-23
validation_scope: Opus design/spec prompt for RW-1 only; no implementation or live/runtime mutation
---

# Opus prompt - design/spec RW-1 `Export from SS`

You are the design/spec author for the next bounded SoundSwitch exporter task in
`/Users/bbui/rb_ss_bridge_v2`.

Your task is **planning only**. Do not edit Python, config, tests, runtime state,
the saved SoundSwitch project, or hardware. Do not start/restart the bridge, send
commands, open MIDI/serial/Enttec, or enable pack output.

## Mission

Author a code-grounded Part A-E implementation spec for **RW-1: one-click
canonical export/publish/reload**.

The operator workflow to deliver is:

1. Brandon makes changes in SoundSwitch and saves them.
2. Brandon clicks one bridge-menubar action named **Export from SS**.
3. The existing exporter performs a complete read-only rescan of the canonical
   saved project.
4. A fully staged and independently verified pack replaces the prior pack at
   one stable canonical pack location. Repeated exports must not accumulate
   timestamped pack directories.
5. If the bridge is running, the menubar requests an explicit pack reload and
   reports export and reload outcomes separately.
6. If the bridge is stopped, export still succeeds without starting it.
7. Export/reload never enables output, changes backend, restarts the bridge, or
   opens MIDI/serial/Enttec/DMX hardware.

The current pack format is a directory containing 95 canonical artifacts. In
operator language, “one file gets overwritten” means one stable pack location,
not a new export directory per click. Do not redesign the verified format into
a single archive unless current executable requirements force that architecture
change; if they do, identify it as a blocking decision instead of inventing it.

## Read the smallest authoritative path

Read in this order, then inspect only symbols/tests needed to resolve the spec:

1. `AGENTS.md` and `PRIVATE_OPERATOR_PROFILE.md` if present.
2. `docs/agents/change_contracts.yml`, keys `soundswitch_pack_player`,
   `runtime_commands`, and `docs`.
3. `docs/plans/active/soundswitch_exporter_remaining_work.md`, especially RW-1,
   milestones M0-M2, invariants, and gates.
4. `docs/subsystems/soundswitch_output.md`,
   `docs/subsystems/runtime_commands.md`, and
   `docs/setup/runtime_commands.md`.
5. `tools/export_soundswitch_pack.py` and its export/durability tests in
   `tests/test_soundswitch_pack.py`.
6. `scripts/bridge_menubar.py` and `tests/test_bridge_menubar.py`.
7. `soundswitch_pack_controller.py`, `soundswitch_pack_runtime.py`,
   `soundswitch_pack_player_config.py`, and focused tests for controller,
   runtime commands, and config.
8. Only the Task 2/export and Task 7e reload constraints needed from
   `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md`.

Code and tests beat documents. Re-run line searches at the current HEAD; do not
trust the line numbers below if the branch moved.

## Verified starting facts to recheck

- `tools/export_soundswitch_pack.export_pack()` rejects any existing or
  symlinked destination before decoding.
- Its current safe path is: full decode -> compile -> sibling staging directory
  -> fsync artifact files/directories -> independent `verify_pack()` ->
  `os.replace(staging, new_destination)` -> fsync parent.
- That path is tested only for a previously absent destination. Replacement of
  an existing non-empty pack directory has no implemented transaction.
- `scripts/bridge_menubar.py` has no `Export from SS` item, handler, export
  worker, concurrency guard, progress state, or pack result row.
- `set_soundswitch_pack action=reload` already exists. The controller validates
  before swapping; reload does not enable a disabled pack; failure behavior is
  sanitized and must remain fail-safe.
- Local `config/soundswitch_pack_player.json` is ignored and absent in the
  current checkout. The tracked example contains `pack_path` but no source
  project path.
- Source project bytes are read-only. The workflow reads saved changes only and
  must not automate Command-S or mutate SoundSwitch.
- No filesystem, subprocess, status-provider call, MIDI, serial, socket, sleep,
  or blocking lock may be added to the 200 Hz push loop.
- Current project proof passes 29/29 and the full suite passed 2256 tests at the
  audited head. Those results are a baseline, not proof of RW-1.

## Questions the spec must resolve, not defer

### 1. Canonical source and destination authority

- Name the exact authority for the canonical saved project path.
- Name the exact authority for the canonical pack destination.
- Reuse `pack_path` where possible; do not introduce a second conflicting
  runtime pack-path owner.
- Define behavior when config is absent, paths are empty, parent is missing,
  the destination is the wrong type, or any path component is a symlink.
- Keep paths and source identifiers out of runtime status, menubar text, logs,
  and command error payloads.

### 2. Replace transaction for an existing directory

Specify an implementable, crash-conscious transaction for macOS/POSIX that:

- builds and verifies a sibling staged pack without touching the current pack;
- independently verifies the exact staged bytes that may be published;
- never exposes a partially written directory at the canonical location;
- preserves or restores the old verified pack if publication fails;
- defines the exact rename/swap/backup sequence and every rollback branch;
- rejects symlink destination/parent attacks and cross-filesystem publication;
- fsyncs the necessary files and directory entries;
- cleans staging/backup artifacts without deleting the only verified copy;
- handles first export and replacement export through explicit tested paths;
- serializes concurrent clicks/processes and defines stale-lock recovery without
  guessing or silently deleting an active transaction.

Do not write “atomically replace the directory” without proving the exact
primitive works for an existing non-empty directory on the supported macOS
filesystem. If true single-operation directory exchange requires a platform
primitive, name the seam, fallback, support boundary, and tests.

### 3. Menubar execution model

- Keep the AppKit main thread responsive during decode/compile/fsync/verify.
- Define the worker/thread/subprocess seam and how completion safely returns to
  UI state.
- Prevent double-click/concurrent exports and define retry after failure.
- Define bounded states such as idle, exporting, published, export_failed,
  reload_requested, reload_succeeded, reload_failed.
- Provide concise sanitized operator text. The operator must be able to tell:
  export failed; export succeeded but bridge was off; export and disabled reload
  validation succeeded; export succeeded but live reload failed; or both
  succeeded.
- Do not turn routine status into a noisy dashboard and do not expose local
  paths, UUIDs, ports, device names, raw exception messages, or project bytes.

### 4. Reload handshake and transaction boundary

- Define how the menubar determines whether a fresh bridge status snapshot is
  running versus stale/off.
- Reuse the existing command-file parser and `set_soundswitch_pack reload`; do
  not invent a second reload control plane.
- Define a bounded correlation/acknowledgement mechanism. Merely appending a
  command is not proof that reload succeeded.
- Specify timeout, stale status, command rejection, bridge exit during reload,
  and rapid subsequent-export behavior.
- Define whether a successful disk publication is retained when runtime reload
  fails, and how the old live bundle/new disk bundle split is reported and
  safely recovered. Ground this in current controller behavior.
- Prove reload never implies enable, backend change, bridge start/restart, or
  hardware open. A disabled runtime must remain disabled; a stopped bridge must
  stay stopped.

### 5. Failure and rollback matrix

The spec must enumerate at least:

- unsaved SoundSwitch edit limitation;
- source missing/wrong UUID/wrong version/concurrent drift;
- unsupported active content or mapping;
- generator commit failure;
- artifact write/fsync/verify failure;
- canonical destination absent/existing/file/symlink;
- publish rename/exchange failure at every step;
- cleanup failure;
- concurrent export attempt and stale lock;
- bridge off/stale/multiple processes;
- command append failure;
- reload validation failure;
- sender/input start failure when the already-enabled runtime reloads;
- menubar quit/crash during export or between publish and reload;
- success followed immediately by a second export.

For each row name: old on-disk pack state, new on-disk pack state, live runtime
state, operator-visible result, retry action, and whether any hardware operation
is possible.

## Required output: one Part A-E implementation spec

Write:

```text
docs/plans/active/soundswitch_rw1_export_from_ss_spec.md
```

Use this structure:

### Part A - Context and verified current state

- Exact objective, non-goals, authority files/symbols, current behavior, root
  gap, and explicit software/hardware status.
- A short code-grounded data/control-flow diagram only if it clarifies the
  export -> publish -> reload boundary.

### Part B - Implementation design

- Exact files and symbols to add/change.
- Canonical path authority and config impact.
- Replace transaction with pseudocode detailed enough to implement without
  guessing.
- Menubar worker/state/callback design.
- Existing runtime-command reload handshake and sanitized result schema.
- Cleanup, shutdown, concurrency, recovery, and rollback behavior.
- Required docs/change-contract updates.

### Part C - Invariants and forbidden behavior

- Preserve every invariant in the active remaining-work roadmap.
- Explicitly state what remains unchanged for OS2L, MIDI lasers, LEDs/Govee,
  Rekordbox readers, scripted player semantics, T7d, Static Overrides,
  blackout/emergency, and output enablement.
- No watcher, no SoundSwitch project write, no implicit live mutation.

### Part D - Tests and validation

- Exact focused test files/cases, including fault injection for every rename,
  fsync, verify, command, status, thread, and crash boundary practical in
  software.
- AppKit logic must have pure/testable seams so CI does not require a live menu
  bar or SoundSwitch.
- Include repeated-export byte equality, old-pack preservation, reload ack,
  disabled/off behavior, no-device-open assertions, full suite, proof gate,
  docs gates, staleness report, and `git diff --check`.
- Mark all software tests as hardware-unvalidated.

### Part E - Acceptance, sequencing, and rollback

- Checklist with no ambiguous “done” items.
- Commit/task slicing that keeps publication, menubar, and reload acknowledgement
  reviewable without leaving an unsafe half-feature.
- Exact rollback/disable procedure.
- Stop point: spec and review handoff only. No implementation in this task.

## Mandatory design constraints

1. Preserve the current decoder/compiler/verifier; extend the publication seam
   rather than rebuilding the exporter.
2. Full rescan on every click; no filesystem watcher or incremental cache.
3. Only a fully independently verified staged pack may become canonical.
4. Failed export must leave the prior verified canonical pack byte-identical and
   loadable.
5. Do not imply that disk publish and live reload are one success state.
6. Never auto-enable, select a backend, start/restart the bridge, or open output
   hardware.
7. No raw/local identifiers in UI/status/errors.
8. No blocking work in the AppKit main thread or StateManager push loop.
9. Default-off/absent-config operation must leave existing bridge behavior
   unchanged.
10. Scope is RW-1 only. Do not fix pause-vs-stop, mode authority, MIDI-input
    health, status expansion beyond what RW-1 requires, T7d, native Autoloops,
    local live config, or hardware validation.

## Final response from the design task

Return:

1. the created spec path;
2. the exact current-code facts reverified;
3. every policy/architecture decision made by the spec;
4. unresolved blocker(s), if any, with the exact evidence needed;
5. a short independent-review prompt targeting directory replacement safety,
   UI concurrency, reload acknowledgement, sanitization, and no-implicit-enable.

Do not claim RW-1 implemented. Do not claim hardware validation. Do not perform
any live action.
