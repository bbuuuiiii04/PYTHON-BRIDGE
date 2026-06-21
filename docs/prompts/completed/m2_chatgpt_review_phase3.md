# ChatGPT Review Checklist — M2 Phase 3 (after Gemini implements)

Purpose: Phase 3 edits the 40fps render thread + BeatSyncEngine boundary. The dangerous failure is a
color-only change triggering a motion reset (visible stutter/restart on the live rig). Review the diff
against `main`; demand actual test output.

## Files that should appear in the diff (Patch 1 only — ONLY these)
- `govee_realtime_runner.py` (signature split, anchor capture, abs_pos threading, reset matrix).
- `govee_frame_renderer.py` (adds pure `resolve_fade(params, abs_pos, anchor_beat)` helper ONLY;
  `render`/`render_comet`/`_comet_frame`/`universal_colorizer` signatures UNCHANGED).
- `led_color_engine.py` (emit `color_from`/`color_to`/`fade_beats` + previous-color memory).
- `state_manager.py` may appear ONLY for LedColorEngine fade-memory reset hook wiring from existing realtime teardown / idle / emergency / force-deactivate paths.
- new test file.
Red flag any dispatch refactor, config/bank edit, cloud/DIY/RB/SoundSwitch/laser edit, or unrelated behavior change, OR changes the signature of `render`/`render_comet`/`_comet_frame`/
`universal_colorizer`.

## Motion vs color signature checks
- Motion signature EXCLUDES all 15 color keys: `color, color2, color_a, color_b, color_from, color_to, color_a_from, color_a_to, color_b_from, color_b_to, fade_beats, gradient_stops, slot_colors, slot_colors_from, slot_colors_to`.
- Color signature = EXACTLY those 15. The two partition cleanly (no key in both, none missing).
- `slot_colors_from`/`slot_colors_to` are present in the exclusion list (the common omission).

## configure-call checks (the core safety property)
- A color-only param change does NOT call `BeatSyncEngine.configure` (`_signature` unchanged → no reset).
- A motion param change DOES call `configure`.
- Verify via a spy/counter on `configure`, asserting exact call counts across color-only vs motion changes.

## Fade determinism checks
- `t = clamp((abs_pos - color_applied_abs_beat)/fade_beats, 0, 1)`; monotonic from→to; clamps at both ends.
- `fade_beats <= 0` ⇒ t=1 ⇒ output byte-identical to Phase 2 (no-fade).
- `resolve_fade` stays PURE: takes `params` + `abs_pos` + `anchor_beat`; reads no live engine/global
  state; makes NO `render`/`render_comet`/`_comet_frame`/`universal_colorizer` signature changes.
- No absolute `fade_start_beat` stamped anywhere.

## Reset matrix checks
- `_color_signature` + `_color_applied_abs_beat` + engine previous-color memory reset on: `_idle_tick`
  deactivation, `_emergency_teardown`, `force_deactivate`, `stop`, new audible track, color-SHAPE change.
- They do NOT reset on a mere motion/effect change.
- A new color signature stamps a fresh `_color_applied_abs_beat = abs_pos`.

## Previous-color memory + step checks
- Memory key = `(track_key, role, section_id, look_name, color_shape)`, `cycle` EXCLUDED.
- `look_name` + `color_shape` in the key (no cross-look contamination — test it).
- `step_within_section` uses `step_index = cycle`; deterministic; no wall-clock randomness.
- `fade_beats_by_role[role]` < the role's re-dispatch cadence (boundary test present).

## Test coverage / runtime / activation-gating checks
- Tests: color-only≠configure, motion=configure, signature partition, fade_beats=0 byte-identical,
  enabled:false byte-identical, deterministic interpolation, full reset matrix, step determinism,
  no-motion-reset-on-color-change. Full suite green (baseline + Phase 2b additions, 0 failed).
  - require tests proving each color/fade key does not call configure
  - require tests proving motion param changes still call configure
  - require true dual-color fade tests for color_a and color_b
  - require LedColorEngine previous-color memory reset through the approved StateManager hook
  - require render/render_comet/_comet_frame/universal_colorizer signatures unchanged
- No new per-frame allocation/lock on the 40fps path that wasn't there before (perf regression).
- CONFIRM Patch 1 implements deterministic fades in code whenever fade params are present. Existing looks without fade params preserve existing behavior. Config/bank activation is Patch 2, requires dry-run + sign-off.

## Claims Gemini is NOT allowed to make
- "Fades validated on the rig." (Dry-run + operator sign-off is a separate gate.)
- "Activated live." (Patch 1 enables behavior only when params present; config/bank activation is Patch 2).
- "Motion behavior verified unchanged" without the configure-call-count test proving it.
