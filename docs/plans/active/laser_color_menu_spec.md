---
doc_status: active-spec
truth_level: implementation-spec, code-grounded
last_verified_commit: b16792a
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Implementation Spec - Laser color menus (follow-LED + chase combos + brightness floor)

Operator-designed with Claude 2026-07-07 (this chat). Brandon dictated the per-mood laser color
menus, the "laser must never be dimmer than the LEDs" rule, CH9=90, and "don't touch CH3/CH4 /
don't overcomplicate." Implementer is a Claude subagent (operator-authorized override of the usual
Codex-only rule, this scope only). **Do not touch CH3 or CH4 anywhere.**

## Part A - Context & Root Cause (verified; read, do not implement)

Today the laser color feature (`laser_color_engine.py` `LaserColorEngine._target()`) takes the
LED engine's `color_state()` and snaps its single RGB to the nearest of 6 fixed laser colors, writing
that one solid CH8 per mood. Two limits Brandon wants gone:

1. **[confirmed]** The RGB the laser reads is the palette **center** (`led_color_engine.py`
   `color_state()` ~:918-938 returns `_p_to_rgb(self._anchor_p, ...)`; `_anchor_p` is set to the
   palette center by `_apply_palette_now()` ~:1405-1408 and only slides between centers during a
   palette-change fade `advance_fade()` ~:901-916). The LEDs' actual per-section wander lives in a
   **separate** path (`resolve_color()` ~:591-701 rolls `p = cue_rng.uniform(focus_lo, focus_hi)`)
   that never writes `_anchor_p`. So the laser cannot see where the LEDs actually are — it holds one
   color per mood. Following the wander requires exposing the LEDs' actual last-emitted color as a
   **pure read**.
2. **[confirmed]** The mapping is quantize-to-one-solid. Brandon wants a small **menu** per mood
   (some solids, some two-color **chase** effects), the pick to **follow the LED color**, a hard
   **brightness floor** (laser never dimmer than the LEDs), and CH9 driven (chase speed) instead of
   passthrough.

Supporting confirmed facts:
- `_target()` (`laser_color_engine.py` ~:117-150) already receives `state` (the `color_state` dict,
  which includes `state["palette"]` — the mood name, e.g. `"blue_cyan"` for v1 and `"v2:GLACIER"`
  for v2 zones, confirmed in `color_state()` v2 branch ~:919-931) plus `white_moment`, `drop_phase`,
  `post_drop_progress`. **The menu keys off `state["palette"]` — no new plumbing to reach it.**
- `fixed_ch9` already threads through `_settled_ch9()` (~:151-158) and the merge seam only overwrites
  CH8=`frame[7]` / CH9=`frame[8]` (`soundswitch_laser_player.py` `_merge_color_snapshot` ~:124);
  a `None` snapshot leaves authored bytes = **fail-open**. So CH9=90 is a pure config value.
- `_nearest_fixed_color()` (~:182-187) uses `FIXED_COLOR_RGB` where `purple`=(255,0,255) (magenta,
  camera-calibrated). Keep that table as-is; menus reference color **names**, values live in config.
- `LaserColorMap.from_dict()` (~:52-79) is where new config fields (`menus`, `fixed_ch9`, brightness
  overrides) get parsed. `enabled/fixed/effects/settle/white_templates` already parsed there.
- `_update_laser_color_from_led()` / `_sync_laser_color_if_needed()` (`state_manager.py`
  ~:3103-3161) re-run `_target()` when the `color_state` signature changes; the signature is
  `(rgb, palette, white_sand_active, rainbow_active)`. **Add the new live-color field to that
  signature** so the laser re-syncs when the LEDs wander (Task 4).

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- **Never read or write CH3 or CH4.** Not in config, not in code, not in the merge seam. The chase
  effects are captured at CH3=0/CH4=10 but we deliberately leave those channels to the authored pack;
  some chase CH8 values may therefore render differently live — that is an accepted operator eyeball
  risk, NOT something to "fix" by driving CH3/CH4.
- Out of scope, do not touch: `soundswitch_laser_player.py` merge logic, the OS2L/DMX path, the LED
  dispatch/render, laser director/executor, any v2 dressing math beyond the one stash in Task 3.
- Behavior that must NOT change: fail-open (any None/invalid/disabled → authored CH8/CH9 pass
  through), `color_state()` purity (no RNG advance, no journey/focus mutation on read), the 200 Hz
  push loop (no blocking I/O added), white_moment/white_sand → white, rainbow → rainbow effect,
  post-drop CH9 ease-down via `settle.ease_beats`.
- Error handling: fail **closed to authored color** (return `None` from `_target()`), never a
  success-shaped guess. No broad `try/except` that swallows a real bug; the existing `try/except`
  in `update()` that maps exceptions → `None` snapshot (fail-open) is the only catch-all allowed.

### Task 1 — `config/laser_color_map.json`: add menus, set CH9, keep solids
Add a `menus` object keyed by mood name; set `fixed_ch9: 90`. Each menu entry is either a **string**
(a solid color name, CH8 from `fixed`) or an **object** `{"chase": <ch8>, "colors": [a, b]}` (a chase;
CH8 is the literal chase value, `colors` are the two color names used for matching + brightness).
Exact content (operator-dictated; every mood, not just v1):

```json
"fixed_ch9": 90,
"menus": {
  "blue_cyan":  ["blue", "cyan", {"chase": 172, "colors": ["blue", "cyan"]}],
  "deep_ocean": ["blue", "cyan", "green", {"chase": 172, "colors": ["blue", "cyan"]}],
  "indigo":     ["blue", "purple", {"chase": 164, "colors": ["blue", "purple"]}],
  "violet":     ["purple", "white", {"chase": 72, "colors": ["purple", "white"]}],
  "crimson":    ["red", "white", {"chase": 100, "colors": ["red", "white"]}],
  "v2:GLACIER":   ["blue", "cyan", "white", {"chase": 172, "colors": ["blue","cyan"]}, {"chase": 68, "colors": ["cyan","white"]}],
  "v2:DEEP_POOL": ["blue", "cyan", {"chase": 172, "colors": ["blue","cyan"]}, {"chase": 164, "colors": ["blue","purple"]}],
  "v2:TWILIGHT":  ["blue", "purple", {"chase": 164, "colors": ["blue","purple"]}],
  "v2:ION":       ["green", "cyan"],
  "v2:VOLT":      ["purple", {"chase": 68, "colors": ["cyan","white"]}],
  "v2:EMBERCORE": ["red", "white", {"chase": 100, "colors": ["red","white"]}],
  "v2:NEUTRAL":   ["blue", "cyan", {"chase": 172, "colors": ["blue","cyan"]}, {"chase": 68, "colors": ["cyan","white"]}]
}
```
Leave `fixed`, `effects.rainbow_family`, `settle`, `white_templates` unchanged. **No `rainbow` or
`white_sand` menu entry** — those moods hit the early `rainbow_active` / `white_sand_active` returns
in `_target` and never reach the menu pick (verified: `color_state()` sets `white_sand_active` true
whenever `_current_palette=="white_sand"`, and `rainbow_active` on mode-override). Menus only exist
for moods that actually reach the pick.

### Task 2 — `laser_color_engine.py`: parse menus, add brightness, rewrite `_target()` pick
1. **Config parse** in `LaserColorMap.from_dict()`: add field `menus: Mapping[str, tuple] | None`.
   Parse each mood's list into a tuple of normalized entries: a str → `("solid", name)`; a dict with
   int `chase` and a `colors` list of **1 or 2** names → `("chase", ch8, tuple(names))`. Drop
   malformed entries silently (a menu that ends up empty → treat mood as "no menu" = legacy
   behavior). Keep the dataclass frozen (store as nested tuples, not lists).
2. **Brightness rank** — module-level constant, hardcoded (ponytail: simple 3-level lookup, not
   luminance math; `# ponytail: 3-tier rank, per-fixture luminance if it ever looks wrong`):
   `_BRIGHTNESS = {"white": 3, "cyan": 2, "green": 2, "yellow": 2, "blue": 1, "purple": 1, "red": 1}`.
   - `_entry_brightness(entry)`: solid → `_BRIGHTNESS.get(name, 1)`; chase →
     `max(_BRIGHTNESS.get(c, 2) for c in entry_colors)` (unknown name like `rainbow` → 2).
   - `_led_brightness(live_rgb, state, white_moment)` — **takes the already-resolved `live_rgb`**
     (never re-reads `state` blindly; a None/invalid rgb would throw in `_nearest_fixed_color` and
     silently kill the feature via the outer try/except): if `white_moment or
     state.get("white_sand_active")` → 3; else `_BRIGHTNESS.get(_nearest_fixed_color(live_rgb), 1)`.
     Note: in practice at the menu-pick point `white_moment`/`white_sand_active` are already false
     (they early-return to white above), so the floor here only ever distinguishes rank 1 vs rank 2
     — e.g. it filters `blue` (1) when the LEDs sit at `cyan` (2). The "laser goes white when the
     LEDs go white" behavior is delivered by the **early white return**, not this floor. Do not claim
     otherwise in the oracle doc.
3. **Rewrite `_target()`** — keep the current early paths, insert the menu pick before the legacy
   single-solid path. Exact order:
   - `if not self._map.enabled: return None`  *(unchanged)*
   - `if white_moment or state.get("white_sand_active"):` → white solid `(fixed["white"], None)` *(unchanged)*
   - `if state.get("rainbow_active"):` → rainbow effect path *(unchanged; rainbow is driven by
     `effects.rainbow_family`, preserving today's behavior — there is no rainbow menu entry)*
   - `live = state.get("live_rgb")` if `_valid_rgb(state.get("live_rgb"))` else `state.get("rgb")`.
     If `not _valid_rgb(live): return None`. *(`state` is a dict — always use `.get()`, never attribute access.)*
   - `menu = (self._map.menus or {}).get(state.get("palette"))` (menus None or key missing →
     **legacy**: fall through to the existing `_nearest_fixed_color(live)` single-solid return,
     unchanged, so any mood without a menu keeps working).
   - `led_color = _nearest_fixed_color(live)`; `led_b = _led_brightness(live, state, white_moment)`.
   - `eligible = [e for e in menu if _entry_brightness(e) >= led_b]`. If empty →
     `eligible = [max(menu, key=_entry_brightness)]` (**never go dark; brightest allowed**).
   - `is_drop = drop_phase == "drop"`.
   - **Pick:** if `is_drop`: prefer the first eligible chase whose `colors` contain `led_color`, else
     the first eligible chase, else the eligible solid matching `led_color`, else brightest eligible.
     if not drop: prefer the eligible solid whose name == `led_color`, else brightest eligible solid,
     else (only solids filtered out) the brightest eligible chase.
   - Resolve CH8: solid → `fixed.get(name)`; chase → its ch8. If CH8 is None → `return None` (fail-open).
   - CH9: `None if fixed_ch9 is None else self._settled_ch9(fixed_ch9, drop_phase, post_drop_progress)`.
   - `return (ch8, ch9)`.

   The pick is deliberately deterministic (no RNG) and reuses the brightness floor to give Brandon's
   "some drops solid" for free: on a bright (white-ish) drop the mood's dim chase (e.g. blue+cyan) is
   filtered out and the drop stays on a bright solid/chase; on a darker drop the chase fires.

### Task 3 — `led_color_engine.py`: stash the LEDs' actual last-emitted color (pure read)
Add `self._last_emitted_rgb: tuple[int,int,int] | None = None` in `__init__`. Stash it on **every
color-returning path** of the resolvers, so it works in BOTH engines:
- `resolve_color()` main paths: `fixed_rgb` (~:641), `rainbow` (~:649), and the main focus-window
  path (~:701) — right before each `return` that carries a `"color"`, set
  `self._last_emitted_rgb = tuple(int(v) for v in <the color being returned>)`.
- **`_v2_resolve_color()` (the ACTIVE engine — F2):** do the same on its color-returning paths
  (manual / palate-reset / base-pick). `resolve_color` delegates to `_v2_resolve_color` at ~:612-620
  and returns before reaching the main paths, so without this the whole feature is a **no-op in v2**.
- Do **not** stash on the `{}` early-returns (disabled/exempt/wrong-source).
- **Clear on engine switch:** wherever `_v2_active` flips (v1↔v2), set `self._last_emitted_rgb = None`
  so a stale v1 color can't leak into a fresh v2 zone (or vice-versa). Grep the `_v2_active`
  assignment site(s) and null it there.

In `color_state()`, add one key to **both** the v2 and non-v2 return dicts:
`"live_rgb": self._last_emitted_rgb or <the rgb already in that dict>`. This is a **pure read** —
`color_state()` still advances no RNG and mutates no journey/focus state; the write happens only
inside the resolvers, which already mutate `_prev_color`. Last-writer-wins across roles is accepted
(ponytail: one field, dominant-role refinement later if the laser looks noisy).

**Scoped OUT (F5):** `resolve_slot_colors` / `_v2_resolve_slot_colors` do NOT stash. Slot looks are
rarer and multi-colored; the laser follows the most recent `resolve_color` emission for those
sections. This is a deliberate simplification, not an oversight — do not add slot stashing.

### Task 4 — `state_manager.py`: include live_rgb (QUANTIZED) in the laser re-sync signature
In `_sync_laser_color_if_needed()` (the `sig` tuple, ~:3143-3148) add one element derived from
`color_state.get("live_rgb")`. **Quantize it, do not use the raw RGB** — F4: `_last_emitted_rgb` is
last-writer-wins across roles and can differ every 200 Hz tick, so a raw-RGB signature element would
flap the sig every tick and force a `_target` + `color_state()` recompute per tick (this repo has a
CPU-starvation history). Instead add `_nearest_fixed_color(live_rgb)` (the laser only cares about
which of the 6 buckets it lands in), guarded: `_nearest_fixed_color(tuple(live)) if live is a
list/tuple of 3 ints else None`. That changes only when the laser-relevant color would actually
change — cue cadence, not tick cadence. Do not change the surrounding flow.

## Part C - Invariants That MUST Still Hold (live safety)
- **Fail-open:** disabled map, missing menu, None/invalid RGB, None CH8, or any exception → `_target`
  returns `None` → merge seam passes authored CH8/CH9. Never emit a guessed color, never blank the laser.
- **`color_state()` stays pure:** no RNG advance, no `_focus_*`/`_anchor_p`/journey mutation on read.
- **200 Hz push loop:** pick is pure in-memory dict/list work; no I/O, no locks, no allocation storms.
- **CH3/CH4 untouched** everywhere.
- **White + rainbow + post-drop settle** behave exactly as today (their branches are unchanged).
- **Static override / blackout / emergency** still win downstream — this feature only sets CH8/CH9 on
  the injected snapshot and never overrides those masks (they live past the merge seam).

## Part D - Tests — `tests/test_laser_color_engine.py` (extend)
Pure-function seam (no files, no subprocess): build a `LaserColorMap.from_dict({...})` with a small
menu and drive `LaserColorEngine._target()` / `update()` directly with hand-built `state` dicts.
Required cases (assert exact CH8/CH9):
1. Non-drop, `live_rgb` near cyan in `blue_cyan` → **cyan solid** (CH8=fixed cyan), CH9=90.
2. Non-drop, `live_rgb` near blue → **blue solid**.
3. Drop (`drop_phase="drop"`), dark `live_rgb` in `blue_cyan` → **chase 172**, CH9=90.
4. **White early-return (not the menu floor):** `white_moment=True` in `blue_cyan` → `fixed["white"]`
   (=6), CH9=None, via the early path — the menu/chase/floor are never reached. (This is what
   delivers "LEDs white → laser white"; assert it explicitly so the story is honest.)
5. **Brightness floor proper (rank 1 filtered):** non-drop, `state["palette"]="violet"`, `live_rgb`
   near cyan (rank 2) → the `purple` solid (rank 1) is filtered out; result is a rank-2 option,
   **never `purple`**. (Confirms the floor removes dimmer-than-LED options within the menu.)
6. `fixed_ch9=None` → CH9 passthrough (None) on solids; `fixed_ch9=90` + post_drop progress=1.0 →
   CH9 eased toward 0 (settle unchanged).
7. **Fail-open:** menu missing for palette → legacy nearest-fixed solid; invalid live_rgb → `None`;
   disabled map → `None`.
8. `color_state()` **purity:** call it twice after a `resolve_color()`; `_focus_fc`, `_anchor_p`,
   and any RNG-derived state are byte-identical across the two reads; `live_rgb` reflects the last
   emitted color.
9. v2 solid: `state["palette"]="v2:ION"`, `live_rgb` near green → **green solid** (ION has no chase).
10. **v2 follow actually works (F2):** drive `_v2_resolve_color()` so it emits a color, then
    `color_state()["live_rgb"]` reflects that emitted color (not the dressing center); and after an
    engine switch the stale color is cleared (`live_rgb` falls back to the current dict rgb).

## Part E - Acceptance (definition of done)
- [ ] All Part D tests pass; full suite `python3 -m unittest discover tests` has no **new** failures
  (pre-existing reds noted in the run, not introduced here).
- [ ] Contract: read `docs/agents/change_contracts.yml` key `laser` and update **every** doc it lists
  under `docs_update` — the full list is 10 docs, not 3: `docs/subsystems/laser.md`,
  `docs/status/feature_status_matrix.md`, `docs/status/support_matrix.md`,
  `docs/status/validation_matrix.md`, `docs/validation/hardware_validation_log.md`,
  `docs/agents/task_playbooks/change_laser_behavior.md`, `docs/architecture/laser_blackout_authority.md`,
  `docs/architecture/laser_color_authority.md`, `docs/plans/active/laser_color_engine_design_spec.md`,
  `docs/status/active_work_registry.md`. For the status/validation matrices, add/adjust the laser-color
  row to `software-tested / hardware-unvalidated` (chase values await live eyeball). Do not leave any
  of the 10 stale, or `check_docs_drift`/staleness will trip (AGENTS.md §7).
- [ ] `docs/architecture/laser_color_authority.md` updated — it is the acceptance oracle; note color
  is now menu-picked (follow-LED + brightness floor + drop-fires-chase) rather than single-center-solid,
  and that "LEDs white → laser white" is the early white path, not the menu floor.
- [ ] Hard checks pass: `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
  `python3 tools/check_docs_drift.py`.
- [ ] `rg -n "CH3|CH4|ch3|ch4|frame\[2\]|frame\[3\]"` shows this change added **no** CH3/CH4 handling.
- [ ] Grep proof of fail-open: every new `_target` exit that can't resolve returns `None`.

## When You Finish — report back
- Changed files; tests/checks run with pass/fail counts; the exact CH8/CH9 the tests assert per mood.
- Plain-language operator summary for Brandon: what the laser now does per mood live, what's unchanged
  (white/rainbow/fail-open/blackout), that CH3/CH4 were not touched, that chase values (172/68/100/
  164/72/188) still need his live eyeball because CH3/CH4 stay authored, and that it takes effect on
  the next bridge restart (menubar launch, verify exactly one process).

## Adversarial self-review (author, pre-handoff)
- **"The chase never fires because nearest-fixed always lands on a solid."** Prevented: chase firing
  is gated on `is_drop`, not on the color landing between two solids. Non-drops track the solid;
  drops fire the eligible chase. Verified by test 3 vs tests 1-2.
- **"Brightness floor blanks the laser when everything is filtered."** Prevented: empty `eligible`
  falls back to the brightest menu entry (never None from the filter); only an unresolved CH8 (config
  hole) returns None, which is fail-open, not a blank guess. Test 5 + test 7.
- **[folded from red-team F1] "The floor delivers LEDs-white→laser-white."** It does NOT — white
  early-returns before the menu, so the floor only sorts rank 1 vs rank 2. Story corrected in Task 2
  and the oracle doc; tests split into 4 (early white path) + 5 (rank-1 filtered).
- **[folded from red-team F2] "Feature is a no-op in the active v2 engine."** Prevented: Task 3 now
  stashes in `_v2_resolve_color` too and clears `_last_emitted_rgb` on engine switch. Test 10.
- **[folded from red-team F4] "live_rgb flaps the sync signature every 200 Hz tick."** Prevented:
  Task 4 puts the **quantized** `_nearest_fixed_color(live_rgb)` in the signature, not raw RGB, so it
  changes at cue cadence. No per-tick recompute.
- **[folded from red-team U1] "_led_brightness re-reads state and throws on None → silent death."**
  Prevented: it takes the already-resolved `live` rgb as its first arg.
- **"Stashing live color breaks color_state purity."** Prevented: the write is in `resolve_color()`
  (already impure/mutating), the read in `color_state()` only reads the field. Test 7 asserts no
  focus/anchor/RNG drift across reads.
- **"Adding live_rgb to the sync signature spams re-syncs at 200 Hz."** Bounded: `_sync` only fires
  on signature *change*, and `live_rgb` changes at LED-cue cadence (per section/step), not per tick;
  `_target` is pure and cheap. No I/O added. If live-noisy, the fix is dominant-role stash (Task 3
  note), not reverting the signature.
- **"v2 palette key mismatch."** `color_state()` emits `"v2:<ZONE>"`; menus use the same literal
  keys; a missing key = legacy nearest-fixed, still safe.
