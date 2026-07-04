---
doc_status: active-spec
truth_level: implementation-spec, code-grounded
last_verified_commit: 267edd3
last_verified_date: 2026-07-04
validation_scope: spec only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — Laser blackout re-wire (Package 1 of AWR-119/111)

Behavior contract this implements: `docs/architecture/laser_blackout_authority.md` —
read it first; its rules and survival matrix are the acceptance oracle. Design
evidence: `docs/plans/active/laser_color_engine_design_spec.md` Part C.

## Part A — Context & Root Cause (verified at `bd96b32`; read, do not implement)

- [confirmed] In pack mode, smart-drop/breakdown blackout does nothing to the
  bridge's own DMX: `PackOutputBackend.trigger()` resolves only by
  `scene_name` (`laser_output_backend.py:169-176`), and blackout messages
  carry none (`laser_config.py:803-819` builds them without `scene_name`;
  `laser_models.py:53` defaults it to `""`), so `trigger()` returns `False`.
- [confirmed] Worse, the owner refcount never latches in pack mode:
  `hold_blackout_mask` adds the owner, then **discards it when
  `backend.trigger()` returns False** (`laser_executor.py:330-340`). It also
  early-returns when `smart_drop_mode != "blackout_mask"` (:325) or
  `manual_blackout_on` is unset (:327-329). `trigger_blackout_on` likewise
  sets `_blackout_pending_for_drop_window` only on trigger success
  (:300-302). Net: `_mask_owners` is permanently empty in pack mode.
- [confirmed] The frame-level mask has exactly ONE writer:
  `state_manager.py:2342-2364` inside `_drive_pack_output` (:2300, invoked
  once per 200 Hz push tick via `_push_tick` :2092-2107). It computes
  `blackout = blackout_held if input_healthy else False` (:2361) from the
  MIDI-input snapshot alone and calls
  `player.set_masks(blackout=…, emergency=False)` (:2364) **every pass** — a
  direct `set_masks` call anywhere else is overwritten within ~5 ms. The
  SS-present path clears masks (:2387).
- [confirmed] The manual system is healthy and out of scope: per-binding
  refcount (`soundswitch_midi_input.py:280-314`), group `any()` merge
  (:621-635), overlay-trust gate (`state_manager.py:2352-2361`).
- [confirmed] The executor wipe (`clear_pending_blackout` :79-82 →
  `_release_all_masks` :358-362, also via `reset_runtime_state` :84-97) fires
  from `state_manager.py:1225,1232,1419,1462,1504,3244,3263,3517,3551,3558` —
  every lifecycle boundary. Smart owners ending at boundaries is intended;
  this is why the manual pad must never live in `_mask_owners`.
- [confirmed] Player mask API: `set_masks(*, blackout, emergency)` /
  `set_blackout` (`soundswitch_laser_player.py:323-333`); `render()` returns
  `ZERO_FRAME` when masked (:422-424).

Root cause: the smart-side blackout was designed for MIDI actuation; in pack
mode both its actuation (the note) and its bookkeeping (the owner latch) die
on the backend-rejection path, and the frame-level writer never consults it.

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY `laser_executor.py`, `state_manager.py`, tests, and the
  contract-mandated docs. Do NOT touch `soundswitch_midi_input.py`,
  `soundswitch_laser_player.py`, `smart_rearm.py`, `laser_output_backend.py`,
  or any timing/decision knob.
- MIDI-mode note behavior stays byte-compatible except as Task 1 states
  (latch-before-send); no change to which notes are sent on success paths.
- No new files except the test module. No new threads. No I/O added anywhere
  on the push loop (`_push_tick` call graph).
- Error handling: fail closed — a raise inside the drive path already submits
  a direct ZERO frame (`state_manager.py:2100-2106`); do not add broad
  try/except or success-shaped fallbacks.

### Task 1 — `laser_executor.py`: latch owners independent of send success
1. `hold_blackout_mask(owner)`: keep the `smart_drop_blackout_enabled()`
   gate. **Latch the owner into `_mask_owners` unconditionally after that
   gate** (under `self._lock`). Then, only if `manual_blackout_on` is
   configured AND the mask was not already dark, attempt the note send as
   today — but a rejected send must NOT discard the owner (delete the
   :338-339 rollback). Keep the `manual_blackout_on_rejected` gate counter so
   MIDI-mode diagnostics stay visible.
2. `trigger_blackout_on(ctx)`: set `_blackout_pending_for_drop_window = True`
   after the mode/duplicate gates **regardless of trigger success**; the note
   send stays best-effort. Move the `manual_blackout_on is None` early-return
   (:296-299) so it guards ONLY the note send — the pending latch is set even
   with no message configured (authority rule 7: frame-level actuation needs
   no MIDI note). Demote the :306 "blackout_on rejected" warning to DEBUG —
   in pack mode rejection is by-design and would otherwise warn once per
   armed window; the `manual_blackout_on_rejected` gate counter keeps
   MIDI-mode visibility. (Consequence, intended: `_resolve_pending_blackout`
   may emit a note-off whose note-on never went out — harmless; the off is a
   no-op to any listener.)
3. Add a thread-safe read accessor:
   ```python
   def mask_owners_active(self) -> bool:
       """True while any smart-side blackout owner or drop-window latch holds."""
       with self._lock:
           return bool(self._mask_owners) or self._blackout_pending_for_drop_window
   ```
   Pure state read under the existing lock; no I/O, no allocation beyond the
   bool. `release_blackout_mask`, `_release_all_masks`,
   `_resolve_pending_blackout`, and `clear_pending_blackout` are UNCHANGED.

### Task 2 — `state_manager.py`: OR the smart side into the single writer
1. In `_drive_pack_output`, where `blackout` is computed (:2361), extend to:
   ```python
   smart_dark = (self._laser_executor.mask_owners_active()
                 if self._laser_executor is not None else False)
   blackout = (blackout_held if input_healthy else False) or smart_dark
   ```
   using the existing `self._laser_executor` attribute (see :544 for the
   established access pattern). `blackout_bindings`/`layers` handling and the
   `emergency=False` argument are unchanged.
2. The SS-present path (:2387) stays `set_masks(blackout=False, …)` — the
   player bool is DERIVED state recomputed every pass from the two owner
   systems, so no held intent is erased (authority rule 8): when SS leaves,
   the next pass recomputes both sides. Add a one-line comment there stating
   exactly that, so a future reader doesn't "fix" it.
3. Nothing else in the drive path changes; `_pack_truth_intent` continues to
   receive the computed `blackout` (now OR-inclusive) wherever it already
   flows.

### Task 3 — tests: `tests/test_laser_blackout_rewire.py`
Implement the survival matrix from `laser_blackout_authority.md` §Required
Behavior Tests, at minimum:
1. Pack-mode latch: a rejecting backend (`trigger()` → False) + `hold_blackout_mask("breakdown")`
   → `mask_owners_active()` is True; release clears it.
2. Pending latch: `trigger_blackout_on` with rejecting backend →
   `mask_owners_active()` True until `_resolve_pending_blackout`.
3. Writer OR: with a stub executor whose `mask_owners_active()` returns True,
   the next `_drive_pack_output` pass calls `set_masks(blackout=True, …)`
   even when the MIDI-input snapshot reports no manual hold; frame renders
   ZERO. (Drive via the established pack-driver test harness pattern in the
   existing state_manager pack tests.)
4. Manual survival: manual hold via the MIDI-input snapshot + every wipe path
   (`reset_runtime_state`, `clear_pending_blackout`, and the state_manager
   lifecycle sites' equivalents) → blackout stays True across passes,
   clearing only when the manual snapshot releases.
5. Overlap semantics: smart+manual held → releasing either alone keeps
   blackout True; releasing both clears it on the next pass.
6. MIDI-mode compatibility: with an accepting backend, note on/off sequences
   for hold/release/resolve are unchanged from current behavior.

## Part C — Invariants That MUST Still Hold
- Blackout is absolute: masked frames are ZERO regardless of any renderer,
  color, or static-look state (`soundswitch_laser_player.py:202-203,422-424`).
- The push loop gains no blocking I/O; `mask_owners_active()` is a
  lock-guarded bool read.
- The C2 unconditional wipe remains smart-side only; the manual MIDI-binding
  system is untouched by this package.
- Exactly one bridge process; no runtime/bridge restart is authorized by this
  spec.
- All AGENTS.md §6 invariants.

## Part D — Tests
Task 3 above. Pure-function seams: `mask_owners_active()` needs no backend;
the writer OR is testable with a stub executor + fake MIDI-input snapshot per
the existing pack-driver tests. Run the full suite
(`python3 -m unittest discover tests`).

## Part E — Acceptance (definition of done)
1. Contract-first: extend the `laser` contract in
   `docs/agents/change_contracts.yml` (docs_update must include
   `docs/subsystems/laser.md`, `docs/architecture/laser_blackout_authority.md`,
   `docs/plans/active/laser_color_engine_design_spec.md`,
   `docs/status/active_work_registry.md`) BEFORE code edits.
2. Tasks 1-3 implemented; new tests green; full suite green.
3. `python3 tools/check_docs_metadata.py`, `check_agent_contracts.py`,
   `check_docs_drift.py` all pass; contract docs updated (laser.md's
   "blackout-mask migration" bullet updated to implemented/software-tested
   status language; authority doc `last_verified_commit` bumped).
4. No diff outside the allowed files.

## When You Finish
Report: changed files, test names + counts, checks output. Operator summary
(plain language): smart-drop/breakdown blackout now actually darkens the
bridge's own laser output; your held blackouts (laser pad web / future deck
mute) can never be un-darkened by automation; nothing about timing knobs or
MIDI-mode behavior changed; live/hardware validation remains pending and no
bridge restart was performed.
