---
doc_status: active-plan
truth_level: code-grounded
last_verified_commit: d47d155
last_verified_date: 2026-06-22
validation_scope: spec only; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — Laser drop/post-drop/chorus lifecycle (mirror the LED engine, gated)

> **Live-critical / default-ON.** This ships **on by default** on every set (operator decision:
> "default on always"). It is therefore NOT behind an opt-out-only flag — it has a **runtime
> kill switch that defaults ON** so the show can disable it instantly if hardware misbehaves.
> Implement exactly, commit after each task. The goal: the **laser** drop/post-drop/chorus
> behavior **mirrors the LED engine's existing, battle-tested, GATED state machine**, with the
> operator's configurable values, and **fixes a current live bug** where the laser fires/cycles
> drop looks during buildup/groove.

## Operator intent (authoritative)
Mirror the LED engine for `drop` / `post_drop` / chorus on the **laser**:
- A drop look hits and holds for a configurable number of beats, **then** goes to `post_drop`,
  which **cycles within the chorus**.
- At most **N drop looks in a row** (LED uses 2), then settle into `post_drop`.
- The drop look only fires **when the LED engine would allow it** (phrase-context gated) — NOT on
  every `smart_drop_crossing`. This is the fix for the buildup/groove drop-leak (Part A3).
- If **no post_drop look is mapped/usable**, **default to (cycle) drop looks** — never go dark.
- Operator's laser values: **drop impact = 32 beats** (LED default 8), **post_drop cycle = 32
  beats**. **Everything configurable.**
- The drop autoloop arm and the laser look are the **same MIDI note** to SoundSwitch.
- **Default ON**, with a runtime kill switch (`drop_lifecycle_mirror`, default `true`).

## Note — SoundSwitch is being retired (native DMX / T7d incoming)
The lifecycle logic (gated resolver, cycling, fallback) is **renderer-agnostic** and carries
forward to native DMX. SS-specific surface is kept minimal: the backend↔frontend MIDI sync
checker (Task 5) is **transitional / optional**, not a hard merge gate, because the note→autoloop
mapping disappears with SS. Do not build new SS-coupled tooling beyond what Task 5 specifies.

## Part A — Context & root cause (verified; read, do not implement)

### A1. What the laser does today (the gap)
- [confirmed] Laser role is decided by `LaserDirector._decide` (`laser_director.py:293`):
  drop_crossing fires the drop **once** (`:433-445`), a fixed post-drop **hold**
  (`post_drop_hold_beats`) at `:448-477`, then it **falls through to groove**
  (`_decide_phrase_default`, `:538`). No drop-look cycling, no "N drops in a row", no
  chorus-driven post_drop cycling, no no-post_drop fallback. `drop`/`post_drop` are not refire
  roles (`laser_executor.py:181` `refire_roles=("phrase","buildup","breakdown")`).
- [confirmed] The executor rotates a bank only for `role=="phrase"` (`:388-394`); other auto
  roles hold the latched scene (`:396-399`). Rotation primitive: `_choose_bank_scene_locked`
  (`:401`) over `_bank_for_role` (`:435`); `drop_bank`/`post_drop_bank` exist
  (`laser_models.py:98-99`) and `drop`/`post_drop` are already in `_AUTO_ROLES`
  (`laser_executor.py:24`).

### A2. The LED engine to MIRROR (authoritative source-of-truth — verified)
Implemented in **`state_manager.py`** (not the LED director). Full role resolver, in LED order:
- [confirmed] Constants (`state_manager.py:132-139`): `LED_DEFAULT_DROP_IMPACT_BEATS = 8.0`,
  `LED_MAX_DROP_IMPACTS = 2`, `LED_DEFAULT_POST_DROP_CYCLE_BEATS = 32.0`,
  `_LED_DROP_IMPACT_PREDECESSORS = {"up","low","buildup","breakdown"}`.
- [confirmed] `_led_role_from_smart_phrasing` (`:2222-2259`) order: **(0)** clear lifecycle if
  `_led_drop_lifecycle_should_clear` (`:2305`); **(1)** drop anchor → drop/post_drop; **(2)**
  breakdown; **(3)** pre_drop (`transition_window_active`); **(4)** buildup; **(5)** chorus/
  post_drop window → drop while `abs_beat < _led_drop_impact_until_beat` else post_drop; **(6)**
  low → breakdown; **(7)** groove.
- [confirmed] **Drop anchor + GATE** (`_led_drop_marker_anchor` `:2273-2281`,
  `_led_drop_impact_allowed` `:2283-2303`): anchor exists on a **chorus phrase-start crossing**
  (`current_phrase_is_chorus and phrase_start_crossing`, anchor=`current_phrase_start_beat`) **or**
  a `smart_drop_crossing` (anchor=`active_drop_beat` or abs_beat). The impact is **allowed only
  when** `previous_phrase_label ∈ {up,low,buildup,breakdown}`, OR (smart_drop_crossing and
  `current_phrase_label ∈` that set), OR a chorus→chorus impact while
  `_led_first_drop_anchor_beat is not None and _led_drop_impact_count < LED_MAX_DROP_IMPACTS`.
  If anchor present but impact NOT allowed → **post_drop** (not drop).
- [confirmed] **Lifecycle state** (3 pieces, all needed for parity): `_led_first_drop_anchor_beat`
  (`:2299,2310,2313`), `_led_drop_impact_until_beat` (`:2315`), `_led_drop_impact_count`
  (`:2318`). `_led_arm_drop_lifecycle` (`:2312`): `impact_until = anchor + 8.0`,
  `impact_count += 1`. Cleared by `_clear_led_drop_lifecycle` (`:2348`).
- [confirmed] **Post-drop cycling**: cycle index = `elapsed // post_drop_cycle_beats` measured
  from the anchor (`:2466-2468`); the changing index rotates the look. NOTE the LED cadence is
  abs-beat-anchored, NOT autoloop-tick-anchored — see A4/Task 4 for the laser cadence decision.
- [confirmed] **Per-look duration** (`_led_note_drop_decision_accepted` `:2321-2346`): LED arms
  with the flat 8.0 first, then **later** rewrites `impact_until = anchor + drop_duration_beats(look)`
  using the **actually-accepted** look. The laser has no executor→director acceptance feedback, so
  per-look duration is **out of scope** (Task 2/flat-only); see A4.

### A3. ROOT CAUSE of the live bug (verified) — laser drop role is UNGATED
The operator reports: *"Sometimes I catch SoundSwitch cycling drop looks while I am in a buildup
or a regular groove role,"* especially after a transition. Verified findings:
- [confirmed] **Refire is healthy.** `_select_scene`→`_bank_for_role` (`laser_executor.py:435-452`)
  is bank-correct: a `phrase`(groove)/`breakdown`/`buildup` refire rotates ONLY that role's bank;
  it **cannot** emit a `drop_bank` note. Refire timing resets on transition:
  `_clear_smart_rearm_state` sets `midi_refire_origin_beat=-1` (`state_manager.py:4222`) and is
  called on master change (`:2590`), track load (`:2618`), stop (`:4173`); the executor's
  `reset_runtime_state` reshuffles phrase bank + clears active scenes on master change (`:2596`)
  / track load (`:2624`). **So the symptom is NOT a refire-bank bug.**
- [confirmed] **The drop ROLE is ungated.** `_decide` priority 9 (`:433-445`) emits `role="drop"`
  on **any** `sp.smart_drop_crossing`, with **no** phrase-label/predecessor gate — unlike the LED
  engine, which gates the identical event via `_led_drop_impact_allowed`. A `smart_drop_crossing`
  the LED engine would suppress (predecessor not up/low/buildup/breakdown) makes the laser fire a
  drop look mid-groove/buildup.
- [confirmed] **`drop_hold` outranks `buildup`.** Priority 10 `drop_hold` (`:448-477`) is checked
  BEFORE priority 11 `buildup` (`:486-513`), with no phrase gate. With the operator's **32-beat**
  hold, the director keeps returning `role="drop"` for 32 beats after an anchor; a buildup/groove
  inside that window is masked, and each re-entry to `drop` (e.g. after a breakdown blip) rotates
  `drop_bank` → **cycling drop looks** during perceived buildup/groove. This matches the report.
- [confirmed] **The fix is the mirror itself, done with the LED gate.** Routing the laser drop
  decision through the gated lifecycle (only fire/hold drop when the LED engine would) removes the
  ungated/over-ranked drop. This spec MUST preserve that gate; an ungated mirror would not fix the
  bug. (This is why the old "extract resolver but keep priority-9 ungated" draft was rejected.)
- [unknown] Which mechanism fires on any *specific* sighting (spurious `smart_drop_crossing`
  detection vs. 32-beat hold masking buildup) — needs one `/tmp/bridge.log` sample
  (`grep -E "drop_crossing|drop_hold|\[LX\] fired  role=drop|midi-refire"`). The gated mirror
  fixes BOTH mechanisms, so impl does not block on this; Part D adds a regression test for both.

### A4. Smart Drop blackout coupling — MUST be preserved (verified; the trap that killed v1)
- [confirmed] The executor keys its Smart Drop blackout resolution AND the at-anchor immediate
  fire on `is_drop_crossing = (decision.reason == "drop_crossing")` (`laser_executor.py:109`, used
  at `:127,135,158,168,177,206,219,240,244`). If the mirror REPLACED `drop_crossing` with a new
  reason, `_resolve_pending_blackout(reason="drop_crossing_success")` (`:244`) would never run and
  the armed blackout would not clear at the drop. In `blackout_mask` mode `autoloop_tick_just_fired`
  is **deliberately false at the crossing** (`state_manager.py:3718`), so any cycle-gated fire
  would also miss the drop. **Therefore: the at-anchor impact MUST keep emitting `reason="drop_crossing"`,
  role="drop", unchanged.** Cycling is purely ADDITIVE on sustained ticks (new reasons
  `drop_cycle`/`post_drop_cycle`). The executor's blackout path is left untouched.

### A5. Field availability + cadence (verified)
- [confirmed] `LaserContext.smart_phrasing` (`laser_models.py:143`) is built with the SAME
  `sp_state` the mutating LED resolver consumes that tick (`state_manager.py:3824` vs `:1741`).
  `SmartPhrasingState` (`smart_phrasing.py:43-69`) has every field the LED resolver/anchor/gate
  use: `abs_beat, current_phrase_label, current_phrase_start_beat, phrase_start_crossing,
  previous_phrase_label, current_phrase_is_chorus, current_phrase_is_low, beats_into_phrase,
  active_drop_beat, smart_drop_crossing, smart_post_drop_active, beats_to_next_drop,
  transition_window_active`. No missing field.
- [confirmed] **Cadence source.** `autoloop_tick_just_fired` is set by markers/anchors/arm plus a
  32-beat interval reset on each marker (`state_manager.py:3719-3787`, `AUTOLOOP_ARM_PHRASE_BEATS`).
  There is **no** general per-feature cycle timer. The laser cycle cadence therefore uses
  `autoloop_tick_just_fired` (Task 4) — there is **no separate `drop_cycle_beats` knob** (it would
  be fake config that the code ignores). `post_drop_cycle_beats` is honored only as the LED-style
  cadence *intent*; the laser actually rotates on autoloop ticks (documented divergence, Task 4).

### A6. Config reality (verified — the fallback trap)
- [confirmed] `config/laser_director.json`: `house_drop_1` is **`scene_type=static`** (note 96) and
  is the **first** entry of `house.drop_bank` AND the **only** entry of `dubstep.drop_bank` and
  `dubstep.post_drop_bank`. `house_drop_2/3` are `safety_class=high_impact`. `house.post_drop_bank=[]`.
  ⇒ `dubstep.post_drop_bank` is **non-empty but contains zero cyclable scenes**. A
  "`post_drop_bank` non-empty" fallback test is therefore WRONG (dubstep would go dark). The
  fallback predicate MUST be "has a usable cyclable scene" (Task 3/Task 4).

### A7. ROOT CAUSE of the second live bug (verified) — drop cycling is NOT random
The operator reports: *"It pretty much just starts at house_drop_12, then every drop for that track
is house_drop_12, and when I transition to another track every drop becomes house_drop_13."*
Verified — it is a **persistent-cursor round-robin with a random START only**, not random cycling:
- [confirmed] `_seed_role_cursors` (`laser_executor.py:415-422`) sets the drop cursor to
  `rng.randrange(len(bank))` — a random *start index* — but **only at construction / personality
  change**.
- [confirmed] `_choose_bank_scene_locked` (`:401-413`) is a deterministic walk:
  `index = cursor % len(bank); cursor += 1`. Sequential (12, 13, 14…), not random.
- [confirmed] The cursor **persists across tracks/decks**: `reset_runtime_state` is called on track
  load (`state_manager.py:2624`) and master change (`:2596`) with `reset_cursors=False`, and only
  reshuffles the *phrase* bank (`laser_executor.py:90-93`), never drop/post_drop. Cursors reseed
  ONLY on personality change (`:72`).
- [confirmed] Today there is ~one drop episode per track (drop is not yet a per-cycle role), so the
  drop cursor advances **once per track** → same look all track, +1 next track. Exactly the report.
- [confirmed] **The LEDs already shuffle-bag drop/post_drop.** `LEDLookDirector` is built with
  `shuffled_roles=LED_AUTOMATION_ROLE_ORDER` (`__main__.py:582`), which includes `"drop"` and
  `"post_drop"` (`led_look_director.py:20-28`). The LED mechanism `_look_name_for_role`
  (`:330-356`) is a shuffle-bag with **reshuffle-on-exhaustion**: a monotonic `cursor` (`:326`)
  walks a shuffled permutation of the role's looks and the bag is **reshuffled every time the
  cursor wraps a full bank length** (`cursor % len(look_names) == 0`). So all N looks play in a
  random order, then a fresh shuffle, repeat. (Note: it does NOT guard a same-look repeat exactly
  at the bag boundary — probability ~1/N; this is accepted LED behavior.)
- [decision] Operator wants the laser drops to **mirror the LEDs** (confirmed this session ⇒
  shuffle-bag). Task 4 therefore mirrors LED `_look_name_for_role` exactly — reshuffle on
  exhaustion, monotonic per-role cursor, per-role bag — NOT the laser phrase bank's weaker
  per-track-reset shuffle. It **replaces** the round-robin cursor for drop/post_drop only; the
  phrase bank is unchanged. The laser adds one thing the LED bag lacks: the bag is built from the
  **usable** entries only (autoloop + allowed), so non-cyclable entries never enter the rotation.
- [confirmed] **Authoring loop (operator-described, in-scope):** operator authors a new autoloop
  look in SoundSwitch, maps its note in the laser pad, saves the SS autoloop, exports to the
  bridge — which lands the scene in `scenes` (with a note) and the personality `drop_bank`. The
  shuffle-bag is rebuilt from the current bank each pass/reset, so a newly-exported drop look joins
  the cycle automatically on the next track (no curation). Task 5's checker catches a note mapped
  in the pad but not in SS (or vice-versa) during this loop.

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **Default ON** via kill switch `drop_lifecycle_mirror` (default `true`). When **off**, laser
  output is **byte-for-byte identical to today** (existing suite proves it). When **on** (default),
  behavior changes deliberately and safely per A3 (gated) + A4 (blackout preserved).
- **Do not** change LED runtime behavior. Task 1 extracts a pure resolver; the live LED path keeps
  its own code (parity-proven, not refactored — avoids LED regression).
- **Do not** modify the operator's `personalities` / `drop_bank` / `post_drop_bank` / `scenes` /
  `_pad_meta`. Runtime handles banks **as they are**; never auto-curate, reorder, or repopulate.
- **Do not** modify `smart_phrasing.py`, `autoloop_controller.py`, `smart_rearm.py`, the push
  loop's threading, the executor's **blackout** code paths (A4), SoundSwitch pack code, or Govee.
- Follow AGENTS.md §7: this is the `laser` (and touches `led_govee`) change-contract — update the
  docs those contracts list and run §8 hard checks.

### Task 1 — Extract a SHARED pure drop-lifecycle resolver (parity-proven against LED)
Create `drop_lifecycle.py`: a pure, I/O-free resolver reproducing the LED drop/post_drop region
(`_led_drop_marker_anchor`, `_led_drop_impact_allowed`, `_led_arm_drop_lifecycle`,
`_led_drop_lifecycle_should_clear`, and the chorus drop→post_drop flip `:2248-2256`). It carries
the **complete** LED lifecycle state — **all three fields** — and is parameterized by config:
```
DropLifecycleConfig(
    max_drops_in_a_row: int,        # = LED_MAX_DROP_IMPACTS default 2
    drop_impact_beats: float,       # flat impact window (operator: 32.0; LED parity: 8.0)
    post_drop_cycle_beats: float,   # default 32.0 (cadence intent; see Task 4)
    impact_predecessors: frozenset, # = {"up","low","buildup","breakdown"}
)
DropLifecycle:
    state: first_drop_anchor_beat | None, impact_until_beat | None, impact_count: int
    drop_anchor(sp_like) -> float | None            # mirrors _led_drop_marker_anchor :2273
    impact_allowed(sp_like) -> bool                 # mirrors _led_drop_impact_allowed :2283
    should_clear(sp_like) -> bool                   # mirrors _led_drop_lifecycle_should_clear :2305
    arm(anchor_beat) -> None                        # mirrors _led_arm_drop_lifecycle :2312
    resolve_drop_role(sp_like, *, mutate) -> str    # "drop" | "post_drop" | "none"
    reset() -> None                                 # clears all three state fields
```
`resolve_drop_role` returns ONLY the drop-region decision: `"drop"`/`"post_drop"` when the LED
engine would be in the drop lifecycle (at an anchor, or inside chorus/post_drop), else `"none"`
(caller falls through to its own breakdown/buildup/phrase logic). It takes a small struct of the
A5 SmartPhrasing fields; it MUST NOT import bridge runtime modules. Refactoring the live LED path
to call this is **out of scope** (avoids LED regression); the parity test (Task D) proves equality.

### Task 2 — `laser_models.py` + `laser_config.py`: configurable knobs (default-on)
Add to `LaserPersonality` (near `drop_style`, `laser_models.py:~115`):
- `drop_lifecycle_mirror: bool = True`   (**kill switch, default ON**)
- `max_drops_in_a_row: int = 2`
- `drop_impact_beats: float = 32.0`      (operator value; flat — no per-look pairing this pass)
- `post_drop_cycle_beats: float = 32.0`
- **Do NOT add `drop_cycle_beats`** (A5: fake config; cadence is `autoloop_tick_just_fired`).
- **Do NOT add `drop_pairs`** this pass (A2/A4: the executor rotates the bank, so the director
  cannot know the fired scene; per-look duration would key off the wrong scene — out of scope).
Validate in `laser_config.py` (`_validate_personality`, mirror existing `:641-690`): `bool` for
the flag; `max_drops_in_a_row` positive int; `drop_impact_beats`/`post_drop_cycle_beats` positive
numbers. Unknown/missing → the defaults above (feature ON by default). Build in `_build_personality`
(`:830`). **Because default is ON, the config example + the live config already-loaded personalities
must be re-validated to load clean** (run the suite + a load smoke test).

### Task 3 — `laser_director.py`: gate the drop role + drive the mirrored lifecycle
Add `self._drop_lifecycle: Optional[DropLifecycle]` built in `set_personality_config` (`:180`) and
`__init__` from the new knobs; rebuild it on personality reload. Add
`reset_runtime_state(reason: str)` (see Task 3b). In `_decide`, when `drop_lifecycle_mirror` is ON:

3a. **Gate priority-9 `drop_crossing` (the A3 fix), keep its reason/blackout semantics (the A4
constraint).** Replace the bare `if sp.smart_drop_crossing:` trigger (`:434`) with the gated,
LED-faithful anchor+allow test:
```python
anchor = self._drop_lifecycle.drop_anchor(sp)          # chorus phrase-start OR smart_drop_crossing
if anchor is not None and self._drop_lifecycle.impact_allowed(sp):
    self._drop_lifecycle.arm(anchor)                   # sets impact_until, count += 1
    self._post_drop_start_abs_beat = abs_beat
    # reason STAYS "drop_crossing" → executor fires immediately + resolves blackout (A4, unchanged)
    return LaserSceneDecision(scene=self._drop_scene, reason="drop_crossing",
                              priority=9, source="policy", role="drop")
```
When `anchor is None` or impact not allowed → do **not** emit a drop; fall through. (This is what
kills the ungated/groove drop.) When the flag is **off**, the original `:434` path runs unchanged.

3b. **Replace priority-10 `drop_hold` + the chorus fall-through with resolver-driven cycling**
(`:448` through the `_decide_phrase_default` call at `:538`), flag-ON only:
```python
role = self._drop_lifecycle.resolve_drop_role(sp, mutate=True)
if role == "drop":          # sustained inside impact window
    return LaserSceneDecision(scene=self._drop_scene, reason="drop_cycle",
                              priority=10, role="drop", source="policy")
if role == "post_drop":
    if self._has_usable_cyclable_post_drop():    # A6 fallback predicate (Task 3c)
        return LaserSceneDecision(scene=self._post_drop_scene or self._drop_scene,
                                  reason="post_drop_cycle", priority=10, role="post_drop",
                                  source="policy")
    # no usable post_drop look → cycle drops (never go dark)
    return LaserSceneDecision(scene=self._drop_scene, reason="drop_cycle",
                              priority=10, role="drop", source="policy")
# role == "none" → existing buildup-window / phrase-default logic, unchanged
```
Breakdown stays at priority 8 (ahead of the lifecycle) — **intentional, documented divergence**
from LED order; it is strictly safer (no drop during an active breakdown) and matches today's
laser behavior. `pre_drop`/`low` are not laser roles and remain routed to the existing
buildup/phrase logic (documented; pre_drop_scene stays inert per `laser_config.py:632`).

3c. **`_has_usable_cyclable_post_drop()`**: true iff `post_drop_bank` (or `post_drop_scene`)
contains ≥1 scene that is `scene_type=="autoloop"` and not (high_impact while
`allow_high_impact` is false). The director needs read access to `config.scenes` + the personality;
inject the scene catalog at construction (the executor already holds it). Mirror this exact
predicate in Task 4's executor skip.

3d. **`reset_runtime_state(reason)`** on `LaserDirector`: clears `_drop_lifecycle.reset()` AND the
existing `_reset_smart_observation_state()` fields (`_post_drop_start_abs_beat`,
`_last_smart_abs_beat`, etc.). Wire it in `state_manager.py` at EVERY site that today clears LED
lifecycle / resets the executor: `_on_master_changed` (`:2589/2596`), `_on_track_loaded`
(`:2617/2624`), `_do_full_stop` (`:4172/4180`), `_do_resume` (`:4203` — today resets NEITHER
director nor executor; add both), scripted/idle `_apply_lighting` (`:3154`, `:3181`), and after
personality apply (`:2744-2746`). This closes the B3 leak that compounds the A3 symptom.

### Task 4 — `laser_executor.py`: refire + rotate drop/post_drop on the autoloop cadence
1. Make `drop`/`post_drop` refire-eligible **only** for the new cycle reasons. Replace
   `refire_allowed` (`:182-189`) — note `drop_crossing` is NOT a cycle reason, so the A4 blackout
   path is untouched:
   ```python
   cycling = decision.reason in ("drop_cycle", "post_drop_cycle")
   refire_allowed = (
       ctx.autoloop_tick_just_fired
       and (role in refire_roles or (cycling and role in ("drop", "post_drop")))
       and scene_def.scene_type == "autoloop"
       and (last_role_trigger_beat < 0.0 or float(ctx.abs_beat) > last_role_trigger_beat)
   )
   ```
2. **Shuffle-bag selection for drop/post_drop — mirror LED `_look_name_for_role` (A7).** Replace
   the round-robin cursor for these two roles with a shuffle-bag, used for BOTH the at-anchor
   `drop_crossing` pick and the cycle ticks (so the fired note is random either way). Add executor
   state `self._role_bag: dict[str, tuple[str, ...]] = {}` and reuse `self._role_cursors` (monotonic).
   - **Usable filter (A6, replaces the old "advance past" logic):** define
     `_usable_bag_entries(role) = [s for s in _bank_for_role(role)
       if (sd := self._config.scenes.get(s)) and sd.scene_type == "autoloop"
       and not (sd.safety_class == "high_impact" and not allow_high_impact)]`.
     Non-cyclable entries never enter the bag, so they are never fired as a cycle.
   - **Pick (mirror LED `:330-356`):** in a new `_next_shuffled_scene_locked(role)`:
     ```python
     usable = self._usable_bag_entries(role)
     if not usable:
         self._role_active_scene[role] = ""
         return ""                                   # → Task-3 fallback / no-op (never dark-send)
     cursor = self._role_cursors.get(role, 0)
     bag = self._role_bag.get(role, ())
     if cursor % len(usable) == 0 or not bag or len(bag) != len(usable):
         shuffled = list(usable); self._rng.shuffle(shuffled)   # reshuffle on exhaustion / bank change
         bag = tuple(shuffled); self._role_bag[role] = bag
     scene = bag[cursor % len(bag)]
     self._role_cursors[role] = cursor + 1
     self._role_active_scene[role] = scene
     return scene
     ```
     The `len(bag) != len(usable)` guard rebuilds the bag when the operator exports a new/removed
     drop look (A7 authoring loop) so it joins the rotation without curation. This mirrors the LED
     reshuffle-on-exhaustion exactly (incl. the accepted ~1/N bag-boundary repeat — do NOT add a
     guard the LEDs don't have, to keep parity).
   - In `_select_scene` (`:375`), for `role in ("drop","post_drop")` with a cycling reason: fire
     only on `ctx.autoloop_tick_just_fired`, then `return self._next_shuffled_scene_locked(role)`.
     For the `drop_crossing` reason (flag-on), also route the drop pick through
     `_next_shuffled_scene_locked("drop")` so the at-anchor look is shuffled too. Leave the
     flag-off `drop_crossing`/`drop_hold` paths on the existing `_choose_bank_scene_locked`.
   - **Teardown:** clear `_role_bag` in `reset_runtime_state` alongside `_role_active_scene` so each
     track starts a fresh shuffle (B3 / Task 3d).
   The 32-beat cadence comes from `autoloop_tick_just_fired` (A5) — **no new timer**. (Documented
   divergence from LED's abs-beat-anchored post_drop cadence; acceptable and renderer-agnostic.)

### Task 5 — Keep the laser MIDI mapping consistent (TRANSITIONAL; SS retiring)
> Do not curate/reorder/repopulate banks. Task 5 is mapping **consistency**, not bank composition.
5a. **Validation** (`laser_config.py`, flag-aware): every scene referenced by
`drop_bank`/`post_drop_bank` exists in `scenes` with a MIDI note; no `(channel,note)` collision
across those banks. A bank with only non-cyclable entries or an empty `post_drop_bank` is **valid**
(→ runtime fallback) — at most an **info** log, never a load error. (Note: today `dubstep`'s banks
are static-only; this MUST NOT block load.)
5b. **`_pad_meta`**: only if Codex changes a scene's note (it should not) — update
`note_labels`/`banks` in the same commit. Otherwise leave as-is.
5c. **Sync checker `tools/check_laser_midi_sync.py`** (new, pure `reconcile(config_dict, ss_map)
-> list[issue]` + thin CLI, read-only, never mutates): report each drop/post_drop bank note →
scene (type/safety) → pad label → SS autoloop; exit non-zero ONLY on a genuine break (bank note
unmapped in SS, `(channel,note)` collision across banks, bank entry missing from `scenes`).
Non-cyclable entry = info. **Marked transitional/optional** (not a CI hard gate) because SS is
being retired; keep it small.
5d. **Operator step (doc, not code)**: in the bounded SS project confirm each drop/post_drop note
triggers the intended autoloop, re-export the pack. Operator-run, optional.

## Part C — Invariants that MUST still hold (live safety)
1. **Kill switch off = no change.** `drop_lifecycle_mirror=False` → identical laser output/MIDI to
   today (proven by existing suite). Default is ON.
2. **Smart Drop blackout UNTOUCHED (A4).** The at-anchor impact still emits `reason="drop_crossing"`;
   the executor's blackout arm/resolve code is not modified. Cycling reasons never enter the
   blackout path. Blackout note-on/off pair is byte-identical with the flag on (tested).
3. **Drop role is GATED (A3).** A drop look only fires/holds when the lifecycle's
   `impact_allowed` is true (LED parity). No drop look during buildup/groove from an ungated
   `smart_drop_crossing` or an over-ranked `drop_hold`.
4. **No arm spam.** Cycling MIDI fires **only** on `ctx.autoloop_tick_just_fired`.
5. **N-in-a-row honored.** ≤ `max_drops_in_a_row` consecutive impacts before `post_drop`, with the
   LED predecessor allowances (incl. the capped chorus→chorus path; requires `first_drop_anchor_beat`).
6. **No-post_drop fallback (A6).** A personality with no **usable cyclable** post_drop look cycles
   drops — never emits a post_drop with no usable look → no dark/no-op gap. ("Bank non-empty" is
   NOT the test.)
7. **Clean teardown (B3).** Director + executor + LED drop-lifecycle state reset on track/deck
   change, stop, **resume**, scripted, idle, and personality apply. `role_changed` clears the
   previous role's active scene. No leak across tracks/decks/transitions.
8. **No push-loop I/O.** Resolver is pure; decision logic only.
9. **Don't touch arm/BPM/refire plumbing.** `autoloop_controller` arm/sync/BPM-follow and the
   `midi_refire_origin_beat` logic are untouched (A3 confirmed they already reset correctly).
10. **LED unchanged.** Live LED path keeps current behavior; shared resolver proven equal (Task D).
11. **Banks never curated.** Operator personalities/banks unmodified; runtime skips non-cyclable
    entries and uses the fallback. A genuine mapping break is surfaced; a non-cyclable entry / empty
    `post_drop_bank` is valid.
12. **Random drop/post_drop selection (A7).** Drop/post_drop looks are picked by a shuffle-bag that
    mirrors the LED `_look_name_for_role` (reshuffle on exhaustion). No persistent round-robin
    cursor that yields the same look all track / +1 per track. The bag is built from usable entries
    only and rebuilt when bank membership changes; it resets per track on teardown.

## Part D — Tests (pure-function seam; no files/subprocess)
- `tests/test_drop_lifecycle.py` — the resolver, table-driven: drop held `drop_impact_beats` then
  post_drop; ≤`max_drops_in_a_row` then post_drop; predecessor up/low/buildup/breakdown → drop;
  **disallowed predecessor (groove/other) → NOT drop** (post_drop or none); chorus→chorus capped
  (exercises `first_drop_anchor_beat`); no usable post_drop → drop fallback; lifecycle clears when
  chorus/post-drop ends.
- **Parity test** — assert the resolver's role sequence equals the LED resolver
  (`_led_role_from_smart_phrasing`) for the **drop/post_drop region** across shared timelines with
  LED-equivalent config (max=2, impact=8, cycle=32). Timelines MUST include: chorus phrase-start
  anchor; smart_drop_crossing with allowed and **disallowed** predecessors; chorus→chorus cap;
  lifecycle clear on chorus end.
- **Blackout-preservation test (A4)** — `test_laser_executor*`: a `drop_crossing` decision still
  arms/resolves the blackout identically with the flag ON vs OFF, in `blackout_mask` AND
  `legacy_rearm` modes; the at-anchor drop fires on the crossing tick even though
  `autoloop_tick_just_fired` is False in blackout mode.
- **Regression test for the live bug (A3)** — `test_laser_director*`: feed a `smart_drop_crossing`
  with a groove/buildup predecessor (disallowed) → assert the director emits **no** `drop`/`drop_cycle`
  (no drop look in groove/buildup); and a long (32-beat) impact window does not mask a later buildup
  beyond the gate.
- **Cycling + shuffle-bag test (A7)** — `test_laser_executor*` with a seeded `rng`:
  `drop_cycle`/`post_drop_cycle` with `autoloop_tick_just_fired=True` fire MIDI each tick and select
  via the shuffle-bag — assert that over one full pass every **usable** entry appears exactly once
  (no repeat within a pass), the order is the seeded permutation, and the bag **reshuffles on
  exhaustion** (second pass order may differ). Assert static/high-impact-disallowed entries
  **never** appear. With `autoloop_tick_just_fired=False` → no MIDI. A static-only `post_drop_bank`
  (the `dubstep` case) → drop-cycle fallback, never dark. A bank-membership change (add/remove a
  scene) rebuilds the bag. Cross-track: assert the per-track pattern is NOT "same look all track,
  +1 next track" (the regression being fixed).
- **Teardown test (B3)** — master change with both decks playing, and pause→resume: assert
  director + executor lifecycle state cleared.
- **Integrated parity caveat** — the parity test covers the resolver; the
  director/executor tests above cover the integration. Do NOT accept resolver-only green as proof
  of live behavior.
- All existing laser + LED tests pass unchanged.

## Part E — Acceptance (definition of done)
- [ ] Shared `drop_lifecycle.py` with **all three** state fields; **parity test green** vs the LED
      resolver incl. disallowed-predecessor + chorus→chorus-cap timelines.
- [ ] Knobs added (`drop_lifecycle_mirror` **default true** + max/impact/cycle); **NO**
      `drop_cycle_beats`, **NO** `drop_pairs`. Kill switch OFF = byte-identical to today.
- [ ] Default ON: laser fires a **gated** drop (LED parity) → holds `drop_impact_beats` (32) →
      post_drop cycling every autoloop tick within chorus; ≤`max_drops_in_a_row` (2); no-usable-
      post_drop → cycle drops. **No drop look during groove/buildup** (A3 regression test green).
- [ ] **Drop/post_drop selection is shuffle-bag (A7), mirroring the LED** (`_look_name_for_role`):
      random order, reshuffle on exhaustion, usable-only, bag resets per track. The old "same look
      all track, +1 next track" round-robin is gone (regression test green).
- [ ] **Smart Drop blackout byte-identical** flag-on vs off in both modes (A4 test green).
- [ ] **Teardown**: director+executor reset on track/deck/stop/resume/scripted/idle/personality (B3).
- [ ] Banks untouched; runtime skips non-cyclable entries; `dubstep` static-only banks load clean
      and fall back (no dark). Sync checker (transitional) reports info, exits 0 on the live config.
- [ ] `python3 -m unittest discover tests` green; AGENTS.md §8 hard checks green; `laser`
      (+`led_govee`) change-contract docs updated. No push/tick-path I/O added.

## When you finish
- Commit per task with real messages. Report: files touched, parity-test result, the A4
  blackout-equivalence proof, the A3 regression result, the sync-checker output on the live config,
  and confirmation that kill-switch-OFF is a byte-for-byte no-op.

## Pre-handoff checklist status (Claude self-review before Codex)
1. Claims labeled confirmed/assumed/unknown — yes (A1–A6); the one unknown (which mechanism per
   sighting) is surfaced and does NOT block (gated mirror fixes both).
2. Verified against CURRENT code at `d47d155` — yes (every file:line re-read this pass).
3. Pending-state guard — A4 checks the blackout pending-state (`_blackout_pending_for_drop_window`)
   and the `drop_crossing` reason coupling, not just the new reasons against each other.
4. Mode-transition cleanup — Task 3d enumerates ALL transition paths incl. the resume path that
   today resets neither director nor executor.
5. Third-party API completeness — N/A (no new third-party API; MIDI message path unchanged).
6. Cross-checked against existing code — gate reuses `_drop_scene`/`drop_bank`/`autoloop_tick_just_fired`
   authority vars; predicate matches `scene_type`/`safety_class`/`allow_high_impact` as the executor uses them.
7. Pure-function seam — `drop_lifecycle.py` is pure and table-tested.
8. Live safety explicit — Part C; blackout preserved (A4); gate is strictly-safer than today.
9. Adversarial self-review — done: the v1 trap (replacing `drop_crossing` → blackout break, A4) and
   the fallback trap (`dubstep` static-only banks → dark, A6) are both closed; the parity-illusion
   (resolver-only green) is called out in Part D.
