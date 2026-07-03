---
doc_status: active-prompt
truth_level: synthesized-from-code-tests-research-and-live-U0U1-capture
last_verified_commit: 3131aa7
last_verified_date: 2026-07-01
validation_scope: Fable 5 one-shot prompt — adversarially audit the "parity is runtime, not exporter" reframe with Ghidra + the live capture, then author a Codex-executable spec for the parity fixes; bounded to SoundSwitch 2.10.3 canonical project / RAVE / 2 mirrored lasers / Universe 0 / CH1-CH19
---

# Fable 5 Prompt — Audit the Parity Reframe, then Author the Fix Spec

> 2026-07-02 routing note: this prompt is older than the live truth-check/offline
> time-domain evidence packet. For the current post-exam one-shot Fable handoff,
> use `docs/prompts/active/soundswitch_truth_exam_fable_fix_prompt.md` with
> `docs/research/soundswitch/soundswitch_truth_exam_live_blockers_2026_07_02.md`
> and `docs/research/soundswitch/soundswitch_time_domain_exam_2026_07.md`.
> Do not treat this prompt's "3 runtime bugs" reframe or "no new captures" rule
> as current truth unless reverified against those newer evidence docs.

## 0. Your mission and the one-shot rule

You are **Fable 5**, the planner/auditor. You get **exactly one prompt — no follow-up round.** Your spec, once Codex implements it, must **FINALIZE the SoundSwitch exporter + bridge DMX runtime feature for shipping**: the bridge pack perfectly mimics SoundSwitch across everything the operator can do, the parity is *proven*, every runtime/exporter gap and edge case is fixed or fail-closed-flagged, and the only thing left is the operator's own physical hardware/optical/kill-path validation run. Treat this as the finishing spec for the entire feature, not a patch. Two jobs, in order:

1. **ADVERSARIALLY AUDIT** the reframe in §2 (claim: the SoundSwitch exporter/pack content is already *faithful*, and perfect parity is blocked only by **3 runtime bridge bugs** — not by any exporter/cue-composition mechanism). Use **Ghidra/GhidraMCP** (authorized, §5) *and* the existing live U0/U1 capture (§3). **Try to REFUTE it.** The reframe rests on a thin sample: 4 scripted tracks (of 32), 3 static looks (of 4 mapped), 18 of 19 autoloops. Confirm it, bound it, or break it — and say which, with evidence.

2. **AUTHOR the complete, self-contained, Codex-executable spec that achieves PERFECT PARITY** — the end state is the bridge pack reproducing SoundSwitch's DMX (CH1-19) **bit-exactly** across **every** surface, mode transition, timing condition, and edge case the operator can reach, so the bridge can fully replace SoundSwitch live. The 3 runtime bugs (§6.1) are the **known floor, not the ceiling**: you must sweep the whole runtime + exporter for **every** divergence from SoundSwitch — known or not (§6.2) — and spec the fix for each (runtime or exporter). The spec must be complete enough for Codex to execute end-to-end and reach perfect parity with no further planning from you and no second Fable pass. Anything not yet provable must be explicitly fail-closed + flagged, with the exact capture that would prove it.

Rules: You author a spec; you do NOT write production code and you do NOT run captures. **The operator does NOT want to run any more captures** — you get the ONE existing capture (§3) as evidence and must derive+prove everything from it plus Ghidra + code analysis. Do NOT make a new capture a required step or a ship gate anywhere; anything unprovable from existing evidence is fail-closed + flagged, and any live re-capture you mention must be explicitly OPTIONAL/post-ship. Never defer to a "future spec." **Code wins over docs**; re-verify every file:line against current code.

---

## 1. Product purpose and locked scope

**Purpose.** SoundSwitch is the operator's authoring tool. A read-only exporter compiles the saved project (autoloops, scripted tracks, attribute cues, static looks, TrackMap, learned MIDI) into an immutable "bridge pack." At playback the bridge renders that pack to CH1-19 DMX so SoundSwitch isn't needed at runtime. Goal: the bridge's DMX (U1) equals SoundSwitch's own DMX (U0) exactly, so the bridge can replace SoundSwitch live. The operator authors, clicks Export, and anything they made renders identically — no per-look capture.

**FIRST PRINCIPLE — ALGORITHM-LEVEL PARITY, NOT CONTENT-LEVEL (non-negotiable).** Parity MUST be proven at the level of the *render algorithm*, not per content item. The requirement is: for the RAVE / CH1-19 profile, the bridge's render functions (`render_scripted_frame`, `render_autoloop_frame`, static-look composition) are **behaviorally equivalent to SoundSwitch's own render code** — derived by reading SoundSwitch's algorithm in Ghidra and confirmed on the existing capture's samples. Once that equivalence holds, **ANY content the operator authors — the current 32 scripted tracks / 19 autoloops / static looks, OR 150 brand-new ones added later — renders identically BY CONSTRUCTION, with no new capture, ever.** The existing capture is a one-time *algorithm-validation* artifact, not a content enumeration. **If your audit finds the render is content-dependent (i.e. correctness can't be proven for as-yet-unseen authored content without capturing it), that is a DESIGN DEFECT to FIX — make the render provably content-independent — NOT a reason to require captures.** A spec that would force the operator to capture every new authored look/track/loop has failed the product and is unacceptable. The only legitimate boundary is the locked profile/layout/version scope (§1): content outside RAVE/CH1-19/2.10.3 fails closed; content *inside* it always renders correctly once the algorithm is proven.

**Locked scope (operator-confirmed — do not widen):** SoundSwitch 2.10.3; the **default/canonical project only** (pinned UUID `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}` — reject any other); **RAVE** venue (GUID `b8ad2201b9e4c94696c898a7e8f6a5a9`); **2 DMX lasers that are always mirrored**; **Universe 0, CH1-19**, no separate intensity channel. **Snap-and-hold** (no time-varying/interpolated output — capture-confirmed, §2). **Best-effort export + "unverified" flag** for anything not provably correct: "never block the operator's content" means **do not block authoring/export visibility** — an unproven look/cue still exports and is visible/authorable — but it does **NOT** mean allow unverified content to drive **parity-live output**. Anything not yet proven-to-match-U0 must be flagged and must **fail-closed on the live parity path** (rendered only under an explicit operator-acknowledged "unverified" state, never silently trusted as SoundSwitch-equivalent). `DD42028C` is a metadata-less orphan the operator never plays — **excluded from operator performance/parity coverage** (it is not part of the show), but **retained as a NEGATIVE-CONTROL witness**: a known-divergent track the parity oracle should correctly FLAG as non-matching. Do not erase it; use it to prove the oracle catches divergence.

---

## 2. The reframe you must audit (my findings — treat as a HYPOTHESIS to attack)

Verified by the live capture at `tools/ssfmt/captures/parity/parity_20260701T185231Z` (see §3). U0 = SoundSwitch on Art-Net universe 0; U1 = the bridge's truth-check shadow render on universe 1.

**Claim: the exporter/pack content is faithful; parity is blocked by 3 RUNTIME bugs.**

### 2.1 Static — RENDER ALREADY CORRECT (audit: does it generalize?)
- For the 3 live mapped looks — slot 0 (FULL STRAIGHT LINES WHITE), 24 (STROBE BUILDUP #1), 16 (OFF) — SoundSwitch's real CH1-19 U0 frame is **byte-identical** to the exporter's `generic_attributes`-only render (`fixture_group=0x493`) AND to the pack's `pre_rendered_frame_ch1_ch19`. Verified programmatically. Example settled U0 for slot 24: `[1,0,21,255,0,40,138,0,255,0,255,0,255,0,93,0,0,0,255]`.
- Therefore `render_static_look_frame` (`soundswitch_pack.py:81-86`) and runtime `apply_layers` (`soundswitch_laser_player.py:179-214`) applying **only generic attributes** — ignoring the intensity/strobe/colour/position maps — is NOT a defect for this rig: SoundSwitch bakes those into the generic frame at author/export time. Slot 24 also confirmed **time-invariant** (2,548 U0 packets, one frame) and nothing nonzero beyond CH19 (mirror → one 19-ch output).
- **The only static problem is trigger authority:** the bridge never observes the held look (`static_held` never fired; log `[SS-MIDI] input port gone`). Claude's prior group-health-poison fix (`soundswitch_midi_input.py` snapshot split) was necessary but NOT sufficient — the MIDI input port itself is dropping.
- **ATTACK THIS:** With Ghidra (`RebuildStaticLookCache 0x100335230`, `StaticLook::Read 0x10033aa6c`), confirm the composition is generic-only for the RAVE profile in ALL cases — including the 21 mapped-but-unused / unmapped static slots that have empty generic but populated colour/position/strobe/intensity. Is there any authored look whose real CH1-19 comes from those maps (not generic)? If yes, the "generic-only is correct" claim is bounded, not universal — surface it.

### 2.2 Scripted — cue VALUES already correct; the "17% mismatch" is a RENDER zero-blip flicker
- On the Rihanna track `{528E8B22-BD17-41B9-A111-275D3E8B3031}`, U1's cue *values* match U0's (same choreographed frames, incl. a CH15 155↔191 toggle that matches U0). The mismatch is entirely **periodic full-frame ZERO blips in U1**: ~0.16 ms every ~21 ms, a **17.8% zero duty cycle** — which exactly matches the operator's long-known "~17% scripted mismatch."
- Verified the blips originate in the **pack render/driver path**, not the truth sink: the sink (`artnet_truth.py:214-243`) only logs submitted frames and even flags `active_dark` (dark frame + active intent), i.e. it is *handed* zero frames. So the render/driver periodically emits a full-zero frame during steady scripted playback. Likely cause: the pack driver transiently clearing the scripted base (the stale-snapshot / elapsed-discontinuity / transport guards in `state_manager._drive_pack_output` ~3923-3996 firing on momentary snapshot jitter). **This is a real hardware-flicker bug for production output**, and it is the whole "17%."
- The DD42028C "unknown cue mechanism" was an orphan dead end; **real tracks' cue composition is correct** (`raw_reference-1 → stored_key` resolution + cumulative step-function reproduce U0's values).
- **ATTACK THIS (NO NEW CAPTURES — use the existing capture + Ghidra + code):** (a) Is the values-match real across MORE than Rihanna? Check the other 3 captured scripted windows (`{AE9E3C61...}`, `{9947C65E...}`, `{FC10FC02...}`). For the tracks NOT in the capture, do NOT request a capture — instead prove the general claim from **code + Ghidra**: show that `render_scripted_frame`'s cue resolution/composition is track-independent (same `raw-1→stored_key` + cumulative step-function for every `shared_441_dictionary_timeline` doc), so if it matches U0 on the captured tracks and the algorithm matches SoundSwitch's (Ghidra), it matches for all 32. (b) With Ghidra on the cue resolve/compose path (below `SSVenueData::GetLightingState`), confirm there is NO residual composition mechanism the 4 tracks happened to avoid. (c) **Pin the zero-blip root cause in code** and prove from the code path (not a new capture) whether it is systemic across all scripted tracks and whether it reaches real production output vs only the shadow — this is the highest-value fix.

### 2.3 Autoloop — model correct; needs accurate phase + selection
- U0 confirmed: **real animation**, dwell **exactly 32 beats**, tempo-locked (12.00 s @160 BPM, 12.38 s @155 BPM = 32×60/BPM), **phrase-anchored** (a new loop starts at the phrase marker; the bridge selects by phrase and advances at the next phrase or ~32 beats — operator-confirmed). Per-frame phase truth lives in the truth sidecar `rbss_artnet_truth_frames.slice.jsonl` (`target_identity`/`anchor_beat`/`phase_tick`), NOT `status_samples` (native_autoloop is empty under SS-present suppression).
- Claude already fixed the phase-zero runtime bug (`state_manager.py:4013-4044` bootstraps the held scene only when `native_autoloop.state is None`; `native_autoloop_resolver.py:142-210` re-anchors only on a real edge). Cycle = 19,200 ticks at 600 ticks/beat.
- **Two open items:** SSAutoLoop4.ssfile "LAGGY 1/4 W" (IAC note 96) never got selected by the bridge in the capture (a selection/authority gap, not a render gap); and the exact phase origin/anchor must be locked as a *derived* contract, not the current grid-search guess.
- **ATTACK THIS:** From `AutoLoopLayout::GetStateForTime 0x10025f000` + the sidecar, confirm the phrase-anchored 32-beat phase contract exactly (origin, quantization, reset/continue) and that `render_autoloop_frame(loop, phase_tick)` reproduces U0 at each phase. Root-cause why note 96 never fires.

---

## 3. The capture (your primary empirical evidence)

`tools/ssfmt/captures/parity/parity_20260701T185231Z/` (gitignored). Files:
- `artdmx_packets.jsonl` — every Art-Net packet: `{ch1_32, universe, mono_ns, ...}`. **universe 0 = U0 (SoundSwitch), universe 1 = U1 (bridge shadow).** Split by universe to compare.
- `rbss_artnet_truth_frames.slice.jsonl` — the U1 truth sidecar with per-frame intent incl. `native_autoloop.target_identity/anchor_beat/phase_tick`, `elapsed_ms`, `active_dark`. This is the real autoloop-phase + scripted-elapsed alignment source.
- `alignment_index.jsonl` — state windows (surface/label/look_slot|ssid|loop_identity/t_start_mono/t_end_mono). NOTE: static rows are absent (the static-hold detector never fired because the bridge never saw the holds — recover static windows from `actions.jsonl` `static_slot_*` timestamps instead).
- `status_samples.jsonl`, `actions.jsonl`, `capture_meta.json`, `capture_end.json`, `artifacts.sha256`, `bridge.tail.log`. Totals: U0 152,613 pkts, U1 878,408, sidecar 426,750 rows, status 12,233 samples.
- The comparator `tools/artnet_compare.py` is LIVE-only (binds sockets); do not run it against the file — pair U0/U1 offline by nearest `mono_ns`, but note U1 sends ~5-6× faster than U0, so use a **duty-cycle** measure (fraction of active time U1 is all-zero), not raw nearest-neighbor match rate, which aliasing inflates.

---

## 4. Read these (code wins over docs)

Code: `soundswitch_pack.py` (exporter), `soundswitch_laser_player.py` (renderer: `render_scripted_frame:110-129`, `render_autoloop_frame:132-154`, `apply_layers:179-214`), `soundswitch_pack_loader.py`, `soundswitch_pack_verifier.py`, `soundswitch_project_decoder.py` (raw-1 resolution ~529-548), `state_manager.py` (`_drive_pack_output` ~3780-4130 — the pack driver, base-clear guards, truth enqueue), `artnet_truth.py` (truth sink), `native_autoloop_resolver.py`, `soundswitch_midi_input.py` (static trigger input; the group-health fix + the port-gone path :430-506).
Docs (verify vs code): `docs/plans/active/soundswitch_exporter_remaining_work.md` (status + invariants), `docs/research/soundswitch/soundswitch_ssfile_format.md` + `soundswitch_ghidra_addendum.md` + `soundswitch_re_closure_report.md` (format RE + the confirmed binary symbol/address map), `docs/plans/active/soundswitch_pack_parity_root_cause_spec.md` (the prior parity investigation — treat as the **BASELINE to audit**; supersede its conclusions **only if your audit proves the reframe**. It holds the Ghidra function map and rejected hypotheses; DD42028C in it is the negative-control witness, not show scope).

---

## 5. Ghidra / GhidraMCP authorization and method

**You are explicitly authorized to use Ghidra + GhidraMCP** against the SoundSwitch 2.10.3 binary; the operator will have the project open (prior sessions connected via `mcp__ghidra`). Use it to *independently verify* the reframe, not to re-crack a nonexistent mechanism: confirm the static 5-map→CH1-19 composition, confirm there is no residual scripted cue-composition mechanism, and confirm the autoloop phase contract. Start from the confirmed symbol/address map (ghidra_addendum + parity root-cause spec lines 59-83), then decompile the render/compose/lookup path. Do not present a Ghidra finding as truth without cross-checking the capture. Prior work is arm64-verified; treat x86_64 as symbol-checked only unless decompiled.

---

## 6. The parity goal and the fixes — Codex-executable

**Definition of done: the bridge pack PERFECTLY mimics SoundSwitch.** For the locked setup, at every scripted cue boundary, static-look trigger, autoloop phase, mode transition, precedence case, and timing condition the operator can produce, the bridge's emitted CH1-19 frame is **byte-identical** to SoundSwitch's, with correct timing. The three confirmed bugs (§6.1) are the *known floor*; your audit + the exhaustive sweep (§6.2) must find **everything else** in the way, and the spec must fix all of it or fail-closed + flag it with the capture that would prove it.

**This spec is the FINISHER.** Once Codex implements it, the SoundSwitch exporter + bridge DMX runtime feature must be **ship-ready**: perfect parity implemented *and proven from the EXISTING capture* (`tools/ssfmt/captures/parity/parity_20260701T185231Z`) via an offline oracle — the operator does NOT want to run additional captures, so the proof strategy must derive everything from the one capture already taken plus Ghidra + code analysis, and **must not require any new capture as a ship gate**. Anything not provable from existing capture+Ghidra+code is fail-closed + flagged (see §2 live-parity rule), NOT deferred to a new capture. Every edge case handled or fail-closed-flagged, all software gates green (`docs/plans/active/soundswitch_exporter_remaining_work.md` §"Required software gates"), and the ONLY remaining external gate is the operator's physical hardware/optical/kill-path run (which you cannot perform — define its procedure). Also fold in any still-open items from that doc's §"Remaining work" / §"Project completion definition" that block shipping. State an explicit **ship gate** (the checklist that means "done").

### 6.1 Confirmed fixes (priority order)
1. **Scripted zero-blip flicker (PRIORITY).** Root-cause the periodic full-zero frames in the pack render/driver path and fix so a steadily-playing scripted track emits a continuous frame — **without** regressing the intended real clears (genuine stop/unload/stale/track-change/discontinuity must still zero; only *transient* jitter must not). Likely in `state_manager._drive_pack_output`'s transport/fresh/discontinuity gates and/or `render_scripted_frame`. Pure-function test seam + a duty-cycle regression (steady playback ⇒ 0% spurious zero frames).
2. **Static MIDI trigger authority.** Root-cause `[SS-MIDI] input port gone` (the port the operator's controllers use for static holds keeps dropping; the group-health-poison fix wasn't enough) and fix so held static looks reach the bridge and render. Preserve the group-health overlay-trust behavior already landed.
3. **Autoloop phase + selection.** Lock the phrase-anchored 32-beat phase contract as derived (not guessed); ensure `render_autoloop_frame` reproduces U0 at each phase; root-cause and fix SSAutoLoop4 (note 96) never being selected. Build on the landed phase-zero fix; do not regress it.

### 6.2 Exhaustive DMX-runtime edge-case sweep (find EVERY divergence)
Perfect mimicry means no divergence anywhere — so sweep the whole pack render/driver runtime **and** the exporter for ANY case where U1 would differ from SoundSwitch's U0 or emit unsafe DMX. Enumerate each, reproduce it **from the existing capture + code analysis + Ghidra (no new captures)**, and spec a fix; explicitly fail-closed + flag any you cannot prove from existing evidence (do NOT request a new capture as the resolution). Cover at minimum:
- **Transport / mode transitions:** scripted↔autoloop↔idle↔static, deck switch mid-cue, pause/resume, stop/unload, seek / elapsed-discontinuity, track-change — and whether EVERY state field is cleaned up on EVERY transition path (not only the path that sets it).
- **Precedence / masking:** blackout/emergency override, static-overlay precedence, SoundSwitch-present suppression, the reload-wait latch — each must match SoundSwitch's real precedence, not just an internally-consistent one.
- **Mirror integrity:** whether the 2-laser `0x493`/`0x496` mirror ever diverges on CH1-19.
- **Reload / runtime-swap races:** pack reload or backend swap during live playback (the atomic `PackRuntime` swap).
- **Timing / clocking:** BPM drift + tempo change (the capture already showed 160→155 BPM), phrase-boundary races, the 200 Hz push loop vs 60 Hz memory interpolation, phase quantization/rounding.
- **Input health:** MIDI port-gone, a controller dropping mid-hold, the group-health overlay-trust path.
- **Frame integrity:** anything nonzero beyond CH19, out-of-range channel values, non-primary fixture-group leakage, partial/garbled frames.
- **Coverage completeness (WITHOUT new captures):** the capture proves 4 of 32 scripted tracks, 3 of 4 static looks (bridge U1 side never reached for static — trigger-authority bug), 18 of 19 autoloops. The operator will NOT run more captures. So the spec must close the gap by **generalization-by-code+Ghidra, not by more data**: prove the render algorithm is content-independent (a captured-track match + a Ghidra-confirmed algorithm ⇒ all tracks match), and prove the static/autoloop U1 side via code once the trigger/selection bugs are fixed (the captured U0 is the target; the fixed renderer's U1 is checked against it offline). Anything that genuinely cannot be proven this way is fail-closed + flagged as "unverified-parity," never rendered as trusted live output and never deferred to a new capture.
- Plus **any exporter/composition fix your audit uncovers** if the reframe is wrong anywhere.

---

## 7. Deliverable — the Codex spec (Part A-E, self-contained)

- **Part A — Audit result + root cause (read-only):** your verdict on the reframe per surface (CONFIRMED / BOUNDED / REFUTED) with Ghidra + capture evidence, every claim labeled confirmed/assumed/unknown. The confirmed mechanism/root-cause for each of the 3 runtime bugs, the full §6.2 edge-case sweep results (every divergence found, its root cause, its proof status: proven / needs-capture / fail-closed-flagged), and any exporter issue found.
- **Part B — Design:** the exact fix for each; the "unverified parity" flag model; how verification breaks the exporter/verifier self-reference (oracle grounded in U0/Ghidra, not a re-render). Keep the static step-function model; add no time-awareness.
- **Part C — Tasks for Codex (ordered, commit after each):** files to change, exact change, a pure-function test seam per task, acceptance check. Scripted zero-blip first.
- **Part D — Verification (NO new captures required for ship):** the ship proof is an **offline oracle** replaying the EXISTING capture's U0 against the fixed renderer (must fail against today's renderer, pass after fix), per surface, plus code+Ghidra generalization for content not in the capture. Do NOT make any new capture a ship gate. You MAY note an OPTIONAL post-ship live re-capture as a nice-to-have confidence check (explicitly optional, never blocking), but the feature ships on the offline oracle + code/Ghidra proof alone.
- **Part E — Constraints, invariants, live-safety, self-review:** §8 + the 9-point pre-handoff checklist.

## 8. Constraints, invariants, out-of-scope

- **Invariants:** StateManager is the sole DeckState writer + sole per-tick pack-frame submitter; the 200 Hz loop gains no blocking/socket/MIDI/serial/filesystem/subprocess work; source SoundSwitch project is read-only; identity is exact (reject non-pinned UUID); only verified packs load; reload/export never enables output, changes backend, starts the bridge, or opens hardware; direct DMX and MIDI-laser output stay mutually exclusive; blackout/emergency wins; status/logs never leak paths/ports/device-names/UUIDs/raw frames. (Full list: `soundswitch_exporter_remaining_work.md` §Invariants.)
- **Live-safety:** the bridge drives real lasers; no task enables hardware output, changes backend, or restarts the bridge (operator-only, gated by a physical kill path). The scripted zero-blip is itself a flicker-safety issue — the fix must not introduce a stuck-non-zero frame on a real stop/unload.
- **Git:** work on `main`; no new branches; no secrets/live-config/canonical-pack contents committed.
- **Out of scope (fail-closed):** any project but the pinned UUID; any venue/profile/universe/fixture but RAVE/CH1-19; SoundSwitch ≠ 2.10.3; multi-deck/crossfade; time-varying/interpolated rendering; multi-fixture-group compositing beyond the mirror assert; `.ssproj` internals; hardware validation.

## 9. Self-review before finalizing
Confirm: you attacked the reframe (didn't just accept it) and stated CONFIRMED/BOUNDED/REFUTED per surface with evidence; every mechanism is confirmed/assumed/unknown, never guessed; the zero-blip root cause is pinned in code and proven systemic-or-not; you swept the runtime EXHAUSTIVELY for every divergence (§6.2), not just the 3 known bugs; every Codex task has a pure-function seam and a must-fail-then-pass check; the capture protocol is executable by operator+Claude; nothing is deferred to a second pass; live-safety and pinned-scope fail-closed boundaries hold. Above all: **once Codex implements this spec, is the feature actually SHIP-READY** — perfect parity proven or fail-closed-flagged, all edge cases + closeout items covered, only the operator's physical hardware run remaining? If not, the spec is incomplete — finish it.
