---
doc_status: current
truth_level: operator-authoritative target behavior
last_verified_commit: b16792a
last_verified_date: 2026-07-07
validation_scope: behavior contract plus software-tested Package 4 plumbing and the 2026-07-07 menu/follow-LED/brightness-floor/CH9=90 layer; held CH8/CH9 forwarding verified in software; menu chase CH8 values (172/68/100/164/72) are NOT hardware-validated (CH3/CH4 stay authored); no live or hardware validation. AWR-238 hot-plug recovery is transport-only and does not change color authority.
---

# Laser Color Authority

Status: AUTHORITATIVE TARGET BEHAVIOR; PACKAGE 4 PLUMBING + MENU/FOLLOW-LED LAYER IMPLEMENTED/SOFTWARE-TESTED (design approved by operator 2026-07-04; menu layer 2026-07-07)

This document defines how laser color is expected to behave now that the bridge
has the Package 4 color plumbing. Behavior that differs from this document is a
regression unless this document is intentionally updated. Code-grounded design detail lives in
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

Package 4's plumbing shipped disabled; it is now **enabled** (operator decision
2026-07-04, fixed-color chart) and the **menu/follow-LED layer** (2026-07-07)
sits on top of it. `config/laser_color_map.json` now has `enabled: true`, a
calibrated fixed-color CH8 table, `fixed_ch9: 90`, and a per-mood `menus` block.
Fail-open is unchanged: any disabled/missing-menu/invalid state passes authored
CH8/CH9 through.

**What the menu layer changed (2026-07-07):** instead of quantizing the LED
color to one solid CH8 per mood, each mood now has a small **menu** of options
(some solid colors, some two-color **chase** effects). The laser **follows the
LEDs' actual last-emitted color** (their real per-section wander, exposed as a
pure read `color_state()["live_rgb"]`), applies a **brightness floor** (the
laser is never picked dimmer than the LEDs), and on a **drop** fires the mood's
eligible **chase** instead of a flat solid. CH9 is now driven at `90` (chase
speed) instead of passthrough. Moods with no menu keep the legacy single-solid
nearest-fixed behavior. **CH3/CH4 are never read or written** — the chase
effects are authored at CH3=0/CH4=10 in the pack, so some chase CH8 values may
render slightly differently live; that is an accepted operator eyeball risk, not
a bug to "fix" by driving CH3/CH4.

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
   ladder), laser color is **menu-picked to follow the LEDs' last-emitted
   color** (2026-07-07). The pick reads `color_state()["live_rgb"]` (the LEDs'
   real per-section wander, quantized to the nearest fixed color), then within
   the mood's menu: non-drops track the eligible **solid** that matches the LED
   color; **drops fire the eligible chase** (two-color effect). A **brightness
   floor** removes any menu option dimmer than the LEDs (3-tier rank:
   white=3; cyan/green/yellow=2; blue/purple/red=1), and if everything is
   filtered it keeps the brightest option (never dark). Moods with no menu fall
   back to the legacy single-solid nearest-fixed pick. Because the LED engine
   already varies color per drop section, per-drop laser variation still emerges
   automatically. **"LEDs white → laser white" is delivered by the early white
   return (rule 6), NOT by the brightness floor** — at the menu-pick point white
   has already early-returned, so the floor only ever separates rank 1 from rank
   2 within a menu.
1b. **Per-tier chase divisions (AWR-170 B).** A chase menu entry's `chase` may be
   a single int (all drops render that division, byte-identical to before) OR a
   `{"standard"|"intense"|"monster": <ch8>}` dict. When it is a dict, the drop's
   F2 energy tier picks the division CLASS at the drop — harder drops spin the
   chase faster (the operator's red+white 100→116→140 ladder, seeded on `crimson`
   + `v2:EMBERCORE`); the two-color pair is unchanged. Missing tier keys fall back
   to `standard` then to the first present value; an all-junk dict fails closed
   (the entry is skipped, never invented). The tier is plumbed one hop from the
   f2_plan (`state_manager._laser_color_drop_tier`, a push-loop-safe lookup);
   `None`/unknown/`small` tier ⇒ `standard`, so F2-off / scripted / tier-less
   drops render exactly today's single value. Every menu WITHOUT the dict form is
   byte-identical.
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
   across the post-drop autoloop, CH9 (now driven at `90`) eases down so the
   moment decays instead of hard-stopping. Once the chart lands, the settle
   texture may optionally use the gradient/flowing-water families — an operator
   taste call, not a default.
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
    and reading the engine's held immutable snapshot on every pack drive needs
    no cross-thread machinery. The merge must never wait on the color engine.
12. **Fail-open = lasers keep rendering.** Missing, disabled, or all-null
    snapshots pass authored CH8/CH9 through. If a later LED color read fails,
    the engine keeps its previous held color instead of force-clearing it.
    Never "no lasers."

## Chart Gating

13. The chart gates **only the mapper's value table** — one CH8 value per
    fixed color, effect-family range boundaries, CH9 speed semantics. Package
    4 implements the plumbing (sampling, snapshot, merge seam, white-moment
    signal, settle and rainbow hooks) against the disabled/all-null pass-through
    table.
14. Chart sources, in leverage order: the fixture profile (operator has it);
    labeling the CH8/CH9 values already present in the pack; a supervised
    live visual pass for the ambiguous multi-color effects (operator: only
    knowable visually). The chart lands as pure config — zero code rework.
15. **Fixed-color half LANDED 2026-07-04** (operator-supplied camera
    calibration from the virtuallasernode project, sweep 2026-06-05,
    white-balanced): CH8 values 4-31 encode the seven fixed colors in
    4-value bands, calibrated order **W, R, Y, G, C, B, M**
    (`idx = (CH8-4)//4`). Cross-validation: every fixed-color CH8 value the
    pack ever authored decodes cleanly (10=red, 17=green, 21=cyan,
    24/25=blue, 28=magenta); all authored values ≥ 32 are effect-family
    territory. `config/laser_color_map.json` now carries red=10, green=17,
    cyan=21, blue=25, purple=28 (pack-proven in-band values), white=6,
    yellow=14 (mid-band; never pack-authored). **ENABLED by operator
    decision 2026-07-04** (takes effect at the next bridge start; the
    supervised first visual pass is still the hardware gate). The bundled
    enable-time change landed with it: the quantizer's `purple` anchor is
    now (255,0,255) — the config key `purple` maps to the fixture's MAGENTA
    band (28-31). Still pending from the operator: the CH8 effect/animation
    family ranges (≥ 32) and the CH9 speed curve — those gate ONLY the
    Rainbow laser tier and the settle texture; fixed color injection is
    complete without them (per-channel merge leaves authored CH9
    untouched).

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
5. Fail-open: missing/disabled/all-null snapshot → authored CH8/CH9 pass
   through unchanged; a read failure with an existing snapshot keeps the held
   color; no blocking of the render path.
6. Post-drop settle: CH9 monotonically eases across the post-drop window.
7. CH11 byte-identical everywhere with the color engine present vs absent.

## Implementation Notes

Implemented home: sampler/quantizer/producer in `laser_color_engine.py`, the
merge seam in `soundswitch_laser_player.py`'s Autoloop success path, the
white-moment flag in `led_dispatch_coordinator.py`, held-snapshot forwarding
in `state_manager.py`, and the chart at `config/laser_color_map.json`.
`load_laser_color_map()` resolves the chart path as env
`RBSS_LASER_COLOR_MAP_CONFIG` → module-relative default (AWR-186 M2: the frozen
bundle carries no chart, so the installer lands it in App Support and the
launch profile points the env at it; every source run leaves the env unset and
is byte-identical).
`led_color_engine.py` exposes `color_state()` for the current anchor RGB
without advancing RNG or mutating journey state.

**Menu/follow-LED layer (2026-07-07, `laser_color_menu_spec.md`):**
`LaserColorMap` parses a `menus` block into nested tuples; `_target()` picks
from the mood's menu using `_entry_brightness`/`_led_brightness` (module-level
`_BRIGHTNESS` 3-tier rank) and `_pick_menu_entry` (deterministic, no RNG).
`led_color_engine.py` stashes the LEDs' actual last-emitted color in
`self._last_emitted_rgb` inside **both** resolvers (`resolve_color` and the
active-engine `_v2_resolve_color`), clears it on v1↔v2 engine switch, and
surfaces it as `color_state()["live_rgb"]` (still a pure read — the write is in
the resolvers, which already mutate). `state_manager._sync_laser_color_if_needed`
adds the **quantized** `live_rgb` bucket to the re-sync signature (raw RGB would
flap the sig every 200 Hz tick). CH3/CH4 are never touched. Design detail:
`docs/plans/active/laser_color_engine_design_spec.md` Parts B, D, E and
`docs/plans/active/laser_color_menu_spec.md`.
