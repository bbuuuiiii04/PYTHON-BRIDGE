---
doc_status: completed-spec
truth_level: historical-implementation-spec
last_verified_commit: 9095cef
last_verified_date: 2026-06-23
validation_scope: implemented RW-1 post-review fix spec; historical evidence only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — RW-1 `Export from SS` review fixes

> **Scope:** three small, additive corrections to the just-landed RW-1 feature,
> found by independent review of `88a9815..9095cef`. This spec does NOT change the
> swap/lock primitives, `export_pack`, the runtime command surface, the status
> schema, or anything in `StateManager`/push-loop/OS2L/lasers/LEDs/readers. It
> only makes the menubar reload-ack **more conservative** and makes orphan-backup
> recovery **refuse non-directory backups**.
>
> **Accepted status stays:** SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
> Nothing here opens MIDI/serial/Enttec/DMX, enables output, changes the backend,
> or starts/restarts the bridge.

## Operator decision locked for this spec (2026-06-23)

**Stale/unknown bridge state must NOT trigger a blind reload.** When the bridge
process is alive but its status snapshot is not fresh, we cannot confirm whether
pack output is enabled. The conservative, honest behavior is: do **not** append a
reload command, and report "saved — live reload not confirmed." Real-world
consequence: if the operator clicks **Export from SS** while the bridge is
momentarily unresponsive (status >3 s old), the lights will not be hot-swapped
and the menubar will say it could not confirm live — the operator clicks again
once the bridge is responsive. This trades one possible re-click for never firing
a runtime command at an unknown live state. (During a healthy live show the
snapshot is fresh, so the normal reload path is unaffected.)

---

## Part A — Context & root cause (verified; read, do not implement)

All three issues were surfaced by a GPT reviewer ("Bridge") and independently
re-verified against current code at `9095cef`, with two reproduced live.

### A1. Claim 1 — menubar sends a reload on a stale/unknown snapshot  [confirmed — reproduced]

`scripts/bridge_menubar.py:702` suppresses the reload only for `not bridge_pids()`
or `evaluate_reload_ack(...) == "not_live"`. But `evaluate_reload_ack`
(`scripts/bridge_menubar.py:248-256`) returns `"stale"` (not `"not_live"`) for a
missing/old snapshot. So when the bridge process is alive but its status is
stale, control falls through to `append_command({"cmd":"set_soundswitch_pack",
"action":"reload"})` at `scripts/bridge_menubar.py:706`.

Reproduced (`_run_export` with `bridge_pids()==["123"]` and a stale status):
`append_command` was called with the reload command; final state `reload_failed`.

Severity is bounded — the reload is architecturally safe (`_reload` in
`soundswitch_pack_controller.py` is no-implicit-enable; it runs off the 200 Hz
push loop) — but it is a contract/intent deviation: the design (`docs/plans/active/
soundswitch_rw1_export_from_ss_spec.md` §A4) is "if bridge off OR pack not enabled
→ no reload," and a stale snapshot is "enabled-state unknown," which today is
treated as "go ahead."

### A2. Claim 2 — reload-ack can confirm off a pre-existing sha  [confirmed mechanism; benign]

There is no `written_at` freshness bound *after* `append_command`, so the first
poll iteration (`scripts/bridge_menubar.py:708-712`) can match a pre-existing
`pack_sha12` and report `reload_succeeded`. The **only** case where the sha
pre-matches is an identical-content re-export, where the live pack already serves
exactly the exported content — so "live now" is truthful, not false (matches the
RW-1 spec's accepted limitation §9). The residual is cosmetic: a redundant no-op
reload is appended in that case. This spec removes the redundant reload as a
by-product of the Claim 1 fix; **no behavior change is needed for changed
content**, which already waits correctly for the real sha flip.

### A3. Claim 3 — `_recover_orphan_backup` can promote a non-directory backup  [confirmed — reproduced]

`tools/export_soundswitch_pack.py:148` does `os.replace(backups[0], destination)`
with **no type check** on `backups[0]`. The newest-by-mtime `.{name}.bak-*` entry
— whatever its type — is moved into the canonical pack location when the
destination is missing. The destination guard at `:145` only inspects the
*destination* (absent at that point); the post-move guard at `:151`
(`is_dir() and not is_symlink()`) then silently skips cleanup once the destination
is a symlink.

Reproduced (symlink `.pack.bak-zzz` with newest mtime + missing dest):
`destination` became a symlink pointing at attacker-controlled content; the real
old-pack directory was left orphaned. `publish_pack`'s re-check at
`tools/export_soundswitch_pack.py:290` then aborts with `ValueError` →
`unknown_error`, but the canonical location is already corrupted.

A legitimate swap backup is **always** a real directory (created at
`tools/export_soundswitch_pack.py:238` via `os.replace(destination, backup)` where
`destination` was a verified real dir), so any non-directory `.bak-*` is stray or
hostile and must never become the canonical pack. Likelihood is low (needs a stray
non-dir `.bak-*` in `~/Music/SoundSwitch/`), but it defeats exactly the
symlink-rejection / "never expose a bad canonical pack" guarantee the RW-1 design
promised, so it should be closed.

### A4. Out-of-scope, verified untouched at `9095cef`  [confirmed]

`runtime_status.py`, `soundswitch_pack_controller.py`, `__main__.py`, `export_pack`,
the swap/lock primitives (`_atomic_swap_dir`, `_renamex_np_swap`, `_export_lock`,
`_gc_orphan_staging`, `_stage_artifacts`) and the status schema are correct and
must not change.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules

- Do **not** touch `runtime_status.py`, `soundswitch_pack_controller.py`,
  `__main__.py`, `export_pack`, `publish_pack`, `_atomic_swap_dir`,
  `_renamex_np_swap`, `_export_lock`, `_gc_orphan_staging`, or `_stage_artifacts`.
- Do **not** add a runtime command, change `parse_command`, or change the status
  schema. The menubar's only runtime command stays `set_soundswitch_pack reload`.
- The menubar must still import AppKit + stdlib only and never import the bridge
  package, open a device, or send `enable`/`backend`.
- No path/UUID/port/device/raw-exception text in any UI string, result file, log,
  or committed file (the canonical `~/Music/SoundSwitch/...` constant in source +
  example config is the one intentional exception, per RW-1 kickoff revision #3).

### Task 1 — `tools/export_soundswitch_pack.py`: only a real directory may be promoted

Replace the whole `_recover_orphan_backup` function (currently
`tools/export_soundswitch_pack.py:140-154`).

Current:
```python
def _recover_orphan_backup(parent: Path, name: str) -> None:
    destination = parent / name
    backups = sorted(parent.glob(f".{name}.bak-*"), key=_backup_sort_key, reverse=True)
    if not backups:
        return
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError("destination must be a real directory")
    if not destination.exists():
        os.replace(backups[0], destination)
        _fsync_dir(parent)
        backups = backups[1:]
    if destination.is_dir() and not destination.is_symlink():
        for backup in backups:
            _remove_backup(backup)
        _fsync_dir(parent)
```

New:
```python
def _recover_orphan_backup(parent: Path, name: str) -> None:
    destination = parent / name
    candidates = sorted(parent.glob(f".{name}.bak-*"), key=_backup_sort_key, reverse=True)
    if not candidates:
        return
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError("destination must be a real directory")
    # A swap backup is ALWAYS created from a real directory (see _atomic_swap_dir),
    # so only a real directory may ever become the canonical pack. Any symlink/file
    # ".bak-*" is stray (or hostile) junk and must NEVER be moved into place.
    real_backups = [p for p in candidates if p.is_dir() and not p.is_symlink()]
    junk = [p for p in candidates if not (p.is_dir() and not p.is_symlink())]
    if not destination.exists() and real_backups:
        os.replace(real_backups[0], destination)
        _fsync_dir(parent)
        real_backups = real_backups[1:]
    if destination.is_dir() and not destination.is_symlink():
        for backup in real_backups:
            _remove_backup(backup)
    for stray in junk:
        _remove_backup(stray)
    _fsync_dir(parent)
```

Notes for the implementer:
- The early `ValueError` (bad destination type) is unchanged and still raised
  before anything is moved or removed.
- If the destination is missing and there is **no** real-directory backup (only
  junk), the destination is left **absent** — never fabricated from junk — and the
  next `publish_pack` correctly takes the first-export path.
- `_remove_backup` already handles symlinks/files (`tools/export_soundswitch_pack.py:125-129`).

### Task 2 — `scripts/bridge_menubar.py`: conservative reload-ack pre-check

Replace the pre-check + poll block inside `_run_export` (currently
`scripts/bridge_menubar.py:700-713`).

Current:
```python
            expected_sha12 = result["manifest_sha256"][:12]
            status = read_status()
            if not bridge_pids() or evaluate_reload_ack(status, expected_sha12) == "not_live":
                self._marshal_export_result("published_not_live", result)
                return

            append_command({"cmd": "set_soundswitch_pack", "action": "reload"})
            deadline = time.monotonic() + EXPORT_RELOAD_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if evaluate_reload_ack(read_status(), expected_sha12) == "succeeded":
                    self._marshal_export_result("reload_succeeded", result)
                    return
                time.sleep(EXPORT_RELOAD_POLL_SECONDS)
            self._marshal_export_result("reload_failed", result)
```

New:
```python
            expected_sha12 = result["manifest_sha256"][:12]
            if not bridge_pids():
                self._marshal_export_result("published_not_live", result)
                return
            precheck = evaluate_reload_ack(read_status(), expected_sha12)
            if precheck == "not_live":
                # Bridge is up but pack output is disabled: saved to disk, not live.
                self._marshal_export_result("published_not_live", result)
                return
            if precheck == "stale":
                # Bridge is alive but its status snapshot is not fresh, so we cannot
                # confirm pack output is enabled. Never fire a blind reload at an
                # unknown live state; report saved-but-unconfirmed.
                self._marshal_export_result("reload_failed", result)
                return
            if precheck == "succeeded":
                # The live pack already serves this exact content (e.g. identical
                # re-export): it is already live, so do not re-send a reload.
                self._marshal_export_result("reload_succeeded", result)
                return

            # precheck == "pending": fresh + enabled + sha not yet matching.
            append_command({"cmd": "set_soundswitch_pack", "action": "reload"})
            deadline = time.monotonic() + EXPORT_RELOAD_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if evaluate_reload_ack(read_status(), expected_sha12) == "succeeded":
                    self._marshal_export_result("reload_succeeded", result)
                    return
                time.sleep(EXPORT_RELOAD_POLL_SECONDS)
            self._marshal_export_result("reload_failed", result)
```

Notes for the implementer:
- Do **not** change `evaluate_reload_ack` (`scripts/bridge_menubar.py:248-256`),
  `export_display`, or the `allowed_states` set in `finishExport_`
  (`scripts/bridge_menubar.py:732-734`) — `reload_failed` and `published_not_live`
  are already allowed states.
- Keep `published_result = result` set before this block (currently
  `scripts/bridge_menubar.py:698`) so the existing `except` path still maps a
  post-publish exception to `reload_failed`, not `export_failed`.
- The read-count is preserved: one `read_status()` in the pre-check, then one per
  poll iteration (this keeps `test_export_worker_bridge_on_reloads_and_confirms_matching_sha`'s
  two-status `side_effect` valid).

### Task 3 — docs + change-contract verification (anti-drift)

- `docs/subsystems/soundswitch_output.md`: in the Export-from-SS reload-ack
  description, state that (a) a stale/unconfirmed bridge snapshot reports
  "saved — live reload not confirmed" and does **not** send a reload, and (b) an
  identical re-export reports live without re-sending a reload. Keep the wording
  free of paths/identifiers.
- `docs/agents/change_contracts.yml`: no new entries needed (the
  `soundswitch_pack_player` contract already lists
  `tools/export_soundswitch_pack.py`, `scripts/bridge_menubar.py`,
  `tests/test_soundswitch_pack*.py`, and `tests/test_bridge_menubar.py`). Bump the
  touched contract docs' `last_verified_commit` to the new HEAD per AGENTS.md §7.
- Run the §D hard checks + staleness and fix any drift they report.

---

## Part C — Invariants that MUST still hold (live safety)

1. The 200 Hz push loop and `StateManager` are untouched; the menubar and tool are
   separate processes. No filesystem/subprocess/MIDI/serial/socket/sleep/blocking
   lock is added to `_push_tick`.
2. The menubar's only runtime command stays `set_soundswitch_pack reload`; it never
   sends `enable`/`backend`, never opens a device, never imports the bridge
   package. The Task 2 change only **removes** conditions under which reload is
   sent (strictly more conservative) — it never adds a new send path.
3. Reload still cannot enable output, change backend, restart the bridge, or open
   MIDI/serial/Enttec/DMX (`soundswitch_pack_controller._reload` is
   no-implicit-enable; unchanged).
4. A failed decode/compile/verify/swap still leaves the prior canonical pack
   **byte-identical and `load_pack`-able**. Task 1 strengthens this: a non-directory
   `.bak-*` can never become the canonical pack, and a real-directory backup is
   never deleted while it is the only valid pack.
5. Disk-saved vs live-confirmed stay **distinct, honest** states. A stale/unknown
   bridge state never reports "live now"; a disabled runtime stays
   `published_not_live`; a stopped bridge stays `published_not_live`.
6. Default-off neutrality is unchanged: the feature still only runs on an explicit
   click; with no click every existing behavior is unchanged.

---

## Part D — Tests (pure seams; no device, no live menu bar, no SoundSwitch)

### D1. `tests/test_bridge_menubar.py` — add to `BridgeMenubarTests`

Reuse the existing `_worker`, `_ok_subprocess`, and `_import_module` helpers
(`tests/test_bridge_menubar.py:101-116`). `_ok_subprocess` writes
`manifest_sha256 = "a"*64`, so `expected_sha12 == "a"*12`.

```python
    def test_export_worker_bridge_on_but_stale_does_not_reload(self) -> None:
        bridge_menubar = self._import_module()
        worker = self._worker(bridge_menubar)
        handler = bridge_menubar.BridgeMenuBar._run_export
        stale = {"stale": True, "stale_age_s": 99,
                 "soundswitch_pack": {"enabled": True, "pack_sha12": "a" * 12}}
        with patch.object(bridge_menubar.subprocess, "run", side_effect=self._ok_subprocess), \
             patch.object(bridge_menubar, "read_status", return_value=stale), \
             patch.object(bridge_menubar, "bridge_pids", return_value=["123"]), \
             patch.object(bridge_menubar, "append_command") as append_command, \
             patch.object(bridge_menubar.time, "sleep"):
            handler(worker)
        append_command.assert_not_called()
        state, result = worker._marshal_export_result.call_args.args
        self.assertEqual(state, "reload_failed")
        self.assertTrue(result["ok"])

    def test_export_worker_bridge_on_pack_disabled_publishes_without_reload(self) -> None:
        bridge_menubar = self._import_module()
        worker = self._worker(bridge_menubar)
        handler = bridge_menubar.BridgeMenuBar._run_export
        disabled = {"soundswitch_pack": {"enabled": False}}
        with patch.object(bridge_menubar.subprocess, "run", side_effect=self._ok_subprocess), \
             patch.object(bridge_menubar, "read_status", return_value=disabled), \
             patch.object(bridge_menubar, "bridge_pids", return_value=["123"]), \
             patch.object(bridge_menubar, "append_command") as append_command, \
             patch.object(bridge_menubar.time, "sleep"):
            handler(worker)
        append_command.assert_not_called()
        self.assertEqual(
            worker._marshal_export_result.call_args.args[0], "published_not_live")

    def test_export_worker_identical_reexport_confirms_without_resending_reload(self) -> None:
        bridge_menubar = self._import_module()
        worker = self._worker(bridge_menubar)
        handler = bridge_menubar.BridgeMenuBar._run_export
        already = {"soundswitch_pack": {"enabled": True, "pack_sha12": "a" * 12}}
        with patch.object(bridge_menubar.subprocess, "run", side_effect=self._ok_subprocess), \
             patch.object(bridge_menubar, "read_status", return_value=already), \
             patch.object(bridge_menubar, "bridge_pids", return_value=["123"]), \
             patch.object(bridge_menubar, "append_command") as append_command, \
             patch.object(bridge_menubar.time, "sleep"):
            handler(worker)
        append_command.assert_not_called()
        self.assertEqual(
            worker._marshal_export_result.call_args.args[0], "reload_succeeded")
```

### D2. `tests/test_soundswitch_pack.py` — add to `PublishPackReplaceTests`

```python
    def test_orphan_backup_never_promotes_symlink_or_file_to_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / ".pack.bak-real"; real.mkdir(); (real / "value").write_text("REAL")
            target = root / "evil"; target.mkdir(); (target / "x").write_text("evil")
            sym = root / ".pack.bak-zzz"; sym.symlink_to(target)
            os.utime(real, (1, 1)); os.utime(sym, (9, 9), follow_symlinks=False)
            destination = root / "pack"  # missing: simulates a crash mid-swap
            export_module._recover_orphan_backup(root, "pack")
            self.assertTrue(destination.is_dir() and not destination.is_symlink())
            self.assertEqual((destination / "value").read_text(), "REAL")
            self.assertFalse(sym.exists())            # stray symlink junk removed
            self.assertTrue(target.is_dir())          # its target untouched

    def test_orphan_backup_with_only_junk_leaves_destination_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stray_file = root / ".pack.bak-file"; stray_file.write_text("not a pack")
            target = root / "evil"; target.mkdir()
            stray_link = root / ".pack.bak-link"; stray_link.symlink_to(target)
            export_module._recover_orphan_backup(root, "pack")
            self.assertFalse((root / "pack").exists())   # never fabricated from junk
            self.assertFalse(stray_file.exists())
            self.assertFalse(stray_link.exists())
```

### D3. Existing tests that MUST stay green (regression guard)

- `tests/test_soundswitch_pack.py::PublishPackReplaceTests::test_orphan_backup_recovery_restores_newest_or_discards_when_dest_valid`
- `tests/test_soundswitch_pack.py::PublishPackReplaceTests::test_orphan_backup_is_retained_when_destination_is_invalid`
- `tests/test_bridge_menubar.py::test_export_worker_bridge_off_publishes_without_reload`
- `tests/test_bridge_menubar.py::test_export_worker_bridge_on_reloads_and_confirms_matching_sha`
- `tests/test_bridge_menubar.py::test_post_publish_command_failure_remains_saved_not_export_failed`

### D4. Gates (record outputs; all hardware-unvalidated)

```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 -m unittest tests.test_soundswitch_pack tests.test_bridge_menubar
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check

cd /Users/bbui
python3 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation \
  --project ~/Music/SoundSwitch/default.ssproj --output-dir /tmp/rbss-rw1-fix-proof   # expect 29/0/0
```

Run the two changed modules under **Python 3.11** as well (CI is 3.11; local is
3.14).

---

## Part E — Acceptance (definition of done)

- [ ] Task 1: a symlink/file `.bak-*` is never moved into the canonical
      destination; a real-directory backup is still restored on a missing dest and
      discarded on a valid dest; junk is removed (D2 green).
- [ ] Task 2: bridge-on + stale → no reload appended, state `reload_failed`;
      bridge-on + pack disabled → no reload, `published_not_live`; identical
      re-export (pre-existing sha match) → no reload, `reload_succeeded`; changed
      content (fresh + enabled + old sha) → reload sent + confirmed (D1 + existing
      tests green).
- [ ] Menubar still sends only `reload`; no `enable`/`backend`; no new runtime
      command; no status-schema change; no bridge-package import.
- [ ] Full suite + `tests.test_soundswitch_pack` + `tests.test_bridge_menubar`
      green; proof gate `29/0/0`; the three hard doc checks pass; staleness
      re-verified; `git diff --check` clean.
- [ ] No path/UUID/port/device/raw-exception leaks in any UI string, result file,
      log, or committed file (besides the intentional canonical-path constant).

## When you finish

Commit per task (Task 1 → Task 2 → Task 3). Report: tests run + counts, the proof
verdict, the three hard doc checks, the staleness line, and explicit confirmation
that the menubar still sends only `reload` and that no non-directory backup can
become canonical. Do not claim the fixes complete until an independent review of
the orphan-recovery type-check and the reload-ack pre-check passes.
