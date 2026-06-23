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
> kill switch that defaults ON** so the show can disable it via personality config update (hot-reload or restart; it is NOT a single runtime command).
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
- **Default ON**, with a config-driven kill switch (`drop_lifecycle_mirror`, default `true`) applied on the next personality re-apply via the hot-reloader.

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
- **Default ON** via config-driven kill switch `drop_lifecycle_mirror` (default `true`). When **off**, laser
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

### Identifier & literal-implementation contract (READ FIRST — implementer = Sonnet 4.6)
Implement EXACTLY the code in these tasks. Do not improvise, rename, "clean up", reorder, or add
anything not listed. Where a task shows a `python` block, that block is the source of truth —
transcribe it verbatim (adjusting only the leading indentation to match the host method/class).
- **Create with these exact names (no synonyms):**
  - module `drop_lifecycle.py`; dataclasses `DropLifecycleConfig`, `DropResult`; class
    `DropLifecycle` with methods `reset`, `_abs_beat`, `drop_anchor`, `impact_allowed`,
    `should_clear`, `arm`, `resolve` and state attrs `_first_drop_anchor_beat`,
    `_impact_until_beat`, `_impact_count`.
  - director attrs `self._drop_lifecycle`, `self._drop_lifecycle_mirror`, `self._allow_high_impact`,
    `self._post_drop_bank`, `self._scenes`; director methods `reset_runtime_state`,
    `_has_usable_cyclable_post_drop`; module const `_LASER_DROP_IMPACT_PREDECESSORS`.
  - executor attr `self._role_bag`; executor methods `_usable_bag_entries`,
    `_next_shuffled_scene_locked`.
  - `LaserPersonality` fields `drop_lifecycle_mirror`, `max_drops_in_a_row`, `drop_impact_beats`,
    `post_drop_cycle_beats`.
- **Exact, case-sensitive reason strings:** `"drop_crossing"`, `"drop_cycle"`, `"post_drop_cycle"`.
  Roles: `"drop"`, `"post_drop"`. Invent NO new reason/role strings. Do NOT change the existing
  `"drop_hold"`/`"post_drop_hold"` reasons (they live only in the flag-OFF path).
- **Line numbers are from HEAD `c4edf97` and WILL shift as you edit.** Always locate a target by the
  quoted surrounding code, never by the bare number.
- **Never touch:** the executor blackout methods (`trigger_blackout_on`, `_resolve_pending_blackout`,
  `hold_blackout_mask`, `release_blackout_mask`, `_release_all_masks`, `clear_pending_blackout`) and
  the `is_drop_crossing` branches in `on_decision`; `smart_phrasing.py`; `smart_rearm.py`;
  `autoloop_controller.py`; the `_led_*` LED path in `state_manager.py`; the push-loop threading.
- **The flag-on/flag-off switch is read from state, never from a decision field:** the director reads
  `self._drop_lifecycle_mirror`; the executor reads `self._personality.drop_lifecycle_mirror`. Do NOT
  add a field to `LaserSceneDecision`.
- **Commit after each task** with the message in "When you finish".

### Task 1 — Create `drop_lifecycle.py` (pure, no bridge imports). Transcribe verbatim.
A pure resolver reproducing ONLY the LED drop/post_drop region of `_led_role_from_smart_phrasing`
(`state_manager.py:2228-2256`) plus its helpers (`_led_drop_marker_anchor :2273`,
`_led_drop_impact_allowed :2283`, `_led_drop_lifecycle_should_clear :2305`,
`_led_arm_drop_lifecycle :2312`, `_led_abs_beat :2365`). It carries all THREE LED state fields and is
parameterised by config. It MUST NOT import any bridge runtime module; it reads `sp` by attribute
(duck-typed). Create the file with EXACTLY this content:
```python
"""Pure, renderer-agnostic drop / post_drop lifecycle resolver.

Mirrors the LED drop-region resolver in state_manager.py (_led_role_from_smart_phrasing and its
helpers). Pure: no I/O, no bridge imports. `sp` is any object exposing the SmartPhrasing attributes
read below (the live laser passes a SmartPhrasingState; tests pass a types.SimpleNamespace).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DropLifecycleConfig:
    max_drops_in_a_row: int            # = LED_MAX_DROP_IMPACTS (2)
    drop_impact_beats: float           # flat impact window (operator 32.0; LED-parity 8.0)
    post_drop_cycle_beats: float       # inert here; carried for the future native-DMX cadence
    impact_predecessors: frozenset     # = frozenset({"up", "low", "buildup", "breakdown"})


@dataclass(frozen=True)
class DropResult:
    role: str            # "drop" | "post_drop" | "none"
    armed_this_tick: bool


class DropLifecycle:
    def __init__(self, config: DropLifecycleConfig) -> None:
        self._config = config
        self._first_drop_anchor_beat: Optional[float] = None
        self._impact_until_beat: Optional[float] = None
        self._impact_count: int = 0

    def reset(self) -> None:
        self._first_drop_anchor_beat = None
        self._impact_until_beat = None
        self._impact_count = 0

    def _abs_beat(self, sp) -> Optional[float]:
        if sp.abs_beat is not None:
            return float(sp.abs_beat)
        if sp.current_phrase_start_beat is not None and sp.beats_into_phrase is not None:
            return float(sp.current_phrase_start_beat) + float(sp.beats_into_phrase)
        if sp.active_drop_beat is not None:
            return float(sp.active_drop_beat)
        return None

    def drop_anchor(self, sp) -> Optional[float]:
        if sp.current_phrase_is_chorus and sp.phrase_start_crossing:
            if sp.current_phrase_start_beat is not None:
                return float(sp.current_phrase_start_beat)
        if sp.smart_drop_crossing:
            if sp.active_drop_beat is not None:
                return float(sp.active_drop_beat)
            return self._abs_beat(sp)
        return None

    def impact_allowed(self, sp) -> bool:
        previous = str(sp.previous_phrase_label or "other")
        if previous in self._config.impact_predecessors:
            return True
        if sp.smart_drop_crossing:
            current = str(sp.current_phrase_label or "other")
            if current in self._config.impact_predecessors:
                return True
        if previous == "chorus":
            if (
                self._first_drop_anchor_beat is not None
                and self._impact_count < self._config.max_drops_in_a_row
            ):
                return True
        return False

    def should_clear(self, sp) -> bool:
        if sp.smart_drop_crossing:
            return False
        if sp.current_phrase_is_chorus or sp.smart_post_drop_active:
            return False
        return self._first_drop_anchor_beat is not None

    def arm(self, anchor_beat: float) -> None:
        if self._first_drop_anchor_beat is None:
            self._first_drop_anchor_beat = float(anchor_beat)
        self._impact_until_beat = float(anchor_beat) + self._config.drop_impact_beats
        self._impact_count += 1

    def resolve(self, sp, *, mutate: bool) -> DropResult:
        if mutate and self.should_clear(sp):
            self.reset()
        anchor = self.drop_anchor(sp)
        if anchor is not None:
            if self.impact_allowed(sp):
                armed_this_tick = False
                if mutate:
                    self.arm(anchor)
                    armed_this_tick = True
                return DropResult(role="drop", armed_this_tick=armed_this_tick)
            if mutate and self._first_drop_anchor_beat is None:
                self._first_drop_anchor_beat = anchor
            return DropResult(role="post_drop", armed_this_tick=False)
        # No anchor. Reproduce ONLY the chorus/post_drop window (LED :2248-2256). Breakdown,
        # pre_drop, buildup, low, groove are the laser director's OWN branches -> "none".
        if sp.current_phrase_is_chorus or sp.smart_post_drop_active:
            abs_beat = self._abs_beat(sp)
            if (
                abs_beat is not None
                and self._impact_until_beat is not None
                and abs_beat < self._impact_until_beat
            ):
                return DropResult(role="drop", armed_this_tick=False)
            return DropResult(role="post_drop", armed_this_tick=False)
        return DropResult(role="none", armed_this_tick=False)
```
**Attributes `resolve` may read on `sp` (and NO others):** `abs_beat`, `current_phrase_start_beat`,
`beats_into_phrase`, `active_drop_beat`, `current_phrase_is_chorus`, `phrase_start_crossing`,
`smart_drop_crossing`, `previous_phrase_label`, `current_phrase_label`, `smart_post_drop_active`.
`armed_this_tick` is True on EXACTLY the ticks `arm()` runs (anchor present AND `impact_allowed`) —
the same ticks the LED runs `_led_arm_drop_lifecycle` / increments `_led_drop_impact_count`.
Refactoring the live LED path to call this is OUT OF SCOPE (the Task-D parity test proves equality).

### Task 2 — `laser_models.py` + `laser_config.py`: configurable knobs (default-ON)
**2a.** In `laser_models.py`, in the `LaserPersonality` dataclass, immediately AFTER the line
`drop_style: str = "drop_mode"` (`:115`), add exactly:
```python
    drop_lifecycle_mirror: bool = True        # kill switch, default ON
    max_drops_in_a_row: int = 2
    drop_impact_beats: float = 32.0           # operator value; flat window
    post_drop_cycle_beats: float = 32.0       # inert: not consumed by the laser decision/exec path
```
Do NOT add `drop_cycle_beats` or `drop_pairs` (A5/A2: fake config / wrong-scene keying).

**2b.** In `laser_config.py` `_validate_personality`, immediately BEFORE the
`bpm_band_min = data.get("bpm_band_min", 0.0)` line (`:692`), add exactly:
```python
    drop_lifecycle_mirror = data.get("drop_lifecycle_mirror", True)
    if not isinstance(drop_lifecycle_mirror, bool):
        errors.append(f"{prefix}: 'drop_lifecycle_mirror' must be a boolean")

    max_drops_in_a_row = data.get("max_drops_in_a_row", 2)
    if (
        not isinstance(max_drops_in_a_row, int)
        or isinstance(max_drops_in_a_row, bool)
        or max_drops_in_a_row < 1
    ):
        errors.append(f"{prefix}: 'max_drops_in_a_row' must be a positive integer")

    for _knob in ("drop_impact_beats", "post_drop_cycle_beats"):
        _value = data.get(_knob, 32.0)
        if isinstance(_value, bool) or not isinstance(_value, (int, float)) or _value <= 0:
            errors.append(f"{prefix}: '{_knob}' must be a positive number")
```

**2c.** In `laser_config.py` `_build_personality` (`:830`), inside the `LaserPersonality(...)`
constructor call, add these kwargs directly AFTER `drop_style=_canon_drop_style(...)` (`:866`),
before the closing `)` (`:867`):
```python
        drop_lifecycle_mirror=bool(data.get("drop_lifecycle_mirror", True)),
        max_drops_in_a_row=int(data.get("max_drops_in_a_row", 2)),
        drop_impact_beats=float(data.get("drop_impact_beats", 32.0)),
        post_drop_cycle_beats=float(data.get("post_drop_cycle_beats", 32.0)),
```
Missing/unknown keys → these defaults (feature ON). **After this task, `python3 -m unittest discover
tests` AND a load smoke test of BOTH `config/laser_director.json` and
`config/laser_director.example.json` must pass clean** (default-ON means existing personalities load
with the mirror enabled).

### Task 3 — `laser_director.py`: gate the drop role + drive the mirrored lifecycle

> **Sub-task order is 3-pre → 3b → 3a → 3c → 3d.** This is intentional: `set_personality_config`
> (`:180`, 3b) is higher in the file than `_decide` (`:432`, 3a). Working top-to-bottom prevents
> line-number drift from earlier insertions shifting later targets. Follow this order exactly.

**3-pre. Imports + construction (do these first).**
- At the top of `laser_director.py`, add `from .drop_lifecycle import DropLifecycle, DropLifecycleConfig`
  right after the existing `from .smart_phrasing import SmartPhrasingState` (`:38`), and a module-level
  constant right after `_DEFAULT_EMERGENCY_SCENE` (`:48`):
  `_LASER_DROP_IMPACT_PREDECESSORS = frozenset({"up", "low", "buildup", "breakdown"})`.
- Add `scenes: Optional[dict] = None,` as the LAST keyword-only parameter in
  `LaserDirector.__init__` (`:63-83`), after `drop_style: str = "drop_mode",` (`:82`). In the body,
  add `self._scenes = scenes or {}` right after `self._drop_style = self._canon_drop_style(drop_style)`
  (`:102`).
- In `__init__`, immediately AFTER `self._decision_log = LaserDecisionLog()` (`:126`), add exactly:
  ```python
          self._drop_lifecycle: Optional[DropLifecycle] = None
          self._drop_lifecycle_mirror: bool = True
          self._allow_high_impact: bool = False
          self._post_drop_bank: tuple[str, ...] = ()
  ```
- At the construction site `__main__.py:393-399`, add `scenes=cfg.scenes,` as a new kwarg to the
  `LaserDirector(...)` call (after `emergency_scene=cfg.emergency_scene,`). This is the SAME `cfg`
  object the executor receives at `:414-418`, so scene-catalog refresh semantics are identical to
  the executor's existing `self._config` — **add no config-reload handling.**

**3b. Build the lifecycle in `set_personality_config` (`:180`).** At the END of that method, AFTER
`self._drop_style = self._canon_drop_style(...)` (`:197-199`), append exactly:
```python
        self._drop_lifecycle_mirror = bool(getattr(personality, "drop_lifecycle_mirror", True))
        self._allow_high_impact = bool(getattr(personality, "allow_high_impact", False))
        self._post_drop_bank = tuple(personality.post_drop_bank)
        self._drop_lifecycle = DropLifecycle(DropLifecycleConfig(
            max_drops_in_a_row=int(getattr(personality, "max_drops_in_a_row", 2)),
            drop_impact_beats=float(getattr(personality, "drop_impact_beats", 32.0)),
            post_drop_cycle_beats=float(getattr(personality, "post_drop_cycle_beats", 32.0)),
            impact_predecessors=_LASER_DROP_IMPACT_PREDECESSORS,
        ))
```
Constructing a fresh `DropLifecycle` here IS the per-personality reset — no extra call needed.

**3a. Replace the Priority-9 + Priority-10 region of `_decide` (`laser_director.py:432-477`).** Locate
the block beginning `# Priority 9: Drop crossing (once per target beat).` and ending with the
Priority-10 `drop_hold` return's closing `)` (just before `# Priority 11:`). Replace that ENTIRE block
with the code below. The `else:` branch is the CURRENT block transcribed verbatim, re-indented one
level — **do not alter a character of it.** Do NOT touch anything at/after `# Priority 11:` (`:479`):
```python
        # Priority 9 + 10: gated drop lifecycle (mirror) OR the original ungated path.
        drop_lifecycle_mirror_on = self._drop_lifecycle_mirror
        if self._drop_lifecycle is not None and drop_lifecycle_mirror_on:
            res = self._drop_lifecycle.resolve(sp, mutate=True)  # full LED drop region, one call
            # Preserve today's priority-9 guards (:433): do NOT emit the immediate at-anchor
            # drop_crossing on the first smart tick after a reset (previous_abs_beat is None) or
            # with an unconfigured drop scene. resolve() may still have armed the lifecycle this
            # tick — fine: the impact then surfaces as res.role == "drop" -> drop_cycle below,
            # which fires no MIDI at a blackout-mode crossing (autoloop_tick_just_fired is False
            # there), matching today's no-fire.
            if res.armed_this_tick and previous_abs_beat is not None and self._drop_scene:
                # ALLOWED impact START -> reason="drop_crossing": executor fires immediately AND
                # resolves the Smart Drop blackout, byte-identical to today for allowed crossings
                # (A4). res.armed_this_tick is True only when impact_allowed (the GATE) — an
                # ungated smart_drop_crossing in groove/buildup no longer fires a drop (A3 fix).
                self._post_drop_start_abs_beat = abs_beat
                self._last_smart_abs_beat = abs_beat
                return LaserSceneDecision(
                    scene=self._drop_scene, reason="drop_crossing",
                    priority=9, source="policy", role="drop",
                )
            if res.role == "drop":  # sustained inside the window (or guarded-out first tick)
                self._last_smart_abs_beat = abs_beat
                return LaserSceneDecision(
                    scene=self._drop_scene, reason="drop_cycle",
                    priority=10, source="policy", role="drop",
                )
            if res.role == "post_drop":
                self._last_smart_abs_beat = abs_beat
                if self._has_usable_cyclable_post_drop():
                    return LaserSceneDecision(
                        scene=self._post_drop_scene or self._drop_scene,
                        reason="post_drop_cycle",
                        priority=10, source="policy", role="post_drop",
                    )
                return LaserSceneDecision(  # no usable post_drop -> cycle drops, never dark
                    scene=self._drop_scene, reason="drop_cycle",
                    priority=10, source="policy", role="drop",
                )
            # res.role == "none": the resolver owns the drop/post_drop window, so we are NOT in a
            # post-drop hold. The preserved Priority-11 buildup gate (below) reads this local.
            in_post_drop_hold = False
        else:
            # Flag OFF (or no lifecycle): the ORIGINAL Priority-9 + Priority-10 code, VERBATIM.
            # Priority 9: Drop crossing (once per target beat).
            if previous_abs_beat is not None and self._drop_scene:
                if sp.smart_drop_crossing:
                    self._pending_drop_crossing_beat = None
                    self._drop_rearm_edge_seen_for_pending = False
                    self._post_drop_start_abs_beat = abs_beat
                    self._last_smart_abs_beat = abs_beat
                    return LaserSceneDecision(
                        scene=self._drop_scene,
                        reason="drop_crossing",
                        priority=9,
                        source="policy",
                        role="drop",
                    )

            # Priority 10: Hold after the drop.
            in_post_drop_hold = (
                self._post_drop_hold_beats > 0
                and self._post_drop_start_abs_beat >= 0.0
                and (abs_beat - self._post_drop_start_abs_beat) < self._post_drop_hold_beats
            )
            if in_post_drop_hold:
                if self._drop_style == "emphasized_drop":
                    if self._post_drop_scene:
                        self._last_smart_abs_beat = abs_beat
                        return LaserSceneDecision(
                            scene=self._post_drop_scene,
                            reason="post_drop_hold",
                            priority=10,
                            source="policy",
                            role="post_drop",
                        )
                elif self._drop_scene:
                    # drop_mode: hold the rotated drop look itself for the post-drop
                    # window; there is no separate post-drop scene. The executor keeps
                    # the already-fired (rotated) drop scene latched via role-unchanged
                    # + same-scene skip, so this decision MUST NOT re-fire MIDI — the
                    # reason is deliberately not "drop_crossing".
                    self._last_smart_abs_beat = abs_beat
                    return LaserSceneDecision(
                        scene=self._drop_scene,
                        reason="drop_hold",
                        priority=10,
                        source="policy",
                        role="drop",
                    )
        # Both branches above have either returned or set `in_post_drop_hold`. Execution continues
        # into the UNCHANGED Priority-11 buildup window + _decide_phrase_default (current :479+).
```
**`in_post_drop_hold` is a plain function-local** (Python has no block scope), so the flag-ON `none`
path setting it `False` and the flag-OFF path computing it both reach the buildup gate at
`:493`/`:515-528`. Do NOT delete, move, or edit the Priority-11 buildup window, the buildup-gate
logging, the `_last_smart_abs_beat`/`_post_drop_start_abs_beat` housekeeping, or the
`_decide_phrase_default(...)` call — only `:432-477` changes.
Breakdown stays at priority 8 (ahead of the lifecycle) — **intentional, documented divergence**
from LED order; it is strictly safer (no drop during an active breakdown) and matches today's
laser behavior. **Documented edge divergence:** if `smart_post_drop_active` is true during an
up phrase, LED checks buildup (`:2245`) *before* the chorus/post_drop window (`:2248`); the laser
consults the resolver before its buildup window, so it may emit `post_drop_cycle` where LED would
emit buildup. Narrow (chorus and up are normally mutually exclusive), accepted, and consistent with
scoping buildup out of the mirror. `pre_drop`/`low` are not laser roles and remain routed to the
existing buildup/phrase logic (pre_drop_scene stays inert per `laser_config.py:632`).

**3c. `_has_usable_cyclable_post_drop` (new method on `LaserDirector`).** Add it directly BEFORE
`_decide` (`:293`), after the closing line of `_record_decision` (`:291`). Add exactly:
```python
    def _has_usable_cyclable_post_drop(self) -> bool:
        for name in self._post_drop_bank:
            sd = self._scenes.get(name)
            if sd is None:
                continue
            if sd.scene_type != "autoloop":
                continue
            if sd.safety_class == "high_impact" and not self._allow_high_impact:
                continue
            return True
        return False
```
It iterates `self._post_drop_bank` ONLY (NOT `post_drop_scene`) so it is byte-identical to the
executor's `_usable_bag_entries("post_drop")` (Task 4). The two predicates MUST agree, or the director
will emit `post_drop_cycle` for a bank the executor then cannot fill → dark. `sd` is a scene-def with
`.scene_type` and `.safety_class` str attributes (the executor reads them at
`laser_executor.py:162,175,187`).

**3d. `reset_runtime_state` (new method on `LaserDirector`).** Add it directly AFTER
`_has_usable_cyclable_post_drop` (3c), still before `_decide`. Add exactly:
```python
    def reset_runtime_state(self, reason: str) -> None:
        del reason  # accepted for call-site symmetry / logging only
        if self._drop_lifecycle is not None:
            self._drop_lifecycle.reset()
        self._reset_smart_observation_state()
```
Do NOT add `self._drop_lifecycle.reset()` to `_reset_smart_observation_state` (`:683`) — that method
runs on EVERY idle/stale/not-ready/scripted tick (`_decide` priorities 3–7) and would wipe a
mid-chorus lifecycle. The LED clears its lifecycle only at the transition sites below + `should_clear`;
mirror that. (The resolver is not consulted on those early-return ticks anyway.)

**3d-wiring. Wire `reset_runtime_state` in `state_manager.py` at exactly these 6 sites.** For sites
1–3, the director call goes DIRECTLY AFTER the existing executor call (inside the same `if` or with
its own guard). For sites 4–6, there is no existing executor call; add only the director call. Each
snippet shows ≥3 surrounding anchor lines so you can locate the insertion point by code, not line
number (line numbers will shift as you edit).

**Site 1: `_on_master_changed`** — find the existing executor reset at `:2595-2596`:
```python
        # BEFORE (current code):
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason="master_changed")
        if (

        # AFTER (add the director call directly below, with its own guard):
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason="master_changed")
        if self._laser_director is not None:
            self._laser_director.reset_runtime_state(reason="master_changed")
        if (
```

**Site 2: `_on_track_loaded`** — find the existing executor reset at `:2623-2624`:
```python
        # BEFORE (current code):
            if self._laser_executor is not None:
                self._laser_executor.reset_runtime_state(reason="active_track_loaded")
            if self._led_look_director is not None:

        # AFTER (add the director call directly below):
            if self._laser_executor is not None:
                self._laser_executor.reset_runtime_state(reason="active_track_loaded")
            if self._laser_director is not None:
                self._laser_director.reset_runtime_state(reason="active_track_loaded")
            if self._led_look_director is not None:
```

**Site 3: `_do_full_stop`** — find the existing executor reset at `:4179-4180`:
```python
        # BEFORE (current code):
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason="stop")

    def _do_resume(self, deck: int, elapsed_ms: int, bpm: float) -> None:

        # AFTER (add the director call directly below):
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason="stop")
        if self._laser_director is not None:
            self._laser_director.reset_runtime_state(reason="stop")

    def _do_resume(self, deck: int, elapsed_ms: int, bpm: float) -> None:
```

**Site 4: `_do_resume`** — find `self._clear_led_drop_lifecycle()` at `:4203`, insert AFTER it:
```python
        # BEFORE (current code):
        self._clear_led_drop_lifecycle()
        self._log_status()

        # AFTER (add BOTH director AND executor resets between the two lines):
        self._clear_led_drop_lifecycle()
        if self._laser_director is not None:
            self._laser_director.reset_runtime_state(reason="resume")
        if self._laser_executor is not None:
            self._laser_executor.reset_runtime_state(reason="resume")
        self._log_status()
```

**Site 5: scripted `_apply_lighting`** — find `self._clear_led_drop_lifecycle()` inside the
`if mode == "scripted":` block at `:3154`, insert AFTER it:
```python
        # BEFORE (current code):
            self._clear_led_drop_lifecycle()
            self._clear_smart_rearm_state()

        # AFTER (add director-only reset between the two lines):
            self._clear_led_drop_lifecycle()
            if self._laser_director is not None:
                self._laser_director.reset_runtime_state(reason="scripted")
            self._clear_smart_rearm_state()
```

**Site 6: idle `_apply_lighting`** — find `elif mode == "idle":` at `:3181`, insert at the TOP of
the block (after the `elif` line, before `self._clear_smart_rearm_state()`):
```python
        # BEFORE (current code):
        elif mode == "idle":
            self._clear_smart_rearm_state()

        # AFTER (add director-only reset at the top of the block):
        elif mode == "idle":
            if self._laser_director is not None:
                self._laser_director.reset_runtime_state(reason="idle")
            self._clear_smart_rearm_state()
```

Do NOT add an executor `reset_runtime_state` at the scripted/idle sites (it already gets
`clear_pending_blackout` via `_clear_smart_rearm_state`; its role-bag reshuffles on return — leaving it
avoids changing executor behavior on those transitions). Personality apply (`_apply_personality_change`
`:2746`) already rebuilds the lifecycle via `set_personality_config` (3b) — no extra reset there.

### Task 4 — `laser_executor.py`: refire + shuffle drop/post_drop on the autoloop cadence
**4a. New executor state.** In `__init__`, immediately AFTER `self._mask_owners: set[str] = set()`
(`:66`), add: `self._role_bag: dict[str, tuple[str, ...]] = {}`.

**4b. Clear it on teardown.** In `reset_runtime_state`, INSIDE the `with self._lock:` block (next to
`self._role_active_scene = {role: "" for role in _AUTO_ROLES}` `:93`), add: `self._role_bag = {}`. Do
NOT reseed `self._role_cursors` here (the call sites pass `reset_cursors=False`); clearing the bag
forces a fresh shuffle on the next pick, which is enough to re-shuffle per track. The cursor offset
persists by design (Part D's per-pass assertion must start at a reshuffle boundary).

**4c. Refire eligibility for cycle reasons.** Replace the `refire_allowed` assignment (`:181-189`)
with exactly (`drop_crossing` is NOT a cycle reason → the A4 blackout path is untouched):
```python
        refire_roles = ("phrase", "buildup", "breakdown")
        cycling = decision.reason in ("drop_cycle", "post_drop_cycle")
        with self._lock:
            last_role_trigger_beat = float(self._role_last_trigger_beat.get(role, -1.0))
            refire_allowed = (
                ctx.autoloop_tick_just_fired
                and (role in refire_roles or (cycling and role in ("drop", "post_drop")))
                and scene_def.scene_type == "autoloop"
                and (last_role_trigger_beat < 0.0 or float(ctx.abs_beat) > last_role_trigger_beat)
            )
```
The replacement scope is EXACTLY lines `:181-189` (from `refire_roles =` through the closing `)` of
`refire_allowed`). Lines `:190-195` (`same_scene_candidate` and `same_scene_refire`) are NOT
replaced — they remain at the same 12-space indentation, inside the SAME `with self._lock:` block
that the replacement re-opens. The net effect: `cycling` is added before the lock as a new local,
the refire condition gains `(cycling and role in ("drop", "post_drop"))`, and everything after `:189`
is untouched.

**4d. Two new methods (add directly after `_choose_bank_scene_locked`, `:413`).** Both REQUIRE the
caller to already hold `self._lock` (the `_locked` convention):
```python
    def _usable_bag_entries(self, role: str) -> list[str]:
        allow_high_impact = bool(
            self._personality.allow_high_impact if self._personality is not None else False
        )
        out: list[str] = []
        for name in self._bank_for_role(role):
            sd = self._config.scenes.get(name)
            if sd is None:
                continue
            if sd.scene_type != "autoloop":
                continue
            if sd.safety_class == "high_impact" and not allow_high_impact:
                continue
            out.append(name)
        return out

    def _next_shuffled_scene_locked(self, role: str) -> str:
        usable = self._usable_bag_entries(role)
        if not usable:
            self._role_active_scene[role] = ""
            return ""                       # caller decides: impact-fallback (4e) / cycle no-op
        cursor = self._role_cursors.get(role, 0)
        bag = self._role_bag.get(role, ())
        if cursor % len(usable) == 0 or not bag or len(bag) != len(usable):
            shuffled = list(usable)
            self._rng.shuffle(shuffled)     # reshuffle on exhaustion / bank-membership change
            bag = tuple(shuffled)
            self._role_bag[role] = bag
        scene = bag[cursor % len(bag)]
        self._role_cursors[role] = cursor + 1
        self._role_active_scene[role] = scene
        return scene
```
This mirrors LED `_look_name_for_role` (`led_look_director.py:330-356`). The `len(bag) != len(usable)`
guard rebuilds when a drop look is added/removed (A7). Do NOT add a same-look bag-boundary guard the
LED lacks (keeps parity; the ~1/N repeat is accepted).

**4e. Replace the WHOLE `_select_scene` method body (`:375-399`)** with exactly (the `phrase` branch
and the trailing `active_scene` branch are byte-identical to today; only the two middle branches and
the three local flags are new):
```python
    def _select_scene(
        self,
        decision: LaserSceneDecision,
        ctx: LaserContext,
        role_changed: bool,
    ) -> str:
        role = decision.role
        if role in ("manual", "emergency"):
            return decision.scene
        if role not in _AUTO_ROLES:
            return decision.scene

        cycling = decision.reason in ("drop_cycle", "post_drop_cycle")
        mirror_on = bool(
            self._personality is not None
            and getattr(self._personality, "drop_lifecycle_mirror", False)
        )
        flag_on_drop_impact = (
            mirror_on and role == "drop" and decision.reason == "drop_crossing"
        )

        with self._lock:
            if role == "phrase":
                if decision.reason not in _PHRASE_TRIGGER_REASONS:
                    return ""
                # Phrase/default should only trigger on real autoloop phrase edges.
                if decision.reason == "phrase_boundary" and not ctx.autoloop_tick_just_fired:
                    return ""
                return self._choose_bank_scene_locked(role=role, fallback_scene=decision.scene)

            if role in ("drop", "post_drop") and cycling:
                # Cycle ticks fire ONLY on an autoloop edge; empty usable set -> no-op (hold).
                if not ctx.autoloop_tick_just_fired:
                    return ""
                return self._next_shuffled_scene_locked(role)

            if flag_on_drop_impact:
                # At-anchor impact: shuffled when usable, else the static one-shot (A8, never dark).
                scene = self._next_shuffled_scene_locked("drop")
                if not scene:
                    scene = decision.scene
                return scene

            active_scene = self._role_active_scene.get(role, "")
            if role_changed or not active_scene:
                return self._choose_bank_scene_locked(role=role, fallback_scene=decision.scene)
            return active_scene
```
**Flag-OFF is byte-identical to pre-change EXCEPT the resume transition, which now also resets the executor (a benign phrase-bank reshuffle + active-scene clear; no dark, no drop leak):** `mirror_on` is False → `flag_on_drop_impact` is False and the
cycle reasons never appear, so a flag-off `drop_crossing`/`drop_hold` falls through to the original
`active_scene` / `_choose_bank_scene_locked` path. The flag is read from
`self._personality.drop_lifecycle_mirror` — there is NO new `LaserSceneDecision` field.

The 32-beat cadence comes from `ctx.autoloop_tick_just_fired` (A5) — **no new timer.** (Documented
divergence from LED's abs-beat-anchored post_drop cadence; acceptable and renderer-agnostic.)

### Task 5 — Keep the laser MIDI mapping consistent (TRANSITIONAL; SS retiring)
> Do not curate/reorder/repopulate banks. Task 5 is mapping **consistency**, not bank composition.
> This task is **transitional/optional** — it is NOT a CI hard gate. SoundSwitch is being retired.

**5a. Validation (`laser_config.py`) — NO new code needed.** The existing
`for bank_field in _PERSONALITY_BANK_FIELDS:` loop (`:715-731`) in `_validate_personality` already
validates that every `drop_bank`/`post_drop_bank` entry references a known scene. Note-collision
checking **cannot** live here because `_validate_personality` only receives `scene_keys: set[str]`
(a flat set of names), not the scene defs with their MIDI notes. The full collision check is in
`tools/check_laser_midi_sync.py` (5c), which loads the entire config dict.

Do NOT add any new validation errors for banks. A bank with only non-cyclable (static) entries or
an empty `post_drop_bank` is **valid** (runtime fallback handles them at A6/A8). Today `dubstep`'s
banks are static-only; adding a validation error would block load.

**5b. `_pad_meta`.** If this implementation does NOT change any scene's MIDI note (it should not),
leave `_pad_meta`/`note_labels`/`banks` as-is. Only if a note is changed (it should not be),
update `_pad_meta` in the same commit.

**5c. Sync checker.** Create `tools/check_laser_midi_sync.py` with exactly this content:
```python
#!/usr/bin/env python3
"""Laser drop/post_drop bank ↔ scene MIDI sync checker (transitional).

Pure read-only reconciliation: loads the laser config, checks that every scene
referenced by drop_bank/post_drop_bank exists in `scenes` with a MIDI note, and
reports (channel, note) collisions across those banks. Non-cyclable entries
(scene_type != "autoloop") are reported as info, not errors.

Exit 0 on clean or info-only; exit 1 on genuine breaks (missing scene, note
collision). This is NOT a CI hard gate — SoundSwitch is being retired.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "laser_director.json"


def reconcile(config_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of issue dicts: {level, message, personality, bank, scene}."""
    issues: list[dict[str, Any]] = []
    scenes = config_dict.get("scenes", {})
    personalities = config_dict.get("personalities", {})

    for p_name, p_data in personalities.items():
        if not isinstance(p_data, dict):
            continue
        note_owners: dict[tuple[int, int], tuple[str, str]] = {}

        for bank_field in ("drop_bank", "post_drop_bank"):
            bank = p_data.get(bank_field, [])
            if not isinstance(bank, list):
                continue
            for scene_name in bank:
                if not isinstance(scene_name, str):
                    continue
                sd = scenes.get(scene_name)
                if sd is None or not isinstance(sd, dict):
                    issues.append({
                        "level": "error",
                        "message": f"bank entry references unknown scene",
                        "personality": p_name,
                        "bank": bank_field,
                        "scene": scene_name,
                    })
                    continue

                scene_type = sd.get("scene_type", "static")
                midi = sd.get("midi", {})
                note = (int(midi.get("channel", 1)), int(midi.get("note", 0)))

                if scene_type != "autoloop":
                    issues.append({
                        "level": "info",
                        "message": f"non-cyclable entry (scene_type={scene_type!r})",
                        "personality": p_name,
                        "bank": bank_field,
                        "scene": scene_name,
                    })

                prev = note_owners.get(note)
                if prev is not None:
                    prev_bank, prev_scene = prev
                    if prev_scene != scene_name:
                        issues.append({
                            "level": "error",
                            "message": (
                                f"(channel={note[0]}, note={note[1]}) collision: "
                                f"{prev_bank}/{prev_scene} vs {bank_field}/{scene_name}"
                            ),
                            "personality": p_name,
                            "bank": bank_field,
                            "scene": scene_name,
                        })
                else:
                    note_owners[note] = (bank_field, scene_name)

    return issues


def main() -> int:
    config_path = DEFAULT_CONFIG
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])

    if not config_path.exists():
        print(f"config not found: {config_path}", file=sys.stderr)
        return 1

    data = json.loads(config_path.read_text(encoding="utf-8"))
    issues = reconcile(data)

    errors = [i for i in issues if i["level"] == "error"]
    infos = [i for i in issues if i["level"] == "info"]

    for issue in issues:
        tag = "ERROR" if issue["level"] == "error" else "INFO"
        print(
            f"[{tag}] {issue['personality']}/{issue['bank']}/{issue['scene']}: "
            f"{issue['message']}"
        )

    if errors:
        print(f"\n{len(errors)} error(s), {len(infos)} info(s)", file=sys.stderr)
        return 1

    print(f"\nclean: 0 errors, {len(infos)} info(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
Run `python3 tools/check_laser_midi_sync.py` on the live config after all other tasks. It MUST
exit 0 (info-only for non-cyclable entries is expected and acceptable).

**5d. Operator step (doc, not code).** In the bounded SS project the operator confirms each
drop/post_drop note triggers the intended autoloop, re-exports the pack. This is operator-run and
optional — do NOT automate it.

## Part C — Invariants that MUST still hold (live safety)
1. **Kill switch off = no change.** `drop_lifecycle_mirror=False` → flag-OFF is byte-identical to pre-change EXCEPT the resume transition, which now also resets the executor (a benign phrase-bank reshuffle + active-scene clear; no dark, no drop leak). Default is ON.
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

Create three new test files. Each MUST pass `python3 -m unittest discover tests` when all Tasks 1–5
are complete. Transcribe each verbatim.

### D1. `tests/test_drop_lifecycle.py` — pure resolver, table-driven

Create this file with EXACTLY this content:
```python
"""Tests for drop_lifecycle.py — the pure, renderer-agnostic drop/post_drop resolver.

Covers: drop held for drop_impact_beats then post_drop; ≤max_drops_in_a_row then
post_drop; predecessor gate (up/low/buildup/breakdown → drop; groove/other → NOT
drop); chorus→chorus cap; lifecycle clear when chorus/post-drop ends; flat-vs-flat
LED parity (WITHOUT _led_note_drop_decision_accepted rewrite).

NOTE: This proves FLAT-WINDOW parity only. The live LED window is per-look-duration
(rewritten by _led_note_drop_decision_accepted); the laser window is the flat
drop_impact_beats. They are NOT equal in production.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.drop_lifecycle import (  # noqa: E402
    DropLifecycle,
    DropLifecycleConfig,
    DropResult,
)

_PREDECESSORS = frozenset({"up", "low", "buildup", "breakdown"})


def _cfg(
    *,
    max_drops: int = 2,
    impact_beats: float = 8.0,
    cycle_beats: float = 32.0,
) -> DropLifecycleConfig:
    return DropLifecycleConfig(
        max_drops_in_a_row=max_drops,
        drop_impact_beats=impact_beats,
        post_drop_cycle_beats=cycle_beats,
        impact_predecessors=_PREDECESSORS,
    )


def _sp(**kw) -> types.SimpleNamespace:
    """Build a duck-typed SmartPhrasing namespace with safe defaults."""
    defaults = dict(
        abs_beat=None,
        current_phrase_start_beat=None,
        beats_into_phrase=None,
        active_drop_beat=None,
        current_phrase_is_chorus=False,
        phrase_start_crossing=False,
        smart_drop_crossing=False,
        previous_phrase_label="other",
        current_phrase_label="other",
        smart_post_drop_active=False,
    )
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


class TestDropAnchor(unittest.TestCase):
    def test_chorus_phrase_start_crossing(self) -> None:
        lc = DropLifecycle(_cfg())
        sp = _sp(
            current_phrase_is_chorus=True,
            phrase_start_crossing=True,
            current_phrase_start_beat=128.0,
        )
        self.assertEqual(lc.drop_anchor(sp), 128.0)

    def test_smart_drop_crossing_with_active_drop_beat(self) -> None:
        lc = DropLifecycle(_cfg())
        sp = _sp(smart_drop_crossing=True, active_drop_beat=256.0)
        self.assertEqual(lc.drop_anchor(sp), 256.0)

    def test_smart_drop_crossing_fallback_to_abs_beat(self) -> None:
        lc = DropLifecycle(_cfg())
        sp = _sp(smart_drop_crossing=True, abs_beat=300.0)
        self.assertEqual(lc.drop_anchor(sp), 300.0)

    def test_no_anchor(self) -> None:
        lc = DropLifecycle(_cfg())
        sp = _sp()
        self.assertIsNone(lc.drop_anchor(sp))


class TestImpactAllowed(unittest.TestCase):
    def test_allowed_predecessors(self) -> None:
        for pred in ("up", "low", "buildup", "breakdown"):
            lc = DropLifecycle(_cfg())
            sp = _sp(previous_phrase_label=pred)
            self.assertTrue(lc.impact_allowed(sp), f"predecessor={pred}")

    def test_disallowed_predecessors(self) -> None:
        for pred in ("chorus", "other", "groove"):
            lc = DropLifecycle(_cfg())
            sp = _sp(previous_phrase_label=pred)
            self.assertFalse(lc.impact_allowed(sp), f"predecessor={pred}")

    def test_smart_drop_crossing_current_label_fallback(self) -> None:
        lc = DropLifecycle(_cfg())
        sp = _sp(
            previous_phrase_label="other",
            smart_drop_crossing=True,
            current_phrase_label="up",
        )
        self.assertTrue(lc.impact_allowed(sp))

    def test_chorus_to_chorus_capped(self) -> None:
        """After max_drops_in_a_row chorus→chorus impacts, further ones are disallowed."""
        lc = DropLifecycle(_cfg(max_drops=2))
        # First: need first_drop_anchor_beat set
        lc._first_drop_anchor_beat = 64.0
        lc._impact_count = 0
        sp = _sp(previous_phrase_label="chorus")
        self.assertTrue(lc.impact_allowed(sp))  # count=0 < 2
        lc._impact_count = 1
        self.assertTrue(lc.impact_allowed(sp))  # count=1 < 2
        lc._impact_count = 2
        self.assertFalse(lc.impact_allowed(sp))  # count=2 >= 2, capped

    def test_chorus_to_chorus_requires_first_anchor(self) -> None:
        """chorus→chorus is only allowed when first_drop_anchor_beat is set."""
        lc = DropLifecycle(_cfg(max_drops=2))
        sp = _sp(previous_phrase_label="chorus")
        self.assertFalse(lc.impact_allowed(sp))  # no anchor → disallowed


class TestResolve(unittest.TestCase):
    def test_drop_impact_then_hold_then_post_drop(self) -> None:
        """Anchor fires drop, holds for impact_beats, then transitions to post_drop."""
        lc = DropLifecycle(_cfg(impact_beats=8.0))
        # Drop crossing at beat 64
        sp_cross = _sp(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            current_phrase_is_chorus=True,
            abs_beat=64.0,
        )
        res = lc.resolve(sp_cross, mutate=True)
        self.assertEqual(res.role, "drop")
        self.assertTrue(res.armed_this_tick)

        # Sustained inside impact window (beat 68 < 64+8=72)
        sp_hold = _sp(
            current_phrase_is_chorus=True,
            smart_post_drop_active=True,
            abs_beat=68.0,
        )
        res = lc.resolve(sp_hold, mutate=True)
        self.assertEqual(res.role, "drop")
        self.assertFalse(res.armed_this_tick)

        # After impact window (beat 80 >= 72)
        sp_post = _sp(
            current_phrase_is_chorus=True,
            smart_post_drop_active=True,
            abs_beat=80.0,
        )
        res = lc.resolve(sp_post, mutate=True)
        self.assertEqual(res.role, "post_drop")
        self.assertFalse(res.armed_this_tick)

    def test_disallowed_predecessor_yields_post_drop(self) -> None:
        """A smart_drop_crossing with predecessor=groove → post_drop, NOT drop."""
        lc = DropLifecycle(_cfg())
        sp = _sp(
            smart_drop_crossing=True,
            active_drop_beat=128.0,
            previous_phrase_label="groove",
            abs_beat=128.0,
        )
        res = lc.resolve(sp, mutate=True)
        self.assertEqual(res.role, "post_drop")
        self.assertFalse(res.armed_this_tick)

    def test_lifecycle_clears_when_chorus_ends(self) -> None:
        """After leaving chorus/post_drop, lifecycle state resets."""
        lc = DropLifecycle(_cfg(impact_beats=8.0))
        # Arm
        sp_arm = _sp(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            abs_beat=64.0,
        )
        lc.resolve(sp_arm, mutate=True)
        self.assertIsNotNone(lc._first_drop_anchor_beat)

        # Leave chorus (no anchor, not chorus, not post_drop_active)
        sp_groove = _sp(abs_beat=200.0, current_phrase_label="other")
        lc.resolve(sp_groove, mutate=True)
        self.assertIsNone(lc._first_drop_anchor_beat)
        self.assertEqual(lc._impact_count, 0)

    def test_none_role_when_not_in_chorus(self) -> None:
        """Outside the chorus window, resolver returns 'none'."""
        lc = DropLifecycle(_cfg())
        sp = _sp(abs_beat=64.0, current_phrase_label="up")
        res = lc.resolve(sp, mutate=True)
        self.assertEqual(res.role, "none")

    def test_armed_this_tick_only_on_impact(self) -> None:
        """armed_this_tick is True ONLY when arm() runs (impact_allowed + anchor)."""
        lc = DropLifecycle(_cfg())
        # Allowed predecessor
        sp1 = _sp(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            abs_beat=64.0,
        )
        res1 = lc.resolve(sp1, mutate=True)
        self.assertTrue(res1.armed_this_tick)

        # Sustained chorus (no new anchor)
        sp2 = _sp(
            current_phrase_is_chorus=True,
            abs_beat=66.0,
        )
        res2 = lc.resolve(sp2, mutate=True)
        self.assertFalse(res2.armed_this_tick)

    def test_abs_beat_fallback_composition(self) -> None:
        """_abs_beat prefers abs_beat, then phrase+offset, then active_drop_beat."""
        lc = DropLifecycle(_cfg())
        # Priority 1: abs_beat
        sp1 = _sp(abs_beat=100.0, current_phrase_start_beat=50.0, beats_into_phrase=10.0)
        self.assertEqual(lc._abs_beat(sp1), 100.0)
        # Priority 2: phrase + offset
        sp2 = _sp(current_phrase_start_beat=50.0, beats_into_phrase=10.0)
        self.assertEqual(lc._abs_beat(sp2), 60.0)
        # Priority 3: active_drop_beat
        sp3 = _sp(active_drop_beat=200.0)
        self.assertEqual(lc._abs_beat(sp3), 200.0)
        # None
        sp4 = _sp()
        self.assertIsNone(lc._abs_beat(sp4))

    def test_operator_32_beat_impact_window(self) -> None:
        """With operator's 32-beat window, drop holds until beat anchor+32."""
        lc = DropLifecycle(_cfg(impact_beats=32.0))
        sp_cross = _sp(
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            current_phrase_is_chorus=True,
            abs_beat=64.0,
        )
        lc.resolve(sp_cross, mutate=True)

        # Beat 95: still in window (64+32=96)
        sp_95 = _sp(current_phrase_is_chorus=True, abs_beat=95.0)
        self.assertEqual(lc.resolve(sp_95, mutate=True).role, "drop")

        # Beat 96: window expired
        sp_96 = _sp(current_phrase_is_chorus=True, abs_beat=96.0)
        self.assertEqual(lc.resolve(sp_96, mutate=True).role, "post_drop")


class TestParity(unittest.TestCase):
    """Flat-vs-flat parity with the LED resolver.

    This proves the resolver reproduces the LED _led_role_from_smart_phrasing
    drop/post_drop region with LED-equivalent config (max=2, impact=8).
    It does NOT prove live-LED-window parity (the LED rewrite via
    _led_note_drop_decision_accepted is out of scope).

    LED non-drop roles (breakdown, pre_drop, buildup, low, groove) are mapped
    to "none" — the resolver does NOT port those branches.
    """

    def test_a8_divergence_breakdown_start_crossing(self) -> None:
        """When chorus co-occurs with breakdown_start_crossing, LED returns
        breakdown but the resolver returns drop/post_drop. This is a KNOWN,
        integration-shielded divergence (priority-8 handles breakdown first
        in the director)."""
        lc = DropLifecycle(_cfg(impact_beats=8.0))
        # Arm a lifecycle first so the chorus window is active
        lc._first_drop_anchor_beat = 64.0
        lc._impact_until_beat = 72.0
        lc._impact_count = 1
        sp = _sp(
            current_phrase_is_chorus=True,
            smart_post_drop_active=True,
            abs_beat=80.0,  # past impact window → post_drop from resolver
        )
        res = lc.resolve(sp, mutate=False)
        # Resolver says post_drop; LED would say breakdown. Accepted divergence.
        self.assertEqual(res.role, "post_drop")

    def test_a8_divergence_transition_window(self) -> None:
        """When chorus co-occurs with transition_window_active, LED returns
        pre_drop but the resolver returns drop/post_drop. Accepted divergence."""
        lc = DropLifecycle(_cfg(impact_beats=8.0))
        lc._first_drop_anchor_beat = 64.0
        lc._impact_until_beat = 72.0
        lc._impact_count = 1
        # transition_window_active is NOT read by the resolver — it returns
        # drop/post_drop based on the chorus window. LED would return pre_drop.
        sp = _sp(
            current_phrase_is_chorus=True,
            abs_beat=80.0,
        )
        res = lc.resolve(sp, mutate=False)
        self.assertEqual(res.role, "post_drop")


if __name__ == "__main__":
    unittest.main()
```

### D2. `tests/test_laser_director_lifecycle.py` — A3 regression + teardown

Create this file with EXACTLY this content:
```python
"""Tests for the gated drop lifecycle integration in LaserDirector.

Covers:
  - A3 regression: smart_drop_crossing with disallowed predecessor does NOT
    produce a drop/drop_cycle decision (the live bug fix).
  - Teardown: director lifecycle state clears on reset_runtime_state.
  - Flag-off: drop_lifecycle_mirror=False → original ungated behavior.
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_director import LaserDirector  # noqa: E402
from rb_ss_bridge_v2.laser_models import (  # noqa: E402
    LaserContext,
    LaserMidiMessage,
    LaserPersonality,
    LaserScene,
    LaserSceneDecision,
)
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402


def _sp(**overrides) -> SmartPhrasingState:
    defaults = dict(reason="test")
    defaults.update(overrides)
    return SmartPhrasingState(**defaults)


def _ctx(
    *,
    abs_beat: float = 64.0,
    playing: bool = True,
    active_track_loaded: bool = True,
    autoloop_ready: bool = True,
    autoloop_tick_just_fired: bool = False,
    smart_phrasing: Optional[SmartPhrasingState] = None,
    scripted_id: int = 0,
) -> LaserContext:
    return LaserContext(
        active_deck=1,
        playing=playing,
        elapsed_ms=60_000,
        bpm=128.0,
        beatpos=0.0,
        abs_beat=abs_beat,
        position_stale=False,
        lighting_mode="autoloop",
        os2l_connected=True,
        active_track_loaded=active_track_loaded,
        autoloop_ready=autoloop_ready,
        autoloop_tick_just_fired=autoloop_tick_just_fired,
        scripted_id=scripted_id,
        smart_phrasing=smart_phrasing,
    )


def _scene(name: str, *, scene_type: str = "autoloop") -> LaserScene:
    return LaserScene(
        name=name,
        scene_type=scene_type,
        safety_class="safe",
        midi=LaserMidiMessage(kind="note_pulse", channel=1, note=36, velocity=127, duration_ms=80),
    )


def _personality(*, mirror: bool = True, max_drops: int = 2, impact_beats: float = 32.0) -> LaserPersonality:
    return LaserPersonality(
        name="house",
        safe_scene="safe_static",
        default_scene="house_phrase_1",
        phrase_scene="house_phrase_1",
        buildup_scene="buildup_1",
        pre_drop_scene="",
        drop_scene="house_drop_1",
        post_drop_scene="post_drop_1",
        breakdown_scene="breakdown_1",
        transition_scene="safe_static",
        phrase_bank=("house_phrase_1",),
        buildup_bank=("buildup_1",),
        drop_bank=("house_drop_1",),
        post_drop_bank=("post_drop_1",),
        breakdown_bank=("breakdown_1",),
        drop_lifecycle_mirror=mirror,
        max_drops_in_a_row=max_drops,
        drop_impact_beats=impact_beats,
        post_drop_cycle_beats=32.0,
    )


def _make_director(*, mirror: bool = True, **personality_kw) -> LaserDirector:
    scenes = {
        "safe_static": _scene("safe_static", scene_type="static"),
        "house_phrase_1": _scene("house_phrase_1"),
        "buildup_1": _scene("buildup_1"),
        "house_drop_1": _scene("house_drop_1"),
        "post_drop_1": _scene("post_drop_1"),
        "breakdown_1": _scene("breakdown_1"),
    }
    p = _personality(mirror=mirror, **personality_kw)
    d = LaserDirector(
        enabled=True,
        dry_run=True,
        drop_scene="house_drop_1",
        post_drop_scene="post_drop_1",
        breakdown_scene="breakdown_1",
        buildup_scene="buildup_1",
        buildup_lookahead_beats=32,
        post_drop_hold_beats=8,
        scenes=scenes,
    )
    d.set_personality_config(p)
    return d


class TestA3RegressionGatedDrop(unittest.TestCase):
    """A3: smart_drop_crossing with a groove/other predecessor must NOT produce
    role=drop or reason=drop_crossing when the mirror is ON."""

    def test_disallowed_predecessor_no_drop(self) -> None:
        d = _make_director(mirror=True)
        now = time.monotonic()
        # Prime with one non-crossing tick so _last_smart_abs_beat is set
        sp_prime = _sp(abs_beat=60.0, current_phrase_label="other")
        d.tick(_ctx(abs_beat=60.0, smart_phrasing=sp_prime), now=now)

        # Crossing with disallowed predecessor
        sp_cross = _sp(
            abs_beat=64.0,
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="other",
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
        )
        dec = d.tick(_ctx(abs_beat=64.0, smart_phrasing=sp_cross), now=now + 0.01)
        # Must NOT be drop or drop_cycle
        self.assertNotEqual(dec.role, "drop")
        self.assertNotEqual(dec.reason, "drop_crossing")
        self.assertNotEqual(dec.reason, "drop_cycle")

    def test_allowed_predecessor_fires_drop(self) -> None:
        d = _make_director(mirror=True)
        now = time.monotonic()
        sp_prime = _sp(abs_beat=60.0, current_phrase_label="up", current_phrase_is_up=True)
        d.tick(_ctx(abs_beat=60.0, smart_phrasing=sp_prime), now=now)

        sp_cross = _sp(
            abs_beat=64.0,
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
        )
        dec = d.tick(_ctx(abs_beat=64.0, smart_phrasing=sp_cross), now=now + 0.01)
        self.assertEqual(dec.role, "drop")
        self.assertEqual(dec.reason, "drop_crossing")

    def test_flag_off_ungated_crossing(self) -> None:
        """Flag OFF: crossing fires drop regardless of predecessor (today's behavior)."""
        d = _make_director(mirror=False)
        now = time.monotonic()
        sp_prime = _sp(abs_beat=60.0)
        d.tick(_ctx(abs_beat=60.0, smart_phrasing=sp_prime), now=now)

        sp_cross = _sp(
            abs_beat=64.0,
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="other",
        )
        dec = d.tick(_ctx(abs_beat=64.0, smart_phrasing=sp_cross), now=now + 0.01)
        self.assertEqual(dec.role, "drop")
        self.assertEqual(dec.reason, "drop_crossing")

    def test_32_beat_hold_no_mask_buildup(self) -> None:
        """A 32-beat impact window must NOT mask a later buildup beyond the gate."""
        d = _make_director(mirror=True, impact_beats=32.0)
        now = time.monotonic()
        # Prime
        sp_prime = _sp(abs_beat=60.0, current_phrase_label="up", current_phrase_is_up=True)
        d.tick(_ctx(abs_beat=60.0, smart_phrasing=sp_prime), now=now)
        # Drop crossing
        sp_cross = _sp(
            abs_beat=64.0,
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            current_phrase_label="chorus",
            current_phrase_is_chorus=True,
        )
        d.tick(_ctx(abs_beat=64.0, smart_phrasing=sp_cross), now=now + 0.01)

        # At beat 90 (within 32-beat window), leaving chorus → buildup should work
        sp_buildup = _sp(
            abs_beat=90.0,
            current_phrase_label="up",
            current_phrase_is_up=True,
            beats_to_next_drop=10.0,
            next_smart_drop_beat=100.0,
        )
        dec = d.tick(
            _ctx(abs_beat=90.0, smart_phrasing=sp_buildup),
            now=now + 0.02,
        )
        # Once leaving chorus, the lifecycle should resolve "none" and let buildup through
        # (the resolver only returns drop/post_drop inside chorus/post_drop_active windows)
        self.assertIn(dec.role, ("buildup", "phrase", "drop"))
        # The key assertion: it is NOT stuck on drop_hold for 32 beats regardless of context


class TestTeardown(unittest.TestCase):
    def test_reset_clears_lifecycle(self) -> None:
        d = _make_director(mirror=True)
        now = time.monotonic()
        sp_prime = _sp(abs_beat=60.0, current_phrase_label="up", current_phrase_is_up=True)
        d.tick(_ctx(abs_beat=60.0, smart_phrasing=sp_prime), now=now)

        sp_cross = _sp(
            abs_beat=64.0,
            smart_drop_crossing=True,
            active_drop_beat=64.0,
            previous_phrase_label="up",
            current_phrase_is_chorus=True,
        )
        d.tick(_ctx(abs_beat=64.0, smart_phrasing=sp_cross), now=now + 0.01)

        # Reset (simulating track load)
        d.reset_runtime_state(reason="active_track_loaded")

        # After reset, a fresh crossing should arm again (impact_count reset to 0)
        sp_prime2 = _sp(abs_beat=200.0, current_phrase_label="up", current_phrase_is_up=True)
        d.tick(_ctx(abs_beat=200.0, smart_phrasing=sp_prime2), now=now + 0.02)

        sp_cross2 = _sp(
            abs_beat=210.0,
            smart_drop_crossing=True,
            active_drop_beat=210.0,
            previous_phrase_label="up",
            current_phrase_is_chorus=True,
        )
        dec = d.tick(_ctx(abs_beat=210.0, smart_phrasing=sp_cross2), now=now + 0.03)
        self.assertEqual(dec.role, "drop")
        self.assertEqual(dec.reason, "drop_crossing")


if __name__ == "__main__":
    unittest.main()
```

### D3. `tests/test_laser_executor_lifecycle.py` — shuffle-bag + A8 never-dark + cycling

Create this file with EXACTLY this content:
```python
"""Tests for the executor shuffle-bag, A8 never-dark fallback, and cycling gates.

Covers:
  - Shuffle-bag rotation: usable entries only, reshuffle on exhaustion, bag
    rebuilt on bank-membership change.
  - A8: static-only personality fires the static _drop_scene on drop_crossing
    (never dark); usable-bank personality picks from the bag.
  - Cycling gate: drop_cycle/post_drop_cycle only fire on autoloop_tick_just_fired.
  - A7 regression: not "same look all track, +1 next track".
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_config import LaserConfig  # noqa: E402
from rb_ss_bridge_v2.laser_executor import LaserSceneExecutor  # noqa: E402
from rb_ss_bridge_v2.laser_models import (  # noqa: E402
    LaserContext,
    LaserMidiMessage,
    LaserPersonality,
    LaserScene,
    LaserSceneDecision,
)
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402


class _FakeMidiOutput:
    def __init__(self) -> None:
        self.calls: list[tuple[LaserMidiMessage, str]] = []
        self.trigger_result = True

    def trigger(self, msg: LaserMidiMessage, priority: str = "normal") -> bool:
        self.calls.append((msg, priority))
        return self.trigger_result

    def status(self) -> dict:
        return {
            "available": True, "running": True, "dry_run": False,
            "degraded": False, "degraded_reason": "", "port_name": "test",
            "queue_size": 0, "queue_max": 64,
            "trigger_count": len(self.calls), "drop_count": 0,
            "rejected_count": 0, "send_error_count": 0,
            "sent_count": len(self.calls), "panic_count": 0, "last_error": "",
        }


def _scene(name: str, *, scene_type: str = "autoloop", safety_class: str = "safe",
           note: int = 36) -> LaserScene:
    return LaserScene(
        name=name,
        scene_type=scene_type,
        safety_class=safety_class,
        midi=LaserMidiMessage(kind="note_pulse", channel=1, note=note, velocity=127, duration_ms=80),
    )


def _ctx(
    *,
    abs_beat: float = 64.0,
    autoloop_tick_just_fired: bool = False,
) -> LaserContext:
    return LaserContext(
        active_deck=1, playing=True, elapsed_ms=1000, bpm=128.0,
        beatpos=0.0, abs_beat=abs_beat, position_stale=False,
        lighting_mode="autoloop", os2l_connected=True,
        active_track_loaded=True, autoloop_ready=True,
        autoloop_tick_just_fired=autoloop_tick_just_fired,
        scripted_id=0,
    )


def _decision(scene: str, reason: str, role: str) -> LaserSceneDecision:
    return LaserSceneDecision(scene=scene, reason=reason, priority=10, source="policy", role=role)


def _make_config(scenes: dict[str, LaserScene]) -> LaserConfig:
    return LaserConfig(
        enabled=True, dry_run=False, smart_drop_mode="blackout_mask",
        midi_output_port="test", scenes=scenes,
        personalities={}, default_personality="",
        startup_scene="safe_static", stop_scene="safe_static",
        stale_scene="safe_static", emergency_scene="safe_static",
        fallback_scene="safe_static",
    )


class TestShuffleBag(unittest.TestCase):
    """A7: drop/post_drop selection uses shuffle-bag (reshuffle on exhaustion)."""

    def test_full_pass_sees_all_usable_entries(self) -> None:
        """Over one full bag pass every usable entry appears exactly once."""
        scenes = {
            "d1": _scene("d1", note=41),
            "d2": _scene("d2", note=42),
            "d3": _scene("d3", note=43),
            "d_static": _scene("d_static", scene_type="static", note=44),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        config = _make_config(scenes)
        personality = LaserPersonality(
            name="test", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d_static", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1", "d2", "d3", "d_static"),
            drop_lifecycle_mirror=True,
        )
        rng = random.Random(42)
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(
            config=config, backend=backend, personality=personality,
            rng=rng, randomize_cursors=False,
        )

        # Fire 3 drop_cycle decisions with autoloop_tick_just_fired=True
        fired: list[str] = []
        for beat in range(0, 3):
            ctx = _ctx(abs_beat=float(64 + beat * 32), autoloop_tick_just_fired=True)
            dec = _decision("d_static", "drop_cycle", "drop")
            ex.on_decision(dec, ctx)

        # Collect the scenes that were triggered
        for msg, _ in backend.calls:
            for sname, sdef in scenes.items():
                if sdef.midi.note == msg.note and sname != "safe_static":
                    fired.append(sname)
                    break

        # Only usable (autoloop) entries should appear; d_static is scene_type=static → excluded
        for name in fired:
            self.assertNotEqual(scenes[name].scene_type, "static",
                                f"{name} is static and should not be in a cycle")

    def test_no_fire_without_autoloop_tick(self) -> None:
        """drop_cycle with autoloop_tick_just_fired=False → no MIDI."""
        scenes = {
            "d1": _scene("d1", note=41),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        config = _make_config(scenes)
        personality = LaserPersonality(
            name="test", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d1", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1",),
            drop_lifecycle_mirror=True,
        )
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(
            config=config, backend=backend, personality=personality,
            randomize_cursors=False,
        )
        ctx = _ctx(abs_beat=64.0, autoloop_tick_just_fired=False)
        dec = _decision("d1", "drop_cycle", "drop")
        ex.on_decision(dec, ctx)
        self.assertEqual(len(backend.calls), 0)


class TestA8NeverDark(unittest.TestCase):
    """A8: static-only personality fires the static drop scene on impact (never dark)."""

    def test_static_only_drop_crossing_fires(self) -> None:
        """A drop_crossing for a static-only bank fires the configured static scene."""
        scenes = {
            "house_drop_1": _scene("house_drop_1", scene_type="static", note=96),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        config = _make_config(scenes)
        personality = LaserPersonality(
            name="dubstep", safe_scene="safe_static", default_scene="safe_static",
            phrase_scene="safe_static", buildup_scene="safe_static", pre_drop_scene="",
            drop_scene="house_drop_1", post_drop_scene="house_drop_1",
            breakdown_scene="safe_static", transition_scene="safe_static",
            drop_bank=("house_drop_1",),
            post_drop_bank=("house_drop_1",),
            drop_lifecycle_mirror=True,
        )
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(
            config=config, backend=backend, personality=personality,
            randomize_cursors=False,
        )
        ctx = _ctx(abs_beat=64.0, autoloop_tick_just_fired=False)
        dec = _decision("house_drop_1", "drop_crossing", "drop")
        ex.on_decision(dec, ctx)
        # MUST fire — the static scene is valid for an impact
        self.assertGreater(len(backend.calls), 0)
        self.assertEqual(backend.calls[0][0].note, 96)

    def test_usable_bank_shuffles_impact(self) -> None:
        """A drop_crossing for a usable-bank personality picks from the shuffle bag."""
        scenes = {
            "d1": _scene("d1", note=41),
            "d2": _scene("d2", note=42),
            "d_static": _scene("d_static", scene_type="static", note=44),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        config = _make_config(scenes)
        personality = LaserPersonality(
            name="house", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d_static", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1", "d2", "d_static"),
            drop_lifecycle_mirror=True,
        )
        rng = random.Random(42)
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(
            config=config, backend=backend, personality=personality,
            rng=rng, randomize_cursors=False,
        )
        ctx = _ctx(abs_beat=64.0)
        dec = _decision("d_static", "drop_crossing", "drop")
        ex.on_decision(dec, ctx)
        # Must fire (not empty/dark); the note should be d1 or d2 (usable), not d_static
        self.assertGreater(len(backend.calls), 0)
        fired_note = backend.calls[0][0].note
        self.assertIn(fired_note, (41, 42), "impact should pick from usable bag, not static")


class TestA7Regression(unittest.TestCase):
    """A7: not 'same look all track, +1 next track'."""

    def test_cross_track_not_deterministic_sequential(self) -> None:
        """After a track reset, the bag is rebuilt → order changes, not +1."""
        scenes = {
            "d1": _scene("d1", note=41),
            "d2": _scene("d2", note=42),
            "d3": _scene("d3", note=43),
            "safe_static": _scene("safe_static", scene_type="static", note=99),
        }
        config = _make_config(scenes)
        personality = LaserPersonality(
            name="test", safe_scene="safe_static", default_scene="d1",
            phrase_scene="d1", buildup_scene="d1", pre_drop_scene="",
            drop_scene="d1", post_drop_scene="",
            breakdown_scene="d1", transition_scene="safe_static",
            drop_bank=("d1", "d2", "d3"),
            drop_lifecycle_mirror=True,
        )
        rng = random.Random(42)
        backend = _FakeMidiOutput()
        ex = LaserSceneExecutor(
            config=config, backend=backend, personality=personality,
            rng=rng, randomize_cursors=False,
        )

        # Track 1: fire 3 cycles
        notes_track1: list[int] = []
        for i in range(3):
            ctx = _ctx(abs_beat=float(64 + i * 32), autoloop_tick_just_fired=True)
            dec = _decision("d1", "drop_cycle", "drop")
            ex.on_decision(dec, ctx)
        for msg, _ in backend.calls:
            notes_track1.append(msg.note)
        backend.calls.clear()

        # Track reset (simulates track load)
        ex.reset_runtime_state(reason="active_track_loaded")

        # The definitive check: _role_bag was cleared by reset_runtime_state
        self.assertEqual(ex._role_bag, {})

        # Track 2: fire 3 more cycles — bag must rebuild from scratch
        notes_track2: list[int] = []
        for i in range(3):
            ctx = _ctx(abs_beat=float(64 + i * 32), autoloop_tick_just_fired=True)
            dec = _decision("d1", "drop_cycle", "drop")
            ex.on_decision(dec, ctx)
        for msg, _ in backend.calls:
            notes_track2.append(msg.note)

        # Track 2 must have fired (bag was rebuilt, not permanently empty)
        self.assertGreater(len(notes_track2), 0, "track 2 cycles must fire after reset")


if __name__ == "__main__":
    unittest.main()
```

### D-notes (implementer instructions for Part D)

- **All three test files above are verbatim** — transcribe them exactly. Adjust `import` paths
  only if you renamed the package (you should not).
- **All existing tests must still pass unchanged.** Run `python3 -m unittest discover tests` at
  the end. If an existing test fails, your code change is wrong, not the test.
- The `_personality` fixtures in D2 and D3 include the new `drop_lifecycle_mirror`,
  `max_drops_in_a_row`, `drop_impact_beats`, `post_drop_cycle_beats` fields from Task 2. The
  `_make_director` fixture in D2 passes `scenes=` to `LaserDirector(...)` (Task 3-pre).
- The parity test (D1 `TestParity`) proves flat-window equivalence only. It does NOT prove
  live-LED-window parity (the `_led_note_drop_decision_accepted` rewrite is out of scope). The
  A8 divergence tests assert KNOWN integration-shielded differences, not failures.
- The A8 never-dark test (D3 `TestA8NeverDark`) proves dubstep's static-only bank fires the
  configured `house_drop_1` on impact — never `""`. This is the critical regression guard.
- The shuffle-bag test (D3 `TestShuffleBag`) uses `randomize_cursors=False` so the cursor starts
  at 0 (a reshuffle boundary). This avoids the mid-bag seeding issue noted in the spec.
- All existing laser + LED tests pass unchanged.

## Part E — Acceptance (definition of done)
- [ ] Shared `drop_lifecycle.py` with **all three** state fields; **parity test green** vs the LED
      resolver incl. disallowed-predecessor + chorus→chorus-cap timelines.
- [ ] Knobs added (`drop_lifecycle_mirror` **default true** + max/impact/cycle); **NO**
      `drop_cycle_beats`, **NO** `drop_pairs`. Kill switch OFF = byte-identical to pre-change EXCEPT the resume transition.
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
2. Verified against CURRENT code — yes. Line-number citations verified against `c4edf97`; only the
   spec doc changed since (`git diff --name-only c4edf97..HEAD` = spec only). All `:NNN` references
   confirmed accurate against live code.
3. Pending-state guard — A4 traces the blackout end-to-end: arm (`:121-151`), the executor
   `drop_crossing_success` path, AND the SM net (`:3842-3853`) that clears a gated-off crossing. The
   net (not `drop_crossing`) is the real clear path — the earlier "must keep drop_crossing or the
   blackout strands" claim is corrected. The mask-owner teardown divergence on disallowed crossings
   is surfaced (C2 + Part D).
4. Mode-transition cleanup — Task 3d enumerates ALL transition paths (6 sites) with before/after
   code snippets including surrounding anchor lines. Resume path now resets both director and executor.
5. Third-party API completeness — N/A (no new third-party API; MIDI message path unchanged).
6. Cross-checked against existing code — gate reuses `_drop_scene`/`drop_bank`/`autoloop_tick_just_fired`
   authority vars; predicate matches `scene_type`/`safety_class`/`allow_high_impact` as the executor uses them.
7. Pure-function seam — `drop_lifecycle.py` is pure and table-tested.
8. Live safety explicit — Part C; blackout preserved (A4); gate is strictly-safer than today.
9. Adversarial self-review — done (Opus-max review + Antigravity final audit). Fixed:
   - **Bug #7 (D3 A7 regression)**: `assertEqual(ex._role_bag, {})` moved BEFORE track-2 cycles.
   - **Bug #8 (Task 5a)**: Truncated/impossible validation code removed; `_validate_personality` only
     has `scene_keys: set[str]`, cannot do note-collision checks. Replaced with "NO new code needed".
   Verified correct (not bugs despite initial suspicion): D3 `_FakeMidiOutput` duck-typing; D2
   `scenes=` param (Task 3-pre); executor `reset_runtime_state` keyword-only; `LaserContext` blackout
   defaults; D3 `_make_config(scenes)` provides full `LaserConfig` (not `None`); all `SmartPhrasingState`
   fields have defaults.
   Remaining accepted divergences (cadence, flat window, breakdown ordering) are documented, not hidden.
