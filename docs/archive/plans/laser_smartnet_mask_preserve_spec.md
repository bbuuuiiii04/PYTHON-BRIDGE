---
doc_status: deferred-reference
truth_level: code-grounded
last_verified_commit: b2ce63d
last_verified_date: 2026-06-23
validation_scope: spec only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — SM-net: a gated-off Smart-Drop crossing must not force-release held blackout masks

## STATUS — DEFERRED (decision 2026-06-23): do NOT implement in the MIDI path

The holistic review plus operator discussion concluded this **C2** edge is a **narrow, cosmetic,
MIDI-only** artifact: a disallowed Smart-Drop crossing landing inside a held `master_switch`
(deck-switch) cover releases it ~a beat early. It replaces a worse pre-existing bug (a spurious drop
look), nothing strands (both `breakdown` and `master_switch` covers have their own release paths —
`smart_rearm.py:244/268-277` and the first autoloop tick `state_manager.py:3797`), and a ~78-minute
live log showed 48 properly-led-in crossings and **zero** gated-off ones — i.e. C2 was not observed in
practice. The legitimate up→chorus and chorus→chorus (two-drops-in-a-row, cap 2) drops both emit
`drop_crossing`, so they never reach this SM-net path.

The blackout mask is also MIDI **actuation** that does not carry to the future output: when the
bridge-native direct-DMX/`PackOutputBackend` lane becomes the live laser output, the held
`manual_blackout_*` note retires (DMX blacks out via a zero CH1-CH19 frame; the pack backend already
no-ops `manual_blackout_*` because they carry no `scene_name`), but the masking **decision**
(refcounted overlapping owners + teardown timing) must be ported to the frame-level blackout.

**Agreed resolution:** settle the blackout owner/teardown semantics — including this C2 edge — when
the DMX frame-level blackout is designed, NOT by patching the outgoing MIDI path. The MIDI-path fix
below (`clear_drop_window_blackout`) is retained as **reference/analysis only** and is **not queued
for Codex**. Cross-refs: `docs/subsystems/laser.md` (Blackout-mask migration) and
`docs/plans/active/soundswitch_exporter_remaining_work.md#invariants`.

---

> Original (now-deferred) hardening from the holistic laser-lifecycle review (head `b2ce63d`). Closes
> the one laser-internal inconsistency surfaced as accepted-divergence **C2** in
> `docs/plans/active/chorus_drop_cycling_spec.md`. Kept below as the reference design for the eventual
> DMX-path blackout work — not for the MIDI path.

## Part A — Context & root cause (verified; read, do not implement)

**Plain meaning.** The lasers have a single shared "blackout mask" — a held MIDI blackout note that
keeps the lasers dark. It can be held by named owners (`"breakdown"`, `"master_switch"`) with
reference counting. Separately, the Smart-Drop pre-window can arm a short *drop-window* blackout. Both
share the same physical note. Today, when a Smart-Drop crossing is **gated off** (the new A3 drop
gate decides the drop was not properly led in), the StateManager "SM net" clears the blackout by
calling a routine that **releases every mask owner**, not just the drop-window pending. That can lift
a held `breakdown`/`master_switch` transition mask a beat early.

**Why it exists / root cause.**
- [confirmed] The SM net runs after the director tick on any blackout-mode crossing that did not
  produce a `drop_crossing` decision:
  `state_manager.py:3850-3864` — `if smart_drop_result.crossing and smart_drop_blackout_mode:` …
  `if self._laser_executor is not None and not drop_crossing_decision_emitted:
  self._laser_executor.clear_pending_blackout(reason="smart_drop_crossing_without_drop_decision")`.
- [confirmed] `clear_pending_blackout` does **two** things — release ALL masks, then resolve the
  drop-window pending: `laser_executor.py:79-82`
  ```
  def clear_pending_blackout(self, *, reason: str = "smart_drop_reset") -> None:
      self._release_all_masks()
      self._resolve_pending_blackout(reason=reason)
  ```
- [confirmed] `_release_all_masks` releases every owner: `laser_executor.py:343-347`.
- [confirmed] `_resolve_pending_blackout` clears only the drop-window pending and sends
  `manual_blackout_off` **only when no owner remains** (the `owners_remain` guard):
  `laser_executor.py:293-306` (esp. `owners_remain = bool(self._mask_owners)` and
  `if not pending or owners_remain: return`).
- [confirmed] Mask owners and their **own** release paths (so the SM-net release is redundant, not
  load-bearing):
  - `"breakdown"` held at `smart_rearm.py:289`; released by the forward end-crossing
    `smart_rearm.py:244` and the leaked-window safety net `smart_rearm.py:268-277`.
  - `"master_switch"` held at `state_manager.py:3179` (only when the director is enabled); released on
    the first autoloop tick `state_manager.py:3797`.
- [confirmed] Behavior asymmetry today: an **allowed** crossing reaches the executor as
  `reason="drop_crossing"` and resolves via `_resolve_pending_blackout(reason="drop_crossing_success")`
  (`laser_executor.py:247-248`), which **preserves** held masks (owners_remain guard). A **disallowed**
  crossing is gated (`laser_director.py:477-487`), produces no `drop_crossing`, and hits the SM net,
  which **releases** masks. Same musical event, opposite mask treatment.
- [confirmed] Scope of the feature-introduced change: only the `"master_switch"` case is newly
  reachable. During a breakdown the director returns `breakdown` at Priority 8
  (`laser_director.py:457-465`) because every personality has `breakdown_scene` configured
  (verified in both `config/laser_director.json` and `config/laser_director.example.json`), so the SM
  net behaves identically pre/post-feature for breakdown. The fix still correctly covers both owners.
- [confirmed] The LED/Govee path has **no** shared mask (it never calls the mask API), so this is a
  laser-internal inconsistency, not a laser-vs-LED divergence. The drop/post_drop **role** decision
  already mirrors the LED resolver and is unchanged by this spec.

**Root cause (one line):** the SM-net "clear the drop-window blackout for a gated-off crossing" path
reuses `clear_pending_blackout`, which *also* tears down unrelated, separately-owned transition masks.

**Live consequence today:** a disallowed Smart-Drop crossing landing inside the brief post-master-
change re-arm window lifts the `master_switch` transition mask early — the lasers un-blackout ~a beat
before the first autoloop tick. Cosmetic, recoverable, narrow. No strand (the mask has its own
release). This spec makes the gated-off crossing leave held masks intact so the transition mask ends
at its correct time (first autoloop tick), matching the allowed-crossing behavior.

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **Do not** change `_resolve_pending_blackout`, `_release_all_masks`, `clear_pending_blackout`,
  `trigger_blackout_on`, `hold_blackout_mask`, or `release_blackout_mask` behavior. Add one new
  public wrapper only.
- **Do not** change any OTHER caller of `clear_pending_blackout`. The following MUST keep releasing
  all masks (full-teardown semantics): `laser_executor.py:97` (`reset_runtime_state`),
  `state_manager.py:3840` (`laser_director_disabled`), `state_manager.py:4223`
  (`smart_rearm_state_cleared`). Only the SM-net gated-off crossing call site changes.
- **Do not** touch `smart_phrasing.py`, `smart_rearm.py`, `drop_lifecycle.py`, `laser_director.py`,
  the LED `_led_*` path, the 200 Hz push-loop threading, or readers (RB/SS/Govee).
- No new persistent state fields. No new I/O on the push loop.

### Task 1 — `laser_executor.py`: add a pending-only public clear (drop-window only, mask-respecting)
Add a public method next to `clear_pending_blackout` (around `laser_executor.py:79-82`) that resolves
ONLY the drop-window pending and leaves mask owners untouched. It is a thin wrapper over the existing
private resolver; do not duplicate its logic.

```python
def clear_drop_window_blackout(self, *, reason: str = "drop_window_reset") -> None:
    """Resolve only the Smart-Drop *drop-window* pending blackout.

    Unlike clear_pending_blackout(), this does NOT release named mask owners
    (breakdown / master_switch). manual_blackout_off is still sent only when no
    owner remains (the _resolve_pending_blackout owners_remain guard), so a held
    transition mask survives a gated-off Smart-Drop crossing and ends on its own
    release path (breakdown end-crossing / first autoloop tick).
    """
    self._resolve_pending_blackout(reason=reason)
```

### Task 2 — `state_manager.py`: SM-net gated-off crossing uses the pending-only clear
At the SM-net call site (`state_manager.py:3855-3861`), change ONLY the gated-off branch from
`clear_pending_blackout` to the new `clear_drop_window_blackout`. Keep the same `reason` string.

Before:
```python
            if (
                self._laser_executor is not None
                and not drop_crossing_decision_emitted
            ):
                self._laser_executor.clear_pending_blackout(
                    reason="smart_drop_crossing_without_drop_decision"
                )
```
After:
```python
            if (
                self._laser_executor is not None
                and not drop_crossing_decision_emitted
            ):
                self._laser_executor.clear_drop_window_blackout(
                    reason="smart_drop_crossing_without_drop_decision"
                )
```
Do not change the surrounding `if smart_drop_result.crossing and smart_drop_blackout_mode:` block,
the `os.drop_cut_armed = False` cleanup, or the `drop_crossing_decision_emitted` computation.

## Part C — Invariants that MUST still hold (live safety)
1. **No stranded dark.** When NO mask is held, a gated-off crossing must still clear the drop-window
   blackout and send `manual_blackout_off` exactly as today (byte-identical no-mask behavior). The
   `_resolve_pending_blackout` owners_remain guard already guarantees this — verify with a test.
2. **Held masks survive a disallowed crossing.** A `breakdown` or `master_switch` owner held across a
   gated-off crossing stays held (no `manual_blackout_off` sent for it); the lasers stay dark until
   the owner's own release path fires (`smart_rearm.py:244/268-277`, `state_manager.py:3797`).
3. **Allowed-crossing path unchanged.** The `reason="drop_crossing"` success path
   (`laser_executor.py:247-248`) is not touched; allowed crossings still preserve masks.
4. **Full-teardown callers unchanged.** `reset_runtime_state`, `laser_director_disabled`, and
   `smart_rearm_state_cleared` still call `clear_pending_blackout` and still release all masks.
5. **No double-off / no leak.** After a gated-off crossing with a held mask, the later owner release
   must send exactly one `manual_blackout_off` (because `_blackout_pending_for_drop_window` is now
   False and `still_dark` reflects only the remaining owner — `laser_executor.py:333-341`).
6. Push-loop stays non-blocking; no new socket/MIDI/file/subprocess I/O on the tick path.

## Part D — Tests
Pure executor-level seam (no files/subprocess), using the existing `_FakeMidiOutput` +
`_make_config(smart_drop_mode="blackout_mask")` harness in `tests/test_laser_executor_lifecycle.py`
(see `TestLaserBlackoutEquivalence`, `tests/test_laser_executor_lifecycle.py:297` onward). Add a new
`TestSmartNetMaskPreservation` (or extend the blackout class):

1. **Mask survives gated-off clear.** `hold_blackout_mask("master_switch")`; arm a drop-window
   blackout (`trigger_blackout_on(ctx)` or set `_blackout_pending_for_drop_window = True` via the
   public arm path); call `clear_drop_window_blackout(reason="smart_drop_crossing_without_drop_decision")`.
   Assert: `status()["blackout_mask_owners"]` still contains `"master_switch"`;
   `status()["blackout_pending_for_drop_window"]` is `False`; and **no** `manual_blackout_off`
   (note == `manual_blackout_off.note`) was sent to the fake backend during the call.
2. **No-mask case unchanged (no stranded dark).** With NO owner held, arm the drop-window blackout,
   call `clear_drop_window_blackout`; assert exactly one `manual_blackout_off` IS sent and
   `_blackout_pending_for_drop_window` is `False`. This must match today's `clear_pending_blackout`
   no-mask result.
3. **Contrast / regression.** `clear_pending_blackout` with a held `"breakdown"` owner STILL releases
   it (owner gone, off sent) — proving Task 1 did not change the existing API.
4. **Clean later release.** After test 1, `release_blackout_mask("master_switch")` sends exactly one
   `manual_blackout_off` (no double-off), confirming invariant C5.
5. (Optional, if cheap) An integration check that a gated-off crossing reason reaches the executor as
   `post_drop_cycle`/`drop_cycle` (not `drop_crossing`) so the SM net — not the executor — owns this
   clear, mirroring the existing `test_gated_off_crossing_executor_defers_clear_to_sm_net`.

## Part E — Acceptance (definition of done)
- [ ] `clear_drop_window_blackout` added as a thin wrapper over `_resolve_pending_blackout`; no other
      executor blackout/mask method changed.
- [ ] Only the SM-net gated-off call site (`state_manager.py:~3859`) switched; the three full-teardown
      callers untouched.
- [ ] New tests (D1–D4) present and green; no test modified to make this pass.
- [ ] `python3 -m unittest discover tests` green (report the total; baseline is 2256 OK).
- [ ] `python3 -m unittest tests.test_laser_executor_lifecycle tests.test_smart_transitions` green.
- [ ] AGENTS.md §8 hard checks green (`check_docs_metadata.py`, `check_agent_contracts.py`,
      `check_docs_drift.py`); `python3 tools/check_laser_midi_sync.py` exits 0 on the live config;
      `git diff --check` clean.
- [ ] `docs/subsystems/laser.md` updated: note that a gated-off Smart-Drop crossing now preserves held
      breakdown/master_switch masks (it resolves only the drop-window pending). Bump that card's
      `last_verified_commit`. Update the `laser` change-contract docs list if required by
      `docs/agents/change_contracts.yml`.
- [ ] `docs/plans/active/chorus_drop_cycling_spec.md` C2 note updated to "resolved" (the mask teardown
      on disallowed crossings is fixed), or a one-line pointer to this spec added.

## When you finish
- Commit per task (Task 1, Task 2, tests, docs) with real messages, e.g.
  `fix: SM-net gated-off crossing preserves held blackout masks (C2)`.
- Report back: the discover-tests total, the four blackout assertions' results, confirmation that the
  three full-teardown callers were left unchanged, and `git diff --check` clean.

---

## Pre-handoff checklist status (Claude self-review before Codex)
1. **Claims labeled** — yes; every Part A claim is [confirmed] against HEAD `b2ce63d`.
2. **Verified against CURRENT code** — yes; all file:line re-read this session (executor blackout
   methods, SM-net block, mask owners + release paths, config breakdown_scene).
3. **Pending-state guard** — the two pending-state fields are `_blackout_pending_for_drop_window` and
   `_mask_owners`; the fix handles both (clears pending, respects owners). No other tick-pending field
   shares this note.
4. **Mode-transition cleanup** — no new state field is introduced, so there is nothing new to clean up
   on idle/scripted/autoloop/stop/resume transitions. The existing full-teardown callers (reset/
   disable/smart_rearm) are explicitly preserved.
5. **Third-party API completeness** — N/A; MIDI message path unchanged. The new method only re-invokes
   the existing `_resolve_pending_blackout` → `self._backend.trigger(manual_blackout_off, ...)`.
6. **Cross-checked against existing code** — the wrapper reuses the canonical resolver and the
   `owners_remain` guard already used by `on_tick` (`laser_executor.py:104-105`) and the
   `drop_crossing_success` path; the SM-net reason string is preserved verbatim.
7. **Pure-function test seam** — yes; executor blackout state is unit-testable via `_FakeMidiOutput`
   with no files/subprocess (existing `TestLaserBlackoutEquivalence` proves the harness).
8. **Live safety explicit** — Part C: no stranded dark, masks survive, allowed path unchanged, full-
   teardown callers unchanged, single off / no leak, push loop non-blocking.
9. **Adversarial self-review** — attacked:
   - *"Could the mask now strand dark?"* No — both owners have independent release paths
     (`smart_rearm.py:244/268-277`, `state_manager.py:3797`); the SM-net release was redundant.
   - *"Could the drop-window blackout now strand on?"* No — `_resolve_pending_blackout` still clears
     the pending flag and sends off when no owner remains (invariant C1).
   - *"Double-off when the owner later releases?"* No — pending is False by then, so `still_dark`
     reflects only the remaining owner; exactly one off (invariant C5, test D4).
   - *"Did we change the breakdown case?"* The fix covers it, but it was not a feature regression
     (breakdown_scene always configured → Priority-8 breakdown → SM net identical pre/post). Stated.
