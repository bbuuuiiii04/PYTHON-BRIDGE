---
doc_status: active-spec
truth_level: code-and-capture-grounded
last_verified_commit: e0eed61
last_verified_date: 2026-06-29
validation_scope: offline read-only analysis tool spec; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no bridge run, no StateManager change, no MIDI/serial/Art-Net/Enttec/DMX/hardware open, no SoundSwitch/project mutation
---

# Codex Implementation Spec — SoundSwitch Autoloop Equivalence Oracle

Build an **offline, read-only** tool that proves (or refutes) that the bridge's native
autoloop renderer `render_autoloop_frame()` reproduces what SoundSwitch actually
rendered, by diffing the bridge render against SoundSwitch's captured DMX output for
the two T7d normal-mix scout captures.

This is the gate that decides whether native autoloop DMX can retire SoundSwitch's
runtime role. It is **analysis only** — it changes no runtime behavior and opens no
hardware.

## Part A — Context & root cause (verified; read, do not implement)

### What we are proving
- SoundSwitch autoloops are **not audio-reactive** and are a **pure function of (look,
  phase)** over an 8-bar / 32-beat / 19,200-tick cycle. [confirmed by operator]
- The bridge already decodes every authored autoloop and already has a pure-function
  renderer for them; it is simply not wired into the live tick. So the open question is
  purely: **does `render_autoloop_frame(look, phase_tick)` equal SoundSwitch's actual
  per-frame DMX?** [confirmed: code below]

### Verified code facts (file:line)
- Renderer: `soundswitch_laser_player.py:125` `render_autoloop_frame(loop, phase_tick) ->
  tuple[int,...]`. Returns a 19-channel (CH1-19) frame. Internally does
  `wrapped = phase_tick % loop.cycle_ticks` plus prior-cycle end-state inheritance and
  signed negative pre-roll (`:144-147`). `phase_tick` is a **cumulative non-negative int
  tick count**; the function wraps it. Returns `ZERO_FRAME` if `not loop.supported_active`
  or `loop.layout not in SUPPORTED_LAYOUTS`. [confirmed]
- Cycle length: `soundswitch_pack_loader.py:26` `AUTOLOOP_CYCLE_TICKS = 19_200`; the loader
  stamps autoloop documents with this (`:494`). 19,200 ticks = 32 beats ⇒ **600 ticks/beat**.
  [confirmed]
- Content load: `soundswitch_pack_loader.py:497` `load_pack(pack: str|Path) -> LoadedPack`;
  `LoadedPack.autoloops: Mapping[str, LoadedAutoloop | LoadedDocument]` keyed by relative
  path (e.g. `"SSAutoLoop18.ssfile"`) (`soundswitch_pack_models.py:277`). `LoadedAutoloop`
  carries `cycle_ticks`, `supported_active`, `document` (`soundswitch_pack_models.py:115,
  122-123`). [confirmed]
- Decode + note→autoloop map: the SoundSwitch project decoder produces
  `resolved_controls: tuple[ResolvedControlBinding, ...]` and `autoloops:
  tuple[LightingDocument, ...]` (`soundswitch_pack_models.py:278,283`). A
  `ResolvedControlBinding` with `target_kind == "autoloop"` carries the source MIDI binding
  (device name, `message_type`, note) and its `target` (`SSAutoLoopN.ssfile`)
  (`soundswitch_project_decoder.py:993,1011`). The SoundSwitch-facing device is the IAC bus
  (e.g. `"IAC Driver Bus 1"`, see `soundswitch_pack.py:313`). [confirmed]
  - Cross-check reference for the note→file mapping: `tests/test_inventory_project_artifacts.py:214`
    (`by_note[64] -> "SSAutoLoop18.ssfile"`, `by_note[96] -> "SSAutoLoop4.ssfile"`).
- Ground-truth frames: `tools/ssfmt/re/parse_artnet_pcap.py:89` `universe_frames(path,
  universe=0, channels=19) -> list[tuple[float, tuple[int,...]]]` returns `(epoch_seconds,
  19-channel tuple)` per ArtDMX frame. `read_pcap` timestamps are epoch seconds
  (`:41`). [confirmed]
- The captured Art-Net (loopback udp/6454, Universe 0, CH1-19) is **SoundSwitch's own DMX
  render captured passively** — nothing in the repo emits Art-Net; it is sniffed only
  (`tools/ssfmt/re/artnet_sniff.py:30`, conductor capture `tools/t7d_capture_conductor.py:580`).
  The bridge's *own* native autoloop DMX path is **Enttec serial**, not Art-Net
  (`soundswitch_frame_sender.py:3`). The Art-Net is the **measurement tap / ground truth**,
  not a show path. [confirmed] Lasers are MIDI (`[LX]` = LaserDirector) and are **out of
  scope** for this tool. [confirmed]
- Phase evidence: `session.jsonl` `autoloop_phase` rows carry `epoch_ns`, `abs_beat_pos`,
  `bpm`, `active_deck`, `lighting_mode`, `playing`, `accepted_note`, `accepted_scene`,
  `role`, `phrase_anchor_last_beat`, `midi_refire_origin_beat`, `autoloop_tick_just_fired`.
  [confirmed: sampled run1 row]

### Captures to run against (read-only)
- Run 1 (clean): `tools/ssfmt/captures/t7d/t7d_scout_mix_20260629_161931`
  — `artnet_classic.pcap`, `session.jsonl` (94 MB), `logs/bridge.log`, `project.before.sha256`.
- Run 2 (sealed/degraded): `tools/ssfmt/captures/t7d/t7d_scout_mix_cont_20260629_163143`
  — same files; `session.jsonl` 152 MB; project added 5 SoundSwitch files mid-run (preset +
  `recordable/*.dat`); no phase footer. Autoloop `.ssfile` content is unchanged by those
  additions, but the oracle must still hash-gate (Task 4).

### Content source + integrity (verified constraint)
The capture stored only the project **hashes** (`project.before.sha256`), not the `.ssfile`
bytes. The renderable autoloop content must come from the current project / canonical pack
**and be proven identical** to what SoundSwitch played during the capture by matching each
autoloop's source SHA-256 against the capture's `project.before.sha256`. If a look's hash
does not match, that look is reported `CONTENT_DRIFTED` and excluded from match scoring —
never silently rendered against a different version.

### Known unknowns (must be surfaced, not buried)
- [unknown] The exact phase origin SoundSwitch used relative to the bridge's `abs_beat_pos`
  (a sub-cycle offset). The oracle **discovers** this (Task 5 search), it is not assumed 0.
- [unknown] Fixed render/transport latency between the bridge's beat clock and SoundSwitch's
  emitted Art-Net frame. The oracle searches a small latency window (Task 5).
- [assumed] The note fired in `bridge.log` / `accepted_note` equals the note SoundSwitch
  received and thus the active autoloop. Resolve authority is the IAC-bus
  `ResolvedControlBinding`; Codex must confirm `accepted_note` populates during active
  autoloop playback and fall back to the bridge.log MIDI timeline if not.
- [assumed] CH1-19 of the render tuple correspond to DMX channels 1-19 of the captured
  universe (the same CH1-CH19 profile). Make this an explicit, single-point constant.

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules (do not touch)
- **No production module is modified.** The tool only *imports and calls*
  `soundswitch_laser_player`, `soundswitch_pack_loader`, `soundswitch_project_decoder`,
  `tools/ssfmt/re/parse_artnet_pcap`. If an import needs a tiny pure helper exposed, add it
  without changing behavior and say so.
- **No bridge run, no StateManager, no `select_autoloop` wiring.** This is not the native-
  autoloop implementation; it is its evidence gate.
- **No hardware/IO beyond reading capture files**: no serial, MIDI, Art-Net socket, Enttec,
  or live SoundSwitch. `parse_artnet_pcap` reads files only — keep it that way.
- **No SoundSwitch project mutation.** Read project/pack bytes read-only.
- Lasers (MIDI) are entirely out of scope.
- No new third-party dependencies.

All new code lives under `tools/ssfmt/re/` (the existing RE/analysis home).

### Task 1 — `tools/ssfmt/re/autoloop_oracle/groundtruth.py`: pcap → frame stream
- Function `load_groundtruth(pcap_path) -> list[tuple[float, tuple[int,...]]]`: thin wrapper
  over `parse_artnet_pcap.universe_frames(pcap_path, universe=0, channels=19)`. Validate each
  tuple is length 19; raise on empty.
- Constant `DMX_CH = 19` and `DMX_CHANNEL_BASE = 0` (tuple index 0 == DMX channel 1) — the
  single explicit channel-mapping point.

### Task 2 — `tools/ssfmt/re/autoloop_oracle/phase_track.py`: session.jsonl → beat timeline
- Stream the file line by line (files are 94–152 MB; never `json.load` the whole file). Parse
  only rows where `kind == "autoloop_phase"`.
- Emit a sorted list of `PhaseSample(epoch_s: float, abs_beat_pos: float, bpm: float,
  active_deck: int, lighting_mode: str, playing: bool, accepted_note: int|None,
  phrase_anchor_last_beat: float, midi_refire_origin_beat: float)`. `epoch_s = epoch_ns / 1e9`.
- Function `beat_at(samples, t) -> float|None`: linear-interpolate `abs_beat_pos` at wall time
  `t` (the rows are dense — ~200 Hz). Return None outside the sample range or across a
  discontinuity (abs_beat_pos resets / active_deck change within the interpolation interval).

### Task 3 — `tools/ssfmt/re/autoloop_oracle/active_look.py`: which autoloop is live when
- Build `note_to_autoloop: dict[int, str]` from the decoded project's `resolved_controls`:
  keep bindings where `target_kind == "autoloop"`, `binding.message_type == "note"`, and the
  device is the IAC bus; map `note -> target` (e.g. `64 -> "SSAutoLoop18.ssfile"`). Provide the
  decode entry path explicitly (use the project-decode function in
  `soundswitch_project_decoder.py`; if a single project-decode entry is not public, decode the
  needed parts and assemble `resolved_controls` exactly as the exporter does — do not invent a
  mapping).
- Build `active_look_at(t) -> str|None`: prefer per-row `accepted_note` from Task 2 (resolve via
  `note_to_autoloop`); fall back to the most recent prior `bridge.log` autoloop MIDI event
  (`[LX] fired` / `midi-refire` note) when `accepted_note` is null. Return None when no look is
  active or the note is unmapped.
- **Autocycle guard:** if more than 32 beats elapsed since the last refire/fire for the active
  look (SoundSwitch could have free-cycled to a random look — see capture-evidence report
  §refire), mark that interval `UNRELIABLE_GROUNDTRUTH` and exclude it from scoring (count and
  report it; never silently include).

### Task 4 — `tools/ssfmt/re/autoloop_oracle/content.py`: load + hash-gate the looks
- `load_autoloops(pack_or_project) -> dict[str, LoadedAutoloop]` via
  `soundswitch_pack_loader.load_pack(...)` filtered to `LoadedAutoloop` entries.
- `verify_against_capture(loaded, project_before_sha256_path) -> dict[str, str]`: for each
  autoloop, prove its source SHA-256 equals the capture's `project.before.sha256` entry for that
  `SSAutoLoopN.ssfile`. Status per look ∈ {`MATCHED_SOURCE`, `CONTENT_DRIFTED`, `MISSING`}.
  Only `MATCHED_SOURCE` looks are scored.

### Task 5 — `tools/ssfmt/re/autoloop_oracle/diff.py`: pure-function align + diff core
This is the algorithm; it MUST be pure (no file/subprocess IO) and unit-tested in Part D.
- `phase_tick(abs_beat: float, phase_offset_beats: float) -> int`:
  `round((abs_beat + phase_offset_beats) * 600)`, clamped `>= 0`. (600 = 19200/32.)
- `predicted_frame(loop: LoadedAutoloop, abs_beat: float, phase_offset_beats: float) ->
  tuple[int,...]`: call `render_autoloop_frame(loop, phase_tick(...))`.
- `frame_mismatch(predicted, actual, tol: int) -> int`: count channels where
  `abs(predicted[i]-actual[i]) > tol` over the 19 channels.
- `score(frames, beat_fn, look_fn, loops, *, latency_s, phase_offset_beats, tol) -> ScoreResult`:
  for each ground-truth `(t, actual)` in an active+reliable window, compute
  `abs_beat = beat_fn(t - latency_s)`, `loop = loops[look_fn(t - latency_s)]`, then
  `mismatch = frame_mismatch(predicted_frame(loop, abs_beat, phase_offset_beats), actual, tol)`.
  Aggregate: frames scored, exact-match frames (tol applied), per-channel error histogram,
  per-look match rate, worst-mismatch sample timestamps.
- `search(frames, beat_fn, look_fn, loops, *, latency_grid, phase_grid, tol) -> Best`: evaluate
  `score` over the small grid (e.g. latency −0.25..+0.25 s step 0.01; phase_offset 0..32 beats
  step 0.05) and return the `(latency_s, phase_offset_beats)` maximizing exact-match rate, plus
  its full `ScoreResult`. Note in the result that latency and phase-offset are partially
  degenerate (a single best alignment is the claim, not two independent physical constants).

### Task 6 — `tools/ssfmt/re/autoloop_oracle/run.py`: CLI + report
- CLI: `python3 -m tools.ssfmt.re.autoloop_oracle.run <capture_dir> [--pack PATH] [--tol N]`.
- Wire Tasks 1-5 for one capture; write `autoloop_oracle_report.md` + `.json` into the capture
  dir (these are ignored capture artifacts, like the existing analysis sidecars).
- Report MUST include: best `(latency, phase_offset)`; overall exact-match rate; **per-look**
  status (`MATCHED_SOURCE`/`CONTENT_DRIFTED`/`MISSING`) and exact-match rate; frames scored vs
  excluded (with exclusion reasons: idle, transition, `UNRELIABLE_GROUNDTRUTH`,
  `CONTENT_DRIFTED`); looks never seen on the wire (e.g. note 96 / `SSAutoLoop4.ssfile`); and a
  one-line verdict per look ∈ {`EQUIVALENT`, `MISMATCH(residual)`, `NO_GROUNDTRUTH`,
  `CONTENT_DRIFTED`}. No silent caps anywhere — if anything is dropped, the count and reason
  are printed.

### Task 7 — tests (Part D).

## Part C — Invariants that MUST still hold (live safety)
1. The tool runs fully offline and **changes no runtime behavior**. It imports production
   modules read-only and must not instantiate `StateManager`, start any thread that writes
   DMX, or open serial/MIDI/socket/Enttec/Art-Net/SoundSwitch.
2. No production module is modified to make the oracle work (any exposed helper is pure and
   behavior-preserving).
3. Source SoundSwitch project / pack bytes are read-only; no project mutation.
4. The 200 Hz push loop and all live subsystems are untouched (this tool never imports a path
   that runs them).
5. Honest evidence: passive wire + software comparison **never** becomes a hardware/fixture
   validation claim. Status line stays `SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED`.
6. A look whose source hash does not match the capture is excluded, never rendered as if it
   were the captured version.

## Part D — Tests (`tests/test_autoloop_oracle.py`, pure-function seam only)
All tests use **synthetic in-memory inputs** — no capture files, no pcap, no subprocess.
Construct a tiny fake `LoadedAutoloop` (or smallest real-shaped object the renderer accepts)
with a known 2-or-3-channel timeline so `render_autoloop_frame` output is predictable.
1. **Exact match:** synthetic ground-truth frames generated from the fake loop at a known
   phase ⇒ `score` reports 100% exact-match at offset 0.
2. **Phase-offset recovery:** generate frames at a known nonzero `phase_offset_beats` ⇒
   `search` recovers that offset (within grid resolution) and reports ~100% match there.
3. **Latency recovery:** generate frames shifted by a known latency ⇒ `search` recovers it.
4. **Deliberate mismatch:** corrupt one channel in the ground truth ⇒ `frame_mismatch`/`score`
   report the mismatch (not a false pass).
5. **Wrap correctness:** `phase_tick` beyond one cycle (e.g. 33 beats) maps into the cycle and
   renders the same as 1 beat (sanity for the `% 19200` wrap + pre-roll path).
6. **Autocycle guard:** a >32-beat gap interval is excluded and counted.
Do not modify any production test to make these pass.

## Part E — Acceptance (definition of done)
- [ ] `python3 -m tools.ssfmt.re.autoloop_oracle.run <capture>` runs on **both** captures and
  writes a report with a per-look verdict.
- [ ] Report states best `(latency, phase_offset)`, overall exact-match rate, per-look match
  rates, and every excluded frame's reason (no silent drops).
- [ ] Content hash-gate enforced: only `MATCHED_SOURCE` looks scored; drifted/missing flagged.
- [ ] `note 96 / SSAutoLoop4.ssfile` (never fired) is reported `NO_GROUNDTRUTH`, not a false pass.
- [ ] `tests/test_autoloop_oracle.py` passes; the diff core is proven by the synthetic
  match / mismatch / offset-recovery / latency-recovery / wrap / guard tests above.
- [ ] `python3 -m unittest discover tests` stays green; no production module or test modified.
- [ ] Report carries the `SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED` status and makes
  no fixture/hardware claim.
- [ ] The result clearly answers, per look: does the bridge render equal SoundSwitch's captured
  output, and if not, what is the residual / required phase offset.

## When you finish
- Commit per task (Task N message: `oracle: <task>`). Final commit message:
  `tools: SoundSwitch autoloop equivalence oracle (offline, read-only)`.
- Report back: the per-look verdict table for both captures, the best `(latency, phase_offset)`
  found, overall exact-match rate, and any look that is `MISMATCH` / `CONTENT_DRIFTED` /
  `NO_GROUNDTRUTH` — in plain language, stating whether steady-state native autoloops are
  proven equivalent to SoundSwitch.

## Adversarial self-review (done before handoff)
- *"The diff trivially passes because render renders the same doc it decoded."* — Guarded: the
  ground truth is SoundSwitch's **independent** Art-Net capture, not a re-render. A pass means
  decode+render+phase all match SoundSwitch's real output.
- *"Phase origin assumed zero."* — Guarded: Task 5 searches phase offset and latency; the claim
  is the best-fit alignment + residual, reported, not assumed.
- *"Wrong look attributed to a window."* — Guarded: IAC-bus resolved-binding authority +
  autocycle guard excludes ambiguous/free-cycled intervals.
- *"Stale/contaminated content."* — Guarded: per-look source-hash gate against the capture's
  `project.before.sha256`.
- *"Reads 150 MB into memory / OOM."* — Guarded: Task 2 streams line-by-line.
- *"Silent truncation hides coverage gaps."* — Guarded: every excluded frame is counted with a
  reason; never-seen looks are reported `NO_GROUNDTRUTH`.
- Residual risk to accept: latency/phase degeneracy means the tool reports a best *alignment*,
  not two separately-proven physical constants — fine for the equivalence claim, noted in Part B5.
