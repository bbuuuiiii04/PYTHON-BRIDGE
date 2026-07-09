---
doc_status: current
truth_level: code-verified
last_verified_commit: b0bbcb3
last_verified_date: 2026-07-08
validation_scope: implementation spec only — nothing here is implemented; every file:line and every operator-dialed value re-verified this session (params fetched live from the pad drafts.json, code sites re-read at HEAD after the AWR-152/154/155 rounds); implementation gates on executive review
---

# Codex Implementation Spec - LED round 2: strobe-gate rebuild + accepted-look promotion (AWR-156)

Round 2 over the LOCKED verdict trail from the 2026-07-08 pad sessions
(AWR-152 lane). Spec-authoring only; **implementation gates on executive
review**. Scope is items (a)-(g) below, exactly. NOT in scope (verdicts
pending, do not touch): `drop_firework_explosion_2`, `rainbow_drop` /
`rainbow_post_drop`, `comet_rainbow_ordered` promotion, and any re-check of
the remnants spawn-feel change.

## Part A - Context & Root Cause (verified; read, do not implement)

**Standing promotion rules (operator-ruled 2026-07-08, binding — record them,
build to them):**

1. **Strobes are TIME-BASED (real Hz + duty), never beat/BPM-subdivided** — a
   strobe must feel identical at 140 and 160 BPM. Ruled mid-pad-session,
   lab-verified (equal flashes/sec at 128 and 90 BPM).
2. **Sparkles are TIME-BASED, never beat-tied** — continuous spawning with
   independent per-sparkle lifecycles; synchronized whole-field re-rolls are
   the diagnosed flicker mechanism (~17 Hz hard pops).

**Why the current strobe gate is broken** (AWR-153 diagnosis,
`docs/research/led_white_strobe_gate_diagnosis_2026_07_08.md`, all
[confirmed]): `_drop_white_aggressive` gates on
`(beat % 0.25) < 0.0625` (`govee_frame_renderer.py:511`) — a stateless ~29 ms
beat-domain window designed for 40 fps. The runner renders one frame per tick
and holds the last frame through any stall with no catch-up
(`govee_realtime_runner.py:251-265` loop; razer frames replace strip state,
nothing decays). Sampling model: at a jittery 60 fps ~31% of strobe cycles
show NO flash and a stall on an ON frame holds full white ~147 ms — the
ProcessType fix alone does not make this gate robust.

**Why the comet colors churn** (AWR-152 audit, knob #4, operator verdict
locked): the slot cues map color to brightness — `slot_coord = intensity *
4.0` at `govee_frame_renderer.py:1158` (groove chase), `:1211` (groove
nebula), `:1262` (post-drop chase), `:1303` (post-drop nebula palette
comets), `:1352` (drop chase), `:1409` (drop nebula palette comets), `:1495`
(post-drop center comet); `_slot_drop_center_burst` uses the same idiom with
a main/accent split (`:1446-1448`). One comet body sweeps 137° of hue in
VOLT. Verdict: **the intensity-hue mashup dies; per-spawn single color wins**
("a multicolor cycling comet effect, which is cool").

**Heartbeat stutter mechanism** (measured): un-normalized sub-pixel falloff
made a moving head's peak brightness dip to 0.53× between pixels; fix =
peak-normalized head weights (production `_comet_frame` normalizes for the
same reason, `govee_frame_renderer.py:146-158`).

**Injection plumbing** [confirmed at HEAD]: engine colors reach realtime
renders as runtime-injected params — `_led_inject_engine_colors`
(`led_dispatch_policy.py:917-997`) merges `color`/`slot_colors` into decision
params; the runner re-resolves per frame via `resolve_fade`
(`govee_realtime_runner.py:427`) and renders at `:447-454` with
`beat_pos=ir.local_beat, local_t=ir.local_t` (local_t = seconds since cue
start). Runtime-injected keys are NOT static config keys, so the C5 param
allowlist does not apply to them; every STATIC config param on a look MUST be
allowlisted in `REALTIME_EFFECT_PARAM_KEYS` (`govee_frame_renderer.py:972`,
`_SYNC_PARAM_KEYS :987`) or the look disables ALL LED.

**Operator-dialed values** (fetched live from the pad `drafts.json` this
session — these are THE accepted numbers; do not substitute defaults):

| Draft (status) | Accepted values |
| --- | --- |
| `strobe_subdiv` (accepted) | hz 6.0, duty 0.3 — THE reference feel |
| `strobe_blue`/`_cyan`/`_green`/`_red` (accepted) | their pure colorway, hz 6.0, duty 0.3 |
| `strobe_red_white` (accepted) | hz 5.5, duty 0.25; side A red; **side B was dialed to red — RESTORE side B to white (255,255,255), the executive's standing default. FLAG: one-line operator veto restores his red dial.** |
| `strobe_blue_cyan` (accepted) | hz 5.0, duty 0.25; A (0,0,255), B (0,135,255) — his dialed azure B, keep |
| `strobe_cyan_white` (accepted) | hz 5.0, duty 0.25; A (0,255,255), B (100,105,255) — his dialed periwinkle B, keep (flag visibly in the look comment; name says white, dial says periwinkle) |
| `buildup_balloon_comet` (accepted) | start_width 6, end_width 0.8, build_beats 32, dim_floor 0.05, loop_beats 4, color white |
| `groove_heartbeat_chase` (accepted) | base_width 1.5, pulse_width 3.0, decay 0.3, loop_beats 4.0, color_mode 2 |
| `post_drop_firework_remnants` (accepted) | dim_beats 8, ember_hold_beats 8, ember_decay_beats 2, sparkle_density 0.35, sparkle_size 1.0, sparkle_life_s 0.8 |

Lab reference implementations live in the gitignored
`config/led_lab/effects_lab.py` (`_head_weights` peak-norm, `_ember_field`
time-based sparkles, `groove_heartbeat_chase` color modes,
`buildup_balloon_comet`, `post_drop_firework_remnants`, `strobe_colorway`/
`_hz_gate`). Port their logic; do NOT import from `config/led_lab/` (never a
runtime dependency, never committed).

[assumed, verify while implementing]: `ir.local_t` advances on wall-clock
seconds through pauses/seeks exactly as the beat-sync engine defines cue
time; if local_t can jump backward on wrap/retrigger, the Hz gate simply
re-phases (stateless in local_t) — acceptable, note it in the report.

## Part B - Tasks (implement exactly, in order; one commit per task)

### Absolute Rules

- Out of scope: `drop_firework_explosion_2` and both rainbow drafts (verdicts
  pending); `exempt_looks` and the freestyle nebulas' bank membership (veto
  #1 stands); `step_within_section` (knob #5 is a locked NO-OP — `groove`
  stays `true`, do not touch); v1 engine paths; `config/led_look_director.json`
  (LIVE, gitignored, read-only — mirror is operator-gated);
  `config/led_lab/**`; laser/SoundSwitch/Rekordbox subsystems; the running
  bridge and pad processes.
- Behavior that must not change: blackout/emergency semantics (incl. AWR-154
  reasons + AWR-155 fail-open), AWR-150 substitute + staged takeover, AWR-149
  plan rotation mechanics, the 6-slot invariant, `slot5_white` zone tints,
  buildup cues (white by design), the positional-mapping prototypes
  (`_slot_groove_center_chase`, `_slot_post_drop_firework_chase` — ordered
  gradients, operator-liked, NOT mashup sites).
- Error handling: config validation fails closed in the existing errors-list
  pattern; renderer effects fail dark on malformed params (existing `_color`/
  `_slots` idioms); no broad try/except; the runner gains NO blocking I/O.

### Task 1 - `govee_realtime_runner.py`: inject real frame timing

In `_compose_frame` (`:422-455`), after `params = resolve_fade(...)` (`:427`),
inject the runner's measured frame period:
`params = {**params, "frame_period_s": self._frame_period_ema}`.
Maintain `self._frame_period_ema` on the runner thread in `_loop`/`_tick_once`
as an exponential moving average (alpha ≈ 0.2) of actual inter-tick gaps
(`self._time_fn()` deltas), initialized to `1.0 / self._fps`. Runtime-injected
key — deliberately NOT added to any static allowlist (the `slot_colors`
pattern). No other runner behavior changes.

### Task 2 - `govee_frame_renderer.py`: Hz-based frame-timing-aware strobe gate

Add one module-level helper (near `_edm_beat`):

```python
def _hz_strobe_on(local_t: float, params: Mapping[str, Any]) -> bool:
    """Time-based strobe gate (AWR-153 binding ruling): hz + duty in the
    seconds domain, BPM-free. Frame-timing-aware: the ON window is widened
    to at least ~1.6 rendered frames so every cycle lands at least one ON
    frame at any achievable fps (the 40fps-designed beat gate missed ~31%
    of cycles under jitter)."""
    hz = max(0.5, min(10.0, float(params.get("hz", 6.0))))
    duty = max(0.05, min(0.5, float(params.get("duty", 0.3))))
    frame_period = max(1e-4, float(params.get("frame_period_s", 1.0 / 40.0)))
    cycle_s = 1.0 / hz
    on_s = max(duty * cycle_s, min(cycle_s * 0.9, 1.6 * frame_period))
    return (max(0.0, float(local_t)) % cycle_s) < on_s
```

Rebuild `_drop_white_aggressive` (`:505-512`) on it: full-strip pure white
when `_hz_strobe_on(local_t, params)` else dark; defaults hz 6.0 / duty 0.3
(the accepted reference feel). Delete the beat-domain comment block. Add
`hz`, `duty` to its `REALTIME_EFFECT_PARAM_KEYS` entry.

### Task 3 - `govee_frame_renderer.py`: the colorway strobe family

One new frame effect `drop_strobe_colorway(beat, local_t, frame_index,
params, segments, seed)`: when `_hz_strobe_on` is ON, full strip in
`color_a`, or alternating `color_a`/`color_b` per flash
(`flash_idx = int(local_t * hz)`, even→A odd→B) when `color_b` is present;
dark otherwise. Colors via the existing `_color` validator; missing
`color_a` defaults white. Register in `_EFFECTS`, add to
`REALTIME_STROBE_EFFECTS`, allowlist
`{"color_a", "color_b", "hz", "duty", "duration_beats"} | _SYNC_PARAM_KEYS`.
Port from the lab `strobe_colorway`, replacing the lab gate with
`_hz_strobe_on`.

### Task 4 - `govee_frame_renderer.py`: promote the three accepted looks

1. `buildup_balloon_comet` — frame effect, port from the lab: dual-head
   4-beat-loop chase whose head width lerps `start_width→end_width` over
   `build_beats` with brightness falling to `dim_floor`; heads use the
   peak-normalized weight helper (below). Params allowlist:
   `{"start_width", "end_width", "build_beats", "dim_floor", "loop_beats",
   "color", "duration_beats"} | _SYNC_PARAM_KEYS`; default color pure white
   (buildup language). Not a strobe.
2. `rt_groove_heartbeat` — SLOT effect (engine-palette-fed): dual-head chase,
   width = `base_width + pulse_width * exp(-(beat % 1.0) / decay)`; heads use
   peak-normalized weights written into palette slots by `color_mode`
   (static config param, int 0-3): 0 = both heads slot 1; 1 = each head's
   weight split between slots 1 and 3 by its strip position
   (`t = pos/segments`, slot1 weight `1-t`, slot3 weight `t`); 2 = head 1 →
   slot 1, head 2 → slot 3 (default, matches his accepted red+white combo
   feel — the engine palette supplies the actual colors); 3 = within each
   head, weight splits core→edge between slot 1 (core) and slot 3 (edge).
   Slots 0-4 only; slot 5 stays white-reserved. Register in `SLOT_EFFECTS`;
   allowlist `{"base_width", "pulse_width", "decay", "loop_beats",
   "color_mode", "duration_beats"} | _SYNC_PARAM_KEYS`. Not a strobe.
3. `rt_post_drop_firework_remnants` — SLOT effect: background = slot 5 (the
   zone-tinted white) dimming `1.0→0` over `dim_beats`; embers = time-based
   field (port `_ember_field`: per-ember independent cycles seeded
   `(seed, "ember", k)` / `(seed, "ember", k, cycle_idx)`, sine envelopes,
   positions re-rolled per cycle, `life_s` seconds domain), each ember
   writing its weight into a per-cycle-chosen slot 0-4; ember level full
   until `ember_hold_beats` then linear to 0 over `ember_decay_beats`
   (accepted 8+2 — done by beat 10). Register in `SLOT_EFFECTS`; allowlist
   `{"dim_beats", "ember_hold_beats", "ember_decay_beats", "sparkle_density",
   "sparkle_size", "sparkle_life_s", "duration_beats"} | _SYNC_PARAM_KEYS`.
   Not a strobe (embers fade on sine envelopes).

Shared helper for 1-2 (module-level): peak-normalized anti-aliased head
weights — triangle falloff `max(0, 1 - dist/width)` per pixel, all weights
divided by the head's max weight so the brightest pixel always carries the
full head level (kills the measured 0.53× between-pixel dip).

### Task 5 - `govee_frame_renderer.py`: knob #4 — the mashup dies

At each of the eight sites (`:1158, :1211, :1262, :1303, :1352, :1409,
:1495`, and `_slot_drop_center_burst :1446-1448`): replace the
intensity-derived `slot_coord` with a whole-spawn slot choice; intensity
becomes brightness only (write `field[idx][slot] += intensity`, clamped).

- Chases/nebulas/center-comet (spawn-indexed sites): palette spawns take
  `slot = spawn_idx % 5` where a spawn index exists (`_drop_chase_spawn_times`
  sites); the two heads of the groove chase/nebula take slots
  `(cycle % 5)` and `((cycle + 2) % 5)` with `cycle = int(cue_beat /
  loop_beats)` (the accepted lab mapping). Nebula WHITE comets keep slot 5
  exactly as today.
- `_slot_drop_center_burst`: main bursts rotate slots 0-2
  (`burst_idx % 3`), accent bursts rotate slots 2-4 (`2 + burst_idx % 3`) —
  the main/accent split survives, the intra-burst hue sweep dies.
- The sparkle-intro pixels in `_slot_drop_chase :1333` / `_slot_drop_nebula
  :1387` already pick one random slot per pixel — unchanged.

### Task 6 - `config/led_look_director.example.json`: looks, widths, banks

1. **Colorway looks** (7): `rt_drop_strobe_blue`, `_cyan`, `_green`, `_red`,
   `_red_white`, `_blue_cyan`, `_cyan_white` — action realtime, backend
   realtime_razer, scene_ref `drop_strobe_colorway`, safety_class `drop`,
   `allow_strobe: true`, fallback `rt_blackout`, `color_source` engine-exempt
   NOT applicable: these are fixed colorways — set `"color_source": "baked"`
   so the engine never recolors them; params carry the pinned accepted
   values from Part A's table (with `strobe_red_white` side B = white per the
   standing default — FLAGGED for one-line operator veto). Add all 7 to
   `banks.default.drop`. Rebuild note: `rt_drop_white_aggressive` keeps its
   look entry; its renderer now runs the Hz gate with hz 6.0/duty 0.3
   defaults.
2. **Promoted looks**: `rt_buildup_balloon_comet` (buildup bank; params =
   his dialed values from Part A; `"color_source": "baked"`, white),
   `rt_groove_heartbeat` (groove bank; `color_source` engine; params
   base_width 1.5, pulse_width 3.0, decay 0.3, loop_beats 4.0,
   color_mode 2), `rt_post_drop_firework_remnants` (post_drop bank;
   `color_source` engine; params = accepted 8+2 row from Part A).
3. **Knob #9 widths** (role-scoped): add `"width": 4` to the params of
   `rt_drop_chase`, `rt_drop_nebula`, `rt_post_drop_chase`,
   `rt_post_drop_nebula`, `rt_post_drop_center_comet`; add `"width": 2.5` to
   `rt_groove_chase` and `rt_groove_nebula`. **FLAG: the groove 2.5 default
   is veto-able (his comet_width dial never reported a final number); drop/
   post_drop 4 is his stated request.**
4. **Bank recast (f)** — AMENDED by operator 2026-07-08 late (rename, not
   just move): the demoted looks are RENAMED so their names read as
   post-drop remnant/sparkle material — implementer picks the names (e.g.
   `rt_post_drop_remnant_chase` / `rt_post_drop_remnant_nebula`; MUST NOT
   collide with the existing `rt_post_drop_chase` / `rt_post_drop_nebula`).
   The rename is a LOOK-name rename only — each look's renderer `scene_ref`
   stays exactly what it is. Propagate the new names everywhere the look
   name appears: look definitions, bank lists, tests, and any remaining
   references (the drop_pairs entries are deleted by this same task). The
   operator summary must note that the config mirror carries the rename so
   his live-config equivalents map cleanly. Then: move the renamed looks
   from `banks.default.drop` into `banks.default.post_drop` (operator
   verbatim: "Current sparkling cues can play the role of the sparkling
   remnants");
   delete their `drop_pairs` entries (`rt_drop_chase` → `rt_post_drop_chase`,
   `rt_drop_nebula` → `rt_post_drop_nebula`) — a post_drop-role look never
   fires a pair, and the AWR-149 drop→post_drop pairing will carry
   explosion→remnants arcs once the explosion round lands (NOT this round).
   Their paired post_drops already sit in the post_drop bank; no other pair
   changes.
5. **Knob #5 NO-OP**: `step_within_section.groove` remains `true` — assert
   in the diff review that this key is untouched.

### Task 7 - Tests (`tests/test_govee_frame_renderer.py`,
`tests/test_govee_realtime_runner.py`, `tests/test_led_config.py`)

Pure seams, no disk/subprocess:

1. Hz gate: BPM-invariance (equal ON-fraction and flashes/sec for the same
   local_t series regardless of any beat inputs); frame-aware widening (at
   frame_period 1/28 s and hz 6/duty 0.3 the ON window ≥ 1.6 frames → a
   synthetic 28 fps frame-time sweep lands ≥1 ON frame in EVERY cycle);
   caps (hz ≤ 10, duty ≤ 0.5).
2. Runner injection: `frame_period_s` present in params reaching the
   renderer; EMA sane after simulated slow ticks (fake `time_fn`/`sleep_fn`
   seams already exist, `govee_realtime_runner.py:63-81`).
3. Colorway effect: solid vs alternating flashes; `_color` fallback; strobe
   registration (name in `REALTIME_STROBE_EFFECTS`); param allowlist entries
   exist for every static param used by the new/changed looks (C5 guard).
4. Promotions: balloon width/brightness monotonic shrink over build_beats;
   heartbeat peak-normalization (constant peak luminance for a constant-width
   traveling head — the 0.53× regression test) + all four color_modes write
   only their documented slots; remnants ember timeline (full at beat ≤ 8,
   zero by beat 10.5 at defaults; slot 5 carries only background; embers only
   slots 0-4) + determinism (same seed/local_t → identical field).
5. Knob #4: for each rewritten cue, a frame rendered mid-body contains at
   most the spawn's single slot (plus slot-5 white where documented); the
   groove chase's two heads land on different slots; center burst main/accent
   stay in their slot bands.
6. Config: example config loads clean; the 7 colorway looks validate
   (strobe class + allowlist); bank membership assertions (colorways +
   promotions present; rt_drop_chase/rt_drop_nebula in post_drop, absent
   from drop; their drop_pairs entries gone; `step_within_section.groove`
   still true).

### Task 9 (ADDENDUM, operator refinement 2026-07-08 late — implement between Tasks 7 and 8) - narrow the slot-5 zone tint to NEBULA COMETS ONLY

Operator taste ruling: the zone-tinted slot-5 white applies to **nebula
comets only**. Firework bursts and twinkle-star whites keep BAKED pure white.

- Mechanism (single site, covers bridge + pad + lab injection paths alike):
  add a module-level `BAKED_WHITE_SLOT5_EFFECTS = frozenset({"post_drop_firework_chase"})`
  next to `SLOT_EFFECTS`; in `GoveeFrameRenderer.render()`'s slot path, right
  where `slot_colors` is resolved (`govee_frame_renderer.py:1927-1929` at
  spec-verification HEAD), when `str(name) in BAKED_WHITE_SLOT5_EFFECTS` and
  the palette has ≥ 6 entries, replace index 5 with the literal
  `(255, 255, 255)` before colorizing. Document on the set: future
  twinkle-star white accents belong here too (none write slot 5 today —
  knob #8 removed the breakdown stars' white; `_slot_twinkle` never had it).
- Nebula white comets (`rt_drop_nebula` / `rt_post_drop_nebula` slot-5
  writes) are deliberately NOT in the set — they read the zone tint once the
  operator mirrors. The example-config `slot5_white` zone tints STAY (nebulas
  are their consumer now).
- Boundary note (executive visibility): this spec's new
  `rt_post_drop_firework_remnants` uses slot 5 as its dimming BACKGROUND —
  that is a background, not a white accent, and the refinement did not name
  it; it stays zone-tinted. If the operator wants it pure, it is a one-line
  addition to the set.
- Knob #8 stands (no random white breakdown stars) — but the operator
  summary MUST carry the flag: one line (re-adding a white entry to the
  star-twinkle slot range or the baked set) restores occasional baked-white
  breakdown stars if he wants them back.
- Tests: firework-chase burst pixels render literal pure white under a
  fully-tinted injected palette; nebula white comets render the injected
  slot-5 tint; remnants background renders the tint.
- T8 registry text must include: "knob #3 refined — tint scope narrowed to
  nebula whites by operator taste 2026-07-08 late."

### Task 8 - Contract docs (final commit)

`led_govee` + `config_schema` contracts (`docs/agents/change_contracts.yml`):
update every `docs_update` doc for both — `docs/subsystems/led_govee.md`
(cue table rows for the 4 new effects + the mapping/width/bank changes + the
two standing promotion rules), `docs/status/feature_status_matrix.md`,
`docs/status/support_matrix.md`, `docs/status/validation_matrix.md`,
`docs/validation/hardware_validation_log.md`,
`docs/validation/software_test_inventory.md`,
`docs/status/active_work_registry.md` (AWR-156 row → implemented /
software-tested), `docs/architecture/palette_control_authority.md` +
`docs/plans/active/streamdeck_palette_control_design_spec.md` (verify, only
if claims touched), `docs/agents/task_playbooks/change_led_govee_behavior.md`,
`docs/subsystems/config.md`, `docs/setup/configuration.md`.

## Part C - Invariants That MUST Still Hold (live safety)

- The 200 Hz push loop and the runner thread gain no blocking I/O; the EMA is
  arithmetic on already-taken timestamps.
- Slot vectors stay exactly 6; slot 5 stays white-reserved — zone-tinted for
  NEBULA COMETS and the remnants background, baked pure white for effects in
  `BAKED_WHITE_SLOT5_EFFECTS` (Task 9); the heartbeat and knob-#4 rewrites
  write only slots 0-4.
- An un-mirrored live config renders identically to today for every look
  whose entry it defines (all new params live in the EXAMPLE config; the
  live config lacks them → renderer defaults reproduce current behavior
  EXCEPT the two locked behavior changes that need no config: the
  `_drop_white_aggressive` gate rebuild and the knob-#4 mapping change —
  name both in the operator summary).
- Strobe ceiling: nothing flashes faster than 10 Hz / 50% duty (gate caps);
  every strobing effect is in `REALTIME_STROBE_EFFECTS` so the `allow_strobe`
  config validation (`led_config.py:633`) keeps guarding it.
- C5: every static param on every new/changed look has an allowlist entry —
  one missing key disables ALL LED (tested in Task 7.3).
- AWR-149 rotation, AWR-150 substitute flow, AWR-154/155 blackout semantics:
  byte-identical code paths, untouched files aside.

## Part D - Test seams (summarized in Task 7)

All renderer logic is pure (frame = f(beat, local_t, frame_index, params,
segments, seed)); the runner timing uses the existing injectable
`time_fn`/`sleep_fn` seams; config assertions load the tracked example file
only.

## Part E - Acceptance (definition of done)

- [ ] Tasks 1-8 implemented in order, one commit per task, explicit paths
  (`git add` by path, never `-A`; auto-sync may fragment history — note
  affected tasks, never rewrite).
- [ ] Both contracts' `docs_update` lists fully updated; contract test
  commands + full `python3 -m unittest discover tests` (known environmental
  reds excepted — currently the 4+1 family) + the three hard doc checks all
  green.
- [ ] The two FLAGGED items (`strobe_red_white` side B = white; groove width
  2.5) called out in the operator summary as one-line veto points.
- [ ] Part A's [assumed] local_t wrap behavior verified and stated.
- [ ] LIVE config untouched; mirror + restart listed as operator-gated.
- [ ] Status language: implemented / software-tested / hardware-unvalidated.

## When You Finish

Report changed files per task, test/check output, the local_t verification,
and any deviation. Plain-language operator summary: after the next config
mirror + restart — the white drop strobe stops holding/stuttering and flashes
at a steady dialed rate at any BPM; seven colorway strobes join the drop
rotation at the rates he dialed (red+white pair restored to red+WHITE unless
he vetoes); the balloon buildup, heartbeat groove (palette-colored), and
firework remnants become real looks in their roles; comets stop rainbow-
smearing — each comet is one palette color; drop/post-drop comets get fat
heads (width 4), grooves 2.5 (veto-able); the sparkle chases move to the
post-drop slot where he said they belong. Groove color re-rolls stay exactly
as they are (his call). Nothing changes until he mirrors the config and
restarts; restoring the previous config restores today's behavior except the
strobe-gate fix and the single-color comets, which are code-level and were
his explicit verdicts.
