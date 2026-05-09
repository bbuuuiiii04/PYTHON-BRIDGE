# Live BPM V2 Controlled Rearm

Status: DEPRECATED

Scope: dynamic live BPM follow for an already armed SoundSwitch autoloop. Live
testing showed that SoundSwitch rearms autoloops when the bridge sends a BPM
update. Current runtime behavior enables active live follow by default, sends
validated BPM changes with rate limiting, and pairs the apply with a one-shot
beat `change=True` re-lock. This document is retained as the older V2 design
record; `docs/bridge_design.md` is authoritative for current runtime behavior.

## Goals

- Keep live BPM fail-closed when validation is absent or stale.
- Keep `RBSS_LIVE_BPM_FOLLOW=0` as the active-follow kill switch.
- Update SoundSwitch BPM with rate limiting when validated live BPM changes.
- Pair BPM applies with a one-shot absolute beat `change=True` re-lock.
- Cancel pending updates on stop, idle, deck switch, track switch, Rekordbox restart,
  or live BPM invalidation.

## Runtime Switch

Active follow is enabled by default. Disable it with:

```text
RBSS_LIVE_BPM_FOLLOW=0
```

This switch only affects already armed autoloops. The normal live BPM arm
snapshot remains controlled by the LiveBPMService validation path and its kill
switch.

Live BPM discovery itself can be disabled with:

```text
RBSS_LIVE_BPM_DISABLE=1
```

## State Additions

`OutputState` tracks:

- `pending_live_bpm: float`
- `pending_live_bpm_since: float`
- `pending_live_bpm_target_beat: int`
- `last_live_follow_bpm: float`
- `live_follow_generation: int`

The generation resets whenever arm/disarm/deck/track/restart state changes.

## Runtime Algorithm

During active autoloop only, when active follow is enabled:

1. Read current validated `live_bpm`.
2. Compare it to current `timing_bpm`.
3. If delta is below threshold, do nothing.
4. If delta exceeds threshold and the rate limit allows it, send BPM to decks
   1, 2, 3, 4.
5. Set `autoloop_arm_bpm` / timing BPM to the new value after the send.
6. Mark the next autoloop beat as `change=True` once, then return steady beats
   to `change=False`.
7. Clear pending live-follow state.

## Cancellation Rules

Clear pending live-follow state when:

- lighting mode leaves `autoloop`
- `RB_RESTARTED`
- active deck changes
- active track filepath changes
- play state stops long enough to enter idle
- live BPM service returns unvalidated/stale
- resume settle has not completed yet

## Logging

Use periodic status only, not per-beat spam:

```text
[SS][AUTOLOOP-TICK] ... timing_bpm=... arm_bpm=... meta_bpm=... live_bpm=...
```

When active follow applies a BPM update:

```text
[SS][LIVE-BPM-APPLY] deck=1 bpm=132.00 beat=17
```

`LIVE-BPM-APPLY` means the bridge intentionally sent BPM to SoundSwitch. In
SoundSwitch terms this should be paired with the next one-shot beat re-lock, not
treated as a purely internal bridge timing update.

Color intent:

- `AUTOLOOP-ARM`: green
- `AUTOLOOP-TICK`: cyan
- `LIVE-BPM-APPLY`: green
- cancellations/failures: orange

## Tests

- Default follow applies live BPM changes after arm.
- `RBSS_LIVE_BPM_FOLLOW=0` disables active follow.
- Rate limit prevents push-loop spam while pitch is moving.
- The next autoloop beat after apply sends `change=True` once.
- Pending state cancels on stop, idle, deck switch, track switch, restart, stale live BPM.
- Logs show apply events without per-beat spam.

## Live Acceptance Evidence

Observed live run:

```text
[SS][AUTOLOOP-ARM] ... source=fallback timing_bpm=130.00 arm_bpm=130.00 ...
[SS][LIVE-BPM-APPLY] deck=1 bpm=134.30 beat=129
[SS][AUTOLOOP-TICK] ... timing_bpm=134.30 arm_bpm=134.30 ... pending_bpm=none
```

This proves the bridge detected the live BPM move during an active autoloop,
sent the SoundSwitch BPM update, and then updated bridge timing to the applied
BPM. Current runtime behavior additionally pairs that apply with a one-shot beat
re-lock.
