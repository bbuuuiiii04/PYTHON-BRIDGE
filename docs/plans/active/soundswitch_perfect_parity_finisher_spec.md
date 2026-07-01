---
doc_status: active-spec
truth_level: capture-grounded (parity_20260701T185231Z) + current-code-verified + prior-session-ghidra-corroborated
last_verified_commit: 0a86521
last_verified_date: 2026-07-01
validation_scope: Fable 5 finisher spec for SoundSwitch exporter + bridge DMX runtime parity. Adversarial audit of the "parity is runtime, not exporter" reframe using the existing parity capture + current code + prior-session arm64 Ghidra decompiles (live GhidraMCP NOT connected this session). Bounded to SoundSwitch 2.10.3 / canonical project {3CCBCD6F-7C1B-44D8-882C-A52A74CC1827} / RAVE b8ad2201... / 2 mirrored lasers / Universe 0 / CH1-19. Spec only; no production code written; no captures taken.
supersedes_conclusions_of: docs/prompts/active/soundswitch_perfect_parity_fable5_prompt.md §2 reframe (bounded/refuted per surface below); builds on docs/plans/active/soundswitch_pack_parity_root_cause_spec.md (baseline, vindicated)
---

# Codex Implementation Spec — SoundSwitch Perfect-Parity Finisher

**One-line:** The scripted "17% mismatch" is **not** a runtime flicker — it is the
**exporter/pack content** being dark or wrong where SoundSwitch is lit, which the runtime
renders faithfully. This spec builds an **externally-grounded offline oracle** (U0 from the
existing capture, not a self re-render), fixes the exporter cue-resolution + first-event/gap
model, fixes static trigger authority and autoloop selection, sweeps the DMX runtime for every
other divergence, and **fails closed** on anything not proven — with an explicit ship gate that
needs **no new capture**.

> **Roles:** Claude authored this spec; **Codex implements.** Work on `main`, commit after each
> task. No new branches. No secrets/live-config/canonical-pack contents committed. No hardware,
> no bridge restart, no SoundSwitch export click.

---

## Part A — Audit result & root cause (read-only; do not implement)

### A.0 Method & evidence provenance

- **Capture (primary evidence):** `tools/ssfmt/captures/parity/parity_20260701T185231Z/` —
  U0 (universe 0 = SoundSwitch) 152,613 pkts, U1 (universe 1 = bridge shadow render) 878,408 pkts,
  truth sidecar 426,750 frame rows. Analyzed offline (streaming) — no new capture taken. The
  all-zero 512-byte DMX frame hashes to `076a27c79e5ace2a3d47f9dd2e83e4ff6ea8872b3c2218f66c92b89b55f36560`
  [confirmed] — used to detect true full-frame zeros (the sidecar's `visible`/`active_dark` key on
  **CH1 only**, so they are *not* a full-zero signal).
- **Code:** verified against current HEAD `0a86521`. All file:line below re-read now.
- **Ghidra:** **live GhidraMCP was NOT connected in this session** (only Canva MCP present at audit
  time; the `ghidra` server the operator later configured is not visible to this running session and,
  per operator note, will appear next fresh session). Ghidra claims below are **prior-session arm64
  decompiles** recorded in `docs/plans/active/soundswitch_pack_parity_root_cause_spec.md:57-83` and
  `docs/research/soundswitch/soundswitch_ghidra_addendum.md` — labelled **[ghidra-prior]**, never
  presented as this-session truth, and cross-checked against the capture. Two residual items (A.3.d,
  A.4.c) would benefit from a fresh live decompile; they are **fail-closed** until then and are
  **never** gated on a new capture.

### A.1 Verdict summary (attacked the reframe; per surface)

| Surface | Reframe claim (§2) | **Audit verdict** | Basis |
| --- | --- | --- | --- |
| Static render | generic-only is correct; only trigger authority is broken | **CONFIRMED (bounded: colour map + RAVE profile)** | capture byte-match on 3 live looks + [ghidra-prior] no-intensity/strobe-0/no-pan-tilt |
| Static trigger | port drops; group-health fix insufficient | **CONFIRMED broken** | `static_held=0` all capture; `[SS-MIDI] input port gone` every ~5s; binding coverage gap |
| Scripted "17% = runtime zero-blip flicker" | cue values already correct; mismatch is a driver/render flicker | **BOUNDED → largely REFUTED** | deterministic-in-elapsed zeros; `transport='playing'`; exporter first-event gaps; **real-track cue-value divergence** |
| Scripted cue values correct on real tracks | true for all real tracks; DD42028C is an excluded orphan | **REFUTED for 2 of 4 captured tracks** | AE9E3C61 wrong strobe cue; FC10FC02 near-total divergence |
| Autoloop phase | phase-zero fixed; model correct | **CONFIRMED fixed** in this capture | phase_tick spans full [0,~19198] on all 18 targets |
| Autoloop selection/anchor | note 96 never selected; anchor must be derived | **CONFIRMED gap (selection) + BOUNDED (anchor)** | binding exists; resolver never emits policy-note 96; anchor re-set per phrase, origin unproven vs SS |
| Frame integrity / mirror / >CH19 | (sweep) | **CONFIRMED clean** | no channel >19 ever nonzero across all U0+U1 scripted packets |

**Bottom line that changes the plan:** the reframe's *mechanism* for scripted is wrong. The mismatch
is **exporter/pack-content**, deterministic, and the runtime faithfully renders it. This **vindicates
the baseline root-cause spec** (`soundswitch_pack_parity_root_cause_spec.md`) and means the priority
fix is exporter cue/first-event fidelity + an external oracle, **not** a driver debounce. The
DD42028C-class defect is **not** confined to the excluded orphan — it recurs in real show tracks.

### A.2 Static — CONFIRMED correct, bounded (do not add map compositing)

- [confirmed] Runtime `apply_layers` applies **only** `look.generic_attributes` for
  `fixture_group == PRIMARY_FIXTURE_GROUP (0x493)` (`soundswitch_laser_player.py:207,84-89`), skipping
  looks with `profile_has_intensity_channel` (`:201`). Exporter `render_static_look_frame` is likewise
  generic-only (`soundswitch_pack.py:81-86`).
- [ghidra-prior] For the RAVE 19-ch profile the four non-generic maps do **not** reach CH1-19:
  no intensity-flag channel exists, strobe fractions are 0.0, stored position GUIDs have no pan/tilt
  target ⇒ "their generic map therefore contains the exact active CH1-CH19 output"
  (`soundswitch_ghidra_addendum.md:104-105,176-178`; `RebuildStaticLookCache 0x100335230`,
  `SetChannelAttributes 0x10033710c`). Colour is the **only** residual map.
- [confirmed] `local/soundswitch/rbss_canonical_pack/static_looks.json`: 8 authored looks carry
  CH1-19 output via generic (slots 0,1,2,8,17,24,25,26); slots 16 "OFF" and 31 "BLACK OUT" have
  generic that renders all-zero (intended dark); **21 slots (3–7,10–15,18–23,27–30) have empty
  generic, empty names, default 5-entry maps, and a zero pre-rendered frame** — unauthored default
  slots, exactly the reframe's flagged set. Their generic-only render (zero) is correct *iff* colour
  contributes nothing (the [ghidra-prior] result), which is the one unproven point.
- **Verdict: CONFIRMED, bounded to (a) the colour-map assumption and (b) the RAVE profile.** No
  runtime map-compositing is needed or wanted. The residual is closed by an **export-time assertion**
  (Task C6), not by adding runtime map math.

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
- **[assumed→prove-in-oracle] Gap-fill hypothesis.** Rihanna's intro is *mostly* dark in **both** U0
  and U1 (both-zero 21,184), so SoundSwitch is not blanket-filling gaps with autoloop there; but
  FC10FC02's U0 is lit throughout its pre-first-event window. Two candidate causes for "U0 lit where
  the pack is dark": (i) SoundSwitch composites an **autoloop under scripted gaps** that the bridge
  suppresses (`native_autoloop_resolver.py:164-173` returns `software_zero_frame` when
  `scripted_active`), or (ii) the exporter **dropped/mis-timed** early cues. The oracle (Task C1) must
  disambiguate empirically from the existing capture (does U0's gap frame match a known autoloop phase
  of an active loop, or a shifted scripted cue?). **[unknown][ghidra-prior residual A.3.d]**: whether
  `SSPlaybacks::RefreshCache/SetChannelAttributes` composites autoloop beneath a scripted track is not
  decompiled this session — fail-closed until the oracle or a fresh Ghidra pass answers it.
- **Verdict: BOUNDED → largely REFUTED.** Root cause is the **exporter cue-resolution + first-event/gap
  model**, not runtime. Two of four real tracks show value divergence. This is exactly the baseline
  spec's warning (`soundswitch_pack_parity_root_cause_spec.md:117-282`). The runtime is exonerated for
  scripted (the single `transport=""` frame/track is negligible).

### A.4 Autoloop — phase fixed; selection + anchor-origin + near-empty content open

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
  SS-groove mappings ([[project_autoloop_intelligence]]). Not a render bug.
- **[bounded] Anchor origin unproven.** `resolve()` sets `anchor_beat = float(abs_beat_pos)` at the
  first observed scene edge (`native_autoloop_resolver.py:191-199`); 3–10 distinct anchors per loop in
  the capture (re-anchor per phrase edge). Whether that origin matches SoundSwitch's phrase-anchored
  start beat ([ghidra-prior] `AutoLoopLayout::GetStateForTime 0x10025f000` at 600 ticks/beat;
  `buildAutoLoopForStartingBeat` selects a start beat) is **not proven** — the edge-observation beat
  may carry a latency offset vs SS's phrase-aligned start beat. **[unknown][ghidra-prior residual
  A.4.c]**.
- **[bounded] Some loops export near-empty.** `SSAutoLoop5` (note 32, groove), `SSAutoLoop18`
  (note 64, buildup), `SSAutoLoop3` have **1–2 events and zero nonzero boundaries** → render
  `empty_dark_look` (dark). Faithful to pack content, but whether the pack content is *correct* vs U0
  (exporter under-render of those loop documents) is **unproven** — same exporter-fidelity question as
  scripted.
- **Verdict: BOUNDED.** Phase CONFIRMED fixed; selection (note 96), anchor origin, and near-empty-loop
  content are open and must be oracle-proven or fail-closed.

### A.5 §6.2 edge-case sweep — findings & proof status

| # | Case | Finding | Proof status |
| --- | --- | --- | --- |
| 1 | Beyond-CH19 / mirror leakage | No channel >19 ever nonzero (U0+U1). Single mirrored 19-ch output. | **proven clean** (capture) |
| 2 | Zero-blip = runtime jitter | Refuted; deterministic in elapsed, `transport='playing'`. | **proven** (capture+code) |
| 3 | First-event/intro gap | Pack dark until first timeline event; SS lit earlier/through gaps. | **proven present** (capture+pack) |
| 4 | Scripted-gap autoloop-fill precedence | SS may composite autoloop under scripted gaps; bridge suppresses. | **needs oracle** (A.3.d) — fail-closed |
| 5 | Cue-resolution value divergence | AE9E3C61 wrong strobe cue; FC10FC02 near-total. DD42028C-class in real tracks. | **proven present** (capture) |
| 6 | Autoloop selection (note 96) | Binding exists; resolver never emits policy-note. | **proven** (pack+capture) |
| 7 | Autoloop anchor origin | Edge-anchored; vs SS phrase-anchor unproven. | **needs oracle/ghidra** — fail-closed |
| 8 | Static trigger authority | Port drops every ~5s; binding covers only DDJ StaticOverride16. | **proven broken** (log+pack) |
| 9 | Static colour-map residual | 21 empty-generic default slots render zero; colour unproven inert. | **needs export assertion** — fail-closed |
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
- **Ground truth = U0 packets** from `parity_20260701T185231Z`. Never the pack, never U1-as-truth.
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
- **Autoloop assertion:** for each covered target, map U0 frames to `phase_tick` via the sidecar
  `native_autoloop.{target_identity,anchor_beat,phase_tick}` and compare
  `render_autoloop_frame(document, phase_tick)` to nearest U0. Report per-phase match + whether U0's
  gap frames match an autoloop phase (feeds A.3.d gap-fill disambiguation).
- **Static assertion:** for the 3 live-mapped looks (0,24,16), assert the pack's
  `pre_rendered_frame_ch1_ch19` equals the U0 held frame during that look's `actions.jsonl`
  `static_slot_*` window (recover windows from actions, not alignment — the static detector never
  fired). No U1 static side exists in this capture (trigger bug) — the static oracle checks pack-render
  == U0, which is capture-provable **today** for the 3 attempted looks.
- **Negative control:** the oracle MUST classify **DD42028C** as non-matching (it is the known-divergent
  witness; use its prior evidence in `soundswitch_pack_parity_root_cause_spec.md:177-217`). An oracle
  that "passes" DD42028C is broken.
- **Generalization (no new capture):** for the 28 scripted / 1 autoloop targets **not** in the capture,
  the oracle cannot compare to U0. Parity for them is claimed **only** by *algorithm generalization*:
  (a) the render functions are proven **content-independent** for a layout (same
  `raw_reference-1 → stored_key` resolution `soundswitch_project_decoder.py:538-544`, same boundary
  step-function `soundswitch_laser_player.py:122-128`, same cue-attribute application), **and** (b) the
  captured witnesses of that layout pass the U0 oracle. If (a)+(b) hold, any content of that layout
  renders identically **by construction**. **Today (a)+(b) FAIL for `shared_441_dictionary_timeline`**
  because AE9E3C61 (same layout) diverges — so *all* unproven tracks of that layout stay fail-closed
  until the resolver is fixed and the captured witnesses pass.

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
- **Live fail-closed gate (Task C8):** when the pack runtime is in a *parity-live* mode (bridge
  replacing SoundSwitch, i.e. `soundswitch_connected == False` and pack output enabled), a document
  whose lane is `unverified_parity` must **not** be rendered as trusted output. It renders only under an
  explicit operator-acknowledged "unverified" state (a status flag + a distinct operational_state), and
  otherwise emits the documented safe base (ZERO for scripted/autoloop; held manual static still
  allowed). This never changes the SS-present shadow path (which already submits ZERO to the backend,
  `state_manager.py:4116`). Export/visibility is unchanged.

### B.3 Fix design per lane

- **Scripted first-event/gap (Task C3):** first resolve *which* cause via the oracle (A.3.d). If SS
  composites autoloop under scripted gaps, add **scripted-gap autoloop composition** matching SS's
  precedence (do **not** invent a new precedence — mirror SS). If instead the exporter dropped/mis-timed
  early cues, fix the exporter timeline extraction. Keep snap-and-hold; add **no** interpolation/time-
  varying output. Any track not oracle-provable → `unverified_parity`.
- **Scripted cue-resolution (Task C4):** the AE9E3C61 wrong-strobe divergence is the DD42028C-class
  defect. Do **not** apply a global raw-reference offset (rejected: `soundswitch_pack_parity_root_cause_spec.md:214-217`).
  Resolve cue identity deterministically from saved bytes per layout, proven per-boundary against U0; if
  a layout/document cannot be proven from bytes, mark `unverified_parity` (offline oracle-canonicalization
  is the operator-gated escape hatch, baseline Task 4). FC10FC02 and AE9E3C61 must pass the oracle or
  fail closed.
- **Static trigger authority (Task C5):** two root causes, both fixed: (i) the input port dropping
  (`[SS-MIDI] input port gone`, `soundswitch_midi_input.py:454-484`) — root-cause the exact-port
  matcher/retry so the operator's static-controller port stays open; (ii) binding coverage — the pack's
  learned static control is only `DDJ-800 StaticOverride16`, but the operator holds via Stream Deck;
  make the observed-vs-authored gap explicit and fail-closed (status shows "static trigger unobserved")
  rather than silently claiming static parity. Preserve the RW-4 group-health overlay-trust behavior
  (`state_manager.py:3896-3921`). Keep render generic-only.
- **Static colour assertion (Task C6):** export-time, assert for every static slot that the four
  non-generic maps contribute nothing to CH1-19 for the RAVE profile ([ghidra-prior]: no intensity ch,
  strobe 0.0, no pan/tilt target, colour resolves to generic). If any slot violates the assertion (a
  colour/other map that *would* drive CH1-19 with empty generic), flag that slot `unverified_parity` —
  do not silently export a zero frame for it.
- **Autoloop selection + anchor (Task C7-autoloop):** (i) make SSAutoLoop4 reachable — either map the
  drop-policy condition to note 96 in the scene resolver, or, if note 96 is only reachable via an
  operator "BY GENRE" mapping that is genuinely absent, mark SSAutoLoop4 `unverified_parity` and surface
  it (do not claim autoloop parity-complete while a mapped loop is unreachable). (ii) Lock the
  phrase-anchor contract as **derived**: anchor to the phrase-aligned start beat, not the raw edge-
  observation beat; prove the phase reproduces U0 on the captured loops via the oracle. Do not regress
  the landed phase-zero guard.

---

## Part C — Tasks for Codex (ordered; commit after each; pure-function seam + must-fail-then-pass each)

### Absolute rules
- **Do not** write production code that opens hardware, changes backend, enables output, restarts the
  bridge, or clicks Export. **Do not** add blocking/socket/MIDI/serial/filesystem/subprocess work to the
  200 Hz push loop (`state_manager._push_tick`/`_drive_pack_output`).
- **Do not** apply a global raw-reference offset. **Do not** add time-varying/interpolated rendering.
- **Do not** treat the existing verifier's internal re-render as parity proof.
- **Do not** require any new capture anywhere. Unprovable ⇒ `unverified_parity`, never "capture later".
- **Out of scope (fail closed):** any project but the pinned UUID; any venue/profile/universe/fixture
  but RAVE/CH1-19; SoundSwitch ≠ 2.10.3; multi-deck/crossfade; `.ssproj` internals; hardware.

### Task C1 — Offline parity oracle (pure core + CLI). *Foundation.*
Files: `soundswitch_parity_oracle.py` (pure), `tools/ssfmt/parity_oracle.py` (CLI/IO),
`tests/test_soundswitch_parity_oracle.py`, `tests/fixtures/soundswitch/parity_oracle/…` (small
committed reduced fixtures derived from the existing capture: for each captured SSID, a table of
`(elapsed_ms, U0_frame)` samples at cue boundaries + neighbors; the 3 static look U0 held frames; a
handful of autoloop `(phase_tick, U0_frame)` per covered target; the DD42028C negative-control table).
- Pure core API: `classify_scripted(document, samples) -> OracleReport`,
  `classify_autoloop(document, phase_samples) -> OracleReport`,
  `classify_static(pre_rendered_frame, u0_held) -> OracleReport`. No file/socket access in the core.
- CLI reads the capture, builds the elapsed→U0 mapping (B.1), and runs the core.
- **Must-fail-then-pass:** against **today's** pack, the oracle MUST report FAIL for AE9E3C61,
  FC10FC02, and DD42028C, and the scripted first-event BLIP for Rihanna/9947C65E; and PASS for the
  Rihanna/9947C65E lit-region value match. A test asserts these exact starting verdicts (so a future
  regression that "passes everything" is caught).
- Acceptance: `python3 -m unittest tests.test_soundswitch_parity_oracle` green; oracle reproduces the
  Part A per-track numbers within tolerance from the committed fixtures (no live capture needed).

### Task C2 — Parity registry + fail-closed publication (extends baseline Tasks 1–2).
Files: `tests/fixtures/soundswitch/scripted_parity_registry.json` (+ autoloop/static registries),
`soundswitch_pack_models.py`, `soundswitch_pack.py`, `soundswitch_pack_verifier.py`,
`soundswitch_pack_loader.py`, `tools/export_soundswitch_pack.py`,
`tests/test_soundswitch_scripted_parity.py`.
- Add the 3-state lane (B.2) to each scripted/autoloop/static document's provenance. Seed:
  AE9E3C61, FC10FC02, DD42028C, and every uncaptured `shared_441_dictionary_timeline` doc =
  `unverified_parity`; Rihanna/9947C65E lit-region = `oracle_proven` only after Task C3/C4 make the
  oracle pass; static looks 0/24/16 = `oracle_proven` (already byte-match), the 21 empty-default slots =
  `oracle_proven` (zero) once Task C6's colour assertion holds, else `unverified_parity`.
- Verifier: `oracle_proven` requires committed U0-oracle evidence (source hash + capture id + per-
  boundary totals); export **fails closed** (raises) on an active document that is `unverified_parity`
  *and* the operator has not chosen the explicit unverified-publish path.
- **Must-fail-then-pass:** a test asserts that exporting today's pack marks AE9E3C61/FC10FC02/DD42028C
  `unverified_parity` and that publication of them fails closed; after Task C3/C4 fixes, they flip to
  `oracle_proven` (or stay fail-closed with a recorded reason). Pure-function seam: registry
  classification is a pure function of `(document, oracle_report)`.

### Task C3 — Scripted first-event / gap fidelity.
Files: `soundswitch_parity_oracle.py` (gap-fill disambiguation), `native_autoloop_resolver.py` /
`state_manager.py` *only if* SS composites autoloop under scripted gaps, `soundswitch_project_decoder.py`
/ `soundswitch_pack.py` *if* the exporter mis-times early cues,
`tests/test_soundswitch_scripted_first_event.py`.
- Use the oracle to decide A.3.d from the existing capture: for each SSID's pre-first-event / mid-gap
  region where U0 is lit, does U0's frame equal (i) an active autoloop's `render_autoloop_frame(phase)`
  ⇒ **gap-fill**, or (ii) a shifted/earlier scripted cue ⇒ **exporter cue-timing**?
- Implement the branch the evidence supports; mirror SS precedence exactly; keep snap-and-hold. Any SSID
  not resolvable ⇒ `unverified_parity`.
- **Must-fail-then-pass:** oracle reports Rihanna BLIP=2,822 today; after the fix the pre-60065ms region
  matches U0 (BLIP→0 within tolerance) OR the track is fail-closed with a recorded reason. Pure seam:
  the gap-fill classifier is a pure function.

### Task C4 — Scripted cue-resolution fidelity (DD42028C-class in real tracks).
Files: `soundswitch_project_decoder.py`, new pure `soundswitch_scripted_resolution.py`,
`tests/test_soundswitch_scripted_resolution.py` (+ reuse baseline Task 3/4 oracle-canonicalization CLI).
- Resolve cue identity deterministically from saved bytes per layout; prove per-boundary against U0 via
  the oracle. AE9E3C61's CH10/CH11 (255,255)-vs-(110,0) and FC10FC02 must resolve to U0 or fail closed.
  No global offset; no cue-name/nearest-key guessing (`soundswitch_pack_parity_root_cause_spec.md:499-501`).
- **Must-fail-then-pass:** the pure resolver test fails on today's model for AE9E3C61's divergent
  boundaries and passes after the fix (or the doc is `unverified_parity`). Global-offset rejection test
  retained (`raw-1`, direct, `raw±2/3` cannot satisfy all rows).

### Task C5 — Static MIDI trigger authority.
Files: `soundswitch_midi_input.py`, `tests/test_soundswitch_midi_input.py`, `runtime_status.py` (status
surface only).
- Root-cause `[SS-MIDI] input port gone` (`:454-484`): fix the exact-port matcher/retry so a present
  static-controller port is not spuriously declared gone (verify `_port_present` name-matching against
  the real enumerated port names; ensure the never-seen fast-retry churn does not corrupt a live port's
  enumeration per the `:474-481` comment). Preserve RW-4 overlay-trust (`state_manager.py:3896-3921`).
- Make the observed-vs-authored binding gap explicit: if the operator's held-static device/notes are not
  in the pack's learned controls (today: only `DDJ-800 StaticOverride16`), status reports "static
  trigger unobserved / binding gap" and static parity is **not** claimed (fail-closed), rather than
  silently rendering base.
- **Must-fail-then-pass:** a unit test injecting a present-then-flapping port asserts the port is NOT
  declared gone while present; a test asserts an unbound held-static attempt surfaces the gap flag.
  Pure seam: `_port_present(port_list, name)` tested directly.

### Task C6 — Static colour-map export assertion (close the bounded residual).
Files: `soundswitch_pack.py`, `soundswitch_project_decoder.py`, `tests/test_static_looks.py`.
- At export, for every static slot assert the four non-generic maps contribute **nothing** to CH1-19 for
  the RAVE profile: intensity has no channel, strobe fraction 0.0, position has no pan/tilt target,
  colour resolves to generic-equivalent (the [ghidra-prior] result). If a slot violates it, flag that
  slot `unverified_parity` (do not export a silent zero as if proven).
- **Must-fail-then-pass:** a synthetic look with empty generic + a colour value that *would* map to
  CH1-19 must be flagged `unverified_parity`; the 8 authored + 21 empty-default real slots pass. Pure
  seam: the assertion is a pure function of the look record + profile.

### Task C7 — Autoloop selection + anchor + edge-case unit sweep.
Files: `native_autoloop_resolver.py`, the scene-selection source that maps musical context→note (the
laser/autoloop resolver that produces `LaserResolvedScene`), `soundswitch_laser_player.py` (autoloop
render only if a defect is proven), `tests/test_native_autoloop_resolver.py`,
`tests/test_state_manager_pack_driver.py`.
- Selection: make SSAutoLoop4 reachable (map drop-policy → note 96) OR mark it `unverified_parity` and
  surface it if note 96 requires an absent operator mapping. Do not regress the phase-zero guard.
- Anchor: lock the phrase-anchored contract as derived (anchor to the phrase-aligned start beat, not the
  raw edge beat); prove via the oracle that the phase reproduces U0 on captured loops. Near-empty loops
  (5/18/3) must be oracle-checked vs U0 (correct-dark) or `unverified_parity`.
- Edge-case sweep unit tests (§6.2 items 10–13): precedence combinations
  (blackout > emergency > static-override > scripted/autoloop base; SS-present suppression; reload-wait
  latch) each asserted; a mid-playback `set_pack_runtime` swap asserted not to emit a stale nonzero
  frame; a BPM 160→155 change asserted not to perturb scripted (elapsed-keyed) output and to keep
  autoloop phase continuous.
- **Must-fail-then-pass:** a test proving SSAutoLoop4 is unreachable today (resolver never emits note 96)
  and reachable/flagged after the fix; anchor test proving phrase-aligned phase matches the captured
  loop's U0 phase.

### Task C8 — Live fail-closed parity gate (wire the flag model into the driver, read-only).
Files: `state_manager.py` (`_drive_pack_output` selection only), `runtime_status.py`,
`tests/test_state_manager_pack_driver.py`.
- When parity-live (pack enabled AND `soundswitch_connected == False`), a document whose lane is
  `unverified_parity` must not render as trusted output: emit the safe base (ZERO scripted/autoloop;
  held manual static still honored) and publish an explicit `operational_state = "unverified_parity"`
  unless the operator has acknowledged it. No change to the SS-present shadow path (already ZERO to
  backend, `:4116`). No blocking work added to the tick.
- **Must-fail-then-pass:** a driver test with an `unverified_parity` scripted doc asserts safe-base +
  the status flag when parity-live, and unchanged behavior when SS-present. Pure seam: the lane→action
  decision is a pure helper.

---

## Part D — Verification (NO new capture is a ship gate)

- **Ship proof = the offline oracle (Task C1) replaying the EXISTING capture**, per surface:
  - It **fails** against today's renderer/exporter (AE9E3C61, FC10FC02, DD42028C, scripted first-event
    BLIP) and **passes** after the fixes — or the unprovable documents are recorded `unverified_parity`
    with a reason. DD42028C stays correctly flagged (negative control).
  - Content not in the capture is covered by **algorithm generalization** (B.1): a layout is claimed
    parity-safe only when it is content-independent **and** has ≥1 `oracle_proven` witness. No per-item
    capture, ever.
- **Software gates (must be green)** — from `soundswitch_exporter_remaining_work.md:252-269`:
  ```bash
  python3 -m unittest \
    tests.test_state_manager_pack_driver tests.test_soundswitch_pack_commands \
    tests.test_runtime_status tests.test_bridge_menubar tests.test_soundswitch_frame_sender \
    tests.test_enttec_dmx_pro tests.test_soundswitch_pack_startup \
    tests.test_soundswitch_parity_oracle tests.test_soundswitch_scripted_parity \
    tests.test_soundswitch_scripted_resolution tests.test_soundswitch_scripted_first_event \
    tests.test_static_looks tests.test_soundswitch_midi_input tests.test_native_autoloop_resolver
  python3 -m unittest discover tests
  python3 tools/check_docs_metadata.py && python3 tools/check_agent_contracts.py && python3 tools/check_docs_drift.py
  python3 tools/check_docs_staleness.py --report
  git diff --check
  ```
- **Optional, non-blocking (post-ship):** a fresh live re-capture, and a fresh live GhidraMCP decompile
  of `SSPlaybacks::RefreshCache/SetChannelAttributes` (A.3.d gap-fill) and `AutoLoopLayout::GetStateForTime`
  (A.4.c anchor origin) once the `ghidra` server is visible — confidence checks only, never ship gates.

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
1. **Every claim labeled** confirmed/assumed/unknown — done in Part A; unknowns (A.3.d gap-fill, A.4.c
   anchor origin) surfaced and fail-closed, not buried.
2. **Verified against CURRENT code** (HEAD `0a86521`) — every file:line re-read this session; the
   phase-zero guard, driver gates, generic-only render, and constants confirmed present.
3. **Pending-state guard** — Task C7/C8 assert precedence across *all* active pending states
   (blackout/emergency/static-override/reload-wait/SS-present), not only the new lane vs one other.
4. **Mode-transition cleanup** — the new `unverified_parity` lane is read-only in the driver (no new
   mutable tick state); Task C7 asserts reload-swap and BPM-change transitions don't leak stale frames.
5. **Third-party API completeness** — the SoundSwitch cue/static/autoloop composition is grounded in the
   [ghidra-prior] symbol map (exact addresses in Part A); the oracle's elapsed→U0 join uses the exact
   `(sequence, dmx_sha256)`→`mono_ns` chain, not a hand-waved "match".
6. **Cross-checked against existing code** — resolution uses the canonical `raw_reference-1 → stored_key`
   path (`soundswitch_project_decoder.py:538-544`) and the canonical `autoloop_bindings` from
   `iac_selections`; no local re-derivation.
7. **Pure-function seams** — every task names a pure core (oracle classifiers, registry classifier,
   resolver, `_port_present`, colour assertion, lane→action) testable without files/subprocess.
8. **Live safety explicit** — E.2; snap-forward-only, never clobber live output, fail-closed to ZERO.
9. **Adversarial self-review** — I attacked the reframe and **partially refuted it** (scripted mechanism
   and "values correct" claims) with capture evidence; forced the specific failure (AE9E3C61 wrong strobe
   cue; FC10FC02 0.6% match; deterministic-in-elapsed zeros). The one way this spec could still be wrong:
   if the scripted "U0 lit where pack dark" is SS gap-filling with autoloop (A.3.d) rather than a bad
   export — which is why Task C3 makes the oracle disambiguate *before* choosing the fix, and fails
   closed if it can't.

### E.4 SHIP GATE (the checklist that means "done")
- [ ] Offline oracle (C1) committed; **fails** on today's pack for AE9E3C61/FC10FC02/DD42028C + scripted
      first-event BLIP; **passes** (or records `unverified_parity` + reason) after C3/C4.
- [ ] Every active scripted/autoloop/static document is `oracle_proven`, `algorithm_generalized`, or
      `unverified_parity` — none silently `rendered` (C2). Export fails closed on unproven active docs.
- [ ] `shared_441_dictionary_timeline` is `algorithm_generalized` **only** after its captured witnesses
      pass the U0 oracle (i.e. AE9E3C61 resolved), else its uncaptured tracks stay `unverified_parity`.
- [ ] Static: 3 live looks `oracle_proven`; colour assertion (C6) holds for all 32 slots or flags the
      violators; trigger-authority port fix (C5) landed with the observed-vs-authored gap surfaced.
- [ ] Autoloop: phase-zero guard intact; SSAutoLoop4/note-96 reachable or flagged; phrase-anchor contract
      derived + oracle-proven on captured loops; near-empty loops oracle-checked or flagged.
- [ ] §6.2 sweep: items 1–3,5,6,8 proven; 4,7,9 resolved-or-flagged; 10–14 unit-swept (C7).
- [ ] Live fail-closed parity gate (C8) wired; SS-present shadow path unchanged; no tick-loop regressions.
- [ ] All software gates green (Part D); `soundswitch_exporter_remaining_work.md:274-291` completion
      boxes updated (offline oracle box checkable; independent-review + operator-hardware boxes remain).
- [ ] **Only remaining external gate = the operator's physical hardware/optical/kill-path run** (which
      Codex cannot perform): with the bridge parity-live and SoundSwitch closed, confirm on real lasers
      that (a) each `oracle_proven` scripted track and autoloop matches the prior SoundSwitch look, (b)
      held static looks reach the rig after the C5 fix, (c) blackout/emergency kills output, (d) no
      `unverified_parity` document drives trusted output. Fallback at any failure: reopen SoundSwitch.

## When you finish (report back)
- Files changed; oracle per-surface totals (before/after) incl. the DD42028C negative control result;
  which scripted layouts are `oracle_proven` vs `algorithm_generalized` vs `unverified_parity`; the
  A.3.d gap-fill resolution (autoloop-fill vs exporter-timing) with its evidence; the C5 port-gone root
  cause; the note-96 resolution; software-gate output; and the exact operator hardware/kill-path
  procedure that remains. State plainly what is proven vs fail-closed-flagged — no "done" without the
  oracle evidence.
