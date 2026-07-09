---
doc_status: current
truth_level: code-verified
last_verified_date: 2026-07-09
last_verified_commit: HEAD-2026-07-09-overnight
validation_scope: implementation spec for LIGHTING ENGINE v2 Feature 4 (texture layer), authored from the locked design (D§5/§7 texture rows, S-2 containment) + the AWR-147 calibration semantics notes; STRICT DEPENDENCY - implements only AFTER F2 (AWR-163) lands and passes the executive gate (F2-first build order); awaiting executive review, nothing implemented
---

# Codex Implementation Spec - LIGHTING ENGINE v2 F4: the texture layer (AWR-164)

F4 makes the room's choices *taste* like the music without ever deciding
when or whether anything fires: texture classes computed from the cached
v4 series season WHICH variant of an already-selected look plays and HOW its
knobs sit. **S-2 containment is the constitution of this feature** (design
D§7): texture picks variants and seasonings inside the moment's owner —
never scheduling, never darkness, never family/tier. F4 off ⇒ family
default variants everywhere; role cues untouched BY CONSTRUCTION.

Normative annexes: `docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md`
(D§5.1/5.4/5.5/5.7, §7 F4 rows, App. E texture inventory) and
`docs/research/spectral_calibration_expansion_2026_07_08.md` (semantics +
scrub gates). **Depends on AWR-163 (F2)**: F4 flags ride the F2 per-track
plan record and season F2's `drop_look_routing` selections.

## Part A - The binding texture model (verified)

1. **Texture classes = existing pure functions in `spectral_profile.py`**
   (consumer-only feature; zero analysis-layer changes): `stab_flags:216`,
   `sustained_bass_flags:226`, `growl_flags:236`, `sustained_synth_flags:245`,
   `kick_prominence_flags:258`, `bright_tilt_flags:268`, `thick_flags:274`,
   `bottom_gone_flags:121` (texture-darkness consumer — the AND-rule keeps
   this one job, D§4.1-1), `roll_flags:195` + `roll_acceleration:201`,
   plus F2's bass-forward (D§5.1), simmer (D§5.4), euphoric-eligibility
   (D§5.5).
2. **Calibration semantics locks (C§6d/§6e — binding):**
   - `sustained_synth` is a CLEAN-EUPHORIC proxy; it counts vocals
     (source-agnostic); never surface or document it as "synth."
   - `lowmid_pulse` (:311/:382) is EXPERIMENTAL: breadth problem (wobble,
     rolls, chugs, sirens all fire it) + a named false negative (slow
     beat-locked wub < 2.5 cyc/beat invisible). **F4 ships it UNCONSUMED**
     behind `texture.busy_pulse_experimental: false` — computed into the
     plan record for observability only; no renderer consumes it until the
     operator's scrub gate closes. Any future rework must solve the
     kick-confound below 2.5 cyc/beat (D App. E) — recorded, not attempted.
   - Two scrub-gated limitations honored: kick-prominence under sidechained
     walls; sustained_synth on thick layered walls (D§5.7) — both consumed
     as WEAK signals (variant preference, never a hard switch).
   - Bass-forward B/K grain density is a LIVE-GATED taste call (C§6b#5
     ear-confirmed the alternation itself).
3. **Consumption map (selection-only, the whole feature):**
   - **Drop-variant seasoning**: within the F2-selected drop look, texture
     picks the variant/params — bass-forward beats alternate the
     sparkle-vs-chase treatment inside HOUSE growl-bar drops (D§5.1,
     CSN-calibrated BKBB pattern); stab vs sustained-bass picks the
     pulse-expand vs sparkle→groove HOUSE variant (D§3 family text); WALL
     trap-vs-dense variation reads `onset_density_mh`/`pre_gap` (D§3.1 —
     already family-internal, F4 just carries the seasoning knob through).
   - **Role-cue flavoring**: euphoric-eligible windows flavor the playing
     role cue toward the zone's bright/white end (selection weight, D§5.5 —
     the moment's owner still decides); simmer sections render the
     sparse-and-dim floor with simmer detection (F2 carries the floor;
     F4 upgrades WHEN it applies from "quiet section" to measured simmer —
     D§7's F4-off note: without F4 the floor is the zone's dimmest look at
     rung 2 without simmer detection).
   - **Texture-darkness**: `bottom_gone_flags` seasons droop/darkness
     TEXTURE inside cues (per D§4.1-1 this is its only remaining job —
     never sizing real darkness, which is F2's ladder).
4. **Kill switch**: `v2.f4` block, example-ON / absent-OFF (the un-mirrored
   live config stays off). F4-off ⇒ every selection input reads "no
   texture" ⇒ family default variants (D§7 dependency rule 3). F2-off ⇒ F4
   has no v2 drop cue to season (rule 2) — F4 must no-op cleanly under it.

## Part B - Tasks (one commit each, explicit paths; DISPATCH ONLY AFTER F2 LANDS + GATES)

### Absolute Rules
- Containment is testable law: NO F4 code path may alter scheduling,
  darkness windows, family, tier, or look ROUTING — only variant/param
  selection within the already-chosen look. Any task needing more is a spec
  defect: STOP and report.
- Consumer-only: `spectral_profile.py` unchanged (spectral_analysis
  contract registered as consumer). No new analysis, no re-analysis.
- Same overnight discipline: no bridge starts, live config read-only,
  fresh-read shared docs, explicit paths, fragmentation noted-never-rewritten.

### Task 1 - Texture flags into the F2 plan record (`lighting_moments_v2.py`)
Extend the F2 plan with per-track/per-window texture: drop-window texture
vector (stab/sustained-bass/growl/kick-prominence/thick/tilt + bass-forward
beat mask), per-section simmer + euphoric runs, busy-pulse (computed,
flagged experimental, unconsumed). Pure functions, plan-time only, reasons
published (D§12).

### Task 2 - Drop-variant seasoning (`led_dispatch_policy.py` params path)
Within the F2-selected drop look: map the texture vector to the look's
variant params through the existing runtime injection (texture → params
like sparkle density/size, chase-vs-sparkle alternation windows for
bass-forward beats, trap-sparse vs dense-stutter WALL seasoning). Config
table `f4.variant_seasoning` with shipped defaults per family; unknown
texture ⇒ family default (containment).

### Task 3 - Role-cue flavoring + simmer upgrade
Euphoric runs add selection WEIGHT toward bright/white-end looks within the
role's existing bank choice (a preference input to the existing
`look_preference` predicate seam, `led_dispatch_policy.py:1670-1701` — reuse
it, do not invent a parallel filter); simmer detection upgrades the F2
sparse-dim floor trigger from section-tier to measured simmer.

### Task 4 - Kill switch + config (`led_config.py`, `led_models.py`, example)
`v2.f4` block (enabled example-ON/absent-OFF, `busy_pulse_experimental`
false, seasoning table). Validation fail-closed; legacy-key tolerance.

### Task 5 - Tests
Containment proofs (the mandatory ones): with F4 on, scheduling/darkness/
family/tier/routing decisions byte-identical to F4-off on the same inputs —
only params/variant fields differ; F4-off ⇒ family defaults everywhere;
F2-off ⇒ F4 no-ops. Semantics locks pinned (sustained_synth never labeled
synth in any surfaced string; busy-pulse computed-not-consumed). Seasoning
map anchors: CSN bass-forward BKBB pattern drives the alternation mask;
euphoric weight only ever ADDS preference within the bank. Plan-time purity
(no per-tick recompute).

### Task 6 - Contract docs
Contracts: `led_govee` + `config_schema` + `spectral_analysis`
(consumer-only note). Full docs_update; AWR-164 registry row; D§7 F4 rows
flip to implemented; suite (known-red baseline) + three hard checks.

## Part C - Invariants
- S-2 containment absolute (Task 5's byte-identity proofs are the feature's
  acceptance, not an extra).
- F4-off and un-mirrored-live-config byte-identical to F2-only behavior.
- `lowmid_pulse` renders NOTHING this round.
- Scripted stand-down, transport-loss suspend, and every blackout
  precedence rule inherited from F2 unchanged.

## Part E - Acceptance
- [ ] Dispatched only after AWR-163 lands + passes the executive gate.
- [ ] Tasks 1-6 in order; containment byte-identity tests green; suite at
  the known-red baseline; three hard checks.
- [ ] Operator summary: the same moments now TASTE like the track — growl
  bars alternate sparkle and chase inside the drop, euphoric walls lean the
  room bright, dead-quiet stretches read as a true simmer — but nothing
  fires at a different time or size than F2 already decided, and one switch
  returns to F2-plain.
- [ ] Print exactly AWR164-DONE with real suite numbers, or AWR164-BLOCKED.
