---
doc_status: active-prompt
truth_level: current-evidence-packet-grounded
last_verified_commit: 00d8be2
last_verified_date: 2026-07-02
validation_scope: Fable 5 one-shot handoff prompt for SoundSwitch exporter/runtime perfect-parity spec synthesis from current evidence docs. Prompt-only; no implementation, live action, bridge restart, SoundSwitch action, MIDI/DMX/Enttec action, or hardware validation.
---

# Fable Prompt: SoundSwitch Exporter Perfect-Parity Spec

Target model: Claude Fable 5
Effort: xhigh

You are Fable 5 working from evidence in `/Users/bbui/rb_ss_bridge_v2`.

Mission: synthesize a Codex-executable one-shot spec to make the SoundSwitch exporter and runtime pack playback achieve perfect parity with SoundSwitch for the supported local project surface.

Why this matters:
Brandon needs one complete handoff that lets Codex fix the exporter/runtime SoundSwitch path without another round of partial discoveries. Do not narrow this to the live truth-check comparator. The target is perfect parity across exported values, timeline timing, autoloop cycling, static looks, BPM/pitch behavior, playback edges, seeks, transitions, active-deck authority, and comparator/capture validity.

Benign scope:
This is benign local software/spec work for Brandon's DJ lighting bridge. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. Review normal software correctness, tests, maintainability, runtime safety, and operator behavior only.

Deliverable:
- Produce a Codex-executable implementation spec.
- Do not implement code.
- Do not edit files.
- Do not perform live, hardware, SoundSwitch, Rekordbox, MIDI, DMX, bridge restart, process-memory, or capture actions.
- Return concise source-tied rationale, claim labels, ordered tasks, tests/checks, and acceptance criteria.

Packet manifest for Brandon:
- Send this prompt plus:
  - `docs/research/soundswitch/soundswitch_truth_exam_live_blockers_2026_07_02.md`
  - `docs/research/soundswitch/soundswitch_time_domain_exam_2026_07.md`
  - `docs/plans/active/soundswitch_exporter_remaining_work.md`
  - `local/soundswitch/rbss_canonical_pack/manifest.json`
- The repo docs above are the durable packet; the `/tmp/rbss_*` files named below are optional raw evidence for spot-checking, not required to understand the mismatch inventory.
- Proven by current evidence: active canonical pack lanes report zero active `unverified_parity`; offline and live evidence identify real timing/byte disagreement classes; static/playback/BPM/transition/seek/active-deck gaps are explicitly known.
- Not proven by current evidence: official comparator PASS, full static parity, full playback-edge parity, full seek/rewind parity, full BPM/pitch parity, full transition/active-deck parity, Enttec/hardware parity, or broad compatibility beyond the pinned project/profile/version.

Source-of-truth order:
1. Current repo code and tests, if you are allowed to inspect them.
2. Current canonical pack and machine reports listed below.
3. Current evidence docs listed below.
4. Historical prompts only as context, never as proof unless reverified.

Allowed tools and paths:
- Read-only repo/file inspection is allowed only inside `/Users/bbui/rb_ss_bridge_v2`.
- Read-only inspection of the exact evidence files below is allowed.
- Do not run exporter, bridge, SoundSwitch, Rekordbox, live comparators, capture tools, or commands that mutate `local/`, project files, runtime state, or hardware-adjacent state.
- If you need a command result that is not already in this prompt, write the exact read-only command Codex should run later instead of running it yourself.

Evidence packet:
- `docs/research/soundswitch/soundswitch_time_domain_exam_2026_07.md`
  - Offline passive capture report from `tools/ssfmt/captures/parity/parity_20260701T185231Z/`.
  - Scripted timing: 436 measured boundaries, median 15.841 ms, p95 28.229 ms, 5 boundaries over one 40 ms wire frame, max 740.657 ms.
  - Autoloop timing: 1377 transitions, median 14.682 ms, p95 93.783 ms, 230 transitions over one 40 ms wire frame, max 748.502 ms.
  - Static, rewind/seek, pause/stop/restart, BPM pitch movement, transitions, active deck, and MIDI behavior are not cleanly covered by that capture.
- `docs/research/soundswitch/soundswitch_truth_exam_live_blockers_2026_07_02.md`
  - Live truth-check evidence and blockers from 2026-07-02.
  - Official comparator was invalid because capture topology produced `missing_u0` and `sequence_gap:*` style invalidity; diagnostic filtered rows remain root-cause evidence.
  - Diagnostic aggregate from `/tmp/rbss_truth_exam_combined_mismatch_details.jsonl`: 10350 parsed rows, 6967 byte mismatch rows, 3226 timing mismatch rows, 157 summary rows.
  - Largest diagnostic groups: Wanton autoloop 5364 rows, Titanium scripted 2101 rows, Wanton idle 1300 rows, BLACKPINK scripted 1003 rows, Titanium idle 321 rows.
  - Byte-diff shapes included U0 zero/U1 authored, U1 zero/U0 authored, and nonzero disagreements.
  - Its "Representative diagnostic rows" section gives exact file/mode/state/channel examples for each byte-diff shape plus the worst timing outliers.
  - Its "Completion audit against the original greenlight surface" section is the required checklist of captured-fail, gap, and fail-closed surfaces.
- `local/soundswitch/rbss_canonical_pack/manifest.json`
  - Supported boundary: SoundSwitch 2.10.3, universe 0, CH1-CH19, fixture profile `b8ad2201b9e4c94696c898a7e8f6a5a9`, project UUID `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}`.
  - Totals: 42 autoloops, 45 scripted inventory entries, 44 parsed scripted, 32 active existing-path scripted, 233 render cues, 233 total venue records, 32 static looks, 19 IAC autoloop bindings, 25 learned mappings, 1 DDJ static override.
  - Active parity lanes: `algorithm_generalized=67`, `oracle_proven=16`, `unverified_parity=0`.
  - Inactive lanes still exist: `algorithm_generalized=29`, `unverified_parity=6`.
- Optional raw: `/tmp/rbss_time_domain_exam_refresh.json`
  - Fresh rerun of `tools/ssfmt/time_domain_exam.py` against the July 1 capture and current canonical pack.
  - Confirms the same scripted/autoloop timing numbers above.
  - Scripted witnesses: `528e8b22...` 30 boundaries, 0 over 40 ms; `9947c65e...` 45 boundaries, 1 over 40 ms; `ae9e3c61...` 358 boundaries, 1 over 40 ms; `fc10fc02...` 3 boundaries, all 3 over 40 ms.
  - Handoffs: 3 scripted handoffs; one sidecar mono gap was 1443.264 ms.
  - U1 zero-frame runs in joined scripted rows: 8 runs, median 1673.5 frames, max 15921 frames.
- Optional raw: `/tmp/rbss_parity_fixture_scripted.json`
  - Scripted fixture builder found one capture-source divergence for `9947c65e-cfd1-476e-aa90-4aed65ae5f11`.
  - Witness row counts: `528e8b22...` 30, `9947c65e...` 57, `ae9e3c61...` 68, `fc10fc02...` 6.
- Optional raw: `/tmp/rbss_parity_fixture_autoloop.json`
  - Autoloop fixture builder found capture-source divergences for `SSAutoLoop13`, `14`, `15`, `16`, `17`, `46`, `47`, `48`, `50`, `55`, `6`, and `8`.
  - Some covered loops produced zero accepted fixture rows despite timing rows: `SSAutoLoop15`, `17`, `46`, `47`, `50`, and `8`.
- Optional raw: `/tmp/rbss_parity_fixture_static.json`
  - Static capture windows unavailable.
  - Slots 0, 24, and 16 were attempted but `static_held` was never observed; slot 31 was unavailable from StreamDeck/reserved bridge MIDI IAC.
  - U0 was recorded but static alignment is not accepted.
- Optional raw: `/tmp/rbss_soundswitch_coverage_no_validation.json`
  - Structural coverage without validation: 42 autoloops all `structurally_parsed_no_per_file_capture`, no referenced missing GUIDs, 2 unused stale GUIDs.
  - Scripted structural coverage: 45 rows; 36 `structurally_parsed`, 8 `structurally_parsed_not_wire_validated`, 1 `unsupported`.
  - Full scripted structural inventory has 18 referenced missing cue GUID references across inactive/not-wire-validated rows.
- Optional raw: `/tmp/rbss_project_inventory_default.json` and `/tmp/rbss_project_inventory_codex.json`
  - Project artifact classification is partial/fail-closed because `.ssa`, `.sspreset`, and non-MIDI recordable control-registry semantics remain opaque.
  - Default project: 19 resolved autoloop bindings, 5 resolved static look bindings, 0 unresolved in those selections.
  - Codex project: 18 resolved autoloop bindings, 4 resolved static look bindings, 0 unresolved in those selections.
  - Bridge scene bindings still include `no_decoded_project_binding` rows, so exporter/spec must not overclaim those as decoded SoundSwitch project bindings.
- Raw live artifacts if needed for Codex later, not for Fable broad ingestion by default:
  - `/tmp/rbss_truth_exam_combined_mismatch_details.jsonl`
  - `/tmp/rbss_artnet_truth_frames.jsonl`
  - `/tmp/rbss_truth_exam_report*.json*`
  - `/tmp/bridge.log`

Known mismatch and gap classes that must be covered:
1. Comparator and capture validity
   - Official comparator invalidity is itself a blocker. A future pass must compare SoundSwitch U0 against bridge truth U1 without loopback duplication/interleaving false invalidity, while still rejecting real packet gaps.
2. Exported DMX value parity
   - Active manifest currently claims zero active unverified parity lanes, but live diagnostic rows still showed byte disagreements. Fable must decide whether those disagreements are runtime truth-frame generation, stale source, capture topology, active-deck state, or exporter data defects.
3. Scripted timing parity
   - Offline scripted timing is mostly close but not perfect: 5/436 boundaries over 40 ms and `fc10fc02` is a hard blocker with 3/3 large misses.
4. Autoloop timing and cycling parity
   - Offline autoloop timing has 230/1377 transitions over 40 ms, wrap outliers, stable implied BPM near 160, and worst residuals near 0.75 s.
   - Live Wanton autoloop diagnostic rows showed large byte/timing disagreement volume.
5. Capture-source divergence and stale source edits
   - Scripted `9947c65e...` and many autoloops have fixture-builder capture-source divergences. The spec must require separating exporter defects from changed SoundSwitch/project source bytes.
6. Static looks and manual/static state parity
   - Static is not proven. Attempted static slots did not produce accepted `static_held` windows. Static look exporter/runtime behavior must be specified and validated, not assumed.
7. Playback edges
   - Live Titanium evidence showed `playing=true` with `active_deck=0`, `mode=idle`, then delayed scripted ownership. Pause/resume/stop/restart/cold-start must be parity surfaces.
8. Seeks and rewinds
   - Live backward seek produced high mismatch volume. Forward seek past cue boundaries and backward rewinds must be explicit acceptance cases.
9. BPM and pitch movement
   - Bridge detected live BPM movement, but diagnostics lacked `live_bpm`, and transition evidence showed stale live BPM contamination (`bpm=145.0`, `live_bpm=155.0`). Deck-scoped live-BPM authority is a required parity surface.
10. Transitions and active-deck authority
   - Offline handoff evidence includes a 1443.264 ms sidecar mono gap. Live transition evidence showed autoloop-to-scripted deck split and stale ownership. Crossfader/master/deck authority must be tested.
11. Idle/stale metadata and zero-frame behavior
   - Live idle rows used stale Wanton metadata with `active_deck=0`. Offline scripted rows include long U1 zero-frame runs. The spec must define intentional zero/idle output versus stale or delayed ownership.
12. Inactive, unsupported, and opaque inventory
   - Perfect parity must be scoped honestly. Active supported surface can be fixed; inactive unverified lanes, unsupported scripted row, opaque `.ssa`/`.sspreset`/recordable semantics, and bridge scenes with no decoded project binding must be tracked, guarded, or intentionally excluded with tests.
13. Normal operator mode
   - Truth mode must not trap normal operation. Normal launch should report truth disabled; truth launch should be explicit and reversible.
14. Hardware-adjacent final validation
   - Software tests cannot prove Enttec/SoundSwitch/live hardware behavior. The spec must include a final live exam plan, but Fable must not run it.

Required Fable procedure:
1. Read the evidence packet and identify contradictions, stale assumptions, and missing proof.
2. Label every important claim `[confirmed]`, `[assumed]`, `[unknown]`, or `[rejected]`.
3. Separate root-cause categories: exporter data/rendering, runtime frame selection, timing/scheduler, capture/comparator topology, source freshness, deck/transport/BPM authority, and operator control.
4. Produce a single Codex-executable spec that can fix the full supported parity surface in one implementation pass.
5. Include specific tests/checks that would fail for each known mismatch class.
6. Include a final live validation run-sheet that covers all live-only surfaces after software changes, but keep implementation and live operation assigned to Codex/Brandon.

Output format:
1. Verdict: `READY FOR CODEX SPEC`, `READY WITH EVIDENCE GAPS`, or `NOT READY`.
2. Coverage matrix: surface, current evidence, verdict, required fix/proof, acceptance test.
3. Root-cause hypothesis map, with confidence labels and evidence links.
4. Codex-executable implementation spec:
   - Ordered tasks.
   - Likely files/modules to inspect or touch.
   - Files/areas not to touch unless evidence requires it.
   - Tests and offline commands.
   - Required docs/evidence updates.
   - Live validation gates and operator actions.
5. Stop conditions and no-overclaim rules.
6. Final self-check that the spec covers every mismatch/gap class listed above.
