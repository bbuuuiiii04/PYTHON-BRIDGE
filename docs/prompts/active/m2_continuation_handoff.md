# M2 Continuation Handoff — GEMINI EXECUTION CONTRACT (read this whole file first)

> Audience: **Gemini 3.1 Pro**, implementing M2 Phase 2b then Phase 3 on the rb_ss_bridge_v2 bridge.
> Editor: Opus 4.8 (spec-hardening pass, 2026-06-16), grounded against **current local `main`**.
> This is a LIVE DJ lighting bridge. Wrong edits to the 200Hz dispatch path or the 40fps render thread
> degrade a live show. **Be surgical. If anything is unclear or a precondition fails: STOP and report.
> Do NOT improvise, infer scope, over-edit, or touch unrelated systems.**

## 0. ABSOLUTE RULES (violating any = stop)
1. **Source of truth = current executable code on local `main`.** Not docs, not old branches. Verify every
   file:line claim before editing (it may have drifted). Do NOT `git pull`, do NOT switch branches, do NOT
   trust a doc over the code.
2. **Phase order is strict:** finish Phase 2b (code → review → tests green) **before** starting Phase 3.
3. **Two-step within each phase:** (step A) code + tests, safe/inert; (step B) live-config / activation,
   which is **operator-gated** — do NOT do step B without explicit operator sign-off in the task.
4. **Do not modify unrelated systems:** laser, Rekordbox, SoundSwitch, cloud/DIY scene logic,
   BeatSyncEngine motion, the baked sand cue's coloring. Touch ONLY the files each spec names.
5. **Do not commit, stash, push, or checkout** unless explicitly instructed. Leave changes uncommitted.
6. **If unsure, STOP and report. Never guess.**

## 1. PREFLIGHT (run before any edit; STOP if any check fails)
```
cd /Users/bbui/rb_ss_bridge_v2
git branch --show-current            # MUST be: main
git status --short                   # MUST be clean (ignore untracked docs/prompts/active/*.md)
cd /Users/bbui && /opt/homebrew/bin/python3 -m pytest -q   # MUST be 1661 passed / 3 skipped / 1 xfailed / 0 failed
```
If branch ≠ `main`, tree dirty with code changes, or any test fails BEFORE you edit → **STOP, report, do not edit.**

## 2. VERIFIED FOUNDATION (already on `main` — do NOT re-implement)
Confirmed from code 2026-06-16:
- **Phase 1**: `govee_frame_renderer.py` has `MAX_SLOTS=6`, `MotionField`, `universal_colorizer` (clamps via
  `_clamp_channel` = ROUND, not truncate), `SLOT_EFFECTS` (typed `dict[str, SlotEffectFn]`, `:1359`);
  `led_color_engine.py` has `resolve_slot_colors` (slots 0-4 gradient + slot 5 pure white).
- **Phase 2a**: 5 engine slot cues in `SLOT_EFFECTS` — `groove_center_chase`,
  `groove_center_burst_retract`, `post_drop_firework_chase` (slot-5 white bursts on 4th beat),
  `breakdown_full_breathing`, `breakdown_star_twinkle`; + baked `breakdown_star_twinkle_sand` (a Frame
  effect in `_EFFECTS`, NOT in `SLOT_EFFECTS`; hardcoded Dune Sand, 30% cap, bypasses the colorizer).
- **M1/M1b**: `state_manager._dispatch_led_automation` injects `resolve_color` → `params["color"]` at the
  seam (`computed = engine.resolve_color(...)` at `state_manager.py:1728`).
- Registries: `REALTIME_EFFECT_PARAM_KEYS` (`:913`), strobe cross-check in `led_config.py:585`,
  look validator `_validate_look` (`:337`), engine-only config parse `_parse_color_engine`.
- Runner anchors (`govee_realtime_runner.py`): `set_desired` :89, `force_deactivate` :117, `stop` :153,
  `_tick_once` :213, `_active_applied_monotonic` :70/:279, `_compose_frame` :318, `_idle_tick` :368,
  `_emergency_teardown` :389, `_signature` :403.
- **Regression baseline: 1661 passed / 3 skipped / 1 xfailed / 0 failed.** `test_led_config.py` passes
  clean. (Any older "1658 + 3 failures" note is STALE.)

## 3. WHAT TO BUILD (in this order)
- **Phase 2b** → `docs/prompts/active/m2_phase2b_impl_spec.md`. Make the 5 engine slot cues selectable +
  palette-colored: inject `slot_colors` at the seam for slot-based looks; define the 6 looks; (gated) add
  to banks. Read its **GEMINI SCOPE LOCK** + **REVIEWER PATCHES** blocks — they override the body.
- **Phase 3** → `docs/prompts/active/m2_phase3_impl_spec.md`. Deterministic color fades +
  `step_within_section` WITHOUT motion resets. Riskier. Read its **GEMINI SCOPE LOCK** + **REVIEWER
  PATCHES**. Two-patch split is MANDATORY. Patch 1 implements fades in code whenever params present; config/bank activation is step B, gated.
- **Then** M1 live-validation on the rig (operator runs a show; `grep color-inject /tmp/bridge.log`).

## 4. FILES THAT MAY CHANGE / MUST NOT CHANGE
Phase 2b — may change: `state_manager.py` (the seam only), a NEW `tests/test_led_color_engine_m2_phase2b.py`,
and (step B, gated) `config/led_look_director.example.json`. Must NOT change: renderer cues,
`govee_realtime_runner.py`, cloud/DIY logic, laser/RB/SS, the live `config/led_look_director.json` (operator's).
Phase 3 — may change: `govee_realtime_runner.py`, `govee_frame_renderer.py` (add pure `resolve_fade` helper
only; do NOT change `render`/`render_comet`/`_comet_frame`/`universal_colorizer` signatures),
`led_color_engine.py` (fade endpoints + previous-color memory), `state_manager.py` (NARROW EXCEPTION ONLY to call/add a LedColorEngine fade-memory reset hook from existing LED realtime teardown / idle / emergency / force-deactivate paths), NEW test file. Must NOT change: motion
geometry, BeatSyncEngine semantics, baked sand, unrelated systems.
**If you think you need to edit a file not listed, STOP and justify it to the operator first.**

## 5. REQUIRED FINAL REPORT (every phase)
1. Files changed (exact paths + line counts) — and confirmation NO other files were touched.
2. Exact behavior implemented, mapped to the spec sections.
3. Test commands run + ACTUAL output (targeted + full suite); the new tests you added.
4. Tests NOT run and why.
5. Risks / anything that didn't map cleanly (call it out; do not paper over).
6. Explicit confirmation each NON-GOAL was not touched, and nothing was committed.
7. The exact next step.

## 6. STOP CONDITIONS (stop immediately and report; do not improvise)
- Working tree dirty with code changes before you start.
- Branch is not `main`, or expected Phase 1/2a foundation (§2) is missing.
- Any test fails BEFORE your edits.
- Uncertainty about config-load behavior or which keys are allow-listed.
- You would need to touch a system not listed in §4.
- You cannot preserve the baked sand cue as baked/non-slot-colored (Phase 2b).
- You cannot guarantee Phase 3 color-only changes avoid a motion reset / `configure` call.
- A spec instruction conflicts with the actual code.

## 7. STANDING OPERATOR RULES
- No config or production edits without explicit approval; adding looks to live banks = live-selectable on
  restart → needs sign-off + a dry-run watch.
- Keep all engine calls on the hot path try/except-guarded (degrade to engine-off, never crash dispatch).
- `color_engine.enabled:false` (or no block) must remain byte-identical to legacy.
- Verify before writing; label findings confirmed/assumed/unknown; no unsolicited scope.

## 8. RECOVERY / TOPOLOGY NOTE
`main` (currently the integration point) absorbed the color-engine work via squash PRs #103/#104. Prior
states are still reachable (`214e206`, `origin/m2-phase2-cues` @ `b69b74d`) if needed. An automated process
in this repo periodically commits the working tree into catch-all commits and may fork branches from stale
points — always re-run PREFLIGHT (§1) and re-verify anchors against the actual tree before trusting them.
```
```
