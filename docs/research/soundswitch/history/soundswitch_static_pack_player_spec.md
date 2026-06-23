---
doc_status: historical-draft
truth_level: code-byte-binary-and-wire-verified
last_verified_commit: 8ca5875
last_verified_date: 2026-06-21
validation_scope: implementation specification for a version-locked static pack/export/import/player; no runtime implementation or hardware validation
---

# Codex Implementation Spec - SoundSwitch Static Pack Exporter, Importer, and Laser Player

> **Preserved draft, superseded for implementation on 2026-06-21.** This file is
> intentionally retained, not removed. It predates closure of DDJ-800 Static
> Overrides, the exact 32-slot Static Look grammar, and learned MIDI-map
> add/remove behavior. Use the final
> `soundswitch_importer_exporter_player_codex_spec.md` in this directory.

## Part A - Context and root cause (verified; read, do not implement)

### Product boundary

- [confirmed] The first supported source is SoundSwitch 2.10.3, container v3,
  the maintainer's current project, fixture profile
  `b8ad2201b9e4c94696c898a7e8f6a5a9`, Universe 0, CH1-CH19.
- [confirmed] The bridge remains the deck, transport, timing, scene-policy, and
  safety authority. SoundSwitch remains an authoring source, not a required
  runtime process.
- [confirmed] This spec supports all current bridge-addressable sources: 19/19
  decoded IAC autoloop bindings and 32/32 current scripted files whose TrackMap
  paths exist. The inactive In-App Demo layout remains unsupported and visible.
- [confirmed] Status remains **SOFTWARE/WIRE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED**. This spec does not authorize live DMX output.
- [assumed] The first direct-DMX integration uses one bridge-selected owner deck,
  matching `runtime_invariants.md`'s current active-deck authority. Exact
  SoundSwitch crossfader parity is outside v1.
- [unknown] Physical Enttec serial port and fixture-connected safety state are
  operator inputs and cannot be inferred from project bytes.

### Closed reverse-engineering facts

- [confirmed] Physical CAF layout is little-endian. `AttributesCueMap` is
  `u32 version, u32 count, repeat(guid[16], u32 key)`. Timeline entries are
  `u32 version, u32 constant, i32 elapsed, u32 raw_reference`. The document
  trailer is 10 bytes. `SSAutoLoop13.ssfile` has a real physical count of 257;
  the former 256-record "continuation" was a three-byte-shift parser artifact.
- [confirmed] SoundSwitch 2.10.3 runtime resolves positive references as
  `stored_key = raw_reference - 1`; raw zero is clear/control. Evidence covers
  legacy A5 (14/14), legacy autoloops, and the 2026-06-21 cold-open newly
  authored Opalite track (3/3 one-based, 0/3 direct). Current writer bytes may
  still correspond directly to the cue selected in the editor; exporter v1
  must reproduce emitted runtime behavior, not editor intent.
- [confirmed] Cue patches are sparse, GUID-identified, Venue-gated, persistent
  updates into an initially zero buffer. CH8/CH9/CH11 are persistent control
  channels in the verified renderer; raw-zero clears the main layer while the
  control layer persists according to the existing reference algorithm.
- [confirmed] The 17-byte type-1 records are intensity `AttributeTrack` nodes.
  The current 19-channel profile has no intensity channel, so these nodes are
  retained in the pack but do not alter CH1-CH19.
- [confirmed] The current decoded MIDI registry has exactly 19 enabled IAC
  note bindings for autoloop files 3, 5, 18, 4, 13-17, 8, 46-48, 50, 52-55.
  Note 41 and channel-2 notes 0/1/2 have no current IAC bindings.
- [confirmed] SoundSwitch blackout is a boolean override applied on each refresh;
  release clears the flag and the current source state is rendered again. It is
  not a saved-frame restore stack.
- [confirmed] SoundSwitch two-playback mode blends deck buffers by live level/
  crossfader values. Four-playback mode selects the highest upfader and retains
  the prior owner on ties. V1 uses the bridge's existing active-deck authority
  and does not reproduce these optional composition modes.
- [confirmed] `.ssa`, `.sspreset`, other recordable registries, demo media, and
  Venue backup are inventoried and hashed. They are not loaded by the static
  `.ssfile` playback call chain used by v1. They remain visible and fail closed
  if a future supported version proves them render-affecting.

### Current bridge seams

- [confirmed] `StateManager` is the only `DeckState` writer
  (`state_manager.py:300`) and owns the 200 Hz loop
  (`state_manager.py:307`, `state_manager.py:3149`).
- [confirmed] `DeckState.scripted_id` and `OutputState.lighting_mode` already
  identify scripted/autoloop/idle state (`models.py:82`, `models.py:139`).
- [confirmed] `_update_lighting` and `_apply_lighting` own mode transitions
  (`state_manager.py:3040`, `state_manager.py:3087`).
- [confirmed] `LaserDirector` remains scene policy and `LaserSceneExecutor`
  remains accepted-scene/blackout/cooldown execution authority.
- [confirmed] `MidiOutput` already uses a bounded sender thread; existing MIDI
  behavior must remain the default.

## Part B - Tasks (implement exactly, in order)

### Absolute rules

- Do not import `tools/ssfmt/re/` from bridge runtime or production exporter
  modules. Port reviewed algorithms with typed models and independent tests.
- Do not read `~/Music/SoundSwitch` from the 200 Hz loop. Export is an offline
  command; runtime loads one immutable pack at startup or explicit reload.
- Do not perform serial, filesystem, socket, subprocess, sleep, retry, or
  blocking queue work in `_push_tick`.
- Do not modify the real SoundSwitch project. Exporter access is read-only and
  full-rescan based.
- Keep existing SoundSwitch/OS2L, MIDI laser, LED/Govee, Rekordbox, and runtime
  command behavior unchanged when the new mode is absent or disabled.
- Direct DMX mode is default-off, mutually exclusive with physical MIDI laser
  emission, and dry-run until a separate operator approval.
- Never commit local project paths, audio paths, serial ports, device IDs,
  captures, source project bytes, or live config.

### Task 0 - Extend change contracts before production code

Add a `soundswitch_static_pack_player` contract in
`docs/agents/change_contracts.yml` covering the new production modules, CLI,
config example, startup wiring, StateManager integration, status/commands,
tests, and required architecture/subsystem/setup docs. Its forbidden
assumptions must include version/profile expansion, passive-wire versus physical
hardware proof, and Enttec hard-kill last-frame behavior.

### Task 1 - Production source models and strict decoders

Create:

- `soundswitch_pack_models.py`
- `soundswitch_project_decoder.py`
- `tests/test_soundswitch_project_decoder.py`

Requirements:

1. Typed immutable models for source manifest, Venue cue/profile, catalog entry,
   autoloop, scripted track, TrackMap mapping, MIDI binding, diagnostics, and
   unsupported artifact.
2. Bounded counts/lengths, exact source offsets, exact EOF/trailer consumption,
   duplicate-key rejection, and unsupported-version rejection.
3. Physical CAF parsing only: no three-byte-shift compatibility representation.
4. Version-locked runtime reference resolution:
   `raw == 0 -> clear_control`; `raw > 0 -> stored key raw - 1`.
5. Full project-relative inventory before and after decode. Reject symlinks,
   source drift, disappearing files, exact identity conflicts, and unaccounted
   in-scope bytes.
6. Decode the known MIDI control map and derive note-to-autoloop binding from
   control path plus catalog file number. Never hard-code the current 19 rows.
7. Keep every unsupported/opaque artifact in the result. Only inactive artifacts
   may be unsupported in an exportable v1 pack.

### Task 2 - Deterministic static pack exporter and verifier

Create:

- `tools/export_soundswitch_pack.py`
- `soundswitch_pack.py`
- `soundswitch_pack_verifier.py`
- `tests/test_soundswitch_pack.py`

CLI contract:

```bash
python3 tools/export_soundswitch_pack.py \
  --project /path/to/project.ssproj \
  --output /path/to/new-pack-dir
```

Output artifacts:

- `manifest.json`
- `fixture_profile.json`
- `selection_map.json`
- `venue_cues.json`
- `autoloops/<file-number>.json`
- `scripted/<normalized-ssid>.json`
- `track_map.json`
- `import_report.json`

Requirements:

1. Stable relative-path ordering, source ordering for equal-time records, sorted
   diagnostics, canonical JSON, no timestamps in hashed content, and atomic
   publish to a new output directory.
2. Manifest includes generator commit/schema, project/version/profile IDs,
   every source path/size/SHA-256/parse status, every artifact hash, totals, and
   declared v1 scope.
3. Pack records retain raw bytes/fields, physical offsets, stored key, resolved
   GUID, cue source offsets, intensity nodes, and negative/clear classification.
4. Export pre-renders deterministic CH1-CH19 frames at every event boundary
   using the independently ported persistent-layer algorithm. Captures are
   verifier oracles, never frame inputs.
5. `soundswitch_pack_verifier.py` re-hashes every artifact and rejects one-byte
   mutation, missing/extra source, count mismatch, unsupported active binding,
   unresolved positive reference, cue/profile mismatch, or noncanonical order.
6. Two exports from identical bytes must compare byte-for-byte identical.

### Task 3 - Pure importer/player

Create:

- `soundswitch_pack_loader.py`
- `soundswitch_laser_player.py`
- `tests/test_soundswitch_laser_player.py`

Required pure seams:

```python
render_scripted_frame(track, elapsed_ms) -> tuple[int, ...]  # 19 bytes
render_autoloop_frame(loop, phase_tick) -> tuple[int, ...]  # 19 bytes
render_output_frame(selection, transport, blackout) -> tuple[int, ...]
```

Rules:

1. Scripted selection uses normalized SSID/scripted identity and current
   authoritative elapsed. Seek/backward seek/pause/resume/refire are history
   independent: recompute from the immutable event sequence.
2. Scripted stop/end/unload returns all zero.
3. Autoloop phase is derived from bridge phrase/beat authority; preserve
   pre-roll and steady-loop wrap exactly as the verified reference renderer.
4. Apply negative-time records when constructing the cycle-start state; preserve
   equal-time source order.
5. Apply sparse cues and raw-zero/control persistence exactly. Intensity nodes
   are retained but skipped only when the loaded profile declares no intensity
   channel.
6. Blackout is a stateless final mask. Releasing it renders the current elapsed/
   phase state, not a cached pre-blackout frame.
7. Unsupported selection, stale pack, missing SSID/note binding, or player error
   returns zero plus a structured diagnostic; never reuse the previous nonzero
   frame.

### Task 4 - Output backend abstraction without behavior drift

Create `laser_output_backend.py` with a nonblocking protocol for accepted scene,
blackout hold/release, frame submission, status, and shutdown.

Refactor `LaserSceneExecutor` so:

- the existing MIDI backend is the default adapter and preserves current calls,
  ordering, cooldown, role rotation, blackout owner reference counts, and tests;
- the direct-pack backend receives only scenes the executor actually accepts;
- scene-to-autoloop resolution uses the pack's decoded MIDI/control map plus the
  existing configured scene mapping;
- default/dry-run behavior produces no new physical output.

Adversarial guard: a rejected/cooldown-skipped MIDI scene must not advance the
direct player selection. Test this explicitly.

### Task 5 - Enttec sender worker

Create:

- `enttec_dmx_pro.py`
- `soundswitch_frame_sender.py`
- `tests/test_enttec_dmx_pro.py`
- `tests/test_soundswitch_frame_sender.py`

Port the proven Enttec USB Pro label-6 packet contract from
`/Users/bbui/virtuallasernode/calib/dmx_pro.py`; do not invoke it as a subprocess
and do not import by an external filesystem path.

Requirements:

1. Pure `build_dmx_packet(frame_512)` seam with start `0x7e`, label `6`,
   513-byte payload (`start_code + 512`), little-endian payload length, end
   `0xe7`.
2. One worker owns serial I/O. The hot path submits to a latest-frame-only,
   nonblocking bounded mailbox.
3. Expand CH1-CH19 into a 512-byte frame using the validated external fixture-map
   config. Do not infer physical addresses from names.
4. On idle, stale input, pack/player error, normal stop, SIGINT, or SIGTERM, push
   a physical zero packet before close.
5. Document and surface the Enttec Pro hard-kill hazard: widget firmware repeats
   the last frame after process death. A physical kill switch/power path remains
   required; software cannot claim fail-safe behavior for `kill -9` or host loss.

### Task 6 - Config, startup, StateManager, status, and commands

Add a tracked example config and validated loader. Suggested fields:

```json
{
  "enabled": false,
  "dry_run": true,
  "pack_path": "",
  "fixture_map_path": "",
  "output_backend": "none",
  "enttec_port": "",
  "frame_stale_timeout_ms": 250
}
```

Wire at startup in `__main__.py`; load/verify the pack before threads start.
`StateManager` may call only pure player methods and nonblocking frame submit.
Use existing `active_deck`, `DeckState.scripted_id`, `soundswitch_id`, elapsed,
lighting mode, beat/phrase state, and executor-approved scene selection. Do not
invent another deck or transport authority.

Add sanitized status for availability, enabled/dry-run, pack schema/hash, source
project hash, selected source, elapsed/phase, last frame hash, queue drops,
stale/error state, and blackout. Never expose absolute audio paths or serial
device details. Any enable/reload/output command is a separate runtime-command
contract change and must remain operator-gated; no implicit hot enable.

### Task 7 - Shadow verification before physical output

With output backend `none`, record rendered frame hashes and compare against the
frozen passive captures. Required regression oracles:

- A5 legacy scripted capture: 16/16;
- 2026-06-21 cold new Opalite capture: 3/3 one-based and 0/3 direct;
- existing New Sky, Opalite, TITANIUM oracle packs;
- autoloop files 5/18 exact captures and the legacy autoloop probe;
- all 19 current active MIDI bindings parse and select an exportable file;
- all 32 existing-path scripted files load and render without unresolved refs.

Physical output remains blocked until shadow results, code review, config review,
single-process bridge verification, fixture-map review, rollback procedure, and
explicit operator approval all pass.

## Part C - Invariants that MUST still hold (live safety)

- `StateManager` remains the only `DeckState` writer.
- Existing direct-reader authority/readiness and ANLZ-before-track-load ordering
  remain unchanged.
- The 200 Hz loop performs no blocking I/O and no project/pack/config parsing.
- Existing OS2L SoundSwitch mode works unchanged when direct-pack mode is off.
- Existing MIDI laser behavior is byte/order equivalent when the MIDI backend is
  selected.
- LED/Govee behavior and its worker ownership are unchanged.
- Emergency blackout beats manual override; blackout release renders current
  position; any error/stale state outputs zero.
- Exactly one sender owns the Enttec port. Exactly one bridge process is required.
- No hardware validation claim follows from parser tests or passive Art-Net.

## Part D - Tests and checks

Add focused unit tests for:

- physical 257-count parsing and 10-byte trailers;
- reference raw 0/1/positive bounds and one-based cold-new regression;
- negative time, equal-time order, steady-loop wrap, sparse persistence, clear,
  intensity-no-channel behavior, seek/pause/refire, and blackout release;
- all current catalog/MIDI/TrackMap active bindings;
- source drift, symlink, duplicate key, missing cue, unsupported active layout,
  noncanonical JSON, and one-byte verifier mutations;
- MIDI backend parity and rejected-scene non-advancement;
- latest-frame mailbox overflow/staleness and zero-on-error/shutdown;
- Enttec packet bytes without opening serial hardware.

Run every contract-required test plus:

```bash
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

No test may read or mutate the live SoundSwitch project or open MIDI/serial/DMX.

## Part E - Acceptance

- [ ] Contract added before production code.
- [ ] Complete stable project rescan; no hidden fuzzy discovery.
- [ ] 42/42 current autoloops and 44/45 scripted artifacts accounted for;
      unsupported demo visible and inactive.
- [ ] 19/19 active autoloop bindings and 32/32 existing-path scripts exportable.
- [ ] Repeated exports byte-identical; independent verifier rejects adversarial
      mutations.
- [ ] Pure player passes every frozen byte/wire oracle without capture-seeded
      production state.
- [ ] Default-off/dry-run startup produces no MIDI or DMX behavior change.
- [ ] Existing MIDI backend parity passes.
- [ ] No blocking work enters `_push_tick`.
- [ ] All error, stale, idle, stop, unload, shutdown, and blackout paths produce
      zero.
- [ ] Shadow mode is reviewed before any physical-output approval request.
- [ ] Status remains SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## When you finish

Report changed files, pack schema, source/pack hashes used in tests, exact test
and docs-check results, unsupported artifacts, shadow parity totals, and an
adversarial self-review. Include a plain-language operator summary covering what
direct-pack mode would do live, what existing SoundSwitch/MIDI/LED behavior stays
unchanged, healthy logs/status, failure watchpoints, what is software/wire-only,
and the exact approval commands required before any restart, enable, Enttec port
open, or fixture-connected test.
