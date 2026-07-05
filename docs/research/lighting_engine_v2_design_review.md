---
doc_status: current
truth_level: design-review — code-verified at HEAD
last_verified_commit: 4a24209
last_verified_date: 2026-07-05
validation_scope: design review only — read-only code reading at HEAD plus the existing measured-corpus facts; no runtime behavior change, no bridge execution, no hardware validation
---

# LIGHTING ENGINE v2 — Adversarial Design Review

Fable 5 staged review (2026-07-05) of the full v2 design record
(`docs/research/spectral_palettes_arrival_crossfade_exploration.md`, "the record"). Every
load-bearing claim below is labeled **confirmed / assumed / unknown / rejected** and tied to a
file:line at commit `4a24209`, a design-record section, or a named measured fact from the
record's 2026-07-04 read-only sweep. The record was verified at `c39bfa3`; six cited files
changed since (logging overhaul), so every code claim used here was re-verified at HEAD —
re-located line numbers are given below and supersede the record's.

---

## 1. Verdict

**PASS WITH REQUIRED CHANGES.**

Plain meaning: the design is sound and buildable. Its two best decisions — deriving identity
from whole-track measurements that are proven stable, and the texture layer's
decorate-never-decide containment — are exactly the right lessons from the smart-drop failure,
and every primitive the design needs was re-verified to exist in the code at HEAD. But the
record is a layered negotiation transcript, not a clean spec input: several superseded early
layers (musical key in the color mapping, the double-drop moment, the Camelot palette board)
still sit in load-bearing sections and would poison a Codex spec written from them. Beyond
that, the biggest genuine design gaps are: the identity fallback tier quietly collapsed when
the operator cut musical key and nobody re-priced it; no rule says who wins when two designed
moments land on the same bar; the per-feature kill switches have no defined ownership map for
the twenty-one addendum behaviors; and the living-room-is-the-only-light fact bites four
specific darkness moves that were designed from festival lore. All fixable on paper, none
require hardware, and none invalidate the GO verdicts.

---

## 2. Rulings — every v2 element

Rulings: **KEEP** (build as designed) / **CHANGE** (build with the stated concrete change) /
**REDESIGN** (replace with the stated design) / **CUT** / **NEW** (proposal, §5).
Findings referenced as F-n (§3), operator-locked challenges as OLC-n (§4), proposals as P-n (§5).

### Feature 1 — track identity (colors)

| # | Element | Ruling | Basis / required change |
|---|---|---|---|
| 1.1 | Sound-character → color zone (grit/punch/bass/drama), neon zones | **KEEP** | Axes measured stable (Spearman 0.86–0.96, named measured fact — confirmed). Zone boundaries must be corpus-absolute, same rule Feature 4 already adopted (record §Feature 4 "absolute calibration") — see F-9 for the schema-upgrade consequence. Also OLC-3. |
| 1.2 | Deterministic per-track hash spreads tracks within zone | **KEEP** | Requires replacing today's salted seed — the current per-track seed mixes in the random set seed and the deck number (`led_color_engine.py:374-375`, confirmed), so it is not stable across nights. The record knows this; the pure-function replacement stands. See F-17 on the key choice. |
| 1.3 | Identity permanent across nights (pure function, no RNG) | **KEEP** | The correction path (1.10) becomes load-bearing, not optional — OLC-4. |
| 1.4 | Zones pick colors, never power; drops always full-scale | **KEEP** | Operator-locked; interacts with SET mode via addendum item 5's resolution — coherent. |
| 1.5 | Depth axis = saturation floor + gradient span only | **KEEP** | |
| 1.6 | Soft flip (4–8 beat p-space fade) at active-deck flip until Feature 3 | **KEEP with CHANGE** | Handover must key off the active-deck resolution flip, not the color engine's recent-track deque — the deque (maxlen 3, `led_color_engine.py:318-320,367`, confirmed) deliberately ignores A→B→A flips, which is right for "new track" dedupe and wrong for identity handover. F-10. |
| 1.7 | First-play bloom with ~8-beat hold gate | **KEEP with CHANGE** | Needs a precedence rule when it collides with a blend, build, or pre-drop window — F-4. Restart semantics: F-13. |
| 1.8 | Late-drop palette surprise stays inside the track's own colors | **KEEP** | Constrains the existing drop-snap (`led_color_engine.py:409-447`, confirmed) to within-identity — exactly what the record's spec bullets already pin. |
| 1.9 | Character drives motion style (punchy → sharp, smooth → flow) | **KEEP** | kick_cv stability 0.902 (measured fact). |
| 1.10 | Long single-zone stretches are a feature | **KEEP** | Operator-locked (chapters). See OLC-3 for the sameness edge. |
| 1.11 | Unmeasurable tracks → neutral-safe zone + operator correction path | **KEEP** | Correction path made concrete as P-6 (wrong-color veto pad). |
| 1.12 | 10-family Camelot palette board (Glacier…Solar table) | **REDESIGN** | Superseded inside the record itself: the neon-zone revision (addendum item 1) removed key from the color story, but the board still anchors families to Camelot neighborhoods. Replacement: re-cut the board as zone-anchored families — cool/deep set (blues/teals/purples) for smooth-melodic zones, electric-neon set (hot magenta, acid cyan, lime) for aggressive zones, deep red/purple for the dubstep-extreme zone, true red rare/earned — with the hash spreading hue within the family. Warm stops still get added to `scale_stops` (six cool-only stops today, `led_models.py:72-79`, confirmed) because earned ambers/reds need to exist in the scale; they are accents now, not key-owned families. F-1. |
| 1.13 | Tiered fallback (spectral → ANLZ+key → hash → journey) | **CHANGE** | Tier 2 silently died when key was cut and must be re-priced — F-2. Replacement tiering: Tier 1 spectral character (full identity); Tier 2 ANLZ-structure-only (dynamics budget from drop count + energy classes at `energy_model.py:15-29`, confirmed; zone = neutral-safe, hash-spread within it); Tier 3 hash-only; journey fallback unchanged. Plus the coverage fix: run the one-time library backfill (P-part of F-2) so Tier 1 covers ~the whole on-disk library instead of 66%. |
| 1.14 | Identity derivation decoupled from smart-rearm flags | **KEEP** | Still coupled at HEAD (`state_manager.py:566-569` requires `RBSS_SMART_REARM_EXPERIMENT` and `RBSS_SPECTRAL_ENABLE`, confirmed) — the record's own-flag decision stands. |
| 1.15 | Broken/no beatgrid tracks | **KEEP (as degrade)** | Spectral envelopes are beatgrid-keyed (`audio_spectral_features.py:153-194`, confirmed) → no grid means no character → hash tier; texture layer absent; arrivals ride the BPM-extrapolated anchor exactly as everything else. Safe-neutral by construction. |

### Feature 2 — Land on the One

| # | Element | Ruling | Basis / required change |
|---|---|---|---|
| 2.1 | Arrival scheduler in `BeatSyncEngine`, per-frame retarget from live anchor | **KEEP** | All primitives re-verified at HEAD: frozen `born_bpm` drift is real (`beat_sync_engine.py:26,190-201`, confirmed), wrap detection exists (`:50-68`, confirmed), the runner feeds a fresh anchor + live BPM every frame (`govee_realtime_runner.py:213-217,289-292,331`, confirmed), the push loop publishes the anchor with live BPM and a monotonic clamp (`state_manager.py:3671-3677`, confirmed). Zero push-loop work added — arrival math is runner-thread arithmetic. |
| 2.2 | Landing as infrastructure — existing comets/sweeps land on the one | **KEEP** | Highest impact per line; retrofits the whole comet library. |
| 2.3 | Build-move family: squeeze-explode, fuse (cascade), swell (phrase) | **KEEP** | Ship squeeze-explode as the visible demonstration per the record's own build-order logic. |
| 2.4 | Character picks the build move + body language, per-track consistent | **KEEP** | |
| 2.5 | Fires at every true drop, never on a bare 16/32-bar cycle | **KEEP** | ANLZ drop markers: 97.7% coverage, mean 6.6/track (measured fact); markers already drive v1 drop cues live, so the trust is inherited, and a missing marker just means no build move — safe absence. |
| 2.6 | Tempo bending: continuous retarget; recalc on backward jumps only | **KEEP with CHANGE** | Bind each arrival instance to (deck, load_gen); on anchor-deck change mid-flight, degrade (wall-clock finish or melt), never retarget across two decks' beat timelines — F-5 scenario 2. The wrap → wall-clock degrade and the jitter → trigger-on-beat degrade stand as written. |
| 2.7 | Audio-matched pre-drop blackout (silence-length-matched, cap ~4 bars; snap flick ~125–250 ms when music slams in) | **KEEP with CHANGES** | (a) Living-room ruling: §3 F-7 — true black stays the WILD OUT default because the room's own music is near-silent in exactly those beats (the sound explains the darkness); SET mode gets the ember floor (P-1). (b) The silence scan must reuse the operator-ear-validated empty-floor detector, not a second new detector (P-2 / F-16). (c) Owned by Feature 2's kill switch; kill reverts to the fixed 4-beat predark that exists in live config today (`led_predark_beats: 4`, live config, confirmed) — F-3. |
| 2.8 | Strobe acceleration lives in specific buildup cues (operator correction 2) | **KEEP** | Cue-owned behavior, role system schedules it — matches how v1 buildup cues already work (`govee_frame_renderer.py:644-731`, confirmed buildup strobe/ramp cues exist). Rates: see F-6 physics. |
| 2.9 | Drop-type cue selection (dubstep-wall / techno-comet / tech-house sparkle→groove / bass-house pulse-expand) | **KEEP with CHANGE** | Add an explicit low-confidence default: when the drop-window classification is ambiguous, select the track's neutral drop family (today's behavior, identity-painted). Misclassification consequence analysis in F-11. Chooses *which* cue, never *whether/when* — containment holds. |
| 2.10 | Trap vs dubstep drop distinction (sparse halftime hits + vacuum vs dense stutter) | **KEEP** | As classifier classes. The rhythmic vacuum's darkness ruling is in F-7. |
| 2.11 | LED-first; lasers join later via the pre-arm pattern | **KEEP** | `beat_math` future-beat mapping confirmed (`beat_math.py:50-68`); autoloop arm machinery present at HEAD (`autoloop_controller.py:151-167`, confirmed). |

### Feature 3 — mix-aware crossfade

| # | Element | Ruling | Basis / required change |
|---|---|---|---|
| 3.1 | Fader is the boss; takeover mirrors actual fader motion | **KEEP** | Upfader signal confirmed at HEAD: deck 1/2 chains only, 7.2.11 block only (`rb_offsets.py:90,108-111`, confirmed), 30 Hz poll (`rb_state_reader.py:136`, `config.py:60`, confirmed), 1.0 s staleness (`active_deck_resolver.py:12`, confirmed). |
| 3.2 | Accents-first, bar-quantized rhythmic entry, then base | **KEEP** | Bar-quantizing also masks unknown fader-step coarseness — good design. Requires the base/accent color contract, F-8. |
| 3.3 | Near colors glide; opposite trade ownership then commit | **KEEP with CHANGE** | Re-ground "near/opposite" in hue distance between the two identities' families (p-space distance), not Camelot adjacency — the record's §C3 harmonic framing predates the key cut and is superseded — F-1. The no-muddy-midpoint rule stands. |
| 3.4 | Quick blend compressed; slam = snap; chops = room chops along | **KEEP** | Snap-on-reset behavior confirmed (`smart_phrasing.py:206-214`). |
| 3.5 | Abandoned blend breathes back out (monotonic + hysteresis, no resolve fired) | **KEEP** | Correct shape; constants tuned from the recorded session (3.8). |
| 3.6 | Double drop CUT | **KEEP** | Operator-locked. But the accidental case still needs defined behavior — both faders top with both tracks inside drops happens without "doing double drops"; ruling: active-deck resolution picks the leader (both-top → low-EQ comparison already exists, `active_deck_resolver.py:125-140`, confirmed), the other deck's identity stays accent-only. F-15. The record's §C3 double-drop design paragraph is dead text and must not enter the spec — F-1. |
| 3.7 | Deck 1/2 only; 7.2.11 pin; silent degrade to time-based proxy | **KEEP** | Confirmed absent for decks 3/4 and the crossfader (closed label set, `rb_offsets.py:196-201,236-238`). Accepted operating constraint per the locked agreement. |
| 3.8 | Smoothing/hysteresis constants from one `RBSS_RECORD_SESSION` capture | **KEEP** | Fader physical smoothness remains **unknown** (record's label stands); acquisition path is the one hardware input only the operator can produce (§6 Q4). Tuning harness: P-5. |
| 3.9 | Blend consumes existing mixer machinery; active-deck resolution stays authority | **KEEP** | `MIXER_STATE` → snapshot → resolver rerun confirmed at HEAD (`state_manager.py:1138-1142`). Blend paints the in-between only. |
| 3.10 | Dipless blending + single-axis transitioning (addendum 6) | **KEEP** | Dipless is also the living-room-correct answer: the room's brightness floor holds during blends. |
| 3.11 | F3 requires F1 identities | **CHANGE (make explicit)** | With Feature 1 killed there is no incoming palette; blend must auto-collapse to the soft flip (1.6). Part of the kill matrix, F-3. |

### Feature 4 — texture layer

| # | Element | Ruling | Basis / required change |
|---|---|---|---|
| 4.1 | Per-beat texture map, precomputed at load, lookup at runtime | **KEEP** | Runs in the existing ANLZ worker thread pattern (`state_manager.py:1865-1899`, confirmed); dispatch-time lookup is in-memory — push-loop invariant holds. |
| 4.2 | Decorate-never-decide containment | **KEEP** | The strongest single decision in the design. Make it structural, not conventional: gate texture application at the dispatch policy on role ∈ {groove, ambient} so it *cannot* touch drop/buildup/landing cues — one predicate, enforced where roles are resolved (`led_dispatch_policy.py:732-772`, confirmed seam). F-4. |
| 4.3 | Tier 1 classes (kick-prominence, empty-floor, thick/thin, bright/dark tilt) | **KEEP** | Empty-floor detector operator-ear-validated (named measured fact). |
| 4.4 | Tier 2 (growl/whir; schema v4 + ~2 h re-analysis; proof required first) | **KEEP (future)** | Record is honest that current envelopes provably cannot separate these. Schema v4 re-extraction creates an identity-epoch risk — F-9. |
| 4.5 | Absolute corpus calibration, never per-track percentiles | **KEEP** | Extends to the blackout silence scan too (F-16). |
| 4.6 | Ear-test gate per class | **KEEP** | |
| 4.7 | Own kill switch | **KEEP** | Kill leaves role cues untouched by construction — coherent remaining behavior guaranteed by the containment rule. |

### Modes, switch architecture, pads, lasers, cue migration, observability

| # | Element | Ruling | Basis / required change |
|---|---|---|---|
| 5.1 | WILD OUT mode (every drop 100%, default) | **KEEP** | Operator-locked. Challenge on long-night adaptation: OLC-1. |
| 5.2 | SET mode (~80% held drops, ceiling reserved for peak tier) | **CHANGE** | Implement budgeting by **layer withholding**, not a flat 0.8 brightness multiply: held drops lose the white burst, the strobe ceiling, and full-strip span but keep 100%-intensity color hits; the true ceiling adds white + max strobe + full span back. Rationale: on LED strips a 0.8 intensity multiply is barely visible (gamma), while withholding white/strobe is exactly how the research's own pros budget; and the render seam is frame RGB composition, not device brightness — the runner hardcodes `set_brightness(100)` on activate (`govee_realtime_runner.py:319`, confirmed) — F-14. The ~80% number survives as the peak-brightness trim on withheld drops. |
| 5.3 | WILD↔SET flip mid-set | **KEEP with CHANGE** | Define once: mode changes take effect at the next look boundary (next dispatch/phrase step), never mid-move. One line in the spec — F-3. |
| 5.4 | Master switch: one engine at a time, live-switchable, v2 off ⇒ v1 byte-identical | **KEEP with CHANGE** | Byte-identical is achievable because the brain/body split is real (v1 director + color engine remain the untouched code path). Define mid-move flip semantics: switching tears down v2 instances through the existing reset/idle machinery (`beat_sync_engine.py:128-131`, `govee_realtime_runner.py` idle path, confirmed) and the newly-active brain takes over at the next dispatch — no cross-engine blending, ever. F-3. |
| 5.5 | Per-feature kill switches | **KEEP with REQUIRED CHANGE** | The kill-ownership matrix does not exist and must be written before specs — every addendum behavior (1–21) and operator correction maps to exactly one owning feature switch, and the three cross-feature dependencies get explicit degraded forms. F-3 (High). |
| 5.6 | New pad kinds via the existing MIDI pattern (engine switch, mode toggle, kills) | **KEEP** | Pad-kind pattern confirmed at HEAD (`soundswitch_midi_input.py:8,307,343-368`). |
| 5.7 | Palette pads become identity controls (lock identity / queue color) | **KEEP** | Gives the reserved color-engine live controls their surface (standing never-delete note honored). |
| 5.8 | Stream Deck Part F layered compositor stays orthogonal | **KEEP** | Manual overlay vs automation — orthogonal by authority design. |
| 5.9 | Laser: measured-character picker replaces playlist/BPM personality resolution | **KEEP** | Resolver confirmed (`personality_resolver.py:20,76-109`; default `house`, only {dubstep, house} personalities exist in live config — confirmed). The "catalog the hardware vocabulary" step (operator correction 6a) is genuinely load-bearing: two personalities is not a vocabulary. |
| 5.10 | Haze = UNKNOWN; both beam and surface designs stay in scope | **KEEP** | The one open physical question only the operator can settle (§6 Q3). |
| 5.11 | Laser design process: catalog → Claude drafts per zone → live audition → lock | **KEEP** | Template-Lab-style audition is proven practice in this repo. Zone-complement coloring: P-4. |
| 5.12 | Cue migration: shape/color split, library collapse, identity paints | **KEEP with CHANGE** | Baked-color cues confirmed at HEAD (`govee_frame_renderer.py:346,394,456` — name-carried colors). The split requires a uniform per-cue color-slot contract (base / accent / white) across all ~40 render functions so identity and the blend painter have defined injection points — F-8. `color_source` engine/baked seam already exists (`led_models.py:241`, confirmed). |
| 5.13 | `drop_pairs` survives, parameterized by identity | **KEEP** | |
| 5.14 | Template Lab authors shapes; engine supplies color | **KEEP** | |
| 5.15 | v1 DIY looks + color tags → v2 accent vocabulary | **KEEP** | |
| 5.16 | High-impact cooldowns carry into v2 pacing | **KEEP with CHANGE** | 12 s cooldown confirmed in live config. Define which v2 classes are "high-impact": drop bursts yes; phrase-end stingers and turnaround accents must be their own (shorter) class or every second stinger silently vanishes — a 16-bar phrase at 140 BPM is ~27 s, but stinger + drop + white burst interactions inside one phrase will collide with a single global 12 s lockout. F-12. |
| 5.17 | Observability: engine, identity/zone, mode, texture class + reason in status; LED Pad identity chip | **KEEP with CHANGE** | Add: per-feature kill states, last drop-type classification + its reason, live blend scalar, and a per-track identity log line at load (track → zone → color) so zone misfires are reportable precisely — feeds P-6. Cheap, all read-side. |
| 5.18 | Addendum items not separately listed (2 white-burst decay, 7 complementary pairs, 8 fade constants, 9 monolithic strip idiom, 13 trim knob, 15 diffusion note, 16 archetype refinements, 18 phrase stepping, 19 intra-phrase development, 20 turnaround stinger) | **KEEP** | Item 18's dependency confirmed: phrase grid + crossing flags already flow into LED dispatch (`led_dispatch_policy.py:707-709`, confirmed). Item 20 rides the arrival scheduler (2.1) and the cooldown-class fix (5.16). Item 9 matches the renderer's whole-strip idiom (confirmed by inventory). Item 14 palate reset: **KEEP as a dim neutral wash, not a blackout** (living room, F-7). Item 21 span scaling: **CHANGE**, see F-7 — span scales, but off-span segments drop to a dim base, not black, outside short accents; "center" must be a configurable anchor point on a room-perimeter strip (60 segments around the room — live config, confirmed). |
| 5.19 | Vocal-flip treatment | **CUT — confirmed already cut** | Operator correction 1 stands; silence-only scan. Round-3's pop-wash lore does not re-enter through any other item — checked. |
| 5.20 | Record's seeds: drop-landing restore / texture-gated accent discipline / key-neighborhood pre-echo | **KEEP / KEEP / CHANGE** | Seed 1 elevated into Feature 2 proper (P-3). Seed 2 is a natural Feature 1 output (eligibility predicate seam confirmed, `led_color_engine.py:453`). Seed 3: replace "key-neighborhood" with "identity-family pre-echo" — key is out of the color story; the mechanism (ambient accents drift one step toward the incoming track's family on load) survives unchanged and needs no key at all. |

---

## 3. Findings (severity-first)

**F-1 (High) — Superseded design layers still stand in load-bearing sections; they will
poison Codex specs.** Location: record §"What a Codex spec must pin" (Workstream A bullet:
"fixed published mapping from the four axes **+ key** to family"), §A3 dimension 1 (key→Camelot
hue), the 10-family Camelot board, §C3 "Harmonic mix vs clash" (Camelot adjacency) and §C3
"The double drop" — all superseded by the locked agreement (key out of the color story;
operator: no double drops) but never struck. Failure scenario: a Codex spec author follows §1
source-of-truth order, reads the spec-pin bullets as the distilled instruction, and ships a
key-driven palette mapping and/or a double-drop moment that the operator explicitly vetoed.
Required change: before any spec is authored, amend the record to mark those passages
`stale/superseded — see Locked agreement` (or excise them into a history appendix). The
walkthrough-revisions-win rule the record states in prose must be made visible at every
superseded site. **Confirmed** (all cited passages present in the record at HEAD).

**F-2 (High) — The identity fallback tier collapsed when key was cut, and the record never
re-priced it.** Location: record §A3 "Tiered fallback" Tier 2: "key hue (100% coverage)…
hue family and dynamics remain solid… hue is the recognition carrier." With key removed from
the color story (locked Feature 1 item 1), Tier 2 has **no zone input at all**: zones come
from spectral character (grit/punch/bass/drama), which exists only in the spectral cache; ANLZ
mood is near-constant (92.5% mood=1, measured fact) and drop structure gives dynamics, not
character. Failure scenario: any track without a cache entry (currently ~34% of the on-disk
library — 455 of 686 join, measured fact) silently gets a neutral-zone identity, and on a
night with several uncached tracks the "every track wears its own light" premise visibly
fails for a third of the set. Required change: (a) re-specify Tier 2 as
structure-only-dynamics + neutral-safe zone + hash spread (ruling 1.13); (b) close the gap at
the source — one background backfill sweep extracting spectral features for the whole on-disk
library (the extraction path and cache already exist and fill at load,
`state_manager.py:1865-1899`, `spectral_cache.py:175-192`, confirmed; the record's own Tier-2
schema-v4 estimate prices a full re-analysis at ~1.5–2 h). After backfill, Tier 1 coverage is
effectively total and Tier 2 becomes a corner case. **Confirmed** (coverage numbers are the
record's measured facts; the key cut is operator-locked text).

**F-3 (High) — No kill-switch ownership matrix; per-feature kills and mode/engine switches
have undefined combined states.** Location: record §Locked agreement (packaging bullets) and
§v1→v2 mapping (switch architecture) — the *existence* of switches is locked, but nothing maps
the 21 addendum items + 4 operator corrections to owning switches, and three cross-feature
dependencies are undefined: blend-needs-identity (F1 off + F3 on), blackout-owned-by-landing
(F2 off ⇒ audio-matched blackout reverts to the live config's fixed `led_predark_beats: 4` —
confirmed present), landing-retimes-role-cues (F2 off ⇒ cues trigger-on-beat as today).
Failure scenario: operator kills Feature 1 mid-night because a zone misfires; Feature 3 keeps
running, asks for the incoming deck's identity, gets none, and the blend paints undefined
colors (or crashes dispatch — which the engine-guard swallows into engine-off,
`led_dispatch_policy.py:744-761`, confirmed, silently killing *all* v2 color work). Required
change: a one-page kill matrix in the record before specs: every behavior → owning switch;
the three dependency rules above; mode/engine flips take effect at the next look boundary
(rulings 5.3/5.4). **Confirmed** (absence verified by reading the full record).

**F-4 (Medium) — No arbiter for colliding designed moments.** Location: record features 1–4
jointly; the cue-layering correction (operator correction 4) orders texture vs role cues but
nothing orders the *new* moments against each other. Failure scenario: a first-play track is
blended in and its first drop is 8 beats past the fader commit — bloom (1.7), blend resolve
(3.2), landing build (2.x), pre-drop blackout (2.7), and a phrase-boundary step (item 18) all
claim the same two bars; whichever dispatch order wins is accidental, and the room sees two
moments stepped on each other (e.g. a bloom brightening *into* a pre-drop blackout). Required
change: one precedence list in the spec, applied at dispatch: emergency/manual (existing
authority, unchanged) > pre-drop blackout + drop cue > landing move > blend resolve > palate
reset > first-play bloom > phrase step/stinger > texture seasoning. Lower-priority moments
inside a claimed window are skipped, not queued (they're moments, not tasks). **Confirmed**
gap (no such rule exists in the record).

**F-5 (Medium) — Arrival instances can retarget across deck timelines.** Location: record §B2
(per-frame retargeting) — progress is recomputed from the live anchor each frame, but the
anchor's *deck* can change mid-flight (active-deck flip, `get_active_beat_anchor` returns
whatever deck is active — `led_dispatch_policy.py:260-274`, confirmed). Failure scenario:
backspin on deck A during a landing move; resolver flips to deck B whose `abs_beat_pos` is 300
beats away; the arrival math sees a huge forward jump — progress clamps or the move melts, but
in the worst case (B's position just *behind* the target) the move retargets onto a musically
unrelated downbeat and "lands" mid-phrase on the new track. Required change (cheap): stamp
each arrival instance with (deck, load_gen) at spawn; anchor mismatch ⇒ degrade to wall-clock
completion (the existing wrap path). **Confirmed** (anchor carries `deck`,
`led_models.py:244-252`; nothing in the design binds instances to it).

**F-6 (Medium) — Strobe physics: the render pipeline caps realizable strobe at 15 Hz, with
aliasing artifacts well below that.** Location: addendum item 4 ("drop bursts may run
high-Hz") and the round-2 research constants (15–30 Hz). The realtime path renders at 30 fps
(`govee_realtime_runner.py:54,208`, confirmed) and strobes are frame-sampled square waves
(`govee_frame_renderer.py:276-284`, confirmed): 15 Hz is the absolute ceiling (1 frame on / 1
off), and non-divisor rates (e.g. 12 Hz at 30 fps) alias into irregular flutter; LAN send
jitter adds more. Failure scenario: a buildup cue specced to accelerate 4→20 Hz reads clean to
~7.5 Hz, turns into shimmer, then plateaus — the acceleration illusion dies exactly at the
climax. Required change: spec strobe rates as frame-divisible steps (30/n: 15, 10, 7.5, 6,
5…) and design acceleration as stepped rate + rising intensity/width (the eye reads the
combination as continuous). This is physics, not a policy cap — the operator's no-cap lock is
untouched (see OLC-2 for the comfort challenge). **Confirmed** (code); perceptual claim
**assumed** (standard, but the live pass is the gate).

**F-7 (Medium) — Living-room darkness audit: four designs imported festival darkness into the
room's only light source; two need floors, two are fine as-is.** The constraint (record
§Venue reality) applied item by item: (a) **audio-matched pre-drop blackout (≤4 bars)** — KEEP
true black in WILD OUT: the music itself is near-silent in exactly those beats, the operator
already runs 4-beat hand-tuned blackouts live (`led_predark_beats: 4`, confirmed), and the
sound explains the darkness to the room; SET mode defaults to the ember floor (P-1). At 140
BPM the 4-bar cap is ~6.9 s of total darkness — flagged as the taste veto in §6 Q1. (b)
**trap rhythmic vacuum** (items 16/17) — the drop phrase is mostly-dark with blinding hits
for 30+ s; in a living room this is the single most likely "someone trips or asks for the
lights" moment. CHANGE: vacuum gaps render at the ember floor by default in SET mode; WILD
OUT keeps true 0% (operator-locked spirit), with the floor available as a per-cue param. (c)
**span scaling** (item 21) — "small center segment in verses" would leave the room's only
light at a fraction of one wall for minutes. CHANGE: off-span segments hold a dim identity
base (depth-axis-scaled), not black; span contrast comes from motion living in the span, not
from darkness outside it. (d) **palate reset** (item 14) — CHANGE to a 1–2 s dim neutral
wash, never a blackout: a genre pivot is not a musical silence, and an unexplained 2 s
room-blackout reads as a power cut. (e) **SET-mode dimming** — resolved by ruling 5.2
(withhold layers, don't dim the room). (f) **breakdown ease-down** (P-3) — bounded by the
track's dynamics budget and never below the ember floor in SET mode. **Confirmed** constraint
(operator venue statement); each ruling is design judgment for the live-look gate.

**F-8 (Medium) — The blend painter and identity recoloring need a uniform per-cue color-slot
contract that does not exist yet.** Location: record §v1→v2 mapping ("split shape from
color") and §C3 (accents-first entry). At HEAD, color lives per-function: baked name-carried
palettes (`govee_frame_renderer.py:346,394`, confirmed), per-effect params, and engine slots.
Accents-first blending requires every cue to expose *which* of its pixels are "base" vs
"accent" vs "white" so the incoming identity can take accents first. Failure scenario
without it: the blend painter lerps whatever params it can find; on half the cue library the
"accent" is baked and the blend reads as nothing happening until a full-base snap. Required
change: the shape/color split defines exactly three color slots (base / accent / white) as
the cue-author contract; Template Lab authors shapes against those slots; blend and identity
paint only through them. **Confirmed** (code state); contract proposal is the concrete
replacement.

**F-9 (Medium) — "Permanent identity" breaks silently at extraction-schema upgrades.**
Location: record Feature 1 lock item 2 (permanent across nights) + §Feature 4 Tier 2 (schema
v4 re-extraction planned). Zone assignment discretizes continuous measured axes; re-extraction
under a new schema shifts envelope values, and boundary tracks flip zones — permanence is
only guaranteed *within* a schema epoch (bit-identical re-extraction is a measured fact, but
only for the same schema). Failure scenario: Tier 2 ships, the library re-analyzes overnight,
and a dozen familiar tracks wear new colors with no explanation. Required change: identity
derivation pins its input schema version; a schema upgrade is a declared identity epoch —
either freeze identity on the v3 scalars (derive-once-and-store per content id) or announce
the epoch in status and let the correction path (P-6) handle the handful that land wrong.
Recommend freeze-and-store: it also makes identity survive cache eviction. **Confirmed**
(schema staleness invalidates cache entries wholesale — `spectral_cache.py:175-181`).

**F-10 (Medium) — Identity handover keyed on the wrong seam.** Location: record §A2(a) and
§What-a-spec-must-pin (consume at `begin_dispatch`, replacing the palette pick "at track
boundary"). The color engine's new-track detection dedupes via a 3-deep recent-keys deque
(`led_color_engine.py:318-320,365-370`, confirmed): A→B→A within three keys does *not*
re-trigger the new-track branch. Right for RNG-journey dedupe; wrong for v2 — flipping back
to deck A must repaint A's identity. Failure scenario: operator cuts to deck B for 16 bars
and back; the room keeps wearing B's identity while A plays. Required change: v2 identity
selection follows the active-deck flip event (the soft-flip trigger, ruling 1.6), with the
deque left to the v1 journey path it was built for. **Confirmed**.

**F-11 (Low) — Drop-type misclassification consequences are asymmetric; default must be
neutral.** A wrongly-chosen dubstep wall sustained through a tech-house phrase is the loudest
possible wrong seasoning (16 bars of full-strip strobe), while a wrongly-neutral drop is
invisible. The classifier (drop-lift intensity + texture axes in the drop window,
`energy_model.py:15-29` classes confirmed) therefore needs confidence thresholds tuned so
ties and thin data always land on the neutral family. Fires only from Rekordbox markers —
whether/when containment unaffected (operator correction 3 honored). Required change: spec
the neutral default + publish the classification and its reason in status (ruling 5.17).

**F-12 (Low) — One global 12 s high-impact cooldown will eat the new per-phrase accents.**
Live config `high_impact_cooldown_s: 12` (confirmed). Phrase-end stingers (item 20),
turnaround accents, and white bursts (item 2) inside the same phrase will trip it. Required
change: cooldown classes — drop-scale impacts keep 12 s; stinger/burst class gets its own
short cooldown; classes documented in the spec so v1's discipline carries over deliberately,
not accidentally (ruling 5.16).

**F-13 (Low) — "First play of the night" needs a session-boundary definition.** A bridge
restart mid-night (which happens — watcher restarts are routine) clears in-memory seen-sets
and every track blooms again. Default chosen: accept re-blooms after restart (in-memory
set only, zero persistence machinery); veto path in §6 Q2. Required change: state the choice
in the spec so it's a decision, not an accident.

**F-14 (Low) — SET-mode brightness must be applied in frame composition, not device
brightness.** The runner asserts `set_brightness(100)` at activate (`govee_realtime_runner.py:319`,
confirmed) and per-frame device brightness calls are not part of the 30 fps contract. The
trim knob (item 13) and SET budgeting scale RGB values in `_compose_frame` — one multiply,
gamma-aware. **Confirmed** seam.

**F-15 (Low) — Accidental simultaneous drops need defined behavior under the double-drop
CUT.** Ruling 3.6: leader = active-deck resolution (existing both-top low-EQ rule,
`active_deck_resolver.py:125-140`, confirmed); the other deck contributes nothing beyond its
ordinary blend-accent share. No new moment fires. One sentence in the spec.

**F-16 (Low) — One silence primitive, two consumers.** The audio-matched blackout scan
(addendum 3) and the texture layer's empty-floor class (Feature 4) are the same physical
question ("is the bottom gone on this beat?"). The empty-floor detector is already
operator-ear-validated (measured fact); the blackout scan must call it, not re-implement a
second near-zero test with its own thresholds. Prevents the two features from disagreeing
about silence on the same beat — which would produce a blackout over a beat the texture layer
paints, exactly the kind of incoherence the kill matrix can't fix. Also P-2.

**F-17 (Low) — Identity key durability.** `content_id` with filepath fallback (record spec
bullets) survives nights but not necessarily a Rekordbox database rebuild. If permanence is
the product, derive the hash from the most durable identifier available (filepath, or
content_id + filepath both checked at load with filepath winning on mismatch). Cheap to pin
now, painful to migrate later. **Assumed** (DB-rebuild id behavior unverified — flagged as
the reason to prefer filepath).

---

## 4. Operator-locked challenges

**OLC-1 — WILD OUT as the every-night default (lock: "drops always 100%, WILD OUT default").**
Motivating scenario: a 3-hour night. Eyes adapt; by hour two a 100% white-and-strobe drop
delivers measurably less perceived punch than the same drop an hour earlier, because there
was no contrast budget — the room has seen the ceiling thirty times. SET mode already exists
and is the professional answer (round-2 lore, adopted by the operator as a mode); the
challenge is only the *default*: consider SET as the default for sessions the operator
expects to run long, keeping WILD OUT one pad-press away. The lock's spirit — "when I want
100%, nothing dilutes it" — survives fully; this only changes which mode the night starts in.
Taste call; veto-shaped in §6 Q5.

**OLC-2 — Uncapped strobe rates (lock: "no rate cap in v2").** Two motivating facts, one
scenario. Fact 1 (physics, F-6): above 15 Hz the pipeline cannot render a strobe at all, so
the lock's upper region is unreachable regardless of policy — no config cap needed, the frame
clock *is* the cap. Fact 2 (the room): strips are the only light; a sustained high-rate
strobe in someone's whole field of view is the most probable "guest asks for it to stop"
event of any v2 behavior. Scenario: a dubstep stretch chains three drop phrases; strobe
bursts with no burst-length discipline run near-continuously for 90 s; a guest gets genuinely
uncomfortable and the operator has to fumble for a kill mid-set. Challenge: keep the lock (no
*rate* cap), but adopt burst-length discipline as cue-design guidance — bursts decay after a
few seconds (round-2 item, already scene lore) and the between-burst floor breathes. This is
authoring guidance for the cue library, not an engine cap, so the lock stands untouched.

**OLC-3 — Neon zones (lock: aggressive → electric neons; operator: "i like where we are
going").** Motivating scenario: the operator's library skews aggressive (the
aggression-ranking measured fact), so on a bass-heavy night most tracks land in the same
electric-neon zone — three trap tracks in a row wear hot-magenta/acid-cyan/lime variations
and the "every track wears its own light" premise flattens into "every track wears neon."
Challenge (inside the lock): the zone keeps its neon anchor, but in-zone spread must be
engineered wide — the hash spreads hue meaningfully across the family, and the depth/dynamics
axes (saturation floor, gradient span, excursion budget) must be visibly different between
same-zone neighbors, so recognition comes from the *combination*, not hue alone. If the live
pass still reads as sameness, the fix is more zones on the aggressive side (splitting by
punch vs grit), not abandoning neon.

**OLC-4 — Permanent identity (lock: pure function, no RNG, permanent across nights).** Not a
challenge to reverse the lock — a consequence it must carry: permanence means a wrong zone
assignment is *permanently* wrong until corrected, every night, on a track the operator
plays often. The correction path (locked item 10) is therefore a launch requirement, not a
nice-to-have — it must exist the first night v2 paints identities (concrete form: P-6).
Scenario without it: one beloved track lands acid-lime forever, and the only fix is a config
dive mid-week from memory.

---

## 5. New proposals (each cleared against: reliable signals only / zero per-track authoring /
safe-neutral failure / living-room reality / existing kill-switch + authority architecture)

**P-1 — The ember floor.** A single global "minimum room light" layer: sustained dark states
(anything darker than N% for more than ~2 bars outside a WILD OUT drop window or pre-drop
blackout) render at a barely-there deep-red/amber glow (~3–5%, identity-tinted where one
exists) instead of true 0%. SET mode: on by default. WILD OUT: off (locks honored). Gates:
no signals needed (pure render policy — reliability trivially satisfied); zero authoring;
failure mode is *more* light, never less (safe-neutral); it exists *because* of the living
room; sits below manual/emergency authority and dies with the master switch. One multiply +
clamp in frame composition (same seam as F-14).

**P-2 — One silence primitive.** Promote the operator-ear-validated empty-floor detector to a
single shared "bottom-gone" classifier consumed by the texture darkness class, the
audio-matched blackout scan, and landing-move eligibility. Same cached envelopes, corpus-
absolute thresholds (Feature 4's own calibration rule). Gates: measured + ear-validated
signal; no authoring; absent data ⇒ absent classification ⇒ no darkness (safe); one truth
about silence keeps every darkness feature coherent with every other (F-16).

**P-3 — Landing restore as Feature 2's marquee moment.** Elevate the record's seed 1 from
"seed" to Feature 2 scope: during a detected breakdown, ease the room down within the track's
dynamics budget, then use the arrival scheduler to fly light back in so it *lands on the
drop's first beat* — the drop beat is known ahead of time from ANLZ (confirmed) and pre-arming
against a future beat is the proven autoloop pattern (confirmed). It is the same machinery as
the build family, it composes the blackout + landing + drop-cue stack into one legible arc,
and it is the single v2 moment guests will describe out loud. Gates: backbone signals (ANLZ
markers + arrival engine); no authoring; marker absent ⇒ today's role change (safe); respects
the ember floor; owned by Feature 2's kill.

**P-4 — Zone-complement laser pairing.** Make addendum item 7's proven pairs the laser
personality rule: each color zone carries a fixed complementary accent pair (neon zones →
cyan+magenta family; smooth/deep zones → deep blue+amber; extreme zone → red+white), and the
measured-character picker (ruling 5.9) selects the personality whose accent pair matches the
zone — LEDs and lasers contrast by construction, never mud. Gates: same measured axes as
Feature 1 (reliable); pairs are config, not per-track (no authoring); no character ⇒ default
personality exactly as today (safe, `personality_resolver.py:108-109` confirmed); haze-agnostic
(colors apply to beams or surface patterns alike); lives inside the existing personality/kill
architecture.

**P-5 — Blend rehearsal harness.** Feature 3's constants (EMA, hysteresis, bar-quantize
thresholds) get tuned offline against the one recorded practice session: a small read-only
tool replays the captured `MIXER_STATE` stream through the blend state machine and renders
the presence-step/scalar timeline (the session recorder already captures generic bridge
events — record §C1, confirmed env-gated recorder). Every constants change re-runs against
the same captured blends — no live iteration burned on tuning. Gates: it's a test harness
(no runtime surface at all); fails safe by definition; directly converts the record's one
labeled unknown (fader smoothness) into a repeatable asset.

**P-6 — The wrong-color veto pad.** The concrete correction path locked item 10 requires:
one pad/LED Pad action ("wrong color") that, for the currently-active track, logs content id
+ current zone to a small corrections file and immediately re-derives identity with the next
zone over (cycling on repeat presses). File-backed (survives restarts), per-track scoped,
empty by default (zero authoring until the operator objects to a specific track — which is
the *definition* of the correction path, not per-track authoring). Failure: file unreadable ⇒
derived identity as computed (safe). Surfaces via the existing pad-kind pattern (confirmed
seam) and shows in the status identity line (ruling 5.17).

---

## 6. Open questions for Brandon (taste only — defaults are chosen; veto if wrong)

1. **How dark is "blackout" allowed to get?** Default built: in WILD OUT mode the pre-drop
   blackouts and trap-drop gaps go truly pitch black (the music is silent there — the room
   will understand); in SET mode the room never drops below a barely-visible deep-red glow so
   people can find their drinks. Veto either half.
2. **If the bridge restarts mid-night, tracks may do their first-play bloom again.** Default:
   we accept the re-bloom (it's rare and it's pretty). Veto if you'd rather it never repeat —
   that costs a small memory file.
3. **Haze:** still marked unknown from your side. If you'll ever run haze, say so before the
   laser package is designed — it changes lasers from wall-pattern drawing to beam shows.
4. **The one recording:** Feature 3's fader feel still needs that single practice session
   with `RBSS_RECORD_SESSION` set, riding a few long blends on the DDJ-800. Nothing else in
   v2 waits on hardware from you.
5. **Long nights:** WILD OUT stays the default as you locked. If a night runs past ~2 hours,
   the drops genuinely hit softer to adapted eyes. If you ever want it, "start in SET,
   WILD OUT one pad away" is built and waiting — no action needed now.

---

## 7. Claim-label index (load-bearing claims of this review)

- Frozen-BPM animation drift + wrap immunity + TTL expiry — **confirmed**
  (`beat_sync_engine.py:1-6,26,50-68,183-188,190-201`).
- Live anchor per frame with live BPM + monotonic clamp — **confirmed**
  (`govee_realtime_runner.py:213-217,289-292,331`; `state_manager.py:3671-3677`;
  `led_dispatch_policy.py:260-274`).
- Mixer offsets 7.2.11-only, decks 1/2 only, no crossfader; 30 Hz poll; 1.0 s staleness —
  **confirmed** (`rb_offsets.py:90,108-111,196-201,236-238`; `rb_state_reader.py:136,470,472`;
  `active_deck_resolver.py:7-12,45-50,75-76,125-140`; `config.py:60`).
- Journey RNG session-seeded; per-track seed salted with set seed + deck; recent-keys deque
  maxlen 3; drop-snap re-pick — **confirmed**
  (`led_color_engine.py:269-284,318-320,365-376,396-400,409-447`; live config
  `set_seed_mode: "random"`).
- Six cool-only default scale stops; single-deck LEDContext; `color_source` seam; BeatAnchor
  shape — **confirmed** (`led_models.py:72-79,213-226,241,244-252`).
- Spectral extraction beat-keyed, per-band peak-normalized, flatness unnormalized; cache
  staleness = schema + mtime + size; extraction off the push loop in the ANLZ worker;
  spectral still coupled to smart-rearm flags — **confirmed**
  (`audio_spectral_features.py:117-123,148-150,153-194,197-201`; `spectral_cache.py:175-192`;
  `state_manager.py:566-569,1865-1899`).
- Live config: 72 looks; palette weights blue_cyan 10 / indigo 6 / deep_ocean 4 / violet 3 /
  crimson 2 / white_sand 0 / rainbow 0; `led_predark_beats: 4`; safety caps (max_brightness
  100, strobe 750 ms, high-impact cooldown 12 s, drop_flash 750 ms) — **confirmed** (read
  2026-07-05).
- Renderer: 30 fps frame-sampled strobes; baked name-carried cue colors; whole-strip idiom;
  `set_brightness(100)` at activate — **confirmed**
  (`govee_frame_renderer.py:276-284,346,394,456`; `govee_realtime_runner.py:54,208,319`).
- Laser personalities today = {dubstep, house}, default house; playlist/BPM/default
  resolution — **confirmed** (`personality_resolver.py:20,76-109`; `config/laser_director.json`).
- Pad-kind pattern for new controls — **confirmed** (`soundswitch_midi_input.py:8,307,343-368`).
- Phrase grid + crossing flags reach LED dispatch — **confirmed** (`led_dispatch_policy.py:707-709`).
- Corpus numbers (coverage 455/476/686, stability 0.86–0.96, mood skew 92.5%, drop markers
  97.7% / 6.6 per track, aggression ranking, empty-floor ear validation, growl/bright
  non-separability) — **confirmed as the record's named measured facts** (not re-derived,
  per review charter).
- Fader physical smoothness during a ride — **unknown** (unchanged; acquisition path §6 Q4).
- Govee device-side processing latency — **unknown**; all v2 timing claims ride the identical
  anchor/transport chain as v1's live-validated beat-locked looks, so landing accuracy is
  **assumed** equal to v1's proven feel pending the operator's live pass (F-6 note).
- Perceptual claims (adaptation, aliasing visibility, 80%-vs-100% gamma flatness) — **assumed**
  (standard practice + research lore; the live-look gate is the arbiter).
- Rekordbox DB-rebuild content-id stability — **unknown** (F-17's reason to prefer filepath).
