---
doc_status: research-current
truth_level: live-diagnostic-evidence-grounded
last_verified_commit: a2abf61
last_verified_date: 2026-07-02
validation_scope: Live capture session covering static-hold, autoloop BPM/pitch movement, forward/backward drag-seek, and scripted-to-scripted transition. Supersedes the "static hold never observed" finding in soundswitch_truth_exam_live_blockers_2026_07_02.md for this specific gap. No code changes, bridge restart, or hardware validation performed.
---

# SoundSwitch Live Capture Findings - 2026-07-02 Evening

Status: complete for this session's 4 target gaps. Follow-up to
`soundswitch_truth_exam_live_blockers_2026_07_02.md`, which left these rows
as GAP ("no captured evidence"). This session closes the evidence gap on
all 4.

## Scope

- Operator (Brandon) performed all live DJ actions: autoloop, static hold,
  scripted playback, drag-seeks, deck transitions.
- Claude ran read-only bridge-status monitoring throughout, plus (after
  troubleshooting a live Art-Net topology issue) an ArtPollReply discovery
  responder so SoundSwitch's Art-Net indicator would show connected. No
  code was changed, no bridge restart performed, no DMX/lighting output
  was altered by anything Claude ran.
- Primary evidence source: the bridge's own truth-check sidecar,
  `/tmp/rbss_artnet_truth_frames.jsonl`, run_id `e032a1a0f2dd4e6b922315326f90f41a`,
  pack_sha256 `87957ecd3c812c2aa023f61338ce8c1cb2069930702dfb194965923d3924e995`.
  This file is ephemeral (`/tmp`, not committed) — this doc is the durable
  record of what it showed.

## Evidence integrity

- 472,241 per-frame rows scanned, one continuous `run_id` throughout.
- `frame_index` counter fully sequential across the whole file: 0 skipped
  frames, 0 duplicated frames.
- Bridge's own send-side counters at session end: `dropped_count=0`,
  `send_error_count=0`, `overflow_count=0`.
- A parallel Python-side read-only status-file monitor ran continuously
  from before the session started, confirming the bridge process itself
  never restarted mid-session (single unbroken run).

## Finding 1: Static/manual look hold — WORKS (corrects prior "never observed")

Prior evidence (`soundswitch_truth_exam_live_blockers_2026_07_02.md`, lines
807-814) stated static hold was attempted but `static_held` was never once
observed true. That is now superseded for this configuration/session.

Sidecar shows **9,001 frames with `static_held=true`**, in 7 contiguous
windows:

| Frames | Slot | Notes |
| --- | --- | --- |
| 110333-111503 | 0 | first attempt |
| 111564-113275 | 0 | re-entered after a brief drop |
| 113443-113465 | 24 | brief, switched slots |
| 454711-454799 | 16 | second attempt begins |
| 454801-454802 | 16 | brief drop |
| 455036-455199 | 0 | still settling |
| 455386-461225 | 24 | settled and held through end of window |

Operator account: "the first static look hold was interrupted by smart
drop blackout, and i also fumbled with the midi pad a bit. and for the
last static look hold, i also fumbled with the midi pad a bit before
settling on a midi pad to hold on." This matches the data precisely — the
short flickering windows are the fumbling, the long final window (frames
455386-461225) is the settled hold.

Bridge log confirms the first-window interruption: repeated
`role=smart_drop_blackout phase=pre_drop look=room_blackout reason=emergency_blackout`
RGB-role triggers between 18:02:55 and 18:07:53, overlapping the first
static window's timeframe.

Interpretation for Fable: static hold is not structurally broken. It is
real and does work end-to-end (bridge state -> `static_held=true` ->
sidecar). What's still open: whether `smart_drop_blackout` (an RGB/LED
role, a different subsystem from the SoundSwitch pack's static-hold state)
should be able to interrupt a held static SoundSwitch look at all, per the
manual-static policy invariant ("held static stays operator-controlled...
loses only to blackout/emergency/pack-disabled/shutdown" — verify whether
`smart_drop_blackout`'s `emergency_blackout` reason is the *intended*
override path, or an unintended cross-subsystem interruption).

Also note: an independent read-only status-file monitor polling
`/tmp/rb_ss_bridge_v2_status.json` at 0.5s intervals **never once caught
`static_held=true`** during this same session, despite windows up to 6.6
seconds long. Given the sidecar (fed from live in-process state) proves
real holds occurred, this suggests the on-disk status JSON snapshot may
lag or miss `static_held` transitions — worth checking whether
`runtime_status.py`'s serialization of that field is reliably synced to
current state, since any operator tooling that reads the status file
(rather than the sidecar) would have concluded static hold was broken when
it was not.

## Finding 2: BPM/pitch movement during native Autoloop — CONFIRMED

Bridge log, deck 1, while `mode=autoloop`:

```
18:07:28.992  bpm=130.0  live_bpm=128.0  mode=autoloop
18:07:33.994  bpm=130.0  live_bpm=134.0  mode=autoloop
18:07:38.999  bpm=130.0  live_bpm=135.1  mode=autoloop
18:07:44.002  bpm=130.0  live_bpm=131.8  mode=autoloop
18:07:49.005  bpm=130.0  live_bpm=130.5  mode=autoloop
```

Clean rise (128.0 -> 135.1) then fall (135.1 -> 130.5), matching the
operator's stated action (pitch fader moved one direction, held, then the
other direction) while autoloop was active on deck 1. This closes the
"BPM/pitch movement while native Autoloop is active" gap explicitly listed
as not-captured in the prior truth-exam doc.

## Finding 3: Scripted-to-scripted transition, no autoloop deck involved — CONFIRMED

Deck/mode transition timeline extracted from the sidecar (deduplicated on
`(active_deck, mode, scripted_id, transport)` change):

```
frame=447998  elapsed_ms=100245  active_deck=2  mode=scripted  scripted_id=55826080  transport=playing
frame=451508  elapsed_ms=40333   active_deck=1  mode=idle      scripted_id=547339584 transport=
frame=451509  elapsed_ms=40338   active_deck=1  mode=scripted  scripted_id=547339584 transport=playing
```

Deck 2 was mid-playback on one scripted track when deck 1 loaded and
started a *different* scripted track and became the active deck — a
direct scripted-to-scripted handoff with no autoloop deck in the path.
This isolates the deck-split/stale-BPM bug from the prior truth-exam
session's autoloop-to-scripted transition capture: that bug was specific
to autoloop-sourced handoffs, not general dual-deck scripted handoffs,
*if* this transition's `active_deck`/state stayed clean afterward (no
stale metadata observed in subsequent frames for this transition).

## Finding 4: Drag-seek (forward and backward) — CONFIRMED, small-jump pattern explained

Operator account: "i just dragged the wave form to fastfoward backwards
seek the track" — a manual waveform drag, not a single discrete jump.

Two clusters of `elapsed_ms` anomalies (deviating from real-time frame
progression by >300ms) were found, both inside scripted playback:

```
FORWARD: frame 134503->134504  elapsed 106026->106506ms (Δ=480ms)
FORWARD: frame 134571->134572  elapsed 107922->109013ms (Δ=1091ms)
FORWARD: frame 134638->134639  elapsed 110695->111683ms (Δ=988ms)

BACKWARD: frame 446600->446601 elapsed 91557->91149ms  (Δ=-408ms)
FORWARD:  frame 447736->447737 elapsed 90856->92085ms  (Δ=1229ms)
FORWARD:  frame 447798->447799 elapsed 93458->94753ms  (Δ=1295ms)
FORWARD:  frame 447857->447858 elapsed 96170->97049ms  (Δ=879ms)
```

A click-drag on a waveform reports several intermediate position updates
during the drag rather than one instantaneous jump, which is exactly this
multi-step pattern (several sub-2-second jumps in sequence, same
direction, close together in frame_index). This is consistent with real
drag-seek behavior, not measurement jitter. Confirmed as evidence for the
"rewind/seek" and "forward boundary" gap rows, with the caveat that this
was a drag-seek rather than a large discrete jump — a large discrete jump
(e.g. click far ahead on the waveform, or a hotcue jump) remains
uncaptured this session if that's a materially different code path.

## Net effect on the Fable perfect-parity gap matrix

Of the 4 gaps this session targeted:

- Static/manual look hold: was GAP -> now has real positive evidence
  static hold works, plus a specific, named interruption mechanism
  (`smart_drop_blackout`) to check against the manual-static policy
  invariant.
- Autoloop BPM/pitch: was GAP (not captured) -> now CONFIRMED.
- Scripted-to-scripted transition (no autoloop deck): was GAP -> now
  CONFIRMED, and usefully isolates the deck-split bug to autoloop-sourced
  handoffs specifically.
- Seeks (forward + backward): was GAP (forward not cleanly isolated) ->
  now has real evidence for drag-seek behavior specifically; a large
  discrete jump/hotcue-style seek is still unverified.

Remaining unconfirmed from the original gap list (unchanged by this
session): mixer-master-authority handoff variations (`rb_master_deck` /
`mixer_authority` in `state_manager.py` — driven by OS2L-reported deck
levels, not crossfader; the bridge subscribes to a `"crossfader"` OS2L
trigger in `osl_output.py` but no code anywhere parses or acts on it, so
that specific signal is dead/unused and not a real gap to chase), cold-
idle-into-multiple-tracks, exhaustive autoloop note/bank coverage, and all
hardware/
Enttec parity (operator-only, out of Fable's authority).
