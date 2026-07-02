---
doc_status: active-prompt
truth_level: current-commit-and-command-output-grounded
last_verified_commit: 68df846
last_verified_date: 2026-07-02
validation_scope: Codex offline analysis prompt — measure the TIME-DOMAIN dimensions of
  SoundSwitch parity (DMX timing, autoloop cycling alignment, transitions, playback edges,
  rewinds, BPM behavior) from the existing Jul 1 passive capture plus code inspection. Read-only
  on the capture and the live project; analysis tooling and evidence docs only; no runtime code
  changes, no bridge/live actions.
---

# Codex Prompt — SoundSwitch Time-Domain Parity Exam (offline, from existing capture)

**One-line:** the VALUE side of pack-vs-SoundSwitch parity is byte-proven (commit `5bb3a5b`:
261/261 capture samples + the A5 wire capture 16/16). This prompt measures the TIME side —
does the pack's behavior match SoundSwitch's real DMX output in *when* things happen — using
data that already exists, so the operator does not need a physical rig or a new live session
for anything this capture covers.

**You are self-directed.** The operator will not answer analysis questions mid-task. If a step
is impossible, record WHY in the report and move to the next step — never silently skip.

## Hard rules

- The capture directory is READ-ONLY: `tools/ssfmt/captures/parity/parity_20260701T185231Z/`.
- `~/Music/SoundSwitch/` is READ-ONLY. Never start/stop the bridge, never open SoundSwitch,
  never send MIDI/DMX, never touch Enttec/serial.
- NO changes to runtime code (`state_manager.py`, players, resolvers, senders, loaders). You may
  ADD offline analysis tooling under `tools/ssfmt/` (pure functions + a CLI, following the
  pattern of `tools/ssfmt/build_parity_fixture.py`) and evidence docs. Work on `main`, commit
  after meaningful checkpoints, run `python3 -m unittest discover rb_ss_bridge_v2/tests` from
  the parent dir and the three hard docs checks from the repo root before each commit.
- Do not tune tolerances to make results pass. Measure, report, classify.

## Grounded facts you build on (verified — do not re-derive)

1. **The capture contains BOTH sides.** `artdmx_packets.jsonl` (1.38 GB) holds per-packet rows
   `{ts, mono_ns, universe, sequence, dmx_sha256, ch1_32, payload_hex}` for universe 0
   (SoundSwitch's real output) AND universe 1 (the bridge's truth-check shadow of its own pack
   render decisions — ~577k packets). `rbss_artnet_truth_frames.slice.jsonl` (363 MB) is the
   bridge sidecar: rows carry `sequence`, `dmx_sha256`, `elapsed_ms`, `soundswitch_id`,
   `transport`, `frame_index`, `native_autoloop{target_identity, phase_tick, …}` — no mono_ns.
   `alignment_index.jsonl` has per-surface windows with `t_start_mono`/`t_end_mono` (seconds).
   `actions.jsonl` and `status_samples.jsonl` exist — inventory their fields before relying on
   them.
2. **The sidecar→wall-clock join is solved.** Reuse
   `rb_ss_bridge_v2.tools.ssfmt.build_parity_fixture`: `iter_artdmx`, `iter_jsonl`,
   `build_u0_runs`, `join_sidecar_to_mono` / `join_autoloop_to_mono` (two-pointer join on
   `(sequence, dmx_sha256)` in file order — ArtDMX sequence wraps 0-255 and all-zero frames
   share sha `076a27c7…`, so never use a global dict lookup). Prior join stats: 128,467 joined,
   25 dropped, monotone ratio 0.99935.
3. **The capture's U1 was rendered by the OLD (value-buggy) code.** The 2026-07-02 fix
   (`5bb3a5b`) changed decode/resolution/verifier ONLY — first verify with
   `git diff 7e1cae2..5bb3a5b --stat` that no tick/driver/sender/timing path changed, and state
   that in the report. Consequence: U1/sidecar TIMESTAMPS and U0 timing are valid evidence;
   U1 BYTE VALUES at former splice points are not (they are the old bug — ignore value diffs
   already explained by it, and re-render expected values with the CURRENT pack where needed).
4. A worked example of the method already exists:
   `tools/ssfmt/re/validate_scripted_capture.py` measured ordered transition timing on the A5
   capture (`rms_transition_residual_ms: 6.56`, `max: 15.47`). U0 wire cadence is ~25-40 ms per
   frame, so sub-frame residuals are the noise floor — one wire frame (~40 ms) is the natural
   "indistinguishable on the wire" bound.
5. Fresh pack for expected values: export one with
   `python3 tools/export_soundswitch_pack.py --project ~/Music/SoundSwitch/default.ssproj
   --output <scratch>` (expect active lanes `{algorithm_generalized: 67, oracle_proven: 16,
   unverified_parity: 0}`). Scripted rendering: `rb_ss_bridge_v2.soundswitch_laser_player
   .render_scripted_frame`; autoloop: `render_autoloop_frame(document, phase_tick)`.

## Tasks — measure each time-domain dimension

For every task: pure-function core + small CLI under `tools/ssfmt/`, unit tests for the pure
seams (synthetic streams, never the real capture), and numbers into the report.

### T1 — Scripted boundary timing (covers: dmx timing, track timeline)
For each scripted witness window (528e8b22, 9947c65e, ae9e3c61, fc10fc02): take every timeline
boundary event of the CURRENT pack document; find SS's actual U0 frame-transition (the mono_ns
where U0 changes to that boundary's expected frame, using U0 runs) and the model's predicted
time (event `time` in elapsed_ms mapped to mono via the sidecar join's local linear fit).
Report per-witness: residual distribution (median/rms/max), count of boundaries beyond one wire
frame (40 ms), and drift-over-elapsed (slope of residual vs elapsed across each full window —
this is the timeline-drift/BPM-coupling measurement; a near-zero slope over a 3-5 minute track
means the timeline does not drift).

### T2 — Autoloop cycling alignment (covers: autoloop cycling, wrap)
For each PASS-registry loop with capture coverage: within its windows, measure U0's
frame-transition times against the transition times predicted from the sidecar's `phase_tick`
progression + the loop's serialized event ticks (cycle 19200 ticks, 600/beat). Report residuals
as in T1, specifically including wrap crossings (transitions near tick 19200→0). Additionally
measure the phase RATE: regress sidecar phase_tick against mono time per window and compare the
implied BPM against U0's observed flip cadence — this is the cycling-alignment number.

### T3 — Bridge decision latency (covers: dmx timing head-to-head)
The capture has BOTH universes. For matched U0/U1 content transitions inside disk-consistent
regions (use only boundaries whose values the old code rendered correctly — the 195
previously-passing fixture rows identify safe regions): measure the mono_ns delta between SS's
U0 transition and the bridge's U1 transition for the SAME logical boundary. Report the
distribution (median/p95/max). This is the direct "would the room see a difference" number;
deltas within ~1 wire frame are indistinguishable.

### T4 — Transitions / active deck (covers: transitions, active deck)
Locate every track-change and deck-switch in the sidecar (`soundswitch_id` changes, `transport`
edges, elapsed resets). For each: measure (a) how long U0 kept emitting the OUTGOING show's
frames past the switch, (b) what U1/sidecar did in the same window (zero frames? how many
ticks?), (c) time until both sides emit the INCOMING show. Report the handoff-gap distribution
for both sides. Expected from prior analysis: SS holds stale ~50-240 ms; the pack zeroes ~1-2
driver ticks — quantify both precisely and state the worst-case perceptual difference.

### T5 — Playback edges, rewinds, BPM events (covers: rewinding, playback, bpm adjustments)
Inventory `actions.jsonl`, `status_samples.jsonl`, and the sidecar for: pauses/stops (transport
edges), elapsed discontinuities (seeks — |Δelapsed| large between adjacent rows), and BPM
changes (fields available in status samples; otherwise infer from phase-rate changes in T2).
For every instance found, measure both sides' behavior around it (as in T4). For each of the
three behaviors, conclude one of: MEASURED (with numbers) or NOT-IN-CAPTURE. For
NOT-IN-CAPTURE items, ALSO do the code-level characterization: cite file:line of the driver
behavior (`state_manager.py` `_drive_pack_output` seek/pause/stop handling — READ ONLY) and
what SS's expected behavior is per OS2L docs/prior evidence, and add the item to the residual
live-exam list.

### T6 — Verdict table + residual live exam
Produce the final table mapping every dimension of the operator's greenlight statement —
autoloops, scripted tracks, static looks, attribute cues, dmx output values, track timeline,
dmx timing, autoloop cycling, track rewinding, playback, bpm adjustments, transitions, active
deck, midi behavior — to one of:
- **PROVEN (values)** — cite the 261/261 + A5 16/16 evidence (already done, commit `5bb3a5b`);
- **MEASURED-PASS (timing)** — your T1-T5 number is within one wire frame / no drift;
- **MEASURED-DIFFERENT** — quantified difference + plain-language perceptual meaning;
- **NOT-IN-CAPTURE** — with the exact ≤10-minute live scenario that would close it (the
  operator can DJ that scenario with a capture running; no physical rig needed — the existing
  truth-check exam prompt `docs/prompts/active/soundswitch_truth_check_exam_codex_prompt.md`
  Part 2 already defines the mechanics).

Static looks note: the capture contains no accepted held-static windows (known), so static
timing is expected NOT-IN-CAPTURE — say so rather than stretching.

## Deliverables

1. New evidence doc `docs/research/soundswitch/soundswitch_time_domain_exam_2026_07.md`
   (dated, with the T6 table, all distributions, join stats, and every NOT-IN-CAPTURE item),
   registered per the docs rules (status header; `python3 tools/check_docs_metadata.py` must
   pass).
2. The analysis CLIs + pure-seam unit tests committed under `tools/ssfmt/` + `tests/`.
3. An updated exam checklist item in `docs/plans/active/soundswitch_exporter_remaining_work.md`
   reflecting what is now measured offline vs what remains for the short targeted live run.
4. Final chat report: the T6 table verbatim, the three worst numbers you found anywhere, and a
   one-paragraph plain-language answer to: "based on DMX timing evidence, would a dancefloor
   ever see a difference between the pack and SoundSwitch?" — answered honestly from the
   measurements, never from optimism.
