# Opus Handoff: Integrating M2 Motion Skeletons into the Bridge

## Context
Antigravity and I have been prototyping a new set of LED looks based on a slot-based "M2 Motion Field" architecture. Antigravity has perfected the visual geometries, animation timing, and overall aesthetic of these cues.

Your task is to take these completed geometric formulas and cleanly wire them into the actual `rb_ss_bridge_v2` runtime engine (e.g., `led_color_engine.py` and `govee_frame_renderer.py`). 

You can find the standalone prototype code with the exact math and logic here:
`/Users/bbui/.gemini/antigravity-ide/brain/dfbaeb5b-bff1-4229-b752-205a92c40a78/scratch/motion_skeletons.py`

## The Prototyped Cues

1. **`groove_center_chase`**: A completely smooth, dual-head comet chase shooting outward from the center. It uses dynamic color slots 0-4.
2. **`post_drop_firework_chase`** (currently named `post_drop_center_chase` in the script): Uses the smooth comet as a base, but overlays a highly chaotic, rapid-fire sequence of pure white 0.1-beat "firework bursts" across 80% of the strip. This firework overlay occurs EXCLUSIVELY during the 4th beat of the 4-beat cycle. It uses Slot 5 for pure white.
3. **`breakdown_star_twinkle_sand`**: A very dark ambient baseline where individual segments smoothly breathe in and out over 1-4 beat lifespans. This one is hardcoded to a "Dune Sand" RGB palette. Max brightness is strictly capped at 30%.
4. **`breakdown_star_twinkle`**: The dynamic `MotionField` version of the star twinkle, capable of accepting any standard color palette.
5. **`breakdown_full_breathing`**: Synchronized full-strip breathing (like a lung), with the color slowly drifting across the palette over 32 beats.
6. **`groove_center_burst_retract`**: A volume bar effect that shoots outward aggressively at the start of a beat and rapidly retracts inward during the decay phase.

## Your Responsibilities

Antigravity owns the math and the aesthetic; you own the architectural integration.

1. **Architecture Translation**: The prototype uses a 6-slot system where Slots 0-4 are the gradient palette, and Slot 5 is strictly reserved for Pure White. You must translate this `field[idx][slot]` logic into the bridge's native `govee_frame_renderer.py` (which currently expects RGB `Frame` outputs), or fully implement the M2 architecture if that is the active plan. Do not alter the core geometric timing or math (e.g., the 0.05 distance checks for fireworks).
2. **Post-Drop Looks**: For the firework chase, **DO NOT** overwrite the existing `post_drop_chase_*` looks. Instead, add a completely new family of looks named `post_drop_firework_chase_*` (e.g., `_blue`, `_cyan`, `_cyan_white`) to `govee_frame_renderer.py` and register them in the `_LOOKS` dictionary.
3. **Breakdown/Ambient Looks**: Wire the new `breakdown_*` cues into the engine so they are officially available as selectable ambient/breakdown options in the look director. You'll need to figure out the best way to handle the hardcoded `sand` palette version vs the dynamic version.
4. **Validation**: Ensure that all color bindings, beat fractions, and rendering loops correctly interface with `led_color_engine.py` and the UDP transport without dropping frames.
