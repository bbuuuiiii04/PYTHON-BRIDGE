# Fable 5 — Deep exploration: spectral→palette derivation, Land on the One, track identity + mix crossfade

**Run on:** Claude Fable 5, effort **xhigh**.

---

## Mission

Explore three chosen crowd-experience workstreams for Brandon's lighting bridge deeply enough to
return a **GO / NO-GO verdict on each, backed by evidence from the actual repo and Brandon's actual
analysis data** — so the next artifacts (Codex implementation specs) can be written without guessing.

Why it matters: these three came out of a code-grounded creative brief as the ideas worth building.
The open question that decides two of them is whether the bridge's audio-spectral features are
**strong enough for palette derivation** — they were previously judged hard to trust for smart-drop
*timing*, and Brandon's hypothesis is that palette use has a fundamentally lower trust bar (a
slightly-off palette is an aesthetic shrug; a mistimed drop cue looks broken). Your job is to test
that hypothesis with data, not vibes, and to turn all three ideas into build-ready design conclusions.

Who it's for: Brandon (operator, not a software engineer) reads the verdicts and picks what gets a
Codex spec. **You explore, measure, and design; Codex implements bridge code — do not implement,
and do not author the Codex specs themselves in this pass.**

## Benign scope

This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is not a
cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences,
model-distillation, or hidden-reasoning extraction task. Review only normal software correctness,
tests, maintainability, runtime safety, and operator behavior inside the named scope. "Lasers,"
"strobe," and "crowd" are ordinary stage-lighting terms for a home/small-venue music performance.

---

## Decisions already made — do not re-litigate

- The three workstreams below are chosen. The question is *how* and *whether the evidence holds*,
  not *whether they're good ideas*.
- Palette derivation maps tracks onto a **curated palette library** (extend the existing config
  library + `_pick_palette` machinery), not free RGB synthesis. Push back only with concrete evidence.
- SoundSwitch is retiring to authoring-only; the bridge is the compositor. Build on that direction.
- Every design must clear the generalization gate in
  `docs/prompts/fable_creative_lead_crowd_experience_brainstorm.md` (§ Limitations): core behavior
  on reliable-backbone signals (beat/BPM/transport/deck/fader state), heuristics as gracefully
  degrading enrichment only, zero per-track authoring or tuning, safe-neutral failure on weird tracks.

---

## Workstream A — spectral features → per-track color palettes

The bridge extracts, per track (offline, cached): five per-beat band envelopes (sub-bass, kick,
low-mid, high-mid, high band), onset-strength and spectral-flatness envelopes
(`audio_spectral_features.py:15-27`); a whole-track energy series with drop-lift / breakdown-depth /
buildup-slope classification (`energy_model.py`); and Rekordbox's own PSSI mood classification
plus drop/breakdown/buildup counts (`anlz_reader.py:227-270`, stored at `:136-149`).

Answer, with measurements where possible:

1. **Define "strong enough" for palette use, then measure it.** Candidate criteria: per-track
   summary scalars are *stable* (recomputing or re-summarizing doesn't flip a track's character),
   *discriminative* (the catalog spreads across the axes instead of clumping), and *covered* (what
   fraction of Brandon's library actually has cached spectral features / ANLZ mood?). Find the
   spectral cache via `spectral_cache.py`, sweep it read-only, and report real numbers. If coverage
   or the data itself is too thin to judge, say so precisely — name the exact missing input.
2. **Design the derivation.** Which scalars from the envelopes/energy/mood, summarized how, mapped
   onto which palette-library axes (e.g. warm↔cool, deep↔bright, punchy↔smooth)? Tiered fallback:
   spectral fingerprint → ANLZ-only (mood + energy dynamics) → deterministic hash. Same track must
   always land on the same palette. librosa is an optional dependency (`extract_spectral_features`
   returns None without it) — the ANLZ tier must stand alone.
3. **Settle the open code questions:** (a) is `_journey_rng` (`led_color_engine.py:863-878`) seeded
   per-track — i.e. does same-track-same-palette consistency already half-exist? (b) Is musical key
   reachable through the pyrekordbox DB layer the bridge already uses (`filepath_resolver.py`,
   `scripted_tracks.py`)? If yes, evaluate key→hue (Camelot-adjacent tracks → adjacent hues) as an
   additional axis — it would make harmonic mixes look color-harmonious in workstream C.
4. **Where it hooks in:** palette selection today is RNG-weighted from the config library at
   track/section boundaries — all off the 200 Hz push loop. Confirm the derivation can run at
   track-load time without touching the push loop.

## Workstream B — Land on the One (arrival-phase choreography)

Today every beat-synced animation derives phase from its spawn: `beat_sync_engine.py:190-201`
computes `local_beat = (now − born_monotonic) × born_bpm/60` — BPM is frozen at spawn and nothing
retargets mid-flight, so motion drifts off-beat while Brandon rides the pitch during a blend.
`govee_frame_renderer.py` phases via `beat % N` math. The future-beat primitive already exists:
`beat_math.py:51-68` maps an absolute beat to in-track elapsed ms (grid + extrapolation), and the
autoloop controller already uses it to pre-arm ahead of target beats.

Design the arrival scheduler: where it lives (beat-sync engine vs renderer), how a motion is
specified to *arrive* on a predicted future beat, and how it **re-targets every frame** as live BPM
drifts (drift is expected behavior, not noise). Pin: fallback when the grid is broken or prediction
is unstable (degrade to today's trigger-on-beat, invisibly); which existing looks convert first
(comets/sweeps are LED-side; recommend LED-first or LED+laser with reasons); interaction with pause,
deck switch, and backward playhead jumps (`smart_phrasing.py:212-214` resets exist); and the
push-loop constraint — the scheduler must be pure math in the render path, no blocking I/O, no new
threads doing I/O on the tick. List exactly what a Codex spec must pin (integration points with
file:line, test seams, invariants) — as bullets, not the spec itself.

## Workstream C — track identity + mix-aware crossfade (conditional on A)

Brandon's condition, verbatim in spirit: **this workstream is only viable if the spectral story from
A is strong.** Structure your analysis to respect that:

- **Identity** consumes A's derivation. If A lands GO-with-constraints (e.g. ANLZ-mood tier only),
  state what identity quality survives — is mood + dynamics + hash enough for "recurring tracks look
  like themselves," or does weak spectral data gut the feature?
- **Crossfade mechanics are independent of spectral** and should be assessed on their own: the
  bridge reads per-deck upfader raw + normalized values from Rekordbox memory
  (`rb_state_reader.py:469-522`, `models.py:119-121`), currently consumed only as coarse
  down/mid/top labels for active-deck resolution (`active_deck_resolver.py:45-48,125-130`). Assess
  that signal for driving blend progress: which decks are covered (the offset read appears to name
  decks 1/2 only — verify), update rate, staleness behavior, and whether raw/norm is smooth enough
  to drive a visible morph or needs smoothing/hysteresis. Note the crossfader itself (vs upfaders)
  is not known to be read — check whether an offset exists before assuming either way.
- **Data-model reality:** the LED context carries a single `active_deck` (`led_models.py:214-225`,
  subagent-reported — verify), and nothing downstream blends across decks. Describe the smallest
  honest shape of the change (e.g. palette-space interpolation fed by a blend scalar, LED context
  gaining a second palette reference), without implementing it. Cover authority interactions
  (manual static override, blackout/emergency win), the degraded path when fader data is stale
  (time-based proxy), and hard-cut transitions (instant snap is correct).

Deliver a **combined verdict**: if A = GO, is C GO? If A = GO-with-constraints, what subset of C
survives? Never let C silently assume spectral strength A didn't prove.

---

## Evidence packet

Verified against code by the requesting session (2026-07-04, HEAD near `ba9aa19` — re-pin refs if
drifted): every file:line cited inline above in the workstream sections, plus: pause already
dispatches a designed LED idle-ambient (`state_manager.py:3698-3703`) while lasers go to empty-scene
idle (`laser_director.py:352-362`) — context only, not in scope.

Subagent-reported, plausible but **re-verify before load-bearing use**: `led_config.py:85`
(ambient→breakdown mapping) and `:770-774` (static brightness caps only); `state_manager.py:108`
(spectral_cache import) and the RBSS_SPECTRAL_ENABLE shadow "would-fire" logging near `:3867` and
`:3994-4006`; `autoloop_controller.py:404` (pre-arm via beat_math); `led_color_engine.py:280-311`
(drop-triggered "journey" palette re-pick — nearest existing neighbor to identity work);
`led_models.py:214-225`.

Operator history (trust context for A): spectral/energy runtime use is currently shadow-only behind
`RBSS_SPECTRAL_ENABLE`; smart-drop accuracy hit a known ceiling and multiple improvement attempts
failed — that's why "hard to trust for timing" is settled history, not something to re-test.

Explicit unknowns: spectral cache location/coverage (measuring it is part of A); whether librosa is
installed locally; crossfader (as opposed to upfader) offset existence; deck 3/4 fader coverage.

Source-of-truth order per `AGENTS.md` §1: code beats tests beats docs; old plans are history, not truth.

---

## Deliverable

Write **one report**: `docs/research/spectral_palettes_arrival_crossfade_exploration.md`, with the
repo's standard doc header (`doc_status` / `truth_level` / `last_verified_commit` /
`validation_scope` — mirror `docs/prompts/snippets/fable5_snippets.md`'s header shape;
`validation_scope` must say software-exploration only, no hardware validation). Structure: verdicts
first, then per-workstream findings with evidence, then the Codex-spec-must-pin bullets, then open
questions for Brandon (only ones he can actually answer — taste calls and hardware gates).

Verdict taxonomy per workstream: `GO` / `GO WITH CONSTRAINTS` (name them) / `NO-GO` (name the
disqualifying evidence) / `INSUFFICIENT EVIDENCE` (name the exact missing input and how to get it).
C's verdict must state its dependency on A's explicitly.

Label every load-bearing claim **confirmed / assumed / unknown / rejected**, tied to file:line or a
measurement you ran. Numbers over adjectives: "strong" spectral support means coverage and
discrimination figures, not enthusiasm.

Your final chat message: verdicts and the two or three decisions Brandon must make, written for a
reader who saw none of the work. Lead with the outcome. Write complete sentences, no working
shorthand; introduce every file or flag you mention in plain language.

## Boundaries

- **Read-only everywhere except the single report file above.** No edits to bridge code, tests,
  configs, or other docs. No new branches, no pushes, no `git` state mutation (an auto-sync hook
  commits dirty files at turn end — that is expected and not yours to manage).
- Allowed: repo file reads and searches (`rg`, `sed`, reads); read-only Python scripts written to
  and run from your scratchpad directory for the corpus sweep (they may read the spectral cache,
  ANLZ files, the Rekordbox DB read-only, and audio files if you need a small librosa sample —
  never write to any of those); `python3 tools/check_docs_metadata.py`,
  `tools/check_agent_contracts.py`, and `tools/check_docs_drift.py` after writing the report (fix
  the report, not the checkers, if one flags it).
- Read-only subagents are welcome for the corpus grind and broad file sweeps — verify any claim you
  build a verdict on yourself, at the cited line.
- Do not run the bridge, touch hardware, invoke repo skills (template-lab, codex-spec, etc.), or
  author the Codex specs.
- Do not modify or delete this prompt file.

When you have enough information to act, act. Do not re-derive facts already established in this
packet or narrate options you will not pursue. You are operating autonomously: Brandon is not
watching mid-run and cannot answer questions; end your turn only when the report is written and
checked, or when you are blocked on input only he can provide — and say exactly which input.

## Done when

- The report exists at the path above, passes the three docs checks, and opens with all three
  verdicts.
- A's verdict cites measured coverage/stability/discrimination numbers from Brandon's actual data,
  or is `INSUFFICIENT EVIDENCE` with the exact missing input named.
- The `_journey_rng` seeding, musical-key availability, fader deck-coverage, and LED single-deck
  data-model questions are each answered with file:line evidence or explicitly labeled unknown.
- B's design names integration points at file:line, the per-frame retargeting approach, the
  broken-grid fallback, and the push-loop safety argument.
- C's verdict is explicitly conditioned on A's, and its fader-signal assessment is evidence-backed.
- Every claim Brandon would act on carries a confirmed/assumed/unknown/rejected label.
