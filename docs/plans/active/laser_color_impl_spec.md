---
doc_status: active-spec
truth_level: implementation-spec, code-grounded
last_verified_commit: bd96b32
last_verified_date: 2026-07-04
validation_scope: spec only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; CH8/CH9 value table intentionally ships empty (pass-through)
---

# Codex Implementation Spec — Laser color plumbing (Package 4 of AWR-111)

Behavior contract: `docs/architecture/laser_color_authority.md`. Design
evidence: `docs/plans/active/laser_color_engine_design_spec.md` Parts B, D, E.
Depends on Package 2 (`streamdeck_palette_control_impl_spec.md`) for the
engine accessor's mode fields and `white_sand`; implement after it.

**The chart is NOT a dependency of this package.** Everything here ships with
an empty value table = byte-identical pass-through output. The operator's
CH8/CH9 chart later lands as pure config.

## Part A — Context (verified at `bd96b32`; read, do not implement)

- [confirmed] The pack player renders the whole 19-channel frame
  (`soundswitch_laser_player.py:23` `CHANNEL_COUNT = 19`); `render()` :422
  returns `ZERO_FRAME` when masked (:423-424) BEFORE any base render;
  scripted base via `_scripted_base`, autoloop base via `_autoloop_base`
  (:388-420, success path :417-418 `render_autoloop_frame`); every
  diagnostic/uncertain path returns before a healthy frame; static-override
  layers apply OVER the base (:443-457) and lose to blackout (:202-203).
- [confirmed] Autoloop documents ALREADY author CH8/CH9 (922 cue writes
  across 42 docs, incl. bridge-active ones) — injection is a deliberate
  overwrite; pass-through = today's exact output.
- [confirmed] `CONTROL_CHANNELS = {8, 9, 11}` (:25); `clear_control` events
  preserve them (:109-111). CH11 = strobe, operator-ruled untouched.
- [confirmed] Render and LED dispatch share ONE thread: `_push_tick` →
  `_drive_pack_output` → `render()` (`state_manager.py:2092-2107,2415,2635`)
  and `_dispatch_led_automation` → `begin_dispatch`
  (`led_dispatch_policy.py:637,731` ← `state_manager.py:3029`) both run on
  the `state-manager` thread (:586,643). So color computation at dispatch
  time and consumption at render time need NO cross-thread synchronization —
  just pure, non-blocking math.
- [confirmed] No "current RGB" accessor exists on the LED engine —
  `resolve_color` (`led_color_engine.py:507`) needs per-cue context;
  `snapshot()` returns names, not RGB. Package 2 adds the fade/mode fields
  this package reads.
- [confirmed] White-moment read point: the per-dispatch template name is
  chosen at `led_dispatch_coordinator.py:219-227` (`scene_ref` →
  `EffectSpec.effect_name`, called from :130), on the state-manager thread.
  White templates: `drop_white_aggressive` (`govee_frame_renderer.py:505`,
  dispatch :866-867), `post_drop_white_shatter` (:515, :868-869),
  `buildup_white_zone_strobe`/`buildup_white_half_strobe` (:874-876).
- [confirmed] Fixed-color model (operator): CH8 = {Red, Green, Blue, Cyan,
  Yellow, Purple, White} + effect families (color-change, RGB color-change,
  "original color change", flowing-water combos, gradient); CH9 = color
  speed. Exact values pending the operator chart.

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Out of scope: blackout/mask logic (Package 1), the drop presentation
  policy (Package 3), the MIDI scene path, exporter/pack files, CH11 anywhere.
- With `enabled: false` OR an empty value table, every rendered frame must be
  **byte-identical** to current behavior — this is the master regression
  gate.
- No I/O, locks, or allocation storms in `render()`; the injection is a
  tuple-copy + two writes.
- Error handling: any mapper error → no injection this frame (fail-open =
  authored pass-through), never a raise into the render path beyond what
  already fail-closes to ZERO.

### Task 1 — `led_color_engine.py`: color-state accessor
Add `color_state() -> dict`: `{rgb: (r,g,b) from _p_to_rgb(_anchor_p) [the
current blended anchor during a fade], palette: _current_palette,
white_sand_active: bool (current or mode-mapped palette is white_sand),
rainbow_active: bool (_mode_override is set)}`. Pure read, state-manager
thread only, no RNG advance (must not perturb seeded journeys — assert in
tests that calling it changes no engine state).

### Task 2 — white-moment flag
In `LEDDispatchCoordinator._spec_from_decision` (or its :130 caller — pick
the single site where `scene_ref` is final), set a `white_moment: bool` on
the dispatch result when `scene_ref` is in the white-template set. Carry it
to StateManager's laser-color update call (Task 3). The template set is
config (`config/laser_color_map.json` `white_templates`, defaulting to the
four names above) so new Template-Lab whites join without code.

### Task 3 — NEW `laser_color_engine.py`: mapper + snapshot
1. `LaserColorMap` — loaded from `config/laser_color_map.json`:
   `{enabled: bool, fixed: {red|green|blue|cyan|yellow|purple|white:
   int|null}, effects: {rainbow_family: {ch8: int|null, ch9: int|null}},
   settle: {ease_beats: int}, white_templates: [str]}`. `null` anywhere =
   that behavior does not inject (pass-through). Ship
   `enabled: false` + all-null example.
2. `LaserColorEngine.update(state: dict, *, white_moment: bool,
   drop_phase: str | None, post_drop_progress: float | None)` — pure math,
   called on the state-manager thread from the LED dispatch path (beside the
   Task 2 carry): computes the target `(ch8, ch9) | None`:
   white_moment or white_sand_active → `fixed.white`; rainbow_active →
   `effects.rainbow_family`; else nearest fixed color to `rgb` by squared
   RGB distance over the six non-white colors (White is NEVER nearest-color
   output; deterministic tie-break in the order red, green, blue, cyan,
   yellow, purple); post-drop → CH9 eased down linearly across
   `settle.ease_beats` (never below 0). Any needed value `null` → result
   `None`.
3. Stores the result as an immutable `LaserColorSnapshot(ch8, ch9, seq)`
   attribute; `snapshot() -> LaserColorSnapshot | None`. Single-threaded by
   construction (Part A) — document that with a comment, no locks.

### Task 4 — `soundswitch_laser_player.py`: the merge seam
1. `LaserPackPlayer.set_color_snapshot(snap | None)` — stored attribute;
   `reload()` and `clear_selection()` leave it alone (it is re-set every
   dispatch); masks ignore it by construction.
2. In `_autoloop_base` ONLY, on the success path (:417-418): if a snapshot
   with non-None values is set, copy the rendered tuple and overwrite
   index 7 (CH8) and index 8 (CH9) before returning. Scripted, diagnostic,
   reload-wait, missing-selection, and masked paths are untouched — they
   return before this line or bypass base render entirely.
3. StateManager wiring: after each `LaserColorEngine.update(...)` in the
   dispatch path, pass the snapshot to the player
   (`player.set_color_snapshot(engine.snapshot())`); pass `None` while the
   feature is disabled.

### Task 5 — tests: `tests/test_laser_color_engine.py`
1. **Byte-identity master test:** with `enabled: false`, an all-null table,
   or no snapshot: rendered frames across scripted/autoloop/masked/
   static-layered/diagnostic scenarios are identical to a control run
   without the feature.
2. Quantizer: synthetic table → known RGB → expected colors; White never
   produced by nearest-color; deterministic tie-breaks.
3. Injection scope: only healthy autoloop frames differ when a snapshot is
   set; blackout → ZERO regardless; static override applied after injection
   wins its channels; CH11 byte-identical in every scenario.
4. White moment: flag on → `fixed.white` on CH8 for the duration; off →
   reverts to quantized color. `white_sand` → sustained white.
5. Settle: CH9 monotonically non-increasing across post_drop_progress 0→1.
6. `color_state()` mutates nothing (snapshot engine state before/after).

## Part C — Invariants That MUST Still Hold
- Blackout/emergency absolute (frame ZERO regardless of snapshot); static
  override outranks injected color; "unsure → do not inject" structural.
- CH11 never written by any new code path.
- Fail-open = authored CH8/CH9 pass through; never "no lasers."
- Render path gains no I/O/locks; push-tick crash path
  (`state_manager.py:2100-2106`) untouched.
- Scripted tracks byte-identical always (authority: authored show sovereign).
- All AGENTS.md §6 invariants; no bridge restart authorized.

## Part D — Tests
Task 5; the quantizer/settle/white logic is a pure-function seam (table +
inputs → values, no files beyond loading the JSON config in one loader test).

## Part E — Acceptance
1. Contract-first: extend the `laser` contract + add `laser_color` in
   `docs/agents/change_contracts.yml` (docs_update:
   `docs/subsystems/laser.md`, `docs/architecture/laser_color_authority.md`,
   `docs/plans/active/laser_color_engine_design_spec.md`,
   `docs/status/active_work_registry.md`) BEFORE code.
2. Tasks 1-5 green; byte-identity master test green; full suite green; docs
   checks pass; §10 status language only.
3. No diff outside: `led_color_engine.py` (accessor only),
   `led_dispatch_coordinator.py` (flag only), `laser_color_engine.py`,
   `soundswitch_laser_player.py` (seam only), `state_manager.py` (wiring
   only), `config/laser_color_map.json` (new, all-null), tests, contract docs.

## When You Finish
Report: changed files, test counts, checks, and the operator summary: with
the shipped config the lasers behave EXACTLY as today (pass-through); when
his CH8/CH9 chart lands it goes into `config/laser_color_map.json` and
`enabled: true` — no code changes; hardware validation remains his gate.
