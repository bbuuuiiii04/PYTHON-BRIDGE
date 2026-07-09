---
doc_status: current
truth_level: code-verified
last_verified_date: 2026-07-09
last_verified_commit: HEAD-2026-07-09-overnight
validation_scope: implementation spec for LIGHTING ENGINE v2 Feature 2 (moments/darkness/drop-typing), authored from the locked design (docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md §§3-5, 7-9) with the AWR-147 desk-calibration SUPERSESSIONS applied (41 verdicts, 5 rounds — the quantized emphasis-blackout ladder REPLACES §4.1's gap-mirror sizing) and tonight's operator design inputs folded in; AWR-162 (Energy Ladder) rides this round; IMPLEMENTED 2026-07-09 (Tasks 1-6, Opus orchestrator) — tier ships on the CURRENT corpus-absolute grading (the family-percentile redesign was measured against the corpus and REJECTED, 0/5 fixtures; redesign hypothesis of record = era/loudness normalization; see the AWR-163 registry row for verbatim evidence); darkness ladder is tier-independent; AWR-162 (A)+(D.1) delivered, (B)/(C) config-seeded/live-tuned, (D.2) deferred; F2-off byte-identical (kill test green)
---

# Codex Implementation Spec - LIGHTING ENGINE v2 F2: moments, darkness, drop typing (AWR-163)

F2 turns the calibrated v4 spectral analysis into the room's moment engine:
per-drop family/tier typing, the quantized emphasis-blackout ladder, build
moves that land on the one, white-share and rate rungs — rendered through
the looks that rounds 1-3 already shipped. **Normative annexes** (read both
FIRST): `docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md` (the exact rules;
cited as D§n) and `docs/research/spectral_calibration_expansion_2026_07_08.md`
(the 41-verdict calibration; cited as C§6b-6f). Where they conflict, **C
supersedes D** — the deltas are enumerated in Part A. AWR-162
(`docs/plans/active/laser_energy_ladder_spec.md`) implements WITH this round
and consumes the interfaces named in Task 4.

## Part A - The binding model (design + supersessions, verified)

1. **Family classifier: D§3.1 VERBATIM.** WALL / COMET / HOUSE / NEUTRAL
   from `drop_window_vector(v4, D, width=16)` (`spectral_profile.py:502-556`)
   with the exact thresholds in D§3.1 (audit: 41/21/11/27% over 3,936
   windows). Desk-validated (C: NEUTRAL twice, COMET gate, HOUSE T3, one
   trap miss noted). Ties land NEUTRAL. Descriptors only, never genres.
2. **Tier scorer: D§3.2 is ON NOTICE — implement the v2 grading.** The
   corpus-absolute violence formula missed ~6 of ~15 graded (C§6d/§6e; both
   directions; misses cluster on hard-techno/big-room/older masters and
   early-track windows). F2 ships a family-aware tier: violence per D§3.2
   BUT (a) graded against FAMILY-conditional cuts (recompute p55/p85 per
   family over the corpus with `tools/spectral_calibration_report.py`
   machinery — one offline run, constants frozen into the module with the
   run recorded in the report), (b) **track-start damping**: a drop with
   runway < 64 beats from track start caps at tier 1 unless hotcue-tagged
   (three early-track overshoots, C§6b#2/§6c/§6e; mirrors AWR-139's runway
   rule), (c) the six documented failure cases become the test fixture —
   the fix must flip the under-reads (Satisfaction, Age Of Love→T2,
   ONE CHANCE 2:36→T2+) without breaking the validated reads
   (I COULD BE THE ONE HOUSE T3, DROP EM's T2/T1/T1/T2 spread).
3. **Darkness: the C§6f FINAL LADDER replaces D§4.1's `gap=min(raw_gap,16)`
   sizing.** Blackout length is drop EMPHASIS, quantized {0, 1, 2, 4, 8, 16}
   or BALLOON-SHRINK:
   - 1-2: grooves / music-runs-straight-in (default when nothing below fires)
   - 4: the default emphasis unit (his workhorse — 6 of 19 labels)
   - 8: intense trap drops / true stops (percussion done, vocals+effects only)
   - 16: TRUE COLLAPSE + HARD/DARK MONSTER incoming (WALL/COMET-grade) ONLY —
     melodic/mainstage never earns 16 regardless of collapse depth (Caramelle
     rejection, C§6f)
   - BALLOON-SHRINK instead of black for melodic swells: build-window
     `perc_full` ≲ 0.30 → balloon (strips shrink + room dims into the drop);
     ≳ 0.40 → 4-beat black; PIN the boundary at **0.35** with the six labeled
     builds as fixtures (Innerbloom 0.20, Caramelle 0.10 → balloon;
     Diamond Therapy 0.93, Errday@1:31, Tremor@3:22 → 4-black; the gray zone
     0.30-0.40 defaults to 4-black — dark-but-lit beats wrong-balloon).
   - D§4.1's machinery SURVIVES as inputs: sub-only gone flags, tolerant scan,
     bass-duty (no longer a hard veto — it feeds the balloon/black split),
     measured `raw_gap` **CAPS** the quantized length (never dark over landed
     music), floor-returned ABORT (pinned: abort at the 2nd consecutive
     floor-present beat counting from the FIRST in-window beat, entry-beat
     inclusive — the reading that yields abort@150 corpus behavior; the
     alternative "116" reading is rejected, recorded here per the AWR-147 pin
     request), relative dip (D§4.1-5, TUNE-LIVE), snap flick + perc-cut
     1-beat upgrade (D§4.1-6 — ear-validated "perfect"), breakdown
     sparse-and-dim floor (D§4.1-7; never true black).
   - "True stop" class: pre-window percussion gone + vocals/effects only —
     derive from cached `perc_full` + band series (C§6c), pin as
     `med(perc_full[window]) ≤ 0.15 AND med(full_db[window]) ≥ ref − 10`.
4. **Marker hygiene is load-bearing (C§6c-4, §6f):** consecutive chorus
   markers inside one drop section collapse to ONE drop (reuse the AWR-131
   smart-drop collapse semantics — do not invent a second dedupe); DJ-intro
   pseudo-drops damp via 2's runway rule; variable-BPM grid-health flag is
   RECOMMENDED-NOT-IMPLEMENTED (analysis layer, out of scope — record only).
5. **Aggression profile D§3.3 + white-share D§5.2 + rate rungs D§5.3 (with
   the 30fps/BPM alias guard) + bass-forward D§5.1 (drop-variant seasoning
   only) + simmer D§5.4: verbatim.** All slot-fed (D§8): white rides slot 5
   weight (zone-tinted per AWR-156 T9 for nebula-class, baked for
   `BAKED_WHITE_SLOT5_EFFECTS`).
6. **Build moves D§9 + the BALLOON family member:** squeeze-explode / fuse /
   swell per the D§9 selection rule; ADD balloon-shrink as the fourth move,
   selected by the darkness ladder (3's balloon branch), rendered through
   the promoted `rt_buildup_balloon_comet` mechanics (round 2) with
   build-length-proportional shrink. Squeeze composes INTO blackout windows
   (D§9); landing restore per D§9 P-3.
7. **Cloud-drop gap: RESOLVED by AWR-150.** Every drop impact renders
   realtime on the beat (RT substitute + staged cloud takeover), so F2
   choreography (darkness → detonation, landing arcs) binds to the RT frame
   path unconditionally; committed cloud picks still take over post-impact.
8. **Tonight's operator design inputs folded in:** drop-texture routing —
   family/tier selects among the promoted drop looks (the firework
   explosion arc when it passed its contrast gate, colorway strobes,
   rainbow_drop, knob-4 slot cues) via a config-shaped
   `drop_look_routing` table (family × tier → look preference list, bank
   membership still the gate); remnants background dim length follows the
   musical content (8-beat default when ambiguous — the F2 dim-routing
   input); post-drop dynamic width decay (width 4 → groove width over
   ~16 beats) via the runtime width injection pattern.
9. **Kill-switch discipline (D§7):** everything above lands under the F2
   switch; F2 off ⇒ fixed `led_predark_beats: 4` predark, v1 drop cues, no
   moves — byte-identical to today. F1-off+F2-on renders families through
   v1 colors (D§7 rule 4). Scripted tracks: v2 stands down completely.
   Transport loss: suspend to v1 fallback, never a new dark-room mode.
10. **AWR-162 interface (Task 4):** per-drop laser tier mapping — family
    NEUTRAL or damped-T1-thin → `small`; T1 → `standard`; T2 → `intense`;
    T3 → `monster`. **FLAGGED EXECUTIVE DEFAULT, one-line operator veto
    (same treatment as strobe_red_white side B): NEUTRAL → small silences
    lasers on ~27% of corpus drops, and damped-T1-thin → small silences
    early-track drops — the operator's approved (A) was ENERGY-gated;
    NEUTRAL is a typing outcome he never ruled on. The default is kept
    because it fails toward fewer unwanted laser fires; his one line flips
    either mapping.** Plus the emphasis-blackout window feed (lasers dark
    the same beats) and the quantized 4-beat pre-chorus phrase lookahead
    (chorus phrase starts from `phrase_roles`).

## Part B - Tasks (one commit each, explicit paths)

### Absolute Rules
- Parallel-lane files (if still in flight at dispatch): verify Track B/C
  sentinels landed before touching `state_manager.py`/`drop_presentation.py`
  or `govee_frame_renderer.py`; shared docs fresh-read + explicit paths +
  HEAD-lock retry discipline as all night. NO bridge starts; live config
  read-only.
- F2 switch defaults: the switch ships DEFAULT ON in the EXAMPLE config;
  an ABSENT key means OFF — so the un-mirrored live config is
  byte-identical-off, and live activation requires the operator's mirror +
  restart. (Task 5 states the same rule; they must match.)
- The 200 Hz push loop gains no blocking I/O: all rule evaluation is
  plan-time (track load / anlz worker) or cheap per-tick arithmetic on
  precomputed windows.
- Emergency/manual/tactical blackout precedence, AWR-154/155 owner
  semantics, AWR-157 blank-role hold, AWR-160 load gate: untouched.

### Task 1 - `lighting_moments_v2.py` (NEW pure module): the rule engine
Family classifier (A.1), tier v2 (A.2 — with the offline family-cut
constants), darkness ladder (A.3 — full decision function returning
`(kind, beats|balloon, window, abort_at, cap_inputs, reason)`), true-stop
class, white-share, rate rung, bass-forward flags, simmer/euphoric
eligibility, build-move selection incl. balloon (A.6). Every function pure
over cached v4 series + marker lists; every constant named at module top;
every decision returns its plain-text reason (D§12 observability).

### Task 2 - Plan-time integration (`state_manager.py` + anlz/spectral worker path)
At track identity time (the existing v4-cache async arrival that feeds
`set_track_identity`), compute the per-track F2 PLAN: deduped/damped drop
list (A.4), per-drop family/tier/darkness decision, per-build move + white
share, published as one immutable record per (deck, load_gen) alongside the
identity record. Missing cache/markers ⇒ empty plan ⇒ F2 no-ops for that
track (fail toward today's behavior). Log one INFO line per track:
`[F2] plan deck=N drops=K families=... tiers=... darkness=...`.

### Task 3 - Dispatch wiring (`led_dispatch_policy.py` / `state_manager.py`)
With the F2 switch on and a plan present:
1. **Darkness**: the per-drop window drives the tactical pre-drop blackout
   machinery (replacing the fixed `led_predark_beats` countdown for planned
   drops; unplanned drops keep the fixed predark), balloon branch dispatches
   the balloon build look instead of dark, abort releases early, dips/flicks
   ride the existing short-cut path. AWR-150 guarantees the RT frame at
   impact.
2. **Drop typing**: at impact, family × tier selects the drop look via the
   `drop_look_routing` config table (defaults shipped for every family×tier
   cell using the rounds-1-3 look inventory; unknown cell → today's rotation
   pick); aggression profile sets hz/duty/width params through the existing
   runtime param injection; white-share scales slot-5 weight; rate rung sets
   the look's beat division.
3. **Builds**: move selection arms the arrival (BeatSyncEngine target =
   drop beat, D§9 travel defaults TUNE-LIVE); squeeze composes into the
   blackout window; landing restore per eligibility.
4. **Post-drop**: width decay injection (A.8) + remnants dim routing
   default 8.
### Task 4 - AWR-162 hookup (implement that spec's Tasks 1-4 HERE, as written)
The tier→laser mapping (A.10), planner energy gate, per-tier chase
divisions, flagged burn-down, emphasis-sync laser darkness, 4-beat
pre-chorus laser lookahead. AWR-162's Part B/C text is normative — including
the AWR-138 re-entry invariant restatement and both its FLAGGED taste items.

### Task 5 - Config + kill switch (`led_config.py`, `led_models.py`, example config)
`v2.f2` block: `enabled` (example TRUE; absent ⇒ False — un-mirrored live
config stays off), `drop_look_routing` table, balloon boundary, dip/flick
TUNE-LIVE values, `impact_burndown` (from AWR-162, ships false). Validation
fail-closed; unknown legacy keys ignored (the round-1 tolerance pattern).

### Task 6 - Tests
The C-calibration verdicts ARE the fixtures: table-driven tests over
synthetic series reproducing every named anchor — ladder (all 19+ blackout
labels incl. Hide and Seek 16→short, FE!N 2, Cruel Summer 8-true-stop,
kidstopbreathing 16, Caramelle balloon-not-16, the perc-cut flick), balloon
split (six builds), tier v2 (six failure cases flip, validated cases hold),
family anchors (CSN, DROP EM spread), abort edge (the pinned reading),
marker dedupe/damping, plan fail-empty, F2-off byte-identity (the kill
test), scripted stand-down, AWR-162's both-sides re-entry pins, no-plan
drops keep fixed predark.

### Task 7 - Contract docs (final commit)
Contracts: `led_govee`, `laser` (AWR-162 side), `drop_presentation`,
`config_schema`, `spectral_analysis` (consumer registration only — zero
analysis-layer changes; C: "all rule changes land in the F2 consumer spec").
Full docs_update for each; AWR-163 + AWR-162 registry rows to implemented /
software-tested; the design doc's D§14 feature table F2 rows flip to
implemented; suite (known six reds) + three hard checks.

## Part C - Invariants
- F2 OFF (and every un-mirrored live config) is byte-identical to today —
  the kill test is mandatory, not optional.
- Markers stay authoritative for WHEN; analysis only dresses (D charter).
- True black belongs to the blackout window alone; breakdowns
  sparse-and-dim; simmer never true black (OLC-A).
- No re-analysis at runtime — cached series only (D authority 4.1).
- Push loop: no blocking I/O; plan computation rides the existing async
  identity worker.
- Emergency > manual > tactical > F2 darkness, always; AWR-155 bare-clear
  clears F2 darkness too (it is an owner like any other).
- AWR-162's invariants (both-sides re-entry, tier-less fallback,
  CH3/CH4 untouched, burn-down OFF) hold verbatim.

## Part E - Acceptance
- [ ] Tasks 1-7 in order, one commit each, explicit paths; fragmentation
  noted-never-rewritten.
- [ ] Every C-calibration anchor test green; suite at known-six-reds; three
  hard checks; kill test proves F2-off byte-identity.
- [ ] Operator summary (plain words): with F2 on after your mirror —
  blackouts before drops are now sized by how hard the drop hits (1-2 for
  grooves, 4 as the standard hit, 8 for trap stops, 16 only for a true
  collapse into a monster; melodic swells get the balloon shrink instead of
  black); drop looks are chosen by what the drop actually is (wall/comet/
  house) and how violent it is; builds aim at the one; the lasers follow the
  same energy tiers (small drops keep them silent) and go dark with every
  blackout and for 4 beats before each chorus; everything can be killed
  back to today's behavior with one switch. ONE-LINE VETO ITEMS for you:
  drops the analysis calls NEUTRAL (~27%) and very-early-track drops
  currently keep the lasers silent — say the word and either fires lasers
  like a standard drop instead.
  **KNOCK-ON (executive condition 3, plain words): the hardest old-school-techno
  and big-room drops may read one aggression notch low until the tier redesign
  lands — the lasers still fire (standard tier) and the chase is one class
  chunkier, but the blackout SIZING is unaffected (the darkness ladder never
  reads the tier). This is because the current tier reads perceived hardness a
  notch soft on older/quieter masters; the family-percentile fix was rejected
  (0/5 fixtures — see the AWR-163 registry row) and the redesign of record is
  era/loudness normalization.**
- [ ] Print exactly AWR163-DONE with real suite numbers, or AWR163-BLOCKED.
