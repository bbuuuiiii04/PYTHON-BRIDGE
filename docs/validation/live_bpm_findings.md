# Live BPM Memory Findings

Status: VALIDATION REFERENCE

Date: 2026-05-04
Target: Rekordbox 7.2.11 on macOS, DDJ-800, rb_ss_bridge_v2
Scope: historical read-only memory investigation plus integration notes. The
runtime bridge now uses the same fail-closed validation model in
`LiveBPMService`; absolute addresses in this document remain session-local
evidence and must not be hardcoded.

## Integration Status

Accepted for bridge integration behind fail-closed guards:

- `LiveBPMService` attaches read-only to the current Rekordbox process.
- Candidates are promoted only through observed current-session movement.
- Validated values are keyed by current pid/base/deck and invalidate on restart.
- Autoloop arm snapshots validated live BPM when available, otherwise falls back
  to `d.meta.bpm`.
- Active autoloop live BPM follow is enabled by default and can be disabled
  with `RBSS_LIVE_BPM_FOLLOW=0`.
- When validated live BPM diverges from the current timing BPM, the bridge sends
  BPM to all four SoundSwitch deck slots with rate limiting and pairs it with a
  one-shot beat `change=True` re-lock.
- SoundSwitch reacts to BPM sends; the one-shot re-lock is the current
  controlled resync point.

Disable runtime live BPM discovery with:

```text
RBSS_LIVE_BPM_DISABLE=1
```

## Probe

Standalone probe:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm snapshot --deck 1 --mode bpm --expect-bpm 128
python3 -m rb_ss_bridge_v2.probe_live_bpm watch --deck 1 --type f32 --addr 0xADDR
```

The probe reuses `rb_memory.py` Mach/vmmap helpers, resolves current deck anchors, scans float32/float64 BPM or pitch-factor shaped values, and can watch candidate addresses during pitch changes. It has `snapshot`, `watch`, and `compare` subcommands.

Dynamic validation command:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 2 --expect-bpm 126 --expected-after 132.3 --bpm-min 121 --bpm-max 137 --include-rw-regions --duration 25 --hz 5
```

Current-session cache check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2 --expect-bpm 132.3
```

Seed known process-local candidates into a validation run:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 2 --expect-bpm 126 --expected-after 132.3 --addr 0x12d928388 --addr 0x12dba36ec --addr 0x12dba36f0 --watch-limit 8 --duration 25 --hz 5
```

`validate` performs the current dynamic detection pattern in one read-only flow:

- scans for BPM-shaped candidates near `--expect-bpm`;
- watches the top candidates while only the target deck pitch is moved;
- optionally includes manual `--addr` seed candidates before scan-ranked candidates;
- marks candidates as `pass`, `moved_unverified`, `moved_wrong_value`, `zero_start_churn`, `zero_end_decay`, `stale`, or `read_error`;
- reports trace metadata including zero-ish start/end flags and discontinuity count;
- can save full per-candidate traces with `--save-traces`;
- can monitor current-session cached candidates from another deck with `--monitor-cache-deck`, or manual read-only monitor seeds with `--monitor-addr`;
- writes passed candidates to `~/.cache/rb_ss_bridge_v2/live_bpm_candidates.json` only when `--expected-after` is supplied and the final watched value is within tolerance;
- leaves bridge runtime behavior unchanged.

`cache-check` reuses only candidates cached for the current Rekordbox pid, base address, and deck. It is intended as a fast same-process sanity check before deciding whether another broad scan is needed.

Read-only cached-candidate stability monitor:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 2 --expect-bpm 133.9 --duration 30 --hz 5
```

`cache-monitor` watches current-session cached candidates without writing cache. It is meant for deck-separation checks, for example moving Deck A while confirming cached Deck B live-BPM fields stay stable.

Pure validation logic has lightweight unit coverage:

```bash
python3 -m unittest discover -s tests
```

These tests cover verdict classification, zero-start/zero-end churn classification, trace metadata, render-cache ranking penalties, and current-session cache filtering. They do not attach to Rekordbox or prove any address live; live address proof still requires controlled `validate`/`watch` runs.

Important: all absolute addresses below are session-local evidence. Do not integrate any hardcoded address or single fixed offset into the bridge.

## Acceptance Status

Accepted with current-session dynamic validation, not static offsets.

The evidence proved that Rekordbox exposes live/displayed BPM-like float32
values that update with pitch before or during arm-relevant windows. The bridge
does not require a stable absolute offset. It dynamically scans, watches,
validates movement, and fails closed when validation is absent.

## Session 1 Evidence

Rekordbox pid: `5304`
Base: `0x100554000`

Tracks:

- Deck A / Deck 1: `Twin Diplomacy - I Got Feeling`, TimecodeLink BPM `150.0`, later pitched to `135.9`.
- Deck B / Deck 2: `I Wanna Go (John Summit Extended Remix)`, TimecodeLink BPM `138.0`, later pitched to `144.8`.

Deck 1:

- Strong candidate: `0x1257ed938`
- Structural relation: `secondary1 + 0x1cb8`
- Behavior: changed from `150.0` to `135.919998169`, matching TimecodeLink Deck A `135.9`.
- Other exact-150 fields such as `0x1257edef4`, `0x1257ee184`, `0x1257f28b4`, and `0x1257f2b44` stayed stale/cache-like and should not be promoted.

Deck 2:

- Initial exact-138 candidates `0x138066780` and `0x13a7624ec` stayed static at `138.0`; reject as stale/cache.
- Live candidates moved from `138.0` to about `144.8448` during Deck B pitch:
  - `0x13d7217bc`
  - `0x13f2db89c`
  - `0x13fa9e76c`
- TimecodeLink later reported Deck B `BPM=144.8`.
- These are strong temporal candidates but heap/UI-cache-looking and not structurally anchored.

## Session 2 Evidence After Restart

Rekordbox pid: `26636`
Base: `0x100068000`

Fresh anchors:

- `container = 0x110f16ec0`
- `dpu1 = 0x6000039b0690`
- `inner1 = 0x600006af5930`
- `secondary1 = 0x110f18340`
- `container_dpu2_slot = 0x6000031763f0`
- `container_dpu2_inner = 0x104b365d0` (suspect path; not live BPM proof)

Tracks:

- Deck A: `I Love It (Cazes Edit)`, BPM `130.0`, then pitched to `122.2`.
- Deck B: `devault - feels like us (capochino flip)`, BPM `140.0`, then pitched to `147.0`, then returned to `140.0`.

Deck 1:

- Fresh exact-130 field: `0x110f19e08`
- Structural relation: `secondary1 + 0x1ac8`
- Behavior after pitch: `122.199996948`, matching TimecodeLink Deck A `122.2`.
- Cross-restart note: Deck 1's offset changed from `secondary1 + 0x1cb8` to `secondary1 + 0x1ac8`; do not hardcode the offset.

Deck 2:

- Old pre-restart chain addresses read `0.0` after restart; reject absolute reuse.
- Broad scan while Deck B was about `147.0` found many duplicates.
- Watched candidates:
  - `0x13cd5234c`: `147.0` then dropped to `0.0`; reject.
  - `0x109789660`: stayed around `147.000015`; reject as stale.
  - `0x119750280`: stayed around `139.989990`; reject as stale.
  - `0x117d92fac`: moved `146.989 -> 145.589 -> 142.790 -> 141.390 -> 139.990`.
  - `0x11975027c`: moved with `0x117d92fac`.
- TimecodeLink later reported Deck B `140.0`, matching `0x117d92fac` and `0x11975027c` at `139.989990234`.
- Current best Session 2 Deck 2 candidates: `0x117d92fac` and `0x11975027c`.

## Session 3 Evidence After Restart

Latest TimecodeLink tail at about 2026-05-04 08:43-08:44 shows:

- Deck A: `Blow Your Brain Cell (Extended...)`, BPM `132.0`, paused.
- Deck B: `EsDeeKid, Timothee Chalamet - 4 Raws (Whethan Remi...)`, BPM `144.1`, paused.

Rekordbox pid: `27400`
Base: `0x104f40000`

Fresh anchors:

- `container = 0x152f2fc50`
- `dpu1 = 0x600001178b60`
- `inner1 = 0x6000041c6560`
- `secondary1 = 0x11b314430`
- `container_dpu2_slot = 0x6000019bc8c0`
- `container_dpu2_inner = 0x109a0e5d0` (suspect path; not live BPM proof)

Deck 1 snapshot:

- Top exact field: `0x11b3160e8`
- Structural relation: `secondary1 + 0x1cb8`
- Value: f32 `132.000000`
- Pitch-watch behavior: moved from `132.000000` to `116.159996033`.
- TimecodeLink later reported Deck A `BPM=116.2`.
- Status: strong Session 3 Deck 1 candidate. This further supports `secondary1 + 0x1cb8`, but Session 2 still showed `secondary1 + 0x1ac8`, so offset rediscovery remains required.

Deck 2 snapshot:

- Broad bounded scan at expected BPM `144.1` found many duplicate BPM-like fields.
- Exact f64 candidates included:
  - `0x11b3e3ee8`
  - `0x11b588af8`
- Near f32 candidates included:
  - `0x11b31aaa8` at `144.119995`, also visible as `secondary1 + 0x6678`
  - `0x11b7fb5ac`
  - `0x11b83e8dc`
  - `0x11e30ddbc`
  - `0x11e30ddc0`
- Pitch-watch behavior after Deck B pitch:
  - `0x11b31aaa8`: `144.119995117 -> 158.531997681`
  - `0x11b7fb5ac`: `144.119995117 -> 158.531997681`
  - `0x11b83e8dc`: `144.119995117 -> 158.531997681`
  - `0x11e30ddbc`: `144.119995117 -> 158.531997681`
  - `0x11e30ddc0`: stayed `144.119995117`; reject as stale.
- TimecodeLink later reported Deck B `BPM=158.5`.
- Status: strong Session 3 Deck 2 temporal candidates, but still not structurally anchored. `0x11b31aaa8` is the most interesting of this group because it is nearest to known anchors (`secondary1 + 0x6678`), although the anchor itself is Deck 1 oriented and cannot be treated as Deck 2 proof without further structure validation.

## Session 4 Evidence After Restart

Rekordbox pid: `28244`
Base: `0x102efc000`

Fresh anchors:

- `container = 0x12f615d40`
- `dpu1 = 0x600000b5e840`
- `inner1 = 0x600005819ba0`
- `secondary1 = 0x11c0091d0`
- `container_dpu2_slot = 0x600000390f00`
- `container_dpu2_inner = 0x1079ca5d0` (suspect path; not live BPM proof)

Tracks:

- Deck A: `9A - How Deep Is Your Love x Glue (Tiger Toast Boo...)`, BPM `125.0`, later `118.8`.
- Deck B: `Odd Mob 'Rock The Rhythm (I Like That)' [Extended...]`, BPM `132.0`, later `141.2`.

Deck 1:

- Anchor-window snapshot did not find a 125.0 match near the usual Deck 1 route.
- Dominant near-anchor values were stale-looking `128.0` and `120.0` fields.
- Direct watch of prior Deck 1 offsets:
  - `secondary1 + 0x1cb8` at `0x11c00ae88`: stayed `0.0`.
  - `secondary1 + 0x1ac8` at `0x11c00ac98`: stayed `0.0`.
- TimecodeLink later reported Deck A `BPM=118.8`, but the watched Deck 1 offsets did not capture it.
- Status: negative evidence for hardcoded Deck 1 offsets. Deck 1 also needs rediscovery/ranking, not just Deck 2.

Deck 2:

- Broad bounded scan at expected BPM `132.0` again found many duplicate exact/near fields.
- Watched candidates after Deck B pitch:
  - `0x11c1e63ec`: `132.000000000 -> 141.240005493`
  - `0x11d8aa6cc`: `132.000000000 -> 141.240005493`
  - `0x12801527c`: `132.000000000 -> 141.240005493`
  - `0x13f74a8b8`: `132.000000000 -> 141.240005493`
  - `0x11c1e63f0`: stayed `132.000000000`; reject as stale duplicate.
  - `0x11d703f38`: stayed `131.892425537`; reject as stale/non-live.
- TimecodeLink later reported Deck B `BPM=141.2`.
- Status: strong Session 4 Deck 2 temporal candidates. This is the second post-restart Deck 2 session where exact duplicate fields split cleanly into live and stale groups during pitch-watch.

## Session 5 Evidence After Restart

Rekordbox pid: `28908`
Base: `0x104084000`

Fresh anchors:

- `container = 0x12d8053c0`
- `dpu1 = 0x6000007c0000`
- `inner1 = 0x600005480000`
- `secondary1 = 0x11a704790`
- `container_dpu2_slot = 0x600000fb3e30`
- `container_dpu2_inner = 0x108b525d0` (suspect path; not live BPM proof)

Tracks:

- Deck A: `How It's Done`, BPM `160.0`.
- Deck B: `Rude Boy (Cazes Edit)`, BPM `126.0`, later `132.3`.

Deck 1:

- Anchor-window snapshot did not find a clean `160.0` near `secondary1`.
- Best close candidate was `0x60000548ea54` at `inner1 + 0xea54`, value `160.431167603`.
- Watch result: `0x60000548ea54` stayed unchanged while Deck B pitch moved.
- Status: useful Deck A control only. No Session 5 Deck 1 live-BPM candidate was validated.

Deck 2:

- Broad bounded scan at expected BPM `126.0` again found many duplicate exact/near fields.
- Watched candidates after Deck B pitch:
  - `0x12d928388`: `126.000000000 -> 132.299987793`
  - `0x12dba36ec`: `126.000000000 -> 132.300003052`
  - `0x12ddac77c`: `126.000000000 -> 132.300003052`
  - `0x12851064c`: `126.000000000 -> 132.300003052`
  - `0x12d9298d0`: `125.984252930 -> 132.283462524`
  - `0x12c65e560`: `125.984252930 -> 132.283462524`
  - `0x12dba36f0`: stayed `126.000000000`; reject as stale duplicate.
- TimecodeLink later reported Deck B `BPM=132.3`.
- Status: strong Session 5 Deck 2 temporal candidates with clean deck separation. This confirms the Session 3/4 pattern: one pitch-watch can split exact BPM duplicates into live and stale groups.

Session 5 cache validation:

- Seeded `validate` with known Session 5 Deck 2 live candidates and one stale duplicate.
- A first run from about `132.0` to intended `140.0` correctly rejected the candidates as `moved_wrong_value` because the actual final value was `140.819992`, outside the requested target tolerance.
- A second run with final target `140.82` passed and cached four live candidates:
  - `0x12dba36ec`
  - `0x12ddac77c`
  - `0x12851064c`
  - `0x12d928388`
- Stale duplicate `0x12dba36f0` stayed `126.000000000` and was rejected as `stale`.
- `cache-check --deck 2 --expect-bpm 140.82` read back all four cached current-session candidates and each matched the current live Deck B value.

## Session 6 Evidence After Restart

Rekordbox pid: `50777`
Base: `0x104330000`

Fresh anchors:

- `container = 0x12ff42c00`
- `dpu1 = 0x6000022298f0`
- `inner1 = 0x600007115110`
- `secondary1 = 0x10f113ca0`
- `container_dpu2_slot = 0x600002a638e0`
- `container_dpu2_inner = 0x108dfe5d0` (suspect path; not live BPM proof)

Tracks:

- Deck A: `Bulletproof x Control x I Cannot (Cazes VIP Edit)`, BPM `130.0`.
- Deck B: `We Could Be Love (Odd Mob Extended Remix)`, BPM `130.0`, later `133.9`.

Cache invalidation:

- Before rediscovery, `cache-check --deck 2` returned zero current-session candidates because the previous cache entries were keyed to the old pid/base. This confirms stale per-process cache entries are not reused after restart.

Deck 2 rediscovery:

- Fresh scanner validation at Deck B `130.0` found many BPM-shaped candidates.
- During a seeded validation move, three candidates moved with Deck B from `130.000000` to `133.899994`; five same-value duplicates stayed stale:
  - moved: `0x12ff45e98`
  - moved: `0x12ce8782c`
  - moved: `0x128fec9fc`
  - stale: `0x10f115cc8`
  - stale: `0x12ce5f5ec`
  - stale: `0x128feca00`
  - stale: `0x1285b6cb0`
  - stale: `0x1285b6cac`
- A second validation with final target `133.9` passed and cached four current-session candidates:
  - `0x12ff45e98`
  - `0x12ce8782c`
  - `0x128fec9fc`
  - `0x12ff473e0`
- `cache-check --deck 2 --expect-bpm 133.9` read back all four cached candidates and each matched the current Deck B value.
- Status: restart rediscovery plus cache invalidation/promotion are validated for Deck 2.

## Session 7 Deck 1 Parity Attempt

Same Rekordbox process as Session 6:

- pid/base: `50777` / `0x104330000`
- Deck A: `Bulletproof x Control x I Cannot (Cazes VIP Edit)`, TimecodeLink `BPM=130.0`, later `133.9`.
- Deck B: `We Could Be Love (Odd Mob Extended Remix)`, TimecodeLink `BPM=133.9`.

Deck 1 validation scan at initial Deck A `130.0`:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 130.0 --bpm-min 124 --bpm-max 136 --include-rw-regions --watch-limit 20 --duration 8 --hz 4 --max-hits-per-region 12
```

- Watched 20 candidates.
- All 20 were `stale`.
- TimecodeLink later showed Deck A did not move until after this watch window, so this run is not strong negative evidence by itself.

Deck 1 validation after Deck A and Deck B were both beatmatched at `133.9`:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 133.9 --bpm-min 126 --bpm-max 141 --include-rw-regions --watch-limit 28 --duration 20 --hz 5 --max-hits-per-region 16
```

- Four SQLite-region fields were marked `moved_unverified`, but they started at `0.0` and ended at unrelated values:
  - `0x115bc8e18`: `0.000000 -> 134.396042`
  - `0x115bcd90c`: `0.000000 -> 134.640625`
  - `0x10c260e84`: `0.000000 -> 131.450760`
  - `0x115bc8cb4`: `0.000000 -> 136.380676`
- The strongest current-session Deck 2 cached candidates stayed fixed at `133.899994` during the Deck 1 run:
  - `0x12ff45e98`
  - `0x12ce8782c`
  - `0x128fec9fc`
- TimecodeLink still showed Deck A and Deck B both at `133.9` through the run, so no Deck 1 candidate could be promoted.

Seeded follow-up on the four SQLite fields plus known Deck 2 candidates:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 133.9 --addr 0x115bc8e18 --addr 0x115bcd90c --addr 0x10c260e84 --addr 0x115bc8cb4 --addr 0x10f115cc8 --addr 0x12ff45e98 --addr 0x12ce8782c --addr 0x128fec9fc --bpm-min 126 --bpm-max 141 --include-rw-regions --watch-limit 12 --duration 30 --hz 5 --max-hits-per-region 8
```

- The four SQLite fields decayed to `0.0`; reject as unrelated churn, not live BPM:
  - `0x115bc8cb4`: `136.380676 -> 0.000000`
  - `0x115bcd90c`: `134.640625 -> 0.000000`
  - `0x115bc8e18`: `134.396042 -> 0.000000`
  - `0x10c260e84`: `131.450760 -> 0.000000`
- Known Deck 2 candidates and a same-value duplicate stayed fixed at `133.899994`.
- `cache-check --deck 1 --expect-bpm 133.9` returned zero current-session cached candidates.
- `cache-check --deck 2 --expect-bpm 133.9` still returned four current-session candidates matching Deck B.
- Status: Deck 1 is still unsolved. Today produced no pass/cache evidence and no valid deck-separation pass.

## Post-Session 7 Probe Improvements

After Session 7, the probe gained read-only evidence-quality improvements. These are code/tooling changes only; they do not add live Deck 1 evidence and do not change bridge runtime behavior.

New validation metadata:

- `WatchResult` records whether the first and final finite samples were zero-ish.
- `WatchResult` records the number of adjacent-sample discontinuities.
- `--save-traces` writes full timestamp/value traces to `~/.cache/rb_ss_bridge_v2/live_bpm_traces_<timestamp>.json`.

New verdict labels:

- `zero_start_churn`: a candidate starts at `0.0` and later jumps to nonzero BPM-like values.
- `zero_end_decay`: a candidate starts nonzero and later decays to `0.0`.

These labels are intended to make the Session 7 SQLite-region false positives obvious in the first pass instead of leaving them as generic `moved_unverified`.

New deck-separation helpers:

- `validate --monitor-cache-deck <deck>` watches current-session cached candidates from another deck during the same validation window.
- `validate --monitor-addr 0xADDR` adds manual read-only monitor seeds.
- `cache-monitor --deck <deck>` watches current-session cached candidates without scanning, validating, or writing cache.

Example beatmatched ownership check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 133.9 --expected-after 125.0 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --monitor-cache-deck 2 --save-traces
```

This tests Deck 1 candidates while also confirming current-session Deck 2 cached fields do not follow Deck A pitch movement. Passing Deck 1 candidates are still required before claiming Deck 1 parity.

## Session 8 Deck 1 Current-Session Pass And Separation

Same Rekordbox process as Sessions 6-7:

- pid/base: `50777` / `0x104330000`
- Deck A: `Rude Boy (Cazes Edit)`, TimecodeLink `BPM=129.8`, then `127.0`, then `129.8`.
- Deck B: `We Could Be Love (Odd Mob Extended Remix)`, TimecodeLink `BPM=133.9`, later `129.8`.

Initial Deck 1 scan with Deck 2 monitor:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 129.78 --expected-after 127.0 --bpm-min 123 --bpm-max 136 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --max-hits-per-region 16 --monitor-cache-deck 2 --save-traces
```

- No Deck 1 candidate passed because the Deck A pitch movement happened before the scan/watch window captured a clean before/after transition.
- Deck 2 monitor candidates stayed stable at `133.899994` / `133.838654`.
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T215241Z.json`

Seeded fast Deck 1 validation:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 127.0 --expected-after 129.8 --addr 0x10f115cc8 --addr 0x10f117210 --addr 0x11cff4fe0 --addr 0x11cff4e98 --watch-limit 8 --duration 30 --hz 5 --tolerance 0.35 --monitor-cache-deck 2 --save-traces
```

- Two Deck 1 candidates passed and were cached:
  - `0x10f115cc8`: `127.000000 -> 129.800003`, `pass`, nearest `secondary1 +0x2028`
  - `0x10f117210`: `126.984123 -> 129.783783`, `pass`, nearest `secondary1 +0x3570`
- Two seeded CoreGraphics-looking fields stayed stale:
  - `0x11cff4e98`: `127.999992 -> 127.999992`
  - `0x11cff4fe0`: `128.000000 -> 128.000000`
- Deck 2 monitor candidates stayed stable:
  - `0x12ff45e98`: `133.899994 -> 133.899994`
  - `0x12ff473e0`: `133.838654 -> 133.838654`
  - `0x12ce8782c`: `133.899994 -> 133.899994`
  - `0x128fec9fc`: `133.899994 -> 133.899994`
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T215411Z.json`

Deck 1 cache check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1 --expect-bpm 129.8
```

- Current-session Deck 1 cache contained two candidates:
  - `0x10f115cc8`: `129.800003`, `matches`
  - `0x10f117210`: `129.783783`, `matches`

Deck separation with only Deck B moved:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 1 --expect-bpm 129.8 --duration 30 --hz 5
```

- Deck 1 cached candidates stayed fixed while Deck B moved:
  - `0x10f115cc8`: `129.800003 -> 129.800003`, `stale`
  - `0x10f117210`: `129.783783 -> 129.783783`, `stale`
- `Expected BPM mismatches: 0`
- TimecodeLink confirmed Deck B moved from `133.9` to `129.8` while Deck A stayed `129.8`.

Status:

- Deck 1 now has strong current-session pass/cache evidence.
- Deck 1 also has current-session deck-separation evidence against Deck 2 movement.
- Deck 1 is still not fully solved until restart cache invalidation, rediscovery, recache, and post-restart separation are validated.

## Session 9 Deck 1 Restart Rediscovery

Rekordbox was restarted after Session 8.

New process:

- pid/base: `56549` / `0x104598000`
- Previous process was `50777` / `0x104330000`.

Tracks:

- Deck A: `DaBaby - POP DAT THANG (XANDRA Remix - 132bpm Fmin)`, TimecodeLink `BPM=132.0`, later `128.0`.
- Deck B: `Doechii - Nissan Altima [Devault Remix]`, TimecodeLink `BPM=132.0`, later `128.0`.

Cache invalidation after restart:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2
```

- Deck 1 current-session cached candidates: `0`
- Deck 2 current-session cached candidates: `0`
- Status: old absolute candidates from pid/base `50777` / `0x104330000` did not apply to the new process.

Deck 1 rediscovery from beatmatched state:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 132.0 --expected-after 128.0 --bpm-min 124 --bpm-max 138 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --max-hits-per-region 16 --save-traces
```

- Four Deck 1 candidates passed and were cached:
  - `0x146ef5378`: `132.000000 -> 128.000000`, nearest `secondary1 +0x1998`
  - `0x146eedb6c`: `132.000000 -> 128.000000`, nearest `container -0x4a04`
  - `0x146ef68c0`: `132.013199 -> 128.012802`, nearest `secondary1 +0x2ee0`
  - `0x146ef6a50`: `132.013199 -> 128.012802`, nearest `secondary1 +0x3070`
- One IOAccelerator candidate was correctly rejected as churn:
  - `0x134ece308`: `132.000000 -> 0.000000`, `zero_end_decay`
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T220150Z.json`

Deck 1 cache check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1 --expect-bpm 128.0
```

- Current-session Deck 1 cache contained four candidates, all matching:
  - `0x146ef5378`: `128.000000`
  - `0x146eedb6c`: `128.000000`
  - `0x146ef68c0`: `128.012802`
  - `0x146ef6a50`: `128.012802`

Deck separation with only Deck B moved:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 1 --expect-bpm 128.0 --duration 30 --hz 5
```

- Deck 1 cached candidates stayed fixed while Deck B moved:
  - `0x146ef5378`: `128.000000 -> 128.000000`, `stale`
  - `0x146ef68c0`: `128.012802 -> 128.012802`, `stale`
  - `0x146ef6a50`: `128.012802 -> 128.012802`, `stale`
  - `0x146eedb6c`: `128.000000 -> 128.000000`, `stale`
- `Expected BPM mismatches: 0`
- TimecodeLink confirmed Deck B moved from `132.0` to `128.0` while Deck A stayed `128.0`.

Status:

- Deck 1 now has restart cache invalidation, rediscovery, recache, cache-check, and deck-separation evidence.
- Absolute addresses and offsets still remain session-local. Session 8 and Session 9 found different addresses and different nearest-anchor deltas.
- This is enough evidence to discuss a guarded opt-in prototype design, but not enough to make live BPM default bridge behavior.

## Session 10 Deck 1 Restart Rediscovery

First extra restart after Session 9.

New process:

- pid/base: `57703` / `0x102630000`
- Previous process was `56549` / `0x104598000`.

Tracks:

- Deck A: `Your Mind (HNTR Remix)`, TimecodeLink `BPM=132.0`, later `128.0`.
- Deck B: `Gimme That (Bass) (Original Mix) Clean 132`, TimecodeLink `BPM=132.0`, later `128.0`.

Cache invalidation after restart:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2
```

- Deck 1 current-session cached candidates: `0`
- Deck 2 current-session cached candidates: `0`

Deck 1 rediscovery:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 132.0 --expected-after 128.0 --bpm-min 124 --bpm-max 138 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --max-hits-per-region 16 --save-traces
```

- Five Deck 1 candidates passed and were cached:
  - `0x11932c928`: `132.000000 -> 128.000000`, nearest `secondary1 +0x1f18`
  - `0x14520a91c`: `132.000000 -> 128.000000`, nearest `secondary1 +0x2bedff0c`
  - `0x1452f62cc`: `132.000000 -> 128.000000`, nearest `secondary1 +0x2bfcb8bc`
  - `0x11932de70`: `131.940628 -> 127.942429`, nearest `secondary1 +0x3460`
  - `0x11932e000`: `131.940628 -> 127.942429`, nearest `secondary1 +0x35f0`
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T220826Z.json`

Deck 1 cache check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1 --expect-bpm 128.0
```

- Current-session Deck 1 cache contained five candidates, all matching:
  - `0x11932c928`: `128.000000`
  - `0x14520a91c`: `128.000000`
  - `0x1452f62cc`: `128.000000`
  - `0x11932de70`: `127.942429`
  - `0x11932e000`: `127.942429`

Deck separation with only Deck B moved:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 1 --expect-bpm 128.0 --duration 30 --hz 5
```

- Deck 1 cached candidates stayed fixed while Deck B moved:
  - `0x11932c928`: `128.000000 -> 128.000000`, `stale`
  - `0x11932de70`: `127.942429 -> 127.942429`, `stale`
  - `0x11932e000`: `127.942429 -> 127.942429`, `stale`
  - `0x14520a91c`: `128.000000 -> 128.000000`, `stale`
  - `0x1452f62cc`: `128.000000 -> 128.000000`, `stale`
- `Expected BPM mismatches: 0`
- TimecodeLink confirmed Deck B moved from `132.0` to `128.0` while Deck A stayed `128.0`.

Status:

- Deck 1 restart rediscovery succeeded again with a new pid/base and a new address set.
- This further supports scan/watch/cache behavior as the useful invariant.
- Absolute addresses and nearest-anchor deltas remain session-local.

## Session 11 Deck 1 Restart Rediscovery

Second extra restart after Session 9.

New process:

- pid/base: `58398` / `0x102084000`
- Previous process was `57703` / `0x102630000`.

Tracks:

- Deck A: `PICTURE IN MY MIND W IN K NIKKO REMIX FINAL`, TimecodeLink `BPM=128.0`, later `132.0`.
- Deck B: `Right Round (Netgate Edit)`, TimecodeLink `BPM=128.0`, later `132.0`.

Cache invalidation after restart:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2
```

- Deck 1 current-session cached candidates: `0`
- Deck 2 current-session cached candidates: `0`

Deck 1 rediscovery, opposite pitch direction:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 128.0 --expected-after 132.0 --bpm-min 124 --bpm-max 138 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --max-hits-per-region 16 --save-traces
```

- Two Deck 1 candidates passed and were cached:
  - `0x14874d818`: `128.000000 -> 132.000000`, nearest `secondary1 +0x1dc8`
  - `0x11c15c20c`: `128.000000 -> 132.000000`, nearest `base +0x1a0d820c`
- One IOAccelerator candidate moved but landed wrong and was rejected:
  - `0x11af326bc`: `128.000000 -> 0.501961`, `moved_wrong_value`
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T221247Z.json`

Deck 1 cache check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1 --expect-bpm 132.0
```

- Current-session Deck 1 cache contained two candidates, both matching:
  - `0x14874d818`: `132.000000`
  - `0x11c15c20c`: `132.000000`

Deck separation with only Deck B moved:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 1 --expect-bpm 132.0 --duration 30 --hz 5
```

- Deck 1 cached candidates stayed fixed while Deck B moved:
  - `0x14874d818`: `132.000000 -> 132.000000`, `stale`
  - `0x11c15c20c`: `132.000000 -> 132.000000`, `stale`
- `Expected BPM mismatches: 0`
- TimecodeLink confirmed Deck B moved from `128.0` to `132.0` while Deck A stayed `132.0`.

Status:

- Deck 1 rediscovery passed in the opposite pitch direction with a new pid/base and new address set.
- Deck separation passed again after rediscovery.
- Absolute addresses and nearest-anchor deltas remain session-local.

## Session 12 Deck 2 Incoming-Track Rediscovery

Restarted Rekordbox and loaded different-BPM tracks to model the normal DJ
beatmatch flow: keep the outgoing deck stable and pitch the incoming deck into
match.

New process:

- pid/base: `59202` / `0x104014000`
- Previous process was `58398` / `0x102084000`.

Tracks and TimecodeLink baseline:

- Deck A: `Blow Your Brain Cell (Extended`, TimecodeLink `BPM=132.0`.
- Deck B: `Function  (Extended Mix)`, TimecodeLink `BPM=130.0`.
- Both decks were paused.

Cache invalidation after restart:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2
```

- Deck 1 current-session cached candidates: `0`
- Deck 2 current-session cached candidates: `0`

Deck 2 rediscovery while pitching only Deck B from `130.0` to `132.0`:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 2 --expect-bpm 130.0 --expected-after 132.0 --bpm-min 124 --bpm-max 138 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --max-hits-per-region 16 --save-traces
```

- Five Deck 2 candidates passed and were cached:
  - `0x131d8f30c`: `130.000000 -> 132.000000`, nearest `secondary1 +0x22e753cc`
  - `0x135a5dc3c`: `130.000000 -> 132.000000`, nearest `secondary1 +0x26b43cfc`
  - `0x135dfc4ec`: `130.000000 -> 132.000000`, nearest `secondary1 +0x26ee25ac`
  - `0x127114de8`: `130.000000 -> 132.000000`, nearest `secondary1 +0x181faea8`
  - `0x10ef2caa0`: `130.010834 -> 132.011002`, nearest `secondary1 +0x12b60`
- Four IOAccelerator candidates were rejected as `zero_start_churn`, confirming the new churn label is useful for noisy fields.
- Twenty-three candidates were stale.
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T221853Z.json`

Deck 2 cache check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2 --expect-bpm 132.0
```

- Current-session Deck 2 cache contained five candidates, all matching:
  - `0x131d8f30c`: `132.000000`
  - `0x135a5dc3c`: `132.000000`
  - `0x135dfc4ec`: `132.000000`
  - `0x127114de8`: `132.000000`
  - `0x10ef2caa0`: `132.011002`

Deck separation with only Deck A moved:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 2 --expect-bpm 132.0 --duration 30 --hz 5
```

- Deck 2 cached candidates stayed fixed while Deck A moved:
  - `0x10ef2caa0`: `132.011002 -> 132.011002`, `stale`
  - `0x127114de8`: `132.000000 -> 132.000000`, `stale`
  - `0x131d8f30c`: `132.000000 -> 132.000000`, `stale`
  - `0x135a5dc3c`: `132.000000 -> 132.000000`, `stale`
  - `0x135dfc4ec`: `132.000000 -> 132.000000`, `stale`
- `Expected BPM mismatches: 0`
- TimecodeLink confirmed Deck B stayed at `132.0` while Deck A moved after the match window. Deck A was observed at `129.4` and then `145.2`; this does not invalidate the separation result because Deck 2 candidates remained stable.

Status:

- Deck 2 rediscovery passed in a realistic incoming-track beatmatch workflow with different starting BPMs.
- Deck 2 cache promotion and current-session cache-check passed after restart.
- Deck 2 separation passed: cached Deck 2 fields did not follow Deck A movement.
- Absolute addresses remain session-local and must not be reused across restarts.

## Session 13 Deck 2 Incoming-Track Attempt With No Observed Pitch Move

Restarted Rekordbox for another Deck 2 incoming-track rediscovery attempt.

New process:

- pid/base: `60143` / `0x1020d0000`
- Previous process was `59202` / `0x104014000`.

Tracks and TimecodeLink baseline:

- Deck A: `Kesha - Blow (CHALANT & Donny`, TimecodeLink `BPM=130.0`.
- Deck B: `Lights On (Control Room Extend`, TimecodeLink `BPM=135.0`.
- Both decks were paused.

Cache invalidation after restart:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2 --expect-bpm 132.0
```

- Deck 2 current-session cached candidates: `0`

Attempted Deck 2 rediscovery expecting Deck B to move from `135.0` to `130.0`:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 2 --expect-bpm 135.0 --expected-after 130.0 --bpm-min 124 --bpm-max 138 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --max-hits-per-region 16 --save-traces
```

- Result: `stale=32`
- No candidates passed.
- Cache was not updated.
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T222332Z.json`

TimecodeLink after the watch:

- Deck A remained `130.0`.
- Deck B remained `135.0` through the validation window.

Follow-up cache check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2 --expect-bpm 130.0
```

- Deck 2 current-session cached candidates: `0`

Status:

- This is an inconclusive operator/window attempt, not Deck 2 negative evidence.
- TimecodeLink did not show the expected Deck B pitch movement during the watch, so stale results are expected.
- Repeat the same Session 13 setup and move only Deck B when the watch prompt appears.

Session 13 rerun in the same process:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 2 --expect-bpm 135.0 --expected-after 130.0 --bpm-min 124 --bpm-max 138 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --max-hits-per-region 16 --save-traces
```

- Five Deck 2 candidates passed and were cached:
  - `0x149f457f8`: `135.000000 -> 130.000000`, nearest `secondary1 +0x68d8`
  - `0x11a1087ac`: `135.000000 -> 130.000000`, nearest `container_dpu2_inner +0x1356a1dc`
  - `0x11a1b4a3c`: `135.000000 -> 130.000000`, nearest `container_dpu2_inner +0x1361646c`
  - `0x11a68e70c`: `135.000000 -> 130.000000`, nearest `container_dpu2_inner +0x13af013c`
  - `0x11a20fa10`: `134.983124 -> 129.983749`, nearest `container_dpu2_inner +0x13671440`
- Four noisy fields were rejected as `zero_start_churn`, including a SQLite field that jumped from `0.0` to `131.450760`.
- Twenty-three candidates were stale.
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T222507Z.json`

Deck 2 cache check after rerun:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2 --expect-bpm 130.0
```

- Current-session Deck 2 cache contained five candidates, all matching:
  - `0x149f457f8`: `130.000000`
  - `0x11a1087ac`: `130.000000`
  - `0x11a1b4a3c`: `130.000000`
  - `0x11a68e70c`: `130.000000`
  - `0x11a20fa10`: `129.983749`

Deck separation with only Deck A moved:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 2 --expect-bpm 130.0 --duration 30 --hz 5
```

- Deck 2 cached candidates stayed fixed while Deck A moved:
  - `0x149f457f8`: `130.000000 -> 130.000000`, `stale`
  - `0x11a1087ac`: `130.000000 -> 130.000000`, `stale`
  - `0x11a1b4a3c`: `130.000000 -> 130.000000`, `stale`
  - `0x11a20fa10`: `129.983749 -> 129.983749`, `stale`
  - `0x11a68e70c`: `130.000000 -> 130.000000`, `stale`
- `Expected BPM mismatches: 0`
- TimecodeLink confirmed Deck B stayed at `130.0` during separation while Deck A moved to `131.3` and later `140.4`.

Status:

- Deck 2 rediscovery passed in the same restarted process after the operator movement was performed.
- Deck 2 cache promotion, current-session cache-check, and deck separation passed.
- The earlier no-move attempt remains useful as evidence that stale-only output correctly fails closed and does not cache.

## Session 14 Deck 1 Incoming-Track Rediscovery Test 1

Restarted Rekordbox for mirrored Deck A incoming-track validation.

New process:

- pid/base: `61382` / `0x102a64000`
- Previous process was `60143` / `0x1020d0000`.

Tracks and TimecodeLink baseline:

- Deck A: `DaBaby - POP DAT THANG - SIDEQ`, TimecodeLink `BPM=139.0`.
- Deck B: `Blow Your Brain Cell (Extended`, TimecodeLink `BPM=132.0`.
- Both decks were paused.

Cache invalidation after restart:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1
```

- Deck 1 current-session cached candidates: `0`

Deck 1 rediscovery while pitching only Deck A from `139.0` to `132.0`:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 139.0 --expected-after 132.0 --bpm-min 124 --bpm-max 145 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --max-hits-per-region 16 --save-traces
```

- Ten Deck 1 candidates passed and were cached:
  - `0x1348109c8`: `139.000000 -> 132.000000`, nearest `secondary1 +0x1b88`
  - `0x1273d1d9c`: `139.000000 -> 132.000000`, nearest `secondary1 -0xd43d0a4`
  - `0x11af4b3cc`: `139.000000 -> 132.000000`, nearest `base +0x184e73cc`
  - `0x11bec742c`: `139.000000 -> 132.000000`, nearest `secondary1 -0x18947a14`
  - `0x134811f10`: `138.969315 -> 131.970856`, nearest `secondary1 +0x30d0`
  - `0x1348120a0`: `138.969315 -> 131.970856`, nearest `secondary1 +0x3260`
  - `0x13481a2c0`: `138.969315 -> 131.970856`, nearest `secondary1 +0xb480`
  - `0x13481b360`: `138.969315 -> 131.970856`, nearest `secondary1 +0xc520`
  - `0x134825f60`: `138.969315 -> 131.970856`, nearest `secondary1 +0x17120`
  - `0x13484ef80`: `138.969315 -> 131.970856`, nearest `secondary1 +0x40140`
- One IOAccelerator candidate was rejected as `zero_end_decay`:
  - `0x1405a6408`: `138.399994 -> 0.000000`
- Twenty-one candidates were stale.
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T222910Z.json`

Deck 1 cache check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1 --expect-bpm 132.0
```

- Current-session Deck 1 cache contained ten candidates, all matching.

Deck separation with only Deck B moved:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 1 --expect-bpm 132.0 --duration 30 --hz 5
```

- All ten Deck 1 cached candidates stayed fixed while Deck B moved.
- `Expected BPM mismatches: 0`
- TimecodeLink confirmed Deck A stayed at `132.0` while Deck B moved to `142.6`.

Status:

- Deck 1 rediscovery passed in a realistic incoming-track workflow after restart.
- Deck 1 cache promotion, current-session cache-check, and deck separation passed.
- Absolute addresses remain session-local and must not be reused across restarts.

## Session 15 Deck 1 Incoming-Track Rediscovery Test 2

Restarted Rekordbox for a second mirrored Deck A incoming-track validation.

New process:

- pid/base: `61977` / `0x1005a8000`
- Previous process was `61382` / `0x102a64000`.

Tracks and TimecodeLink baseline:

- Deck A: `Percolator (Cazes Edit)`, TimecodeLink `BPM=130.0`.
- Deck B: `How Deep Is Your Love x Don't`, TimecodeLink `BPM=128.0`.
- Both decks were paused.

Cache invalidation after restart:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1
```

- Deck 1 current-session cached candidates: `0`

Deck 1 rediscovery while pitching only Deck A from `130.0` to `128.0`:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 130.0 --expected-after 128.0 --bpm-min 124 --bpm-max 134 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --max-hits-per-region 16 --save-traces
```

- Eight Deck 1 candidates passed and were cached:
  - `0x12506800c`: `130.000000 -> 128.000000`, nearest `secondary1 -0xfeb9ea4`
  - `0x11afbfeec`: `130.000000 -> 128.000000`, nearest `secondary1 -0x19f61fc4`
  - `0x11ae13e0c`: `130.000000 -> 128.000000`, nearest `secondary1 -0x1a10e0a4`
  - `0x134f23408`: `130.000000 -> 128.000000`, nearest `secondary1 +0x1558`
  - `0x134f24950`: `130.010834 -> 128.010666`, nearest `secondary1 +0x2aa0`
  - `0x134f24ae0`: `130.010834 -> 128.010666`, nearest `secondary1 +0x2c30`
  - `0x134f623a0`: `130.010834 -> 128.010666`, nearest `secondary1 +0x404f0`
  - `0x134f75060`: `130.010834 -> 128.010666`, nearest `secondary1 +0x531b0`
- Twenty-four candidates were stale.
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T223323Z.json`

Deck 1 cache check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1 --expect-bpm 128.0
```

- Current-session Deck 1 cache contained eight candidates, all matching.

Initial Deck separation attempt:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 1 --expect-bpm 128.0 --duration 30 --hz 5
```

- All eight Deck 1 cached candidates stayed fixed.
- `Expected BPM mismatches: 0`
- TimecodeLink did not show Deck B moving during the monitor window; Deck A and Deck B both remained `128.0`.

Aborted rerun:

- A second monitor attempt was started, but the operator reported Deck B was not moved.
- The attempt was interrupted with `KeyboardInterrupt` before completion and produced no usable result.

Deck separation rerun with only Deck B moved:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 1 --expect-bpm 128.0 --duration 30 --hz 5
```

- All eight Deck 1 cached candidates stayed fixed while Deck B moved:
  - `0x134f23408`: `128.000000 -> 128.000000`, `stale`
  - `0x134f24950`: `128.010666 -> 128.010666`, `stale`
  - `0x134f24ae0`: `128.010666 -> 128.010666`, `stale`
  - `0x134f623a0`: `128.010666 -> 128.010666`, `stale`
  - `0x134f75060`: `128.010666 -> 128.010666`, `stale`
  - `0x12506800c`: `128.000000 -> 128.000000`, `stale`
  - `0x11afbfeec`: `128.000000 -> 128.000000`, `stale`
  - `0x11ae13e0c`: `128.000000 -> 128.000000`, `stale`
- `Expected BPM mismatches: 0`
- TimecodeLink confirmed Deck A stayed at `128.0` while Deck B moved to `137.0` and later `131.8`.

Status:

- Deck 1 rediscovery, cache promotion, and current-session cache-check passed after restart.
- Deck separation passed after rerun with Deck B movement.
- The initial no-move monitor remains documented as inconclusive; it did not affect the cached candidate set.

## Session 16 All-Inclusive DJ Workflow Restart Test

Restarted Rekordbox for one combined workflow run proving both incoming-deck
directions in a single pid/base.

New process:

- pid/base: `63036` / `0x102458000`
- Previous process was `61977` / `0x1005a8000`.

Tracks and TimecodeLink baseline:

- Deck A: `Blow Your Brain Cell (Extended`, TimecodeLink `BPM=132.0`.
- Deck B: `Rude Boy (Cazes Edit)`, TimecodeLink `BPM=126.0`.
- Both decks were paused.

Cache invalidation after restart:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2
```

- Deck 1 current-session cached candidates: `0`
- Deck 2 current-session cached candidates: `0`

### Deck 2 incoming half

Deck 2 rediscovery while pitching only Deck B from `126.0` to `132.0`:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 2 --expect-bpm 126.0 --expected-after 132.0 --bpm-min 122 --bpm-max 136 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --max-hits-per-region 16 --save-traces
```

- Eight Deck 2 candidates passed and were cached:
  - `0x1274d3c9c`: `126.000000 -> 132.000000`, nearest `container -0x13268fa4`
  - `0x1274108ec`: `126.000000 -> 132.000000`, nearest `container -0x1332c354`
  - `0x1268c5aec`: `126.000000 -> 132.000000`, nearest `container -0x13e77154`
  - `0x13a744b08`: `126.000000 -> 132.000000`, nearest `secondary1 +0x69e8`
  - `0x13a746050`: `125.984253 -> 131.983505`, nearest `secondary1 +0x7f30`
  - `0x13a7461e0`: `125.984253 -> 131.983505`, nearest `secondary1 +0x80c0`
  - `0x13a78ef60`: `125.984253 -> 131.983505`, nearest `secondary1 +0x50e40`
  - `0x13a78f0f0`: `125.984253 -> 131.983505`, nearest `secondary1 +0x50fd0`
- Twenty-four candidates were stale.
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T223911Z.json`

Deck 2 cache check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2 --expect-bpm 132.0
```

- Current-session Deck 2 cache contained eight candidates, all matching.

Deck 2 separation with only Deck A moved:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 2 --expect-bpm 132.0 --duration 30 --hz 5
```

- All eight Deck 2 cached candidates stayed fixed while Deck A moved.
- `Expected BPM mismatches: 0`
- TimecodeLink confirmed Deck B stayed at `132.0` while Deck A moved to `138.6`.

### Deck 1 incoming half

Deck 1 rediscovery while pitching only Deck A from `138.6` to `132.0`:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm 138.6 --expected-after 132.0 --bpm-min 126 --bpm-max 142 --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --max-hits-per-region 16 --save-traces
```

- Nine Deck 1 candidates passed and were cached:
  - `0x12aa2cd7c`: `138.600006 -> 132.000000`, nearest `container -0xfd0fec4`
  - `0x126ce353c`: `138.600006 -> 132.000000`, nearest `container -0x13a59704`
  - `0x11c0ee85c`: `138.600006 -> 132.000000`, nearest `base +0x19c9685c`
  - `0x13a740148`: `138.599991 -> 132.000000`, nearest `secondary1 +0x2028`
  - `0x13a741690`: `138.613861 -> 132.013199`, nearest `secondary1 +0x3570`
  - `0x13a741820`: `138.613861 -> 132.013199`, nearest `secondary1 +0x3700`
  - `0x1276e0dc0`: `138.613861 -> 132.013199`, nearest `container -0x1305be80`
  - `0x1276e0810`: `138.613861 -> 132.013199`, nearest `container -0x1305c430`
  - `0x1276b3ee0`: `138.613861 -> 132.013199`, nearest `container -0x13088d60`
- One IOAccelerator candidate was rejected as `zero_end_decay`.
- Twenty-two candidates were stale.
- Trace saved:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T224110Z.json`

Deck 1 cache check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1 --expect-bpm 132.0
```

- Current-session Deck 1 cache contained nine candidates, all matching.

Deck 1 separation with only Deck B moved:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 1 --expect-bpm 132.0 --duration 30 --hz 5
```

- All nine Deck 1 cached candidates stayed fixed while Deck B moved.
- `Expected BPM mismatches: 0`
- TimecodeLink confirmed Deck A stayed at `132.0` while Deck B moved to `154.7`.

Status:

- Both Deck 2 and Deck 1 rediscovery passed in one restarted process.
- Both decks had current-session cache promotion and cache-check success.
- Both deck-separation checks passed with the opposite deck moved.
- This is the strongest single-session DJ workflow evidence so far.
- Absolute addresses remain session-local and must not be reused across restarts.

## Working Conclusions

- Rekordbox appears to keep live/displayed BPM as float32 values in readable memory.
- Deck 1 has strong evidence as of Session 11: current-session pass/cache/separation in Session 8, restart invalidation/rediscovery/recache/cache-check/separation in Sessions 9-10, and opposite-direction restart rediscovery/separation in Session 11.
- Deck 2 live fields can be found by broad read/write scans and pitch-watch validation across repeated restarts. Current-session cache invalidation and promotion were validated in Sessions 5, 6, and 12.
- Session 12 adds realistic incoming-track evidence for Deck 2: Deck A held at `132.0`, Deck B loaded at `130.0`, Deck B was pitched to `132.0`, cached, and then shown not to follow Deck A movement.
- Deck 2 is not yet tied to a reliable structural anchor; the current usable approach is scan/watch/cache for the current Rekordbox pid/base.
- Duplicate BPM values are common; exact match alone is not meaningful.
- A usable bridge field must be selected by temporal behavior and deck separation, not by one-time value equality.
- Beatmatched decks are not an edge case for DJ use. Equal or near-equal Deck A/Deck B BPM must be treated as a required ownership test because most live workflows intentionally match deck BPMs, often after only a short unequal-BPM window while loading and pitching the incoming track.
- The monitor/trace modes improve evidence quality and remain useful for future
  candidate investigations.
- Bridge runtime integration must remain fail closed; no absolute address or
  single offset is stable enough to hardcode.
- Default V1 implementation keeps active autoloops on the BPM snapshot taken at
  arm time. V2 live-follow is explicit opt-in and treats SoundSwitch BPM sends
  as phrase-boundary controlled autoloop rearms.

## Next Restart Procedure

After Rekordbox restart and tracks loaded on Deck 1 and Deck 2:

1. Read TimecodeLink baseline BPMs and track names:

```bash
tail -n 80 "$HOME/Library/Application Support/TimecodeLink/timecodelink.log"
```

2. Snapshot Deck 1 around anchors:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm snapshot --deck 1 --mode bpm --expect-bpm <deck1_bpm> --window 0x10000 --limit 80
```

3. Snapshot Deck 2 with bounded broad scan:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm snapshot --deck 2 --expect-bpm <deck2_bpm> --library-bpm <deck2_library_bpm> --mode bpm --bpm-min <min> --bpm-max <max> --window 0x10000 --include-rw-regions --max-rw-region 0x400000 --max-rw-total 0x10000000 --max-hits-per-region 20 --limit 80
```

4. Pitch one deck at a time and watch top candidates. When testing Deck 1, monitor cached Deck 2 candidates if they exist:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm <before> --expected-after <after> --include-rw-regions --watch-limit 32 --duration 30 --hz 5 --monitor-cache-deck 2 --save-traces
```

5. If no scan candidates are plausible but cached candidates exist for the other deck, run a stability-only separation check:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-monitor --deck 2 --expect-bpm <deck2_bpm> --duration 30 --hz 5
```

6. Promote only fields that move immediately with the correct deck, reject stale duplicates/churn, and record address, region, anchor delta, expected BPM, observed sequence, zero-start/zero-end flags, discontinuity count, and whether the field was available before arm.
