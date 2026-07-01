---
doc_status: active-prompt
truth_level: synthesized-from-code-tests-research-and-live-U0U1-capture
last_verified_commit: 3131aa7
last_verified_date: 2026-07-01
validation_scope: Fable 5 one-shot prompt — adversarially audit the "parity is runtime, not exporter" reframe with Ghidra + the live capture, then author a Codex-executable spec for the parity fixes; bounded to SoundSwitch 2.10.3 canonical project / RAVE / 2 mirrored lasers / Universe 0 / CH1-CH19
---

# Fable 5 Prompt — Audit the Parity Reframe, then Author the Fix Spec

## 0. Your mission and the one-shot rule

You are **Fable 5**, the planner/auditor. You get **exactly one prompt — no follow-up round.** Your spec, once Codex implements it, must **FINALIZE the SoundSwitch exporter + bridge DMX runtime feature for shipping**: the bridge pack perfectly mimics SoundSwitch across everything the operator can do, the parity is *proven*, every runtime/exporter gap and edge case is fixed or fail-closed-flagged, and the only thing left is the operator's own physical hardware/optical/kill-path validation run. Treat this as the finishing spec for the entire feature, not a patch. Two jobs, in order:

1. **ADVERSARIALLY AUDIT** the reframe in §2 (claim: the SoundSwitch exporter/pack content is already *faithful*, and perfect parity is blocked only by **3 runtime bridge bugs** — not by any exporter/cue-composition mechanism). Use **Ghidra/GhidraMCP** (authorized, §5) *and* the existing live U0/U1 capture (§3). **Try to REFUTE it.** The reframe rests on a thin sample: 4 scripted tracks (of 32), 3 static looks (of 4 mapped), 18 of 19 autoloops. Confirm it, bound it, or break it — and say which, with evidence.

2. **AUTHOR the complete, self-contained, Codex-executable spec that achieves PERFECT PARITY** — the end state is the bridge pack reproducing SoundSwitch's DMX (CH1-19) **bit-exactly** across **every** surface, mode transition, timing condition, and edge case the operator can reach, so the bridge can fully replace SoundSwitch live. The 3 runtime bugs (§6.1) are the **known floor, not the ceiling**: you must sweep the whole runtime + exporter for **every** divergence from SoundSwitch — known or not (§6.2) — and spec the fix for each (runtime or exporter). The spec must be complete enough for Codex to execute end-to-end and reach perfect parity with no further planning from you and no second Fable pass. Anything not yet provable must be explicitly fail-closed + flagged, with the exact capture that would prove it.

Rules: You author a spec; you do NOT write production code and you do NOT run captures (the operator + Claude own captures — you get the existing one as evidence and may *specify* additional captures for them in the spec). Never defer to a "future spec." **Code wins over docs**; re-verify every file:line against current code.

---

## 1. Product purpose and locked scope

**Purpose.** SoundSwitch is the operator's authoring tool. A read-only exporter compiles the saved project (autoloops, scripted tracks, attribute cues, static looks, TrackMap, learned MIDI) into an immutable "bridge pack." At playback the bridge renders that pack to CH1-19 DMX so SoundSwitch isn't needed at runtime. Goal: the bridge's DMX (U1) equals SoundSwitch's own DMX (U0) exactly, so the bridge can replace SoundSwitch live. The operator authors, clicks Export, and anything they made renders identically — no per-look capture.

**Locked scope (operator-confirmed — do not widen):** SoundSwitch 2.10.3; the **default/canonical project only** (pinned UUID `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}` — reject any other); **RAVE** venue (GUID `b8ad2201b9e4c94696c898a7e8f6a5a9`); **2 DMX lasers that are always mirrored**; **Universe 0, CH1-19**, no separate intensity channel. **Snap-and-hold** (no time-varying/interpolated output — capture-confirmed, §2). **Best-effort export + "unverified" flag** for anything not provably correct (never block the operator's content). `DD42028C` is a metadata-less orphan the operator never plays — **excluded** from all scope.

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
- **ATTACK THIS:** (a) Is the values-match real across MORE than Rihanna? Check the other 3 captured scripted windows in the capture (`{AE9E3C61...}`, `{9947C65E...}`, `{FC10FC02...}`) and, if needed, specify a capture of more of the 32 tracks. (b) With Ghidra on the cue resolve/compose path (below `SSVenueData::GetLightingState`), confirm there is NO residual composition mechanism the 4 tracks happened to avoid. (c) **Pin the zero-blip root cause in code** and prove whether it is systemic across all scripted tracks and whether it reaches real production output (not just the shadow) — this is the highest-value fix.

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
Docs (verify vs code): `docs/plans/active/soundswitch_exporter_remaining_work.md` (status + invariants), `docs/research/soundswitch/soundswitch_ssfile_format.md` + `soundswitch_ghidra_addendum.md` + `soundswitch_re_closure_report.md` (format RE + the confirmed binary symbol/address map), `docs/plans/active/soundswitch_pack_parity_root_cause_spec.md` (prior investigation — note it is largely superseded by this reframe; DD42028C excluded).

---

## 5. Ghidra / GhidraMCP authorization and method

**You are explicitly authorized to use Ghidra + GhidraMCP** against the SoundSwitch 2.10.3 binary; the operator will have the project open (prior sessions connected via `mcp__ghidra`). Use it to *independently verify* the reframe, not to re-crack a nonexistent mechanism: confirm the static 5-map→CH1-19 composition, confirm there is no residual scripted cue-composition mechanism, and confirm the autoloop phase contract. Start from the confirmed symbol/address map (ghidra_addendum + parity root-cause spec lines 59-83), then decompile the render/compose/lookup path. Do not present a Ghidra finding as truth without cross-checking the capture. Prior work is arm64-verified; treat x86_64 as symbol-checked only unless decompiled.

---

## 6. The parity goal and the fixes — Codex-executable

**Definition of done: the bridge pack PERFECTLY mimics SoundSwitch.** For the locked setup, at every scripted cue boundary, static-look trigger, autoloop phase, mode transition, precedence case, and timing condition the operator can produce, the bridge's emitted CH1-19 frame is **byte-identical** to SoundSwitch's, with correct timing. The three confirmed bugs (§6.1) are the *known floor*; your audit + the exhaustive sweep (§6.2) must find **everything else** in the way, and the spec must fix all of it or fail-closed + flag it with the capture that would prove it.

**This spec is the FINISHER.** Once Codex implements it, the SoundSwitch exporter + bridge DMX runtime feature must be **ship-ready**: perfect parity implemented *and proven* (offline oracle + full-coverage operator+Claude capture exam, Part D), every edge case handled or fail-closed-flagged, all software gates green (`docs/plans/active/soundswitch_exporter_remaining_work.md` §"Required software gates"), and the ONLY remaining external gate is the operator's physical hardware/optical/kill-path run (which you cannot perform — define its procedure). Also fold in any still-open items from that doc's §"Remaining work" / §"Project completion definition" that block shipping. State an explicit **ship gate** (the checklist that means "done").

### 6.1 Confirmed fixes (priority order)
1. **Scripted zero-blip flicker (PRIORITY).** Root-cause the periodic full-zero frames in the pack render/driver path and fix so a steadily-playing scripted track emits a continuous frame — **without** regressing the intended real clears (genuine stop/unload/stale/track-change/discontinuity must still zero; only *transient* jitter must not). Likely in `state_manager._drive_pack_output`'s transport/fresh/discontinuity gates and/or `render_scripted_frame`. Pure-function test seam + a duty-cycle regression (steady playback ⇒ 0% spurious zero frames).
2. **Static MIDI trigger authority.** Root-cause `[SS-MIDI] input port gone` (the port the operator's controllers use for static holds keeps dropping; the group-health-poison fix wasn't enough) and fix so held static looks reach the bridge and render. Preserve the group-health overlay-trust behavior already landed.
3. **Autoloop phase + selection.** Lock the phrase-anchored 32-beat phase contract as derived (not guessed); ensure `render_autoloop_frame` reproduces U0 at each phase; root-cause and fix SSAutoLoop4 (note 96) never being selected. Build on the landed phase-zero fix; do not regress it.

### 6.2 Exhaustive DMX-runtime edge-case sweep (find EVERY divergence)
Perfect mimicry means no divergence anywhere — so sweep the whole pack render/driver runtime **and** the exporter for ANY case where U1 would differ from SoundSwitch's U0 or emit unsafe DMX. Enumerate each, reproduce it (from the existing capture or a specified new operator+Claude capture), and spec a fix; explicitly list any you cannot yet prove and the capture that would. Cover at minimum:
- **Transport / mode transitions:** scripted↔autoloop↔idle↔static, deck switch mid-cue, pause/resume, stop/unload, seek / elapsed-discontinuity, track-change — and whether EVERY state field is cleaned up on EVERY transition path (not only the path that sets it).
- **Precedence / masking:** blackout/emergency override, static-overlay precedence, SoundSwitch-present suppression, the reload-wait latch — each must match SoundSwitch's real precedence, not just an internally-consistent one.
- **Mirror integrity:** whether the 2-laser `0x493`/`0x496` mirror ever diverges on CH1-19.
- **Reload / runtime-swap races:** pack reload or backend swap during live playback (the atomic `PackRuntime` swap).
- **Timing / clocking:** BPM drift + tempo change (the capture already showed 160→155 BPM), phrase-boundary races, the 200 Hz push loop vs 60 Hz memory interpolation, phase quantization/rounding.
- **Input health:** MIDI port-gone, a controller dropping mid-hold, the group-health overlay-trust path.
- **Frame integrity:** anything nonzero beyond CH19, out-of-range channel values, non-primary fixture-group leakage, partial/garbled frames.
- **Coverage completeness:** the reframe is proven on only 4 of 32 scripted tracks, 3 of 4 static looks, 18 of 19 autoloops — the spec MUST define exactly what additional operator+Claude captures close the gap to ALL 32 scripted tracks, all 4 mapped static looks, and all 19 autoloops, and must fail-closed + flag anything still unproven.
- Plus **any exporter/composition fix your audit uncovers** if the reframe is wrong anywhere.

---

## 7. Deliverable — the Codex spec (Part A-E, self-contained)

- **Part A — Audit result + root cause (read-only):** your verdict on the reframe per surface (CONFIRMED / BOUNDED / REFUTED) with Ghidra + capture evidence, every claim labeled confirmed/assumed/unknown. The confirmed mechanism/root-cause for each of the 3 runtime bugs, the full §6.2 edge-case sweep results (every divergence found, its root cause, its proof status: proven / needs-capture / fail-closed-flagged), and any exporter issue found.
- **Part B — Design:** the exact fix for each; the "unverified parity" flag model; how verification breaks the exporter/verifier self-reference (oracle grounded in U0/Ghidra, not a re-render). Keep the static step-function model; add no time-awareness.
- **Part C — Tasks for Codex (ordered, commit after each):** files to change, exact change, a pure-function test seam per task, acceptance check. Scripted zero-blip first.
- **Part D — Verification / capture protocol (run by operator + Claude, not you):** offline oracle per surface (must fail against today's renderer, pass after fix) + the live whole-show U0/U1 capture exam (what to capture, coverage, pass/fail). Specify additional captures needed (e.g. more of the 32 scripted tracks; SSAutoLoop4).
- **Part E — Constraints, invariants, live-safety, self-review:** §8 + the 9-point pre-handoff checklist.

## 8. Constraints, invariants, out-of-scope

- **Invariants:** StateManager is the sole DeckState writer + sole per-tick pack-frame submitter; the 200 Hz loop gains no blocking/socket/MIDI/serial/filesystem/subprocess work; source SoundSwitch project is read-only; identity is exact (reject non-pinned UUID); only verified packs load; reload/export never enables output, changes backend, starts the bridge, or opens hardware; direct DMX and MIDI-laser output stay mutually exclusive; blackout/emergency wins; status/logs never leak paths/ports/device-names/UUIDs/raw frames. (Full list: `soundswitch_exporter_remaining_work.md` §Invariants.)
- **Live-safety:** the bridge drives real lasers; no task enables hardware output, changes backend, or restarts the bridge (operator-only, gated by a physical kill path). The scripted zero-blip is itself a flicker-safety issue — the fix must not introduce a stuck-non-zero frame on a real stop/unload.
- **Git:** work on `main`; no new branches; no secrets/live-config/canonical-pack contents committed.
- **Out of scope (fail-closed):** any project but the pinned UUID; any venue/profile/universe/fixture but RAVE/CH1-19; SoundSwitch ≠ 2.10.3; multi-deck/crossfade; time-varying/interpolated rendering; multi-fixture-group compositing beyond the mirror assert; `.ssproj` internals; hardware validation.

## 9. Self-review before finalizing
Confirm: you attacked the reframe (didn't just accept it) and stated CONFIRMED/BOUNDED/REFUTED per surface with evidence; every mechanism is confirmed/assumed/unknown, never guessed; the zero-blip root cause is pinned in code and proven systemic-or-not; you swept the runtime EXHAUSTIVELY for every divergence (§6.2), not just the 3 known bugs; every Codex task has a pure-function seam and a must-fail-then-pass check; the capture protocol is executable by operator+Claude; nothing is deferred to a second pass; live-safety and pinned-scope fail-closed boundaries hold. Above all: **once Codex implements this spec, is the feature actually SHIP-READY** — perfect parity proven or fail-closed-flagged, all edge cases + closeout items covered, only the operator's physical hardware run remaining? If not, the spec is incomplete — finish it.
