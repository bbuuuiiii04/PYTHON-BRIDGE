---
doc_status: current
truth_level: operator-authoritative target behavior
last_verified_commit: bd96b32
last_verified_date: 2026-07-04
validation_scope: behavior contract only; feature not implemented — no software, live, or hardware validation implied; CH8/CH9 value chart pending operator inputs
---

# Laser Color Authority

Status: AUTHORITATIVE TARGET BEHAVIOR; NOT YET IMPLEMENTED (design approved by operator 2026-07-04)

This document defines how laser color is expected to behave once the bridge
owns it. Behavior that differs from this document is a regression unless this
document is intentionally updated. Code-grounded design detail lives in
`docs/plans/active/laser_color_engine_design_spec.md`.

Sibling authorities: `drop_presentation_authority.md` (whether lasers fire at
all on a drop), `laser_blackout_authority.md` (blackout beats everything),
`palette_control_authority.md` (where the palette names come from).

## Meaning

SoundSwitch is out of the live path; the bridge renders the whole laser DMX
frame. On **autoloop (non-scripted) tracks, the LED color engine is the color
authority and the lasers follow it** — the bridge deliberately overwrites the
pack's authored CH8/CH9 on those frames. On **scripted tracks, the authored
show is sovereign**: lasers play exactly the cue colors baked into the pack,
and the color engine stands down completely.

## Vocabulary

| Term | Meaning |
| --- | --- |
| fixed colors | The laser's real color set: Red, Green, Blue, Cyan, Yellow, Purple, White. There is no RGB wheel. |
| effect families | CH8's upper ranges: color-change effects, RGB color-change effects, the "original color change" effect, flowing-water effect combinations, and a color-gradient effect (operator-stated taxonomy). |
| CH9 | Color speed — the rate of the active CH8 effect. |
| CH11 | Strobe. **Untouched by the bridge** (operator ruling 2026-07-04; future decision). |
| quantizer | The mapper from the LED engine's current color to the nearest fixed color. |
| white moment | A cue-mandated LED white event (drop white-strobe, white buildups, post-drop shatter, reserved white accent). |
| the chart | The pending CH8/CH9 value table: one CH8 value per fixed color, each effect family's range boundaries, and the CH9 speed curve. |

## Color Source Rules

1. On autoloop frames where lasers are firing (per the drop presentation
   ladder), laser color = **nearest fixed color to the LED engine's current
   color**, sampled at phrase anchors and per drop section. Because the LED
   engine already varies color per drop section, per-drop laser variation
   emerges automatically — it is not a separate feature.
2. The quantizer's tie-breaks are deterministic (fixed preference order).
   Same inputs, same color, every time.
3. **White is reserved.** The quantizer never outputs White from
   nearest-color math; White fires only for white moments (rule 6) and
   `white_sand` (rule 7). Yellow will rarely or never be selected (the LED
   hue space excludes yellow/orange) — that is expected, not a bug.
4. A drop landing mid-palette-fade samples the blended color and quantizes
   it. Acceptable by design.
5. On scripted frames, diagnostic frames, idle, and any uncertain state, the
   engine writes **nothing**. "Unsure → do not inject" is structural: color
   injection exists only in the healthy autoloop render path.

## White Rules

6. **White-moment mirroring:** during the LED engine's cue-mandated white
   moments, lasers go White (CH8 white value) for the duration of the moment.
   Non-scripted only; scripted white already rides authored cues.
7. **`white_sand` → laser White**, sustained until the palette's track/lock
   rules revert it. One shared palette name, per-engine value.

## Motion Rules

8. **Post-drop settle:** the drop fires at full palette color and speed;
   across the post-drop autoloop, CH9 speed eases down so the moment decays
   instead of hard-stopping. Once the chart lands, the settle texture may
   optionally use the gradient/flowing-water families — an operator taste
   call, not a default.
9. **Rainbow mode (laser tier):** while Rainbow mode is on, wherever lasers
   fire, CH8 carries a color-change/RGB-change effect-family value at a CH9
   speed instead of a quantized fixed color. Until the chart lands, Rainbow
   mode is LED-only.

## Placement & Safety Rules

10. Color injection lives **inside the frame renderer's autoloop path,
    beneath the blackout/emergency gate and beneath static-override
    layering**: blackout zeroes everything regardless of injected color; a
    manually-held static look wins over engine color; injecting color onto a
    blacked-out, diagnostic, or zero frame is forbidden by construction.
11. The color computation must never block or add I/O to the render path. It
    is pure in-memory math; since LED dispatch and the pack render share the
    state-manager thread (verified 2026-07-04), computing at dispatch time
    and reading an immutable snapshot at render time needs no cross-thread
    machinery. The merge must never wait on the color engine.
12. **Fail-open = authored color passes through.** If the color producer
    errors, stalls, or its snapshot is stale, the frame ships with the pack's
    authored CH8/CH9 — exactly today's output. Lasers keep moving; only the
    follow-the-LEDs behavior is lost. Never "no lasers."

## Chart Gating

13. The chart gates **only the mapper's value table** — one CH8 value per
    fixed color, effect-family range boundaries, CH9 speed semantics. All
    plumbing (sampling, snapshot, merge seam, white-moment signal, settle and
    rainbow hooks) is implementable now against a pass-through table.
14. Chart sources, in leverage order: the fixture profile (operator has it);
    labeling the CH8/CH9 values already present in the pack; a supervised
    live visual pass for the ambiguous multi-color effects (operator: only
    knowable visually). The chart lands as pure config — zero code rework.

## Required Behavior Tests

1. Quantizer: known RGB inputs → expected fixed colors; deterministic
   tie-breaks; White never produced by nearest-color math.
2. Injection scope: autoloop-with-lasers frames only — scripted, diagnostic,
   idle, suppressed, and blacked-out frames byte-identical with the engine
   present vs absent.
3. Static override over injected color; blackout over everything (frame is
   ZERO regardless of injected values).
4. White moment: flag asserted → CH8 white for the moment's duration, then
   reverts to quantized palette color.
5. Fail-open: producer dead/stale snapshot → authored CH8/CH9 pass through
   unchanged; no blocking of the render path.
6. Post-drop settle: CH9 monotonically eases across the post-drop window.
7. CH11 byte-identical everywhere with the color engine present vs absent.

## Implementation Notes

Planned home: sampler/quantizer/producer in `laser_color_engine.py`
(mirroring `led_color_engine.py`), the merge seam in
`soundswitch_laser_player.py`'s autoloop path, the white-moment flag published
from the LED render side, and the chart at `config/laser_color_map.json`.
A new public LED-engine accessor for "current anchor RGB" is required — no
such API exists today. Design detail:
`docs/plans/active/laser_color_engine_design_spec.md` Parts B, D, E.
