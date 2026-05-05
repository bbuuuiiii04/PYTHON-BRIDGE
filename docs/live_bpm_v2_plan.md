# Live BPM V2 Controlled Rearm

Scope: dynamic live BPM follow for an already armed SoundSwitch autoloop. Live
testing showed that SoundSwitch rearms autoloops when the bridge sends a BPM
update. V2 therefore treats a BPM send as a controlled rearm trigger and delays
it until a phrase-safe boundary. V1 remains the default behavior, where autoloop
timing is frozen to the BPM snapshot taken at arm time.

## Goals

- Keep V1 fail-closed behavior as the default.
- Add an explicit opt-in switch for V2 live-follow behavior.
- Update SoundSwitch BPM only after live BPM has stabilized.
- Allow the implied SoundSwitch autoloop rearm only at phrase-safe absolute beat
  positions: `9, 17, 25, ...`.
- Keep one pending BPM update per active autoloop.
- Cancel pending updates on stop, idle, deck switch, track switch, Rekordbox restart,
  or live BPM invalidation.

## Runtime Switch

Use an environment flag first:

```text
RBSS_LIVE_BPM_FOLLOW=1
```

If unset, active autoloops keep V1 frozen timing. This switch only affects
already armed autoloops. The normal live BPM arm snapshot remains controlled by
the LiveBPMService validation path and its kill switch.

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

During active autoloop only, when V2 is enabled:

1. Read current validated `live_bpm`.
2. Compare it to current `timing_bpm`.
3. If delta is below threshold, do nothing.
4. If delta exceeds threshold, start or replace a pending update.
5. Require the new value to remain stable for 1.5 s.
6. Compute the next absolute beat where:

```text
beat_number % 8 == 1
beat_number > 1
```

Examples: `9, 17, 25, 33`.

7. When the active absolute beat reaches the target, send BPM to decks 1, 2, 3, 4.
   This is expected to make SoundSwitch rearm its autoloop at that phrase point.
8. Set `autoloop_arm_bpm` / timing BPM to the new value only after the send.
9. Clear the pending update.

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

When V2 schedules an update:

```text
[SS][LIVE-BPM-PENDING] deck=1 current=128.00 pending=132.00 target_beat=stabilizing
[SS][LIVE-BPM-PENDING] deck=1 current=128.00 pending=132.00 target_beat=17
```

Pending replacement logs are rate-limited while pitch is still moving; the
periodic `AUTOLOOP-TICK` line carries the current pending value between those
events.

When V2 applies it:

```text
[SS][LIVE-BPM-APPLY] deck=1 bpm=132.00 beat=17
```

`LIVE-BPM-APPLY` means the bridge intentionally sent BPM to SoundSwitch. In
SoundSwitch terms this should be treated as a phrase-aligned autoloop rearm, not
as a purely internal bridge timing update.

Color intent:

- `AUTOLOOP-ARM`: green
- `AUTOLOOP-TICK`: cyan
- `LIVE-BPM-PENDING`: yellow
- `LIVE-BPM-APPLY`: green
- cancellations/failures: orange

## Tests

- V1 default ignores live BPM changes after arm.
- V2 flag schedules one pending update when live BPM changes.
- Pending value is replaced if live BPM changes again before the boundary.
- Update applies only on beat `9, 17, 25, ...`.
- Pending update cancels on stop, idle, deck switch, track switch, restart, stale live BPM.
- Logs show pending/apply events without per-beat spam.

## Live Acceptance Evidence

Observed live run:

```text
[SS][AUTOLOOP-ARM] ... source=fallback timing_bpm=130.00 arm_bpm=130.00 ...
[SS][LIVE-BPM-PENDING] deck=1 current=130.00 pending=130.14 target_beat=stabilizing
[SS][LIVE-BPM-PENDING] deck=1 current=130.00 pending=134.30 target_beat=129
[SS][LIVE-BPM-APPLY] deck=1 bpm=134.30 beat=129
[SS][AUTOLOOP-TICK] ... timing_bpm=134.30 arm_bpm=134.30 ... pending_bpm=none
```

This proves the bridge detected the live BPM move during an active autoloop,
waited for stabilization, scheduled the SoundSwitch BPM/rearm on absolute beat
`129`, and then updated bridge timing to the applied BPM.
