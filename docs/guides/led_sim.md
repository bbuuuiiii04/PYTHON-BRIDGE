---
doc_status: current
truth_level: software-tested
last_verified_commit: 138a2d2
last_verified_date: 2026-07-10
validation_scope: >
  LED room simulator (AWR-196): engine + server + browser UI implemented and
  software-tested (24 unit/service tests). The sim's on-screen accuracy against
  the real room is operator-calibrated and NEVER hardware-proven by this repo;
  SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# LED Room Simulator

A local web page that shows what the room's Govee strip does when the real
renderer plays an effect — a top-down view of the room with the strip drawn
around the walls, including the soft wash of light it throws into the room.

The frames come from the exact same code that lights the real strip
(`govee_frame_renderer.py`). The sim reimplements zero effects: if the sim
shows a chase turning the corner at segment 21, that is what the renderer
told it, not a drawing guess.

**What it never does:** the sim never talks to the Govee device (no network
sends of any kind — its only socket is its own local page on port 8767), never
touches the running bridge, and never edits lighting configs. It only reads
them. It is safe to leave open during a live mix.

## Start it

```bash
python3 -m tools.led_sim_web            # http://127.0.0.1:8767
python3 -m tools.led_sim_web --port 8767 --profile config/led_sim_profile.json
```

The pad stays on 8766; the sim takes 8767. Your saved room calibration lives
in `config/led_sim_profile.json` (gitignored, like other live configs); until
you save one, the committed example defaults are used.

## Play something

Pick a source, hit **Render**, and it plays in the room view:

- **Production effect** — any renderer effect by name.
- **Production look** — your look configs (`config/led_look_director.json`),
  resolved to their effect + params.
- **Lab draft** — Template Lab drafts, through the same lab loader the Pad
  uses. If the lab module is broken mid-edit, the sim says so and everything
  else keeps working.
- **Replay file** — a frames-JSONL file (see below).

Transport: play/pause, loop, scrub. BPM, seed, and duration shape the render
request exactly like the Pad's previews do — same beat math, so the same
effect + params + seed + bpm + fps gives identical frames in both tools.

## Calibrate it to YOUR room (the whole point)

The defaults are assumptions, not measurements. Two steps, both in the
**Calibrate** panel:

1. **Geometry** — where the strip actually sits. Play the same slow effect on
   the real strip from the Pad (there's a "slow beat_chase" preset button),
   then drag the four corner handles, slide the seg-0 handle, or click the
   direction arrow until the sim's motion matches the room: corners turn where
   the real corners turn, direction matches, start matches.
2. **Photometrics** — how the strip's light actually looks. Put a test card on
   the real strip (white / red / green / blue / gray50 / single segment
   buttons), hold your phone photo next to the canvas, and turn the knobs
   until they match.

Hit **Save profile** when it looks right. Knobs are local until saved; Revert
reloads the last save.

### Knob meanings (plain language)

| Knob | What it models |
| --- | --- |
| `gamma` | How the strip compresses dim vs bright values — higher = dims fade faster. |
| `white R/G/B` | Color cast of the strip's "white" (per-channel gain). |
| `brightness` | Overall output level. |
| `diffusion (seg)` | How wide one segment's glow smears along the wall. |
| `bleed` | How much each segment leaks into its two neighbors (ring-wrapped). |
| `wash reach mm` | How far the indirect glow reaches into the room. |
| `wash gain` | How strong that indirect glow is. |
| `fps` | Playback cadence of rendered frames. |
| `latency ms` | Delay between "renderer says" and "strip shows". |
| `hold mode` | `zoh` = frames switch hard; `slew` = colors glide toward each new frame. |
| `slew ms` | How slow that glide is (models unknown LED controller response). |

Every one of these is a calibration knob, not a claim about the hardware —
your eyes against the real room are the only truth source.

## Frames-JSONL (replay format)

Line 1 header, then one line per frame:

```json
{"v": 1, "kind": "header", "fps": 60, "segments": 60, "meta": {"name": "beat_chase"}}
{"v": 1, "t_ms": 0, "frame": [[255, 0, 0], [0, 0, 0], "… 60 pixels total"]}
```

Generate one offline (no server needed):

```bash
python3 -m tools.led_sim_engine render-jsonl --name beat_chase --out /tmp/chase.jsonl \
  --fps 60 --duration-s 8 --bpm 128
```

The replay loader only accepts files inside this repo or the temp dir. There
is no live-session frame capture — that would need a runtime tap and is out of
scope for this round.

## The view seam (for the future Pad integration)

`tools/led_sim_assets/ledsim-view.js` is a self-contained ES module:

```js
createLedSimView(canvas, profile) -> { renderFrame(frame), setProfile(p), hitTest(x, y), destroy() }
```

It draws only — it never fetches or persists. A future Pad round can mount
this module and feed it frames; nothing else is coupled. The view's
photometric/bleed/geometry formulas are deliberate JS mirrors of
`tools/led_sim_engine.py` (each carries a lockstep comment); the Python twins
carry the unit tests.

## Hard lines

- No device contact, ever: no UDP, no transport/discovery imports, loopback
  HTTP on 8767 only.
- Reads `config/led_look_director.json`; writes ONLY
  `config/led_sim_profile.json`, and only via validated Save.
- A matching sim render does not prove room-visible hardware behavior.

Tests: `python3 -m unittest tests.test_led_sim_engine tests.test_led_sim_service`.
