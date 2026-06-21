---
doc_status: research-closure-blocked
truth_level: code-byte-capture-and-binary-grounded
last_verified_commit: 2c71a2e
last_verified_date: 2026-06-20
validation_scope: read-only repo/project/capture analysis plus static ARM64 and x86_64 binary analysis; no SoundSwitch/project/runtime/MIDI/DMX mutation; SOFTWARE/WIRE-VALIDATED ONLY — HARDWARE-UNVALIDATED
---

# SoundSwitch Reverse-Engineering Completion Report (AWR-107)

## 1. Final verdict

**RE NOT COMPLETE: EXACT BLOCKERS REMAIN**

Do not write or execute the final exporter/importer/player implementation spec.
The current evidence is sufficient to preserve already captured content through
an oracle-frame lane, but it does not prove that every object the bridge can fire
today—or future create/edit/delete/reorder operations—can be exported from project
bytes without guessing or recurring capture.

This corrects the earlier “closed enough” verdict. Fail-closed behavior remains a
required safety gate, but it is not an acceptable final disposition for Brandon's
active content.

Current application evidence:

- SoundSwitch 2.10.3, universal ARM64/x86_64 binary SHA-256
  `636ed4aa48287d019a96c60f8d9107e75f3e72abe4f7b0aa8fa54aaa661984e9`.
- Project Venue SHA-256
  `f34bfc796e9e589c7eb4707ee4f223c6ea6fd2f597d08622d30370f16a2a3398`.
- Active TrackMap parse: 96 mappings, 63 paths currently present, 32 mapped
  scripted `.ssfile` objects with an existing audio path.
- Configured laser output: 23 scene targets plus a held blackout command. The
  automatic house path uses 19 autoloop targets; one additional post-drop target
  is configured but not selected by the current house personality.

## 2. Active content inventory

Status vocabulary in this report:

- **clean/export-safe**: project bytes plus wire/binary evidence determine the
  frame sequence without an oracle frame input.
- **oracle-canonicalized/export-safe**: a complete captured event sequence can be
  emitted byte-for-byte for the exact captured source hash.
- **dirty but repairable**: an exact re-author/cold-load validation procedure is
  available, but it has not yet been completed.
- **dirty and requiring operator capture**: current bytes do not close ownership,
  provenance, or rendering; a bounded passive capture can canonicalize it.
- **still unresolved**: the smallest resolving action is known but not performed.

### 2.1 MIDI-selected autoloops

The note→AppLog index mapping below is re-derived from the paired bridge/AppLog
capture. `SSAutoLoopN.ssfile` uses `N = AppLog index + 1`.

| Bridge target | MIDI note | AppLog index / file | Current status | Current wire evidence |
| --- | ---: | --- | --- | --- |
| `house_breakdown_1` | 1 | 2 / `SSAutoLoop3` | dirty; operator capture required | 623/699 zero-init frames exact; one unresolved segment |
| `house_groove_1` | 32 | 4 / `SSAutoLoop5` | **clean/export-safe** | 3517/3517 frames exact across 9 segments |
| `house_buildup_1` | 64 | 17 / `SSAutoLoop18` | **clean/export-safe** | 1687/1687 frames exact across 6 segments |
| `house_drop_1` | 96 | 3 / `SSAutoLoop4` | dirty; operator capture required | 840/949 exact |
| `house_drop_2` | 97 | 12 / `SSAutoLoop13` | dirty; operator capture required | 2693/2913 transition-fit; 0/2913 zero-init |
| `house_drop_3` | 99 | 14 / `SSAutoLoop15` | dirty; operator capture required | 672/674 transition-fit |
| `house_drop_4` | 100 | 13 / `SSAutoLoop14` | dirty; operator capture required | 112/241 transition-fit |
| `house_drop_5` | 98 | 5 / `SSAutoLoop6` | dirty; operator capture required | 1632/1633 transition-fit; inherited color |
| `house_drop_6` | 101 | 15 / `SSAutoLoop16` | dirty; operator capture required | 334/1670 transition-fit |
| `house_drop_7` | 102 | 16 / `SSAutoLoop17` | dirty; operator capture required | 2076/2339 transition-fit |
| `house_drop_8` | 103 | 7 / `SSAutoLoop8` | dirty; operator capture required | 789/794 transition-fit |
| `house_drop_9` | 104 | 45 / `SSAutoLoop46` | dirty; operator capture required | 584/598 transition-fit |
| `house_drop_10` | 105 | 46 / `SSAutoLoop47` | dirty; operator capture required | 446/800 exact |
| `house_drop_11` | 106 | 47 / `SSAutoLoop48` | dirty; operator capture required | 162/449 exact; auxiliary records present |
| `house_drop_12` | 107 | 49 / `SSAutoLoop50` | dirty; operator capture required | 228/404 exact |
| `house_drop_13` | 108 | 51 / `SSAutoLoop52` | dirty; operator capture required | 1032/1353 transition-fit |
| `house_drop_14` | 109 | 52 / `SSAutoLoop53` | dirty; operator capture required | 1789/2417 exact |
| `house_drop_15` | 110 | 53 / `SSAutoLoop54` | dirty; operator capture required | 633/924 transition-fit |
| `house_drop_16` | 111 | 54 / `SSAutoLoop55` | dirty; operator capture required | 343/835 transition-fit; negative/ref-zero residual |
| `house_post_drop_1` | 41 | binding not captured | **still unresolved** | configured/manual-reachable; current house bank is empty |

The old “29/30 distinct frames” statement is not an active-corpus closure
result. It describes distinct states from a seven-file subset and hides the
segment failures above. The current validator correctly reports `status=partial`
and unresolved Universe-0 deck ownership/control layers.

### 2.2 Scripted tracks

Four of the 32 currently mapped/existing scripted tracks have a complete oracle
event sequence for their present source hash:

| SSID / title | Status | Evidence |
| --- | --- | --- |
| `A5B0ACD1…` — SANFRANDISCO | **oracle-canonicalized/export-safe** | 16/16 captured events; 0 literals; pack SHA `b24c7546…`; the byte-lane convention remains blocked by the binary/wire conflict in §4 |
| `AE9E3C61…` — New Sky | **oracle-canonicalized/export-safe** | 367/367 event frames, mirrored groups, 0 literals; pack SHA `b7c97430…` |
| `74044FA4…` — Opalite | **oracle-canonicalized/export-safe** | 39/39 event frames, mirrored groups, 1 literal at 88,389 ms; pack SHA `731db83c…` |
| `FC10FC02…` — TITANIUM | **oracle-canonicalized/export-safe** | 64/64 event frames, mirrored groups, 2 literals at 151,359 and 153,189 ms; pack SHA `6dd1457e…` |

The remaining 28 active scripted objects are structurally parsed but are **dirty
and requiring operator capture**. Structural parsing is not byte-parity proof:

| SSID | Track |
| --- | --- |
| `025C1DDF…` | Isoxo - how2fly vs Rihanna - We Found Love |
| `02E3AA51…` | M.A.A.D. CITY (EYEWITNESS & NJOY) |
| `16F51143…` | I Wanna Go (John Summit Extended Remix) |
| `1A62CF25…` | Booyah Bounce - Cheyenne Giles & Knock2 |
| `1FD042ED…` | BLACKPINK - JUMP (JAY ESKAR EXTENDED REMIX) |
| `32D96480…` | Slut Me Out 2 (RAW Remix) |
| `4883E811…` | Knock2 x Nelly - Gettin' Hot in Here |
| `494785CC…` | Dracula (OMNOM Remix) |
| `528E8B22…` | Where Have You Been (Hardwell Club Mix) |
| `5996871E…` | Party Rock Anthem (REXY=DEXY REMIX) |
| `651A3059…` | Billie Eilish - LUNCH (Phrva Flip) |
| `69F8532E…` | Better Place (Original Mix) MT V3 |
| `772519EB…` | Turn My Swag On (NETGATE x Danny Diggz VIP) |
| `8C6BFF4A…` | YOU KNOW YOU LIKE IT (CG REMIX) |
| `9947C65E…` | Niggas In Paris X Core X OK!OK!OK! |
| `AD786435…` | PICTURE IN MY MIND W IN K NIKKO REMIX |
| `B335B3AF…` | Rude Boy (Klean Remix) |
| `BFF9DFCD…` | MEAN GIRLS rmx - FINAL V4 |
| `C3A1B60D…` | Trademark USA (DEFOND remix) |
| `D44722CA…` | ...Baby One More Time (Never Sleep Remix) |
| `DD42028C…` | Where You Are (Crankdat Remix) |
| `E36664D0…` | Scilo - Lowkey |
| `ED463C27…` | No Hands (SWEETLK Tremor Edit) |
| `ED66BABB…` | MANEATER (DRYDEN EDIT) |
| `F0947ED0…` | TYNAN - His Name Is |
| `F1E0AB45…` | Kesha - Blow (CHALANT & Donny Graves Remix) |
| `F358F6B0…` | Cool For The Summer (Daevo Remix) |
| `FB4EF1CA…` | Break Free (Juelz Remix) |

Thirteen additional `.ssfile` objects have no currently existing TrackMap audio
path and are not classified as bridge-active. They remain inventory findings,
not implementation support claims.

### 2.3 Attribute cues

- Venue completeness is **clean/export-safe as a cue library**: declared 233,
  parsed 233, no fatal/warn entries, all mirrored laser cue patches decode for
  the current profile.
- Across the 19 active autoloops and 32 active scripted files, 192 cue GUIDs are
  possible reference targets when both direct and one-based candidates are
  retained. Every candidate GUID exists in the 233-cue Venue library.
- Which candidate a legacy/edited record actually selects is still a track-level
  provenance blocker. Therefore the cue objects are decoded, but 192-candidate
  usage assignment is not globally export-safe until §4 is closed or the object
  is oracle-canonicalized.

`verify_export_completeness.py` proves only the Venue result above. It does not
currently verify `.ssfile`, TrackMap, or autoloop-catalog total-byte coverage.

### 2.4 Static looks and utility targets

The current Venue has 14 structurally parsed static-look slots. The bridge
configuration can address three channel-2 utility notes:

| Bridge target | Note | Reachability | Status |
| --- | ---: | --- | --- |
| `safe_static` | ch2 note 0 | manual-reachable; not emitted by normal idle policy | **still unresolved**: note→slot binding and wire frame not captured |
| `transition_safe_1` | ch2 note 1 | manual-reachable; no current automatic selection path | **still unresolved**: note→slot binding and wire frame not captured |
| `emergency_blackout` | ch2 note 2 | active emergency command | **still unresolved**: configured target has no isolated wire capture |

The parser's positional slot model is not a substitute for the missing MIDI-map
and wire evidence. The other 11 Venue static slots are not addressed by the
current bridge configuration.

### 2.5 Blackout, all-off, and restore

The held blackout command is active: channel 1 note 0 `note_on`/`note_off`, with
named owners for Smart Drop, breakdown, and master-switch masks.

Passive evidence confirms the primary mask behavior:

- Of note-on events beginning from a nonzero frame, 37/43 reached all-zero
  within 41 ms. The remaining events overlap deck/scene/owner changes.
- Of note-off events beginning from zero, 39/46 restored a nonzero frame within
  51 ms. Seven stayed zero because another holder/transition remained active.
- Scripted confirmed stop/unload markers reach all-zero; a `scripted→idle`
  transition can briefly retain CH8/CH9/CH11 before the later stop clears them.

Classification: **blackout-on is confirmed; restore ownership/precedence is
still unresolved**. A bridge-native player must not guess whether release
restores the pre-mask frame or re-renders the current elapsed position.

## 3. Claim ledger

Evidence keys: **B** project bytes/parser, **T** tests, **W** Art-Net/AppLog/bridge
capture, **G** Ghidra/nm/otool/static disassembly.

| Load-bearing claim | Binary corroboration | Byte/capture/test corroboration | Final status | Exporter/player impact |
| --- | --- | --- | --- | --- |
| Cue identity is GUID/ClassId; `cue_index` is serialized reference metadata | GUID-keyed maps/readers/writers | controlled renumbering preserves GUID identity | **confirmed by bytes + Ghidra/binary** | key exported cues by GUID |
| Packed dictionary physical form is version/count + `[GUID][u32 LE key]`; timeline is four `u32 LE` values | CAF read/write methods | shifted big-endian research framing recovers identical values | **confirmed by bytes + Ghidra/binary** | parser description must use the physical LE layout |
| Packed `{SSID}.ssfile` uses a loader distinct from `ReadEntry` | call chain opens the `.ssfile` through `SoundSwitchDocData→MainTrack→AttributeCueTrack→ReadEntry` | A5 offsets align exactly to those fields | **contradicted** | prior “find separate packed loader” gate is obsolete |
| Current 2.10.3 writer emits direct stored keys | ARM64 and x86_64 `WriteEntry` write `AttributesCueMap::Lookup(GUID)` unchanged | new scripted/autoloop controlled records are direct | **confirmed by bytes + Ghidra/binary** | new records should be direct |
| Current 2.10.3 loader resolves raw key directly | both architectures use lower-bound/exact stored-key lookup with no subtract-one branch | A5 current file is opened after its mtime, yet 14/14 positive wire events match key-minus-one and 0/14 direct | **unresolved/blocking** | static binary and wire cannot both define the same record without an unmodeled step |
| All legacy scripted records are one-based | no binary branch supports it | A5 16/16 total, 14/14 positive, 2/2 clear under one-based | **weakened** | A5 is safe only through its oracle pack until a cold-load test resolves the conflict |
| Edited legacy files become MIXED with no per-record discriminator | writer explains newly appended direct keys; loader has no provenance bit | WHYB diff preserves old values and adds direct values in the same 16-byte grammar | **confirmed by bytes/tests/captures only** for storage; runtime meaning unresolved | bytes alone cannot choose per-record convention |
| Save/Save As canonicalizes legacy `.ssfile` references | none | controlled Save As changed TrackMap only; `.ssfile` hashes stayed unchanged | **contradicted** | Save As is not a repair workflow |
| Create/edit/move/delete in a new current-version object stays direct | current writer always writes direct | controlled new scripted/autoloop mutations emit direct records; move/delete preserve structure | **confirmed by bytes + Ghidra/binary**; wire validation still needed | promising go-forward lane, not yet a 100% guarantee |
| Applying a cue overwrites only present enabled keys; omitted keys persist | cache-entry merge copies prior state and overwrites enabled keys | A5 and captured scripted/autoloop state transitions | **confirmed by bytes + Ghidra/binary** | persistent layered buffer is the base renderer |
| Attribute value maps directly to DMX byte | identity path in output code | captured values equal Venue values | **confirmed by bytes + Ghidra/binary** | no value transform in current laser profile |
| Initial renderer state is zero | zero-initialized cache | A5 and multiple captures | **confirmed by bytes + Ghidra/binary** | deterministic start state when ownership is isolated |
| Raw reference 0 universally clears main channels while CH8/9/11 persist | no universal special-case proved | fits A5/autoloop subset; scripted transition-to-idle can retain controls briefly | **weakened** | scope the rule; do not make it universal |
| 29/30 distinct frames closes the bridge-used autoloop corpus | none | current all-segment validator leaves 17/19 automatic targets unresolved | **obsolete** | cannot authorize active autoloop export |
| New Sky mismatch proves a renderer reset/mask defect | none | oracle resolution maps all 367 frames | **obsolete** | mismatch was upstream reference/provenance, not the final frame model |
| Oracle packs for A5/New Sky/Opalite/TITANIUM reproduce current captures byte-exact | none needed | event count equals timeline count; mirrored groups match; full frames retained | **confirmed by bytes/tests/captures only** | exact captured-version playback is possible |
| Oracle `byte_exact=true` independently proves semantic cue reconstruction | none | `persist`, `clear`, and `literal` re-render paths return the stored observed frame | **weakened** | full-frame playback is exact; semantic cue attribution is not independently proved for those entries |
| Literal frames make perfect playback impossible | none | a literal stores the complete 19-byte frame at an exact elapsed time | **contradicted** | literals are acceptable for exact playback, bounded to 3/470 events across the three requested packs |
| Completeness verifier covers Venue, `.ssfile`, and catalogs | none | executable verifier accepts one Venue argument and tests Venue only | **contradicted** | product completeness checks remain unimplemented/research-incomplete |
| MIDI note→autoloop file binding is known for the automatic house set | not needed | paired bridge/AppLog capture gives all 19 mappings | **confirmed by bytes/tests/captures only** | automatic file selection can be exported for those 19 targets |
| Static utility mapping and emergency look are known | none | config has notes but no isolated AppLog/wire binding | **unresolved/blocking** | three reachable utility targets cannot yet be mirrored perfectly |
| Blackout note-on zeros and note-off restores deterministically | executor owner model is clear | mask-on is strongly captured; overlapping holders/decks obscure exact restore precedence | **unresolved/blocking** | player blackout release policy must wait for isolated proof |

## 4. `.ssfile` reference/provenance conclusion

### 4.1 What is solved

The physical format and current writer are solved:

```text
AttributesCueMap:
  u32_le version = 1
  u32_le count
  repeat count: guid[16], u32_le stored_key

AttributeCueTrackEntry:
  u32_le version = 1
  u32_le constant = 1
  u32_le elapsed_ms
  u32_le raw_key
```

Both ARM64 and x86_64 2.10.3 writers serialize `raw_key = map.Lookup(cue GUID)`.
Both static loaders look up the stored raw key directly. Controlled new-object
records agree with that direct rule.

### 4.2 What is not solved

The A5 capture contradicts that loader: SoundSwitch logged `track file found`
for the current file after its final mtime, but its wire output matches
`raw_key - 1` for all 14 positive events and direct for none. No architecture
difference exists; both slices implement the same direct lookup.

The exact missing step could be an in-memory/project migration, cue-library
ordering transform, or a still-unidentified resolution layer. The evidence does
not justify choosing one.

Edited legacy content is therefore unrecoverably ambiguous **from bytes alone**
when both `raw_key` and `raw_key - 1` exist in the dictionary. The 16-byte record
contains no provenance bit.

### 4.3 Canonicalization and operator-safe workflow

- **Save/Save As:** proven insufficient; it does not rewrite `.ssfile` content.
- **Duplicate/export/import:** not proven to canonicalize; do not prescribe it.
- **Oracle repair:** full passive Art-Net capture plus the exact project/Venue
  hashes produces a full-frame pack and repairs any current deterministic track.
- **Re-author repair candidate:** on a fixture-bearing project copy, clear every
  timeline record, save/close, cold-open, re-place every cue, save/close, then
  cold-open and capture once. Accept only if every emitted record is direct and
  the direct byte render matches every captured event. This exact clear→rebuild
  sequence has not yet been completed, so it is an operator action, not a claim.

Smallest experiment that closes the binary/wire conflict:

1. Freeze the copied project and hashes.
2. Create a new scripted track with three known, value-distinguishable cues.
3. Save and quit SoundSwitch completely.
4. Cold-open SoundSwitch 2.10.3 and the copy.
5. Passively capture one full playback with one deck/owner and no blackout.
6. Compare direct and one-based results per record.
7. Add, move, delete, and re-add one cue, repeating the cold-open capture after
   each mutation.

Until this passes, Brandon cannot create/edit/delete/reorder arbitrary future
content and have a byte-only exporter derive the correct DMX without guessing.

## 5. Oracle lane conclusion

The oracle lane covers the exact captured source hashes for A5, New Sky,
Opalite, and TITANIUM. For New Sky, Opalite, and TITANIUM:

| Pack | Timeline events | Cue/persist/clear resolved | Literal | Mirrored 0x493/0x496 |
| --- | ---: | ---: | ---: | --- |
| New Sky | 367 | 367 | 0 | identical |
| Opalite | 39 | 38 | 1 | identical |
| TITANIUM | 64 | 62 | 2 | identical |

Literal frames are acceptable for perfect playback because the lane's runtime
artifact is a complete elapsed→19-byte-frame sequence. A literal is not a guess;
it is the canonical frame. The three literals are bounded (3/470 requested-pack
events) and do not require re-authoring for playback of the captured versions.

They do require a new capture after any edit. A clean re-author/cold-load run is
the procedure for eliminating ongoing capture dependence. Also, the current
research tool stores full observed frames for every event; its semantic
`byte_exact` assertion is partly tautological for persist/clear/literal entries.
The correct product acceptance test is independent pack playback compared to the
frozen capture, not the current in-process assertion alone.

## 6. Remaining unknowns and smallest resolving action

| Unknown | Why it blocks perfection | Smallest resolving action |
| --- | --- | --- |
| Direct binary loader vs A5 one-based wire | byte-only reference rule is not trustworthy | cold-open three-cue mutation matrix in §4.3 |
| 17 automatic autoloops | inherited state/control/ownership residuals remain | one deck, known all-zero start, two full cycles per note, repeat once; build per-file oracle or prove zero-init render |
| `house_post_drop_1` note 41 | no AppLog index/file binding | isolated note-41 trigger with AppLog + Art-Net capture |
| 28 active scripted tracks | no complete event oracle and no proven global byte convention | full passive one-owner play-through per current file, or validated clear→re-author workflow |
| Three utility/static targets | note→slot and frame semantics unproved | isolated ch2 notes 0/1/2 from known state, each on/off twice, with AppLog and Art-Net |
| Blackout release | overlapping holders/decks obscure restore rule | one owner, fixed elapsed/static scene: capture frame A, note-on→zero, advance position, note-off; compare restore to A and current-position render; repeat |
| Universe-0 deck ownership/compositing | current autoloop validator is provisional | two-deck A/B/AB controlled capture after single-owner baselines |
| Re-save/duplicate/import canonicalization | only Save As is disproved | test each operation on the same frozen three-cue copy; compare hashes and cold-load wire |

These actions require explicit operator approval because they involve
SoundSwitch UI/runtime, MIDI, and Art-Net capture. They must use a project copy
and a physically safe fixture state. No restart, toggle, MIDI send, or hardware
operation is authorized by this report.

## 7. Go/no-go for implementation

**NO-GO for the final implementation spec and product implementation.**

Research tooling may continue. The future implementation must eventually
include:

- GUID-keyed Venue and timeline objects using the physical little-endian CAF
  layout;
- a byte lane only after the cold-load provenance gate passes;
- a full-frame oracle lane keyed to exact source/Venue/capture hashes;
- total-byte/count completeness checks for Venue, TrackMap, catalogs, every
  `.ssfile`, MIDI bindings, and active-object inventory;
- exact elapsed-position playback, seek/refire/stop/unload, blackout mask and
  restore semantics, multi-deck ownership, and mirrored fixtures;
- independent replay-versus-capture acceptance tests.

Remain blocked on exporter/player/runtime integration, Enttec/live DMX, and the
final implementation spec. Status remains **SOFTWARE/WIRE-VALIDATED ONLY /
HARDWARE-UNVALIDATED**.
