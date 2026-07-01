---
doc_status: active-spec
truth_level: code-capture-and-ghidra-grounded root-cause spec
last_verified_commit: 837c5a6
last_verified_date: 2026-06-30
validation_scope: read-only investigation plus software tests; no bridge restart, no live runtime toggle, no SoundSwitch project mutation, no fixture-pack/config mutation, no physical DMX/hardware writes
---

# Codex Implementation Spec - SoundSwitch DMX Cue Mismatch

This spec fixes the bridge-vs-SoundSwitch DMX cue mismatch by matching the
runtime model SoundSwitch actually uses. Do not reduce this to "truth mode" or
"software zero frame". U1 truth proved the bridge is sending its own rendered
frame; the bug is that the bridge's rendered frame is often not the same frame
SoundSwitch renders on U0.

## Part A - Root Cause Verdict

### A1. Art-Net truth path is not the scripted mismatch cause

- [confirmed] `tools/artnet_compare.py` splits packets by universe only:
  SoundSwitch U0 and bridge truth U1 are selected at `tools/artnet_compare.py:184-189`.
- [confirmed] U1 packets are reconciled against sidecar sequence/frame/hash before
  U0 comparison: `tools/artnet_compare.py:248-266`.
- [confirmed] U0 is then paired to U1 by nearest packet timestamp within the
  tolerance: `tools/artnet_compare.py:271-287`,
  `tools/artnet_compare.py:404-428`.
- [confirmed] Truth frames are expanded, hashed, sidecar-written, and queued from
  the exact 19-channel bridge render in `artnet_truth.py:214-239`.
- [confirmed] DMX address expansion is a direct CH1-CH19 to fixture-map write.
  No name inference or offset logic exists in `soundswitch_frame_sender.py:39-66`.

Verdict: the comparator is trustworthy for proving "U1 equals bridge sidecar".
It is not a sufficient oracle for "bridge single-deck render equals SoundSwitch
global playback-mixer render". Comparator/pairing is not the root cause of the
scripted bytes, but it needs better diagnostics after the runtime fix.

### A2. Scripted mismatch root cause: bridge renders one active deck; SoundSwitch renders playback mixer state

- [confirmed] Bridge pack output selects exactly one active deck:
  `state_manager.py:3834-3875`.
- [confirmed] It derives exactly one deck's `soundswitch_id`, `scripted_id`,
  `elapsed_ms`, and `transport`: `state_manager.py:3923-3981`.
- [confirmed] It calls `player.select_scripted()` once for that deck and elapsed
  time: `state_manager.py:3985-3990`.
- [confirmed] It submits exactly `player.render().frame` to truth/output:
  `state_manager.py:4067-4089`.
- [confirmed] `DeckState` has playback identity and transport, but no
  SoundSwitch playback-mixer fields: `models.py:77-90`. The only mixer snapshot
  presently decoded for bridge authority is per-deck upfader/LOW labels:
  `models.py:116-124`, `active_deck_resolver.py:24-33`.
- [confirmed by GhidraMCP] SoundSwitch native code does not render only the
  current bridge show deck. In `SSPlaybacks::RefreshCache_2PlayBackMode`
  (`10033799c`), SoundSwitch:
  - gets light state for playback 0 and playback 1,
  - uses `this[0x470]` for colour/intensity crossfade,
  - uses `this[0x471] / 255.0` for attribute crossfade,
  - selects playback 1's cue cache when attribute crossfade is at or above 0.5,
  - blends intensity/position/strobe attributes between the two playback buffers,
  - calls `SetChannelAttributes(...)` for each channel.
- [confirmed by GhidraMCP] `SSPlaybacks::SetXFadeLevel` (`100336eb4`) writes
  the same crossfade byte to colour/intensity, attribute, and another fade slot.
  `SetColourIntCrossFadeLevel` (`100336e9c`) and
  `SetAttributeCrossFadeLevel` (`100336ea8`) can set those independently.
- [confirmed by GhidraMCP] In four-playback mode,
  `SoundSwitchDoc::Private::RefreshLights4PlaybackMode` (`1003080d8`) sets deck
  levels for playbacks 0, 1, 2, and 3, then asks
  `SSPlaybacks::GetEffective4PlaybackIndex` (`100336a90`) for the effective
  playback. `SSPlaybacks::RefreshCache_4PlayBackMode` (`100337d98`) renders the
  effective max-level playback, scaled by its deck level.
- [confirmed by GhidraMCP] SoundSwitch subscribes to all four deck
  SoundSwitch IDs, filepaths, levels, elapsed times, beat positions, play states,
  loop states, and `crossfader` at string address `100d06bed`.

Verdict: the scripted mismatch is a bridge runtime content-selection/composition
bug. The bridge pack renderer is modeling "one active deck" while SoundSwitch U0
is produced by SoundSwitch's playback mixer. Matching U0 requires modeling
SoundSwitch's playback mixer inputs and render rules, not only selecting a deck.

### A3. Concrete scripted sample provenance

Captured sidecar row:

- [confirmed] `/tmp/rbss_artnet_truth_frames.jsonl:628505` has
  `active_deck=2`, `lighting_mode=scripted`, `scripted_active=true`,
  `transport=playing`, `elapsed_ms=124463`,
  `soundswitch_id={FB4EF1CA-E91C-4951-829F-DFF7D6FF0792}`,
  no static slots, no blackout, `visible=true`, `active_dark=false`, and bridge
  hash `57b253fac8b4ac85a1416340f5c919d44a6f3a26743eb7ce84004788b0015b71`.

Bridge-side value source:

- [confirmed] `render_scripted_frame(FB4..., 124463)` produces
  `[17,0,52,100,196,93,138,255,203,0,145,255,0,0,0,0,0,0,0]` and SHA256
  `57b253fac8b4ac85a1416340f5c919d44a6f3a26743eb7ce84004788b0015b71`.
- [confirmed] That frame is the FB4 scripted document event at `time=124459`,
  `source_order=23`, `raw_reference=23`,
  `resolved_cue_guid=07bdebaf2b53444dae9956e29eb8bc09`.

SoundSwitch-side value source:

- [confirmed] The target U0 sample
  `[17,0,55,0,0,93,138,255,255,0,145,0,0,0,245,0,0,0,0]`
  is not an FB4 scripted boundary frame.
- [confirmed] Its differing values line up with a second loaded scripted track,
  `528e8b22-bd17-41b9-a111-275d3e8b3031`, event `time=135124`,
  `source_order=65`, `raw_reference=140`,
  `resolved_cue_guid=fd9cf0804b213c4cada2c0b0e245e4b0`, whose frame is
  `[62,0,55,0,0,93,138,114,255,0,155,0,0,0,245,0,0,0,0]`.
- [confirmed] Channel source map for the target:
  - CH1, CH8, CH11 match FB4.
  - CH3, CH4, CH5, CH9, CH12, CH15 match the `528e...` track.
  - CH6 and CH7 match both.

Verdict: the scripted sample is a two-playback/mixer composite, not a single
pack parser error, fixture offset, or Art-Net pairing artifact. A one-deck bridge
render cannot consistently equal that U0 frame.

### A4. Fixture/channel mapping is not the scripted sample cause

- [confirmed] Pack compiler filters scripted/static render input to the primary
  fixture group `0x493`: `soundswitch_pack.py:31`,
  `soundswitch_pack.py:81-86`, `soundswitch_pack.py:115-120`.
- [confirmed] For the FB4 sample, rendering either observed fixture group gives
  the same bridge frame. Therefore the concrete FB4 mismatch cannot be explained
  by selecting group `0x493` versus `0x496`.
- [confirmed] The differing addresses are not a constant shift. The SoundSwitch
  target pulls different channels from different tracks.

Verdict: no fixture-address offset explains the scripted mismatch. Fixture
mapping still matters for parity, but it is not this root cause.

### A5. Runtime player fixture-group filtering bug

- [confirmed] `soundswitch_laser_player.py:_apply_attribute` accepts every loaded
  attribute and writes by `dmx_channel` only; it does not filter
  `row.fixture_group` in the baseline code: `soundswitch_laser_player.py:83-86`.
- [confirmed] Existing focused test expects non-primary fixture-group static rows
  to be skipped: `tests/test_soundswitch_laser_player.py:206-221`.
- [confirmed] The test run failed before the fix:
  `test_apply_layers_skips_malformed_without_zeroing_base` produces `(10,20,3)`
  instead of `(10,3,3)`.
- [implemented in current worktree] Runtime `_apply_attribute` now skips
  non-primary fixture groups before channel/value validation, and a scripted-cue
  regression covers the same policy.

Verdict: this was a parser/render parity bug and is fixed in the current
worktree. It is not the concrete scripted FB4 sample root cause because both
fixture groups render the same FB4 frame in that sample.

### A6. Autoloop SS-lit / bridge-dark root cause

- [confirmed] Native autoloop resolver returns software zero whenever its state is
  unseeded: `native_autoloop_resolver.py:201-202`.
- [confirmed] `LaserSceneExecutor.on_decision()` can return `None` for an
  already-active same scene/no-refire path while the executor still holds the
  active autoloop scene: `laser_executor.py:217-228`.
- [implemented in current worktree] The bridge now exposes the executor's
  latched autoloop scene (`laser_executor.py:391-406`) and `StateManager` falls
  back to it when `_native_captured_scene` is absent:
  `state_manager.py:4013-4018`.
- [confirmed] Autoloop report `/tmp/rbss_artnet_autoloop_60_1782857387.json`
  shows repeated SS-lit/bridge-dark hash pairs at lines 70-105, including bridge
  dark `076a27c7` versus SS lit `b3e2c328` count 1177 and bridge dark `076a27c7`
  versus SS lit `9c2b748d` count 494, with U1 truth present and no truth send
  drops/errors in the reported run.

Verdict: autoloop dark mismatches are a separate bridge runtime phase/state-latch
bug. The current worktree contains the minimal latch fix and regression test.

## Part B - Minimal Fix Plan

Task 1 - Keep the autoloop latch fix.

- Preserve `LaserSceneExecutor.current_autoloop_scene()`.
- Preserve the `StateManager` fallback from `_native_captured_scene` to the
  executor-latched scene.
- Keep the regression:
  `tests/test_state_manager_pack_driver.py:test_native_autoloop_seeds_from_executor_latched_scene_without_new_edge`.

Task 2 - Keep fixture-group filtering in the pure runtime renderer.

- Preserve the same primary fixture-group gate used by `soundswitch_pack.py` in
  `soundswitch_laser_player.py:_apply_attribute`.
- Preserve the scripted-event focused regression in
  `tests/test_soundswitch_laser_player.py` so non-primary scripted cue
  attributes are skipped, not just static-layer rows.
- Existing static-layer malformed test must pass.

Task 3 - Add a pure SoundSwitch playback-mixer renderer.

- Do not replace `render_scripted_frame()`. Add a new pure renderer beside it,
  e.g. `render_scripted_mixer_frame(...)`, that takes already-rendered playback
  light states plus explicit mixer inputs.
- Required inputs:
  - playback 0/1 scripted documents and elapsed positions for two-playback mode;
  - playback levels 0/1 as bytes or normalized floats;
  - colour/intensity crossfade byte;
  - attribute crossfade byte;
  - static-look cache/layers only after base parity is proven.
- Match Ghidra behavior for two-playback mode:
  - get both playback light states;
  - colour/intensity fade uses `0x470`;
  - attribute fade uses `0x471 / 255.0`;
  - cue-cache side switches to playback 1 at `attribute_fade >= 0.5`;
  - channel writes must be based on fixture profile/channel semantics, not a
    hand-maintained list of channel numbers.
- Match Ghidra behavior for four-playback mode separately:
  - compute effective playback by max deck level with the observed hysteresis;
  - render that playback's state scaled by its level.
- If the bridge does not yet decode a required mixer input, expose the gap as
  `unsupported_mixer_parity` instead of silently comparing one-deck output to U0.

Task 4 - Feed SoundSwitch-equivalent mixer inputs into pack output.

- StateManager must not use `active_deck` as a proxy for SoundSwitch's playback
  mixer.
- Add a narrow runtime snapshot containing only what the SoundSwitch pack output
  needs: deck playback levels, crossfader/crossfade bytes, playback mode, and
  per-playback scripted IDs/elapsed positions.
- Reuse existing decoded upfader values where they match SoundSwitch's deck
  `level`; do not invent crossfader values from active-deck labels.
- If crossfader/playback-mode decoding is absent or stale, fail closed with a
  clear status/sidecar diagnostic rather than emitting a false "matching" frame.

Task 5 - Upgrade the comparator/reporting layer after runtime parity exists.

- Keep U1-sidecar hash reconciliation unchanged.
- Add software-only classification for mismatches:
  - `single_deck_frame`: U0 equals one known deck render.
  - `two_playback_mixer_frame`: U0 equals the pure mixer render.
  - `bridge_dark_while_ss_lit`: bridge frame zero while SoundSwitch nonzero.
  - `fixture_group_leak`: bridge differs only by non-primary fixture-group rows.
  - `timing_mismatch`: no in-tolerance U0/U1 pair.
  - `unclassified_byte_mismatch`: evidence bundle required.
- Include channel source maps for mismatches, like the FB4/528e sample above.

## Part C - Constraints

- No bridge restart, runtime toggle, SoundSwitch automation, process-memory
  sampling, fixture-pack/config mutation, Enttec send, serial write, physical DMX,
  laser, LED/Govee, or hardware-adjacent action without explicit operator approval.
- The 200 Hz output path must not gain blocking I/O or Ghidra-dependent logic.
- Truth mode U1 remains an observation lane only. Production output policy and
  SoundSwitch-present suppression gates remain unchanged unless separately
  approved.
- Do not "fix" this by loosening comparator tolerance or ignoring lit mismatches.
- Do not hand-code a channel-number table for colour/pan/tilt/strobe if the
  fixture profile/channel map already carries the semantic class.

## Part D - Tests

Required focused tests before implementation is accepted:

1. `tests/test_state_manager_pack_driver.py`
   - `test_native_autoloop_seeds_from_executor_latched_scene_without_new_edge`
   - proves SS-lit/bridge-dark latch regression.
2. `tests/test_soundswitch_laser_player.py`
   - existing static-layer fixture-group skip test passes.
   - new scripted cue fixture-group skip test fails before Task 2 and passes
     after Task 2.
3. New pure mixer-renderer tests:
   - FB4 single-deck frame remains
     `[17,0,52,100,196,93,138,255,203,0,145,255,0,0,0,0,0,0,0]`.
   - Two-playback/mixer fixture reproduces the observed channel source map:
     CH1/8/11 from FB4, CH3/4/5/9/12/15 from `528e...`, CH6/7 shared.
   - Attribute-fade threshold test: below 0.5 uses playback 0 cue cache; at/above
     0.5 uses playback 1 cue cache.
   - Four-playback max-level effective index test matches Ghidra behavior,
     including the previous-max hysteresis.
4. `tools/artnet_compare.py --self-check`
   - preserves existing PASS/FAIL/INVALID behavior and adds classification
     coverage without hiding byte mismatches.

Current known test status from this investigation:

- `PYTHONPATH=/Users/bbui python3 -m unittest tests.test_soundswitch_laser_player`
  passes after the fixture-group fix.

## Part E - Acceptance

Software acceptance:

- The scripted sample is no longer explained as a fixture offset or comparator
  artifact. The implementation either:
  - renders the SoundSwitch-equivalent mixer frame, or
  - emits a hard diagnostic that required mixer inputs are unavailable/stale and
    refuses to claim parity.
- Autoloop report no longer has repeated bridge-dark/SS-lit pairs after an
  operator-approved restart/live recapture.
- Fixture-group tests pass and non-primary rows cannot leak into runtime render.
- Comparator reports whether each lit mismatch is single-deck, mixer, autoloop
  dark, fixture-group, timing, or unclassified.

Operator/live acceptance:

- Requires explicit approval before any restart, runtime toggle, SoundSwitch
  capture, Art-Net capture, process-memory sampling, or hardware-adjacent check.
- Healthy behavior after approval: U1 sidecar hashes remain present with no truth
  drops/overflow/send errors; lit scripted comparisons either match U0 or classify
  as a known unsupported mixer-state case with exact channel/source evidence;
  autoloop no longer emits bridge dark while SoundSwitch is lit for the same
  eligible active look.
- Hardware-visible DMX remains unvalidated until an operator-approved rig run.
