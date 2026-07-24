---
doc_status: draft-for-review
truth_level: planned
last_verified_commit: 22fb4f6f
last_verified_date: 2026-07-24
validation_scope: >
  Design spec only (ACCSPEC seat, exec4 dispatch 2026-07-24). Defines the
  accent-layer capability class (base cue + event-locked accents) for LEDs;
  authorizes NO implementation, config, dependency, or runtime change; every
  build stage needs its own Codex spec, review, and operator gate. All code
  claims verified at HEAD 22fb4f6f and labeled confirmed/assumed/unknown.
  SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Accent Layer — design spec v1 (base cue + event-locked accents, LED-first)

Sibling of `docs/plans/active/energy_fabric_ladder_spec_v1.md` (the fabric
grades energy and CASTS the base cue; this spec defines the accent overlay
that rides ON that cast base). Governed, like everything in the program, by
the ratified transcription vision (AMENDMENT-2, landed `a3375b6b`, in
`docs/architecture/spectral_program_design_authority_amendments.md`): the
accent layer is a COMPONENT mechanism of "lights as an instrument playing the
track" — the micro-timescale one.

**Governing vision (operator law, quoted faithfully — never re-solicit):**

> LED cues = BASE layer (carries the section; may loop 32 bars) + ACCENT layer
> on top, **event-locked, not loop-locked**: downbeat slams, one-beat loop
> stabs, bass jabs, N-beat switchups, music cuts, melodic fake-drops
> (restraint) each get a discrete, moment-synced answer, then return to base.

Also (same ratified record): "hard-techno switchup pattern (4-beat change
every 16 beats) must be characterized by the lights. House drop slamming the
downbeat → quick bright full flash then whatever the music says next." And the
standing fact recorded with it: **F4 is SEASONING, not accents** — "It fires
no discrete events; that is why he has never noticed it. The accent layer is a
NEW capability class, not an F4 tune-up."

## The exemplar ledger (PRE-MACHINE seed truth — preserve untouched, never re-derive)

The operator volunteered these with exact timestamps BEFORE any machine
analysis of these moments (concept-seed grade). They are quoted verbatim as
the standing ledger for future concept/family validation: when a detector +
compiler exist, their output is judged against these lines — the lines
themselves are never regenerated, re-derived, or "corrected" by any machine.

> 1. **SPIRAL (BELPHIE SCHRANZ REWORK):**
>    - Buildup starts exactly 1:29.9 — small dim white comets toward strip
>      center every beat, growing brighter/bigger approaching 1:42.0.
>    - 1:42.0 — sparkle-buildup effect begins, PLUS accent: bright single
>      comet ripple center-outward exactly at 1:42.0, again +4 beats, again
>      +4 beats (accents the single bass jab in the buildup).
>    - Main drop exactly 1:48.0 — accent: brief hard FULL-LED FLASH STROBE for
>      1-2 beats, then immediately: extremely fast relentless comets pounding.
>    - 1:53.2 (4th bar of drop) — very tight one-beat loop effect → accent:
>      intense sparkle effect ON TOP of the relentless comets.
> 2. **ANIMALS (BOTNEK EDIT):**
>    - 2:00 "drop" is NOT a real drop (main melody) — LEDs must reflect that
>      (restraint; no drop treatment).
>    - 2:30 real drop — beat-synced pounding comet effect as the bass layer +
>      LED sparkles complementary to the big-room musical accents: sparkle when
>      the musical figure plays, STOP when it stops ("I literally cannot put
>      into words what this drop sounds like" — the sparkles track the figure).
> 3. **GODSPEED (160 BPM):**
>    - 1:53.9 — pounding comet chase with a brief 1-beat LED impact flash.
>    - 2:04.5 (44 beats after the drop) — music CUT; lights honor it; after the
>      bar finishes, drop section resumes: same impact, possibly different
>      comet cycling effect.

---

## Part A — Context & current state (verified at HEAD 22fb4f6f; read, do not implement)

### A.1 F4 is seasoning — the code proves the distinction

- [confirmed] F4's injection point is `_led_inject_f4_seasoning()`
  (`led_dispatch_policy.py:1252-1265`), whose own contract says:
  "CONTAINMENT: never touches the look name, scene_ref, backend, routing,
  schedule, or darkness — only `decision.params`." Its inputs are per-drop
  texture keys (`_f4_drop_seasoning_key`, `:162-178`: house_stab /
  house_sustain / wall_trap / wall_dense) and simmer stretches
  (`_led_f4_simmer_seasoning`, `:1219-1230`), producing parameter dicts (e.g.
  a sparkle-density scalar from the bass-forward mask, `:1233-1250`,
  `_F4_BF_SPARKLE_MIN/MAX` `:158-159`).
- Consequence: F4 modulates HOW the already-chosen base cue renders, over a
  whole role dispatch. It cannot fire a discrete, moment-synced answer at an
  event time. The accent layer is therefore a new capability class; F4 stays
  untouched as the seasoning layer beneath it.

### A.2 Today's ONLY event-locked LED answer is the drop impact

- [confirmed] The drop-impact machinery (`led_dispatch_policy.py:184-188`
  `_LED_DROP_IMPACT_PREDECESSORS` + `LED_MAX_DROP_IMPACTS = 2`; state at
  `:248-249`; gating at `:2299-2360` incl. `_led_drop_impact_allowed`) fires a
  discrete answer at a drop arrival, bounded per drop lifecycle. Nothing
  equivalent exists for bass jabs, loop stabs, switchups, or cuts — exactly
  the gap the vision names.

### A.3 The renderer already has the execution primitives

- [confirmed] `beat_sync_engine.py` is a "beat-division trigger clock +
  animation-instance lifecycle" (`:1-25`): sync modes
  `retrigger`/`overlap`/`continuous` (`VALID_SYNC_MODES`, `:21`), overlap cap
  `MAX_PULSES = 16`, seek catch-up cap `MAX_CATCHUP = 1`, and a queued
  MANUAL-FIRE drain (`MAX_MANUAL_PENDING = 4`) — i.e. a mechanism for
  spawning bounded, short-lived animation instances at chosen moments already
  exists, wall-clock-based and immune to Rekordbox loop wraps.
- [confirmed] `govee_frame_renderer.py` renders wall-clock Hz-gated strobes
  (`_hz_strobe_on`, `:372-381`) and classifies retrigger-vs-continuous
  effects (`_RETRIGGER_EFFECTS` `:1198`, `default_sync_mode` `:1206-1211`).
- [assumed] these primitives are a sufficient execution seam for accent
  overlays (a one-beat flash, a spawned ripple, a sparkle burst ON TOP of the
  running base instance); the implementation spec must verify instance
  layering does not fight the base look's instance lifecycle.

### A.4 Precedence surfaces that must sit ABOVE accents

- [confirmed] LED blackout/emergency mask state:
  `led_dispatch_policy.py:222-223` (`_led_emergency_blackout`,
  `_led_blackout_owners`), `:444-445` (`_led_blackout_active` = owners OR
  emergency), smart-drop blackout key `:246`, surfaced in status `:362-363`.
- [confirmed] Manual/emergency roles preempt automation in the look director
  (`led_look_director.py:196-212`).

### A.5 The event supply is already legislated — the design authority

- [confirmed] Events come from the spectral program's typed families: the L3
  event envelope (`docs/architecture/spectral_program_design_authority.md:83-97`
  — common envelope + per-family payloads, no universal confidence field;
  impulse_v1 is the named second family).
- [confirmed] L7 (`:147-157`) already legislates the delivery shape: "An
  offline CUE COMPILER (later, own spec) consumes confirmed events + a
  versioned presentation policy and emits immutable schedules (cue id, event
  id, target time, role, tier, duration, allowed timing error, priority,
  dedupe group, cooldown, safe fallback) that FEED the existing authority —
  never pre-baked MIDI bypassing it. Density limits, overlap resolution,
  seek/replay semantics are compiler responsibilities, evaluated first in
  shadow mode." Presentation authority remains the existing dispatch
  machinery (led_dispatch_policy, masks, balance law).
- [confirmed] Runtime consumption is gated by §1.1 (`:44-47`: schedules via a
  separately specced adapter; never models, never file reads in the push
  loop) and §8 (`:267-281`: immutable schedule identity, async load with
  fallback-to-current-behavior, seek/loop/hot-cue/pitch/deck-switch tests,
  **end-to-end MEASURED timing** per backend against an operator-defined
  visible tolerance, supervised validation, default-off rollout; "Offline
  timestamp precision (Stage-1 p90 8.5 ms) is never cited as live firing
  precision").
- Consequence: this spec invents NO new pipeline. The accent layer is the
  LED presentation consumer of the already-ratified
  events → compiler → schedule → adapter chain.

### A.6 Root statement of the gap

The base layer exists (cast by the fabric's E4 once built; bag-picked today).
Seasoning exists (F4). A single hardcoded event answer exists (drop impact).
What does not exist: a general, schedule-fed accent overlay class — discrete,
event-locked, bounded answers (flash, ripple, burst, cut-honor, switchup
characterization) that fire at scheduled musical moments ON TOP of the running
base cue and then return to it.

---

## Part B — Design (implement in stages, each with its own Codex spec + gate)

### B.0 Absolute rules

- LED-first: the laser chain is untouched by every stage below (laser accent
  warrants are a separate lane — the vision's "lasers = accents/grand
  moments" is served by the laser-warrant workstream, not this spec).
- Accents ride ON the cast base: an accent never replaces, re-picks, or
  re-dispatches the base cue; it overlays and returns. Base selection belongs
  to the fabric casting layer (E4) — with today's bag-pick until E4 lands.
- Never static-only: a section carried by base+accents must always have a
  living base underneath; accents are not a license to park a static look and
  garnish it. (Vision law; also why the base layer stays a first-class cue.)
- Restraint is scheduled, not improvised: a melodic fake-drop (ANIMALS 2:00)
  gets restraint because the schedule contains NO accent there — the absence
  of a scheduled event is the restraint mechanism, matching the true-drop /
  runway law the bridge already encodes.
- Event supply is offline-compiled schedules ONLY (L7). No live audio event
  detection is designed here, and none may be smuggled in later without its
  own authority-level review (§1.1 push-loop law).
- F4 unchanged. No re-solicitation of the vision. No labeling sessions —
  validation is normal mixing + veto; the exemplar ledger above is the only
  pinned truth and is never re-derived.

### B.1 The accent vocabulary (presentation classes, machine-internal)

Derived from the operator's own event list — each is a discrete answer with a
bounded lifetime, and each maps to an exemplar line for eventual validation:

| Accent class | Discrete answer (bounded) | Exemplar anchor |
|---|---|---|
| `impact_flash` | full-LED flash/strobe, 1-2 beats | SPIRAL 1:48.0; GODSPEED 1:53.9; "house drop slamming the downbeat" |
| `ripple` | single bright comet ripple (e.g. center-outward), one shot | SPIRAL 1:42.0 (+4, +4 beats — bass jab) |
| `burst_overlay` | intense sparkle burst ON TOP of the running base, N beats | SPIRAL 1:53.2 (one-beat loop) |
| `figure_track` | sparkle voice that plays while a scheduled figure plays, stops when it stops | ANIMALS 2:30 |
| `cut_honor` | lights honor a music cut (hold/dark) until the bar resolves, then base resumes | GODSPEED 2:04.5 |
| `switchup_mark` | brief characterization at an N-beat switchup boundary | hard-techno 4-of-16 pattern |

Class names are machine-internal presentation vocabulary (the operator never
labels events); the compiler maps event families → classes via the versioned
presentation policy (L7). `figure_track` is the hardest class (it is a
short-horizon light-voice — the transcription asymptote's nearest relative)
and is staged LAST; the honest-confidence calibration in the ratified vision
record applies to it in full.

### B.2 Architecture: schedule → adapter → overlay executor

1. **Input:** an immutable per-track accent schedule (L7's exact emission:
   cue id, event id, target time, role, tier, duration, allowed timing
   error, priority, dedupe group, cooldown, safe fallback). Produced by the
   offline cue compiler (its own future spec, per L7); identity-hashed per §8.
2. **Adapter (runtime, gated by §8):** loads the schedule ASYNC at track load
   (never in the push loop), verifies identity hashes, exposes the next
   scheduled accents to the LED policy tick. Missing/stale/hash-mismatched →
   feature-off, today's behavior byte-identical (§8's own words).
3. **Overlay executor (LED policy + renderer):** at a scheduled target time,
   the policy layer requests an overlay instance; execution reuses the
   beat_sync_engine instance machinery (A.3) — bounded lifetime, capped
   concurrency, then base continues (the base instance is never torn down by
   an accent). [assumed seam — implementation spec must verify layering.]
4. **Shadow mode first (L7 law):** stage A0 runs the whole chain with
   rendering DISABLED — scheduled accents only produce decision-log lines —
   so density, conflicts, and timing error are measured in real mixing before
   a single photon changes. Density/conflict findings feed back to the
   compiler, not to runtime hacks.

### B.3 Precedence & restraint laws (explicit, total order)

From strongest to weakest, all [confirmed] surfaces cited in A.4:

1. Emergency blackout / blackout owners / smart-drop blackout mask
   (`_led_blackout_active`) — accents never render under any mask.
2. Manual and emergency roles (`led_look_director.py:196-212`) — operator
   hands win.
3. The existing drop-impact machinery — at drop arrival the impact is the
   authority; a scheduled `impact_flash` at the same moment DEDUPES against
   it (L7 dedupe group), never double-fires. `LED_MAX_DROP_IMPACTS = 2`
   remains the cap for drop hits; accent classes have their own per-class
   cooldowns from the schedule.
4. Breath-hold windows (fabric B.5, when built): during a hold, only
   `cut_honor`-compatible stillness is allowed; ramp-like accents are
   suppressed by the compiler (a compiler responsibility, decided offline —
   the runtime never arbitrates it live).
5. Accent overlays.
6. F4 seasoning (params on the base), then the base cue itself.
- Cleanup law: every accent instance dies on track change, seek out of its
  window, stop, deck switch, or mask onset — cleanup on EVERY transition
  path, not just natural expiry.
- Density law: schedule-side caps (compiler) AND runtime hard caps (existing
  `MAX_PULSES`-style bounds) — both, because §8 demands the runtime stay safe
  even against a defective schedule.

### B.4 Relationship to the energy fabric (stated, per charter)

- The fabric CASTS the base cue (E4) and grades the moment (layers 1-3); the
  accent layer answers scheduled events ON that base. Two different
  timescales of the same transcription: fabric = section/track scale, accents
  = event scale.
- Accent intensity inherits the fabric's grades where available: `drop_grade`
  and `section_energy` scale accent tier (a low-grade drop's `impact_flash`
  is still full-brightness — the no-dim-drop law — but its duration/cooldown
  profile can differ). Absent fabric data → schedule's own tier stands alone
  (fail open, both layers independent by construction).
- Neither layer blocks the other's rollout: accents can ship in shadow (A0)
  before E4 lands, and E4 casts bases regardless of accent availability.

### B.5 Staging (each stage = its own Codex spec, review, operator gate)

1. **A0 — shadow chain:** schedule format fixture + adapter + decision-log
   shadow (no rendering). Requires: L7 compiler emitting at least a hand-run
   schedule for testing (fixture schedules live in tests; per-track
   hand-authored schedules are TEST FIXTURES only, never shipped behavior —
   the generalization law stands).
2. **A1 — first two classes live:** `impact_flash` + `ripple` behind a
   default-off flag, §8 gates satisfied (incl. measured end-to-end timing
   against an operator-defined visible tolerance).
3. **A2 — `burst_overlay` + `cut_honor`.**
4. **A3 — `switchup_mark`.**
5. **A4 — `figure_track`** (last; needs a family payload that carries the
   figure's on/off envelope, and honest timing evidence).
Event-family availability (impulse_v1 etc.) is owned by the spectral program
roadmap (R5+); accent stages consume whatever families are confirmed, and A0
does not wait for them (fixtures suffice).

---

## Part C — Invariants that MUST still hold (live safety)

- 200 Hz push loop (`state_manager.py:499`) gains NO blocking I/O: schedule
  load is async at track load (§1.1/§8); the per-tick accent check is an
  in-memory lookup.
- `StateManager` remains the only `DeckState` writer; events immutable;
  ANLZ-before-TRACK_LOADED ordering unchanged.
- With the feature disabled or a schedule missing/stale/hash-mismatched:
  SoundSwitch, lasers, LEDs/Govee, reader state, blackout/emergency behavior,
  and logging remain unchanged (§8 verbatim — fail open to today's show).
- All masks and manual/emergency roles beat accents (B.3 order); accents
  never dim or delay a drop treatment; no accent renders during blackout.
- Laser subsystem: zero diffs, all stages.
- Runtime hard caps bound accent concurrency/rate independently of schedule
  correctness; a defective schedule can at worst produce capped, logged,
  maskable overlays — never darkness, never an unmasked strobe storm
  (per-class rate caps pinned in each stage spec).
- Live-mixing walk-throughs required per stage: seek across scheduled
  accents (no catch-up burst beyond existing `MAX_CATCHUP` discipline), loop
  wraps (wall-clock instances already immune, `beat_sync_engine.py:1-25`),
  deck switch mid-accent, mask onset mid-accent, duplicate-cue/dedupe with
  drop impact, stop/resume.

## Part D — Test seams (per stage; pure-function, no disk/subprocess)

- Schedule adapter: pure parse/validate/identity-check over in-memory
  fixtures; stale/mismatch → explicit disabled result.
- Accent arbitration: pure function (tick state × masks × active impact ×
  schedule window) → fire/suppress/dedupe decision; full precedence table
  from B.3 enumerated as cases, incl. the ANIMALS-2:00 no-event restraint.
- Instance lifetime: pure window math (spawn, expiry, every cleanup path).
- Shadow-mode invariant: with rendering disabled, zero frame-payload deltas
  (byte-compare) while decision-log lines appear.
- Fabric coupling: accent tier scaling with/without fabric data; no-dim-drop
  floor asserted.

## Part E — Acceptance / definition of done

**For this document (now):** exec review → operator gate on the DESIGN
(veto-first defaults: the class vocabulary in B.1, the precedence order in
B.3, and shadow-first staging stand unless vetoed). Classified as AWR-287 in
`docs/status/active_work_registry.md` (this round).

**For every implementation stage (later, non-negotiable):**
- Contract-first: expected keys `led_govee` (change_contracts.yml:101),
  `drop_presentation` (:430) for impact dedupe, `config_schema` (:670) for
  the flag/adapter config, `tests` (:785); the schedule adapter likely needs
  a NEW contract entry (add it before code, per the anti-drift rule).
- §8 runtime gates in full for anything that renders: measured end-to-end
  timing per backend, default-off, operator acceptance; offline precision
  never cited as live precision.
- Hard checks + full unittest suite green; §10 status language only.

### Non-scope (explicit)

- Laser accents / laser warrants (separate lane; laser chain zero-diff here).
- The cue compiler itself and event-family detectors (L7/L3 own specs, spectral
  program roadmap).
- Live audio event detection of any kind.
- F4 changes, base-cue casting (fabric E4), breath-hold (fabric E5), Template
  Lab pool expansion.
- Re-deriving, adjusting, or machine-checking the exemplar ledger timestamps.

### Claim ledger

- [confirmed] every file:line in Part A, re-read at HEAD 22fb4f6f, 2026-07-24.
- [assumed] beat_sync_engine's instance machinery is a sufficient overlay
  execution seam (A1's spec must verify layering vs the base instance).
- [assumed] the L7 schedule fields cover accent needs without extension
  (dedupe group + cooldown + tier map cleanly to B.3; verify at A0).
- [unknown] end-to-end LED latency vs the accent classes' visible tolerance —
  §8 requires measuring it before any live stage; A1 cannot pass without it.
- [unknown] whether `figure_track`'s envelope data will exist in a family
  payload (depends on the spectral program's future families; A4 waits).
