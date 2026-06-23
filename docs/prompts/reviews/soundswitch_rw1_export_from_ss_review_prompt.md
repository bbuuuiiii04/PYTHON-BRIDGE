---
doc_status: active-prompt
truth_level: code-grounded
last_verified_commit: 683af8d
last_verified_date: 2026-06-23
validation_scope: adversarial review prompt for the RW-1 spec only; no implementation
---

# Independent review — RW-1 `Export from SS` spec

You are an adversarial reviewer who did **not** author the spec. Target:
`docs/plans/active/soundswitch_rw1_export_from_ss_spec.md` at the current HEAD.
Verify every load-bearing claim against current code; do not trust the spec's own
line numbers. Output: APPROVE / REVISE-AND-APPROVE / REJECT with specific findings
labeled confirmed/assumed/unknown. Do not implement.

Attack these five surfaces hardest:

1. **Directory replacement safety.** Does the swap (`_atomic_swap_dir` via
   `renamex_np(RENAME_SWAP)` with the move-aside fallback) ever expose a partial or
   missing canonical pack to a concurrently-loading bridge? Prove the prior verified
   pack survives byte-identical on every failure branch (decode, compile, fsync,
   `verify_pack`, swap, cleanup). Check first-publish (`os.replace`) vs replace
   (`renamex_np` needs both paths to exist). Check the crash window in the fallback
   and that `_recover_orphan_backup` cannot delete the only valid pack. Check
   cross-filesystem and symlink-destination/parent rejection, and the `_export_lock`
   stale-lock recovery (dead pid / TTL).

2. **UI concurrency / AppKit safety.** Confirm no decode/compile/verify/poll runs on
   the AppKit main thread; only marshaled state updates (`performSelectorOnMainThread`)
   touch it. Confirm the in-process guard plus the cross-process lock actually prevent
   two publishers, and that a `subprocess` timeout/crash returns the UI to a clean,
   re-enabled state.

3. **Reload acknowledgement honesty.** Confirm `evaluate_reload_ack` never reports
   "live now" off a stale snapshot or when the runtime pack is disabled, and that the
   identical-re-export (same sha) case is handled without a false failure. Confirm the
   menubar's only runtime command is `set_soundswitch_pack reload`.

4. **Sanitization.** Confirm no path/UUID/port/device/raw-exception/project-byte leaks
   into the result JSON, UI strings, logs, or any committed file; only verdict /
   error-category / content-sha / count are surfaced.

5. **No implicit enable / no hardware / neutrality.** Confirm reload cannot enable
   output, change backend, start/restart the bridge, or open MIDI/serial/Enttec/DMX;
   a disabled runtime stays disabled and a stopped bridge stays stopped. Confirm RW-1A
   is untouched and the feature is default-off until clicked, leaving OS2L / lasers /
   LEDs / readers / scripted / T7d / static / blackout behavior unchanged.

Also confirm scope discipline: `export_pack` and its `test_atomic_publish_requires_new_destination`
are untouched; no new runtime command or status-schema change; tests have pure seams
and open no device.
