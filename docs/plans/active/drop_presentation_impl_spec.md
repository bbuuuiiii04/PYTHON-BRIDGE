---
doc_status: active-spec
truth_level: implementation-spec, code-grounded
last_verified_commit: 267edd3
last_verified_date: 2026-07-04
validation_scope: spec only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — Drop presentation policy + Laser Solo (Package 3 of AWR-119)

Behavior contract: `docs/architecture/drop_presentation_authority.md` — its
ladder, edge rulings, and Required Behavior Tests are the acceptance oracle.
Design evidence: `docs/plans/active/streamdeck_palette_control_design_spec.md`
Part C.9. **Depends on Package 1** (`laser_blackout_rewire_spec.md` — owner
discipline) **and Package 2** (`streamdeck_palette_control_impl_spec.md` —
pads, events, coordinator, feedback file). Implement after both.

## Part A — Context (verified at `bd96b32`; read, do not implement)

- [confirmed] True-drop machinery exists and is reused, not reinvented:
  Smart-Drop selection `select_smart_drops` (`smart_phrasing.py:601-617`);
  drop-lifecycle tension gate `impact_predecessors` (`drop_lifecycle.py:18`);
  ANLZ drop beats arrive via `Ev.ANLZ_DATA` payload `drop_beat_indices`
  (`models.py:247`).
- [confirmed] Pre-drop window plumbing: smart phrasing computes
  `next_smart_drop_beat` and `beats_to_next_drop`
  (`smart_phrasing.py:329-334`, result fields :455-456, declared :55-56).
  Smart-drop blackout arms via `smart_drop_blackout_arm`
  (`state_manager.py:3211-3220`, fed to the laser context :3233) with a
  second arm path `smart_phrasing_blackout_arm` (:3460); window length
  `pre_drop_blackout_beats` (`laser_models.py:108`) applied at
  `state_manager.py:1651-1652` (`self._sp_drop_window`). [assumed: the two
  arm computations' interplay — Codex must trace both before hooking
  pre-dark, and hook the SAME signal(s) so LED pre-dark aligns with the
  laser pre-window.]
- [confirmed] Track-load hook: `Ev.TRACK_LOADED` → `_on_track_loaded`
  (`state_manager.py:992,1488`), active-deck branch `if deck ==
  self._os.active_deck:` (:1497).
- [confirmed] Gear-shift data: per-deck BPM persists across handover —
  `DeckState.meta.bpm` (`models.py:37`; per-deck dict `state_manager.py:439`;
  only cleared by that deck's own next load :1490). Live BPM accessor:
  `AutoloopController.live_bpm_value(deck)` (`autoloop_controller.py:125`;
  used for active and mirror at `state_manager.py:2840,2851`).
  `Ev.MASTER_CHANGED` handling at :958-979. [assumed: outgoing live BPM
  freshness at the exact handover tick — Codex verifies and falls back to
  `meta.bpm` when the live value is stale/None.]
- [confirmed] Scripted gate: `scripted_led_mode`
  (`led_dispatch_policy.py:667-670`) / `lighting_mode == "scripted"`; the
  policy is EXEMPT on scripted tracks (authority §Scripted-Track Exemption).
- [confirmed] Base suppression precedent: `clear_selection()`
  (`soundswitch_laser_player.py:312-322`) yields a ZERO base while held
  static overrides still stand alone (:428-443) and masks are untouched. Five
  existing callers, all in `_drive_pack_output`
  (`state_manager.py:2385,2414,2550,2609,2611`).
- [confirmed] Hot-cue names live in `master.db`, NOT ANLZ (library-wide scan
  2026-07-04: every ANLZ cue tag empty; 413 named cue points in the DB).
  Read pattern: `pyrekordbox.db6.Rekordbox6Database` as in
  `filepath_resolver.py:244-246`; cues are `Cues` JSON blobs on `ContentCue`
  rows — per-cue `Comment` and `InMsec`, keyed by `ContentID`, filtered
  `rb_local_deleted == 0`. The operator's existing `DROP`/`BUILDUP` cue names
  are navigation aids and must never trigger anything; only the configured
  marker (`LASER`) tags a solo.
- [confirmed] Package 2 provides: the reserved Solo pad note (60, config
  `laser_solo_note` — row built by THIS package) + binding kinds pattern,
  the coordinator + feedback-writer thread, the feedback file (`laser_solo`
  field), the LED blackout OWNER SET (`led_dispatch_policy.py` per Package 2
  Task 2 item 4 — this package's `drop_spotlight` owner rides it), and
  `atomic_write_json` (`runtime_status.py:631-636`) for the learned store.

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Out of scope: laser color (Package 4), blackout owner systems' internals
  (Package 1 landed them — consume, don't modify), smart-drop/breakdown
  decision timing, the exporter/pack, scripted rendering, autoloop selection.
- With `/drop_presentation` `enabled: false`: every drop renders
  `leds_plus_lasers` exactly as today; the Solo pad and mute pads still work.
  This is the master regression gate.
- ZERO randomness: no RNG anywhere in this package.
- The `master.db` read happens ONLY at track load and ONLY off the
  state-manager thread's hot path [assumed: `filepath_resolver`'s DB access
  runs on the reader/resolver side — Codex verifies which thread executes
  `filepath_resolver.py:244-246` and puts the cue read in the same flow,
  attaching results to the existing `Ev.FILEPATH_RESOLVED` payload or a
  sibling event; NEVER a DB read inside `_push_tick`].
- Error handling: a missing/locked DB, malformed `Cues` JSON, or corrupt
  learned store degrades to "no tags/no learned entries" with ONE logged
  warning — the show never blocks on curation data.

### Task 1 — NEW `drop_presentation.py`: pure planner + session state
1. `plan_track(drop_beats, phrase_roles, tagged_beats, learned_keys,
   config) -> TrackPlan`: per true drop, the presentation + reason string
   (authority §Observability vocabulary). Implements: hotcue match (±2 beats
   nearest smart drop), learned lookup, finale guarantee (last true drop ≥
   `leds_plus_lasers`), personality ranking (last-drop-first, then longest
   runway, top `ceil(laser_ratio × N)`), runway computation (contiguous
   breakdown/buildup beats walking back; groove resets contiguity; missing
   phrase data → runway 0 and invisible to record logic).
2. `SessionState`: opening-damper track counter (a track counts after ≥16
   beats as audible active deck), tonight's runway record + observed-drop
   count, per-track auto-solo-used latch, gear-shift pending flag. All
   in-memory; reset on construction (session = process lifetime).
3. `LearnedStore`: load/save `local/state/laser_solo_learned.json` via
   `atomic_write_json`; keys `f"{content_id}:{round(drop_beat)}"` —
   **beat-position keys, not list indices** (operator 2026-07-04: survives
   Rekordbox re-analysis reindexing); lookup matches a plan drop when
   `|stored_beat − drop_beat| ≤ 2` (mirror the hot-cue tolerance). Record on
   solo FIRE (not arm; not when the drop was already tagged/learned); veto →
   remove + save. Corrupt/missing file → empty store + one warning.
4. `WindowMachine`: the pre-dark/solo/suppression state machine with every
   fail-open trigger from the authority doc (window end, role change, track
   change, active-deck change, stop, manual interaction, laser-output loss,
   predicted-impact-passed-without-drop). Pure transitions driven by inputs
   (beats, roles, arm signals) — no I/O, no time.time() (beat-driven).

### Task 2 — hot-cue tags: DB read at track load
In the `filepath_resolver` flow (same thread/session as its existing
`Rekordbox6Database` use :244-246): fetch the track's `ContentCue.Cues`,
filter non-deleted cues whose `Comment` contains `hotcue_marker`
(case-insensitive), convert `InMsec` → beats via the track's existing beat
math (first-beat/BPM authorities already carried in `FILEPATH_RESOLVED`
payload — reuse them, do not invent a parallel conversion), and attach
`laser_tag_beats: list[float]` to the resolved-track payload. Unmatched
markers (no smart drop within ±2 beats) are surfaced in the presentation
status, not dropped silently.

### Task 3 — `soundswitch_laser_player.py`: base suppression
Add `set_base_suppressed(held: bool)`; in `render()`, when suppressed, treat
the base exactly like the `missing_selection` path (:428-443): ZERO base +
diagnostic `"base_suppressed"`, held static layers still apply, masks
untouched. It must NOT clear `_selection` (the drop keeps rendering the
instant suppression lifts). Suppression must never touch blackout/emergency
state or owners (authority rule: suppression ≠ blackout).

### Task 4 — `state_manager.py` wiring
1. Track load (active branch :1497): build the `TrackPlan` (drops arrive via
   `Ev.ANLZ_DATA`; plan finalizes when both ANLZ data and cue tags are in —
   until then, drops render `leds_plus_lasers` as today [fail-open]).
   Damper counting does NOT happen here — it cannot be decided at load time
   (see item 3).
2. Master change (:958-979 vicinity; hook where `active_deck` actually
   flips, not just the raw event — both authority paths converge in the
   resolver re-run): compute the gear-shift delta **live-then-meta on BOTH
   sides** (`live_bpm_value(deck)` first, `meta.bpm` fallback when live is
   None/stale — a pitched deck plays its live tempo, authority tier 5);
   ≥ +10.0 → set the pending gear-shift flag consumed by the incoming
   track's first true drop.
3. Per push tick (inside existing dispatch flow, pure reads): feed the
   `WindowMachine` with `beats_to_next_drop`/`next_smart_drop_beat`, the
   smart-drop arm signals (Part A), drop-role state, the drop-lifecycle
   impact events, AND the laser-output-live input: pack runtime active AND
   the latest `_drive_pack_output` pass rendered an autoloop base with no
   diagnostic (set a small SM-held bool where the drive path knows the
   render result); mid-window loss = that input going false. Apply outputs —
   pre-dark = LED blackout with owner `{reason: "drop_spotlight"}` (the
   Package-2 owner set; distinct from the manual mute owner); solo window =
   same owner held through the window; `leds_only` =
   `player.set_base_suppressed(True)` for the window.
   **Damper counting lives here too:** latch a track as counted once its
   deck has been the audible active deck (playing) for ≥16 beats since load,
   once per `(deck, load_gen)` — loaded-but-never-audible decks never count.
4. Darkness guard before pre-dark AND at impact: the SAME laser-output-live
   signal as item 3 + rendering a drop autoloop + no laser blackout/mute
   held (Package 1's `mask_owners_active()` + the MIDI-input snapshot) +
   laser enabled; fail → presentation downgraded to `leds_plus_lasers`,
   reason `guard_fallback_both`.
5. Solo pad events (binding kind `laser_solo_pad`, note 60 — add the kind in
   the Package-2 pattern; this package builds the binding row from Package
   2's reserved `laser_solo_note` config): arm/disarm/veto per the
   authority; learning on fire via `LearnedStore`; feedback `laser_solo`
   field updated (off/armed/active) through the Package-2 coordinator.
   **LearnedStore persistence never runs on the state-manager tick path:**
   the coordinator enqueues the mutated store payload to the Package-2
   feedback-writer thread, which serializes via `atomic_write_json`;
   veto-unlearn rides the same path.
6. Scripted exemption: every hook above no-ops while `lighting_mode ==
   "scripted"` for the active deck; arm state persists per the authority.

### Task 5 — config
`/drop_presentation` block in `config/led_look_director.example.json` +
loader in `led_config.py`: `{enabled: true, laser_ratio: 0.4,
opening_tracks: 3, led_predark_beats: 4, drop_window_cap_beats: 32,
hotcue_marker: "LASER", solo_learn_threshold: 1, gearshift_bpm_jump: 10,
record_min_drops: 5, ws_handoff_enabled: false}`. `ws_handoff_enabled` is
parsed but the ritual tier is NOT implemented in this package (explicitly
deferred; leave a named no-op guard so enabling it logs "not implemented").

### Task 6 — tests: `tests/test_drop_presentation.py`
Implement the authority doc's Required Behavior Tests 1-9 verbatim, plus:
- Byte-identity with `enabled: false` across a scripted+autoloop session sim.
- Runway math: groove-resets, missing-phrase-data, mid-buildup record
  crossing detection timing.
- Planner determinism: identical plans across repeated runs/plays.
- DB-read degradation: locked/missing DB → no tags, one warning, show runs.
- Suppression vs static override vs blackout layering (with Package 1 masks).
- WindowMachine: every fail-open trigger table-tested (incl. the
  laser-output-live input going false mid-window).
- Gear-shift pitched-deck case: outgoing live 128 vs incoming tag 126 pitched
  to live 138.6 → fires; meta-only comparison would miss it.
- Damper ≥16-beat latch: loaded-but-never-audible counts nothing; once per
  `(deck, load_gen)`.
- Learned-store beat keys: ±2-beat lookup tolerance; a shifted re-analysis
  beat within tolerance still matches; index-style keys rejected by test.

## Part C — Invariants That MUST Still Hold
- Blackout absolute; manual mutes survive everything; suppression never
  touches blackout owners (Package 1 contract + survival tests stay green).
- No DB/file I/O on the state-manager thread's tick path; learned-store
  writes ride the Package-2 writer thread or the resolver thread.
- Zero RNG; plans are pure functions of track structure + curation.
- Scripted tracks byte-identical; mirrors (decks 3/4) generate no decisions.
- LEDs can never latch dark: every dark state has an enumerated restore.
- All AGENTS.md §6 invariants; no bridge restart authorized.

## Part D — Tests
Task 6. Pure seams: `plan_track`, runway math, `WindowMachine` transitions,
gear-shift delta, learned-store round-trip (tmpdir) — all hardware-free.

## Part E — Acceptance
1. Contract-first: add a `drop_presentation` contract in
   `docs/agents/change_contracts.yml` (docs_update:
   `docs/subsystems/led_govee.md`, `docs/subsystems/laser.md`,
   `docs/architecture/drop_presentation_authority.md`, the design spec,
   `docs/status/active_work_registry.md`) BEFORE code.
2. Tasks 1-6 green; authority Required Tests 1-9 all present and green; full
   suite green; docs checks pass; §10 status language only.
3. No diff outside: `drop_presentation.py`, `filepath_resolver.py`,
   `soundswitch_laser_player.py` (suppression only), `state_manager.py`,
   `led_config.py`, example config, `soundswitch_midi_input.py` /
   `led_palette_control.py` (solo-pad kind + feedback field only),
   `models.py` (one event kind), tests, contract docs.

## When You Finish
Report: changed files, test counts, checks, and the operator summary: what
the automation now decides per drop and every way he stays in charge (mutes,
veto, `enabled: false`); that `DROP`/`BUILDUP` cue names are ignored by
design; that everything is SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
until his live pass.
