---
doc_status: active-spec
truth_level: capture-grounded (parity_20260701T185231Z) + current-code-verified + live-ghidra-evidence-packet (docs/research/soundswitch/soundswitch_perfect_parity_ghidra_evidence.md)
last_verified_commit: c59d78c
last_verified_date: 2026-07-02
validation_scope: Fable 5 finisher spec for SoundSwitch exporter + bridge DMX runtime parity. Patched 2026-07-01 against the recorded live-GhidraMCP evidence packet (docs/research/soundswitch/soundswitch_perfect_parity_ghidra_evidence.md, recorded at commit 7b0bd6a), which closes A.3.d (no autoloop gap-fill; scripted = all-zero-seeded carry-forward hold), pins the scripted cue-resolution mechanism (file-embedded exact-key lookup), closes A.4.c (beatgrid-tiled autoloop windows, phase_tick=(beat_pos-window_start)*600), pins note-96 selection (bridge resolver gap), and re-bounds static composition (non-generic maps are independent overlays; Task C6 assertion mandatory). Patched 2026-07-02 by read-only implementation-surface audit at commit c59d78c so C1-C8 explicitly name decoder, model, exporter, verifier, loader, runtime, status/menubar, proof-tool, and test surfaces that can preserve stale raw_reference, carry-forward, static, autoloop, or unverified-parity assumptions. Target = BYTE-EXACT SoundSwitch-U0-equivalent CH1-19 output for ALL supported authored content, present and future, inside the locked scope. Bounded to SoundSwitch 2.10.3 / canonical project {3CCBCD6F-7C1B-44D8-882C-A52A74CC1827} / RAVE b8ad2201... / 2 mirrored lasers / Universe 0 / CH1-19 / snap-and-hold. Spec only; no production code written; no captures taken.
supersedes_conclusions_of: docs/prompts/active/soundswitch_perfect_parity_fable5_prompt.md §2 reframe (bounded/refuted per surface below); builds on docs/plans/active/soundswitch_pack_parity_root_cause_spec.md (baseline, vindicated); this spec's own earlier [ghidra-prior] fail-closed placeholders for A.3.d/A.4.c (superseded by the live evidence packet, see §0.4)
---

# Codex Implementation Spec — SoundSwitch Perfect-Parity Finisher

**One-line:** The target is **byte-exact SoundSwitch-U0-equivalent CH1-19 output for every
supported authored document — current and future — in the locked scope**. The scripted "17%
mismatch" is **not** a runtime flicker — it is **exporter/pack content** being dark or wrong where
SoundSwitch is lit, which the runtime renders faithfully. The recorded live-Ghidra evidence packet
(`docs/research/soundswitch/soundswitch_perfect_parity_ghidra_evidence.md`, incorporated as §0.4)
pins the mechanisms: scripted output is an **all-zero-seeded carry-forward cue cache** (no autoloop
gap-fill — that theory is dead), cue identity is an **exact-key lookup against each `.ssfile`'s own
serialized `(GUID, stored_key)` records** (no offset, no `raw−1` arithmetic), autoloop phase is
**beatgrid-tiled windows with `phase_tick = (beat_pos − window_start) × 600`**, note 96 is a
**bridge resolver gap** (SS has no note-96 semantics), and static non-generic maps are
**independent overlays whose CH1-19 effect must be proven from profile data (Task C6 is
mandatory)**. This spec builds an **externally-grounded offline oracle** (U0 from the existing
capture, never a self re-render), fixes the exporter cue-resolution + carry-forward/first-event
model, fixes static trigger authority and autoloop selection/anchoring, sweeps the DMX runtime for
every other divergence, and **fails closed only on genuinely out-of-scope/unsupported content** —
with an explicit ship gate that needs **no new capture**. `unverified_parity` is a temporary safety
state, never a success state: supported authored content that stays unverified is unfinished work
or a defect (§0.1).

> **Roles:** Claude authored this spec; **Codex implements.** Work on `main`, commit after each
> task. No new branches. No secrets/live-config/canonical-pack contents committed. No hardware,
> no bridge restart, no SoundSwitch export click.

---

## Part 0 — Goal, scope lock, and recorded binary evidence (normative; read first)

### 0.1 Perfect-parity definition (the target)

- **Perfect parity = BYTE-EXACT SoundSwitch-U0-equivalent DMX output on CH1-19**, frame for frame at
  the approved snap-and-hold boundaries, for **every** supported authored SoundSwitch artifact inside
  the locked scope (§0.2): scripted tracks, autoloops, static looks, cue-dictionary entries, timeline
  events, TrackMap bindings, and learned MIDI controls — **current and future**. Given the same
  musical inputs (elapsed, beatgrid, learned controls), the exporter+bridge must render the same
  CH1-19 bytes SoundSwitch U0 would render.
- **`unverified_parity` is a temporary safety/blocker state, never a parity outcome.** It exists so
  unproven output can never drive the rig as if it were SoundSwitch-equivalent. A *normal supported
  authored document* still `unverified_parity` at ship is **unfinished work or a defect** — never
  success. Only genuinely out-of-scope or structurally unsupported formats (Part C absolute rules)
  may fail closed permanently.
- Explicitly rejected as success conditions: "probably correct"; "passes the internal verifier";
  "matches its own re-render"; "the current captured tracks pass"; "most things pass and the rest
  fail closed".

### 0.2 Locked supported scope

SoundSwitch **2.10.3**; canonical/default project `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}`; **RAVE**
venue/profile; **2 mirrored lasers**; **Universe 0**; **CH1-19**; **snap-and-hold** DMX (no
time-varying/interpolated output); no separate intensity channel **unless the profile assertion
(Task C6) proves otherwise**. Everything outside this fails closed as out-of-scope.

### 0.3 General exporter-correctness requirement (anti-whitelist)

Inside the locked scope the operator may add, remove, rename, reorder, or edit **arbitrary**
authored content — 1,000 scripted tracks, 128 new autoloops, edited cue dictionaries, changed
timeline events, changed TrackMap bindings, edited static looks, re-learned MIDI controls. The
exporter/bridge must **discover, decode, compile, verify, and render** those changes byte-exactly
**without**:

- hardcoded SSIDs, cue IDs, GUIDs, track counts, or autoloop counts;
- per-track / per-look / per-loop manual capture (a new capture is never a correctness dependency);
- literal U0-frame storage as the primary render path (captured frames are oracle evidence only);
- cue-name guessing, nearest-key hacks, global raw-reference offsets, or library-order
  reconstruction;
- whitelists of "known-good" documents;
- U1-as-truth or internal self-render as proof.

DD42028C, Rihanna `{528E8B22…}`, `{9947C65E…}`, AE9E3C61, and FC10FC02 are **witnesses of the
general model**, used as oracle evidence — never special cases to patch. A fix that makes only the
captured witnesses pass without generalizing by construction is a defect.

### 0.4 Recorded binary evidence and implications (normative inputs)

Source: `docs/research/soundswitch/soundswitch_perfect_parity_ghidra_evidence.md` — a recorded,
live, read-only GhidraMCP pass over the thin arm64 slice of SoundSwitch 2.10.3 (binary SHA
re-confirmed there). It supersedes this spec's earlier `[ghidra-prior]` fail-closed placeholders;
where older wording below conflicts with this section, **this section wins**. Use only what is
recorded there — no additional binary findings are assumed or invented.

**Finding 1 — Scripted gaps. Status: CONFIRMED.**
SoundSwitch paints **no** autoloop, base, static-default, or other underlay beneath a scripted
track. Scripted DMX is a cue cache **seeded from an all-zero entry**; each cache entry =
**previous entry + this cue's converted attribute changes** (carry-forward / snap-and-hold);
entries with empty/unresolved attribute maps are **skipped**, so the prior hold continues; the only
overlay is the Static Look/Override cache; blackout/emergency is the final mask.
(`SSPlaybacks::RefreshCache 0x100338198`, `RefreshCache_2PlayBackMode 0x10033799c`,
`SetChannelAttributes 0x10033710c`, `AttributeCueTrackCache::Rebuild 0x1003c1e38` — the
`RefreshCache` autoloop block updates manager/UI state only; it writes no channel values.)
Consequences: dark before the first cue is *correct*; cue values carry forward through gaps; if U0
is lit while the bridge/pack is dark, the cause is **exporter dropped/mis-timed cue data or missing
carry-forward/hold logic** — never native autoloop gap-fill. **Effect on tasks:** the draft's
gap-fill theory is dead as a main branch (Task C3 rewritten); the bridge's suppression of autoloop
under scripted stays as-is.

**Finding 2 — Scripted cue identity / resolution. Status: CONFIRMED.**
Cue identity is resolved by an **exact-key `std::map` lookup of the saved timeline `raw_reference`
against the `.ssfile`'s own serialized `(GUID, stored_key)` records** (the file's embedded
`AttributesCueMap`; `AttributesCueMap::Read 0x1003c0f00`, `AttributeCueTrackEntry::ReadEntry
0x1003c16ac`). It is **not** `raw_reference − 1`, not a global offset, not a footer/prefix/
shared-table remap, not cue-name guessing, not nearest-key, not library-order reconstruction. A
fresh export happens to write 0-based library-order keys, but `Read` always consumes the file's
stored keys — an edited/aged project is a **permutation**. A lookup miss resolves to a null/default
GUID whose cache entry is skipped (hold continues). **Caveat (preserve — do not simplify away):**
prior empirical data showed a `raw−1`-style match for DD42028C rows while the binary performs no
subtraction — treat that as a **bridge representation / decoder-label mismatch** (the file's stored
keys equal `raw−1` on only 69 of 91 rows there; no single offset satisfies all 91), not a real
binary `−1` operation, and never let this conclusion overwrite the capture observations. **Effect
on tasks:** Task C4 = parse each scripted file's serialized key records and resolve by exact key;
AE9E3C61 / FC10FC02 / DD42028C are witnesses of key-resolution defects, never hardcoded fixes.

**Finding 3 — Static non-generic maps. Status: BOUNDED.**
Intensity, strobe, colour, and position are carried as **separate overlays** and applied through
dedicated channel-setter paths **independently of the generic map**, gated by each channel's
declared attribute type (`RebuildStaticLookCache 0x100335230`, `StaticLook::Read 0x10033aa6c`,
`SetChannelAttributes 0x10033710c`). Whether they *reach* RAVE CH1-19 depends on the supported
profile's channel types and the looks' stored values — profile **data** the binary alone cannot
decide. **Effect on tasks:** generic-only static rendering is **not proven correct by assumption**;
the Task C6 export-time profile/channel/stored-value assertion is **mandatory** (upgraded from
belt-and-suspenders), and static parity is claimed only after the assertion and/or U0-oracle proof
holds.

**Finding 4 — Autoloop phase contract. Status: CONFIRMED.**
`phase_tick = (beat_pos − window_start) × 600` (int-truncated; 600 ticks/beat), with `beat_pos`
derived from the **beatgrid** (`AutoLoopLayout::GetStateForTime 0x10025f000`,
`buildAutoLoopForStartingBeat 0x10025f22c`); window length = `GetAutoLoopNumberBeats` (default 32 →
`phase_tick ∈ [0, 19200)`, matching the capture's [0, ~19198]); windows **tile forward from beat 0
in beatCount steps** and re-anchor where the prior window expired; pre-roll/negative beats wrap mod
beatCount. The window is **beatgrid-derived — never the bridge's observed scene edge**. **Effect on
tasks:** Task C7 replaces the edge-observation anchor with derived beatgrid tiling; beatCount comes
from the loop document (never hardcoded); the draft's vague "phrase-anchor" language is replaced by
this concrete rule.

**Finding 5 — Autoloop selection / note 96. Status: CONFIRMED (mechanism).**
Selection is a **generic learned `(data_byte, channel, type) → control-path` map** plus an internal
index auto-rotation (`NamedControlMapCollections::newControlMapping 0x10013c240`,
`MIDIControl::operator>> 0x10012f674`); **note 96 has no intrinsic SS meaning** (no special-case
branch exists). The `(channel 0, data 96) → SSAutoLoop4` mapping **exists** in this pack's
`selection_map.json`; the bridge's scene resolver simply never emits note 96. **Effect on tasks:**
note 96 is a **bridge resolver / selection-rule gap** to fix in Task C7 so the learned mapping can
fire; do **not** mark SSAutoLoop4 unsupported — that branch applies only when a pack's mapping is
genuinely absent, which is not the case here.

Remaining **UNKNOWN**s are enumerated in §D.2, each with the instrument that closes it (profile
assertion, decoder inspection, or the U0 oracle) — none needs more decompilation or a new capture.

---

## Part A — Audit result & root cause (read-only; do not implement)

### A.0 Method & evidence provenance

- **Capture (primary evidence):** `tools/ssfmt/captures/parity/parity_20260701T185231Z/` —
  U0 (universe 0 = SoundSwitch) 152,613 pkts, U1 (universe 1 = bridge shadow render) 878,408 pkts,
  truth sidecar 426,750 frame rows. Analyzed offline (streaming) — no new capture taken. The
  all-zero 512-byte DMX frame hashes to `076a27c79e5ace2a3d47f9dd2e83e4ff6ea8872b3c2218f66c92b89b55f36560`
  [confirmed] — used to detect true full-frame zeros (the sidecar's `visible`/`active_dark` key on
  **CH1 only**, so they are *not* a full-zero signal).
- **Code:** verified against current HEAD `c59d78c`. The 2026-07-02 implementation-surface audit re-read
  the C1-C8 decoder/model/exporter/verifier/loader/runtime/status/test surfaces named below; older
  root-cause line anchors from the 2026-07-01 pass remain evidence references, not an implementation
  file list.
- **Ghidra:** the audit in this Part originally ran without live GhidraMCP and labelled binary
  claims **[ghidra-prior]** (recorded in `docs/plans/active/soundswitch_pack_parity_root_cause_spec.md:57-83`
  and `docs/research/soundswitch/soundswitch_ghidra_addendum.md`). A subsequent **live read-only
  GhidraMCP pass is now recorded** in
  `docs/research/soundswitch/soundswitch_perfect_parity_ghidra_evidence.md` and is incorporated as
  **§0.4**. It **closes** the two residual fail-closed items — **A.3.d** (scripted gap composition:
  no autoloop underlay; all-zero-seeded carry-forward hold) and **A.4.c** (autoloop anchor:
  beatgrid-tiled windows) — pins the cue-resolution mechanism (file-embedded exact-key), pins
  note-96 selection (bridge resolver gap), and **downgrades** the addendum's static claim ("the
  generic map contains the exact CH1-19 output") from binary fact to a **profile-data condition**
  that Task C6 must assert. Where this Part's older [ghidra-prior] wording conflicts with §0.4,
  **§0.4 wins.** Nothing below is gated on a new capture.

### A.1 Verdict summary (attacked the reframe; per surface)

| Surface | Reframe claim (§2) | **Audit verdict** | Basis |
| --- | --- | --- | --- |
| Static render | generic-only is correct; only trigger authority is broken | **BOUNDED — generic-only is a profile-data condition, not a binary fact (§0.4 Finding 3)** | capture byte-match on 3 live looks; live Ghidra shows non-generic maps are independent overlays ⇒ Task C6 assertion mandatory |
| Static trigger | port drops; group-health fix insufficient | **CONFIRMED broken** | `static_held=0` all capture; `[SS-MIDI] input port gone` every ~5s; binding coverage gap |
| Scripted "17% = runtime zero-blip flicker" | cue values already correct; mismatch is a driver/render flicker | **BOUNDED → largely REFUTED** | deterministic-in-elapsed zeros; `transport='playing'`; exporter first-event gaps; **real-track cue-value divergence** |
| Scripted cue values correct on real tracks | true for all real tracks; DD42028C is an excluded orphan | **REFUTED for 2 of 4 captured tracks** | AE9E3C61 wrong strobe cue; FC10FC02 near-total divergence |
| Autoloop phase | phase-zero fixed; model correct | **CONFIRMED fixed** in this capture | phase_tick spans full [0,~19198] on all 18 targets |
| Autoloop selection/anchor | note 96 never selected; anchor must be derived | **CONFIRMED gap (bridge resolver) + anchor mechanism CONFIRMED (§0.4 Findings 4/5)** | binding exists; resolver never emits note 96 (SS is note-agnostic); SS windows tile from the beatgrid — bridge must derive, then oracle-prove |
| Frame integrity / mirror / >CH19 | (sweep) | **CONFIRMED clean** | no channel >19 ever nonzero across all U0+U1 scripted packets |

**Bottom line that changes the plan:** the reframe's *mechanism* for scripted is wrong. The mismatch
is **exporter/pack-content**, deterministic, and the runtime faithfully renders it. This **vindicates
the baseline root-cause spec** (`soundswitch_pack_parity_root_cause_spec.md`) and means the priority
fix is exporter cue/first-event fidelity + an external oracle, **not** a driver debounce. The
DD42028C-class defect is **not** confined to the excluded orphan — it recurs in real show tracks.

**Evidence-packet update (§0.4):** the live Ghidra pass then pinned the mechanisms — scripted output
is an all-zero-seeded **carry-forward** cue cache with **no autoloop gap-fill** (A.3.d closed
against gap-fill); cue identity is **file-embedded exact-key** lookup (the DD42028C-class defect is
a key-resolution defect); autoloop windows are **beatgrid-tiled** (A.4.c closed on the SS side);
note 96 is a **bridge resolver gap**; static non-generic maps are independent overlays that make
**Task C6 mandatory**. Tasks C3/C4/C6/C7 below are written against those facts, not against open
branches.

### A.2 Static — captured looks byte-match; generic-only BOUNDED until the C6 assertion (no map compositing on assumption)

- [confirmed] Runtime `apply_layers` applies **only** `look.generic_attributes` for
  `fixture_group == PRIMARY_FIXTURE_GROUP (0x493)` (`soundswitch_laser_player.py:207,84-89`), skipping
  looks with `profile_has_intensity_channel` (`:201`). Exporter `render_static_look_frame` is likewise
  generic-only (`soundswitch_pack.py:81-86`).
- [superseded by §0.4 Finding 3] The addendum's claim that for the RAVE 19-ch profile the four
  non-generic maps do **not** reach CH1-19 ("their generic map therefore contains the exact active
  CH1-CH19 output", `soundswitch_ghidra_addendum.md:104-105,176-178`) is **not a binary invariant**.
  The live pass (`RebuildStaticLookCache 0x100335230`, `StaticLook::Read 0x10033aa6c`,
  `SetChannelAttributes 0x10033710c`) shows intensity/strobe/colour/position are **separate
  overlays** applied via dedicated channel setters **independently of generic**, gated by each
  channel's declared attribute type. Generic-only is correct **iff** the RAVE profile has no
  intensity-typed channel, strobe fractions are 0.0, there is no pan/tilt-typed channel (or the
  position target is null), **and** colour resolves to the generic-equivalent value — conditions
  that live in profile + look **data**, not in these functions. Not just colour: all four maps are
  in the residual until asserted.
- [confirmed] `local/soundswitch/rbss_canonical_pack/static_looks.json`: 8 authored looks carry
  CH1-19 output via generic (slots 0,1,2,8,17,24,25,26); slots 16 "OFF" and 31 "BLACK OUT" have
  generic that renders all-zero (intended dark); **21 slots (3–7,10–15,18–23,27–30) have empty
  generic, empty names, default 5-entry maps, and a zero pre-rendered frame** — unauthored default
  slots, exactly the reframe's flagged set. Their generic-only render (zero) is correct *iff* the
  four non-generic maps contribute nothing to CH1-19 (§0.4 Finding 3) — exactly what the Task C6
  assertion proves per slot.
- **Verdict: BOUNDED.** The 3 captured looks byte-match U0, and the generic-only model is *expected*
  to hold for RAVE — but per §0.4 Finding 3 it is **assumed-until-asserted**, not proven. No runtime
  map-compositing is added on assumption; the residual is closed by the now-**mandatory** export-time
  profile/channel/stored-value assertion (Task C6). A slot that fails the assertion is surfaced and —
  because static looks are supported content — is a **blocker** to work (dedicated-path composition
  proven vs U0, per Task C6's violation branch), never a silent generic-only export and never a
  permanent fail-closed.

### A.3 Scripted — the "17%" is exporter/pack-content, deterministic (reframe mechanism REFUTED)

Four scripted SSIDs captured; DD42028C excluded (negative control). Full-frame U0/U1 pairing
(nearest `mono_ns`), plus sidecar `transport`/`elapsed_ms`, plus the pack's own timeline:

- **[confirmed] The zero-blip is deterministic in elapsed, not a runtime race.** For every scripted
  SSID, **0.0%** of the elapsed values that produced a zero frame *also* produced a nonzero frame.
  `render_scripted_frame` is a pure function of `(document, elapsed_ms)` — same elapsed ⇒ same frame
  always. So the zeros come from the **renderer returning the pack's frame for that elapsed**, not
  from jitter.
- **[confirmed] `transport='playing'` on essentially every scripted frame** (exactly one `transport=""`
  frame per track). The driver's stale-snapshot / discontinuity / transport guards
  (`state_manager.py:3930-3990`, `_PACK_SEEK_JUMP_MS=2000` at `:126`, `MEM_STALE_S=3.0` at
  `config.py:62`) **did not fire**. **The reframe's proposed cause (§2.2, "guards firing on momentary
  snapshot jitter → transport=None") is REFUTED** — transport never went None during playback.
- **[confirmed] The dominant defect is a first-event / intro-and-gap gap.** The pack's first timeline
  event equals the bridge's first lit frame exactly: Rihanna `{528E8B22…}` **60065 ms**
  (`scripted/528e8b22….json`), `{9947C65E…}` **51805 ms**, `{FC10FC02…}` **97232 ms**,
  `{AE9E3C61…}` **11 ms**. `render_scripted_frame` returns `ZERO_FRAME` for `elapsed < first_event`
  (`soundswitch_laser_player.py:123-127`). Where SoundSwitch is lit before the pack's first event (or
  in mid-track gaps), U1 is dark while U0 is lit.
- **[confirmed] Per-track (U0/U1 nearest-mono pairing):**
  - **Rihanna `{528E8B22…}` — reframe CONFIRMED for this track.** both-zero 21,184; value-MATCH
    12,882; U1-zero/U0-lit **BLIP 2,822**; value-diff 146 (20 timing-skew). **BLIP / U0-lit-time =
    2,822/15,850 = 17.8%** — exactly the operator's known number. All zeros are `< 60069 ms` (intro);
    **zero mid-track zeros**. Values otherwise match. The "17%" here = a startup region where SS leads
    the pack's first cue, **not** a periodic flicker.
  - **`{9947C65E…}` — reframe CONFIRMED.** MATCH 14,518; BLIP 3,163 (**17.9%** of lit); value-diff 2
    (both skew); U1 nonzero set ⊆ U0. Has 1,276 genuine mid-track dark frames in addition to the intro
    gap.
  - **`{AE9E3C61…}` — reframe REFUTED.** **Zero** playing-zeros (lit from elapsed 239 ms). Its defect
    is **value/cue-resolution divergence**: 6,519 value-diff frames (only 89 timing-skew); 9 distinct
    U1 frames SoundSwitch **never** emits; e.g. U1 CH10/CH11 = **(255,255)** ("MASTER STROBE") where
    U0 = **(110,0)** ("STROBE"), plus CH5/CH19 diffs. This is the **DD42028C-class wrong-cue selection
    in a real show track.**
  - **`{FC10FC02…}` — reframe REFUTED.** MATCH **312 (0.6%)**; first cue at **97232 ms** while U0 is
    richly lit the whole window; 5,170 value-diffs (0 skew). Severe late/incomplete/wrong export.
- **[confirmed] Frame integrity clean:** no channel beyond CH19 is ever nonzero in any U0 or U1
  scripted packet (`MAX_NONZERO_CH_BEYOND_19 = 0`); the mirror emits a single 19-ch output.
- **[resolved — §0.4 Finding 1] Gap-fill hypothesis is DEAD.** The recorded live decompile of
  `SSPlaybacks::RefreshCache/RefreshCache_2PlayBackMode/SetChannelAttributes` +
  `AttributeCueTrackCache::Rebuild` proves SoundSwitch paints **no** autoloop/base/default output
  under a scripted track: the scripted cache is seeded from an **all-zero entry**, each entry is
  **previous entry + this cue's changes** (carry-forward / snap-and-hold), empty/unresolved cues are
  **skipped** (the prior hold continues), the only overlay is Static Look, and blackout is the final
  mask; `RefreshCache`'s autoloop block updates manager/UI state only. Therefore every "U0 lit where
  the pack is dark" case is **exporter-side**, in one of two shapes: (i) U0 lit **before** the pack's
  first event ⇒ SS's cache holds an **earlier cue the exporter dropped or mis-timed**; (ii) U0 lit
  **through a mid-track gap** where the pack goes dark ⇒ the exporter/renderer is **not reproducing
  the carry-forward hold**. The bridge's suppression of autoloop under scripted
  (`native_autoloop_resolver.py:164-173` returns `software_zero_frame` when `scripted_active`) is
  **correct as-is** — do not add an autoloop-under-scripted compositor. **A.3.d is closed.** The
  oracle (Task C1) still confirms each held value per boundary/gap empirically — as defense against
  a *mis-resolved* cue interacting with the hold (§0.4 Finding 2), not to re-litigate gap-fill.
- **Verdict: BOUNDED → largely REFUTED.** Root cause is the **exporter cue-resolution + first-event/gap
  model**, not runtime. Two of four real tracks show value divergence. This is exactly the baseline
  spec's warning (`soundswitch_pack_parity_root_cause_spec.md:117-282`). The runtime is exonerated for
  scripted (the single `transport=""` frame/track is negligible).

### A.4 Autoloop — phase fixed; anchor mechanism closed (bridge derivation to prove); selection gap + near-empty content open

- **[confirmed] Phase-zero is FIXED in this capture.** All 18 covered targets show `phase_tick`
  spanning the full `[0, ~19198]` range with `pt_zero ≈ 0.0–0.1%` (natural wrap). The landed guard
  (`state_manager.py:4022-4030`: bootstrap the held scene only when
  `self._native_autoloop.state is None`) works; `render_autoloop_frame` (`soundswitch_laser_player.py:132-154`)
  is exercised across all phases.
- **[confirmed] SSAutoLoop4 (note 96) never fires — binding EXISTS, selection does not emit it.**
  `selection_map.json.iac_selections` contains `(channel_zero_based=0, data_byte=96) →
  SSAutoLoop4.ssfile` active (`_autoloop_bindings`, `soundswitch_pack_loader.py:383-409,635-668`); the
  resolver `bindings.get((0,96))` would succeed. Root cause: the bridge's scene resolver emits the
  **specific** drop notes 97–111 and the groove/buildup policy notes 32/64, but **never the drop-policy
  note 96** (`house_drop_1`). Selection-policy gap — consistent with the pending operator "BY GENRE"/
  SS-groove mappings ([[project_autoloop_intelligence]]). Not a render bug. **[§0.4 Finding 5]** The
  live decompile confirms the SS side is a **generic** learned `(data_byte, channel, type) →
  control-path` map plus internal index rotation — note 96 has **no intrinsic SS meaning** — so this
  is purely a **bridge resolver gap** to fix; the "mark unsupported" branch does not apply while the
  mapping is present in this pack.
- **[resolved on the SS side — §0.4 Finding 4; bridge derivation still to prove] Anchor origin.**
  The recorded live decompile (`AutoLoopLayout::GetStateForTime 0x10025f000`,
  `buildAutoLoopForStartingBeat 0x10025f22c`) pins the SS contract: `beat_pos` comes from the
  beatgrid (`BeatSpace::getBeatPosFor`), window length = `GetAutoLoopNumberBeats` (default 32), the
  first window is built **from beat 0**, each subsequent window re-anchors where the prior expired —
  i.e. **windows tile forward in beatCount steps from beat 0** (`window_start = beat0 + k·beatCount`),
  pre-roll/negative beats wrap mod beatCount, and `phase_tick = (beat_pos − window_start) × 600`
  (int-truncated, ∈ [0, 19200) at beatCount 32 — matching the capture's [0, ~19198]). The bridge's
  current `anchor_beat = float(abs_beat_pos)` at the first observed scene edge
  (`native_autoloop_resolver.py:191-199`; 3–10 distinct anchors per loop in the capture) is the
  **wrong origin** — an edge-observation beat can carry a latency offset vs the beatgrid tiling.
  **A.4.c is closed as a mechanism**; the residual is whether the **bridge's beatgrid beat 0**
  matches SS's `BeatSpace` beat 0 on real tracks — proven via the oracle on captured loops
  (Task C7, §D.2 U4), not by more decompilation.
- **[bounded] Some loops export near-empty.** `SSAutoLoop5` (note 32, groove), `SSAutoLoop18`
  (note 64, buildup), `SSAutoLoop3` have **1–2 events and zero nonzero boundaries** → render
  `empty_dark_look` (dark). Faithful to pack content, but whether the pack content is *correct* vs U0
  (exporter under-render of those loop documents) is **unproven** — same exporter-fidelity question as
  scripted.
- **Verdict: BOUNDED.** Phase CONFIRMED fixed; anchor **mechanism** CONFIRMED (§0.4 Finding 4) with
  the bridge's beatgrid derivation still to be oracle-proven (§D.2 U4); selection (note 96) is a
  bridge resolver gap to **fix** (Task C7); near-empty-loop content must be oracle-checked (§D.2
  U5). Fail-closed only as a temporary state per §0.1.

### A.5 §6.2 edge-case sweep — findings & proof status

| # | Case | Finding | Proof status |
| --- | --- | --- | --- |
| 1 | Beyond-CH19 / mirror leakage | No channel >19 ever nonzero (U0+U1). Single mirrored 19-ch output. | **proven clean** (capture) |
| 2 | Zero-blip = runtime jitter | Refuted; deterministic in elapsed, `transport='playing'`. | **proven** (capture+code) |
| 3 | First-event/intro gap | Pack dark until first timeline event; SS lit earlier/through gaps. | **proven present** (capture+pack) |
| 4 | Scripted-gap autoloop-fill precedence | **Resolved (§0.4 Finding 1): SS composites nothing under scripted gaps — all-zero seed + carry-forward hold only.** Bridge suppression is correct; the defect is exporter-side (dropped cues / missing hold). | **closed by recorded binary evidence**; oracle re-confirms held values (C1/C3) |
| 5 | Cue-resolution value divergence | AE9E3C61 wrong strobe cue; FC10FC02 near-total. DD42028C-class in real tracks. | **proven present** (capture) |
| 6 | Autoloop selection (note 96) | Binding exists; resolver never emits policy-note. | **proven** (pack+capture) |
| 7 | Autoloop anchor origin | **SS mechanism resolved (§0.4 Finding 4): beatgrid-tiled windows from beat 0, phase=(beat−start)×600.** Bridge edge-anchor is the wrong origin; must derive from beatgrid tiling. | **mechanism closed**; bridge derivation oracle-proven (C7) |
| 8 | Static trigger authority | Port drops every ~5s; binding covers only DDJ StaticOverride16. | **proven broken** (log+pack) |
| 9 | Static non-generic residual | Non-generic maps are independent overlays (§0.4 Finding 3); **all four** (not just colour) must be proven inert per slot from profile + look data. | **needs export assertion (C6, mandatory)** — fail-closed until asserted |
| 10 | Precedence: blackout/emergency/static-override/SS-present suppression/reload-wait | Code paths present & ordered (`render()` `soundswitch_laser_player.py:391-418`; driver SS-present zero at `state_manager.py:4102-4117`); not adversarially unit-proven for every combination. | **needs unit sweep** (Task C7) |
| 11 | Reload / backend-swap race during playback | Atomic `set_pack_runtime` (`state_manager.py:3604-3633`) resets layer tracker; degradation latch survives; not proven against a mid-playback swap. | **needs unit sweep** (Task C7) |
| 12 | Timing: BPM 160→155 drift, phrase races, 200 Hz vs 60 Hz, phase quantization | Autoloop cycle 19,200 ticks / 600 ticks/beat; scripted snap-and-hold is BPM-independent (elapsed-keyed). Not stress-proven at tempo change. | **needs oracle+unit** (Task C1/C7) |
| 13 | Input health: MIDI port-gone, controller drop mid-hold, group-health overlay-trust | RW-4 overlay-distrust latch present (`state_manager.py:3896-3921`); the port-gone itself is the live defect (Task C5). | **partial** — Task C5 |
| 14 | Frame integrity: out-of-range, partial/garbled, non-primary group leakage | `_validate_frame` enforces 19×[0,255] (`soundswitch_laser_player.py:77-81`); `_apply_attribute` filters to `0x493` (`:84-89`). Clean in capture. | **proven + guarded** |

---

## Part B — Design

### B.1 The externally-grounded offline oracle (breaks the self-reference)

**Problem it solves:** the existing verifier (`soundswitch_pack_verifier.py:329-355`) proves the pack
is *internally consistent* (`stored == raw-1`, re-render matches its own model) — a wrong-but-consistent
model still passes. Parity must be judged against **SoundSwitch's own DMX (U0)**, never a re-render.

**Design:**
- New offline, I/O-isolated tool `tools/ssfmt/parity_oracle.py` + a **pure** core module
  `soundswitch_parity_oracle.py` (importable, no file/socket/subprocess deps in the core).
- **Ground truth = U0 packets** from `parity_20260701T185231Z`. Never the pack, never U1-as-truth,
  never an internal self re-render. U1 packets are used **only** as a join vehicle
  (sequence/hash → `mono_ns`), never as a correctness reference. The oracle exists precisely to
  catch **wrong-but-self-consistent** exporter output — any check that compares the exporter to its
  own model is void as parity evidence.
- **elapsed→U0 mapping** (per scripted SSID): join each sidecar frame row `(sequence, dmx_sha256,
  elapsed_ms, soundswitch_id, transport)` to its U1 packet by `(sequence, dmx_sha256)` in file order
  (the capture already guarantees this join — see `capture_end`/prior all-surface run), take that U1
  packet's `mono_ns`, then take the **nearest U0 packet(s)** by `mono_ns`. Yields tuples
  `(soundswitch_id, elapsed_ms, U0_frame, U1_frame)`.
- **Scripted assertion:** render the **pack** with `render_scripted_frame(document, elapsed_ms)` and
  compare to `U0_frame`. Classify each sample: `MATCH`, `BLIP` (pack zero / U0 lit),
  `VALUE_DIFF` (both lit, unequal), `U0_DARK`. Away from cue boundaries require exact equality; within
  a bounded timing tolerance of a U0 transition (±1 U0 inter-packet interval) accept either adjacent
  U0 frame (timing-skew, not a value error). Report per-SSID totals + a per-boundary table.
  The oracle additionally verifies the **carry-forward contract** (§0.4 Finding 1) empirically:
  the pack's first event aligns with U0's first lit frame; U0's held bytes through mid-track gaps
  equal the pack's held bytes; channels a cue does not touch keep their prior values across
  boundaries. Where U0 is lit and the pack is dark, classify **dropped-cue** (U0's frame equals an
  earlier/shifted cue of this track) vs **missing-hold** (U0's frame equals the previous cue's held
  bytes) — both exporter-side; the autoloop-fill class is retired.
- **Autoloop assertion:** for each covered target, map U0 frames to `phase_tick` via the sidecar
  `native_autoloop.{target_identity,anchor_beat,phase_tick}` and compare
  `render_autoloop_frame(document, phase_tick)` to nearest U0. Report per-phase match. Also compare
  the **beatgrid-tiled** window derivation (§0.4 Finding 4) against U0's observed phase — the proof
  instrument for §D.2 U4 (bridge beat-0 equivalence) and Task C7's anchor fix. (The former "does
  U0's scripted-gap frame match an autoloop phase" check is retired — gap-fill is dead per §0.4
  Finding 1.)
- **Static assertion:** for the 3 live-mapped looks (0,24,16), assert the pack's
  `pre_rendered_frame_ch1_ch19` equals the U0 held frame during that look's `actions.jsonl`
  `static_slot_*` window (recover windows from actions, not alignment — the static detector never
  fired). No U1 static side exists in this capture (trigger bug) — the static oracle checks pack-render
  == U0, which is capture-provable **today** for the 3 attempted looks.
- **Negative control:** the oracle MUST classify **DD42028C** as non-matching (it is the known-divergent
  witness; use its prior evidence in `soundswitch_pack_parity_root_cause_spec.md:177-217`). An oracle
  that "passes" DD42028C is broken.
- **Generalization (no new capture, no whitelist):** for the 28 scripted / 1 autoloop targets **not**
  in the capture, the oracle cannot compare to U0. Parity for them is claimed **only** by *algorithm
  generalization*: (a) the pipeline is proven **content-independent** for a layout — cue identity
  resolved by **file-embedded exact-key lookup** of `raw_reference` against that file's own
  serialized `(GUID, stored_key)` records (§0.4 Finding 2; this replaces the draft's
  "`raw_reference-1 → stored_key`" description of `soundswitch_project_decoder.py:538-544`, which
  Task C4 step 1 must inspect and correct or re-label), the **all-zero-seeded carry-forward** step
  function (§0.4 Finding 1; `soundswitch_laser_player.py:122-128` must be verified to hold — not
  blank — between boundaries), and the same cue-attribute application — **and** (b) the captured
  witnesses of that layout pass the U0 oracle at every approved boundary. If (a)+(b) hold, any
  authored content of that layout — including future tracks/loops the operator creates — renders
  identically **by construction**; this, plus structural decode assertions (parse errors, unknown
  versions, unresolvable keys surfaced loudly), is how "1,000 new scripted tracks / 128 new
  autoloops" are covered without per-item capture or whitelists. **Today (a)+(b) FAIL for
  `shared_441_dictionary_timeline`** because AE9E3C61 (same layout) diverges — so *all* unproven
  tracks of that layout stay `unverified_parity` (a temporary blocker per §0.1) until the resolver
  is fixed and the captured witnesses pass.

### B.2 The "unverified-parity" flag model (fail-closed on the live path only)

Per §1 of the prompt: never block authoring/export **visibility**, but never let unproven content
drive **parity-live output** as if SoundSwitch-equivalent.

- Extend the pack's per-document render provenance (baseline Task 2) to a 3-state parity lane, stored
  in the pack + a committed registry `tests/fixtures/soundswitch/scripted_parity_registry.json` and its
  autoloop/static equivalents:
  - `oracle_proven` — captured witness passed the U0 oracle at every approved boundary.
  - `algorithm_generalized` — layout is content-independent **and** ≥1 witness of that layout is
    `oracle_proven`.
  - `unverified_parity` — everything else (no witness, or a witness fails). **Fails closed live.**
  - Lane assignment is a **pure computed classification** of `(document, oracle_report, structural
    checks)` — never a hand-curated list. The registry stores **evidence** (capture id, per-boundary
    totals, hashes), not a whitelist of blessed SSIDs (§0.3). Per §0.1, `unverified_parity` is a
    **temporary safety state**: the ship gate (E.4) requires every normal supported active document
    to end `oracle_proven` or `algorithm_generalized`; a supported document stuck
    `unverified_parity` is an open defect, not a shippable outcome.
- **Live fail-closed gate (Task C8):** when the pack runtime is in a *parity-live* mode (bridge
  replacing SoundSwitch, i.e. `soundswitch_connected == False` and pack output enabled), a document
  whose lane is `unverified_parity` must **not** be rendered as trusted output. It renders only under an
  explicit operator-acknowledged "unverified" state whose command/config surface is named and tested in
  C8 (`runtime_status.py`, `soundswitch_pack_player_config.py`, `config/soundswitch_pack_player.example.json`,
  `__main__.py`, and command/config tests). Without that named path, it emits the documented safe base
  (ZERO for scripted/autoloop; held manual static still allowed). This never changes the SS-present
  shadow path (which already submits ZERO to the backend, `state_manager.py:4116`). Export/visibility is
  unchanged.

### B.3 Fix design per lane (rewritten against §0.4)

- **Scripted carry-forward / first-event (Task C3):** the gap-fill branch is **dead** (§0.4
  Finding 1) — do **not** add an autoloop-under-scripted compositor; the bridge's suppression
  (`native_autoloop_resolver.py:164-173`) is correct as-is. Implement SS's cache model in the
  exporter/renderer: all-zero seed; each boundary frame = **previous boundary frame + this cue's
  converted attribute changes** (channels a cue does not touch keep their prior values);
  empty/unresolved cues **skip** (prior hold continues — never a blank); dark only before the
  earliest cue; holds persist through gaps until the next cue (driver stop/unload/track-change
  still zeroes — E.2). Fix dropped/mis-timed early-cue extraction so the pack's first event aligns
  with U0's first lit frame. Keep snap-and-hold; add **no** interpolation/time-varying output. Any
  track still divergent after C3+C4 ⇒ `unverified_parity` (temporary blocker) with the failing
  boundary recorded.
- **Scripted cue-resolution (Task C4):** implement §0.4 Finding 2 exactly — parse each `.ssfile`'s
  embedded `AttributesCueMap` `(GUID, stored_key)` records and resolve each timeline entry's
  `raw_reference` by **exact-key lookup**; a miss yields no-cue ⇒ the entry **skips** (hold) and is
  loudly surfaced (a miss inside a healthy supported file usually means a decoder misparse). **No**
  global raw-reference offset (rejected: `soundswitch_pack_parity_root_cause_spec.md:214-217`),
  **no** library-order reconstruction, **no** cue-name/nearest-key guessing. **DD42028C caveat
  (preserve):** the prior empirical `raw−1` match is a bridge/decoder **representation or label
  artifact** (the file's stored keys equal `raw−1` on only 69/91 rows there), not a binary `−1` —
  keep the capture observations as fixtures; fix the mechanism. AE9E3C61 (CH10/CH11 must resolve to
  U0's `(110,0)` "STROBE", not the library-adjacent `(255,255)` "MASTER STROBE"), FC10FC02, and
  DD42028C must pass the U0 oracle after the fix. Oracle-canonicalization stays the operator-gated
  escape hatch (baseline Task 4) for a document whose bytes genuinely cannot be decoded — not a
  shortcut.
- **Static trigger authority (Task C5):** two root causes, both fixed: (i) the input port dropping
  (`[SS-MIDI] input port gone`, `soundswitch_midi_input.py:454-484`) — root-cause the exact-port
  matcher/retry so the operator's static-controller port stays open; (ii) binding coverage — the pack's
  learned static control is only `DDJ-800 StaticOverride16`, but the operator holds via Stream Deck;
  make the observed-vs-authored gap explicit and fail-closed (status shows "static trigger unobserved")
  rather than silently claiming static parity. Preserve the RW-4 group-health overlay-trust behavior
  (`state_manager.py:3896-3921`). Keep render generic-only **pending the C6 assertion** (never as an
  unexamined assumption).
- **Static non-generic assertion (Task C6 — mandatory per §0.4 Finding 3):** at export, for every
  static slot assert — against the RAVE profile's per-channel attribute **types** and the look's
  stored map **values** — that intensity has no typed channel, strobe fractions are 0.0, position
  has no pan/tilt-typed target, and colour resolves to the generic-equivalent value. Pass ⇒
  generic-only render is **proven**, and every supported static look (current and future) is
  byte-exact by construction. Fail ⇒ the slot is surfaced as a **blocker**: the byte-exact path is
  dedicated-path composition in SS's order (static maps overwrite intensity/colour/pan/tilt/strobe
  before the emit loop; attribute-typed channels emit from the dedicated setter path; default-type
  channels emit cue⊕static-generic — §0.4 Finding 3), proven against U0 — never a silent
  generic-only export, never a permanent fail-closed for a supported look.
- **Autoloop selection + anchor (Task C7):** (i) selection — drive the resolver from the pack's
  **learned selection map generally** (any `(data_byte, channel, type) → target` binding; no
  hardcoded note list; no hardcoded loop count) so the existing `(0, 96) → SSAutoLoop4` binding can
  fire; note 96 is a bridge resolver gap, not an SS semantic (§0.4 Finding 5); the
  `unverified_parity`+surface branch applies only to a pack whose mapping is genuinely absent — not
  this one. (ii) anchor — replace the edge-observation anchor with **derived beatgrid tiling**
  (§0.4 Finding 4): `beatCount` from the loop document (`GetAutoLoopNumberBeats` semantics; default
  32; never hardcoded), `window_start = beat0 + k·beatCount` (the tile containing the current
  beat), `phase_tick = int((beat_pos − window_start) × 600)`, pre-roll wrapped mod beatCount. Prove
  via the oracle that this reproduces U0 phase on the captured loops (this simultaneously proves
  bridge-beatgrid beat-0 equivalence, §D.2 U4). Do not regress the landed phase-zero guard.
  Near-empty loop exports (SSAutoLoop5/18/3) are oracle-checked vs U0 (correct-dark vs exporter
  under-render ⇒ fix extraction) or flagged as temporary blockers.

---

## Part C — Tasks for Codex (execution order: C1 → C2 → C4 → C3 → C6 → C5 → C7 → C8)

Commit after each task. Every task carries: files + implementation intent + pure-function seam +
must-fail-then-pass test + acceptance condition + generalization proof. C4 runs before C3 because a
held value is only correct if the cue that seeded it resolved correctly (§0.4 Findings 1+2
interact); task numbering is kept for reference stability.

### Absolute rules
- **Do not** write production code that opens hardware, changes backend, enables output, restarts the
  bridge, or clicks Export. **Do not** add blocking/socket/MIDI/serial/filesystem/subprocess work to the
  200 Hz push loop (`state_manager._push_tick`/`_drive_pack_output`).
- **Do not** apply a global raw-reference offset. **Do not** add time-varying/interpolated rendering.
- **Do not** hardcode SSIDs, cue IDs, GUIDs, track counts, autoloop counts, or note numbers; **do
  not** maintain whitelists of known-good documents; **do not** store literal U0 frames as the
  primary render path (captured frames are oracle evidence only); **do not** guess by cue name or
  nearest key; **do not** reconstruct keys from library order (§0.3).
- **Do not** add an autoloop-under-scripted compositor or any base/default underlay beneath scripted
  gaps — the gap-fill theory is dead (§0.4 Finding 1); scripted is all-zero-seeded carry-forward +
  Static Look overlay + blackout mask, nothing else.
- **Do not** treat the existing verifier's internal re-render as parity proof.
- **Do not** require any new capture anywhere. Unprovable ⇒ `unverified_parity`, never "capture later".
- **Do** treat `unverified_parity` on normal supported content as an open defect to fix within these
  tasks (§0.1) — fail-closed is a holding state, not an exit.
- **Out of scope (fail closed):** any project but the pinned UUID; any venue/profile/universe/fixture
  but RAVE/CH1-19; SoundSwitch ≠ 2.10.3; multi-deck/crossfade; `.ssproj` internals; hardware.

### C.0 Implementation-surface coverage matrix (2026-07-02 audit patch)

This matrix is part of the implementation contract. If a file is named here, the task must either
change it, add a must-fail-then-pass test around it, or explicitly prove it already matches the
target behavior. Leaving one of these surfaces untouched is allowed only with a written reason in the
task closeout.

| Task | Required behavior | Files already named in this spec before the audit | Additional repo files now explicit | Why the additional files matter / miss class | Exact section patched |
| --- | --- | --- | --- | --- | --- |
| C1 | U0-grounded oracle; no internal self-render proof | `soundswitch_parity_oracle.py`, `tools/ssfmt/parity_oracle.py`, `tests/test_soundswitch_parity_oracle.py`, oracle fixtures | `tools/artnet_compare.py`, `tools/ssfmt/re/validate_scripted_capture.py`, `tools/ssfmt/re/validate_autoloop_capture.py`, `tools/ssfmt/re/layered_renderer.py`, `tests/test_artnet_compare.py`, `tests/test_autoloop_oracle.py` | These are the existing parity/capture/oracle-adjacent instruments. If they keep treating U1 or self-render as proof, parity is silently weakened. | Task C1 Files and must-fail tests |
| C2 | Per-document parity lanes through export, verification, load, runtime, and publication | parity registries, `soundswitch_pack_models.py`, `soundswitch_pack.py`, `soundswitch_pack_verifier.py`, `soundswitch_pack_loader.py`, `tools/export_soundswitch_pack.py`, `tests/test_soundswitch_scripted_parity.py` | `soundswitch_pack_runtime.py`, `state_manager.py`, `runtime_status.py`, `scripts/bridge_menubar.py`, `tests/test_runtime_status.py`, `tests/test_bridge_menubar.py`, `tests/test_soundswitch_pack_commands.py`, `tests/test_soundswitch_pack_controller.py`, `tests/test_soundswitch_pack_startup.py` | Lane metadata must survive pack load/reload and be visible operationally. Missing runtime/status surfaces can let `unverified_parity` look healthy or publish as trusted output. | Task C2 Files, verifier, and acceptance |
| C3 | Scripted all-zero seed, sorted events, carry-forward gaps, skip-hold misses, stop/unload/track-change zeroing | `soundswitch_project_decoder.py`, `soundswitch_pack.py`, `soundswitch_laser_player.py`, `soundswitch_parity_oracle.py`, `tests/test_soundswitch_scripted_first_event.py` | `soundswitch_pack_models.py`, `soundswitch_pack_loader.py`, `soundswitch_pack_verifier.py`, `state_manager.py`, `tests/test_soundswitch_laser_player.py`, `tests/test_state_manager_pack_driver.py`, `tests/test_ssfile_reference_convention.py` | Loader/verifier define the boundary frames the runtime receives; `state_manager.py` owns stop/unload/track-change fail-closed behavior. Missing them can either blank gaps or hold stale nonzero frames. | Task C3 Files, intent, tests, acceptance |
| C4 | Scripted `raw_reference` resolved by each `.ssfile`'s embedded exact key; no `raw-1`, library order, nearest key, name matching, or self-render proof | `soundswitch_project_decoder.py`, new `soundswitch_scripted_resolution.py`, `tests/test_soundswitch_scripted_resolution.py` | `soundswitch_pack_models.py`, `soundswitch_pack.py`, `soundswitch_pack_verifier.py`, `soundswitch_pack_loader.py`, `soundswitch_laser_player.py`, `tools/prove_soundswitch_pack_generation.py`, `tools/ssfmt/re/analyze_scripted_layouts.py`, `tools/ssfmt/re/analyze_scripted_ssfile.py`, `tools/ssfmt/re/analyze_ssfile_structure.py`, `tests/test_soundswitch_project_decoder.py`, `tests/test_soundswitch_pack.py`, `tests/test_prove_soundswitch_pack_generation.py`, `tests/test_ssfile_reference_convention.py` | The independent verifier currently has the same old assumption class, loader/player consume resolved fields, and proof/research tools can keep re-legitimizing `raw-1`. Missing verifier/loader blocks parity; missing proof-tool quarantine silently weakens it. | Task C4 Files, steps, must-fail tests, acceptance |
| C5 | Static trigger authority from real MIDI port and learned-control binding coverage; status does not claim unseen static parity | `soundswitch_midi_input.py`, `tests/test_soundswitch_midi_input.py`, `runtime_status.py` | `soundswitch_pack_models.py`, `soundswitch_project_decoder.py`, `soundswitch_pack.py`, `soundswitch_pack_loader.py`, `state_manager.py`, `tools/export_soundswitch_pack.py`, `scripts/bridge_menubar.py`, `tests/test_state_manager_pack_driver.py`, `tests/test_runtime_status.py`, `tests/test_bridge_menubar.py`, `tests/test_soundswitch_pack.py` | Static binding coverage is decoded/exported/loaded before MIDI dispatch, and static precedence/status live in the driver/menubar. Missing these silently reports parity while no learned trigger fired. | Task C5 Files, binding gap, tests, acceptance |
| C6 | Static non-generic maps either proven inert from profile/look data or composed in SS order | `soundswitch_pack.py`, `soundswitch_project_decoder.py`, `tests/test_static_looks.py` | `soundswitch_pack_models.py`, `soundswitch_pack_verifier.py`, `soundswitch_pack_loader.py`, `soundswitch_laser_player.py`, `tests/test_soundswitch_pack.py`, `tests/test_soundswitch_laser_player.py` | Verifier currently recomputes generic-only and loader/runtime carry the profile flag. Missing them can keep `has_intensity_channel=False` or generic-only runtime assumptions after export proves otherwise. | Task C6 Files, violation branch, tests, acceptance |
| C7 | Autoloop selection from learned maps; beatCount from each loop document; beatgrid-tiled phase; no hardcoded 32-beat/19200/note list | `native_autoloop_resolver.py`, generic scene-selection source, `soundswitch_laser_player.py`, `tests/test_native_autoloop_resolver.py`, `tests/test_state_manager_pack_driver.py` | `config.py`, `laser_models.py`, `laser_executor.py`, `laser_director.py`, `laser_config.py`, `config/laser_director.json`, `soundswitch_project_decoder.py`, `soundswitch_pack.py`, `soundswitch_pack_verifier.py`, `soundswitch_pack_loader.py`, `state_manager.py`, `autoloop_controller.py`, `soundswitch_pack_player_config.py`, `soundswitch_pack_runtime.py`, `tools/artnet_compare.py`, `tests/test_laser_config.py`, `tests/test_laser_executor.py`, `tests/test_live_bpm_service.py`, `tests/test_autoloop_controller.py`, `tests/test_soundswitch_pack.py`, `tests/test_soundswitch_laser_player.py`, `tests/test_artnet_compare.py`, `tests/test_t7d_phase_contract.py`, `tests/test_autoloop_oracle.py`, `tests/test_inventory_project_artifacts.py` | The hardcoded 19,200/32-beat model is split across loader, resolver, config, phase tests, and proof tools; note 96 can stay unreachable through scene config/executor even if resolver changes. Missing any of these can block or silently weaken autoloop parity. | Task C7 Files, selection, anchor, tests, acceptance |
| C8 | `unverified_parity` can never drive trusted live output; SS-present suppression/status/reload stay correct | `state_manager.py`, `runtime_status.py`, `tests/test_state_manager_pack_driver.py` | `soundswitch_pack_models.py`, `soundswitch_pack.py`, `soundswitch_pack_verifier.py`, `soundswitch_pack_loader.py`, `soundswitch_laser_player.py`, `soundswitch_pack_runtime.py`, `soundswitch_pack_controller.py`, `scripts/bridge_menubar.py`, `__main__.py`, `soundswitch_pack_player_config.py`, `config/soundswitch_pack_player.example.json`, `tests/test_runtime_status.py`, `tests/test_bridge_menubar.py`, `tests/test_soundswitch_pack_commands.py`, `tests/test_soundswitch_pack_controller.py`, `tests/test_soundswitch_pack_startup.py`, `tests/test_soundswitch_pack_player_config.py`, `tests/test_artnet_truth.py`, `tests/test_artnet_compare.py` | The live gate depends on lane propagation through pack load/reload and operator-visible status. Missing these can let unverified supported content publish, reload, or display as trusted. | Task C8 Files, gate, tests, acceptance |

### Task C1 — Offline parity oracle (pure core + CLI). *Foundation.*
Files: `soundswitch_parity_oracle.py` (pure), `tools/ssfmt/parity_oracle.py` (CLI/IO),
`tools/artnet_compare.py`, `tools/ssfmt/re/validate_scripted_capture.py`,
`tools/ssfmt/re/validate_autoloop_capture.py`, `tools/ssfmt/re/layered_renderer.py`,
`tests/test_soundswitch_parity_oracle.py`, `tests/test_artnet_compare.py`,
`tests/test_autoloop_oracle.py`, `tests/fixtures/soundswitch/parity_oracle/…` (small committed
reduced fixtures derived from the existing capture: for each captured SSID, a table of
`(elapsed_ms, U0_frame)` samples at cue boundaries + neighbors; the 3 static look U0 held frames; a
handful of autoloop `(phase_tick, U0_frame)` per covered target; the DD42028C negative-control table).
- Pure core API: `classify_scripted(document, samples) -> OracleReport`,
  `classify_autoloop(document, phase_samples) -> OracleReport`,
  `classify_static(pre_rendered_frame, u0_held) -> OracleReport`. No file/socket access in the core.
- CLI reads the capture, builds the elapsed→U0 mapping (B.1), and runs the core.
- The scripted classifier implements the carry-forward checks of B.1: pre-first-event alignment
  (pack first event vs U0 first lit frame), mid-gap holds, and post-boundary carry-forward
  (channels a cue does not touch keep prior values). U0-lit gap regions are classified
  **dropped-cue** vs **missing-hold** (the autoloop-fill class is retired per §0.4 Finding 1).
  Fixtures include mid-gap and post-boundary hold samples, not only boundary-adjacent samples.
- **Must-fail-then-pass:** against **today's** pack, the oracle MUST report FAIL for AE9E3C61,
  FC10FC02, and DD42028C, and the scripted first-event BLIP for Rihanna/9947C65E; and PASS for the
  Rihanna/9947C65E lit-region value match. A test asserts these exact starting verdicts (so a future
  regression that "passes everything" is caught). Existing parity tools/tests must also prove they do
  not use U1, pack self-render, `oracle_rendered` frames, or sidecar-only truth as the acceptance
  oracle; those instruments may summarize coverage, but only U0 evidence can prove byte parity.
- Acceptance: `python3 -m unittest tests.test_soundswitch_parity_oracle` green; oracle reproduces the
  Part A per-track numbers within tolerance from the committed fixtures (no live capture needed).

### Task C2 — Parity registry + fail-closed publication (extends baseline Tasks 1–2).
Files: `tests/fixtures/soundswitch/scripted_parity_registry.json` (+ autoloop/static registries),
`soundswitch_pack_models.py`, `soundswitch_pack.py`, `soundswitch_pack_verifier.py`,
`soundswitch_pack_loader.py`, `soundswitch_pack_runtime.py`, `state_manager.py`, `runtime_status.py`,
`scripts/bridge_menubar.py`, `tools/export_soundswitch_pack.py`,
`tests/test_soundswitch_scripted_parity.py`, `tests/test_runtime_status.py`,
`tests/test_bridge_menubar.py`, `tests/test_soundswitch_pack_commands.py`,
`tests/test_soundswitch_pack_controller.py`, `tests/test_soundswitch_pack_startup.py`.
- Add the 3-state lane (B.2) to each scripted/autoloop/static document's provenance. Lane assignment
  is **computed** by a pure classifier from `(document, oracle_report, structural checks)` — the
  registry stores evidence, never a hand-curated allow-list (§0.3). Expected initial verdicts (not
  pinned outcomes): AE9E3C61, FC10FC02, DD42028C, and every uncaptured
  `shared_441_dictionary_timeline` doc = `unverified_parity`; Rihanna/9947C65E lit-region =
  `oracle_proven` only after Task C3/C4 make the oracle pass; static looks 0/24/16 = `oracle_proven`
  (already byte-match), the empty-default slots = `oracle_proven` (zero) once Task C6's non-generic
  assertion holds, else `unverified_parity`.
- Verifier: `oracle_proven` requires committed U0-oracle evidence (source hash + capture id + per-
  boundary totals); export **fails closed** (raises) on an active document that is `unverified_parity`
  unless the explicit unverified-publish path is implemented through the named C8 command/config
  surfaces and tests. If that path is not implemented, `unverified_parity` active documents always
  raise/fail closed.
- Loader/runtime/status: the lane and its evidence summary must survive pack JSON, verifier output,
  `LoadedDocument`, `PackRuntime`, pack reload/swap, `runtime_status`, and the menubar/status surface.
  A document in `unverified_parity` must be visibly distinct from healthy output everywhere it is
  reported; no status string may collapse it into "pack ok" or "oracle_proven".
- **Must-fail-then-pass:** a test asserts that exporting today's pack marks AE9E3C61/FC10FC02/DD42028C
  `unverified_parity` and that publication of them fails closed; after Task C3/C4 fixes, they flip to
  `oracle_proven` (or stay fail-closed with a recorded reason). Runtime/status tests assert the lane is
  present after a pack load/reload and appears as an explicit degraded/unverified status. Pure-function
  seam: registry classification is a pure function of `(document, oracle_report)`.

### Task C3 — Scripted carry-forward / first-event fidelity (gap-fill branch DEAD — §0.4 Finding 1).
Files: `soundswitch_project_decoder.py`, `soundswitch_pack_models.py`, `soundswitch_pack.py`,
`soundswitch_pack_verifier.py`, `soundswitch_pack_loader.py`, `soundswitch_laser_player.py`
(renderer hold semantics only if divergent from the model), `state_manager.py` (stop/unload/
track-change zeroing and scripted suppression only), `soundswitch_parity_oracle.py` (dropped-cue vs
missing-hold classification), `tests/test_soundswitch_scripted_first_event.py`,
`tests/test_soundswitch_laser_player.py`, `tests/test_state_manager_pack_driver.py`,
`tests/test_ssfile_reference_convention.py`.
Runs **after C4** — a held value is only correct if the cue that seeded it resolved correctly.
- **Intent:** make the exporter+renderer reproduce SS's cache model exactly (§0.4 Finding 1):
  frames form a step function seeded from **all-zero**; each boundary frame = previous boundary
  frame **plus this cue's converted attribute changes** (channels a cue does not touch keep their
  prior values); empty/unresolved cues are **skipped** — the prior hold continues, never a blank;
  output is dark only before the earliest cue; holds persist through gaps until the next cue. Do
  **not** add autoloop-under-scripted output; `native_autoloop_resolver.py` scripted suppression stays
  correct. If `state_manager.py` is touched, the only valid changes are tests or fail-closed/zeroing
  preservation around stop, unload, track change, discontinuity, reload-wait, and SS-present
  suppression.
- Fix early-cue extraction: every timeline event SS serialized must appear in the pack with its
  time; the pack's first event must align with U0's first lit frame. Use the oracle's dropped-cue
  vs missing-hold classification per SSID to locate which shape each divergence is.
- **Must-fail-then-pass:** oracle reports Rihanna BLIP=2,822 and `{9947C65E…}`'s 1,276 mid-track
  dark frames today; after C3(+C4) the pre-first-event and mid-gap regions match U0 (BLIP→0 and
  missing-hold→0 within timing tolerance) for all four captured SSIDs. A unit test feeds a
  synthetic document with a multi-cue timeline + a gap + an empty cue and asserts carry-forward
  (untouched channels persist) and skip-hold (an empty cue does not blank). Pure seam: the
  dropped-cue/missing-hold classifier and the carry-forward composition are pure functions. Driver
  tests must also prove stop/unload/track-change/discontinuity still emit ZERO rather than holding the
  last scripted nonzero frame.
- **Acceptance / generalization:** captured witnesses show zero BLIP and zero missing-hold; the
  carry-forward property is asserted structurally (a property of the composition over *any*
  document), which is the generalization proof for future tracks. Divergence that survives ⇒
  `unverified_parity` (temporary blocker) with the failing boundary recorded.

### Task C4 — Scripted cue-resolution: file-embedded exact-key lookup (runs before C3)
The DD42028C-class fix, per §0.4 Finding 2.
Files: `soundswitch_project_decoder.py`, `soundswitch_pack_models.py`, `soundswitch_pack.py`,
`soundswitch_pack_verifier.py`, `soundswitch_pack_loader.py`, `soundswitch_laser_player.py`, new pure
`soundswitch_scripted_resolution.py`, `tools/prove_soundswitch_pack_generation.py`,
`tools/ssfmt/re/analyze_scripted_layouts.py`, `tools/ssfmt/re/analyze_scripted_ssfile.py`,
`tools/ssfmt/re/analyze_ssfile_structure.py`, `tests/test_soundswitch_scripted_resolution.py`,
`tests/test_soundswitch_project_decoder.py`, `tests/test_soundswitch_pack.py`,
`tests/test_prove_soundswitch_pack_generation.py`, `tests/test_ssfile_reference_convention.py`
(plus reuse baseline Task 3/4 oracle-canonicalization CLI).
- **Step 1 — inspect the current decoder** (`soundswitch_project_decoder.py:538-544`): determine
  whether it already parses each `.ssfile`'s serialized `(GUID, stored_key)` records or
  reconstructs keys from library order / a `raw−1` rule. The evidence packet proves the **binary**
  semantics, not what the bridge currently does — establish that first, then fix or re-label
  accordingly.
- **Step 2 — implement §0.4 Finding 2 exactly:** parse the file's embedded `AttributesCueMap`
  records (16-byte GUID + u32 `stored_key`, as serialized), build the key→GUID map, resolve each
  timeline entry's `raw_reference` by **exact-key equality**. A miss ⇒ no-cue ⇒ the cache entry
  **skips** (prior hold continues, per §0.4 Finding 1) **and** is surfaced loudly (a miss inside a
  healthy supported file usually means a decoder misparse — investigate, don't absorb). No offset,
  no library-order reconstruction, no nearest-key, no cue-name matching
  (`soundswitch_pack_parity_root_cause_spec.md:499-501`).
- **Step 3 — sweep every consumer/proof path:** the pack model must document the exact semantics of
  `raw_reference`, `stored_key`, `resolved_stored_key`, and `resolved_cue_guid`; `soundswitch_pack.py`
  and `soundswitch_pack_loader.py` must preserve the resolved key/GUID without recomputing it; the
  verifier must stop enforcing `stored == raw - 1` and must not accept `oracle_rendered`/pre-rendered
  frames as parity proof without C1 U0 evidence. Historical proof/research tools that encode raw-1,
  direct, nearest-key, or library-order candidates must be updated to call the pure resolver or be
  explicitly labeled non-authoritative so they cannot satisfy an acceptance gate.
- **DD42028C caveat (do not lose):** prior empirical data showed a `raw−1`-style match for DD42028C
  while the binary does **no** subtraction — this is a bridge **representation/label mismatch**
  (the file's stored keys equal `raw−1` on 69/91 rows, `direct` on 27/91, and **no single offset
  satisfies all 91** — e.g. raw 186→key 187, raw 188→key 187, raw 4→key 2/3;
  `soundswitch_pack_parity_root_cause_spec.md:170-217`). Do not "simplify" by overwriting the
  capture observations with the binary conclusion; the fix is the mechanism (exact key against the
  file's own permutation), and the old empirical table becomes the regression fixture.
- **Must-fail-then-pass:** the pure resolver, run with today's key source, fails DD42028C's
  permutation fixture and AE9E3C61's divergent boundaries (the bridge picked the library-adjacent
  "MASTER STROBE" `(255,255)` where U0 shows "STROBE" `(110,0)` on CH10/CH11); after the fix it
  reproduces every fixture row exactly and AE9E3C61/FC10FC02 pass the U0 oracle. The global-offset
  rejection test is retained (`raw-1`, direct, `raw±2/3` cannot satisfy all rows). Existing tests that
  currently encode old assumptions must be flipped: `tests/test_soundswitch_project_decoder.py`
  raw-one/raw-maximum cases, `tests/test_ssfile_reference_convention.py`, and any
  `tests/test_soundswitch_pack.py` path that treats internal verifier/self-render as proof must fail
  before the exact-key/U0-proof fix and pass after.
- **Acceptance / generalization:** resolution consumes only the file's own bytes ⇒
  content-independent by construction; with the captured witnesses oracle-proven, every
  `shared_441_dictionary_timeline` document (and future authored tracks of the same serialization)
  becomes `algorithm_generalized`. A file whose serialized map cannot reproduce U0 by exact key ⇒
  `unverified_parity` (temporary blocker; likely a new layout/version to decode — surface it),
  never an offset fallback.

### Task C5 — Static MIDI trigger authority.
Files: `soundswitch_midi_input.py`, `soundswitch_pack_models.py`, `soundswitch_project_decoder.py`,
`soundswitch_pack.py`, `soundswitch_pack_loader.py`, `state_manager.py`, `runtime_status.py`,
`scripts/bridge_menubar.py`, `tools/export_soundswitch_pack.py`, `tests/test_soundswitch_midi_input.py`,
`tests/test_state_manager_pack_driver.py`, `tests/test_runtime_status.py`, `tests/test_bridge_menubar.py`,
`tests/test_soundswitch_pack.py`.
- Root-cause `[SS-MIDI] input port gone` (`:454-484`): fix the exact-port matcher/retry so a present
  static-controller port is not spuriously declared gone (verify `_port_present` name-matching against
  the real enumerated port names; ensure the never-seen fast-retry churn does not corrupt a live port's
  enumeration per the `:474-481` comment). Preserve RW-4 overlay-trust (`state_manager.py:3896-3921`).
- Make the observed-vs-authored binding gap explicit: if the operator's held-static device/notes are not
  in the pack's learned controls (today: only `DDJ-800 StaticOverride16`), status reports "static
  trigger unobserved / binding gap" and static parity is **not** claimed (fail-closed), rather than
  silently rendering base. The binding coverage check must be derived from decoded/exported learned
  controls, preserved through `soundswitch_pack_loader.py`, consumed by the MIDI group, and surfaced in
  `runtime_status.py`/`scripts/bridge_menubar.py`.
- **Must-fail-then-pass:** a unit test injecting a present-then-flapping port asserts the port is NOT
  declared gone while present; a test asserts an unbound held-static attempt surfaces the gap flag in
  runtime status and menubar output; a state-manager test asserts static override precedence remains
  above scripted/autoloop base after the new status path. Pure seam: `_port_present(port_list, name)`
  and the learned-binding coverage classifier are tested directly.
- **Acceptance / generalization:** the matcher/retry fix is device-name-general (no hardcoded port
  names beyond config); binding coverage is computed from the pack's learned controls — any future
  learned static binding is honored by the same coverage check, never a fixed list.

### Task C6 — Static non-generic export assertion (MANDATORY)
§0.4 Finding 3 upgraded this from belt-and-suspenders to necessary.
Files: `soundswitch_project_decoder.py`, `soundswitch_pack_models.py`, `soundswitch_pack.py`,
`soundswitch_pack_verifier.py`, `soundswitch_pack_loader.py`, `soundswitch_laser_player.py`,
`tests/test_static_looks.py`, `tests/test_soundswitch_pack.py`, `tests/test_soundswitch_laser_player.py`.
- **Intent:** at export, for **every** static slot (the current 32 and any future edit), assert
  against the RAVE profile's per-channel attribute **types** and the look's stored map **values**
  that the four non-generic maps contribute nothing to CH1-19: **(a)** no intensity-typed channel
  exists; **(b)** strobe fractions are 0.0; **(c)** no pan/tilt-typed channel, or the position
  target is null; **(d)** colour resolves to the generic-equivalent value on every colour-typed
  channel. Generic-only rendering is **proven** only when the assertion passes — never assumed from
  the runtime's current behavior.
- **Violation branch (supported content ⇒ blocker, not a resting state):** a violating slot is
  flagged `unverified_parity` and surfaced with the exact map/channel that violated. Because static
  looks are supported authored content, the path to byte-exact parity is then dedicated-path
  composition in SS's order (static maps overwrite intensity/colour/pan/tilt/strobe before the emit
  loop; attribute-typed channels emit from the dedicated setter path; default-type channels emit
  cue⊕static-generic — §0.4 Finding 3), proven against U0 evidence. A silent generic-only export of
  a violating slot is forbidden. The verifier and loader must carry the profile/channel assertion
  result; a hardcoded `has_intensity_channel=False` or generic-only recomputation in the verifier is
  not an acceptance proof.
- **Must-fail-then-pass:** a synthetic look with empty generic + a colour/strobe/position value that
  *would* map to a CH1-19 attribute type must be flagged; the real project slots (the authored
  looks, the OFF/BLACK OUT pair, and the empty defaults) pass — expected; if any real slot fails,
  that is a live blocker to surface, not to suppress. Pure seam: the assertion is a pure function of
  `(look record, profile channel-type table)`. Existing generic-only static renderer/verifier tests
  must be split into two classes: proven-inert profile/look data passes, and a synthetic non-generic
  contribution fails until dedicated-path composition is implemented and U0-proven.
- **Acceptance / generalization:** with the assertion in the export path, every future authored look
  either proves generic-only byte-exactness by construction or is loudly flagged — no new capture,
  no per-look manual approval.

### Task C7 — Autoloop selection (learned-map general) + beatgrid-derived anchor + edge-case unit sweep.
Files: `native_autoloop_resolver.py`, `config.py`, `laser_models.py`, `laser_executor.py`,
`laser_director.py`, `laser_config.py`, `config/laser_director.json`, `soundswitch_project_decoder.py`,
`soundswitch_pack.py`, `soundswitch_pack_verifier.py`, `soundswitch_pack_loader.py`, `state_manager.py`,
`autoloop_controller.py`, `soundswitch_laser_player.py` (autoloop render only if a defect is proven),
`soundswitch_pack_player_config.py`, `soundswitch_pack_runtime.py`, `tools/artnet_compare.py`,
`tests/test_native_autoloop_resolver.py`, `tests/test_state_manager_pack_driver.py`,
`tests/test_laser_config.py`, `tests/test_laser_executor.py`, `tests/test_live_bpm_service.py`,
`tests/test_autoloop_controller.py`, `tests/test_soundswitch_pack.py`,
`tests/test_soundswitch_laser_player.py`, `tests/test_artnet_compare.py`,
`tests/test_t7d_phase_contract.py`, `tests/test_autoloop_oracle.py`,
`tests/test_inventory_project_artifacts.py`.
- **Selection (§0.4 Finding 5):** note 96 is a **bridge resolver gap** — the SS mechanism is a
  generic learned `(data_byte, channel, type) → control-path` map with no note-96 special case, and
  the `(0, 96) → SSAutoLoop4` binding **exists** in this pack. Fix the resolver's general selection
  rule so any binding present in the pack's selection map can fire (map the drop-policy condition to
  note 96 here), with **no hardcoded note list and no hardcoded autoloop count** — future packs with
  different or more bindings must work unchanged. The `unverified_parity`+surface branch applies
  **only** to a pack whose mapping is genuinely absent — not this one. The selection fix must include
  the full scene chain: laser config/policy, `LaserResolvedScene`, executor/director note emission,
  pack `selection_map`/`iac_selections`, verifier crosswalk, loader bindings, and state-manager runtime
  wiring. A config/policy mismatch that keeps note 96 unreachable is the same parity defect as a
  resolver miss.
- **Anchor (§0.4 Finding 4):** replace the edge-observation anchor (`anchor_beat` at the first
  scene edge, `native_autoloop_resolver.py:191-199`) with the derived beatgrid tiling: `beatCount`
  from the loop document (`GetAutoLoopNumberBeats` semantics; default 32; never hardcoded),
  `window_start = beat0 + k·beatCount` (the tile containing the current beat),
  `phase_tick = int((beat_pos − window_start) × 600)`, pre-roll/negative beats wrapped mod
  beatCount. Prove via the oracle that this reproduces U0 phase on the captured loops — that proof
  simultaneously settles the residual bridge-beatgrid beat-0 equivalence question (§D.2 U4). Do not
  regress the landed phase-zero guard. Remove hardcoded 19,200/32-beat stamping from loader/resolver
  paths (`AUTOLOOP_CYCLE_TICKS`, `AUTOLOOP_ARM_PHRASE_BEATS`, and derived 600-tick tests are allowed
  only as defaults after the loop document supplies or defaults `beatCount`). Near-empty loop exports
  (SSAutoLoop5/18/3) must be
  oracle-checked vs U0 (correct-dark vs exporter under-render ⇒ fix extraction) or flagged
  `unverified_parity` as temporary blockers.
- Edge-case sweep unit tests (§6.2 items 10–13): precedence combinations
  (blackout > emergency > static-override > scripted/autoloop base; SS-present suppression; reload-wait
  latch) each asserted; a mid-playback `set_pack_runtime` swap asserted not to emit a stale nonzero
  frame; a BPM 160→155 change asserted not to perturb scripted (elapsed-keyed) output and to keep
  autoloop phase continuous (beatgrid-derived windows are BPM-change-safe by construction — assert it).
- **Must-fail-then-pass:** a test proving SSAutoLoop4 is unreachable today (resolver never emits
  note 96) and reachable after the fix via the general rule (assert there is no note-96 literal
  special-case in the resolver); an anchor test proving the beatgrid-tiled phase matches the
  captured loops' U0 phase where an edge-anchored phase with an injected observation latency does
  not. Existing tests that hardcode `cycle_ticks=19200`, `AUTOLOOP_CYCLE_TICKS`, 32-beat wrapping,
  `AUTOLOOP_TICKS_PER_BEAT == 600`, hardcoded note lists, or fixed autoloop counts must fail before
  the per-document `beatCount`/learned-map fix and pass after by deriving those values from the loaded
  document or explicit defaulted metadata.
- **Acceptance / generalization:** selection reads bindings from the pack; the anchor reads
  beatCount from the loop document; both are content-independent, so future autoloops are covered by
  ≥1 oracle-proven captured witness + the structural rule (B.1), with no per-loop work.

### Task C8 — Live fail-closed parity gate (wire the flag model into the driver, read-only).
Files: `soundswitch_pack_models.py`, `soundswitch_pack.py`, `soundswitch_pack_verifier.py`,
`soundswitch_pack_loader.py`, `soundswitch_laser_player.py`, `soundswitch_pack_runtime.py`,
`soundswitch_pack_controller.py`, `state_manager.py` (`_drive_pack_output` selection only),
`runtime_status.py`, `scripts/bridge_menubar.py`, `__main__.py`,
`soundswitch_pack_player_config.py`, `config/soundswitch_pack_player.example.json`,
`tests/test_state_manager_pack_driver.py`, `tests/test_runtime_status.py`,
`tests/test_bridge_menubar.py`, `tests/test_soundswitch_pack_commands.py`,
`tests/test_soundswitch_pack_controller.py`, `tests/test_soundswitch_pack_startup.py`,
`tests/test_soundswitch_pack_player_config.py`, `tests/test_artnet_truth.py`, `tests/test_artnet_compare.py`.
- When parity-live (pack enabled AND `soundswitch_connected == False`), a document whose lane is
  `unverified_parity` must not render as trusted output: emit the safe base (ZERO scripted/autoloop;
  held manual static still honored) and publish an explicit `operational_state = "unverified_parity"`
  unless the operator has acknowledged it. No change to the SS-present shadow path (already ZERO to
  backend, `:4116`). No blocking work added to the tick. The gate must consume lane metadata from the
  loaded pack, survive startup/reload/controller swaps, and update status/menubar output without
  changing backend selection or SS-present suppression. If an operator-acknowledged unverified path is
  implemented, its command/config surface must be named in this task (`runtime_status.py`,
  `soundswitch_pack_player_config.py`, `config/soundswitch_pack_player.example.json`, `__main__.py`)
  and tested before code changes; otherwise the only behavior is fail-closed safe base.
- **Must-fail-then-pass:** a driver test with an `unverified_parity` scripted doc asserts safe-base +
  the status flag when parity-live, and unchanged behavior when SS-present. Startup/reload/controller
  tests assert an unverified lane cannot be promoted to trusted output during pack load, pack swap, or
  command handling; runtime/menubar tests assert it is visibly degraded. Pure seam: the lane→action
  decision is a pure helper.
- **Acceptance / generalization:** driver tests green; the gate reads lanes from the registry
  generically (no document-specific branches). The gate is a *temporary-state guard* per §0.1 —
  ship still requires the `unverified_parity` set on supported content to be **empty** (E.4).

---

## Part D — Verification (NO new capture is a ship gate)

- **Ship proof = the offline oracle (Task C1) replaying the EXISTING capture**, per surface:
  - It **fails** against today's renderer/exporter (AE9E3C61, FC10FC02, DD42028C, scripted first-event
    BLIP + mid-gap missing-holds) and **passes** after the fixes. `unverified_parity` at ship is
    acceptable **only** for genuinely out-of-scope / structurally-unsupported documents with a
    recorded reason — a normal supported document left `unverified_parity` means the work is not
    done (§0.1). DD42028C stays the negative control **against the old resolver** (pinned as a
    permanent regression fixture); after Task C4 it must resolve and pass like any other supported
    track — it is a witness, not a special case (§0.3).
  - Content not in the capture is covered by **algorithm generalization** (B.1): a layout is claimed
    parity-safe only when it is content-independent **and** has ≥1 `oracle_proven` witness. No per-item
    capture, ever. This is how the **general model** — not each future track individually — is
    proven: byte-exact for future authored content **by construction**, with structural decode
    assertions surfacing anything novel instead of silently absorbing it.
- **Software gates (must be green)** — from `soundswitch_exporter_remaining_work.md:252-269`:
  ```bash
  python3 -m unittest \
    tests.test_state_manager_pack_driver tests.test_soundswitch_pack_commands \
    tests.test_runtime_status tests.test_bridge_menubar tests.test_soundswitch_frame_sender \
    tests.test_enttec_dmx_pro tests.test_soundswitch_pack_startup \
    tests.test_soundswitch_pack_controller tests.test_soundswitch_pack \
    tests.test_soundswitch_pack_player_config \
    tests.test_soundswitch_laser_player \
    tests.test_soundswitch_parity_oracle tests.test_soundswitch_scripted_parity \
    tests.test_soundswitch_scripted_resolution tests.test_soundswitch_scripted_first_event \
    tests.test_soundswitch_project_decoder tests.test_ssfile_reference_convention \
    tests.test_prove_soundswitch_pack_generation \
    tests.test_static_looks tests.test_soundswitch_midi_input tests.test_native_autoloop_resolver \
    tests.test_laser_config tests.test_laser_executor tests.test_live_bpm_service \
    tests.test_autoloop_controller tests.test_artnet_compare tests.test_artnet_truth \
    tests.test_t7d_phase_contract tests.test_autoloop_oracle tests.test_inventory_project_artifacts
  python3 -m unittest discover tests
  python3 tools/check_docs_metadata.py && python3 tools/check_agent_contracts.py && python3 tools/check_docs_drift.py
  python3 tools/check_docs_staleness.py --report
  git diff --check
  ```
- **Optional, non-blocking (post-ship):** a fresh live re-capture, and — only if U1/U4 below resist
  the assertion/oracle route — a live decompile of the venue/profile channel-type readers and the
  `BeatSpace`/`SeratoBeatGrid` beat-0 derivation. Confidence checks only, never ship gates. The
  A.3.d and A.4.c decompiles are **done** and recorded in the evidence packet (§0.4).

### D.2 Remaining-unknowns ledger (each with its closing instrument; none needs more decompilation or a new capture)

| ID | Unknown | Why still unknown | Affects supported content? | Codex decision branch | Proof instrument | Blocker class |
| --- | --- | --- | --- | --- | --- | --- |
| U1 | Do the RAVE profile's channel attribute types / stored static-map values let intensity/strobe/colour/position reach CH1-19? | Profile + look **data**, not in the decompiled functions (§0.4 Finding 3) | Yes — static looks | C6 assertion pass ⇒ generic-only proven; fail ⇒ dedicated-path composition proven vs U0 | C6 export-time assertion over `(profile channel-type table, look bytes)` + captured-look byte-match | **Blocker until asserted** (expected pass) |
| U2 | Does the current bridge decoder parse the file's serialized `(GUID, stored_key)` records, or reconstruct keys (library order / `raw−1` label)? | The binary proves SS semantics, not bridge code (§0.4 Finding 2 caveat) | Yes — all scripted | C4 step 1 inspects `soundswitch_project_decoder.py:538-544`; fix or re-label | C4 must-fail-then-pass on the DD42028C permutation fixture + AE9E3C61/FC10FC02 U0 oracle | **Blocker until C4 lands** |
| U3 | Exact held frame after a key-miss (miss ⇒ skip ⇒ hold) interacting with a mis-resolved cue | Data-dependent edge; the binary shows skip-hold structurally but not per-file outcomes | Edge content only | Exporter mirrors skip-hold; every miss on supported content surfaced as probable misparse | Oracle per-boundary held-value confirmation (C1/C3) | Blocker only if witnessed in a supported file |
| U4 | Does the bridge's beatgrid beat 0 equal SS's `BeatSpace` beat 0 (and is 32-beat tiling phrase-aligned) on real tracks? | `BeatSpace`/`SeratoBeatGrid` internals not decompiled; beatgrid-data property | Yes — autoloop phase | C7 derives windows from bridge beatgrid tiling; oracle compares phase to U0 on captured loops | U0 oracle phase comparison (C7) | **Blocker until the oracle passes on captured loops** |
| U5 | Are the near-empty autoloop exports (SSAutoLoop5/18/3: 1–2 events, render dark) faithful to U0, or exporter under-render? | Never compared to U0 yet | Yes — those loops | Oracle-check U0 during those loops; lit U0 ⇒ fix extraction | U0 oracle on captured loop windows (C7) | **Blocker until checked** |
| U6 | When should the resolver *musically* emit note 96 (drop-policy vs operator "BY GENRE" intent)? | Operator-policy question, not a binary/code fact (§0.4 Finding 5) | Selection timing only — not per-frame byte parity | C7 makes the binding fireable via the general rule; default = drop-policy note; surface for operator confirmation | Resolver unit test + operator confirmation ([[project_autoloop_intelligence]]) | Not a parity blocker; surfaced |
| U7 | Byte parity of authored content with **no captured witness of its layout/serialization version** | No U0 sample exists; new capture is excluded by rule | Future content | `algorithm_generalized` iff content-independent pipeline + ≥1 proven witness of that layout; a truly novel layout ⇒ `unverified_parity` + loud surface (decode work, then re-prove) | Structural content-independence tests + witness oracle passes (B.1) | Out-of-scope fail-closed **only** for genuinely novel/unsupported formats; otherwise a blocker to decode |

---

## Part E — Constraints, invariants, live-safety, self-review

### E.1 Invariants that MUST hold (from `soundswitch_exporter_remaining_work.md:205` + runtime_invariants)
- `StateManager` is the sole `DeckState` writer and sole per-tick pack-frame submitter; the 200 Hz loop
  gains no blocking/socket/MIDI/serial/filesystem/subprocess work.
- Source SoundSwitch project is read-only; identity is exact (reject any non-pinned UUID); only verified
  packs load; reload/export never enables output, changes backend, starts the bridge, or opens hardware.
- Direct DMX and MIDI-laser output stay mutually exclusive; blackout/emergency wins; SS-present
  suppression intact (bridge must not fight U0 on physical output).
- Static Override + blackout precedence remain above base scripted/autoloop; snap-and-hold only (no
  time-varying output); mirror asserts a single 19-ch output; nothing nonzero beyond CH19.
- Status/logs never leak paths/ports/device-names/UUIDs/raw frames.

### E.2 Live-safety
- The scripted zero-blip fix must **not** introduce a stuck-non-zero frame on a real stop/unload/track-
  change/discontinuity — those must still zero. Directional safety: fail-closed to ZERO on uncertainty
  (the driver already does, `:4134-4153`); the fail-closed parity gate (C8) must never *hold* output.
- No task enables hardware, changes backend, or restarts the bridge (operator-only, gated by the
  physical kill path). After any operator restart: `pgrep -f rb_ss_bridge_v2 | wc -l` must be `1`.

### E.3 Nine-point pre-handoff self-review (adversarial)
1. **Every claim labeled** confirmed/assumed/unknown — done in Part A + §0.4; the former unknowns
   (A.3.d gap-fill, A.4.c anchor origin) are now CLOSED by the recorded evidence packet; the live
   remaining unknowns are enumerated with closing instruments in §D.2.
2. **Verified against CURRENT code** (HEAD `c59d78c`) — the 2026-07-02 implementation-surface audit
   re-read the C1-C8 decoder/model/exporter/verifier/loader/runtime/status/test surfaces; the
   phase-zero guard, driver gates, generic-only render, old `raw_reference` assumptions, and
   hardcoded autoloop constants were confirmed as implementation targets.
3. **Pending-state guard** — Task C7/C8 assert precedence across *all* active pending states
   (blackout/emergency/static-override/reload-wait/SS-present), not only the new lane vs one other.
4. **Mode-transition cleanup** — the new `unverified_parity` lane is read-only in the driver (no new
   mutable tick state); Task C7 asserts reload-swap and BPM-change transitions don't leak stale frames.
5. **Third-party API completeness** — the SoundSwitch cue/static/autoloop composition is grounded in
   the **recorded live decompile** evidence packet (§0.4: exact functions + addresses for the cache
   rebuild, cue-map read, static setters, autoloop layout, and control mapping); the oracle's
   elapsed→U0 join uses the exact `(sequence, dmx_sha256)`→`mono_ns` chain, not a hand-waved "match".
6. **Cross-checked against existing code** — the decoder's current key path
   (`soundswitch_project_decoder.py:538-544`, historically described as `raw_reference-1 →
   stored_key`) is exactly what Task C4 step 1 must inspect and correct to file-embedded exact-key
   resolution (§0.4 Finding 2); autoloop bindings stay the canonical `iac_selections`-derived
   `_autoloop_bindings`; no local re-derivation.
7. **Pure-function seams** — every task names a pure core (oracle classifiers, registry classifier,
   resolver, `_port_present`, static non-generic assertion, lane→action) testable without
   files/subprocess.
8. **Live safety explicit** — E.2; snap-forward-only, never clobber live output, fail-closed to ZERO.
9. **Adversarial self-review** — I attacked the reframe and **partially refuted it** (scripted mechanism
   and "values correct" claims) with capture evidence; forced the specific failure (AE9E3C61 wrong strobe
   cue; FC10FC02 0.6% match; deterministic-in-elapsed zeros). The draft's residual risk — "what if the
   U0-lit gaps are SS autoloop gap-fill?" — is now **closed by the recorded binary evidence** (§0.4
   Finding 1: no underlay; all-zero seed + carry-forward hold), so Task C3 implements the exporter
   branch directly instead of disambiguating first. The remaining ways this spec could be wrong are
   exactly the §D.2 unknowns, each with a named closing instrument (C6 assertion, C4 decoder
   inspection, U0 oracle) — none silently assumed.

### E.4 SHIP GATE (the checklist that means "done")

**Definition of done:** *perfect parity = byte-exact, U0-oracle-proven (or
algorithm-generalized-by-construction) CH1-19 output for **every** normal supported authored
document in the locked scope (§0.1/§0.2).* Fail-closed (`unverified_parity`) is a **safety state,
never a success condition** for supported content. Explicitly insufficient: "probably correct";
"passes the internal verifier"; "works for the current captured tracks"; "most things pass and the
rest fail closed".

- [ ] Offline oracle (C1) committed; **fails** on today's pack for AE9E3C61/FC10FC02/DD42028C +
      scripted first-event BLIP + mid-gap missing-holds; **passes** after C3/C4. The old-resolver
      DD42028C fixture stays as the permanent negative-control regression.
- [ ] Cue resolution is file-embedded exact-key (C4): the DD42028C permutation fixture resolves
      exactly; AE9E3C61 + FC10FC02 are oracle-proven; no offset/nearest-key/library-order path
      remains in code; the DD42028C bridge-label caveat is recorded where the decoder documents its
      key semantics.
- [ ] Scripted carry-forward model (C3): all-zero seed, previous+changes composition, skip-hold on
      empty/unresolved cues, first-event alignment — structural unit-proof + all four captured
      SSIDs oracle-proven end-to-end (BLIP=0, missing-hold=0, VALUE_DIFF=0 outside timing
      tolerance).
- [ ] Every active scripted/autoloop/static document ends `oracle_proven` or
      `algorithm_generalized`; **zero normal supported documents remain `unverified_parity`** (any
      that do are open defects and block ship); only genuinely out-of-scope /
      structurally-unsupported items are fail-closed, each with a recorded reason (C2). Lanes are
      computed, never hand-listed; export fails closed on unproven active docs.
- [ ] `shared_441_dictionary_timeline` reaches `algorithm_generalized` via its passing captured
      witnesses (AE9E3C61 resolved) — and the same rule covers arbitrary future authored
      tracks/loops: no hardcoded SSIDs/cue-IDs/counts/whitelists anywhere (grep-level check).
- [ ] Static: captured looks `oracle_proven`; the **mandatory** C6 profile/channel/stored-value
      assertion passes for all slots — or violators are surfaced as blockers with the
      dedicated-path composition scheduled (never silently exported); trigger-authority port fix
      (C5) landed with the observed-vs-authored gap surfaced.
- [ ] Autoloop: phase-zero guard intact; selection driven by the pack's learned map generally
      (note 96 fires via the existing binding; no hardcoded notes/counts); anchor = beatgrid-tiled
      `window_start` with `phase_tick = (beat_pos − window_start) × 600`, oracle-proven on captured
      loops (closes §D.2 U4); near-empty loops oracle-checked (§D.2 U5) or flagged as blockers.
- [ ] §6.2 sweep: items 1–3,5,6,8 proven; 4 and 7 closed by the evidence packet + oracle
      confirmation; 9 closed by C6; 10–14 unit-swept (C7).
- [ ] Live fail-closed parity gate (C8) wired; SS-present shadow path unchanged; no tick-loop
      regressions. The gate is a temporary-state guard, not a parity substitute.
- [ ] All software gates green (Part D); `soundswitch_exporter_remaining_work.md:274-291` completion
      boxes updated (offline oracle box checkable; independent-review + operator-hardware boxes remain).
- [ ] **Only remaining external gate = the operator's physical hardware/optical/kill-path run** (which
      Codex cannot perform): with the bridge parity-live and SoundSwitch closed, confirm on real lasers
      that (a) each proven scripted track and autoloop matches the prior SoundSwitch look, (b)
      held static looks reach the rig after the C5 fix, (c) blackout/emergency kills output, (d) no
      `unverified_parity` document drives trusted output. Fallback at any failure: reopen SoundSwitch.

## When you finish (report back)
- Files changed; oracle per-surface totals (before/after) incl. the DD42028C old-resolver
  negative-control result; which scripted layouts are `oracle_proven` vs `algorithm_generalized`,
  plus an explicit list of any document still `unverified_parity` **with its defect reason** (a
  normal supported document in that state = not done, §0.1); the dropped-cue vs missing-hold
  classification per captured SSID with the fix evidence; the C4 step-1 decoder finding (did the
  old code parse serialized keys or reconstruct them?); the C6 assertion outcome per slot; the C5
  port-gone root cause; the note-96 resolver change; the C7 anchor proof (beatgrid-tiled phase vs
  U0); software-gate output; and the exact operator hardware/kill-path procedure that remains.
  State plainly what is byte-exact-proven vs blocked — no "done" without the oracle evidence.
