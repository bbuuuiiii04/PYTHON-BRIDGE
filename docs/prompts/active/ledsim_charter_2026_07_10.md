# LEDSIM charter — accurate LED render & simulation (operator order ~23:50)

doc_status: current
truth_level: dispatch-charter (ACTIVE)
seat: dedicated Fable/xhigh manager lane `ledsim`, own build workflow, full review chain

## Operator order (verbatim intent)

"Queue up a Fable xHigh agent to work on an ACCURATE LED RENDER and SIMULATION...
Needs to be a near perfect real life representation."

## Hardware ground truth (operator-supplied, 2026-07-09 ~23:50)

- Govee **H612D** (Strip Light S, RGBIC segmented color control, Wi-Fi; box shows
  32.8ft SKU — operator's install is the 15m/49.2ft length)
- 24V DC, 2A, 48W
- **360 individual LEDs → 60 controllable segments × 6 LEDs per segment**
  (matches the bridge's 60-segment frame width)
- Mount: **top-of-wall perimeter of a rectangular living room** ("[ ]" — full loop)
- Room: RECTANGULAR, strip on the full perimeter at top-of-wall. Operator ruling
  2026-07-10 ~00:4x: NO room shots — geometry is SELF-CALIBRATED in the sim.
  One dimension supplied: "2284" (unit unconfirmed; treat as mm ⇒ ~2.28m short
  wall; with full-perimeter coverage 2(a+b)=15m ⇒ long wall ≈ 5.22m — DEFAULT
  layout only, everything below overrides it).
- SELF-CALIBRATION IS THE DESIGN (replaces photos): the four corner positions
  (as segment indices), the start-segment/controller corner, and travel
  direction are DRAGGABLE calibration knobs in the sim UI. Calibration flow:
  operator plays a chase on the real strip, drags corners/start until the sim
  matches what his eyes see, saves — persisted as the device profile. Strip
  macro photos on file with the executive (per-segment IC, alternating emitter
  packages, cut pads, powered head) inform the diffusion/bleed model.

## The five accuracy axes (what "near perfect" decomposes into)

1. **Geometry**: render the 60 segments on the ROOM's perimeter (top-down or
   3D-lite view), not a flat bar — corner mapping, direction of travel, start
   offset. Chases must visibly run around the room; symmetric effects must hit
   the walls they really hit.
2. **Photometrics**: LED vs sRGB — gamma/perceived-brightness curve, RGB-mix
   white vs canvas white, per-segment diffusion (6 LEDs under one diffuser),
   adjacent-segment bleed, and CRITICALLY the indirect wash: perimeter strips
   are seen mostly as ceiling/wall glow, so simulate surface wash, not just
   emitter dots.
3. **Temporal truth**: model the live pipeline (frame-engine ~60fps cadence,
   LAN transport pacing, device response/latency of the H612D), NOT the ideal
   preview grid; optional latency knob, calibrated.
4. **Data-true input**: consume the real renderer output (same MotionField/Frame
   path as govee_frame_renderer + real palette-engine state); support (a) lab
   drafts, (b) production looks, (c) replay of recorded session frames.
5. **Calibration loop** (hardware is never the paper ideal): a test-pattern
   procedure comparing sim vs the physical room (operator eyeball or phone
   photo), with per-channel gamma/brightness/bleed knobs persisted as the
   device profile. Ship knobs, not assumptions.

## Constraints

- Fable/xhigh seat (standing operator order); NO Fable Agent-tool subagents —
  delegation via tmux lanes only. Full adversarial review before any gate
  (runtime-behavior rule). Staged/isolated: the sim is tooling — it must never
  touch the show runtime paths; integration with the Lab preview happens via
  the pad-round coordination (fence with the pad manager).
- 8GB machine: the sim must run lightweight (canvas/WebGL in the existing pad
  web stack preferred over new heavy deps — ladder: existing stack first).
- Registry id assigned at dispatch by the executive. Signals + report files per
  fleet protocol (executive is outside tmux; mailbox + signal files).

## Registry

AWR-196. Dispatched 2026-07-10 ~00:4x, lane `ledsim`, Fable/XHIGH.
