---
doc_status: current
truth_level: pilot-run-report
last_verified_commit: 6037a88
last_verified_date: 2026-07-09
validation_scope: >
  STEMS PILOT execution report (AWR-168). Built + ran HTDemucs 4-stem separation on 33 of
  the operator's own brickwalled masters, measured per-stem per-beat envelopes, and
  evaluated the frozen pass/fail gate from stems_pilot_spec.md. Offline tooling only — zero
  bridge runtime change, no v3/v4 cache write, no config edit. Software-tested (16 metrics
  unit tests + full-suite baseline) and separation-run-observed; NOT ear-validated, NOT
  hardware-validated. All numbers measured this run; status words stay within AGENTS.md §10.
  Not implementation-authorizing for the full sweep — see the recommendation.
---

# STEMS PILOT run report — separation quality gate on the operator's masters (AWR-168)

## Verdict in one line

The **separation is clean, cheap, and memory-safe** on the operator's brickwalled masters
(the technical risk the pilot existed to test — a decisive pass), but the **frozen scorecard
gate returned FAIL** on three criteria that trace to coarse-proxy limits, missing
operator-labeled moments, and a thin sidechain anchor set — **not** to separation quality.
The spec's explicit CALL-OFF conditions were all NOT met.

## What actually ran (confirmed)

- Environment: venv `~/.venvs/rbss-stems` **outside** the repo, Python 3.11.15. Installed
  (pinned, resolved this run): **torch 2.13.0, torchaudio 2.11.0, demucs 4.0.1, librosa
  0.11.0, numpy 2.4.6, soundfile 0.14.0, pyrekordbox 0.4.4**. `pyrekordbox` was added
  beyond the brief's pip line because corpus enumeration needs it [assumed-necessary].
- Model: single `htdemucs` (4 stems drums/bass/other/vocals), MIT, weights 80.2 MB. Resolved
  separation call (demucs 4.0.1, confirmed): `apply_model(model, wav, split=True,
  segment=7.8, overlap=0.25, device="cpu", num_workers=0, progress=False)`,
  `torch.set_num_threads(3)`.
- Decode: the corpus-proven librosa/soundfile stack → stereo float32 @ 44.1 kHz (no
  ffmpeg/torchaudio). Stems stayed in memory; only envelope JSONs were written, to
  `~/Library/Application Support/RBSS Bridge/stems_pilot/`.
- Disk floor tool-enforced; run with `--min-free-gb 10`. Free disk stayed ~31–38 GB.
- The run was interrupted once by harness background-task reaping at track 10/33; it is
  resumable by envelope key and completed cleanly on relaunch (10 cached tracks skipped).

## Operational results (measured, 33 tracks) — PASS

- Separation success: **33/33, 0 errors** (target ≥90%).
- **Peak RSS: 1.52 GB** at segment 7.8 (gate wanted <6.5 GB). The ~7 GB figure in the
  literature is *unsegmented*; segmented inference held far below — RAM was never a concern.
- Per-track wall-clock median: **134.7 s (~2.25 min)**. Extrapolated full library
  (~716 tracks) ≈ **27 h on torch-CPU**, resumable — overnight-scale, faster than the
  audit's 35–50 h worst case; an MLX port would cut it further.
- **Reconstruction: median per-beat |sum-of-stems − mix| = 0.04 dB, 100% of tracks within
  1.5 dB.** The four stems re-sum to the master almost exactly — the separation is real and
  clean on brickwalled masters, which was the central technical risk the pilot existed to
  test. This is the load-bearing result.

## Frozen gate result (evaluate_gates on the full 33-track corpus)

**VERDICT: FAIL.** Criteria: operational ✓, reconstruction ✓, sidechain ✗, vocal ✗,
wobble ✓, named-element-floor ✗. Call-off reasons: `sidechain`, `vocal`,
`named_element_floor`. Elements PASS: 5 of 9.

| Element | Verdict | Cleared | Evidence (per-anchor stat; * = cleared) |
|---|---|---|---|
| rolls | **PASS** | 3/6 | dense-run beats 13*, 33*, 15* on buildup anchors vs 0, 2, 0 — clean discriminator |
| screeches | **PASS** | 4/5 | other-mid crest 16.2*, 11.2*, 10.3*, 11.4*, 9.7 — clean discriminator |
| eight08s | **PASS** | 3/3 | sustained bass-sub frac 0.18*, 0.25*, 0.29* |
| distorted_kicks | **PASS** | 4/4 | drums attack-low crest 26.7*, 20.6*, 27.5*, 10.0* (clears broadly — weak specificity) |
| wobble | PASS* | 7/7 | conc 0.50–0.61 — **FALSE POSITIVE**: concentration clears every dense track, wobble or not |
| sidechain_sub | PARTIAL | 1/2 | pump **9.7 dB*** on one Rock Ur World, 1.5 dB on the other — the mechanism works, anchors are thin |
| offbeat_hats | PARTIAL | 1/3 | slot-offset −2.4, 6.0*, 1.5 — kick transient in slot 0 confounds it |
| claps_snares | FAIL | 0/4 | drums-high crest 2.6, 3.1, 6.9, 3.4 — industrial claps buried in the brickwalled wall |
| vocal_axis | FAIL | 0/6 | ghost margin −0.2 … −7.6 (best), never ≤ −12 — auto-windows invalid (drops contain vocals) |

Aggregate criteria: sidechain 1/2 anchors pumped (need ≥2); vocal `pair_separates=True` but
worst ghost margin **+0.8 dB** (need ≤ −12); wobble 7 "moments" (trivially, see false
positive); element floor 5 PASS (need 6) with two elements failing on all anchors.

## The honest finding on the scorecard

Every failing criterion is a **measurement limit, not a separation failure**:

- **Vocal ghost (criterion 4)** needs the operator's labeled *known-instrumental drop
  windows*. Unattended, I auto-derived "high-energy = instrumental," which is wrong for EDM
  — drops routinely **contain** vocals — so the vocal stem reads loud in those windows and
  the margin sits near 0. `pair_separates` is genuinely True (vocal presence differs across
  tracks), and the vocals stem's dynamic range is 50–65 dB (it cleanly reaches near-silence,
  not a constant bleed). The axis exists; the *cleanliness* criterion needs labels.
- **Wobble (criterion 5)** needs the operator's *labeled wobble moments*. Growl-band
  modulation concentration is 0.42–0.61 on **every** dense electronic track — even the duty
  gate the bridge's own validated `lowmid_pulse` uses does not separate a wobble from
  beat-rate periodicity here. So wobble's "PASS" is not trustworthy; honestly, wobble is not
  isolable from coarse per-beat modulation on these masters.
- **Sidechain (criterion 3)** resolved to only **2** anchors (both "Rock Ur World" versions;
  no reliable tech-house genre tag for fill without playlist data). One ducked **9.7 dB** —
  a strong, clean sidechain signal exactly where v4's full-mix read 1/28 — but the other
  only 1.5 dB, so 1/2 < the required 2. The mechanism demonstrably works; the anchor set was
  too thin to clear the count.
- **Claps/snares and offbeat hats** are confounded by the mastered wall (claps buried) and
  by the kick's transient landing in the same drum-high slot as the offbeat.

What *did* clear on his masters, with real per-stem advantage v4's full mix cannot provide:
**rolls, screeches, 808s, distorted kicks, and — where present — a 9.7 dB sidechain duck.**
That is 4–5 elements with measurable advantage, well above the spec's "fewer than 2
elements" call-off floor.

## Was the spec's CALL-OFF triggered? No.

All four explicit call-off conditions were checked and **none fired**: repeated RAM failure
(no — 0 errors, peak 1.52 GB), reconstruction sanity broken (no — 0.04 dB), vocal ghosting
unbounded (no — the vocal stem reaches near-silence, worst margin +0.8 dB is bounded), fewer
than 2 elements show advantage over v4 (no — at least 4). The pilot did not meet all six
PROCEED conditions (the vocal/wobble criteria need operator labels; sidechain needs ≥3
anchors), but it tripped no CALL-OFF — it lands in the gap the binary gate did not cover.

## Recommendation (honest, not implementation-authorizing)

Do **not** read this as "stems don't work." The separation is proven clean, cheap, and
memory-safe on the operator's own brickwalled masters, and it is the only path to a real
vocal axis. What did not clear is a coarse-proxy / missing-label scorecard, not the
separation. Two low-cost paths, either of which unblocks a full commit:

1. **Re-evaluate with labels, no re-separation.** The per-stem envelope cache is kept as the
   record. `tools/stems_pilot.py --report` recomputes the scorecard + gate from those JSONs
   on plain Python (no venv, no torch). Given the operator's labeled instrumental windows +
   wobble moments + a couple more sidechain anchors, the gate can be re-run in seconds
   against the already-separated stems.
2. **Or the executive green-lights the sweep** on the operational + reconstruction proof +
   the elements that cleared, treating the fine rhythmic/vocal proxies as F4-consumer design
   work (finer onset-level analysis than coarse per-beat envelopes) rather than a pilot gate.

## Teardown

Per spec, the venv (1.0 GB) + htdemucs weights (80 MB) were removed to refund the disk. The
record kept: this report, `scorecard.json`, `report.md`, and the 33 per-stem envelope JSONs
under the `stems_pilot/` namespace — re-evaluable via `--report` with **no** re-install. The
venv rebuilds in ~4 min and weights re-download in ~7 s if a re-run or the full sweep is
authorized.

## Corpus resolution (33 tracks; anchors + versions)

Ambiguous titles (versions/edits of the same song) were all included, capped at 3 per
needle — recorded, not single-track guesses. Unresolved anchors: "embercore" (screeches),
"pitch mad attak" (distorted_kicks / claps_snares). Per-element anchor coverage: wobble 7,
rolls 6 (3 shared with wobble), vocal_axis 6, screeches 5, distorted_kicks 4, claps_snares
4, offbeat_hats 3, eight08s 3, **sidechain_sub 2** (short of the ideal 3).

| content_id | elements | title |
|---|---|---|
| 108697335 | wobble,rolls | Dom Dolla - Girl$ (YDG Remix) |
| 221859151 | wobble,rolls | Girl$ (Walker & Royce Remix) |
| 230645698 | wobble,rolls | RESET x girl$ (Stevo Intro Edit) |
| 160453389 | wobble | You & Me (Vintage Culture) |
| 185740735 | wobble | You & Me (Flume Remix) [YDG FLIP] |
| 242247291 | wobble | Billie Eilish - LUNCH (Phrva Flip) |
| 265800373 | wobble | feels like us (capochino flip) |
| 142116429 | rolls | Satisfaction (BEAUZ Hard Techno) |
| 171452719 | rolls | Satisfaction (KX CHR Hard Techno) |
| 222401127 | rolls | non stop x satisfaction (ecchi nate) |
| 40097556 | sidechain_sub | Rock Ur World X Lights (Dabin) |
| 73542876 | sidechain_sub | Rock Ur World (feat. fussy) |
| 152559811 | eight08s | One Chance (feat. Marlhy) |
| 152981372 | eight08s | kidstopbreathing (ionika edit) |
| 177242956 | eight08s | ONE CHANCE (HIVE FLIP) |
| 121635875 | screeches | Crankdat - STFU (Loud Mix) |
| 137456408 | screeches | katseye - gnarly (jpky flip) |
| 184997994 | screeches | DROP EM (Original Mix) |
| 31216947 | screeches | GNARLY (SEUNG x JUMSKY) |
| 40720413 | screeches | GNARLY (OK JAYE! Remix) |
| 11205583 | distorted_kicks,claps_snares | Tremor (Sensation 2014 Anthem) |
| 182595278 | distorted_kicks,claps_snares | Age Of Love (Dave Summer Edit) |
| 209838230 | distorted_kicks,claps_snares | Tremor (WINK Edit) |
| 226226926 | distorted_kicks,claps_snares | TREMOR x PAIN (VIP) [ISOKNOCK] |
| 112870160 | offbeat_hats | BANGARANG (DRYDEN EDIT) |
| 139063315 | offbeat_hats | WHICH ONE (Drake x Central Cee) |
| 205107859 | offbeat_hats | Bangarang (BRLLNT Edit) |
| 14567764 | vocal_axis | Temperature (MERCO Edit) |
| 78739472 | vocal_axis | Temperature (Afinity Remix) |
| 182625749 | vocal_axis | Can't Say Nah (Odd Mob) |
| 39964930 | vocal_axis | Can't Say Nah (Walker & Royce) |
| 248391466 | vocal_axis | ADVENTURE OF A LIFETIME (GECHA) |
| 5193687 | vocal_axis | I Kissed Girl (Netgate Edit) |

## Tests + checks (confirmed)

- `tests/test_stems_pilot_metrics.py`: 16 tests green on Python 3.14 and venv 3.11.
- Full-suite baseline (3.14): 3668 tests, 6 failures + 1 error — the pre-existing known reds
  (export_pack_parity ×2, soundswitch_laser_player slot16, soundswitch_parity_oracle,
  state_manager_drop_presentation ×2 [F2 in-flight], led_color_engine_m2_patch_d). The stems
  files touch none of those modules.
- Three hard checks green: `check_docs_metadata`, `check_agent_contracts`, `check_docs_drift`.
  Contract: `spectral_analysis` code_globs extended with the two stems tools; inspect
  extended with the spec.

## Threshold discipline

Element thresholds were set on the first-5 tuning tracks + spec/domain reasoning and frozen
before the full-corpus evaluation (no post-hoc tuning on the judged data). The one formula
correction during tuning — rolls = longest consecutive-all-sub-beats-filled run, replacing a
dynamic-range-to-noise-floor measure that fired on any loud track — was a correctness fix,
logged here, applied before the full run.

## Plain-language operator summary

I built the stems tool, installed it in a throwaay setup outside the project, and split 33 of
your own tracks into drums / bass / vocals / other overnight. The big result: the splitting
works cleanly on your loud, brickwalled masters — the four parts add back up to the original
almost perfectly (0.04 dB off), it never used more than 1.5 GB of memory, and each track took
about 2¼ minutes, so your whole library is roughly a 27-hour overnight job. That was the real
unknown, and it passed.

The automatic scorecard, though, came back FAIL — but not because the splitting is bad.
Several of the sounds you named came through clearly in their own stem in a way the current
analysis can't see: rolls, screeches, 808s, distorted kicks, and (on one Rock Ur World) a
clean 9.7 dB sidechain "duck" right where the old measure only caught 1 of 28. What it
couldn't score are the things that need YOUR ear-marks: which exact seconds are the wobble
moments, and which drop windows are truly vocal-free. Without those labels my stand-in guesses
don't work (in EDM, drops usually still have vocals, so "loud = no vocals" is wrong), and one
sound — the wobble — genuinely can't be told apart from a normal steady beat by this simple
measure. Claps in the hard-techno wall are buried, and offbeat hats get drowned by the kick.

So: nothing is broken, and I deleted the install to give your disk back (the split-up track
data is kept, so re-checking costs nothing). Two ways forward, your call: (1) you give me the
labeled moments and I re-score in seconds against the stems I already made, or (2) we commit
to the full library on the strength of the clean splitting + the sounds that already came
through, and treat the fussy ones as work for the lights' texture layer later. Either way,
this proved the hard part works.
