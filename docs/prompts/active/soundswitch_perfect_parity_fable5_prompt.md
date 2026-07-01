---
doc_status: active-prompt
truth_level: synthesized-from-code-tests-research-and-live-pack
last_verified_commit: 3131aa7
last_verified_date: 2026-07-01
validation_scope: Fable 5 authoring prompt — produce a Codex-executable SoundSwitch perfect-parity spec; bounded to SoundSwitch 2.10.3 canonical project / RAVE profile / 2 mirrored DMX lasers / Universe 0 / CH1-CH19
---

# Fable 5 Prompt — Author the SoundSwitch ↔ Bridge-Pack Perfect-Parity Spec

## 0. Your mission and the one-shot rule

You are **Fable 5**, acting as the planner/auditor. Produce **ONE complete, self-contained, Codex-executable implementation spec** that makes the bridge's exported SoundSwitch lighting pack reproduce SoundSwitch's own DMX output **exactly** — perfect parity — for **autoloops, scripted tracks, and static looks**, on the bounded setup in §1.

Hard rules for this engagement:

- **You get exactly one prompt. There is no follow-up round with you.** Your spec must be complete enough that Codex can execute it to completion with no further planning from you, and complete enough that the operator + the requesting agent (Claude) can run the verification captures against it. **Never defer a decision to a "future spec."** If a design choice is required, make it, justify it from evidence, and encode it.
- **You author a spec. You do NOT write production code and you do NOT run captures.** Codex implements. The operator + Claude run the captures. Your spec defines *what to build* and *the exact capture/verification protocol they will run*.
- **Use Ghidra + GhidraMCP (authorized in §7).** The whole point is to read SoundSwitch's **actual rendering algorithm** from the binary and reproduce it, rather than guess from captures. The operator will have the SoundSwitch project open for you.
- **Code wins over docs.** Every file:line reference below was verified at HEAD `3131aa7` but re-verify against current code; if a doc and code disagree, trust code and say so.

Deliverable format is specified in §9. Read §1–§8 first; do not start writing the spec until you have.

---

## 1. Product purpose and locked scope

**Purpose.** SoundSwitch is the operator's **authoring tool**. A read-only exporter compiles the saved SoundSwitch project — autoloops, scripted tracks, attribute cues, static looks, catalogs, TrackMap, learned MIDI — into an immutable "bridge pack." At playback the bridge renders that pack to DMX (CH1–CH19) so **SoundSwitch is not needed at runtime**. The end goal: the bridge's DMX output (call it **U1**) equals SoundSwitch's own DMX output (**U0**) exactly, so the bridge can replace SoundSwitch for live playback. The operator authors in SoundSwitch, clicks "Export from SoundSwitch," and anything they created renders identically — **with no per-look capture**.

**Locked scope (operator-confirmed — do not widen).**
- SoundSwitch **2.10.3**, container v3.
- The **default/canonical project only**, pinned UUID `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}` (the exporter must keep rejecting any other UUID even on the same RAVE venue).
- **RAVE** venue/fixture profile, GUID `b8ad2201b9e4c94696c898a7e8f6a5a9`.
- **2 DMX lasers**, **Universe 0**, **CH1–CH19**, 19-channel no-separate-intensity profile.
- No generalization to other projects, venues, profiles, fixtures, universes, or SoundSwitch versions. Those remain fail-closed.

---

## 2. Operator-locked intents — do NOT re-litigate these

The operator answered these directly. They are settled inputs, not open questions:

1. **The two lasers are ALWAYS identical/mirrored.** Both lasers show the same look on the same CH1–19. Therefore rendering a single 19-channel output is correct, and multi-fixture-group compositing is **not** required. **BUT:** your spec must (a) confirm this mirror invariant from SoundSwitch's rendering via Ghidra + one capture, and (b) have the exporter/verifier **assert** it — if the second fixture group ever produces CH1–19 values that differ from the primary group, flag it (best-effort, per intent #4). Do not silently assume; prove-then-assert.
2. **Snap-and-hold — no time-varying output.** Every change is instant; nothing fades, ramps, sweeps, or flashes as an interpolated stream between cue placements. **This means the existing static per-boundary / per-phase step-function model is architecturally correct.** Do NOT make the renderer time-aware and do NOT add interpolation. The work is **composition fidelity** (right static CH1–19 values at each boundary/phase), not a new engine. Still: confirm time-invariance via Ghidra/capture (strobe/colour appear to be static channel values the fixture self-animates — verify SoundSwitch does not emit a per-tick DMX stream for them).
3. **Occasional whole-show captures are acceptable as the parity proof**, run by the operator + Claude (never per-look, never by you). Your spec defines the capture protocol and the offline oracle that consumes it.
4. **Best-effort export with an "unverified" flag** when a specific cue/look/loop cannot yet be *proven* to match SoundSwitch. Never block the operator's content. Each unproven item carries a machine- and operator-visible "unverified parity" flag; the flag set shrinks to empty as your mechanisms land. Perfect parity = the flag set is empty and the capture exam passes.

---

## 3. Definition of done (parity goal)

Perfect parity = for the locked setup, at every cue boundary / static-look trigger / autoloop phase the operator can author, the bridge's emitted CH1–19 frame is **byte-identical** to SoundSwitch's emitted CH1–19 frame, with correct timing, single active deck, no blend. Acceptance is proven by:
- an **offline oracle** per surface (recompute the bridge frame and compare to an operator-approved SoundSwitch U0 capture reduced to a committed fixture), which must **fail** against the current (wrong) renderer and **pass** against the corrected one; and
- a **live whole-show U0/U1 capture exam** (operator + Claude) with full coverage and zero unexplained mismatches.

---

## 4. Current state and verified parity gaps (the map)

The full compile→verify→render pipeline exists and is software-tested, but it is a **triple re-implementation** of SoundSwitch's rendering (exporter, verifier, and player all recompute the same way), so **the verifier cannot catch a shared misunderstanding**, and **parity has never actually been proven against real SoundSwitch DMX.** Verified gaps by surface (file:line at HEAD `3131aa7`; re-verify):

### 4.1 Scripted tracks
- Exporter compiles a **cumulative static step-function**: `render_document_boundaries` (`soundswitch_pack.py:89-123`) walks the timeline in **stored order** (no time sort), applies each resolved cue's attributes where `fixture_group == 0x493` only, last-write-wins, `clear_control` zeroes all but channels {8,9,11}. Player replays it (`soundswitch_laser_player.py:110-129`).
- Cue resolution is `raw_reference==0 → clear/control`, `raw>0 → stored_key = raw−1` then GUID lookup (`soundswitch_project_decoder.py:~529-548`). **Confirmed correct** (permutation lookup; wire-proven).
- **DEFECT (the core one):** this internally-consistent model can still be **wrong vs SoundSwitch U0.** Witness `DD42028C` (`.ssfile` SHA-256 `1ff7dd03…`, layout `dictionary_timeline_addressed_footer`, 91 timeline rows, 189 cue-dictionary rows): only **23 of 31** distinct looks reproduce; boundary match ~**69/91** (old) / ~**81/91** (a containment patch, still inexact). A second track `{528E8B22…}` (Rihanna) mismatches at **~17%**. **31 of 32 active scripted tracks are UNPROVEN.**
- **Root cause is UNKNOWN even after a prior GhidraMCP pass** — no addressed-footer / retained-prefix / shared-table remap and **no single global key offset** explains it (brute force vs nearest U0: raw−1=69/91 best, all others worse). The wrong rows require **mutually incompatible key deltas** (e.g. raw=3↔key1, raw=4↔key2, raw=186↔key187, raw=188↔key183, while raw=94↔key93 is already right). This is the hardest unknown; see §6.1.
- Boundary 10 (t=41202) is a **separate, fixable** carry-over regression: `TRAPDUB DROP 1` resolves correctly but a held-frame containment patch left the prior strobe's CH10/11 `(110,0)` instead of the cue's `(0,255)`.
- The verifier **recomputes boundaries with the same semantics** (`soundswitch_pack_verifier.py:281-366`) and has a dormant `oracle_rendered` escape hatch (`:302-355`) — it proves exporter↔verifier agreement, never agreement with SoundSwitch.

### 4.2 Autoloops
- `render_autoloop_frame` (`soundswitch_laser_player.py:132-154`) = a two-pass phase step-function over a **hardcoded 19,200-tick / 8-bar / 32-beat cycle** at **600 ticks/beat**, re-applying signed-negative pre-roll each cycle. Cycle length is injected by the loader (`soundswitch_pack_loader.py:26,534`), **not read from the artifact, never verified**.
- The **phase-zero runtime bug is already FIXED** at HEAD (Claude, this session): `state_manager.py:4013-4044` only bootstraps the executor's held scene when `self._native_autoloop.state is None`; hold ticks pass `scene=None` so `anchor_beat` holds and phase advances (`native_autoloop_resolver.py:142-210`). Do not re-solve this; do confirm it and build on it.
- **DEFECT:** the **phase contract itself is unproven** — SoundSwitch's phase origin, fixed render/transport latency, and anchor rule (first edge? selected-loop start beat? phrase/drop event? beatgrid phase?) are **unknown**; the existing offline oracle *grid-searches* them. Pre-fix captures showed ~**0.72–0.79** exact-match rates. A post-fix capture is an open gate.

### 4.3 Static looks
- **BIG confirmed gap:** `render_static_look_frame` (`soundswitch_pack.py:81-86`) and runtime `apply_layers` (`soundswitch_laser_player.py:179-214`, applies only `generic_attributes` at :207) render **ONLY `generic_attributes`** and **completely ignore `intensity_values`, `strobe_values`, `colour_values`, `position_values`.**
- Ground truth from the live pack: **all 32 static looks populate intensity/strobe/colour/position; only 11 of 32 have non-empty generic.** So the 21 looks with empty generic render **dark**, and even the 11 are missing their intensity/strobe/colour/position contribution. `position` = the lasers' pan/tilt (movement); `colour` = colour. The verifier recomputes from generic only (`soundswitch_pack_verifier.py:478-514`), so it cannot catch this.
- SoundSwitch's own composition of the five maps is in `RebuildStaticLookCache` (Ghidra `0x100335230`) → this is the most tractable, highest-value crack; see §6.2.
- Runtime trigger authority (the MIDI input path that tells the bridge a look is held) had a group-health poisoning bug; **already fixed** this session (`soundswitch_midi_input.py` snapshot split — overlay-trust vs raw health). Note it and build on it; static content parity is still unproven and needs a capture with non-zero `static_held` rows.

### 4.4 Cross-surface
- Only fixture group **`0x493`** is rendered; the pack also carries group **`0x496`** (your mirrored 2nd laser) with *more* attributes (3,680 vs 3,674) plus small groups `0x494`/`0x497`. Under intent #1 (mirrored) rendering one is correct **once proven+asserted**.
- `colour_values.raw_value` (raw bytes) and `position_values.position_guid` (a GUID) are stored as **opaque tokens, never decoded to DMX** — if a look's real output reaches CH1–19 through these, it is lost today. Ghidra must reveal how they map to channels.
- Exporter builds boundaries in **stored order**; the player sorts by `(time, source_order)`. These agree only if stored order == time order; the verifier does not check `time` monotonicity. Resolve this ordering ambiguity in the spec.

---

## 5. Authoritative sources to read (code wins over docs)

**Code (primary):** `soundswitch_pack.py` (exporter/compiler), `soundswitch_laser_player.py` (renderer), `soundswitch_pack_loader.py` (pack model), `soundswitch_pack_verifier.py` (verifier), `soundswitch_project_decoder.py` (`.ssfile`/`.ssproj` decode + raw−1 resolution), `soundswitch_pack_models.py` (source dataclasses), `native_autoloop_resolver.py` + `state_manager.py:_drive_pack_output` (~3780-4130) + `laser_executor.py:current_autoloop_scene` (runtime autoloop), `soundswitch_midi_input.py` (static trigger input). Tests under `tests/` mirror each.

**Docs (verify against code):**
- `docs/plans/active/soundswitch_exporter_remaining_work.md` — implementation-status authority + invariants.
- `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md` — original product/format contract (superseded for scripted exact-parity by the root-cause spec).
- `docs/plans/active/soundswitch_pack_parity_root_cause_spec.md` — the active parity investigation; contains the DD42028C evidence, the full GhidraMCP function map (its lines 59-83), the rejected hypotheses, and the oracle plans.
- `docs/research/soundswitch/soundswitch_ssfile_format.md`, `soundswitch_re_closure_report.md`, `soundswitch_ghidra_addendum.md`, `soundswitch_authoring_mutation_matrix.md` — format RE (knowns/unknowns) and the confirmed binary reader/writer symbol map.
- `docs/plans/active/soundswitch_autoloop_equivalence_oracle_spec.md` — the autoloop phase oracle design.
- Live pack (ground truth): `local/soundswitch/rbss_canonical_pack/` (fixture_profile, venue_cues, static_looks, autoloops/, scripted/, selection_map, track_map, manifest).
- Captures corpus: `tools/ssfmt/captures/all_surface/all_surface_20260701_024858/` (all-surface U0/U1), `tools/ssfmt/captures/t7d/` (autoloop scout oracle). `tools/artnet_compare.py` is the U0/U1 comparator; `tools/ssfmt/re/autoloop_oracle/` the phase oracle.

---

## 6. The unknowns you must resolve with Ghidra (do not guess)

For each, read SoundSwitch's actual algorithm from the binary, state it precisely, and encode the reproduction in the Codex spec. The confirmed binary reader/writer symbols and addresses are in `soundswitch_ghidra_addendum.md` and the parity root-cause spec (lines 59-83); start there, then decompile deeper along the **render/lookup** path (prior passes only nailed the **read/parse** path).

### 6.1 Scripted cue composition — THE primary blocker
Prior Ghidra confirmed the reader/cache shape (`AttributesCueMap::Read 0x1003c0f00`, `AttributeCueTrackEntry::ReadEntry 0x1003c16ac`, cache rebuild/lookup) but **found no mechanism** producing DD42028C's U0 deltas. The gap is the **runtime render/compose path**, not parsing. Decompile **below `SSVenueData::GetLightingState`** and the playback lookup that turns a resolved cue into the emitted CH1–19 frame: how does SoundSwitch, at a given elapsed time, choose and **compose** cue content into the frame? Candidates to prove or kill: layered/overlapping cue composition (not the single-chain LTP the bridge assumes), a cache-invalidation or catalog/attribute-value indirection distinct from `stored_key`, the addressed-footer's real runtime role, or a per-attribute (not per-cue) resolution. The wire-only `raw−1` render rule has **no located binary callsite** — find it. If the exact mechanism is genuinely not in the saved bytes + render path, say so and specify the fail-closed + capture-derived-oracle fallback for scripted (best-effort per intent #4).

### 6.2 Static-look 5-map composition — highest-value tractable crack
Decompile `RebuildStaticLookCache 0x100335230`, `StaticLook::Read 0x10033aa6c`, `SetChannelAttributes 0x10033710c`, `RefreshCache 0x100338198`. Produce the **exact function** that composes `intensity_fraction` (f64), `strobe_fraction` (f64), `ColourValue[8]`, `position_guid[16]`, and the sparse generic `SSAttrValueMap` into the final CH1–19 bytes for the RAVE profile — including how `colour_values.raw_value` and `position_values.position_guid` map to specific channels, and how intensity/strobe fractions scale channel bytes. This directly fixes the confirmed static-look gap in §4.3.

### 6.3 Autoloop phase contract
From `AutoLoopLayout::GetStateForTime 0x10025f000` (the 600-ticks/beat conversion) and the loop state machine: derive SoundSwitch's exact **phase origin/anchor**, cycle length (confirm 19,200 or derive per-loop), quantization, and any reset/continue/snap behavior, plus the fixed render/transport latency. Turn the current grid-search *guessing* into a *derived* contract. Define the post-fix autoloop capture that proves it.

### 6.4 Fixture-group mirror invariant
Confirm from the render path that groups `0x493` and `0x496` always emit identical CH1–19 (intent #1), and specify the assert/flag if they ever diverge.

### 6.5 Time-invariance
Confirm SoundSwitch emits no per-tick time-varying DMX for strobe/colour/movement on this profile (i.e. the fixture self-animates from static channel values) — validating the snap-and-hold model (intent #2). If any surface *does* emit a time-varying stream, that is a scoped exception to raise explicitly, not to silently model.

---

## 7. Ghidra / GhidraMCP authorization and method

- **You are explicitly authorized to use Ghidra and GhidraMCP** against the SoundSwitch 2.10.3 binary. The operator will have the SoundSwitch project open. Prior sessions connected via `mcp__ghidra` (`get_current_function`, `list_methods`, decompile) with no port repair needed; a headless fallback exists if the live server is down.
- Method: start from the confirmed symbol/address map, decompile the **render/compose/lookup** path (not just read/parse), and **cross-check every claim against the live pack data and at least one operator+Claude capture** before encoding it. Prior work is arm64-verified; treat x86_64 as symbol-checked only unless you decompile it.
- Do not present Ghidra output as truth without source/behavior confirmation. `INFERRED`/`AMBIGUOUS` findings require a capture or wire check.

---

## 8. Methodology the spec must follow

**Ghidra (derive the exact algorithm) → reproduce it in exporter + verifier + player → prove with an offline oracle → prove with a live whole-show U0/U1 capture (operator + Claude).** Because the verifier currently re-implements the same semantics as the exporter, the spec must break that circularity: the **oracle's ground truth is SoundSwitch's own output** (Ghidra-derived algorithm and/or captured U0), never a re-render. Captures are run by operator + Claude; you specify exactly what to capture, how to reduce it to a committed fixture, and the pass/fail bar (including that each oracle test must **fail** against today's renderer and **pass** against the fixed one).

---

## 9. The deliverable — the Codex-executable spec you must produce

Write ONE spec, in the operator's Part A–E format, that Codex can execute end to end. It must contain:

- **Part A — Context & root cause (read-only):** the confirmed mechanism per surface (from your Ghidra work), labeled `confirmed` / `assumed` / `unknown`, with binary + code citations. State plainly what is provable and what falls back to capture-derived oracle + best-effort flag.
- **Part B — Design:** the exact composition algorithms to implement for scripted, autoloop, and static-look rendering (the reproductions of §6), the fixture-group mirror assert, the stored-order vs time-order resolution, and the "unverified parity" flag model (per-item, in the pack manifest + status). Keep the static step-function model; do not add time-awareness.
- **Part C — Implementation tasks for Codex:** ordered, each with the files to change (exporter `soundswitch_pack.py`, player `soundswitch_laser_player.py`, verifier `soundswitch_pack_verifier.py`, loader, decoder as needed), a pure-function test seam per task, and the acceptance check. Include: the static-look 5-map composition (highest value), the autoloop phase contract, the scripted cue-composition fix or fail-closed fallback, boundary-10 containment fix, and the verifier changes so it validates against the **oracle** not a self-re-render.
- **Part D — Verification / capture protocol (run by operator + Claude, NOT Fable):** the offline oracle per surface (inputs, reduction of a U0 capture to a committed fixture, the must-fail-then-pass test), and the live whole-show U0/U1 capture exam (what to capture, coverage requirements, `tools/artnet_compare.py` usage, pass/fail). Specify the exact operator+Claude steps and artifacts.
- **Part E — Constraints, invariants, live-safety, and self-review:** §10 below, plus the 9-point pre-handoff checklist.

The spec must be self-contained: no "TBD," no "future spec," no dependence on a second Fable pass.

---

## 10. Constraints, invariants, out-of-scope

- **Repo invariants (do not break):** `StateManager` is the sole `DeckState` writer and sole per-tick pack-frame submitter; the 200 Hz loop gains no filesystem/socket/MIDI/serial/subprocess/blocking work; source SoundSwitch projects are read-only; identity is exact (pinned project UUID; reject others); only independently-verified packs load; reload/export never enables output, changes backend, starts the bridge, or opens hardware; direct DMX and physical MIDI-laser output stay mutually exclusive; blackout/emergency wins; status/logs/docs never leak local paths, ports, device names, UUIDs, raw frames/hashes. (Full list: `soundswitch_exporter_remaining_work.md` §Invariants.)
- **Live-safety:** the bridge drives real lasers. No task may enable hardware output, change backend, or restart the bridge; those are operator-only actions gated by a physical kill path. Reason through the live-mixing case for any behavior change.
- **Git:** work on `main`; no new branches/worktrees. Do not commit secrets, local IPs, device IDs, live config, or the gitignored canonical pack contents.
- **Out of scope (keep fail-closed):** any project other than the pinned UUID; any venue/profile/universe/fixture other than RAVE/CH1–19; any SoundSwitch version ≠ 2.10.3; multi-deck/crossfade emulation (bridge single-active-deck authority selects the source); time-varying/interpolated rendering (snap-and-hold); multi-fixture-group compositing beyond the mirror assert; `.ssproj` internal object graph; hardware validation (operator-only).

## 11. Before you finalize — self-review

Confirm: every mechanism is `confirmed` (Ghidra + capture), `assumed` (stated, with the capture that would confirm it), or `unknown` (with the fail-closed + best-effort-flag fallback) — never guessed. Every Codex task has a pure-function test seam and a must-fail-then-pass oracle check. The capture protocol is executable by operator + Claude with named artifacts and a clear pass/fail. Nothing is deferred to a second pass. The static step-function model is preserved (no time-awareness added). Live-safety and the pinned-scope fail-closed boundaries hold.
