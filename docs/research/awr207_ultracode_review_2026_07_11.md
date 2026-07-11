---
doc_status: current
truth_level: review
last_verified_commit: 85cb8ea
last_verified_date: 2026-07-11
validation_scope: >
  Independent adversarial (ultracode) review of AWR-207 USB-export track
  resolution (local-twin beatgrid match + local-ANLZ phrase handoff). Reviews
  every commit 38e127a..85cb8ea touching filepath_resolver.py, state_manager.py,
  and tests. Read-only; the live bridge main loop was not running (only pad
  servers/menubar). Software-inspection + one read-only DB timing run; no
  live-hardware or live-load evidence.
---

# AWR-207 Ultracode Adversarial Review — USB-export track resolution

**Reviewer lane:** independent, zero-deference (builder was a GPT/Codex seat).
**Diff reviewed:** `git 38e127a..85cb8ea` — `filepath_resolver.py` (+213/-38),
`state_manager.py` (+5/-2), `tests/test_filepath_resolver_usb_twin.py` (+155 new),
`tests/test_smart_transitions.py` (+30), plus docs/contracts.

## VERDICT: PASS-with-required-fixes

The design is sound and the production wiring is correct **by inspection** —
every hop from the USB `ANLZ_PATH` event to a real-marker `ANLZ_DATA` emission
routes through production code, local resolution is byte-identical, and the
match fails closed. Two things keep it off a clean PASS: (1) there is **no
executed end-to-end proof** that phrase markers actually populate through the
real chain — every test mocks the seams, and the AWR-206 lesson is precisely
that seam-reachability ≠ runtime proof; and (2) a trivial early-worker race and
a measured scripted-entry timing window that the operator must weigh. None are
blockers; all are cheap to close.

Plain-language summary: **the machine is built right and wired right, but nobody
has yet watched a real USB track light up end-to-end.** Until that happens (a
live load or one production-path integration test), "USB tracks light like local
tracks" is confirmed-by-reading, not confirmed-by-running.

---

## Required before the operator relies on it

- **R1 — Prove phrase flows end-to-end by execution, not inspection.** All five
  resolver unit tests and the one `state_manager` test mock `_start_anlz_worker`
  / `_extract_beatgrid_from_anlz` / `Rekordbox6Database`. None drive the real
  chain `ANLZ_PATH → _on_track_loaded → resolve_by_anlz → _db_lookup_by_anlz →
  FILEPATH_RESOLVED → _on_filepath_resolved → _start_anlz_worker(local) →
  read_anlz_drops → ANLZ_DATA(real markers)`. Gold standard: a live USB load
  showing `phrase != "other"` in the heartbeat, or an integration test that
  feeds a real (or fixture) local `.EXT`-bearing ANLZ through `_read_runtime_anlz_data`
  and asserts non-empty `drop_beat_indices`. **[required]**
- **R2 — Skip the early TRACK_LOADED ANLZ worker for device-export paths**
  (`state_manager.py:2258-2264`). For a USB path it reads an ANLZ with no PSSI,
  produces empty phrase markers, and creates the (narrow) clobber race in
  Finding 1 — pure loss, no gain. One-line guard:
  `if self._smart_rearm_experiment and not _is_device_export_anlz_path(anlz_path):`.
  Cheap, removes wasted I/O and the race. **[required, trivial]**

## Operator decision (not a code defect)

- **F2 timing** below is a real widening of already-accepted local behavior. It
  needs your judgment on whether ~3.4 s worst-case matters for how you bring
  tracks in, not a mandatory fix.

---

## Surface-by-surface findings

### Surface 1 — Reachability (the AWR-206 lesson)

**[confirmed] The twin-match + `local_anlz_path` path is wired through real
production code, hop by hop:**

1. Reader emits `ANLZ_PATH` before `TRACK_LOADED` (`rb_state_reader.py:408`;
   invariant intact).
2. `state_manager.py:1493` stores it in `_pending_anlz_path[deck]`.
3. `_on_track_loaded` pops it and calls `resolve_by_anlz(deck, load_gen, path)`
   (`state_manager.py:2252-2255`).
4. `resolve_by_anlz` spawns the `anlz-d{deck}` daemon thread →
   `_db_lookup_by_anlz` (`filepath_resolver.py:513-522`).
5. UUID substring match misses for the USB device id (uppercase `000086A0`
   is not a substring of any lowercase local UUID path — case-sensitive `in`),
   so `if device_export:` (`filepath_resolver.py:439`) is entered and the twin
   match runs, returning a payload with `local_anlz_path`
   (`filepath_resolver.py:440-461`).
6. Worker publishes `FILEPATH_RESOLVED` with that payload
   (`filepath_resolver.py:532`).
7. `_on_filepath_resolved` sets `resolved_anlz_path = payload.get("local_anlz_path")
   or anlz_path` and schedules `_start_anlz_worker(resolved_anlz_path, …)`
   (`state_manager.py:2552-2574`).
8. `_start_anlz_worker` → `_read_runtime_anlz_data(local_path)` →
   `read_anlz_drops(local_path)` → `_candidate_anlz_paths` resolves the local
   `.EXT`/`.2EX` siblings (`anlz_reader.py:169,194`), so PSSI phrase parses from
   the local twin.
9. `ANLZ_DATA` consumer sets `meta.anlz_drops`/`smart_drops`/… (`state_manager.py:1548-1555`).

**[confirmed] The builder's desk validation** (content `39964930` resolved from
mounted USB `000086A0`) proves step 5. My read-only run independently confirms
`_local_anlz_path(AnalysisDataPath)` reconstructs **paths that exist and parse**
(candidate ANLZ reads succeeded at ~6 ms each), so the relative-`AnalysisDataPath`
assumption holds for this DB.

**[unknown] What is NOT proven:** steps 7-9 have never executed against a real
local `.EXT` — there is no evidence that `read_anlz_drops(local_twin)` actually
returned non-empty phrase markers for a USB load. This is exactly the AWR-206
trap. → **R1.**

### Surface 2 — Does phrase actually flow?

**[confirmed] The mechanism is correct:** the resolved worker runs against the
LOCAL twin's ANLZ, and `read_anlz_drops` pulls PSSI from the local `.EXT` sibling
(`anlz_reader.py:203` `_extract_pssi_phrases`, fed by `_candidate_anlz_paths`).
So identity alone is not relied on — the phrase parse consumes the local file,
per Tasks 1b/1c.

**[confirmed, Finding 1 — arbitration race, LOW-MED severity]** Two workers emit
`ANLZ_DATA` with the **same `load_gen`** for a USB track, and they now
**disagree**:
- Early worker (`state_manager.py:2259`, raw USB path, `source="anlz"`) →
  empty phrase (USB has no PSSI).
- Resolved worker (`state_manager.py:2570`, local twin, `source="anlz_spectral"`)
  → real phrase.

The consumer's rule `can_update = event_source == "anlz" or existing_markers_empty`
(`state_manager.py:1512`) means the early `"anlz"` read can **overwrite non-empty
markers** if it is processed *after* the resolved read. The design comment at
`state_manager.py:1556-1558` literally assumes "markers usually match the earlier
fast read" — true for local, **false for USB**. This is a real latent clobber.

**Severity is LOW-MED, not a blocker, because timing gives the early worker a
huge head start:** the resolved worker cannot start until `FILEPATH_RESOLVED`,
which my measurement shows is ~2-3.4 s after `TRACK_LOADED` (Surface 7b). The
early worker's tiny USB read (~6 ms) is enqueued long before. The clobber
requires the early worker's thread to be starved on `_anlz_extract_gate`
(`BoundedSemaphore(2)`, `state_manager.py:2297`) for the entire ~2-3 s window —
only possible under sustained 2-deck+ simultaneous-load contention, and the
semaphore is not FIFO. Rare in the operator's 2-deck fader/EQ style, but it is a
**silent** phrase-loss when it hits — the exact symptom AWR-207 exists to cure. →
**R2** removes it outright and deletes a useless read.

### Surface 3 — False-match risk

**[confirmed] Fail-closed structure is correct:** `_unique_usb_twin`
(`filepath_resolver.py:315-323`) returns the match only when **exactly one**
candidate passes; 0 or 2+ → `None`. Tests pin this
(`test_unique_match_and_ambiguous_fail_closed`).

**[confirmed, Finding 3 — discrimination is weaker than it looks, LOW severity
in scope]** `_beatgrid_fingerprint` is a SHA-256 of the raw float64 beat times
(`spectral_cache.py:331-334`), and `_beatgrids_match` (`filepath_resolver.py:249-274`)
otherwise checks first-beat ±10 ms + 17 sampled points ±10 ms. For **constant-tempo
EDM** (the operator's corpus), a beatgrid is fully determined by
`(first_beat, bpm, beat_count)` — the 17 sample points carry **no independent
information**, and two different 128-BPM tracks with the same first-beat offset
(±10 ms) and same length in beats (±1) produce an **identical fingerprint**. So
the real discriminators are just `bpm ±0.05` (prefilter), `first_beat ±10 ms`,
and `count ±1`. My DB run shows **222 tracks at 128 BPM** — the collision space
is not empty.

**Why it is still safe within AWR-207 scope:** when the true twin is present
(the spec's stated assumption — the export came from this library), any
same-grid collision produces **≥2 matches → ambiguous → None** (degraded-honest,
never a wrong identity). The only path to a *wrong* identity is **true twin
absent + exactly one coincidental collision** — i.e. a guest/foreign stick, which
is explicitly AWR-208's E3/E4 scope, not AWR-207. **[assumed]** the operator's
USB tracks generally have local twins; the ambiguity guard is the real safety net
and it only protects when the twin is co-present.

**[assumed, Finding 4 — recall risk, LOW, fail-closed direction]** The prefilter
(`_usb_twin_prefilter`, `filepath_resolver.py:277-311`) uses the USB grid's
**last beat time** (`times[-1]/1000`) as the duration proxy versus DB `Length`
(±2 s), and `statistics.median(beatgrid_bpms)` versus stored BPM (±0.05). Both
can **reject a true twin** (→ `usb-twin-miss` → degraded-honest, never wrong):
- if the local beatgrid stops >2 s before track end (long outro/ambient tail),
  `abs(last_beat − Length) > 2 s`;
- if a variable-tempo track's median beat-BPM differs from the single stored BPM
  by >0.05.
This costs *recall*, not correctness. The builder proved one track resolves;
**generalization across the whole catalog (an operator mandate) is unproven** and
is what the next USB session actually gates.

### Surface 4 — Local regression

**[confirmed] Clean — byte-identical behavior for local UUID loads.**
- `_is_device_export_anlz_path` returns `False` for local UUID paths
  (`test_device_detection_excludes_local_uuid_paths`), so the entire
  `if device_export:` block is skipped.
- The refactor into `_payload_for_content` (`filepath_resolver.py:366-401`)
  preserves every field, order, and the laser-tag exception handling; `local`
  loads carry **no** `local_anlz_path` key.
- `state_manager.py:2552-2553`: `payload.get("local_anlz_path") or anlz_path` →
  for local, `None or anlz_path` → the same path passed today; `str()` on a str
  is a no-op. `test_usb_twin_payload_matches_local_payload_plus_local_anlz_path`
  proves the USB payload equals the local payload plus the one extra key.
- **load_gen arbitration is unchanged in code** (only the path argument to
  `_start_anlz_worker` changed; deck/gen untouched). Finding 1 is an *assumption*
  the arbitration now violates for USB, not a code change to arbitration.

### Surface 5 — Performance

**[confirmed] No push-loop risk, no whole-library ANLZ sweep.** All new I/O
(`_db_lookup_by_anlz`, prefilter, candidate ANLZ reads) runs in the existing
`anlz-d{deck}` daemon thread (`filepath_resolver.py:515-521`). The twin path
reads only prefiltered candidates' ANLZ files, DB prefilter first
(`filepath_resolver.py:440-448`).

**[confirmed] The earlier "local materialization regression" concern is
withdrawn.** The code changed `for c in db.get_content()` to
`contents = list(db.get_content())`. My run shows `get_content()` is already
effectively eager (~1.9 s to materialize 2054 rows regardless), so the explicit
`list()` adds negligible cost and local latency is unchanged.

**[confirmed, Finding 5 — no per-session memo, NOTE]** The spec allowed (didn't
require) an in-process `usb-path→content_id` memo. None was implemented, so every
USB load re-pays the full lookup (see 7b timing). Daemon-thread only; an
optimization opportunity, not a defect.

### Surface 6 — Seam extensibility (AWR-208 readiness)

**[confirmed] Met.** The `FILEPATH_RESOLVED` payload carries `local_anlz_path` as
a plain optional string, and the consumer
(`state_manager.py:2552`) treats it **source-agnostically** —
`payload.get("local_anlz_path") or anlz_path`. A future AWR-208 stick-sidecar
source that produces the same payload shape with `local_anlz_path` populated
flows through the identical `_start_anlz_worker` path with **zero** state_manager
change. The contract addition (`change_contracts.yml`) documents the field. No
redesign needed to admit a second source.

### Surface 7 — Scripted tracks from USB (operator mandate)

**(a) SSID + scripted engagement — [confirmed] works identically to local.**
The twin payload is built by the same `_payload_for_content`, so
`soundswitch_id = _read_soundswitch_id(content.FolderPath)` reads the tag from the
**local twin's** audio file (`filepath_resolver.py:391`) exactly as a local load.
Downstream, `_on_filepath_resolved` resolves `scripted_id` from `meta.soundswitch_id`
/ `meta.filepath` (twin's local values) and emits `SCRIPTED_ARM`
(`state_manager.py:2576-2621`). `_update_lighting` then sees `scripted_id and
is_playing → "scripted"` (`state_manager.py:3278`). Scripted mode engages the
same as local. **[assumed]** the local twin's audio file carries the
`soundswitch_id` tag (true if SS scripts were authored against the local library).

**(b) Timing — [confirmed, Finding 2 — MEDIUM, operator judgment] a scripted USB
track CAN start in autoloop before flipping to scripted.** `_update_lighting`
runs every tick and derives mode purely from `scripted_id + is_playing`
(`state_manager.py:3278-3283`). At load, `scripted_id = 0` (`state_manager.py:2218`),
so a *playing* deck renders **autoloop** until `FILEPATH_RESOLVED` sets
`scripted_id`, then flips to scripted on the next tick.

Measured worst-case `TRACK_LOADED → FILEPATH_RESOLVED` latency for USB (read-only
run, this DB):

| Component | Cost |
|---|---|
| `Rekordbox6Database(unlock=True)` open | 0.16 s |
| `list(db.get_content())` (2054 tracks, full — UUID miss, no early exit) | **1.91 s** |
| prefilter (in-memory) | ~0 |
| candidate ANLZ reads — up to ~40 of the 222 128-BPM tracks after ±2 s filter, ~6 ms each | ~0.24-1.3 s |
| **USB total** | **~2.3-3.4 s** |

Local pays open + the same ~1.9 s `get_content` (it's eager) but **not** the
candidate reads, so local's autoloop→scripted window is already ~2 s — accepted
behavior today. **AWR-207 widens it by the ~0.24-1.3 s candidate-read time.** If
the operator load-then-plays (beatmatch/cue before bringing a track in), the
resolve finishes before the track is audible — no visible flash. If he
**instant-plays or instant-doubles a scripted USB track at its drop**, up to
~3.4 s of that drop can render in autoloop before scripted takes over. That is a
real, visible wrong-mode window, wider than local. Mitigation: the spec-sanctioned
per-session memo would erase the repeat-load cost (not the first load); the ~1.9 s
`get_content` dominates and is inherent/shared with local.

**(c) Stale scripted state on ambiguous/unresolved USB — [confirmed] SAFE, no
stale state.** When the twin match returns `None`, `_resolve_anlz_worker` skips
lsof and returns **without** publishing `FILEPATH_RESOLVED`
(`filepath_resolver.py:535-543`), so no `SCRIPTED_CLEAR` is emitted. That does
**not** leave the previous scripted show running, because:
- `_on_track_loaded` zeroes `d.scripted_id = 0` **synchronously at load**
  (`state_manager.py:2218`), before any resolution; and
- `_update_lighting` is **fully state-derived every tick, not event-driven** —
  its own docstring: "missed events cannot leave SS in a stale mode"
  (`state_manager.py:3273-3274`). With `scripted_id = 0` and the deck playing, it
  derives `desired = "autoloop"` and, if the prior mode was `"scripted"`,
  transitions scripted→autoloop and sends the fresh autoloop selection to SS
  (`state_manager.py:3297-3307`), tearing down the stale look. Autoloop arming
  needs only `is_playing` + BPM (from the direct/live BPM reader), **not**
  resolution.

So AWR-207's skip-lsof — even though it removed the `SCRIPTED_CLEAR` that the old
(buggy) lsof path used to emit — cannot leave a stale scripted look, because the
lighting mode is re-derived from state, not from the missing event. An unresolved
USB track after a scripted track runs **autoloop** (degraded-honest), which is the
intended outcome.

---

## Verification I actually ran

- **[confirmed]** `python3 -m unittest rb_ss_bridge_v2.tests.test_filepath_resolver_usb_twin
  rb_ss_bridge_v2.tests.test_smart_transitions` → **108 tests OK**.
- **[confirmed]** Read-only DB timing run (bridge main loop not running): open
  0.16 s, `get_content` 1.91 s, 2054 contents, 222 at 128 BPM, per-candidate ANLZ
  read ~6 ms, and `_local_anlz_path` reconstructions exist + parse.
- **[assumed, not re-run by me]** the builder's "187 focused / full 4359 baseline
  reconciled" claim.
- **[confirmed]** bridge main loop (`python3 -m rb_ss_bridge_v2`) is **not** among
  the running processes — only `led_pad`/`laser_pad`/`bridge_menubar`; my read-only
  DB open did not race the live resolver.

## Bottom line

Ship-ready in design and wiring; **not yet proven by running.** Close R1 (one
live load or one production-path integration test) and R2 (one-line early-worker
guard), then decide whether the Finding-2 timing window matters for your load
style. Everything else — local regression, fail-closed matching, scripted
engagement, no-stale-scripted, AWR-208 seam — checks out with evidence above.
