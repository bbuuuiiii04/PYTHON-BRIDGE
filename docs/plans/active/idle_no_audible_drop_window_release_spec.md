---
doc_status: current
truth_level: code-verified
last_verified_date: 2026-07-09
last_verified_commit: HEAD-2026-07-09-overnight
validation_scope: SHIP-BLOCKER fix spec (D3-F1 from the QA showcase loop; executive-authorized fix round, fix shape RULED at the executive desk): _enter_idle_no_audible leaks the drop_spotlight LED-blackout owner when the active-deck resolver goes to 0 mid-solo-window (room stuck dark up to the 192-beat cap on the live Director-enabled rig); repro triple-verified (QA + executive + LED manager, exit=2 at HEAD); latent pre-2026-07-09, tonight raised exposure
---

# Codex Implementation Spec - idle-no-audible releases the drop-presentation window (AWR-171 / D3-F1)

## Part A - Root cause (verified at HEAD by three desks; read, do not re-derive)

1. [confirmed] `_enter_idle_no_audible` (`state_manager.py:2086`) resets LED, laser, autoloop,
   and smart-rearm state but NEVER releases the drop-presentation window — no
   `_drop_presentation_release_on_stop()` call anywhere in the method.
2. [confirmed] `_do_stop` DOES call it (`state_manager.py:5118`), last, after the laser
   executor/director resets — that is the asymmetry: stop releases, idle-no-audible leaks.
3. [confirmed] `_push_tick_inner` early-returns when `active_deck not in (1, 2)`, so once the
   resolver lands on 0 mid-solo-window nothing downstream ever ticks the window machine again —
   the `drop_spotlight` owner stays held and `_dispatch_led_idle_ambient` renders nothing: a dark
   room until the 192-beat cap (or forever if beats stop advancing).
4. [confirmed] `_drop_presentation_release_on_stop` (`state_manager.py:2865`) is IDEMPOTENT,
   no-ops when the policy is disabled (keeps `enabled:false` byte-identical), reuses the
   WindowMachine's universal `stopped=True` fail-open, and is pure/in-memory — safe on the 200 Hz
   path and safe to call on every idle entry including ones with no window open.
5. [confirmed] Repro: `python3 /private/tmp/claude-501/-Users-bbui-rb-ss-bridge-v2/17613c93-b505-455f-ac6c-2d34a371e2bf/scratchpad/lane_scratch/QASD3/leak_repro.py`
   (run from the PARENT dir `/Users/bbui`) exits 2 at HEAD: idle-no-audible leaks, `_do_stop`
   releases.
6. [ruled — executive live reasoning, on record] Fail-open beats fail-dark: an early
   lights-return on an idle blip is visible and recoverable; stuck-dark is the showcase failure.

## Part B - The fix (implement exactly; ONE task, one commit)

### Absolute Rules
- SCOPE IS ONE HOP: do not widen. No refactors, no second call sites, no changes to the window
  machine, the resolver, or `_push_tick_inner`. The QA program runs in parallel on disjoint files.
- Out of scope: everything except `state_manager.py` (the one call) + the new test file + the
  contract-listed docs.
- No behavior change when the drop-presentation policy is disabled (the helper's own guard
  provides this — do not add a second guard).

### Task 1 - `state_manager.py`: mirror the `_do_stop` release into `_enter_idle_no_audible`
Add `self._drop_presentation_release_on_stop()` at the END of `_enter_idle_no_audible`, after the
laser executor/director `reset_runtime_state` calls — the exact position `_do_stop` uses
(`:5110-5118` ordering), with a comment mirroring `_do_stop`'s ("every idle-no-audible entry
routes through here, so a resolver-to-0 mid-solo-window can't leave the room latched dark").
One shared release for every idle-no-audible entry — same helper, no copy.

### Task 2 - Pinned unit test
New test (place beside the existing drop-presentation state_manager tests,
`tests/test_state_manager_drop_presentation.py`): open a LASERS_ONLY solo window so the
`drop_spotlight` owner latches (reuse the existing test scaffolding there), drive
`_enter_idle_no_audible`, and assert the owner set is empty, dark-hold false, window phase idle —
EXACTLY the post-`_do_stop` state (assert equality with a `_do_stop`-path twin, not hand-picked
fields, so the paths can never drift apart again). Also pin: idle entry with NO window open is a
no-op (idempotency), and policy-disabled idle entry stays byte-identical.

## Part C - Invariants
- 200 Hz push loop gains no I/O (the helper is pure/in-memory — verified).
- `enabled:false` drop-presentation config stays byte-identical (helper's first guard).
- `_do_stop` behavior unchanged (untouched).
- Laser executor/director reset ordering in `_enter_idle_no_audible` unchanged — the new call
  appends after them.

## Part E - Acceptance
- [ ] QA repro exits 0-family with owners cleared:
  `cd /Users/bbui && python3 <repro path in Part A-5>` prints released owners and exits 0/1 (any
  non-FINDING exit), owners `()` after the idle path.
- [ ] New pinned tests green; the drop-presentation suite green.
- [ ] Full suite from REPO ROOT: exactly the named FIVE-red baseline
  (`test_drop_slot_color_smoke_and_snap` error; both `test_export_pack_parity_self_heal` fails;
  `test_ddj_slots_8_16_17_24_exact_ch1_ch19`; `test_autoloop_capture_rows_identify_passes_and_blockers`
  — the loader cwd-form red is absent from repo root). The two `test_soundswitch_pack`
  byte-identity tests flap (AWR-169) — isolate before counting them either way.
- [ ] Three hard checks; contract docs per `led_govee`/`drop_presentation` in
  `docs/agents/change_contracts.yml` (registry row AWR-171).
- [ ] Print exactly D3F1FIX-DONE with the repro exit code + suite numbers above it, or
  D3F1FIX-BLOCKED with the reason.

## When You Finish
Report: the diff hunk (it should be a handful of lines), repro before/after exit codes, tests
added, suite numbers, docs updated. Name any deviation explicitly.
