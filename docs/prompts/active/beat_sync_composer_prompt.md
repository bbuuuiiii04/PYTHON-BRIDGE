# Composer Implementation Prompt — Universal Beat-Sync Trigger Runtime

## Context

Repo: `/Users/bbui/rb_ss_bridge_v2/`
Real-time Rekordbox → SoundSwitch → Govee LED bridge. It runs live at EDM shows; wrong behavior
is immediately visible to an audience. Implement exactly what the spec says. Do not add features,
do not refactor beyond the spec, do not add comments the spec does not include.

Correction note: the original beat-sync draft over-specified `groove_chase_*` as
`overlap` by default. That regressed the live visual smoothness because it bypassed the
existing named `_groove_chase()` / `_dual_chase()` scene. The revised spec keeps normal
`groove_chase_*` looks on the continuous named renderer; `overlap` is opt-in only.

## Spec

Read and implement the full spec at:
```
/Users/bbui/rb_ss_bridge_v2/docs/plans/active/beat_sync_runtime_spec.md
```
Part A is context. Part B (Tasks 1–6) is what you implement. Part C is the tests you write. Part D
is the acceptance bar.

## Absolute Rules

1. **Follow the revised spec exactly.** Tasks show the exact code / current→replacement. Use those exact
   strings; do not paraphrase or "improve" them.
2. **`GoveeFrameRenderer` effect functions stay pure** — all new state lives in the new
   `beat_sync_engine.py`. The beat-sync renderer additions are `_comet_frame`, `render_comet`,
   `blank`, `fold_additive`, the param-key unions, and the default-resolver helpers. Preserve
   existing local smoothness fixes such as interpolated moving heads.
3. **Normal `groove_chase_*` defaults to `continuous`, not `overlap`.** With live JSON `params={}`,
   `rt_groove_chase_*` must reuse the existing named `_groove_chase()` scene so the chase remains
   smooth. The `overlap` mode still exists as an explicit opt-in and renders the comet primitive,
   NOT the named `groove_chase` function.
4. **Do NOT edit `config/led_look_director.json`.** All defaults resolve in code; the live JSON
   stays `params={}` and must keep loading. If you think a config edit is needed, stop and report.
5. **Do NOT** commit, deploy, restart the bridge, enable it live, or touch the live config. Work on
   a branch / working tree only.
6. **Do not modify any file the spec does not name.** Files in scope: `beat_sync_engine.py` (new),
   `govee_frame_renderer.py`, `led_config.py`, `govee_realtime_runner.py`,
   `led_dispatch_coordinator.py`, and the four test files in Part C.
7. If a `file:line` reference has drifted, locate by the quoted snippet / function name, not the
   number.
8. All existing tests must stay green. Run the full suite.

## Task order (commit after each)

1. Task 1 — `beat_sync_engine.py` (new module: `TriggerClock`, `AnimInstance`, `InstanceRender`, `BeatSyncEngine`).
2. Task 2 — config permit + validate new params (`govee_frame_renderer.py` param-key union + defaults; `led_config.py` validation).
3. Task 3 — renderer comet primitive + `render_comet` / `blank` / `fold_additive`.
4. Task 4 — `EffectSpec` fields, `_signature`, `_spec_from_decision`.
5. Task 5 — runner: engine wiring, `fire_trigger` + manual queue, `_tick_once`/`_compose_frame`, status fields, teardown clears.
6. Task 6 — coordinator: call `fire_trigger()` on manual realtime trigger.
7. Part C — write all tests. Part D — verify acceptance.

## When you finish

Output, as the final section of your response, a single fenced code block titled
`PASTE BACK TO CLAUDE` containing a concise review-request for Claude that includes:
(a) every file you changed/created, one-line rationale each;
(b) every deviation from the spec and why (if any);
(c) any TODOs/assumptions/uncertain spots;
(d) the exact test command you ran and its pass/fail summary;
(e) an explicit request for Claude to review for: freeze actually fixed across a scripted
backward-wrap anchor; `groove_chase_*` defaults to continuous named-renderer behavior; explicit
`overlap` comet vs `retrigger`/`continuous` correctness; `sync_mode` coverage of all effects;
thread-safety of `fire_trigger` vs the 30 fps tick; live-mixing safety under manual spam + fast
loops; owner-lock/leak (instances cleared on deactivate/emergency); config back-compat (live JSON
still loads).

That block is what the operator copies back to Claude for review.
