---
doc_status: research-current
truth_level: binary-static-analysis-corroborating
last_verified_commit: 2c71a2e
last_verified_date: 2026-06-20
validation_scope: read-only static analysis of the local SoundSwitch.app binary (Ghidra headless + nm/c++filt/otool); no SoundSwitch modification, no live process attach, no bridge/runtime/MIDI/DMX change; hardware-unvalidated
---

# SoundSwitch Reverse-Engineering — Ghidra/Binary Addendum (AWR-107)

## Scope and authority

This addendum records read-only **static analysis of the local SoundSwitch
binary** used to corroborate or narrow the open scripted-renderer/exporter
blockers in `soundswitch_scripted_renderer_closure_handoff_spec.md` and
`soundswitch_ssfile_format.md`. Per `AGENTS.md` §1, **executable code / current
bytes / wire captures still win**. A binary finding is treated as
*corroborating evidence or a falsifiable lead*, never as standalone truth: each
item below names how to validate it against project bytes, controlled diffs, or
existing captures. No SoundSwitch app bundle, project file, or running process
was modified or attached.

### Method (no GhidraMCP required)

- Binary: `/Applications/SoundSwitch.app/Contents/MacOS/SoundSwitch` — Mach-O
  **universal** (x86_64 + arm64), native **C++/Qt** (not Electron), ~46 MB main
  executable, **RTTI class names and build paths retained** (build path anchor
  `/Users/arkaos/jenkins/w/SH/SS_MacOS_universal/src/ss/...`). SoundSwitch
  reports app version 2.10.3.
- Structural/API facts came from `nm -arch arm64 | c++filt` and `otool -tV`
  (scriptable, no GUI). Pseudocode came from **Ghidra headless** (`analyzeHeadless`
  + a Jython decompiler post-script) against the arm64 slice imported to a
  throwaway project `/tmp/ssauto`. Symbol dump: `/tmp/ss_syms_arm64.txt`.
- **GhidraMCP was not used and is not required for this work.** The MCP plugin
  runs an in-GUI HTTP server intended for interactive exploration; headless gives
  the same decompilation deterministically. See "Setup notes" at the end.

All addresses below are arm64 vmaddrs (image base `0x100000000`).

## 2026-06-20 closure correction — the packed `.ssfile` loader is identified

The earlier closure report incorrectly treated `AttributeCueTrackEntry::ReadEntry`
as a different `.ssproj`-internal serialization and left a separate “packed
`.ssfile` loader” to find. Headless call-chain analysis now contradicts that:

```text
SoundSwitchDoc::LoadLightingTrack @0x1002e8744
  -> SoundSwitchDoc::OpenFileOnPlayBack @0x1002f153c
  -> SoundSwitchDocData::LoadFromFile @0x1003314b4
  -> SoundSwitchDocData::Read @0x1003318e8
  -> MainTrack::ReadMain @0x1003cfb8c
  -> AttributeCueTrack::ReadAttributesCueTrack @0x1003c26e4
  -> AttributesCueMap::Read @0x1003c0f00
  -> AttributeCueTrackEntry::ReadEntry @0x1003c16ac
```

The apparent packed/big-endian representation in the research parser is a
three-byte-shifted view of the same little-endian CAF fields. For A5, the actual
first record is `u32_le(1), u32_le(1), u32_le(59088), u32_le(91)`; the shifted
parser recovers the same elapsed/reference values.

Both ARM64 decompilation and x86_64 disassembly show:

- `AttributesCueMap::Read` reads `[GUID][u32 key]` unchanged;
- `ReadEntry` reads the timeline key and performs a direct lower-bound/exact-key
  lookup with no subtract-one branch;
- `AttributesCueMap::Write` emits the stored key unchanged; and
- `WriteEntry` writes `AttributesCueMap::Lookup(cue GUID)` unchanged.

Controlled new-object bytes corroborate the direct writer. However, the A5
capture remains 14/14 positive events exact under `raw-1` and 0/14 under direct,
even though AppLog says the current file was found after its final mtime. This is
now an explicit **binary/wire contradiction**, not proof of two numeric loader
branches. The smallest resolving action is the cold-open controlled capture in
`soundswitch_re_closure_report.md` §4.3.

---

## Finding 1 — Cue/Venue references resolve by **GUID**, not by numeric index

**Blocker addressed:** reference resolution / provenance / exporter fail-closed
(closure handoff B1, A4; ssfile_format "Reference resolution is
PROVENANCE-DEPENDENT").

**Evidence (symbols):**
- `sys::ClassId` is an **RFC-4122 UUID**: `sys::ClassId::FromRfc4122(...)`,
  `IsValidGuidStr(char const*)`, `UuidCompare(ClassId,ClassId)`,
  `ClassId(TGenerate)` (mint a UUID), `ClassId(char const*)`.
- The cue loaders are GUID-keyed:
  `AttributesCue::Read(CAF::InStream&, std::map<sys::ClassId, Venue*>&)` and
  `AttributesCueLibrary::Read(CAF::InStream&, std::map<sys::ClassId, Venue*>&)`;
  the writer emits the *set of referenced GUIDs*:
  `AttributesCue::Write(CAF::OutStream&, std::set<sys::ClassId> const&)`.
- Runtime cue containers are keyed by ClassId: `std::map<sys::ClassId,
  AttributesCue*>` and `std::map<sys::ClassId, AttributesCueVenueEntry>`.
- Serialization container is `CAF::InStream` / `CAF::OutStream` (the `.ssfile` /
  `*.bin` "CAF" framing); `Read(InStream&)` / `Write(OutStream&)` is the seam.

**Pseudocode (`AttributeCueTrackEntry::Read` @ `0x3c1580`):**
```c
read u32 version;                         // CAF::InStream vtable+0x40
if (version >= 3) throw ss::XFileNeedVersionUpdate;   // future/unsupported
if (version == 2) { read u32; read u32 index; this->field_0x8 = index; }
SSAttrValueMap::Read(stream);             // the cue patch (key/value map)
```

**Two cue-entry resolution paths exist**, but they do **not** establish a
one-based/direct numeric-key branch:
- `AttributeCueTrackEntry::ResolveAttributesCue(AttributesCueLibrary&)` @ `0x3c1550`
  — **legacy**: resolves position/venue by a stored `sys::ClassId` and leaves the
  cue-entry pointer null (numeric index resolved positionally elsewhere).
- `AttributeCueTrackEntry::ResolveAttributesCueNew(AttributesCueLibrary&, sys::ClassId const&)`
  @ `0x3c150c` — **new/direct**: additionally resolves the cue entry by a passed
  **GUID** via `AttributesCue::GetAttributesCueEntryNew(sys::ClassId const&)`.
- Same old/new split at track level (`AttributeCueTrack::ResolveAttributesCues`
  vs `...New`), plus `lxe::AttributeCueEntryDEPRECATED` /
  `AttributeCueTrackSubRegionDEPRECATED` — evidence of format evolution and
  Venue-entry resolution, but not evidence that the serialized numeric key is
  adjusted by one.

**Means for parser/exporter:** **GUID (`sys::ClassId`) is the stable identity;
the numeric `cue_index` is serialized reference metadata**. The old/new
resolution functions concern Venue/cue-entry resolution; they do not prove a
numeric one-based/direct branch. Controlled bytes still show MIXED-looking
legacy/current values with no per-record discriminator. Fail-closed remains the
correct safety behavior while unresolved, but it is not the final active-content
answer. The per-record
`version` byte read by `AttributeCueTrackEntry::Read` is a lead worth checking in
the parser, **but it does not by itself discriminate MIXED records** (per
`8697587`, edits renumber `cue_index` while keeping records at the same version),
so it must not be used to relax fail-closed without byte proof.

**Means for offline renderer:** resolve references by GUID only after the source
record is canonicalized by a validated byte rule or oracle frame sequence.

**Validate:** re-confirm against `8697587`'s WHYB before/after pair and the
A5 one-based wire proof; check whether the `.ssfile` per-entry `version` byte is
visible to the current parser and whether it ever differs within one file.

**Confidence:** high (symbol signatures + disassembly).

### Finding 1b — Dictionary layout + reference reader (2026-06-20 follow-up)

Decompiled `AttributesCueMap::Read/Write` (`@0x3c0f00`/`0x3c1214`) and
`AttributeCueTrackEntry::ReadEntry(CAF::InStream&, AttributesCueMap&)` (`@0x3c16ac`):

```c
// AttributesCueMap on disk: [u32 version<=1][u32 count] then per entry:
//   [16-byte GUID][u32 LE cue_index]
// ReadEntry: read u32 version(<=1); read u32; read u32 -> field8; read u32 rawRef;
//   look up rawRef in the cue_index-keyed tree (EXACT key match in the decompile).
```

- **Confirmed (byte-validated against wire-proven A5):** the dictionary entry is
  `[16-byte GUID][u32 LE cue_index]`. For A5 "RED BOX SWAY DROP" the u32 after the
  GUID is `90`, and wire raw_ref is `91` → one-based, exactly matching the bridge's
  existing parse. The bridge's `[3 zero][16 GUID][u8 cue_index]` framing is the
  same 20 bytes re-aligned and **agrees** on `cue_index=90`. No dictionary parser bug.
- **No MIXED discriminator found.** The per-record `version` read by `ReadEntry`
  and the in-`.ssfile` timeline `field_a/field_b` are identical (`1`, `(1,1)`) for
  **both** clean and MIXED New Sky records, so they cannot discriminate edited
  records. This confirms the storage-level "no per-record discriminator" result.
- **Blocking contradiction:** `ReadEntry` is the actual `.ssfile` timeline loader,
  and both binary slices use direct stored-key lookup. That does not reproduce
  A5's wire-proven key-minus-one result. Neither source is discarded; the
  cold-load matrix in the closure report must identify the missing step.

---

## Finding 2 — Render is a **persistent layered buffer with identity DMX**; omitted channels persist

**Blocker addressed:** offline renderer implementation gate; New Sky
CH8/CH9/CH15 effect-cue residual (closure handoff A7, B-series); ssfile_format
"Layered render model and remaining control blocker".

**Pseudocode (`AttributeCueTrackCacheEntry` merge-ctor @ `0x3c4710`):**
```c
// AttributeCueTrackCacheEntry(idx, const& PREV, const AttKeyValueMap& NEW_CUE, const Venue&)
this->values = new int[PREV.count];
memcpy(this->values, PREV.values, PREV.count*4);     // (1) inherit ALL prior channel values
for (node : NEW_CUE /* std::map key->value */) {
    key = node.key; val = node.value;
    if (venue.fixtureLib.isAttrEnabled(key) & 1)     // (2) venue-enable gate
        this->values[key] = val;                     // (3) overwrite ONLY keys present in the cue
    // mark Venue::GetTrackForChannel(key) in a utl::BitArray (changed-track set)
}
// value array element type is utl::Array<AttrValueInitZero,...> => first entry initialises to all-zero
```
```c
// AttributeCueTrackCacheEntry::Lookup(key) @ 0x3c4960
return key < count ? values[key] : 0;
```

**Pseudocode (`SSPlaybacks::SetChannelAttributes` @ `0x33710c`) — per-DMX-channel emit:**
```c
SetIntensity(...); SetColour(...);            // intensity & colour applied explicitly (with overrides)
for (ch = channel.start; ch < channel.end; ch++) {
    key = channelMap.keyFor(ch);
    switch (channelFunctionType(ch)) {        // lxe::ChannelFunctionCommandType
      case 1..4, 0xb..0x10, 0x29: continue;   // handled explicitly above (intensity/pos/etc) — not overwritten here
      case 0x69/0x6a: v = <colour component>; // colour-speed / colour members
      default:
        v = (cueCache ? AttributeCueTrackCacheEntry::Lookup(cueCache, key) : 0);  // value from merged cue cache
    }
    ref = ChannelValues::GetAttributeRef(out, key);
    write v into out at 1/2/4-byte width per AttributeType;   // IDENTITY: DMX byte == attribute value
}
SetStrobe()/SetShutterOpen()/SetShutterClosed();             // CH11 strobe path
```

**Means for renderer (decisive):**
- **Persistence is real and is the default.** Each cue's cache entry = previous
  cache entry **memcpy'd**, then **only the keys present in that cue's
  `AttKeyValueMap` are overwritten**. Channels omitted from a cue keep their
  prior value. This **binary-confirms** ssfile_format's "sparse cue patches
  update only encoded channels; they do not zero-fill omitted channels" and the
  layered-persistent-buffer model.
- **Identity DMX confirmed:** output byte = attribute value (only 8/16/32-bit
  width conversion by `AttributeType`); **no attribute→DMX transform and no
  effect engine** — matches the operator-confirmed model.
- **Cue application is Venue-gated:** keys not enabled for the current Venue
  fixture are ignored by the merge.
- **Initial state is all-zero** (`AttrValueInitZero`), matching the A5 all-zero
  anchor.

**Consequence for the New Sky residual (superseded by oracle closure):** because the
renderer **persists** omitted channels and writes only keys present in the cue's
map, the wire result `CH8/CH9/CH15 = 0/255/0` for `BUILDUP SPEEDUP` **cannot** be
a missing render-time mask/reset/layer rule. It is upstream and falls to one of:
the mismatch is upstream of the persistent renderer. Oracle canonicalization now
resolves all 367 New Sky event frames with no literal fallback. The earlier
cue-patch-suspect alternative is weakened; it must not be used to rewrite Venue
parsing without a controlled byte/capture contradiction for the resolved GUID.

**Validate:**
- Compare `parse_venue_cues.py`'s `AttKeyValueMap` decode for the New Sky
  effect-cue GUIDs (`WHITE`, `BUILDUP SPEEDUP`, `STROBE`, `MASTER STROBE`,
  `INTENSIFY`) against the raw `SoundSwitchVenues.bin` bytes — does the cue map
  actually contain CH8/CH15 keys the parser dropped?
- Re-run the A5 layered render: persistence + identity + all-zero init must stay
  16/16 exact (it does in the existing oracle).

**Confidence:** high (decompiled).

---

## Finding 3 — Deck composition (crossfade) lives in `RefreshCache`, above `SetChannelAttributes`

**Blocker addressed:** bridge-owned multi-deck composition / transport
(ssfile_format "Deck ownership and transport blockers").

**Pseudocode (`SSPlaybacks::RefreshCache_2PlayBackMode` @ `0x33799c`):**
```c
GetLightState(deckA -> SSLightBuffer A);     // SoundSwitchPlayBack::GetLightState
GetLightState(deckB -> SSLightBuffer B);
xa = byte[this+0x470]/255.0;  xb = byte[this+0x471]/255.0;   // crossfader weights
for (key : activeChannels) {
    intensity = lerp(A.intensity, B.intensity, xa);          // NEON fmadd blends
    colour    = CalculateColourFade(A.colour, B.colour, xa);
    pan/tilt  = lerp(A.*, B.*, xb);
    SetChannelAttributes(channel, cueCache, &intensity, &colour, &pan, &tilt, &strobe, out, staticLook);
}
```
A `RefreshCache_4PlayBackMode` variant exists (4-source composition).

**Means for bridge:** the per-deck light buffer and the **crossfade blend** are
SoundSwitch-internal; an offline renderer that owns transport/selection must
either reproduce the blend or render a single owning deck. For the current rig's
**single-owner Universe-0** surface this is mostly the single-deck path, but the
2-/4-playback blend is the reason temporal proximity never identified output
ownership in the captures.

**Confidence:** high (decompiled); exact crossfader byte semantics medium.

---

## Finding 4 — Fixture/group routing: partial, not closed here

**Blocker addressed:** group routing / 0x493↔0x496 mirror.

**Evidence:** `Venue::GetTrackForChannel(channel)` maps a channel/attribute key to
a track index (used to set the changed-track `utl::BitArray`); patch/addressing
classes `lxe::FixtureDmxMode`, `FixtureEntry`, `DMXRange`, `DMXMapItem`,
`DMXMapScene::signalSetUniverse(uint,bool)`. These confirm channel→track→DMX
addressing exists, but **this pass did not decompile the specific routing that
makes Venue groups `0x493` and `0x496` mirror**. That mirror remains as
documented (group records' parent/owner fields in `soundswitch_ssfile_format.md`)
and is **not** newly resolved.

**Confidence:** low / partial (not closed).

---

## What Ghidra did **not** resolve (still open per the closure handoff)

- **Legacy index literal base.** `AttributeCueTrackEntry::Read` reads a version-2
  index, but the binary path to a literal `raw − 1` was not traced; the one-based
  legacy convention remains **wire-proven**, not yet decompile-confirmed.
- **New Sky residual disambiguation.** Binary proves it is upstream of rendering
  but does not decide MIXED-reference (Finding 1) vs cue-patch-decode (Finding 2)
  — that needs the Venue-byte check named in Finding 2.
- **0x493/0x496 physical mirror**, the 17-byte auxiliary records, negative-time
  activation, `.ssa`/preset semantics — unchanged; binary internals alone do not
  unblock these.
- **Operator-capture-gated items** (transport unload-from-active-frame latency,
  one DIRECT-discriminating reference candidate, BLACKPINK holdout) are authority
  blockers Ghidra cannot touch.

## Net effect on AWR-107

- Reference-resolution model (Finding 1) and renderer model (Finding 2) are now
  **binary-corroborated**: GUID-keyed resolution + persistent layered buffer +
  identity DMX + venue-enable gate + all-zero init. Fail-closed-on-MIXED is
  correct and mechanism-grounded.
- The New Sky effect-cue residual is **re-classified from "missing renderer
  layer/mask/reset semantics" to an upstream parser/resolution issue** that is
  byte-validatable **without a new capture** — the highest-value next research
  step is the Venue-byte `AttKeyValueMap` re-check in Finding 2.
- No exporter/renderer readiness gate is newly *passed*; status remains
  **SOFTWARE/WIRE-VALIDATED ONLY — HARDWARE-UNVALIDATED** and exporter/runtime
  implementation stays deferred.

## Setup notes (GhidraMCP)

- GhidraMCP **is installed** at
  `~/Library/ghidra/ghidra_11.3.2_PUBLIC/Extensions/GhidraMCP/` (version-matched
  to Ghidra 11.3.2), but its `Module.manifest` contained **invalid keys**
  (`GHIDRA_MODULE_NAME=` / `GHIDRA_MODULE_DESC=` — those belong in
  `extension.properties`). Ghidra's manifest parser rejected lines 2–3, so the
  module's plugin never loaded and never appeared under **File → Configure**.
- **Fixed** by emptying the manifest (canonical-valid; 60/96 stock Ghidra
  manifests are empty); original saved as `Module.manifest.bak_invalid_keys`.
  Headless now reports **0 manifest errors**. To use MCP interactively the user
  must still restart Ghidra, enable the plugin (File → Configure), start its HTTP
  server, and run `bridge_mcp_ghidra.py` (its venv was missing `requests`; now
  installed).
- The existing GUI project `~/Desktop/Ghidra Projects/Soundswitch Reverse
  Engineer` was **empty** (binary opened but never saved/imported). For
  repeatable analysis use `analyzeHeadless` against an imported slice, as done
  here.
