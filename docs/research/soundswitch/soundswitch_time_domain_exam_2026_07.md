---
doc_status: research-current
truth_level: capture-and-command-output-grounded
last_verified_commit: 68df846
last_verified_date: 2026-07-02
validation_scope: Offline time-domain parity analysis from passive capture
  tools/ssfmt/captures/parity/parity_20260701T185231Z plus current scratch export
  /Users/bbui/rbss_tmp/rbss_time_domain_pack. No bridge start/stop, no SoundSwitch launch,
  no MIDI/DMX/Enttec action, no runtime-code change.
---

# SoundSwitch Time-Domain Parity Exam - July 2026 Offline Capture

## Bottom line

The existing passive capture proves useful timing facts but does **not** retire the live U0/U1
truth-check exam.

Scripted timeline timing is mostly within one wire frame: 436 measured boundaries, median
15.841 ms, p95 28.229 ms, and 5 boundaries over 40 ms. Three scripted witnesses are effectively
wire-indistinguishable except named outliers; `fc10fc02` has only 3 measured boundaries and all
3 are large misses, so that window remains a blocker/gap rather than a pass.

Autoloop cycling is not cleanly proven by this capture: 1377 measured transitions, median
14.682 ms, but p95 93.783 ms and 230 transitions over 40 ms. Several loops have 700+ ms worst
residuals. The measured phase rate is stable at about 160 BPM, but the transition timing
alignment has visible-size outliers.

## Provenance

- Prompt: `docs/prompts/active/soundswitch_time_domain_offline_exam_codex_prompt.md`.
- Capture: `tools/ssfmt/captures/parity/parity_20260701T185231Z/`.
- Current scratch pack: `/Users/bbui/rbss_tmp/rbss_time_domain_pack`.
- Measurement JSON: `/Users/bbui/rbss_tmp/rbss_time_domain_exam.json`.
- Analyzer: `tools/ssfmt/time_domain_exam.py`.
- Focused tests: `python3 -m unittest tests/test_time_domain_exam.py`.
- Full prompt-required export used the supported CLI form without `--result-json`; the current
  exporter rejects `--result-json` for non-canonical exports.

The scratch export reported manifest SHA
`87957ecd3c812c2aa023f61338ce8c1cb2069930702dfb194965923d3924e995` and active lanes:

```json
{"algorithm_generalized": 67, "oracle_proven": 16, "unverified_parity": 0}
```

The old-to-fixed diff check (`git diff --stat 7e1cae2..5bb3a5b`) changed decoder/verifier/render
evidence files and tests, not the live tick/driver/sender timing path. Therefore this capture's
U0 timing and sidecar/U1 timestamps are usable timing evidence, while old U1 byte values at known
value-bug regions are not.

## Capture inventory

- `actions.jsonl`: 32 operator/action rows.
- `alignment_index.jsonl`: 24 windows: 6 scripted, 18 autoloop, 0 static.
- `status_samples.jsonl`: 12233 rows; 7559 rows include at least one playing deck sample; 7338
  rows include non-unknown BPM.
- Static looks: no accepted held-static windows in the alignment index; attempted static slots
  were recorded but reclassified/incomplete.

Join stats:

- Scripted sidecar/U1 join: 119217 joined, 6967 dropped, monotone ratio 0.9993457089411389.
- The analyzer uses ordered `(sequence, dmx_sha256)` joins through Art-Net sequence wrap; it does
  not use global sequence/hash dictionaries.

## T1 - Scripted Boundary Timing

Overall scripted boundary residuals:

| Metric | Value |
| --- | ---: |
| boundaries | 436 |
| median | 15.841 ms |
| p95 | 28.229 ms |
| RMS | 57.130 ms |
| max absolute | 740.657 ms |
| > one 40 ms wire frame | 5 |

Per witness:

| Witness | Boundaries | Max abs | >40 ms | Drift slope |
| --- | ---: | ---: | ---: | ---: |
| `528e8b22-bd17-41b9-a111-275d3e8b3031` | 30 | 36.003 ms | 0 | 0.076199 ms/boundary |
| `9947c65e-cfd1-476e-aa90-4aed65ae5f11` | 45 | 57.301 ms | 1 | -0.021630 ms/boundary |
| `ae9e3c61-af40-4392-80b4-380d39c631b9` | 358 | 377.891 ms | 1 | -0.021727 ms/boundary |
| `fc10fc02-93c2-418f-8815-16088884da42` | 3 | 740.657 ms | 3 | -113.435940 ms/boundary |

Interpretation: `528e8b22` is measured-pass on timing. `9947c65e` and `ae9e3c61` are mostly
within wire-frame timing but each has a named outlier. `fc10fc02` is not passable from this
offline run; it needs a targeted live or capture rerun.

## T2 - Autoloop Cycling Alignment

Overall autoloop transition residuals:

| Metric | Value |
| --- | ---: |
| transitions | 1377 |
| median | 14.682 ms |
| p95 | 93.783 ms |
| RMS | 131.384 ms |
| max absolute | 748.502 ms |
| > one 40 ms wire frame | 230 |

Wrap residuals:

| Metric | Value |
| --- | ---: |
| wrap transitions | 110 |
| median | 16.204 ms |
| p95 | 143.743 ms |
| RMS | 144.859 ms |
| max absolute | 466.569 ms |
| > one 40 ms wire frame | 23 |

Measured phase rate:

| Metric | Value |
| --- | ---: |
| segment fits | 50 |
| median implied BPM | 159.996 |
| p95 implied BPM | 161.231 |
| max implied BPM | 161.777 |

Largest autoloop residuals:

| Loop | Transitions | Max abs | >40 ms | Wrap max | Median implied BPM |
| --- | ---: | ---: | ---: | ---: | ---: |
| `SSAutoLoop46.ssfile` | 186 | 748.502 ms | 12 | 28.448 ms | 160.001 |
| `SSAutoLoop16.ssfile` | 143 | 742.453 ms | 8 | 28.224 ms | 159.995 |
| `SSAutoLoop15.ssfile` | 64 | 736.980 ms | 4 | 28.380 ms | 159.995 |
| `SSAutoLoop8.ssfile` | 77 | 733.280 ms | 6 | 23.700 ms | 159.990 |
| `SSAutoLoop17.ssfile` | 122 | 725.378 ms | 13 | 285.451 ms | 159.997 |
| `SSAutoLoop47.ssfile` | 41 | 700.019 ms | 8 | 6.549 ms | 159.997 |
| `SSAutoLoop13.ssfile` | 514 | 629.555 ms | 174 | 466.569 ms | 158.634 |
| `SSAutoLoop6.ssfile` | 51 | 267.173 ms | 5 | 267.173 ms | 160.004 |

Interpretation: phase rate is stable, but transition alignment has too many outliers for a
measured-pass verdict. This is a measured difference or capture-method blocker, not a pass.

## T3 - Bridge Decision Latency

The capture's U1 sidecar was produced by old value-buggy code. The analyzer therefore only counts
a U1 transition when the sidecar hash matches the current expected 512-channel frame. That leaves
only 1 hash-safe scripted transition, with a 3725.066 ms U1-minus-U0 delta. This is insufficient
coverage for a decision-latency pass and should be treated as **NOT-COVERED** for the final
greenlight table.

## T4 - Transitions / Active Deck

Three scripted handoffs were visible in the joined sidecar:

| From | To | Sidecar mono gap |
| --- | --- | ---: |
| `528e8b22-bd17-41b9-a111-275d3e8b3031` | `ae9e3c61-af40-4392-80b4-380d39c631b9` | 6.671 ms |
| `ae9e3c61-af40-4392-80b4-380d39c631b9` | `9947c65e-cfd1-476e-aa90-4aed65ae5f11` | 5.417 ms |
| `9947c65e-cfd1-476e-aa90-4aed65ae5f11` | `fc10fc02-93c2-418f-8815-16088884da42` | 1443.264 ms |

U1 zero-frame run lengths in joined scripted rows: 8 runs, median 1673.5 frames, max 15921 frames.
This proves long zero-frame regions exist in the U1 shadow stream, but the offline analyzer does
not yet cleanly separate intentional SoundSwitch-present software-zero, idle gaps, and transition
handoff behavior. The live comparator remains the correct proof for active-deck transition parity.

## T5 - Playback Edges, Rewinds, BPM Events

Measured from capture:

- BPM/phase rate for Autoloops: measured at about 160 BPM across 50 fits.
- General playback exists in status samples: 7559 samples include at least one playing deck.

Not cleanly covered:

- Pause/resume, stop/restart, and seek/rewind behavior are not separately labeled with accepted
  alignment windows in this capture.
- Static Look timing is not covered; `alignment_index.jsonl` has zero static windows.
- Manual controller MIDI behavior is not covered as a pass; static attempts were incomplete or
  unavailable.

Code-level characterization, read-only:

- `state_manager.py:3936-3942` detects elapsed discontinuities using `_PACK_SEEK_JUMP_MS`.
- `state_manager.py:3972-3988` derives `playing`, `paused`, or zero/no transport; pause hold is
  bounded by `STOP_DEBOUNCE_S`.
- `state_manager.py:3992-4005` selects scripted playback at authoritative `elapsed_ms`, and clears
  selection on non-parity diagnostics.
- `state_manager.py:4094-4111` enqueues the truth-check frame with elapsed, transport, static,
  blackout, and native-autoloop intent.
- `state_manager.py:4112-4127` suppresses production pack output to software zero while
  SoundSwitch is connected, while still allowing the truth-check lane to carry the decision.

## T6 Verdict Table

| Dimension | Verdict | Evidence |
| --- | --- | --- |
| DMX output values | PROVEN (values) | Existing 261/261 + A5 16/16 value proof at commit `5bb3a5b`; not rederived here. |
| Attribute cues | PROVEN (values) | Covered by the value proof and current zero-unverified parity export. |
| Scripted tracks | MEASURED-DIFFERENT | Most boundaries are within one wire frame, but 5/436 exceed 40 ms and `fc10fc02` is not passable. |
| Track timeline | MEASURED-DIFFERENT | Median 15.841 ms and p95 28.229 ms, but named outliers remain. |
| DMX timing | MEASURED-DIFFERENT | Scripted mostly pass-like; Autoloop has 230/1377 transitions over 40 ms. |
| Autoloops | MEASURED-DIFFERENT | Stable phase rate near 160 BPM, but large transition residual outliers up to 748.502 ms. |
| Autoloop cycling | MEASURED-DIFFERENT | Wrap median 16.204 ms, but 23/110 wrap transitions exceed 40 ms. |
| Static looks | NOT-IN-CAPTURE | No accepted held-static windows. Live closure: hold/release static over scripted and autoloop, overlap holds, blackout press/toggle. |
| Track rewinding | NOT-IN-CAPTURE | No accepted seek/rewind alignment windows. Live closure: seek backward >=30 s mid-scripted and forward past a cue boundary. |
| Playback | NOT-IN-CAPTURE | Playing samples exist, but pause/stop/restart are not isolated as accepted windows. Live closure: pause >=3 s, resume, stop/restart, mid-track load/play. |
| BPM adjustments | NOT-IN-CAPTURE | Constant-rate Autoloop phase measured, but pitch-fader changes are not isolated. Live closure: move pitch both directions during scripted and held Autoloop. |
| Transitions | NOT-IN-CAPTURE | Three sidecar handoffs observed, but U0 outgoing hold/incoming-show timing is not cleanly classified. Live closure: three deck-to-deck transitions with crossfades. |
| Active deck | NOT-IN-CAPTURE | Handoff rows exist, but not enough to prove active-deck/crossfade behavior. |
| MIDI behavior | NOT-IN-CAPTURE | Static/MIDI windows incomplete/unavailable in capture. |

## Residual Live Exam List

A <=10 minute targeted truth-check run should cover:

1. `fc10fc02` scripted window through at least two cue boundaries.
2. Autoloops `SSAutoLoop46`, `16`, `15`, `8`, `17`, `47`, `13`, and `6`, including one full
   32-beat wrap for at least two of them.
3. Static hold/release over scripted and Autoloop, overlapping holds, and manual blackout.
4. Pause/resume, stop/restart, backward seek >=30 s, forward seek past a cue boundary.
5. Pitch fader both directions during scripted and during held Autoloop.
6. Three deck transitions with real crossfades and active-deck switches.

## Dancefloor Answer

Based only on this offline DMX timing evidence, a dancefloor **could** see differences in the
outlier cases. The normal scripted timing center is effectively wire-frame tight, but the worst
scripted and Autoloop residuals are around 0.7-0.75 seconds, and Autoloop outliers are numerous.
That is too large to dismiss as Art-Net frame cadence. The correct next step is not a code patch
from this report; it is the targeted live U0/U1 truth-check exam to decide whether those outliers
are real behavior differences, capture-alignment artifacts, or old-code/value-region contamination.
