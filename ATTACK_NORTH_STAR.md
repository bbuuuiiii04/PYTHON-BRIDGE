# ATTACK: does passing the list deliver the instrument?

**Written 2026-08-02 by a fresh adversarial seat with no history in the eight review rounds.
Read-only attack; nothing else was changed. Every claim is labelled
[confirmed] / [assumed] / [unknown]. All file:line references were read at the current HEAD
during this attack.**

The question under attack: the acceptance gate says one per-track list (laser moments with
position + length, track energy, drop energy, accented moments) passing his ear cold means the
bridge is successful and greenlit for live wiring. His actual goal, in his own ratified words, is
lights that are **an instrument performing the track** — transcription, sound to light directly,
per-element light-voices, energy read on three layers, cues cast never cycled, base + event-locked
accents. Is the program building that, or building a very good receipt?

Short answer up front: **the list is the right first gate and his ordering is right — but the
word "wiring" is hiding a second program roughly the size of the first.** Today, of the four
columns his ear will approve, **zero have a runtime consumer that could perform them.** The
detailed findings follow, worst first in each pass.

---

## PASS 1 — SUFFICIENCY: can the list, as specced, drive the vision?

### 1.1 WORST: the lengths he ruled co-equal with location have no way to be executed. [confirmed]

His law (acceptance-gate memory, verbatim): *"how long the lasers last for is literally AS
important."* The list contract enforces it absolutely — refusal R2, no row without
`extent_beats`, any role, any component (`local/spectral_v5_2026_07_17/acceptance_list_format_v3.md:508`).
The paper side is airtight.

The performing side cannot receive a length at all:

- The laser path fires a MIDI scene and holds it by **personality config constants**, not by
  moment data: `drop_impact_beats` defaults to 32.0 and `post_drop_cycle_beats` to 32.0
  (`laser_director.py:209-214`), `post_drop_hold_beats` is a config knob (`laser_director.py:103`).
  A scene's own hold time is per-scene config (`hold_beats` → ms conversion,
  `laser_executor.py:726-740`). There is no path anywhere that says "this laser lasts 14 beats
  because this growl lasts 14 beats."
- The LED path is the same shape: `LEDLookDecision` carries no per-event length
  (`led_models.py:447-459`); the only durations the LED system understands are config-owned —
  `drop_pairs[look].duration_beats` default 8.0 (`led_look_director.py:443-447`) and
  `LED_DEFAULT_DROP_IMPACT_BEATS = 8.0` (`led_dispatch_policy.py:34`). Inside the renderer,
  `duration_beats` is a **modulo** — a loop length, not a stop time
  (`govee_frame_renderer.py:367-369`); nothing in the renderer ever ends a cue.

So a passed row "growl, 14 beats, cuts at beat 16" certifies the machine *heard* 14 beats.
The rig, wired as it stands, would fire its configured scene and hold for its configured
constant. **Failure scenario:** the exact Palm of My Hands row he called textbook passes the
list; live, the laser runs 32 beats into the section after the growl died, which is the "lasers
need to ACCENT the moment" failure he wrote the length law to kill.

### 1.2 The accent quarter of the list describes a capability the rig does not have. [confirmed]

The accent vision is a discrete, exactly-timed light event layered ON TOP of a running base look
(his ratified articulation, accent-layer memory). I searched the three LED consumers for that
mechanism and it does not exist:

- One decision → one look → one effect at a time; the dispatch layer never composites two looks
  (`govee_frame_renderer.py:2109-2183` is the single render entry; `fold_additive` at
  `:2100-2107` is only used inside individual effects).
- There is no scheduler: no way to fire anything at an arbitrary track time, and no queue of
  future events — the only queued thing is the paired post-drop look slot
  (`led_look_director.py:619-630`). The dispatch layer is purely reactive to current
  `SmartPhrasingState` crossings (`led_dispatch_policy.py:1271-1605`, role computation
  `:2288-2325`).
- "Stab" exists in the codebase only as an F4 texture tag that nudges parameters like
  `sparkle_density` on the base look (`led_dispatch_policy.py:162-178, 1251-1269`) — the
  seasoning he has never once noticed, per his own memory record.

The list's `shape` field (beat_mask, stab_train, envelope — `acceptance_list_format_v3.md:333-356`)
is genuinely the closest thing the program has to transcription content, and it maps beautifully
onto his verdict corpus. But **no renderer parameter accepts a beat_mask or a stab train**
(the per-effect parameter allowlists at `govee_frame_renderer.py:1156-1192, 2011-2063` contain
nothing of the kind — and an un-allowlisted parameter disables ALL LED output,
`govee_frame_renderer.py:2006-2010`). The one column that carries "what the light does, beat by
beat" has nowhere to land.

### 1.3 Both energy columns grade quantities the runtime never uses. [confirmed]

- The per-drop energy grade the list will show him (E3) is attached to `DropDecision` explicitly
  as **STATUS-ONLY — "no presentation/laser/LED path reads this"**
  (`drop_presentation.py:210-214`; feature default-off per AGENTS.md source map).
- Track energy (E1, the library rank in the list header) has **no consumer at all** in the LED
  path: no continuous energy value, rank, or percentile is read anywhere in
  `led_dispatch_policy.py` (verified by sweep; the only "energy" symbol is the render-inert
  `max_energy` latch, `led_dispatch_policy.py:251, 2372-2375`).
- What the runtime DOES use for energy is a **different system entirely**: F2 family × tier
  buckets (1/2/3) cut at frozen percentiles of a "violence" scalar
  (`lighting_moments_v2.py:298-307` per extraction; consumed as a look-name pool filter at
  `led_dispatch_policy.py:2152-2189`), and the laser side's interim `"intense"/"monster"` tier
  gate (`drop_presentation.py:154-170` — the code's own comment says a future spectral refactor
  will replace it).

So there are two parallel energy systems: the one his ear will certify (E1/E3 lanes) and the one
the lights actually obey (F2 tiers). **The gate validates the disconnected one.** Failure
scenario: the list's "Drops, biggest to smallest" strip passes on every track; live, drop look
intensity is still routed by F2 tier cells his passed grades never touched, and a drop his list
called the track's biggest gets the same pool it gets today.

### 1.4 The list cannot test "cues CAST, never cycled" — and the runtime is a cycling machine. [confirmed]

The list deliberately never names a cue: *"Rows describe what lights do... never which look"*
(`acceptance_list_format_v3.md:194`), because cue authoring is downstream. Fair. But that means
the casting law — right cue, right track, right moment — is structurally outside the gate.
Meanwhile the runtime picks looks by **shuffled rotation bags**: lasers literally
`self._rng.shuffle` the role bank (`laser_executor.py:569-584`), LEDs draw from per-(role,
backend) shuffle bags (`led_look_director.py:556-586`). F2 routing narrows the pool by
family/tier, but a pool draw is still a cycle, not a cast. A perfect list plus today's selectors
is still a cycled show.

### 1.5 The energy fabric's middle layer and the breath-hold rule are out of the list by ruling. [confirmed]

Section-by-section energy arcs were explicitly excluded from this list round (ruling D6,
`acceptance_list_format_v3.md:199, 980`). The breath-hold rule — a track holding its breath
4 bars before the drop must get lights that hold their breath too — is a section-arc behavior
with no row type. The buildup cues that would violate it are self-timed against a hardcoded
32-beat internal cue clock (`govee_frame_renderer.py:22, 367-369`), with nothing listening for a
breath-hold. The gate can pass forever without ever asking his litmus-test question.

**Pass 1 verdict:** the list is sufficient to certify *hearing* (locations, lengths, ordering,
structure) and — by its own honest design — insufficient to certify *performing*. That is
acceptable only if everyone treats it that way.

---

## PASS 2 — OFFLINE VERSUS LIVE: what breaks between a located moment and that moment firing?

### 2.1 WORST: the live rig does not consume the list — it re-detects everything with a different, fail-open detector. [confirmed]

There is **no timestamp-indexed moment table anywhere in the runtime.** Every live decision is
edge-triggered by the playhead crossing ANLZ-derived beat markers
(`smart_phrasing.py:344-364` — `prev_abs_beat < drop_beat <= abs_beat`), recomputed every 5 ms
tick (`state_manager.py:571, 4883-4885`). The offline list locates moments from decoded audio
and a sealed grid; the live rig fires from Rekordbox phrase markers. Two detectors, one show.

The sharpest divergence is the safety direction. The v8 operating model requires the offline
laser builder to **fail closed** — no phrase proof, no laser row, `DROP_PROOF_MISSING` (v8 §4).
The runtime does the opposite twice over:

- `select_true_drops` **fails open**: if the runway filter would remove every drop, it returns
  all smart drops unchanged (`smart_phrasing.py:782-797`).
- The laser runway gate **fails open** when a track has no buildup markers at all
  (`laser_director.py:330-338` — "an empty list can never mean 'suppress'").

**Failure scenario:** the list passes on every track he names. Live, he plays a track with
sparse phrase data — the list would have refused to print laser rows for it; the rig happily
fires lasers on markers with no proven runway. That is the same family as "2:24 is during the
fucking buildup???" (failure dossier, `docs/plans/active/spectral_program_failure_dossier_2026_08_02.md:103-106`)
recurring **after** a fully passed gate — the gate never looked at the path that actually fires.

### 2.2 The list is per-track; the show is a two-deck blend the list never sees. [confirmed]

Only the active deck's phrasing is ever evaluated (`state_manager.py:4548-4549`). During his
real mixes — channel faders + EQ, never the crossfader — both decks sit at fader-top while he
works the lows, and the resolver's rule for that exact window is **hold the outgoing deck**
until bass dominance exceeds 0.01 or the RB master byte breaks a neutral-EQ tie
(`active_deck_resolver.py:137-174`). Meanwhile the incoming deck's drop plan is only built once
it becomes active (`state_manager.py:2840-2841`, retried at deck entry `:2308`), and the deck
switch resets lifecycle, LED role keys, and smart-rearm state (`state_manager.py:2261-2308`).

**Failure scenario:** an approved drop at 1:48.0 on the incoming track lands while lighting
still belongs to the outgoing deck — nothing fires, or the resolver flips seconds later and the
track enters mid-drop with a freshly reset plan. Every judgment on the list was made in cold
solo listening; a real set puts many of the most important moments inside exactly this contested
window. The gate contains no transition case at all.

### 2.3 The playhead is an instrument he plays; the list assumes linear playback. [confirmed]

- A **forward** needle jump over a drop marker fires a full drop crossing at whatever beat the
  jump lands on — the crossing test is interval-inclusive and there is no forward-discontinuity
  guard (`smart_phrasing.py:346-350`).
- A **backward** jump ≥ 0.1 beat resets smart phrasing and clears the fired-drop set, so a
  looped drop re-fires every pass (`smart_phrasing.py:250-252` per extraction; reset behavior
  clearing `_fired_drop_beats`); loops of ≤ 1 beat are silently swallowed by the LED beat clamp
  (`led_dispatch_policy.py:2476-2500`, threshold `config.py:86` — flagged ASSUMED in config
  itself for tight loops).
- Rekordbox loop state is not read at all — no loop offsets exist in `rb_offsets.py`
  (per extraction, `rb_offsets.py:209-227`); a loop is just a repeating backward jump.

The offline evidence ("starts 1:48.0, lasts 7 beats") is true of the file. Live, position is a
thing he manipulates, and every manipulation re-runs detectors the list never certified.

### 2.4 The list is judged to the tenth of a second; nobody has measured whether any output path can hit that. [confirmed / unknown]

The list renders `m:ss.t` rows and he judges lengths to the beat at the tenth. The live chain:
60 Hz memory polls interpolated at an assumed 1.0× rate on the memory path
(`state_manager.py:4652-4654`), 30 Hz state reader, drop actuation quantized to integer beat
boundaries on the smart-rearm path (`state_manager.py:4956, 4987` per extraction), and — the
big one — the cloud LED transport's own docstring says a cloud scene lands **"typically 1-5 s
into the drop"** (`led_dispatch_coordinator.py:190-196`). A 1-2 beat impact flash cannot ride
that path at all; only the realtime LAN path and MIDI lasers are candidates, and
**[unknown]** whether any end-to-end latency number has been measured since the program's own
honest-confidence note (recorded 2026-07-22, operator-accepted) that none existed. Sub-beat
accent timing through real hardware is the runner-up uncertainty in his own vision memory, and
the gate does nothing to retire it.

### 2.5 Tempo movement quietly detaches beat-locked animation. [confirmed]

A continuous beat-synced look re-anchors to a moved BPM only after **3 seconds of sustained
divergence** (`beat_sync_engine.py:32-38, 241-284`) — deliberate jitter immunity, but it means
every pitch move he makes mid-phrase leaves the "beat-locked" animation free-running on the old
tempo for at least 3 s. The list can say nothing about this; it has no tempo axis.

---

## PASS 3 — THE GATE'S PREDICTIVE VALUE: the list passes perfectly; what still goes wrong?

Assume every track he names passes cold. Each of the following is then still true:

1. **The lights cannot play the passed list.** Lengths → config constants (1.1). Accents → no
   mechanism (1.2). Energy → no consumer (1.3). Look choice → rotation, not casting (1.4).
   Laser location → re-detected by a different, fail-open detector (2.1). The pass certifies the
   score; the orchestra that would play it has not been built. [confirmed]
2. **Unlisted tracks get today's behavior.** The gate passes on tracks he names; live he plays a
   745-track library. Every fail-open path (2.1) means tracks the offline side would refuse
   still light up — with behavior the gate never examined. [confirmed]
3. **The show between the rows is unjudged.** The list caps at 6 rows per track, 3 drops + 1
   hold-off + 2 slots for laser/accent (`acceptance_list_format_v3.md:729-733`). Most of the
   wall-clock of any set is base looks chosen by rotation — the layer his "orchestrated, every
   cue musically backed" standard applies to most broadly — and the list's own law says an
   unmentioned moment is unreviewed, never approved. The gate samples moments; the vision is
   continuous. [confirmed]
4. **The transition show is unjudged** (2.2) — and with palettes turning per-track identity into
   per-mix color changes, mixes are precisely where a bad cast is most visible. [confirmed]
5. **The breath-hold and section-arc behaviors are unjudged by ruling** (1.5). [confirmed]

What the gate would need before it *predicts* the instrument rather than the hearing:

- a **measured end-to-end timing budget** per output path (MIDI laser, LAN LED, cloud LED),
  with a rule that a row class is only deliverable on paths that can hit its start and length —
  this retires the sub-beat uncertainty his own vision memory flags;
- a **named consumer contract per list column**: which runtime input each column becomes
  (length → what, grade → what, shape → what). A column with no consumer is a receipt entry,
  and today that is all four;
- a **transition case**: what the approved moment does when it lands in a contested two-deck
  window;
- and the second, downstream acceptance that already exists in his standing method — **normal
  mixing with timestamp vetoes, silence is a pass** — explicitly named as the gate for the
  *performance*, so nobody ever claims the list pass covered it. [assumed — this is my
  recommendation, not anything ruled]

To be fair to the gate: it is genuinely excellent at what it actually tests. The failure dossier
shows every catastrophic miss so far was a *hearing* miss (wrong moments, missing lengths,
buildup lasers), and the list format closes those with real teeth (R2, R13, the thirteen
refusals). The gate is not theater. It is just a gate on the first half.

---

## PASS 4 — WHAT SHOULD CHANGE

**Straight recommendation: keep his ordering. Do not widen the acceptance gate. Add the missing
downstream half as its own named thing.**

1. **The ordering is right.** [confirmed as my judgment against the evidence] Hear first, wire
   second is the correct de-risking: no lighting change ships to earn acceptance, no gig is the
   experiment, and the hearing problem is demonstrably the one that has been failing. Widening
   the gate with runtime concerns would slow the one artifact his ear can actually judge, and
   his ear cannot veto latency budgets anyway. Nothing about the gate itself should change.

2. **But "greenlit for LIVE WIRING" must be understood as authorizing a wiring PROGRAM, not a
   wiring task.** The operating model honestly disclaims all runtime authority (v8 line 17-19)
   — and no document anywhere owns what happens after the pass. The gap is not a cable; it is:
   a beat-indexed per-track moment schedule the runtime consumes (the natural join already
   exists: track-time → absolute beat via the beatgrid, `beat_math.py:19-48`; the natural
   attach point is the same load-gen-guarded path as hot-cue laser tags,
   `state_manager.py:2717-2721`; the natural consumer is `plan_track`,
   `drop_presentation.py:251`); an accent overlay capability class (new, per his own memory);
   per-moment length execution replacing config constants; a casting selector replacing
   rotation bags; consumers for both energy columns; deck-contention and discontinuity rules;
   and one measured latency number per path. That is a second program, and pretending otherwise
   is how the greenlight becomes a disappointment on the first live night.

3. **Two reconciliations are cheap now and expensive later,** and belong in whatever spec owns
   the downstream half, written *before* the gate passes so wiring doesn't start from a
   contradiction: (a) the fail-open/fail-closed disagreement — the runtime's
   `select_true_drops` and laser runway gate fail open (`smart_phrasing.py:782-797`,
   `laser_director.py:330-338`) while the offline side fails closed, which means the wired show
   can violate LASERS-ONLY-ON-DROPS on exactly the tracks the list refused to speak about;
   (b) the two parallel energy systems — F2 tiers steering the lights vs the E1/E3 lanes his
   ear certifies (1.3). Either the certified lanes replace the tiers at wiring time, or the gate
   certified numbers the show ignores.

4. **The second acceptance already exists and costs nothing:** his standing validation method —
   normal mixing, timestamp vetoes, silence approves the night. State it as the downstream gate
   of the wiring program. No labeling, no new sessions, no new burden on him.

**The honest bottom line on the attack question:** the program is not optimizing a receipt
*instead of* an instrument — it is optimizing the correct first half of the instrument, with the
correct judge, in the correct order. The danger is narrower and very real: the receipt is
becoming so rigorous, and the eight rounds so focused on it, that the size of the unbuilt second
half has disappeared from every active document. Zero of the four passed columns can currently
be performed. Say that out loud in the plan of record, and the ordering is not just defensible
— it is right.

---

## To Brandon, directly

Your gate is right and your ordering is right — I went looking for a reason to say otherwise
and didn't find one. Hear first, wire second is exactly how to keep a live night from being the
experiment. But I checked every consumer your lights actually run through, and here is the one
thing nobody has said plainly: when the list passes, the rig as it exists today cannot play it.
The lasers hold for config constants, not for the 14 beats your ear approved. The accent layer
the list describes has no mechanism behind it yet — nothing can fire a one-shot on top of a
running look. Both energy numbers you'll be judging are read by nothing; the lights obey a
different, older energy system. And the live rig re-detects drops with a detector that fails
open where your list fails closed — so a track your list refuses to print lasers for can still
fire lasers live, in a buildup-shaped way you have already been angry about once. None of that
means the list work is wasted — it is the score, and the score has to pass your ear before
anything else matters. It means "ready for live wiring" is the start of the second build, not
the end of the first, and the greenlight should buy a wiring spec with your normal-mixing veto
as its own finish line. Nothing needs to change about how you judge. Something needs to change
about what everyone tells you the pass means.
