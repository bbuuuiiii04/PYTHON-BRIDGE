# Fable 5 prompt — locate Lighting Engine v2 on its roadmap, then expand F2's spectral-driven drop choreography

**Target model:** Claude Fable 5. **Effort:** xhigh. (Long-horizon design synthesis over a locked authority doc + a real cached audio-analysis feature; safety-sensitive live lighting; feeds a Codex spec.)

## Benign scope

This is benign local software work for Brandon's DJ lighting bridge. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning-extraction task. "Laser," "strobe," "blackout," and "drop" are stage-lighting looks driven over MIDI/DMX for a home EDM party. Review only normal software correctness, tests, maintainability, runtime safety, and operator-visible lighting behavior inside the named scope.

## Mission

Figure out exactly where Lighting Engine v2 stands on its own roadmap today, then design **F2's within-drop choreography** — how the LEDs and lasers should ride the *musical element* inside a drop section, driven by the spectral audio analysis the bridge already computes. The output feeds a Codex implementation spec; **do not implement anything.** Fable reasons, designs, and audits; Codex writes the code.

Why it matters: this bridge runs the lights live in a room full of people (mostly drunk EDM fans). Feature 1 (each track wears its own color) is live. The next feature, F2, is the one that makes the biggest moment of the night — the drop — actually *land*: the light stops reacting on a fixed beat count and starts following what the music is doing. Getting F2's design right, grounded in what the analysis can really see, is the difference between "every drop looks the same" and "every drop looks like itself." A confident-but-wrong design that reaches Codex makes the next party worse, so reach fewer conclusions that are each proven over the code and the locked design.

## What Brandon wants the design to serve (the real target, in his words)

The lighting inside a drop should follow the **musical element and its length**, for LEDs *and* lasers — not a fixed beat count. Concrete cases he named, to design against:

- A track with a long buildup drops, and for **8 counts** a high euphoric synth chord layers over the drop — the lasers should ride exactly those 8 counts.
- Elements vary: some last **4 counts, some 16, some 32**.
- A dubstep chorus **hits hard for the whole phrase** — LEDs and lasers go hard the whole phrase.
- An ISOxo-grade trap/dubstep drop wants **16 counts of full LED strobe, 16 counts of drop progression, then 16 counts of full strobe again** — the light follows that internal block structure.

These are the design targets, not a per-track wishlist: the mechanism must **generalize across the EDM catalog from measured signal**, never a per-track hand-tune and never a genre string (both get cut in this repo).

## Deliverable and format

Written to be read cold by Brandon, then handed to a Codex spec author:

1. **Roadmap position — outcome first.** One short section stating, with evidence, exactly what is built vs designed-only vs unbuilt across F1/F2/F3/F4 and the spectral analysis, and what "we are here" means for starting F2.
2. **F2 within-drop choreography design.** The core deliverable: how a drop's own measured character selects and shapes what the fixtures do over the drop's timeline. Cover at least — the drop-type family selection (§4.2), the intensity/aggression profile within a family (strobe density, burst structure, rate rung, white share, micro-darkness), the dynamic pre-drop blackout sizing (§4.1), and how the *within-drop time structure* (the 8-count stab, the 16/16/16 alternation, the full-phrase wall) is derived from the cached per-beat/quarter-beat features rather than a fixed count. Say plainly which of Brandon's four cases the design lands, which it approximates, and which it cannot reliably do from the current analysis (name the fallback — e.g. an operator hot-cue override — for those).
3. **Signal-grading + ground-truth validation pass.** For every measured signal the design leans on, grade it (backbone / corpus-calibrated-use / weak-or-cut) using the operator rule already recorded in the design doc's F4 decisions, and cut or downgrade any choreography that rests on a weak signal. Reliable signals decorate; unreliable ones must not drive a live drop. **Then design the falsifiable proof that each detector fires on the musical moment Brandon actually means — not a correlated wrong one.** Words like "euphoric stab" or "growl wall" are not a definition the analysis can be trusted against; the only trustworthy check is agreement with operator-labeled examples on **held-out tracks** (tracks the thresholds were not tuned on). Specify: which concrete moments in which of Brandon's real walkthrough tracks get labeled, how the analysis's firing is compared against those labels, and what agreement rate clears a detector for live use vs sends it to the cut/override pile. A detector that only works on the tracks it was tuned on is per-track and must be cut (operator rule). The design doc *claims* held-out separability and specific blackout-gap numbers on named tracks — treat that as intent to re-verify against the shipped cache, not as settled proof.
4. **Lasers inside the drop.** Keep the existing "which drops get lasers at all" casting (v1 drop-presentation authority — rare, ranked, operator-traceable) untouched, and design only the *within-drop* laser shaping (when the beams go hard vs recede) off the same measured element structure, so the two layers compose.
5. **RC2 reconciliation.** A short, decisive section: how F2's "landing as infrastructure" (arrival math robust to backward beat motion) relates to the **now-landed** RC2 fix (**AWR-141 — implemented + software-tested**, a `WRAP_HOLD_BEATS = 0.5` threshold in `TriggerClock.advance`, `beat_sync_engine.py`, that stops continuous effects flickering on sub-seek jitter). RC2 is **already fixed on the current continuous clock** — this is not an open bug. State whether F2 subsumes it, still needs it as a foundation, or composes with it — and make the one real design call: when F2's arrival model exists, should the continuous atmospheric effects (breathing, twinkle, breakdown simmer) migrate onto F2's backward-robust clock, or stay on the (already RC2-fixed) continuous clock. Give a recommendation, not a survey.
6. **Readiness verdict + Codex-spec seams.** End with `READY` / `READY WITH GAPS` / `NOT READY` for handing F2 to a Codex implementation spec, listing any blocking gaps and the exact open operator decisions that remain (taste calls only — not routine mechanics). Do not write the Codex spec itself; hand off the seams (which functions, which config, which existing code carries forward) so the spec author can pick it up.

## Evidence packet

**Source-of-truth order (non-negotiable):** executable code `*.py` → `tests/` → config examples → `runtime_status.py` → file tree → docs → old prompts/plans. If a doc conflicts with code, **code wins.** If you cannot verify a claim, mark it unknown — never guess.

**The locked design authority (do not re-litigate — these are settled operator decisions; expand and spec them, don't reopen them):**
- `docs/architecture/lighting_engine_v2_authority.md` — the intended-experience contract. §4 "Moments that land (Feature 2)", §4.1 "The pre-drop blackout (the rules, settled)", §4.2 "Drop-type selection", §5 "Which fixtures fire (v1 authority, carried forward)", §6 "Lasers in the haze era", §8 "Texture (Feature 4)".
- `docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md` — the complete design. §3 drop family/tier/aggression, §4 landing + blackout + dip rules, §5 white-share/rate-rung/texture-signal detail, and **§15.6 "Gap-closing decisions — F1–F4 operator session (2026-07-05)"** which holds the locked F2/F3/F4 calls (including: repeat/dense drop markers become **family-driven** — WALL/COMET re-fire full-energy across the whole chorus, HOUSE keeps ~2 impactful then settles to post_drop, NEUTRAL gets a small hit — replacing the hardcoded `LED_MAX_DROP_IMPACTS = 2`; and the F4 signal-grading rule).

**The spectral analysis that already exists (verify shape/granularity against code before trusting this summary):**
- `audio_spectral_features.py` — `extract_spectral_features_v4` produces `SpectralFeaturesV4`: absolute-dB **per-beat and quarter-beat (`sub4`) multi-band envelopes**, HPSS harmonic/percussive measures, onset-strength/onset-density envelopes, and timbre descriptors. Band ranges include a growl band (60–500 Hz harmonic) and onset mid-high (500–11025 Hz).
- `spectral_profile.py`, `spectral_cache.py` — cache and compat layer; the analysis is computed once per track and cached (`docs/research/spectral_audio_analysis_redesign.md` is the design record; `docs/research/anlz_energy_project.md` for the ANLZ energy line).
- `state_manager.py` — where the analysis is consumed **today**: `extract_spectral_features_v4` + `_calculate_smart_drop_energy_shadow` feed **smart-drop detection** (which markers are real drops) and F1 identity color. The `max_energy` render path is a **stub** — `led_dispatch_policy.py` logs "max_energy consumed (render unchanged until F2)". So the fine-grained element structure is analyzed and cached but **not yet used to shape what the light does inside a drop** — that gap is exactly F2's job.

**The live drop machinery F2 builds on / around (verify ownership before asserting):**
- `led_dispatch_policy.py` — LED role resolution + drop lifecycle; `_led_drop_marker_anchor`, `_led_drop_impact_allowed`, `LED_MAX_DROP_IMPACTS`, the max_energy stub.
- `drop_presentation.py` — the WindowMachine (pre_dark / in_window phases) and the drop-presentation ladder (which fixtures fire per drop — the casting layer to keep intact).
- `smart_phrasing.py` — drop markers, phrase segments, the drop window; `laser_director.py` / `laser_executor.py` — laser policy vs MIDI execution; `led_look_director.py` — look/param selection (the F4 containment point at `_look_name_for_role`).
- `govee_frame_renderer.py`, `beat_sync_engine.py`, `govee_realtime_runner.py` — the realtime render path F2's landing/arrival math and any migrated continuous effects would touch (also the RC2 site).

**Known-stale / evidence-only:** any project memory, any doc without a current status header, and old prompts/plans. Verify against current code before relying on them. The RC2 flicker mechanism and the F2 design are both under active work this same session — re-verify file:line at your HEAD.

**Explicit unknowns to resolve, not guess:** the exact granularity and reliability of each v4 signal on Brandon's real tracks (the design doc records some as blind spots — chorus softness, growl-*intensity* ranking, slow wobble, sidechained kick-prominence, thick-wall sustained-synth); whether an 8-count harmonic stab is separable from surrounding drop energy at the cached resolution; whether the analysis is per-beat enough to key a 16/16/16 block alternation. Where a case needs a signal the analysis cannot reliably give, say so and route it to the operator hot-cue override rather than inventing a detector.

## Boundaries

- **Read-only.** Read code, tests, config, docs, and the design authority. You may run the test suite read-only (`python3 -m unittest discover tests`; some suites need optional deps, there is a known small red baseline — do not "fix" tests). Do **not** edit bridge code, change config, restart or touch the running bridge, or touch hardware.
- **No implementation.** The deliverable is the F2 design + readiness verdict + Codex-spec seams. Codex implements bridge code; do not write the Codex spec file itself — hand off the seams.
- **Do not re-litigate locked decisions.** The §15.6 operator calls and the v1 fixture-casting authority are settled. Expand and make them implementable; flag a genuine code/design conflict if you find one, but do not reopen a decided taste call.
- **Delegate the grind, keep the judgment.** Hand multi-file symbol tracing, signal-shape verification, and corpus/log sweeps to cheaper-tier subagents (the read-only `bridge-triage` agent returns conclusions + `file:line`, never transcripts; or the Claude session at `tmux a -t claude`). You are the only Fable-tier agent: never spawn another Fable-tier subagent, and announce nested spawns. Keep the live-safety and design judgment on yourself; verify a subagent's load-bearing claims before relying on them.

## Claim discipline and success criteria

Label every load-bearing claim **confirmed / assumed / unknown / rejected**, each tied to a `file:line`, a test, an authority-doc section, or a spectral-feature definition. "The design doc says so" confirms *intent*, not that the *signal exists at the needed resolution* — keep "the analysis is designed to capture X" separate from "the analysis reliably captures X on these tracks," and verify the latter against the feature code before leaning on it.

You are done when: the roadmap position is stated with evidence; F2's within-drop choreography is designed to a level a Codex spec author can execute, with each of Brandon's four cases explicitly landed / approximated / routed-to-override; every leaned-on signal is graded, weak ones are cut, and each surviving detector has a **falsifiable held-out validation plan** (labeled moments on real tracks + the agreement bar that clears it for live) rather than an asserted "it generalizes"; the laser within-drop shaping composes with the untouched casting layer; the RC2 relationship and the continuous-effect migration call are decided; and the readiness verdict names its blocking gaps and remaining operator taste-calls.

**Verdict line to end on:** `F2 READINESS: READY / READY WITH GAPS / NOT READY` + the RC2 relationship in one clause.
