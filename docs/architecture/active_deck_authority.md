---
doc_status: current
truth_level: operator-authoritative target behavior
last_verified_commit: 74febec
last_verified_date: 2026-06-29
validation_scope: behavior contract plus software-tested implementation; live/hardware validation pending
---

# Active Deck Authority

Status: AUTHORITATIVE TARGET BEHAVIOR; SOFTWARE-TESTED IMPLEMENTATION AT `74febec`

This document defines how the bridge is expected to choose `active_deck`.
Behavior that differs from this document is a regression unless this document is
intentionally updated.

Current code implements this contract in software through `active_deck_resolver.py`,
`StateManager`, `RBStateReader`, runtime status, and the Rekordbox 7.2.11 named
mixer offset fields. This is not a live-output or hardware-validation claim.
No bridge restart, live Rekordbox sampling, SoundSwitch, laser, LED/Govee, DMX,
MIDI, Enttec, or physical-output validation is implied by this document.

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
| `rb_master_deck` | Rekordbox-reported master deck, or unknown/unavailable when no current valid direct master read exists. |
| mixer authority | Decoded mixer state for Deck 1 and Deck 2. |
| eligible deck | A deck that is playing and has an audible upfader. |
| fader `down` | Decoded physical silent/down position from RE evidence. |
| fader `audible` | Decoded physical audible-but-not-top position from RE evidence. |
| fader `top` | Decoded physical top position from RE evidence. |
| bass `neutral` | Decoded physical 12 o'clock bass EQ position from RE evidence. |

The behavior contract uses physical decoded labels, not raw memory numbers.
Raw value mapping belongs to the Rekordbox reverse-engineering layer.
Current resolver thresholds, tolerance values, stale windows, and stability time
are implementation policy constants, not RE-proven facts.

## Authority Inputs

The resolver uses only:

- Deck 1 and Deck 2.
- deck playing state.
- upfader decoded position.
- bass EQ decoded position.
- current valid/fresh `rb_master_deck` only for the tie/fallback cases in this
  document.

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

Current implementation decodes Deck 1/2 upfader and LOW/BASS only for authority.
CFX FILTER remains non-authority and is not part of the first runtime status
surface.

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

`rb_master_deck` is usable only when current, valid/fresh, and Deck 1 or Deck 2.
If a rule below says to use `rb_master_deck` while it is unavailable, stale, or
invalid, the bridge must not synthesize Deck 1. It must hold the current eligible
`active_deck` when possible; otherwise it must go idle with a visible
master-unavailable reason until a dominant candidate or valid master appears.

1. If no deck is eligible, the show is idle after the stability behavior below.
2. If exactly one deck is eligible, that deck becomes `active_deck`.
3. If both decks are eligible and exactly one fader is `top`, the top-fader deck
   wins.
4. If both decks are eligible and both faders are `top`, compare bass EQ.
5. If both top-fader decks have unequal bass positions, the higher bass position
   wins.
6. If both top-fader decks have `neutral` bass labels, current valid/fresh
   `rb_master_deck` is the preferred tie-break, subject to stability/no-flicker
   behavior. Neutral-labeled LOW/BASS values are a tie even when their raw
   normalized values differ inside the neutral band.
7. If both top-fader decks have equal non-neutral bass and current `active_deck`
   is still eligible, hold current `active_deck`.
8. If both top-fader decks have equal non-neutral bass and there is no current
   active deck, use current valid/fresh `rb_master_deck`.
9. If both decks are eligible and neither fader is `top`, hold current
   `active_deck` if still eligible.
10. If both decks are eligible, neither fader is `top`, and there is no current
    active deck, use current valid/fresh `rb_master_deck` if eligible.
11. If exactly one eligible deck remains in a neither-top fallback state, use
    that deck.
12. If none are eligible, idle.

## Stability

Any `active_deck` change requires the candidate to remain stable first.

The exact human-visible feel may need live tuning after operator-approved
runtime observation. Numeric thresholds/tolerances in code are conservative
implementation policy, not proof about Rekordbox internals.

Rules:

- During the stability wait, hold the current active deck only if it remains
  playing and audible.
- If current `active_deck` becomes non-audible, go idle until a candidate wins
  stability.
- Bass-swap changes use the same stability rule.
- Do not switch on momentary in-between reads during fader or bass movement.

## Rekordbox Master

`MASTER_CHANGED` updates `rb_master_deck` only when the input represents current
valid Rekordbox direct master truth for Deck 1 or Deck 2. While mixer authority
is enabled, stable raw Deck A/B master reads are refreshed before the resolver's
stale window expires.

Raw Deck C/D, sentinel/no-master, and unreadable direct-master reads invalidate
`rb_master_deck`; they must not alias into Deck 1/2. Invalidating events clear
`rb_master_deck_valid` and rerun the resolver.

`rb_master_deck` must carry enough validity/freshness/source state that status,
tie-breaking, and invalid-mixer fallback can distinguish proven Rekordbox master
truth from startup defaults, unsupported reads, sentinel/no-master values,
unreadable chains, stale data, or legacy OSC fallback input.

While mixer authority is valid, `MASTER_CHANGED` must not directly set
`active_deck`. Rekordbox master wins only the tie cases described above.

Status and logs must not call audible authority "master". Use `active_deck` or
`show_deck` for audible authority and `rb_master_deck` for Rekordbox master.

## Legacy OSC Active-Deck Input

OSC `/bridge/active_deck` and `/bridge/bridge_deck` are historical
TimecodeLink-era inputs. They must not bypass the fader/EQ resolver.

If retained, they are legacy/debug/fallback inputs only. They are not valid
mixer authority. For mixer-authority-enabled versions, they must not select the
show deck directly; invalid/stale mixer fallback goes through current valid/fresh
`rb_master_deck` only.

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
- temporarily use old RB-master behavior only when `rb_master_deck` is current
  and valid/fresh.
- keep trying to reacquire valid mixer authority.
- allow old RB-master behavior to change `active_deck`.
- mark the reason as `mixer_invalid_fallback`.
- if `rb_master_deck` is unavailable/stale during invalid mixer authority, do
  not default to Deck 1. Hold a still-playing current show deck only through an
  explicit fallback reason, or go idle visibly.

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
Stale `rb_master_deck` may remain visible with age/source/fallback diagnostics,
but status-facing validity and heartbeat `master` must be false/empty once the
stale window expires.

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

## Implementation Notes

Current implementation facts:

- `Ev.MASTER_CHANGED` from `RBStateReader` updates `rb_master_deck` while mixer
  authority is enabled; it does not directly write `active_deck`.
- OSC `/bridge/active_deck` and `/bridge/bridge_deck` enqueue
  `Ev.LEGACY_ACTIVE_DECK`, which cannot rewrite `rb_master_deck` and cannot
  select `active_deck` while mixer authority is enabled.
- Playing-only mirror auto-switch and resume-time empty-deck correction are
  suppressed as independent authority while mixer authority is enabled.
- `active_deck=0` is an idle/no-audible state; push-loop output paths must not
  call `deck_route(0)` or index `self._deck[0]`.
- Entering `active_deck=0` runs the existing safe SoundSwitch/OS2L idle
  clear/off body over the fixed safe deck set, without calling `deck_route(0)`.
- Runtime status and heartbeat expose show deck separately from
  `rb_master_deck`; heartbeat must not report `master = active_deck`.
- Invalid/stale mixer authority falls back visibly to current valid/fresh
  Rekordbox direct master behavior and does not synthesize Deck 1.

Historical behavior that wrote `active_deck` directly from direct master,
playing-only mirror detection, resume correction, or heartbeat master mirroring
is retained only as documented invalid-mixer `rb_master_deck` fallback or has
been replaced by resolver-mediated behavior. Legacy OSC active-deck requests are
retained only for non-mixer-authority fallback operation.
