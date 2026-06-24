---
doc_status: active-plan
truth_level: code-test-and-current-project-grounded
last_verified_commit: 38953ca
last_verified_date: 2026-06-23
validation_scope: docs-only completion audit and remaining-work roadmap; SoundSwitch 2.10.3 canonical project/RAVE profile; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# SoundSwitch Exporter and Bridge-Native DMX - Remaining Work

This is the single active completion checklist and roadmap for the SoundSwitch
exporter / static-pack / bridge-native DMX project. It replaces the old
session-by-session progress ledger and the completed T4-T8 orchestration
handoffs as the current implementation-status authority.

The bounded product goal is:

1. Brandon authors and **saves** lighting in SoundSwitch 2.10.3.
2. Brandon clicks one bridge-menubar action, **Export from SS**.
3. The exporter performs a complete, stable, read-only rescan of the canonical
   SoundSwitch project.
4. A verified replacement is published to one canonical pack location. Failed
   exports leave the previous verified pack untouched.
5. A running bridge reloads the verified replacement without an implicit
   enable or backend change.
6. Scripted tracks, Autoloops, Static Overrides, blackout, and emergency policy
   render through the bridge-owned CH1-CH19 player and the mutually exclusive
   direct-DMX backend.
7. Existing OS2L, MIDI-laser, LED/Govee, Rekordbox-reader, and command behavior
   remains unchanged whenever pack mode is absent, disabled, dry-run, or
   `output_backend=none`.

This roadmap does **not** authorize a bridge restart, config toggle, MIDI/serial
open, Enttec open, DMX send, fixture connection, or hardware test.

> Accepted status: **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

## 1. Evidence labels and authority

- **[C] confirmed** - read in current code/current project bytes, or executed in
  the 2026-06-23 audit.
- **[P] required policy/spec decision** - the gap is confirmed, but the exact
  implementation must be designed and reviewed before code changes.
- **[U] unknown** - requires live capture, live configuration, or hardware
  evidence; no software inference may promote it.

Authority order for every task:

1. executable code;
2. tests;
3. tracked example configuration;
4. runtime command/status surfaces;
5. current file tree and current saved SoundSwitch project;
6. current research/validation documents;
7. retained completed implementation records and research history as historical
   evidence only.

## 2. Audit snapshot

Audit date: **2026-06-23**. The executable implementation baseline was
`soundswitch/impl` at `b2ce63d`; this roadmap was re-verified through `5029ec4`.
Subsequent commits changed Markdown/agent instructions,
`docs/agents/change_contracts.yml` housekeeping, and only the authority-path
docstring in `tools/prove_soundswitch_pack_generation.py`; no executable runtime
behavior changed, so the code/test findings remain tied to `b2ce63d`. The
worktree was clean before the initial docs-only pass.

### 2.1 Current saved-project proof

Command executed from `/Users/bbui` against the current canonical project, with
the report written under `/tmp`:

```bash
python3.14 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation \
  --project ~/Music/SoundSwitch/default.ssproj \
  --output-dir /tmp/rbss-soundswitch-audit-proof
```

Result:

```text
final_verdict: PASS_IMPLEMENTATION_MAY_BEGIN
counts: 29 PASS / 0 FAIL / 0 INCOMPLETE (foundation 27/27)
```

[C] Current project/profile inventory proven by that run:

- project UUID `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}`;
- SoundSwitch `2.10.3`, primary Venue `RAVE`, Universe 0, CH1-CH19,
  no intensity channel;
- 42/42 current Autoloops parse;
- 44/45 scripted files parse;
- the one unsupported script is the inactive In-App Demo and has no active
  existing-path TrackMap row;
- 32/32 active existing-path scripted tracks are supported;
- 19/19 learned IAC Autoloop bindings resolve;
- 32 Static Looks parse and DDJ slots 8/16/17/24 render their expected frames;
- 232 render-bearing Venue cues plus one catalog-tail record parse;
- the 166-cue active union has zero missing GUIDs and retains SHA-256
  `88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2`;
- F9 one-byte pack mutation and F10 active CC/pitch override fail closed.

### 2.2 Tests and docs checks executed

Focused RW-1 exporter/menubar/config tests:

```text
Ran 83 tests in 7.993s
OK
```

Full suite:

```text
Ran 2286 tests in 31.993s
OK (skipped=3, expected failures=1)
```

Current-project proof gate:

```text
final_verdict: PASS_IMPLEMENTATION_MAY_BEGIN
counts: 29 PASS / 0 FAIL / 0 INCOMPLETE (foundation 27/27)
```

Hard docs checks:

```text
docs metadata check passed
agent contract check passed
docs drift check passed
```

The advisory staleness report identified seven contracts as stale from the
global `a5f7ced` baseline, including the broad `soundswitch_pack_player`
contract. The RW-1 docs named by the reviewed spec were re-verified, but the
global baseline was not advanced because unrelated contract docs remain to be
re-verified. Hard checks passing does not mean every broad contract document is
current; it proves only the checker-enforced surfaces.

### 2.3 Live/runtime state observed without mutation

[C] The ignored local `config/soundswitch_pack_player.json` is absent.

[C] The last status snapshot was stale and reported the pack disabled/not
configured (`legacy_midi_not_configured`, no pack loaded, zero pack frames).

[C] No bridge core process was running during the audit. No process was
started, stopped, signaled, or restarted.

## 3. Completion matrix

| Workstream | Status | Verified boundary |
| --- | --- | --- |
| Reverse engineering / format closure | **done, bounded** | Current 2.10.3 canonical project/RAVE/CH1-CH19 scope only. |
| Current-project decoder | **done, software** | Strict read-only full inventory, identity/stability/collision/layout checks. |
| Canonical pack compiler and independent verifier | **done, software** | Deterministic 95-artifact pack; new-path atomic publish; F9/F10 pass. |
| Complete rescan semantics | **done inside each export** | Saved add/edit/rename/delete/mapping/static changes are read on the next invocation. |
| Menubar `Export from SS` workflow | **implemented, software-tested; review pending** | Background subprocess, sanitized progress/result, stopped/disabled no-reload path, and fingerprint reload acknowledgement are covered by pure tests. |
| Replace one canonical pack in place | **implemented, software-tested; review pending** | `publish_pack()` verifies staging before macOS swap or recoverable move-aside fallback; failure-path and real-project byte/load tests pass. |
| Scripted content support | **done, bounded software/wire** | 32/32 active existing-path scripts supported; inactive demo excluded explicitly. |
| Pure scripted renderer/player | **done, software/wire** | Sparse persistence, raw-zero, seek/backseek, paused query, stop/unload zero, overrides/masks. |
| Scripted `StateManager` driver | **partial** | Playing/fresh/valid-SSID path submits frames; runtime pause/mode/input-health gaps remain. |
| Static Override/blackout input adapter | **partial runtime integration** | Adapter semantics tested; driver ignores health/error/drop fields. |
| Pack config/startup/runtime commands | **implemented, default-off** | Config load, startup construction, explicit enable/reload/backend, and atomic runtime-bundle swap; a post-swap shutdown-ownership gap remains because new output owners are not re-registered for cleanup (RW-1A). |
| Direct-DMX backend and Enttec sender | **implemented, software/wire only** | Fixture-map expansion, 518-byte framing, mailbox, and startup-owned graceful zero/stop; runtime-swap cleanup remains RW-1A; no rig proof. |
| MIDI-laser/direct-DMX mutual exclusivity | **implemented, software-tested** | One injected backend and port-level startup selection. |
| Offline/shadow Task 8 | **done, software** | Backend-none/frame-hash shadow; runtime Autoloop phase intentionally deferred. |
| T7d capture tooling | **done, software** | Phase tracer, conductor, oracle and synthetic tests exist. |
| T7d live phase evidence | **blocked/incomplete** | 2 arm + 2 refire captures pass conductor integrity; 4 scenario pairs, identity/holdout reconciliation, and the unique oracle remain; no scale/quantizer/origin selected. |
| Native-DMX Autoloop driver | **not implemented by design** | `StateManager` never calls `select_autoloop`; base stays zero. |
| Hardware gate / physical fixture validation | **not started** | No repeatable repo hardware record; local pack config absent. |
| PR integration | **open** | PR #116 contains the implementation series; merge is not completion proof. |

## 4. What is complete and must not be rebuilt

### 4.1 Saved-project decode and export semantics

- [x] [C] Project identity is pinned by UUID, SoundSwitch version, Venue GUID,
  and current 19-channel fixture profile.
- [x] [C] Every export invocation snapshots the complete project tree and
  rejects symlinks, concurrent source drift, case collisions, missing sources,
  identity conflicts, unresolved active references, and unsupported active
  layouts (`soundswitch_project_decoder.decode_project`).
- [x] [C] Autoloop identity is catalog/file-number based, not display-name or
  file-order based.
- [x] [C] Scripted identity is normalized SSID plus the saved TrackMap path
  classification.
- [x] [C] Learned MIDI mappings and all 32 primary-Venue Static Looks are
  rescanned during each export invocation.
- [x] [C] Added, edited, renamed, and deleted saved content is represented by
  the next full export. There is no frozen-corpus dependency.
- [x] [C] The source SoundSwitch project is read-only. The exporter does not
  and must not save or mutate SoundSwitch.
- [x] [C] Export captures saved on-disk changes only. Unsaved SoundSwitch UI
  state is outside the readable project boundary.

### 4.2 Pack compiler, verification, and loader

- [x] [C] The compiler emits the canonical 95-artifact directory.
- [x] [C] Identical inputs generate byte-identical pack trees.
- [x] [C] Independent verification checks manifest/inventory/source hashes,
  canonical JSON, semantics, crosswalks, fixture boundary, and optional current
  source-project equality.
- [x] [C] New-path export stages, fsyncs, verifies, and atomically renames the
  staging directory into a previously absent destination.
- [x] [C] A failed new-path export removes staging and does not publish it.
- [x] [C] `load_pack()` returns immutable verified models and rejects mutations.

Do not replace these components with a watcher, capture-derived renderer, fuzzy
scan, or ad-hoc JSON copy pipeline.

### 4.3 Scripted content and pure rendering

- [x] [C] All 32 current active scripted tracks use supported layouts and have
  no missing referenced cue.
- [x] [C] Future ordinary saved scripted tracks in the supported 2.10.3 layout
  family are decoded from their current bytes; no per-track capture is needed.
- [x] [C] A genuinely new active layout fails export before publication and
  needs a separate evidence/format-extension task.
- [x] [C] `render_scripted_frame()` applies persistent sparse patches from an
  initial zero state using authoritative integer elapsed milliseconds.
- [x] [C] Equal-time stored order, raw-zero clear/control behavior, static
  precedence, blackout/emergency precedence, and stop/end/unload zero are
  covered by tests and current-project golden frames.
- [x] [C] The pure player accepts `transport="paused"` and rerenders the
  current authoritative elapsed position without history dependence.

### 4.4 Low-level direct-DMX software lane

- [x] [C] `__main__._build_soundswitch_pack_startup()` constructs a verified
  player, controller group, fixture-map-bound sender, and `PackOutputBackend`.
- [x] [C] `__main__._start_soundswitch_pack_workers()` starts controller inputs
  before the serial sender and rolls both back on failure.
- [x] [C] Pack startup and runtime reload never fall back to physical MIDI after
  a pack failure.
- [x] [C] `StateManager` is the sole per-tick `submit_frame` owner.
- [x] [C] `SoundSwitchFrameSender` expands CH1-CH19 using only the validated
  fixture map and queues Enttec frames through a bounded latest-frame mailbox.
- [x] [C] Graceful stop requests a zero packet before serial close for the
  startup-owned sender. A sender created by a runtime `set_soundswitch_pack`
  swap is published into `sm._pack_runtime` but is not registered in
  `__main__.pack_output_owners`; SIGTERM/SIGINT/atexit cleanup therefore does
  not zero/stop that live swapped sender (RW-1A).
- [x] [C] Process death/`kill -9` cannot be claimed safe; Enttec may retain the
  last frame and therefore still requires a physical kill method.

> **Forward note — laser transition-blackout migration (cross-subsystem; settle here, not in MIDI):**
> when the laser-director output migrates to the direct-DMX/`PackOutputBackend` lane, the laser
> transition blackout — today the MIDI mask (`breakdown`/`master_switch` covers + the Smart-Drop
> drop-window, the held `manual_blackout_on/off` note refcounted in `LaserSceneExecutor`, cleared by
> the StateManager SM-net `smart_drop_crossing_without_drop_decision`) — must be reproduced as a
> frame-level blackout. The held note retires (the pack backend already no-ops `manual_blackout_*`;
> they carry no `scene_name`), but the masking **decision** (overlapping refcounted owners + teardown
> timing) ports over. Settle the owner/teardown semantics, including the known **C2** gated-off
> -crossing edge, here rather than in the outgoing MIDI path. See `docs/subsystems/laser.md`
> (Blackout-mask migration) and `docs/plans/active/laser_smartnet_mask_preserve_spec.md`.

## 5. Confirmed remaining implementation gaps

### RW-1 - One-click canonical export/publish/reload workflow

**Status:** [C] implemented and software-tested on branch
`soundswitch/rw1-export-from-ss`; independent implementation review is pending.

Evidence:

- commits `bcbb312`, `5d9b59f`, and `38953ca` implement replace publication,
  the canonical sanitized CLI, and the menubar worker/reload handshake.
- `PublishPackReplaceTests` plus current-project tests cover first publish,
  replacement, idempotence, staged verification failure, fallback rollback,
  symlink/parent rejection, lock recovery, orphan cleanup, and byte-identical
  loadability of the prior verified pack.
- `tests/test_bridge_menubar.py` covers exact argv construction, result parsing,
  reload-ack freshness, stopped/disabled behavior, exact reload command,
  click concurrency, timeout recovery, and sanitized display strings.

Required behavior:

- [x] [C] Define one stable canonical pack location. The existing format is a
  directory; “one file” in operator UX means one canonical pack location, not
  multiple timestamped export directories.
- [x] [C] Add a replace-capable publication API that builds and verifies a
  sibling staging directory, preserves the old verified pack through every
  pre-publish failure, atomically swaps only after verification, fsyncs the
  directory entries/rename, and rolls back safely if replacement fails.
- [x] [C] Do not follow or replace a symlinked destination or parent.
- [x] [C] Serialize concurrent export attempts; a second click must not create
  two publishers or race reload.
- [x] [C] Add `Export from SS` to the menubar and run blocking decode/export/
  verify work off the AppKit/UI thread.
- [x] [C] Show sanitized progress and terminal success/failure without local
  project paths, device names, ports, raw exceptions, or project bytes.
- [x] [C] After successful publish, request `set_soundswitch_pack/reload` only
  when appropriate. Reload never implies enablement or a backend change. The
  menubar sends no command when status reports pack output disabled; publication
  success is standalone and the default-off posture remains unchanged.
- [x] [C] If the bridge is stopped, complete export successfully and report
  that the pack will load on the next configured startup; do not start or
  restart the bridge.
- [x] [C] A failed export or reload must leave a clear operator-visible result;
  export success and runtime reload success must be distinguishable.
- [x] [C] Keep SoundSwitch save outside the bridge. SoundSwitch changes remain
  save-before-export; the bridge does not automate Command-S. The compact menu
  text does not add instructional copy.

Acceptance gate:

- one click performs exactly one full rescan;
- the canonical location is the only persistent pack location;
- successful replacement is independently verified;
- failed replacement leaves the old verified pack byte-identical and loadable;
- enabled runtime requests reload and requires a fresh matching pack fingerprint
  before reporting live; disabled runtime receives no command and remains
  disabled, and a stopped bridge stays stopped;
- no hardware/device is opened by export tests;
- menubar remains responsive and reports sanitized state.

Implementation evidence satisfies these software gates. Independent review is
still required before RW-1 is promoted from review-pending to complete.

### RW-2 - Scripted runtime transport semantics

**Status:** [C] partial/mismatched. **Priority:** before any scripted hardware gate.

Evidence:

- `soundswitch_laser_player.py:213-224` accepts `playing` and `paused`.
- `soundswitch_laser_player.py:271-315` renders both `playing` and `paused`, and
  returns zero for stopped/ended/unloaded.
- `state_manager.py:1120-1124` represents `PAUSE` by setting
  `DeckState.playing=False`.
- `state_manager.py:3292-3311` selects scripted output only when `playing=True`;
  every false value clears the selection. The runtime therefore cannot
  distinguish paused from stopped for the pack driver.
- Pure-player pause tests exist, but `tests/test_state_manager_pack_driver.py`
  does not cover a real pause-vs-stop distinction.

Required work:

- [ ] [P] Design one authoritative transport derivation using existing
  StateManager/Rekordbox state; do not create a second transport owner.
- [ ] [P] Pin desired pause behavior to the already-authorized player contract:
  paused rerenders/holds the current authoritative elapsed frame; stopped,
  ended, unloaded, stale, and errored resolve zero.
- [ ] [P] Cover pause, resume, stop debounce, master change, track load, stale
  position, elapsed discontinuity, and source recovery.
- [ ] [P] Prove that pause does not retain an obsolete cached frame; the frame
  must still derive from immutable events at authoritative elapsed.

### RW-3 - Explicit scripted/autoloop/idle authority gate

**Status:** [C] implementation does not enforce the full stated authority tuple.

Evidence:

- `StateManager._update_lighting()` derives `scripted` only from
  `d.scripted_id and is_playing`, otherwise `autoloop`/`idle`.
- `StateManager._drive_pack_output()` currently gates scripted selection on
  `playing + fresh PositionCache + normalized soundswitch_id + no load/change
  discontinuity`; it does not require `d.scripted_id` or
  `OutputState.lighting_mode == "scripted"`.
- Current tests inject SSID/playing directly and do not prove the real
  filepath-resolved -> scripted-id -> lighting-mode -> pack-frame chain.

Required work:

- [ ] [P] Specify and implement one explicit mode-authority decision that reuses
  `active_deck`, `d.scripted_id`, `d.meta.soundswitch_id`,
  `os.lighting_mode`, transport, and fresh position authority.
- [ ] [P] Zero the automatic base during any unresolved/mismatched transition;
  do not render an SSID merely because it is syntactically valid.
- [ ] [P] Add real event-chain integration tests for load, filepath resolve,
  scripted match, play, master switch, track replacement, and return to
  autoloop/idle.
- [ ] [P] Preserve the accepted manual Static Override policy and its blackout
  precedence; do not let the mode gate silently change controller behavior.

### RW-4 - Controller-input health fail-to-zero integration

**Status:** [C] snapshot health exists but the driver ignores it.

Evidence:

- `MidiInputSnapshot` exposes `worker_alive`, `error`, and `mail_drop_count`
  alongside held state (`soundswitch_midi_input.py:36-47`).
- The adapter clears stale held state and reports `stale_hold`
  (`soundswitch_midi_input.py:100-121`).
- `StateManager._drive_pack_output()` reads only `blackout_held` and
  `held_static_slot` (`state_manager.py:3267-3277`).
- A dead/errored controller can therefore clear its held override while the
  automatic scripted base continues; the active implementation does not
  satisfy the broader fail-to-zero requirement stated by the original spec.

Required work:

- [ ] [P] Decide and document the exact healthy/recovery latch using existing
  snapshot fields; no MIDI API call may enter `_push_tick`.
- [ ] [P] On worker death, input error, conflicting holds, or safety-relevant
  mailbox loss, resolve the appropriate output to zero before recovery.
- [ ] [P] Define how an intentionally empty controller-alias configuration is
  distinguished from a configured worker failure so scripted playback without
  manual inputs is not accidentally made impossible.
- [ ] [P] Require a fresh healthy snapshot before normal input-controlled output
  resumes; prevent stale note-off/note-on state from reappearing after reload.
- [ ] [P] Add tests for worker death while static held, worker death while
  blackout held, no aliases configured, mailbox drops, stale hold, conflict,
  pack reload, and healthy recovery.

### RW-5 - Operational status and menubar visibility

**Status:** [C] basic status exists; original operational surface is incomplete.

Evidence:

- `PackRuntime.sanitized_status()` currently exposes availability, enabled,
  backend, pack-loaded/hash, frame count, active-identity presence, and reason
  (`soundswitch_pack_runtime.py:35-58`).
- It does not expose the current source kind, scripted authority/elapsed,
  Autoloop phase readiness, held static slot, blackout, MIDI-input health,
  mailbox drops, sender health, last-frame hash, or stale/error category.
- The menubar has no pack/export status row or export progress.

Required work:

- [ ] [P] Define a sanitized, bounded status schema sufficient to distinguish
  `exporting`, `export_failed`, `published`, `reload_failed`, `disabled`,
  `scripted_active`, `autoloop_phase_blocked`, `input_degraded`,
  `sender_degraded`, and `zero_safe` without leaking identifiers/paths/ports.
- [ ] [P] Source status from copied/snapshot state; never call providers,
  filesystems, subprocesses, MIDI, or serial inside the 200 Hz push loop.
- [ ] [P] Show concise menubar state without turning routine operation into a
  noisy dashboard.
- [ ] [P] Add status/menubar tests and update drift checks if the documented
  command/status contract changes.

### RW-1A - Runtime output ownership on shutdown

**Status:** [C] implemented and software-tested (`__main__._shutdown_zero_pack_outputs`,
commits `1908737`/`988d73a`) per the reviewed spec
(`docs/plans/active/soundswitch_rw1a_shutdown_ownership_spec.md`). Independent
implementation review returned **REVISE-AND-APPROVE**: one narrow concurrent-swap
race (cleanup runs before `command_reader.stop()`, which does not join) plus minor
test-coverage gaps remain; a code-only revision is in flight. **Priority:** before
RW-6, M5, hardware work, or any pack-output enablement.

**Chosen design (supersedes the "re-register in `pack_output_owners`" option
below):** the live runtime-swapped sender is already the single source of truth
via `sm.get_pack_runtime()` (startup and post-swap alike), so the shutdown path
zeroes it directly (option b). No controller changes and no per-publish
re-registration are required.

Evidence:

- `__main__.main()` creates `pack_output_owners` for the startup sender and MIDI
  input, and `_cleanup_pack_outputs()` is the SIGTERM/SIGINT/atexit cleanup path.
  Those owner slots are assigned only around startup worker construction.
- `SoundSwitchPackController._swap_to_started()` builds and starts new output
  objects, then publishes them through `StateManager.set_pack_runtime()` without
  updating `pack_output_owners`.
- `StateManager.stop()` only sets its stop event, and `_run()` exits without
  zeroing or stopping the currently published `PackRuntime` outputs.
- `test_shutdown_zeros_pack_before_slow_bridge_joins` is a static source-order
  assertion. It does not exercise SIGTERM after a runtime swap.
- Pack output is currently default-off and the ignored local pack config is
  absent, so this is latent until pack mode is enabled and runtime-swapped.

Required work:

- [ ] [P] After every runtime swap, make the live published `PackRuntime`'s
  `frame_sender` and `midi_input` reachable by shutdown cleanup. Either
  re-register them in `pack_output_owners` when publishing, or have the
  SIGTERM/SIGINT/atexit path zero and stop `sm.get_pack_runtime()` directly.
- [ ] [P] Keep all zero/stop/join work outside `_push_tick`; no blocking work may
  enter the 200 Hz path.
- [ ] [P] Add a behavioral shutdown test that swaps to a new fake sender, raises
  SIGTERM through the shutdown path, asserts that the **live** sender's
  `zero_and_stop()` is called, and proves that stopping the stale startup sender
  is a harmless no-op. The existing source-order test is not acceptance evidence
  for this runtime-swap case.

### RW-6 - Local pack configuration and deployment preparation

**Status:** [C] code exists; [U] live values and physical mapping are not validated.

- [ ] [U] Select the one canonical pack location after RW-1 design.
- [ ] [U] Create the ignored local pack config from the tracked example only
  after review. Do not commit paths, aliases, fixture addresses, or ports.
- [ ] [U] Verify the physical CH1-CH19 -> DMX-address fixture map.
- [ ] [U] Verify controller device-to-port aliases if Static Overrides/blackout
  inputs are used.
- [ ] [U] Verify the Enttec port and physical kill method.
- [ ] [U] Keep `enabled=false`, `dry_run=true`, `output_backend=none` until the
  reviewed hardware gate explicitly advances each setting.

This is deployment/configuration work, not proof that the runtime implementation
is correct.

### RW-7 - T7d live Autoloop phase evidence

**Status:** [C] tooling complete; [C] 4 integrity-accepted captures across 2 of
6 scenarios; [U] phase contract incomplete; implementation blocked.

- [x] [C] Schema-2 phase tracing and footer integrity are wired.
- [x] [C] Capture conductor and active-wait operator workflow exist.
- [x] [C] Falsifiable oracle searches scale/quantizer/recorded-state origins;
  600 is a hypothesis, not a default.
- [x] [C] Capture-count gate met for `arm` (2 ACCEPTED, 1 FAIL) and `refire`
  (2 ACCEPTED). These are conductor integrity verdicts, not oracle verdicts.
- [ ] [U] Reverify exactly one bridge process, pack disabled, fixtures/Enttec
  safe, and the B1 trace smoke test before the next capture session.
- [ ] [U] Collect two accepted repetitions of each remaining scenario:
  master-switch, drop-hold, buildup, and correction.
- [ ] [U] Cover at least three verified identities, at least two BPM/pitch
  values, and one full holdout identity. Accepted traces contain observed BPM
  values 130/138/141/150, but identity ownership and the holdout split remain
  unverified.
- [ ] [U] Prove unchanged project hashes, Universe-0 ownership, sufficient frame
  count, trace integrity, and no recorder drop for every accepted segment.
- [ ] [U] Obtain one unique scale/quantizer/origin/reset/continue/snap contract,
  or record `FAIL`/`INCOMPLETE` without writing a runtime spec.

The retired phrase-anchor scenario is not part of the current live contract
because the operator does not run `RBSS_PHRASE_ANCHOR=1`. Re-add it only if the
live launch policy changes.

### RW-8 - Native-DMX Autoloop runtime integration

**Status:** [C] intentionally not implemented; blocked by RW-7.

Current boundary:

- `LaserPackPlayer.select_autoloop(identity, phase_tick)` and pure rendering
  exist.
- `PackOutputBackend.last_accepted_identity` records the executor-accepted
  verified pack identity.
- `StateManager._drive_pack_output()` never calls `select_autoloop`; its
  automatic base remains zero for Autoloop mode unless an independent held
  Static Override is active.

Only after `PASS_T7D_PHASE_CONTRACT`:

- [ ] author a separate reviewed Part A-E implementation spec grounded in the
  accepted capture hashes and derived contract;
- [ ] reuse executor-accepted identity and existing beat/transition authority;
- [ ] compute phase with the proven scale, quantizer, and per-transition origin;
- [ ] define every reset/continue/snap path, including stop, track/deck change,
  arm correction, refire, buildup/drop hold, reload, stale/error, and shutdown;
- [ ] keep unknown transition classes zero-safe rather than guessing;
- [ ] add pure phase math, StateManager integration, shadow, error, teardown,
  and nonblocking tests;
- [ ] rerun the proof gate and all SoundSwitch/full-suite/docs gates;
- [ ] obtain fresh adversarial review before hardware work.

### RW-9 - Final offline/shadow/adversarial closeout

**Status:** [C] old Task 8 passed for the pre-RW implementation; new changes
must be re-gated.

- [ ] rerun current-project proof after RW-1/RW-2/RW-3/RW-4/RW-5 changes;
- [ ] prove byte-identical repeated replacement exports;
- [ ] mutate current and staged pack artifacts adversarially and prove rejection;
- [ ] run the menubar workflow with a fake/subprocess seam and no AppKit freeze;
- [ ] run scripted event-chain shadow including play/pause/resume/seek/stop,
  master/track transitions, input failure/recovery, static/blackout, reload, and
  disabled/default-off neutrality;
- [ ] after RW-8, add runtime Autoloop phase shadow using the proven contract;
- [ ] perform a fresh high-effort adversarial review by a reviewer who did not
  implement the corresponding task.

### RW-10 - Task 9 hardware handoff and operator gate

**Status:** [U] not executed; handoff must be written/reviewed after software
closeout.

- [ ] Author the exact fixtures-safe hardware handoff; do not execute it during
  authoring/review.
- [ ] Name the sanitized backend/port alias, physical fixture state, zero-frame
  preflight, physical kill method, stop/start/rollback commands, and
  single-process verification.
- [ ] Test order must be safe zero/static -> one scripted track -> DDJ
  press/release -> blackout press/release -> one proven Autoloop -> disconnect
  -> graceful shutdown.
- [ ] Record logs/status/frame/physical pass-fail criteria for each step.
- [ ] Explicitly acknowledge the Enttec last-frame hazard on `kill -9`.
- [ ] Obtain explicit operator approval immediately before any restart, output
  enable, serial/MIDI open, DMX send, or fixture-visible test.
- [ ] Keep status hardware-unvalidated unless a repeatable validation record is
  completed and referenced from `docs/validation/hardware_validation_log.md`.

### RW-11 - Documentation and branch closeout

- [x] This roadmap replaces the stale progress ledger as active status authority.
- [x] Material T7/T8 implementation records are grouped under completed
  SoundSwitch planning history; redundant prompts/handoffs were deleted.
- [ ] Keep the roadmap, active-work registry, research README, subsystem cards,
  architecture, setup docs, matrices, and validation inventories aligned after
  every behavior patch.
- [x] Correct T7d evidence/blocker docs for the 2 arm + 2 refire accepted
  integrity captures and 1 failed arm run.
- [ ] Keep those evidence docs current after every remaining capture and oracle
  pass; never pre-fill results.
- [ ] Merge PR #116 only after the chosen software checkpoint is reviewed and
  gates are current. PR state is coordination metadata, not validation.

## 6. Dependency-ordered roadmap

### Milestone M0 - Documentation authority reset

**This docs-only pass.** No runtime behavior changes.

- [x] verify code/test/project evidence;
- [x] establish this remaining-work authority;
- [x] correct stale routing/status claims;
- [x] remove redundant completed prompts/handoffs from active routing and group
  retained implementation/research history by lifecycle;
- [x] run and record final docs checks/diff review.

### Milestone M1 - One-click exporter workflow

Dependency: M0. Does not depend on T7d or hardware.

1. Opus designs a Part A-E implementation spec for RW-1.
2. Independent review attacks replacement atomicity, failure rollback, menu
   responsiveness, sanitized output, concurrency, and reload/no-enable behavior.
3. Codex implements only the reviewed spec.
4. Run targeted export/menubar/controller tests, proof gate, full suite, and
   docs gates.

### Milestone M2 - Scripted live-runtime contract closure

Dependency: M0; may be designed in parallel with M1 but should land as separate
reviewable commits.

1. Design/spec RW-2, RW-3, RW-4, and RW-5 from existing authority variables.
2. Resolve pause versus stop without a second transport owner.
3. Gate scripted output explicitly by current mode/identity/authority.
4. Integrate input health and expanded status.
5. Run scripted event-chain shadow and adversarial review.

### Milestone M2A - Runtime output shutdown ownership

Dependency: M0. This must land before RW-6 advances beyond default-off, before
any pack-output enablement or hardware work, and before M5.

1. Implement RW-1A without adding blocking work to `_push_tick`.
2. Behaviorally swap to a new fake sender and exercise the SIGTERM shutdown
   path, proving the live sender is zeroed/stopped and stale startup cleanup is
   harmless.
3. Run focused startup/controller/shutdown tests, the full software suite, and
   docs gates before any enablement handoff.

### Milestone M3 - T7d capture evidence

Dependency: current capture tooling; does not require physical direct-DMX
output. Requires operator presence and fixtures-safe confirmation.

1. Resume the active capture handoff at `master-switch`; capture the four
   remaining scenario pairs one scenario at a time.
2. Keep the agent turn alive at physical action gates and poll for evidence.
3. Run the independent oracle and update evidence/blocked docs.
4. Stop without a runtime spec if the result is not
   `PASS_T7D_PHASE_CONTRACT`.

### Milestone M4 - Native-DMX Autoloop integration

Dependency: M3 PASS only.

1. Author/review the evidence-grounded T7d Part A-E spec.
2. Implement proven phase/origin integration and zero-safe transitions.
3. Rerun all proof/shadow/full-suite/docs gates and fresh adversarial review.

### Milestone M5 - Hardware gate and final milestone closeout

Dependencies: M1, M2, M2A, M4, current proof/shadow/review approval, local
config prepared but disabled.

1. Author and review the T9 handoff only.
2. Obtain explicit operator approval for execution.
3. Validate exactly one bridge process, safe physical state, zero preflight,
   scripted path, controls/masks, proven Autoloop, disconnect, and shutdown.
4. Record evidence and update status without overstating compatibility.

## 7. Mandatory invariants for every remaining task

1. `StateManager` remains the only writer of `DeckState`.
2. No filesystem, subprocess, MIDI API, serial, socket, sleep, retry, or
   blocking queue operation enters the 200 Hz push loop. The Enttec latest-frame
   mailbox lock and MIDI-input snapshot lock are the permitted short-held,
   non-blocking in-memory synchronization; neither performs I/O in its critical
   section.
3. Source SoundSwitch projects are read-only and saved bytes are authority.
4. Full rescan identity is exact; never use display-name, fuzzy path, or file
   order as identity.
5. Publish only independently verified packs.
6. Invalid export/reload/startup never partially swaps runtime state and never
   falls back from pack failure to physical MIDI.
7. Direct DMX and physical MIDI-laser output remain mutually exclusive at both
   backend construction and physical port ownership.
8. Automatic output resolves zero on unowned mode, stop/unload, stale/error,
   invalid identity, failed reload, sender failure, disable, and shutdown.
9. Manual Static Override behavior may change only through an explicit reviewed
   policy; emergency/blackout must always win.
10. Reload/export does not implicitly enable output, select a backend, restart
    the bridge, or open hardware.
11. Default-off/absent-config behavior remains byte/order-neutral for existing
    OS2L, MIDI lasers, LEDs/Govee, Rekordbox readers, commands, and logs except
    for explicitly added sanitized observability.
12. No local path, device ID, port, fixture address, project byte, capture, or
    secret is surfaced at runtime. The intentional canonical
    `~/Music/SoundSwitch/...` source/pack constants and tracked example value are
    the only committed operator paths authorized by RW-1.
13. Graceful shutdown sends zero (currently guaranteed only for the
    startup-owned sender; runtime-swapped senders require RW-1A); hard-kill
    safety requires a physical kill path and cannot be claimed in software.
14. Software tests and passive wire captures never become physical fixture
    validation claims.

## 8. Required gates after implementation patches

Run the narrow task tests during development, then before checkpoint:

```bash
cd /Users/bbui
python3.14 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation \
  --project ~/Music/SoundSwitch/default.ssproj \
  --output-dir /tmp/rbss-soundswitch-proof

cd /Users/bbui/rb_ss_bridge_v2
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

Also require Python 3.11 affected-module coverage for startup/dataclass/import
changes because CI uses 3.11 while the local default used in this audit is 3.14.

Hardware-facing tests must use injected fake MIDI/serial/Enttec interfaces until
the separately approved T9 execution gate.

## 9. Document map and lifecycle

### Current authority

- `docs/plans/active/soundswitch_exporter_remaining_work.md` - this active
  completion checklist and task ordering.
- `docs/plans/active/soundswitch_README.md` - grouped project index.
- `docs/research/soundswitch/README.md` - research/format authority routing.
- `docs/research/soundswitch/soundswitch_re_closure_report.md` - bounded RE
  completion verdict; not current implementation status.
- `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md`
  - original product/implementation contract; this roadmap records actual
  landed versus remaining work.
- `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md` and
  `soundswitch_t7d_capture_gate_handoff.md` - current operator-evidence path.
- `docs/validation/soundswitch_t7d_phase_contract_evidence.md` and
  `soundswitch_t7d_phase_contract_blocked.md` - honest current incomplete
  verdict: four integrity-accepted captures cover arm/refire, four scenario
  pairs plus identity/oracle proof remain.

### Completed/superseded planning history

Completed implementation specs/proofs and the old progress ledger belong under
`docs/plans/completed/soundswitch/`. Redundant session handoffs, orchestration
prompts, review packs, and the superseded readiness-review prompt were deleted;
git history remains their provenance. Historical research handoffs/drafts are
grouped under `docs/research/soundswitch/history/`. The active T7d resume prompt
remains active only for the operator capture pass.

## 10. Next task

The next task is an independent implementation review of RW-1. The reviewer
must attack directory replacement/recovery, UI concurrency, fingerprint reload
acknowledgement, sanitization, and no-implicit-enable/no-hardware neutrality.
RW-1 must not be called complete until that review approves the implementation.

Ready-to-send prompt:
the implementing Codex session provides an updated ChatGPT review prompt in its
final response.

Independent roadmap review prompt:
`docs/prompts/reviews/soundswitch_exporter_remaining_work_adversarial_review_prompt.md`.

## When this project can be called complete

Do not call the SoundSwitch exporter / bridge-native DMX project complete until:

- [ ] one-click saved-project export safely replaces one canonical pack and
  provides operator feedback;
- [ ] scripted runtime pause/mode/input-health/status gaps are closed and
  shadow-reviewed;
- [ ] T7d live evidence uniquely proves the active phase contract;
- [ ] native Autoloop direct-DMX integration uses only that proven contract;
- [ ] proof gate, adversarial pack tests, full suite, docs checks, and fresh
  independent reviews pass on the final software checkpoint;
- [ ] the operator-approved hardware sequence is executed and recorded;
- [ ] existing OS2L/MIDI-laser/LED-Govee/Rekordbox behavior is verified
  unchanged outside explicitly enabled pack mode;
- [ ] status remains bounded honestly to the exact evidence collected.
