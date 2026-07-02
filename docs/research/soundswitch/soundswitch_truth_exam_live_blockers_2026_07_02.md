---
doc_status: research-current
truth_level: live-diagnostic-and-offline-command-output-grounded
last_verified_commit: 00d8be2
last_verified_date: 2026-07-02
validation_scope: SoundSwitch truth-check live diagnostic evidence after official comparator invalidity, plus offline exporter/time-domain coverage summaries. No code changes, bridge restart, SoundSwitch action, MIDI/DMX/Enttec action, or hardware validation.
---

# SoundSwitch Truth Exam Live Blockers - 2026-07-02

Status: in progress, diagnostic evidence collection after official comparator invalidated.

## Scope

- Operator controls all live actions: SoundSwitch, bridge menubar, DJing.
- Codex does not edit code, restart the bridge, click SoundSwitch, or patch defects during capture.
- Official comparator rows are preserved, but this run is not an official PASS candidate because the comparator reports setup-invalid sequence gaps.
- Diagnostic rows are still useful for Fable handoff because they filter the observed duplicate U1 echo and record U0/U1 timing/value disagreements.

## Pre-flight Facts

- Canonical pack publish previously passed with active lanes: algorithm_generalized 67, oracle_proven 16, unverified_parity 0.
- Truth-check U1 is enabled on the running bridge.
- Bridge run id observed during capture: `31ddce212d9e4edcaebf5694b4b31550`.
- Pack sha observed during capture: `87957ecd3c812c2aa023f61338ce8c1cb2069930702dfb194965923d3924e995`.
- Sidecar: `/tmp/rbss_artnet_truth_frames.jsonl`.

## Official Comparator Invalidity

Evidence files:

- `/tmp/rbss_truth_exam_report.json`
- `/tmp/rbss_truth_exam_report_retry.json`
- `/tmp/rbss_truth_exam_report_artpoll_only_invalid.json`

Observed reasons:

- `missing_u0`
- `sequence_gap:87->116`
- `sequence_gap:157->60`
- `sequence_gap:16->178`

Packet-count diagnosis:

- U0 arrives from SoundSwitch on loopback.
- U1 arrives duplicated/interleaved on loopback, including bridge-origin U1 and echoed/source-port-6454 U1.
- The strict comparator sequence check invalidates before byte/timing comparison.

## Scripted Track: New Sky (Odd Mob Remix)

Diagnostic evidence files:

- `/tmp/rbss_truth_exam_filtered_payload_compare.jsonl`
- `/tmp/rbss_truth_exam_mismatch_details.jsonl`

Coverage:

- First required section `0:38-1:00`: covered diagnostically, not official-pass covered.
- Second required section `2:40-3:01`: covered diagnostically, not official-pass covered.

Summary from filtered payload compare:

- Final U0 frames: 5292.
- Matched: 5249.
- Timing mismatches: 29.
- Byte mismatches: 14.
- Max timing delta: 23.035792 ms.
- Missing U1: 0.

Summary from mismatch detail logger:

- Byte mismatch rows: 67.
- Timing mismatch rows: 52.
- Max detailed timing delta: 16.31625 ms.

Recurring value mismatch pattern:

- U0 is zero while U1 outputs authored values, or U0 outputs authored values while U1 is zero.
- Repeated channels include 1, 3, 4, 5, 6, 7, 10, 11, 12, 13, 15, 19.

Representative rows:

- `track_elapsed_ms=91492`: byte mismatch, `dt_ms=1.845083`, channels 1, 4, 5, 6, 7, 8, 9, 11, 15, 19.
- `track_elapsed_ms=104110`: byte mismatch, `dt_ms=1.367625`, channels 1, 4, 5, 6, 7, 15, 19.
- `track_elapsed_ms=119812`: timing mismatch, `dt_ms=12.612125`.
- `track_elapsed_ms=129877`: timing mismatch, `dt_ms=-16.31625`.
- `track_elapsed_ms=210620`: byte mismatch, `dt_ms=1.862792`, U0 authored values while U1 zero on channels 1, 4, 5, 6, 7, 10, 12, 13, 15, 19.

Interpretation:

- This is a suspected scripted timeline/output timing mismatch, not a proven official comparator FAIL because the official comparator is setup-invalid in this socket topology.
- It is still actionable evidence for Fable: fix the official comparator capture topology first, then reproduce these `New Sky` mismatches with strict comparator rows.

## Continuing Capture Plan

Continue collecting diagnostic evidence for additional blocker classes:

- Titanium scripted former divergence section `1:30-2:40`.
- One additional scripted track played deep.
- Playback edges: pause, resume, stop/restart, mid-track load.
- Rewind/seek backward and forward across cue boundary.
- BPM fader moves in scripted and autoloop.
- Autoloop bank coverage including notes 96-111 and 52-55 loops.
- Static looks and blackouts over scripted/autoloop.
- Deck transitions scripted-to-scripted and scripted-to-autoloop-track.

For each scenario, record:

- Track, deck, elapsed range.
- Operator action.
- Official comparator state.
- Diagnostic mismatch counts.
- Representative byte/timing rows.
- Whether the issue is measurement-chain invalid, suspected new divergence, known handoff window, or not covered.

## Scripted Track: TITANIUM (TWINSICK REMIX)

Requested coverage:

- Former divergence section `1:30-2:40`.

Observed bridge timeline:

- Bridge saw `TITANIUM (TWINSICK REMIX).wav` on deck 1, scripted, BPM 128.0.
- Observed active scripted elapsed through the required range, including approximately `1:34`, `1:44`, `1:54`, `2:04`, `2:14`, `2:24`, `2:34`, and beyond.

Official comparator:

- Still invalid with repeated `sequence_gap:86->88` rows in `/tmp/rbss_truth_exam_report_continued_artpoll_invalid.json`.

Diagnostic capture issue:

- The first continued diagnostic detail logger remained stuck at `seen_u0=10`, `seen_u1=43` while Titanium played.
- A raw 5-second packet sampler during Titanium confirmed U0 and U1 were arriving:
  - `('127.0.0.1', 0): 184`
  - `('192.168.1.121', 0): 184`
  - `('127.0.0.1', 1): 1038`
  - `('192.168.1.121', 1): 1037`
- Interpretation: the separate official comparator and diagnostic logger split/starved UDP delivery under `SO_REUSEPORT`; this made Titanium's required section timeline-covered but not value-comparable in that pass.

Action taken:

- Stopped separate official comparator and separate detail logger.
- Started a single combined ArtPollReply advertiser + filtered U0/U1 detail logger:
  - `/tmp/rbss_truth_exam_combined_mismatch_details.jsonl`

Fable handoff implication:

- Fix or replace the live comparator capture topology so Art-Net discovery and filtered comparison happen in one receiver path, or otherwise avoid duplicate/interleaved U1 and listener starvation.

## Playback Edge: Titanium Play / Pause Hold / Resume

Capture file:

- `/tmp/rbss_truth_exam_combined_mismatch_details.jsonl`

Operator action:

- From idle/stopped Titanium, pressed play, let it run, paused/held, then resumed.

Status observations:

- Before edge: `TITANIUM (TWINSICK REMIX).wav`, deck 1, elapsed around `232802 ms`, bridge mode `idle`, active deck `0`, playing `false`.
- During play edge, detail rows showed `playing=true` while status still reported `active_deck=0` and `mode=idle` at `track_elapsed_ms=246070`.
- Later bridge status moved to `active_deck=1`, `mode=scripted`, `playing=true` around `track_elapsed_ms=253880`.
- After pause, status returned to `active_deck=0`, `mode=idle`, `playing=false`, around `track_elapsed_ms=254999`.

Mismatch rows:

- Recent edge window contained 122 rows:
  - summaries: 18
  - timing mismatches: 81
  - byte mismatches: 23
- Representative byte mismatches during play edge:
  - `track_elapsed_ms=246070`, `playing=true`, but `active_deck=0`, `mode=idle`; channels 8, 9, 11 mismatched with U0 zero and U1 nonzero (`255`, `255`, `210`).
  - `track_elapsed_ms=254848`, `active_deck=1`, `mode=scripted`; channels 8, 9, 11 mismatched with U0 nonzero (`255`, `255`, `210`) and U1 zero.
- Representative timing mismatches:
  - idle before play: `dt_ms=-16.890167` at `track_elapsed_ms=232802`.
  - scripted after resume: `dt_ms=5.291833` at `track_elapsed_ms=254369`.
  - after pause/idle: `dt_ms=-14.71425` at `track_elapsed_ms=254999`.

Interpretation:

- Playback edge exposes two distinct blocker candidates:
  1. Active-deck/mode state lag: playback can be `playing=true` while bridge status still reports active deck `0` and mode `idle`.
  2. Output edge mismatch: channels 8, 9, 11 flip between U0 nonzero/U1 zero and U0 zero/U1 nonzero around play/resume/pause.
- This needs strict-comparator repro after capture topology is fixed, but the combined diagnostic rows are actionable enough for Fable to inspect state transition timing and U1 truth-frame generation around idle/scripted edges.

## Rewind / Seek: Titanium Backward Seek

Capture file:

- `/tmp/rbss_truth_exam_combined_mismatch_details.jsonl`

Operator action:

- Titanium was resumed, then seeked backward by more than 30 seconds.

Status observations:

- Before rewind/seek edge, Titanium was around the pause/resume edge region near `254999 ms`.
- After the seek, bridge status showed Titanium playing/scripted around `141088 ms`.
- The logger also captured rows around `176536 ms`, then later rows around `144665`, `140804`, and `140599 ms`, consistent with a backward timeline jump.

Mismatch summary from a 45-second monitor window after the seek:

- Total recent rows: 1980.
- Byte mismatches: 1967.
- Timing mismatches: 8.
- Summary rows: 5.

Representative rows after rewind:

- `track_elapsed_ms=144665`: byte mismatch on channels 1, 3, 4, 6, 7, 15, 17; U0 zero while U1 had authored values (`17`, `17`, `255`, `134`, `138`, `159`, `219`).
- `track_elapsed_ms=140804`: byte mismatch on channels 7 and 19; U0/U1 both nonzero but disagree (`141` vs `134`, `79` vs `107`).
- `track_elapsed_ms=140599`: byte mismatch on channels 1, 3, 6, 7, 10, 15, 19; U0 zero while U1 had authored values (`62`, `28`, `131`, `141`, `255`, `165`, `79`).
- `track_elapsed_ms=140599`: timing mismatch `dt_ms=-12.012583`.

Interpretation:

- Backward seek produced a high-volume scripted mismatch burst, not just isolated timing drift.
- Pattern is stronger than the playback-edge rows: after the timeline jump, U1 appears to continue/land on authored frames that do not match SoundSwitch U0 at the same live time.
- This is a likely rewind/seek blocker candidate for Fable to inspect in scripted elapsed-position authority and U1 truth-frame generation after non-monotonic elapsed changes.

## Forward Boundary Playback After Rewind: Titanium

Requested action:

- Seek forward past a visible/cue boundary after the backward seek.

Observed:

- No discrete forward seek was confirmed in bridge status/log output.
- The track did continue through a phrase/cue-style boundary after the rewind:
  - Bridge log: `2:36.064`, phrase `chorus`.
  - Bridge log: `2:41.067`, phrase `up`.
- Combined diagnostic rows continued through this boundary.

Recent monitor window:

- Status around monitor: Titanium scripted, active deck 1, playing, elapsed around `166749 ms`.
- Recent rows in a 35-second window:
  - total: 17
  - byte mismatches: 10
  - timing mismatches: 3
  - summaries: 4
- Elapsed range in recent rows: `133427` to `163708 ms`.

Representative rows:

- `track_elapsed_ms=148547`: byte mismatch on channel 6, U0 `45`, U1 `0`.
- `track_elapsed_ms=153063`: byte mismatch on channels 3, 4, 6, 7, 15, 17; U0 authored values while U1 zero.
- `track_elapsed_ms=156137`: timing mismatch around `+/-5.1 ms`.
- `track_elapsed_ms=160163`: timing mismatch `5.096416 ms`.

Interpretation:

- Forward boundary playback after rewind remains mismatching.
- A clean explicit forward-seek jump is still not covered; if needed, rerun with a deliberate visible jump forward while combined logger is active.

## BPM Adjustment While Scripted: Titanium

Requested action:

- Move the pitch fader one direction, hold, then move the other direction while Titanium was scripted.

Initial observation:

- The first monitoring window missed the pitch movement and saw no BPM change.
- BPM watcher output:
  - initial state: `(128.0, 128.0, 232797, True)` for `(deck_bpm, live_bpm, elapsed_ms, playing)`.
  - final state: `(128.0, 128.0, 254999, False)`.
- Bridge log stayed at `bpm=128.0 live_bpm=128.0`.
- The track later stopped/ended at `254999 ms`.

Diagnostic rows during the wait:

- A 20-second capture window recorded 14 rows:
  - timing mismatches: 12
  - summaries: 2
  - byte mismatches: 0
- Representative timing rows:
  - `track_elapsed_ms=243889`: `dt_ms=6.049625` and `5.974417`.
  - `track_elapsed_ms=245917`: `dt_ms=-5.314583` and `-6.721583`.
  - `track_elapsed_ms=250948`: `dt_ms=-5.989542` and `-7.748417`.

Interpretation:

- Superseded by the rerun below, where bridge logs did capture the pitch movement.

## BPM Adjustment While Scripted: Titanium Rerun

Operator action:

- Operator reported doing the pitch movement again while Titanium was scripted.

Bridge log evidence:

- Live BPM movement was confirmed in `/tmp/bridge.log`.
- `15:14:33`: Titanium at `1:31.897`, `bpm=128.0`, `live_bpm=128.0`.
- `15:14:36`: `[LBPM][CURRENT] current=128.205`.
- `15:14:38`: status line at `1:36.927`, `live_bpm=130.9`.
- `15:14:43`: status line at `1:42.129`, `live_bpm=134.6`.
- `15:14:53`: status line at `1:52.756`, `live_bpm=139.5`.
- `15:14:58`: status line at `1:58.209`, `live_bpm=140.1`.
- `15:15:00`: `[LBPM][CURRENT] current=140.698`.
- `15:15:03`: status line at `2:03.707`, `live_bpm=139.7`; reverse movement begins.
- `15:15:08`: status line at `2:09.064`, `live_bpm=135.2`.
- `15:15:13`: status line at `2:14.229`, `live_bpm=129.6`.
- `15:15:18`: status line at `2:19.242`, `live_bpm=128.0`.

DMX diagnostic rows in the surrounding window:

- `/tmp/rbss_truth_exam_combined_mismatch_details.jsonl` rows still store `bpm=128.0` because the logger records deck metadata BPM, not `live_bpm`.
- Last 180-second diagnostic window after the movement:
  - total rows: 83
  - timing mismatches: 50
  - byte mismatches: 15
  - summary rows: 18
  - recorded row `bpm` values: only `128.0`, due logger limitation above.
- Representative rows around the same broad scripted window:
  - `track_elapsed_ms=154932`: byte mismatch on channels 1, 3, 4, 6, 7, 15, 17, with U0 authored values and U1 zero.
  - `track_elapsed_ms=167079`: timing mismatch `dt_ms=-5.10825`.
  - `track_elapsed_ms=184202`: timing mismatch around `9.7 ms`.

Interpretation:

- BPM input authority itself is confirmed: bridge detected live BPM rising from 128.0 to about 140.7 and returning to 128.0.
- DMX comparison remains diagnostic-only, and the current logger needs improvement to include `live_bpm` in each mismatch row.
- Even during/around the BPM movement window, U0/U1 timing and byte mismatches continued.

## Native Autoloop / SoundSwitch Loop Coverage

Operator action:

- Operator moved into an autoloop-capable flow and held the loop long enough to cover multiple tick/cycle boundaries.
- Track observed: `Wanton - Vielleicht Vielleicht (remix) .wav`.

Bridge log evidence:

- `15:21:16`: bridge armed autoloop on deck 1 at `0:00.222`, `bpm=160.0`, `src=live`, file `Wanton - Vielleicht Vielleicht (remix) .wav`.
- `15:21:17`: native autoloop emitted dark/default init:
  - `status=empty_dark_look`
  - `role=phrase`
  - `scene=house_groove_1`
  - `note=32`
  - `target=SSAutoLoop5.ssfile`
  - `name=BLACKOUT`
- Tick coverage:
  - `15:21:22`: beat `16.01`, note `32`.
  - `15:21:34`: beat `48.00`, note `64`, `BLACKOUT`, reason `buildup_to_drop_window`.
  - `15:21:40`: beat `64.00`, note `64`.
  - `15:21:46`: beat `80.01`, note `107`, `house_drop_12`, `New Autoloop`, reason `drop_crossing`.
  - `15:21:52`: beat `96.00`, note `105`, `house_drop_10`, `MEGA DROP`, reason `drop_crossing`.
  - `15:22:04`: beat `128.01`, note `98`, `house_drop_5`, `stack out in`, reason `drop_cycle`.
  - `15:22:16`: beat `160.00`, note `1`, `BLACKOUT`, reason `breakdown_active`.
  - `15:22:28`: beat `192.01`, note `1`.
  - `15:22:40`: beat `224.01`, note `1`.
  - `15:22:52`: beat `256.01`, note `32`, reason `phrase_boundary`.
  - `15:22:58`: beat `272.01`, note `64`, reason `buildup_to_drop_window`.
- Bridge continued reporting `live_bpm=160.0`, `mode=autoloop`, deck 1 active during this interval.
- `SS-MIDI input port gone; retrying exact port` warnings continued during the same run, even while outgoing MIDI transmit lines were present.

Diagnostic DMX evidence:

- Source: `/tmp/rbss_truth_exam_combined_mismatch_details.jsonl`.
- Filter: rows where `mode=autoloop` and `file=Wanton - Vielleicht Vielleicht (remix) .wav`.
- Window covered `track_elapsed_ms=615` through `125526`.
- Total diagnostic rows: `1542`.
  - summary rows: `13`
  - timing mismatches: `208`
  - byte mismatches: `1321`
- Maximum absolute timing delta in this autoloop window: `42.902375 ms`.

Representative byte mismatch rows:

- `track_elapsed_ms=29992`: 9-channel mismatch:
  - ch 1: U0 `255`, U1 `62`
  - ch 3: U0 `48`, U1 `55`
  - ch 4: U0 `14`, U1 `0`
  - ch 6: U0 `117`, U1 `93`
  - ch 7: U0 `145`, U1 `138`
  - ch 8: U0 `71`, U1 `21`
  - ch 9: U0 `255`, U1 `0`
  - ch 11: U0 `214`, U1 `0`
  - ch 15: U0 `159`, U1 `44`
- `track_elapsed_ms=35537`: U0 zero while U1 authored on channels 1, 3, 6, 7, 8, 15:
  - ch 1: U0 `0`, U1 `62`
  - ch 3: U0 `0`, U1 `55`
  - ch 6: U0 `0`, U1 `93`
  - ch 7: U0 `0`, U1 `138`
  - ch 8: U0 `0`, U1 `21`
  - ch 15: U0 `0`, U1 `20`
- `track_elapsed_ms=125526`: U0 zero while U1 authored on channels 1, 6, 7, 8, 11, 12, 15, 18:
  - ch 1: U0 `0`, U1 `255`
  - ch 6: U0 `0`, U1 `117`
  - ch 7: U0 `0`, U1 `95`
  - ch 8: U0 `0`, U1 `17`
  - ch 11: U0 `0`, U1 `255`
  - ch 12: U0 `0`, U1 `255`
  - ch 15: U0 `0`, U1 `191`
  - ch 18: U0 `0`, U1 `248`

Representative timing mismatch rows:

- `track_elapsed_ms=1143`: timing delta `5.324916 ms`.
- `track_elapsed_ms=108329`: timing delta `9.299667 ms`.
- Autoloop-window maximum observed timing delta was `42.902375 ms`.

Interpretation:

- Native autoloop state, tick cadence, loop note selection, dark looks, drop notes, and wrap/phrase cycling were observed in the bridge log.
- DMX parity is not clean during autoloop. The diagnostic stream shows both sustained timing drift beyond the 5 ms tolerance and heavy byte mismatches, including U0-zero/U1-authored cases and nonzero disagreement cases.
- Official PASS/FAIL remains unavailable because the official comparator lane is invalidated by the duplicate/interleaved U1 topology described earlier.

## Transition / Handoff: Autoloop To Scripted And Deck Alignment

Operator action:

- Operator transitioned from the autoloop flow on `Wanton - Vielleicht Vielleicht (remix) .wav` into scripted track `BLACKPINK - 뛰어(JUMP) [JAY ESKAR EXTENDED REMIX] (1).mp3`.
- The run then held long enough to observe deck/mode stabilization.

Bridge log evidence:

- Before transition:
  - `15:24:16`: deck 1 was autoloop, `Wanton`, `bpm=160.0`, `live_bpm=160.0`, elapsed `3:00.320`.
- Initial scripted transition on deck 1:
  - `15:24:19`: `scripted-match deck=1`, `scripted_id=1017390805`, latency `663 ms`.
  - `15:24:19`: `mode deck=1 autoloop->scripted`.
  - `15:24:19`: `arm-scripted deck=1`, elapsed `0:00.590`, `bpm=145.0`, file `BLACKPINK - 뛰어(JUMP) [JAY ESKAR EXTENDED REMIX] (1).mp3`.
  - `15:24:21`, `15:24:26`, `15:24:31`: deck 1 stayed scripted on BLACKPINK with `bpm=145.0`, `live_bpm=145.0`.
- Unexpected fallback back to autoloop:
  - `15:24:35`: `mode deck=1 scripted->autoloop`, elapsed reset to `0:00.000`.
  - `15:24:36`: `clear-scripted deck=1`.
  - `15:24:36`: `rearm-autoloop deck=1 file=Wanton - Vielleicht Vielleicht (remix) .wav`.
  - `15:24:36`: deck 1 returned to autoloop on `Wanton`, elapsed `2:40.058`, `bpm=160.0`, `live_bpm=160.0`.
- Deck 2 then matched the scripted track while deck 1 remained autoloop:
  - `15:24:44`: `scripted-match deck=2`, same `scripted_id=1017390805`, latency `1097 ms`.
  - `15:24:46`: deck 1 autoloop `Wanton`; deck 2 scripted `BLACKPINK`.
- Dual-deck state persisted:
  - `15:25:22`: deck 1 `Wanton`, mode `autoloop`, `bpm=160.0`, `live_bpm=155.0`; deck 2 `BLACKPINK`, mode `scripted`, `bpm=145.0`, `live_bpm=155.0`.
  - `15:25:40`: `arm-scripted deck=2`, elapsed `0:26.856`, `bpm=145.0`, BLACKPINK.
  - From `15:25:42` through at least `15:27:37`, deck 2 stayed scripted on BLACKPINK while deck 1 remained paused/stale in autoloop on `Wanton`.

Live BPM / authority concern:

- BLACKPINK metadata BPM was `145.0`.
- After the deck 2 handoff, deck 2 repeatedly reported `live_bpm=155.0` while still showing `bpm=145.0`:
  - `15:25:42`: deck 2 `0:28.151`, `bpm=145.0`, `live_bpm=155.0`.
  - `15:26:07`: deck 2 `0:54.886`, `bpm=145.0`, `live_bpm=155.0`.
  - `15:27:37`: deck 2 `2:31.154`, `bpm=145.0`, `live_bpm=155.0`.
- This looks like live-BPM authority contamination or stale live-BPM propagation from the previous autoloop/deck state. It is not just a DMX comparator issue; it is visible in bridge state logs.

Diagnostic DMX evidence:

- Source: `/tmp/rbss_truth_exam_combined_mismatch_details.jsonl`.
- BLACKPINK scripted rows in this transition capture:
  - total rows: `167`
  - timing mismatches: `139`
  - byte mismatches: `18`
  - summaries: `10`
  - elapsed range: `808` to `119368 ms`
  - maximum absolute timing delta: `34.926541 ms`
- Representative timing rows:
  - `track_elapsed_ms=808`: active deck 1 scripted, timing deltas `-14.652917 ms`, `24.4215 ms`, `7.627833 ms`, `7.367875 ms`.
  - `track_elapsed_ms=116623`: active deck 2 scripted, timing deltas `23.473875 ms` and `23.420417 ms`.
- Representative byte mismatch rows:
  - `track_elapsed_ms=53933`: channel 1 U0 `62`, U1 `3`; channel 10 U0 `255`, U1 `0`; channel 11 U0 `0`, U1 `227`.
  - `track_elapsed_ms=76285`: channels 1, 3, 6, 7, 10, 11, 15, 19 mismatched, including U0-zero/U1-authored values and channel 11 reverse disagreement.

Interpretation:

- Transition/handoff is not clean.
- The system briefly recognized BLACKPINK as scripted on deck 1, then dropped back to autoloop on deck 1 and later recognized BLACKPINK on deck 2.
- Deck state became internally mixed: deck 1 retained/stayed autoloop on `Wanton` while deck 2 was scripted on BLACKPINK.
- Live BPM authority appears contaminated after the handoff, with deck 2 scripted BLACKPINK reporting `live_bpm=155.0` despite metadata `bpm=145.0`.
- DMX mismatches persisted after the transition and remained outside the 5 ms comparator tolerance.

## Role Look / Idle Edge Window After Transition

Requested action:

- Attempted static/manual-look coverage after transition.
- No distinct SoundSwitch static-pack status field or manual static-pack mode was observed in `/tmp/rb_ss_bridge_v2_status.json` during this window.
- What was observed instead: scripted role-driven RGB/LED looks, then the playback edge into idle.

Bridge log evidence:

- State at the start of this window:
  - deck 2 scripted on `BLACKPINK - 뛰어(JUMP) [JAY ESKAR EXTENDED REMIX] (1).mp3`.
  - deck 2 metadata `bpm=145.0`, but still `live_bpm=155.0`.
  - deck 1 stale/stopped on `Wanton - Vielleicht Vielleicht (remix) .wav`, still reporting `live_bpm=155.0`.
- Role-look activity:
  - `15:28:15`: `LED look=rt_buildup_ramp_3`, role `buildup`, via `realtime`; RGB effect `buildup_ramp_3` activated.
  - `15:28:25` through `15:29:04`: repeated `room_blackout` triggers:
    - role `smart_drop_blackout`, reason `emergency_blackout`.
    - role `utility`, look `room_blackout`, reason `role_entry:utility`.
  - `15:29:17`: `color-inject look=rt_breakdown_full_breathing`, palette `crimson`; `LED look=rt_breakdown_full_breathing`, role `breakdown`, via `realtime`.
  - `15:29:42`: `color-inject look=rt_breakdown_star_twinkle`, palette `crimson`; `LED look=rt_breakdown_star_twinkle`, role `breakdown`, via `realtime`.
  - `15:29:44`: RGB deactivated with reason `idle_grace`.
- State edge:
  - During role-look playback, bridge stayed scripted on deck 2 with BLACKPINK but `live_bpm=155.0`.
  - After track/playback stopped, status moved to `mode=idle`, `active_deck=0`.
  - Diagnostic rows in idle then referenced stale deck/file metadata: `file=Wanton - Vielleicht Vielleicht (remix) .wav`, `bpm=160.0`, `track_elapsed_ms=222101`, `playing=false`, `active_deck=0`.

Diagnostic DMX evidence:

- Source: `/tmp/rbss_truth_exam_combined_mismatch_details.jsonl`.
- Approximate window: BLACKPINK scripted rows from `track_elapsed_ms>=214000`, plus subsequent idle rows carrying stale `Wanton` metadata at `track_elapsed_ms=222101`.
- Total rows: `1265`.
  - timing mismatches: `1251`
  - byte mismatches: `0`
  - summaries: `14`
- Modes/files represented:
  - `486` rows: `mode=scripted`, BLACKPINK, `playing=true`, `active_deck=2`.
  - `779` rows: `mode=idle`, `Wanton`, `playing=false`, `active_deck=0`.
- Maximum absolute timing delta in this window: `60.454334 ms`.

Representative rows:

- Scripted BLACKPINK role-look window:
  - `track_elapsed_ms=214295`, active deck 2, `dt_ms=-5.229541`, `-5.262958`, `-5.333958`.
- Idle after playback stopped:
  - `track_elapsed_ms=222101`, active deck 0, file `Wanton`, `dt_ms=-5.216833`, `-5.046458`, `-5.0685`.

Interpretation:

- This is not evidence of a clean manual SoundSwitch static-pack test; no distinct static-pack state was observed.
- It is useful evidence that scripted role looks and the idle edge still show DMX timing mismatches.
- The idle edge also keeps stale metadata visible in diagnostic rows, with active deck 0 but file/BPM from `Wanton`.
- Live BPM contamination from the prior transition persisted throughout the scripted role-look window.

## Disarm / Operator Control Blocker

Observed after capture:

- Diagnostic Python Art-Net logger was stopped; UDP 6454 was then owned only by SoundSwitch.
- Bridge truth-check remained active in `/tmp/rb_ss_bridge_v2_status.json`.
- The original truth run remained `enabled=true`, `running=true`, run id `31ddce212d9e4edcaebf5694b4b31550`.
- After a bridge reload/restart, truth-check came back still armed with a new run id `1e977402510f4a1d940a11e93a8ce1b3`.

Root cause evidence:

- Live bridge command line included `RBSS_ARTNET_TRUTH_CHECK=1 RBSS_ARTNET_UNIVERSE=1`.
- `scripts/ss_bridge_watcher.sh` also hardcodes `RBSS_ARTNET_TRUTH_CHECK=1` in the watched/manual launch env.
- Therefore this exam configuration is launch-env controlled, not a normal runtime toggle.

Interpretation:

- The operator cannot disarm truth-check from a normal menu-bar action unless the menu-bar path has a separate launch mode that omits `RBSS_ARTNET_TRUTH_CHECK=1`.
- Restarting the bridge under the same watcher/manual command re-arms truth-check automatically.
- Required safe closeout is a bridge restart without `RBSS_ARTNET_TRUTH_CHECK=1`, or a code/config fix later that gives the menu bar an explicit normal/non-truth launch path.

Closeout action:

- Stopped the truth-mode watcher/bridge.
- Started a persistent Terminal bridge session titled `RBSS_BRIDGE_NORMAL` without `RBSS_ARTNET_TRUTH_CHECK` and without `RBSS_ARTNET_UNIVERSE`.
- Verified one normal bridge process: PID `77240`, command `/opt/homebrew/bin/python3 -u -m rb_ss_bridge_v2`.
- Verified truth status disabled:
  - `enabled=false`
  - `reason=disabled`
  - `run_id=""`
  - `targets=[]`
- Verified OS2L SoundSwitch connection restored: `connected=true`, endpoint `192.168.1.121:55928`.
- Remaining normal-mode issue: pack output is disabled with `reason=pack_start_failed` because `/dev/cu.usbserial-EN396681` is missing.

## Coverage Audit / Non-Exhaustive Gaps

Verdict:

- This capture is broad and actionable, but it is not exhaustive.
- Do not claim "all possible mismatches" were captured.
- Use this document as the current blocker set plus a prioritized gap list.

Captured with evidence:

- Official comparator invalidity and duplicate/interleaved U1 topology.
- Scripted-track byte/timing mismatches on New Sky.
- Titanium scripted timing coverage and later diagnostic windows.
- Playback play/pause/resume edge.
- Backward seek/rewind.
- Forward boundary playback after rewind, but not a clean explicit forward seek.
- Scripted BPM movement on Titanium, including bridge-observed live BPM drift from 128.0 to about 140.7 and back.
- Native Autoloop cycle/wrap with representative dark/drop notes.
- Autoloop to scripted transition and deck split.
- Stale live-BPM propagation after transition.
- Scripted role-look and idle edge timing/stale-metadata behavior.
- Truth-check disarm/operator-control blocker.

Not captured or not cleanly isolated:

- A valid official comparator PASS/FAIL run.
- Clean explicit forward seek jump.
- Manual/static SoundSwitch pack looks as a distinct static-pack mode.
- Scripted-to-scripted transition without an autoloop source deck.
- Deck 1 to deck 2 transition matrix beyond the observed autoloop/scripted split.
- Stop/load/play from cold idle into multiple different scripted tracks.
- Crossfader or mixer-master handoff variations.
- BPM/pitch movement while native Autoloop is active.
- Exhaustive Autoloop note/bank coverage; only representative notes were observed.
- Normal pack DMX output with Enttec hardware active; normal-mode pack output failed because `/dev/cu.usbserial-EN396681` was missing.

Implication for Fable:

- Fix the captured root causes first, especially comparator topology and state authority.
- Add diagnostics/tests that make the uncaptured gaps cheaper to validate in the next exam.
- After fixes, rerun a shorter targeted live exam focused on the gap list before declaring exhaustive parity.

## Aggregate Diagnostic Pattern Mining

Source:

- `/tmp/rbss_truth_exam_combined_mismatch_details.jsonl`
- Parsed rows: `10350`

Overall row types:

- Byte mismatches: `6967`
- Timing mismatches: `3226`
- Summary rows: `157`

Rows by mode:

- `autoloop`: `5471`
- `scripted`: `3104`
- `idle`: `1775`

Top mode/file groups:

- Autoloop, `Wanton - Vielleicht Vielleicht (remix) .wav`: `5364` rows
  - byte mismatches: `4881`
  - timing mismatches: `457`
  - max absolute timing delta: `43.710833 ms`
  - top mismatch channels: 1, 15, 7, 11, 6, 4, 19, 3
- Scripted, `TITANIUM (TWINSICK REMIX).wav`: `2101` rows
  - byte mismatches: `1978`
  - timing mismatches: `89`
  - max absolute timing delta: `15.5165 ms`
  - top mismatch channels: 11, 9, 8, 19, 7, 6, 17, 3
- Idle, `Wanton - Vielleicht Vielleicht (remix) .wav`: `1300` rows
  - timing mismatches: `1289`
  - max absolute timing delta: `60.454334 ms`
- Scripted, `BLACKPINK - 뛰어(JUMP) [JAY ESKAR EXTENDED REMIX] (1).mp3`: `1003` rows
  - timing mismatches: `943`
  - byte mismatches: `35`
  - max absolute timing delta: `129.093 ms`
- Idle, `TITANIUM (TWINSICK REMIX).wav`: `321` rows
  - timing mismatches: `188`
  - byte mismatches: `73`
  - max absolute timing delta: `177.326334 ms`
- Autoloop, `The Devil Dwarf - PSYNDUSTRIAL (FREE DOWNLOAD).wav`: `67` rows
  - timing mismatches: `67`
  - max absolute timing delta: `96.331 ms`
- Autoloop, empty file metadata: `40` rows
  - timing mismatches: `39`
  - max absolute timing delta: `50.520709 ms`
- Idle, `Ray Volpe - Laserbeam (Carlo Kalu Edit) .wav`: `35` rows
  - timing mismatches: `35`
  - max absolute timing delta: `72.979167 ms`

Aggregate byte-diff channel frequency:

- ch 11: `5808`
- ch 8: `4536`
- ch 1: `4410`
- ch 9: `4315`
- ch 15: `4274`
- ch 7: `3977`
- ch 6: `3513`
- ch 4: `3137`
- ch 19: `2935`
- ch 3: `2649`
- ch 18: `2481`
- ch 17: `1703`
- ch 12: `902`
- ch 10: `892`
- ch 13: `772`
- ch 5: `717`

Aggregate byte-diff shape:

- U0 zero while U1 authored: `18697` channel-level diffs.
- U1 zero while U0 authored: `10764` channel-level diffs.
- U0/U1 both nonzero but disagree: `17560` channel-level diffs.

Representative shape examples:

- U0 zero while U1 authored:
  - Titanium idle/play edge, `track_elapsed_ms=232802`, `active_deck=0`, `mode=idle`, `playing=true`, channels 8/9/11 U0 `0`, U1 `255/255/210`.
- U1 zero while U0 authored:
  - Titanium scripted edge, `track_elapsed_ms=254848`, `active_deck=1`, `mode=scripted`, channels 8/9/11 U0 `255/255/210`, U1 `0`.
- Nonzero disagreement:
  - Titanium scripted after rewind, `track_elapsed_ms=140804`, channels 7 and 19 disagree: `141` vs `134`, `79` vs `107`.

Interpretation:

- The mismatch problem is not isolated to a single track, mode, or channel.
- Autoloop produces the largest byte-mismatch volume.
- Scripted BLACKPINK and idle/stale metadata windows produce the largest observed timing deltas.
- Channels 8/9/11 dominate Titanium edge mismatches; channels 1/15/7/11/6 dominate Autoloop mismatch volume.
- The three byte-diff shapes point to both authority/zero-frame timing bugs and real value-selection disagreement bugs.

Representative diagnostic rows from
`/tmp/rbss_truth_exam_combined_mismatch_details.jsonl`:

| Class | File/mode | State | Evidence |
| --- | --- | --- | --- |
| U0 zero / U1 authored | `TITANIUM (TWINSICK REMIX).wav`, idle | `active_deck=0`, `playing=true`, `track_elapsed_ms=232802`, `dt_ms=-2.004959`, `u0_seq=161`, `u1_seq=108` | ch8 `0->255`, ch9 `0->255`, ch11 `0->210` |
| U1 zero / U0 authored | `TITANIUM (TWINSICK REMIX).wav`, scripted | `active_deck=1`, `playing=true`, `track_elapsed_ms=254848`, `dt_ms=3.120083`, `u0_seq=210`, `u1_seq=76` | ch8 `255->0`, ch9 `255->0`, ch11 `210->0` |
| Nonzero disagreement | `TITANIUM (TWINSICK REMIX).wav`, scripted | `active_deck=1`, `playing=true`, `track_elapsed_ms=140804`, `dt_ms=2.298333`, `u0_seq=239`, `u1_seq=155` | ch7 `141->134`, ch19 `79->107` |
| Mixed zero/nonzero disagreement | `TITANIUM (TWINSICK REMIX).wav`, scripted | `active_deck=1`, `playing=true`, `track_elapsed_ms=157233`, `dt_ms=2.044459`, `u0_seq=42`, `u1_seq=210` | ch17 `219->0`, ch19 `0->255` |
| Worst observed timing | `TITANIUM (TWINSICK REMIX).wav`, idle | `active_deck=0`, `playing=false`, `track_elapsed_ms=246070`, `u0_seq=64`, `u1_seq=244` | `dt_ms=-177.326334` |
| BLACKPINK timing outlier | `BLACKPINK - 뛰어(JUMP) [JAY ESKAR EXTENDED REMIX] (1).mp3`, scripted | `active_deck=2`, `playing=true`, `bpm=145.0`, `track_elapsed_ms=132932`, `u0_seq=0`, `u1_seq=91` | `dt_ms=-129.093` |
| Autoloop timing outlier | `The Devil Dwarf - PSYNDUSTRIAL (FREE DOWNLOAD).wav`, autoloop | `active_deck=1`, `playing=true`, `bpm=160.0`, `track_elapsed_ms=2907`, `u0_seq=69`, `u1_seq=53` | `dt_ms=96.331` |

Top high-diff group samples:

- Wanton autoloop at `track_elapsed_ms=160242`, `dt_ms=-0.017542`,
  `diff_count=13`: ch1 `62->3`, ch3 `41->28`, ch4 `0->93`,
  ch5 `193->0`, ch6 `100->134`, ch7 `138->90`, ch8 `77->71`,
  ch9 `145->255`, ch11 `0->231`, ch15 `152->159`, ch17 `200->0`,
  ch18 `48->0`, ch19 `0->74`.
- Titanium scripted at `track_elapsed_ms=127483`, `dt_ms=0.012875`,
  `diff_count=8`: ch1 `0->62`, ch3 `0->28`, ch6 `0->131`,
  ch7 `0->141`, ch9 `241->255`, ch10 `0->255`, ch15 `0->165`,
  ch19 `0->79`.
- BLACKPINK scripted at `track_elapsed_ms=64266`, `dt_ms=-0.019792`,
  `diff_count=11`: ch1 `62->3`, ch3 `28->0`, ch4 `0->203`,
  ch6 `121->110`, ch7 `124->138`, ch8 `121->86`, ch9 `255->200`,
  ch10 `255->0`, ch15 `190->0`, ch18 `0->255`, ch19 `111->0`.

## Perfect-parity exporter coverage addendum

This addendum was added after the live exam because the required target is not
"enough evidence for a comparator bug." The target is a one-shot Fable handoff
for SoundSwitch exporter/runtime perfect parity across every supported surface.

Fable packet manifest:

- Primary prompt: `docs/prompts/active/soundswitch_truth_exam_fable_fix_prompt.md`.
- Send with this report, `docs/research/soundswitch/soundswitch_time_domain_exam_2026_07.md`,
  `docs/plans/active/soundswitch_exporter_remaining_work.md`, and
  `local/soundswitch/rbss_canonical_pack/manifest.json`.
- The repo docs above are the durable packet. Allow read-only inspection of the
  exact `/tmp/rbss_*` machine outputs named below only if Fable needs raw
  spot-check evidence.
- Current evidence proves captured disagreement classes and explicit coverage
  gaps. It does not prove official comparator PASS, full static/playback/seek/BPM
  /transition/active-deck parity, Enttec/hardware parity, or compatibility
  beyond the pinned SoundSwitch project/profile/version.

Optional raw machine outputs refreshed during this pass:

- `/tmp/rbss_time_domain_exam_refresh.json`
- `/tmp/rbss_parity_fixture_scripted.json`
- `/tmp/rbss_parity_fixture_autoloop.json`
- `/tmp/rbss_parity_fixture_static.json`
- `/tmp/rbss_soundswitch_coverage_no_validation.json`
- `/tmp/rbss_project_inventory_default.json`
- `/tmp/rbss_project_inventory_codex.json`

Current bounded exporter surface from
`local/soundswitch/rbss_canonical_pack/manifest.json`:

- SoundSwitch `2.10.3`, universe `0`, channel span `CH1-CH19`.
- Fixture profile `b8ad2201b9e4c94696c898a7e8f6a5a9`.
- Project UUID `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}`.
- `42` autoloops.
- `45` scripted inventory entries, `44` parsed scripted, `32` active
  existing-path scripted.
- `233` render cues and `233` venue records.
- `32` static looks.
- `19` IAC autoloop bindings, `25` learned mappings, `1` DDJ static override.
- Active parity lanes: `algorithm_generalized=67`, `oracle_proven=16`,
  `unverified_parity=0`.
- Inactive lanes still exist: `algorithm_generalized=29`,
  `unverified_parity=6`.

Offline time-domain mismatches:

- Scripted timing: `436` measured boundaries, median `15.841 ms`,
  p95 `28.229 ms`, `5` boundaries over one `40 ms` wire frame,
  max `740.657 ms`.
- Scripted witness `fc10fc02-93c2-418f-8815-16088884da42` is a hard blocker:
  `3` measured boundaries and all `3` are over one wire frame.
- Autoloop timing: `1377` transitions, median `14.682 ms`, p95 `93.783 ms`,
  `230` transitions over one `40 ms` wire frame, max `748.502 ms`.
- Autoloop wrap timing: `110` wrap transitions, median `16.204 ms`,
  p95 `143.743 ms`, `23` over one wire frame, max `466.569 ms`.
- Scripted handoff evidence includes `3` handoffs and one sidecar mono gap of
  `1443.264 ms`.
- Joined scripted rows include `8` U1 zero-frame runs, median `1673.5` frames,
  max `15921` frames.

Fixture/source divergence findings:

- Scripted fixture builder found capture-source divergence for
  `9947c65e-cfd1-476e-aa90-4aed65ae5f11`.
- Autoloop fixture builder found capture-source divergences for
  `SSAutoLoop13`, `SSAutoLoop14`, `SSAutoLoop15`, `SSAutoLoop16`,
  `SSAutoLoop17`, `SSAutoLoop46`, `SSAutoLoop47`, `SSAutoLoop48`,
  `SSAutoLoop50`, `SSAutoLoop55`, `SSAutoLoop6`, and `SSAutoLoop8`.
- Some covered autoloops produced zero accepted fixture rows despite timing
  rows: `SSAutoLoop15`, `SSAutoLoop17`, `SSAutoLoop46`, `SSAutoLoop47`,
  `SSAutoLoop50`, and `SSAutoLoop8`.

Static/manual-state coverage:

- Static capture windows are unavailable.
- Slots `0`, `24`, and `16` were attempted, but bridge `static_held` was never
  observed.
- Slot `31` was unavailable from StreamDeck/reserved bridge MIDI IAC.
- U0 was recorded, but static alignment is not accepted; static look parity is
  therefore unproven and must be fixed or validated explicitly.

Structural coverage without validation:

- Autoloops: `42/42` structurally parsed with no referenced missing GUIDs, but
  all have `capture_status=no_capture_evidence` in the no-validation coverage
  run.
- Scripted: `45` structural rows: `36` structurally parsed, `8`
  structurally parsed but not wire-validated, and `1` unsupported.
- Full scripted structural inventory has `18` referenced missing cue GUID
  references across inactive/not-wire-validated rows.
- Project artifact classification remains partial/fail-closed because `.ssa`,
  `.sspreset`, and non-MIDI recordable control-registry semantics remain opaque.
- Bridge scene bindings still include `no_decoded_project_binding` rows; do not
  claim those are decoded SoundSwitch project bindings.

Perfect-parity mismatch/gap matrix for Fable:

| Surface | Current evidence | Required closeout |
| --- | --- | --- |
| Comparator/capture validity | Official comparator invalid; diagnostic stream still useful | Fix topology/filtering so official U0 vs U1 compare can pass/fail deterministically |
| Exported DMX values | Active lanes claim zero unverified, live rows still show byte diffs | Separate stale source/capture/runtime defects from exporter defects and test each |
| Scripted timing | 5/436 boundaries over 40 ms; `fc10fc02` all-bad sample | Fix/prove boundary timing for all active scripted witnesses |
| Autoloop cycling | 230/1377 transitions over 40 ms; large wrap/outlier residuals | Fix/prove loop phase, wrap, and transition timing |
| Static looks | Attempted but no accepted `static_held` windows | Implement/prove static hold/release and overlap semantics |
| Playback edges | Live Titanium showed `playing=true`, `active_deck=0`, `mode=idle` | Fix/prove play, pause, resume, stop, restart, cold load/play |
| Seeks/rewinds | Live backward seek produced high mismatch burst | Fix/prove backward seek and forward seek across cue boundaries |
| BPM/pitch | Live BPM movement detected; diagnostics lacked `live_bpm`; stale deck BPM observed | Fix/prove deck-scoped BPM authority and diagnostics |
| Transitions/active deck | Live deck split and offline 1443.264 ms handoff gap | Fix/prove scripted-scripted and autoloop-scripted deck ownership/crossfader cases |
| Idle/zero frames | Stale file metadata in idle rows; long U1 zero-frame runs | Define and test intentional zero output versus stale/delayed authority |
| Unsupported/opaque inventory | Inactive unverified lanes, unsupported scripted row, opaque project artifacts | Track, guard, or explicitly exclude without overclaiming perfect parity |
| Normal operator mode | Truth launch previously rearmed via env | Normal launch must be truth-disabled; truth launch explicit and reversible |

Completion audit against the original greenlight surface:

| Requirement | Current verdict | Evidence |
| --- | --- | --- |
| Official U0/U1 comparator verdict | GAP | Official reports were invalid due to capture topology; diagnostic stream is evidence but not official PASS/FAIL. |
| Scripted output values | CAPTURED-FAIL / SOURCE-AMBIGUOUS | Live rows show byte disagreements in Titanium and BLACKPINK; scripted fixture builder also found `9947c65e...` capture-source divergence. |
| Scripted timeline timing | CAPTURED-FAIL | Offline report: `5/436` boundaries over one wire frame; `fc10fc02...` has `3/3` large misses. |
| Autoloop output values | CAPTURED-FAIL | Wanton autoloop has the largest byte-mismatch volume; representative row shows `13` channel diffs. |
| Autoloop cycling/wrap timing | CAPTURED-FAIL | Offline report: `230/1377` transitions and `23/110` wraps over one wire frame. |
| Static looks | GAP | Static slots were attempted, but no accepted `static_held` windows were observed. |
| Manual blackout / static overlap | GAP | No accepted static/manual windows; must be explicitly validated or fail-closed. |
| Playback edges | GAP / LIVE-FAIL LEAD | Titanium live edge showed `playing=true`, `active_deck=0`, `mode=idle`; pause/resume/stop/restart are not fully covered. |
| Rewinds/seeks | GAP / LIVE-FAIL LEAD | Backward seek produced mismatch burst; forward seek past cue boundary remains not cleanly covered. |
| BPM/pitch changes | GAP / LIVE-FAIL LEAD | Bridge saw pitch movement, but diagnostic rows lacked `live_bpm`; stale `live_bpm` contamination was observed in transition context. |
| Transitions / active deck | GAP / LIVE-FAIL LEAD | Offline handoff gap `1443.264 ms`; live autoloop-to-scripted deck split observed; full crossfader/deck matrix not covered. |
| Idle/zero-frame behavior | CAPTURED-FAIL | Idle rows used stale file metadata and long U1 zero-frame runs exist in joined scripted rows. |
| MIDI/control bindings | GAP | Project inventory resolves selected bindings but bridge scene bindings still include `no_decoded_project_binding`; static control did not produce accepted live windows. |
| Unsupported/inactive inventory | GAP / FAIL-CLOSED REQUIRED | Inactive unverified lanes, one unsupported scripted row, and opaque `.ssa`/`.sspreset`/recordable semantics remain. |
| Enttec/hardware parity | GAP | No hardware/Enttec evidence; software/wire only. |

Additional live captures for gap closure are operator-owned and outside Fable's
execution authority. Fable's task is to use this packet to specify fixes,
diagnostics, acceptance tests, and fail-closed behavior for every captured-fail
or gap surface above.

The active Fable handoff for this full scope is:
`docs/prompts/active/soundswitch_truth_exam_fable_fix_prompt.md`.

## Live monitor addendum — 2026-07-02 16:11 EDT

This addendum records the live truth-capture state after the operator asked
whether truth should be enabled and why Titanium was being replayed.

- Truth was enabled in the active bridge process:
  `soundswitch_pack.truth_check.enabled=True`, `running=True`,
  `run_id=ab28b26243714c2881aa119d3439a1bf`, `universe=1`,
  `sidecar_path=/tmp/rbss_artnet_truth_frames.jsonl`, and no truth send errors
  were reported in `/tmp/rb_ss_bridge_v2_status.json`.
- SoundSwitch was connected according to bridge status.
- The truth sidecar was actively growing, but the sampled rows were idle-only:
  `lighting_mode=idle`, `soundswitch_id=""`, `elapsed_ms=0`, and zero-frame
  `dmx_sha256=076a27c79e5ace2a3d47f9dd2e83e4ff6ea8872b3c2218f66c92b89b55f36560`.
- The official live comparator run
  `/tmp/rbss_truth_exam_report_live_20260702T160636.json` was invalid, not a
  pass/fail parity verdict: first `reason=missing_u0`, then repeated
  `reason=sequence_gap:219->88`, with `matches=0`.
- That invalid comparator run was stopped to avoid flooding the report with
  duplicate invalid rows. The truth sidecar was not deleted or reset.
- Titanium should not be used as the main next target. It is now a regression
  anchor only; the remaining capture priority is static/manual overlap,
  blackout, rewind/seek, BPM/pitch movement, autoloop bank/wrap coverage, and
  real active-deck transitions.

## Live monitor addendum — 2026-07-02 16:12-16:13 EDT

Autoloop capture began after the quiet watcher was armed.

- Bridge state changed from idle to autoloop:
  `lighting_mode=autoloop`, `active_deck=1`.
- Sidecar rows advanced through autoloop elapsed samples including
  approximately `1099 ms`, `5957 ms`, `10817 ms`, `15674 ms`, and `20534 ms`.
- Truth remained enabled and running with the same run id
  `ab28b26243714c2881aa119d3439a1bf`; SoundSwitch remained connected; truth
  send errors remained `0`.
- A fresh comparator started during the non-idle autoloop window and bound both
  Art-Net interfaces, but it invalidated immediately: first
  `reason=missing_u0`, then repeated `reason=sequence_gap:127->129`, with
  `matches=0`.
- This makes comparator topology/sequence validation a live blocker independent
  of Titanium. The raw truth sidecar captured autoloop state, but the official
  comparator still cannot produce a deterministic PASS/FAIL verdict.

Continued autoloop monitoring:

- Autoloop remained active on deck 1 through approximately `74017 ms`, then
  continued through approximately `98318 ms`.
- `static_held` remained false and `blackout` remained false throughout the
  sampled deck-1 autoloop window; this run still did not capture static or
  blackout overlay semantics.
- At `2026-07-02 16:14:33 EDT`, active deck changed from deck 1 to deck 2 while
  still in autoloop mode; sidecar elapsed reset to approximately `4001 ms`.
- This is useful active-deck/transition evidence, but because the comparator
  remained invalid it is not an official U0/U1 pass/fail verdict.

## Live setup blocker — SoundSwitch Art-Net not connected

The operator observed that SoundSwitch was not connected to Art-Net. That
explains the official comparator failures:

- `missing_u0` means the comparator did not see SoundSwitch's universe-0
  Art-Net stream.
- The bridge status field `soundswitch.connected=True` is OS2L/socket status,
  not proof that SoundSwitch is emitting Art-Net.
- The bridge truth lane remained enabled and sending U1:
  `run_id=ab28b26243714c2881aa119d3439a1bf`, `universe=1`,
  `send_error_count=0`.
- Therefore the current sidecar/autoloop/deck-transition capture is useful
  bridge-state evidence, but it is not an official SoundSwitch-vs-bridge
  parity capture until SoundSwitch Art-Net output is connected and U0 packets
  are visible.
