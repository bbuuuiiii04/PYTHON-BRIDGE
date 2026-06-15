# Implementation Spec — LED Role Mapping v2 (ambient→groove, chorus drop-hold/cycle → post_drop)

Status: ACTIVE. Implementer: Codex. Reviewer: Claude.
Package: `rb_ss_bridge_v2`. Live DJ rig — role changes are visible to an audience. Implement exactly.

---

## Part A — Context (read, do not implement)

`_led_role_from_smart_phrasing` (`state_manager.py:1873-1886`) maps the smart-phrasing state to a
lighting role; the director then picks a look from the matching bank. Today:

```python
if smart_drop_crossing:          return "drop"        # the drop is true for ONE beat (the hit)
if breakdown...:                 return "breakdown"
if smart_post_drop_active:       return "post_drop"    # fixed post_drop_beats window after ANY drop
if transition_window_active:     return "pre_drop"
if _led_buildup_active:          return "buildup"      # only in an "up" phrase with a drop in lookahead
if current_phrase_is_chorus:     return "groove"
return "ambient"                                       # everything else while PLAYING falls here
```

Two problems this spec fixes:
1. **Dead baseline.** The playing catch-all returns `ambient`, which is also what the *stopped*
   path (`_dispatch_led_idle_ambient`) uses. Ambient looks are static, so verses / long ups / full
   tracks look dead. Fix: the playing catch-all becomes `groove` (beat-driven). Ambient stays the
   stopped-only state (that path is untouched).
2. **Chorus deflates instantly.** `drop` is true for one beat (the hit); after a fixed
   `post_drop_beats` window the chorus drops to `groove`. And nothing **cycles** — each role fires
   one look and holds it (the look only re-fires when the role_key changes). Fix: during a chorus,
   **hold + cycle the drop** for `LED_DROP_HOLD_BEATS`, then **sustain post_drop** for the rest of
   the chorus; `post_drop` now occurs **only inside a chorus phrase, after the hold** (matches the
   operator's intent: "post_drops can only occur in chorus markings AND after N beats after a drop").

**Cycling mechanism (already in the codebase):** the director advances a per-role bank cursor every
time it dispatches that role (`led_look_director.py:201-212`). It only dispatches when the role_key
**changes** (`state_manager.py:1578`: same key → return). So "cycle" = make the role_key change over
time; "hold" = keep it stable. We cycle the drop by bucketing its role_key by beats-into-the-chorus.

**Grounding facts (verified):**
- `PhraseSegment` has `start_beat`/`end_beat` (`smart_phrasing.py`, `PhraseSegment`) and
  `_compute_tick_state` already resolves the current segment by those bounds → "beats into the
  current phrase" is derivable where the current segment is resolved.
- `_led_buildup_active` requires `current_phrase_is_up and not current_phrase_is_chorus`
  (`state_manager.py:1895-1898`) → it never fires during a chorus, so it cannot conflict with the new
  chorus block.
- Live `default` bank: `drop` has 14 looks; `post_drop` and `pre_drop` are **empty** today.
  Drop role-key buckets advance every 16 beats. Because the hold window is also 16 beats, the
  selected drop look holds through the first 16 counts; with an empty `post_drop` bank, LED dispatch
  falls back to the `drop` role and continues cycling drop looks every 16 counts through the chorus.
  Populating `post_drop` is recommended curation (Part E), not required for this code to be safe.
- `smart_post_drop_active` / `active_drop_beat` stay computed in smart_phrasing for other consumers
  (`smart_rearm.py` uses `active_drop_beat`); this spec only stops the **LED role** from using
  `smart_post_drop_active`.

**Out of scope (deferred):** the `lift` tier for ups-outside-a-buildup-window. It would require a new
bank role (`_BANK_ROLES` makes every role mandatory in every bank — `led_config.py:397-399` — so it
forces edits to every bank in the live config). With this spec, ups outside a buildup window fall to
the `groove` baseline (already a big win over dead ambient). Add `lift` later if desired.

---

## Part B — Tasks (implement in order)

### Absolute rules
- Follow this spec exactly; use the shown current→replacement code.
- Do NOT edit `config/led_look_director.json` (Part E is operator curation, not yours).
- Do NOT change `smart_post_drop_active` / `active_drop_beat` computation or any laser/rearm code.
- Work on a branch. If commits are explicitly authorized and the worktree can be staged narrowly,
  commit after each task; otherwise leave changes uncommitted and report why. Do not deploy or
  restart the bridge.
- If a `file:line` reference drifted, locate by the quoted snippet / function name.

---

### Task 1 — `state_manager.py`: module constants

Add near the other module timing constants (around `state_manager.py:112`, by
`_SNAPSHOT_PUBLISH_INTERVAL_S`):

```python
LED_DROP_HOLD_BEATS = 16.0   # chorus: hold + cycle the drop look this many beats, then post_drop
LED_DROP_CYCLE_BEATS = 16.0  # chorus drop: advance to the next drop-bank look every N beats
```

### Task 2 — `smart_phrasing.py`: expose `beats_into_phrase`

**2a.** Add a field to `SmartPhrasingState` (after `current_phrase_is_low`, `:47`):
```python
    beats_into_phrase: Optional[float] = None
```

**2b.** In `_compute_tick_state`, capture the current phrase's start and compute the offset. Replace
the current-phrase resolution block (`:266-280`):

current:
```python
        current_phrase_label: PhraseLabel = "other"
        phrase_anchor_requested = False

        for seg in snapshot.phrase_segments:
            if prev_abs_beat is not None and prev_abs_beat < seg.start_beat <= abs_beat:
                phrase_anchor_requested = True

            if seg.start_beat <= abs_beat < seg.end_beat:
                current_phrase_label = seg.label
                break

        current_phrase_is_up = current_phrase_label == "up"
        current_phrase_is_chorus = current_phrase_label == "chorus"
        current_phrase_is_low = current_phrase_label == "low"
```
replacement:
```python
        current_phrase_label: PhraseLabel = "other"
        current_phrase_start_beat: Optional[float] = None
        phrase_anchor_requested = False

        for seg in snapshot.phrase_segments:
            if prev_abs_beat is not None and prev_abs_beat < seg.start_beat <= abs_beat:
                phrase_anchor_requested = True

            if seg.start_beat <= abs_beat < seg.end_beat:
                current_phrase_label = seg.label
                current_phrase_start_beat = seg.start_beat
                break

        current_phrase_is_up = current_phrase_label == "up"
        current_phrase_is_chorus = current_phrase_label == "chorus"
        current_phrase_is_low = current_phrase_label == "low"
        beats_into_phrase = (
            abs_beat - current_phrase_start_beat
            if current_phrase_start_beat is not None else None
        )
```

**2c.** Pass it into the returned `SmartPhrasingState(...)` (the constructor near `:414-425`), add:
```python
            beats_into_phrase=beats_into_phrase,
```

### Task 3 — `state_manager.py`: new role mapping

Replace `_led_role_from_smart_phrasing` (`:1873-1886`) entirely:
```python
    def _led_role_from_smart_phrasing(self, sp_state: SmartPhrasingState) -> str:
        if sp_state.smart_drop_crossing:
            return "drop"
        if sp_state.smart_breakdown_active or sp_state.breakdown_start_crossing:
            return "breakdown"
        if sp_state.transition_window_active:
            return "pre_drop"
        if self._led_buildup_active(sp_state):
            return "buildup"
        if sp_state.current_phrase_is_chorus:
            # Chorus = the drop section. Hold + cycle the drop for the first
            # LED_DROP_HOLD_BEATS, then sustain post_drop for the rest of the chorus.
            bip = sp_state.beats_into_phrase
            if bip is None or bip < LED_DROP_HOLD_BEATS:
                return "drop"
            return "post_drop"
        if sp_state.current_phrase_is_low:
            return "breakdown"
        return "groove"
```
Changes vs current: removed the standalone `smart_post_drop_active` branch (post_drop is now
chorus-only, after the hold); chorus splits into drop-hold → post_drop; `low` phrases map to the
(calm) breakdown bank; the playing catch-all is `groove` instead of `ambient`.

### Task 4 — `state_manager.py`: cycle the drop in the role_key

Replace the marker block of `_led_automation_role_key` (`:1907-1915`):

current:
```python
        marker = ""
        if role in {"drop", "post_drop"} and sp_state.active_drop_beat is not None:
            marker = f"{sp_state.active_drop_beat:.3f}"
        elif role in {"buildup", "pre_drop"} and sp_state.next_smart_drop_beat is not None:
            marker = f"{sp_state.next_smart_drop_beat:.3f}"
        elif role == "breakdown" and sp_state.breakdown_restore_beat is not None:
            marker = f"{sp_state.breakdown_restore_beat:.3f}"
        elif role in {"ambient", "groove"}:
            marker = str(sp_state.current_phrase_label)
```
replacement:
```python
        marker = ""
        if role == "drop":
            bip = sp_state.beats_into_phrase
            if bip is not None:
                # Bucket by beats-into-chorus so the key changes every cycle -> the drop bank cycles.
                marker = f"c{int(bip // LED_DROP_CYCLE_BEATS)}"
            elif sp_state.active_drop_beat is not None:
                marker = f"{sp_state.active_drop_beat:.3f}"
        elif role == "post_drop":
            marker = str(sp_state.current_phrase_label)   # stable -> one sustained post_drop look
        elif role in {"buildup", "pre_drop"} and sp_state.next_smart_drop_beat is not None:
            marker = f"{sp_state.next_smart_drop_beat:.3f}"
        elif role == "breakdown" and sp_state.breakdown_restore_beat is not None:
            marker = f"{sp_state.breakdown_restore_beat:.3f}"
        elif role in {"ambient", "groove"}:
            marker = str(sp_state.current_phrase_label)
```
(The final `return f"{active}:{d.load_gen}:{role}:{marker}"` line is unchanged.)

### Task 5 — `state_manager.py`: empty post_drop falls back to drop dispatch

After computing `role = self._led_role_from_smart_phrasing(sp_state)`, apply an effective dispatch
role:
- If role is not `post_drop`, dispatch it unchanged.
- If `post_drop` has a mapped preview decision, dispatch `post_drop`.
- If `post_drop` has no mapped preview decision but `drop` does, dispatch `drop`.
- If neither previews, leave `post_drop` unchanged so normal no-look telemetry still reports the
  missing mapping.

This keeps the future `post_drop` bank behavior intact while today's empty `post_drop` bank continues
cycling the drop bank every `LED_DROP_CYCLE_BEATS` counts during chorus.

---

## Part C — Tests

### `tests/test_smart_phrasing.py` (extend)
- `beats_into_phrase` is `abs_beat - current_phrase_start` when inside a segment; `None` when no
  segment covers `abs_beat`. Use the existing snapshot/segment fixtures in this file.

### `tests/test_led_state_manager.py` (extend + update)
Mirror the existing `_led_role_from_smart_phrasing` tests (build a `SmartPhrasingState(...)` and
assert the returned role):
- chorus, `beats_into_phrase=4.0` (< HOLD) → `"drop"`.
- chorus, `beats_into_phrase=20.0` (>= HOLD) → `"post_drop"`.
- chorus, `beats_into_phrase=None` → `"drop"` (safe default).
- `smart_drop_crossing=True` → `"drop"` (priority over chorus split).
- playing, non-chorus, label `"other"` → `"groove"` (was `"ambient"`).
- `current_phrase_is_low=True` (no breakdown detector) → `"breakdown"`.
- buildup still wins: `_led_buildup_active` true → `"buildup"` (set up `beats_to_next_drop` within
  lookahead, `current_phrase_is_up=True`).
- **role_key cycling:** for role `"drop"`, two states with `beats_into_phrase=4.0` and `=12.0`
  produce the **same** key (holds within a 16-count bucket); `=4.0` and `=20.0` produce
  **different** keys (next 16-count bucket). For role `"post_drop"`, two states with different
  `beats_into_phrase` but the same `current_phrase_label` produce the **same** key (sustained, one
  look).
- **empty `post_drop` fallback:** after the hold, if `post_drop` has no mapped look but `drop` does,
  dispatch uses `drop`; verify `beats_into_phrase=20.0` and `=36.0` produce two drop dispatches,
  while a same-bucket tick such as `=28.0` does not re-dispatch.
- **mapped `post_drop`:** when `post_drop` has a mapped preview decision, dispatch stays on
  `post_drop` after the hold.
- **Update existing assertions** that expected the old `"ambient"` for a playing non-chorus phrase →
  now `"groove"`. These are intended behavior changes, not regressions.

### Golden traces (`tests/test_golden_trace.py` and any recorded-trace fixtures)
Run the golden-trace tests after the role change. Current `tests/test_golden_trace.py` exercises laser
Smart Drop traces rather than LED role sequences, so fixture regeneration is not expected unless a
test failure proves an affected trace. If any recorded trace does change, regenerate/update only that
fixture and **manually verify the diff contains only the intended role changes** (ambient→groove on
playing non-chorus phrases; chorus → drop-cycle → post_drop). Do not blanket-accept golden changes
without reading the diff.

---

## Part D — Acceptance

1. From the repo root, `python3 -m unittest discover -s tests -p 'test*.py'` green (with intended
   golden/role-test updates if any).
2. Role unit tests above pass.
3. A simulated chorus phrase: role goes `drop` for the first `LED_DROP_HOLD_BEATS`; after that,
   mapped `post_drop` sustains with a stable key, while an empty `post_drop` bank falls back to
   `drop` and cycles every `LED_DROP_CYCLE_BEATS` until the chorus segment ends. Once the phrase
   label leaves `chorus`, role returns to `groove`.
4. A playing non-chorus phrase yields `groove`, never `ambient`; the stopped path still yields ambient.

---

## Part E — Operator curation (NOT Composer — Brandon does this after merge)

- **`post_drop` bank is empty today.** Until you add looks to it, the post-hold chorus phase falls
  back to the `drop` bank and advances every 16 counts. Add 1–3 sustained, slightly-lower-energy
  looks to `banks.default.post_drop` in `config/led_look_director.json` to get a distinct post-drop
  feel.
- **`groove` bank** already has 14 looks (DIY + beat-driven `rt_*`). For the liveliest baseline,
  weight toward the beat-driven `rt_groove_*` looks.
- **Tuning:** `LED_DROP_HOLD_BEATS` (default 16; your stated 8–16 range) and `LED_DROP_CYCLE_BEATS`
  (default 16) are module constants in `state_manager.py` — adjust to taste.
- **Deferred:** the `lift` tier for ups-with-no-drop (see Part A) — say the word and it's a follow-up
  spec (new bank role + config edits to every bank).
