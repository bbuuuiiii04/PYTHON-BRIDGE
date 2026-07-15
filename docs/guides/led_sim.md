---
doc_status: current
truth_level: software-tested
last_verified_commit: f800912
last_verified_date: 2026-07-15
validation_scope: >
  H612D LED Studio (AWR-196): fixture-level command-frame capture, 60-by-6
  emitter view, timestamp-held playback, calibration sequences, and local web
  service are software-tested. Device color, PWM, latency, physical response,
  packet delivery, and hardware cadence remain unmeasured;
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

For a production effect or look, the server drives the real
`GoveeRealtimeRunner` with a deterministic beat clock and replaces only its
network transport with an in-memory capture. The 60 RGB values shown for each
frame are therefore the values the runner attempted to hand to the transport
for that controlled input. Production effect rendering, runner fades, strobe
shaping, and runner composition are not reimplemented in JavaScript.

Recorded frames keep their original `t_ms` timestamps. Playback uses
sample-and-hold: a frame remains visible until the next timestamp. The browser
does not invent in-between frames. Its **PAINT** and **SKIP** readout reports
browser drawing health, not Govee hardware health.

## What is not exact yet

The capture boundary is before the network and physical controller. The studio
does not yet know or prove:

- whether every packet reaches the controller, or when it arrives;
- controller buffering, dropped/late-frame behavior, PWM, or refresh scanning;
- the H612D's measured RGB transfer, low-level cutoff, peak brightness, or
  mixed-color behavior;
- measured latency, color transition time, or phone/camera/display color error;
- scheduling jitter from a running bridge under real system load.

The committed profile is an identity starting point, not a hardware
measurement. A convincing-looking screen is not validation.

## Start it

```bash
python3 -m tools.led_sim_web
python3 -m tools.led_sim_web --port 8767 --profile config/led_sim_profile.json
```

Open `http://127.0.0.1:8767`. The server listens on loopback only. The default
saved profile is `config/led_sim_profile.json`, which is gitignored. If it does
not exist, the committed example is loaded without writing anything.

## Author mode

Choose a source and press **Render look**:

- **Production look** reads the current look config, including its stable seed,
  effect parameters, sync mode, and beat division, then uses the real runner.
- **Production effect** runs an effect through the same offline runner capture.
- **Lab draft** uses the Template Lab preview path and is labeled as a lab
  pipeline, not a production-runtime capture.
- **Recorded frames** loads frames-JSONL from this repo or the system temp
  directory.

The transport supports play/pause, loop, exact-frame scrubbing, left/right
frame stepping, and Space to play or pause. The fixture view always shows all
360 physical emitters grouped into their 60 command segments.

## Calibrate mode

These deterministic sequences are generated offline; selecting one does not
send it to the strip:

| Sequence | Measurement purpose |
| --- | --- |
| Segment map | Black/white sync marks, then segments 00 through 59 one at a time; verifies order, direction, group boundaries, and six-LED grouping. |
| Color response | RGB and white ramps at 0, 1, 2, 4, 8, 16, 32, 64, 96, 128, 160, 192, 224, and 255, followed by cyan, magenta, and yellow references. |
| Timing response | One- through 30-frame black/white holds plus one- and two-frame 60-segment chases; exposes frame holds, dropped steps, transition time, and slow-motion/PWM clues. |

Static white, red, green, blue, gray-50, and segment-0 frames are also
available.

No color checker is required for a first relative profile. A fixed phone on a
tripod with exposure, white balance, focus, lens, framing, and recording mode
locked can measure repeatability and relative RGB/timing response. It cannot
establish absolute colorimetric parity; that claim needs measured reference
equipment and a characterized laptop display.

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
| `calibration_status` | `unmeasured`, `relative`, or `measured`; it must describe the evidence honestly. |

Old room-layout profiles are accepted in memory by overlaying their compatible
values onto the fixed H612D defaults. They are not silently rewritten.

## Frames-JSONL

Line 1 is a header. Every later line carries one 60-segment frame and its
nondecreasing timestamp:

```json
{"v":1,"kind":"header","fps":60,"segments":60,"meta":{"name":"beat_chase"}}
{"v":1,"t_ms":0,"frame":[[255,0,0],[0,0,0]]}
```

The shortened frame above is illustrative; a valid H612D line contains exactly
60 RGB triples. Generate a production-runtime capture without starting the web
server:

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
- Reads the LED look config; writes only the chosen simulator profile, and only
  when **Save values** is pressed after validation.
- Matching command frames do not prove device receipt or visible parity.
- Six displayed LEDs per segment are a control-group model, not six individual
  commands.

Focused checks:

```bash
python3 -m unittest tests.test_led_sim_engine tests.test_led_sim_service
```
