---
doc_status: current
truth_level: spec
last_verified_commit: 9ead100
last_verified_date: 2026-07-09
validation_scope: >
  Design spec for move-invariant track identity: the same track must resolve to the same
  lighting identity (zone/palette, v4 spectral cache entry, per-track corrections, learned
  drops) no matter where the file lives — library reorganization, renamed folders, USB copy,
  different volume. Design only — no code, no runtime, no migration executed. All
  current-state claims verified against HEAD 9ead100 (code read + live on-disk store
  inspection); rekordbox-behavior claims about moves/exports are labelled assumed/unknown
  where live verification is still needed. Implementation gates on the executive.
work_status: design complete, awaiting operator taste calls (§11) — implementation parked behind the executive gate with the USB launcher bundle
relates_to: usb_bridge_launcher_design.md, lighting_engine_v2_f2_spec.md
---

# Track identity — move invariance (no path as primary key)

**Operator directive (verbatim, 2026-07-09): "i don't think we should hard code file paths,
we should plan to fix this" and "the bridge should recognize the files even if i move them."**

Plain meaning: today, some of the bridge's per-track memory is filed under the track's disk
path. Move the file and that memory is orphaned — the bridge re-analyzes from scratch and
forgets corrections. This design changes the filing key to something that travels with the
track itself, so moving/renaming/copying a file never loses its lighting identity, while a
genuinely *replaced* file (different audio content at the same name) still re-analyzes.

## 1. What exists today (all `confirmed` at 9ead100 unless labelled)

Per-track persistent state and its keys:

| Store | Key today | Location | file:line |
|---|---|---|---|
| Spectral v4 cache (716 entries live) | `sha1(realpath ⊕ mtime_ns ⊕ size ⊕ beatgrid_fp)` — **path-keyed** | `~/Library/Application Support/RBSS Bridge/spectral_cache/v4/` | `spectral_cache.py:330-345` |
| Spectral v3 cache (488 entries live) | same `_cache_key` function | `…/spectral_cache/` | `spectral_cache.py:48-125` |
| LED v2 identity store (301 entries live) | `content_id` (rekordbox DB id) first; `"path:"+realpath` fallback | `local/state/led_identity_v2.json` (cwd-relative; resolves to `~/local/state/…` today) | `led_identity_v2.py:133-136`, `led_models.py:87` |
| Laser-solo LearnedStore | `f"{content_id}:{round(beat)}"` — content_id only, guarded no-op when empty | `local/state/laser_solo_learned.json` | `drop_presentation.py:483-492`, guards `state_manager.py:2540,2790` |
| Scripted-track match | SSID (`SOUNDSWITCH_ID` ID3 tag) FIRST, exact-filepath fallback | in-memory | `state_manager.py:2455-2482` |
| F2 drop plans (spec, unimplemented) | per `(deck, load_gen)`, derived from the same identity worker | — | `lighting_engine_v2_f2_spec.md` Task 2 |

Where the inputs come from (`confirmed`):
- Rekordbox's memory never exposes the audio filepath — only title + ANLZ path
  (`rb_offsets.py:176-179`, `rb_state_reader.py:360,365`). The filepath is derived by
  `filepath_resolver.py` via three racing paths: ANLZ-UUID→DB lookup (returns the DB's
  registered `FolderPath` + `content_id`, `:263-321`), `lsof` on rekordbox's open files
  (returns the REAL mounted path, `:471-579`), and title-fuzzy DB lookup (`:397-469`). All
  three thread `content_id` into the `FILEPATH_RESOLVED` payload when the DB match succeeds
  (`:289,:337,:453`).
- `content_id` is rekordbox's own DB primary key (`djmdContent.ID` via pyrekordbox against
  `~/Library/Pioneer/rekordbox/master.db`, `config.py:20`). The bridge reads the LOCAL
  collection DB only — no code reads a USB device's exported DB.
- Re-analysis trigger today: mtime_ns + size are baked INTO the v4/v3 cache key, so a
  changed file gets a *new* key (old entry orphaned); a separate GC predicate
  (`_cache_file_is_stale_v4`, `spectral_cache.py:304-321`) unlinks orphans, invoked one-shot
  at startup behind two env flags (`__main__.py:909-927,1130`).
- The LED v2 IdentityStore has **no staleness trigger at all** — records freeze as
  `"measured"` forever; only manual correction or entry deletion changes them
  (`led_identity_v2.py:301-328`).
- **Tick-path placement (`confirmed`):** every cache/identity lookup happens once per track
  load in background daemon workers downstream of `FILEPATH_RESOLVED`
  (`state_manager.py:2393-2454,2236-2241`; cache calls `:244,:252,:298-316`). The 200 Hz push
  loop and the reader tick path contain zero cache/identity references (grep-verified). The
  directive's "key computation at load/plan time, never per-tick" is already the
  architecture; this design keeps it that way.

**Correction to the kickoff premise (`confirmed` from live data):** the LED v2 identity
store is NOT (filepath, beatgrid)-keyed — it is content_id-first, and all 301 live entries
are content_id keys (zero path-fallback entries). The genuinely path-keyed store is the
spectral cache. The deeper problem is that **content_id resolution is itself
path-dependent** (two of the three resolver paths match registered DB paths/UUIDs), and
content_id does not survive delete-and-reimport.

## 2. What breaks today, per move scenario

| # | Scenario | content_id | Spectral v4 cache | LED v2 identity + corrections | Verdict today |
|---|---|---|---|---|---|
| S1 | Move/rename managed by rekordbox (RB updates `FolderPath`; same DB row) | stable | **MISS** (realpath changed) → re-extracts an unchanged file | kept (content_id key) | violates directive (wasted re-analysis) |
| S2 | Move/rename OUTSIDE rekordbox, then re-import (new DB row) | **NEW id** | MISS | **orphaned** — corrections lost | violates directive |
| S3 | USB copy (RB device export), played from the stick | `unknown` — plausibly `""` (UUID/path match vs local DB unverified live) | MISS | falls to `path:`-fallback key → orphaned | violates directive |
| S4 | Replaced content at the same path (new master/re-export) | stable | new key → re-extracts | kept under content_id — **stale vs new audio** | re-analysis correct; identity staleness pre-existing |
| S5 | Same file, rekordbox re-analyzed (beatgrid changed) | stable | new key (beatgrid_fp) → re-extracts | kept | correct |

## 3. Key candidates, evaluated

Criteria (operator-directed): survives rekordbox relocation; keeps "replaced ⇒ re-analyze,
moved ⇒ don't"; collision risk; load-time cost (never per-tick).

| Candidate | Moves (S1/S2/S3) | Replaced (S4) | Collisions | Cost | Verdict |
|---|---|---|---|---|---|
| Path (status quo, cache) | fails all | correct via new key | n/a | free | **rejected as primary — operator directive** |
| `content_id` (RB DB id) | S1 yes; S2 NO (new row); S3 unknown/likely fails; meaningless on a foreign Mac (USB launcher scenario) | blind to content | none | free (already threaded) | keep as *alias/provenance*, not primary |
| SSID (`SOUNDSWITCH_ID` ID3, travels inside the file) | yes for any byte-preserving copy | blind to content; survives retagging `unknown` | none observed | free-ish (tag read exists, `filepath_resolver.py:121-145`) | keep as *alias*; absent on un-SS'd tracks — can't be primary |
| Beatgrid fingerprint (ANLZ-derived, `spectral_cache.py:324-327`) | yes IF ANLZ resolves | changes on re-analysis of identical audio → over-invalidates identity | low | free (already computed) | stays a *freshness component* of the spectral key only |
| **Audio content fingerprint (chosen)** | yes — property of the bytes | yes — new bytes ⇒ new key | negligible (§4) | one ≤2 MiB read + sha1 per track load, in the existing background worker | **primary key** |

## 4. Chosen design: content fingerprint as the one primary key

**The key.** `track_fp = "fp:" + sha1(size_bytes ⊕ first_1MiB ⊕ last_1MiB)` of the audio
file. Computed **once per track load** inside the resolver worker thread (all three resolver
paths already do file I/O there), shipped in the `FILEPATH_RESOLVED` payload and stored on
`TrackMetadata` alongside `content_id`/`soundswitch_id` — one computation, every consumer
downstream reads the field. On read failure: `track_fp = ""` and every consumer degrades
exactly as today's cache-miss path does (provisional/NEUTRAL identity, F2 no-op — fail
toward today's behavior, never block).

- **Move-invariant by construction:** the key is a property of the file's content, not its
  location, mtime, or DB registration. S1, S2, S3 all resolve to the same key.
- **Replace-sensitive:** a different master/encode differs in head, tail, and virtually
  always size ⇒ new key ⇒ re-analysis (S4 preserved). mtime is deliberately EXCLUDED — copy
  tools disagree about preserving it (`cp` doesn't, Finder does), and a false mtime change
  must not re-analyze a moved-not-replaced file.
- **Collision risk:** sha1 over size+head+tail across a personal library (~10³ tracks) —
  vanishing; two distinct real-world encodes with identical first/last MiB AND identical
  byte size do not occur in practice. Residual ceiling flagged honestly: a pathological
  mid-file-only edit with identical head/tail/size would collide; upgrade path if ever
  needed is a full-file hash knob, not built now.
- **Cost:** ≤2 MiB read + sha1 ≈ single-digit ms warm / tens of ms cold, once per track
  load, on the worker thread. The 200 Hz loop is untouched (§1 tick-path proof; the
  spectral-extraction path already reads the entire file on a miss, so this is strictly
  cheaper than one cache miss).

**Per-store key changes:**
- **Spectral v4 + v3 caches:** `_cache_key` material becomes
  `track_fp ⊕ beatgrid_fingerprint` (drop realpath/mtime/size — size already lives inside
  the fingerprint; beatgrid stays so S5 re-extracts as today). Same change for both cache
  generations — v3 is still live on the smart-drop path (`state_manager.py:298-316`).
- **LED v2 IdentityStore:** `content_key()` returns `track_fp` when non-empty; `content_id`
  and last-seen path move into the record body as provenance/alias fields. The `path:`
  fallback survives only for the `track_fp == ""` failure case (no file readable ⇒ nothing
  better exists). Freeze-forever semantics unchanged; under fingerprint keys a replaced
  file is a NEW key, so a fresh identity is derived and old corrections stay attached to the
  old content — semantically right (different audio ⇒ corrections may not apply) and it
  RESOLVES the S4 identity-staleness row for future replacements.
- **LearnedStore (laser solos):** key becomes `f"{track_fp}:{round(beat)}"` with the same
  empty-guard no-op behavior when `track_fp` is missing.
- **Scripted-track matching: NO CHANGE.** SSID-first matching is already move-invariant
  (the tag rides inside the file); the filepath fallback stays as-is.
- **F2 interaction (named, not edited):** F2 Task 2 derives per-`(deck, load_gen)` plans at
  identity time from this same worker; with fingerprint-keyed identity/cache, F2 plans
  inherit move-invariance automatically and its documented empty-plan degrade is unchanged.
  No edits proposed to `lighting_engine_v2_f2_spec.md`.

## 5. Migration (one-time, flagged per directive)

Both persistent stores need a **one-time remigration**; both are flagged as such:

- **Spectral caches (716 v4 + 488 v3 entries):** each payload already stores its
  `audio_filepath`. An offline one-shot tool (bridge idle, not the runtime): stat each
  stored path → file exists ⇒ compute `track_fp`, rewrite under the new key; file missing
  ⇒ leave for the existing eviction sweep. Estimated minutes of disk I/O, run once.
  Runtime afterwards reads/writes ONLY the new key — no dual-read code left behind.
- **LED v2 IdentityStore (301 entries) + LearnedStore:** resolve each `content_id` →
  `FolderPath` via the rekordbox DB (read-only), compute `track_fp` from the file, rewrite
  the key, keep `content_id` in the body. Unresolvable entries (missing file / stale DB row)
  are kept under their legacy key, not deleted — corrections are never destroyed by
  migration; they simply stop matching until the operator's file resurfaces (at which point
  a small `merge legacy` pass could unify — not built until needed).
- Store files gain a `schema_version` bump so a pre-migration bridge never misreads a
  post-migration store (fail closed to re-derive, never crash).

## 6. ANLZ handling for USB-resident tracks

`anlz_reader.py` consumes whatever ANLZ path rekordbox's memory exposes; for device playback
that is `assumed` to be the device-resident `PIONEER/USBANLZ/...` path — the reader is
path-prefix-agnostic and needs no change (`confirmed` the suffix-swap helper is the only
path logic, `anlz_reader.py:1114-1132`). Two `unknown`s carried, both resolvable only with a
live USB session (implementation-phase verification, not paper):
- whether the memory-exposed ANLZ path for device playback actually points at the stick;
- whether `_db_lookup_by_anlz`'s UUID match succeeds against the local DB for device copies
  (with fingerprint keys this stops mattering for identity — it only affects `content_id`
  provenance and beatgrid availability at resolve time; the runtime ANLZ read at plan time
  still supplies the beatgrid, `state_manager.py:226-285`).

## 7. Live safety / runtime invariants

- No new I/O on the 200 Hz push loop or reader ticks — fingerprint computation and all key
  lookups stay in the existing load-time background workers (§1 placement, preserved).
- Absent data reads as no signal: fingerprint failure ⇒ empty key ⇒ today's exact degrade
  (provisional identity, F2 no-op), never a false event — matching the `spectral_analysis`
  contract's forbidden-assumption language.
- v4 code still never modifies the rekordbox DB, ANLZ files, or audio files (read-only
  fingerprinting; the DB is touched read-only during migration).
- Mid-set behavior is unchanged in every scenario where today succeeds; the design only
  ADDS hit cases (moved files) and never converts a today-hit into a miss (the beatgrid
  component is kept, the path/mtime components are dropped — strictly widening).

## 8. Affected modules + change contracts

| Change | Modules | Governing contract | Contract action needed |
|---|---|---|---|
| Fingerprint computation + payload field | `filepath_resolver.py`, `models.py`, `state_manager.py` | `drop_presentation` (owns filepath_resolver), `core_bridge` (models/state_manager) | none — covered |
| Spectral key change + migration tool | `spectral_cache.py` (+ offline tool) | `spectral_analysis` | none — covered |
| IdentityStore re-key | `led_identity_v2.py`, `led_config.py`, `led_models.py` | `led_govee` | none — covered |
| LearnedStore re-key | `drop_presentation.py` | `drop_presentation` | none — covered |
| ANLZ (no code change; claims only) | `anlz_reader.py` | **NONE — governance gap** | `anlz_reader.py` appears in ZERO contracts' code_globs (grep-verified); add it to `rekordbox_readers` before implementation. `rekordbox_readers` also omits `filepath_resolver.py` — same fix. |

Per AGENTS.md §7, the contract-gap closure is a REQUIRED first task of any implementation
spec for this design.

## 9. Falsifiable acceptance criteria (the move-a-file table)

Each row must be demonstrated with a real file and the actual stores (software-level; no
hardware needed):

| # | Action | Required result |
|---|---|---|
| A1 | Compute key; move the file to another folder on the same disk; recompute | identical `track_fp`; same v4 cache entry hits; same identity record (zone + correction intact) |
| A2 | Rename the file and its parent folder; recompute | identical key, same hits |
| A3 | Byte-identical copy onto a USB volume (`/Volumes/...`); recompute | identical key, same hits |
| A4 | Replace the file's content (different encode, same name); recompute | DIFFERENT key; v4 re-extracts; fresh identity derived; old record untouched under old key |
| A5 | Touch mtime only (`touch` — moved-not-replaced proxy) | identical key; NO re-analysis |
| A6 | Post-migration sweep | ≥ the pre-migration hit rate on the operator's real library; zero corrections lost (301-entry before/after diff) |
| A7 | Static check | no fingerprint/cache/identity call sites reachable from `RBStateReader` tick methods or the push loop (test seam: pure function `track_fp(path)` + grep-gate, per the codex-spec pure-seam rule) |

## 10. Explicitly out of scope

- Hardening `content_id` resolution itself (making the DB lookups path-independent) — with
  fingerprint keys it demotes to provenance; not worth its complexity now.
- Reading USB device-export DBs (`.pdb`), foreign-Mac library merging, or any rekordbox DB
  writes (NEVER — standing rule).
- The USB launcher bundle mechanics (sibling doc `usb_bridge_launcher_design.md`); this
  design is a dependency of that bundle's "operate normally on a foreign Mac" bar but lands
  independently and helps the home rig too (S1/S2 are pure library-reorg wins).
- Building the full-file-hash knob, alias-merge tooling, or per-tick anything.

## 11. Operator taste calls + open unknowns (flagged, not decided)

1. **Rekordbox export settings (`unknown`, needs one look at the operator's RB prefs):** if
   device export transcodes audio (an RB option), USB copies are NOT byte-identical ⇒ new
   fingerprint ⇒ fresh analysis on the stick copy (corrections don't follow). If exports are
   plain copies (default), S3 passes as designed. If transcoding is on, the fallback is the
   SSID alias (does the tag survive RB's transcode? `unknown`) — decide only if this
   actually bites.
2. **Migration timing:** the one-shot remigration runs with the bridge idle (minutes of disk
   reads over ~1.2k cache entries + 301 identity rows). Operator picks when.
3. **Corrections vs replaced content:** design says a replaced file starts a fresh identity
   (old corrections stay filed under the old content). Veto if corrections should follow the
   NAME rather than the CONTENT — that would need a different (path-shaped) rule and cuts
   against the directive.
