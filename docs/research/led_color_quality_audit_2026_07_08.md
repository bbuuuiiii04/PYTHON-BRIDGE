---
doc_status: current
truth_level: code-verified
last_verified_commit: c866c8c
last_verified_date: 2026-07-08
validation_scope: read-only code audit plus offline pure-python render math over the live LED config (no runtime, bridge, network, or hardware action); every proposal is a veto-pending operator decision — nothing here is implemented
---

# AWR-152 — LED color/look quality audit: white leakage + hue smoothness (2026-07-08)

**What this is.** The read-only audit for the LED color/look quality pass lane
(kickstart: `docs/prompts/led_color_quality_pass_manager_kickstart_2026_07_08.md`).
It answers, mechanism by mechanism, why the operator's Govee cues read **too
white** and why **hues don't feel smooth** at runtime, then lays out a
veto-ready knob table, per-skeleton verdicts, and an assessment of the
"realtime twins for cloud drop looks" idea. Operator taste verdicts are design
inputs here, not up for debate (memory `project_led_look_color_quality_pass.md`):
buildups are SUPPOSED to be white; the complaint is white leaking into
everything else; keep BOTH cloud and RT looks per role.

**Rejection rule applied:** every claim below names its mechanism with
file:line, or it was cut. Claim labels: [confirmed] = verified against code at
`c866c8c` or computed from the live config this session; [assumed] /
[unknown] as marked.

**Evidence standard note.** The computed tables in Part 2 and the Appendix
come from a small offline pure-python script that imports the repo's own
`led_identity_v2.derive_dressing` and replays `universal_colorizer` math over
the live zone config values. No bridge process, no hardware, no full suite.

---

## 0. Context confirmed before anything else

- **The v2 identity engine is live-enabled** (`config/led_look_director.json:215`,
  `"v2": {"enabled": true}`). All engine color resolution routes through the v2
  paths (`led_color_engine.py:617-625`, `:737-745`); the v1 palette journey only
  runs during scripted stand-down (`led_color_engine.py:415-427`). [confirmed]
- The live config was modified 2026-07-08 09:05. Contents are coherent with the
  landed AWR-149/AWR-150 structures; **what specifically changed at 09:05 is
  [unknown]** (file is gitignored; no history exists). Flagged, not blocking.
- Landed platform context relied on: AWR-146 frame-engine child, AWR-149
  deterministic mixed-transport rotation, AWR-150 drop-impact guarantee
  (RT substitute on the beat + staged cloud takeover), AWR-151 ProcessType fix.

---

## Part 1 — Every path where white enters a cue color

### 1-A. Structural: pure white is baked into every palette both engines emit — [confirmed]

- **v2:** `derive_dressing` always appends `(255,255,255)` as slot 5 —
  `led_identity_v2.py:43` (`WHITE` constant) and `:198`
  (`slot_rgbs=base_slots + accent_slots + (WHITE,)`). Every zone, every track,
  no knob.
- **v1 (scripted stand-down only):** slot 5 forced pure white in all three slot
  fill strategies — `led_color_engine.py:805, 817, 835, 847` — plus the
  fixed-rgb/rainbow paths `:761, :767` and the v2 manual paths `:1174-1176, :1185`.
- **Which cues actually render slot 5** (slot motion maps only touch slots 0-4
  unless a cue explicitly writes slot 5):
  - `rt_drop_nebula` / `rt_post_drop_nebula`: **every other comet is pure
    white** and half the sparkle-intro pixels — `govee_frame_renderer.py:1292-1300`
    (post-drop comets), `:1386-1390` (drop sparkle intro), `:1398-1406`
    (drop comets).
  - `post_drop_firework_chase`: pure-white firework bursts on slot 5 every 4th
    beat — `govee_frame_renderer.py:1565-1586`.
  - `breakdown_star_twinkle`: `rng.randint(0, MAX_SLOTS - 1)` **includes slot 5**
    — `govee_frame_renderer.py:1728` — so ~1/6 of breakdown stars are pure
    white. Its sibling `rt_twinkle` deliberately stops at slot 4
    (`govee_frame_renderer.py:842`, `star_rng.randint(0, 4)`). I read the 0-5
    range as unintended (inconsistent with the "slot 5 reserved for white"
    operator decision comments at `:1636`, `:1682`).
- **Palate-reset inconsistency:** during a v2 palate reset the slot path dims
  slots 0-4 to `palate_reset_dim` (live 0.35) but re-appends **full-brightness
  pure white** as slot 5 — `led_color_engine.py:1185` — while the single-color
  path dims all six slots (`:1142`). Any slot-5 cue flashes full white inside
  the deliberately-dim reset window. [confirmed]

### 1-B. Exempt legacy RT skeletons with hardcoded white, in the live rotation — [confirmed]

The live `exempt_looks` list (`config/led_look_director.json:40-83`) removes
these looks from engine coloring entirely (`led_color_engine.py:630-631`,
`:750-751` early-return `{}`), so their baked renderer colors ship as-is. These
exempt looks sit in the **active default bank**:

| Look (bank line) | Baked white mechanism |
| --- | --- |
| `rt_groove_freestyle_nebula` (config:1365, groove) | `_groove_nebula` color2 = `(255,255,255)` — a pure-white comet head half the time (`govee_frame_renderer.py:388`) |
| `rt_drop_chase_freestyle_nebula` (config:1396, drop) | white sparkle-intro pixels + white comets (`govee_frame_renderer.py:592, 597-603`) |
| `rt_post_drop_freestyle_nebula` (config:1403, post_drop) | white comets from beat 0 (`govee_frame_renderer.py:495-502`) |
| `rt_drop_white_aggressive` (config:1397, drop) | **full-strip pure-white 16th-note strobe** (`govee_frame_renderer.py:505-512`) — an entirely white drop look |
| `rt_post_drop_white_shatter` (its drop pair, config:512-514) | full-white stroboscopic static (`govee_frame_renderer.py:515-529`) |

Also structural in the renderer: `_edm_color_for_look` returns cyan/white for
any unsuffixed name (`govee_frame_renderer.py:346-359`); every generic effect
defaults `color` to `(255,255,255)` (`:250, :258, :276, :289, :298, :318, :333,
:341`); a slot effect with no injected palette falls back to a single white
slot (`_DEFAULT_SLOT_COLORS`, `:1869`). These are fallback paths, not the live
hot path — but the design rule they encode is "missing color = white," never
"missing color = dark." [confirmed]

### 1-C. Cloud scene content — the engine cannot touch it — [confirmed]

`govee_scene_adapter.py` contains no color-param handling (verified by search);
cloud DIY looks dispatch a Govee `scene_ref` only. Engine-injected colors reach
only the realtime runner (`govee_realtime_runner.py:427`, `resolve_fade` over
`spec.params`). So white *content inside* cloud scenes is unreachable except by
bank membership or re-authoring the scene in Govee. White cloud scenes
currently in colored roles:

- `groove_diy_bright_white_chase` — groove bank (config:1362), tagged `white`
  (config:91).
- `drop_diy_1_red_white_chase` — drop bank (config:1386), tagged `red`.
- `drop_diy_3` — drop bank (config:1388), tagged `white` (config:101).

Buildup cloud whites are per the standing taste call and are not findings.

### 1-D. Selection skew: v2 makes cloud-scene filtering arbitrary and white-favoring — mechanism [confirmed], magnitude [assumed]

- `diy_eligible` filters cloud DIY looks by tag against the **v1** current
  palette (`led_color_engine.py:517-556`).
- Under v2, the v1 palette froze at whatever `_pick_palette` chose at engine
  init: `begin_dispatch` returns early into the v2 path (`led_color_engine.py:415-427`),
  so `_current_palette` never advances.
- The predicate stays wired in whenever the engine is enabled — v2 or not
  (`led_dispatch_policy.py:1666-1668`), and the director drops ineligible looks
  from the bank unless the filtered set is empty (`led_look_director.py:434-437`).
- Meanwhile `white`-tagged looks are **always eligible** via the M1 sentinel
  (`led_color_engine.py:537`).

Net effect: for an entire session, color-tagged cloud scenes can be silently
filtered out of their banks by a stale random palette, while white-tagged ones
always survive — the surviving cloud pool skews white. Magnitude depends on
which palette init happened to pick each launch ([assumed], varies per launch;
e.g. an init pick of `indigo` (blue-purple ± spread 0.1) excludes `cyan`- and
`red`-tagged looks all session).

### 1-E. Additive overlap wash — [confirmed by computation]

`universal_colorizer` sums slot contributions per pixel and clamps once
(`govee_frame_renderer.py:1047-1055`); `fold_additive` does the same for legacy
comets (`:1893-1900`). Two overlapping comets on adjacent slots in VOLT (live
zone values, key_hash=7, bass=0.5):

```
slot2 (197,0,255) hue 286°, sat 1.00  +  slot3 (0,223,255) hue 188°, sat 1.00
= (197,223,255) hue 213°, sat 0.23  ← washed near-white lavender
```

Single-hue-family zones wash far less (GLACIER slot2+slot3 = sat 0.65). So
overlap moments physically read as white-ish flashes in the split-family zones
(VOLT, ION, EMBERCORE). Overlaps occur whenever two spawns coexist (spawn
interval 1 beat, travel 2 beats — `_drop_chase_spawn_times`,
`govee_frame_renderer.py:532-547`).

### 1-F. The white knobs the operator could tune are dead — [confirmed]

- **v1 `palette.white`:** the mechanism exists (`_blend_white`,
  `led_color_engine.py:120-126`, applied at `:676, :686-688, :801, :815, :832,
  :844`) but **every live v1 palette sets `white: 0.0`**
  (config:120, 134, 143, 156, 165) *and* v1 is dormant under v2. Live
  contribution today: zero. The memory's `_blend_white` suspect is a real code
  path but not the culprit.
- **v2 zone `"white"` values** (live 0.03-0.08, config:262, 295, 328, 361, 394,
  427, 460): parsed into `ZoneRampConfig.white` (`led_config.py:1391`, model
  `led_models.py:79`) and **never read by any consumer** — verified by search
  across `led_color_engine.py`, `led_identity_v2.py`, `govee_frame_renderer.py`,
  `led_dispatch_policy.py`, `govee_scene_adapter.py`. Dead config.
- Ruled out as a white source: **v2 accent slots are not near-white** —
  `sat_floor` (lerp 0.55→0.85 on normalized bass ± depth variant, clipped
  0.40-0.95, `led_identity_v2.py:180`) re-saturates the pale ramp entries via
  `max(s, sat_floor)` (`:166`). Computed live slot sets show every slot at
  sat ≥ 0.65 except the hardcoded slot-5 white (Appendix A).

---

## Part 2 — Hue-smoothness diagnosis

### 2-1. Color is mapped to brightness, not position — the dominant mechanism [confirmed by computation]

Nearly every slot cue computes `slot_coord = intensity * 4.0`
(`govee_frame_renderer.py:1158` groove chase, `:1211/:1223` groove nebula,
`:1262` post-drop chase, `:1352` drop chase, `:1409` drop nebula,
`:1446-1448` drop center burst, `:1495` post-drop center comet). As a comet
head passes a pixel — or the anti-aliased edge dims, or a strobe gate chops
frames — that pixel's **hue** sweeps the palette, because dimmer = lower slot.
Computed on the live zone configs (Appendix B):

- **VOLT:** one comet body traverses hue **173° → 310°** (aqua → magenta).
- **EMBERCORE:** traverses **16° → 352° → 300°**, crossing the red/purple
  boundary inside one body.
- **GLACIER** stays tight (186°-203°) because base and accent share a family.

With the default `width 0.8` (≈1.6 px on the 60-segment strip,
config:551 `segments: 60`), that whole gradient lives inside ~2 pixels and
re-runs every beat — it reads as per-pixel hue noise, not a gradient. The
operator's own prototype cues map by **position within the comet body**
instead (`_slot_groove_center_chase` `relative_pos`,
`govee_frame_renderer.py:1104-1117`; `_slot_post_drop_firework_chase`
`:1540-1552`) — those are exactly the skeletons that look right.

### 2-2. Per-cycle random hue re-rolls — [confirmed]

`step_within_section` is `true` for groove and post_drop (config:21-28), so
each cycle re-seeds and re-rolls a random point on the ramp — v1:
`led_color_engine.py:665-672`; v2: `:1145-1150` (`p = uniform(0,1)` from a
per-(key_hash, section_id, step) seed). Each re-roll is an arbitrary jump on
the zone ramp, smoothed only by a 2-beat RGB fade
(`fade_beats_by_role.groove: 2.0`, config:33). Hue jumps mid-groove are by
construction, not drift.

### 2-3. All blending is RGB-space lerp — [confirmed; bounded impact]

`_p_to_rgb` (`led_color_engine.py:79-117`), `_ramp_at`
(`led_identity_v2.py:148-156`), `_v2_base_pick` (`led_color_engine.py:1373-1381`),
and the runner's fade `_lerp` (`govee_frame_renderer.py:65-71`) all interpolate
in RGB. Within one hue family this is fine — computed v2 base picks drift
smoothly (VOLT p=0→1: hue 322°→286°, sat 1.0 throughout, Appendix C). But any
blend across the base↔accent family boundary (slots 2↔3 in VOLT/ION/EMBERCORE)
passes through desaturated middles — the same math as the 1-E overlap wash.

### 2-4. Not guilty — [confirmed]

- The 16-step hue quantization (`HUE_SLOTS = 16`, `led_identity_v2.py:41`)
  against zone `hue_span ≤ 0.08` gives sub-visible per-track offsets.
- The v1 scale-stop piecewise lerp between adjacent cool-corridor stops keeps
  midpoints saturated (stop table `led_models.py:102-109`).
- Cycle-seeded hue picks only affect the `rainbow` manual mode
  (`led_color_engine.py:649, :1368-1370`).

---

## Part 3 — Veto-ready knob proposals

Each row names its mechanism; reject any row independently. "Visible change"
is the plain-English relay line for the operator.

| # | Knob (mechanism) | Current | Proposed | Expected visible change |
| --- | --- | --- | --- | --- |
| 1 | Default-bank membership of the 3 exempt freestyle nebulas (`config/led_look_director.json:1365, 1396, 1403`; white baked at `govee_frame_renderer.py:388, 592-603, 495-502`) | in groove/drop/post_drop rotation | remove from the `default` bank (keep the looks defined and in `legacy_color_suffix` for manual use) | the hardcoded cyan/white comets stop appearing in colored roles; the same motions stay in rotation via their engine-colored twins (`rt_groove_nebula`, `rt_drop_nebula`, `rt_post_drop_nebula`) already in the banks |
| 2 | `groove_diy_bright_white_chase` in the groove bank (`config:1362`; cloud content unreachable per 1-C) | groove | move to the buildup bank (white is the buildup language) or drop from banks | one less all-white groove scene; buildups unchanged in spirit |
| 3 | Slot-5 pure white → zone-tinted white (`led_identity_v2.py:198`; consumes the dead zone `white` knob from 1-F, or a new per-zone `slot5_rgb`) | `(255,255,255)` always, every zone | e.g. GLACIER ice-white `(200,235,255)`, EMBERCORE warm-white `(255,225,200)`, VOLT `(230,215,255)` | white accents (nebula comets, fireworks, stars) stop being clinical pure white and match each zone's temperature |
| 4 | Slot-cue color mapping (`intensity * 4.0` sites listed in 2-1) | color follows brightness — every comet sweeps the whole palette | per-spawn slot pick (each comet/burst = ONE palette color, rotating slots 0-4), or positional mapping like `groove_center_chase` | comets become single-colored and stable; the per-pixel rainbow churn disappears; overlap wash drops sharply. The single biggest smoothness fix |
| 5 | `step_within_section.groove` (`config:24`; re-roll mechanism 2-2) | `true` | `false` (drop is already `false`) | one hue per groove section instead of a random jump every 32-beat cycle; hue changes land on section boundaries |
| 6 | v2 DIY filtering (`led_dispatch_policy.py:1666-1668` + frozen v1 palette, mechanism 1-D) | stale frozen v1 palette filters cloud scenes; white-tagged always pass | under v2, pass `None` (no tag filtering) or map zones→allowed tags | cloud scene variety returns to even rotation; the white-favoring skew ends |
| 7 | Palate-reset slot path (`led_color_engine.py:1185` vs `:1142`) | slot 5 stays full white while slots 0-4 dim to 0.35 | dim slot 5 by the same factor | no full-brightness white flashes during the deliberately-dim track-change reset |
| 8 | `breakdown_star_twinkle` slot range (`govee_frame_renderer.py:1728`) | `randint(0, 5)` — includes pure-white slot | `randint(0, 4)` (match `rt_twinkle`, `:842`) | no random pure-white stars in breakdown ambience |
| 9 | Comet head width on the 60-segment strip (`width 0.8` defaults, `govee_frame_renderer.py:1144, 1198, 1251, 1287, 1341, 1393`) | ~1.6 px heads | 2.5-3.0 | visible comet bodies instead of blinking single-pixel dots — a direct "skeletons look bad" fix |
| 10 | Dead-knob hygiene (1-F) | `palette.white` all 0.0 + zone `white` parsed-but-unconsumed | either row 3 consumes zone `white`, or delete both from the live config | no functional change; stops future sessions chasing knobs that do nothing (this audit did) |

**Deliberately not a row:** `rt_drop_white_aggressive` +
`rt_post_drop_white_shatter` (`config:1397, 1160-1170`; renderer
`govee_frame_renderer.py:505-529`). That pair is the only all-white drop moment
in the bank — a pure taste veto: keep if the operator wants one white drop per
rotation; cut both from `default` if "no white drops, period." Note the AWR-150
interaction: while they stay in the bank, they are also candidates for the
on-beat substitute in front of ANY committed cloud drop scene (see Part 5).

---

## Part 4 — RT skeleton verdicts (keep / change / cut from the default bank)

| Verdict | Skeletons | Why |
| --- | --- | --- |
| **Keep as-is** | `rt_twinkle`, `rt_groove_center_chase`, `rt_groove_center_burst_retract`, `rt_post_drop_firework_chase`, `rt_breakdown_full_breathing`, `rt_breakdown_star_twinkle_sand`, all six `rt_buildup_*` | positional color mapping (2-1) or single-family motion; buildup whites are by design; the sand twinkle's warm palette is a deliberate operator bake (`govee_frame_renderer.py:1746-1789`) |
| **Change** (knob #4 + #9 mechanics; motion is fine) | `rt_groove_chase`, `rt_groove_nebula`, `rt_drop_chase`, `rt_drop_nebula`, `rt_post_drop_chase`, `rt_post_drop_nebula`, `rt_post_drop_center_comet` | intensity→slot churn + 1.6 px heads |
| **Change** (additional per-cue defect) | `rt_drop_center_burst` — lights only even pixels (`govee_frame_renderer.py:1438-1439`), gappy on a 60-segment strip; `rt_breakdown_star_twinkle` — knob #8 white stars | |
| **Cut from default bank** | `rt_groove_freestyle_nebula`, `rt_drop_chase_freestyle_nebula`, `rt_post_drop_freestyle_nebula` (knob #1) | exempt, baked cyan/white, duplicate motions of their engine twins |
| **Operator veto** | `rt_drop_white_aggressive` + `rt_post_drop_white_shatter` | the white-drop taste call above |

One taste flag, no verdict: the drop/post-drop 16th-note strobe gates
(`int(beat * 16.0) % 2`, e.g. `govee_frame_renderer.py:460, 481, 1247, 1283,
1324, 1373, 1474`) run ~17 Hz at 128 BPM. If "looks bad" includes the flicker
feel, the gate subdivision is the knob; left alone otherwise.

---

## Part 5 — "Realtime twins for cloud drop looks" verdict

**Feasible, cheap, but sequence it after knobs 1-4.** [confirmed mechanism]

- The plumbing already exists: `substitute_realtime_drop` picks from the drop
  bank's `realtime_razer` subset via the (drop, realtime_razer) shuffle bag
  (`led_look_director.py:317-376`), advancing only the backend cursor.
- Today that subset includes the two all-white looks, so a red cloud drop can
  get a pure-white strobe stand-in — the aesthetic mismatch the twins idea
  targets is real.
- The cheap version is a config hint, not new renders: an optional `rt_twin`
  field per cloud drop look (checked first in `substitute_realtime_drop`,
  falling back to the current bag). Cost: one config key + ~15 lines + tests.
- Recommendation: land the white/hue knobs first — zone-colored engine drops
  may already make substitutes read consistent, and per-scene twin curation is
  exactly the decision load the operator should not carry unless the mismatch
  survives the fixes.

---

## Part 6 — Boundaries, unknowns, next step

- Read-only throughout: no code, config, bridge, or hardware touched during
  the audit; no heavy compute (one small offline render-math script).
- Deliverable 4 of the kickstart (Template Lab iteration plan for the
  skeletons the operator dislikes) is **deliberately not written** — it is
  gated on the operator's vetoes coming back through the executive.
- Open unknowns: what changed in the live config at 09:05 on 2026-07-08 (no
  history exists); the real-world magnitude of the 1-D selection skew (depends
  on the palette each launch froze).
- Status: analysis only; changes no runtime behavior; not
  implementation-authorizing. Implementation, when released, routes per repo
  rules (Codex implements bridge code; contract-first).

---

## Appendix A — Computed v2 slot colors per zone (live config, key_hash=7, bass=0.5, drama=0.5, punch=0)

sat_floor = 0.65, span = 0.57 for all rows below. Format: RGB (hue°, sat, val).

| Zone | slot0 | slot1 | slot2 | slot3 | slot4 | slot5 |
| --- | --- | --- | --- | --- | --- | --- |
| GLACIER | (2,110,235) 212° 0.99 | (0,165,255) 201° 1.0 | (0,223,255) 188° 1.0 | (89,238,255) 186° 0.65 | (89,238,255) 186° 0.65 | (255,255,255) PURE WHITE |
| DEEP_POOL | (1,38,128) 223° 0.99 | (0,63,140) 213° 1.0 | (0,92,140) 201° 1.0 | (38,0,160) 254° 1.0 | (0,62,200) 221° 1.0 | (255,255,255) PURE WHITE |
| TWILIGHT | (79,0,166) 269° 1.0 | (108,0,197) 273° 1.0 | (136,0,220) 277° 1.0 | (176,0,220) 288° 1.0 | (230,0,184) 312° 1.0 | (255,255,255) PURE WHITE |
| ION | (0,166,255) 201° 1.0 | (26,215,240) 187° 0.89 | (60,255,217) 168° 0.76 | (143,255,60) 94° 0.76 | (186,255,89) 85° 0.65 | (255,255,255) PURE WHITE |
| VOLT | (244,0,156) 322° 1.0 | (232,0,202) 308° 1.0 | (197,0,255) 286° 1.0 | (0,223,255) 188° 1.0 | (89,255,235) 173° 0.65 | (255,255,255) PURE WHITE |
| EMBERCORE | (188,0,29) 351° 1.0 | (166,0,70) 335° 1.0 | (119,0,120) 300° 1.0 | (255,30,32) 359° 0.88 | (255,132,89) 16° 0.65 | (255,255,255) PURE WHITE |
| NEUTRAL | (0,150,226) 200° 1.0 | (0,188,241) 193° 1.0 | (0,222,255) 188° 1.0 | (0,255,253) 180° 1.0 | (89,206,255) 198° 0.65 | (255,255,255) PURE WHITE |

Every non-white slot has sat ≥ 0.65 — the palettes themselves are saturated;
the only white the engine injects is the hardcoded slot 5.

## Appendix B — Comet-body hue sweep under `slot_coord = intensity * 4.0`

Pixel color as one comet head passes (intensity 1.0 → 0.1), colorizer blend of
adjacent slots, live zone values:

| intensity | GLACIER | VOLT | EMBERCORE |
| --- | --- | --- | --- |
| 1.0 | (89,238,255) 186° | (89,255,235) 173° | (255,132,89) 16° |
| 0.8 | (71,190,204) 186° | (14,184,201) 185° | (204,40,35) 2° |
| 0.6 | (21,137,153) 187° | (71,54,153) 250° | (104,7,51) 333° |
| 0.5 | (0,112,128) 188° | (98,0,128) 286° | (60,0,60) 300° |
| 0.3 | (0,53,76) 198° | (68,0,64) 304° | (47,0,24) 329° |
| 0.1 | (0,13,24) 207° | (24,0,17) 318° | (18,0,5) 343° |

Hue range traversed by ONE comet body: GLACIER 186-203° (tight);
VOLT 173-310° (over a third of the wheel); EMBERCORE crosses 352°→2°→300°.

## Appendix C — v2 single-color path is smooth within a zone

`_v2_base_pick` (RGB lerp slots 0→1→2), VOLT: p = 0/0.25/0.5/0.75/1.0 → hue
322°/315°/308°/296°/286°, sat 1.0 throughout. The single-color engine path is
not a smoothness offender; the slot-cue mapping (2-1) and the re-rolls (2-2)
are.
