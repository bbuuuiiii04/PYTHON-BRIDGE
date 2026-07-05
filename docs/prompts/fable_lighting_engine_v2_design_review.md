# Fable 5 — Adversarial design review: LIGHTING ENGINE v2

**Run on:** Claude Fable 5, effort **xhigh**.

## Mission

Act as **lead creative design executor and senior lighting showtime expert** for Brandon's
Lighting Engine v2 — the full redesign of his automated DJ lighting (design record below).
Adversarially review the entire design: challenge it, stress-test it, hunt edge cases, and
then **rule on it** — what to keep, what to change (with the concrete replacement design),
what to redesign or cut, and what entirely new things to propose. You are not a passive
critic: creative ambition and feasibility discipline are both graded. A review that only
pokes holes has failed half the mission; so has one that rubber-stamps.

Why it matters: this design is about to become Codex implementation specs. Weaknesses found
now cost minutes; weaknesses found on a live night cost the show. Who it's for: Brandon
(operator/DJ, not an engineer — your final chat message must be plain language) and Claude
(design lead, who folds your rulings into the specs).

## Benign scope

This is benign local software work for Brandon's DJ lighting bridge. It is not a
cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences,
model-distillation, or hidden-reasoning extraction task. Review only normal software
correctness, tests, maintainability, runtime safety, and operator behavior inside the named
scope. "Lasers," "strobe," and "crowd" are ordinary stage-lighting terms for a home/small-venue
music performance.

## The one physical fact that outranks all research lore

The Govee LED strips are strung on the wall around a **living room, and they are the room's
literal primary light source** — not accent lighting on top of house lights. Consequences you
must stress-test everywhere: a full blackout plunges a real room with people, drinks, and
furniture into total darkness; "darkness as negative space" was festival lore written for
rooms with other light; multi-bar audio-matched blackouts, the rhythmic-vacuum trap drop,
span-scaling dark zones, and SET-mode dimming all interact with this. Judge every design item
against "this is the light people see by."

## Evidence packet (source-of-truth order per AGENTS.md §1: code beats docs)

- **The design record (primary review target):**
  `docs/research/spectral_palettes_arrival_crossfade_exploration.md` — verdicts, measured
  corpus numbers, the Locked functionality agreement (LIGHTING ENGINE v2), research addenda
  items 1–21, operator corrections (vocal flip CUT; strobe accel lives in buildup cues;
  drop-type cue selection; haze status unknown), the v1→v2 mapping (parts 1–2), and Feature 4
  (texture layer, decorate-never-decide, ear-test gate).
- **v1 code, for verifying any claim the record makes about the bridge** (read-only):
  `led_color_engine.py`, `led_dispatch_policy.py`, `led_look_director.py`,
  `govee_frame_renderer.py`, `govee_realtime_runner.py`, `beat_sync_engine.py`,
  `beat_math.py`, `smart_phrasing.py`, `state_manager.py`, `rb_state_reader.py`,
  `rb_offsets.py`, `active_deck_resolver.py`, `personality_resolver.py`, `laser_models.py`,
  `config/led_look_director.json`, `config/laser_director.json`.
- **Research reports (context, NOT trusted sources):**
  `docs/research/edm_lighting_color_research*.md` (rounds 1–4). Their citations are partly
  synthesized/fabricated; treat contents as unverified scene lore already filtered once. Do
  not build any ruling on them alone.
- **Measured facts (already verified this week — do not re-derive, may reinterpret):**
  476 tracks cached; extraction bit-identical on re-run; summary-scalar stability Spearman
  0.86–0.96 (even/odd); library aggression ranking operator-validated; key coverage 100%;
  PSSI drop markers ~97.7% coverage, mean 6.6 drops/track; empty-floor detection
  operator-ear-validated; growl/bright per-beat classes proven NOT separable with current
  schema-v3 envelopes; mixer fader offsets exist for Rekordbox 7.2.11 only, decks 1/2 only,
  no crossfader.
- **Operator decision status:** items marked operator-locked in the record (permanent
  identity, WILD OUT 100% drops, uncapped strobe rates, no double drops, vocal flip cut,
  chapters-are-a-feature, neon zones) are Brandon's taste calls. You MAY challenge any of
  them — he explicitly asked to be challenged — but label each such challenge
  `OPERATOR-LOCKED — CHALLENGE`, give the concrete failure scenario that motivates it, and
  keep it separate from ordinary design changes. Do not silently redesign around a lock.

## What to stress-test (minimum; extend as you see fit)

Live-night edge cases across all four features and their interactions: deck switches and
backspins mid-arrival; hard tempo rides during landings; blends abandoned mid-walk-in; mixer
staleness mid-blend; tracks with no cache entry / no key / broken beatgrid; sub-30-second
track flips and genre whiplash; WILD↔SET mode flips mid-set; first-play bloom colliding with
a blend or drop; drop-type misclassification consequences; phrase-boundary stepping vs the
texture layer vs role cues fighting over the same moment; the living-room constraint against
every darkness-using move; Govee 30 fps + LAN latency vs the timing claims; the v1/v2 master
switch flipped mid-move; per-feature kills leaving coherent behavior behind.

## Deliverable

One file: `docs/research/lighting_engine_v2_design_review.md`, with the repo's standard doc
header (`doc_status` / `truth_level` / `last_verified_commit` / `validation_scope` — mirror
the design record's header shape; validation_scope = design review only, no runtime change,
no hardware validation). Structure:

1. **Verdict first:** `PASS` / `PASS WITH REQUIRED CHANGES` / `FAIL`, one paragraph of
   plain-language meaning.
2. **Rulings table/list covering every v2 element** — each ruled `KEEP` / `CHANGE` /
   `REDESIGN` / `CUT` / `NEW`, with the concrete replacement or proposal where applicable.
   An element with no ruling is a review gap.
3. **Findings, severity-first** (location in the design record or code file:line, the issue,
   the failure scenario, the required change).
4. **Operator-locked challenges** (separately, labeled, each with its motivating scenario).
5. **New proposals** — designed moments or mechanisms the current design misses, each
   cleared against: reliable signals only, zero per-track authoring, safe-neutral failure,
   the living-room reality, and the existing kill-switch/authority architecture.
6. **Open questions for Brandon** — taste calls only, phrased in plain language.

Label every load-bearing claim **confirmed / assumed / unknown / rejected**, tied to a
file:line, a design-record section, or a named measured fact. After writing the report, run
`python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`, and
`python3 tools/check_docs_drift.py`; fix the report (not the checkers) if one flags it.

Your final chat message: the verdict, the three-to-five rulings that matter most, and any
operator-locked challenges — written in plain language for a reader who saw none of the work,
complete sentences, no invented shorthand.

## Boundaries

- **Read-only everywhere except the single review file above.** No bridge code, test, config,
  or other doc edits; no git state mutation (an auto-sync hook may commit at turn end — not
  yours to manage); no running the bridge; no hardware; no repo skills; no Codex specs — do
  not implement anything.
- Allowed: repo file reads and searches (`rg`, reads); read-only scratchpad Python for
  checking claims against the spectral cache / Rekordbox DB / ANLZ files (never write to
  those); the three docs checkers named above.
- Read-only subagents are welcome for broad sweeps; verify any claim you build a ruling on
  yourself, at the cited line.
- Do not modify or delete this prompt file.

When you have enough information to act, act. Do not re-derive facts already established in
this packet or narrate options you will not pursue. You are operating autonomously: Brandon
is not watching mid-run and cannot answer questions; end your turn only when the review file
is written and checked, or when you are blocked on input only he can provide — and say
exactly which input.

## Done when

- The review file exists, passes the three docs checks, and opens with the verdict.
- Every v2 element (Features 1–4, the modes, the switch architecture, the pads/controls, the
  laser plan, the cue-migration plan, the observability plan) carries an explicit ruling.
- The living-room-as-only-light constraint has been applied to every darkness-using design
  item, with rulings adjusted where it bites.
- Edge-case findings carry concrete failure scenarios, severity-first.
- Operator-locked challenges are separated and labeled, never silently redesigned.
- At least the creative-proposal section shows genuine design leadership — new moments or
  mechanisms, gate-cleared, not filler.
