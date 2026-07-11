---
doc_status: current
truth_level: operator-authoritative target behavior
last_verified_commit: b16792a
last_verified_date: 2026-07-07
validation_scope: Package 1 re-wire implemented and software-tested in current worktree; no live or hardware validation implied. Reconfirmed unchanged by the 2026-07-07 laser-color menu/follow-LED layer — that feature only sets CH8/CH9 on the injected snapshot and still loses to blackout/emergency downstream.
---

# Laser Blackout Authority

Status: AUTHORITATIVE TARGET BEHAVIOR; PACKAGE 1 RE-WIRE IMPLEMENTED / SOFTWARE-TESTED / HARDWARE-UNVALIDATED

This document defines who may hold the lasers dark, who may release them, and
what can never be un-darkened by automation. Behavior that differs from this
document is a regression unless this document is intentionally updated.
Code-grounded design detail lives in
`docs/plans/active/laser_color_engine_design_spec.md` Part C. This is the
live-critical contract on this feature set: hold it to the highest scrutiny.

## Meaning

Blackout is the absolute override on the laser frame: when any blackout is
held, the frame is all-zero regardless of what any renderer, color engine, or
static look wants. The 2026-07-07 laser-color menu/follow-LED layer does not
change this — it only writes CH8/CH9 onto the injected color snapshot, which
still sits beneath the blackout/emergency gate and static-override layering.
There are exactly **two blackout owner systems**, and the
old SoundSwitch "release-everything undoes someone else's blackout" bug must
remain structurally impossible:

| System | Owners | Purpose |
| --- | --- | --- |
| **Manual** — MIDI-binding refcount | laser-pad-web note; the deck's Laser mute pad | The operator holding the room dark. |
| **Smart** — executor owner set | `breakdown`, `master_switch`, `pre_chorus`, smart-drop pre-window | Automatic transition covers. |

**Separation is by owner, not by MIDI note.** The historical notes collide in
wire terms (a numbering-convention artifact); nothing may ever rely on note
distinctness for safety.

## Rules

1. The frame-level blackout is the **OR of both systems**: it is held while
   ANY manual binding or ANY smart owner holds it, and clears only when ALL
   holders have released.
2. There is **one writer** of the frame-level mask state. Independent direct
   writes that a periodic writer would overwrite within a tick are forbidden —
   the OR happens at the single writer, or through a per-owner API with
   equivalent semantics.
3. **A manual hold survives everything automatic.** Track load, stop, resume,
   master change, smart-drop resolution, solo-window restore, presentation
   fail-opens, personality resets, pack reload, SoundSwitch appearing — none
   of these may release a manually-held blackout. Only the operator's own
   release (or input-health policy on the manual system itself) clears it.
4. **Smart owners are wiped at lifecycle boundaries by design** (track load,
   stop, resume, master change): transition covers end when the transition
   ends. The unconditional release-all path is a smart-side mechanism only —
   **it must never be pointed at, or merged with, the manual system.**
5. **The manual pad path must never route through the smart owner set** (it
   would be wiped at every track load). The deck's Laser mute is a second
   manual *binding*, joining the existing manual refcount — never a new,
   parallel blackout mechanism.
6. **Owner bookkeeping must not depend on MIDI-send success.** Holding an
   owner latches the owner, full stop; whether a note also goes out is a
   backend detail. (The historical pack-mode failure — owners silently
   discarded when the backend rejected the note — is the named regression
   this rule exists to prevent.)
7. Smart-drop/breakdown blackout actuates at the **frame level** (no MIDI
   note required); its timing knobs (pre-window beats, breakdown caps) stay in
   the decision layer and are never baked into the pack or the actuation.
8. The SoundSwitch-present suppression path may clear the bridge's own
   automatic output state, but must not be able to silently erase a live
   manual hold's intent.
9. **Base suppression is not blackout.** The drop presentation policy's
   `leds_only` laser-dark uses selection/base withholding, which a
   manually-held static override survives; it must never touch either
   blackout system or their owners (`drop_presentation_authority.md`).
10. Emergency masking, pack-disabled zeroing, and shutdown zeroing outrank
    everything here, unchanged.
11. Priority, top to bottom: **emergency/blackout → static-override layers →
    engine color → base render.** Nothing below a layer may defeat anything
    above it.

## Required Behavior Tests

1. **The survival matrix (the core test):** with a manual hold active, drive
   every automatic release/reset path — track load, stop, resume, master
   change, smart-drop resolve, breakdown release, solo-window restore, pack
   reload, SS-present transition — and assert the frame stays ZERO throughout,
   releasing only on the manual release.
2. Two manual holders (pad web + deck mute): releasing one keeps the frame
   dark; releasing both clears it.
3. Smart hold + manual hold overlapping: smart release does not clear the
   frame; manual release with a smart owner still held does not clear it.
4. Pack-mode owner latch: holding with a rejecting backend still latches the
   owner and still drives the frame dark.
5. Single-writer discipline: a smart-side hold set between writer passes is
   not lost to the next pass (the OR is stable across ticks).
6. Base suppression during a held static override: the override still renders;
   blackout owners untouched; blackout still zeroes both.

## Implementation Notes

Package 1 is implemented in software: executor owner latching no longer depends
on backend trigger success, and the executor's owner state is ORed into the
existing single mask-writer site in StateManager's pack driver. The focused
software regression is `tests/test_laser_blackout_rewire.py`. Live laser,
SoundSwitch, MIDI, DMX, Enttec, Rekordbox, LED, and Govee behavior remains
hardware-unvalidated until an operator-approved live run.

**AWR-170 (D.2) — the `pre_chorus` smart owner.** Lasers black out for
`f2.pre_chorus_laser_beats` (example 4; absent-key = 0 = off) before every chorus
phrase start. Chorus starts are the RAW anlz-drop markers (uncollapsed — the
AWR-131 collapse only merged drop *decisions*), so a chorus mid-drop-section that
F2's per-drop transition window never darkens still earns its own laser breath.
`smart_phrasing.update()` arms/clears the window on rising/falling edges (a plan
input `pre_chorus_beats`, gated to 0 by StateManager when F2 is off / no plan /
scripted); `smart_rearm._pre_chorus` holds/releases the `pre_chorus` owner. The
owner is released on the marker crossing AND on any leaked exit
(`not pre_chorus_window_active`) — scrub/loop/skip — the AWR-154 latched-dark
guard; the `OutputState.pre_chorus_active` latch is cleared alongside
`breakdown_active` on the shared reset paths, and `_release_all_masks` clears the
owner itself at every lifecycle boundary. Held-static + pre_chorus window ⇒ the
static ducks dark for the window and restores on release (Rule 9 is base
suppression; this is a real blackout owner, so mask precedence applies —
`tests/test_state_manager_pack_driver.py::...pre_chorus_then_restores`). Software
seams: `tests/test_laser_tier_prechorus.py`.

**AWR-206 — relaxed arm gate for the smart-drop pre-window blackout**
(software-tested / hardware-unvalidated; STAGED — activates at the operator's
next bridge restart). Fix round: the first attempt put the relaxed arm inside the
executor's `auto_gate_blocked` branch, which is UNREACHABLE in production — the
`LaserDirector` returns an idle decision at its `autoloop_ready` gate one layer
*above* the executor's automatic-gate check, so that branch never carries a live
arm signal (SOL review `docs/research/sol_awr206_review_2026_07_11.md`).

This changes only WHEN the 4-beat smart-drop pre-drop blackout *arms*; it changes
none of the survival/release rules above. Scene MIDI still fires only behind the
strict `_passes_automatic_gates` (which requires `autoloop_ready`), and no
automatic scene is ever selected on the arm path. The fix carries blackout arm
intent across the director's readiness early return: when `autoloop_ready` is
False the director still returns its `autoloop_not_ready` idle decision (empty
scene) but tags it `blackout_arm=True` (`laser_director.py` priority-7). The
executor's idle/no-scene guard then arms the manual blackout note when
`should_arm_blackout` (arm signal AND `role in _AUTO_ROLES` OR
`decision.blackout_arm`) and the relaxed gate `_passes_blackout_gates` = the
strict gate MINUS `autoloop_ready` (still requires `playing`,
`active_track_loaded`, not `position_stale`, `lighting_mode == "autoloop"`,
`scripted_id == 0`). The manual blackout command (`manual_blackout_on`) is
config-fixed, so this path needs no scene mapping. Reason: at the pre-drop instant
during real mixing the SoundSwitch autoloop is normally mid-re-arm (the
clear-1-beat-before-reload re-anchor), so `autoloop_ready` was False and the
strict gate silently ate the blackout — the note itself never needed a
render-ready autoloop, only a genuinely live deck. Both arm signals
(`smart_drop_blackout_arm`, `smart_phrasing_blackout_arm`) take the same path.
The pre-window latch (`_blackout_pending_for_drop_window`) and every release path
(drop crossing, the StateManager no-drop-decision safety net at
`state_manager.py:4882-4893` for when the autoloop is still not ready at the
crossing, `_release_all_masks`, `clear_pending_blackout`, lifecycle resets,
shutdown zeroing) are untouched, so a blackout armed under churn releases exactly
as before (fail-open beats fail-dark). The arm signal is level-held on every
200 Hz push tick while the drop stays armed, so the relaxed-gate skip reason logs
at INFO throttled to once per changed failing-condition tuple (was an unreachable
DEBUG line). Software seams: `tests/test_laser_executor.py`
(`test_integrated_director_executor_arms_blackout_under_autoloop_churn` — the real
director→executor chain, fails at pre-fix HEAD; `test_blackout_arms_under_autoloop_churn_*`;
`test_relaxed_gate_blocks_arm_on_each_failing_subcondition`;
`test_blackout_arm_idempotent_across_idle_churn_ticks`;
`test_drop_crossing_decision_resolves_blackout_armed_under_churn`;
`test_state_manager_safety_net_resolves_blackout_armed_under_churn`;
`test_blackout_skip_logs_failing_subconditions_at_info`;
`test_blackout_skip_log_throttled_to_once_per_failing_tuple`).
