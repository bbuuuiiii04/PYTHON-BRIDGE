# Fable 5 prompt — locate Lighting Engine v2 on its roadmap, then design F2's spectral-driven drop choreography

**Target model:** Claude Fable 5. **Effort:** xhigh. Set a large max-output budget — this is a long design synthesis. Feeds a Codex spec; **do not implement.**

## Benign scope

This is benign local software work for Brandon's DJ lighting bridge. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning-extraction task. "Laser," "strobe," "blackout," and "drop" are stage-lighting looks driven over MIDI/DMX for a home EDM party. Review only normal software correctness, tests, maintainability, runtime safety, and operator-visible lighting behavior inside the named scope.

## Mission

Find exactly where Lighting Engine v2 stands on its own roadmap today, then design **F2's within-drop choreography**: how the LEDs and lasers should ride the *musical element* inside a drop, driven by the spectral audio analysis the bridge already computes. Fable reasons and designs; Codex writes the code — **do not implement.**

Why it matters: this bridge runs the lights live for a room of (mostly drunk) EDM fans. F1 (each track wears its own color) is live; F2 is what makes the drop actually *land* — the light stops reacting on a fixed beat count and starts following the music. A confident-but-wrong design reaching Codex makes the next party worse, so prefer a few conclusions each proven against the code and the locked design over a full list of guesses.

## The design target (Brandon's own words)

The lighting inside a drop follows the **musical element and its length** — LEDs *and* lasers, not a fixed beat count. Design against these real cases:

- a long buildup drops and a euphoric synth chord layers over it for **8 counts** — lasers ride exactly those 8;
- elements vary — **4, 16, 32** counts;
- a dubstep chorus **hits hard for the whole phrase** — LEDs and lasers go hard the whole phrase;
- an ISOxo trap/dubstep drop wants **16 counts full LED strobe → 16 counts progression → 16 counts full strobe** — the light follows that internal block structure.

The mechanism must **generalize across the EDM catalog from measured signal** — never per-track, never a genre string (both get cut here).

## Deliverable (written to be read cold by Brandon, then handed to a Codex spec author)

1. **Roadmap position, outcome first** — with evidence, what is built vs designed-only vs unbuilt across F1–F4 and the spectral analysis, and what that means for starting F2.
2. **F2 within-drop choreography** (the core) — how a drop's own measured character selects its drop-type family (§4.2), shapes the aggression profile within that family (strobe density, burst structure, rate rung, white share, micro-darkness), sizes the dynamic pre-drop blackout (§4.1), and — the crux — derives the *within-drop time structure* (the 8-count stab, the 16/16/16 alternation, the full-phrase wall) from the cached per-beat/quarter-beat features rather than a fixed count. State plainly which of the four cases the design lands, which it approximates, and which the current analysis can't reliably do (route those to an operator hot-cue override).
3. **Signal-grading + held-out validation** — grade every signal the design leans on (backbone / corpus-calibrated / weak-or-cut) by the operator rule in the design doc's F4 decisions, and cut any choreography resting on a weak one. Then design the *falsifiable* proof that each surviving detector fires on the moment Brandon means, not a correlated one: agreement with operator-labeled moments on **held-out tracks** the detector was not tuned on — name which moments in which real tracks get labeled, and the agreement bar that clears a detector for live use vs sends it to cut/override. A detector that only works on its tuning tracks is per-track → cut. The design doc's claimed held-out separability and blackout-gap numbers are intent to re-verify against the shipped cache, not settled proof.
4. **Lasers inside the drop** — leave the "which drops get lasers at all" casting (v1 drop-presentation authority: rare, ranked, operator-traceable) untouched; design only the *within-drop* laser shaping (beams hard vs recede) off the same element structure, so the two layers compose.
5. **RC2 reconciliation** — RC2 is already fixed (AWR-141, landed: `WRAP_HOLD_BEATS = 0.5` in `TriggerClock.advance`, `beat_sync_engine.py`), not an open bug. Decide whether F2's "landing as infrastructure" (arrival math robust to backward beat motion, authority §4) subsumes it, still needs it as a foundation, or composes with it — and make the one real call: when F2's arrival model exists, do the continuous atmospheric effects (breathing, twinkle, breakdown simmer) migrate onto it, or stay on the already-fixed continuous clock? Recommend, don't survey.
6. **Readiness verdict + Codex-spec seams** — `READY / READY WITH GAPS / NOT READY` for handing F2 to a Codex spec, with the blocking gaps and the open operator taste-calls (not routine mechanics). Hand off the seams (which functions, config, existing code carry forward); do not write the Codex spec itself.

## Evidence packet

**Source-of-truth order:** code `*.py` → `tests/` → config examples → `runtime_status.py` → file tree → docs → old prompts/plans. Code wins over docs. Can't verify → mark unknown, never guess.

**Locked design authority (settled operator decisions — expand and spec, do not reopen):**
- `docs/architecture/lighting_engine_v2_authority.md` — §4 "Moments that land (F2)", §4.1 pre-drop blackout rules, §4.2 drop-type selection, §5 which fixtures fire (v1 casting), §6 lasers, §8 texture (F4).
- `docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md` — §3 drop family/tier/aggression, §4 landing/blackout/dip, §5 white-share/rate-rung/texture signals, and **§15.6 gap-closing decisions (2026-07-05)** — the locked F2/F3/F4 calls, incl. repeat/dense markers become **family-driven** (WALL/COMET re-fire full-energy across the chorus; HOUSE ~2 then post_drop; NEUTRAL a small hit) replacing hardcoded `LED_MAX_DROP_IMPACTS = 2`, plus the F4 signal-grading rule.

**Spectral analysis that already exists (verify shape/granularity against code):**
- `audio_spectral_features.py::extract_spectral_features_v4` → `SpectralFeaturesV4`: absolute-dB **per-beat and quarter-beat (`sub4`)** multi-band envelopes, HPSS harmonic/percussive measures, onset-strength/density envelopes, timbre descriptors; bands include a growl band (60–500 Hz harmonic) and onset mid-high (500–11025 Hz).
- `spectral_profile.py`, `spectral_cache.py` — computed once per track and cached (design record: `docs/research/spectral_audio_analysis_redesign.md`; ANLZ energy line: `docs/research/anlz_energy_project.md`).
- Consumed **today** in `state_manager.py` (`extract_spectral_features_v4` + `_calculate_smart_drop_energy_shadow`) only for smart-drop *detection* and F1 color; the `max_energy` render is a **stub** (`led_dispatch_policy.py` logs "render unchanged until F2"). So the fine-grained element structure is analyzed and cached but not yet used to shape the drop — that gap is F2's job.

**Live drop machinery F2 builds on (verify ownership):** `led_dispatch_policy.py` (LED role/drop lifecycle: `_led_drop_marker_anchor`, `_led_drop_impact_allowed`, `LED_MAX_DROP_IMPACTS`, max_energy stub); `drop_presentation.py` (WindowMachine pre_dark/in_window + the casting ladder to keep intact); `smart_phrasing.py` (drop markers, phrase segments, drop window); `laser_director.py` / `laser_executor.py` (policy vs MIDI execution); `led_look_director.py` (look/param selection, F4 containment at `_look_name_for_role`); `govee_frame_renderer.py` / `beat_sync_engine.py` / `govee_realtime_runner.py` (realtime render path — arrival math + the RC2 site).

**Already landed (implemented + software-tested this 2026-07-07 session, each adversarially reviewed PASS; HARDWARE-UNVALIDATED; auto-sync committed, so re-verify file:line at HEAD). Treat as the baseline F2 extends — do not re-derive as unimplemented or re-open RC2:**
- **AWR-140** capped two-hit drop restore (`drop_lifecycle.py`, `led_dispatch_policy.py`) — the 2nd-chorus marker re-fires a drop look, capped at 2, then demotes to `post_drop`.
- **AWR-141 (RC2)** wrap-flicker fix (`beat_sync_engine.py TriggerClock.advance`, `WRAP_HOLD_BEATS = 0.5`) — the flicker is FIXED (see deliverable 5).
- **AWR-142 (RC5)** blackout transport + runway observability (`_dispatch_led_smart_drop_blackout`) — pre-drop blackouts now log `transport=realtime|cloud` and `runway_beats=` (data if F2 touches the pre-drop blackout).
- **AWR-143** presentation label-rearm leak fix (`state_manager._drop_presentation_tick`) — a presentation impact now requires `sp_state.smart_drop_crossing`; F2's per-drop / per-section presentation sits on this gate.
- **AWR-144 (RC4)** LED solo pre-dark hold (`_dispatch_led_automation`) — the LED drop look is held when the room-split plan's pending verdict is `LASERS_ONLY`; F2's within-drop laser shaping composes with this.

**Explicit unknowns (resolve, don't guess):** the granularity/reliability of each v4 signal on Brandon's real tracks — the design doc records blind spots (chorus softness, growl-*intensity* ranking, slow wobble, sidechained kick-prominence, thick-wall sustained-synth); whether an 8-count harmonic stab is separable from surrounding drop energy at the cached resolution; whether it is per-beat enough to key a 16/16/16 alternation. Where the analysis can't reliably give a signal, say so and route to the hot-cue override — don't invent a detector.

**Known-stale:** project memory, any doc without a current status header, old prompts/plans — verify against code first.

## Boundaries

- **Read-only.** Read code/tests/config/docs; you may run the suite read-only (`python3 -m unittest discover tests` — some suites need optional deps, there is a known small red baseline, don't "fix" tests). No editing bridge code/config, no bridge restart, no hardware.
- **No implementation, no Codex spec file** — deliver the F2 design + readiness verdict + seams; Codex writes the code.
- **Don't re-litigate locked decisions** (§15.6, v1 casting). Flag a genuine code/design conflict, but don't reopen a decided taste call.
- **Delegate the grind to `tmux a -t claude`** (a separate Max-x20 account; drive it with `tmux send-keys -t claude '<task>' Enter`, poll with `tmux capture-pane -t claude -p`). Prefer it over Agent-tool subagents (including the read-only `bridge-triage` agent), which bill the SAME rate-limited account you run on — use those only when the tmux session is busy. You are the only Fable-tier agent: never spawn another; announce nested spawns; verify a delegate's load-bearing claims before relying on them.

## Claim discipline + done

Label every load-bearing claim **confirmed / assumed / unknown / rejected**, tied to a `file:line`, a test, an authority-doc §, or a spectral-feature definition. Keep "the analysis is *designed* to capture X" separate from "it *reliably* captures X on these tracks" — verify the latter against the feature code, not the design doc's word.

**End on:** `F2 READINESS: READY / READY WITH GAPS / NOT READY` + the RC2 relationship in one clause.
