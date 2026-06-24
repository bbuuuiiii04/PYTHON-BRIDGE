---
doc_status: active-review-prompt
truth_level: code-grounded
last_verified_commit: 4ffe7c8
last_verified_date: 2026-06-24
validation_scope: independent review of RW-3 implementation commits 6fdef84 through 4ffe7c8; review-only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no live/runtime mutation authorized
---

# Independent implementation review — RW-3 mode authority

You are the independent adversarial reviewer for RW-3 in
`/Users/bbui/rb_ss_bridge_v2`.

This is **review-only**. Do not edit files, commit, push, change configuration,
start/restart/stop the bridge, append runtime commands, enable pack output, change
the backend, open MIDI/serial/Enttec/DMX devices, or perform fixture-visible testing.
Read-only inspection and offline tests that write only to `/tmp` are allowed.

## Review target

```text
Branch: main
Implementation base: d4bcdd5
Implementation head: 4ffe7c8
Implementation commits:
  6fdef84 feat(soundswitch): RW-3 mode-only scripted gate + identity-aware pause hold
  f426668 fix(soundswitch): RW-3 disarm pack pause-hold on scripted de-ownership
  9ba16f0 test(soundswitch): RW-3 mode/hold/de-ownership cases; RW-2 hold-key fixup
  4ffe7c8 test(soundswitch): RW-3 inner autoloop-uuid zero + same-identity clear→arm
Spec: docs/plans/active/soundswitch_rw3_mode_authority_spec.md
Allowed implementation files:
  state_manager.py
  tests/test_state_manager_pack_driver.py
```

Review the fixed range `d4bcdd5..4ffe7c8`, even if current `HEAD` also contains
this review-prompt commit. Confirm the implementation range changes only the two
allowed files. Do not treat this prompt or later documentation-only commits as part
of the implementation range.

## Required source order

1. Read `AGENTS.md` completely and `PRIVATE_OPERATOR_PROFILE.md` if present.
2. Read the RW-3 spec named above, especially Part B Absolute Rules, Parts C-E,
   and R1-R11.
3. Inspect `git diff d4bcdd5..4ffe7c8` and resolve every anchor against current
   code. Code and tests win when documentation conflicts.
4. Trace the relevant current code in:
   - `state_manager.py`: initialization, event drain/run ordering,
     `SCRIPTED_ARM`/`SCRIPTED_CLEAR`, `_on_track_loaded`, `_on_master_changed`,
     `_on_filepath_resolved`, `_arm_unscripted`, `_update_lighting`, `_push_tick`,
     and `_drive_pack_output`
   - `tests/test_state_manager_pack_driver.py`
   - `soundswitch_laser_player.py`: UUID normalization, scripted selection,
     `clear_selection`, `scripted_not_found`, Static Override, and blackout precedence
   - `models.py`: `DeckState.scripted_id`, `TrackMetadata.soundswitch_id`, and
     `OutputState.was_playing`/`lighting_mode`
   - `scripted_tracks.py`: registry and `register()` semantics
5. Use `docs/architecture/runtime_invariants.md` and
   `docs/subsystems/soundswitch_output.md` only as secondary evidence.

## Claims to verify independently

- The automatic scripted base now requires `DeckState.scripted_id != 0`; a valid
  embedded UUID alone cannot claim scripted mode.
- The gate is intentionally mode-only. It performs no scripted-registry or identity
  lookup and always asks the player to render the loaded `d.meta.soundswitch_id`.
- The pause hold key is exactly `(active, load_gen, scripted_id, norm_ssid)` and a
  different deck, generation, scripted id, or normalized SSID cannot resurrect it.
- `_arm_unscripted(deck)` clears the hold only when `deck` owns the hold, closing the
  same-drain clear → re-resolve → re-arm hole without dropping an active-deck hold
  when the mirror deck is cleared.
- A fresh PLAY is required after held-deck scripted de-ownership before a paused
  scripted frame can be held again.
- Unowned, autoloop, idle, invalid, stale, changed, discontinuous, and expired-hold
  automatic bases still use `clear_selection()` and never send
  `transport="stopped"`, `"ended"`, or `"unloaded"`.
- Held Static Override remains an authoritative overlay and may stand over a ZEROed
  automatic base; blackout/emergency and pack-disabled/shutdown still win.
- RW-2 pause timing and resume behavior remain intact.
- RW-4 controller-input health, RW-5 status/menubar, and RW-8 native-DMX Autoloop
  remain out of scope. `select_autoloop` remains uncalled.
- The change adds no blocking work, I/O, locks, sleeps, retries, new instance fields,
  helpers, config/status/startup changes, or DeckState writers outside StateManager.
- OS2L, lasers, LEDs/Govee, Rekordbox readers, runtime commands, and default-off
  behavior remain unchanged.
- RW-3 was not marked complete; independent review and hardware validation remain
  open.

## Attack these risks hardest

1. **Mode-only mismatch.** Find any reachable state where `scripted_id != 0` causes
   content other than the loaded SSID to render, or where the master-deck transfer,
   OSC arm, filepath match, queue drop, or direct-mode timing makes mode-only unsafe.
2. **Same-identity resurrection.** Construct the strongest paused sequence that
   clears ownership and restores the same four-part identity before the next driver
   tick. Determine whether any path bypasses `_arm_unscripted` while preserving both
   `load_gen` and `was_playing`.
3. **Mirror-deck isolation.** Prove `_pack_play_hold_key[0]` is always the hold-owning
   deck. Find any case where clearing a mirror deck wrongly drops the active hold or
   clearing the held deck wrongly preserves it.
4. **ZERO and overlay precedence.** Try to produce a new non-zero automatic base from
   an unowned/stale/error state. Separately verify that any newly visible held-static
   frame is the explicitly accepted overlay behavior, not an automatic-base leak.
5. **Hot-path and ownership safety.** Confirm all added work is in-memory and runs on
   the StateManager thread. Check that `_arm_unscripted` has no off-thread caller.
6. **Test strength.** Confirm R1-R11 exist and fail for the intended pre-RW-3 defect.
   Inspect R6/R8 to ensure they drive the real `_push_tick()` path under
   `RBSS_SCRIPTED_DIRECT=0`. Decide whether R8 can false-pass despite the deliberate
   unregistered `scripted_id=7` warning, and whether R9 proves the registry is not
   consulted without leaking global registry state.
7. **Scope and status.** Confirm the exact two-file implementation diff, four commit
   messages/order, unchanged default-off config, and that no roadmap/status checkbox
   claims RW-3 complete.

## Existing implementation evidence to distrust and reproduce

The implementer reported:

- R1-R11: 11/11 passed independently.
- `tests.test_state_manager_pack_driver`: 44/44 passed on Python 3.14 and 3.11.
- Full suite: 2,331 tests passed, 3 skipped, 1 expected failure.
- Pack proof: `PASS_IMPLEMENTATION_MAY_BEGIN`, 29 PASS / 0 FAIL / 0 INCOMPLETE.
- Hard documentation checks and implementation-range `git diff --check`: passed.
- Advisory staleness: `core_bridge`, `runtime_commands`, and
  `soundswitch_pack_player` remain flagged; no status/roadmap completion edit was
  made because the implementation spec and operator required the narrow boundary.

These are claims, not authority. Re-run enough to verify them.

## Minimum verification

```bash
cd /Users/bbui/rb_ss_bridge_v2
git status --short --branch
git diff --name-only d4bcdd5..4ffe7c8
git diff --check d4bcdd5..4ffe7c8
python3 -m unittest tests.test_state_manager_pack_driver
python3.11 -m unittest tests.test_state_manager_pack_driver
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
```

You may rerun the full suite and the offline 29/0/0 pack-generation proof if useful.
Do not treat software tests or project-file proof as hardware validation.

## Required response

Return the review in chat without modifying the repository:

1. Verdict: exactly `APPROVE`, `REVISE-AND-APPROVE`, or `REJECT`.
2. Findings first, ordered by severity, with `path:line`, a concrete failing
   sequence, live impact, and the smallest required correction. If none, say
   `No findings.`
3. Exact verification commands and result summaries.
4. Explicit conclusions for mode-only identity safety, same-identity teardown,
   mirror-deck isolation, Static Override/blackout precedence, push-loop purity,
   test strength, two-file scope, and unchanged completion status.
5. Residual risks and missing evidence, preserving
   **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.
