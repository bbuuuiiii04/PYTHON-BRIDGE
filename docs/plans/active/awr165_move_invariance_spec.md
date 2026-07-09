---
doc_status: current
truth_level: spec
last_verified_commit: 57d514f
last_verified_date: 2026-07-09
validation_scope: >
  Codex implementation spec for AWR-165 move-invariant track identity: re-key the spectral
  v3+v4 caches, the LED v2 IdentityStore, and the laser-solo LearnedStore from
  path/mtime/content_id keys to a content fingerprint ("fp:" + sha1(size + first/last MiB)),
  so moving/renaming/copying a track never loses its lighting identity while replaced content
  still re-analyzes. Authored from the locked design
  (docs/plans/active/track_identity_move_invariance_design.md, design-verified at 9ead100);
  EVERY seam cite in Part A independently re-verified at 57d514f (the F2/F4/laser/AWR-176
  rounds moved state_manager.py and spectral_cache.py lines since the design). Spec only —
  no code, config, store, or runtime state changed by this document.
work_status: awaiting Codex implementation — target window 2026-07-11 18:28+ (operator-scheduled Codex quota window); interim mitigation for tonight's USB export is tools/spectral_stick_sweep.py (AWR-183, path-keyed pre-warm)
relates_to: track_identity_move_invariance_design.md, usb_bridge_launcher_design.md, lighting_engine_v2_f2_spec.md
---

# Codex Implementation Spec - AWR-165 Move-Invariance (path-independent spectral + identity caches)

**Operator directive (verbatim, 2026-07-09): "the bridge should recognize the files even if
i move them."** Design authority: `docs/plans/active/track_identity_move_invariance_design.md`
(all §-references below point there). This spec is the executable version of that design.
Read the design once for rationale; implement from THIS document — every file:line here was
re-verified at `57d514f` and supersedes the design's `9ead100`-era line numbers.

**Implementation target: the Codex window opening 2026-07-11 18:28+.** Do not start earlier
against a moving HEAD without re-running the Part A verification greps.

---

## Part A - Context & Root Cause (verified; read, do not implement)

All claims `[confirmed]` by direct code read / live-store inspection at `57d514f` unless
labelled otherwise.

### A.1 Root cause

The spectral cache key is a hash of **where the file lives and when it changed**, not what
it contains: `_cache_key` = `sha1(realpath ⊕ mtime_ns ⊕ size ⊕ beatgrid_fingerprint)`
(`spectral_cache.py:337-352`). Move or rename a track ⇒ new key ⇒ full re-extraction
(~15 s worker-thread cost per track at load) and the old entry orphans. The LED v2 identity
store keys by rekordbox `content_id` (`led_identity_v2.py:133-136` — bare `str(content_id)`,
`"path:"+realpath` fallback), which survives rekordbox-managed moves but dies on
delete-and-reimport (new DB row) and is `[unknown]` for USB device playback — and 2 of the 3
filepath-resolver paths derive `content_id` by matching registered DB paths/UUIDs, so the
"content" id is itself path-dependent. Full break matrix: design §2 (S1-S5).

### A.2 The stores and their keys, at 57d514f

| Store | Key today | Where | Verified cite |
|---|---|---|---|
| Spectral v4 cache (716 entries live at design time) | `_cache_key` (path+mtime+size+grid) | `~/Library/Application Support/RBSS Bridge/spectral_cache/v4/` | `spectral_cache.py:337-352` (key), `:142-155` get, `:158-196` put, `:199-210` evict, `:311-328` stale predicate |
| Spectral v3 cache (488 entries; still live on the smart-drop path) | same `_cache_key` | `…/spectral_cache/` (flat top level) | `:48-83` get, `:86-124` put, `:127-139` evict, `:383-400` stale predicate; v3 runtime read `state_manager.py:323,:338` |
| LED v2 IdentityStore (301 entries, all bare content_id keys) | `content_key(content_id, filepath)` | `local/state/led_identity_v2.json` (cwd-relative) | `led_identity_v2.py:133-136`; store path `led_models.py:86`; loaded `__main__.py:505`; JSON shape `{"version": 1, "tracks": {...}}` with **fail-closed version check** `led_identity_v2.py:276-293` (version≠1 ⇒ degraded read-only) |
| Laser-solo LearnedStore | `f"{content_id}:{round(beat)}"` | `local/state/laser_solo_learned.json` (`drop_presentation.py:51`) | `drop_presentation.py:496-569`; key parse uses `rpartition(":")` at `:529` |
| Scripted-track match | SSID (`SOUNDSWITCH_ID` ID3 tag) first, exact-filepath fallback | in-memory | `state_manager.py:2573-2620` — **already move-invariant, NO CHANGE** |

Cache payloads store `audio_filepath`, `mtime_ns`, `size`, `beatgrid_fingerprint`
(v4: `spectral_cache.py:290-293`; v3: `:365-370`). **Post-design delta [confirmed]:** AWR-176
(landed today) added `growl_band_frames` + `growl_centroid_frames` to the v4 payload
(`:303-304`) — the migration tool must preserve these (and any future field) by copying the
payload verbatim, never by field allow-list.

### A.3 Where the inputs flow (the seams your tasks touch)

- **Three resolver paths**, all in worker threads inside `filepath_resolver.py`, all thread
  `content_id`/`soundswitch_id`/`filepath` into the `FILEPATH_RESOLVED` payload:
  - ANLZ-UUID→DB: `_resolve_anlz_worker` `:376-396` → `_db_lookup_by_anlz` `:263-321`
    (payload dict built at `:302-311`);
  - title-fuzzy DB: `_resolve_title_worker` `:411-469` (payload `:448-458`);
  - lsof: `_resolve` `:503-580` (payload `:560-570`; `_db_lookup` `:324-341` supplies
    content_id).
- `StateManager._on_filepath_resolved` (`state_manager.py:2510`) copies the payload onto
  `TrackMetadata` (`:2516-2526`; dataclass at `models.py:34-54`, `clear()` at `:56-74`), then
  spawns the ANLZ/identity/spectral background worker (`:2547-2572`) passing
  `identity_key=led_identity_content_key(content_id, filepath)` (`:2561-2564`; second call
  site `:1903`).
- That worker runs `_read_runtime_anlz_data` (`state_manager.py:233-306`): v4 cache get/put
  at `:252-260` (extraction gated by `_V4_AT_LOAD_MAX_S` `:312`), identity derive `:266-271`,
  F2 plan `:277-286`, and the v3-compat path `_runtime_spectral_features` `:315-338`.
- LearnedStore call sites: `beats_for_track` fed by `content_id = str(d.meta.content_id or "")`
  (`state_manager.py:2653,:2657-2659`), stashed as `_drop_presentation_plan_content_id`
  (`:593,:2668`) and consumed by `record` (`:2915-2916`) and `remove` (`:3077-3080`) — all
  behind `if content_id` empty-guards.
- One-shot cache eviction at startup: `_start_spectral_cache_eviction_if_enabled`
  (`__main__.py:909-927`) behind `RBSS_SMART_REARM_EXPERIMENT=1` AND `RBSS_SPECTRAL_ENABLE=1`.
- Offline tools that build the same path-keyed cache keys (all must move to the new keying,
  Task 3c): `tools/spectral_sweep.py:86,:92`, `tools/spectral_calibration_report.py:389,:399`,
  `tools/stems_pilot.py:670-671,:694,:867`, `tools/eval_smart_drop_algorithm.py:798,:803`,
  and `tools/spectral_stick_sweep.py` (reuses `spectral_sweep._sweep_one`; untracked on
  2026-07-09, expected committed by implementation time — `[assumed]`, verify presence).
- `anlz_reader.py` needs **no code change**: its only path logic is the suffix-swap helper
  `_candidate_anlz_paths` (`anlz_reader.py:1115-1133`), path-prefix-agnostic. It appears in
  **zero** change contracts (grep-verified at 57d514f) — closing that gap is Task 0.
- Rekordbox DB constant: `RB_DB_PATH` (`config.py:20`). The DB is read via
  `pyrekordbox.db6.Rekordbox6Database(str(RB_DB_PATH), unlock=True)` with a
  `warnings.catch_warnings()/simplefilter("ignore")` wrapper, iterated via `db.get_content()`
  yielding rows with `.ID`, `.FolderPath`, `.AnalysisDataPath`, `.BPM`, `.Length`, and closed
  with `db.close()` in a `finally` (exact working pattern: `filepath_resolver.py:279-321`).
  **The bridge NEVER writes this DB (standing rule).**

### A.4 Interim mitigation (tonight — context, not your work)

`tools/spectral_stick_sweep.py` (AWR-183, usb lane, runs tonight) pre-warms **path-keyed**
v4 entries for the USB export by keying the on-stick absolute path (`/Volumes/<name>/...`).
It works only while the target Mac mounts the stick under the same volume name — exactly the
fragility this spec removes. Payoff after this spec lands: a stick track is a byte-copy of
its library twin (when rekordbox device export doesn't transcode — design §11.1), so its
fingerprint matches and the library's cache entry serves stick playback with **no sweep at
all**. Interaction to honor in Task 6: stick-path-keyed legacy entries only migrate while
the stick is mounted; otherwise they are kept-legacy (not deleted) by the missing-file rule
only if the tool is run with the stick absent — document this in the tool's `--help`.

### A.5 Chosen key (design §3-§4, decided — do not re-litigate)

`track_fp = "fp:" + sha1(size_bytes ⊕ first_1MiB ⊕ last_1MiB)`, computed **once per track
load** in the resolver worker, shipped in the `FILEPATH_RESOLVED` payload, stored on
`TrackMetadata`. Move-invariant by construction (S1/S2/S3), replace-sensitive (S4), beatgrid
stays a freshness component of the spectral key only (S5). mtime deliberately excluded.
Collision ceiling and the not-built full-file-hash knob: design §4. `content_id` and SSID
demote to provenance/alias. Prefix `"fp:"` cannot collide with live legacy keys (bare
numeric content_ids or `"path:..."`) — `[confirmed]` against the live store shape.

---

## Part B - Tasks (implement exactly, in order; commit after each task by explicit path)

### Absolute Rules

- **Out of scope — do not touch:** `rb_state_reader.py`, `rb_memory.py`, `rb_offsets.py`,
  `live_bpm.py`, `mtc_reader.py` (readers stay byte-identical); `lighting_moments_v2.py` and
  `docs/plans/active/lighting_engine_v2_f2_spec.md` (F2 inherits invariance through the
  identity worker — design §4 — with zero F2 edits); the AWR-176 growl-centroid fields
  (preserve verbatim, never re-derive); scripted-track matching (`state_manager.py:2573-2620`);
  `audio_spectral_features.py` extraction internals; anything laser-policy or Govee-transport;
  live configs; the rekordbox DB (read-only, ever).
- **Behavior that must not change:** every scenario that hits today still hits (the key drops
  path/mtime components and keeps the beatgrid component — strictly widening, design §7);
  F2-off byte-identity; `ANLZ_PATH` before `TRACK_LOADED`; event immutability; the 200 Hz
  push loop gains no I/O.
- **Error handling (per task, no exceptions to this):** `compute_track_fp` returns `""` on
  any `OSError` and never raises; empty `track_fp` ⇒ `_cache_key` returns `None` ⇒ the
  existing miss path; identity falls back to today's `content_id`/`path:` key; LearnedStore
  keeps its empty-guard no-op. Migration is dry-run by default, fail-closed per entry
  (unreadable entry ⇒ logged + kept, never deleted on error), nonzero exit if a store file
  itself is unreadable. No broad `try/except`, no success-shaped fallbacks, no silent
  early-returns.
- Work directly on `main`; no branches/worktrees. The worktree may be dirty from parallel
  lanes — never revert or clean files you did not change; commit only your explicit paths.

### Task 0 - Contract gap closure (REQUIRED FIRST — AGENTS.md §7)

`docs/agents/change_contracts.yml`: add `anlz_reader.py` and `filepath_resolver.py` to
`rekordbox_readers.code_globs` (currently `rb_memory.py`, `rb_state_reader.py`,
`live_bpm.py`, `rb_offsets.py`, `mtc_reader.py`, `docs/data/offsets-macos.yaml` — verified).
`filepath_resolver.py` stays in `drop_presentation` too (dual coverage is intentional:
resolver curation-tags belong to drop_presentation; resolver-as-reader belongs to
rekordbox_readers). Mirror the change in the human table `docs/agents/change_contracts.md`
if its `rekordbox_readers` row enumerates files. Run
`python3 tools/check_agent_contracts.py` before committing.

### Task 1 - `filepath_resolver.py`: the fingerprint helper

Add near `_read_soundswitch_id` (`:116`):

```python
_FP_CHUNK = 1024 * 1024  # 1 MiB


def track_fp_digest(size_bytes: int, head: bytes, tail: bytes) -> str:
    """Pure digest core - the test seam. 'fp:' + sha1(size NUL head NUL tail)."""
    h = hashlib.sha1()
    h.update(str(int(size_bytes)).encode("ascii"))
    h.update(b"\0")
    h.update(head)
    h.update(b"\0")
    h.update(tail)
    return "fp:" + h.hexdigest()


def compute_track_fp(filepath: str) -> str:
    """Content fingerprint of an audio file; '' on any read failure (never raises)."""
    if not filepath:
        return ""
    try:
        size = os.stat(filepath).st_size
        with open(filepath, "rb") as fh:
            head = fh.read(_FP_CHUNK)
            fh.seek(max(0, size - _FP_CHUNK))
            tail = fh.read(_FP_CHUNK)
    except OSError:
        return ""
    return track_fp_digest(size, head, tail)
```

Notes: `import hashlib` if not present. Files ≤ 2 MiB produce overlapping head/tail —
deterministic and still content-sensitive, fine. Do NOT add mtime, realpath, or content_id
to the material.

### Task 2 - Thread `track_fp` through the load path

1. **All three resolver payloads** gain `"track_fp": compute_track_fp(<resolved filepath>)`,
   computed in the worker thread right where each payload is built:
   - `_db_lookup_by_anlz` payload dict (`:302-311`) — compute from `fp` (the `FolderPath`);
   - `_resolve_title_worker` payload (`:448-458`) — from `fp`;
   - `_resolve` lsof payload (`:560-570`) — from `matched`.
   One computation per resolution; do not recompute downstream.
2. **`models.py`**: `TrackMetadata` gains `track_fp: str = ""` (place after `content_id`,
   `:38`); `clear()` (`:56-74`) resets it to `""`. This is the mode-transition cleanup — verify
   `clear()` is the single reset path for load transitions (it is today; `is_empty()` at
   `:76-77` unchanged).
3. **`state_manager.py` `_on_filepath_resolved`** (`:2516-2526`): add
   `meta.track_fp = str(payload.get("track_fp", "") or "")`. **Use `.get` with default** —
   recorded sessions replayed by `session_replayer.py` predate the field and must degrade to
   `""` (today's behavior), not `KeyError`.

### Task 3 - `spectral_cache.py`: re-key v3 + v4 to `track_fp ⊕ beatgrid_fingerprint`

1. **Key derivation** — replace `_cache_key` (`:337-352`) with:

```python
def _cache_key_from_fp(track_fp: str, beatgrid_fingerprint: str) -> Optional[str]:
    if not track_fp:
        return None
    material = "\0".join((track_fp, beatgrid_fingerprint))
    return hashlib.sha1(material.encode("utf-8")).hexdigest()


def _cache_key(track_fp: str, beatgrid_times_ms: Sequence[float]) -> Optional[str]:
    return _cache_key_from_fp(track_fp, _beatgrid_fingerprint(beatgrid_times_ms))
```

   The `_cache_key_from_fp` split is REQUIRED: the migration tool (Task 6) derives new keys
   from the `beatgrid_fingerprint` already stored in each payload (the raw grid is NOT stored),
   so key derivation must be reachable without a grid. `_beatgrid_fingerprint` (`:331-334`)
   unchanged.
2. **Public signatures** — `get_cached`, `put_cached`, `get_cached_v4`, `put_cached_v4`
   each gain a **required positional** `track_fp: str` parameter (keep `audio_filepath` for
   payload provenance and logs):
   `get_cached_v4(audio_filepath, beatgrid_times_ms, track_fp)` etc., keying via
   `_cache_key(track_fp, beatgrid_times_ms)`. Required-positional is deliberate: a missed
   caller must fail loudly with `TypeError`, never silently key wrong / always-miss.
3. **Payloads** (`_payload_v4_for_write` `:281-308`, `_payload_for_write` `:355-380`): add
   `"track_fp": track_fp`; keep `audio_filepath` (last-seen provenance, refresh on write);
   keep writing `mtime_ns`/`size` (informational only from now on). Do not bump
   `SCHEMA_VERSION`/`SCHEMA_VERSION_V4` — the `track_fp` payload field is the new/legacy
   discriminator.
4. **Stale predicates** (`_cache_file_is_stale_v4` `:311-328`, `_cache_file_is_stale`
   `:383-400`): if the payload **has** a non-empty `"track_fp"` ⇒ stale only on
   corrupt/schema-mismatch (a moved file's entry must survive its old path going away —
   that is the whole feature). If the payload **lacks** `track_fp` ⇒ legacy entry ⇒ keep
   today's full rule (schema + stat + mtime/size compare), which auto-GCs unmigrated strays.
   Add: `# ponytail: fp-keyed entries never expire; ~1.2k entries — add last-used age eviction only if the dir ever bloats.`
5. **Runtime callers** — thread the fingerprint through `state_manager.py`:
   `_read_runtime_anlz_data` gains kwarg `track_fp: str = ""` and passes it at `:252,:260`
   and into `_runtime_spectral_features(audio_filepath, beatgrid_times_ms, track_fp, *, v4=None)`
   (`:290,:315-338`, all five get/put sites); the spawn block (`:2547-2572`) adds
   `track_fp=meta.track_fp` to `worker_kwargs`.
6. **Offline tools** — same signature everywhere; each tool computes
   `compute_track_fp(track["filepath"])` once per track at enumeration time (import from
   `rb_ss_bridge_v2.filepath_resolver`):
   `tools/spectral_sweep.py:86,:92` (this also covers `tools/spectral_stick_sweep.py`, which
   reuses `_sweep_one` — verify its call threads `track_fp`; its enumeration already has the
   on-stick absolute path to fingerprint); `tools/spectral_calibration_report.py:389,:399`;
   `tools/stems_pilot.py:670-671,:694,:867` (it imports `_cache_key` directly — update to the
   new signature); `tools/eval_smart_drop_algorithm.py:798,:803`.

### Task 4 - `led_identity_v2.py`: IdentityStore re-key

1. `content_key` (`:133-136`) becomes:

```python
def content_key(track_fp: str, content_id: str, filepath: str) -> str:
    if track_fp:
        return str(track_fp)
    if content_id:
        return str(content_id)
    return "path:" + os.path.realpath(str(filepath))
```

   New required first parameter (same fail-loud rationale as Task 3.2). Both call sites
   updated: `state_manager.py:1903` and `:2561-2564` pass `str(meta.track_fp or "")` first.
2. Store version: `IdentityStore.load` (`:276-293`) accepts `version in (1, 2)`;
   `to_dict` (`:294-295`) writes `"version": 2`. A pre-migration (old-code) bridge reading a
   version-2 store hits the existing fail-closed branch ⇒ degraded read-only, never clobbers
   — that IS the design §5 schema-bump requirement, already built; do not add more.
3. New records frozen under fp keys carry provenance in the body: `"content_id"` and
   `"last_path"` fields added at freeze time (`freeze` `:301-315`; populate from the worker's
   available metadata — thread `content_id`/`filepath` alongside `identity_key` in
   `worker_kwargs` only if not already derivable; keep the diff minimal). Freeze-forever
   semantics unchanged. Replaced content ⇒ new fp ⇒ fresh identity; old corrections stay
   filed under the old key (design §11.3 default — operator veto stands open, not blocking).

### Task 5 - LearnedStore re-key (`state_manager.py` only)

Key format becomes `f"{track_fp}:{round(beat)}"`. `drop_presentation.py` needs **no parse
change**: `rpartition(":")` (`:529`) splits on the LAST colon, so `fp:<sha1>:<beat>` parses
correctly (`[confirmed]` by reading the parse; cover with a test anyway). In
`state_manager.py`: `:2653` becomes `track_fp = str(d.meta.track_fp or "")` feeding
`beats_for_track` (`:2657-2659`); rename `_drop_presentation_plan_content_id` →
`_drop_presentation_plan_track_fp` at its four sites (`:593,:2668,:2915,:3077`) and keep the
empty-guards exactly as they are. Legacy `content_id:beat` entries stop matching (fp keys
can't collide with them) until Task 6 migrates them.

### Task 6 - `tools/migrate_track_identity_keys.py` (one-shot, offline, bridge idle)

New tool; **dry-run by default, mutates only with `--apply`**; prints per-store counts
(migrated / kept-legacy / deleted-missing / failed). Backup each store file to
`<name>.pre_fp_migration.bak` alongside before rewriting (`local/state/` and the cache dir
are runtime-local; `[assumed]` gitignored — verify with `git check-ignore` and STOP if a
store path is tracked; backups must never be committed, per AGENTS.md §6).

1. **Spectral v4 then v3 dirs** (respect the versioning convention, `spectral_cache.py:1-8` —
   never cross versions): for each `*.json`: payload already has `track_fp` ⇒ skip (idempotent
   re-runs); else stat `audio_filepath` — missing ⇒ **unlink** (identical outcome to today's
   eviction predicate); present ⇒ `compute_track_fp(path)` (`""` ⇒ count failed, keep file),
   new key = `_cache_key_from_fp(fp, payload["beatgrid_fingerprint"])`, write payload
   **verbatim + `track_fp` field** under the new key (atomic tmp+`os.replace`, same pattern
   as `put_cached_v4` `:173-189`), unlink the old file. Never re-extract audio here.
2. **IdentityStore** (`local/state/led_identity_v2.json`, 301 entries): keys starting `fp:`
   ⇒ skip; `path:` keys ⇒ fingerprint that path directly; bare content_id keys ⇒ resolve
   `FolderPath` via the read-only pyrekordbox pattern from A.3 (one DB open for the whole
   run, `finally: db.close()`); resolvable ⇒ re-key, add `content_id`/`last_path` provenance
   to the body; unresolvable (missing file / stale DB row) ⇒ **keep under the legacy key** —
   corrections are never destroyed by migration (design §5). Write `"version": 2`.
3. **LearnedStore** (`local/state/laser_solo_learned.json`): reuse the same
   content_id→FolderPath→fp mapping; re-key `content_id:beat` → `fp:...:beat`; unresolvable
   kept as-is. (File has no version field; legacy leftovers are inert, not harmful.)
4. Key-derivation caveat, stated in the tool's output: migrated spectral keys are only as
   fresh as the stored `beatgrid_fingerprint` — a track rekordbox re-analyzed since caching
   migrates to a key its next load won't hit (it re-extracts, exactly the S5 rule). Correct
   behavior; no wrong data can be served because fp AND grid must both match.
5. **Deployment ordering (put this in the tool docstring AND the operator summary):** the
   runtime reads ONLY new-style keys after this round (no dual-read), so run the migration
   in the same sitting as the first post-upgrade bridge restart — before the next mix.
   Skipping it loses no data but costs one re-extraction per track on its first post-upgrade
   load (worker-thread, ~15 s to full-strength lighting — live-safe but degraded). If stick
   entries from AWR-183 should survive, run with the stick mounted.

### Task 7 - Docs + registry (contract `docs_update` closure)

Update per Part E's checklist. Registry: extend the AWR-165 row in
`docs/status/active_work_registry.md` (implemented state, commits, what remains
operator-gated). Status language: `implemented` / `software-tested` only —
SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED stands.

---

## Part C - Invariants That MUST Still Hold (live safety)

- **200 Hz push loop gains no blocking I/O.** Fingerprinting runs only in
  `FilepathResolver` worker threads; cache/identity/learned lookups stay in the
  `_start_anlz_worker` background worker and the load-time handler. `rb_state_reader.py` /
  `rb_memory.py` are untouched (byte-identical; that is the A7 gate).
- `ANLZ_PATH` enqueued before `TRACK_LOADED` — unaffected (no reader edits), must stay true.
- `StateManager` remains the only `DeckState` writer; `BridgeEvent`s immutable after
  creation (the new payload field is set at creation only).
- **Fail toward today, never block:** `track_fp == ""` (unreadable file, replayed old
  session, resolver fallback) reproduces today's exact behavior — cache miss ⇒ extraction
  path, identity ⇒ content_id/path key, learned ⇒ no-op guard, F2 ⇒ documented empty-plan
  degrade. Absent data reads as no signal, never a false event.
- **Strictly widening:** no scenario that hits today may become a miss (beatgrid component
  kept; only path/mtime dropped). The one transition exception is pre-migration legacy
  entries (Task 6.5) — bounded, disclosed, live-safe.
- Scripted matching, blackout/emergency masks, Static Override semantics, F2-off
  byte-identity: untouched.
- Read-only forever: rekordbox DB, ANLZ files, audio files. No secrets/IPs/device IDs in any
  commit; migration backups stay untracked.
- Deck coverage: `track_fp` rides the existing per-deck `TrackMetadata`, so decks
  active/mirror/3/4 inherit it uniformly — no per-deck special-casing.

## Part D - Tests

New file `tests/test_track_fp_move_invariance.py` (pure seam + tmp-file scenario tests —
`unittest`, stdlib only):

1. **Pure digest seam** (`track_fp_digest` — no disk): determinism; size participates;
   head-byte and tail-byte changes change the digest; `fp:` prefix shape.
2. **Move-scenario table (design §9) over tmp files** via `compute_track_fp`:
   A1 move to another dir ⇒ identical fp; A2 rename file+parent ⇒ identical; A3 byte-copy ⇒
   identical (tmp dir stands in for the USB volume — the real-volume run is the operator's);
   A4 changed bytes (head, tail, and size-only variants) ⇒ different fp; A5 `os.utime`
   mtime-only touch ⇒ identical; unreadable/missing/empty-path ⇒ `""`.
3. **Cache re-key** (extend the existing spectral-cache tests if present, else add here,
   using a tmp cache dir): fp-keyed put/get roundtrip; same fp from a DIFFERENT
   `audio_filepath` still hits (the move case, end to end); `track_fp=""` ⇒ miss both ways;
   legacy payload (no `track_fp`) with stale mtime ⇒ still evicted, fp payload with dead
   `audio_filepath` ⇒ NOT evicted; `_cache_key_from_fp(fp, grid_fp) == _cache_key(fp, grid)`.
4. **Identity keying** (extend `tests/test_led_identity_v2.py` — exists, it's in the
   led_govee contract's test list): `content_key` precedence fp > content_id > path;
   version-2 store loads; version-1 store still loads; version-3 ⇒ degraded read-only.
5. **LearnedStore parse-compat:** record/load roundtrip with an `fp:<sha1>:<beat>` key
   (guards the `rpartition` assumption).
6. **Migration** (import the tool's functions directly — no subprocess): fixture v4 entry +
  identity + learned stores in tmp dirs ⇒ re-keyed with payload fields preserved verbatim
   (include a `growl_centroid_frames` field in the fixture to pin the AWR-176 preservation);
   missing-file cache entry deleted; unresolvable identity entry kept; dry-run mutates
   nothing; second `--apply` run is a no-op (idempotence).
7. **A7 placement gate:** static test asserting `rb_state_reader.py` and `rb_memory.py`
   source contains none of `compute_track_fp`, `track_fp_digest`, `spectral_cache`,
   `IdentityStore`, `LearnedStore`.

Full suite `python3 -m unittest discover tests` must land at the documented known-red
baseline — zero NEW reds attributable to this round.

## Part E - Acceptance (definition of done)

- [ ] Task 0 contract additions in `change_contracts.yml` (+ `.md` mirror) and
      `python3 tools/check_agent_contracts.py` green.
- [ ] Tasks 1-6 implemented as specified; every `get_cached*`/`put_cached*`/`content_key`
      caller repo-wide compiles against the new required parameters
      (`grep -rn "get_cached\|put_cached\|content_key\|_cache_key" --include="*.py"` shows no
      stale signature).
- [ ] Design §9 acceptance rows A1-A5 + A7 demonstrated by the Part D tests; A6 (operator's
      real library: ≥ pre-migration hit rate, zero corrections lost, 301-entry before/after
      diff) demonstrated by running the migration tool `--apply` on the REAL stores in the
      same sitting as the deploy — report the printed counts verbatim.
- [ ] Hard checks green: `python3 tools/check_docs_metadata.py`,
      `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.
- [ ] Full suite at the known-red baseline; the per-contract named tests pass
      (`tests.test_led_identity_v2`, `tests.test_drop_presentation`,
      `tests.test_state_manager_drop_presentation`, `tests.test_filepath_resolver_hotcue_tags`).
- [ ] Contract `docs_update` closure — update or explicitly re-verify (bump
      `last_verified_commit`) every listed doc:
      **spectral_analysis:** `docs/research/spectral_audio_analysis_redesign.md`, `AGENTS.md`;
      **led_govee:** `docs/subsystems/led_govee.md`, `docs/status/feature_status_matrix.md`,
      `docs/status/support_matrix.md`, `docs/status/validation_matrix.md`,
      `docs/validation/hardware_validation_log.md`, `docs/validation/software_test_inventory.md`,
      `docs/status/active_work_registry.md`, `docs/architecture/palette_control_authority.md`,
      `docs/plans/active/streamdeck_palette_control_design_spec.md`,
      `docs/agents/task_playbooks/change_led_govee_behavior.md`;
      **drop_presentation:** `docs/subsystems/laser.md`,
      `docs/architecture/drop_presentation_authority.md` (+ the led_govee overlaps above);
      **core_bridge:** `docs/subsystems/core_bridge.md`,
      `docs/architecture/current_architecture.md`, `docs/architecture/runtime_invariants.md`;
      **rekordbox_readers (Task 0):** `docs/subsystems/rekordbox_readers.md`,
      `docs/status/support_matrix.md`, `docs/status/feature_status_matrix.md`,
      `docs/status/validation_matrix.md`, `docs/validation/software_test_inventory.md`,
      `docs/agents/task_playbooks/change_rekordbox_reader.md`.
- [ ] AWR-165 registry row updated; status language §10-compliant.
- [ ] No reader files, F2 files, or out-of-scope files in any diff.

## When You Finish

Report: changed files with per-task commits; test/check output (suite baseline attribution
included); the migration tool's real-store counts; anything marked `[assumed]` you had to
resolve differently.

Plain-language operator summary (chat, not a doc pointer): after this round the bridge
recognizes a track by what's IN the file, so moving, renaming, or copying it to a stick
keeps its lighting memory (colors, corrections, learned laser moments) and skips
re-analysis; a genuinely replaced file still re-analyzes fresh. One catch to say out loud:
run the migration tool once (with the USB stick plugged in, if its entries should carry
over) right when the new bridge first starts — skip it and nothing breaks, but each track's
first load re-analyzes once (~15 s to full-strength lighting for that track). Name the two
open taste calls that stay open (rekordbox export-transcode check §11.1, corrections-follow-
content default §11.3) and that everything here is software-tested only, hardware-unvalidated.

---

## Pre-handoff self-review (authoring-time, per the codex-spec checklist)

Adversarial pass — concrete failure modes attacked and how the spec prevents them:

1. **Silent always-miss from a missed caller** (worst failure: v4 cache quietly dead, live
   lighting degrades with no error): prevented structurally — `track_fp` is a REQUIRED
   positional on every re-keyed function, so a missed caller is a loud `TypeError`; Part E
   has the repo-wide caller grep.
2. **Migration can't derive keys** (payloads store no raw beatgrid): caught at authoring —
   the `_cache_key_from_fp` split exists precisely for this; migration never needs the grid.
3. **`fp:<sha1>:<beat>` breaks LearnedStore parsing:** checked — `rpartition(":")` splits on
   the last colon; pinned by test D.5.
4. **Old bridge reads a migrated identity store:** version-2 write hits the existing
   `version != 1` fail-closed branch ⇒ degraded read-only. Verified in current code, pinned
   by test D.4.
5. **AWR-176 fields dropped by migration:** payloads copied verbatim (never field
   allow-lists), pinned by the D.6 fixture.
6. **First post-upgrade mix without migration:** disclosed and bounded (Task 6.5) — one
   worker-thread re-extraction per track, live-safe, no data loss.
7. **Replayed old sessions:** `payload.get("track_fp", "")` ⇒ today's behavior.
8. Checklist items: claims labeled (A.1-A.5); verified at 57d514f (this document's cites,
   not the design's); pending-state — `track_fp` is load-time metadata with no same-tick
   output interplay; mode-transition cleanup — `TrackMetadata.clear()` single reset path
   (Task 2.2); third-party API — exact pyrekordbox pattern cited (A.3); authority-variable
   reuse — `meta.track_fp` is the one source, computed once in the resolver; pure seam —
   `track_fp_digest` (D.1); live safety — Part C; this section is item 9.

Residual `[unknown]`s carried from the design (implementation-phase, not paper-resolvable):
USB device-playback `content_id`/ANLZ-path behavior (design §6 — matters only for
provenance/beatgrid availability, not identity, once fp keys land); rekordbox
export-transcode setting (§11.1 — operator checks prefs once; affects S3 payoff only).
