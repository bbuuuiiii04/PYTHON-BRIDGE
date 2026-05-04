# Live BPM Memory Findings

Date: 2026-05-04
Target: Rekordbox 7.2.11 on macOS, DDJ-800, rb_ss_bridge_v2
Scope: read-only memory investigation only. No bridge runtime behavior has been changed.

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
- marks candidates as `pass`, `moved_unverified`, `moved_wrong_value`, `stale`, or `read_error`;
- writes passed candidates to `~/.cache/rb_ss_bridge_v2/live_bpm_candidates.json` only when `--expected-after` is supplied and the final watched value is within tolerance;
- leaves bridge runtime behavior unchanged.

`cache-check` reuses only candidates cached for the current Rekordbox pid, base address, and deck. It is intended as a fast same-process sanity check before deciding whether another broad scan is needed.

Pure validation logic has lightweight unit coverage:

```bash
python3 -m unittest discover -s tests
```

These tests cover verdict classification, render-cache ranking penalties, and current-session cache filtering. They do not attach to Rekordbox or prove any address live; live address proof still requires controlled `validate`/`watch` runs.

Important: all absolute addresses below are session-local evidence. Do not integrate any hardcoded address or single fixed offset into the bridge.

## Acceptance Status

Not accepted for bridge integration yet.

Current evidence proves that Rekordbox exposes live/displayed BPM-like float32 values that update with pitch before or during arm-relevant windows. It does not yet prove a stable rediscovery route for Deck 2, and Deck 1's offset from `secondary1` shifted across restart.

Acceptance blockers:

- Need a deterministic per-deck rediscovery strategy, not absolute addresses.
- Need Deck 2 structural anchoring or a production-grade scan/ranking rule that separates live Deck 2 from duplicate stale/cache fields.
- Need Deck 1 rediscovery and cache validation to match the Deck 2 evidence level.
- Need proof that selected fields are available before SoundSwitch autoloop arm and do not arrive late like ENGINE STATE.

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

## Working Conclusions

- Rekordbox appears to keep live/displayed BPM as float32 values in readable memory.
- Deck 1 has shown promising anchor-adjacent fields in Sessions 1-3, but Session 4 rejected the two known offsets by staying `0.0`, and Session 7 did not produce a cacheable candidate.
- Deck 2 live fields can be found by broad read/write scans and pitch-watch validation across repeated restarts. Current-session cache invalidation and promotion were validated in Sessions 5 and 6.
- Deck 2 is not yet tied to a reliable structural anchor; the current usable approach is scan/watch/cache for the current Rekordbox pid/base.
- Duplicate BPM values are common; exact match alone is not meaningful.
- A usable bridge field must be selected by temporal behavior and deck separation, not by one-time value equality.
- Beatmatched decks are not an edge case for DJ use. Equal or near-equal Deck A/Deck B BPM must be treated as a required ownership test because most live workflows intentionally match deck BPMs, often after only a short unequal-BPM window while loading and pitching the incoming track.
- Six sessions are enough for Deck 2 restart evidence. More Deck 2 restarts are lower value than Deck 1 parity testing and a guarded prototype design.

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

4. Pitch one deck at a time and watch top candidates:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm watch --deck 2 --type f32 --duration 25 --hz 5 --addr 0xADDR1 --addr 0xADDR2 --addr 0xADDR3
```

5. Promote only fields that move immediately with the correct deck, reject stale duplicates, and record address, region, anchor delta, expected BPM, observed sequence, and whether the field was available before arm.
