---
doc_status: current
truth_level: operator-authoritative target behavior
last_verified_commit: 12ffb09
last_verified_date: 2026-07-04
validation_scope: Package 1 re-wire implemented and software-tested in current worktree; no live or hardware validation implied
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
static look wants. There are exactly **two blackout owner systems**, and the
old SoundSwitch "release-everything undoes someone else's blackout" bug must
remain structurally impossible:

| System | Owners | Purpose |
| --- | --- | --- |
| **Manual** — MIDI-binding refcount | laser-pad-web note; the deck's Laser mute pad | The operator holding the room dark. |
| **Smart** — executor owner set | `breakdown`, `master_switch`, smart-drop pre-window | Automatic transition covers. |

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
