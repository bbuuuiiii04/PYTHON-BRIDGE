---
doc_status: active-implementation-spec
truth_level: evidence-constrained-spec
last_verified_commit: a5f7ced
last_verified_date: 2026-06-20
validation_scope: spec only; no implementation; software+wire-grounded; hardware-unvalidated
---

# Codex Implementation Spec — SoundSwitch Standalone Laser Exporter + Renderer + Enttec Output

> Scripted byte-parity is currently blocked. Execute
> `docs/plans/active/soundswitch_scripted_renderer_closure_handoff_spec.md`
> before implementing this runtime spec.

## Part A — Context & root cause (verified; read, do not implement)

**Goal.** Author lighting in SoundSwitch, export a static pack to the bridge, and have the bridge
reproduce SoundSwitch's Universe-0 CH1–19 laser output **byte-exact at runtime with SoundSwitch not
running**. The bridge already owns decks, transport, beat/BPM, autoloop selection, and color-cue
selection; SoundSwitch is purely the laser DMX renderer being replaced.

### Verified facts (read in current code / wire this session)
- [confirmed] The bridge emits **no DMX/Art-Net/Enttec** today — `grep -ril "artnet|enttec|dmx_pro|
  6454|universe" --include=*.py` outside `tools/ssfmt` returns nothing. DMX laser output is a NEW
  capability; it does not exist yet.
- [confirmed] The existing laser path is **MIDI only** and is a SEPARATE output from the DMX lasers:
  `laser_executor.py:44` holds `self._midi_output`, `:237` calls `self._midi_output.trigger(...)`.
  This spec must NOT modify or share state with that path.
- [confirmed] `StateManager` owns a **200 Hz push loop** sharing one thread with the event loop
  (`state_manager.py:307` `_TICK_INTERVAL = 1.0/200`; `:2922` comment "no time.sleep() in push loop
  thread"). The push loop must not gain blocking serial/file/socket I/O (`runtime_invariants`).
- [confirmed] **Output adapter already exists**: VLN `/Users/bbui/virtuallasernode/calib/dmx_pro.py`
  drives the Enttec DMX-USB-Pro. Contract: write a 512-byte frame (CH1→index 0) atomically to
  `/tmp/vln_calib_frame.bin`; a `dmx_pro.py daemon --port <tty>` process pushes it to the widget at
  ~40 pps and self-refreshes. It has watchdog-stale blackout, catchable-exit blackout, and `set`/
  `blackout`/`base`/`show` subcommands. `kill -9` of the daemon leaves the LAST frame on the wire
  (widget firmware self-retransmits) — physical kill switch is the true failsafe.
- [partial] **Autoloop render model is a layered persistent buffer of static snapshots**: autoloop
  wire segments show ~4–9 distinct frames over ~500 captured frames (~33 fps). This model is NOT
  general scripted-track truth: the 2026-06-20 TITANIUM, Opalite, and New Sky captures are only
  16/64, 23/39, and 304/367 event samples exact. Documented in
  `docs/research/soundswitch_ssfile_format.md` ("Layered laser render model"). Current hypothesis:
  - **Position layer** = captured legacy timeline cues resolved **ONE-BASED**. Autoloop and A5 wire
    evidence support this convention, while representative scripted tracks retain layer/mask
    residuals.
  - **Color layer** = an independently bridge-selected color Attribute Cue → CH8 (color/effects),
    CH9 (color speed).
  - **Persist channels** CH8, CH9, CH11 (strobe) hold in the validated autoloop/A5 scope. New Sky
    falsifies a universal scripted persist rule: a decoded CH15-only record clears CH8 on wire.
  - Idle/transition = all-zero frame.
- [confirmed, autoloop scope only] **Byte-exact verification** (evidence `/tmp/soundswitch_finish_IiVlD1`,
  `autoloop_probe.pcap`): over the full bridge-used autoloop corpus captured (SSAutoLoop
  3/5/18/50/52/53/54), 29/30 distinct wire frames are full-frame byte-exact under
  `position-cue(one-based) ⊕ color-cue(CH8/9) ⊕ persist(8,9,11)` with a steady-loop inherited initial
  state; color layer 30/30; the 1 miss is the all-zero blackout frame. Reproduced via
  `layered_renderer.render_timeline(..., control_channels=(8,9,11))`.
- [confirmed] **Reference convention is provenance-dependent** (`project_ss_ref_convention`): legacy
  records one-based (wire-proven), newly-created direct, **edited-legacy files MIXED with no byte
  disambiguator**. The exporter MUST fail closed on mixed/edited files, never silently resolve them.
- [confirmed] **Scripted-track detection must be byte-based**: a duplicated project lazily forgets
  which tracks are scripted until opened (`project_ss_scripted_rediscovery`). Detect from
  `{SSID}.ssfile` bytes + TrackMap, never a UI flag.
- [confirmed] **SoundSwitch autoloop capacity is up to 32 per bank × 4 banks = 128**
  (`project_ss_autoloop_banks`); 42 is merely the count currently populated. The exporter must bound
  to 128 and never assume the current count. The bridge currently drives ~19 (bank-4 all 16, banks
  1/2/3 one each); export inventories all populated looks and flags the bridge-used subset.
- [confirmed, operator + code] **The "laser" subsystem IS the SoundSwitch autoloop-selection
  mechanism, not a separate rig.** `LaserDirector` (`laser_director.py`) decides a scene
  (`house_phrase_1`, …) and `midi_output.py` sends a MIDI note to `IAC Driver Bus 1`
  (`config/laser_director.json: "midi_output_port": "IAC Driver Bus 1"`), which SoundSwitch maps to
  an autoloop. SoundSwitch then renders Universe-0 CH1–19 to the **2 mirrored DMX laser fixtures**
  (groups `0x493` and `0x496`). SoundSwitch's ONLY job in this rig is these lasers. The standalone
  path keeps `LaserDirector`'s scene decision and replaces its *output* (MIDI-select → direct DMX).
- [confirmed] **Color is intentionally decoupled.** Operator authoring convention: attribute-cue
  looks leave CH8/CH9 unchecked, so an autoloop of attribute cues has color open; a color attribute
  cue placed *before* the autoloop sets CH8/CH9 for the whole loop (persists, as wire-verified).
  Phase-1 render takes the active color from the imported pack timeline; **phase-2 intent is a
  bridge-owned laser color engine mirroring the LED color engine** (the bridge picks CH8/CH9 itself).

### Unknowns — surface, do NOT guess (each blocks the live-wiring task, not the offline tasks)
- [unknown] **Runtime color-cue selection variable (phase-2 only).** For phase-1 the color comes from
  the pack timeline; for the future bridge-chosen-color engine, the exact bridge variable/event that
  names the current color is not yet identified in code.
- [unknown] **Scene/MIDI-note → `SSAutoLoopN.ssfile` binding.** Today this lives in SoundSwitch's
  MIDI-mapping config. Standalone, the bridge must know which autoloop file each `LaserDirector` scene
  selects. The exporter/config must capture this map (it is NOT in the `.ssfile` bytes alone).
- [unknown] **Physical DMX start addresses of the two mirrored fixtures (0x493, 0x496) in the
  512-channel Enttec universe.** Wire data is CH1–19 of a group; the universe address map for BOTH
  mirrored fixtures must be supplied as explicit config, never inferred.
- [unknown] **Multi-deck compositing on the DMX path** (which deck owns the universe, blending). The
  bridge owns deck logic, but how two decks' looks combine on the laser universe is not decoded.
- [partial, software-only] **Scripted-track transport edge cases** (seek/pause/resume/loop/refire,
  end, unload) against the static export. The research helper provides pure
  `layered_renderer.render_at_elapsed(...)`: every query replays eligible records from an explicit
  initial state in `(elapsed, source_sequence)` order with CH8/CH9/CH11 persistence and explicit
  direct/one-based provenance. `render_playback_state(...)` adds playing/paused versus
  ended/unloaded all-zero policy. The dedicated Opalite capture validates a byte-exact backward
  seek, a byte-exact forward seek, 22/22 logged loop samples, re-fire from the first playing sample,
  and 2/2 confirmed-stop all-zero frames. A first forward seek and pause landed in the same known
  116–133 s static-model residual interval seen in uninterrupted playback: wire held stable through
  pause and returned to byte-exact after resume. Unload reset position but left stale bridge
  filename/mode; wire was already zero. This validates position reconstruction where the base model
  is correct, not complete scripted rendering.

**Readiness correction:** autoloop output is static-snapshot stepping reproducible from project
bytes, but representative scripted output is not yet byte-exact under the same layer/mask rules.
The offline exporter, inventory, and fail-closed parser remain buildable research tasks; a production
scripted renderer must not be enabled until the new residuals are decoded and recaptured. Live wiring
remains a separate operator-gated task because it is the highest-risk action.

### Scripted validation scope required before Task 4

Representative passive captures must cover multiple real scripted tracks, including legacy
one-based and newly-created direct provenance, the decoupled color workflow, and arbitrary-position
samples after forward/backward seek, pause/resume, loop/refire, end, and unload. Edited-legacy MIXED
tracks remain negative controls and non-exportable. TITANIUM (`FC10FC02`), Opalite (`74044FA4`),
and New Sky (`AE9E3C61`) plus an Opalite transport run are now captured, but none is full-frame
byte-exact. Opalite's default-project bytes behave one-based on wire despite the earlier “new direct”
provenance label. New Sky falsifies the proposed scripted decoupled CH8 persistence rule. The
archived `WHYB-AFTER.ssproj` copy of `528E8B22` (`63302346…`) fails closed as MIXED. BLACKPINK/JUMP
and clean Where Have You Been remain uncaptured follow-ups, but more captures alone cannot clear the
current render-model gate. Do not mark scripted rendering complete.

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- `LaserDirector`/`laser_executor`/`midi_output` are the **scene-selection brain** that the new DMX
  renderer integrates with (it is what selects the autoloop today via IAC Bus 1) — NOT an off-limits
  separate rig. Do not break its existing decision logic or its MIDI-to-SoundSwitch output; during
  bring-up the DMX path may run ALONGSIDE the MIDI-select output (coexist) until validated, then the
  MIDI-select becomes optional. Tasks 1–3 still touch none of these files; only Task 4 integrates.
- Do **not** add blocking serial/file/socket I/O to `state_manager.py`'s push loop. DMX output runs
  out-of-process via the `dmx_pro.py` daemon + frame file; the bridge only does a non-blocking atomic
  frame-file write.
- Do **not** copy secrets, local IPs, device IDs, the `/dev/tty*` port, or the captured pcaps into
  the repo. The Enttec port is config/CLI only.
- Tasks 1–3 are **offline** (no hardware, no bridge runtime change). Task 4 (live wiring) is gated
  and must not be started without the Part A unknowns resolved and explicit operator approval.
- Reuse VLN `dmx_pro.py` as the output adapter — do not reimplement Enttec framing.

### Task 1 — `tools/ssfmt/export_ss_pack.py`: deterministic project → static pack exporter
Pure, read-only. Input: a SoundSwitch `.ssproj` dir + a fixture-map config. Output: a `pack.json`.
- Reuse `tools/ssfmt/re/analyze_ssfile_structure.parse_autoloop_structure`,
  `analyze_scripted_ssfile.parse_scripted_structure`, `parse_venue_cues.parse_venue_cues`,
  `analyze_static_looks`, `parse_autoloop_catalogs` — all already exist.
- Autoloop inventory bound is **up to 128 (4 banks × 32)**, not the count currently populated; iterate
  the catalogs (`parse_autoloop_catalogs`), do not hard-code 42.
- For each autoloop and scripted track: emit the timeline as a list of records
  `{tick|elapsed, raw_cue_reference, resolved_guid, reference_rule, kind}`.
  - Resolve `resolved_guid` per provenance: **one-based** for legacy files, **direct** for files
    proven new. If the file is **mixed/edited or provenance is unknown → mark the record
    `resolved_guid: null, status: "ambiguous"` and the whole look `exportable: false`** (fail
    closed). Never pick a convention silently.
- Emit a cue dictionary: `guid -> {name, groups: {"0x493": {ch:val}, "0x496": {ch:val}}}` from the
  Venue (the wire-verified per-cue patch) — **emit BOTH mirrored fixture groups** `0x493` and `0x496`
  (the rig has 2 DMX lasers that mirror each other; the renderer/output drives both).
- **Emit the scene/MIDI-note → autoloop binding** required for standalone selection: the map from
  each `LaserDirector` scene (and/or the MIDI note it sends on IAC Bus 1) to the `SSAutoLoopN.ssfile`
  it selects. This is NOT in the `.ssfile` bytes — source it from the SoundSwitch MIDI-mapping config
  and/or the catalog, and from `config/laser_director.json` scene names. If it cannot be resolved
  deterministically, emit it as `null` and mark affected looks `exportable: false` (fail closed).
- Tag each look `bridge_used: true/false` if it maps to a catalog index the bridge drives (optional
  metadata; do not drop non-used looks — `log` what is included).
- Inventory and FAIL CLOSED on: unsupported layouts, In-App Demo, `.ssa`/`.sspreset`/`recordable/`
  changes, profile mismatches, duplicate cue indices (reuse comparator semantics).
- Determinism: two runs over the same bytes produce byte-identical `pack.json`.

### Task 2 — `tools/ssfmt/ss_pack_renderer.py`: PURE-FUNCTION byte-exact frame renderer
The algorithm seam. No file/serial/subprocess I/O inside the core function.

**Port, don't reinvent.** The verified reference implementation is
`tools/ssfmt/re/layered_renderer.render_timeline(...)` run with `control_channels=(8,9,11)` and the
steady-loop second pass — that is what produced the 29/30 byte-exact result. Reuse/port its compose
logic exactly; the wire-regression test (Part D) is the pin that proves no divergence. Do NOT author
a fresh compositing algorithm from the prose below — the prose only explains intent.

- `render_frame(pack, *, look_id, phase, active_color_guid, prev_state) -> tuple[int]*19`
  (then mapped to 512 length per the fixture-map offset in Task 3).
- Compose the verified model:
  1. Select the active timeline record: the record with the greatest `time <= phase` after the
     project's own ordering, with the **steady-loop** convention — i.e. resolve the loop exactly as
     `layered_renderer` does, including its pre-roll handling. **Negative-tick pre-roll records
     (e.g. −143, −210) and the loop wrap are real**: do not naively `tick % 19200`; mirror
     `layered_renderer`'s `time>=0` filtering + inherited steady-loop initial state so the loop-start
     frame equals the prior cycle's end state.
  2. If `raw_cue_reference == 0` (clear): zero the **main** channels, keep `PERSIST_CHANNELS` from
     `prev_state`.
  3. Else overlay the resolved position cue's `0x493` patch onto `prev_state` (cue channels
     overwrite; absent channels persist from `prev_state`).
  4. **Color layer:** CH8/CH9 are "whichever cue most recently set them." A timeline cue MAY itself
     set CH8/CH9 (verified: SSAutoLoop52's own raw-27 GREEN / raw-22 RED records drive color via the
     persist rule) — in that case the timeline already supplies color and no external overlay is
     needed. `active_color_guid` (the bridge's independently selected color cue) is overlaid onto
     CH8/CH9 **only when supplied (non-null)**, for looks whose position cues leave CH8/CH9 open.
     Either way the persist rule on `{8,9}` is what carries color across position-only records.
- Constants: `PERSIST_CHANNELS = {8, 9, 11}` and the main-channel set are named module constants with
  a comment citing the wire verification + this spec; no inline magic numbers.

### Task 3 — `tools/ssfmt/ss_dmx_sender.py`: frame-file output adapter (reuse VLN)
- Vendor a copy of VLN `dmx_pro.py` into the repo as `tools/ssfmt/dmx_pro.py` (verbatim; record the
  source path + sha in a header comment) OR import it by configured path. Do NOT rewrite the Enttec
  framing.
- A thin `write_frame(frame_19, *, fixture_map)` that maps the 19 rendered channels onto the physical
  DMX start address of **BOTH mirrored laser fixtures** (0x493 and 0x496) within a single 512-byte
  buffer, then atomically writes `/tmp/vln_calib_frame.bin` via `dmx_pro.write_frame_file`. The two
  fixtures mirror each other, so both receive the rendered 19-channel block at their configured start
  addresses. The `dmx_pro.py daemon` (operator starts it with `--port`) pushes to the widget.
- Blackout helper that writes an all-zero frame (idle/stop/error).

### Task 4 — Live bridge wiring (GATED; do not implement until Part A unknowns are resolved + operator approves)
Specify-only here; this is the highest-risk task (physical laser output):
- **Integrate with `LaserDirector`, do not bypass it.** It already decides the scene (and which
  autoloop, via the IAC Bus 1 MIDI select). Feed its scene decision through the scene→autoloop map
  (Task 1) into the Task 2 renderer + Task 3 output, on a SEPARATE thread/cadence — never inside the
  200 Hz push loop's critical section. During bring-up the existing MIDI-select-to-SoundSwitch output
  may run alongside (coexist); once the DMX path is validated, MIDI-select becomes optional.
- Color: phase-1 takes color from the pack timeline (the color cue placed before the autoloop);
  phase-2 (separate, future) lets a bridge-owned laser color engine pick CH8/CH9 (mirrors the LED
  color engine) — out of scope for this spec beyond leaving `active_color_guid` as the injection seam.
- Blackout on: deck stop/unload, idle, watchdog-stale, and process exit.
- Behind an explicit config flag, default OFF.

## Part C — Invariants that MUST still hold (live safety)
- The 200 Hz push loop gains NO blocking I/O (serial/file/socket/subprocess). DMX leaves the process
  via atomic frame-file write + out-of-process daemon only.
- The existing MIDI laser path and all laser MIDI behavior are unchanged and share no mutable state
  with the new DMX path.
- Laser output fails safe: any idle/stop/error/watchdog path writes an all-zero frame; the operator's
  physical kill switch remains the ultimate failsafe (documented, not bypassed).
- The exporter fails closed: mixed/edited/ambiguous/unsupported looks are marked non-exportable, never
  rendered from a guessed convention.
- No secrets/ports/device IDs committed.

## Part D — Tests
- `tests/test_ss_pack_renderer.py` (pure-function, no files): feed synthetic pack records + prev_state
  and assert the composited 19-tuple — cover: position overlay, persist on raw-0 clear, color overlay,
  loop wrap, ambiguous-look guard.
- **Wire-regression test**: a committed fixture of the verified frames (e.g. SSAutoLoop52 raw-27 →
  `{1:41,3:48,4:14,6:117,7:145,8:21,11:214,15:159}`) asserts `render_frame` reproduces them
  byte-exact. (Use a small hand-authored pack subset, not the raw project bytes — keep proprietary
  project data out of the repo.)
- Exporter determinism test: two runs → identical `pack.json`; a mixed/edited look → `exportable:
  false`.
- Run: `python3 -m py_compile tools/ssfmt/*.py tools/ssfmt/re/*.py`,
  `python3 -m unittest discover tests`, and the four doc checks if docs change.

## Part E — Acceptance (definition of done)
- Tasks 1–3 implemented; Task 4 left specified-only (gated).
- `render_frame` reproduces the committed wire-verified frames byte-exact.
- Exporter is deterministic and fails closed on mixed/edited/unsupported looks.
- Full test suite green; no change to MIDI laser path; push-loop invariant intact.
- Docs updated per the `soundswitch_research` contract (`change_contracts.yml`), incl. this spec's
  status and a pointer from `soundswitch_exporter_renderer_full_plan.md`.

## When you finish
- Commit per task (`feat(ssfmt): ...`), reference this spec, and report: which tasks landed, the
  byte-exact test result, any look marked non-exportable and why, and the still-open Part A unknowns
  that gate Task 4.
