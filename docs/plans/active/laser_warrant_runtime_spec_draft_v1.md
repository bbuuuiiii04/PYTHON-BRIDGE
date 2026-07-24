---
doc_status: draft
truth_level: >
  DRAFT implementation spec — pending the vetted list (operator veto pass not
  yet run) + operator veto-mode confirmation. NO code has changed. Not an
  implementation authorization: implementation channel is Codex or a
  sanctioned Claude seat AFTER exec review + operator activation — never the
  authoring seat.
last_verified_commit: e76cbbf0
last_verified_date: 2026-07-24
validation_scope: >
  Spec only. Every [confirmed] claim was read in current code at e76cbbf0 by
  the RTSPEC authoring seat on 2026-07-24 (file:line cited). SOFTWARE-VALIDATED
  ONLY / HARDWARE-UNVALIDATED applies to the whole repo and everything here.
---

# Codex Implementation Spec — Laser-warrant vetted spans: artifact + runtime wiring (DRAFT v1)

Status: **DRAFT — pending vetted list + operator veto-mode confirmation.**
Two deliverables in one spec: (1) the bridge-consumable **vetted-spans
artifact** built from the operator's veto pass over the laser-warrant ranked
list, and (2) the **runtime wiring** that lets lasers fire (or be permitted)
when the playhead enters a vetted span — strictly UNDER every existing laser
precedence, fail-open, and byte-identical to today when no artifact exists.

Plain meaning first: the offline program produced a ranked list of "growl"
moments where lasers are probably justified. Brandon vetoes the wrong rows
(silence is a pass). The rows that survive become a small JSON file the bridge
reads. When a playing track reaches one of those moments, the laser layer gets
a low-priority "this moment is warranted" signal. Everything that protects the
show today — blackouts, emergency, drop policy, scripted mode — still wins.
If the file is missing, wrong, or stale, the bridge behaves exactly as it does
today. A warrant failure can only ever mean *fewer extra laser moments*, never
a dark or wrong show.

---

## Part A — Context & root cause (verified; read, do not implement)

### A.1 The offline side (what exists today)

- [confirmed] The ranked-list machinery is sealed at
  `local/spectral_v5_2026_07_17/laser_warrant_v1/` (MANIFEST.json pins runner
  + fixtures + `cid_title_map.json`; spec =
  `local/spectral_v5_2026_07_17/laser_warrant_list_spec_v3.md`, sha
  `6e40100f…`). `results/` are regenerable outputs, not frozen, and are NOT
  currently on disk (verified 2026-07-24: no `results/` under the package
  dir). The row count of the delivered batches (~161 rows per the exec4
  handoff) is therefore [assumed] here; the deterministic double-run
  (spec v3 §E.1) makes regeneration byte-reproducible.
- [confirmed] Row schema, from the frozen runner
  (`laser_warrant_v1/laser_warrant_v1.py:364-381`): each rendered row carries
  `content_id` (64-hex sha256 of the audio file bytes), `title`,
  `beat_span [start,end)` (beatgrid indices), `seconds_span`
  (`beatgrid_times_ms[b]/1000.0`, rounded to 3 dp), `peak_similarity`,
  `argmax_exemplar` (Q1/P2/P3), `flags` (`ATYPICAL`, `WARRANT-DOUBT`),
  `recurrence {member_count, recurs_at_beats, recurs_at_mmss}`, `mmss_span`.
- [confirmed] `ranked_events.json` persists ONLY the rendered rows (head
  event span + recurrence anchor beats) — member events' full spans are not
  written (`laser_warrant_v1.py:449-455` writes `event_rows` only). So a
  passed recurrence row's member spans must be recovered by re-running the
  frozen runner (deterministic) at artifact-build time, or approximated as
  `[anchor, anchor+8)` from `recurs_at_beats`. This spec chooses the re-run
  (exact spans; convex-hull absorption per spec v3 §C.5 means member spans
  can exceed 8 beats).
- [confirmed] Veto ingestion is designated append-only with its own round
  (spec v3 §E.5): "operator vetoes are append-only artifacts; sealed corpus
  files are never edited."
- [confirmed] Title-map precedent for offline identity joins:
  `build_cid_title_map.py` sha256-hashes library audio files and joins to a
  scratch COPY of the rekordbox master.db (never the live db), per the
  `stage2_sweep_resolve.py` precedent cited in spec v3 §B.4.

### A.2 The runtime side (how the bridge identifies a loaded track at HEAD)

This is the join problem: **the artifact is keyed by sha256-of-audio-bytes;
the bridge does not know that hash at runtime.**

- [confirmed] The bridge's `meta.content_id` is the **rekordbox master.db
  ContentID** (a numeric DB id as string), not a hash:
  `filepath_resolver.py:858` (`content_id = str(content.ID)`) and
  `filepath_resolver.py:1030`. It reaches `DeckState.meta` via the
  `FILEPATH_RESOLVED` event (`state_manager.py:2573`,
  `meta.content_id = payload["content_id"]`).
- [confirmed] `meta.filepath` is the master.db `FolderPath` — the LOCAL
  library audio path (`filepath_resolver.py:856`).
- [confirmed] USB loads resolve back to the **local twin** in master.db: the
  device-export path runs `_unique_usb_twin` beatgrid fingerprint matching
  and, on a unique match, builds the payload from the LOCAL content row
  (`filepath_resolver.py:911-933`, log `[FRES] usb-twin-match`). So on both
  local and successful-twin USB loads, `meta.content_id` and `meta.filepath`
  are the local library's values — the same library the offline build hashed.
  On twin miss/ambiguity there is no local identity ([confirmed] log paths at
  `filepath_resolver.py:934-938`) → no warrant spans for that load
  (fail-open, today's behavior).
- [confirmed] No runtime audio-bytes sha256 exists anywhere:
  `spectral_cache.py:337-352` keys its cache by
  sha1(realpath, mtime_ns, size, beatgrid-fingerprint) — file *stats*, not
  file *bytes*. Computing a true sha256 at load would re-read the whole audio
  file even on spectral-cache hits.
- [confirmed] Track-position/beat state available per push tick:
  `LaserContext` carries `elapsed_ms`, `abs_beat`, `beatpos`
  (`laser_models.py:122-149`), built purely from push-tick locals at
  `state_manager.py:5365-5384` ("Must not call … read files … or perform any
  I/O", `state_manager.py:5335-5338`).
- [assumed] `elapsed_ms` is track-file-timeline position (the same timeline
  as `beatgrid_times_ms`, hence pitch-fader-invariant): strong evidence is
  that beat interpolation and `first_beat_ms` both work off
  `beatgrid_times_ms` against elapsed (`filepath_resolver.py:859`), but the
  implementer must re-verify at the wiring site before relying on it.
- [confirmed] The sanctioned off-push-loop pattern for per-track-load work:
  `StateManager._start_anlz_worker` (`state_manager.py:2325-2411`) — daemon
  worker thread, `load_gen` staleness guard on both entry
  (`state_manager.py:2355-2356`) and consumption, result re-injected as a
  `BridgeEvent` via `eq.put_nowait`. The consumer-side `load_gen` guard
  pattern is `state_manager.py:1513-1517` (`ANLZ_DATA`). `ANLZ_PATH` itself
  fires before `TRACK_LOADED` (`models.py:295`; AGENTS.md §6).

### A.3 Where the laser layer decides (the precedence ladder at HEAD)

- [confirmed] `LaserDirector._decide` ladder (`laser_director.py:367-676`):
  priority 1 `emergency` (:375), 2 `manual_override` (:386), 3 `not_playing`
  (:400), 4 `idle_no_track` (:412), 5 `position_stale` (:424), 6 `scripted`
  (:436), 7 `autoloop_not_ready` (+`blackout_arm`, AWR-206) (:453-457),
  8 `breakdown_active` (:506), 9 `drop_crossing` (:542, :577),
  10 drop/post-drop cycles + holds and the phrase default
  (`_decide_phrase_default`, :757+), 11 `buildup_to_drop_window` (:647-648).
  The terminal fall-through is `_decide_phrase_default` (:676).
- [confirmed] The personality's drop scene attribute is `self._drop_scene`
  (`laser_director.py:542`).
- [confirmed] The executor is role-driven with a fixed `_AUTO_ROLES` set and
  strict gates `_passes_automatic_gates` (`laser_executor.py:61-62, 131,
  169, 625`); the drop-lifecycle mirror path keys on
  `reason == "drop_crossing"` specifically (`laser_executor.py:493`), so a
  new reason string cannot trip it.
- [confirmed] AWR-220's interim gate `drop_laser_qualifies(tier, tier_min)`
  lives in `drop_presentation.py:154` (config keys
  `laser_ratio`/`laser_tier_min`, `drop_presentation.py:86,99,129`); it
  gates *personality drop lasers by F2 tier*. This spec does NOT touch it
  (explicitly out of scope; a future round may let vetted spans feed it —
  see Part B Open Question OQ-2).
- [confirmed] Blackout/emergency authority is layered ABOVE scene selection:
  smart + manual mask owners, MIDI-input blackout refcount, pack frame-level
  blackout (`docs/subsystems/laser.md` "Blackout-mask migration";
  `docs/architecture/laser_blackout_authority.md`). Nothing in this spec adds
  a writer to any mask.

### A.4 Root cause / why this round exists

There is no defect. This is the planned live consumer of spectral-program
deliverable #1: after the operator's veto pass, the surviving growl spans must
reach the running bridge or the whole retrieval program terminates in a
markdown file. The design tension being resolved: the artifact's identity key
(sha256 of audio bytes) is not known at runtime, and the laser layer's
precedence ladder must not be disturbed.

---

## Part B — Tasks (implement exactly, in order)

### Absolute rules

- Out of scope, must not touch: LED/Govee anything, SoundSwitch output/pack
  code, detector/spectral analysis logic, `drop_presentation.py` behavior,
  blackout/mask owners, `smart_phrasing.py`, sealed dirs under
  `local/spectral_v5_2026_07_17/` (read-only; the veto/artifact builders WRITE
  ONLY under `laser_warrant_v1/vetoes/` and the new artifact output path).
- Behavior that must not change: with no artifact file present, or
  `mode: "off"`, every laser decision, LED frame, and SS frame is
  byte-identical to today (regression-gated by test, Part D T1).
- Error handling: artifact missing/unreadable/schema-mismatched → log once at
  INFO, feature inert (fail-open = today's behavior). Never raise into the
  event loop or push loop; never a success-shaped fallback that pretends a
  span matched. Join miss / sanity-check failure per track → that track has
  no spans, one INFO line, nothing else.
- Live rekordbox master.db is NEVER opened by any new offline tool — scratch
  copy only (precedent: spec v3 §B.4 / `stage2_sweep_resolve.py`).
- No new I/O of any kind on the 200 Hz push loop (AGENTS.md §6).

### Task 1 — Veto ingestion (offline, append-only)

New dir `local/spectral_v5_2026_07_17/laser_warrant_v1/vetoes/` (this is the
one writable area inside the package; sealed payloads stay untouched):

1. `delivered_batches.json` — append-only ledger:
   `{"deliveries": [{"batch": 1, "delivered_at": "<date>", "row_ranks": [1..25]}]}`.
   A row is *vetted* only if its batch was DELIVERED to the operator.
   Silence-is-a-pass applies to delivered rows only; undelivered rows are
   NOT passed.
2. `verdicts_<date>.json` — append-only veto records, one file per veto
   session: `{"verdicts": [{"batch": 1, "rank": 12, "verdict": "veto",
   "note": "<optional operator words>"}]}`. Only `"veto"` records exist —
   passes are the absence of a veto for a delivered row. Files are never
   edited after the session; corrections append a newer file (later file
   wins per (batch, rank); a later `"unveto"` verdict value is permitted for
   correction and must be supported by the builder).

### Task 2 — Artifact builder (offline tool, no runtime importers)

New `tools/build_laser_warrant_artifact.py` (offline, read-only over sealed
inputs, same no-runtime-importers class as `tools/spectral_*`):

1. Re-run the frozen runner deterministically (import
   `laser_warrant_v1.run()` under the spec v3 §B.1 hygiene: `python3 -I -B`,
   `sys.dont_write_bytecode = True`) to recover the full event list including
   member spans; assert `row_count` and per-row `(content_id, beat_span)`
   match the regenerated `ranked_events.json` byte-derivation. If the exec
   prefers not to re-score (~minutes of CPU), the fallback is
   `[anchor, anchor+8)` member spans from `recurs_at_beats` — but then each
   such span carries `"span_source": "anchor_approx"` provenance.
2. Load Task-1 veto files; compute surviving rows = delivered − vetoed.
3. Join keys, built offline exactly like the title map: walk the library
   files already enumerated by the frozen identity maps, sha256 each file to
   its `content_id`, and read a SCRATCH COPY of master.db to record per cid:
   `rb_content_id` (str ContentID), `filepath` (FolderPath), `size_bytes`,
   `mtime_ns`. (Precedent machinery: `build_cid_title_map.py`.)
4. Emit the vetted-spans artifact (schema below) to
   `config/laser_warrant_vetted.json` (gitignored — it embeds the operator's
   track titles and absolute paths; add the gitignore entry + a tiny tracked
   `config/laser_warrant_vetted.example.json`).

Artifact schema v1 (all of it):

```json
{
  "schema_version": 1,
  "generated_at": "<iso date>",
  "provenance": {
    "spec_sha256": "<laser_warrant_list_spec_v3.md sha>",
    "veto_files": ["verdicts_....json"],
    "delivered_batches": [1, 2],
    "builder": "tools/build_laser_warrant_artifact.py"
  },
  "tracks": {
    "<cid64>": {
      "title": "Artist — Title",
      "join": {
        "rb_content_id": "123456",
        "filepath": "/Users/…/track.mp3",
        "size_bytes": 12345678,
        "mtime_ns": 1234567890123456789
      },
      "spans": [
        {
          "beat_span": [328, 336],
          "seconds_span": [163.2, 167.19],
          "rank": 12,
          "peak_similarity": 0.9123,
          "argmax_exemplar": "Q1",
          "flags": ["ATYPICAL"],
          "veto_batch": 1,
          "span_source": "head"
        }
      ]
    }
  }
}
```

Per-span provenance is mandatory (rank, flags, veto batch, span_source
head/member/anchor_approx) so any later live complaint ("lasers fired at the
wrong moment in X") maps straight back to a row the operator can veto in an
append-only follow-up — the veto loop stays the ONLY precision channel.

### Task 3 — Pure runtime module `laser_warrant.py` (new file, repo root)

Pure functions + one small immutable store; no I/O in the hot-path
functions; the pure seam for Part D tests:

- `load_artifact(path) -> WarrantArtifact | None` — parse + schema-validate;
  `None` (with reason string for the log) on any failure. Called only from
  the Task-4 worker thread, never from the push loop.
- `spans_for_track(artifact, rb_content_id, filepath) -> tuple[WarrantSpan, ...]`
  — join order: (1) `rb_content_id` exact match, (2) `filepath` exact match.
  Returns `()` on miss.
- `grid_sanity(span, beatgrid_times_ms, tol_s=0.75) -> bool` — cross-check
  `beatgrid_times_ms[beat_span[i]]/1000` against `seconds_span[i]` (both
  ends, index-guarded). A failure means the track was re-analyzed / regridded
  since the offline build → drop that span (and log once per track). This is
  the staleness guard that replaces runtime hashing.
- `active_span(spans, elapsed_ms) -> WarrantSpan | None` — linear scan
  (≤3 spans/track by construction, spec v3 §C.5 cap); pure math, push-loop
  safe.

### Task 4 — StateManager wiring (event-driven, off the push loop)

1. New event kind `Ev.LASER_WARRANT_SPANS` in `models.py` (payload:
   `{deck, load_gen, spans}`), documented next to `ANLZ_PATH`
   (`models.py:295`).
2. In `_on_filepath_resolved` (`state_manager.py:2573` region), after
   `meta.content_id`/`meta.filepath` land: spawn a daemon worker following
   the `_start_anlz_worker` pattern EXACTLY (`state_manager.py:2343-2411`):
   entry `load_gen` re-check, artifact file `os.stat` mtime check → (re)load
   via `laser_warrant.load_artifact` only when changed (cached parsed
   artifact otherwise), compute `spans_for_track` + `grid_sanity` filter,
   post `Ev.LASER_WARRANT_SPANS` with `eq.put_nowait` (queue-full → WARN,
   drop, same as `state_manager.py:2388-2389`). All artifact I/O therefore
   happens on this worker at track load — never at tick time. This one
   mechanism also gives free hot-refresh: a rebuilt artifact (new veto batch)
   takes effect at the next track load, no restart required (restart also
   works and is the operator's normal activation path).
3. Event consumer in `_handle_event`: `load_gen` guard exactly like
   `ANLZ_DATA` (`state_manager.py:1513-1517`), then store
   `self._laser_warrant_spans[deck] = tuple(spans)`; cleared on track load
   start and meta reset (every mode-transition path that resets `meta` must
   clear it — pre-handoff checklist #4: enumerate ALL reset paths at
   implementation time, mirroring where `meta.reset()`/load bookkeeping
   runs, not just the happy path).
4. Push tick: compute `warrant_span = laser_warrant.active_span(
   self._laser_warrant_spans.get(active, ()), elapsed_ms)` — pure in-memory —
   and pass two new fields into `LaserContext` (`laser_models.py:122`,
   construction site `state_manager.py:5365`):
   `laser_warrant_active: bool = False`,
   `laser_warrant_rank: int = 0` (0 = none; rank for the decision log).

### Task 5 — LaserDirector consumption (the warrant gate, UNDER everything)

Config: a new `laser_warrant` block in the laser director config
(`laser_config.py` / `config/laser_director.example.json`):
`{"mode": "off" | "observe" | "accent", "min_refire_beats": 32}` —
default `"off"`. Unknown mode → treated as `"off"` + one WARN (fail-open).

- `"off"` (DEFAULT): no reads of the new context fields beyond construction.
  Byte-identical decisions (T1 regression gate).
- `"observe"`: no decision changes at all; the decision log
  (`laser_decision_log.py`) gains `warrant_active`/`warrant_rank` fields so
  a mix can be replayed to see exactly when the gate WOULD have acted. This
  is the first-activation mode: the operator mixes normally, we read the log.
- `"accent"`: one new branch in `_decide`, inserted BETWEEN the priority-11
  buildup-window branch (`laser_director.py:647-661`) and the terminal
  `_decide_phrase_default` call (`laser_director.py:676`) — i.e. reachable
  only when priorities 1–11 all declined, which is what "sits UNDER
  blackout/emergency masks, drop policy, and personality" means in this
  ladder. The branch: if `ctx.laser_warrant_active` and the last warrant fire
  for this span is ≥ `min_refire_beats` behind `ctx.abs_beat`, return
  `LaserSceneDecision(scene=self._drop_scene, reason="growl_warrant",
  priority=12, source="policy", role=<OQ-1>)`. It NEVER sets
  `blackout_arm`, never touches masks, never writes drop-lifecycle state.
  The executor is UNCHANGED: strict `_passes_automatic_gates`
  (`laser_executor.py:169,625`) still applies, and the mirror path cannot
  trigger because it keys on `reason == "drop_crossing"`
  (`laser_executor.py:493`).
- Director state for the refire lockout resets wherever director lifecycle
  state already resets (master/track/stop/resume/scripted/idle transitions —
  `docs/subsystems/laser.md` "Director and executor lifecycle state reset";
  checklist #4 applies).

### Open questions (exec review must close these before implementation)

- **OQ-1 (role plumbing)** [unknown]: `role="phrase"` (recommended: ordinary
  auto-scene under existing per-role cooldown/bank machinery, zero
  drop-lifecycle interplay) vs `role="drop"` (drop-bank scene selection but
  more executor surface). Requires one `laser_executor.py` trace of both role
  paths at implementation-spec finalization; this draft deliberately does not
  claim executor behavior it hasn't traced.
- **OQ-2 (relationship to AWR-220)** [decision deferred]: whether vetted
  spans should ALSO feed `drop_laser_qualifies` (a growl span overlapping a
  drop upgrading its laser eligibility). Explicitly NOT in v1.
- **OQ-3 (hardest question — join durability)** [assumed]: `rb_content_id` +
  local `filepath` are stable for the operator's library between artifact
  builds. Known breakers: track re-import (new ContentID), file move (path),
  file retag (sha changes offline, but runtime join doesn't hash — the
  `grid_sanity` check catches re-analysis, NOT a pure retag that keeps the
  grid). Consequence of every breaker is identical: no spans for that track,
  today's behavior. The correct long-term fix if it ever bites is re-running
  the builder (minutes), not runtime hashing.
- **OQ-4 (veto-mode confirmation)** [operator]: the whole round activates
  only after Brandon confirms the veto workflow shape (batches in chat,
  veto-only, silence is a pass) and actually runs the pass. This spec is
  inert until then.

---

## Part C — Invariants that MUST still hold (live safety)

1. 200 Hz push loop gains ZERO blocking I/O — all artifact reads happen on
   the Task-4 worker thread at track load; tick-time work is a ≤3-element
   scan (AGENTS.md §6; `state_manager.py:5335-5338` contract comment).
2. `StateManager` stays the only `DeckState` writer; new state flows in as a
   `BridgeEvent` with `load_gen` guard, mirroring `ANLZ_DATA`
   (`state_manager.py:1513-1517`). Events immutable after creation.
3. `ANLZ_PATH` before `TRACK_LOADED` ordering untouched (`models.py:295`,
   `rb_state_reader.py:449-458`).
4. Laser precedence: priorities 1–11 all still win over the warrant branch by
   construction (insertion after :661, before :676). Emergency, manual
   override, scripted, breakdown, autoloop-not-ready+blackout-arm (AWR-206),
   drop lifecycle, and the buildup window are unreachable-from-below and
   unmodified.
5. Blackout authority: no new mask owners, no mask writes, `blackout_arm`
   never set by the new branch; every existing release path untouched
   (`docs/architecture/laser_blackout_authority.md`).
6. AWR-220 tier gating (`drop_presentation.py:154,310`) byte-identical.
7. Fail-open beats fail-dark: every failure mode (no artifact, bad schema,
   join miss, grid mismatch, queue full, worker exception) degrades to
   "warrant inactive" — the branch can only ADD a scene opportunity, never
   remove, darken, or suppress one.
8. No artifact present OR `mode: "off"` = exactly today's behavior (T1 gate).
9. Secrets/live-config hygiene: `config/laser_warrant_vetted.json` is
   gitignored (titles + absolute paths); example file carries fake data only
   (AGENTS.md §6).
10. Live rekordbox master.db never opened by the offline builder — scratch
    copy only.
11. Policy/execution separation stands: the director decides
    (`laser_director.py`), the executor's gates and MIDI behavior are
    unmodified (`laser_executor.py`).

### Live-mixing scenario walkthrough (mandatory)

- **Normal blend, warrant span on the outgoing deck:** deck 1 in a vetted
  span, operator brings deck 2 in on channel faders + EQ (never crossfader).
  Spans are keyed per deck; the director only sees the ACTIVE deck's context
  (`LaserContext.active_deck`, built from resolver-chosen `d`). When the
  active deck flips to 2, deck 1's span stops mattering that tick — no cross
  contamination, no latched state beyond the refire beat marker, which resets
  on track/master transitions.
- **Track load mid-span:** new `TRACK_LOADED` bumps `load_gen`; the old
  worker's late `LASER_WARRANT_SPANS` event is dropped by the consumer guard;
  span store cleared at load start → no stale spans over the new track.
- **Hot-cue jump / scratch across a span edge:** activation is level-checked
  per tick from `elapsed_ms` (no edge latch), so jumping out ends the accent
  hold-path at the next decision; jumping back in refires only if
  `min_refire_beats` has passed — scratch churn cannot machine-gun scenes.
- **Blackout during a span:** pre-chorus mask, smart-drop blackout, manual
  pad blackout, emergency — all either return earlier in the ladder
  (priorities 1–8) or act at mask/executor level ABOVE scene MIDI. The
  warrant branch at priority 12 is unreachable or overridden in all cases.
- **Drop hits inside a vetted span:** drop_crossing (priority 9) and cycles
  (10) win; the warrant never competes with drop policy — it only fills
  ticks the whole ladder declined.
- **SoundSwitch autoloop mid-re-arm:** priority 7 `autoloop_not_ready`
  returns before the warrant branch; the AWR-206 blackout-arm path is
  byte-identical.
- **Scripted track:** priority 6 returns first; warrant unreachable.
- **Position stale / not playing / no track:** priorities 3–5 return first.
- **Artifact rebuilt mid-show (new veto batch):** next track load's worker
  sees the new mtime and reloads off-loop; the currently-playing track keeps
  its already-posted spans — no mid-track surprises.
- **Track was re-analyzed since the build (beatgrid moved):** `grid_sanity`
  drops the affected spans at load, one INFO line — misplaced lasers are
  structurally prevented rather than hoped away.
- **Bridge restart:** normal menubar/watcher path; after restart verify
  exactly one process (`pgrep -f rb_ss_bridge_v2 | wc -l` == 1). Feature
  state rebuilds from config + artifact at the next track load; nothing
  persisted in-bridge.

### Rollback

`git revert` of the implementation commits + bridge restart = exact prior
behavior. Faster live mitigations, in order: set `mode: "off"` (restart picks
it up), or remove/rename `config/laser_warrant_vetted.json` (next track load
goes inert). No data migration, no persistent state, nothing to clean up.

---

## Part D — Tests

All algorithm tests hit the pure seam in `laser_warrant.py` — no disk, no
subprocess (checklist #7). Fixture artifacts are inline dicts.

- **T1 (the regression gate):** with no artifact configured AND with
  `mode: "off"` + artifact present, a scripted decision-sequence replay
  through `LaserDirector._decide` produces decisions equal to a control run
  built without the feature fields — the byte-identity claim in Part B is a
  test, not a sentence. (Pattern precedent: the `enabled: false` drop
  presentation gate test in `tests/test_state_manager_drop_presentation.py`.)
- **T2 (pure module):** schema accept/reject (missing keys, wrong types,
  future schema_version → None + reason); join order rb_content_id-first
  then filepath, miss → `()`; `grid_sanity` pass/fail/one-end-out-of-grid;
  `active_span` boundaries (enter at s0, exclusive at s1, between-spans gap,
  empty tuple).
- **T3 (director branch):** for every priority-1..11 condition, warrant
  active + that condition ⇒ decision is the HIGHER-priority one (ladder
  table-driven); warrant fires only on full fall-through; refire lockout
  honored; lockout resets on lifecycle reset; `blackout_arm` never set by
  the branch.
- **T4 (wiring):** worker posts spans with correct payload; consumer drops
  stale `load_gen`; span store cleared on new load and on every meta-reset
  path enumerated at implementation; `LaserContext` fields default False/0
  and carry through `state_manager.py:5365` construction.
- **T5 (observe mode):** decisions byte-identical to `off`; decision log
  carries warrant fields.
- **T6 (builder, offline):** delivered−vetoed set arithmetic incl. later-file
  wins and `unveto`; undelivered rows excluded; provenance fields present per
  span; anchor_approx marking when the fallback path is used.

Suite: `python3 -m unittest discover tests` must stay green.

---

## Part E — Acceptance (definition of done)

- [ ] Contract first: extend the `laser` contract in
  `docs/agents/change_contracts.yml` — add `laser_warrant.py`,
  `tools/build_laser_warrant_artifact.py`, and
  `config/laser_warrant_vetted.example.json` to `code_globs` (note: the
  `models.py` event-kind addition rides the existing `state_manager.py`
  coverage; verify which contract owns `models.py` at implementation and
  extend if none) — BEFORE code lands (AGENTS.md §7).
- [ ] All Part B tasks implemented; Part C invariants re-verified at the
  implementation HEAD (line numbers here are e76cbbf0 and MUST be re-checked;
  they drift).
- [ ] Part D tests written and green; full
  `python3 -m unittest discover tests` green.
- [ ] Docs updated per the `laser` contract `docs_update` list
  (`change_contracts.yml:383-393`): `docs/subsystems/laser.md`,
  `docs/status/feature_status_matrix.md`, `docs/status/support_matrix.md`,
  `docs/status/validation_matrix.md`,
  `docs/validation/hardware_validation_log.md`,
  `docs/agents/task_playbooks/change_laser_behavior.md`,
  `docs/architecture/laser_blackout_authority.md`,
  `docs/architecture/laser_color_authority.md`,
  `docs/plans/active/laser_color_engine_design_spec.md`,
  `docs/status/active_work_registry.md` (register the AWR id assigned at
  implementation; this draft is intentionally NOT yet registered — it is not
  active work until exec review + operator gates pass).
- [ ] Hard checks green: `python3 tools/check_docs_metadata.py`,
  `check_agent_contracts.py`, `check_docs_drift.py`, `check_ui_jargon.py`.
- [ ] Gitignore entry for `config/laser_warrant_vetted.json` + example file
  with fake data; no titles/paths/secrets committed.
- [ ] Status language: `implemented` / `software-tested` at most; the
  feature is `hardware-unvalidated` and `experimental` until the operator's
  observe-mode mix readout.
- [ ] Rollout ladder honored: land with `mode: "off"` → operator restart →
  `observe` mix + log readout → operator explicitly enables `accent`. No
  seat skips a rung.

### When you finish (implementer report-back)

Changed files; tests/checks run with output; the decision-log field names for
the observe readout; and a plain-language operator summary: what will visibly
change at the next mix (nothing, until observe/accent is switched on), what
cannot change (blackouts, drops, scripted, everything above priority 12),
the two-step off switch, and the restart + single-process check.

### Adversarial self-review (checklist #9 — how this breaks, and why it can't)

Attack tried: *stale spans firing lasers at the wrong moment after the
operator re-analyzes a track* (grid shift). Defense: `grid_sanity` compares
both span ends against the CURRENT loaded beatgrid at track load and drops
mismatches — the failure collapses to "no spans", not "wrong lasers".
Attack tried: *worker race posting old track's spans onto a new load*.
Defense: double `load_gen` guard (worker entry + consumer), same proven
pattern as ANLZ (`state_manager.py:2355-2356`, `:1513-1517`).
Attack tried: *push-loop I/O smuggled in via "just one os.stat at tick
time"*. Defense: the stat lives in the Task-4 worker; the tick path is a
pure scan over an already-materialized tuple, and T4 asserts the context
build stays I/O-free.
Attack tried: *the accent branch outranking a safety branch after a future
refactor renumbers priorities*. Defense: T3 is table-driven over the ladder,
so any reordering that lets warrant beat a safety reason fails the suite.
Residual risk (named, accepted): OQ-1's executor role choice is untraced in
this draft; implementation cannot start until it is traced and closed.
