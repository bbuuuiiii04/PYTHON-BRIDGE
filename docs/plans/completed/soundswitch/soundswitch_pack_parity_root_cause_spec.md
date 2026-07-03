---
doc_status: active-spec
truth_level: code-artifact-capture-and-static-binary-grounded global root-cause spec
last_verified_commit: 03af947
last_verified_date: 2026-07-01
validation_scope: read-only artifact/capture investigation plus current callable GhidraMCP/static symbol/hash evidence plus 2026-07-01 direct all-surface U0/U1 truth-check capture; no Export from SoundSwitch; no canonical-pack overwrite; no bridge restart; no Enttec/DMX/laser/LED/Govee hardware validation
---

# Codex Implementation Spec - SoundSwitch Global Pack Parity Root Cause

## Part A - Context & Root Cause

### Current verdicts

- [confirmed] Scripted tracks have a real pack mismatch. DD42028C is the
  confirmed witness: the bridge renders its loaded pack exactly, but the pack's
  generated cue replay does not match SoundSwitch U0 for every boundary. The
  other 31 active scripted tracks are unproven, not cleared.
- [confirmed] Autoloops have real residual frame mismatches in both the older
  scout-oracle evidence and the 2026-07-01 direct all-surface truth-check
  capture. The new capture shows every active Autoloop target stuck at
  `phase_tick=0` in bridge U1 truth-check metadata, which points to an
  edge-vs-latched-scene runtime bug rather than the scripted boundary-frame
  defect.
- [confirmed] Static Looks / Static Override do not share the `.ssfile`
  cue-reference mechanism, but the 2026-07-01 all-surface capture proves live
  U0/U1 non-parity in Static Look windows. The first blocker is trigger
  authority: the bridge recorded zero held static rows while SoundSwitch U0
  changed, and the bridge log repeatedly reported the SoundSwitch MIDI input
  port gone/degraded.
- [confirmed] The root cause class is broader than one bad offset: generated
  `.ssfile` cue replay is being treated as canonical DMX parity before it has
  either layout-specific structural proof or an external U0 oracle.
- [confirmed] Fresh export/publication must fail closed for active scripted
  documents without proof. Oracle-derived boundaries are containment only until
  every approved boundary passes, including DD42028C boundary 10.
- [unknown] The exact saved-byte/runtime mechanism that makes DD42028C U0 differ
  from generated cue replay is still blocked after a successful current
  GhidraMCP pass. The opened SoundSwitch arm64 binary shows the `.ssfile`
  reader/writer/cache path consumes cue-map keys, timeline entries, resolved cue
  GUIDs, sparse cache overlays, Static Look overlays, and final output lookup;
  it does not expose an addressed-footer, prefix, or shared-table remap that
  explains the per-row U0 deltas.

### 2026-07-01 GhidraMCP verdict

- [confirmed] GhidraMCP connected in the current session. `get_current_function`
  returned a function from the opened SoundSwitch program at `0x10046221c`, and
  `list_methods` returned the loaded function table. No headless fallback was
  needed because MCP was callable.
- [confirmed] The local universal binary is
  `/Applications/SoundSwitch.app/Contents/MacOS/SoundSwitch`, SHA-256
  `636ed4aa48287d019a96c60f8d9107e75f3e72abe4f7b0aa8fa54aaa661984e9`,
  architectures `x86_64 arm64`. `nm` shows matching target symbols in both
  architectures; arm64 was decompiled because prior SoundSwitch evidence also
  used arm64.
- [confirmed] Decompiled arm64 reader/writer/cache functions:

| Function | Address | Current finding |
| --- | --- | --- |
| `SoundSwitchDocData::Read` | `0x1003318e8` | reads document version, venues, beatgrid, `MainTrack`, then the 10-byte trailer fields; no observed post-trailer cue remap branch |
| `MainTrack::ReadMain` | `0x1003cfb8c` | reads `SSTrack`, link/source/ref tracks, then `AttributeCueTrack::ReadAttributesCueTrack` and `ResolveAttributesCues` |
| `AttributeCueTrack::ReadAttributesCueTrack` | `0x1003c26e4` | reads one `AttributesCueMap`, timeline count, then calls `AttributeCueTrackEntry::ReadEntry` for each row |
| `AttributesCueMap::Read` | `0x1003c0f00` | reads `u32 version`, `u32 count`, then 16-byte cue GUID plus `u32 stored_key`; builds GUID/key and key/GUID maps |
| `AttributesCueMap::AttributesCueMap` | `0x1003c0c2c` | builds writer map from `AttributesCueLibrary` by assigning zero-based keys in library order |
| `AttributeCueTrackEntry::ReadEntry` | `0x1003c16ac` | reads version, constant, elapsed/time, saved positive integer, and looks that integer up in the cue map; no footer/shared-byte lookup was observed |
| `AttributeCueTrackEntry::WriteEntry` | `0x1003c17dc` | writes version, constant, elapsed/time, and the cue-map key for the entry's selected cue GUID |
| `AttributeCueTrack::WriteAttributesCueTrack` | `0x1003c2960` | writes a fresh `AttributesCueMap`, counts resolved entries, then writes each resolved entry |
| `AttributeCueTrack::ResolveAttributesCues` | `0x1003c2c00` | resolves each entry's saved cue GUID through `AttributesCueLibrary`; no name/index heuristic |
| `AttributeCueTrackEntry::ResolveAttributesCue` | `0x1003c1550` | resolves one entry by GUID through `AttributesCueLibrary` |
| `AttributeCueTrackCache::Rebuild` | `0x1003c1e38` | starts with a zero cache entry, then copies the prior entry and overlays each cue's converted attribute map |
| `AttributeCueTrackCache::Rebuild` merge overload | `0x1003c1bd0` | merges two sorted entry vectors, then calls the normal sparse cache rebuild |
| `AttributeCueTrackCacheEntry::Lookup` | `0x1003c4960` | returns cached channel value by attribute/channel key, zero if out of range |
| `SSPlaybacks::RefreshCache` | `0x100338198` | chooses Static Override before normal Static Look, then two- or four-playback cache refresh |
| `SSPlaybacks::SetChannelAttributes` | `0x10033710c` | reads base cache values, then lets Static Look cache replace matching generic attributes before final override/blackout-style transforms |
| `AutoLoopLayout::buildAutoLoopForStartingBeat` | `0x10025f22c` | selects/stores Autoloop index, start/end beat, beat count, and document pointer |
| `AutoLoopLayout::GetStateForTime` | `0x10025f000` | converts playback time to beat position and phase tick at 600 ticks/beat |
| `AutoLoopTrack::GetLightingState` | `0x10025e8b0` | gets the selected Autoloop document/state and renders through `SSVenueData::GetLightingState` |
| `StaticLooks::Read` | `0x10033bcc8` | reads 32 fixed Static Look slots |
| `StaticLook::Read` | `0x10033aa6c` | reads slot name, intensity/strobe/colour/position maps, and generic attributes |
| `SSPlaybacks::RebuildStaticLookCache` | `0x100335230` | converts Static Look maps/generic attributes into static caches |
| `SSPlaybacks::EnableStaticLook` | `0x100338770` | stores direct normal static slot index, clears only matching release |
| `SSPlaybacks::EnableStaticLookOverride` | `0x100338794` | stores direct override slot index, clears only matching release |
- [confirmed] `get_function_xrefs("ReadEntry")` showed calls from
  `ReadAttributesCueTrack` and `ReadPositionTrack`; the relevant scripted cue
  path is `ReadMain -> ReadAttributesCueTrack -> ReadEntry`.
- [rejected] The current Ghidra path did not find a saved addressed-footer,
  prefix, or shared-table runtime cue remap. DD42028C's retained prefix/footer
  bytes are still retained/provenance inputs, but no decompiled target path
  showed them participating in cue identity, cache rebuild, composition, or
  runtime lookup.

### 2026-07-01 all-surface capture verdict

- [confirmed] A direct all-surface Art-Net truth-check capture was recorded at
  `tools/ssfmt/captures/all_surface/all_surface_20260701_024858`. This was not
  the older T7d workflow. The bridge was already running with U1 truth-check
  enabled; it was not restarted or toggled.
- [confirmed] Raw packet counts were U0=66,460 and U1=375,059. The loopback
  subset was U0=33,232 and U1=187,532. The sliced truth sidecar had 154,300
  rows, and all 154,300 sidecar rows aligned back to U1 loopback packets by
  Art-Net sequence plus DMX SHA-256.
- [confirmed] No SoundSwitch export, canonical pack overwrite, SoundSwitch
  project mutation, live config change, Enttec/serial/hardware output, bridge
  restart, laser behavior change, LED/Govee change, or Rekordbox behavior change
  was performed for this capture.

| Surface | Evidence | Current verdict |
| --- | --- | --- |
| Scripted, operator-chosen track | SSID `{528E8B22-BD17-41B9-A111-275D3E8B3031}`, log track `Rihanna - Where Have You Been - 02 - Where Have You Been (Hardwell Club Mix).flac`; nearest U0/U1 comparison: 45,077 matches, 9,550 mismatches, mismatch rate `0.1748` | [confirmed] mostly close but not exact; [unknown] whether mismatches are pack content, boundary/held-frame timing, or static/autoloop overlap until per-boundary analysis is completed. This is not DD42028C and must not be used as DD42028C saved-byte proof. |
| Autoloops | 76,584 sidecar rows; statuses `empty_dark_look=43,948`, `rendering_active=32,636`; every captured active target identity had exactly one phase tick with min/max `(0,0)` | [confirmed] bridge U1 Autoloop runtime is stuck rendering phase zero. The leading runtime mechanism is that a latched Autoloop scene is passed into `NativeAutoloopResolver.resolve()` every tick and treated as a fresh scene edge, resetting `anchor_beat` to the current beat each tick. |
| Static Looks / Static Override | `static_held_rows=0`; static slots always empty; `input_degraded=true` for 133,771 sidecar rows; bridge log repeated `[SS-MIDI] input port gone; retrying exact port`; SoundSwitch-visible static windows changed U0 while U1 stayed on base/zero/Autoloop frames | [confirmed] Static mirroring is blocked before render parity because trigger authority did not reach the bridge. [unknown] Static overlay/content parity after input/held-state authority is restored. |
| Status surface | Top-level status could report SoundSwitch-present native suppression and no scripted/native target while U1 truth sidecar was actively rendering scripted/Autoloop rows | [confirmed] truth-check render intent needs a separate operator-visible status surface; existing production-suppressed status can mislead parity triage. |

### Confirmed global root cause

- [confirmed] The bridge runtime is not corrupting scripted output.
  `render_scripted_frame()` uses loaded scripted boundary frames whenever every
  event has one (`soundswitch_laser_player.py:122-128`), and the pack driver
  submits the player result rather than reinterpreting it. If the pack artifact
  is wrong, the runtime faithfully sends the wrong frame.
- [confirmed] The production exporter still models `.ssfile` timeline rows as a
  single `raw_reference -> stored_key = raw - 1 -> cue GUID` lookup
  (`soundswitch_project_decoder.py:538-544`), then replays one sparse cue patch
  into one frame (`soundswitch_pack.py:101-122`).
- [confirmed] The verifier proves the same internal model, not external
  SoundSwitch U0 parity. It enforces `stored == raw - 1` and recomputes the same
  cue replay (`soundswitch_pack_verifier.py:329-355`), so a wrong-but-consistent
  cue-resolution model can still publish as `rendered`.
- [confirmed by current GhidraMCP] SoundSwitch 2.10.3's arm64
  `AttributeCueTrack::ReadAttributesCueTrack` (`0x1003c26e4`) reads an
  `AttributesCueMap`, then calls `AttributeCueTrackEntry::ReadEntry`
  (`0x1003c16ac`) for each timeline entry. `ReadEntry` reads the saved positive
  integer and uses it to look up the cue map entry; `WriteEntry`
  (`0x1003c17dc`) writes the cue-map key for the selected cue. This confirms
  the physical reader/writer shape, but it does not explain DD42028C's
  SoundSwitch U0 mismatch by any global offset or footer/shared-byte branch.
- [confirmed by current GhidraMCP] Normal playback cache construction is sparse
  persistence, not literal independent frames:
  `AttributeCueTrackCache::Rebuild` (`0x1003c1e38`) starts with a zero cache and
  constructs each later cache entry by copying the prior cache and overlaying
  the current cue's converted attribute map; `AttributeCueTrackCacheEntry::Lookup`
  (`0x1003c4960`) returns the cached attribute value for each channel attribute.
  That validates the current cue-replay renderer shape when the timeline cue
  identity is correct. The arm64 reader/writer evidence confirms the physical
  stored-key shape; the `raw-1` renderer rule is still runtime/wire evidence for
  this SoundSwitch 2.10.3 profile, not a generic reader-format truth.
- [confirmed] DD42028C is the concrete witness that the global model can be
  wrong. For active scripted track
  `dd42028c-0823-4a8d-ad7e-b26e24180272`, source
  `{DD42028C-0823-4A8D-AD7E-B26E24180272}.ssfile`, SHA-256
  `1ff7dd039bc195aec0593c6b0081e214906469f81b224753e7ed9ec1ffbd889f`.
  The document layout is `dictionary_timeline_addressed_footer`, with 189 cue
  dictionary rows and 91 timeline rows
  (`local/soundswitch/rbss_canonical_pack/scripted/dd42028c-0823-4a8d-ad7e-b26e24180272.json:document`).
- [confirmed] The older generated pack at
  `/Users/bbui/Music/SoundSwitch/rbss_canonical_pack` has the same DD42028C
  source hash and `pre_render_status: rendered`. The local repo pack has
  `pre_render_status: oracle_rendered`, but the local patch is only containment,
  not a complete root fix.
- [confirmed] Against `/tmp/rbss_parity_sniff.jsonl` using first-lit U0 alignment,
  the old generated DD42028C boundaries match nearest SoundSwitch U0 at 69/91
  event boundaries. The local `oracle_rendered` patch improves this to 81/91,
  but it is not exact. Boundary 10 at `41202ms` is a containment-regression
  example: old generated CH10/CH11 `(0,255)` matches nearest/held U0, while the
  patched boundary has `(110,0)`.
- [confirmed] The bad headline event at `27539ms` is not a global offset issue.
  The saved row has `raw_reference=3`, exported as stored key `2` / cue `STROBE`
  (`ea7be0ca...`), whose primary patch is CH10=110, CH11=0. SoundSwitch U0
  matches the Venue cue `WHITE DOT STROBE` (`94b568b4...`), stored key `1`, with
  CH10=0, CH11=227, applied over the prior base.
- [confirmed] Other mismatched DD42028C rows require different key deltas:
  `raw=4` resolves to key `2` for several strobe rows, `raw=186` matches key
  `187`, `raw=183` matches key `186`, and `raw=188` matches key `183`. No single
  direct/one-based/global offset rule can repair the track.

#### DD42028C mismatch evidence table

All rows below use the same source `.ssfile` SHA-256
`1ff7dd039bc195aec0593c6b0081e214906469f81b224753e7ed9ec1ffbd889f`,
the same retained prefix SHA-256
`372ecdfda69e47948fd9fb54296ca1f479c7bcab6944051d3b9910ff6a5b6784`,
and the same retained footer SHA-256
`4e6bb40b90754304b29fbaff9707381b8184ab8d627dd4dbc26568e6788f54fc`
in both the old generated pack and local `oracle_rendered` containment pack.
The timeline record bytes are literal `<u32 version, u32 constant, i32 time,
u32 raw_reference>` from
`/Users/bbui/Music/SoundSwitch/default.ssproj/{DD42028C-0823-4A8D-AD7E-B26E24180272}.ssfile`.

| Event | Offset | Time | Saved record bytes | Current generated resolution | U0 / old / local boundary result | Mechanism classification |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 5 | `93711` | `27539ms` | `0100000001000000936b000003000000` | `raw=3 -> raw-1 key=2`, `STROBE`, GUID `ea7be0ca8e396340b5de863399bb6004`, patch CH10/11 `(110,0)` | nearest U0 and local are `(0,227)`; old mismatches; nearest row-local cue is key `1` `WHITE DOT STROBE` GUID `94b568b4f107bf44b0d46aaa4163025e` | [confirmed] cue replay mismatch; [rejected] raw-1 exactness; [rejected] direct/global offset |
| 8 | `93759` | `40577ms` | `0100000001000000819e000004000000` | `raw=4 -> raw-1 key=3`, `MASTER STROBE`, GUID `9b5b1d84cefdb041886c7def04d494fa`, patch CH10/11 `(255,255)` | nearest U0 and local are `(110,0)`; old mismatches; nearest row-local cue is key `2` `STROBE` GUID `ea7be0ca8e396340b5de863399bb6004` | [confirmed] different delta from event 5; [rejected] single offset |
| 10 | `93791` | `41202ms` | `0100000001000000f2a000005e000000` | `raw=94 -> raw-1 key=93`, `TRAPDUB DROP 1`, GUID `7ede3d8f1581094ba622bd93451d97aa`, patch CH10/11 `(0,255)` | nearest U0 and old generated match `(0,255)`; local `oracle_rendered` regresses to `(110,0)` | [confirmed] old generated can be correct; [rejected] local oracle containment as exact proof |
| 80 | `94911` | `98584ms` | `010000000100000018810100ba000000` | `raw=186 -> raw-1 key=185`, `ruby effect`, GUID `2a6ae31cd6ecf94da9bd0c81ece9a434`, patch CH10/11 `(0,255)` | nearest U0 and local are `(196,0)`; old mismatches; row-local cue key `187` `THICK RAINBOW` GUID `852886d7e8e191438de93bbbcd1dee80` matches CH10/11 | [confirmed] positive delta; [rejected] low-row-only strobe fix |
| 82 | `94943` | `98884ms` | `010000000100000044820100bc000000` | `raw=188 -> raw-1 key=187`, `THICK RAINBOW`, GUID `852886d7e8e191438de93bbbcd1dee80`, patch CH10/11 `(196,0)` | nearest U0 and local are `(0,0)`; old mismatches; prior analysis names key `183` `THICK RAINBOW 3` GUID `344add619beca147b2901b62ad254551` as the nearest full-row cue | [confirmed] another different delta; [rejected] cue-name-only fix |

Totals from the current local evidence:

- [confirmed] DD42028C source copies under `default.ssproj`, `codex fixture
  research real.ssproj`, and `vln_ss_analysis/copies/ssproj` all hash to
  `1ff7dd039bc195aec0593c6b0081e214906469f81b224753e7ed9ec1ffbd889f`.
- [confirmed] DD4028C is absent in the scoped repo/pack/capture evidence; it is
  treated as a typo only.
- [confirmed] DD42028C has 91 timeline rows, 76 positive references, 15
  raw-zero/control rows, 189 cue dictionary rows, layout
  `dictionary_timeline_addressed_footer`.
- [confirmed] `/tmp/rbss_parity_sniff.jsonl` contains 16,754 U0 frames and 32
  distinct U0 CH1-CH19 states for this investigation.
- [confirmed] Old generated boundaries match nearest U0 at `69/91`; the local
  `oracle_rendered` containment boundaries match nearest U0 at `81/91`.
  Against held U0 at the same first-lit alignment, old matches `35/91` and
  local matches `43/91`.
- [confirmed] Brute-force simple key rules against nearest U0 score:
  `raw-3 = 0/91`, `raw-2 = 6/91`, `raw-1 = 69/91`, `direct = 27/91`,
  `raw+1 = 1/91`, `raw+2 = 1/91`, `raw+3 = 2/91`. This rejects a new global
  offset as the exact mechanism.

### Blocked exact mechanism

Attempted paths:

- [confirmed] GhidraMCP connection repair/use: tool discovery exposed
  `mcp__ghidra`; `get_current_function` and `list_methods` succeeded against
  the currently opened SoundSwitch project. The `127.0.0.1:8080` refusal path
  was not hit in this run, so no bridge-wrapper repair or duplicate process
  launch was needed.
- [confirmed] Static symbol/xref/decompile path: arm64 target functions listed
  above were decompiled; x86_64 symbols were checked cheaply with `nm` and found
  at corresponding addresses.
- [not needed] Headless/local Ghidra fallback: not run because MCP was callable
  and returned the relevant decompilations.
- [confirmed] Repo artifact and capture reconciliation: old generated pack,
  local `oracle_rendered` pack, `/tmp/rbss_parity_sniff.jsonl`, and
  `/tmp/rbss_artnet_truth_frames.jsonl` were reconciled read-only. No SoundSwitch
  export, canonical-pack overwrite, bridge restart, live config change, Enttec,
  serial, laser, LED/Govee, Rekordbox, or hardware output action was performed.

Exact failure reason:

- [unknown] The opened binary evidence answers the physical reader/writer/cache
  path, but it does not explain the DD42028C U0 per-row deltas from saved bytes.
  The rows that mismatch require incompatible key movements, while the decompiled
  `.ssfile` path shows one cue map, one timeline row integer, GUID resolution,
  sparse cache overlay, and final lookup. No inspected function reads the
  addressed footer/prefix/shared bytes as a cue identity, remap, composition, or
  cache-rebuild input.

Exact remaining unknown:

- [unknown] Whether the U0 mismatch is caused by an uninspected higher-level
  runtime state/cached project state outside the `.ssfile` reader path, capture
  alignment/window ambiguity, a SoundSwitch-internal cache invalidation path not
  represented by saved bytes, or an unlocated callsite below
  `SSVenueData::GetLightingState` that changes the effective entry/cue at
  playback time.

Minimum remaining proof:

- [confirmed] The bridge/exporter must fail closed for active scripted cue replay
  until one of these exists: a committed oracle boundary fixture that passes
  every approved DD42028C boundary, including boundary 10; or a controlled
  SoundSwitch proof that mutates/saves one candidate byte/path at a time and
  shows which saved byte changes the emitted U0 frame. Any capture proof must
  include source hash, alignment metadata, per-boundary validation totals, and
  a stable reduced fixture so `/tmp` files are not the product authority.

Root cause: **the exporter/importer publishes unproven `.ssfile` cue replay as
canonical SoundSwitch DMX.** The shared production model serializes one
raw-reference lookup plus one sparse cue patch as if it were SoundSwitch's
emitted boundary state. DD42028C proves that this model can select or compose
the wrong cue content. Every active scripted document that publishes only
self-consistent cue replay is therefore unproven until it has structural proof
or an external U0 oracle. Active Autoloops carry a related but separate risk:
they use the same saved-document cue replay plus phase/cycle/pre-roll logic, and
their existing oracle reports already show residual mismatch. Prior GhidraMCP
confirms that normal cache playback is prior-cache plus sparse cue overlay, so
sparse persistence itself is not the bridge bug. The missing mechanism may be
layout-specific metadata, legacy edit state, cache-building behavior not
represented in the saved-byte model, or a case that requires capture-backed
canonicalization. Do not promote the local `oracle_rendered` patch into proof
that export is fixed.

### Blast radius

- [confirmed] Scripted tracks: DD42028C is confirmed affected, and the current
  repo-local pack has 32 active existing-path scripted tracks: 30 active
  `shared_441_dictionary_timeline` tracks with `pre_render_status: rendered`,
  one active `dictionary_timeline_no_shared_anchor` track with
  `pre_render_status: rendered`, and DD42028C as the only active
  `dictionary_timeline_addressed_footer` track, locally patched as
  `oracle_rendered` but still inexact. The active shared-layout group currently
  has 1,235 total timeline rows and 959 positive references; one active shared
  scripted document has zero timeline rows. Existing U0/U1 sidecar evidence
  covers only DD42028C, so the other 31 active scripted tracks are **unproven**,
  not cleared.
- [confirmed] Autoloops: 19 active Autoloop targets are all
  `shared_441_dictionary_timeline` / `pre_render_status: rendered`, so they also
  rely on the shared `.ssfile` cue replay model plus Autoloop phase/cycle logic.
  They are affected by real parity mismatches, but not by the scripted
  boundary-frame defect. `render_autoloop_frame()` ignores boundary frames and
  replays events with cycle/pre-roll logic (`soundswitch_laser_player.py:132-154`).
  Existing scout oracle reports show residual mismatches after best alignment:
  exact-match rates `0.793931` and `0.719366`, with many per-look
  `MISMATCH(residual)` rows
  (`tools/ssfmt/captures/t7d/t7d_scout_mix_20260629_161931/autoloop_oracle_report.md:11-43`,
  `tools/ssfmt/captures/t7d/t7d_scout_mix_cont_20260629_163143/autoloop_oracle_report.md:11-43`).
  The 2026-07-01 all-surface truth-check capture adds a direct runtime witness:
  all active Autoloop target identities in the bridge sidecar had
  `phase_tick=0` for every row. Candidate code path to prove/fix:
  `state_manager._drive_pack_output()` supplies a latched scene from
  `current_autoloop_scene()`/native state into `NativeAutoloopResolver.resolve()`
  on every tick; `resolve()` treats any non-null scene as a fresh edge and
  resets `anchor_beat`, preventing phase advancement.
- [confirmed] Static Looks / Static Override: not affected by `.ssfile`
  timeline reference resolution. Static Looks load from `static_looks.json`
  generic attributes (`soundswitch_pack_loader.py:615-632`) and overlay those
  attributes in `apply_layers()` (`soundswitch_laser_player.py:186-214`). The
  current pack exports 32 Static Look slots; 8 pre-rendered slot frames are
  nonzero and 11 slots contain generic CH1-CH19 rows. Current learned controls
  include 5 active Static Look controls across slots 0, 16, 24, and 31, while
  the DDJ Static Override export has one active DDJ override, slot 16. The
  static bank's slot frames still match the closure report hex for slots 8, 16,
  17, and 24. The 2026-07-01 all-surface capture proves live Static Look /
  Static Override non-parity, but it does not prove the static renderer is wrong:
  no held static rows reached the bridge sidecar, static slots stayed empty, and
  the bridge log reported the SoundSwitch MIDI input port gone/degraded while
  SoundSwitch U0 visibly changed.
- [confirmed by current GhidraMCP and current symbols] Static Look runtime state
  is separate from scripted `.ssfile` timeline rows: `StaticLooks::Read`
  (`0x10033bcc8`) reads 32 fixed slots, `EnableStaticLook` (`0x100338770`) and
  `EnableStaticLookOverride` (`0x100338794`) store direct slot indexes,
  `RefreshCache` (`0x100338198`) chooses static override before normal static, and
  `SetChannelAttributes` (`0x10033710c`) applies matching static-cache values
  after base playback cache values.
- [confirmed] Native Autoloop DMX: not affected by DD42028C scripted
  `oracle_rendered` boundaries, but it uses the same Autoloop pack files and
  `render_autoloop_frame()` path, so it inherits the confirmed Autoloop residual
  parity risk until the native Autoloop oracle is resolved.
- [confirmed by current GhidraMCP and current symbols] Autoloop runtime is its own
  beat-window/index path: `AutoLoopTrack::AutoLoopTrack` (`0x10025e570`)
  constructs an `AutoLoopLayout`, and
  `AutoLoopLayout::buildAutoLoopForStartingBeat` (`0x10025f22c`) chooses an
  Autoloop bank/index, start beat, end beat, beat count, and document pointer.
  This does not reuse scripted boundary frames.
- [confirmed] Runtime pack driver: not the root cause. It chooses scripted vs
  native Autoloop, renders through `LaserPackPlayer`, and submits the resulting
  frame. It does not repair or corrupt pack artifact semantics.

### Capture and runtime evidence limits

- [confirmed] Existing `/tmp/rbss_parity_sniff.jsonl` contains 63,970 Art-Net
  rows from the DD42028C investigation: 16,754 U0 rows, 47,216 U1 rows, 32
  distinct U0 CH1-CH19 states, and 31 distinct U1 CH1-CH19 states. This is
  useful witness evidence, but `/tmp` is not a durable source input.
- [confirmed] Existing `/tmp/rbss_artnet_truth_frames.jsonl` contains one
  matching truth-check sidecar run for pack SHA `508027dcb3ca...`, with 22,613
  scripted rows for `{DD42028C-0823-4A8D-AD7E-B26E24180272}` and 31 distinct
  scripted frame hashes. It has no Autoloop rows and no Static Look coverage.
- [confirmed] The direct all-surface capture at
  `tools/ssfmt/captures/all_surface/all_surface_20260701_024858` is durable
  repo-local evidence for one operator-chosen scripted track, representative
  Autoloops, and Static Look / Static Override trigger windows. Its analysis
  summaries are captured in `analysis_summary.json` and `analysis_notes.md` in
  that run directory.
- [unknown] Fresh U0/U1 captures for DD42028C after any scripted fix, one active
  shared-layout scripted track after per-boundary triage, the no-shared-anchor
  active scripted track, post-Autoloop-phase-fix representative Autoloops, and
  post-static-input-fix Static Looks remain open evidence gates.

### Other pack issues that can cause mismatches

- [confirmed] `oracle_rendered` is a verifier escape hatch: provenance and frame
  shape are checked, but semantic mismatch against cue replay is intentionally
  allowed. It must not be treated as structural proof.
- [confirmed] Layout-specific prefix/footer/shared-table bytes are currently
  retained mostly as hashes; if any of those bytes participate in runtime cue
  identity or composition, the exported model can stay internally consistent and
  still mismatch U0.
- [confirmed] Venue cue decode, primary-fixture filtering, and raw-zero
  control-channel persistence are all load-bearing. Current code is
  deterministic and guarded, but a wrong upstream semantic model can pass all
  downstream verifier checks.
- [confirmed] Learned MIDI and slot mappings are separate from `.ssfile` cue
  replay, but stale or duplicate mappings can make the wrong surface appear
  active. Current verifier rejects duplicate active learned-controller events,
  duplicate active Static Override slot ownership, missing active Autoloop
  targets, malformed boundary provenance, and failed native-Autoloop coverage.
- [unknown] Whether DD42028C's addressed footer, shared metadata, editor/runtime
  state, or an unmodeled SoundSwitch cache behavior is the exact saved-byte
  mechanism remains unresolved. No single raw-reference offset explains the
  observed mismatches.

## Part B - Tasks

### Absolute Rules

- Do not click **Export from SoundSwitch** or overwrite
  `local/soundswitch/rbss_canonical_pack` without explicit operator approval.
- Do not treat `/tmp/rbss_parity_sniff.jsonl` or the local `oracle_rendered`
  pack as an ongoing export source. Captures are verifier/oracle evidence only.
- Do not revive the SoundSwitch playback-mixer/two-deck blend theory for this
  target. Acceptance is single-deck U0 parity for the same scripted track or
  Autoloop at the same elapsed/phase.
- Do not make a global raw-reference offset change.
- Do not import `tools/ssfmt/re/` modules into production runtime/exporter code.
  Port reviewed pure logic into production modules with tests.
- Do not add hot-path file reads, subprocesses, sockets, MIDI, serial, or locks
  to the 200 Hz bridge loop.

### Task 1 - Add a global scripted parity proof registry and DD42028C witness

Files:

- `tests/fixtures/soundswitch/dd42028c_boundary_oracle.json`
- `tests/fixtures/soundswitch/scripted_parity_registry.json`
- `tests/test_soundswitch_scripted_parity.py`

Build a small committed fixture from operator-approved evidence, not the full
scratch capture:

- source SSID and `.ssfile` SHA-256;
- first-lit alignment parameters used for `/tmp/rbss_parity_sniff.jsonl`;
- 91 expected boundary frames or a smaller explicit table containing every
  mismatched boundary plus enough neighboring events to prove persistence;
- expected old-generated vs U0 match totals and the known patched-boundary-10
  containment regression.

The test must fail against plain cue replay for DD42028C and must not require
SoundSwitch, Rekordbox, Art-Net, Enttec, or `/tmp` files.

Also commit a small registry for every active scripted `.ssfile` in the current
pack:

- SSID, source SHA-256, layout, event count, positive-reference count, and
  current render provenance;
- proof status: `oracle_passed`, `structural_proven`, or `unproven`;
- DD42028C as `oracle_failed_plain_replay` until the resolver/oracle workflow
  passes every approved boundary.

This registry is not a frozen completion count. It is a fail-closed manifest so
future exports cannot turn unproven cue replay into a silent parity claim.

### Task 2 - Separate scripted export statuses

Files:

- `soundswitch_pack_models.py`
- `soundswitch_project_decoder.py`
- `soundswitch_pack.py`
- `soundswitch_pack_verifier.py`
- `soundswitch_pack_loader.py`
- `soundswitch_laser_player.py` only if the loaded model needs a new status
- `tools/export_soundswitch_pack.py`

Implement explicit scripted render provenance:

- `rendered_cue_replay`: deterministic cue replay, allowed only for
  documents whose layout/version has parity proof or whose U0 oracle passes.
- `oracle_verified_boundaries`: capture-derived boundaries that passed the new
  fixture/oracle validator.
- `unproven_active_scripted`: active scripted document whose generated cue replay
  has no parity proof; export must fail closed unless the operator explicitly
  chooses an oracle-canonicalization workflow.

Verifier behavior:

- normal generated packs still reject boundary frames that do not match their
  declared structural model;
- `oracle_verified_boundaries` must carry source hash, capture/oracle hash,
  alignment metadata, and per-boundary validation totals;
- every active scripted document without structural proof or oracle proof fails
  publication instead of silently exporting wrong frames;
- active Autoloop documents remain in a separate proof lane, but they must not
  be called parity-complete while their oracle reports have residual mismatch.

### Task 3 - Resolve `.ssfile` cue semantics by layout or fail closed

Files:

- `soundswitch_project_decoder.py`
- new pure helper module if needed, for example
  `soundswitch_scripted_resolution.py`
- `tests/test_soundswitch_scripted_resolution.py`

Smallest correct algorithm:

1. Preserve the physical cue dictionary and timeline exactly as today.
2. Parse and retain layout-specific prefix/footer/shared-table fields currently
   only hashed.
3. Prove per-layout cue/composition identity with committed fixtures. DD42028C
   is the first hard witness; the 30 shared-table active scripts and the one
   no-shared active script still need either structural proof or U0 oracle
   coverage before they are treated as parity-safe.
4. If saved metadata produces exact U0 boundary parity for a layout, emit
   structural composition events rather than raw-reference-only events.
5. If no saved-byte resolver is proven for a layout/document, keep it
   fail-closed and require the oracle workflow in Task 4.

Do not guess from cue names or nearest neighboring keys. The resolver must be
deterministic from saved bytes or explicitly marked oracle-derived.

### Task 4 - Promote oracle canonicalization into an offline export aid

Files:

- new CLI under `tools/`, for example
  `tools/canonicalize_soundswitch_scripted_oracle.py`
- production pure model/tests as needed
- docs for the operator gate

Port the minimal `oracle_canonicalize.py` idea into a reviewed offline tool:

- input: generated pack, source `.ssfile` hash, target document identity, clean
  SoundSwitch U0 capture or reduced boundary fixture, explicit alignment
  metadata;
- output: a canonical scripted artifact with cue/composition/literal entries and
  validation statistics;
- never run from bridge runtime;
- never overwrite the canonical pack unless the operator approves a publish step;
- preserve literal fallback only where structural cue composition cannot express
  the observed U0 frame.

Acceptance for any oracle-canonicalized scripted document: exact match at every
approved boundary. DD42028C must include boundary 10.

### Task 5 - Autoloop parity lane

Files:

- `soundswitch_laser_player.py`
- `native_autoloop_resolver.py` only if phase selection is implicated
- `tools/ssfmt/re/autoloop_oracle/` or a production-equivalent validator
- focused tests for `render_autoloop_frame()`

Do not bundle Autoloop fixes into the scripted resolver. Use the existing scout
oracle reports as failing evidence and isolate whether mismatches are caused by:

- edge-vs-latched-scene handling resetting `anchor_beat` every tick;
- phase alignment/latency only;
- cycle/pre-roll replay semantics;
- raw-zero/control-channel persistence;
- selection/refire timing;
- unreliable ground truth windows.

Add a focused regression for the 2026-07-01 capture witness: a latched current
Autoloop scene observed across advancing beat positions must not reset the
resolver anchor every tick, and the rendered metadata must show advancing
`phase_tick` values. The exact SoundSwitch anchor rule still needs proof: if it
is not the first observed scene edge, document whether SoundSwitch anchors to a
selected Autoloop start beat, phrase/drop event, beatgrid phase, or another
runtime state.

Native Autoloop DMX cannot be called parity-complete until this lane has a
passing oracle or a documented residual blocker. A software unit test that only
proves phase advancement is necessary but not sufficient.

### Task 6 - Static Look parity lane

Files:

- `soundswitch_project_decoder.py`
- `soundswitch_pack.py`
- `soundswitch_pack_loader.py`
- `soundswitch_laser_player.py`
- `tests/test_static_looks.py`
- `tests/test_soundswitch_midi_input.py`

Keep the Static Look model separate from `.ssfile` fixes. Verify:

- the bridge can observe the same Static Look / Static Override trigger
  authority that caused SoundSwitch U0 changes in the 2026-07-01 capture;
- the SoundSwitch MIDI input path is not degraded/gone during capture, or the
  operator-visible status fails closed before parity is claimed;
- all 32 slots still export from the primary Venue collection;
- current saved learned mappings are reported honestly, including the current
  one-active-DDJ-slot state;
- software frames for slots 8, 16, 17, and 24 still match the known closure hex;
- a future U0/U1 Static Look capture with nonzero `static_held` sidecar rows is
  required before live Static parity is claimed.

## Part C - Invariants That MUST Still Hold

- SoundSwitch pack mode remains default-off unless live config explicitly enables it.
- SoundSwitch-present suppression remains intact; the bridge must not fight
  SoundSwitch U0 on physical output.
- Static Override and blackout precedence remain above base scripted/Autoloop.
- `StateManager` remains the only `DeckState` writer.
- No parser/exporter fix may add blocking work to `_push_tick`.
- Existing OS2L, laser MIDI, LEDs/Govee, and Rekordbox reader behavior must not
  change for pack-disabled operation.

## Part D - Tests

Required focused tests:

- scripted parity registry marks every active scripted document as proven or
  unproven; unproven active documents fail publication in the fail-closed mode.
- DD42028C boundary fixture: generated cue replay fails, fixed resolver/oracle
  passes every approved boundary.
- Boundary 10 regression: old generated frame was U0-correct under the alignment;
  oracle canonicalization must not make it wrong.
- Global-offset rejection: raw-1, direct, raw-2, and any single offset cannot
  satisfy all DD42028C mismatched rows.
- Active scripted export fail-closed without proof, not only addressed-footer.
- Scripted shared-layout regression using the existing A5 fixture remains green.
- Autoloop oracle regression remains separate and reports residual mismatch until
  fixed.
- Static Look slot frames and learned-mapping counts are tested without requiring
  the stale `[8,16,17,24]` assumption when current saved bytes only export `[16]`.

Commands:

```bash
python3 -m unittest tests.test_soundswitch_scripted_parity
python3 -m unittest tests.test_soundswitch_pack tests.test_soundswitch_laser_player tests.test_soundswitch_project_decoder
python3 -m unittest tests.test_ssfile_reference_convention tests.test_static_looks tests.test_artnet_compare
python3 tools/artnet_compare.py --self-check
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
git diff --check
```

The full suite may still fail on the known DDJ static-slot expectation until
that test is updated to the current saved project state.

## Part E - Acceptance

- No active scripted `.ssfile` publishes as ordinary `rendered` cue replay unless
  it has structural proof or passes its U0 oracle.
- A fresh **Export from SoundSwitch** cannot silently regenerate unproven
  cue-replay boundaries for DD42028C or any other active scripted document.
- The local canonical pack is either regenerated from a proven structural
  resolver or explicitly marked/published from an approved oracle artifact.
- Every scripted track is reported as proven, unproven, or fail-closed by layout
  and evidence, not swept under one global raw-reference rule.
- Autoloop mismatch evidence is tracked in a separate lane and is not claimed
  fixed by scripted work. Native Autoloop runtime cannot be accepted until the
  2026-07-01 phase-zero witness is resolved and post-fix U0/U1 capture shows
  advancing phase and acceptable frame parity.
- Static Looks remain software/binary verified but live parity is not claimed
  until the bridge observes held static state during an operator Static Look /
  Static Override capture and U0/U1 overlay behavior is reconciled. The
  2026-07-01 capture rejects any claim that current live Static mirroring is
  working.
- No live restart, runtime toggle, Enttec/DMX, laser, LED/Govee, SoundSwitch
  export click, or canonical-pack overwrite is performed without explicit
  operator approval.

## When You Finish

Report:

- exact files changed;
- DD42028C fixture totals;
- whether DD42028C was structurally resolved or oracle-derived;
- which scripted layouts are parity-proven vs fail-closed;
- Autoloop oracle status;
- Static Look mapping/frame status;
- tests/checks run and the known DDJ static-slot failure if still present;
- operator summary: expected live behavior, unchanged subsystems, healthy logs,
  watchpoints, software-only vs hardware-unvalidated evidence, and approval
  gates before restart/export/hardware.
