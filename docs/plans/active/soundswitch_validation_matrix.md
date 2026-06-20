---
doc_status: active-validation-evidence
truth_level: byte-and-capture-grounded
last_verified_commit: fd40843
last_verified_date: 2026-06-20
validation_scope: passive software and wire capture only; hardware-unvalidated
---

# SoundSwitch Reverse-Engineering Validation Matrix

## Reading the matrix

`Static exact` is exact CH1-CH19 frame equality from project bytes using the
explicit all-zero/steady-loop policy. Timing residual is reported separately.
`Transition-only` wire-seeded fits are available in the generated JSON but do
not count as static-render proof. `Blocked` means at least one captured segment
retains a layer/field/ownership residual. `Uncaptured` means structural evidence
only.

Reproduce this matrix with `build_coverage_reports.py` using the commands in
`tools/ssfmt/re/README.md`. Status remains **SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED**.

## Evidence matrix

| Evidence | Result | Scope limit |
| --- | --- | --- |
| A5 scripted capture | 16/16 exact; 14/14 positive; 2/2 raw-zero | One file/layout; CH11 layer provisional. |
| Combined autoloop capture | 68 segments; 17 exact segments; 51 unresolved | 19/42 files represented; two decks overlap. |
| Legacy `artnet_lo` capture | 41/42 indices in derived library; 42/42 frozen autoloop hashes still current | No raw segment timestamps/AppLogs; sample-state coverage only. |
| Autoloop structure | 42/42 parsed | Control semantics unresolved. |
| Scripted structure | 44/45 parsed | Only A5 wire validated; demo unsupported. |
| Base/extended catalogs | 42/42 entries; zero trailing bytes | Current v3 files only. |
| TrackMap repeated records | 95 records; 61/61 comparable tags agree | Top-level object graph unnamed; six current scripts unmapped. |
| Fixture prefix | 42/42 share six-group block; all pcaps use only Universe-0 CH1-CH19 and keep Universe 1 zero | Physical four-fixture membership/mirror routing unresolved. |
| Deck correlation | Decks 0 and 1 independently logged | Owner/master/crossfader not logged. |

## Autoloop coverage: 42 rows

`Rec/Cue/TL` is 17-byte record count / dictionary count / total timeline count.
`-1/Ref0` is negative-time / raw-reference-zero. `Max ms` is the maximum matched
static-fit transition residual; `n/a` means no comparable transition, not zero.

| File | Idx | Catalog | Rec/Cue/TL | -1/Ref0 | Aux | Seg | Static exact | Max ms | Mismatch CH | Status |
|---|---:|---|---:|---:|---|---:|---:|---:|---|---|
| 1 | 0 | RED // AG1 (GROOVE) | 11/232/34 | 1/0 | - | 0 | n/a | n/a | - | uncaptured |
| 2 | 1 | DEFAULT 2 (GROOVE) | 32/233/74 | 0/8 | 41841294,42392721,109713279,134893377,152494430,152586487,207820998 | 0 | n/a | n/a | - | uncaptured |
| 3 | 2 | BLACKOUT (BREAKDOWN) | 0/233/2 | 0/2 | - | 3 | 623/699 | n/a | 1,11 | blocked |
| 4 | 3 | LAGGY 1/4 W (DROP) | 79/232/131 | 0/0 | - | 3 | 840/949 | 29.39 | 15 | blocked |
| 5 | 4 | BLACKOUT (GROOVE) | 0/233/1 | 0/1 | - | 9 | 3517/3517 | n/a | - | exact |
| 6 | 5 | stack out in (DROP) | 35/233/13 | 1/0 | - | 4 | 0/1633 | n/a | 3,4,6,7,8,9,11,12,15,18 | blocked |
| 7 | 6 | DEFAULT (GROOVE) | 35/233/146 | 0/16 | 41841294,207820998 | 0 | n/a | n/a | - | uncaptured |
| 8 | 7 | seizure (DROP) | 23/233/34 | 1/0 | - | 2 | 0/794 | n/a | 6,8,9,11,19 | blocked |
| 9 | 8 | CYAN // AG1 (GROOVE) | 11/232/34 | 0/0 | - | 0 | n/a | n/a | - | uncaptured |
| 10 | 9 | PURPLE // AG1 (GROOVE) | 11/232/34 | 0/0 | - | 0 | n/a | n/a | - | uncaptured |
| 11 | 10 | GREEN // AG1 (GROOVE) | 11/232/34 | 0/0 | - | 0 | n/a | n/a | - | uncaptured |
| 12 | 11 | BLUE // AG1 (GROOVE) | 11/232/34 | 1/0 | - | 0 | n/a | n/a | - | uncaptured |
| 13 | 12 | LAGGY 1/8 W (DROP) | 42/233/257 | 1/0 | - | 8 | 0/2913 | n/a | 8,9,15 | blocked |
| 14 | 13 | ruby (DROP) | 2/233/10 | 1/1 | - | 1 | 0/241 | n/a | 1,6,7,8,10,11,17,19 | blocked |
| 15 | 14 | curve out in (DROP) | 32/233/36 | 2/0 | - | 2 | 0/674 | n/a | 8,11,15 | blocked |
| 16 | 15 | pulsating (DROP) | 30/233/51 | 1/1 | - | 3 | 0/1670 | n/a | 1,3,4,6,7,8,9,11,13,15,19 | blocked |
| 17 | 16 | sperm race (DROP) | 60/233/36 | 1/2 | - | 6 | 840/2339 | 22.22 | 1,3,4,6,7,8,9,11,15,19 | blocked |
| 18 | 17 | BLACKOUT (BUILDUP) | 2/233/1 | 0/1 | - | 6 | 1687/1687 | n/a | - | exact |
| 33 | 32 | NEON (GROOVE) | 8/232/17 | 1/0 | - | 0 | n/a | n/a | - | uncaptured |
| 34 | 33 | NEON STUTTER (GROOVE) | 12/232/33 | 0/0 | - | 0 | n/a | n/a | - | uncaptured |
| 35 | 34 | GREEN IN/OUT (GROOVE) | 5/232/17 | 0/8 | 178956970 | 0 | n/a | n/a | - | uncaptured |
| 36 | 35 | GREEN (GROOVE) | 5/230/17 | 0/0 | - | 0 | n/a | n/a | - | uncaptured |
| 37 | 36 | BLUE WAVING (GROOVE) | 25/232/34 | 0/0 | - | 0 | n/a | n/a | - | uncaptured |
| 38 | 37 | BLUE FANNING (GROOVE) | 8/232/33 | 0/0 | - | 0 | n/a | n/a | - | uncaptured |
| 39 | 38 | BLUE FANNING 2 (GROOVE) | 17/232/33 | 0/0 | - | 0 | n/a | n/a | - | uncaptured |
| 40 | 39 | CONVERGING (GROOVE) | 12/232/9 | 0/0 | - | 0 | n/a | n/a | - | uncaptured |
| 41 | 40 | BLUE (GROOVE) | 12/232/66 | 1/32 | - | 0 | n/a | n/a | - | uncaptured |
| 42 | 41 | RED STATIC (GROOVE) | 12/232/66 | 1/32 | - | 0 | n/a | n/a | - | uncaptured |
| 43 | 42 | GREEN STATIC (GROOVE) | 11/232/66 | 0/32 | - | 0 | n/a | n/a | - | uncaptured |
| 44 | 43 | CYAN STATIC (GROOVE) | 12/232/66 | 1/32 | - | 0 | n/a | n/a | - | uncaptured |
| 45 | 44 | BLUE FANNING (GROOVE) | 21/195/131 | 1/0 | - | 0 | n/a | n/a | - | uncaptured |
| 46 | 45 | New Autoloop (DROP) | 10/233/67 | 1/0 | - | 2 | 0/598 | n/a | 8,9,12 | blocked |
| 47 | 46 | MEGA DROP (DROP) | 14/233/70 | 0/0 | - | 2 | 446/800 | 22.57 | 1,3,4,6,7,10,11,12,15 | blocked |
| 48 | 47 | New Autoloop (DROP) | 3/233/13 | 0/0 | 103910499 | 2 | 162/449 | 15.72 | 1,10,11 | blocked |
| 49 | 48 | GREEN // AG (GROOVE) | 11/232/34 | 0/0 | - | 0 | n/a | n/a | - | uncaptured |
| 50 | 49 | New Autoloop (DROP) | 17/233/71 | 0/5 | 6087487,17915603,24042154 | 2 | 228/404 | 14.56 | 1,3,4,6,7,8,11,15,18 | blocked |
| 51 | 50 | RAINBOW // AG (GROOVE) | 11/232/34 | 1/0 | - | 0 | n/a | n/a | - | uncaptured |
| 52 | 51 | New Autoloop (DROP) | 0/233/11 | 1/2 | - | 5 | 766/1353 | 22.80 | 1,3,4,6,7,8,9,11,12,13,15,17,18,19 | blocked |
| 53 | 52 | New Autoloop (DROP) | 0/233/6 | 1/0 | - | 5 | 1789/2417 | 70.32 | 1,4,6,7,10,11,12,13,15,18,19 | blocked |
| 54 | 53 | New Autoloop (DROP) | 0/233/7 | 1/2 | - | 2 | 455/924 | 1.36 | 1,3,4,6,7,8,9,11,15,18,19 | blocked |
| 55 | 54 | New Autoloop (DROP) | 0/233/7 | 1/1 | - | 1 | 1/835 | 0.28 | 1,3,6,7,8,9,10,11,15,18,19 | blocked |
| 56 | 55 | WHITE // AG1 (GROOVE) | 11/232/34 | 0/0 | - | 0 | n/a | n/a | - | uncaptured |

No row has a referenced missing Venue GUID. The unused `b0aca...` dictionary
entry appears in 20 files; file 36 has two different unused stale entries.

## Scripted coverage: 45 rows

Layout keys: `shared` = shared 441-byte table; `footer` = strict dictionary and
timeline followed by a 13-byte trailer and header-addressed footer; `no-anchor`
= strict dictionary/timeline with no shared anchor; `unclassified` = fail closed.

| SSID prefix | Size | Layout | Cue/TL | Ref0 | Continuation | TrackMap records | Wire | Status |
|---|---:|---|---:|---:|---:|---:|---|---|
| 025C1DDF | 6749 | shared | 195/8 | 0 | 0 | 1 | - | structural only |
| 02E3AA51 | 6106 | shared | 162/8 | 3 | 0 | 1 | - | structural only |
| 06F2C1C5 | 29365 | footer | 10/9 | 3 | 0 | 0 | - | structural only |
| 0F32CE31 | 3985 | shared | 60/4 | 0 | 0 | 1 | - | structural only |
| 15D10A9C | 46969 | footer | 10/11 | 3 | 0 | 0 | - | structural only |
| 16F51143 | 6089 | shared | 162/8 | 1 | 0 | 1 | - | structural only |
| 1A62CF25 | 6393 | no-anchor | 119/51 | 19 | 0 | 1 | - | structural only |
| 1FD042ED | 7165 | shared | 119/112 | 21 | 0 | 2 | - | structural only |
| 1FEE70E5 | 4933 | shared | 93/22 | 1 | 0 | 2 | - | structural only |
| 2FCB27C2 | 4777 | shared | 102/1 | 0 | 0 | 3 | - | structural only |
| 32D96480 | 6236 | shared | 162/14 | 2 | 0 | 1 | - | structural only |
| 4883E811 | 6137 | shared | 162/11 | 3 | 0 | 2 | - | structural only |
| 494785CC | 6249 | shared | 162/18 | 4 | 0 | 1 | - | structural only |
| 4C5F1B0F | 10663 | unclassified | -/- | - | - | 2 | - | unsupported |
| 528E8B22 | 9429 | shared | 196/136 | 10 | 0 | 1 | - | structural only |
| 58E67BBC | 5442 | shared | 124/14 | 3 | 0 | 1 | - | structural only |
| 597E28D3 | 33549 | footer | 10/18 | 5 | 0 | 0 | - | structural only |
| 5996871E | 5612 | shared | 118/30 | 8 | 0 | 2 | - | structural only |
| 6145A81A | 5697 | shared | 140/11 | 5 | 0 | 1 | - | structural only |
| 651A3059 | 7137 | shared | 196/31 | 12 | 0 | 1 | - | structural only |
| 69F8532E | 6657 | shared | 196/1 | 0 | 0 | 1 | - | structural only |
| 74044FA4 | 6299 | shared | 129/39 | 8 | 0 | 1 | - | structural only |
| 772519EB | 6869 | shared | 197/13 | 5 | 0 | 1 | - | structural only |
| 8C6BFF4A | 6881 | shared | 208/0 | 0 | 0 | 1 | - | structural only |
| 9383CF6E | 44336 | footer | 10/15 | 2 | 0 | 0 | - | structural only |
| 9947C65E | 7561 | shared | 129/50 | 14 | 0 | 2 | - | structural only |
| A5B0ACD1 | 7621 | shared | 233/16 | 2 | 0 | 1 | 16/16 | byte exact |
| AD786435 | 6181 | shared | 165/10 | 4 | 0 | 1 | - | structural only |
| AE9E3C61 | 17341 | shared | 104/367 | 111 | 256 | 1 | - | structural only |
| B335B3AF | 5977 | shared | 162/1 | 0 | 0 | 1 | - | structural only |
| BFF9DFCD | 8142 | shared | 226/51 | 16 | 0 | 7 | - | structural only |
| C3A1B60D | 6251 | shared | 162/16 | 3 | 0 | 1 | - | structural only |
| CA3D22AA | 6340 | shared | 119/70 | 24 | 0 | 1 | - | structural only |
| D3E7322D | 36995 | footer | 10/16 | 3 | 0 | 0 | - | structural only |
| D44722CA | 7689 | shared | 226/28 | 2 | 0 | 1 | - | structural only |
| D7B1DA3D | 26783 | footer | 10/8 | 1 | 0 | 0 | - | structural only |
| DD42028C | 95206 | footer | 189/91 | 15 | 0 | 9 | - | structural only |
| E36664D0 | 8002 | shared | 25/4 | 0 | 0 | 1 | - | structural only |
| ED463C27 | 5598 | shared | 119/30 | 8 | 0 | 1 | - | structural only |
| ED66BABB | 6009 | shared | 162/3 | 0 | 0 | 1 | - | structural only |
| F0947ED0 | 6958 | shared | 157/59 | 16 | 0 | 1 | - | structural only |
| F1E0AB45 | 6950 | shared | 162/48 | 2 | 0 | 1 | - | structural only |
| F358F6B0 | 7755 | shared | 226/30 | 6 | 0 | 1 | - | structural only |
| FB4EF1CA | 6459 | shared | 166/24 | 1 | 0 | 1 | - | structural only |
| FC10FC02 | 8133 | shared | 216/64 | 13 | 0 | 1 | - | structural only |

## Explicit fail gates

- Files 47, 48, and 55 retain CH11=227 instead of the STROBE cue's CH11=0.
- Auxiliary and negative-time semantics are not uniquely decoded.
- Only A5 has representative scripted wire validation.
- The In-App Demo scripted layout is unsupported.
- Seek/pause/resume/refire/end/unload/transfer behavior is untested.
- The wire address is Universe-0 CH1-CH19, but physical four-fixture
  membership/mirror routing is not decoded.
- Universe-0 deck ownership is not deterministic from current logs.

No exporter or importer may turn `structural only`, `blocked`, `uncaptured`, or
`unsupported` into a supported result without new evidence.
