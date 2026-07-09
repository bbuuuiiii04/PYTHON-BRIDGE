---
doc_status: current
truth_level: code-verified
last_verified_commit: d93f047
last_verified_date: 2026-07-09
validation_scope: >
  Codex implementation spec for AWR-177: the FIRST consumer of the F2 plan's
  per-drop white_share — a params-only white blend on the drop cue's engine
  colors (big builds flash whiter), kill-switched (example-OFF, absent-OFF,
  byte-identical when off), push-loop-safe, mask precedence untouched. Every
  file:line verified at d93f047. Paper only — nothing implemented; ships OFF;
  implementation gates on executive dispatch; activation is an operator
  live-tuning call.
---

# Codex Implementation Spec - White-share drop consumer (AWR-177)

F2 computes a per-drop `white_share` — how intense the build into each drop
measured (design D§5.2: flux rise + level rise over the build window) — and
today **nothing reads it**. This spec wires the first consumer: when the drop
cue fires, its engine-resolved colors blend toward white by an amount mapped
from that drop's `white_share`. A calm-build drop renders exactly as today; a
monster build flashes whiter. Params-only, downstream of every darkness gate,
OFF everywhere until the operator turns it on.

Authority: `docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md` §5.2 (:448-467).
Contracts: `led_govee` + `config_schema` (`docs/agents/change_contracts.yml`).

## Part A - Context & Root Cause (verified; read, do not implement)

1. **Producer [confirmed]** — `white_share()` at `lighting_moments_v2.py:457-472`
   (constants `WHITE_*` `:124-130`, all TUNE-LIVE); stored per drop on
   `DropPlanEntry.white_share` (`:742`, computed at `:850`, rounded `:858`).
   Range [0.15, 1.0]; corpus distribution (design :464-466): masses at
   0.2–0.4, 128 builds ≥ 0.6, only 6 ≥ 0.9 — so a mapping that ignores the
   low mass and scales the tail matches the design's intent ("monsters earn
   full white, ordinary builds get mixes").
2. **Zero consumers [confirmed by repo-wide grep at d93f047]** — no reads of
   `white_share` in `led_dispatch_policy.py`, `led_color_engine.py`,
   `led_look_director.py`, or `govee_frame_renderer.py`. Design note: the
   §5.2 slot-5-weight wiring (design :466-467) targets *buildup* cues and the
   §8 color-slot contract; the operator-directed FIRST consumer (ledtune
   Track C directive, 2026-07-09) is the *drop* look. The old engine-level
   `white` blend knob was removed as dead weight (`led_color_engine.py:37-43`)
   — do not resurrect it; this consumer is per-drop, not per-palette.
3. **The dispatch seam [confirmed]** — the automation dispatch path resolves
   the decision, then injects engine colors
   (`led_dispatch_policy.py:1501`, `_led_inject_engine_colors`), then injects
   F4 seasoning params (`:1508`, `_led_inject_f4_seasoning` — the containment
   precedent: params-only, `replace(decision, params={...})` at `:1255`,
   decision returned unchanged when off). The white blend is a third injection
   immediately after `:1508`, so it composes over whatever colors the engine
   and F4 produced.
4. **Color params shape [confirmed]** — `resolve_color`
   (`led_color_engine.py:589-688`) injects `{"color": (r,g,b)}` plus
   optionally `color_a`/`color_b` (multi) and `color_from` (crossfade
   memory). Looks that inject nothing (engine disabled, exempt looks,
   non-engine `color_source`) have no color params — the blend then no-ops by
   construction. Baked white-only drop shapes are unaffected (already white).
5. **Plan lookup helper [confirmed]** — `_led_f4_active_drop_entry`
   (`led_dispatch_policy.py:1159-1171`) returns the F2 plan entry for the
   CURRENT drop anchor and already stands scripted decks down and handles
   no-plan/no-anchor as `None`. Reuse it verbatim (it is F4-*named* but
   generic — an entry lookup; add a comment noting the second caller).
6. **Gate ordering [confirmed]** — blackout/manual/solo owners gate the
   dispatch *before* the injection point: solo predark returns at
   `:1419-1428`; `moments_blocked` (blackout / manual override / smart-drop
   tactical blackout) is computed at `:1400-1404`; emergency/blackout owners
   zero frames downstream in the child regardless of params. A params-only
   color blend therefore cannot re-light a masked moment — the same
   containment argument the AWR-173 review settled for the CFX overlay.
7. **Config pattern [confirmed]** — sub-feature-inside-`f2` precedent:
   `impact_burndown` (`led_models.py:128-129`, parsed `:154-163` fail-closed;
   example config ships it `"enabled": false` inside an enabled `f2` block).
   `load_f2_config` (`led_config.py:152-166`): absent block / missing file /
   bad JSON ⇒ defaults ⇒ everything off. `StateManager` keeps the full config
   object at `state_manager.py:784` (`self._f2_config`) — the policy mixin
   reads it directly; no new plumbing needed.
8. **Kill-test precedent [confirmed]** — byte-identity tests in
   `tests/test_lighting_moments_v2_f4.py:203-231`
   (`test_f4_off_seasoning_is_identity`, `test_seasoning_changes_only_params`)
   are the exact shape to mirror.
9. **Mapping defaults [assumed — TUNE-LIVE]** — `lo=0.40, hi=0.95,
   max_blend=0.85` below are provisional taste anchors chosen from the corpus
   distribution (most drops unaffected; the ≥0.6 tail whitens progressively;
   the six ≥0.9 monsters approach `max_blend`). The operator's live-tuning
   session owns the final values.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- **Out of scope:** `white_share()` math and every `WHITE_*` constant in
  `lighting_moments_v2.py`; buildup-cue behavior (design keeps "buildup cues
  keep baked white behavior" until F2 owns them, design :581); the laser and
  SoundSwitch paths; `led_color_engine.py` (no engine change — this is a
  dispatch-side post-process); the frame-engine child / renderers; cloud DIY
  scene content (prebaked — no color params to blend; the staged-takeover
  path `:1556-1566` is untouched).
- **Behavior that must not change:** with the feature off (flag false OR
  block absent OR `f2` absent), every dispatched decision object is
  byte-identical to today — same params dict contents, same look/scene_ref/
  backend/schedule. Mask/blackout precedence untouched. Scripted decks
  untouched. Role cues other than `drop` untouched.
- **Error handling:** malformed config values fail closed to defaults
  (disabled); a params value that is not a 3-sequence of numbers is left
  untouched, never coerced; no exception may escape the injection (mirror the
  F4 `try/except → return decision` shape at `:1254-1257` ONLY around the
  final `replace`, not as a blanket).

### Task 1 - `led_models.py`: config fields on `F2Config`
Add to `F2Config` (after `pre_chorus_laser_beats`, `:133`), mirroring the
`impact_burndown` sub-block idiom:
```python
# AWR-177 drop white-share consumer: blend the drop cue's engine colors
# toward white by the drop's measured build intensity (D§5.2). ABSENT block
# or enabled False => feature fully off, decisions byte-identical to today.
drop_white_enabled: bool = False
drop_white_lo: float = 0.40        # white_share at/below this -> no blend (TUNE-LIVE)
drop_white_hi: float = 0.95        # white_share at/above this -> max_blend (TUNE-LIVE)
drop_white_max_blend: float = 0.85 # blend fraction ceiling, 0..1 (TUNE-LIVE)
```
In `from_dict` (`:135-165`), parse `src.get("drop_white")` exactly like the
`impact_burndown` dict (`:154-155`): missing/non-dict ⇒ defaults. Coerce with
`_f2_num`; then validate fail-closed: if not
`0.0 <= lo < hi <= 1.0` or not `0.0 <= max_blend <= 1.0`, force
`drop_white_enabled = False` (never partially apply a broken block).

### Task 2 - `led_dispatch_policy.py`: the injection
1. Module-level pure helper (the test seam):
   ```python
   def _blend_rgb_toward_white(rgb, w):
       """(r,g,b) pulled toward (255,255,255) by fraction w. Non-3-sequence
       or non-numeric input is returned unchanged (never coerced)."""
   ```
   Pinned math: `tuple(int(round(min(255.0, c + (255.0 - c) * w))) for c in rgb)`
   after validating `rgb` is a length-3 sequence of int/float and clamping
   each channel into [0, 255] first. `w <= 0` returns the input as-is.
2. New method `_led_inject_f2_white_share(self, decision, *, role)`, called
   from the dispatch path on a new line immediately after `:1508`
   (`decision = self._led_inject_f2_white_share(decision, role=role)`):
   - `role != "drop"` → return `decision` unchanged.
   - Gates (all cheap attribute reads): `self._f2_enabled` false, or
     `self._f2_config` missing/`drop_white_enabled` false → unchanged.
   - `entry = self._led_f4_active_drop_entry()` (reuse — scripted stand-down
     and no-plan/no-anchor already inside); `entry is None` → unchanged.
   - `ws = float(getattr(entry, "white_share", 0.0))`;
     `w = max(0.0, min(1.0, (ws - lo) / (hi - lo))) * max_blend`;
     `w <= 0.0` → unchanged.
   - Blend ONLY the color params present among
     `("color", "color_a", "color_b", "color_from")` in `decision.params`
     via `_blend_rgb_toward_white`; anything else in params untouched.
   - Return `replace(decision, params={**decision.params, <blended keys>})`
     inside the same narrow `try/except Exception: return decision` shape as
     F4 `:1254-1257`.
   - One `log.debug` line with `ws`, `w`, and the look name (log-style rule:
     high-frequency diagnostics at DEBUG, never INFO).
3. Containment comment on the method, F4-style (`:1240-1244` wording):
   never touches look name, scene_ref, backend, routing, schedule, or
   darkness — only color params; off ⇒ byte-identical.

### Task 3 - `config/led_look_director.example.json`: example block (OFF)
Inside the existing `"f2"` object, add (directive: **example ships OFF** —
unlike f2/f4 themselves, this knob waits for the operator's live-tuning word):
```json
"drop_white": {
  "enabled": false,
  "lo": 0.4,
  "hi": 0.95,
  "max_blend": 0.85
}
```

### Task 4 - Tests
See Part D.

### Task 5 - Contract + docs bookkeeping
1. `docs/agents/change_contracts.yml`: `led_govee` already covers every file
   touched (`led_models.py`, `led_dispatch_policy.py`,
   `config/led_look_director.example.json` in `code_globs`; `F2Config` in
   `key_symbols`) — verify, and add `_led_inject_f2_white_share` is NOT
   needed in key_symbols (methods aren't listed there; confirm convention,
   don't invent). The example-config edit additionally triggers the
   `config_schema` contract.
2. Update every `docs_update` doc of BOTH contracts that the change makes
   stale — at minimum: `docs/subsystems/led_govee.md` (F2 consumer list),
   `docs/subsystems/config.md` + `docs/setup/configuration.md` (the new
   block), `docs/status/feature_status_matrix.md` (new row: implemented /
   software-tested / ships OFF / hardware-unvalidated).
3. `docs/status/active_work_registry.md`: flip the AWR-177 row per §10
   status language.

## Part C - Invariants That MUST Still Hold (live safety)

- **Mask precedence untouched:** blackout (emergency, manual, LED-blackout
  owners, smart-drop tactical), solo predark, and scripted stand-down all
  decide BEFORE the injection or zero frames downstream of it; a color-params
  blend can never re-light a masked moment. No new mask, no new owner.
- **Push-loop safe:** the injection is a plan-entry lookup
  (`for_drop` is a tiny linear scan over a track's drops,
  `lighting_moments_v2.py:773-780`) plus arithmetic on ≤ 4 tuples. No I/O, no
  allocation beyond the params dict copy the F4 injection already performs.
- **F2-off ⇒ structurally off:** with `f2.enabled` false no plan is ever
  built (`state_manager.py:277`), the entry lookup returns `None`, and the
  kill-test byte-identity of F2-off holds unchanged.
- **White-is-a-burst lock holds** (design :631): this whitens the drop-role
  cue only, for the drop moment only — no sustained white outside manual
  looks is introduced.
- **Full-scale law untouched:** blending toward white changes hue, not the
  dispatch's brightness/scale pipeline.
- **LED-only:** zero laser / SoundSwitch / OS2L behavior change.
- Secrets/live-config hygiene: only the EXAMPLE config is edited; the live
  `config/led_look_director.json` is operator-owned and not touched.

## Part D - Tests

Extend `tests/test_led_config.py` (config parsing) and add a focused
`tests/test_led_white_share_consumer.py` (or extend
`test_lighting_moments_v2_f4.py`'s policy-harness pattern — match its
fixture style, `:203-231`):

1. **Pure blend math:** `_blend_rgb_toward_white((0,0,0), 1.0) == (255,255,255)`;
   `w=0` identity; `w=0.5` midpoint; channel clamp on out-of-range input;
   non-sequence / wrong-length / non-numeric input returned unchanged.
2. **Off ⇒ byte-identity (the kill test):** flag false, block absent, `f2`
   absent, and `f2_enabled` false each yield a decision with `params`,
   `look`, `scene_ref`, `backend` all equal to the un-injected decision
   (mirror `test_f4_off_seasoning_is_identity`).
3. **On ⇒ only color params change** (mirror
   `test_seasoning_changes_only_params`): look/scene_ref/backend/schedule
   byte-identical; non-color params byte-identical.
4. **Mapping:** `ws <= lo` ⇒ unchanged; `ws >= hi` ⇒ exactly `max_blend`
   applied; monotone between (two interior points ordered).
5. **Scripted deck ⇒ unchanged** (the reused helper's stand-down proves out
   through this consumer).
6. **No plan / no anchor / no entry ⇒ unchanged.**
7. **Non-drop role ⇒ unchanged.**
8. **Config validation fail-closed:** `lo >= hi`, negative, `>1`, wrong types
   ⇒ `drop_white_enabled` False; absent block ⇒ defaults; the example config
   parses with `enabled` false (pin the example-OFF directive, mirroring
   `test_absent_or_empty_is_disabled` / `test_example_ships_enabled` shapes
   at `tests/test_lighting_moments_v2_f4.py:142-152` — here the pinned
   expectation is **example ships DISABLED**).
9. **Missing color params ⇒ no-op:** a decision whose params carry no color
   keys passes through unchanged even when enabled and `w > 0`.

## Part E - Acceptance (definition of done)

- [ ] All new tests green; `python3 -m unittest discover tests` shows ZERO
  new reds vs the named five-environmental-reds baseline (names in the
  AWR-174 registry row).
- [ ] Three hard checks green (`check_docs_metadata.py`,
  `check_agent_contracts.py`, `check_docs_drift.py`).
- [ ] Task 5 contract verification + all stale `docs_update` docs updated
  (anti-drift rule §7).
- [ ] Example config ships the block with `"enabled": false`; loader proven
  to return disabled defaults when the block is absent (test 8).
- [ ] Registry row AWR-177: implemented / software-tested / **ships OFF** /
  hardware-unvalidated.
- [ ] NOT in this round's scope: turning it on. Activation = operator edits
  the LIVE config during a tuning session (+ menubar restart + single-process
  check), tunes `lo/hi/max_blend` by ear, and rules. Until that word the
  live config carries no `drop_white` keys and behavior is byte-identical to
  today.

## When You Finish

Report: changed files; test/check output; explicit statement that the live
config was not touched and the feature ships OFF.

Plain-language operator summary to relay: "The lights already measure how hard
each build climbs into its drop — that number has been sitting unused. Now,
when you flip one switch in your live config, drops after big builds flash
whiter (the color of the drop look gets pulled toward white, more for monster
builds, not at all for calm ones). It ships switched OFF; nothing changes
until you turn it on at a tuning session, and blackouts/manual overrides always
win exactly as before."
