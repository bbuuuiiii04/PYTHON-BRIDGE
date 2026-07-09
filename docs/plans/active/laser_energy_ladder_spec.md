---
doc_status: current
truth_level: code-verified
last_verified_date: 2026-07-09
last_verified_commit: HEAD-2026-07-09-overnight
validation_scope: implementation spec authored from the executive relay of the operator's A-D verdicts (retiring-seat transcript, session 0d30b46f ~lines 1781/1848 — no repo source doc exists; this spec + docs/research/laser_ch8_ch9_operator_map_2026_07_08.md are the citable record); implementation RIDES THE F2 ROUND (consumes F2's per-drop tier output); awaiting executive review, nothing implemented
---

# Codex Implementation Spec - Laser Energy Ladder (AWR-162; implements with F2)

Operator-approved (relayed verbatim by the executive, 2026-07-09): (A)
energy-gated laser activation APPROVED; (B) density-rides-the-tier APPROVED;
(C) impact burn-down APPROVED PENDING HIS LIVE LOOK — ships flagged/
live-gated; (D) one-darkness APPROVED plus the operator's addition (4-beat
pre-chorus laser blackout). The optional "pre-drop tease" received NO verdict
and is OUT OF SCOPE (parked by the executive as a morning item — do not
implement, do not mention in config).

## Part A - Context (verified at HEAD)

1. **What (A) replaces:** today the planner ranks drops by personality and
   the top `ceil(laser_ratio * N)` render `leds_plus_lasers`
   (`drop_presentation.py:263`, `laser_ratio` default 0.4 `:89`). This is a
   proportion, not an energy judgment. The ladder replaces it with the real
   tier classification from the operator's 41 desk verdicts (the AWR-147
   calibration ladder), delivered by F2.
2. **Tier interface (F2 dependency):** F2 computes a per-drop ENERGY TIER
   {small, standard, intense, monster} from the calibrated v4 spectral
   features at plan time. This spec consumes that tier on the planner's
   per-drop decision; it does not compute tiers itself. Tracks WITHOUT tier
   data (no v4 cache) fall back to today's `laser_ratio` rule unchanged,
   with one log line naming the fallback.
3. **Once-per-drop invariant [restated per executive review]:** the
   presentation decision is made once PER DROP at its impact, and NO
   re-decision ever happens WITHOUT a new drop impact — but a NEW drop's
   impact DOES re-decide for THAT drop mid-window (AWR-138 impact
   re-entry: `impact_now` + pending presentation → `_enter_window` with the
   new presentation, `drop_presentation.py` ~`:703`). Consequences for (A):
   an LEDs-only verdict can never be re-admitted to lasers without a new
   drop impact; and when a new drop re-enters the window, its OWN tier
   decides — a small-tier next drop must land LEDS_ONLY on re-entry too.
   Preserve both sides.
4. **Chase-class ground truth:**
   `docs/research/laser_ch8_ch9_operator_map_2026_07_08.md` — the red+white
   family escalates by DIVISION: 52 → 100 (⭐, "chunky starred") → 116 →
   140 ("finest shimmer"); 192-212 duplicate 140+. Division escalation is the
   operator's aggression axis; colors stay the zone's.
5. Contracts: `drop_presentation`, `laser_color`, `config_schema`.

## Part B - Tasks (sequenced INTO the F2 implementation round)

### Absolute Rules
- Manual solo (AWR-159 semantics), hotcue/learned/finale/gear-shift tiers,
  and every existing override OUTRANK the energy gate exactly as they
  outrank the ratio rule today. Emergency/blackout paths untouched.
- No behavior change for tier-less tracks (legacy ratio fallback).
- CH3/CH4 never touched; CH9-only for (C); all new values config-side and
  operator-tunable (the supervised eyeball / haze session tunes them).

### Task 1 - (A) Energy-gated activation (`drop_presentation.py`)
Planner: when per-drop tiers are available, decision per drop =
`LEDS_ONLY` for tier `small` (lasers do not fire at all), `LEDS_PLUS_LASERS`
for `standard`/`intense`/`monster` — replacing the personality-ranked
`ceil(laser_ratio * N)` selection for tiered tracks. Finale guarantee,
hotcue/learned matches, and manual arms keep their existing precedence.
`laser_ratio` stays as the documented tier-less fallback only.

### Task 2 - (B) Density rides the tier (`laser_color_engine.py` + `config/laser_color_map.json`)
Menus gain optional per-tier chase divisions: each menu chase entry may
carry `"tiers": {"standard": <ch8>, "intense": <ch8>, "monster": <ch8>}`
alongside its base `"chase"`. At a drop, the engine picks the mood's chase
COLOR PAIR as today and swaps CH8 to the tier's division class when the
entry provides one (absent tiers → today's single chase value; unknown tier
→ standard). Seed the config with the documented red+white ladder
(100/116/140) on the menus whose chase is the 100-class; other pairs stay
single-value until the operator supplies their division variants (config
edit, no code).

### Task 3 - (C) Impact burn-down, FLAGGED (`laser_color_engine.py` + config)
New config block `impact_burndown: {"enabled": false, "ease_beats": 8}` —
SHIPS DISABLED (live-gated for the haze session). When enabled: at the drop
hit, CH9 starts at the tier's maximum and eases linearly down across the
drop window; the existing `settle.ease_beats` post-drop settle then finishes
the landing. Pure CH9 speed; no CH8/phase changes.

### Task 4 - (D) One darkness + pre-chorus blackout (`state_manager.py` laser mask wiring)
1. When an F2 emphasis blackout fires (quantized 1/2/4/8/16 beats), the
   lasers go dark for exactly the same beats via the existing pack-mask
   blackout writer — the whole room breathes together.
2. OPERATOR ADDITION: lasers black out for the 4 beats BEFORE every chorus
   phrase start (phrase boundaries remain in the phrasing data — only drop
   DECISIONS were merged by the marker collapse). Seam, named honestly: a
   quantized 4-beat lookahead against `phrase_roles` boundaries — an
   interface OWNED AND DELIVERED BY F2 (the same countdown pattern as the
   existing LED pre-dark, which counts down to known impact beats, but with
   a NEW data source: nothing at HEAD looks ahead to phrase starts today).
   Same mask writer, releases at the chorus start beat.

### Task 5 - Tests
Planner tier gating (small→LEDS_ONLY, others→both; tier-less→legacy ratio
byte-identical; finale/hotcue/manual precedence pinned); once-per-drop
invariant regression pinning BOTH sides: (a) an LEDs-only window is never
re-admitted to lasers WITHOUT a new drop impact, and (b) an AWR-138 impact
re-entry re-decides on the NEW drop's tier — a small-tier next drop lands
LEDS_ONLY on re-entry (a test asserting "never re-decides mid-window"
literally would either fail against AWR-138 or freeze re-entry off — do
not write that test); tier
chase selection (per-tier CH8, absent-tiers fallback, unknown-tier→standard);
burn-down disabled-by-default + enabled CH9 ramp shape; mask timing for
emphasis-sync and 4-beat pre-chorus windows (pure window-machine seams).

### Task 6 - Contract docs
All three contracts' docs_update lists; AWR-162 registry row; the authority
docs (`drop_presentation_authority.md`, `laser_color_authority.md`) gain the
ladder behavior + the flag state of (C); suite + three hard checks.

## Part C - Invariants
- Manual solo and all existing tier/override precedence unchanged.
- Once-per-drop decide-at-impact / release-only window semantics unchanged.
- Tier-less tracks byte-identical to today.
- (C) ships OFF; enabling it is a config act at the haze session.
- Strobe/safety ceilings and CH3/CH4 untouched.

## Part E - Acceptance
- [ ] Implemented WITH the F2 round (tier interface live), one commit per
  task, explicit paths; suite at baseline; hard checks green.
- [ ] Operator summary: small drops keep the lasers silent on purpose;
  bigger drops bring them in with the chase getting more divided as the
  drop gets bigger (his 100→116→140 ladder); the burn-down effect exists
  but stays OFF until the haze session; every emphasis blackout and the 4
  beats before each chorus now darken lasers and LEDs together.
- [ ] Print exactly AWR162-DONE with real suite numbers, or AWR162-BLOCKED.
