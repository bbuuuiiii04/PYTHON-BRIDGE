# Laser Personality — Per-Track Lighting Profiles (REVISED v2)

**Status (2026-05-20):** Phases 0–4 and 6 implemented (resolver +
per-personality timing + scripted-track guard + atomic apply + Laser Pad
resolver UI + live resolver reload polish). Phase 5 live tuning still requires
a real set or rehearsal. Phases 7+ remain deferred.

## Context

The bridge already supports multiple `LaserPersonality` profiles in `laser_director.example.json` and can swap them via `set_personality()`. What's missing is **automatic selection per track** plus **per-personality timing** (the global pre-drop blackout, post-drop hold, and breakdown restore length should vary by genre).

There is an **existing Phase 9 plan in the repo** at `rb_ss_bridge_v2/docs/plans/phase9_personality_resolver_plan.md` that proposes a different design: Rekordbox **Genre tag** → MyTag → BPM, with sticky runtime override, and routing kept at top-level config (not per-personality).

The operator (you) has overridden several of those choices in conversation:
- Signal must be **PER GENRE playlist folder** in Rekordbox, not the Genre tag.
- **No manual override** — resolver is authoritative.
- **MyTag deferred** to a later phase.
- **Per-personality timing fields** are new in this design (Phase 9 had none).

Phase −1 below makes the supersession explicit before any code is cut.

Scope: **unscripted tracks only.** Scripted tracks already have full SoundSwitch shows; personality is not invoked for them.

---

## Phase −1 — Doc supersession (BLOCKING, do first)

Before any code change, **replace** `rb_ss_bridge_v2/docs/plans/phase9_personality_resolver_plan.md` with the current plan's design, calling out the divergence in a "Supersedes prior design" section at the top:

- **Signal source:** PER GENRE playlist folder (not Rekordbox Genre tag).
- **Mapping shape:** per-personality `aliases` list (not top-level `personality_routing.genre_map`).
- **Runtime override:** **removed** — resolver is authoritative, no `/laser/personality/clear`, no sticky override carry-through.
- **MyTag:** deferred to a later phase (slot only, not wired).
- **New: per-personality timing fields** (`pre_drop_blackout_beats`, `post_drop_hold_beats`, `breakdown_default_restore_beats`).
- **Local-config migration required:** add new fields to existing `config/laser_director.json` (operator's local copy is git-ignored — see Section 7).

If you (Brandon) want to keep Phase 9's Genre-tag path as a *fallback* signal between PER GENRE playlist and BPM, say so before Phase 0 begins. Default in this plan: no Genre-tag layer.

---

## 1. Resolver Design

**Three layers. First match wins. Resolve once per track, lock for the track.**

| Layer | Source | Behavior |
|---|---|---|
| 1. (future) MyTag | RB DB `DjmdSongMyTag` → `DjmdMyTag.Name` | Designed slot, not wired in v1. |
| 2. PER GENRE playlist | RB DB: child playlists of the folder named "PER GENRE". | Match each playlist name (case-insensitive, word-boundary) against the union of all personalities' `aliases`. **Longest matching alias across all personalities wins.** |
| 3. BPM fallback | File BPM from RB DB (not live pitch-adjusted) | **Ordered first-match wins.** Personalities are walked in an operator-defined order (top-level `bpm_priority: [name, name, ...]` list in config; first personality whose `bpm_band_min <= bpm < bpm_band_max` matches wins). Overlaps are **allowed** and logged at INFO at config load time (e.g. `[CONFIG] bpm overlap: dubstep[140-155] and hard_techno[140-160]`). Operator owns disambiguation by ordering. Personalities absent from `bpm_priority` are not BPM-eligible. |
| 4. Default | — | `default_personality` from config (House). |

**Resolver firing point:** **`_on_filepath_resolved` in `state_manager.py:1032`, after the scripted-vs-unscripted determination at lines 1089–1144.** Specifically, in the `scripted_id is None` branch where `Ev.SCRIPTED_CLEAR` is enqueued (line 1138). Track-load (`_on_track_loaded` at line 929) is too early — `content_id`, `bpm`, and `filepath` are not yet populated on `d.meta`.

**Master-change re-resolution:** in `_on_master_changed`, if the new master deck already has populated metadata (`d.meta.content_id > 0`) and was previously resolved as unscripted, re-invoke the resolver for that deck.

**Personality activation timing:** resolver writes `pending_personality` to `LaserDirector` immediately. Active personality only swaps **at the next phrase boundary on the active deck**, using a pending-application mechanism. **This mechanism is new code, not a carry-over from Phase 9** (Phase 9's plan describes it but it was never implemented — `LaserDirector` currently has neither `queue_personality_change` nor `_pending_personality`). Idle = apply immediately.

**Boundary apply must update three components atomically** (in one `_apply_pending_personality(ctx)` call):
1. `LaserDirector` — internal personality state.
2. `LaserSceneExecutor.set_personality()` at `laser_executor.py:58` — resets role cursors and cooldowns so the new personality's bank choices take effect.
3. `StateManager` timing cache — `_sp_drop_window`, `_sp_post_drop`, `_sp_transition_window`, `_sp_breakdown_default_restore` recomputed from the newly-active personality (see Section 4).

If these update independently, the active scene bank and SmartPhrasing timing can diverge for one or more ticks. Apply path is a single function that calls all three.

**BPM zone with no `bpm_priority` match:** falls to default + log line `[PERSONALITY] ... rule=default reason=bpm_no_match`.

**Cache strategy:** at bridge startup, query RB DB once to build `{content_id → frozenset(playlist_names)}` covering all tracks in any PER GENRE child playlist (note: `content_id` is **`str`** everywhere — current `TrackMetadata.content_id` is a string and `filepath_resolver.py` stores `str(c.ID)`). On `_on_filepath_resolved`, `StateManager` calls `playlist_cache.get(meta.content_id)`. **If `None`, `StateManager` calls `playlist_cache.refresh()` once and retries the `get`.** `PersonalityResolver.resolve()` is pure and never does I/O — `StateManager` orchestrates miss → `playlist_cache.refresh()` → retry, then passes `playlists` and `bpm` to `resolve()`. No periodic refresh.

**Log line shape (per track resolution):**
```
[PERSONALITY] deck=<n> content_id=<id> file="<short>" → <Personality> (rule=<playlist|bpm|default>, matched="<alias|band>", file_bpm=<n>)
[PERSONALITY] deck=2 content_id="12345" file=".../track.mp3" → Trap (rule=playlist, matched="trap", file_bpm=90 ⚠ outside band 134-155)
[PERSONALITY] deck=1 content_id="67890" file=".../other.wav" → Hard Techno (rule=bpm_range_match, matched="140-160", file_bpm=145)
[PERSONALITY] deck=1 content_id="11111" file=".../some.wav" → House (rule=default, file_bpm=118 no band match)
```
The ⚠ marker is a warning — playlist always wins, mismatches just surface. With default `bpm_priority` order `[hard_techno, dubstep, trap, bass_house, tech_house, house]`, BPM 145 resolves to Hard Techno first (its band 140–160 is reached before Dubstep's 140–155).

---

## 2. Data Model Changes

### `LaserPersonality` (`rb_ss_bridge_v2/laser_models.py`)

Add these fields:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `aliases` | `tuple[str, ...]` | `()` | Playlist-name keywords. Edited in UI. |
| `bpm_band_min` | `float` | `0.0` | BPM fallback lower bound (inclusive). |
| `bpm_band_max` | `float` | `0.0` | BPM fallback upper bound (exclusive). `0.0 == 0.0` disables BPM fallback for this personality. |
| `pre_drop_blackout_beats` | `int` | `4` | Beats before smart-drop crossing to fire blackout. Replaces global `SMART_DROP_LOOKAHEAD_BEATS` for this personality. |
| `post_drop_hold_beats` | `int` | `8` | Beats to hold post-drop scene after a drop crossing. **Replaces `minimum_scene_hold_beats` as the post-drop hold source.** See Section 3. |
| `breakdown_default_restore_beats` | `int` | `64` | Fallback restore distance used by `_build_breakdown_segments()` when no later buildup/drop exists. Replaces global `SMART_BREAKDOWN_DEFAULT_DURATION_BEATS` for this personality. **Renamed from earlier draft's `breakdown_hold_beats` — name now matches semantics (fallback distance, not minimum hold).** |

Existing fields stay: `phrase_interval_beats`, `minimum_scene_hold_beats` (see Section 3 — semantics narrowed), `normal_changes_only_on_phrase_boundary`, `buildup_lookahead_beats`, `allow_high_impact`, all `*_scene` / `*_bank` fields.

### `LaserConfig` (`laser_config.py:87` — not `laser_models.py`)

Add one top-level field: `bpm_priority: tuple[str, ...] = ()` — operator-ordered personality names for BPM fallback resolution.

**Semantics of `bpm_priority`:**
- Personalities **listed** in `bpm_priority` are walked in order at BPM-fallback time. First whose band contains the BPM wins.
- Personalities **absent** from `bpm_priority` are **not BPM-eligible**, even if they have a non-zero band.
- Defaults to **`()`** for old/migrating configs. **Effect: BPM fallback is disabled entirely until the operator adds names.** This is the safe default — no surprise activations from BPM matching a personality the operator hadn't yet wired into the priority list. Bridge falls straight to `default_personality` on no playlist match.
- Validator (hard error): every name in `bpm_priority` must exist in `cfg.personalities`.

Aliases live on each personality (operator preference). The resolver builds its flat alias index at construction time from `cfg.personalities`.

### `TrackMetadata` (`models.py`)

No new fields required for v1 (resolver uses `content_id` and `bpm` which already exist). MyTag slot will need `mytags: tuple[str, ...]` added later — flag this as a Phase 7 prerequisite.

---

## 3. `post_drop_hold_beats` vs `minimum_scene_hold_beats`

**Current behavior** (`laser_director.py:410-424`): post-drop hold uses `self._minimum_scene_hold_beats`. This single field is overloaded for both "normal scene minimum hold" and "post-drop hold duration."

**New behavior:**
- `post_drop_hold_beats` (new) drives the post-drop hold check at `laser_director.py:413`. Code change: `self._minimum_scene_hold_beats` → `self._post_drop_hold_beats` in that block.
- `minimum_scene_hold_beats` (existing) is narrowed to its other use sites — normal scene minimum hold only. Keep the field; just stop using it for post-drop.

When `set_personality_config(cfg)` is called on `LaserDirector`, both `self._minimum_scene_hold_beats` and `self._post_drop_hold_beats` get re-cached from the active personality.

---

## 4. Timing Wiring Through `SmartPhrasingSnapshot`

The three cached SmartPhrasing constants in `state_manager.py:375-379`:
```
self._sp_drop_window: float = float(SMART_DROP_LOOKAHEAD_BEATS)
self._sp_post_drop: float = 8.0
self._sp_transition_window: float = float(SMART_DROP_LOOKAHEAD_BEATS)
```
must be **derived from the currently active personality**, not from globals.

**Wiring:**

1. Add a personality-config callback path. When `LaserDirector.set_personality_config(cfg)` runs, it should notify `StateManager` (or `StateManager` reads from a single `get_active_personality_config()` method on the director).
2. On every personality apply, `StateManager` recomputes:
   ```
   self._sp_drop_window      = float(active.pre_drop_blackout_beats)
   self._sp_transition_window= float(active.pre_drop_blackout_beats)
   self._sp_post_drop        = float(active.post_drop_hold_beats)
   ```
3. `_build_breakdown_segments()` at `state_manager.py:1906` currently uses the module-level `SMART_BREAKDOWN_DEFAULT_DURATION_BEATS`. Change to read `self._active_personality.breakdown_default_restore_beats` (cache as `self._sp_breakdown_default_restore`). Recomputed alongside the three above on personality apply.
4. Keep the global constants in `config.py` as **fallback defaults** for use when no active personality is set (early startup, before any track loads).

Cache invalidation: `_clear_phrase_segment_cache(deck)` already runs on `_on_filepath_resolved` and elsewhere. Also call it whenever active personality changes so that breakdown segments rebuild with the new fallback restore distance.

---

## 5. Resolver Wiring in `StateManager`

- **Two new slots:** `self._personality_resolver: Optional[PersonalityResolver] = None` and `self._personality_playlist_cache: Optional[PlaylistCache] = None`. **Do not reuse `self._resolver`** — that's the `FilepathResolver` attached at `state_manager.py:1027` via `attach_resolver()`.
- New attach methods: `attach_personality_resolver(resolver)` and `attach_personality_playlist_cache(cache)`.
- New helper: `_resolve_personality_for_deck(deck: int, meta: TrackMetadata)`:
  - `playlists = self._personality_playlist_cache.get(meta.content_id)`
  - If `playlists is None`: `self._personality_playlist_cache.refresh()`, then `playlists = self._personality_playlist_cache.get(meta.content_id) or frozenset()`.
  - `resolution = self._personality_resolver.resolve(playlists=playlists, bpm=meta.bpm)` — note: `default` is **not** passed; it's resolver constructor state.
  - Looks up the resolved `LaserPersonality` via `self._laser_personality_provider(resolution.name)`. If missing, log + skip.
  - Calls `director.queue_personality_change(resolution.name, personality_cfg)`.
  - Logs the `[PERSONALITY]` line per Section 1.
- **Per-deck eligibility flag:** new `self._personality_eligible_deck: dict[int, bool]` on StateManager (default `False` per deck).
  - Set to `True` in the SCRIPTED_CLEAR branch at line 1136 (after `Ev.SCRIPTED_CLEAR` is enqueued).
  - **Reset to `False` in `_on_track_loaded` at line 929** (alongside `d.meta.clear()` and `d.scripted_id = 0`). New track load = unknown scripted/unscripted state until next FILEPATH_RESOLVED.
  - Also reset to `False` in the SCRIPTED_ARM branch (line 1121-1135) for symmetry.
  - Checked in `_on_master_changed`: only re-invoke resolver if `self._personality_eligible_deck.get(new_active_deck, False) is True`.

Relying solely on `scripted_id == 0` or `meta.content_id != ""` is too implicit — `_on_filepath_resolved` may not have fired yet for the new master, in which case those fields are stale from a prior load. The explicit eligibility flag tracks the exact "we have run resolver-eligible determination on this deck" lifecycle.

- **Invocation sites:**
  - `_on_filepath_resolved`, in the `else` branch at line 1136 (SCRIPTED_CLEAR), immediately after enqueuing the event AND setting `_personality_eligible_deck[deck] = True`.
  - `_on_master_changed`, when `_personality_eligible_deck[new_active_deck]` is `True` AND `d.meta.content_id` is non-empty.

`PersonalityResolver.resolve()` is **pure** (no I/O — all DB queries happen in `PlaylistCache.refresh()`). Safe to call from the event-handling thread.

---

## 6. New File: `personality_resolver.py`

Two-class split so purity is unambiguous:

```
ResolutionReason = Literal["playlist_match", "bpm_range_match", "default"]

@dataclass(frozen=True)
class PersonalityResolution:
    name: str
    reason: ResolutionReason
    matched: str  # alias text, "min-max" for BPM, or "" for default

class PersonalityResolver:
    """PURE. No I/O. Safe for any thread."""
    def __init__(
        self,
        *,
        alias_index: Mapping[str, str],          # canonical alias → personality (lookup sorts longest-first)
        bpm_priority: Sequence[str],             # personality names in BPM-fallback order
        bpm_bands: Mapping[str, tuple[float, float]],  # personality → (min, max), exclusive max
        known_personalities: Set[str],
        default: str,
    ) -> None: ...

    def resolve(
        self,
        *,
        playlists: frozenset[str],   # canonicalized playlist names for this track
        bpm: float,
    ) -> PersonalityResolution: ...

class PlaylistCache:
    """I/O-bearing. Owns the RB DB query."""
    def __init__(self, db_path: Path) -> None: ...
    def get(self, content_id: str) -> Optional[frozenset[str]]: ...   # None = miss
    def refresh(self) -> int: ...   # re-queries RB DB; returns track count
```

**Resolve flow in `StateManager`:**
```
playlists = cache.get(meta.content_id)
if playlists is None:
    cache.refresh()
    playlists = cache.get(meta.content_id) or frozenset()
resolution = resolver.resolve(playlists=playlists, bpm=meta.bpm)
```

`PlaylistCache` queries via the `pyrekordbox.db6.Rekordbox6Database` pattern in `filepath_resolver.py:244-300`. Locates folder by name (`PER GENRE`), enumerates child playlists, builds `{content_id_str → frozenset(canonical_playlist_names)}`. **`content_id` is `str` everywhere** to match existing `TrackMetadata.content_id`.

DB-unavailable at startup: log + start with empty cache. First cache-miss triggers retry refresh; if still failing, falls to BPM/default.

Pure unit tests in `tests/test_personality_resolver.py` cover `PersonalityResolver` only (no DB). `PlaylistCache` tests deferred / use mocked pyrekordbox.

---

## 7. Default Personalities (ship 6, all duplicated from House)

Ship via `rb_ss_bridge_v2/config/laser_director.example.json`. The operator's local `config/laser_director.json` is git-ignored; the watcher copies the example only when the local file is missing.

**Migration for the existing local config:**

- On startup, if `laser_config.py` loads the local config and any personality is missing the new fields, log `[CONFIG] personality "<name>" missing field "<X>" — using default <value>`. Use defaults from the table in Section 2 — bridge runs.
- Same for missing `aliases` (defaults to `()` → personality only reachable via BPM fallback or as default).
- **Operator action required:** manually merge the new fields from `laser_director.example.json` into local `config/laser_director.json`, or delete local and let the watcher copy the example. Document this in the Phase 1 PR description.

**Per-personality defaults** (applied in `laser_director.example.json`):

| Personality | Aliases | BPM band | phrase_interval | min_scene_hold | buildup_lookahead | pre_drop_blackout | post_drop_hold | breakdown_default_restore | phrase_boundary_only |
|---|---|---|---|---|---|---|---|---|---|
| **House** (default) | `house` | 120–130 | 32 | 0 | 32 | 4 (1 bar) | 8 | 64 | false |
| **Dubstep** | `dubstep`, `bass` | 140–155 | 32 | 16 | 16 | 16 (4 bars) | 16 | 64 | **true** |
| **Trap** | `trap` | 134–155 | 32 | 8 | 8 | 8 (2 bars) | 8 | 32 | false |
| **Hard Techno** | `hard techno` | 140–160 | 16 | 4 | 8 | 8 (2 bars) | 4 | 32 | false |
| **Bass House** | `bass house` | 126–140 | 32 | 8 | 16 | 8 (2 bars) | 12 | 64 | false |
| **Tech House** | `tech house` | 125–138 | 32 | 16 | 32 | 4 (1 bar) | 8 | 64 | false |

Aliases conservative per your call: Hard Techno does not match plain "techno"; Dubstep does not match "riddim".

**BPM band overlaps are allowed and resolved by `bpm_priority` order.** Ship default order favoring higher-energy genres at boundary BPMs:

```json
"bpm_priority": ["hard_techno", "dubstep", "trap", "bass_house", "tech_house", "house"]
```

At BPM 145 (matches Hard Techno [140–160], Dubstep [140–155], Trap [134–155]) → Hard Techno wins. Operator can re-order in config to change disambiguation. Overlaps log at INFO at config load:
```
[CONFIG] bpm-overlap personalities=hard_techno[140-160],dubstep[140-155] zone=140-155
```

---

## 8. UI Changes — Frontend Heavy

Most personality UI work lives in the frontend assets, not just the Python web layer:

- `rb_ss_bridge_v2/tools/laser_pad_assets/pad.js` — Alpine.js-style `laserPadApp()` data model. Add `aliasesDraft`, `bpmBandDraft`, and `timingExtraDraft` (post_drop_hold_beats, pre_drop_blackout_beats, breakdown_default_restore_beats) per-personality.
- `rb_ss_bridge_v2/tools/laser_pad_assets/index.html` — Add an Aliases section to each personality tab, a BPM band input pair, and the three new timing inputs. Add a resolver test panel at the top of the personality area (input: playlist name, output: which personality + which alias matched).
- `rb_ss_bridge_v2/tools/laser_pad_web.py` — Backend may already accept these via `/api/draft` if it patches the JSON directly. Verify the patch path covers nested personality fields; if not, extend the validator path.
- `rb_ss_bridge_v2/tools/laser_config_ops.py` — Add helper for alias-uniqueness check across all personalities.

**Validation rules:**

Hard errors (enforced in `laser_config.py`, fail config load via `LaserConfigResult.errors`):
- Cross-personality duplicate aliases.
- BPM band `min >= max` (except both `0.0`, which disables BPM fallback for that personality).
- `bpm_priority` references unknown personality name.

Soft warnings (UI-visible, via `validate_config_data()` in `tools/laser_config_ops.py` — append to the existing `softDuplicates` / warnings channel):
- Empty aliases on a non-default personality → "only reachable via BPM fallback or as default."
- Personality has BPM band but is absent from `bpm_priority` → "BPM band ignored (not in priority list)."
- BPM band overlap with another personality → "overlap zone X-Y; first in `bpm_priority` wins."

Log-only at config load (no UI surface, just `[CONFIG]` log lines):
- Missing per-personality fields on local-config load (uses defaults).
- BPM-overlap zone summary on each overlap pair.

Aliases case-insensitive, whitespace-trimmed at canonicalization time (both at config validation and at resolver-construction time).

---

## 9. Personality Switch Behavior

- Resolver fires on `_on_filepath_resolved` → records `pending_personality` for that deck.
- On master change → if new master has resolved metadata, re-invoke; record `pending_personality`.
- `LaserDirector._apply_pending_personality(ctx)` runs at top of `_decide()`. Applies pending iff (a) at a phrase boundary, OR (b) idle (no track loaded). **Also ignores pending while `ctx.lighting_mode == "scripted"`** — secondary guard at apply-time, in addition to the primary guard at resolver-invocation site.
- **One-time snapshot duplication** of personalities (no live-inherit). Already true with the current `LaserPersonality` shape.

### Removal of manual *runtime* override path (config-editing UI untouched)

The current code has three pieces of **runtime live-activation** control that must be removed for the resolver to be authoritative:

- `runtime_status.py:228` — runtime command path for setting active personality at runtime.
- `models.py:219` — `Ev.LASER_SET_PERSONALITY` event type.
- `state_manager.py:866` — handler for `Ev.LASER_SET_PERSONALITY`.

**Out of scope for removal — DO NOT touch:**
- The Laser Pad header personality selector. That control changes `_pad_meta.ui.last_personality` (which personality is being *edited* in the UI), not which personality is *live*. Removing it would break config editing entirely.
- Any other config-editing UI that scopes operations to a chosen personality.

**Decision:** **Runtime command path + any OSC route for live personality activation are removed.** `Ev.LASER_SET_PERSONALITY` event type and handler **retained for internal/test use only** — emitting it from tests still works, but no external surface (OSC, web UI live-activation, runtime command) emits it. Phase 3 implementation must:
- Remove or comment out any OSC registration that triggers live activation in `__main__.py`.
- Remove the runtime-command path in `runtime_status.py:228`.
- Add a log warning if `Ev.LASER_SET_PERSONALITY` is observed from a non-test source (`ev.source` not in a small allowlist).
- Audit the web UI before touching it: distinguish "edit-target selector" (KEEP) from "live activate" controls (REMOVE).
- Update any existing tests that emit `Ev.LASER_SET_PERSONALITY` to clarify they're testing the internal path.

If any removal breaks unrelated functionality during Phase 3, surface immediately rather than papering over.

---

## 10. Hot Reload — Resolver Rebuild

`__main__.py` `_on_laser_config_reload` rebuilds the personality resolver on
laser-config reload, reattaches the updated personality provider, and reapplies
the active personality config when it still exists.

Alias edits via the web UI:
1. Save to `laser_director.json` (atomic write).
2. Existing reload flow picks up the config change.
3. New aliases and BPM bands take effect without a bridge restart.

---

## 11. Phased Implementation

Each phase is shippable on its own. Phase −1 is blocking.

### Phase −1 — Replace `docs/plans/phase9_personality_resolver_plan.md`
Per Section above. Hand-off doc, no code.

### Phase 0 — `LaserPersonality` field additions (no behavior change)
- `laser_models.py`: add the six new fields with defaults.
- `laser_config.py`: parse + validate new fields. Alias-uniqueness check.
- Existing config loads unchanged (new fields default).
- Validate: `python3 -m unittest tests.test_laser_config` green.

### Phase 1 — Ship 6 default personalities in example config + migration log
- Add Dubstep, Trap, Hard Techno, Bass House, Tech House to `config/laser_director.example.json` with values from Section 7's table.
- `laser_config.py` logs `[CONFIG] personality "<name>" missing field "<X>"` for any missing field on local-config load.
- Validate: example config loads; missing-field log fires on a synthesized old-shape config.

### Phase 2 — Per-personality timing wired through `SmartPhrasingSnapshot` + `LaserDirector`
- `state_manager.py:375-379` constants become personality-derived. Add `_active_personality_for_timing` cache + `_recache_personality_timing()` helper, called on `set_personality_config` callback.
- `state_manager.py:1906` `_build_breakdown_segments` uses `self._sp_breakdown_default_restore` instead of `SMART_BREAKDOWN_DEFAULT_DURATION_BEATS`.
- `laser_director.py:413` post-drop hold reads `self._post_drop_hold_beats` instead of `self._minimum_scene_hold_beats`.
- `LaserDirector.set_personality_config(cfg)` caches both `_minimum_scene_hold_beats` (normal scenes) and `_post_drop_hold_beats` (post-drop).
- Validate by exercising the atomic apply path that updates all three components (LaserDirector + LaserSceneExecutor + StateManager timing cache) — either drive through the same internal path Phase 3 will use, or explicitly call `director.set_personality(...)`, `director.set_personality_config(...)`, `executor.set_personality(...)`, and `state_manager._recache_personality_timing()` in a test harness. **Do not rely on a bare `set_personality()` call** — it only updates the name field.

### Phase 3 — Resolver + integration (`personality_resolver.py` + `StateManager` wiring)
- New `personality_resolver.py` containing **both** `PersonalityResolver` (pure) and `PlaylistCache` (I/O-bearing).
- Two new slots on `StateManager`: `self._personality_resolver: Optional[PersonalityResolver] = None` and `self._personality_playlist_cache: Optional[PlaylistCache] = None`.
- Two new attach methods: `attach_personality_resolver(resolver)` and `attach_personality_playlist_cache(cache)`. (Or one attach taking both — operator choice; keep names explicit so the FilepathResolver slot isn't reused.)
- Resolver invoked from `_on_filepath_resolved` in the SCRIPTED_CLEAR branch at line 1136. Also from `_on_master_changed` when new master has resolved metadata.
- Resolve flow: `playlists = cache.get(meta.content_id); if None: cache.refresh(); playlists = cache.get(meta.content_id) or frozenset(); resolution = resolver.resolve(playlists=playlists, bpm=meta.bpm)`.
- Resolver invokes `LaserDirector.queue_personality_change(name, cfg)`.
- `LaserDirector._apply_pending_personality(ctx)` runs at top of `_decide()`, with apply-time scripted guard.
- `__main__.py` instantiates the cache + resolver after config load, attaches both to StateManager.
- Manual-override removal: see Section 9.
- `[PERSONALITY]` log lines per Section 1.
- Validate per Phase 3 verification below.

### Phase 4 — UI: aliases editor + BPM band + new timing fields + resolver test panel
- `pad.js` + `index.html` extensions per Section 8.
- `/api/draft` validates aliases (uniqueness, non-empty strings).
- Resolver test panel hits new `/api/resolve-test?playlist=<name>` endpoint in `laser_pad_web.py`.
- Implemented.

### Phase 5 — Tune defaults live
- Real-set or rehearsal run-through. Iterate on per-personality timing values.
- Pending live operator validation.

### Phase 6 — Polish
- Live resolver rebuild on `_on_laser_config_reload` (replace `restart_required` log).
- "Personalities using this scene" view in the UI.
- Missing-scene warnings per personality.
- Cache-health log line ("PER GENRE cache: 412 tracks across 6 playlists").
- Implemented.

### Phase 7 (deferred) — MyTag layer
- Add `mytags: tuple[str, ...]` to `TrackMetadata` in `models.py`.
- Extend `filepath_resolver.py` `_db_lookup_by_anlz` and `_db_lookup` to populate mytags (mechanism described in the existing Phase 9 plan, lines 162–169 — that part is reusable verbatim).
- Add MyTag → personality map (top-level config, since MyTags aren't naturally a per-personality alias). Resolver gains layer 1 above PER GENRE playlist.

### Phase 8 (deferred) — Static accent looks
- Decide firing rules (drop hit, buildup peak, breakdown entry).
- Add per-personality accent scene references.
- Wire executor to fire accents at chosen events.

---

## 12. Critical Files

| File | Phase | Action |
|---|---|---|
| `rb_ss_bridge_v2/docs/plans/phase9_personality_resolver_plan.md` | −1 | Replace with this design |
| `rb_ss_bridge_v2/laser_models.py` | 0 | Add 6 fields to `LaserPersonality` dataclass |
| `rb_ss_bridge_v2/laser_config.py` (LaserConfig at :87) | 0,1 | Add `bpm_priority` to `LaserConfig`; parse + validate new fields; alias-uniqueness; missing-field logging |
| `rb_ss_bridge_v2/runtime_status.py` (line 228) | 3 | Remove runtime manual personality command |
| `rb_ss_bridge_v2/models.py` (line 219) | 3 | Keep `Ev.LASER_SET_PERSONALITY` for tests only; docstring note |
| `rb_ss_bridge_v2/config/laser_director.example.json` | 1 | Add 5 new personalities; populate new fields on House |
| `rb_ss_bridge_v2/state_manager.py` (lines 375–379, 1027, 1080–1144, 1906) | 2,3 | Personality-derived timing cache, `attach_personality_resolver`, resolver invocation in SCRIPTED_CLEAR branch + `_on_master_changed`, `_build_breakdown_segments` uses personality field |
| `rb_ss_bridge_v2/laser_director.py` (line 410+) | 2,3 | `_post_drop_hold_beats` split from `_minimum_scene_hold_beats`; **new** `queue_personality_change` + `_apply_pending_personality(ctx)` pending machinery (inspired by superseded Phase 9 plan; not actual carry-over since no implementation exists) |
| `rb_ss_bridge_v2/personality_resolver.py` | 3 | **NEW** — pure resolver + RB DB cache |
| `rb_ss_bridge_v2/__main__.py` | 3 | Instantiate resolver, attach to StateManager |
| `rb_ss_bridge_v2/tools/laser_pad_assets/pad.js` | 4 | Aliases/BPM band/timing drafts; resolver test |
| `rb_ss_bridge_v2/tools/laser_pad_assets/index.html` | 4 | Per-personality UI sections |
| `rb_ss_bridge_v2/tools/laser_pad_web.py` | 4 | `/api/resolve-test` endpoint; verify `/api/draft` covers new fields |
| `rb_ss_bridge_v2/tools/laser_config_ops.py` | 4 | Alias mutation helpers |
| `rb_ss_bridge_v2/tests/test_personality_resolver.py` | 3 | **NEW** — pure unit tests for `PersonalityResolver` |
| `rb_ss_bridge_v2/tests/test_state_manager_personality.py` | 3 | **NEW** — integration tests: scripted-skip, unscripted-queue, master-change re-resolve |
| `rb_ss_bridge_v2/tests/test_laser_config.py` | 0,1 | New-field validation, alias uniqueness, missing-field logging |
| `rb_ss_bridge_v2/tests/test_laser_director.py` | 2 | post_drop_hold_beats separation tests |

**Reusable existing utilities:**
- `LaserDirector.set_personality()` (`laser_director.py:150`) — existing entry point.
- `LaserSceneExecutor.set_personality()` (`laser_executor.py:58`) — resets cursors on swap.
- `save_config_atomically()` in `laser_pad_web.py` — atomic JSON write.
- `pyrekordbox.db6.Rekordbox6Database` usage in `filepath_resolver.py:244-300` — the resolver's DB cache builder reuses this connection pattern.
- `SmartPhrasingEngine` in `smart_phrasing.py` — phrase boundary events for boundary-gated swaps.

---

## 13. Risks and Edge Cases

- **PER GENRE folder name change in Rekordbox.** Bridge can't find the folder → empty cache → everything falls to BPM/default. Mitigation: log loud warning at startup if the folder lookup returns zero playlists. Operator sees and renames the folder back.
- **Track not in any PER GENRE playlist.** Falls to BPM. Surface in log so PER GENRE gets maintained.
- **Alias collision (`house` inside `tech house`).** Handled by longest-first lookup. Cross-personality exact-duplicate aliases rejected at config load.
- **RB DB locked at startup.** Cache empty; bridge falls to BPM/default. Resolver retries on first `_on_filepath_resolved` cache miss. If chronic, surface in startup health log.
- **RB DB schema drift between RB versions.** Isolate the query in `personality_resolver.py`. Log full exception on query failure; continue with empty cache.
- **Personality applied during scripted track due to ordering bug.** Mitigation: primary guard — resolver invoked only in the `else`-branch at `state_manager.py:1136` (SCRIPTED_CLEAR). Secondary guard — `_apply_pending_personality(ctx)` no-ops when `ctx.lighting_mode == "scripted"`. (`queue_personality_change` does not have `ctx`; do not put the guard there.)
- **Master switch mid-bar.** Pending personality is recorded; actual swap deferred to next phrase boundary on new master.
- **Track moved between PER GENRE playlists mid-set.** Locked at filepath-resolved. No mid-track re-resolve.
- **Empty bank in personality.** Existing executor falls to safe scene. Phase 6 UI warning.
- **Bridge restart safety** (per memory `feedback_bridge_restart.md`): after any restart `pgrep -f rb_ss_bridge | wc -l` must return `1`.
- **`minimum_scene_hold_beats` semantic regression.** Phase 2 narrows its use to normal scenes only. Verify no other code path (especially `laser_executor.py`) relies on the old "covers post-drop too" behavior.
- **Hot reload deprecation expectations.** Operator may expect alias edits to take effect without restart. Section 10 makes the restart requirement explicit; UI surfaces "restart required" already.

---

## 14. Verification

Per-phase verification, all run from `/Users/bbui/rb_ss_bridge_v2`:

**Phase 0:**
- `python3 -m unittest tests.test_laser_config` green (covers field parsing for `LaserPersonality` since the dataclass is constructed inside `laser_config.py`).
- Existing local `config/laser_director.json` still loads; bridge runs unchanged behavior.

**Phase 1:**
- `python3 -m unittest tests.test_laser_config` green including new missing-field log assertions.
- Diff `config/laser_director.example.json` shows 5 new personalities + new fields on House.

**Phase 2:**
- `python3 -m unittest tests.test_laser_director` green for post-drop split.
- Manual verification must exercise the **atomic apply path** that updates all three components (LaserDirector + LaserSceneExecutor + StateManager timing cache). Two options:
  - (a) Drive the change through the same internal path Phase 3 will use (call `_apply_pending_personality(ctx)` directly with a fake ctx after setting `_pending_personality`); OR
  - (b) Use a small test harness that explicitly calls all three pieces in sequence: `director.set_personality(...)`, `director.set_personality_config(...)`, `executor.set_personality(...)`, and `state_manager._recache_personality_timing()`.
- After applying Dubstep, load a track and confirm log line shows pre_drop_blackout firing 16 beats (not 4) before drop crossing. Repeat for Hard Techno → 8 beats.
- Apply a personality whose `breakdown_default_restore_beats` differs from the global 64. Load a track with no later buildup/drop. Confirm breakdown segment endBeat uses the active personality's value, not 64.

**Phase 3:**
- `python3 -m unittest tests.test_personality_resolver` green (pure unit tests, ~15+ tests).
- **`tests.test_state_manager_personality` (new) — at minimum two integration tests:**
  - `test_scripted_match_does_not_queue_personality` — fake `_on_filepath_resolved` payload that resolves a SCRIPTED_ARM (ssid matches a SCRIPTED_TRACK); assert `director.queue_personality_change` never called and no `[PERSONALITY]` log line emitted.
  - `test_unscripted_clear_queues_personality_for_active_deck` — fake payload that resolves to SCRIPTED_CLEAR with a content_id in the test cache; assert `director.queue_personality_change` called exactly once with the expected name.
  - This pair is the regression guard for the ordering bug — primary scripted exclusion lives in this code path; unit tests on the pure resolver can't catch a regression here.
- `python3 -m unittest discover tests` full green.
- Manual: load tracks across all six PER GENRE playlists. Each produces `[PERSONALITY] ... rule=playlist matched="<alias>"` log line.
- Manual: load track NOT in PER GENRE with file BPM 145 → with default `bpm_priority` order, resolves to **Hard Techno**, `rule=bpm_range_match matched="140-160"`.
- Manual: load track NOT in PER GENRE with file BPM 138 → resolves to **Bass House** (band 126–140, exclusive max), `rule=bpm_range_match matched="126-140"`.
- Manual: load track NOT in PER GENRE with file BPM 118 → no band matches → `rule=default`.
- Manual: crossfade between Dubstep track and House track. Confirm `pending_personality` flips at phrase boundary on new master.
- Manual: ensure scripted track load does NOT invoke resolver (look for absence of `[PERSONALITY]` line on scripted IDs).

**Phase 4:**
- Web UI: add alias to a personality, save, restart bridge, confirm resolver picks it up.
- Web UI: try to add a duplicate alias → rejected with error.
- Resolver test panel: type "Dubstep Heaters" → returns Dubstep + matched="dubstep". Type "Random Playlist" → returns House + default.

**Phase 5:** live tuning iteration; no automated verification.

**Always:** after each bridge restart, `pgrep -f rb_ss_bridge | wc -l` must equal `1`.

---

## 15. Implementation Invariants (must hold across all phases)

Codex should keep these as non-negotiables — easy to violate, expensive to debug:

1. **`content_id` is `str` everywhere** — matches existing `TrackMetadata.content_id` (`filepath_resolver.py` stores `str(c.ID)`). Resolver API, cache, log lines: all `str`. Never `int`.
2. **`PersonalityResolver.resolve()` is pure** — no I/O, no globals, no side effects, safe from any thread. All DB work lives in `PlaylistCache`. `StateManager` orchestrates miss → `cache.refresh()` → retry.
3. **Boundary apply is atomic across three components** — `LaserDirector` state, `LaserSceneExecutor.set_personality()` reset, and `StateManager` timing cache (`_sp_drop_window`, `_sp_post_drop`, `_sp_transition_window`, `_sp_breakdown_default_restore`) all update in one function call. No tick may observe a partial swap.
4. **Manual personality override removed at all external surfaces.** OSC route gone, runtime command gone, web UI does not expose it. `Ev.LASER_SET_PERSONALITY` retained as internal/test path only — log warning if `ev.source` is unknown.
5. **BPM overlap rule is one unambiguous rule: ordered first-match wins via `bpm_priority`.** No implicit "highest energy wins" logic in code. Overlaps allowed; operator owns disambiguation by ordering.
6. **Resolver guarded against scripted tracks at two levels:** primary at invocation (only in SCRIPTED_CLEAR branch at `state_manager.py:1136`); secondary at apply-time (skip pending while `ctx.lighting_mode == "scripted"`).
7. **`post_drop_hold_beats` replaces `minimum_scene_hold_beats` only in the post-drop code path** (`laser_director.py:413`). All other uses of `minimum_scene_hold_beats` (normal-scene minimum hold) remain unchanged.
8. **Master-change re-resolution gated on `_personality_eligible_deck[deck]`** — set in SCRIPTED_CLEAR branch, reset in `_on_track_loaded` and SCRIPTED_ARM branch. Never re-resolve a deck whose eligibility is `False`. Do not substitute `scripted_id == 0` or `meta.content_id != ""` as a proxy — those are stale from prior loads until next FILEPATH_RESOLVED.

---

## 16. Out of Scope (Explicit)

- No manual personality override (no OSC route, no UI button, no menu-bar control).
- No change-rate ceiling.
- No drop-aggression dial.
- No static-look accent firing (deferred Phase 8).
- No MyTag layer in v1 (deferred Phase 7).
- No personality during scripted shows — guarded at resolver invocation site.
- No live-inherit between personalities (one-time snapshot only, matches current shape).
- No Rekordbox Genre tag as a resolver layer (operator chose PER GENRE playlist as authoritative).
