---
doc_status: current
truth_level: prompt-handoff
last_verified_commit: 36125cc
last_verified_date: 2026-07-13
validation_scope: >
  One-shot diagnosis handoff for SOL 4.6 xhigh — Rekordbox target-patch /
  codesign failure that blocked the RB7216 live-check. Assessment only;
  no re-sign, restore, bridge restart, or live controller work.
---

# SOL one-shot — RB7216 Rekordbox target-patch / codesign failure

**Seat:** SOL 4.6, effort **xhigh**. Verify the pin on screen before you start.
You are the investigator for this blocker. You report evidence; the operator
gates. Do not declare RB7216 live-cleared.

Communicate in AGENTS.md §0 mode: plain language, mechanism kept, evidence class
stated, no status blocks.

## Mission

Diagnose why the Rekordbox target patch (`get-task-allow`) failed on the
maintainer Mac during the RB7216 live-check, and rank safe next options so the
bridge can attach to Rekordbox 7.2.16 memory again.

**Why it matters:** RB7216 software landing is already on `main`. Live validation
stopped because the reader could not attach (`task_for_pid` kern_return=5 /
`reads_blocked`). An operator-requested patch apply then failed inside codesign.
Until attach works, 7.2.16 live parity cannot be proven.

**Deliverable is assessment only.** Do not implement a fix. Do not re-sign or
restore Rekordbox. Do not restart the bridge or resume controller checks.

## Deliverable

Cold-readable assessment for Brandon with:

1. Root-cause class + confidence
2. Whether `/Applications/rekordbox 7/rekordbox.app` is safe to relaunch as-is
3. Ranked safe next actions (one action at a time), with risk
4. What remains unknown
5. Whether RB7216 live-check can resume after a successful patch, or stays
   blocked for other reasons

**Verdict taxonomy:**

- `DIAGNOSIS READY` — enough evidence for Brandon to choose a next action
- `DIAGNOSIS READY WITH GAPS` — actionable, but named unknowns remain
- `NOT READY` — blocked; name the missing evidence

Label every load-bearing claim `confirmed` / `assumed` / `unknown` /
`rejected` with evidence.

Optional write:
`docs/research/sol_rb7216_rekordbox_patch_codesign_failure_2026_07_13.md`
If written, that file only. No other edits. Commit only if Brandon asks.

Completion:

- Print `RB7216-PATCH-DIAG-DONE` on its own line when finished
- Or `RB7216-PATCH-DIAG-BLOCKED` if stopped
- Machine signal:
  `touch /tmp/rbss_lane_signals/sol.RB7216PATCHDIAG.done`
  or
  `echo "<one-line reason>" > /tmp/rbss_lane_signals/sol.RB7216PATCHDIAG.blocked`

## Evidence packet (verify; do not rediscover from scratch)

Repo: `/Users/bbui/rb_ss_bridge_v2` on `main`  
Live-check start HEAD: `36125cc27f94fcbd1370e78c7eb6cb92dce21c7d`  
Re-check `git rev-parse HEAD` and `git status --short` first.

### Live-check sequence (2026-07-13)

Confirmed:

- Operator confirmed Rekordbox `7.2.16.0342`, then menubar-restarted the bridge.
- One main process: `Python -m rb_ss_bridge_v2` pid `64028`.
  Note: `pgrep -f rb_ss_bridge_v2` also matches pads/menubar/watcher/frame-engine
  on this machine — do not treat that raw count as the single-process invariant.
- `/tmp/bridge.log` was current and showed:
  - `attach failed; direct events unavailable`
  - repeated `task_for_pid(...) failed kern_return=5` / `reads_blocked` from
    RBMEM and LBPM
  - secondary noise: SoundSwitch refused, SS-MIDI port gone, Enttec serial missing
- No successful `7.2.16` attach observed.
- Live lane stopped with `/tmp/rbss_lane_signals/cursor.RB7216LIVE.blocked`

### Patch sequence

Confirmed:

- `--check` before apply: `/Applications/rekordbox 7/rekordbox.app`,
  `get-task-allow present: NO`
- Rekordbox was quit.
- Applied with:
  `printf 'YES\n' | PYTHONPATH=.. python3 -m rb_ss_bridge_v2.rekordbox_patch --apply --admin`
- Failure: codesign `internal error in Code Signing subsystem` in subcomponent
  `.../Contents/MacOS/libssl.3.dylib`
- Auto-restore reported failed; backup remains at
  `~/Library/Application Support/RBSS Rekordbox Backups/backup_vxdj11uy`
- After failure: `get-task-allow` still NO; live app
  `codesign --verify --deep --strict` OK; backup verify OK; app still shows
  Pioneer TeamIdentifier `6BRHGXQ6VU` without get-task-allow.

### Read first

- `AGENTS.md`
- `rekordbox_patch.py` (`codesign_argv`, `apply_patch`, restore path, GUI/CLI)
- `tests/test_rekordbox_patch.py`
- `usb_launcher.py` `--patch-rekordbox`
- `scripts/bridge_menubar.py` `enableRekordboxReads_` and current `MENU_BLUEPRINT`
  (everyday patch item appears removed)
- `docs/setup/usb_launcher_runbook.md` notes on target patch vs caller authorization
- reader attach path in `rb_memory.py` / `rb_state_reader.py` only as needed for
  `kern_return=5` meaning

## Boundaries

Allowed, read-only only:

- inspect named files/tests/docs above
- `rekordbox_patch --check` / `--dry-run`
- `codesign -d` / `--verify` on the live app and backup
- process list / log tail
- optional research doc write

Forbidden:

- any `--apply`, `codesign --force`, restore overwrite of `/Applications/rekordbox*`
- any bridge start/stop/kill/restart
- any Rekordbox launch/quit
- any bridge code/config/test edits beyond the optional research doc
- claiming RB7216 is live-cleared
- writing/implementing a fix unless Brandon asks for a later fix-spec

If the app is now broken, the patch is already present, or the version is not
7.2.16: stop, write the blocked signal with one line of evidence, and wait.

## Questions to settle

1. What class of failure is the `libssl.3.dylib` codesign error?
2. Is the current app safe to relaunch?
3. Was the failed apply a no-op or a partial signature change?
4. Is missing get-task-allow after the 7.2.16 update expected revert?
5. Is the current `--deep` ad-hoc strategy still appropriate for this bundle?
6. Rank safe operator options: retry once / alternate known procedure / restore
   backup / reinstall then re-patch / stop live-check.
7. Separate target patch from caller authorization / SIP debugging restrictions
   on this Mac.
8. Is the missing menubar patch item intentional drift or an operator blocker?

Do not pause for acknowledgment unless genuinely blocked.
