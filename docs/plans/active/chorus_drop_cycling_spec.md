---
doc_status: active-plan
truth_level: code-grounded
last_verified_commit: HEAD
last_verified_date: 2026-06-22
validation_scope: spec only; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — Laser drop/post-drop/chorus lifecycle (mirror the LED engine)

> **Live-critical / plan-first.** Changes live autoloop+laser selection during a show.
> Implement exactly, commit after each task, keep new behavior behind an **opt-in flag,
> default OFF**. The goal: the **laser** drop/post-drop/chorus behavior **mirrors the LED
> engine's existing, battle-tested state machine** — with the operator's configurable values.

## Operator intent (authoritative)
Mirror the LED engine for `drop` / `post_drop` / chorus on the **laser**:
- A drop look holds for a configurable number of beats, **then** goes to `post_drop`, which
  **cycles within the chorus**.
- At most **N drop looks in a row** (LED uses 2), then settle into `post_drop`.
- If **no post_drop looks are mapped**, **default to (cycle) drop looks**.
- Operator's laser values: **drop impact = 32 beats** (LED default 8), **drops cycle every
  32 beats**, **post_drop cycle = 32 beats**. **Everything configurable.**
- The drop autoloop arm and the laser look are the **same MIDI note** to SoundSwitch.

## Part A — Context & root cause (verified; read, do not implement)

### A1. What the laser does today (the gap)
- [confirmed] Laser role is decided by `LaserDirector._decide` (`laser_director.py:293`):
  drop_crossing fires the drop **once** (`:439`), a fixed post-drop **hold**
  (`post_drop_hold_beats`) at `:453-477`, then it **falls through to groove**
  (`_decide_phrase_default`, `:538`). There is **no** drop-look cycling, no "N drops in a
  row", no chorus-driven post_drop cycling, and no no-post_drop fallback. `drop` is not a
  refire role (`laser_executor.py:181` `refire_roles=("phrase","buildup","breakdown")`).
- [confirmed] The laser executor rotates a bank only for `role=="phrase"` (`:388-394`);
  other auto roles hold the latched scene (`:396-399`). Bank rotation primitive exists:
  `_choose_bank_scene_locked` (`:401`) over `_bank_for_role` (`:435`); `drop_bank` exists
  (`laser_models.py:98`).

### A2. The LED engine to MIRROR (authoritative source-of-truth — verified)
The LED engine already implements exactly the requested lifecycle, in **`state_manager.py`**
(not the LED director, which only maps a given role→look). Mirror this:
- [confirmed] Constants (`state_manager.py:132-138`): `LED_DEFAULT_DROP_IMPACT_BEATS = 8.0`,
  `LED_MAX_DROP_IMPACTS = 2` ("up to two drop hits in a row, then post_drop"),
  `LED_DEFAULT_POST_DROP_CYCLE_BEATS = 32.0`,
  `_LED_DROP_IMPACT_PREDECESSORS = {"up","low","buildup","breakdown"}`.
- [confirmed] **Role resolver** `_led_role_from_smart_phrasing` (`state_manager.py:2222`):
  - `_led_drop_marker_anchor` (`:2273`): a drop anchor exists on a **chorus phrase-start
    crossing** or a `smart_drop_crossing`.
  - At a drop anchor: if `_led_drop_impact_allowed` (`:2283` — predecessor in the set, or a
    chorus→chorus impact while `_led_drop_impact_count < LED_MAX_DROP_IMPACTS`) → arm the
    lifecycle (`_led_arm_drop_lifecycle`, `:2312`: `impact_until = anchor + duration`,
    `impact_count += 1`) and return `"drop"`; else return `"post_drop"`.
  - While `current_phrase_is_chorus or smart_post_drop_active` (`:2248-2256`): return
    `"drop"` while `abs_beat < _led_drop_impact_until_beat` (still inside the impact
    duration), else `"post_drop"`.
  - `_led_drop_lifecycle_should_clear` (`:2305`) clears state when chorus/post-drop ends.
- [confirmed] **Per-look duration + paired post_drop**: `led_look_director.drop_duration_beats(look)`
  and `paired_post_drop_look(look)` resolve from `LEDConfig.drop_pairs`
  (`led_models.py:194`, `{drop_look -> {post_drop, duration_beats}}`); `post_drop_cycle_beats`
  defaults `32.0` (`led_models.py:195`). `_led_note_drop_decision_accepted` (`:2321`) sets
  `impact_until = anchor + drop_duration_beats(look)`.
- [confirmed] **Post-drop cycling**: cycle index = `elapsed // post_drop_cycle_beats`
  (`state_manager.py:2468`); the changing cycle advances the role cursor → rotates looks.
- [confirmed] **No-post_drop fallback**: `_led_role_has_mapped_look`/`has_role_look`
  (`state_manager.py:2213`, `led_look_director.py:191`) lets the caller fall back when a
  role has no mapped look. Mirror as: post_drop with no mapped look → keep cycling `drop`.

### A3. MIDI mapping must stay synced — BACKEND + FRONTEND (verified; operator-critical)
The operator explicitly requires the laser MIDI mapping stay synced across backend and
frontend. The cyclable banks are the operator's to define; the code must work with them as
configured and the mapping must be consistent across all surfaces:
- [confirmed] **Backend — scene catalog** `config/laser_director.json` `scenes`: contains
  both `autoloop` drop/post_drop scenes (cyclable) and `static` ones (one-shot hits), each
  with its own MIDI note. A bank may legitimately contain a mix; the cycler uses only the
  autoloop/allowed entries (see Task 4) — **the operator's bank membership is not changed.**
- [confirmed] The executor gates a refire on `scene_def.scene_type=="autoloop"`
  (`laser_executor.py:187`) and `allow_high_impact` (`:172-179`); some personalities have an
  empty `post_drop_bank`, which is fine — it routes to the no-post_drop fallback (cycle drops).
- [confirmed] **Frontend (a) — laser_pad UI**: `config/laser_director.json` `_pad_meta`
  (`banks`, `note_labels`, `ui`) — note labels must match the scene catalog notes.
- [confirmed] **Frontend (b) — SoundSwitch project**: each note a bank can send must map to
  the intended autoloop in the bounded RAVE project and be in the exported pack.
  `~/vln_ss_analysis/soundswitch_laser_cues.json` is keyed by cue/fixture/dmx, **not** MIDI
  note, so this check is in SoundSwitch's MIDI mapping / the pack, not that file.
- [confirmed] No tool cross-checks bridge notes vs pad/SoundSwitch (`tools/` has none).

### A4. Assumptions for Codex to confirm
- [assumed] Changing the laser role's fired note is sufficient for SoundSwitch to cycle the
  autoloops (scene note IS the SS trigger; `autoloop_controller` only beat-syncs). **Confirm**
  no parallel groove-autoloop arm fires on an autoloop tick that would fight the drop note.
- [assumed] The LED resolver's `SmartPhrasingState` fields (`current_phrase_is_chorus`,
  `smart_post_drop_active`, `smart_drop_crossing`, `phrase_start_crossing`,
  `previous_phrase_label`, `current_phrase_start_beat`, `active_drop_beat`, `abs_beat`,
  `beats_to_next_drop`) are all available to `LaserDirector._decide` via its `LaserContext`/
  smart-phrasing snapshot. **Confirm**; if a field is missing on the laser path, surface it
  (do not silently diverge from the LED logic).

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- New behavior **OFF by default**; with it off, laser output is byte-for-byte unchanged.
- **Do not** change LED runtime behavior. (Task 1 extracts a pure resolver and proves it
  equals today's LED logic; the live LED path keeps working.)
- **Do not** modify the operator's `personalities` / `drop_bank` / `post_drop_bank` /
  `scenes` / `_pad_meta` in `config/laser_director.json`. The code must work with the banks
  **as they are**; never auto-curate, reorder, or repopulate the operator's banks.
- **Do not** modify `smart_phrasing.py`, `autoloop_controller.py`, `smart_rearm.py`, the
  push loop's threading, SoundSwitch pack code, or Govee modules.
- Follow AGENTS.md §7: this is the `laser` (and touches `led_govee`) change-contract — update
  the docs those contracts list and run §8 hard checks.

### Task 1 — Extract a SHARED pure drop-lifecycle resolver (parity-proven against LED)
Create `drop_lifecycle.py`: a pure, I/O-free resolver that reproduces
`_led_role_from_smart_phrasing` + its helpers (`_led_drop_marker_anchor`,
`_led_drop_impact_allowed`, `_led_arm_drop_lifecycle`, `_led_drop_lifecycle_should_clear`,
`_led_note_drop_decision_accepted` timing) as a small state object parameterized by a config:
```
DropLifecycleConfig(
    max_drops_in_a_row: int,           # = LED_MAX_DROP_IMPACTS default 2
    drop_impact_beats: float,          # default per-look; flat fallback (operator: 32.0)
    post_drop_cycle_beats: float,      # default 32.0
    impact_predecessors: frozenset,    # = {"up","low","buildup","breakdown"}
    drop_duration_for_look: Callable[[str], float] | None,  # per-look override (drop_pairs)
    has_post_drop_look: Callable[[], bool],                  # no-post_drop fallback -> "drop"
)
DropLifecycle.resolve_role(sp_like, *, mutate) -> str   # "drop"|"post_drop"|... mirrors :2222
```
The resolver must NOT import bridge runtime modules; it takes a small struct of the
SmartPhrasing fields listed in A4. **Parity test (Task D)** asserts it returns the same role
sequence as the current `state_manager` LED logic across a battery of phrase timelines, so
"mirror exactly" is proven, not asserted. (Refactoring the live LED path to call this is an
optional follow-up, explicitly out of scope here to avoid LED regression.)

### Task 2 — `laser_models.py` + `laser_config.py`: configurable knobs (opt-in)
Add to the laser personality (near `drop_style`, `laser_models.py:~110`), all defaulting so
the feature is OFF / inert:
- `drop_lifecycle_mirror: bool = False`  (master opt-in)
- `max_drops_in_a_row: int = 2`
- `drop_impact_beats: float = 32.0`      (operator value; per-look override via drop_pairs below)
- `post_drop_cycle_beats: float = 32.0`
- `drop_cycle_beats: float = 32.0`       (how often a sustained drop rotates to the next look)
- optional `drop_pairs: dict[str,{post_drop:str,duration_beats:float}]` mirroring LED, so a
  drop look can name its paired post_drop look + its own duration.
Validate in `laser_config.py` (mirror `drop_style`/`post_drop_hold_beats` parsing, `:57-73`):
types/ranges, every referenced look exists in `scenes`, positive beats. Unknown → defaults.

### Task 3 — `laser_director.py`: drive the mirrored lifecycle
- In `__init__`/personality-reload (`:102`, `:197`), read the new knobs and build a
  `DropLifecycle` with `drop_duration_for_look` → personality drop_pairs (fallback flat
  `drop_impact_beats`) and `has_post_drop_look` → personality `post_drop_bank` non-empty.
- In `_decide`, when `drop_lifecycle_mirror` is **on**, replace the drop_crossing →
  post_drop_hold → fall-through region (`:432-543`) with role from
  `lifecycle.resolve_role(sp, mutate=True)`:
  - `"drop"` → `LaserSceneDecision(scene=self._drop_scene, reason="drop_cycle",
    role="drop", priority=9, source="policy")`
  - `"post_drop"` → `LaserSceneDecision(scene=self._post_drop_scene or self._drop_scene,
    reason="post_drop_cycle", role="post_drop", priority=10, source="policy")`
  - other roles (breakdown/pre_drop/buildup/groove) → existing branches / `_decide_phrase_default`.
  When the flag is **off**, the existing code path runs unchanged.
- No-post_drop fallback: if `resolve_role` returns `"post_drop"` but `has_post_drop_look()`
  is false, emit `role="drop" reason="drop_cycle"` instead (mirror the LED fallback).

### Task 4 — `laser_executor.py`: refire + rotate drop and post_drop on the cycle cadence
1. Make `drop` and `post_drop` refire-eligible **only** for the new reasons. Replace
   `refire_allowed` (`:182-189`):
   ```python
   cycling = decision.reason in ("drop_cycle", "post_drop_cycle")
   refire_allowed = (
       ctx.autoloop_tick_just_fired
       and (role in refire_roles or (cycling and role in ("drop", "post_drop")))
       and scene_def.scene_type == "autoloop"
       and (last_role_trigger_beat < 0.0 or float(ctx.abs_beat) > last_role_trigger_beat)
   )
   ```
2. In `_select_scene` (`:375`), for `role in ("drop","post_drop")` with a cycling reason:
   fire **only** on `ctx.autoloop_tick_just_fired` and **rotate** the role's bank via
   `_choose_bank_scene_locked(role=role, fallback_scene=decision.scene)` (mirror the phrase
   branch). Leave `drop_crossing`/`drop_hold` paths (flag-off) untouched.
   **Skip non-cyclable bank entries at runtime — do NOT require the operator to curate banks.**
   A bank may contain `static` or high-impact-disallowed scenes; when rotating, advance the
   cursor past any entry whose `scenes` def is not `scene_type=="autoloop"` (or is high-impact
   while `allow_high_impact` is false) and pick the next usable one, bounded by one full pass
   over the bank. If no usable scene exists in the bank this tick, no-op (no MIDI) and let the
   no-post_drop fallback / next tick handle it — never send an unmapped/one-shot note as a
   cycle.
   The 32-beat rotation cadence comes from `autoloop_tick_just_fired` (interval=
   `AUTOLOOP_ARM_PHRASE_BEATS=32`, `state_manager.py:3756`) plus marker boundaries — both
   are the requested cadence; no new timer.

### Task 5 — Keep the laser MIDI mapping synced (BACKEND + FRONTEND)
> **Do not curate, reorder, or repopulate the operator's banks/personalities.** The operator
> defines bank membership; the runtime handles whatever is there (Task 4 skips non-cyclable
> entries; an empty `post_drop_bank` uses the no-post_drop fallback). Task 5 is about keeping
> the **note mapping consistent**, not about changing what's in the banks.
5a. **Mapping integrity validation** (`laser_config.py`): when `drop_lifecycle_mirror` is on,
verify every scene **referenced by** `drop_bank`/`post_drop_bank`/`drop_pairs` exists in
`scenes` with a MIDI note, and that there are **no note collisions** across banks. Surface a
clear error for a truly broken mapping (missing scene / missing note / collision). For a bank
that simply contains non-cyclable entries (static / high-impact-disallowed) or an empty
`post_drop_bank`, **do not error** — that is a valid operator choice handled at runtime; at
most emit an informational log noting which entries won't cycle. Never block load over bank
composition.
5b. **Frontend (a) — `_pad_meta`**: if Codex changes any scene's note (it should not need
to), update `_pad_meta` `note_labels`/`banks` in the same commit. Otherwise leave as-is.
5c. **Frontend (b) — sync checker** `tools/check_laser_midi_sync.py` (new, pure core + CLI,
read-only): print every drop/post_drop bank note → bridge scene (type/safety) → pad label →
SoundSwitch autoloop, and **exit non-zero** only on a genuine mapping break: a bank note not
mapped in SoundSwitch, a note collision across banks, or a bank entry missing from `scenes`.
A non-cyclable (static/high-impact) entry is reported as **info**, not a failure. Pure
`reconcile(config_dict, ss_map) -> list[issue]` unit-tested with fixtures. Never mutates
SoundSwitch or the config. This is the operator-facing backend↔frontend sync check.
5d. **Operator step (doc, not code)**: in the bounded SoundSwitch project confirm each
drop/post_drop note triggers the intended autoloop, and re-export the pack (exporter pins the
project UUID — adding/renaming autoloops needs a re-export). Operator-run, optional.

## Part C — Invariants that MUST still hold (live safety)
1. **Default-off = no change.** `drop_lifecycle_mirror=False` → identical laser output/MIDI.
2. **No arm spam.** Cycling MIDI fires **only** on `ctx.autoloop_tick_just_fired`.
3. **Smart Drop blackout preserved.** Blackout arm is raised only by Smart Drop / smart
   phrasing at drop/transition events (`state_manager.py:3799,4126`), not on cycle ticks; do
   not change blackout. Real-drop blackout behaves exactly as today.
4. **N-in-a-row honored.** No more than `max_drops_in_a_row` consecutive drop impacts before
   `post_drop` (mirror `LED_MAX_DROP_IMPACTS`), with the same predecessor allowances.
5. **No-post_drop fallback.** A personality with no mapped post_drop look cycles drops (never
   emits a `post_drop` with no look → no blackout/idle gap).
6. **No push-loop I/O.** Resolver is pure; decision logic only.
7. **Clean teardown.** Drop lifecycle state resets on track/deck change, stop, resume,
   scripted, idle (mirror `_led_drop_lifecycle_should_clear` / `clear_queued_post_drop`); no
   leak across tracks. `role_changed` clears the previous role's active scene.
8. **Don't touch arm/BPM.** `autoloop_controller` arm/sync/BPM-follow untouched.
9. **MIDI-mapping integrity (no curation).** The operator's banks/personalities are never
   modified. Every note a bank can send maps end-to-end (catalog ↔ `_pad_meta` ↔ SoundSwitch);
   a genuine mapping break (missing scene/note, cross-bank collision) is surfaced, but a
   non-cyclable entry or empty `post_drop_bank` is valid and handled at runtime, never an
   error. The runtime never sends a wrong/unmapped note as a cycle.
10. **LED unchanged.** The live LED path keeps its current behavior; the shared resolver is
    proven equal by the Task-D parity test.

## Part D — Tests (pure-function seam; no files/subprocess)
- `tests/test_drop_lifecycle.py`: the resolver, table-driven over phrase timelines —
  drop held `drop_impact_beats` then post_drop; ≤`max_drops_in_a_row` drops in a row then
  post_drop; predecessor up/low/buildup/breakdown → drop; chorus→chorus impacts capped;
  no-post_drop → drop fallback; lifecycle clears when chorus/post-drop ends.
- **Parity test**: assert the resolver's role sequence equals the current
  `state_manager` LED resolver (`_led_role_from_smart_phrasing`) across the same timelines
  with LED-equivalent config (max=2, impact=8, cycle=32) — proves the mirror.
- `tests/test_laser_director*.py`: flag on → `_decide` emits `drop_cycle`/`post_drop_cycle`
  roles per the resolver; flag off → unchanged; real drop_crossing/post_drop_hold unchanged
  when off.
- `tests/test_laser_executor*.py`: `drop_cycle`/`post_drop_cycle` decisions with
  `autoloop_tick_just_fired=True` rotate the respective bank and fire MIDI each tick; with
  it False → no MIDI; hold→cycle handoff fires the first cycled look on the first tick after
  the impact window; release to groove on chorus end.
- All existing laser + LED tests pass unchanged.

## Part E — Acceptance (definition of done)
- [ ] Shared `drop_lifecycle.py` resolver added; **parity test green** vs the LED resolver.
- [ ] Laser knobs added (`drop_lifecycle_mirror` off by default + max/impact/cycle/pairs);
      flag OFF = no laser behavior change (existing suite green).
- [ ] Flag ON: laser mirrors the LED lifecycle — drop held `drop_impact_beats` (operator 32)
      → post_drop cycling every `post_drop_cycle_beats` (32) within chorus; ≤`max_drops_in_a_row`
      (2) drops in a row; drops rotate every `drop_cycle_beats` (32); no-post_drop → cycle
      drops. All values configurable.
- [ ] Smart Drop blackout + real drop_crossing/post_drop_hold behavior unchanged.
- [ ] **MIDI synced (backend+frontend), banks untouched:** operator personalities/banks are
      not modified; runtime skips non-cyclable entries and uses the no-post_drop fallback;
      every bank note maps end-to-end with no collisions; `tools/check_laser_midi_sync.py`
      exits 0 vs SoundSwitch (non-cyclable entries reported as info, not failure).
- [ ] A4 assumptions confirmed in writing.
- [ ] `python3 -m unittest discover tests` green; AGENTS.md §8 hard checks green; `laser`
      (+`led_govee`) change-contract docs updated. No push/tick-path I/O added.

## When you finish
- Commit per task with real messages. Report: files touched, parity-test result, the
  resolved A4 answers, the sync-checker output, and confirmation flag-off is a no-op.

## Note — T7d capture interaction (operator, not Codex)
This adds new transition patterns (drop/post_drop cycling in chorus). The **live
SoundSwitch-rendered path is unaffected**. The future **native-DMX (T7d)** path has no
phase-contract evidence for these patterns yet, so it will **safe-zero** them until captured
(never renders them wrong). Add a `drop-cycle`/`post_drop-cycle` capture scenario before T7d
native DMX drives those cases.
