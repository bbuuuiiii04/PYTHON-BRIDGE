---
doc_status: current
truth_level: operator-authoritative target behavior
last_verified_commit: cc895f8
last_verified_date: 2026-07-04
validation_scope: Package 2 behavior contract implemented and software-tested; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Palette Control Authority (Stream Deck surface)

Status: AUTHORITATIVE TARGET BEHAVIOR; Package 2 is implemented/software-tested under
`streamdeck_palette` in `docs/agents/change_contracts.yml` (operator hardware validation pending).

This document defines how the operator's Stream Deck color-control surface is
expected to behave. Behavior that differs from this document is a regression
unless this document is intentionally updated. Code-grounded design detail and
file:line evidence live in `docs/plans/active/streamdeck_palette_control_design_spec.md`;
this document is the intent contract that survives implementation drift.

Sibling authorities: `drop_presentation_authority.md` (which fixtures fire per
drop), `laser_color_authority.md` (laser color), `laser_blackout_authority.md`
(blackout ownership).

## Meaning

The Stream Deck is the operator's live hands on color and room state. The
governing principle everywhere on this surface:

**Manual input always wins. Automation may propose; the operator disposes.**

Lock freezes only *automatic* color selection — it never blocks the operator's
own input. No pad on this surface can be overridden, cleared, or repurposed by
automation.

## Vocabulary

| Term | Meaning |
| --- | --- |
| palette | A named color family in the LED color engine's config (`blue_cyan`, …). Identity is the name string. |
| queue | Stage a palette to take effect at the next track boundary. |
| override | Apply a palette to the current track now, held for the rest of that track. |
| fade | The beat-synced blend an override uses to arrive (never a hard jump). |
| lock | Pin the active palette across track boundaries until unlocked. |
| `white_sand` | The manual-only white/off-white palette. Automation can never select it. |
| mute | A per-fixture kill toggle (LED mute, Laser mute). Mixer semantics: lit = muted. |
| Laser Solo | The one-shot "next true drop is lasers-only" pad (contract in `drop_presentation_authority.md`). |
| Rainbow mode | The toggled section-mapped color scheme (white breakdowns, rainbow drops). |
| feedback file | The bridge-written state file the deck script renders pads from. |

## The Deck Surface

15 keys, 3×5, MIDI channel 3. Pad→bridge notes are bridge-assigned and must
stay outside the 36-50 range SoundSwitch-learned static looks use.

| Row | Keys | Pads |
| --- | --- | --- |
| Top | 0-4 | The 5 auto palettes, in config order. |
| Middle | 5-9 | `white_sand` · lock · LED mute · Laser mute · Laser Solo. |
| Bottom | 10-13, 14 | Static looks filling left→right by note; key 14 = Rainbow mode. |

The layout is **pinned**. Pads never auto-rearrange when new SoundSwitch
bindings are authored (the old "waterfall" fill is retired). Static looks
beyond 4 are dropped with a visible log line, never silently.

## Palette Selection Rules

1. Pressing a palette pad **queues** that palette: it takes effect at the next
   track boundary. Queuing replaces any previously queued palette.
2. Pressing the pad of the palette that is **already queued** overrides now:
   the palette applies to the current track, arriving as a **fade** (rule 5),
   and holds for the rest of that track (no drop-snap, no drift).
3. An override **consumes the queue**. A stale queue must never re-apply the
   same palette at the following boundary as a side effect.
4. There is no double-press timer. The queue-then-override gesture is pure
   state: the "second press window" lasts until the queue is consumed at a
   boundary or replaced by another pad.
5. **Fade contract:** an override fades from the current color position to the
   target, beat-synced, completing at the next phrase anchor or 32 beats,
   whichever is sooner (unknown anchor → the 32-beat cap alone). The blend must
   travel inside the engine's allowed hue space — it must never transit the
   excluded yellow/orange band. A track boundary arriving mid-fade cancels the
   fade; boundary logic proceeds normally.
6. During a fade: another override (including `white_sand`) restarts the
   blend from the current blended position toward the new target; a queue
   press stores the queue **without touching the fade**; lock follows rule 9
   (the fade completes, then pins). No manual action ever hard-jumps the
   color.
7. **Lock** pins the currently-active palette across track boundaries: it
   blocks dwell re-picks, drift, and drop-snap.
8. **A queued palette applies at the boundary even while locked, and the lock
   transfers to it** (stays locked on the new palette until unlocked). This is
   operator law: the queue is manual input, and manual input outranks lock.
9. An override likewise applies under lock; the lock remains set on the new
   palette. Lock pressed mid-fade lets the fade complete, then pins the target.
10. **Unlock does not trigger an immediate re-pick.** The current palette
    stays; automatic selection resumes at the next boundary.
11. `white_sand` follows every rule above identically. It differs only in that
    automatic selection can never choose it (manual-only, weight zero). Its
    LED color is borrowed from the Dune Sand twinkle look's palette
    (operator 2026-07-04; Warm Ivory 255,235,200 as the fixed value, sand
    siblings as calibration alternates) — Template Lab may refine on-device.

## Mute Pads

12. LED mute toggles the Govees dark / back. Laser mute toggles the laser
    frame dark / back. Together they compose the three room states by hand:
    LED-only, LED+laser, laser-only.
13. Mutes are **absolute**: all automation (palette engine, drop presentation,
    Rainbow mode) keeps running underneath but cannot make a muted fixture
    emit, and no automatic release may clear a manually-held mute. The single
    exception is **input-health policy on the pad path itself** (operator
    ruling 2026-07-04): if the pad input worker/device dies mid-hold, BOTH
    mutes release — the laser mute via the existing overlay-trust gate, and
    the LED mute deliberately mirroring it for consistency. Re-engaging after
    recovery is a fresh press. Automation is never such a release.
14. Each mute is its **own owner** in the relevant blackout/blackout-like
    system. An automatic restore (e.g. a solo window ending) releases only its
    own hold and can never release the operator's (see
    `laser_blackout_authority.md`).
15. Laser mute rides the existing manual laser-blackout ownership (a second
    manual owner beside the laser-pad-web note). It must never be implemented
    as a new, parallel blackout mechanism.

## Rainbow Mode

16. Rainbow mode is a toggle. While on, color is remapped by phrase role:
    breakdowns and buildups render `white_sand`; grooves, drops, and post-drops
    render **rainbow** (LEDs: full hue wheel, deliberately including the
    yellow/orange band the journey palettes exclude; lasers: the fixture's
    color-change effect families, per `laser_color_authority.md`).
17. Rainbow mode changes **colors, not presentation**: the drop presentation
    ladder, mutes, Solo, and damper all still apply. A LEDs-only drop stays
    LEDs-only, just rainbow.
18. While on, the palette, lock, and `white_sand` pads are inactive (dimmed;
    presses acknowledge but do nothing). The palette journey — including any
    in-flight fade, which completes instantly at freeze — is frozen untouched
    and resumes exactly where it was when the mode toggles off. Track
    boundaries during Rainbow advance no journey state: dwell, re-picks, and
    drop-snap are suspended, and **a queued palette waits, applying at the
    first boundary after Rainbow ends** (operator 2026-07-04).
19. On scripted tracks, Rainbow mode affects only the breakdown/buildup LED
    windows that render there (effectively: white). Lasers stay authored.
20. The `white_sand` ritual (if ever enabled) cannot trigger while Rainbow
    mode is on.

## Feedback & Iconography

21. Pad state flows one way: **bridge → feedback file → deck script renders.**
    The deck script contains no lighting logic and never decides state; it
    draws what the file says and sends notes.
22. Universal state grammar on every pad: **bright = engaged/on, dim =
    available/off, pulsing = pending/armed, brief white flash = press
    acknowledged.**
23. Color is rationed to meanings: **red only ever means "a fixture is
    muted"; amber only ever means solo.** Palette pads wear their own colors;
    the lock glyph is drawn over the currently-active palette's color so the
    operator sees what is locked.
24. A pulsing Laser Solo pad always means "a solo is pending — press to
    cancel," regardless of which tier armed it.
25. Feedback-file failure is cosmetic only: if the file is missing, stale, or
    unwritable, lighting behavior is unaffected; palette/control pads render
    blank; static-look pads keep working; the fault is logged once, not
    per-tick.

## Non-Inputs / Non-Goals

- No audio analysis, no energy model, and no randomness drive anything on this
  surface.
- The deck script never emits on the lasers' MIDI channels.
- The bridge's 200 Hz push loop gains no file, HID, or network I/O from this
  feature: feedback-file writes happen on a dedicated writer thread, and pad
  input arrives through the existing MIDI input worker as BridgeEvents.
- The LED hue-band invariant (no yellow/orange) holds everywhere except inside
  Rainbow mode's rainbow sections, where the full wheel is the point.
- Engine state is owned by StateManager; the deck and web tools reach it only
  through BridgeEvents/runtime commands.

## Observability

Runtime status must expose: current palette, queued palette, lock state,
fade-in-progress, LED mute, laser mute, solo arm state (with arming source),
and rainbow mode. The feedback file carries the same facts plus per-pad
display state and a monotonic sequence number.

## Required Behavior Tests

1. Queue → boundary applies it; queue → same-pad press → override fades now
   and the queue is consumed (no re-apply at the next boundary).
2. Fade completes at the phrase anchor; caps at 32 beats without an anchor;
   never leaves the allowed hue space; cancels cleanly at a track boundary.
3. Queue while locked: applies at the boundary, lock transfers, stays locked.
4. Override while locked: applies, lock stays. Unlock: no immediate re-pick.
5. `white_sand` is never chosen by dwell, drift, drop-snap, or shift across a
   large simulated session; `set`/`queue` reach it.
6. Mute toggles: automation cannot un-mute; solo restore cannot clear a manual
   mute; input-path loss releases both mutes (the rule-13 policy exception);
   mute pads compose all three room states.
7. Rainbow on/off: journey (and an in-flight fade) freezes/restores exactly;
   a queued palette survives Rainbow and applies at the first post-Rainbow
   boundary; palette pads inert while on; role mapping correct on scripted vs
   autoloop.
8. Feedback file: atomic writes, correct state transitions for every pad, and
   graceful blank-render on missing/stale file.

## Implementation Notes

Implemented Package 2 home: coordinator + feedback writer in `led_palette_control.py`;
engine changes (fade state, queue/lock reorder, `white_sand` + rainbow palette
types) in `led_color_engine.py`; events in `models.py`; commands in
`runtime_status.py`; pad bindings via bridge config into the existing MIDI
input group; deck rendering in `streamdeck/streamdeck_midi.py`. Laser Solo and
drop-presentation learning remain later-package design intent.
