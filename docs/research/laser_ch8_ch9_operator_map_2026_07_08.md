---
doc_status: current
truth_level: operator-measured
last_verified_commit: b0bbcb3
last_verified_date: 2026-07-08
validation_scope: hand-measured by the operator on the physical lasers at CH3=0 / CH4=10 (the same authoring condition as the config chase values); annotations are the operator's own taste marks; rendering under other CH3/CH4 animation states remains eyeball-gated live
---

# Laser CH8/CH9 operator hand-map (2026-07-08)

The operator's complete measured CH8 chase/effect vocabulary and CH9 semantics,
transcribed verbatim from his 2026-07-08 session notes. This supersedes
inference from capture corpora for CH8/CH9 design: **this is ground truth.**

Annotation key (operator's own): `!!` = good, more `!` = better,
`⭐️` = favorite, `xx` / `xox` = dislike.

## CH8 (measured at CH3=0, CH4=10)

| CH8 | Effect | Operator marks |
| --- | --- | --- |
| 32 | all color cycling | |
| 36 | red green blue color cycling | |
| 40 | all color cycling with white outline at the ends (w bluuuueeeee w) | |
| 44 | red + white + green + white + blue + white color chasing | |
| 48 | red + white + green + white + blue + white + yellow + white + cyan + white + white chasing | |
| 52 | red + white chasing | !! ⭐️ |
| 56 | green + white chasing | !! |
| 60 | blue + white chasing | !! |
| 64 | yellow + white chasing | !! |
| 68 | cyan + white chasing | !! ⭐️ |
| 72 | purple + white chasing | !! |
| 76 | purple + cyan + white chasing | !! |
| 80 | yellow + green + white chasing | !! |
| 84 | red + purple + white chasing | !! |
| 88 | blue + cyan + white chasing | !! ⭐️ |
| 92 | red + green + blue chasing | |
| 96 | yellow + cyan + purple chasing | |
| 100 | red + white chasing, more divided (rrwwrrww) | !!!! ⭐️ |
| 104 | purple + yellow chasing | xx |
| 108 | red + white + green + white chasing | xx |
| 112 | purple + cyan + yellow + white chasing (blank space between colors) | xox |
| 116 | red + white chasing, even more divided (rwrwrwrwr) | !!!!!! |
| 120 | green + white chasing | !!!!!! |
| 124 | blue + white chasing | !!!!!! |
| 128 | purple + yellow chasing | !!!!!! |
| 132 | all color chasing | !!!!!! |
| 136 | all color chasing (blank space between colors) | xox |
| 140 | red + white chasing, way more divided (rwrwrwrwrwrwrwr) | !!!!!!!!!! |
| 144 | green + white chasing | !!!!!!!!!! |
| 148 | blue + white chasing | !!!!!!!!!! |
| 152 | white + yellow chasing | !!!!!!!!!! |
| 156 | yellow + purple chasing | !!!!!!!!!! |
| 160 | yellow + cyan chasing | !!!!!!!!!! |
| 164 | blue + purple chasing | !!!!!!!!!! ⭐️ |
| 168 | red + cyan chasing | !!!!!!!!!! |
| 172 | blue + cyan chasing | !!!!!!!!!! ⭐️⭐️ |
| 176 | green + purple chasing | !!!!!!!!!! |
| 180 | blue + yellow chasing | !!!!!!!!!! |
| 184 | all color chasing (white between each color) | |
| 188 | rainbow chasing (white between each rainbow; rainbow = all colors except white) | ⭐️ |

**192-212 duplicate the 140+ block** (operator: "look the exact same as 140+"):
192 red+white, 196 green+white, 200 blue+white, 204 yellow+magenta,
208 red+white+green+white+blue+white, 212 all-color with white between.

**Color + dark chases:** 216 white + dark (dark = no color), 228 yellow + dark,
236 purple + dark.

**Special cycling effects:** 240 all-color cycling — starts red, a thin white
line travels across the beam; when it finishes traveling, color cycles to the
next. 244 all-color cycling — two white beams at both ends; when they collide,
the color changes; cycles slightly faster. 248 same with three beams; faster.

## CH9 (color speed — affects ALL the CH8 values above)

| CH9 | Behavior |
| --- | --- |
| 0-3 | color speed OFF |
| 4-127 | slow → fast, positive phase |
| 128-255 | slow → fast, REVERSE phase |

Reverse phase = the same chase running in the opposite direction — two
directions of travel are available for every effect.

## Immediate design consequences (executive notes)

- The July-4 config chase values are CONFIRMED against this map and land on
  the operator's favorites: 172 blue+cyan (⭐️⭐️), 164 blue+purple (⭐️),
  100 red+white divided (⭐️), 68 cyan+white (⭐️), 72 purple+white (!!).
- The same color pair exists at several DIVISION densities (red+white:
  52 → 100 → 116 → 140); operator marks rise with division. Density-by-context
  (bigger drop → more divided) is a candidate design input for F2/laser.
- 188 (rainbow with white separators, ⭐️) is the natural mapping for the
  AWR-147 rainbow track class (`effects.rainbow_family` currently null).
- New unstarred-but-highly-marked vocabulary for menu gaps: 160 yellow+cyan,
  120/144 green+white, 176 green+purple, 148 blue+white, 128 purple+yellow.
- CH9 reverse phase and the 240/244/248 traveler effects are unexploited
  design space (post-drop reversal, buildup traveler, etc.).

Related: `docs/architecture/laser_color_authority.md` (behavior contract),
`config/laser_color_map.json` (live menu state), AWR-147 rainbow class.
