---
doc_status: current
truth_level: implementation-spec
last_verified_commit: 33c3bb9
last_verified_date: 2026-07-09
validation_scope: >
  Codex implementation spec for USB launcher M2 — the operator's 2026-07-09 product
  directive (one-action install, automated payload, home-parity, survive-unplug,
  menubar PURGE with confirmation). Authored same evening under the superman4
  SPEC-TONIGHT-BANK-FOR-JUL-11 ruling; executes in the Jul-11 Codex window after the
  executive re-verifies file:line cites at then-HEAD (same-day drift bit this
  workstream twice). Directive source:
  docs/plans/active/usb_launcher_m2_operator_directive_2026_07_09.md. AWR-186.
---

# Codex Implementation Spec — USB Launcher M2: native install / payload / PURGE

## Part A — Context & Root Cause (verified; read, do not implement)

- The operator's directive (verbatim in the capture doc above) requires: plug stick →
  open → installs itself → bridge runs exactly like the home Mac → survives unplug →
  removable ONLY via a menubar PURGE with explicit confirmation. R5 of the directive
  (read the stick inside an XDJ-RX3) is settled IMPOSSIBLE (AWR-167) and is OUT of
  this spec.
- Today (M1 + the AWR-122 interim): the DMG carries app only; `packaging/stick/
  install.command` installs app + `RBSS_payload/spectral_cache` with a file-level
  manifest at `~/Library/Application Support/RBSS Bridge/install_manifest.txt`, and
  `purge.command` removes exactly manifest paths after a typed confirmation
  [confirmed — built, tested 4/4, desk-smoked 2026-07-09 evening].
- The frozen bundle carries ONLY `config/*.example.json` — never live configs or
  `govee.env` (`packaging/rbss_launcher.spec:39-43` [confirmed]). The bundle reads
  `govee.env` from `~/Library/Application Support/RBSS Bridge/govee.env`
  (`usb_launcher.py:31` [confirmed]) — so "performs JUST LIKE my current macbook"
  fails on a foreign Mac today for Govee-cloud and any live-config-dependent
  behavior (laser director config etc.).
- `usb_launcher._run_bridge` honors an `RBSS_LASER_CONFIG` env override and
  otherwise points at the bundle-internal `config/laser_director.json`
  (`usb_launcher.py:90-92` [confirmed]) — the bundle-internal path only carries the
  example config.
- `local/state/*` stores (LED identity default `local/state/led_identity_v2.json`,
  `led_config.py:1337` [confirmed]) resolve **cwd-relative**; a double-clicked app's
  cwd is not the repo parent, so frozen runs likely cannot persist them
  [assumed — flagged in the design D1 drift notes; Task 0 verifies].
- TCC permission grants key to the app's code signature; ad-hoc rebuilds re-prompt
  (design §5 [confirmed in design]); an Apple Development identity fixes stability
  when the operator mints the cert (`packaging/sign.sh` auto-upgrades, re-runnable
  [confirmed]).
- **Security line (mandated, operator default YES with veto open — do not
  re-litigate):** with secrets riding the stick/DMG, a lost or borrowed stick
  exposes the operator's `GOVEE_API_KEY` and venue configs to whoever holds it;
  PURGE removes them from the Mac but never from the stick itself.

## Part B — Tasks (implement exactly, in order; one commit per task)

### Absolute Rules
- OUT of scope: XDJ link reading (R5, AWR-167), LaunchAgent / `StartOnMount` /
  auto-start (M3), `state_manager.py`, `led_dispatch_policy.py`,
  `govee_frame_renderer.py`, `lighting_moments_v2.py`, all laser/reader runtime
  files EXCEPT the exact seams named in Tasks 2-3. The push loop gains nothing.
- Behavior that must not change: source-run (watcher) behavior byte-identical when
  the new App-Support overrides are absent; scripted/autoloop/laser/LED runtime
  logic untouched; `launch_profile` env set unchanged except the named additions.
- Error handling: fail closed with a plain-language dialog/log line; no broad
  try/except, no success-shaped fallbacks, no silent early returns. A failed
  install step reports WHICH step and leaves the manifest accurate (list only what
  was actually created).
- Dirty worktree: never revert files you did not change; no destructive git; commit
  by explicit paths only.

### Task 0 — Verify-first inventory (read-only; block if reality diverges)
Re-verify at then-HEAD and record in the task commit message: (a) every file:line
cite in Part A; (b) the full set of live-config read points the bridge uses at
runtime (`config.py` laser/LED/JSON loads; expected: `config/laser_director.json`,
`config/led_look_director.json`, others found by grep) [unknown — enumerate]; (c)
where `local/state/*` writes land in a frozen double-click run [assumed above];
(d) that `install_manifest.txt` format (one absolute path per line) is unchanged.

### Task 1 — `packaging/make_stick.sh` (new): one-command stick builder (operator side)
Stages and ships everything in one run, from repo root:
1. PyInstaller build + `packaging/sign.sh` + DMG — reuse the runbook's exact
   commands; build FROM a staging dir so the DMG carries `RBSS Bridge.app` AND
   `RBSS_payload/` (spectral_cache copy + configs bundle per Task 2 layout).
2. Payload staging: `~/Library/Application Support/RBSS Bridge/spectral_cache` →
   staging `RBSS_payload/spectral_cache`; live configs + `govee.env` → staging
   `RBSS_payload/home/` (exact file list from Task 0's inventory; secrets default
   YES per the operator — gate each copy on file existence, fail closed on
   unreadable).
3. Copy DMG + `packaging/stick/*.command` to the stick mount given as `$1`;
   refuse (plain message) if `$1` is not a mounted volume with `PIONEER/` present.
4. NEVER stage into the repo tree; staging dir under `mktemp -d`. Print a final
   summary: DMG size, payload entry count, stick free space.

### Task 2 — Native in-app install (menubar, guest flow)
`scripts/bridge_menubar.py` (+ a new pure helper module `install_controller.py`):
- Detection [pure fn]: app running from a read-only/DMG location (bundle path under
  `/Volumes/` or app-translocation path) AND no manifest present → menubar shows
  **"Install on this Mac…"** as the primary item (everything else still works).
- Install action (NSAlert: "Install RBSS Bridge on this Mac?" / Install / Cancel):
  copy the app bundle → `~/Applications/RBSS Bridge.app`; install
  `RBSS_payload/spectral_cache` (sibling of the running app inside the mounted
  DMG) → App Support `spectral_cache`; install `RBSS_payload/home/*` →
  App Support (incl. `govee.env`); write the SAME file-level
  `install_manifest.txt` the interim uses (superset: app path + every installed
  file) so `purge.command` and native PURGE stay interoperable; then relaunch from
  `~/Applications` and offer to eject the DMG. Partial failure: report the exact
  step, keep manifest accurate.
- Config wiring: extend `launch_profile.bridge_env()` so that when
  App Support copies exist they win: `RBSS_LASER_CONFIG` → App Support
  `laser_director.json` (mechanism exists, `usb_launcher.py:90-92`), and the
  equivalent override for each live-config read point Task 0 enumerated — reuse
  each subsystem's EXISTING override/env seam; add a new env only where none
  exists, named `RBSS_<subsystem>_CONFIG`, resolved in `config.py` beside its
  current default [exact wiring per Task 0's inventory; do not invent parallel
  resolution logic].

### Task 3 — Frozen-run state dir (the "performs JUST LIKE" gap for learned stores)
Per Task 0(c): point `local/state/*` resolution, IN FROZEN RUNS ONLY
(`getattr(sys, "frozen", False)` — the same gate `scripts/bridge_menubar.py`
already uses [confirmed in inventory row]), at
`~/Library/Application Support/RBSS Bridge/state/`. Source runs stay byte-identical
(cwd-relative, existing stores untouched). Pure resolution fn + tests.

### Task 4 — Menubar PURGE (the operator's exact ask)
- Menubar item **"Purge RBSS Bridge…"** (present on installed copies only —
  manifest exists): NSAlert with explicit **Purge** button + Cancel, message
  states exactly what is removed. On confirm:
  1. Stop the owned bridge child by handle + flock (never pkill/pattern — M1 rule).
  2. Remove manifest paths (same allowlist discipline as the interim: under
     `~/Applications` or App Support only, reject `..`), then the whole
     `~/Library/Application Support/RBSS Bridge/` dir (configs/secrets/caches/state
     it installed or created), then `~/Library/Logs/rb_ss_bridge/`.
  3. Move its own `~/Applications/RBSS Bridge.app` to Trash
     (`NSWorkspace.recycleURLs`) and terminate [assumed mechanism — Codex verifies
     the running-bundle-to-Trash behavior on macOS; if blocked, fall back to a
     detached remover process and document it].
  4. Report what remains, honestly: System Settings permission entries (macOS
     keeps those; inert).
- PURGE never touches the stick, the DMG, other volumes, or anything outside the
  three roots above.

### Task 5 — Runbook + contract closure
Update `docs/setup/usb_launcher_runbook.md` (install/PURGE flows replace the
"interim" framing; `make_stick.sh` becomes the build path; parity table gains
install→run→purge rows), `docs/plans/active/usb_bridge_launcher_design.md` §3.3/§4
(implemented-now notes), the directive capture doc (mark R1-R4/R6 implemented),
`docs/validation/software_test_inventory.md`, registry AWR-186 row.

## Part C — Invariants That MUST Still Hold (live safety)
- The bridge process is started only by an operator action (menubar click); install
  NEVER auto-starts the bridge; PURGE stops the owned child before removing files.
- One bridge: the flock (`/tmp/rb_ss_bridge_v2.lock`) discipline unchanged; after
  any bridge start exactly one bridge process (+ frame-engine child).
- The 200 Hz push loop gains no filesystem/network/subprocess work; all install/
  purge work runs on the menubar side, never inside the bridge runtime.
- Secrets: `govee.env`/live configs are payload files only — never committed, never
  logged in full, never staged inside the repo tree; `.gitignore` coverage verified
  in Task 1.
- Masks/emergency/blackout precedence and all scripted/autoloop behavior untouched.
- Fail open beats fail dark: a failed INSTALL leaves the DMG-run app fully usable;
  a failed PURGE step reports and continues to the next removable item, never
  leaves the Mac in a half-broken hidden state silently.

## Part D — Tests
- `install_controller.py` pure seams: DMG-location detection (path cases), payload
  discovery (sibling `RBSS_payload`), manifest writing (file-level, exact-paths),
  config-override resolution (App Support present/absent → env map), frozen state-dir
  resolution (Task 3). No hdiutil/subprocess in unit tests.
- PURGE scoping: extend the `tests/test_stick_commands.py` pattern — allowlist,
  `..` rejection, manifest-exactness, plus the three-root removal order — against
  the pure helper (UI action stays a thin wrapper).
- `make_stick.sh`: `bash -n` + a layout test on a temp staging dir (no PyInstaller
  in tests).
- Scoped suites to run green: `tests.test_usb_launcher`, `tests.test_launch_profile`,
  `tests.test_launch_agent_plist`, `tests.test_stick_commands`,
  `tests.test_bridge_menubar`, new test files; full-suite reconcile BY NAME against
  the current certified environmental-red baseline at the executive's desk.

## Part E — Acceptance (definition of done)
- [ ] Task 0 inventory recorded; any Part A divergence BLOCKED loudly, not patched
      around.
- [ ] All tasks landed, one commit each, explicit paths.
- [ ] Contract `usb_launcher` (`docs/agents/change_contracts.yml`) satisfied:
      every `docs_update` doc updated; `python3 tools/check_docs_metadata.py`,
      `check_agent_contracts.py`, `check_docs_drift.py` green; new files added to
      the contract's `code_globs` FIRST (contract-first rule).
- [ ] Part D tests green; suite baseline reconciled by name.
- [ ] Status language: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED everywhere;
      the operator walkthrough (install → parity table → PURGE on a test Mac/user)
      is the remaining gate and stays operator-owned.
- [ ] Secrets: zero secrets in any commit (grep `GOVEE_API_KEY` in the diff), zero
      staging inside the repo.

## When You Finish
Report: changed files; per-task commits; tests/checks run with counts and red
names; the Task 0 inventory table; what the operator must do (mint cert →
`sign.sh` re-run for stable permissions; run `make_stick.sh <mount>`; the
walkthrough). Plain-language operator summary: what double-clicking does now on a
fresh Mac, what PURGE removes and what it cannot (System Settings entries), that
install never starts the bridge by itself, and that everything remains
hardware-unvalidated until his walkthrough.
