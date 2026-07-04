---
doc_status: current
truth_level: operator-authoritative target behavior
last_verified_commit: fce1169
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
| Middle | 5-9 | `white_sand` · lock (v1; **dark/reserved in v2** — the lock pad is retired, lock rides the palette long-press) · LED mute · Laser mute · Laser Solo. |
| Bottom | 10-13, 14 | Static looks filling left→right by note; key 14 = Rainbow mode. |

The layout is **pinned**. Pads never auto-rearrange when new SoundSwitch
bindings are authored (the old "waterfall" fill is retired). Static looks
beyond 4 are dropped with a visible log line, never silently.

## Palette Selection Rules

> **GESTURE v2 (operator-approved 2026-07-04 evening; NOT YET IMPLEMENTED —
> AWR-121, `docs/plans/active/palette_gesture_v2_spec.md`).** Rules 1-4 and
> 7-10 below define the approved v2 surface. The implemented v1 surface
> (tap-queue / second-tap-override / dedicated lock pad, landed in Package 2)
> remains the correct LIVE behavior until the v2 package lands; divergence
> from v2 is not a regression until then.

1. **Tap** (press shorter than `long_press_s`, default 0.5 s) toggles the
   queue: tap queues that palette for the next track boundary (replacing any
   other queued palette); tapping the **already-queued** palette unqueues it.
   Tapping the **locked, active** palette unlocks it (rule 9). There are no
   multi-tap windows and no double-press gestures — a single press's duration
   is the only timing input, measured per press.
2. **Long-press** (≥ `long_press_s`) is **take-and-hold**: the palette applies
   to the current track NOW, arriving as a fade (rule 5), AND locks (rule 7).
   Long-press on the already-active locked palette is an idempotent no-op.
   The action fires on release; the pad shows the latch locally at the
   threshold so the operator feels when a hold has become a take.
3. A take-and-hold **consumes the queue**. A stale queue must never re-apply
   at the following boundary as a side effect.
4. The old one-track override is reachable by composition, not a gesture:
   take-and-hold, then tap the same pad to unlock — the color stays for this
   track and automatic selection resumes at the next boundary (rule 10).
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
7. **Lock** (armed only via long-press take-and-hold in v2 — there is no
   dedicated lock pad) pins the target palette across track boundaries: it
   blocks dwell re-picks, drift, and drop-snap. The lock arms with the
   take-and-hold and pins the fade's target once the fade completes (the
   rule-6 lock-mid-fade behavior, reused).
8. **A queued palette applies at the boundary even while locked, and the lock
   transfers to it** (stays locked on the new palette until unlocked). This is
   operator law: the queue is manual input, and manual input outranks lock.
9. A take-and-hold on another palette likewise applies under lock; the lock
   transfers to the new palette. **Unlock is a tap on the locked, active
   palette's own pad.**
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
    acknowledged.** v2 additions: **a dim palette pad must still be
    unmistakably its palette's color** (dim reduces brightness/value only,
    never hue or saturation — crimson reads red even idle); **the locked
    palette wears a padlock glyph on its own pad**; **during a long-press the
    pad shows the latch locally when the hold crosses `long_press_s`** (the
    deck renders the threshold cue from its own press timing — display only,
    the bridge's own measurement decides the action).
23. Color is rationed to meanings: **red only ever means "a fixture is
    muted"; amber only ever means solo.** Palette pads wear their own colors;
    the lock glyph is drawn over the currently-active palette's color so the
    operator sees what is locked.
24. A pulsing Laser Solo pad always means "a solo is pending — press to
    cancel," regardless of which tier armed it.
25. Feedback-file failure is cosmetic only: if the file is missing, stale, or
    unwritable, lighting behavior is unaffected; palette/control pads render
    blank; static-look pads keep working; the fault is logged once per
    episode (fail and recovery are transitions, never per-tick lines).
26. The deck script never lies by omission about a degraded boot or a heal
    (2026-07-04 incident: a static-only boot printed one plausible `live`
    banner, healed silently, and masqueraded as an input fault): feedback
    lost/restored and any gain/loss of bound keys are logged as transitions
    with the live note range, and a feedback `seq` regression (= bridge
    restart) clears deck-local toggle latches so a stale latch cannot invert
    a static-look press.
27. Silent input loss is a defect class, not a tolerated risk: the deck key
    callback never lets an exception reach the HID library's read thread (it
    only survives `TransportError`), a dead read thread forces a loud
    reconnect, and a wedged main loop (e.g. hung USB write) hard-exits so the
    watcher respawns the script.

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

1. (v2) Tap queues → boundary applies it; tap the queued pad again → unqueued,
   nothing applies at the boundary; tap-queue replaces any other queued
   palette. (v1 until AWR-121 lands: second tap = override, per Package 2's
   shipped tests.)
2. Fade completes at the phrase anchor; caps at 32 beats without an anchor;
   never leaves the allowed hue space; cancels cleanly at a track boundary.
3. Queue while locked: applies at the boundary, lock transfers, stays locked.
4. (v2) Long-press = take-and-hold: fades now, consumes the queue, locks the
   target (mid-fade lock pins on completion); long-press another palette
   transfers the lock; tap the locked active pad → unlocked, color stays, no
   immediate re-pick; sub-threshold release = tap, never a take.
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
