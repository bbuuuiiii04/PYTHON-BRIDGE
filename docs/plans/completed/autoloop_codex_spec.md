# Section-Correct Autoloop Selection — Audit + Codex Implementation Spec

Audit date: 2026-06-10. All file:line references verified against current working tree
at `/Users/bbui/rb_ss_bridge_v2/`. Labels: **CONFIRMED** / **ASSUMED** / **UNKNOWN**.

---

# Part A — Audit

## A1. Blocker List

### BLOCKER 1 — Piece 1's `scene_type` condition is wrong for the live config
**File:** `config/laser_director.json` + `laser_executor.py:187-199`
9 of 10 house drop scenes are `scene_type: "autoloop"`, not `"static"`:
`house_drop_1` = static, but `house_drop_2`–`house_drop_10` = autoloop (verified via jq).
Only 3 of 48 scenes are static (`house_drop_1`, `safe_static`, `transition_safe_1`).
The plan's proposed condition `scene_def.scene_type == "autoloop"` would therefore let a
**held drop look re-fire MIDI** during the drop_mode post-drop hold whenever
`autoloop_tick_just_fired` fires inside the 16-beat hold window — exactly what the plan
says must not happen.
**Resolution (used in Part B):** make the pass-through role-scoped:
`role in ("phrase", "buildup", "breakdown")` AND `scene_type == "autoloop"`. The role
check excludes `drop`/`post_drop` regardless of config typing; the scene_type check is
kept as the plan's belt-and-suspenders. No config retype required.

### BLOCKER 2 — Piece 4 "just don't pass autoloop_master_phrase_arm=True" is insufficient
**File:** `autoloop_controller.py:166, 537-688`; `state_manager.py:2121-2127`
`arm_autoloop()` sets `os.autoloop_arm_pending = True` **unconditionally** (line 166).
Even in the immediate (non-delayed) path, pending is only cleared by
`_maybe_lock_autoloop_arm` when elapsed reaches the **next absolute 32-beat boundary**
(`autoloop_arm_sync_beat == 0` → `next_arm_phrase()`, line 554-555, lock at 584+).
`ctx.autoloop_ready` (state_manager.py:2121-2127) requires `not autoloop_arm_pending`,
and `LaserSceneExecutor._passes_automatic_gates` (laser_executor.py:368-376) requires
`autoloop_ready`. So with the delay removed, **the bridge still refuses to send any
laser MIDI — including the drop note — until the next 32-beat boundary.** The smart-drop
/ breakdown / phrase-anchor coordinator paths are also gated on `autoloop_arm_pending`
(smart_rearm.py:105, 227, 277).
**Resolution (used in Part B):** in the immediate master-arm path, finalize the arm on
the spot (send BPM, set `last_sent_bpm`, `clear_arm_phrase_lock()`), mirroring the
existing `_maybe_lock_autoloop_arm` finalization at autoloop_controller.py:674-681.

### BLOCKER 3 — Three blackout masks share one physical MIDI note; no coordination exists
**File:** `laser_executor.py:237-273`, `config/laser_director.json` (`manual_commands`)
Smart Drop's existing blackout, the new breakdown blackout (Piece 3), and the new
master-switch blackout (Piece 4) all resolve to the **same MIDI note**
(`manual_commands.blackout_on/off`: note 0, channel 1). The executor today has exactly
one latch (`_blackout_pending_for_drop_window`), and `_resolve_pending_blackout` is
called from ~10 cleanup paths (drop crossings, `on_tick` transition-mask clear,
`reset_runtime_state`, `clear_pending_blackout`). Naively reusing
`trigger_blackout_on()` for breakdown/master masks means any drop-window cleanup lifts
the breakdown/master mask early, and `trigger_blackout_on` no-ops if already pending.
**Resolution (used in Part B):** add an owner-set (`_mask_owners: set[str]`) to the
executor with `hold_blackout_mask(owner)` / `release_blackout_mask(owner)`. The note_off
is only sent when the drop-window latch is clear AND the owner set is empty. Existing
Smart Drop paths are unchanged except for a 2-line guard in `_resolve_pending_blackout`.

### BLOCKER 4 — Breakdown restore has no groove re-fire path through the director
**File:** `laser_director.py:547-606`, `laser_executor.py:303-327`
On the `breakdown_end_crossing` tick, `sp.smart_breakdown_active` is already False, so
the director falls through to `_decide_phrase_default`, which emits reason `"default"` —
and `_select_scene` returns `""` for the phrase role unless the reason is
`default_init`/`phrase_boundary` (laser_executor.py:316-321 via
`_PHRASE_TRIGGER_REASONS`, line 25). Setting `autoloop_tick_just_fired=True` on that
tick (which `breakdown_fired` already does, state_manager.py:1887-1889) is **not
enough**: the director's `_phrase_trigger_pending` must also be set, and it is only set
on absolute 32-grid changes. Without a hook, the blackout lifts at restore and SS shows
a freelanced look for up to 32 beats.
**Resolution (used in Part B):** in `_decide_phrase_default`, latch
`_phrase_trigger_pending = True` when `sp.breakdown_end_crossing` or
`sp.phrase_anchor_requested` is set. (The second condition is also needed for Piece 2 —
without it, marker-relative re-fires that don't align with the absolute 32-grid emit
reason `"default"` and never fire; see Piece 2 findings table, row 8.)

### BLOCKER 5 — Operator prerequisites that code cannot satisfy
1. **SoundSwitch MIDI mappings for all groove looks do not exist yet** (operator-stated).
   `house` phrase_bank = 32 scenes (`house_groove_1..32`, e.g. groove_1 = note 32 ch 1).
   Until mapped in SS, the re-fire machinery sends notes SS ignores. UNKNOWN from code.
2. **"BY GENRE" folder name is not verifiable from code.** It appears nowhere in the
   codebase (grep over .py/.json/.md: no hits as a Rekordbox folder name). The fix in
   Piece 5a is a one-token change but the literal string must be operator-confirmed
   against Rekordbox before merging.

---

## A2. Piece-by-Piece Findings

### Piece 1 — `same_scene_skip` boundary-aware fix

| Claim | File:Line | Status | Note |
|---|---|---|---|
| `same_scene_skip` block exists as quoted | `laser_executor.py:187-199` | CONFIRMED | Exact code matches plan's "before" snippet. |
| `scene_def` in scope + non-None at the check | `laser_executor.py:155-163` | CONFIRMED | Looked up at 155; None → early return 156-163. Skip check runs after the role-cooldown check (174-185). |
| `ctx.autoloop_tick_just_fired` on LaserContext | `laser_models.py:132` | CONFIRMED | Default False. |
| `scene_def.scene_type` field exists | `laser_models.py:67` | CONFIRMED | Class is `LaserScene`, **not** `LaserSceneDef` (plan misnames it). |
| Drop scenes are `static` | `config/laser_director.json` | **REFUTED** | Only `house_drop_1` is static; `house_drop_2..10` are autoloop. See BLOCKER 1. |
| Groove/buildup/breakdown scenes are `autoloop` | `config/laser_director.json` | CONFIRMED | All 32 grooves + `house_buildup_1` + `house_breakdown_1` are autoloop. |
| Every personality's buildup/drop/breakdown bank is length-1 | `config/laser_director.json` | **PARTIALLY REFUTED** | buildup=1, breakdown=1 (both personalities); house drop_bank = **10**; dubstep drop_bank = 1. Doesn't change the fix, but the plan's premise is wrong for house drops. |
| drop_mode post-drop hold relies on skip latch | `laser_director.py:447-476` | CONFIRMED | reason `drop_hold`, role `drop`; executor returns `_role_active_scene["drop"]` then same-scene-skips. With role-scoped condition (Part B) this latch is preserved. |
| `_select_scene` phrase gate independent of skip; both needed | `laser_executor.py:315-327` | CONFIRMED | Phrase role: gated on reason + flag (returns `""` otherwise). Buildup/breakdown roles: `_select_scene` returns active scene **without any flag gate** — `same_scene_skip` is the only barrier for them, so the fix unblocks exactly those. |
| Cooldowns won't block the 32-beat re-assert | `config/laser_director.json` | CONFIRMED | grooves/drops = 8, breakdown = 16, buildup = 32; check is strict `< cooldown`, so a re-fire at exactly +32 passes (laser_executor.py:383-405). |
| `scene_type` has no other runtime consumer today | repo grep | CONFIRMED | Only config tooling (`tools/laser_config_ops.py`) and validation. The new check is its first runtime consumer. |

### Piece 2 — Phrase-relative 32-beat re-fire

| Claim | File:Line | Status | Note |
|---|---|---|---|
| Absolute grid re-fire at state_manager.py:1905 | `state_manager.py:1904-1916` | CONFIRMED | Full block quoted in Part B Task 4. Fires `log_autoloop_tick` + `autoloop_tick_just_fired=True` once per 32 absolute beats. |
| `phrase_anchor_requested` exposed in the `sp` the push loop consumes | `state_manager.py:1793-1795, 2053-2056`; `smart_phrasing.py:66, 201-205, 358` | CONFIRMED | `sp_state = SmartPhrasingResult.state`; field set on `prev_abs_beat < seg.start_beat <= abs_beat`. |
| `SmartPhrasingState` has no `current_phrase_start_beat` | `smart_phrasing.py:42-71` | CONFIRMED | No equivalent field. Option (b) — StateManager-side tracking — is correct and is what Part B uses. |
| Engine receives abs_beat + reliable crossing detection | `smart_phrasing.py:139-209` | CONFIRMED | Caveat: computed at 200 Hz; the crossing tick is *expected* to coincide with the `this_beat > last_beat` boundary tick (markers are integer beats) but the two comparisons use different anchors — **ASSUMED**. Part B latches the flag (`_pending_phrase_marker`) and consumes it at the next beat boundary, so a 1-tick skew cannot drop a fire. |
| `AUTOLOOP_ARM_PHRASE_BEATS = 32`, imported from `.config` | `config.py:8`; `state_manager.py:35` | CONFIRMED | Distinct from `PHRASE_ANCHOR_BEATS = 64` (config.py:18), which drives the **OS2L** phrase anchor in smart_rearm.py — that one is NOT part of this change and must not be touched. |
| `last_autoloop_status_phrase_beat` disposition | `state_manager.py:1911` + 6 reset sites | CONFIRMED | Keep it: Part B repurposes it as "last beat a MIDI re-fire fired" for dedupe; all existing resets (master change 935, RB restart 833, idle 1515, stop 2173, resume 2200, arm 169) remain valid (0 = none). |
| `sp.phrase_anchor_requested` has no existing consumers → no double-fire | repo grep | CONFIRMED | Set in smart_phrasing.py only; defaulted in laser_director.py:411 compat path; consumed nowhere. Safe to become the primary trigger. |
| Director phrase machinery fires on marker-relative beats | `laser_director.py:564-574` | **GAP (BLOCKER 4)** | `_phrase_trigger_pending` is set only on absolute `phrase_interval_beats` grid changes. A flag fire at a marker beat not preceded by a grid change emits reason `"default"` → `_select_scene` returns `""` → no MIDI. Part B Task 5 adds `sp.phrase_anchor_requested` to the pending latch. |
| Buildup window override "regardless of phrase label" | `laser_director.py:486-501` | CONFIRMED gap | Priority 11 currently requires `current_phrase_is_up and not current_phrase_is_chorus`. Implementing the plan's words = remove both label conditions (Part B Task 6). Note this is a live behavior change: a re-fire within 32 beats of the next drop now always selects buildup. The `in_post_drop_hold` exclusion is preserved. |

### Piece 3 — Breakdown MIDI blackout

| Claim | File:Line | Status | Note |
|---|---|---|---|
| Breakdown currently unarms the OS2L autoloop | `smart_rearm.py:254-266` → `sound_switch_engine.py:50-59` | CONFIRMED (mechanism corrected) | Single callsite: `_breakdown` start-crossing calls `send_smart_transition_clear(active)` = `send_deck_clear` + `send_loop_off` × 4 SS decks. It does **not** clear `OutputState` arm fields (plan's wording inaccurate — `autoloop_arm_*`/`last_armed_filepath` survive; `os.breakdown_active=True` is what gates other systems, and `ctx.autoloop_ready` stays True through a breakdown). |
| Path from `breakdown_fired` at state_manager.py:1887 | `state_manager.py:1866-1889` → `smart_rearm.py:219-266` | CONFIRMED | `smart_rearm.tick` → `_breakdown`. Only runs when `lighting_mode == "autoloop"` (state_manager.py:1865 + smart_rearm.py:72). |
| `manual_blackout_on/off` on the config object + populated | `laser_config.py:114-115, 763-777`; `config/laser_director.json` `manual_commands` | CONFIRMED | JSON key is **`manual_commands.blackout_on/off`** (not `manual_blackout_*` — loader maps both spellings). Populated: note 0, ch 1, note_on/note_off. `smart_drop_mode = "blackout_mask"` ✓. |
| `trigger_blackout_on` / `_resolve_pending_blackout` reachable from breakdown handling | `state_manager.py` (has `self._laser_executor`); `smart_rearm.py:51-64` | CONFIRMED gap | `SmartRearmCoordinator` has **no executor reference** — constructor takes only two send callables. Part B wires two new callables (`hold_blackout_mask` / `release_blackout_mask`) from StateManager. Shared-note coordination per BLOCKER 3. |
| Breakdown restore path location | `smart_rearm.py:233-252` | CONFIRMED | `breakdown_end_crossing` → `_send_direct_autoloop_rearm(..., "smart-breakdown", target_beat=os.breakdown_restore_beat)`. Part B keeps the OS2L rearm (it re-anchors SS loop phase — live-validated pattern) and adds mask release + groove re-fire. |
| Scripted path cannot be reached by the blackout change | `state_manager.py:1491-1497, 2203-2218` | CONFIRMED | Scripted arm is `_arm_scripted`/`_check_pending_arm`, never through smart_rearm. Additionally `_apply_lighting("scripted")` → `_clear_smart_rearm_state()` → `clear_pending_blackout()` lifts any pending mask, so a scripted show can never start masked — **provided** Part B routes mask clearing through `clear_pending_blackout` (it does). |

### Piece 4 — Immediate arm on master switch

| Claim | File:Line | Status | Note |
|---|---|---|---|
| `arm_autoloop` callsite + arg | `state_manager.py:1499-1507` | CONFIRMED | Single callsite, passes `self._autoloop_master_phrase_arm` (env `RBSS_AUTOLOOP_MASTER_PHRASE_ARM`, default "1"; **not set in the live watcher env block → live = on**). |
| `should_delay_master_arm` at autoloop_controller.py:351 | `autoloop_controller.py:351-359` | CONFIRMED | Returns `not is_near_phrase_start(...)` when both flags true; `next_arm_phrase` at 495-499. |
| "Fix is as simple as not passing `autoloop_master_phrase_arm=True`" | `autoloop_controller.py:166, 554-555, 584` | **REFUTED** | See BLOCKER 2 — `autoloop_arm_pending` still gates `autoloop_ready` (and all smart_rearm paths) until the next absolute 32-beat boundary. Immediate finalization required. |
| Transition-mask fields reusable for the master-switch blank | `smart_phrasing.py:287-320`; `smart_rearm.py:163-190` | CONFIRMED, not directly | `transition_mask_should_arm` is drop-proximity (`pre_drop_blackout_beats` = 4) — wrong trigger for a master switch. The executor's blackout *mechanism* is reused via the new owner-mask API; the smart-phrasing transition mask itself is untouched. |
| `os.autoloop_arm_after_master_change` semantics | `models.py:158`; set `state_manager.py:936`; read+cleared `autoloop_controller.py:177-179, 295` | CONFIRMED | True only between `_on_master_changed` and the next `arm_autoloop`. (The plan lists this field twice — duplicate, presumably meant `autoloop_master_change_source`, models.py:159.) |
| Does `arm_autoloop` set `lighting_mode="autoloop"` immediately? | `state_manager.py:1478-1481` | CONFIRMED — mode set *before* `_apply_lighting` | `lighting_mode` flips immediately; only `autoloop_arm_pending` lags. With Task 7's immediate finalization, `autoloop_ready` is True right after the arm, and the Piece 2 origin starts fresh (`midi_refire_origin_beat = -1` → absolute-grid fallback until first marker), which is the correct origin. |

### Piece 5 — Prerequisites

| Claim | File:Line | Status | Note |
|---|---|---|---|
| `PlaylistCache(RB_DB_PATH)` with no folder_name | `__main__.py:693` | CONFIRMED | Only instantiation in the repo (grep). |
| Default folder `"PER GENRE"` | `personality_resolver.py:118` | CONFIRMED | Also hardcoded in 3 log strings (lines 158, 168, 200) — cosmetic, optional update. |
| Other instantiations needing the fix | repo grep | CONFIRMED none | Tests excluded. |
| `"BY GENRE"` is the real RB folder | — | **UNKNOWN** | Not mentioned anywhere in the codebase. Operator must confirm the exact Rekordbox folder name (BLOCKER 5.2). |
| `_sp_phrase_lookahead = 32` hardcoded | `state_manager.py:383` | CONFIRMED | Set once in `__init__`; used at 2046. |
| Personality accessible where it must be updated | `state_manager.py:1097-1115` | CONFIRMED | `_recache_personality_timing(personality)` already updates the four sibling timing fields and skips this one — clean insertion point. |
| No existing update path for `_sp_phrase_lookahead` | repo grep | CONFIRMED | Two references total (set + read). Must be added. |

### Piece 6 — Per-track groove bank shuffle

| Claim | File:Line | Status | Note |
|---|---|---|---|
| `_choose_bank_scene_locked` is the single selection point | `laser_executor.py:329-341` | CONFIRMED | Called only from `_select_scene` (322, 326). Banks otherwise read only by `_seed_role_cursors` (length). |
| `_bank_for_role` returns config tuple directly | `laser_executor.py:352-366` | CONFIRMED | Returns `personality.phrase_bank` etc. — shuffle can wrap it. |
| Track-load awareness in the executor | `state_manager.py:944, 971, 2181`; `laser_executor.py:67, 77-88` | CONFIRMED | No `on_track_load()`; `reset_runtime_state(reason=...)` is called with reasons `master_changed`, `active_track_loaded` (active deck only), `stop`, and `set_personality` (reset_cursors=True). Hook the reshuffle there. |
| `_role_cursors` reset on track load today? | `laser_executor.py:84-85` | CONFIRMED — **not reset** | Only `set_personality` resets (reset_cursors=True). Part B resets the phrase cursor to 0 at reshuffle so each track starts a fresh permutation. |
| `_randomize_cursors` exposed in config? | `laser_executor.py:41, 47`; `__main__.py:330-334`; `laser_config.py` | CONFIRMED — constructor-only | Not a config field (`randomize_cursors` absent from JSON schema/loader); `__main__` doesn't pass it → always True. No existing flag to gate the shuffle on; none needed. |

## A3. Prerequisite Checklist

- [ ] **Operator:** SoundSwitch MIDI mappings for all 32 `house_groove_*` notes (and
  verify `house_buildup_1`, `house_breakdown_1` mappings exist). Cannot be code-verified.
- [ ] **Operator:** confirm the exact Rekordbox playlist folder name is `BY GENRE`
  (case/spacing as shown in Rekordbox) before Task 1 merges.
- [ ] **Config:** `personalities.dubstep` has `"aliases": []` and a zeroed BPM band
  (verified via jq), and top-level `bpm_priority` is `[]` — so even after Task 1,
  dubstep can NEVER be auto-selected. Add `"aliases": ["dubstep"]` (matching the
  DUBSTEP playlist name) to `config/laser_director.json`. Hot-reloaded; no restart.
- [x] `manual_commands.blackout_on/off` present in `config/laser_director.json`
  (note 0, ch 1) and mapped to `LaserConfig.manual_blackout_on/off`. **Done — no action.**
- [x] `smart_drop_mode = "blackout_mask"`, `enabled = true`, `dry_run = false`. **Live.**
- [ ] New model field required: `OutputState.midi_refire_origin_beat` (Task 4 includes it).
- [ ] New executor API required: owner-mask blackout (Task 3 includes it).
- [ ] Tests: `tests/test_smart_drop.py` constructs `SmartRearmCoordinator` — new
  constructor params must default to no-ops so existing tests keep passing.

## A4. What the Plan Got Wrong or Missed

1. **Drop scenes are not static** (`house_drop_2..10` are `autoloop`) — the proposed
   `scene_type`-only condition would re-fire held drop looks. BLOCKER 1; fixed with a
   role-scoped condition.
2. **"Every personality's drop_bank has 1 entry" is false** — house drop_bank has 10.
3. **Piece 4's "simple fix" doesn't work** — `autoloop_arm_pending` keeps
   `autoloop_ready` False until the next absolute 32-boundary, gating the very drop MIDI
   the piece is trying to rescue. BLOCKER 2.
4. **Breakdown does not "clear arm state in OutputState"** — it sends an OS2L
   deck-clear/loop-off; OutputState arm fields survive and `autoloop_ready` stays True.
   Matters because it explains why breakdown-scene MIDI passes executor gates today.
5. **Config keys are `manual_commands.blackout_on/off`**, not `manual_blackout_on/off`
   (the loader accepts both; the JSON uses `manual_commands`).
6. **`LaserSceneDef` doesn't exist** — the class is `LaserScene` (laser_models.py:53).
7. **The director's phrase machinery can't fire on marker-relative beats without a
   change the plan didn't list** — `_phrase_trigger_pending` is absolute-grid only.
   BLOCKER 4 / Task 5. Same hook is required for the breakdown-restore groove re-fire.
8. **Single shared blackout note across three masks** — the plan treats Smart Drop's
   blackout as a reusable primitive; it is a single un-refcounted latch with ~10 external
   resolve paths. BLOCKER 3 / Task 3.
9. **Buildup override contradicts current Priority 11 gating** (`is_up && !chorus`).
   Implementing the plan as written is a behavior change — called out, Task 6.
10. **OS2L 64-beat phrase anchor (`PHRASE_ANCHOR_BEATS`, smart_rearm `_phrase_anchor`)
    is a separate system** from the 32-beat MIDI grid being replaced. It stays on its
    drop-anchored absolute schedule and will still set `autoloop_tick_just_fired=True`
    on its own fires — that produces extra (harmless, idempotent) MIDI re-asserts.
    Do not modify it in this change.
11. **Latent mismatch, not fixed here:** with Piece 2, a 64-beat OS2L anchor fire and a
    32-beat marker-relative MIDI fire can land on different beats. Both re-assert the
    same look, so the visible effect is benign; unifying the OS2L anchor onto the
    marker-relative grid is future work.

---

# Part B — Codex Implementation Spec

## B1. Implementation Order

1. **Task 1** (Piece 5a) — PlaylistCache folder name. Independent. ⚠ requires operator
   confirmation of the folder string first.
2. **Task 2** (Piece 5b) — `_sp_phrase_lookahead` personality coupling. Independent.
3. **Task 3** (Piece 3/4 infra) — executor owner-mask blackout API. No behavior change
   by itself. Must land before Tasks 7 and 8.
4. **Task 4** (Piece 2) — `OutputState.midi_refire_origin_beat` + phrase-relative
   re-fire in the push loop + marker latch. Must land before or with Task 5.
5. **Task 5** (Piece 2 + Blocker 4) — director `_phrase_trigger_pending` latch on
   marker crossing / breakdown end.
6. **Task 6** (Piece 2) — buildup-window override in Priority 11.
7. **Task 7** (Piece 1) — `same_scene_skip` role-scoped pass-through. (Safe before or
   after 4/5; only useful once they're in.)
8. **Task 8** (Piece 3) — breakdown blackout via coordinator callables. Requires Task 3.
9. **Task 9** (Piece 4) — immediate master arm + master-switch mask. Requires Tasks 3, 4.
10. **Task 10** (Piece 6) — per-track phrase bank shuffle. Independent.

Do not start Task 8 before Task 3 is merged. Do not start Task 9 before Tasks 3 and 4.

---

## Task 1 — PlaylistCache folder name (Piece 5a)

**File:** `__main__.py`
**Function / location:** `main()`, line 693

**Current code:**
```python
        playlist_cache = PlaylistCache(RB_DB_PATH)
```

**Change:**
```python
        playlist_cache = PlaylistCache(RB_DB_PATH, folder_name="BY GENRE")
```

⚠ Confirm the literal string with the operator against Rekordbox first (A1 BLOCKER 5.2).

**Companion config change (same task):** in `config/laser_director.json`, give the
dubstep personality a playlist alias, e.g. `"aliases": ["dubstep"]`. Without it the
folder fix only ever matches house (`house` is the sole alias in the config and
`bpm_priority` is empty).

Optional cosmetic sub-change (`personality_resolver.py:158, 168, 200`): the log strings
say "PER GENRE folder ..." — replace with `self._folder_name` interpolation or leave.

**Invariants to preserve:**
- Do not change the `PersonalityResolver` default (other callers/tests rely on it).

**Verify after:**
- `/tmp/bridge.log` shows `[PERSONALITY] PER GENRE cache refreshed tracks=N playlists=M`
  with `N > 0` (today it logs `PER GENRE folder not found in Rekordbox DB`).
- Loading a track in a genre playlist logs `[PERSONALITY] deck=N ... (rule=playlist_match ...)`
  instead of `bpm_range_match`/`default`.

---

## Task 2 — `_sp_phrase_lookahead` follows personality (Piece 5b)

**File:** `state_manager.py`
**Function / location:** `_recache_personality_timing`, lines 1097-1115

**Current code:**
```python
        self._active_personality_for_timing = personality
        if personality is None:
            self._sp_drop_window = float(SMART_DROP_LOOKAHEAD_BEATS)
            self._sp_transition_window = float(SMART_DROP_LOOKAHEAD_BEATS)
            self._sp_post_drop = 8.0
            self._sp_breakdown_default_restore = SMART_BREAKDOWN_DEFAULT_DURATION_BEATS
        else:
            self._sp_drop_window = float(personality.pre_drop_blackout_beats)
            self._sp_transition_window = float(personality.pre_drop_blackout_beats)
            self._sp_post_drop = float(personality.post_drop_hold_beats)
            self._sp_breakdown_default_restore = int(
                personality.breakdown_default_restore_beats
            )
```

**Change:** add one line to each branch:
```python
        self._active_personality_for_timing = personality
        if personality is None:
            self._sp_drop_window = float(SMART_DROP_LOOKAHEAD_BEATS)
            self._sp_transition_window = float(SMART_DROP_LOOKAHEAD_BEATS)
            self._sp_post_drop = 8.0
            self._sp_breakdown_default_restore = SMART_BREAKDOWN_DEFAULT_DURATION_BEATS
            self._sp_phrase_lookahead = 32.0
        else:
            self._sp_drop_window = float(personality.pre_drop_blackout_beats)
            self._sp_transition_window = float(personality.pre_drop_blackout_beats)
            self._sp_post_drop = float(personality.post_drop_hold_beats)
            self._sp_breakdown_default_restore = int(
                personality.breakdown_default_restore_beats
            )
            self._sp_phrase_lookahead = float(personality.buildup_lookahead_beats)
```

**Invariants to preserve:**
- Line 383 (`__init__` default 32.0) stays as the pre-personality default.
- `_recache_personality_timing` is already called from `__init__` (via
  `_recache_initial_personality_timing`) and from `_apply_personality_change` — no new
  callsites needed.

**Verify after:**
- Load a dubstep-band track; `[SM] smart-transition-select` / snapshot
  `smart_phrasing.beats_to_next_drop` behavior: `smart_buildup_active` flips within 16
  (not 32) beats of the drop. Quick check: status JSON `smart_phrasing` while a dubstep
  track approaches a drop.

---

## Task 3 — Executor owner-mask blackout API (infra for Pieces 3 & 4)

**File:** `laser_executor.py`

### Sub-change 3a — field
**Location:** `__init__`, after line 61 (`self._blackout_pending_for_drop_window = False`)
```python
        self._blackout_pending_for_drop_window = False
        # Named blackout-mask holders (breakdown, master_switch). The physical
        # MIDI note is shared with the Smart Drop blackout; note_off is only
        # sent when BOTH the drop-window latch and this set are clear.
        self._mask_owners: set[str] = set()
```

### Sub-change 3b — new methods (insert after `_resolve_pending_blackout`, line 273)
```python
    def hold_blackout_mask(self, owner: str) -> None:
        """Hold the manual blackout note on behalf of *owner* (refcounted by name)."""
        if not self.smart_drop_blackout_enabled():
            return
        msg = self._config.manual_blackout_on
        if msg is None:
            return
        with self._lock:
            already_dark = bool(self._mask_owners) or self._blackout_pending_for_drop_window
            self._mask_owners.add(owner)
        if already_dark:
            return
        msg = replace(msg, kind="note_on", behavior="note_on")
        if self._midi_output.trigger(msg, priority="high"):
            log.info("[LX] mask_on  owner=%s  note=%s", owner, msg.note)
            return
        with self._lock:
            self._mask_owners.discard(owner)
        self._record_gate("manual_blackout_on_rejected")

    def release_blackout_mask(self, owner: str) -> None:
        """Release *owner*'s hold; sends note_off only when nothing else holds it."""
        with self._lock:
            if owner not in self._mask_owners:
                return
            self._mask_owners.discard(owner)
            still_dark = bool(self._mask_owners) or self._blackout_pending_for_drop_window
        log.info("[LX] mask_off  owner=%s  still_dark=%s", owner, still_dark)
        if still_dark:
            return
        msg = self._config.manual_blackout_off
        if msg is None:
            return
        msg = replace(msg, kind="note_off", behavior="note_off")
        if not self._midi_output.trigger(msg, priority="high"):
            self._record_gate("manual_blackout_off_rejected")

    def _release_all_masks(self) -> None:
        with self._lock:
            owners = tuple(self._mask_owners)
        for owner in owners:
            self.release_blackout_mask(owner)
```

### Sub-change 3c — guard `_resolve_pending_blackout` (lines 260-273)
**Current code:**
```python
    def _resolve_pending_blackout(self, *, reason: str) -> None:
        """Send blackout-off exactly once for each armed blackout window."""
        with self._lock:
            pending = self._blackout_pending_for_drop_window
            if pending:
                self._blackout_pending_for_drop_window = False
        if not pending:
            return
```
**Change:**
```python
    def _resolve_pending_blackout(self, *, reason: str) -> None:
        """Send blackout-off exactly once for each armed blackout window."""
        with self._lock:
            pending = self._blackout_pending_for_drop_window
            if pending:
                self._blackout_pending_for_drop_window = False
            owners_remain = bool(self._mask_owners)
        if not pending or owners_remain:
            return
```
(rest of the method unchanged)

### Sub-change 3d — clear paths
**Location:** `clear_pending_blackout`, lines 73-75:
```python
    def clear_pending_blackout(self, *, reason: str = "smart_drop_reset") -> None:
        """Clear a pending Smart Drop blackout window, if any."""
        self._release_all_masks()
        self._resolve_pending_blackout(reason=reason)
```
**Location:** `reset_runtime_state`, line 88 — replace
`self._resolve_pending_blackout(reason=reason)` with
`self.clear_pending_blackout(reason=reason)`.

### Sub-change 3e — observability
**Location:** `status()`, add to the returned dict (after
`"blackout_pending_for_drop_window"` line 296):
```python
                "blackout_mask_owners": sorted(self._mask_owners),
```

**Invariants to preserve:**
- `trigger_blackout_on` / drop-crossing resolution behavior unchanged when
  `_mask_owners` is empty (the Smart Drop live path is byte-identical in that case).
- `on_tick`'s `transition_mask_should_clear` → `_resolve_pending_blackout` must NOT lift
  a held breakdown/master mask (3c guarantees this).
- All `_clear_smart_rearm_state` callers (master change, track load, stop, idle,
  scripted arm, RB restart, toggles) lift every mask via 3d — a scripted show can never
  start masked.

**Verify after:**
- Unit: hold("a"), trigger drop blackout, resolve drop → no note_off; release("a") →
  note_off. Existing `tests/test_smart_drop.py` (32 tests) still pass.

---

## Task 4 — Phrase-relative 32-beat re-fire (Piece 2)

### Sub-change 4a — model field
**File:** `models.py`
**Location:** `OutputState`, after `phrase_anchor_last_beat: int = -1` (line 171):
```python
    phrase_anchor_last_beat: int = -1
    # Origin beat for the 32-beat MIDI re-fire counter (Piece 2). -1 = no phrase
    # marker seen yet on this track → fall back to the absolute 32-beat grid.
    midi_refire_origin_beat: int = -1
```

### Sub-change 4b — marker latch
**File:** `state_manager.py`
**Location 1:** `__init__`, after line 369 (`self._last_sp_state ... = None`):
```python
        self._last_sp_state: Optional[SmartPhrasingState] = None
        # Latches sp.phrase_anchor_requested (one 200 Hz tick) until the next
        # beat boundary consumes it, so a marker crossing can never be dropped.
        self._pending_phrase_marker: bool = False
```
**Location 2:** `_push_tick`, immediately after the sp_state computation (lines 1793-1795):
```python
        sp_state = self._update_smart_phrasing_state(
            active, d, abs_beat_pos, bpm,
        )
        if sp_state.phrase_anchor_requested:
            self._pending_phrase_marker = True
```
**Location 3:** `_clear_smart_rearm_state` (lines 2203-2218), add at the end:
```python
        os.phrase_anchor_last_beat = -1
        os.midi_refire_origin_beat = -1
        self._pending_phrase_marker = False
```

### Sub-change 4c — replace the absolute grid block
**File:** `state_manager.py`
**Function / location:** `_push_tick`, lines 1904-1916

**Current code:**
```python
                if os.lighting_mode == "autoloop":
                    phrase_beat = (this_beat // AUTOLOOP_ARM_PHRASE_BEATS) * AUTOLOOP_ARM_PHRASE_BEATS
                    if (
                        phrase_beat > 0
                        and phrase_beat > last_beat
                        and phrase_beat != os.last_autoloop_status_phrase_beat
                    ):
                        os.last_autoloop_status_phrase_beat = phrase_beat
                        grid_status = d.meta.beatgrid_source if grid_pos is not None else "fallback"
                        self._autoloop.log_autoloop_tick(
                            active, elapsed_ms, beatpos_out, bpm, d.meta.bpm, grid_status
                        )
                        autoloop_tick_just_fired = True
```

**Change:**
```python
                if os.lighting_mode == "autoloop":
                    # Phrase-relative MIDI re-fire (Piece 2):
                    #   primary  — RB phrase-marker crossing (latched), resets the counter
                    #   secondary— every 32 beats counted from the last marker fire
                    #   fallback — absolute 32-grid until the first marker is seen
                    marker_crossed = self._pending_phrase_marker
                    self._pending_phrase_marker = False
                    origin = os.midi_refire_origin_beat
                    refire = False
                    if marker_crossed:
                        refire = True
                    elif origin >= 0:
                        refire = (this_beat - origin) >= AUTOLOOP_ARM_PHRASE_BEATS
                    else:
                        refire = (
                            (this_beat // AUTOLOOP_ARM_PHRASE_BEATS)
                            > (last_beat // AUTOLOOP_ARM_PHRASE_BEATS)
                        )
                    if refire and this_beat != os.last_autoloop_status_phrase_beat:
                        os.midi_refire_origin_beat = this_beat
                        os.last_autoloop_status_phrase_beat = this_beat
                        grid_status = d.meta.beatgrid_source if grid_pos is not None else "fallback"
                        self._autoloop.log_autoloop_tick(
                            active, elapsed_ms, beatpos_out, bpm, d.meta.bpm, grid_status
                        )
                        autoloop_tick_just_fired = True
                        if self._laser_executor is not None:
                            self._laser_executor.release_blackout_mask("master_switch")
```
(The `release_blackout_mask` line requires Task 3; if Task 4 lands first, omit it and
add it with Task 9.)

**Invariants to preserve:**
- `AUTOLOOP_ARM_PHRASE_BEATS` (=32) remains the re-fire interval; do NOT use
  `PHRASE_ANCHOR_BEATS` (=64, the OS2L anchor).
- Do not modify `smart_rearm.py::_phrase_anchor` or `os.phrase_anchor_last_beat`
  handling — the OS2L 64-beat anchor is a separate system.
- Block stays exactly where the old one was: after `send_beat` + the arm-lock
  `autoloop.tick`, before the laser-context build, inside `if this_beat > last_beat:`.
- The arm-lock path (`was_arm_pending and not autoloop_arm_pending →
  autoloop_tick_just_fired = True`, lines 1897-1903) is unchanged.
- `os.last_autoloop_status_phrase_beat` keeps its existing reset sites; it now records
  the last fired beat (any value, not only multiples of 32).

**Verify after:**
- `/tmp/bridge.log`: `[SS][AUTOLOOP-TICK]` lines now land on PSSI marker beats (compare
  with `[SM] smart-transition-select` markers), then every +32 from the marker, e.g.
  marker at beat 50 → ticks at 50, 82, 114.
- On a track with no markers, ticks remain at 32/64/96 (fallback path).

---

## Task 5 — Director pending-latch on markers + breakdown end (Piece 2 / Blocker 4)

**File:** `laser_director.py`
**Function / location:** `_decide_phrase_default`, lines 547-574

**Current code (relevant lines):**
```python
        if phrase_changed:
            self._phrase_trigger_pending = True

        if self._phrase_trigger_pending and ctx.autoloop_tick_just_fired:
```

**Change:**
```python
        if phrase_changed:
            self._phrase_trigger_pending = True

        sp = ctx.smart_phrasing
        if sp is not None and (sp.phrase_anchor_requested or sp.breakdown_end_crossing):
            # Marker crossings and breakdown restores are phrase boundaries for
            # the marker-relative re-fire model; arm the pending latch so the
            # same-tick autoloop_tick_just_fired emits a phrase_boundary fire.
            self._phrase_trigger_pending = True

        if self._phrase_trigger_pending and ctx.autoloop_tick_just_fired:
```

**Invariants to preserve:**
- `first_playing_tick` early-return above this code is unchanged (default_init path).
- No change to `_PHRASE_TRIGGER_REASONS` or `_select_scene`.

**Verify after:**
- With Task 4 live: `[LX] fired role=phrase ... reason=phrase_boundary` appears at
  marker-relative beats, not only at absolute 32-grid beats.
- After a breakdown ends: `[LX] fired role=phrase` (or `role=buildup`) within 1 beat of
  `[SM] smart-breakdown-restore`.

---

## Task 6 — Buildup window overrides phrase label (Piece 2)

**File:** `laser_director.py`
**Function / location:** `_decide`, Priority 11, lines 486-501

**Current code:**
```python
        if (
            self._buildup_scene
            and not in_post_drop_hold
            and current_phrase_is_up
            and not current_phrase_is_chorus
            and self._buildup_lookahead_beats > 0
            and 0 < beats_to_next_drop <= self._buildup_lookahead_beats
        ):
```

**Change:**
```python
        if (
            self._buildup_scene
            and not in_post_drop_hold
            and self._buildup_lookahead_beats > 0
            and 0 < beats_to_next_drop <= self._buildup_lookahead_beats
        ):
```

**Invariants to preserve:**
- `in_post_drop_hold` exclusion stays — a drop look in its hold window must not be
  replaced by buildup when two drops are < lookahead apart.
- Leave the (now partially unused) `current_phrase_is_up`/`current_phrase_is_chorus`
  locals in place — `current_phrase_is_up` feeds nothing else here, but removing the
  assignments is unnecessary churn.
- Do not touch `smart_buildup_active` in `smart_phrasing.py` (it has no runtime
  consumer; leave as-is).

**Verify after:**
- On a track whose ANLZ has no explicit "up" label right before a drop, the 32 (house) /
  16 (dubstep, after Task 2) beats before the drop log
  `[LX] fired role=buildup reason=buildup_to_drop_window`.

---

## Task 7 — `same_scene_skip` pass-through (Piece 1)

**File:** `laser_executor.py`
**Function / location:** `on_decision`, lines 187-199

**Current code:**
```python
        same_scene_skip = False
        with self._lock:
            if (
                role not in ("manual", "emergency")
                and not is_drop_crossing
                and selected_scene == self._last_triggered_scene
            ):
                self._same_scene_skip_count += 1
                same_scene_skip = True
```

**Change:**
```python
        same_scene_skip = False
        refire_roles = ("phrase", "buildup", "breakdown")
        with self._lock:
            if (
                role not in ("manual", "emergency")
                and not is_drop_crossing
                and selected_scene == self._last_triggered_scene
                and not (
                    ctx.autoloop_tick_just_fired
                    and role in refire_roles
                    and scene_def.scene_type == "autoloop"
                )
            ):
                self._same_scene_skip_count += 1
                same_scene_skip = True
```

**Invariants to preserve:**
- `drop` and `post_drop` roles must NEVER pass through — the drop_mode post-drop hold
  (laser_director.py Priority 10, reason `drop_hold`) relies on this latch, and 9 of 10
  house drop scenes are typed `autoloop` in config, so a `scene_type`-only condition is
  NOT safe (A1 BLOCKER 1).
- Static scenes never pass through (the `scene_type == "autoloop"` clause).
- The role-cooldown check (lines 174-185) runs before this and still applies: groove=8,
  breakdown=16, buildup=32 cooldown beats — a 32-beat re-fire passes all (strict `<`).
- The `_select_scene` phrase gate (316-321) is untouched; both guards remain.

**Verify after:**
- During a long "up" section (length-1 buildup bank): `[LX] fired role=buildup`
  repeats at each autoloop tick instead of once. Same for `role=breakdown` (until Task 8
  masks it) and length-1 phrase banks.
- During post-drop hold: NO repeated `[LX] fired role=drop` at an autoloop tick.

---

## Task 8 — Breakdown MIDI blackout (Piece 3)

### Sub-change 8a — coordinator wiring
**File:** `smart_rearm.py`
**Location:** `SmartRearmCoordinator.__init__`, lines 51-64

**Current code:**
```python
    def __init__(
        self,
        *,
        output_state_ref: Callable[[], OutputState],
        deck_ref: Callable[[int], DeckState],
        send_direct_autoloop_rearm: Callable[..., None],
        send_smart_transition_clear: Callable[..., None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._output_state_ref = output_state_ref
        self._deck_ref = deck_ref
        self._send_direct_autoloop_rearm = send_direct_autoloop_rearm
        self._send_smart_transition_clear = send_smart_transition_clear
        self._clock = clock
```

**Change:**
```python
    def __init__(
        self,
        *,
        output_state_ref: Callable[[], OutputState],
        deck_ref: Callable[[int], DeckState],
        send_direct_autoloop_rearm: Callable[..., None],
        send_smart_transition_clear: Callable[..., None],
        hold_blackout_mask: Optional[Callable[[str], None]] = None,
        release_blackout_mask: Optional[Callable[[str], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._output_state_ref = output_state_ref
        self._deck_ref = deck_ref
        self._send_direct_autoloop_rearm = send_direct_autoloop_rearm
        self._send_smart_transition_clear = send_smart_transition_clear
        self._hold_blackout_mask = hold_blackout_mask or (lambda owner: None)
        self._release_blackout_mask = release_blackout_mask or (lambda owner: None)
        self._clock = clock
```
(Defaults keep `tests/test_smart_drop.py` constructions working unchanged.)

### Sub-change 8b — breakdown start: blackout instead of OS2L clear
**File:** `smart_rearm.py`
**Location:** `_breakdown`, lines 254-266

**Current code:**
```python
        if (
            sp_state.breakdown_start_crossing
            and sp_state.breakdown_restore_beat is not None
        ):
            log.info(
                "[SM] smart-breakdown-cut  deck=%d  beat=%d",
                active,
                ctx.this_beat,
            )
            self._send_smart_transition_clear(active)
            os.breakdown_active = True
            os.breakdown_restore_beat = int(sp_state.breakdown_restore_beat)
        return False
```

**Change:**
```python
        if (
            sp_state.breakdown_start_crossing
            and sp_state.breakdown_restore_beat is not None
        ):
            if ctx.blackout_mode:
                log.info(
                    "[SM] smart-breakdown-blackout  deck=%d  beat=%d",
                    active,
                    ctx.this_beat,
                )
                self._hold_blackout_mask("breakdown")
            else:
                log.info(
                    "[SM] smart-breakdown-cut  deck=%d  beat=%d",
                    active,
                    ctx.this_beat,
                )
                self._send_smart_transition_clear(active)
            os.breakdown_active = True
            os.breakdown_restore_beat = int(sp_state.breakdown_restore_beat)
        return False
```

### Sub-change 8c — breakdown restore: lift the mask
**File:** `smart_rearm.py`
**Location:** `_breakdown`, lines 233-252

**Current code:**
```python
        if os.breakdown_active:
            if sp_state.breakdown_end_crossing:
                log.info(
                    "[SM] smart-breakdown-restore  deck=%d  beat=%d",
                    active,
                    ctx.this_beat,
                )
                if self._send_direct_autoloop_rearm(
```

**Change (insert one line before the rearm attempt):**
```python
        if os.breakdown_active:
            if sp_state.breakdown_end_crossing:
                log.info(
                    "[SM] smart-breakdown-restore  deck=%d  beat=%d",
                    active,
                    ctx.this_beat,
                )
                self._release_blackout_mask("breakdown")
                if self._send_direct_autoloop_rearm(
```
(Release happens unconditionally at the end crossing — even if the rearm fails, the
lasers must not stay dark. The OS2L rearm itself is intentionally KEPT: it re-anchors
SS's loop phase at the restore beat and is the live-validated smart-rearm pattern.)

### Sub-change 8d — StateManager wiring
**File:** `state_manager.py`
**Location:** `__init__`, `SmartRearmCoordinator` construction, lines 408-413

**Current code:**
```python
        self._smart_rearm = SmartRearmCoordinator(
            output_state_ref=lambda: self._os,
            deck_ref=lambda d: self._deck[d],
            send_direct_autoloop_rearm=_autoloop_rearm_bridge,
            send_smart_transition_clear=self._sse.send_smart_transition_clear,
        )
```

**Change:**
```python
        def _hold_mask(owner: str) -> None:
            if self._laser_executor is not None:
                self._laser_executor.hold_blackout_mask(owner)

        def _release_mask(owner: str) -> None:
            if self._laser_executor is not None:
                self._laser_executor.release_blackout_mask(owner)

        self._smart_rearm = SmartRearmCoordinator(
            output_state_ref=lambda: self._os,
            deck_ref=lambda d: self._deck[d],
            send_direct_autoloop_rearm=_autoloop_rearm_bridge,
            send_smart_transition_clear=self._sse.send_smart_transition_clear,
            hold_blackout_mask=_hold_mask,
            release_blackout_mask=_release_mask,
        )
```

**Invariants to preserve:**
- Scripted arms: untouched. The OS2L unarm for scripted (`send_scripted_arm_phase0`)
  stays; `_apply_lighting("scripted")` → `_clear_smart_rearm_state` →
  `clear_pending_blackout` lifts the breakdown mask before any scripted show starts
  (Task 3d).
- `ctx.blackout_mode == False` (mask MIDI unconfigured / legacy mode) falls back to the
  current OS2L-clear behavior — never a silent no-op breakdown.
- `os.breakdown_active` semantics unchanged — it still suppresses smart drop, phrase
  anchor, and blackout-arm during the breakdown.
- A breakdown start while `os.drop_cut_armed` is still skipped (existing guard, line
  230) — drop and breakdown masks therefore never overlap-arm.

**Verify after:**
- `/tmp/bridge.log` at a breakdown: `[SM] smart-breakdown-blackout` + `[LX] mask_on
  owner=breakdown`; SS goes dark but `[SS][AUTOLOOP-TICK]` lines continue (deck still
  armed — this is the point of the change).
- At restore: `[LX] mask_off owner=breakdown` + `[SM] smart-breakdown-restore` +
  `[SM] autoloop-rearm ... reason=smart-breakdown` + a `[LX] fired role=phrase|buildup`
  within the same beat (Task 5 hook).
- Load a scripted track mid-breakdown: mask lifts (`[LX] mask_off`) before
  `[SM] arm-scripted`.

---

## Task 9 — Immediate arm on master switch + transition mask (Piece 4)

### Sub-change 9a — callsite passes False + holds the mask
**File:** `state_manager.py`
**Location:** `_apply_lighting`, autoloop branch, lines 1499-1507

**Current code:**
```python
        elif mode == "autoloop":
            self._clear_smart_rearm_state()
            self._pending_arm = None
            self._autoloop.arm_autoloop(
                deck,
                elapsed_ms,
                bpm,
                self._autoloop_master_phrase_arm,
            )
```

**Change:**
```python
        elif mode == "autoloop":
            self._clear_smart_rearm_state()
            self._pending_arm = None
            if (
                self._os.autoloop_arm_after_master_change
                and self._laser_executor is not None
                and self._laser_director is not None
                and self._laser_director.is_enabled()
            ):
                # Mask the transition: SS stays dark from the master switch until
                # the first phrase-relative re-fire (Task 4 releases this owner).
                self._laser_executor.hold_blackout_mask("master_switch")
            self._autoloop.arm_autoloop(
                deck,
                elapsed_ms,
                bpm,
                False,
            )
```
Notes: `_clear_smart_rearm_state()` (line above) releases all masks, so the hold must
come after it — the order above is mandatory. `self._autoloop_master_phrase_arm` and the
`RBSS_AUTOLOOP_MASTER_PHRASE_ARM` env become inert for this callsite (the only one);
leave the attribute/env parsing in place and note it for a later cleanup PR.

### Sub-change 9b — immediate finalization in the controller
**File:** `autoloop_controller.py`
**Location:** `arm_autoloop`, immediate-arm branch, lines 257-259

**Current code:**
```python
            else:
                self._sse.send_autoloop_deck_load(deck, mirror, deck, arm_meta)
                if arm_after_master and autoloop_master_phrase_arm:
```

**Change:**
```python
            else:
                self._sse.send_autoloop_deck_load(deck, mirror, deck, arm_meta)
                if arm_after_master and not autoloop_master_phrase_arm:
                    # Immediate master-switch arm: finalize now (mirror the
                    # _maybe_lock_autoloop_arm finalization) so autoloop_ready /
                    # smart-rearm gates open without waiting for the next
                    # absolute 32-beat boundary. The MIDI transition mask covers
                    # the un-phased window visually.
                    self._sse.send_autoloop_bpm(deck, arm_bpm)
                    os.last_sent_bpm = arm_bpm
                    self.clear_arm_phrase_lock()
                    self._log.info(
                        "[SM] arm-immediate  deck=%d  beat=%.1f  bpm=%.2f  src=%s",
                        deck,
                        abs_beat,
                        arm_bpm,
                        arm_source or "<none>",
                    )
                if arm_after_master and autoloop_master_phrase_arm:
```
(The old grace-late block under `arm_after_master and autoloop_master_phrase_arm`
becomes unreachable from the live callsite but stays intact in case the flag is ever
passed True again.)

**Invariants to preserve:**
- Non-master arms (`arm_after_master == False`) are byte-identical: they still pend to
  the next 32-beat lock — this change is scoped to master switches only.
- The no-filepath arm path (lines 286-294) is unchanged.
- `should_delay_master_arm`, `next_arm_phrase`, `_maybe_lock_autoloop_arm` are unchanged.
- Mask release points (all already exist after Tasks 3/4): the Task 4 re-fire block
  (`release_blackout_mask("master_switch")` — first marker or 32-grid fallback beat, and
  drop crossings count because a drop is a chorus-segment marker), plus every
  `_clear_smart_rearm_state` path (stop/idle/track load/scripted/next switch).

**Verify after:**
- Master switch onto a playing unscripted deck: log shows `[SM] arm-autoloop` +
  `[SM] arm-immediate` (no `[SM] arm-pending`/`[SM] clear-autoloop`), `[LX] mask_on
  owner=master_switch`, and at the next marker / 32-grid beat: `[SS][AUTOLOOP-TICK]` +
  `[LX] mask_off owner=master_switch` + `[LX] fired role=...`.
- Drop landing between switch and first anchor: `[SM] smart-drop-*` fires and the drop
  note goes out (this exact sequence is the bug being fixed — verify the note in the SS
  MIDI monitor).
- Master switch onto a scripted deck: NO `mask_on owner=master_switch`
  (`autoloop_arm_after_master_change` is consumed by the scripted branch clearing).

---

## Task 10 — Per-track groove bank shuffle (Piece 6)

**File:** `laser_executor.py`

### Sub-change 10a — field
**Location:** `__init__`, insert BEFORE `self._role_cursors = self._seed_role_cursors()`
(line 58):
```python
        self._role_bank_shuffle: dict[str, tuple[str, ...]] = {}
        self._role_cursors = self._seed_role_cursors()
```

### Sub-change 10b — reshuffle helper (insert after `_seed_role_cursors`, line 350)
```python
    def _reshuffle_phrase_bank_locked(self) -> None:
        """Re-randomize phrase-bank traversal order. Caller must hold self._lock."""
        personality = self._personality
        bank = list(personality.phrase_bank) if personality is not None else []
        if len(bank) > 1:
            self._rng.shuffle(bank)
            self._role_bank_shuffle["phrase"] = tuple(bank)
            self._role_cursors["phrase"] = 0
        else:
            self._role_bank_shuffle.pop("phrase", None)
```

### Sub-change 10c — hook into lifecycle resets
**Location:** `reset_runtime_state`, lines 77-88

**Current code:**
```python
            if reset_cursors:
                self._role_cursors = self._seed_role_cursors()
            self._role_active_scene = {role: "" for role in _AUTO_ROLES}
```
**Change:**
```python
            if reset_cursors:
                self._role_cursors = self._seed_role_cursors()
            self._reshuffle_phrase_bank_locked()
            self._role_active_scene = {role: "" for role in _AUTO_ROLES}
```
(`reset_runtime_state` fires on `active_track_loaded`, `master_changed`, `stop`, and
`set_personality` — every track-context boundary. Reshuffling on stop is harmless.)

### Sub-change 10d — serve the shuffled bank
**Location:** `_bank_for_role`, lines 352-366

**Current code:**
```python
        if role == "phrase":
            return personality.phrase_bank
```
**Change:**
```python
        if role == "phrase":
            shuffled = self._role_bank_shuffle.get("phrase")
            if shuffled:
                return shuffled
            return personality.phrase_bank
```

**Invariants to preserve:**
- Config data is never mutated — the shuffle is a copied tuple.
- Other roles (`buildup`, `drop`, `post_drop`, `breakdown`) read the config bank
  directly; drop-bank rotation behavior is unchanged.
- `_choose_bank_scene_locked` cursor logic unchanged (`cursor % len(bank)`); a shuffled
  permutation + sequential cursor ⇒ all 32 grooves appear exactly once per wrap.
- `_seed_role_cursors` is called in `__init__` before any shuffle exists — 10a's
  ordering (shuffle dict initialized first) is required; the seed only reads bank
  lengths, which the shuffle never changes.
- Thread-safety: `_role_bank_shuffle` is written only under `self._lock`
  (reset_runtime_state) and read under `self._lock` (`_choose_bank_scene_locked` →
  `_bank_for_role`).

**Verify after:**
- Restart bridge, play two different tracks: `[LX] fired role=phrase scene=...`
  sequences differ per track and never repeat a scene within 32 fires.
- `status()` `role_cursors["phrase"]` resets to 0/1 on each track load.

---

## B3. Operator Prerequisites (not Codex)

1. **SoundSwitch MIDI mappings** for every scene in `personalities.house.phrase_bank`
   (`house_groove_1..32` — notes per `config/laser_director.json`, e.g. groove_1 =
   note 32 ch 1), and verify `house_buildup_1` / `house_breakdown_1` mappings exist.
   Without these, re-fires are sent but SS ignores them.
2. **Confirm the Rekordbox playlist folder name** is exactly `BY GENRE` (Task 1 blocks
   on this).
3. After deploy: restart via the menu-bar toggle and confirm exactly ONE bridge process
   (`pgrep -f rb_ss_bridge_v2 | wc -l` → `1`).
4. No watcher env changes are required: `RBSS_SMART_REARM_EXPERIMENT=1`,
   `RBSS_SMART_DROP=1`, `RBSS_SMART_BREAKDOWN=1` are already set;
   `RBSS_AUTOLOOP_MASTER_PHRASE_ARM` is unset and becomes inert after Task 9.
5. First live test should be a low-stakes set: watch for
   `[LX] mask_on`/`mask_off` pairing (never a lone `mask_on` without a matching off
   within ~32 beats outside breakdowns) and for repeated `[LX] fired role=drop` during
   post-drop holds (must not happen).
