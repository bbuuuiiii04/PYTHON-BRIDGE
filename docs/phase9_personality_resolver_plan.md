# Phase 9 / Phase A — Auto-Detection PersonalityResolver

Replace SSID/filepath/folder rule-matching with a three-tier auto-detection resolver that routes via **Rekordbox Genre tag → MyTag set → BPM range → default**, preserving sticky runtime override and phrase-aligned application from the prior locked design.

## Context & pivot

The prior Phase 9 plan (Opus) routed via per-personality `match_ssid` / `match_filepath_exact` / `match_folder_infix` rules. You scrapped that ("different matching signal AND different scope") in favor of the bridge **auto-detecting** personality from the track itself, with operator config kept to a small **top-level mapping table** (Q2 answer).

The bridge already opens `~/Library/Pioneer/rekordbox/master.db` via `pyrekordbox.db6.Rekordbox6Database` in `@/Users/bbui/rb_ss_bridge_v2/filepath_resolver.py:244-271` and `@/Users/bbui/rb_ss_bridge_v2/filepath_resolver.py:274-300`, but only extracts `BPM`, `ID`, `FolderPath`, `Length`. Genre and MyTag joins are unused. `@/Users/bbui/rb_ss_bridge_v2/docs/laser_director_design.md:716-726` flagged this exact extension as out-of-scope until you said so — Phase A now does so.

## Locked decisions

| Decision | Value |
|---|---|
| Auto-detect signal | **Rekordbox Genre tag → MyTag set → BPM range → default** (priority chain) |
| Mapping shape | **Top-level mapping table** at the root of `config/laser_director.json` (single `personality_routing` block) |
| BPM windows (operator-supplied defaults) | House 125–138, Bass House 126–140, Techno 130–145, Hard Techno 150–160, Dubstep 130–155, DnB 160+ |
| BPM range overlap policy | Operator-ordered list; **first match wins**. Validator logs `WARN` on detected overlap; not a hard error. |
| BPM range inclusion | `min <= bpm < max` (exclusive max so adjacent ranges chain cleanly) |
| Genre / MyTag matching | Case-insensitive, whitespace-trimmed exact compare |
| Sticky runtime override | Yes (carry from Opus plan) |
| Override clear command | Dedicated `/laser/personality/clear` OSC route |
| Master deck switch | Re-resolves and may flip personality |
| Phrase-aligned application | All personality changes deferred to next phrase boundary on the active deck (carry from Opus plan) |
| Application when idle | Apply immediately |
| Operator commands timing | Also phrase-aligned (same discipline) |
| Phrase grid source | Single global switch `phrase_grid_source: "mechanical" \| "pssi"` (carry from Opus plan; `"mechanical"` default) |
| Unknown personality name in routing maps | Log `WARN` + skip that route (do not crash) |

## Resolver API

New file: `@/Users/bbui/rb_ss_bridge_v2/personality_resolver.py`

```python
ResolutionReason = str
# Values: "runtime_override" | "genre_match" | "mytag_match" |
#         "bpm_range_match" | "default"

@dataclass(frozen=True)
class BpmRange:
    bpm_min: float       # inclusive
    bpm_max: float       # exclusive
    personality: str

@dataclass(frozen=True)
class PersonalityResolution:
    name: str
    reason: ResolutionReason

class PersonalityResolver:
    def __init__(
        self,
        *,
        genre_map: Mapping[str, str],          # genre name (canonical) -> personality
        mytag_map: Mapping[str, str],          # tag name (canonical) -> personality
        bpm_ranges: Sequence[BpmRange],        # ordered, first-match-wins
        known_personalities: Set[str],         # for sanity-check on construction
    ) -> None: ...

    def resolve(
        self, *,
        override: Optional[str],
        genre: str,
        mytags: Sequence[str],
        bpm: float,
        default: str,
    ) -> PersonalityResolution: ...
```

**Priority** (return on first hit):
1. `override` non-empty → `runtime_override`
2. `_canon(genre)` is a key of `genre_map` and value is in `known_personalities` → `genre_match`
3. any `_canon(t)` for `t in mytags` is a key of `mytag_map` and value is in `known_personalities` → `mytag_match` (first matching tag in the track's MyTag list wins; deterministic order preserved from DB)
4. `bpm > 0` and a `BpmRange` in `bpm_ranges` satisfies `r.bpm_min <= bpm < r.bpm_max` and `r.personality` is known → `bpm_range_match` (first match wins)
5. `default` → `default`

`_canon(s)` = `s.strip().lower()`. Map keys are pre-canonicalized at construction time.

Resolver is **pure** — no I/O, no globals, safe for any thread. Construction logs `WARN` once per unknown personality name and once per detected BPM-range overlap.

## Routing config schema

### `@/Users/bbui/rb_ss_bridge_v2/laser_models.py`

Add `LaserConfig` field (unchanged from Opus plan):
```python
phrase_grid_source: Literal["mechanical", "pssi"] = "mechanical"
```

Add new top-level dataclass:
```python
@dataclass(frozen=True)
class PersonalityRouting:
    genre_map: Mapping[str, str] = field(default_factory=dict)       # canonicalized keys
    mytag_map: Mapping[str, str] = field(default_factory=dict)       # canonicalized keys
    bpm_ranges: tuple[BpmRange, ...] = field(default_factory=tuple)  # ordered
```

Add `LaserConfig.personality_routing: PersonalityRouting = field(default_factory=PersonalityRouting)`.

`LaserPersonality` itself **does not gain new fields** in Phase A — routing lives at config root, not per personality.

### `@/Users/bbui/rb_ss_bridge_v2/laser_config.py`

- New top-level validator `_validate_personality_routing(data)`:
  - `genre_map` / `mytag_map`: `dict[str, str]` if present; both keys and values non-empty strings; canonicalize keys to `key.strip().lower()`; collision on canonicalized keys → `WARN` + first-listed wins.
  - `bpm_ranges`: list of objects `{min: float, max: float, personality: str}`; `min < max`; all non-negative; personality non-empty.
  - All `personality` values must reference existing `personalities` keys; unknown → `WARN` + skip.
  - Detect BPM overlap (`r1.min < r2.max and r2.min < r1.max`) → `WARN` listing both ranges; not a hard error.
- Top-level validator: `phrase_grid_source` must be absent or `"mechanical"`/`"pssi"`. Reject other strings with a clear error (carry from Opus plan).
- `_build_config`: pass `phrase_grid_source` through; build `PersonalityRouting` from the validated dict.

### Config JSON shape

```json
{
  "enabled": true,
  "default_personality": "house",
  "phrase_grid_source": "mechanical",
  "personality_routing": {
    "genre_map": {
      "House": "house",
      "Tech House": "house",
      "Bass House": "bass_house",
      "Techno": "techno",
      "Hard Techno": "hard_techno",
      "Dubstep": "dubstep",
      "Drum & Bass": "dnb",
      "DnB": "dnb"
    },
    "mytag_map": {
      "Driving": "techno",
      "Peak Time": "techno",
      "Funky": "house"
    },
    "bpm_ranges": [
      {"min": 160.0, "max": 999.0, "personality": "dnb"},
      {"min": 150.0, "max": 160.0, "personality": "hard_techno"},
      {"min": 138.0, "max": 150.0, "personality": "techno"},
      {"min": 130.0, "max": 138.0, "personality": "bass_house"},
      {"min": 125.0, "max": 130.0, "personality": "house"}
    ]
  },
  "personalities": { "house": { ... }, "techno": { ... }, ... }
}
```

Operator orders `bpm_ranges` to encode priority (high BPM first to avoid overlap surprises in the 130–138 zone).

## Metadata ingestion extension

### `@/Users/bbui/rb_ss_bridge_v2/models.py` — `TrackMetadata`

Add fields:
```python
genre: str = ""
mytags: tuple[str, ...] = field(default_factory=tuple)
```

Update `clear()` to reset both.

### `@/Users/bbui/rb_ss_bridge_v2/filepath_resolver.py`

Extend both DB lookups so the FILEPATH_RESOLVED payload carries `genre` and `mytags`:

- `_db_lookup_by_anlz(anlz_path)` (currently `@/Users/bbui/rb_ss_bridge_v2/filepath_resolver.py:226-271`): after locating matching `DjmdContent` row, query genre via `c.GenreID → DjmdGenre.Name` and MyTags via `DjmdSongMyTag` join → `DjmdMyTag.Name` (use the same opened `db` session). Add to returned dict.
- `_db_lookup(filepath)` (currently `@/Users/bbui/rb_ss_bridge_v2/filepath_resolver.py:274-300`): same extension; widen return tuple to `(content_id, bpm, first_beat_ms, genre, mytags)` and update both callers (anlz fallback at `:328-389` and lsof path at `:508-540`).
- All new fields default to `""` / `()` on lookup failure — never raise.
- Verify the exact pyrekordbox accessor names (`get_genre`, `get_my_tag_song`, attribute names) at implementation time; fall back to defensive `getattr` access.

### `FILEPATH_RESOLVED` payload (in `models.py` docstring + StateManager handler)

Add keys: `"genre": str`, `"mytags": list[str]`. StateManager `_on_filepath_resolved` stores both into `TrackMetadata`.

## Phrase-aligned application (carried from Opus plan)

Mechanism unchanged from Opus's plan — ported verbatim:

- `LaserDirector` gains `self._pending_personality: Optional[tuple[str, LaserPersonality, str]]` (last-write-wins).
- `queue_personality_change(name, cfg, reason)` stores pending; no-op if already current.
- `_maybe_apply_pending_personality(ctx)` runs at the top of `_decide()` and applies pending **iff** (a) at a phrase boundary per `phrase_grid_source` (mechanical = `phrase_interval_beats` against `ctx.abs_beat`; pssi = transition in `ctx.smart_phrasing.current_phrase_label`), OR (b) idle (no track loaded, `lighting_mode` ∉ {`autoloop`,`scripted`}, no recent phrase tick).
- PSSI fallback: if `phrase_grid_source="pssi"` but no PSSI label is available, silently fall back to mechanical against the current personality's `phrase_interval_beats` — no stuck-pending state.
- Apply sequence on boundary: `set_personality(name)` + `set_personality_config(cfg)` + `set_personality_resolution_reason(reason)`. Scene-role continuity preserved across the swap (groove stays groove; only the underlying scene MIDI note changes).

## Wiring map

### `@/Users/bbui/rb_ss_bridge_v2/state_manager.py`

- Constructor: add `personality_resolver: Optional[PersonalityResolver] = None`, store as `self._personality_resolver`.
- `_on_filepath_resolved`: after existing scripted_arm enqueue, call `self._resolve_personality_for_active_deck(deck, meta)` if resolver present, director present, and `deck == self._os.active_deck`.
- New helper `_resolve_personality_for_active_deck(deck, meta)`:
  - Reads `_runtime_override` from director.
  - Calls `resolver.resolve(override=override, genre=meta.genre, mytags=meta.mytags, bpm=meta.bpm, default=cfg.default_personality)`.
  - Looks up `LaserPersonality` via `self._laser_personality_provider(resolution.name)`. None → log + skip.
  - Calls `director.queue_personality_change(resolution.name, personality_cfg, resolution.reason)`.
- `_on_master_changed`: when active deck changes and the new active deck has populated metadata, call the helper above.
- `Ev.LASER_SET_PERSONALITY` handler: extend to optionally accept `resolution_reason` payload key, default to `"runtime_override"` for `runtime_command` source. Still calls `set_runtime_override` and `queue_personality_change`.
- New event `Ev.LASER_CLEAR_PERSONALITY_OVERRIDE` handler: calls `director.clear_runtime_override()`, then re-runs the helper for the active deck so metadata-based routing immediately reasserts.

### `@/Users/bbui/rb_ss_bridge_v2/laser_director.py`

New attributes:
- `self._runtime_override: Optional[str] = None`
- `self._default_personality: str = ""`
- `self._personality_resolution_reason: str = ""`
- `self._pending_personality: Optional[tuple[str, LaserPersonality, str]] = None`
- `self._phrase_grid_source: str = "mechanical"`

New methods:
- `set_runtime_override(name)` / `get_runtime_override()` / `clear_runtime_override()`
- `set_default_personality(name)` / `get_default_personality()`
- `get_personality()` / `set_personality_resolution_reason(reason)`
- `set_phrase_grid_source(source)`
- `queue_personality_change(name, cfg, reason)` — stores pending; no-op if (name, reason) already current.
- `_maybe_apply_pending_personality(ctx)` — called at top of `_decide()`.

`status()` adds:
```python
"personality_resolution_reason": self._personality_resolution_reason,
"runtime_override_personality": self._runtime_override,
"pending_personality": self._pending_personality[0] if self._pending_personality else None,
"phrase_grid_source": self._phrase_grid_source,
```

`_record_decision()` passes `personality_resolution_reason=self._personality_resolution_reason` into `LaserDecision`.

### `@/Users/bbui/rb_ss_bridge_v2/laser_decision_log.py`

Add `personality_resolution_reason: str = ""` to `LaserDecision`.

### `@/Users/bbui/rb_ss_bridge_v2/__main__.py`

After `LaserDirector` instantiation:
- Build `PersonalityResolver` from `cfg.personality_routing` and `set(cfg.personalities.keys())`; pass to `StateManager(...)`.
- `laser_director.set_default_personality(cfg.default_personality)`
- `laser_director.set_phrase_grid_source(cfg.phrase_grid_source)`

Add `_laser_clear_personality_override()` callback emitting `Ev.LASER_CLEAR_PERSONALITY_OVERRIDE`. Register OSC route `/laser/personality/clear`.

### `@/Users/bbui/rb_ss_bridge_v2/models.py`

- Add `Ev.LASER_CLEAR_PERSONALITY_OVERRIDE`.
- Update `Ev.LASER_SET_PERSONALITY` docstring to note optional `resolution_reason` payload key.
- `TrackMetadata` gets `genre` + `mytags` fields (see above).
- `Ev.FILEPATH_RESOLVED` docstring lists new payload keys `genre`, `mytags`.

## Critical files

| File | Action |
|---|---|
| `personality_resolver.py` | NEW |
| `tests/test_personality_resolver.py` | NEW |
| `laser_models.py` | modify — add `phrase_grid_source`, `BpmRange`, `PersonalityRouting`, wire into `LaserConfig` |
| `laser_config.py` | modify — validate + build `personality_routing` block, validate `phrase_grid_source` |
| `laser_decision_log.py` | modify — add `personality_resolution_reason` |
| `laser_director.py` | modify — pending machinery, 8+ new methods, status keys, decision-record field |
| `state_manager.py` | modify — resolver invocation, master-switch re-resolve, `LASER_SET_PERSONALITY` extension, new clear handler |
| `filepath_resolver.py` | modify — extend `_db_lookup_by_anlz` and `_db_lookup` to fetch genre + MyTags; widen FILEPATH_RESOLVED payload |
| `models.py` | modify — `TrackMetadata.genre`/`mytags`; `Ev.LASER_CLEAR_PERSONALITY_OVERRIDE`; docstring updates |
| `__main__.py` | modify — instantiate resolver, call setters, register OSC `/laser/personality/clear` |
| `tests/test_laser_decision_log.py` | modify — fixtures + expected dicts include new field |
| `tests/test_filepath_resolver_*.py` | modify — payload assertions include `genre` + `mytags` defaults |

## Test plan (Phase A unit tests only)

### `tests/test_personality_resolver.py` (new)

1. `test_runtime_override_wins_over_all_paths`
2. `test_genre_match_case_insensitive`
3. `test_genre_match_whitespace_trimmed`
4. `test_genre_priority_over_mytag_and_bpm`
5. `test_mytag_priority_over_bpm`
6. `test_mytag_first_matching_tag_wins`
7. `test_mytag_unmatched_falls_through_to_bpm`
8. `test_bpm_range_first_match_wins_on_overlap`
9. `test_bpm_range_inclusive_min_exclusive_max`
10. `test_bpm_zero_skips_bpm_path`
11. `test_no_metadata_falls_through_to_default`
12. `test_empty_genre_skips_genre_path`
13. `test_empty_mytags_skips_mytag_path`
14. `test_override_empty_string_treated_as_unset`
15. `test_unknown_personality_in_genre_map_logged_and_skipped`
16. `test_unknown_personality_in_bpm_range_logged_and_skipped`
17. `test_construction_is_pure_no_io`

### `tests/test_laser_config.py` (additions)

18. `test_personality_routing_defaults_to_empty_block`
19. `test_genre_map_must_be_dict_of_strings`
20. `test_bpm_range_min_must_be_less_than_max`
21. `test_bpm_range_overlap_warns_not_errors`
22. `test_unknown_personality_in_routing_warns_skipped`
23. `test_phrase_grid_source_validates_enum_values`

### `tests/test_laser_director.py` (additions)

24. `test_status_exposes_personality_resolution_reason`
25. `test_status_exposes_runtime_override`
26. `test_status_exposes_pending_personality`
27. `test_status_exposes_phrase_grid_source`
28. `test_queue_personality_change_stores_pending_does_not_apply_until_boundary`
29. `test_pending_applies_at_phrase_boundary_preserves_role_changes_midi`
30. `test_pending_applies_immediately_when_idle`
31. `test_pending_applies_at_pssi_boundary_when_grid_source_pssi`
32. `test_pssi_grid_falls_back_to_mechanical_when_no_pssi_tags`
33. `test_runtime_override_setters_and_clear`

### `tests/test_laser_decision_log.py` (updates)

34. Update 2 hardcoded fixtures + 2 expected-dict assertions to include `personality_resolution_reason`.
35. `test_personality_resolution_reason_is_stamped_on_decision`.

### `tests/test_filepath_resolver_*.py` (additions)

36. `test_db_lookup_extracts_genre` (mock pyrekordbox returning a content row with GenreID).
37. `test_db_lookup_extracts_mytags` (mock the join).
38. `test_db_lookup_missing_genre_returns_empty_string`.
39. `test_filepath_resolved_payload_includes_genre_and_mytags`.

State-manager wiring tests (resolver invocation, master-switch re-resolve, override-clear flow) deferred to Phase B replay coverage.

## Out of scope (Phase B and beyond)

- Replay fixtures recording real bridge sessions for each resolution path.
- End-to-end integration tests through real `StateManager` event flow.
- Web UI surface for runtime override status.
- Re-resolving on mid-track metadata refresh (Phase A resolves only on `_on_filepath_resolved` and master switch).
- Config hot-reload that rebuilds resolver indices.
- ID3 fallback when Rekordbox DB is unavailable (Phase A: no DB → empty genre/mytags → BPM/default still work).
- `Literal[...]` type for `personality_resolution_reason`.

## Verification

1. `python3 -m unittest tests.test_personality_resolver` — all 17 resolver tests pass.
2. `python3 -m unittest tests.test_laser_config tests.test_laser_director tests.test_laser_decision_log` — all updated + new tests pass.
3. `python3 -m unittest tests.test_filepath_resolver_beatgrid` (and any other touched fixture tests) pass with new payload keys.
4. `python3 -m unittest discover tests` — full suite green; no regressions.
5. **Manual config**: load `config/laser_director.example.json` populated with the genre map, mytag map, and BPM-range list above; bridge starts without error; `/tmp/rb_ss_bridge_v2_status.json` shows `personality_resolution_reason: "default"`, `runtime_override_personality: null`, `pending_personality: null`, `phrase_grid_source: "mechanical"`.
6. **Manual smoke (genre)**: load a Rekordbox track tagged Genre = "Techno"; status shows `pending_personality: "techno"` after track load; at next phrase boundary, `personality: "techno"`, `reason: "genre_match"`, `pending: null`.
7. **Manual smoke (mytag)**: clear Genre on a track but tag MyTag = "Driving"; verify `reason: "mytag_match"`.
8. **Manual smoke (bpm fallback)**: untagged track at 142 BPM → `reason: "bpm_range_match"`, `personality: "techno"`.
9. **Manual override**: `/laser/personality dubstep` → boundary applies, `runtime_override_personality: "dubstep"`, `reason: "runtime_override"`. `/laser/personality/clear` → next boundary re-resolves from metadata.
