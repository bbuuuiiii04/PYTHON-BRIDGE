---
doc_status: active-ready-for-implementation
truth_level: code-byte-binary-and-wire-verified
last_verified_commit: 8ca5875
last_verified_date: 2026-06-21
validation_scope: implementation specification for a SoundSwitch 2.10.3 current-profile static exporter/importer/player; no runtime implementation or hardware validation
---

# Codex Implementation Spec - SoundSwitch Importer, Exporter, and Bridge-Native Laser Player

## Authority, canonical source identity, and corrections (read first)

**This file is the only active implementation authority.**
`docs/research/soundswitch/soundswitch_static_pack_player_spec.md` is
`historical-draft` / superseded and MUST NOT be cited as implementation
authority; it predates the DDJ Static Override closure, the exact 32-slot Static
Look grammar, and learned-MIDI add/remove behavior.

**Correction provenance (2026-06-21).** This spec was edited after its
`last_verified_commit` stamp (`8ca5875`). The decode foundation was independently
re-verified by the pack-generation proof gate
(`tools/prove_soundswitch_pack_generation.py`); its locally generated
`artifacts/soundswitch_pack_generation_proof/latest.json` reported
`final_verdict: PASS_IMPLEMENTATION_MAY_BEGIN` at repo HEAD `cc526eb`. The proof
reports are generated locally and are gitignored (never committed); regenerate the
gate to reproduce the verdict. The committer MUST re-stamp `last_verified_commit`
to the commit that lands these edits; do not fake provenance.

### Canonical bounded source identity (pinned)

| Field | Canonical value |
| --- | --- |
| Project UUID | `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}` |
| Venue GUID (RAVE) | `b8ad2201b9e4c94696c898a7e8f6a5a9` |
| SoundSwitch version | `2.10.3` (container v3) |
| Universe / channels | Universe 0, CH1-CH19, 19-channel no-intensity profile |

**Project UUID pinning is mandatory.** The exporter, verifier, and proof gate
MUST reject any project whose UUID differs from the canonical UUID **even if the
RAVE Venue GUID matches**. A mutation/scratch corpus
(`{E34F6DCD-EBB9-4088-BD28-7BC0272D011A}`) shares the same RAVE GUID; the Venue
GUID alone is NOT sufficient to authorize export. This is enforced and proven by
`tools/prove_soundswitch_pack_generation.py` check `F1-reject-wrong-uuid-same-venue`.

### Attribute-cue count is a split, not a bare "232"

The current Venue parses to **232 fixture-payload (render-bearing) Attribute Cues
plus 1 minimal default catalog-tail record = 233 total parsed Venue records**.

- Only the 232 fixture-payload cues are export/render-bearing.
- The +1 catalog-tail/default record (`record_kind == "minimal_default_catalog_tail"`)
  MUST be classified deliberately, MUST NOT crash export/player, and MUST NOT be
  confused with an active render-bearing cue.
- All acceptance gates assert the **split (232 + 1 = 233)**, never a bare "232 cues."

### Multi-deck / crossfade scope (intentionally out of scope)

V1 does not emulate SoundSwitch's live multi-deck mixer/crossfader selection
logic. This is intentional: SoundSwitch is used only as an authoring/export
source. At runtime, the bridge's existing Rekordbox active-deck authority selects
the current scripted track, Autoloop, or manual/static override. The pack player
reproduces exported CH1-CH19 behavior for that selected source.

### VirtualLaserNode (VLN) Enttec transport evidence (scope-limited)

VLN evidence (`~/virtuallasernode/calib/dmx_pro.py`) may be cited as prior proof
that Python -> Enttec DMX USB Pro -> fixture transport is viable in the VLN
context. It does **not** prove SoundSwitch pack semantic correctness, exported
CH1-CH19 frame parity, bridge-runtime pack behavior, or show readiness. The
SoundSwitch pack implementation must still prove exported CH1-CH19 parity (the
pack-generation proof gate) before any physical enable. See Task 6.

### Test-suite reporting honesty

Implementation agents MUST report exact current test output and MUST NOT convert
it into "all passed." For reference, a prior full-suite run was
`Ran 1866 ... FAILED (failures=1, skipped=3, expected failures=1)`, where the one
failure is an unrelated order-dependent `test_runtime_status` logging-isolation
flake (passes in isolation). That flake neither validates nor invalidates the
SoundSwitch RE. The targeted SoundSwitch parser/inventory tests
(`tests.test_ssfile_reference_convention`, `tests.test_inventory_project_artifacts`,
`tests.test_static_looks`, `tests.test_venue_fixture_profile`,
`tests.test_prove_soundswitch_pack_generation`) pass deterministically.

## Part A - Context and root cause (verified; read, do not implement)

### Product outcome

- [confirmed] SoundSwitch remains the authoring tool. A complete read-only
  Export converts saved Autoloops, scripted tracks, Attribute Cues, Static
  Looks, catalogs, TrackMap data, and learned MIDI mappings into an immutable
  bridge pack. SoundSwitch is not required at runtime.
- [confirmed] The first supported source is SoundSwitch 2.10.3, project/container
  v3, primary Venue `RAVE` GUID
  `b8ad2201b9e4c94696c898a7e8f6a5a9`, Universe 0 CH1-CH19.
- [confirmed] The closure authority is
  `docs/research/soundswitch/soundswitch_re_closure_report.md`, whose verdict is
  `RE COMPLETE: READY FOR PERFECT EXPORTER SPEC`.
- [confirmed] Status remains **SOFTWARE/WIRE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED**. This spec does not itself authorize a restart, MIDI
  input/output change, serial port open, Enttec output, or fixture-connected
  test.
- [assumed] V1 uses the bridge's current single-active-deck authority instead of
  emulating SoundSwitch's optional two/four-deck composition.
- [unknown] The physical Enttec port, connected fixture state, kill path, and
  optical safety remain operator inputs and require later hardware validation.

### Closed source behavior

- [confirmed] Physical cue maps are `u32 version, u32 count,
  repeat(guid[16], u32 stored_key)`. Timeline entries are
  `<u32 version, u32 constant, i32 time, u32 raw_reference>`. The trailer is 10
  bytes. The old shifted parser is obsolete.
- [confirmed] Version-locked emitted behavior is `raw == 0 -> clear/control` and
  `raw > 0 -> stored_key = raw - 1`. This is wire-proven for legacy A5, legacy
  Autoloops, and a cold-open newly authored scripted track.
- [confirmed] Editor cue intent can differ from emitted runtime behavior. The
  pack reproduces emitted behavior from current saved bytes; it does not
  silently repair the editor selection.
- [confirmed] All 42 current Autoloops parse. Nineteen learned IAC controls
  resolve to parsed files: 18 normal bridge selections plus file 3 for the
  current momentary blackout target.
- [confirmed] Thirty-two current scripted files have existing TrackMap paths;
  all 32 use supported layouts and reference no missing cue GUID.
- [confirmed] The current Venue contains 232 parsed Attribute Cues; the active
  Autoloop/script union references 166, with zero missing.
- [confirmed] The primary Venue has one exact GUID-keyed 32-slot `StaticLooks`
  collection. Version-5 slot records contain intensity, strobe, colour,
  position, and generic attribute maps.
- [confirmed] Four current DDJ-800 note mappings select `StaticOverride` slots
  8, 16, 17, and 24. Note-on holds the direct zero-based slot; matching note-off
  releases it and rerenders the current base source.
- [confirmed] Channel-2 safe/transition/emergency notes are intentionally not
  learned in SoundSwitch. Breakdown note 1 and inactive post-drop note 41 are
  also unlearned. The implementation must not invent pack targets for them.
- [confirmed] The learned-map recordable is decoded. New-map completion,
  unmap, clear-all, and device/collection removal all rewrite the complete
  registry. Full rescans discover new or removed note mappings.
- [confirmed] Type-1 17-byte entries are intensity nodes. The current profile
  has no intensity channel, so they are retained but have no CH1-CH19 effect.
- [confirmed] Static Override cache values replace matching base attributes.
  Blackout/emergency is a later safety mask. Release rerenders current state;
  neither feature restores a cached frame.

### Current bridge seams

- [confirmed] `StateManager` is the central state owner and runs the 200 Hz loop
  (`state_manager.py:300`, `state_manager.py:307`, `state_manager.py:3149`).
- [confirmed] `DeckState.scripted_id` identifies scripted state and
  `OutputState.lighting_mode` tracks scripted/autoloop/idle
  (`models.py:83`, `models.py:139`; line numbers re-verified at HEAD `cc526eb`).
- [confirmed] `_update_lighting` derives mode from current authoritative state,
  and `_apply_lighting` owns transitions (`state_manager.py:3035`,
  `state_manager.py:3087`).
- [confirmed] `LaserDirector` owns policy. `LaserSceneExecutor` owns accepted
  scene execution, cooldown/role rotation, and reference-counted blackout masks
  (`laser_executor.py:31`, `laser_executor.py:62`).
- [confirmed] `LaserSceneExecutor` currently depends directly on `MidiOutput`
  (`laser_executor.py:34-45`). Existing MIDI behavior must remain the default.
- [confirmed] Laser configuration performs file I/O only at startup and must not
  run from `_push_tick` (`laser_config.py:1-19`).
- [confirmed] Runtime status already accepts sanitized provider snapshots
  (`runtime_status.py:98-119`).

## Part B - Tasks (implement exactly, in order)

### Absolute rules

- Do not import production behavior from `tools/ssfmt/re/` into bridge
  runtime/exporter modules. Port reviewed algorithms into typed production modules
  and test them independently. This binds production code only; the Task 0.5 proof
  gate and other research tooling MAY import the `tools/ssfmt/re/` parsers as
  evidence.
- Do not write to or mutate any SoundSwitch project. Export is read-only.
- Do not read project/pack/config files or perform blocking I/O in the 200 Hz
  loop.
- Do not modify ignored live config. Add tracked examples only.
- Preserve current OS2L, MIDI laser, Rekordbox reader, LED/Govee, command, and
  status behavior when pack mode is absent or disabled.
- Pack mode is default-off and dry-run. Physical MIDI laser output and direct
  DMX output are mutually exclusive.
- Do not open a MIDI input, MIDI output, serial, Art-Net, or Enttec device during
  unit tests.
- Never commit project/audio absolute paths, device IDs, live port names,
  captures, source project bytes, secrets, or ignored configs.
- A failure, stale source, stale controller, missing selection, verifier error,
  or unsupported active input must produce zero plus a structured diagnostic;
  never retain an old nonzero frame.

### Task 0 - Add the production change contract first

Extend `docs/agents/change_contracts.yml` with a
`soundswitch_pack_player` contract covering every new production module, CLI,
tracked config example, startup seam, StateManager/executor/status integration,
tests, and required subsystem/architecture/setup docs.

Forbidden assumptions must include:

- other SoundSwitch versions/profiles behave like 2.10.3;
- a project that matches the RAVE Venue GUID is automatically the right project
  (the canonical project UUID must also match; a scratch corpus shares the GUID);
- passive Art-Net proves physical fixtures;
- display name, file order, or cue index is durable identity;
- absent channel-2 utility notes imply hidden SoundSwitch targets;
- a missing MIDI note-off is safe;
- Enttec process death clears its last frame.

### Task 0.5 - SoundSwitch pack-generation verification gate

A reproducible pre-implementation proof gate already exists and MUST gate
implementation:

```bash
python3 tools/prove_soundswitch_pack_generation.py \
  --project ~/Music/SoundSwitch/default.ssproj \
  --output-dir artifacts/soundswitch_pack_generation_proof
```

Artifacts (generated locally; gitignored; never committed):

- `artifacts/soundswitch_pack_generation_proof/latest.json` (machine-readable);
- `artifacts/soundswitch_pack_generation_proof/latest.md` (human-readable).

These reports are environment-specific — they record the operator's absolute
project path, a generation timestamp, and the repo HEAD at run time — so they are
**not** committed (`.gitignore` excludes
`artifacts/soundswitch_pack_generation_proof/latest.*`). Each implementing agent
MUST regenerate them on its own machine and paste the exact JSON/Markdown paths,
the `final_verdict`, and the PASS/FAIL/INCOMPLETE totals into its implementation
handoff (see Part E). A committed or copied-in report is never accepted as proof.

Pure-logic coverage runs in CI without the live project:
`tests.test_prove_soundswitch_pack_generation`.

Rules:

- Exporter/importer/player implementation MUST NOT begin unless the proof gate
  `final_verdict` is `PASS_IMPLEMENTATION_MAY_BEGIN`.
- If `final_verdict` is `PASS_WITH_SPEC_CORRECTIONS_ONLY`, only spec/proof
  corrections may be made before the gate is rerun.
- If `final_verdict` is `FAIL_DO_NOT_IMPLEMENT` or `INCOMPLETE_PROOF_BLOCKER`,
  behavior implementation is blocked until the named blocker is resolved.
- The proof gate MUST be rerun after: SoundSwitch project edits, source-identity
  changes, parser changes, pack-schema changes, verifier changes, or any
  implementation change that touches SoundSwitch-derived semantics.
- The proof gate proves software/wire decode only. It does **not** validate
  Enttec/fixture physical behavior.
- Two proof checks are intentionally deferred until the code they exercise exists,
  then become mandatory acceptance gates: `F9-pack-one-byte-mutation` (one-byte
  pack-artifact mutation rejection) gates **Task 2** (exporter/pack/verifier) and
  the Task 8 hardware gate; `F10-active-cc-override` (active CC/pitch
  render-control export failure) gates **Task 4** (learned-control MIDI input
  adapter) and the Task 8 hardware gate.

### Task 1 - Production source models and strict project decoder

Create:

- `soundswitch_pack_models.py`
- `soundswitch_project_decoder.py`
- `tests/test_soundswitch_project_decoder.py`

Use frozen/immutable models for:

- project/version/source inventory;
- Venue/profile/channel map and Attribute Cues;
- all 32 Static Looks and their five value maps;
- Autoloop catalogs/category order and `.ssfile` records;
- scripted `.ssfile` records and TrackMap identities/locators;
- learned device/collection/MIDI/control-path bindings;
- unsupported/opaque artifacts and diagnostics.

Decoder requirements:

0. **Source-identity gate first.** Read `<project>/.ssproj` and reject unless the
   project UUID equals `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}` AND the version is
   `2.10.3` AND the primary Venue GUID equals `b8ad2201b9e4c94696c898a7e8f6a5a9`.
   A matching RAVE Venue GUID with a different project UUID (the scratch corpus)
   MUST be rejected. No decode proceeds until identity passes.
1. Bound every count/string/offset; consume exact trailers/EOF; retain source
   offsets; reject duplicate keys and unsupported versions.
1a. Decode the Venue Attribute Cue bank as **232 fixture-payload render cues + 1
   minimal default catalog-tail record (233 total parsed records)**. Retain the
   catalog-tail record classified distinctly; it is never a render-bearing cue,
   must not crash decode, and must not be counted as one of the 232.
2. Use only the corrected physical CAF grammar. Do not provide shifted-parser
   compatibility.
3. Resolve positive references with the explicit 2.10.3 `raw-1` rule after the
   version/profile gate. Raw zero remains a distinct clear/control record.
4. Select the unique Static Looks collection by primary Venue GUID, require
   version 1/count 32, and retain every version-5 slot including empty slots.
5. Decode the complete learned MIDI map. Preserve all devices/message types,
   enabled flags, collection IDs, feedback bytes, and control paths.
6. Resolve `AutoLoopsPlayAutoloopN` through current catalog category order and
   `StaticOverrideN` directly to zero-based slot `N`. Never hard-code the
   current notes/files/slots.
7. Reject an enabled event collision when one device/message/channel/data-byte
   maps to multiple render-affecting controls unless a later reviewed rule
   explicitly supports that composition.
8. Permit current intentionally unmapped bridge utility scenes as no-target
   policy inputs. Do not classify them as missing project artifacts.
9. Perform full project-relative inventory before decode and re-stat/re-hash
   afterward. Reject symlinks, disappearing/extra files, concurrent mutation,
   case collisions, and identity conflicts.
10. Retain every opaque artifact in diagnostics. It may be inactive; it may not
    disappear from the report.

### Task 2 - Deterministic exporter, pack, and independent verifier

Create:

- `tools/export_soundswitch_pack.py`
- `soundswitch_pack.py`
- `soundswitch_pack_verifier.py`
- `tests/test_soundswitch_pack.py`

CLI:

```bash
python3 tools/export_soundswitch_pack.py \
  --project /path/to/project.ssproj \
  --output /path/to/new-pack-dir
```

Canonical pack artifacts:

- `manifest.json`
- `fixture_profile.json`
- `venue_cues.json`
- `static_looks.json`
- `midi_mappings.json`
- `selection_map.json`
- `track_map.json`
- `autoloops/<file-number>.json`
- `scripted/<normalized-ssid>.json`
- `import_report.json`

Requirements:

1. Canonical JSON, stable relative-path ordering, stable diagnostics, preserved
   equal-time source order, no timestamps inside hashed content, and atomic
   publish to a new directory.
2. Manifest records schema/generator commit, the **pinned canonical project UUID
   `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}`**, project/version/Venue/profile,
   every source path/size/hash/status, every artifact hash, supported boundary,
   the active-cue union SHA-256
   `88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2`
   (166 active referenced GUIDs from the 19 IAC autoloops + 32 existing-path
   scripted), and active/inactive totals.
3. Pack records retain raw fields, source offsets, raw/stored references,
   resolved GUIDs, negative/clear classification, intensity nodes, and unused
   static maps. Do not retain only pre-rendered frames.
4. Include all **232 fixture-payload Attribute Cues + the 1 default catalog-tail
   record (233 total)**, all 32 Static Looks, all learned mappings, all 42
   Autoloops, and all scripted inventory rows. The catalog-tail record is tagged
   distinctly and never counted among the 232. Active unsupported rows block
   publication; inactive unsupported rows remain reported.
5. Generate explicit crosswalks for current bridge scenes, manual blackout,
   IAC selections, and DDJ Static Overrides. Mark unlearned utility events as
   `no_project_target`; do not invent a target.
6. Pre-render CH1-CH19 at event boundaries and static slots using the production
   pure renderer. Captures remain verifier oracles, never pack input.
7. Refuse a stale cue reference and report source file, physical record offset,
   elapsed/tick, raw reference, candidate key, and missing GUID. Remediation is
   to remove/replace the placement in SoundSwitch, save, and re-export.
8. The independent verifier re-hashes every artifact and rejects: a one-byte
   mutation, missing/extra artifact, count mismatch (including a Venue total that
   is not 232 render cues + 1 catalog-tail), noncanonical ordering, unresolved
   active selection, **a project UUID other than the canonical UUID (even when the
   RAVE Venue GUID matches)**, a drifted active-cue union SHA-256, source/profile
   mismatch, or unsupported active message semantics.
9. Two exports from identical saved bytes must be byte-for-byte identical.

### Task 3 - Pure pack loader and renderer/player

Create:

- `soundswitch_pack_loader.py`
- `soundswitch_laser_player.py`
- `tests/test_soundswitch_laser_player.py`

Required pure seams:

```python
render_scripted_frame(track, elapsed_ms) -> tuple[int, ...]
render_autoloop_frame(loop, phase_tick) -> tuple[int, ...]
render_static_look_frame(static_look) -> tuple[int, ...]
resolve_frame(base, static_override, blackout, emergency) -> tuple[int, ...]
```

Rules:

1. Outputs are exactly 19 integers in 0..255.
2. Script selection uses normalized SSID and authoritative elapsed. Seek,
   backward seek, pause/resume, and refire recompute from immutable events.
3. Stop/end/unload and missing/stale/errored source return zero.
4. Autoloop phase uses bridge beat/phrase authority. Apply signed pre-roll to
   cycle-start state, preserve equal-time stored order, and wrap exactly.
5. Sparse cue application updates only present channels. Raw zero applies the
   verified source clear rule. Retain intensity nodes; skip their output only
   because the loaded profile explicitly declares no intensity channel.
6. Static rendering applies the current profile's generic attributes and
   retains intensity/strobe/colour/position fields for verification/future
   gated profiles.
7. Precedence is emergency/blackout zero mask, then held Static Override, then
   selected scripted/Autoloop base, then zero.
8. Releasing blackout or Static Override recomputes current base position. Do
   not cache a pre-override frame.
9. A new held Static Override replaces the prior active index. Releasing an old
   non-current note must not clear the new slot.
10. Pack reload clears every held controller/blackout selection and outputs
    zero until fresh authoritative state arrives.

### Task 4 - Learned-control MIDI input adapter

Create:

- `soundswitch_midi_input.py`
- `tests/test_soundswitch_midi_input.py`

Requirements:

1. One optional worker owns MIDI input. Startup configuration maps sanitized
   runtime port aliases to pack device identities; never publish local port
   names in status.
2. Normalize note-on velocity zero to note-off. Match exact device identity,
   message type, zero-based channel, and data byte from the pack.
3. V1 render-affecting control activation supports the current note semantics.
   If a future active Static Override/Autoloop is learned to CC or pitch bend,
   export fails with the exact action: relearn it to a note-capable control or
   extend/validate that message semantic before use.
4. Deliver normalized events through a bounded nonblocking mailbox/snapshot.
   No MIDI API call enters `_push_tick`.
5. Static Override note-on selects direct slot; matching note-off releases only
   if still current. Repeated note-on is idempotent.
6. Device disconnect, worker failure, stale held input, shutdown, pack reload,
   and explicit panic clear held state and force zero before normal base output
   may resume.
7. Non-render controls such as current `CueBeat` remain inventoried but do not
   mutate the laser player.

### Task 5 - Output backend abstraction with MIDI parity

Create `laser_output_backend.py`. Refactor `LaserSceneExecutor` to depend on the
backend protocol rather than directly on `MidiOutput`.

Protocol responsibilities:

- accepted scene trigger;
- blackout hold/release by owner;
- frame/selection submission;
- status;
- reset/shutdown.

Rules:

1. Existing MIDI adapter remains default and preserves exact calls, pulse/hold
   ordering, cooldown gates, random role-bank rotation, blackout owner reference
   counts, and tests.
2. Pack backend receives only decisions the executor accepted. A gated,
   cooldown-skipped, missing, or rejected scene must not advance selection.
3. Resolve accepted scene MIDI identity against pack learned mappings. An
   explicitly unlearned scene is a no-op selection, matching current
   SoundSwitch. Safety stop/stale/emergency is handled by the independent final
   zero mask.
4. Current breakdown note 1 remains no-op underneath note-0 mask; current
   channel-2 utilities remain no-target until the project actually learns them.
5. Default/dry-run/none backend produces no new physical output.

### Task 6 - Direct frame sender and Enttec protocol (software only first)

Create:

- `enttec_dmx_pro.py`
- `soundswitch_frame_sender.py`
- `tests/test_enttec_dmx_pro.py`
- `tests/test_soundswitch_frame_sender.py`

**Reference transport (mandatory): existing VirtualLaserNode DMX Pro.** The
implementation MUST use the existing proven VLN DMX Pro transport
`~/virtuallasernode/calib/dmx_pro.py` as the reference implementation for Enttec
packet framing and serial behavior (its `build_dmx_packet` and unit test
`~/virtuallasernode/calib/test_dmx_pro.py` are the known-good contract:
`0x7E | label 6 | len_lsb | len_msb | start_code(0x00)+512 | 0xE7`, length 513
little-endian; blackout `7E 06 01 02 00 <512x00> E7`, 518 bytes; on every
catchable exit a real zero packet is pushed before close).

- The production bridge module `enttec_dmx_pro.py` MAY port/adapt the proven VLN
  logic, but MUST preserve the known-good packet semantics. Do NOT import VLN as
  a runtime dependency, do NOT modify VLN, and do NOT re-derive the framing
  from scratch while VLN is available.
- Any divergence from the VLN implementation MUST be justified in the
  implementation report and covered by tests.
- VLN evidence proves Python -> Enttec DMX Pro -> fixture transport viability in
  the VLN context. It does NOT prove SoundSwitch pack semantic correctness,
  exported CH1-CH19 parity, bridge-runtime safety, or show readiness. SoundSwitch
  pack semantic proof comes ONLY from the pack-generation proof gate (Task 0.5),
  never from VLN.
- If `~/virtuallasernode` is unavailable to the implementing agent, Task 6 is
  blocked pending a Brandon-provided path or source excerpt; it must NOT proceed
  as a from-scratch Enttec implementation with the blocker unacknowledged.

Requirements:

1. Pure `build_dmx_packet(frame_512)` preserves the VLN-proven framing: start
   `0x7e`, label 6, 513-byte payload (`start_code + 512`), little-endian payload
   length, and end `0xe7`. Unit tests assert byte equivalence with the VLN
   reference packet (or justify any intentional difference).
2. One worker owns serial I/O. The hot path submits latest-frame-only into a
   bounded nonblocking mailbox.
3. Expand pack CH1-CH19 into the reviewed fixture-map output. Do not infer
   physical addresses from names.
4. Idle, stale input, source/player/verifier error, normal stop, SIGINT,
   SIGTERM, or sender shutdown requests a zero packet before close (matching the
   VLN catchable-exit blackout behavior).
5. Surface the hard-kill limitation, reproduced verbatim from VLN's verified
   behavior: the Enttec Pro firmware autonomously repeats the last frame, so a
   `kill -9`/host-death leaves the lasers stuck on the last frame, NOT dark.
   Software cannot claim fail-safe `kill -9`; a physical kill/power path remains
   the true failsafe.
6. This task initially stops at packet/unit/loopback tests. No serial/Enttec/
   hardware port is opened during unit tests. Opening real serial hardware remains
   a later explicit operator gate.

Task 6 acceptance — the implementation agent MUST report:

- the exact VLN transport source file inspected (`~/virtuallasernode/calib/dmx_pro.py`);
- a packet-framing comparison between VLN and the new `enttec_dmx_pro.py`;
- tests proving packet byte equivalence (or justified intentional differences);
- confirmation that no serial/Enttec/hardware port was opened during unit tests;
- confirmation that SoundSwitch pack semantic proof still comes from the
  pack-generation proof gate (Task 0.5), not from VLN.

### Task 7 - Config, startup, StateManager, status, and commands

Create a tracked `config/soundswitch_pack_player.example.json` and validated
loader. Minimum fields:

```json
{
  "enabled": false,
  "dry_run": true,
  "pack_path": "",
  "output_backend": "none",
  "fixture_map_path": "",
  "midi_input_aliases": {},
  "enttec_port": "",
  "frame_stale_timeout_ms": 250,
  "controller_hold_timeout_ms": 2000
}
```

Requirements:

1. Load and verify pack/config before worker threads start in `__main__.py`.
2. `StateManager` may call only pure player/controller methods and nonblocking
   frame submission. Reuse `active_deck`, `DeckState.scripted_id`,
   `TrackMetadata.soundswitch_id`, current elapsed/playing, lighting mode,
   beat/phrase state, and executor-accepted selection. Do not create a second
   deck/transport authority.
3. Every transition path—scripted/autoloop/idle, deck change, track load,
   stop/stale, config disable, pack reload, worker error, and shutdown—clears
   incompatible pending/held state and resolves a safe frame.
4. Status is sanitized: availability, enabled/dry-run, pack schema/hash,
   source-project hash, supported boundary, current source identity, elapsed/
   phase, held static slot, blackout owners, last-frame hash, mailbox drops,
   MIDI-input health, stale/error state. Never expose audio paths, device names,
   or serial details.
5. No implicit hot enable. Any enable/reload/backend command must follow the
   runtime-command change contract, validate first, and require an explicit
   operator action. Invalid reload keeps the old verified pack disabled or
   forces zero; it never partially swaps state.

### Task 8 - Offline and shadow verification gates

Before any physical output:

0. Re-run the Task 0.5 pack-generation proof gate and require
   `final_verdict: PASS_IMPLEMENTATION_MAY_BEGIN`; confirm the pinned project UUID
   `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}` and the active-cue union SHA-256
   `88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2`. Complete
   the two deferred proof checks here now that the pack/verifier exist:
   `F9-pack-one-byte-mutation` and `F10-active-cc-override`.
1. Export the frozen current-project fixture corpus twice and require identical
   bytes.
2. Independently verify every pack artifact and cross-reference; reject any
   project UUID other than the canonical UUID even when the RAVE Venue GUID matches.
3. Require current totals: 42/42 Autoloops parsed; 44/45 scripted parsed with
   inactive demo visible; 19/19 IAC bindings resolved; 32/32 existing-path
   scripts exportable; **232 fixture-payload render cues + 1 default catalog-tail
   record = 233 total parsed Venue records**; 166 active referenced cues
   (19 IAC autoloops + 32 existing-path scripted) with zero missing and union
   SHA-256 `88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2`;
   32/32 primary Static Looks; four/four DDJ overrides; zero learned-event
   collisions.
4. Replay A5 16/16, the cold new-track 3/3 one-based/0 direct discriminator,
   legacy Autoloop discriminator, file-5/file-18 exact cases, and existing
   transport oracles without capture-seeded production state.
5. Add static tests for slots 8/16/17/24 and controlled slot-7 create/edit.
6. Run pack backend with physical backend `none`; log only frame hashes and
   compare to independent expected output.
7. Obtain code review, config review, adversarial review, rollback plan, and
   single-process bridge verification before requesting a live gate.

### Task 9 - Explicit live/hardware gate (do not execute automatically)

Physical validation requires all prior acceptance items plus explicit operator
approval for exact commands. The handoff must name:

- whether fixtures are disconnected or connected;
- selected output backend and port alias;
- zero-frame preflight and physical kill method;
- bridge stop/start command and rollback command;
- single-process verification using `rbss-bridge-verify` after restart;
- first safe OFF/static test, then one controlled Autoloop, scripted track, DDJ
  override press/release, blackout press/release, disconnect, and shutdown;
- logs/status/physical behavior that constitute pass/fail.

Do not infer approval from implementation completion.

## Part F - Mandatory hardening requirements

### Must add before implementation

**F-1. Exact scripted/Autoloop timing & phase contract.** Define and test:
elapsed units (milliseconds, integer) and Autoloop phase units (bridge
beat/phrase ticks); steady-loop wrap math; equal-time record ordering (stored
source order is the deterministic tie-break); signed negative pre-roll applied to
cycle-start state before time zero; seek/backward-seek/pause/resume/refire as
history-independent recomputation from immutable events; stop/end/unload -> zero.
Bridge beat/phrase/BPM authority is the only phase source; on stale or missing
beat/track state the player resolves zero plus a diagnostic, never a guessed phase.

**F-2. Rekordbox -> SoundSwitch identity failure rules.** Each of the following
resolves to zero output plus a structured diagnostic, never a guess: missing or
duplicate `soundswitch_id`; no matching scripted pack row for the active
`soundswitch_id`; unsupported active layout; track metadata not ready; track
change; elapsed discontinuity/jump beyond tolerance; stale or ambiguous active-deck
authority. Identity is normalized SSID, cross-validated; the player never
fuzzy-matches the filesystem.

**F-3. Bridge scene/control crosswalk (classify every current control).** Every
current bridge control MUST be classified as exactly one of `pack_selection`,
`static_override`, `blackout_mask`, `bridge_owned_safety`, `no_project_target`,
`inactive_report_only`, or `unsupported_fail_export`:

| Bridge control | MIDI | Classification |
| --- | --- | --- |
| groove / buildup / drop autoloops | IAC notes 32, 64, 96-111 | `pack_selection` (19 IAC autoloops) |
| DDJ static overrides | CH7 n106, CH10 n122/n123/n127 | `static_override` (slots 16/24/8/17) |
| momentary blackout | CH1 note 0 (file 3) | `blackout_mask` |
| safe/static | CH2 note 0 | `bridge_owned_safety` |
| transition | CH2 note 1 | `bridge_owned_safety` |
| emergency | CH2 note 2 | `bridge_owned_safety` |
| breakdown | CH1 note 1 | `no_project_target` (no-op under held note-0 mask) |
| post-drop | CH1 note 41 | `inactive_report_only` (empty bank) |
| any future active CC/pitch render control | — | `unsupported_fail_export` |

`bridge_owned_safety`, `no_project_target`, and `inactive_report_only` controls
are NOT missing-project errors and MUST NOT be given invented SoundSwitch targets.

**F-4. Minimal pack schema rules.** Every pack artifact carries a mandatory
`schema_version`. The loader rejects an unknown major version and performs NO
runtime migration. Any future schema migration is offline-only and tested; the
runtime never migrates a pack in place.

**F-5. Proof-gate golden CH1-CH19 artifacts.** The exporter/player test corpus
MUST include byte-exact golden CH1-CH19 frames for: representative scripted
sample positions; Autoloop pre-roll; Autoloop raw-zero; a count>255 Autoloop
(e.g. `SSAutoLoop13.ssfile`, 257 records); DDJ slots 8/16/17/24 (the four golden
frames in the closure report, reproduced by the Task 0.5 proof gate); blackout
press/release; static-override press/release; and stop/unload zero.

### Must add before direct DMX / hardware

**F-6. Fixture-map proof.** Before any direct DMX, prove the universe/address
mapping and the CH1-CH19 -> 512-byte frame expansion, including one-fixture and
two-fixture behavior, mirrored/duplicated fixture behavior, and zero-frame
expansion. Physical addresses come only from the reviewed fixture-map config,
never inferred from names.

**F-7. Output exclusivity.** Direct DMX and physical MIDI laser output are
mutually exclusive. There is no silent fallback between them. Invalid or
contended port ownership fails disabled / zero, never a partial or dual-output state.

### Reinforced existing rules

**F-8. 200 Hz hot path.** `_push_tick` performs no reload, no project/pack/config
parsing, no hardware/serial/MIDI/network calls, and no locks. The hot path submits
to a bounded latest-frame-only nonblocking mailbox and exposes stale/drop counters.

**F-9. Saved-project workflow.** The exporter reads saved bytes only; unsaved
SoundSwitch edits are invisible by design. Concurrent mutation during read fails
closed with the operator instruction to save/close the edit and re-export.

**F-10. Captures/oracles.** Passive captures and oracles are verifier evidence
only and are NEVER production pack input or renderer-seeded state.

## Part C - Invariants that MUST still hold (live safety)

- `StateManager` remains the only `DeckState` writer.
- `RBStateReader` ANLZ-path-before-track-load ordering and direct-reader
  authority/readiness remain unchanged.
- The 200 Hz loop gains no blocking filesystem, MIDI, serial, network,
  subprocess, retry, or sleep work.
- Existing OS2L mode is unchanged when pack mode is off.
- Existing MIDI laser behavior is byte/order equivalent under the MIDI backend.
- Laser policy and output execution remain separate.
- LED/Govee behavior and worker ownership are unchanged.
- Blackout/emergency beats Static Override and base selection. Release renders
  current state; errors/staleness resolve zero.
- Exactly one worker owns each MIDI input and Enttec port; exactly one bridge
  process is required.
- Live config, source projects, device identifiers, and secrets remain
  uncommitted.
- Parser/unit/shadow tests do not upgrade hardware validation status.

## Part D - Tests and checks

Add focused unit tests for:

- physical count 257, 10-byte trailer, count/offset/EOF bounds;
- raw zero/one/maximum and cold-new `raw-1` regression;
- signed pre-roll, equal-time order, wrap, sparse persistence, stale cue failure,
  intensity-no-channel behavior, seek/pause/refire/stop;
- unique primary Venue Static Looks collection and all 32 version-5 slots;
- Static Override replace/release ordering, blackout precedence, reload clear,
  and device-disconnect/stale hold cleanup;
- learned MIDI add/remove snapshots, disabled bindings, note-on-zero
  normalization, collision rejection, and unsupported CC/pitch active control;
- all current catalog/IAC/DDJ/TrackMap active crosswalks;
- stable source read, source drift, symlink, case collision, unsupported active
  layout, missing cue, noncanonical pack, and one-byte verifier mutation;
- existing MIDI backend parity and rejected-scene non-advancement;
- latest-frame mailbox overflow/staleness, zero-on-error/shutdown, and Enttec
  packet bytes without hardware.

Run every contract-required check plus:

```bash
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

No automated test may mutate the live SoundSwitch project or open live MIDI,
serial, Art-Net, Enttec, or physical DMX.

## Part E - Acceptance

The implementation agent's report MUST include, verbatim:

- [ ] The pack-generation proof-gate command run
      (`python3 tools/prove_soundswitch_pack_generation.py --project ... --output-dir ...`).
- [ ] The JSON report path (`artifacts/soundswitch_pack_generation_proof/latest.json`).
- [ ] The Markdown report path (`artifacts/soundswitch_pack_generation_proof/latest.md`).
- [ ] The proof `final_verdict` (must be `PASS_IMPLEMENTATION_MAY_BEGIN` to proceed).
- [ ] The exact proof pass/fail/incomplete totals.

Acceptance criteria:

- [ ] Production change contract added before behavior code.
- [ ] Source-identity gate pins project UUID `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}`
      and rejects a wrong UUID even when the RAVE Venue GUID matches.
- [ ] Venue cue handling asserts the split: 232 fixture-payload render cues + 1
      default catalog-tail record (233 total); the catalog-tail never renders as a cue.
- [ ] Complete stable rescan with no fuzzy/name/file-order identity.
- [ ] All current project totals, the active-cue union SHA-256, and active
      crosswalks match the closure report and the proof gate.
- [ ] All 32 Static Looks and every learned mapping are present in the pack.
- [ ] Channel-2 utilities and breakdown/post-drop unmapped notes remain explicit
      no-target rows, not guessed targets.
- [ ] Newly added/removed Autoloops and note-based mappings are detected by the
      next export.
- [ ] Identical exports are byte-identical; independent verifier rejects every
      adversarial mutation.
- [ ] Pure player passes reference, transport, Static Override, and blackout
      oracles without capture-seeded state.
- [ ] Default-off/dry-run startup produces no MIDI/DMX/input behavior change.
- [ ] Existing MIDI backend parity passes.
- [ ] No blocking work enters `_push_tick`.
- [ ] Stop/stale/error/reload/disconnect/shutdown paths resolve zero.
- [ ] Shadow mode and adversarial review pass before any live approval request.
- [ ] Status remains SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## Adversarial self-review targets

Implementation review must explicitly try to break:

1. pressing slot 8, then slot 17, then releasing slot 8—slot 17 must remain;
2. Static Override and blackout changing in the same tick—blackout must win;
3. note-0 blackout released after selection changes—current selection must
   render, not the old frame;
4. pack reload while a DDJ note is held—held state must clear to zero;
5. an enabled duplicate learned event—export must fail, not pick first;
6. a rejected executor scene—pack selection must not advance;
7. MIDI-input or Enttec worker death—status must fail and output resolve zero;
8. process hard kill—documentation must state the unpreventable Enttec last-frame
   hazard and require a physical kill path;
9. a project that shares the RAVE Venue GUID but has a different project UUID (the
   scratch corpus)—export must reject on UUID, not authorize on Venue GUID;
10. the minimal default catalog-tail Venue record—export/player must classify it
    distinctly and never render it as one of the 232 fixture-payload cues.

## When you finish

Report changed files, contract/docs updated, pack schema, source/pack fixture
hashes, exact test/check results, the pack-generation proof-gate command +
`final_verdict` + JSON/Markdown report paths + exact pass/fail/incomplete totals,
active/inactive unsupported artifacts, shadow parity totals, and adversarial-review
results.

Include the required plain-language operator summary:

- what pack mode should do differently live;
- what OS2L, MIDI laser, Rekordbox, LED/Govee, and disabled behavior remains
  unchanged;
- healthy status/log indicators for pack verification, current selection,
  controller input, blackout, frame sender, and single bridge process;
- failure watchpoints in SoundSwitch-derived selection, lasers, Rekordbox state,
  and bridge logs;
- what was software/wire verified and what remains hardware-unvalidated;
- exact approval-gated restart/enable/rollback/hardware commands. Do not restart,
  toggle, open a device, or send physical output without that approval.
