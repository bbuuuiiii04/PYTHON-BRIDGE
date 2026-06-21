---
doc_status: research-closure
truth_level: byte-capture-and-binary-grounded
last_verified_commit: 8697587
last_verified_date: 2026-06-20
validation_scope: read-only byte/capture/test analysis + static binary analysis (Ghidra headless, nm/c++filt/otool); no SoundSwitch modification, no live attach, no bridge/runtime/MIDI/DMX change; SOFTWARE/WIRE-VALIDATED ONLY — HARDWARE-UNVALIDATED
---

# SoundSwitch Reverse-Engineering — Closure Report & Implementation-Readiness Verdict (AWR-107)

This report reconciles the SoundSwitch RE work to a single implementation-readiness
verdict for the **exporter** (read SoundSwitch-authored content into a
bridge-owned lighting pack) and the **bridge-native DMX player** (reproduce
SoundSwitch's Universe-0 CH1–19 output without SoundSwitch running).

Source-of-truth order (AGENTS.md §1): executable code / current bytes / wire
captures win; Ghidra/binary evidence corroborates and explains. Where a binary
read appeared to contradict wire proof, **wire proof governs** and the binary
read is marked uncertain.

Companion docs: `soundswitch_ghidra_addendum.md` (binary evidence),
`soundswitch_ssfile_format.md` (byte format), `soundswitch_scripted_renderer_closure_handoff_spec.md`
(prior measured state). Codex implementation spec:
`docs/plans/active/soundswitch_importer_exporter_player_codex_spec.md`.

---

## 1. Verdict (read this first)

**RE is CLOSED ENOUGH to begin implementation of two things now, behind a
fail-closed provenance gate:**

1. **Lighting-pack EXPORTER** for *clean single-provenance* content — autoloops
   and clean scripted tracks (uniform one-based legacy **or** uniform direct) —
   plus the Venue cue library, fixture/channel model, and track map.
2. **Bridge-native offline DMX PLAYER** that reproduces SoundSwitch's
   Universe-0 CH1–19 output via the now-confirmed render model
   (persistent layered buffer + identity DMX + Venue-enable gate + all-zero init).

**Edited / MIXED-provenance active tracks (TITANIUM / Opalite / New Sky) are NOT
fail-closed dead-ends — they are resolved via oracle canonicalization** (see §10).
The MIXED reference ambiguity is byte-undecidable *from the stored file alone*,
but the existing Art-Net captures + the Venue cue library reconstruct each track
as a verified `(elapsed → cue composition / literal frame)` pack that is
byte-exact by construction. New Sky resolves 100% to clean cues; Opalite/TITANIUM
96–97% to cues with the remaining 1–2 events stored as literal frames, so
**playback is byte-exact for all three**.

**Blocked / explicitly NOT for v1:**

- **Physical hardware / Enttec / two-laser fixture output validation** — always
  operator-gated; passive Art-Net is wire evidence only.
- A handful of structural unknowns (auxiliary 17-byte records, negative-time
  activation, footer-addressed scripted layouts, demo layout) that do **not**
  block the clean path or the oracle path and must remain fail-closed.

The render model is not the blocker, and MIXED is no longer a content blocker for
the active tracks. The residual quality item is that two tracks rely on 1–2
literal-frame entries and TITANIUM's capture should be confirmed single-deck; a
single clean recapture per track (operator action) upgrades them to 100% cue
resolution but is **not required** for byte-exact playback.

---

## 2. Claim ledger

Status key: **C** confirmed · **W** weakened · **X** contradicted · **O** obsolete · **U** unresolved.
Evidence: B=bytes/parser, T=tests, W=wire capture, G=Ghidra/binary.

| # | Load-bearing claim | Status | Evidence |
|---|---|---|---|
| 1 | `.ssfile`/Venue/catalog container = `AA AA 09 55` magic + `u32 version` (corpus = v3); Qt strings `[u32 count][UTF-16LE]`; 16-byte GUIDs | **C** | B |
| 2 | Render = **persistent layered buffer**: new state = previous state with only the cue's present keys overwritten; omitted channels persist | **C** | G (`AttributeCueTrackCacheEntry` merge-ctor `@0x3c4710` memcpy prev + overwrite present), B (A5 16/16), W |
| 3 | DMX output is **identity** (channel byte = attribute value, only 8/16/32-bit width); **no effect engine, no attribute→DMX transform** | **C** | G (`SSPlaybacks::SetChannelAttributes @0x33710c`), operator-confirmed |
| 4 | Cue patch application is **Venue-enable gated** (keys not enabled for the current fixture are ignored by the merge) | **C** | G (merge-ctor `isAttrEnabled(key)` guard) |
| 5 | Initial render state = **all zero** (`utl::Array<AttrValueInitZero>`); A5 fits all-zero init with no captured frame as input | **C** | G, B, W |
| 6 | Cue identity is a **GUID** (`sys::ClassId` = RFC-4122 UUID); cue/Venue refs resolve through GUID maps | **C** | G (`ClassId::FromRfc4122`, `AttributesCue::Read(.., map<ClassId,Venue*>)`), B |
| 7 | On-disk per-track cue **dictionary entry = `[16-byte GUID][u32 LE cue_index]`**, version-prefixed; bridge `[3 zero][16 GUID][u8]` framing is the same bytes and agrees on cue_index | **C** | G (`AttributesCueMap::Read/Write`), B (A5 RBSD cue_index=90 both framings) |
| 8 | `cue_index` is **not** stable identity (GUID is); editing renumbers `cue_index` and rewrites refs | **C** | G, B (8697587 WHYB pair) |
| 9 | Cue-reference convention is **provenance-dependent**: clean legacy = one-based (`cue_index = raw−1`), clean new = direct (`cue_index = raw`); A5 one-based is wire-proven (16/16) | **C** | W (A5), B |
| 10 | **Editing a legacy file → MIXED** (old records one-based, renumbered records direct) with **no per-record byte discriminator** | **C** | B (8697587), G (timeline record `version`=1 and `field_a/field_b`=(1,1) for **both** clean and MIXED New Sky records — does **not** discriminate) |
| 11 | MIXED / ambiguous provenance must **fail closed** before rendering | **C** | B (validator exit-2 on `--reference-rule mixed`), T |
| 12 | New Sky / `BUILDUP SPEEDUP` residual = **wrong-cue resolution from MIXED provenance**, NOT a parser bug and NOT a render gap | **C** (newly resolved) | B (`BUILDUP SPEEDUP` Venue patch genuinely `{15:207}`, `entry_count=2` read straight; renderer persistence proven), W (report: low raw-refs 1/2/3/4/13 resolve wrong under one-based with non-uniform offset; high refs exact) |
| 13 | `parse_venue_cues.py` decodes cue patches **byte-correctly** for the supported records (19-channel attribute set; rejects whole record on any invalid entry → fail-closed) | **C** | B |
| 14 | Channel surface = **Universe-0, base channel 1, footprint 19**; Universe-1 zero in every captured frame | **C** | W (123k frames) |
| 15 | Venue fixture groups `0x493` and `0x496` produce **identical** Universe-0 comparisons (mirror) for every captured track | **C** | W, B |
| 16 | Autoloop layered model reproduces **29/30** distinct bridge-used wire frames under `position-cue(one-based) ⊕ color-cue(CH8/9) ⊕ persist(8,9,11)`; lone miss is the all-zero blackout | **C** (autoloop scope) | W, B |
| 17 | Raw-reference `0` = **clear**: zeroes the main/position layer; control channels (CH8/CH9 color, CH11 strobe) persist until next cue; idle/stop/unload = all-zero | **C** (autoloop + A5 + transport scope) | W, B |
| 18 | "Autoloops are uniformly direct" | **O** | superseded by claim 9 (autoloops are one-based legacy, wire-proven) |
| 19 | "`cue_index = raw − 1` applies uniformly" / "high time `0xFFFFFF` is a −1 sentinel" | **O/X** | superseded: provenance-dependent; negative pre-roll times are real signed values |
| 20 | "Missing/expanded dictionary size discriminates edited files" | **X** | 8697587 (A5 is full-bank yet one-based) |
| 21 | TITANIUM 25% / Opalite 58% / New Sky 83% event-exact under one-based | **C** | W (final reports) |
| 22 | TITANIUM low exactness is a render-model gap | **X** | W: misses are high-ref MIXED + 13 clear-events retaining CH8/CH9 + one cue name showing 4 distinct observed wire states (multi-deck/MIXED cascade), not a static-render defect |
| 23 | Transport: position-based render is correct where the underlying static model is correct (backward/forward seek, 22/22 loop, re-fire all exact); stop/unload = all-zero exact | **C** | W (Opalite transport pcap) |
| 24 | Scripted pre-first-beat placement stores `elapsed = 0` (not negative); autoloop pre-roll uses signed-negative ticks | **C** | B (8697587), operator-confirmed |
| 25 | Scripted-track detection must be from `{SSID}.ssfile` bytes + TrackMap, never a UI "scripted" flag (lazy rediscovery) | **C** | operator-confirmed |
| 26 | Auxiliary 17-byte records (72 nonzero across files 2/7/35/48/50), negative-time activation, shared-table semantics | **U** | not render-explained; not on the clean path |
| 27 | Footer-addressed scripted layouts (7 files) and the no-shared-anchor file are structural-only (no representative wire) | **U** | B; fail-closed until wire |
| 28 | Physical fixture membership / how 4 instances mirror Universe-0 CH1–19 | **U** | not needed if exporter emits the 19-ch frame; physical mapping is operator/config |

---

## 3. Resolved findings (what closed this pass)

1. **New Sky / BUILDUP SPEEDUP is a MIXED resolution case, decisively.**
   `parse_venue_cues.py` decodes `BUILDUP SPEEDUP` (`c6c9d740…`) as `{15:207}`
   per group with `entry_count=2` read straight from the record header — i.e. the
   parser is **not** under-reading. The render model **persists** omitted
   channels (Ghidra merge-ctor), so if BUILDUP SPEEDUP applied, CH8 would persist
   `172` (from prior `WHITE`) and CH15 would become `207`. The wire shows
   `CH8=0, CH15=0`. Therefore the active wire cue is **not** the cue the timeline
   reference resolved to. The final report confirms: `WHITE` raw14→idx13 is exact,
   but the adjacent effect-cue refs (raw 1/2/3/4/13) resolve wrong under one-based
   with a **non-uniform** per-record offset. This is the MIXED signature →
   fail-closed correct. Parser bug ✗, renderer gap ✗, missing bytes ✗.

2. **The render model is fully specified and confirmed** (claims 2–5). The
   bridge-native player can be built from it directly (see Codex spec §"player").

3. **The dictionary on-disk layout is confirmed `[16 GUID][u32 cue_index]`** and
   the bridge's existing cue_index reads are correct (A5 RBSD = 90, wire-proven
   one-based from raw 91). No dictionary parser bug.

4. **No byte-level MIXED discriminator exists.** The per-record `version` field
   (read first by `AttributeCueTrackEntry::ReadEntry`) and the timeline
   `field_a/field_b` are identical (`1`,`(1,1)`) for both clean and MIXED New Sky
   records. This independently confirms the prior "no discriminator" conclusion
   and makes fail-closed the final, evidence-grounded blocker for edited files.

5. **Three failing tracks classified** (claim 21–22): all are edited
   default-project files exhibiting MIXED references; TITANIUM additionally shows
   multi-deck/animation cascade. None indicates a render-model defect.

---

## 4. Remaining unknowns (do NOT block v1; keep fail-closed)

| Unknown | Why it doesn't block v1 | What would close it |
|---|---|---|
| MIXED auto-resolution | v1 exports only clean-provenance content + fails closed otherwise | A per-file provenance manifest (known clean files + convention) **or** a wire/playback oracle per file |
| Auxiliary 17-byte records / negative-time activation | Absent from the clean autoloop+A5 render path that already validates | Controlled diff on files 2/7/35/48/50 + wire |
| Footer-addressed + no-anchor scripted layouts (8 files) | Parsed structurally only; excluded until wire-validated | Representative operator capture per layout |
| In-App Demo layout | Already declared unsupported | n/a (permanently excluded) |
| Physical fixture mirror / Enttec address | Exporter emits the Universe-0 19-ch frame; physical patch is config/operator | Operator hardware validation (HW-002) |
| `.ssa` / `.sspreset` / recordable `.dat` semantics | Not render-affecting in current evidence | Controlled diff if ever proven render-affecting |

---

## 5. Blocker classification

| Blocker | Class | Disposition |
|---|---|---|
| MIXED edited-file reference resolution | **byte-undecidable** | Fail closed; require provenance manifest or wire oracle. NOT a v1 dependency. |
| Footer/no-anchor/demo scripted layouts | **needs operator capture** | Fail closed; exclude from v1 supported set. |
| Physical two-laser fixture output | **needs hardware validation** | Out of RE scope; operator-gated runtime task. |
| Auxiliary records / negative-time | **needs controlled diff** | Fail closed; flag and refuse if encountered on an otherwise-supported file. |

No blocker is "impossible"; each has a concrete unlock. None blocks the clean
exporter + player path.

---

## 6. Parser / renderer rule changes needed for implementation

These are *implementation* rules derived from the RE; no current research tool
behavior is wrong, but the productized exporter/player must encode them:

**Parser/exporter rules**
- Treat the cue dictionary entry as `[16 GUID][u32 LE cue_index]`; key cues by
  **GUID**; carry `cue_index` only as the serialized reference key.
- Resolve a timeline `raw_ref` to a cue only under an **explicit** convention
  (`one_based` | `direct`) supplied by trusted provenance; never guess.
- `raw_ref == 0` is the **clear** control event, never `cue_index 0`.
- Decode the Venue cue patch as the 19-channel `(group, channel_id)→value` set;
  if any entry is invalid (unknown group/channel, non-uniform value) the cue is
  **not** exportable → fail closed (mirror `parse_venue_cues.cue_at`).
- Fail closed on: MIXED/ambiguous provenance, unresolved/missing GUID, duplicate
  cue_index, fixture-profile mismatch, footer/demo/no-anchor layouts, files with
  nonzero auxiliary 17-byte records, negative-time records outside the
  autoloop-validated pattern.

**Renderer/player rules**
- State = `dict[channel(1..19) → value]`, initialized to all-zero.
- Apply a cue: copy current state, overwrite only the cue's present channels
  (Venue-enabled), persist the rest. (Layered persistent buffer.)
- `raw_ref==0`: zero the main/position channels; **persist** control channels
  CH8 (color), CH9 (color speed), CH11 (strobe) until a later cue sets them
  (autoloop+A5-scoped rule; keep configurable).
- DMX byte = attribute value (identity); no transform.
- Transport: render is a pure function of `elapsed` over `(elapsed, source_seq)`
  order; ended/stopped/unloaded = all-zero. No mutable cross-frame history;
  captured frames are oracles only, never inputs.
- Emit Universe-0 CH1–19; groups `0x493`/`0x496` mirror (emit identical).

---

## 7. Validation status

| Gate | Status |
|---|---|
| Render model specified & binary-confirmed | **PASS** |
| Clean scripted byte-parity (A5/SANFRANDISCO, one-based) | **PASS** (16/16 events, 14/14 positive, 2/2 ref-zero) |
| Autoloop byte-parity (bridge-used corpus) | **PASS-enough** (29/30 distinct frames; lone miss = blackout) |
| Transport (seek/loop/refire/stop/unload) on a correct static base | **PASS** (Opalite transport pcap) |
| Edited/MIXED scripted byte-parity | **FAIL → fail-closed** (correct behavior; excluded) |
| Dictionary/Venue/cue-patch decode | **PASS** (byte-verified) |
| Reference provenance auto-detection | **N/A** (byte-undecidable; provenance required) |
| Physical fixture / hardware | **UNVALIDATED** (operator-gated) |
| Repo test suite (focused) | **PASS** (`test_ssfile_reference_convention` + `test_scripted_residual_corpus` = 27 OK; `py_compile` OK) |

Separated readiness:
- **Ready for exporter implementation:** YES (clean content + fail-closed gate).
- **Ready for offline DMX player implementation:** YES (model confirmed).
- **Ready for runtime DMX output / two-laser show:** NO (hardware-unvalidated; runtime integration deferred).
- **Hardware-validated / show-ready:** NO (no evidence; forbidden status).

---

## 8. Smallest safe implementation roadmap

1. **Phase 0 — frozen golden corpus + harness** (no new SoundSwitch action).
   Pin A5 (`84f6bf72`), the bridge-used autoloops, the Venue (`f34bfc79` current /
   `521cc9` pre-open — identical cue semantics), and the four final validator
   JSONs as golden oracles. Stand up an offline byte-parity harness.
2. **Phase 1 — Importer/exporter for clean content + Venue/fixture model**, with
   the fail-closed gate. Targets: Venue cue library, fixture/channel model,
   TrackMap identity, autoloop catalogs, clean scripted timelines.
3. **Phase 2 — Bridge-native offline player** reproducing the layered-persistent
   identity model; validate byte-exact against A5 + autoloops + transport.
4. **Phase 3 (BLOCKED)** — MIXED/edited scripted support: unlock only with a
   provenance manifest or per-file wire oracle.
5. **Phase 4 (BLOCKED, operator/hardware)** — runtime Enttec/two-laser output +
   hardware validation.

Full task breakdown, schema, and acceptance criteria:
`docs/plans/active/soundswitch_importer_exporter_player_codex_spec.md`.

---

## 9. Next tasks if implementation begins (Codex/Gemini)

See the Codex spec for the authoritative, phase-ordered task list. In brief, the
**ready** work is: golden-corpus harness → clean importer/exporter + lighting-pack
schema → offline player → byte-parity acceptance against A5/autoloops/transport.
The **blocked** work (MIXED scripted, hardware) is specified with its exact
unlock evidence and must not be started until that evidence exists.

Do **not** begin runtime/Enttec output, modify any SoundSwitch project, or claim
hardware/show readiness. Status remains **SOFTWARE/WIRE-VALIDATED ONLY —
HARDWARE-UNVALIDATED**.

---

## 10. MIXED active-content resolution — oracle canonicalization (exhausted repair paths)

The directive was: do not accept fail-closed for active content until every
repair/canonicalization/oracle path is tested. Result: **the oracle path works
and converts every active MIXED track into verified byte-exact content.**

### 10.1 Tool and proof
`tools/ssfmt/re/oracle_canonicalize.py` (+ `tests/test_oracle_canonicalize.py`,
7 tests). For each captured event it finds the layered cue composition
(pattern cue ⊕ decoupled color cue (CH8/CH9) ⊕ independent strobe (CH11), plus
raw-0 clear-with-control-persist) that reproduces the observed Universe-0 frame;
anything the cue model cannot express is stored as a literal frame. Every pack
entry is asserted to re-render byte-exact (the capture is oracle-only, never
renderer seed).

Measured on the existing captures (Venue `521cc9`/`f34bfc` — identical cue
semantics; group `0x493`, mirrored by `0x496`):

| Track | Events | Cue-resolved | Literal fallback | Byte-exact playback |
|---|---:|---:|---:|---|
| New Sky `AE9E3C61` | 367 | **367 (100%)** | 0 | **yes** |
| Opalite `74044FA4` | 39 | 38 (97%) | 1 | **yes** |
| TITANIUM `FC10FC02` | 64 | 62 (96%) | 2 | **yes** |

So **zero active-content blockers for playback**: the MIXED tracks become a
provenance-free `(elapsed → composition/frame)` pack, byte-exact against wire.

### 10.2 Status of every repair path (directive items 1–7)

| Path | Status | Evidence |
|---|---|---|
| 1. SoundSwitch canonicalize via open/re-save/Save-As/duplicate/reassign | **untested, operator-gated** | a `default_pre_save_as_oracle.ssproj` snapshot was staged but the Save-As was never completed (A5 still `84f6bf72` MIXED); 8697587 proved a single edit does **not** canonicalize. Needs an operator GUI experiment on a copy. |
| 2. AppLog/runtime maps refs→GUIDs | **insufficient alone** | AppLogs expose autoloop index/deck events, not per-scripted-cue GUID/ownership. Useful only fused with wire (= the oracle). |
| 3. Art-Net/VLN oracle → canonical pack | **PROVEN** | §10.1 — New Sky 100%, Opalite/TITANIUM byte-exact via cues+literal. |
| 4. Clean backups / earlier states | **unavailable** | both `default.ssproj` and `codex fixture research real.ssproj` hold identical edited hashes; no pre-edit copy of the 3 tracks exists. |
| 5. Controlled mutation forces direct rewrite | **untested, operator-gated** | 8697587: edits renumber but stay MIXED; whether a specific op forces uniform-direct is unproven. |
| 6. One-time migration tool → clean pack objects | **PROVEN (= path 3 productized)** | `oracle_canonicalize.py` is that tool; emits a verified pack per track. |
| 7. All active tracks repairable | **YES** | all three byte-exact; New Sky fully cue-resolved. |

### 10.3 Honest residual quality items (not blockers)
- **Opalite (1) / TITANIUM (2) literal-frame events**: these reproduce byte-exact
  but are not expressed as named cues. They are compound-sample/cascade artifacts;
  a full layer-state renderer + finer sampling, or one clean recapture, would
  fold them into cue form. Optional.
- **TITANIUM single-deck cleanliness**: 96% of frames resolve to valid Venue cues
  (strong evidence the dedicated capture is largely clean), but the earlier
  "4 distinct observed states per cue name" warrants confirming the capture is
  single-owner before treating its pack as canonical. One clean recapture closes
  this; it does not block byte-exact playback of the existing capture.
- **Capture coverage**: the oracle pack reproduces the *captured* play-through,
  position-indexed (seek/loop/refire validated). A track must have a full-coverage
  capture; gaps need a recapture of that region only.

### 10.4 Consequence for the exporter/player design
The exporter supports **two equally byte-exact lanes**, neither of which is a
fail-closed exclusion for active content:
1. **Byte lane** — clean uniform-provenance files (autoloops, clean scripted)
   export directly from `.ssfile` bytes + Venue.
2. **Oracle lane** — MIXED/edited active tracks are canonicalized from their
   Art-Net capture + Venue into a verified pack.

A file is fail-closed only if it is *both* MIXED *and* has no trustworthy capture
— which is a missing-evidence state with a concrete unlock (one operator capture),
not an unsupported-content verdict.

---

## 11. Go-forward "100% mirror" — completeness guarantee + the last open gate

Goal restated (operator): everything created/edited/deleted in SoundSwitch must
be 100% mirrored in the bridge; the exporter must never silently miss a cue.

### 11.1 No-silent-miss is SOLVED and TESTED
`tools/ssfmt/re/verify_export_completeness.py` (+ `tests/test_export_completeness.py`)
enforces SoundSwitch's own redundant completeness oracles and **fails loud**:
- Venue: parsed cue count must equal the catalog-declared count (233==233 today);
  contiguous index list; unique GUIDs; every byte in the cue region accounted for.
- Any cue using a channel/group outside the active fixture profile is a **fatal**
  error, not a silent skip (test-proven: dropping CH19 or group `0x496` from the
  model makes the verifier fail loudly).
- The same oracle pattern applies to `.ssfile` (count-prefixed dict + timeline,
  decoded to EOF) and autoloop catalogs (parse-to-EOF, zero unparsed).

**Consequence:** a missed/new/unknown cue is impossible to ship silently. The
production parsers must be rebuilt from heuristic scanning to **declared-count
structural parsing with total byte accounting**, and the channel/attribute model
must be **derived from the Venue fixture profile, not hardcoded** (the current
`parse_venue_cues` hardcodes this profile's 19 channels / 4 groups — a new
fixture would otherwise be silently rejected; the verifier turns that into a
loud failure).

### 11.2 Reference resolution — what the binary proves
- `AttributeCueTrack::ReadAttributesCueTrack` (`@0x3c26e4`) + `ReadEntry`
  (`@0x3c16ac`): SoundSwitch builds a per-file `cue_index→GUID` map from the
  file's own dictionary and resolves each timeline reference by **direct exact
  key match — there is no one-based/direct "convention" branch in SS code.**
- That decompiled path is the **`.ssproj` internal** serialization (clean 4×u32
  records). The per-`{SSID}.ssfile` timeline is a **different packed format**
  (raw_ref = top byte of the last u32; time interleaved in the low 24 bits —
  verified byte-exact on A5 record 0: bytes `…e600005b` → raw 91, elapsed 59088).
- A5 `.ssfile` dictionary key = `wire_raw_ref − 1` for all three wire-proven
  cues (RBSD 90/91, RED 21/22, IMPLODE 228/229): uniformly **one-based**.

### 11.3 The last open gate (honest)
SoundSwitch resolves deterministically internally, but the **per-`.ssfile`
serialization rule across create/edit/delete is not fully pinned**: A5 is
uniformly one-based, yet New Sky's 63 effect-cue references still miss under
one-based (and under direct, and under the per-file dictionary). This residual
cannot be closed from current offline artifacts with certainty. Two unlocks:

1. **Controlled authoring experiment (recommended, bounded operator action).**
   On a *copy*: create a track with N known cues; capture; add a cue; delete a
   cue; reorder; capture after each. Diff `.ssfile` bytes + wire each step to
   derive the exact `.ssfile` reference serialization rule for the current
   SoundSwitch version. If new/edited content is uniform (expected), go-forward
   resolution becomes deterministic and provable — MIXED would then be confined
   to pre-existing cross-version-edited legacy files (repaired by the §10 oracle).
2. **Finish the `.ssfile` packed-timeline RE in Ghidra** — locate the loader for
   the packed `{SSID}.ssfile` format (distinct from the `.ssproj` `ReadEntry`)
   and read its reference rule directly.

### 11.4 What this means for the exporter design (pre-spec)
Until 11.3 closes, the exporter must, for every track:
- resolve references under the file's detected convention **and self-verify**
  (every reference resolves in-range to an in-dictionary GUID; render
  cross-checks against a capture when one exists);
- **fail loud** on any unresolved/out-of-range/ambiguous reference — never emit a
  partially-resolved track;
- route detected-MIXED legacy files to the §10 oracle pack.

This guarantees the operator's hard requirement — **never a silent miss** — even
while 11.3 is open. The implementation spec must be written on top of 11.1
(completeness) + 11.4 (fail-loud resolution) and must not be authored until the
operator decides on the 11.3 experiment, because the resolution rule it encodes
depends on that outcome.
