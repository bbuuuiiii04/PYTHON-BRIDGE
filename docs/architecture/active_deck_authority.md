---
doc_status: current
truth_level: operator-authoritative target behavior
last_verified_commit: ab2bc15
last_verified_date: 2026-06-28
validation_scope: behavior contract; implementation and hardware validation pending
---

# Active Deck Authority

Status: AUTHORITATIVE TARGET BEHAVIOR

This document defines how the bridge is expected to choose `active_deck`.
After the fader-dominance feature is implemented, behavior that differs from
this document is a regression unless this document is intentionally updated.

Current code does not yet implement this full contract. Current code still sets
`OutputState.active_deck` from `MASTER_CHANGED` events and playing-only mirror
auto-switch paths. That is the behavior this feature replaces.

## Meaning

`active_deck` means the show-driving audible deck.

The louder or audibly dominant deck drives everything:

- SoundSwitch OS2L
- SoundSwitch pack mode
- lasers
- LEDs/Govee
- scripted/autoloop mode
- beat/BPM/elapsed output
- runtime heartbeat/status

Rekordbox master is retained separately as `rb_master_deck`. It is not the
primary show authority when mixer authority is valid.

## Vocabulary

| Term | Meaning |
| --- | --- |
| `active_deck` / `show_deck` | Deck currently driving bridge outputs. |
| `rb_master_deck` | Rekordbox-reported master deck. |
| mixer authority | Decoded mixer state for Deck 1 and Deck 2. |
| eligible deck | A deck that is playing and has an audible upfader. |
| fader `down` | Decoded physical silent/down position from RE evidence. |
| fader `audible` | Decoded physical audible-but-not-top position from RE evidence. |
| fader `top` | Decoded physical top position from RE evidence. |
| bass `neutral` | Decoded physical 12 o'clock bass EQ position from RE evidence. |

The behavior contract uses physical decoded labels, not raw memory numbers.
Raw value mapping belongs to the Rekordbox reverse-engineering layer.

## Authority Inputs

The resolver uses only:

- Deck 1 and Deck 2.
- deck playing state.
- upfader decoded position.
- bass EQ decoded position.
- `rb_master_deck` only for the tie/fallback cases in this document.

Decks 3 and 4 are not authority candidates. Any SoundSwitch Deck 3/4 use remains
an internal routing detail for existing SoundSwitch/autoloop/scripted behavior.

## Non-Authority Inputs

These must not affect active-deck authority in the first implementation:

- real audio loudness
- crossfader
- trim/gain
- channel mute
- mid EQ
- high EQ
- unrelated effects
- filter knob

Mid/high EQ may be decoded for future visibility, but they do not decide
`active_deck`. The filter knob may be decoded for the LED overlay follow-up, but
it does not decide `active_deck`.

## Eligibility

A deck is eligible only when it is both playing and audible by upfader position.

Rules:

- playing with fader `down` is not eligible.
- fader up while paused/not playing is not eligible.
- bass/EQ cannot make a fader-down deck eligible.
- track metadata is not required to select `active_deck`.
- if selected metadata is missing, downstream outputs that need it must fail
  safe or wait through existing metadata behavior.

## Valid Mixer Authority Resolver

When mixer authority is valid:

1. If no deck is eligible, the show is idle after the stability behavior below.
2. If exactly one deck is eligible, that deck becomes `active_deck`.
3. If both decks are eligible and exactly one fader is `top`, the top-fader deck
   wins.
4. If both decks are eligible and both faders are `top`, compare bass EQ.
5. If both top-fader decks have unequal bass positions, the higher bass position
   wins.
6. If both top-fader decks have equal bass and current `active_deck` is still
   eligible, hold current `active_deck`.
7. If both top-fader decks have equal bass and there is no current active deck,
   use `rb_master_deck`.
8. If both bass EQs are `neutral`, `rb_master_deck` is the preferred tie-break,
   subject to stability/no-flicker behavior.
9. If both decks are eligible and neither fader is `top`, hold current
   `active_deck` if still eligible.
10. If both decks are eligible, neither fader is `top`, and there is no current
    active deck, use `rb_master_deck` if eligible.
11. If exactly one eligible deck remains in a neither-top fallback state, use
    that deck.
12. If none are eligible, idle.

## Stability

Any `active_deck` change requires the candidate to remain stable first.

The exact timing is unknown until Rekordbox mixer values are decoded and
observed. The behavior contract must not invent numeric thresholds.

Rules:

- During the stability wait, hold the current active deck only if it remains
  playing and audible.
- If current `active_deck` becomes non-audible, go idle until a candidate wins
  stability.
- Bass-swap changes use the same stability rule.
- Do not switch on momentary in-between reads during fader or bass movement.

## Rekordbox Master

`MASTER_CHANGED` updates `rb_master_deck`.

While mixer authority is valid, `MASTER_CHANGED` must not directly set
`active_deck`. Rekordbox master wins only the tie cases described above.

Status and logs must not call audible authority "master". Use `active_deck` or
`show_deck` for audible authority and `rb_master_deck` for Rekordbox master.

## Legacy OSC Active-Deck Input

OSC `/bridge/active_deck` and `/bridge/bridge_deck` are historical
TimecodeLink-era inputs. They must not bypass the fader/EQ resolver.

If retained, they are legacy/debug/fallback inputs only. They are not valid
mixer authority.

## Old Mirror Auto-Switch

Playing-only mirror auto-switch is removed as an independent authority path.

While mixer authority is valid:

- mirror/other-deck playing state alone cannot switch authority.
- deck switching goes through the dominance resolver.
- playing state only affects eligibility.

## Invalid Mixer Authority

Dominance requires decoded upfader and bass authority state for both Deck 1 and
Deck 2. If either deck's required mixer state is missing or invalid, mixer
authority is invalid.

Invalid mixer authority is a fault, not normal operation.

When mixer authority is invalid:

- fail visibly through status/logs/menubar.
- temporarily use old RB-master behavior.
- keep trying to reacquire valid mixer authority.
- allow old RB-master behavior to change `active_deck`.
- mark the reason as `mixer_invalid_fallback`.

When mixer authority becomes valid again:

- discard/suppress old playing-only auto-switch authority.
- return immediately to fader dominance, subject only to the normal stability
  rule.
- do not spam logs.

Log only meaningful changes:

- valid -> invalid
- invalid -> valid
- active deck changed
- authority reason changed

## Mode Behavior

Lighting mode follows selected `active_deck`:

- active scripted deck -> scripted mode
- active unscripted deck -> autoloop mode
- no active audible deck -> idle

Scripted tracks obey fader dominance. Autoloops obey fader dominance. A
non-active scripted deck must not keep driving bridge outputs in the background.

## Filter Overlay Follow-Up

The filter knob is a near-term LED/Govee overlay follow-up, not active-deck
authority.

Rules:

- decode filter after upfaders and bass if practical.
- filter overlay responds only to the current `active_deck`.
- non-active deck filter movement is ignored.
- filter overlay affects LEDs/Govee only.
- filter overlay does not affect lasers, SoundSwitch, scripted/autoloop mode,
  or `active_deck`.
- exact LED visual behavior is unresolved.
- unresolved filter visual design must not block fader dominance.

## Observability

Status must expose:

- `active_deck` or `show_deck`
- `rb_master_deck`
- mixer authority validity
- decoded Deck 1 and Deck 2 upfader positions
- decoded Deck 1 and Deck 2 bass EQ positions
- concise active-deck authority reason

Suggested reason strings:

- `only_audible`
- `fader_top`
- `bass_dominance`
- `rb_master_tie`
- `hold_current`
- `idle_no_audible`
- `mixer_invalid_fallback`

Heartbeat must not report `master = active_deck` after this feature lands.

## Required Behavior Tests

The implementation must include direct resolver coverage for these scenarios:

1. Deck 1 playing, fader down, not master. Deck 2 master, fader up, not playing.
   Expected: no audible active deck; do not auto-promote Deck 1.
2. Two tracks playing, both faders top, both bass neutral. Expected:
   `rb_master_deck` wins.
3. Two tracks playing, both faders top, non-master bass low, master bass
   normal/full. Expected: master remains active.
4. Bass swap: non-master bass rises and master bass lowers. Expected:
   non-master becomes active after stable dominance.
5. Deck 1 master fader top, Deck 2 non-master fader down. Deck 2 fades up to
   top: Deck 1 stays active while both are top/equal. Deck 1 fader then drops
   below top: Deck 2 becomes active.
6. Missing/invalid mixer authority falls back visibly to old RB-master behavior.
7. Mixer authority recovery returns to fader dominance.
8. Reason/status changes are emitted without per-tick log spam when cheap to
   test.

## Current Code Mismatch To Replace

[confirmed] Current `Ev.MASTER_CHANGED` goes directly to
`StateManager._on_master_changed`, which writes `self._os.active_deck`.

[confirmed] `RBStateReader` currently emits `Ev.MASTER_CHANGED` when the direct
master byte changes.

[confirmed] OSC `/bridge/active_deck` currently enqueues `Ev.MASTER_CHANGED`
when direct master is not ready.

[confirmed] Current push-loop paths can auto-promote the mirror deck using
playing state alone.

[confirmed] Current resume correction can also write `self._os.active_deck`
directly when correcting an empty-deck mismatch.

[confirmed] Current heartbeat reports `"master": active_deck`.

These current behaviors are implementation targets for replacement or
compatibility fallback under this contract.
