# Pre-Implementation Audit: Section-Correct Autoloop Selection
## rb_ss_bridge_v2 — Fable Code Audit Prompt

---

## Your Role

You are doing a pre-implementation code audit for a feature in `rb_ss_bridge_v2`, a
real-time Rekordbox → SoundSwitch bridge for EDM laser shows. Your job is to verify
the implementation plan against current code, identify every gap, confirm every
line-number claim, and then produce a complete Codex implementation spec. The spec is
the primary deliverable — the audit exists to make the spec correct.

This runs live at shows. Wrong-section laser looks are immediately visible to an audience.
Rigor matters: do not produce the spec until you have verified the claims it depends on.

Label every finding: **CONFIRMED** (verified in current code), **ASSUMED** (plausible
but not verified), or **UNKNOWN** (cannot be determined without runtime data or
additional files).

There is no separate Codex implementation plan document. Derive everything from the
source files listed below and this prompt only. Do not look for or reference any external
plan file.

---

## System Context

### What the bridge does
Rekordbox → SoundSwitch (OS2L/VirtualDJ over TCP). Direct RB memory chains — no Frida.
Outputs: beat sync, BPM, elapsed, scripted show arms, autoloop arms, MIDI via
LaserDirector → IAC Bus 1 → SoundSwitch MIDI mappings → laser looks.

### SoundSwitch autoloop constraints (operator-confirmed, do not re-litigate)
1. Autoloop cycling cannot be disabled — it must be on and cycling for any autoloop to play.
2. Cycling is global and ungateable — random or sequential across the entire pool only.
3. Each autoloop is exactly 8 bars (32 beats at the track BPM).
4. A MIDI note selects *which* autoloop fires. It does NOT restart SS's 8-bar loop phase.
5. Consequence: without the bridge intervening at every 8-bar slot, SS freelances to a
   random look — including surfacing a drop look during a groove section.

### Current MIDI output state
- **Smart Drop**: fires `manual_blackout_on` MIDI one beat before the drop, then a drop
  MIDI note on the crossing. Both paths are already live.
- **Smart Breakdown**: currently unarming the OS2L autoloop (sends `send_deck_clear` /
  `send_loop_off`). This is changing — see §Breakdown MIDI Blackout below.
- **Groove looks**: NO MIDI mappings exist in SoundSwitch yet. This is a prerequisite
  the operator must add manually. Flag this in your output.

### What "autoloop armed" means
The bridge sends OS2L `get_loop` / `play on` / `loop on` to SoundSwitch, which registers
the deck as playing an autoloop. MIDI notes only take effect on an armed deck. When the
deck is not armed, MIDI notes are ignored.

---

## The Implementation Plan (5 pieces)

### Piece 1 — `same_scene_skip` boundary-aware fix

**The problem:** `LaserSceneExecutor.on_decision()` has a skip guard that suppresses
re-sending the same scene to prevent 200Hz spam. This also suppresses the once-per-boundary
MIDI re-assertion the autoloop fix requires. Specifically for length-1 banks (every
personality's `buildup_bank`, `drop_bank`, `breakdown_bank` each have 1 entry), the
selected scene never changes, so `same_scene_skip` fires on every tick including the
8-bar re-fire.

**The fix:** Allow the re-fire to pass through when `ctx.autoloop_tick_just_fired` is
True AND the scene is of type `"autoloop"`. Static scenes (drop looks, post-drop holds)
must NOT pass through — they intentionally rely on `same_scene_skip` to latch without
re-firing MIDI.

The proposed condition change in the skip block:
```
# Before (current):
if (role not in ("manual", "emergency")
    and not is_drop_crossing
    and selected_scene == self._last_triggered_scene):
    same_scene_skip = True

# After:
if (role not in ("manual", "emergency")
    and not is_drop_crossing
    and selected_scene == self._last_triggered_scene
    and not (ctx.autoloop_tick_just_fired and scene_def.scene_type == "autoloop")):
    same_scene_skip = True
```

**Note:** A partial fix already exists in `_select_scene()`: for `decision.reason ==
"phrase_boundary"`, it already gates on `not ctx.autoloop_tick_just_fired` (returns `""`
when the flag is False). This means `_select_scene` already prevents phrase-boundary
sends when the timer hasn't fired. But `same_scene_skip` is a SECOND barrier that still
blocks the send for length-1 banks even when `autoloop_tick_just_fired` is True. Both
are needed. Verify this interaction explicitly.

**Audit tasks for Piece 1:**
1. Verify exact current lines of the `same_scene_skip` block in `laser_executor.py`.
2. Confirm `scene_def` is in scope and non-None at the skip check (looked up earlier in
   the same function).
3. Confirm `ctx.autoloop_tick_just_fired` is a field on `LaserContext` (check
   `laser_models.py`).
4. Confirm `scene_def.scene_type` is a field on `LaserSceneDef` (check `laser_models.py`).
5. Confirm drop scenes are `scene_type: "static"` and groove/buildup/breakdown autoloop
   scenes are `scene_type: "autoloop"` in `config/laser_director.json`. If the config
   file is large, check at minimum `house_drop_1` (or equivalent) and one groove/buildup
   scene.
6. Confirm the drop_mode post-drop hold (Priority 10 in `laser_director.py`) intentionally
   relies on `same_scene_skip` to latch without re-firing MIDI (it should not be broken
   by this change, since `drop_scene` is `scene_type: "static"`).
7. Check `_select_scene()` lines for the existing `autoloop_tick_just_fired` gate — verify
   it does not subsume the `same_scene_skip` fix (i.e., the two guards are independent and
   both needed).

---

### Piece 2 — Phrase-relative 32-beat re-fire (replaces absolute grid)

**The problem:** `state_manager.py` currently fires `autoloop_tick_just_fired = True` on
absolute track-beat grid boundaries:
```python
phrase_beat = (this_beat // AUTOLOOP_ARM_PHRASE_BEATS) * AUTOLOOP_ARM_PHRASE_BEATS
```
This fires on beats 32, 64, 96, ... regardless of where Rekordbox phrase markers fall.

**The correct model:**
- **Primary trigger:** On every Rekordbox PSSI phrase marker crossing, fire the
  section-appropriate MIDI look immediately. This resets the 32-beat counter.
- **Secondary trigger:** Every 32 beats *counted from the last phrase marker* (not from
  beat 0), re-fire the same section-appropriate look to prevent SS from freelancing.
  Example: phrase marker at beat 50 → fires at 50, 82, 114, ... until the next marker.
- When a new phrase marker fires, the secondary 32-beat counter resets to 0 from that marker.
- The buildup window (`buildup_lookahead_beats`, 32 for house / 16 for dubstep) overrides
  the section determination: within that window before a drop, always fire buildup regardless
  of current phrase label.

**What already exists:**
- `SmartPhrasingState.phrase_anchor_requested` is set `True` on every phrase marker crossing
  (when `prev_abs_beat < seg.start_beat <= abs_beat` in `smart_phrasing.py`). This can serve
  as the primary trigger.
- `SmartPhrasingState` does NOT currently expose `current_phrase_start_beat`. The
  phrase-relative 32-beat counter therefore needs one of:
  (a) A new field `current_phrase_start_beat: Optional[float]` on `SmartPhrasingState`,
      populated by `SmartPhrasingEngine` each tick (it already knows the current segment).
  (b) `state_manager.py` tracks `_last_phrase_marker_beat` independently whenever
      `sp.phrase_anchor_requested` fires.
  Option (b) is simpler and avoids touching the frozen dataclass + all callsites.

**Audit tasks for Piece 2:**
1. Verify `state_manager.py:1905` is where the absolute grid re-fire currently lives.
   Show the full surrounding block so Codex can surgically replace it.
2. Confirm `SmartPhrasingState.phrase_anchor_requested` is exposed in the `sp` variable
   that `state_manager.py` consumes in the push loop (check how `sp` is built from
   `SmartPhrasingResult`).
3. Confirm `SmartPhrasingState` does NOT contain `current_phrase_start_beat` or any
   equivalent field (i.e., option (b) is the right approach).
4. Check whether `SmartPhrasingEngine` already receives `abs_beat` and detects segment
   crossings (needed to confirm the crossing detection is reliable). If `phrase_anchor_requested`
   fires on the same tick as `seg.start_beat <= abs_beat`, that is the correct beat to use
   as the new counter origin.
5. Confirm `AUTOLOOP_ARM_PHRASE_BEATS = 32` is the constant used in the absolute grid path,
   and check where it's imported from. The phrase-relative re-fire should use the same 32-beat
   interval.
6. Check whether `last_autoloop_status_phrase_beat` (currently set in the absolute grid path)
   needs to be updated or removed for the phrase-relative model.
7. Check what `sp.phrase_anchor_requested` currently does in `state_manager.py` (search for
   its consumers). If it already triggers a MIDI send, confirm it won't double-fire.

---

### Piece 3 — Breakdown MIDI blackout (replaces OS2L unarm)

**The problem:** Smart Breakdown currently unarmed the OS2L autoloop by clearing arm state
in `OutputState`. This causes the deck to go idle (no look). Instead, it should fire
`manual_blackout_on` MIDI (the same mechanism Smart Drop already uses for its pre-window
blackout), so SoundSwitch goes dark without unarming the autoloop.

**The restore:** When breakdown ends and the bridge restores to autoloop mode,
`manual_blackout_off` MIDI must be sent to lift the blackout, and the groove look must
re-fire.

**Scripted tracks — DO NOT CHANGE:** OS2L unarm for scripted track arms must remain,
because `manual_blackout_on` MIDI in SoundSwitch overrides everything including scripted
shows. The MIDI blackout change is scoped to breakdown/transition only.

**The existing mechanism:** `LaserSceneExecutor.trigger_blackout_on()` sends
`self._config.manual_blackout_on` and `_resolve_pending_blackout()` sends
`self._config.manual_blackout_off`. These already exist for Smart Drop.

**Audit tasks for Piece 3:**
1. Find where Smart Breakdown currently clears the OS2L autoloop arm. Trace the path from
   `smart_rearm_result.breakdown_fired` (seen at `state_manager.py:1887`) through to the
   actual `send_deck_clear` / `send_loop_off` / arm-state-clear calls. List every callsite.
2. Confirm `manual_blackout_on` and `manual_blackout_off` are fields on the laser config
   object that `LaserSceneExecutor` holds. Confirm they are already populated in
   `config/laser_director.json`.
3. Confirm `trigger_blackout_on()` and `_resolve_pending_blackout()` are accessible from
   wherever the breakdown firing is currently handled (i.e., the call is reachable via
   `self._laser_executor` or equivalent reference in `state_manager.py`).
4. Find the breakdown *restore* path — where does the bridge currently re-arm the autoloop
   after breakdown ends? This is where `_resolve_pending_blackout()` + groove re-fire needs
   to be added.
5. Confirm the scripted arm path (OS2L unarm + scripted `send_deck_load`) is a separate
   code path that does NOT go through breakdown firing. Verify the blackout change cannot
   accidentally reach the scripted path.

---

### Piece 4 — Immediate arm on master switch (abandon phrase-boundary delay for transitions)

**The problem:** `AutoloopController.should_delay_master_arm()` delays the OS2L autoloop arm
until the next 32-beat absolute boundary after a master switch. Consequence: if a drop fires
between the master switch and the first arm boundary, the MIDI drop note is sent but
SoundSwitch has no armed autoloop to show it on.

**The fix:** Arm the autoloop immediately on master switch (skip the phrase-boundary wait
for the arm command). Instead of waiting to show something, fire `manual_blackout_on` MIDI
immediately on master switch, so SoundSwitch is dark during the transition period. On the
first phrase marker crossing (or 32-beat boundary), fire the section-appropriate MIDI look
and lift the blackout.

**What controls the delay:** `should_delay_master_arm()` at `autoloop_controller.py:351`.
It returns True when `autoloop_master_phrase_arm=True` and the current position is not near
a phrase start. The fix is to either:
(a) Always pass `autoloop_master_phrase_arm=False` for the transition arm, or
(b) Remove the `should_delay_master_arm` check from `arm_autoloop()` for all cases and
    replace with the MIDI blackout approach.

**Audit tasks for Piece 4:**
1. Find where `arm_autoloop()` is called on master switch in `state_manager.py` (search for
   `arm_autoloop` calls). Identify the `autoloop_master_phrase_arm` argument passed at each
   callsite.
2. Show the full `should_delay_master_arm` block and the `next_arm_phrase` logic
   (`autoloop_controller.py`). Confirm the fix is as simple as not passing
   `autoloop_master_phrase_arm=True`.
3. Identify the existing transition-blackout path (the `transition_mask_should_arm` /
   `transition_window_active` fields in `SmartPhrasingState`). Is this already the mechanism
   for blanking during transitions? If so, can it be reused or extended for the immediate-arm
   scenario?
4. Confirm what `os.autoloop_arm_after_master_change` and `os.autoloop_arm_after_master_change`
   mean in the arm flow. Show the full arm-after-master-change path so Codex can surgically
   modify it.
5. Check: does `arm_autoloop()` also set `lighting_mode = "autoloop"` immediately, or does
   that happen only after the pending arm resolves? If the mode sets immediately, the
   phrase-relative re-fire timer (Piece 2) will start counting from the wrong origin.

---

### Piece 5 — Prerequisite fixes (playlist folder + buildup_lookahead coupling)

**5a. Playlist folder name bug:**
`PlaylistCache` at `__main__.py:693` is called as `PlaylistCache(RB_DB_PATH)` with no
`folder_name` argument, so it uses the default `"PER GENRE"`. The real Rekordbox folder is
`"BY GENRE"`. This means every track falls through to BPM-band personality (everyone becomes
house), making per-genre look selection a no-op.

**Audit tasks for 5a:**
1. Confirm the call at `__main__.py:693` has no `folder_name` arg.
2. Confirm `PersonalityResolver` default in `personality_resolver.py:118` is `"PER GENRE"`.
3. Check whether there are other `PlaylistCache` instantiations elsewhere that also need
   the fix.
4. Confirm `"BY GENRE"` is the actual Rekordbox folder by checking if it's mentioned
   anywhere in the codebase (e.g. comments, config, tests).

**5b. `_sp_phrase_lookahead` hardcoded to 32:**
`state_manager.py` hardcodes `_sp_phrase_lookahead = 32` for the buildup window, but
`LaserDirector` uses per-personality `buildup_lookahead_beats` (dubstep = 16, house = 32).
For dubstep tracks, these disagree: the phrasing engine detects buildup 32 beats before
the drop, but the laser director uses 16.

**Audit tasks for 5b:**
1. Find the exact location where `_sp_phrase_lookahead = 32` is set in `state_manager.py`.
2. Confirm where the personality's `buildup_lookahead_beats` value is accessible in
   `state_manager.py` context (i.e., is there a `self._personality` reference or similar).
3. Show the code path that updates `_sp_phrase_lookahead` when personality changes — or
   confirm no such path exists and it needs to be added.

---

### Piece 6 — Per-track groove bank shuffle

**The problem:** `LaserSceneExecutor._choose_bank_scene_locked` uses a round-robin cursor
starting at 0 on bridge restart. For the `phrase` role (groove looks), this means every
session plays `house_groove_1 → house_groove_2 → house_groove_3 → ...` in the same
numerical order. The sequence is identical across sets and immediately recognizable.

**The fix:** Shuffle the cursor traversal order once per track load for the `phrase` role
bank only. The cursor still increments sequentially, but through a shuffled index array
so every track gets a different, non-repeating progression through the full bank. All 32
groove looks appear exactly once before the sequence wraps. Drop/buildup/breakdown banks
are length-1 (or small) and do not need shuffling.

**Implementation approach:**
- Add a `_role_bank_shuffle: dict[str, tuple[str, ...]]` to `LaserSceneExecutor` that
  stores a shuffled copy of each bank.
- On track load (when `on_tick` sees a new track or when `arm_autoloop` fires), reshuffle
  `_role_bank_shuffle["phrase"]` using `random.shuffle`.
- In `_choose_bank_scene_locked`, use `_role_bank_shuffle[role]` instead of the raw bank
  from config for the `phrase` role; other roles use the config bank directly.
- The existing cursor and `cursor % len(bank)` logic is unchanged — only the source array
  differs.

**Audit tasks for Piece 6:**
1. Confirm `_choose_bank_scene_locked` (`laser_executor.py`) is the single point where the
   scene is selected from the bank. Verify no other path picks from the `phrase` bank.
2. Show `_bank_for_role` — confirm it returns the tuple from config directly (not a
   pre-shuffled copy), so the shuffle can be applied at a higher level without touching
   config data.
3. Find where `LaserSceneExecutor` currently learns about track loads — is there an
   `on_track_load()` method, or does it have to be inferred from `ctx` fields (e.g.
   `ctx.active_track_loaded` transitioning True, or a new track ID appearing)?
4. Confirm `_role_cursors` is reset on track load or personality change today. If it is,
   the shuffle should happen at the same point. If it is not, identify whether the cursor
   should also reset on track load (so the shuffled sequence starts from index 0 each track).
5. Check `_seed_role_cursors` — confirm whether `_randomize_cursors` is exposed in config
   or hardcoded. If it already exists as a config flag, the shuffle can be gated on it
   instead of adding a new field.

---

## Files to Read

Read ALL of the following before answering:

```
/Users/bbui/rb_ss_bridge_v2/laser_executor.py         (442 lines)
/Users/bbui/rb_ss_bridge_v2/laser_director.py         (720 lines)
/Users/bbui/rb_ss_bridge_v2/laser_models.py           (156 lines)
/Users/bbui/rb_ss_bridge_v2/smart_phrasing.py         (535 lines)
/Users/bbui/rb_ss_bridge_v2/smart_rearm.py            (read fully)
/Users/bbui/rb_ss_bridge_v2/state_manager.py          (2255 lines)
/Users/bbui/rb_ss_bridge_v2/autoloop_controller.py    (744 lines)
/Users/bbui/rb_ss_bridge_v2/personality_resolver.py   (243 lines)
/Users/bbui/rb_ss_bridge_v2/__main__.py               (1133 lines)
/Users/bbui/rb_ss_bridge_v2/models.py                 (read fully — OutputState fields)
/Users/bbui/rb_ss_bridge_v2/config/laser_director.json
```

---

## Output Format

Structure your output in two parts.

---

### Part A — Audit

#### A1. Blocker List
Any finding that would cause Codex to implement a piece incorrectly or cause a runtime
failure. Each blocker must name: the file, the current code, and what must change before
Codex touches anything.

#### A2. Piece-by-Piece Findings
For each of Pieces 1–6, a table:

| Claim | File:Line | Status | Note |
|---|---|---|---|
| ... | ... | CONFIRMED / ASSUMED / UNKNOWN | ... |

#### A3. Prerequisite Checklist
Things that must exist before any code is written:
- [ ] SoundSwitch MIDI mappings for groove looks (operator task — cannot be code-verified)
- [ ] `manual_blackout_on` / `manual_blackout_off` present in `config/laser_director.json`
- [ ] Any other missing config, constants, or model fields

#### A4. Anything the Plan Got Wrong or Missed
Any claim in this prompt that is factually incorrect per current code. If a proposed fix
would break something not accounted for, call it out explicitly with the file and line.

---

### Part B — Codex Implementation Spec

This is the primary deliverable. After completing the audit, produce a self-contained
implementation spec that Codex can execute directly without further reasoning. It must
include everything Codex needs and nothing it does not.

Structure it as follows:

#### B1. Implementation Order
A numbered list of tasks in dependency order. Each task names which Piece it implements.
Flag any task that must not be implemented before a prior task is complete.

#### B2. Per-Task Spec
For each task, provide:

```
## Task N — [short name] (Piece X)

**File:** path/to/file.py

**Function / location:** exact function name and current line range

**Current code:**
(paste the exact lines that must change)

**Change:**
(paste the replacement code, or describe the insertion point and new lines precisely)

**Invariants to preserve:**
- bullet list of constraints Codex must not break (e.g. "static scenes must not pass
  through same_scene_skip on non-boundary ticks", "scripted arm path must not be affected")

**Verify after:**
- what to check in /tmp/bridge.log or bridge behavior to confirm this task is correct
```

Do not summarize or paraphrase. Paste actual code. If a change spans multiple locations
in the same file, list each location as a separate sub-change under the same task.
If a change requires a new field on a dataclass or model, include that as a sub-change
before the code that uses it.

#### B3. Operator Prerequisites
Tasks the operator (not Codex) must complete before the feature can be tested end-to-end:
- SoundSwitch MIDI mappings for groove looks
- Any config file additions
- Any other manual steps
