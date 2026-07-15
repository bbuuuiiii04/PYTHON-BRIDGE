---
doc_status: current
truth_level: software-tested
last_verified_commit: e34488c
last_verified_date: 2026-07-15
validation_scope: >
  H612D LED Studio (AWR-196): offline production-runner frame composition,
  fixed 60-by-6 emitter view, timestamp-held playback, calibration sequence v2,
  profile evidence guards, and the local web service are software-tested.
  Generated timing uses an ideal grid. Device color, PWM, latency, physical
  response, packet delivery, and hardware cadence remain unmeasured;
  SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# H612D LED Studio

This local tool shows what the bridge asks the Govee H612D to do. It models the
known fixture shape: **60 controllable RGB segments, six physical LEDs per
segment, 360 LEDs total, 49.2 ft / 14,996.16 mm**. Room shape and strip placement
are deliberately out of scope.

Each group of six dots receives one RGB command because the H612D exposes 60
groups, not 360 separately controllable pixels.

## What is exact today

The studio is fixed to the supplied H612D control shape: 60 RGB command
segments, each displayed as six matching emitters. It rejects replay files with
any other segment count instead of stretching or guessing.

For a **Production effect**, the server drives the real
`GoveeRealtimeRunner` offline with a deterministic beat clock and replaces its
network transport with an in-memory collector. Production effect rendering,
runner fades, strobe shaping, and frame composition are therefore executed by
the Python production classes, not copied into JavaScript. The result is labeled
`production_runner_offline`.

For a **Configured look**, the same path starts with the effect and parameters
read from the current look config. Those parameters are labeled
`pre_runtime_injection`: a running bridge can still inject per-frame color or
other live state before it reaches the runner. This source is useful for
authoring the configured base, but it is not a recording of a final live
`EffectSpec`.

Generated frames use an explicit ideal clock and are labeled `ideal_grid`.
That makes repeatable offline comparison possible; it does **not** reproduce
macOS scheduling jitter, network timing, or controller timing.

Recorded frames keep their original `t_ms` timestamps. Playback uses
sample-and-hold: a frame remains visible until the next timestamp. The browser
does not invent in-between frames. A header `duration_ms` preserves the final
hold exactly. Legacy files without it receive a clearly labeled one-frame
duration estimate. The browser's **DRAW**, **RAF**, and **MISSED** readouts report
browser drawing health, not Govee hardware health.

The two badges over the fixture state the frame source and timing source. The
calibration badge describes only the saved evidence state. With the committed
profile it reads `UNMEASURED`, so the identity transfer is visibly an assumption.

## What is not exact yet

The capture boundary is before the network and physical controller. The studio
does not yet know or prove:

- whether every packet reaches the controller, or when it arrives;
- controller buffering, dropped/late-frame behavior, PWM, or refresh scanning;
- the H612D's measured RGB transfer, low-level cutoff, peak brightness, or
  mixed-color behavior;
- measured latency, color transition time, or phone/camera/display color error;
- scheduling jitter from a running bridge under real system load.

The current screen model is intentionally small: one gamma value, three channel
gains, one brightness value, a three-tap neighbor bleed, one latency offset, and
an optional single slew constant. Real evidence may require a per-channel lookup
table, load-dependent brightness, a cutoff/dead-zone model, asymmetric color
mixing, or a multi-stage temporal model. The committed profile is an identity
starting point, not a hardware measurement. A convincing-looking screen is not
validation, and 100% physical parity cannot honestly be claimed yet.

## Start it

```bash
python3 -m tools.led_sim_web
python3 -m tools.led_sim_web --port 8767 --profile config/led_sim_profile.json
```

Open `http://127.0.0.1:8767`. The server listens on loopback only. The default
saved profile is `config/led_sim_profile.json`, which is gitignored. If it does
not exist, the committed example is loaded without writing anything.

## Author mode

Choose a source and press its render button:

- **Configured look (before live injection)** reads the current look config,
  including its stable seed, base effect parameters, sync mode, and beat
  division, then uses the real runner offline.
- **Production effect** runs an effect through the same offline runner capture.
- **Lab draft** uses the Template Lab preview path and is labeled as a lab
  pipeline, not a production-runner result.
- **Recorded frames** loads frames-JSONL from this repo or the system temp
  directory.

The transport supports play/pause, loop, exact-frame scrubbing, left/right
frame stepping, and Space to play or pause. The fixture view always shows all
360 physical emitters grouped into their 60 command segments.

## Calibrate mode

These deterministic sequences are generated offline. Selecting one does not
send it to the strip. Sequence results include the version
`h612d-cal-v2` and a SHA-256 hash of the exact generated payload.

| Sequence | Measurement purpose |
| --- | --- |
| Segment map | Walks segments 00 through 59 at command levels 16, 64, and 255 with black gaps. Intended to measure order, direction, group boundaries, low-level cutoff, and whether all six emitters in a group behave together. |
| Color response | Exercises dense near-black through full-scale RGB and white ramps plus cyan, magenta, yellow, orange, and violet. Every patch runs at isolated, alternating-segment, and full-strip loads to reveal transfer and load-dependent dimming. |
| Timing response | Runs three color-coded passes of 256 uniquely identifiable counter frames. Every counter frame keeps exactly 28 segments lit, then short holds and one-/two-frame chases follow. This lets a later sender log be matched to captured video while minimizing brightness changes between codes. |

Static white, red, green, blue, gray-50, and segment-0 frames are also
available.

### Capture protocol for the first real measurement

No color checker is required for a first **relative** profile. For useful phone
evidence:

1. Put the phone on a tripod and keep one lens, distance, angle, framing, and
   room-light state for the entire run.
2. Lock exposure, shutter, ISO, white balance, focus, resolution, and frame rate
   wherever the phone allows it. Disable HDR, Night mode, automatic frame-rate
   changes, stabilization, and automatic lens switching where possible. The
   exact controls depend on the phone model, so the model must be recorded.
3. Keep every original camera file. Do not send it through social media, chat,
   or any service that recompresses or changes frame timing.
4. Run the timing sequence at requested rates 10, 20, 30, 40, and 60 FPS, three
   times each. Record once in a locked normal-video mode and again at the
   phone's highest trustworthy slow-motion mode.
5. Run the segment and color sequences without changing the locked camera or
   room setup. The color sequence holds each patch long enough for steady-frame
   sampling.
6. The future live sender must log, for every uniquely coded frame, its sequence
   version/hash, code, monotonic attempt time, and transport success/failure.
7. Record H612D firmware, phone model, camera settings, capture date, and any
   remaining unknowns. SHA-256 hash the untouched capture and the exact sequence.

A phone can establish repeatability, relative channel response, visible cutoff,
relative timing, and many dropped/held-frame patterns. It cannot establish
absolute colorimetry, luminance, or camera-independent perception. Those need a
colorimeter or spectrometer, a characterized laptop display, and ideally a
photodiode plus a shared command clock for timing/PWM proof.

Actual strip capture is a separate, explicit live operation. Before any future
sender contacts the H612D, the operator must approve the exact phrase:
`LIVE H612D CALIBRATION APPROVED`. Stopping or restarting the bridge requires a
separate approval. The current studio contains no hardware sender.

## Device profile

| Field | Meaning |
| --- | --- |
| `gamma` | Fitted command-value to visible-level curve. |
| `white_point` | Fitted red, green, and blue channel gains. |
| `brightness` | Fitted overall display level. |
| `glow_radius`, `glow_gain` | Screen-only visualization of one physical emitter's halo. |
| `bleed` | Fitted light spill into adjacent segments; endpoints never wrap into each other. |
| `fps` | Requested offline runner and playback cadence. Default 60; not a measured H612D refresh claim. |
| `latency_ms` | Fitted display offset. Default zero is an assumption. |
| `hold_mode` | `zoh` holds exact frames; `slew` applies a fitted transition response. |
| `slew_ms` | Fitted transition constant. Slew is ignored while `calibration_status` is `unmeasured`. |
| `calibration_domains` | Separate `color`, `timing`, and `spatial` evidence states. |
| `calibration_status` | Derived whole-profile state: all unmeasured → `unmeasured`; all measured → `measured`; every mixed/relative case → `relative`. |
| `calibration_evidence` | Sequence/capture hashes, firmware, phone and camera settings, date, measured fields, fit residuals, and remaining unknowns. Absolute `measured` status also requires a named reference instrument. |

The server refuses to save `relative` or `measured` status without its required
evidence. Editing any transfer or timing control in the UI resets all domains to
`unmeasured` and clears old evidence so stale measurements cannot be carried
forward silently. Slew is used only when both the whole profile and timing
domain are relative or measured.

Old room-layout profiles are accepted in memory by overlaying their compatible
values onto the fixed H612D defaults. They are not silently rewritten.

## Frames-JSONL

Line 1 is a header. Every later line carries one 60-segment frame and its
nondecreasing timestamp:

```json
{"v":1,"kind":"header","fps":60,"segments":60,"duration_ms":8000,"meta":{"name":"beat_chase","frame_source":"production_runner_offline","timing_source":"ideal_grid"}}
{"v":1,"t_ms":0,"frame":[[255,0,0],[0,0,0]]}
```

The shortened frame above is illustrative; a valid H612D line contains exactly
60 RGB triples. Generate an offline production-runner composition without
starting the web server:

```bash
python3 -m tools.led_sim_engine render-jsonl --name beat_chase \
  --out /tmp/chase.jsonl --fps 60 --duration-s 8 --bpm 128
```

## View seam

`tools/led_sim_assets/ledsim-view.js` is a drawing-only ES module:

```js
createLedSimView(canvas, profile) -> { renderFrame(frame), setProfile(profile), destroy() }
```

It does not fetch, save, or send frames. The Python engine contains the tested
reference transfer and linear-bleed calculations mirrored by the view.

## Hard lines and checks

- No Govee UDP, discovery, cloud, bridge-runtime, subprocess, or non-loopback
  network contact.
- POST requests require a local Host header and JSON content type.
- Reads the LED look config; writes only the chosen simulator profile, and only
  when **Save values** is pressed after validation.
- Matching command frames do not prove device receipt or visible parity.
- `production_runner_offline` does not mean a live bridge capture, and
  `ideal_grid` does not mean measured FPS parity.
- Configured-look parameters are read before live runtime injection.
- Six displayed LEDs per segment are a control-group model, not six individual
  commands.

Focused checks:

```bash
python3 -m unittest tests.test_led_sim_engine tests.test_led_sim_service
```

Current focused result: **42 tests passed** on 2026-07-15. This is software
proof for the offline studio only; no H612D hardware was exercised.
