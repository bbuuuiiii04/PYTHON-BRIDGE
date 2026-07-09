---
doc_status: current
truth_level: spec
last_verified_commit: 9ead100
last_verified_date: 2026-07-09
validation_scope: >
  Milestone-1-only Codex implementation spec for the USB bridge launcher
  (usb_bridge_launcher_design.md §7.1): prove the bundle. Authored during the 2026-07-09
  paper phase. NOT implementation-authorizing: the build starts only when the executive
  opens the gate (F2/F4 landed + operator live-tuning, phantom-load leak fix, Codex routing
  decision). All repo claims verified at 9ead100; PyInstaller-behavior claims are external
  and labelled assumed. Milestones 2-4 are deliberately unspecced.
work_status: authored, parked-on-gate — hand to Codex only on explicit executive/operator dispatch
relates_to: usb_bridge_launcher_design.md, usb_bridge_launcher_fable_review.md
---

# Codex Implementation Spec — USB Bridge Launcher, Milestone 1 (prove the bundle)

**Recommended Codex effort: high.** Read `usb_bridge_launcher_design.md` (the design this
executes) before starting. This spec is valid under EITHER answer to the open operator
decision "Guest-first / defer permanent mode" (design §1) — M1 builds and proves the bundle
on the operator's own Mac and touches neither install mode.

## Part A — Context & Root Cause (verified; read, do not implement)

Goal: a PyInstaller `.app` that runs the FULL bridge with no host Python, launched from a
DMG on the stick, proven on the operator's own Mac against the §2 parity bar of the design.
M1 kills the biggest unknowns for $0: does it package, does the PyObjC menubar survive
freezing, does `--run-bridge` behave identically to a watcher run, does the frame-engine
child spawn frozen, do memory reads still work.

Verified current state (all [confirmed] at `9ead100` unless labelled):
- The bridge runs source-only: watcher → `/opt/homebrew/bin/python3 -m rb_ss_bridge_v2`
  from the repo's PARENT dir (`scripts/ss_bridge_watcher.sh:17,19,137,169`). Python 3.14.6.
- ONE launch-profile env set, shared by auto+manual modes, lives inline in `start_bridge()`
  (`ss_bridge_watcher.sh:147-169`) — the exact set is reproduced in design §2(a). Any bundle
  must reproduce it exactly; today it exists only as that hand-maintained shell block.
- Single-instance flock: `/tmp/rb_ss_bridge_v2.lock`, `__main__.py:614-629`, refusal in
  `main()` `:930-933`. Command-line-agnostic — holds across source-run + bundled mixes.
- Process discovery is source-run-anchored everywhere: watcher `bridge_pids()`
  (`ss_bridge_watcher.sh:103-105`), menubar patterns (`scripts/bridge_menubar.py:35-38`),
  stop/start `toggleBridge_` (`:1146-1163`). A frozen binary is invisible to all of them.
- Frame-engine child [confirmed, the M1-critical new fact]:
  `govee_frame_engine_client.py:454-461` spawns
  `subprocess.Popen([sys.executable, "-m", "rb_ss_bridge_v2.govee_frame_engine", "--fd", N],
  pass_fds=(fd,), cwd=<package parent>)`. NO `sys.frozen` handling exists. Under PyInstaller,
  `sys.executable` is the frozen app binary — this spawn breaks unfixed, and realtime LED
  output depends on the child.
- Dependency manifest gap [confirmed]: `pyproject.toml` omits `python-elgato-streamdeck`
  (+`hidapi`), `Pillow`, `python-rtmidi`, `pyserial` — all imported by runtime code.
  PyInstaller static analysis needs explicit help for these.
- Memory reader: `task_for_pid` + `mach_vm_read_overwrite` (`rb_memory.py:58-70`);
  code-signing state can change `task_for_pid` behavior [external, assumed].
- PyInstaller is NOT installed [confirmed]; PyInstaller-vs-3.14 support is [unknown] — Task 0.
- Contract coverage [confirmed]: `scripts/ss_bridge_watcher.sh` → `logging_visibility` +
  `bridge_menubar`; `govee_frame_engine_client.py` → `led_govee`; NEW launcher files → no
  contract exists yet (Task 1 fixes this FIRST, per AGENTS.md §7).

## Part B — Tasks (implement exactly, in order; commit after each with explicit paths)

### Absolute Rules
- **Gate:** do not start any task until the executive/operator explicitly dispatches this
  spec. Paper phase ends at dispatch, not before.
- Out of scope: temporary/permanent install flows, End Set, `StartOnMount`, uninstall
  (M2/M3); foreign-Mac anything (M4); the memory-read authorization mechanism (separate
  reader spec — see the STOP rule in Task 7); `track_identity_move_invariance_design.md`
  (separate lane); every overnight-program file (`state_manager.py` behavior,
  `drop_presentation.py`, `govee_frame_renderer.py`, reader files, laser files) except the
  two surgical touches named in Tasks 3-4.
- Behavior that must not change: source-run dev workflow (watcher, menubar, manual mode)
  stays byte-identical in behavior; the frame-engine child's socketpair protocol and
  non-frozen spawn path unchanged; no new I/O on the 200 Hz push loop; no test edits to make
  docs pass.
- Error handling: fail closed and SURFACE (log + visible menubar state); no broad
  try/except, no silent fallbacks, no success-shaped degradation. A lock refusal must be
  shown ("bridge already running"), never swallowed.
- Git: work on `main`, explicit-path commits only, never `git clean`, never revert
  unrelated dirty files (parallel lanes may be writing).

### Task 0 — Build-environment gate (resolve before any code)
Determine a (Python, PyInstaller) pair: try current 3.14 first; if PyInstaller lacks 3.14
support, provision a python.org arm64 3.12/3.13 build interpreter [design §3.1 F9] and
verify `python3 -m unittest discover tests` passes on it (record the baseline count; known
reds are documented in the registry). **STOP conditions:** no PyInstaller release supports
any interpreter the suite passes on; or the suite regresses on the build interpreter beyond
the known baseline. Record the chosen pair in the runbook stub (Task 6).

### Task 1 — `docs/agents/change_contracts.yml`: add the `usb_launcher` contract (docs-first)
New contract entry BEFORE code exists: `code_globs`: `usb_launcher.py`, `launch_profile.py`,
`packaging/rbss_launcher.spec`, `packaging/*.plist` (adjust to the exact files Tasks 2-5
create); `tests`: the new unit tests from Part D + the three hard checks; `docs_update`:
`docs/plans/active/usb_bridge_launcher_design.md`, `docs/status/active_work_registry.md`,
`docs/setup/usb_launcher_runbook.md` (created in Task 6), `docs/validation/software_test_inventory.md`.
Run `python3 tools/check_agent_contracts.py` (it must pass — if it requires files to exist,
land this task's yml edit in the same commit as Task 2's skeleton files).

### Task 2 — `launch_profile.py` (new, repo root): the single launch-profile source
One flat module: `BRIDGE_ENV: dict[str, str]` holding exactly the design §2(a) set (the 19
`RBSS_*` flags with their values — copy from `ss_bridge_watcher.sh:147-169` at implementation
time, NOT from any doc; code wins), plus pure helpers `bridge_env(laser_config_path,
extra=None) -> dict` and `bridge_argv(python_exe) -> list[str]`. No I/O, no side effects —
pure data + functions (the test seam). Then rewrite the watcher's `exec env` block to read
it: replace the inline flag list in `start_bridge()` with
`exec env $(python3 - <<'PY' ... print shell-quoted VAR=VAL pairs from launch_profile ... PY) "$PYTHON" -m rb_ss_bridge_v2`
— or an equivalent single-source mechanism of your choosing, PROVIDED the watcher and the
bundle both consume `launch_profile.py` and a test asserts the watcher script references it.
Contracts triggered: `logging_visibility` + `bridge_menubar` (watcher edit) — update their
`docs_update` lists in the same commit.

### Task 3 — `usb_launcher.py` (new, repo root): the bundle entrypoint
Single dispatch `main(argv)`:
- `--run-frame-engine --fd N` → exec `rb_ss_bridge_v2.govee_frame_engine` main with that fd
  (MUST be dispatched before any AppKit import — the child is headless).
- `--run-bridge` → apply `launch_profile.bridge_env(...)` to `os.environ`, then call the
  bridge's `main()` in-process (import `rb_ss_bridge_v2.__main__`) — no re-spawn, no shell.
- `--run-streamdeck` → run `streamdeck/streamdeck_midi.py`'s main (its singleton lock
  `:69` already guards doubles).
- no args → menubar: run `scripts/bridge_menubar.py`'s main, extended minimally so that in
  frozen mode it starts/stops the bridge via its OWN child pid (spawn
  `sys.executable --run-bridge`, keep the Popen handle) instead of pkill patterns
  [design §3.2 requirement 2]. Do NOT change unfrozen menubar behavior — branch on
  `getattr(sys, "frozen", False)` only.
The binary/app executable name must contain `rb_ss_bridge_v2` [design §3.2 requirement 1].
Wait-for-Rekordbox/SoundSwitch watch logic: port the minimal adopt/backoff loop from the
watcher for frozen mode only, or document explicitly in the runbook that M1 frozen mode is
launch-on-click without auto-restart — either is acceptable for M1, SAY WHICH in the
runbook (M2 finalizes lifecycle).

### Task 4 — `govee_frame_engine_client.py`: frozen-aware child spawn (surgical)
In `_default_spawn` (`:454-461`): when `getattr(sys, "frozen", False)`, build argv as
`[sys.executable, "--run-frame-engine", "--fd", str(child_fd)]` and drop the `cwd=` pin
(meaningless in a bundle); when not frozen, the existing argv and cwd stay BYTE-IDENTICAL.
Extract argv construction into a pure function `_child_argv(frozen: bool, fd: int) ->
list[str]` (the test seam). Socketpair creation, `pass_fds`, stdout/stderr handling, and
lifecycle are unchanged. Contract: `led_govee` — update its `docs_update` list.

### Task 5 — `packaging/`: PyInstaller spec + signing + DMG
- `packaging/rbss_launcher.spec` [PyInstaller specifics: assumed — verify against the
  installed version's docs at build time]: onedir, windowed/.app BUNDLE, entry
  `usb_launcher.py`; `hiddenimports` at minimum: `StreamDeck`, `PIL`, `rtmidi`, `serial`,
  `zeroconf._utils.ipaddress`-style dynamic modules as discovered, `pyrekordbox` (+ its
  data files via `collect_data_files`); `datas`: `config/*.example.json`, the canonical
  pack dir `local/soundswitch/rbss_canonical_pack/` if present at build time [decide at
  build: pack assets may ride the stick outside the app instead — record the choice].
  Info.plist: `CFBundleIdentifier` (stable), `LSUIElement` true (menubar app),
  `NSLocalNetworkUsageDescription` (required for zeroconf/Govee-LAN on Sequoia+ even on the
  operator's Mac).
- Ad-hoc sign: `codesign --force --deep -s - "dist/RBSS Bridge.app"` [assumed adequate for
  local run; idea-8 cert experiment is OPERATOR-GATED — build it only if the operator
  adopts idea 8, as a separate flagged commit].
- DMG: `hdiutil create -volname "RBSS Bridge" -srcfolder "dist/RBSS Bridge.app" -ov
  -format UDZO "dist/RBSS Bridge.dmg"` — the DMG ships on the exFAT stick; NEVER a raw
  `.app` or Finder-zip on exFAT (design §3.1 F1, symlink seal).
- Build artifacts (`build/`, `dist/`, any staged venv) are gitignored — commit only the
  spec/plist sources.

### Task 6 — `docs/setup/usb_launcher_runbook.md` (new): M1 runbook stub
Record: chosen build interpreter + PyInstaller version (Task 0); build + sign + DMG
commands; the frozen-mode lifecycle choice from Task 3; the §2 parity checklist as a
fill-in table; the coexistence warning (quit the dev watcher/menubar before a bundled
launch — the flock will refuse, the launcher must show it); the two dev-only watcher
features deliberately absent (truth-check env, WATCHER_NO_LOOP).

### Task 7 — Operator-gated verification run (do NOT perform unattended)
Software checks first (Part D), then hand the operator a plain-language checklist and STOP:
bundled run on the operator's Mac against a TEST session (never a live show): SoundSwitch
rotation, MIDI look-selection, laser output, LED/Govee frames (frame-engine child alive —
two processes, the anchored count still reads ONE bridge), Stream Deck, memory reads.
**Memory-read STOP rule (verbatim from the design): if the bundled bridge's memory reads
behave differently from a source-run bridge, STOP and report — do not improvise
entitlements or new authorization mechanics (separate reader spec's scope).**

## Part C — Invariants That MUST Still Hold (live safety)

- The source-run dev workflow is untouched: a watcher launched today behaves identically
  after Task 2 (same env set, same order, same laser-config force-enable, same Govee
  sourcing, same Stream Deck lifecycle, same monitor).
- Exactly-one-bridge: the flock invariant stands; frozen-mode control is owned-child-pid +
  flock + status liveness, never pattern-matching; anchored `…rb_ss_bridge_v2$` counting
  semantics unchanged (the frame-engine child must not be counted as a bridge).
- The 200 Hz push loop gains no blocking I/O, imports, or new work — the launcher only
  wraps process startup.
- Frame-engine: non-frozen spawn byte-identical; child dies with parent; socketpair
  protocol untouched.
- No secrets in the bundle or the repo: `govee.env`, live configs, device IDs stay out of
  `packaging/` and out of git (existing rules).
- Docs-only files this spec creates must not change runtime behavior.

## Part D — Tests (pure seams; no build, no hardware)

- `tests/test_launch_profile.py`: BRIDGE_ENV matches the design §2(a) set exactly (names +
  values, including `RBSS_LED_TRANSPORT_COOLDOWN=0` and the ABSENCE of
  `RBSS_LED_TRANSPORT_STICKY`); `bridge_env()` merge semantics; a grep-level assertion that
  `scripts/ss_bridge_watcher.sh` references `launch_profile` (single-source proof).
- `tests/test_usb_launcher.py`: `main()` arg dispatch is pure-testable (monkeypatched
  targets): `--run-frame-engine` dispatches before AppKit import; `--run-bridge` applies
  the profile env; unknown args fail closed with a nonzero exit.
- `tests/test_govee_frame_engine_client.py` (extend existing coverage): `_child_argv(False,
  fd)` equals today's argv exactly; `_child_argv(True, fd)` equals the frozen form; spawn
  path selects by `sys.frozen`.
- Existing suites stay at baseline: `python3 -m unittest tests.test_bridge_menubar` (the
  `bridge_menubar` contract's named test) and full
  `python3 -m unittest discover tests` (record the known-reds baseline before starting).

## Part E — Acceptance (definition of done)

- [ ] Tasks 0-6 committed in order, explicit paths, one logical change per commit.
- [ ] `usb_launcher` contract added; `logging_visibility`, `bridge_menubar`, `led_govee`
      docs_update lists satisfied for the files actually touched.
- [ ] Hard checks green: `python3 tools/check_docs_metadata.py`,
      `check_agent_contracts.py`, `check_docs_drift.py`.
- [ ] Full suite at or above the recorded baseline on BOTH the dev interpreter and the
      Task-0 build interpreter.
- [ ] A `.app` builds, ad-hoc signs, and a DMG is produced on the operator's Mac
      (build evidence: command transcripts in the runbook).
- [ ] Task 7 checklist delivered to the operator; NO live/parity claims made by Codex —
      status language stays `implemented` / `software-tested`; the parity bar is the
      OPERATOR's gate to close.
- [ ] Registry row updated (design doc + this spec status), doc_index untouched unless a
      new doc was added (the runbook — add its row).

## When You Finish

Report: changed files; tests/checks run with counts; the Task-0 interpreter decision; which
frozen-lifecycle option Task 3 took; any STOP condition hit. Then a plain-language operator
summary: what double-clicking the DMG app does now, what is deliberately NOT built yet
(install modes, foreign-Mac), the one warning (quit the dev watcher first), and exactly
what the operator must check in the Task-7 run before anyone calls the bundle working.
Evidence class: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED until the operator's
parity run passes.

## Adversarial self-review (spec author, 2026-07-09)

Concrete failure scenario attacked: *Task 2 silently changes the live launch env* — the
watcher rewrite drops or reorders a flag and every future live set runs a subtly different
bridge. Prevention: the env set is copied from code (not docs) at implementation time, the
`test_launch_profile.py` equality test pins names AND values including the two 2026-07-09
deltas (STICKY absent, COOLDOWN=0), and Part C makes watcher-behavior identity an invariant
Codex must verify, not assume. Second attack: *frozen menubar kills the wrong process* —
prevented by banning pattern-based control in frozen mode (owned-pid only, Part B Task 3 /
Part C). Third attack: *the spec authorizes implementation prematurely* — prevented by the
gate rule at the top of Part B and the work_status header; possession of this spec is not
dispatch.
