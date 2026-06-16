# M2 Session Handoff — LED Color Engine M2 + new motion-skeleton cues

> Written 2026-06-15 by the M1b session (Claude/Opus). Read this top-to-bottom before
> touching code. Everything below was verified against the live tree this session; line
> numbers are anchors — **match on symbol names, re-verify before editing.**

## 0. Your mission (two interleaved tracks, NOT two projects)
1. **Implement & review color-engine M2** — the §15.1 slot-vector motion field + universal
   colorizer, and §15.4 self-anchoring fades + `step_within_section` + `abs_pos` plumbing.
2. **Wire in the operator's new motion-skeleton cues** (prototyped in the Antigravity/Gemini
   IDE). These cues ARE M2: they already emit a 6-slot `MotionField` and use the exact
   §15.1 colorizer formula. So building M2's slot architecture is the prerequisite that makes
   the cues wire-able — do them together, not separately.

## 1. Current state

### M1 (done, all on branch `codex/led-doc-cleanup-gates`)
- **M0** (config/model plumbing) + **M1a** (pure `led_color_engine.py`) — COMMITTED in `cf00363`.
- **M1b** (integration) — **DONE + adversarially reviewed (PASS), UNCOMMITTED in the working
  tree.** 5 files: `__main__.py`, `state_manager.py`, `led_look_director.py`, `led_models.py`,
  `govee_frame_renderer.py` + new `tests/test_led_color_engine_integration.py` (16 tests).
  Targeted LED suite 217 passed / 0 new fails; whole suite 1604 passed. The only 3 failing tests
  (`test_led_config.py` ExampleConfig/LiveMode) are PRE-EXISTING (re-confirmed via git stash on the
  clean tree). **FIRST TASK: decide whether to commit M1b before starting M2** — a dirty tree under
  M2 work will be hard to reason about. (Commit only if the operator asks.)

### Live config — engine is ON (gitignored `config/led_look_director.json`)
- A `color_engine` block was added, `enabled:true`. Takes effect on **bridge restart**.
- **Disable fast:** set the block's `enabled:false` → engine off, LED automation unaffected (C5).
- Backups: `/tmp/led_look_director.json.precolorengine` (pre-engine), `/tmp/led_look_director.json.pre_diytags`.
- Recolors ONLY the 15 realtime chase looks (`rt_groove_chase_*`/`rt_drop_chase_*`/`rt_post_drop_chase_*`).
  `exempt_looks` = the other 42 looks. `step_within_section` is ALL-FALSE (M1 holds color per section).
- `diy_color_tags` IS now populated (25 looks) — DIY scene selection follows the palette
  (cohesion), with `white`/untagged looks always eligible and the C4 full-bank fallback guaranteeing
  banks never empty. Verified: blue_cyan→cyan breakdown only; crimson→red only; deep_ocean→cyan+green.
- 5 cool-corridor palettes: `blue_cyan`(10) `indigo`(6) `deep_ocean`(4) `violet`(3) `crimson`(2);
  dwell 3, snap@drop idx (2,3), big_shift 0.30/bias 1.5, `set_seed_mode:random`.
- **Live validation gate (§15.7) is NOT yet done** — the engine has not been watched on hardware.
  Watch `grep color-inject /tmp/bridge.log` and `grep color_engine_error /tmp/bridge.log`.

### Debug observability
- `state_manager._dispatch_led_automation` logs one line per actual injection:
  `[RGB] color-inject look=… palette=… color=… role=… role_key=…`. Injected color is otherwise
  invisible (not in the trigger-accepted log; dry-run frames render nothing). M2 should extend this
  to log `slot_colors` when it starts producing them.

## 2. Authoritative sources
- **`docs/plans/active/led_color_engine_spec.md` §15 is THE contract.** For M2 specifically:
  - **§15.1** — B1: motion field is a per-pixel SLOT-INTENSITY VECTOR (not a scalar pair). Fold =
    sum per-slot; colorize = `rgb[px] = clamp(Σ slot_color[slot]·intensity[px][slot])`. Both render
    paths route the SAME colorizer. Single-slot effects must stay bit-identical to M1.
  - **§15.4** — B4/H1: a DEDICATED color-anchor clock; color keys EXCLUDED from the motion signature;
    self-anchoring fades (`color_from`/`color_to`/`fade_beats`, NO absolute fade_start_beat); requires
    threading `abs_pos` + `color_applied_abs_beat` into `_compose_frame`→`render`/`render_comet`.
    `applied_abs_beat` is NOT retrievable today — read §15.4's correction carefully.
  - **§15.7 M2** — acceptance: structure-invariant (two injected colors → identical slot/intensity
    field, only RGB differs); golden-frame parity vs the M1 baseline (single-slot bit-exact, multi-slot
    ±1/channel documented); fade determinism. **Gate: M2 starts only after M1 is validated live.**
  - **§15.5 note** — `REALTIME_EFFECT_PARAM_KEYS` MUST be extended for new static param keys
    (`slot_colors`, `gradient_stops`, etc.) on the effects that accept them, **or C5 disables ALL LED.**
- **Operator's cue-wiring brief:** `docs/prompts/active/opus_m2_cue_wiring.md` — owns the cue geometry,
  timing, aesthetic, and explicit wiring rules (e.g. DO NOT overwrite `post_drop_chase_*`; add a new
  `post_drop_firework_chase_*` family). Follow it for the cues; do NOT alter the geometric math.
- **Cue prototype:** `~/.gemini/antigravity-ide/brain/dfbaeb5b-bff1-4229-b752-205a92c40a78/scratch/motion_skeletons.py`
  (operator-owned). Treat its math as the source of truth for cue behavior.

## 3. The key architectural insight (read this twice)
The prototype already implements §15.1:
- `MAX_SLOTS = 6` (spec said "default 4" — 6 is fine, it's a configurable default). Slots **0-4 =
  the gradient palette**, **slot 5 = pure white** (reserved for twinkles/fireworks).
- `MotionField = List[List[float]]`, shape `[segments][MAX_SLOTS]` — palette-AGNOSTIC geometry.
- `universal_colorizer(field, slot_colors)` = the exact §15.1 formula.

So the division of labor M2 must build:
- **Cue renderer** emits a `MotionField` (pure geometry; no color knowledge).
- **Color engine** produces `slot_colors: List[RGB]` (length 6) from the CURRENT palette focus
  window — sample 5 gradient points across the focus interval into slots 0-4, put pure white in slot 5.
  This is the new M2 output of `led_color_engine` (today it emits `color`/`color_a`/`color_b`; M2 adds
  `slot_colors`). The p→RGB scale + focus window + white-blend logic already exists in M1a — reuse it.
- **Render path** runs `universal_colorizer(field, slot_colors)` → `Frame`. Per §15.1 BOTH `render`
  and `render_comet` must route the same colorizer; `_comet_frame` emits slot-intensity instead of
  pre-multiplied RGB so additive comet overlap is correct.

Single-slot effects (today's drop_chase/groove_chase) must remain bit-identical when expressed as a
1-slot field (golden-frame test — §15.7/§10 H4).

## 4. Work breakdown

### Track A — color-engine M2 core
A1. `led_color_engine`: add `resolve_slot_colors(...)` (or extend `resolve_color` with a `slots=N`
    mode) → returns `{"slot_colors": [rgb0..rgb4, white]}` sampled across the current focus window.
    Keep it PURE (§15-N8 concurrency invariant: colorizer never dereferences a live engine; all color
    flows by value through `decision.params`).
A2. `govee_frame_renderer`: introduce `MotionField` + `universal_colorizer`; refactor `render` and
    `render_comet` to a shared colorize path; make `_comet_frame` emit slot-intensity. Single-slot
    parity is the gate (golden frames).
A3. §15.4 fades: the dedicated color-anchor clock in `govee_realtime_runner` (motion signature
    EXCLUDES color/fade keys; a separate color signature captures `color_applied_abs_beat`); thread
    `abs_pos` into the colorizer. Then `step_within_section` + `fade_beats_by_role` become live (the
    config already carries them; M1 set step all-FALSE and fades 0). Re-read §15.4's `applied_abs_beat`
    correction — naïvely reusing `configure` time is WRONG.
A4. Extend `REALTIME_EFFECT_PARAM_KEYS` for `slot_colors` (+ any new static keys) on the new effects
    (§15.5 — or C5 disables ALL LED). Add tests for the C5 invariant.

### Track B — wire the cues (per `opus_m2_cue_wiring.md`)
- `groove_center_chase` (dual-head center comet, gradient slots 0-4).
- `post_drop_firework_chase_*` (NEW family — do NOT overwrite `post_drop_chase_*`): comet + tail strobe
  + white firework bursts on slot 5, firing ONLY on the 4th beat of each 4-beat cycle.
- `groove_center_burst_retract` (volume-bar burst-out/retract).
- `breakdown_full_breathing` (full-strip sine breathing + color drift across slots over 32 beats).
- `breakdown_star_twinkle` (MotionField version — palette-driven per-pixel breathing stars).
- `breakdown_star_twinkle_sand` (**hardcoded "Dune Sand" RGB, BYPASSES the colorizer**). NOTE: the sand
  palette is warm orange/amber — it deliberately violates the cool-corridor "no orange/yellow" rule
  because it bypasses the engine. Keep it as an explicit hardcoded special look; do NOT route it
  through the palette engine, and do NOT let it leak into the engine's `scale_stops`.
- Register new effects in `_EFFECTS`/`_GENERIC_EFFECTS` and the new looks in the look config; add them
  to the appropriate banks. Decide `color_source`/`exempt`/`diy_color_tags`/`slot_colors`-eligibility
  for each (the engine recolors slot-based looks via `slot_colors`; sand is exempt/baked).

## 5. Integration anchors (verified this session — re-verify)
- `govee_frame_renderer.py`: `_GENERIC_EFFECTS` :793, `_EFFECTS` :838, `REALTIME_EFFECT_PARAM_KEYS`
  :878 (gradient_sweep keys :885), `REALTIME_EFFECT_NAMES` :852, `_edm_dispatch` :760, `render` :958,
  `render_comet` :934, `_color` helper :24. EffectFn sig: `(name, beat, local_t, frame_index, params,
  segments, seed) -> Frame`.
- `led_dispatch_coordinator.py`: `_spec_from_decision` :208 builds `EffectSpec(params=…)`;
  `EffectSpec.seed` derives from the LOOK NAME (:216) NOT params — engine must compute final colors.
  WI-3 min-dwell gate :74-87 (1.5s) — keep step cadence > that.
- `govee_realtime_runner.py`: `set_desired` propagates params each tick; `_signature` (~:404) gates
  `configure`. §15.4 work lives here.
- `state_manager.py`: M1b seam in `_dispatch_led_automation` (~:1634-1742) — `begin_dispatch` after
  dedup, `resolve_color`+merge before trigger (:1688), structured `(section_id,cycle)` published by
  `_led_automation_role_key` via `self._led_last_section_cycle`. The debug log is here (~:1741).
- `led_models.py`: `Palette` :58, `ColorEngineConfig` :80 (has `step_within_section`, `fade_beats_by_role`,
  unused-in-M1), `LEDLook.color_source/diy_color` :54-55, `LEDLookDecision.color_source` :221,
  `LEDContext.diy_eligible` :207.

## 6. Gotchas, invariants, decisions
- **`enabled:false` / no `color_engine` block ⇒ byte-identical legacy behavior.** Preserve this through M2.
- **Hot-path safety:** all engine calls in `state_manager` are try/except-guarded (degrade to no color).
  Keep new M2 calls equally guarded. Colorizer must be pure and non-blocking (40fps render path).
- **Single-slot bit-exact** is the M2 acceptance gate — write the golden-frame test FIRST.
- **`MAX_SLOTS` reconciliation:** spec says 4, prototype uses 6. Recommend 6; confirm with operator.
- **Sand palette** is intentionally warm + hardcoded — do not "fix" it into the cool corridor.
- **`drop_chase_freestyle_nebula`** is routed to a nebula (`_edm_dispatch` :766/:780), NOT the recolorable
  `_drop_chase`, despite the name prefix — don't be fooled.
- **C5 / `REALTIME_EFFECT_PARAM_KEYS`** is a foot-gun: a new static param key not allow-listed disables
  ALL LED. Runtime-injected params are NOT validated, but static look params ARE.

## 7. Workflow & review discipline (operator's standing rules — honor them)
- The operator has authorized orchestrating implementation via **subagents** for the LED color-engine
  work (this overrides the usual "Codex implements" rule for THIS task). Pattern per milestone:
  **implement subagent (strong model for live-path / Sonnet for mechanical) + Claude adversarial review.**
- **Verify before writing**: run/grep/load to ground every file:line claim; label findings
  confirmed/assumed/unknown. Don't trust subagent test PASS at face value — M1a AND M1b reviews each
  caught a real bug the subagent's own tests masked (an absolute-import break; a masked param case).
  Read the new tests and confirm they assert meaningfully (exact equality, real behavior), not vacuously.
- **Live-mixing safety**: think through what changes on the live rig before enabling; provide a fast
  disable path; gate risky changes behind `color_engine.enabled` and a non-show dry-run.
- No unsolicited scope; present findings and confirm before large/irreversible changes.

## 8. Acceptance / gates
- M1 live dry-run OK (watch the rig) BEFORE trusting M2 visually — but M2 code can be built/tested behind
  the flag in parallel.
- Per §15.7 M2: structure-invariant test, golden-frame parity (single-slot bit-exact; multi-slot ±1/ch
  documented), fade determinism. Each milestone: its own tests green + one live dry-run.

## 9. Open questions for the operator
- Commit M1b (and the debug log) now, or hold until the live dry-run validates it?
- `MAX_SLOTS` = 6 (prototype) confirmed?
- Which banks/roles do the new cues join, and at what weights? (`groove_center_chase` → groove?
  `post_drop_firework_chase_*` → post_drop? the three `breakdown_*` → breakdown/ambient?)
- Should `step_within_section` turn ON for any role once fades land, or stay hold-only for now?
