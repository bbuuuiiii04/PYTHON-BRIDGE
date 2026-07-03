---
doc_status: active-investigation
truth_level: live-capture + deterministic-render + pack-data grounded
last_verified_commit: 3f4bcc0
last_verified_date: 2026-07-01
validation_scope: local ignored canonical-pack patch from one operator-approved SoundSwitch U0 capture; software verification only; no restart or hardware validation
---

# SoundSwitch Bridge Pack - Render Defect (scripted CH11 Strobe et al.)

> **2026-07-01 routing update:** this document records the confirmed
> DD42028C generated-pack defect and the ignored local containment patch. The
> current root-cause implementation spec is
> `docs/plans/active/soundswitch_pack_parity_root_cause_spec.md`. Do not treat
> the `oracle_rendered` local pack as proof that the exporter/importer is
> correct.

The bridge's SoundSwitch pack renderer does not reproduce SoundSwitch's DMX
output for this scripted track. For this witness, the immediate failure is a
**pack DATA defect** (wrong/missing channel values in the generated
`rbss_canonical_pack`), NOT a runtime or render-logic bug. The broader root
cause is global: generated `.ssfile` cue replay was being treated as proven
SoundSwitch DMX parity even though the verifier only checks the same internal
cue-resolution model.

## Anchor facts (capture-free, solid)

- **The bridge emits EXACTLY its pack render.** 100.00% of the 22,613 emitted
  scripted frames hash-match the pure `render_scripted_frame(elapsed)` output
  (31 distinct frames, 0 unexplained). Verified via truth sidecar `dmx_sha256`
  vs. deterministic render hashes. So "bridge output" == "pack render"; any
  mismatch with SoundSwitch is a pack/render-content problem, not a runtime one.
- **The render applies cue values verbatim** (`_apply_attribute`: `frame[ch-1] = value`,
  no scaling/math). So it can only ever emit values that exist in the pack data.

## RETRACTED: there is no blackout/flicker defect ("B")

An earlier claim of ~4,570 mid-show dark flickers was a **capture artifact**: during
playback SoundSwitch's own (dark) second universe leaked onto the loopback socket in
the scratch sniffer and was mislabeled as bridge U1. The bridge's own frame log shows
`active_deck=1` for the entire playthrough and only 166 dark frames — one run at the
very start (elapsed<1615 ms, before the first cue). The bridge renders continuously.

## The real defect — pack render ≠ SoundSwitch output

Capture: John Summit & Hayla "Where You Are (Crankdat Remix)", scripted,
ssid `{DD42028C-0823-4A8D-AD7E-B26E24180272}`, ~131 s. SoundSwitch on universe 0
(bridge does not emit U0 — output backend is Enttec serial — so U0 is clean SoundSwitch).

Of SoundSwitch's 31 distinct output looks, the pack render reproduces **23 exactly, 8 wrong.**
Fixture profile (CH→role): CH1 On/Off, CH2 Auto Mode, CH3 Static Pattern, CH4 Pattern Sel,
CH5 Pattern Size, CH6 Horizontal Adj, CH7 Vertical Adj, CH8 Color, CH9 Color Speed,
CH10 Pattern Line, **CH11 Strobe**, CH12–14 Rotation, CH15/16 Movement, CH17 Zoom,
CH18 Gradient, CH19 X/Y Wave.

Per-channel value-set comparison (SoundSwitch U0 vs deterministic render over full track):

| Channel | Role | SoundSwitch value the render CANNOT produce | Render value SoundSwitch never outputs |
|---|---|---|---|
| CH11 | **Strobe** | **227** (SoundSwitch holds it ~14.6 s; also pulses 245 ×22) — pack has only {0,245,255} | — |
| CH6 | Horizontal Adj | **86** | 131 |
| CH1 | On/Off | — | 45 (SoundSwitch has 62 there) |
| CH7 | Vertical Adj | — | 90 |
| CH8 | Color | — | 17 |
| CH15 | Horizontal Move | — | 186 |

The headline: **CH11 (Strobe) never renders SoundSwitch's `227`** — for ~15 s of the
show the strobe is at the wrong value, and the strobe pulses differ. This is exactly a
"ruined laser look," and the bar is exact parity, not approximate.

## Root Cause

Pack data comes from an importer (`import_report.json`, source `.ssproj`) that resolves
cues through `venue_cues.json` into per-cue channel patches. The track's CH11 data
contains only {0,245,255} in BOTH fixture groups (`0x493` and `0x496` are identical, so
the primary-group filter is not the cause). `227` is absent from this track's cues.

Resolved: `227` is present in `venue_cues.json`; this track simply resolves the
wrong cue rows in a few places. The sustained `CH11=227` SoundSwitch output exactly
matches the sparse Venue cue `WHITE DOT STROBE`, while the generated pack had resolved
the same scripted rows to neighboring strobe/pattern-line cues. A global reference
offset is NOT the fix: `raw_reference - 1` still scores best across the track, and
nearby reference conventions make the overall track much worse.

## Local fix applied 2026-07-01

The ignored local canonical pack at `local/soundswitch/rbss_canonical_pack` was patched
for scripted track `dd42028c-0823-4a8d-ad7e-b26e24180272` from the clean SoundSwitch U0
capture at `/tmp/rbss_parity_sniff.jsonl`:

- aligned first lit U0 frame to the first scripted event at `1615ms`
- replaced this track's 91 `pre_rendered_boundaries[*].frame` values with SoundSwitch's
  held U0 frame at each boundary time
- set `pre_render_status` to `oracle_rendered`
- updated `manifest.json` and `.rbss_canonical_pack.source.json` hashes

Patch result: 14/91 boundary frames changed. Runtime render of this track now includes
`CH11 ∈ {0,227,245,255}` and `CH6=86`; event `27539ms` renders
`(3,0,14,86,190,141,110,162,86,0,227,0,0,0,191,0,0,0,121)`.

Later audit against `/tmp/rbss_parity_sniff.jsonl` found that this is not exact
parity. Using first-lit U0 alignment, the old generated DD42028C boundaries
matched nearest SoundSwitch U0 at 69/91 boundaries; the local patch improved the
score to 81/91, but boundary 10 at `41202ms` regressed from a U0-matching old
generated `(CH10,CH11)=(0,255)` to patched `(110,0)`. The patch is useful
operator containment for the headline CH11=227 section, not a validated export
algorithm.

## Current binary/static finding

The 2026-07-01 callable GhidraMCP pass did not find an addressed-footer,
retained-prefix, or shared-table cue remap in the arm64 `.ssfile`
reader/writer/cache path. `ReadAttributesCueTrack -> ReadEntry` reads the cue
map plus timeline integer, resolves a cue GUID, and normal playback cache rebuild
copies the prior cache then overlays the current cue's sparse attributes. That
supports the renderer shape when cue identity is right, but it does not explain
DD42028C's U0 row deltas. A simple offset change is also rejected: nearest-U0
scores were `raw-2 = 6/91`, `raw-1 = 69/91`, direct `= 27/91`, and `raw+1 =
1/91`.

Tracked code support:

- `soundswitch_laser_player.render_scripted_frame()` now prefers verified
  `boundary_frame` values when every scripted event has one. Autoloop rendering still
  uses event replay because wrap/negative-pre-roll behavior is different.
- `soundswitch_pack_verifier.verify_pack()` still rejects accidental boundary mutation
  for normal generated documents, but accepts explicit `pre_render_status:
  oracle_rendered` documents as capture-derived literal boundaries.

## Caveat

SoundSwitch-side values come from one operator-approved live capture (universe 0, clean).
Not re-measured; treated as ground truth per operator direction (skip re-capture).
No bridge restart or hardware validation has been performed after the local pack patch.
A fresh **Export from SoundSwitch** may regenerate the old bad generated
boundaries unless the exporter/importer fix in
`soundswitch_pack_parity_root_cause_spec.md` is implemented.
