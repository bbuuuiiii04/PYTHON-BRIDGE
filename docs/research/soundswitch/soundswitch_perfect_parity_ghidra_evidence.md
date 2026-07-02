---
doc_status: research-current
truth_level: binary-static-analysis-primary
last_verified_commit: 7b0bd6a
last_verified_date: 2026-07-01
validation_scope: Live read-only GhidraMCP decompile pass (server `ghidra`) against the loaded thin
  arm64 SoundSwitch 2.10.3 program, this session. Answers the five parity-critical questions raised
  by docs/plans/active/soundswitch_perfect_parity_finisher_spec.md (A.3.d gap-fill, cue-resolution
  mechanism, static-look composition, autoloop phase contract, note-96 selection). No process attach,
  no patch, no injection, no hardware, no bridge start/stop, no Export. Every function below was
  decompiled by address this session; addresses and structure match the prior-session records in
  soundswitch_ghidra_addendum.md and are now re-confirmed live rather than cited as prior evidence.
---

# SoundSwitch perfect-parity — Ghidra evidence packet

**Purpose.** Produce the missing binary evidence the finisher spec marks fail-closed
(`[ghidra-prior]`, A.3.d, A.4.c) and classify the scripted cue-resolution mechanism that explains the
AE9E3C61 / FC10FC02 / DD42028C divergences — from a **live** GhidraMCP pass, not a prior-session cite.

## Provenance (this session)

- Local app binary `/Applications/SoundSwitch.app/Contents/MacOS/SoundSwitch`, SHA-256
  `636ed4aa48287d019a96c60f8d9107e75f3e72abe4f7b0aa8fa54aaa661984e9` (re-hashed this session;
  matches the addendum). Universal `x86_64 arm64`; the loaded GhidraMCP program is the **thin arm64**
  slice (addresses `0x1002…`–`0x1004…`). x86_64 not separately decompiled.
- All decompiles below were produced live via `decompile_function_by_address`. Addresses are arm64.
- Method: read-only. GhidraMCP write tools (rename/comment/prototype) were **not** used.

## Bottom line (maps to the five questions)

| # | Question | Status | One-line result |
| --- | --- | --- | --- |
| 1 | Scripted-gap composition | **GHIDRA_CONFIRMED** | Scripted output = carry-forward cue cache seeded from an all-zero entry; **no** autoloop/base/default underlay. Only Static Look overlays; blackout is final mask. Gaps **hold** the prior cue; only pre-first-cue is dark. |
| 2 | Cue identity / resolution | **GHIDRA_CONFIRMED** | Exact-key `std::map` lookup of the saved timeline reference against the `.ssfile`'s **own serialized `(GUID, stored_key)` records**. No `-1`, no offset, no footer/prefix/shared-table remap. Mechanism is **embedded-per-file-table (dictionary) dependent**. |
| 3 | Static non-generic maps → CH1-19 | **GHIDRA_BOUNDED** | Intensity/strobe/colour/position are carried as **separate** overlays and applied via dedicated channel setters **independently of generic**. Whether they *reach* RAVE CH1-19 is profile-data-dependent and **not** decidable from these functions alone. |
| 4 | Autoloop phase contract | **GHIDRA_CONFIRMED** | `phase_tick = (beat_pos − window_start) × 600`; window length = `GetAutoLoopNumberBeats` (default 32 → 19200 ticks); window anchored to beatgrid tiling from beat 0; negative/pre-roll wrapped mod beatCount. |
| 5 | Note-96 / SSAutoLoop4 selection | **GHIDRA_CONFIRMED (mechanism)** | Selection is a generic learned `(data_byte, channel, type) → control-path` map, plus an internal index auto-rotation. Note 96 has **no intrinsic meaning**; reachability is a saved-mapping/operator-data question, not an SS mechanism. |

---

## Q1 — Scripted-gap behavior (does SoundSwitch composite a base/autoloop/static/default under scripted gaps?)

- **status: GHIDRA_CONFIRMED**
- **functions/symbols inspected (live):**
  - `SSPlaybacks::RefreshCache` `0x100338198`
  - `SSPlaybacks::RefreshCache_2PlayBackMode` `0x10033799c`
  - `SSPlaybacks::RefreshCache_4PlayBackMode` `0x100337d98`
  - `SSPlaybacks::SetChannelAttributes` `0x10033710c`
  - `AttributeCueTrackCacheEntry::Lookup` `0x1003c4960`
  - `AttributeCueTrackCache::Rebuild` `0x1003c1e38`
- **observed behavior:**
  - `RefreshCache` acquires the venue lock, picks the static cache pointer (`this+0x4a0` override index,
    else `this+0x49c` normal index, else null), then dispatches to `RefreshCache_2PlayBackMode` or
    `RefreshCache_4PlayBackMode` with `(ChannelValues* out, StaticLookCache* static)`.
  - Its autoloop block does **only** `AutoLoopsManager::GetActivePlayback` → `GetCurrentIndex` /
    `GetProgress` → `AutoLoopsManager::SetCurrentAutoLoopState(index, progress)`. It writes **no channel
    values** into the output `param_1`. Autoloop here updates *manager UI state*, not DMX.
  - `RefreshCache_2PlayBackMode`: the per-channel base comes from
    `SoundSwitchPlayBack::GetLightState(...)` → an `AttributeCueTrackCacheEntry*` (the scripted cue
    cache), passed as `param_2` into `SetChannelAttributes`. In `SetChannelAttributes` the generic
    channel value is `param_2 == 0 ? 0 : AttributeCueTrackCacheEntry::Lookup(param_2, channelKey)`,
    then optionally overlaid by the Static Look generic cache (`param_9 + 0x38`). `Lookup` is a dense
    array read: `param_1 < count ? array[param_1] : 0`.
  - `AttributeCueTrackCache::Rebuild` builds the cache: it first pushes an **all-zero** entry
    (`operator_new(0x60)` + `utl::ArrayInit<AttrValueInitZero>(0x20)` → 32 zeroed attribute slots),
    then for each timeline entry constructs `AttributeCueTrackCacheEntry(time, <previous cache entry>,
    attrMap, venue)` — i.e. **each entry is seeded from the previous entry** and overlays this cue's
    converted attributes (carry-forward / snap-and-hold). Entries whose converted attribute map is
    empty/unflagged (`*(entry+0xd0)==0 && (begin==0 || end==0)`) are **skipped** — no new boundary,
    the prior hold continues.
- **conclusion:** SoundSwitch does **not** composite an autoloop, base, or default look under a
  scripted track's gaps. The scripted DMX is a pure carry-forward step function over the cue cache:
  **dark before the first cue** (all-zero seed), and **holds the last cue's values through gaps**
  after it. The only thing layered over the scripted base is a **Static Look/Override** cache (per-
  channel overlay in `SetChannelAttributes`), and blackout/emergency as a final intensity/shutter mask.
- **implication for Codex:** This **resolves spec A.3.d against the autoloop-gap-fill hypothesis.**
  Where U0 is lit and the pack is dark, the cause is exporter-side, in one of two shapes: (i) U0 lit
  **before** the pack's first event ⇒ SS's cache holds an **earlier cue the exporter dropped/mis-timed**
  (the exporter must extract that earlier cue); (ii) U0 lit **through a mid-track gap** where the pack
  goes dark ⇒ the exporter/renderer is **not reproducing the carry-forward hold** (must hold the last
  cue's channel values until the next cue, seeded from all-zero). Do **not** add an autoloop-under-
  scripted compositor (Task C3's "branch (i)"); implement the exporter cue-timing + snap-and-hold branch.
  Keep Static Look as the only overlay; keep blackout as the final mask.
- **remaining uncertainty:** The exact "skip empty cue → hold" edge (an unresolved/empty cue holds prior
  rather than blanking) is confirmed structurally but its interaction with a *mis-resolved* cue (Q2) is
  data-dependent; the oracle should still confirm the held value per boundary.
- **blocks byte-exact parity?** **No.** This finding *removes* a fail-closed unknown (A.3.d) and points
  the fix at exporter cue-timing + hold. Parity remains gated on the exporter reproducing the hold and
  the cue values (Q2), not on any unresolved binary behavior.

---

## Q2 — Scripted cue identity / cue-resolution mechanism (explains AE9E3C61, FC10FC02, DD42028C)

- **status: GHIDRA_CONFIRMED**
- **functions/symbols inspected (live):**
  - `AttributeCueTrackEntry::ReadEntry` `0x1003c16ac`
  - `AttributesCueMap::Read` `0x1003c0f00`
  - `AttributesCueMap::AttributesCueMap(AttributesCueLibrary&)` (writer ctor) `0x1003c0c2c`
  - `AttributeCueTrackCacheEntry::Lookup` `0x1003c4960` (consumer side)
- **observed behavior:**
  - `AttributesCueMap::Read` reads, per record, a **16-byte GUID** (`InStream vtbl+0x60`, len 0x10) and
    then a **`u32 stored_key`** (`InStream vtbl+0x40`). It builds two trees: a GUID→key map (`this`)
    and a **key→GUID map** at `this+0x20` (node key at `+0x20`, GUID stored at `+0xa8/+0xb0`). The key
    is the **file's serialized `stored_key`** for that record — read verbatim from the file, not derived.
  - `AttributeCueTrackEntry::ReadEntry` reads the entry `<u32 version, u32 constant, i32 time,
    u32 raw_reference>`, then looks `raw_reference` up in the cue map's **key→GUID tree** (`param_2+0x20`)
    with a libc++ `lower_bound`-then-equality descent: it keeps the smallest node with `key >= raw`,
    then requires `key <= raw` — i.e. **exact key match `key == raw_reference`**. On a miss it falls to
    the end sentinel (`param_2+0x20` itself) and copies a null/default GUID (no cue). The resolved GUID
    (`+0xa8/+0xb0`) is copied into the entry (`this+0xb8/0xc0`). **No subtraction, no offset, no second
    table** is consulted after the lookup.
  - The writer ctor `AttributesCueMap::AttributesCueMap` assigns keys `iVar8 = 0, 1, 2, …` in
    `AttributesCueLibrary::GetAttributesCues()` order — i.e. a fresh export writes **0-based, library-
    order** keys. But `Read` (above) always consumes the **file's stored keys**, which for an
    edited/aged project are a **permutation**, not necessarily current library order.
- **conclusion:** Cue identity is resolved by an **exact-key `std::map` lookup of the saved
  `raw_reference` against the `.ssfile`'s own embedded `AttributesCueMap`**, whose `(stored_key → GUID)`
  entries are serialized in the file. Classifying against the spec's candidate list:
  - **NOT `raw_reference − 1`** — the binary performs no subtraction; it is a direct exact match.
  - **NOT a global "direct" rule either** — "direct" only looks correct when the file's stored_keys
    happen to be contiguous library order; the true resolution is whatever the file's serialized map
    says.
  - **IS cache/dictionary dependent** — specifically the per-file embedded `(stored_key → GUID)` table.
    The correct value is `fileMap.at_exact(raw_reference)`.
  - **NOT** footer/prefix/shared-table dependent, **NOT** inherited from prior cache state (identity is
    per-entry), **NOT** affected by hidden/default cue maps.
  - This **explains** all three witnesses: the bridge's `raw−1` (or any single offset) matches only the
    rows where the file's `stored_key == raw−1`. **DD42028C** — the root-cause table
    (`soundswitch_pack_parity_root_cause_spec.md:170-217`) shows a non-monotone permutation
    (raw 186→key 187, raw 188→key 187, raw 4→key 2/3), and brute-force `raw−1=69/91`, `direct=27/91`,
    none=91/91 — the exact signature of "true rule = the file's embedded permutation, not an offset."
    **AE9E3C61** CH10/CH11 `(255,255)`="MASTER STROBE" vs U0 `(110,0)`="STROBE" is the bridge resolving
    to the **library-adjacent** GUID — a classic wrong-permutation-neighbor, i.e. an offset picked the
    neighbor instead of `fileMap[raw]`. **FC10FC02**'s near-total divergence is a file whose embedded
    map is far from any single offset.
- **implication for Codex:** Resolve cue identity by **parsing each `.ssfile`'s embedded
  `AttributesCueMap` `(GUID, stored_key)` records and doing an exact-key lookup of `raw_reference`
  (no offset, no library-order reconstruction, no nearest-key)**. This is precisely the "resolve from
  saved bytes per layout, proven per-boundary against U0" mandate of Task C4, and it is the concrete
  reason the global-offset approach is rejected (`soundswitch_pack_parity_root_cause_spec.md:214-217`,
  `:499-501`). If a file's serialized map cannot reproduce U0 by exact key, the document is
  `unverified_parity` — do not fall back to an offset.
- **remaining uncertainty:** The binary proves the *lookup semantics* and that the key is file-serialized.
  It does **not**, on its own, tell you whether the **current bridge decoder** already parses the file's
  serialized keys or reconstructs them from library order + `raw−1`; that is a bridge-code check
  (`soundswitch_project_decoder.py:538-544`) the oracle/Task C4 must make. A miss-to-sentinel yields a
  null/empty cue which then **skips** in the cache rebuild (Q1) — the per-boundary held value on a miss
  should be oracle-confirmed rather than assumed dark.
- **blocks byte-exact parity?** The **mechanism** is fully resolved (unblocks the fail-closed cue
  question). Byte-exact parity is blocked **only** until the resolver is switched to file-embedded
  exact-key resolution and the captured witnesses (AE9E3C61, FC10FC02) pass the U0 oracle; DD42028C
  stays the negative control. No unresolved *binary* unknown remains here.

---

## Q3 — Static look composition (can non-generic maps affect CH1-19 independently of generic?)

- **status: GHIDRA_BOUNDED**
- **functions/symbols inspected (live):**
  - `SSPlaybacks::RebuildStaticLookCache` `0x100335230`
  - `StaticLook::Read` `0x10033aa6c`
  - `SSPlaybacks::SetChannelAttributes` `0x10033710c`
- **observed behavior:**
  - `RebuildStaticLookCache` builds, for each of the **32** static slots, a `StaticLookCache` with
    **separate** sub-structures: an intensity map (`SetValueForTypeChannelKey(key, type=1,
    frac*100*0x28f5c28)`), a strobe map (`type=0x29`), a **colour** tree (keyed by channel), a
    **position** map for pan/tilt channels (`type=3` pan, `type=4` tilt, resolved via
    `PositionLibrary`/`SoundSwitchPosition`), and a **generic** attribute map built by
    `Venue::ConvertAttributes`. Intensity and strobe are stored as scaled fractions of the look's
    per-channel float values.
  - `StaticLook::Read` (version ≤ 5) reads name, the four fixture maps (intensity, strobe, colour,
    position) and — for version ≥ 3 — a generic `SSAttrValueMap`. Confirms the five distinct payloads
    per look.
  - `SetChannelAttributes` consumes them: when a static cache is present it **overwrites** the local
    colour (`param_4`), pan (`param_5`, type 3), tilt (`param_6`, type 4), intensity (`param_3`,
    type 1) and strobe (`param_7`, type 0x29) from the static cache trees **before** the per-channel
    emit loop. The emit loop then switches on **each channel's attribute type**
    (`*(chanMap+0x118)+chan*0x68+4`): types `1..4, 0xb..0x10, 0x29` are emitted from the dedicated
    `SetIntensity/SetColour/SetPan/SetTilt/SetStrobe` path (which already folded in the static
    intensity/strobe/colour/position), while the `default` type is emitted from
    `cueLookup ⊕ static-generic`. So intensity/strobe/colour/position reach DMX **independently of the
    generic map**, gated by the channel's declared attribute type.
- **conclusion:** Structurally, **yes** — the four non-generic maps are first-class overlays that can
  drive CH1-19 without going through `generic_attributes`. The prior claim that "the generic map
  contains the exact active CH1-CH19 output" is therefore **not** a binary invariant; it holds **only**
  under profile-data conditions the binary cannot self-verify: the RAVE 19-ch profile must have **no
  intensity-typed channel** (so `param_3` never lands), **strobe fractions == 0.0** (so `param_7`
  contributes nothing), **no pan/tilt-typed channel or a null position target** (so `param_5/6` are
  inert), and **colour** must resolve to the same value the generic map would produce.
- **implication for Codex:** This **upgrades Task C6 from belt-and-suspenders to necessary.** The
  export-time assertion must actually verify, against the RAVE profile's per-channel attribute **types**
  and the stored static-map **values**, that intensity has no channel, strobe==0.0, position has no
  pan/tilt target, and colour==generic — per slot. Any slot that violates it (non-empty colour/strobe/
  position that *would* map to a CH1-19 attribute type) must be flagged `unverified_parity`, not exported
  as a silent generic-only frame. Do **not** assume generic-only from the runtime; prove it from the
  profile + look bytes.
- **remaining uncertainty:** The RAVE profile's per-channel attribute **type table** and the specific
  stored static-map values are **not** in these three functions — they live in the venue/profile data
  (`Venue`/`ChannelMap`/fixture-mode records) and the `static_looks` bytes. The generic-only conclusion
  is **assumed-until-asserted**, not binary-proven.
- **blocks byte-exact parity?** For the **8 authored + 3 live-mapped** looks already byte-matched in the
  capture, no. For the **21 empty-generic default slots**, byte-exact parity of their (zero) output is
  **conditionally blocked** until the C6 profile/colour assertion proves the four maps are inert;
  otherwise those slots must be `unverified_parity`. The block is closed by an **assertion over profile
  data**, not by any further binary decompile.

---

## Q4 — Autoloop phase / origin / quantization / cycle length / anchoring

- **status: GHIDRA_CONFIRMED**
- **functions/symbols inspected (live):**
  - `AutoLoopLayout::GetStateForTime(int)` `0x10025f000`
  - `AutoLoopLayout::buildAutoLoopForStartingBeat(int, bool, int)` `0x10025f22c`
- **observed behavior:**
  - `GetStateForTime(time)`: `beat_pos = BeatSpace::getBeatPosFor(this+0x18, time)` (double). Stores the
    integer beat at `this+0xa0`. Negative/pre-roll beats are wrapped forward:
    `beat += beatCount + beatCount*(|beat|/beatCount)` (modulo `beatCount`, keeping phase in
    `[0, beatCount)`).
  - The active layout stores `start_beat` (`piVar6[1]`), `end_beat` (`piVar6[2]`), `beatCount`
    (`piVar6[3]`), index (`*piVar6`), and phase (`piVar6[7]`). If the wrapped beat is **inside** the
    window, `phase_tick = (int)((beat − start_beat) * 600.0)`. If it has **exited** the window
    (`beat < start_beat` or `beat ≥ end_beat`), it calls
    `buildAutoLoopForStartingBeat(this, (int)beat, false, index_or_-1)` to re-anchor, then recomputes
    `phase_tick = (beat − new_start_beat) * 600` (stored at `piVar6[7]`).
  - `buildAutoLoopForStartingBeat`: `beatCount = SoundSwitchDocData::GetAutoLoopNumberBeats(doc)`
    (fallback **0x20 = 32**), clamps the starting beat non-negative
    (`param_1 & (param_1>>31 ^ ~0)`), sets `start = startingBeat`, `end = startingBeat + beatCount`.
    A negative `param_3` (index) triggers the internal **index auto-rotation**; a non-negative `param_3`
    selects a specific index from the bank array. (`AutoLoopLayout::AutoLoopLayout` — per the addendum —
    builds the first window from **beat 0**.)
- **conclusion:** The autoloop phase contract is:
  - **ticks/beat = 600** (literal `* 600.0`), integer-truncated quantization.
  - **phase_tick = (beat_pos − window_start_beat) × 600**, `beat_pos = BeatSpace::getBeatPosFor(time)`.
  - **cycle length = `GetAutoLoopNumberBeats`** (default 32 beats → **`phase_tick ∈ [0, 19200)`**,
    matching the capture's observed `[0, ~19198]`).
  - **origin/anchor = the beatgrid**: the first window is built from **beat 0**; each subsequent window
    re-anchors to the integer beat at which the prior window expired, so window starts **tile forward
    in `beatCount` (32-beat) steps from beat 0**. Pre-roll/negative time wraps modulo `beatCount`.
- **implication for Codex (Task C7 anchor):** Lock the phase contract as **derived from the beatgrid**,
  not from the observed scene-change edge: `window_start = beat0 + k·beatCount` (the 32-beat tile
  containing the current beat), `phase_tick = (beat_pos − window_start) × 600`, `beatCount` from the
  loop document (`GetAutoLoopNumberBeats`, not hard-coded 32 unless the doc says so). This confirms the
  spec's concern that an **edge-observation anchor can carry a latency offset** vs SS's beatgrid-aligned
  window and must be corrected. Do not regress the landed phase-zero guard.
- **remaining uncertainty:** The exact **first-window origin** depends on (a) how the track's beatgrid
  defines beat 0 / downbeat (`BeatSpace`/`SeratoBeatGrid`, not decompiled here) and (b) any
  `OverrideAutoLoop` starting index/beat the operator/manager injects. Whether 32-beat tiling coincides
  with musical **phrase** boundaries is true only if the beatgrid's beat 0 is phrase-aligned — a
  beatgrid-data property, not proven by these two functions.
- **blocks byte-exact parity?** The **phase math** is fully resolved (unblocks A.4.c on the SS side).
  Parity of a specific captured loop is blocked only until the bridge's `window_start` is confirmed to
  derive from the same beatgrid tiling and the oracle reproduces U0 phase on the captured loops — a
  bridge-vs-U0 comparison, not a binary unknown.

---

## Q5 — Autoloop selection / note 96 (reachable via saved mapping, or absent/out-of-scope?)

- **status: GHIDRA_CONFIRMED (mechanism); reachability is a data question**
- **functions/symbols inspected (live):**
  - `NamedControlMapCollections::newControlMapping(MIDIDevice, MIDIMessage*, Control*)` `0x10013c240`
  - `MIDIControl::operator>>(Recordable&, ControlMapDetail&)` `0x10012f674`
  - `AutoLoopLayout::buildAutoLoopForStartingBeat` `0x10025f22c` (internal index rotation, Q4)
- **observed behavior:**
  - `newControlMapping` extracts the MIDI **data byte** (`message+1`, or `+0x18` for pitchbend), the
    **channel** (`status & 0x0f`), and a **type** (`0xB0→1` CC, `0xE0→2` pitchbend, else `0` note), and
    builds a `ControlMapDetail{ data_byte, channel, type, control_path (string), enabled=1 }` keyed by
    device string. Dedup/lookup matches on the tuple `(data_byte, channel, type)`. There is **no**
    special-case for any particular data byte (no note-96 branch).
  - `operator>>(ControlMapDetail)` deserializes exactly `(data_byte, ?, channel, control-path string,
    enabled bool)` — a generic learned binding record.
  - Autoloop index selection reaches a given bank/index through either (a) a learned control whose
    `control_path` targets that autoloop selection, or (b) the **internal auto-rotation** in
    `buildAutoLoopForStartingBeat` (the `param_3 < 0` path advances the index with **no MIDI input**).
- **conclusion:** In SoundSwitch, **note 96 has no intrinsic meaning.** Selection is a generic
  `(data_byte, channel, type) → control-path` learned map plus a beat-driven internal index rotation.
  `SSAutoLoop4` (index 4) is reachable **iff** either a saved `ControlMapDetail` binds a MIDI event
  (e.g. note 96) to its selection control-path, **or** the internal rotation reaches index 4. This is
  fully consistent with the spec's capture finding: the binding `(channel 0, data 96) → SSAutoLoop4`
  **exists** in `selection_map.json`, but the **bridge's** scene resolver never *emits* note 96. That
  is a **bridge selection-policy gap**, not an SS mechanism gap or an SS-side "absent mapping."
- **implication for Codex (Task C7 selection):** Treat note-96 reachability as a **bridge resolver**
  concern, not a SoundSwitch behavior to reverse-engineer further. Either map the drop-policy condition
  to note 96 in the scene resolver so the existing binding fires, **or** mark `SSAutoLoop4`
  `unverified_parity` and surface it (don't claim autoloop-complete while a mapped loop is unreachable).
  No hardcoded SSID/cue fix; no invented SS semantics for note 96.
- **remaining uncertainty:** Whether the operator *intends* note 96 to be operator-driven (a "BY GENRE"
  mapping) vs resolver-driven is an operator-policy decision, not a binary fact. The binary only proves
  the mechanism is data-driven and note-agnostic.
- **blocks byte-exact parity?** **No.** This is a selection/trigger reachability question, orthogonal to
  per-cue byte parity of the rendered frames. It affects *which* loop is chosen, not whether a chosen
  loop renders byte-exactly (that is Q4). It should be surfaced/flagged, not treated as a parity blocker.

---

## What this packet closes vs. leaves open (for the finisher spec)

- **Closed (fail-closed unknowns now answered from the binary):**
  - **A.3.d gap-fill** → CONFIRMED **not** autoloop gap-fill; scripted is carry-forward hold + static
    overlay only. Fix is exporter cue-timing + snap-and-hold (Q1).
  - **Cue-resolution mechanism** → CONFIRMED exact-key lookup against the file's embedded `(stored_key
    → GUID)` map; no offset. Explains AE9E3C61 / FC10FC02 / DD42028C (Q2).
  - **A.4.c anchor origin** → CONFIRMED beatgrid-tiled 32-beat windows from beat 0, `phase=(beat−start)
    ×600`, 600 ticks/beat (Q4).
  - **Note-96 selection** → CONFIRMED SS has no note-96 semantics; it's a bridge resolver gap (Q5).
- **Still bounded (need profile data / oracle, not more binary):**
  - **Static non-generic → CH1-19** (Q3) — needs the RAVE profile channel-type table + static-map
    values; enforce via the Task C6 export assertion, flag violators `unverified_parity`.
  - Per-boundary **U0 value proof** for the resolved cues and the held gap frames — the offline oracle
    (Task C1) against the existing capture, not a decompile.
- **No new capture, no bridge action, no hardware were required or performed for this packet.**

---

## 2026-07-02 parity-evidence finisher addendum

This packet remains the static/binary evidence boundary, not the runtime proof
itself. The static addendum confirms SoundSwitch's static/control lookup is
data-driven and exact enough to support the C6 non-generic assertion path, but
the accepted runtime proof chain is the passive SoundSwitch U0 capture plus the
offline oracle/registry lanes. After the zero-seeded Autoloop-cycle fix, Static
Looks are `algorithm_generalized` from the C6 assertion and the documented
unavailable static windows, and `SSAutoLoop52.ssfile` / `SSAutoLoop54.ssfile`
are oracle-proven. At that earlier checkpoint, no new Ghidra fact promoted the
remaining scripted blockers and trusted publication was still blocked; see the
closeout addendum below for the later software-gate result.

## 2026-07-02 parity-evidence finisher closeout addendum

The later software closeout did not add new Ghidra facts. It changed the proof
chain by rebuilding the passive-capture Autoloop fixture with contiguous
sidecar segments, keeping only PASS Autoloop rows in the positive registry,
recording non-PASS capture segments in the divergence ledger, and generalizing
only across the supported loaded-layout family when every positive cue resolves
into the current venue cue set. Fresh software export then reports active lanes
`algorithm_generalized: 69`, `oracle_proven: 14`, `unverified_parity: 0`;
inactive unverified documents remain reported separately. This clears the
trusted publication software gate only. It is still not live sender, Enttec, or
physical fixture validation.

---

## Addendum — 2026-07-02 (appended; recorded findings above are unchanged)

Byte evidence (261/261 samples from capture `parity_20260701T185231Z`, plus the legacy A5 wire
capture at 16/16, operator UI/timeline ground truth, the operator's live cue editor, and a fresh
SoundSwitch re-bake of `{FC10FC02-…}.ssfile` used as a serialization Rosetta) resolved the Q2
reconciliation recorded above:

- **"The lookup IS exact" was literal.** Timeline reference resolution is `stored_key ==
  raw_reference` in the file's own serialized numbers (ref 0 remains the clear sentinel). The
  "raw−1 is a bridge label space" reconciliation is superseded.
- The compensating error it was masking: **Venue cue values are precede-associated** — each
  `(name, guid)` identity owns the attribute block that the linear scan frames under the
  PREVIOUS record. The shipped `R − 1` + follow-values pipeline was two cancelling off-by-ones,
  byte-equivalent wherever a document's dictionary is venue-consecutive (every witness), and
  divergent exactly at splice points (DD42028C, ae9e3c61, fc10fc02, and the formerly
  "capture-diverged" Autoloops).
- Consequences: all 233 Venue records are render-bearing cues (the `minimal_default_catalog_tail`
  "cue" was an artifact of the same framing bug; the catalog-index block is file-tail metadata);
  the first identity's value block lives in the venue file's unparsed head region (recovered: the
  cue named `OFF` writes all zeros); a `01000000` marker separates each value block from the next
  record (232/232 gaps).
