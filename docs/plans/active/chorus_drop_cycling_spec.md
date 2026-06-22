---
doc_status: active-plan
truth_level: code-grounded
last_verified_commit: c4edf97
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
- [confirmed] **Per-look duration** (`_led_note_drop_decision_accepted` `:2321-2346`, called LIVE at
  `:1934` AFTER the mutating resolver at `:1741`): LED arms with the flat 8.0 first, then **later**
  rewrites `impact_until = anchor + drop_duration_beats(look)` (`:2344`) using the
  **actually-accepted** look. The laser has no executor→director acceptance feedback, so per-look
  duration is **out of scope** (Task 2/flat-only). **Parity consequence (read before trusting the
  parity test):** the resolver reproduces only the FLAT-armed LED window. The live LED window is
  look-duration; the laser window is the flat `drop_impact_beats` (operator 32). They are NOT equal
  in production. The Part D parity test therefore compares against `_led_role_from_smart_phrasing`
  **without** the `_led_note_drop_decision_accepted` rewrite — flat-vs-flat — and MUST say so;
  resolver-green is not live-LED-window parity.

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

### A4. Smart Drop blackout coupling — preserved for ALLOWED crossings; the real clear path is the SM net
- [confirmed] The executor keys its Smart Drop blackout resolution AND the at-anchor immediate
  fire on `is_drop_crossing = (decision.reason == "drop_crossing")` (`laser_executor.py:109`, used
  at `:127,135,158,168,177,206,219,240,244`; success resolve at `:244-245`).
- [confirmed] **The armed blackout does NOT depend on `drop_crossing` to clear (earlier draft was
  wrong).** There is an existing safety net: `state_manager.py:3842-3853` calls
  `clear_pending_blackout(reason="smart_drop_crossing_without_drop_decision")` on **every**
  `smart_drop_result.crossing` where the director did **not** emit a `drop_crossing` decision
  (`drop_crossing_decision_emitted` built at `:3836-3838`). And `smart_drop_result.crossing` is true
  **iff** a blackout was armed for this drop window (`smart_rearm.py:116-146` gates the crossing on
  `os.drop_cut_armed`, set when the blackout arms at `:187-193`). ⇒ Any crossing with a pending
  blackout is cleared by EITHER the executor's `drop_crossing_success` path (allowed) OR the SM net
  (gated-off). **The gate does NOT reintroduce the v1 dark-rig hole.**
- [confirmed] We STILL keep `reason="drop_crossing"` for **allowed** crossings — for a different
  reason: byte-identical **scene** MIDI. In `blackout_mask` mode `autoloop_tick_just_fired` is
  **deliberately false at the crossing** (`state_manager.py:3718-3719`), so a cycle-gated fire would
  miss the impact; `is_drop_crossing` bypasses the refire gate so the drop fires immediately.
  **The at-anchor ALLOWED impact MUST keep emitting `reason="drop_crossing"`, role="drop".** Cycling
  is ADDITIVE on sustained ticks (`drop_cycle`/`post_drop_cycle`). The executor's blackout
  arm/resolve code is left untouched.
- [confirmed] **Disallowed crossings are NOT byte-identical, by design (the A3 fix) — and one
  teardown detail differs.** Today (ungated priority-9, `:433-445`) a disallowed crossing emits
  `drop_crossing` and resolves via the executor's `_resolve_pending_blackout(drop_crossing_success)`
  (`:245`), which **respects mask owners** (`:296-298`). Flag-ON, a disallowed crossing emits
  `post_drop_cycle`, so the SM net's `clear_pending_blackout` runs `_release_all_masks()`
  (`:340-344`) — which **releases mask owners** (`master_switch`/breakdown). This is narrow (a
  smart-drop crossing during an active breakdown is impossible — `smart_rearm.py:112` returns none and
  the arm at `:3808` requires `not breakdown_active`; the `master_switch` mask is normally released by
  the first refire at `:3789` before any drop), but invariant C2 carves it out and Part D's A4 test
  asserts mask-owner state in both flag modes.

### A5. Field availability + cadence (verified)
- [confirmed] `SmartPhrasingState` (`smart_phrasing.py:43-69`) carries every field the LED
  resolver/anchor/gate read: `abs_beat, current_phrase_label, current_phrase_start_beat,
  phrase_start_crossing, previous_phrase_label, current_phrase_is_chorus, current_phrase_is_low,
  current_phrase_is_up (:49), beats_into_phrase, active_drop_beat, smart_drop_crossing,
  smart_post_drop_active, smart_breakdown_active (:62), breakdown_start_crossing (:63),
  beats_to_next_drop, transition_window_active`. (The last three feed the LED **non-drop** branches —
  breakdown `:2241`, buildup `:2269` — which the resolver returns `"none"` for and does NOT port;
  they are listed so the field set is complete and the A8 ordering note is grounded.) The laser
  reaches all fields via `LaserContext.smart_phrasing` (`laser_models.py:143`).
- [confirmed] **NOT the same snapshot as the live LED resolver (claim corrected).** The LED dispatch
  consumes an **offset-shifted** snapshot: `state_manager.py:3616-3620` passes
  `led_sp_state = _led_sp_state_for_next_backend(sp_state, bpm)` to `_dispatch_led_automation`
  (resolver call at `:1741`), while the laser context is built from the **raw** `sp_state` (`:3824`).
  `_led_sp_state_with_offset` (`:3975-3992`) is identity only when the LED automation offset is
  `<= 0`; the default is `0.0` (`:397-398`), so today they coincide — but if the operator sets a
  non-zero `automation_cloud_offset_s`/`automation_realtime_offset_s`, the LED arms drops at beats
  shifted by `offset_beats` and the laser arms at raw beats. **The laser mirrors RAW phrasing; the
  LED backend offset is a separate, deliberate latency-comp concern.** Do NOT try to feed the laser
  the LED offset snapshot; Part D documents this divergence.
- [confirmed] **Cadence source.** `autoloop_tick_just_fired` is set by markers/anchors/arm plus a
  32-beat interval reset on each marker (`state_manager.py:3719-3787`, `AUTOLOOP_ARM_PHRASE_BEATS`).
  There is **no** general per-feature cycle timer. The laser cycle cadence uses
  `autoloop_tick_just_fired` (Task 4) — **no `drop_cycle_beats` knob** (it would be fake config the
  code ignores). **`post_drop_cycle_beats` is likewise NOT consumed by the laser** — nothing in the
  laser decision/exec path reads it (cadence is autoloop ticks). It is retained only as a
  renderer-agnostic cadence-intent value for the future native-DMX path; Task 2 stores it and marks
  it explicitly inert so it is not mistaken for live config (documented divergence from LED's
  abs-beat cadence `:2466-2468`).

### A6. Config reality (verified — the fallback trap)
- [confirmed] `config/laser_director.json`: `house_drop_1` is **`scene_type=static`** (note 96) and
  is the **first** entry of `house.drop_bank` AND the **only** entry of `dubstep.drop_bank` and
  `dubstep.post_drop_bank`. `house_drop_2/3` are `safety_class=high_impact`. `house.post_drop_bank=[]`.
  ⇒ `dubstep.post_drop_bank` is **non-empty but contains zero cyclable scenes**. A
  "`post_drop_bank` non-empty" fallback test is therefore WRONG (dubstep would go dark). The
  fallback predicate MUST be "has a usable cyclable scene" (Task 3/Task 4). **The same "usable"
  filter must NOT be applied to the at-anchor drop IMPACT — see A8: an impact is a one-shot and a
  static scene is valid for it. Filtering the impact to autoloop-only is exactly what would make
  dubstep + every example personality go dark.**

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

### A8. ROOT CAUSE of a regression the gated mirror would INTRODUCE (verified) — the impact dark-drop
The "usable cyclable" filter (A6) is correct for the *cycle* ticks but **must not gate the at-anchor
impact**. Verified against the live + example config:
- [confirmed] **Live `dubstep`** has `drop_scene=drop_bank=post_drop_bank=[house_drop_1]`, and
  `house_drop_1` is `scene_type=static` (note 96); `allow_high_impact=false`. ⇒ the usable-autoloop
  set for `drop` AND `post_drop` is **empty**.
- [confirmed] **All six example-config personalities** (`house, dubstep, trap, hard_techno,
  bass_house, tech_house`) have `drop_bank=[house_drop_1]` (static) ⇒ empty usable drop set.
- [confirmed] If the at-anchor `drop_crossing` pick is routed through a usable-only shuffle bag that
  returns `""` on an empty usable set, `laser_executor.py:157-160` (`if not selected_scene: return`)
  fires **nothing**. Today (flag-off) the impact routes through `_choose_bank_scene_locked`
  (`:401-413`) over the raw `drop_bank` and fires `house_drop_1` (the static one-shot). ⇒ default-ON
  would make the **drop hit dark** for dubstep (live) and every example personality. This violates
  C6/C11 and is the regression Task 4 must NOT ship.
- [decision] The impact is a **one-shot**, so a static scene is valid for it; only **cycles** must be
  autoloop. Task 4 therefore shuffles the impact **when** the usable set is non-empty (house: 15
  usable drops → random impact, per A7) and **falls back to the configured static drop**
  (`decision.scene` = the director's `_drop_scene`) when it is empty (dubstep: fires `house_drop_1`).
  Never dark. (Side effect: where a usable bank exists, the static `house_drop_1` is no longer used as
  an impact — it cannot cycle and a usable autoloop look is always preferred. Accepted.)
- [confirmed] **First-tick + empty-`drop_scene` guard.** Today's priority-9 fires only when
  `previous_abs_beat is not None and self._drop_scene` (`:433`); `_last_smart_abs_beat` initialises to
  `None` (`:122`,`:687`). The flag-ON resolver block MUST preserve both guards on the immediate
  `drop_crossing` emission (Task 3a) so it does not emit on the first post-reset tick or with an
  unconfigured `_drop_scene`.
- [confirmed] **Ordering: breakdown/pre_drop ahead of the chorus window.** LED checks breakdown
  (`:2241`, `smart_breakdown_active OR breakdown_start_crossing`), pre_drop (`:2243`,
  `transition_window_active`), buildup (`:2245`) **before** the chorus/post_drop window (`:2248`). The
  resolver cannot see those signals and returns drop/post_drop whenever in the chorus window. The
  laser integration shields most of this — breakdown is priority-8 (`:421`) before the resolver — but
  priority-8 is **narrower** than LED's breakdown: it tests only `smart_breakdown_active and
  self._breakdown_scene`, NOT `breakdown_start_crossing`, and there is **no pre_drop pre-check**
  before the resolver. ⇒ on a `breakdown_start_crossing`-only tick or a `transition_window_active`
  tick that coincides with a chorus, the laser may emit `post_drop_cycle`/`drop` where LED does
  breakdown/pre_drop. Narrow (chorus rarely co-occurs with breakdown-start/transition), strictly no
  worse than today's ungated drop, and documented as an accepted, integration-only divergence; Part D
  asserts it rather than pretending parity.

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
    resolve(sp_like, *, mutate) -> DropResult   # the WHOLE LED drop region in ONE call
    reset() -> None                              # clears all three state fields
```
`resolve` reproduces ONLY the drop-region slices of `_led_role_from_smart_phrasing`: the
clear-if-`should_clear` + anchor branch (`:2228-2239`) and the chorus/post_drop window
(`:2248-2256`, `abs_beat < impact_until` → "drop" else "post_drop"). For everything the LED
function decides as breakdown / pre_drop / buildup / low / groove (`:2241-2247`, `:2257-2259`),
`resolve` returns `role="none"` — those stay the laser director's own branches; do NOT port
breakdown/buildup into this resolver. It returns `DropResult(role, armed_this_tick)`:
- `role`: `"drop"` | `"post_drop"` | `"none"` (`"none"` = not in the drop lifecycle → caller falls
  through to its own breakdown/buildup/phrase logic).
- `armed_this_tick`: `True` only on the tick a NEW impact was armed (the impact-start). The director
  uses this to keep `reason="drop_crossing"` exactly at the anchor (A4 blackout), and `"drop_cycle"`
  on sustained ticks — so arming happens in exactly ONE place (here), never duplicated in `_decide`.
It takes a small struct of the A5 SmartPhrasing fields; it MUST NOT import bridge runtime modules.
Refactoring the live LED path to call this is **out of scope** (avoids LED regression); the parity
test (Task D) proves equality.

### Task 2 — `laser_models.py` + `laser_config.py`: configurable knobs (default-on)
Add to `LaserPersonality` (near `drop_style`, `laser_models.py:~115`):
- `drop_lifecycle_mirror: bool = True`   (**kill switch, default ON**)
- `max_drops_in_a_row: int = 2`
- `drop_impact_beats: float = 32.0`      (operator value; flat — no per-look pairing this pass)
- `post_drop_cycle_beats: float = 32.0`  (**INERT for the laser** — A5: the laser rotates on
  `autoloop_tick_just_fired`; nothing in the decision/exec path reads this. Store it for the future
  native-DMX cadence only and add a `# inert: not consumed by the laser decision/exec path` comment at
  the field. Do NOT wire it into `resolve()` or the executor.)
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
`reset_runtime_state(reason: str)` (see Task 3d). In `_decide`, when `drop_lifecycle_mirror` is ON:

3a. **ONE unified block replaces priority-9 `drop_crossing` + priority-10 `drop_hold` ONLY
(`:432-477`).** This is the A3 fix (gate) + A4 (blackout preserved) in a single resolver call so
arming happens in exactly one place. **CRITICAL — do NOT extend the replaced range past `:477`:**
the priority-11 buildup window (`:479-513`), the buildup-gate logging (`:514-529`), the
`_last_smart_abs_beat`/`_post_drop_start_abs_beat` housekeeping (`:531-536`), and the
`_decide_phrase_default(...)` call (`:538-543`) are **kept verbatim**. Replace `:432-477` with:
```python
if self._drop_lifecycle is not None and drop_lifecycle_mirror_on:
    res = self._drop_lifecycle.resolve(sp, mutate=True)   # full LED drop region, one call
    # Preserve today's priority-9 guards (:433): never emit the immediate at-anchor drop_crossing on
    # the first smart tick after a reset (previous_abs_beat is None) or with an unconfigured drop
    # scene. (resolve() may have armed the lifecycle this tick regardless — that is fine: the impact
    # then surfaces as res.role=="drop"/drop_cycle below, which fires no MIDI at a blackout-mode
    # crossing since autoloop_tick_just_fired is False there, matching today's no-fire.)
    if res.armed_this_tick and previous_abs_beat is not None and self._drop_scene:
        # impact START → keep reason="drop_crossing": executor fires immediately AND
        # resolves the Smart Drop blackout for an ALLOWED crossing, byte-identical to today (A4).
        # res.armed_this_tick is True only when impact_allowed (the GATE), so an ungated
        # smart_drop_crossing in groove/buildup no longer fires a drop (A3 fix).
        self._post_drop_start_abs_beat = abs_beat
        self._last_smart_abs_beat = abs_beat
        return LaserSceneDecision(scene=self._drop_scene, reason="drop_crossing",
                                  priority=9, source="policy", role="drop")
    if res.role == "drop":          # sustained inside the impact window (or guarded-out first tick)
        self._last_smart_abs_beat = abs_beat
        return LaserSceneDecision(scene=self._drop_scene, reason="drop_cycle",
                                  priority=10, role="drop", source="policy")
    if res.role == "post_drop":
        self._last_smart_abs_beat = abs_beat
        if self._has_usable_cyclable_post_drop():     # A6 fallback predicate (Task 3c)
            return LaserSceneDecision(scene=self._post_drop_scene or self._drop_scene,
                                      reason="post_drop_cycle", priority=10, role="post_drop",
                                      source="policy")
        return LaserSceneDecision(scene=self._drop_scene, reason="drop_cycle",   # never dark
                                  priority=10, role="drop", source="policy")
    in_post_drop_hold = False     # res.role == "none": resolver OWNS the post-drop window, so we
                                  # are NOT in a hold; the preserved buildup gate (:479+) reads this.
else:
    # flag OFF: the ORIGINAL :432-477 (smart_drop_crossing drop_crossing + drop_hold) runs verbatim,
    # including computing `in_post_drop_hold`. Byte-for-byte unchanged.
    <original :432-477 here>
# fall through to the UNCHANGED priority-11 buildup window + _decide_phrase_default (:479-543)
```
**Both branches must define `in_post_drop_hold`** (the buildup gate at `:493`/`:515-528` reads it):
flag-ON "none" path sets it `False`; flag-OFF path computes it as today. Do NOT delete or move the
buildup window — only `:432-477` changes.
Breakdown stays at priority 8 (ahead of the lifecycle) — **intentional, documented divergence**
from LED order; it is strictly safer (no drop during an active breakdown) and matches today's
laser behavior. **Documented edge divergence:** if `smart_post_drop_active` is true during an
up phrase, LED checks buildup (`:2245`) *before* the chorus/post_drop window (`:2248`); the laser
consults the resolver before its buildup window, so it may emit `post_drop_cycle` where LED would
emit buildup. Narrow (chorus and up are normally mutually exclusive), accepted, and consistent with
scoping buildup out of the mirror. `pre_drop`/`low` are not laser roles and remain routed to the
existing buildup/phrase logic (pre_drop_scene stays inert per `laser_config.py:632`).

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
**Placement rule:** put `_drop_lifecycle.reset()` ONLY in `reset_runtime_state` (transition-driven).
Do NOT fold it into `_reset_smart_observation_state` (`laser_director.py:683`), which `_decide` calls
EVERY idle/stale/not-ready/scripted tick (priorities 3–7): clearing the lifecycle per-tick would
diverge from the LED, which clears only at the transition sites above + `should_clear`. The resolver
is never consulted on those early-return ticks anyway (they return before priority 9), so a transient
stale must not wipe a mid-chorus lifecycle.

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
   - In `_select_scene` (`:375`), for `role in ("drop","post_drop")` with a **cycling** reason
     (`drop_cycle`/`post_drop_cycle`): fire only on `ctx.autoloop_tick_just_fired`, then
     `return self._next_shuffled_scene_locked(role)`. On an empty usable set this returns `""`, which
     for a cycle is a correct no-op (the Task-3 post_drop→drop fallback already routed playable
     personalities to `drop_cycle`; a personality with no usable cycle simply holds the latched look —
     never a static/one-shot fired as a cycle).
   - **At-anchor `drop_crossing` (flag-on) MUST NOT go dark (A8).** Route the impact pick through the
     bag **but fall back to the configured static drop** when the bag is empty:
     ```python
     scene = self._next_shuffled_scene_locked("drop")   # shuffled impact when usable (house: 15)
     if not scene:
         scene = decision.scene                          # static one-shot impact (dubstep / example)
     return scene
     ```
     `decision.scene` is the director's `_drop_scene` (`house_drop_1` for dubstep/house). This keeps
     the random impact for personalities with usable autoloop drops AND preserves today's static
     impact for static-only banks. Leave the flag-off `drop_crossing`/`drop_hold` paths on the
     existing `_choose_bank_scene_locked`.
   - **Teardown:** clear `_role_bag` in `reset_runtime_state` alongside `_role_active_scene` so each
     track starts a fresh shuffle (B3 / Task 3d). NOTE `_role_cursors` is **not** reseeded on
     track/master change (`reset_cursors=False` at `state_manager.py:2596/2624`); clearing the bag
     (`not bag` → rebuild) is sufficient to re-shuffle per track. The cursor offset persists, so the
     first pass of a new track may start mid-bag — Part D's "every usable entry once per pass"
     assertion must start at a reshuffle boundary, not at construction.
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
2. **Smart Drop blackout safe (A4).** The executor's blackout arm/resolve code is not modified;
   cycling reasons never enter it. For an **allowed** crossing the at-anchor impact still emits
   `reason="drop_crossing"` and the blackout note-on/off pair is byte-identical (tested). For a
   **disallowed** crossing (gated off) the blackout is cleared by the existing SM net
   (`state_manager.py:3847-3853`), NOT the executor's `drop_crossing_success` path — so the rig does
   not go dark, but the **mask-owner** teardown differs (the net runs `_release_all_masks`); Part D's
   A4 test asserts mask-owner state in both flag modes.
3. **Drop role is GATED (A3).** A drop look only fires/holds when the lifecycle's
   `impact_allowed` is true (LED parity). No drop look during buildup/groove from an ungated
   `smart_drop_crossing` or an over-ranked `drop_hold`.
4. **No arm spam.** Cycling MIDI fires **only** on `ctx.autoloop_tick_just_fired`.
5. **N-in-a-row honored.** ≤ `max_drops_in_a_row` consecutive impacts before `post_drop`, with the
   LED predecessor allowances (incl. the capped chorus→chorus path; requires `first_drop_anchor_beat`).
6. **No-dark drop/post_drop (A6+A8).** (a) post_drop: a personality with no **usable cyclable**
   post_drop look cycles drops instead ("bank non-empty" is NOT the test). (b) drop IMPACT: the
   at-anchor `drop_crossing` falls back to the configured static `_drop_scene` when no usable autoloop
   drop exists, so **dubstep (live) and every example personality still fire a drop hit** — the impact
   is never dark. Cycles remain autoloop-only (no static fired as a cycle).
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
- **Parity test (FLAT-vs-FLAT — state it)** — assert `resolve(...).role` equals the LED resolver
  `_led_role_from_smart_phrasing` for the **drop/post_drop region** across shared timelines with
  LED-equivalent config (max=2, impact=8, cycle=32), **mapping every LED non-drop role
  (breakdown/pre_drop/buildup/low/groove) → `"none"`**. Drive the LED reference WITHOUT
  `_led_note_drop_decision_accepted` (A2) and assert a comment that this proves **flat-window**
  parity, NOT live-LED-window parity. Also assert `armed_this_tick` is True on exactly the ticks LED
  increments `_led_drop_impact_count`. Timelines MUST include: chorus phrase-start anchor;
  smart_drop_crossing with allowed and **disallowed** predecessors; chorus→chorus cap; lifecycle
  clear on chorus end; **and the A8 ordering ticks — chorus co-active with `breakdown_start_crossing`
  (only), and chorus co-active with `transition_window_active`** — where the resolver returns
  drop/post_drop but LED returns breakdown/pre_drop. Assert these as KNOWN, integration-shielded
  divergences and compare the laser director's INTEGRATED output (priority-8 breakdown first)
  separately, rather than asserting raw resolver parity there.
- **Blackout-preservation test (A4)** — `test_laser_executor*` + `test_laser_director*`/state-manager:
  (a) an **allowed** `drop_crossing` decision arms/resolves the blackout identically flag ON vs OFF,
  in `blackout_mask` AND `legacy_rearm` modes; the at-anchor drop fires on the crossing tick even
  though `autoloop_tick_just_fired` is False in blackout mode. (b) a **disallowed** crossing flag-ON
  (predecessor groove/other) emits `post_drop_cycle` (not `drop_crossing`), and the armed blackout is
  cleared by the SM net (`state_manager.py:3847-3853`) — assert the rig does NOT stay dark. (c)
  mask-owner divergence: with a `master_switch` mask held, assert mask state after a disallowed
  crossing flag-ON (net runs `_release_all_masks`) vs flag-OFF (executor `drop_crossing_success`
  preserves it) — documents C2's carve-out.
- **Regression test for the live bug (A3)** — `test_laser_director*`: feed a `smart_drop_crossing`
  with a groove/buildup predecessor (disallowed) → assert the director emits **no** `drop`/`drop_cycle`
  (no drop look in groove/buildup); and a long (32-beat) impact window does not mask a later buildup
  beyond the gate.
- **Cycling + shuffle-bag test (A7)** — `test_laser_executor*` with a seeded `rng`:
  `drop_cycle`/`post_drop_cycle` with `autoloop_tick_just_fired=True` fire MIDI each tick and select
  via the shuffle-bag — assert that over one full pass (started at a reshuffle boundary, since
  `_role_cursors` may be seeded mid-bag) every **usable** entry appears exactly once, the order is the
  seeded permutation, and the bag **reshuffles on exhaustion** (second pass order may differ). Assert
  static/high-impact-disallowed entries **never** appear as a cycle. With
  `autoloop_tick_just_fired=False` → no MIDI. A bank-membership change rebuilds the bag. Cross-track:
  assert the per-track pattern is NOT "same look all track, +1 next track" (the regression fixed).
- **A8 impact-never-dark test** — `test_laser_executor*`: a flag-ON `drop_crossing` for a
  **static-only / empty-usable** drop personality (**live `dubstep`** and an example personality)
  fires the configured static `_drop_scene` (`house_drop_1`), NOT `""`. For a usable-bank personality
  (`house`, 15 usable) the impact is shuffled from the bag. Assert dubstep's `post_drop` →
  drop-cycle fallback → static impact fallback chain never goes dark (drop hit + post_drop both fire).
- **Offset divergence (A5)** — if a parity/integration timeline sets a non-zero LED automation offset,
  feed the LED `_led_sp_state_for_next_backend(sp_state)` and the laser the raw `sp_state`, and assert
  the drop anchors differ by `offset_beats` (the laser mirrors RAW phrasing). At the default offset
  (0.0) they coincide. Do NOT assert equality under a non-zero offset.
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
- [ ] Banks untouched; runtime skips non-cyclable entries for **cycles**; the at-anchor **impact**
      falls back to the static `_drop_scene` so `dubstep` (live) + all example personalities fire a
      drop hit (no dark — A8 test green). Sync checker (transitional) reports info, exits 0 on live config.
- [ ] `python3 -m unittest discover tests` green; AGENTS.md §8 hard checks green; `laser`
      (+`led_govee`) change-contract docs updated. No push/tick-path I/O added.

## When you finish
- Commit per task with real messages. Report: files touched, parity-test result, the A4
  blackout-equivalence proof, the A3 regression result, the sync-checker output on the live config,
  and confirmation that kill-switch-OFF is a byte-for-byte no-op.

## Pre-handoff checklist status (Claude self-review before Codex)
1. Claims labeled confirmed/assumed/unknown — yes (A1–A6); the one unknown (which mechanism per
   sighting) is surfaced and does NOT block (gated mirror fixes both).
2. Verified against CURRENT code at `c4edf97` — yes (re-read this pass; code at HEAD == `d47d155`,
   only the spec doc changed since, so the file:line citations hold).
3. Pending-state guard — A4 traces the blackout end-to-end: arm (`:121-151`), the executor
   `drop_crossing_success` path, AND the SM net (`:3842-3853`) that clears a gated-off crossing. The
   net (not `drop_crossing`) is the real clear path — the earlier "must keep drop_crossing or the
   blackout strands" claim is corrected. The mask-owner teardown divergence on disallowed crossings
   is surfaced (C2 + Part D).
4. Mode-transition cleanup — Task 3d enumerates ALL transition paths incl. the resume path that
   today resets neither director nor executor.
5. Third-party API completeness — N/A (no new third-party API; MIDI message path unchanged).
6. Cross-checked against existing code — gate reuses `_drop_scene`/`drop_bank`/`autoloop_tick_just_fired`
   authority vars; predicate matches `scene_type`/`safety_class`/`allow_high_impact` as the executor uses them.
7. Pure-function seam — `drop_lifecycle.py` is pure and table-tested.
8. Live safety explicit — Part C; blackout preserved (A4); gate is strictly-safer than today.
9. Adversarial self-review — done (Opus-max review, this pass). Closed: the **impact dark-drop**
   regression the usable-filter would introduce for dubstep (live) + all example personalities
   (A8 / Task 4 static fallback); the **A4 blackout reasoning** (corrected to the SM net; mask-owner
   divergence surfaced); the **not-same-snapshot** offset divergence (A5); the **flat-vs-flat** parity
   illusion and the breakdown/pre_drop-vs-chorus ordering hole (A8 + Part D); the
   first-tick/empty-`_drop_scene` guard (A8 / Task 3a); `post_drop_cycle_beats` marked inert
   (A5 / Task 2). Remaining accepted divergences (cadence, flat window, ordering) are documented, not
   hidden.
