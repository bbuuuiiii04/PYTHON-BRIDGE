---
doc_status: current
truth_level: implementation spec — IMPLEMENTED 2026-07-15 (Claude Opus 4.8 tmux seat; operator-authorized AWR-257 build lane). Part B tasks 1-5 + Parts C/D/E landed software-tested / hardware-unvalidated; live LED behavior operator-unvalidated until his next mix. See docs/status/active_work_registry.md AWR-257 for the landed trail. This document is preserved as the authored spec.
last_verified_commit: HEAD 2026-07-15 (post-a8611e3 working tree)
last_verified_date: 2026-07-15
validation_scope: >
  Spec only. No code has changed. Every [confirmed] claim was read in current
  code by the authoring seat on 2026-07-15. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED applies to the whole repo and to everything here.
---

# Codex Implementation Spec — True-Drop LED Section Identity + Cycling (AWR-257)

**Operator intent (Brandon, 2026-07-15):** drop looks must cycle within a drop
section; a tier-3 WALL look must never randomly fire mid-section in a section
that isn't that; one cue must not drone through an entire section. His standing
TRUE DROP definition: only the FIRST marker in a drop section is a true drop,
and a true drop has an up-buildup runway in front of it. Evidence: the AWR-239
pilot's post-hoc runway_v1 diagnostic scored 88.6% on the genuine-drop axis vs
the AI candidate's 60.0% and majority baseline's 65.7%.

**Operator scope rulings (2026-07-15, binding):**
1. **NO kill switch — ships DEFAULT ON.** No enable flag. Rollback is
   `git revert` + menubar restart.
2. **LED-ONLY. Laser behavior must be UNCHANGED.** Laser fires are already
   gated by drop presentation (AWR-220 tier gate + ratio cap + section latch)
   — this change must not alter any laser or SoundSwitch output.
3. Consequence the implementer must hold: `meta.smart_drops`, drop firing,
   blackout ladder, drop presentation, autoloop, and SS paths are all
   UNTOUCHED. The true-drop + section layer governs **LED look selection and
   LED cycling only**.

**Implementation channel (operator 2026-07-15):** tmux `agent --yolo` or a
Claude CLI tmux seat.

---

## Part A — Context & Root Cause (verified; read, do not implement)

### A1. What happens today

- At TRACK_LOADED/ANLZ processing, `meta.smart_drops =
  select_smart_drops(raw_drops, total_beats=...)` — intro/outro trim + 64-beat
  min gap (`state_manager.py:1537-1541`, `smart_phrasing.py:657-679`).
  Presentation fires ONLY these (`state_manager.py:5266`,
  `smart_phrasing.py:327-345`). Raw markers inside the 64-beat gap fire
  nothing and advance nothing. [confirmed]
- The F2 moment brain decides per RAW marker: `state_manager.py:281-286`
  passes raw `data.drop_beat_indices` into
  `lighting_moments_v2.build_track_plan` (`lighting_moments_v2.py:1013`) —
  one independent family/tier decision per marker, looked up at fire time via
  `F2TrackPlan.for_drop(beat, tol=1.0)` (`lighting_moments_v2.py:931`).
  [confirmed]
- LED drop look selection: `state_manager.py:802` loads
  `f2.drop_look_routing`; `led_dispatch_policy.py:2026-2049`
  (`_led_f2_drop_look_names`) narrows the "drop" shuffle bag to
  `routing[family][tier]` using the FIRED drop's own plan entry;
  `led_look_director.py:524-560` draws without replacement and bumps the
  per-role cursor on every accepted drop. [confirmed]
- The runway primitive exists and is pure: `drop_presentation.py:173
  runway_beats(beat, phrase_roles)` — contiguous `up`/`low` beats immediately
  before the beat. Phrase segments
  (`smart_phrasing.py:583 build_phrase_segments_from_markers`) map
  buildups→`up`, drops→`chorus`, breakdowns→`low`, each ending at the next
  marker's start; with NO explicit buildup markers it invents a conservative
  32-beat `up` before each smart drop. So a drop marker's immediately
  preceding segment always ends exactly at the drop beat, and
  `runway_beats(drop) > 0` iff a buildup/breakdown climbs into it — exactly
  the operator's rule, with a built-in fail-open on sparse phrase data.
  [confirmed]

### A2. Root cause of the two LED complaints

1. **Mid-section identity flips:** a section longer than 64 beats fires a
   second smart drop; that marker's OWN plan entry (its own local audio
   window) picks the LED pool — a different family/tier than the section's
   hit lands a jarring look (the "tier-3 WALL ambush"). Nothing ties LED
   identity within one musical section together. [confirmed from A1]
2. **One cue drones through long sections:** the LED cursor only advances
   when a NEW smart drop fires; markers inside the 64-beat gap are invisible,
   so a long section sustains one look. (Lasers/SS already cycle within the
   drop window — A3 — which is why the droning complaint is LED-specific.)
   [confirmed]

### A3. Cue-pool + cycling inventory (read-only Opus sweep 2026-07-15, live tracked configs at HEAD)

**LED pools** (`config/led_look_director.json`, `f2.drop_look_routing`, all
`rt_drop_` prefixed; 16 distinct looks):

| Family | T1 | T2 | T3 |
|---|---|---|---|
| WALL | chase_blue/cyan/red/green | strobe_blue/cyan/green/red | strobe_red_white, strobe_blue_cyan, strobe_cyan_white, white_aggressive |
| COMET | chase_blue/cyan/red/green | center_burst, firework_explosion, palette_comet | center_burst, firework_explosion, white_aggressive, palette_comet |
| HOUSE | chase_blue/cyan/red/green | chase_freestyle_nebula, strobe_blue, strobe_cyan | strobe_blue_cyan, strobe_cyan_white, center_burst |
| NEUTRAL | chase_blue/cyan/red/green | chase_freestyle_nebula, firework_explosion | center_burst, firework_explosion, strobe_blue_cyan |

T1 is identical across families; differentiation begins at T2. (The old
"COMET pools contain no comet; T2≡T3 identical" observation holds only for
the STALE `.example.json` — refuted for live config at HEAD.)

**Laser:** family/tier only gates firing (`drop_laser_qualifies`,
`drop_presentation.py:151-166`); personality picks scenes
(`personality_resolver.py:76-110`); `laser_executor.py:505-516/569-584`
already cycles the 15-autoloop `house_drop_2..16` bank on autoloop edges
within the drop window. **Untouched by this spec.**

**SoundSwitch:** mirrors the active laser scene
(`state_manager.py:4223-4242` → `native_autoloop_resolver.py:218-237`); no
family/tier role. **Untouched by this spec.**

### A4. What is NOT wrong (do not "fix")

- `select_smart_drops`, `meta.smart_drops`, and every firing/blackout/
  presentation consumer: correct and out of scope.
- `runway_beats` and phrase-segment inference: correct as-is; this spec only
  adds call sites (and one module move, Task 1).
- Laser/SS cycling: already sufficient (A3).

---

## Part B — Tasks (implement exactly, in order)

### Absolute Rules

- Out of scope: any laser file (`laser_*.py`, `personality_resolver.py`),
  drop presentation firing logic (`drop_presentation.py` beyond the Task 1
  re-export line), SoundSwitch/autoloop/OS2L/MIDI paths, blackout/emergency/
  static-override owners, scripted-track paths, spectral extractors, and
  `tools/spectral_pilot/`.
- Behavior that must not change (prove it in Part D): laser output for
  identical inputs; SS selection; `meta.smart_drops` values; drop firing
  beats; blackout ladder decisions; F2 plan entries (`build_track_plan`
  inputs stay RAW `data.drop_beat_indices` — the plan is NOT re-keyed);
  scripted-track stand-down; all behavior on tracks whose every fired drop is
  a true drop and whose sections contain no advance points (the common case
  must render exactly as today except by the ≤-tier pool union in Task 4).
- Error handling: absent/short phrase data → no sections (empty tuple), LED
  behavior falls back to today's per-fired-drop path; malformed values never
  raise on the tick path; no broad try/except.
- Dirty worktree: never revert/stash/clean anything you did not write;
  commit by explicit pathspec only. Respect `/tmp/rbss_orchestration.lock`.

### Task 1 — move `runway_beats` into `smart_phrasing.py`

`drop_presentation.py:32` already imports `PhraseSegment` FROM
`smart_phrasing`, so smart_phrasing cannot import back. MOVE `runway_beats`
+ `_RUNWAY_LABELS` (`drop_presentation.py:170-198`) into `smart_phrasing.py`
and re-export from `drop_presentation` (`from .smart_phrasing import
runway_beats`) so the existing consumer (`drop_presentation.py:326`) and its
tests keep working unchanged. A move, not a copy — one implementation only.

### Task 2 — `smart_phrasing.py` + `models.py`: pure true-drop + section model

```python
def select_true_drops(smart_drops, phrase_segments) -> list[int]:
```
Keep smart drops with `runway_beats(float(b), phrase_segments) > 0.0`.
Fail open: if that empties a non-empty input, return the input unchanged.

```python
def drop_sections(true_drops, raw_drops, phrase_segments,
                  advance_min_gap_beats=SECTION_ADVANCE_MIN_GAP_BEATS,
                  ) -> tuple[DropSection, ...]:
```
For each true drop T: `end_beat` = end of the contiguous run of `chorus`
segments starting at T (walk forward while label == "chorus" and segments
stay contiguous), clamped to the next true drop if earlier. `advance_beats`
= `sorted(set(raw_drops))` markers strictly inside `(T, end_beat)`, keeping
only markers ≥ `advance_min_gap_beats` after the previous kept beat (T
counts as the first kept beat), and EXCLUDING markers in the outro trim
region (`total_beats - SMART_DROP_IGNORE_OUTRO_BEATS`, same constant
`select_smart_drops` uses at `smart_phrasing.py:668-673`) — continuations in
the outro must not drive look changes today's selection suppresses (red-team
M1/M2). `drop_sections` therefore also takes `total_beats`.
`SECTION_ADVANCE_MIN_GAP_BEATS = 16`, defined next to
`SMART_DROP_MIN_GAP_BEATS` following the same constant pattern.
`DropSection` = frozen dataclass in `models.py`: `true_drop_beat: int`,
`end_beat: float`, `advance_beats: tuple[int, ...]`. Both functions pure —
no I/O, no state.

### Task 3 — `state_manager.py`: compute sections at the selection site

Placement is exact (reviewer-verified): the real `meta.smart_drops` write is
`state_manager.py:1567`, INSIDE the `if markers_changed:` guard
(`state_manager.py:1564`) — lines 1537-1541 only compute `next_smart_drops`.
Put the sections assignment immediately beside that write, inside the same
guard (markers unchanged ⇒ sections correctly keep their previous value,
exactly like `smart_drops`). Build segments with the same helper
`_build_phrase_segments` delegates to (`state_manager.py:5256`), then

```python
meta.drop_sections = drop_sections(
    select_true_drops(next_smart_drops, segments),
    next_drops, segments, total_beats=total_beats)
```

`meta.drop_sections: tuple[DropSection, ...] = ()` on `TrackMetadata`;
reset everywhere `meta.smart_drops` resets — `models.py:68` plus every other
write/clear site of `smart_drops` (grep them ALL and mirror; do not patch
only the load path). Log one INFO line:
`[SM] true-drop-sections deck=%d smart=%d true=%d sections=%d advances=%d`.

### Task 4 — LED narrowing: section identity governs the pool

**Exact current mechanics (reviewer-verified — do not assume the old spec's
signature):** `_led_f2_drop_look_names` (`led_dispatch_policy.py:2026-2049`)
takes NO arguments; it resolves its anchor internally from
`sp.active_drop_beat` (`:2038`), looks up `plan.for_drop(float(anchor))`
(`:2045`), and returns the SINGLE cell `routing[family][tier]` (`:2048`).
It rides into selection as a preference predicate via
`_led_look_preference_predicate` (`:2051-2069`).

Change it in two ways:

1. **Section-aware anchor.** Accept an optional explicit anchor beat
   parameter. Resolution order: explicit anchor (advances pass the section's
   `true_drop_beat`) → else `sp.active_drop_beat` as today. Then: if the
   resolved anchor sits inside a `DropSection` span
   `[true_drop_beat, end_beat)`, the plan lookup uses
   `plan.for_drop(float(section.true_drop_beat))`; outside any section,
   today's behavior (the anchor's own entry). Anchor `None` keeps returning
   `None` (no narrowing) exactly as `:2039-2040` does today.
2. **≤-tier union** (operator envelope, veto-able default): replace the
   single-cell return at `:2048` with the union of `routing[family][t]` for
   `t <= tier`, same family only — never above the section's tier.

Sections only ever narrow the bag; they never create a look where today none
fires. Scripted/F2-off guards stay exactly where they are.

### Task 5 — section advance events → LED cursor (post_drop pattern, NOT a naive re-fire)

**Why this is not "re-drive the drop path as-is" (red-team H1, verified):** at
an advance beat `active_drop_beat` is already `None`
(`smart_phrasing.py:378-379` clears it after the post-drop window), so the
unmodified predicate would return NO narrowing and the draw would come from
the full multi-family bank — the exact wrong-tier ambush this spec must
prevent. And re-setting `active_drop_beat` to the true drop collides with
the role-key dedupe (`led_dispatch_policy.py:1392` vs the drop marker at
`:2363+`, `marker = f"{float(anchor):.3f}"`) — same marker ⇒ duplicate ⇒
nothing dispatches. The repo already solved this shape for `post_drop`
cycling: a per-cycle counter embedded in the marker with a stable section
id (`led_dispatch_policy.py:2363+`, `marker = f"seq…:c{cycle}"`). Follow it.

- Plumb `drop_sections` into `SmartPhrasingSnapshot` exactly the way
  `smart_drop_beats` rides it today (snapshot field + the builder that reads
  `d.meta.smart_drops` at `state_manager.py:5261/5266`).
- `smart_phrasing.py` tick: when the deck crosses an `advance_beat` of the
  section containing the current beat, surface `section_advance=True`, the
  owning `true_drop_beat`, and a monotonically increasing per-section
  advance index in the tick result. Implement BOTH crossing branches of the
  smart-drop pattern (`smart_phrasing.py:327-345`), including
  `exact_resume_landing` (`:332-336`), with an own fired-set reset on every
  path that resets `_fired_drop_beats`. Pure state machine — no I/O.
- Dispatch: advances enter ONLY through `_dispatch_led_automation` — the
  gate stack at `led_dispatch_policy.py:1288-1310` (blackout, not-ready,
  manual override, scripted, not-autoloop) must run before any advance can
  act; NEVER call the look director + `coordinator.trigger()` as a side
  channel (`led_dispatch_coordinator.py:81-87` has no active-blackout
  recheck — a side channel would punch through an operator blackout).
  Within the accepted path, re-enter at
  `commit_role("drop", ..., look_preference=...)`
  (`led_dispatch_policy.py:2000-2008` → `led_look_director.py:313-329` →
  bag draw + cursor bump `:524-560`), with:
  - the preference predicate built with the explicit section anchor
    (Task 4), never `active_drop_beat`;
  - a role-key marker unique per advance:
    `f"{true_drop_beat:.3f}:a{advance_index}"` (post_drop's cycle-marker
    shape) so the dedupe gate passes each advance exactly once.
- Advance events are LED-look-selection events ONLY. They MUST NOT: fire
  lasers, touch darkness/blackout decisions, emit autoloop/OS2L/MIDI
  traffic, mutate static-override/emergency state, or add I/O to the push
  loop. Advance crossings log at DEBUG only.

## Part C — Invariants That MUST Still Hold (live safety)

1. **Laser byte-identity.** `meta.smart_drops` unchanged + F2 plan keyed on
   raw drops unchanged + laser files untouched ⇒ `_f2_laser_tiers`
   (`state_manager.py:5133-5148`), drop presentation, and SS selection see
   identical inputs and produce identical outputs. Part D pins this.
2. **Push loop gains no blocking I/O.** Sections computed at track-load/event
   time; the tick reads precomputed tuples only.
3. **StateManager sole DeckState writer;** events immutable; `ANLZ_PATH`
   before `TRACK_LOADED` untouched.
4. **Fail open on sparse data:** no sections ⇒ exactly today's LED behavior.
   A track can never lose LED drop response from this change.
5. **Scripted tracks stand down** exactly as today (v2 LED routing guards
   untouched; advances must be inert on scripted tracks).
6. **Mid-mix lifecycle:** section state + advance fired-set are
   load_gen-scoped and reset on every path that resets `_fired_drop_beats`
   and `_smart_drop_beats_cache` (`state_manager.py:5253`) — a stale section
   from the previous track must be impossible.
7. **Pending-state audit:** an advance coexists with pending transition-arm,
   smart-drop blackout arm/mode, static override, emergency mask,
   pack-disabled zeroing — it is a look-cursor move only; every owner that
   wins over a drop-time look selection today wins over an advance
   identically. This holds ONLY because advances enter through
   `_dispatch_led_automation`'s gate stack (Task 5) — any other entry point
   voids this invariant.
8. **No kill switch (operator ruling):** behavior ships on; rollback is
   `git revert` + menubar restart; after any restart verify exactly one
   bridge process (`pgrep -f rb_ss_bridge_v2 | wc -l` == 1).

## Part D — Tests (pure seams; no files, no subprocess)

New `tests/test_true_drop_sections.py`:

1. `select_true_drops`: continuation (chorus in front) dropped; runway'd
   kept; all-disqualified ⇒ fail-open returns input; empty ⇒ empty.
2. False-marker fixture shaped like the operator-ruled I Cannot case
   (marker with no runway, true drop later with buildup): false marker is in
   no section; true drop governs its section.
3. No-buildup track: inferred 32-beat `up` qualifies every smart drop.
4. `drop_sections`: end at first non-chorus segment; clamp at next true
   drop; 16-beat advance floor; T excluded from advances; no raw drops
   inside ⇒ no advances; unsorted/duplicate raw markers handled; outro-trim
   region yields no advances (red-team M1/M2 pins).
5. LED governance: fired continuation drop inside a section draws from the
   section's ≤-tier same-family union pool, not its own entry's pool; fired
   drop outside any section draws exactly today's pool; **anchor `None` with
   a governing section absent returns no narrowing exactly as today**.
6. Laser pin: for a fixture track, `_f2_laser_tiers` inputs/outputs and the
   drop-presentation plan are identical before/after this change (import the
   functions, compare — the code paths must be untouched).
7. Advance cycling: advance bumps the cursor within the section pool; never
   repeats current look while pool > 1; wraps on exhaustion; no advance
   events on scripted tracks; advance fired-set resets with load_gen.
8. Red-team H1 regression pins: (a) an advance's narrowing NEVER falls back
   to the un-narrowed full bank while a section governs (the
   `active_drop_beat is None` path); (b) each advance's role-key marker is
   unique (`:a{index}`) and passes the `led_dispatch_policy.py:1392` dedupe
   exactly once; (c) an advance during an active operator blackout / manual
   override dispatches NOTHING (gate stack proof, `:1288-1310`); (d) exact
   resume landing on an advance beat fires it once.
9. Cleanup: every `meta.smart_drops` reset path found in Task 3's grep also
   resets `meta.drop_sections` (enumerate the paths in the test).

Extend `tests/test_drop_presentation.py` import paths only if the Task 1 move
requires it — behavior pins stay identical.

## Part E — Acceptance (definition of done)

- [ ] All Part D tests green; full `python3 -m unittest discover tests` shows
      ONLY the 6 standing named baseline reds (4 soundswitch_pack flappers +
      2 pre-existing LED color-engine reds, ~2026-07-12) — reconcile by name,
      zero new reds.
- [ ] Laser byte-identity pinned by test (D6), not asserted by prose.
- [ ] Contracts satisfied (anti-drift): `core_bridge` + `led_govee` (+
      `drop_presentation` for the Task 1 move) in
      `docs/agents/change_contracts.yml` — update every `docs_update` doc
      they list (subsystem cards, runtime_invariants advance-event rule,
      status matrices as `implemented`/`software-tested`/
      `hardware-unvalidated`, active_work_registry row AWR-257).
- [ ] `python3 tools/check_docs_metadata.py`, `check_agent_contracts.py`,
      `check_docs_drift.py` all pass.
- [ ] No secrets/live config/backup files staged; commits by explicit
      pathspec.
- [ ] Status language: §10-allowed terms only.

## When You Finish

Report: changed files; tests/checks run with counts; named-reds
reconciliation; the D6 laser-pin evidence; and a plain-language operator
summary — what changes on LEDs at the next mix (one identity per drop
section from the true drop, looks advancing every ≥16 beats within the
section's same-family ≤-tier pool, fake markers no longer steering LED
identity), what is provably unchanged (lasers, SoundSwitch, firing beats,
blackouts, scripted tracks), rollback (`git revert` + menubar restart, then
verify one bridge process), and that live behavior remains
operator-unvalidated until his next mix.
