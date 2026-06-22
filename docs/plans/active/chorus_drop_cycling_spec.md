---
doc_status: active-plan
truth_level: code-grounded
last_verified_commit: HEAD
last_verified_date: 2026-06-22
validation_scope: spec only; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — Drop-look cycling during chorus phrases

> **Live-critical / plan-first.** This changes live autoloop+laser selection during a
> show. Implement exactly as written, commit after each task, keep the new behavior
> behind an **opt-in personality flag defaulting OFF** so existing setups are
> byte-for-byte unchanged until the operator enables it.

## Part A — Context & root cause (verified; read, do not implement)

**Goal (operator).** While a track is in a **chorus** phrase, keep the lighting in the
**drop family** and **cycle (rotate) through the drop scene bank** on the normal refire
cadence — instead of reverting to a groove look. Release back to normal when the chorus
ends. The drop autoloop arm and the laser look are the *same* thing (one MIDI note to
SoundSwitch), so this is one coupled "look".

**How the look is produced today.**
- [confirmed] The **role decision** is made in `LaserDirector._decide` (`laser_director.py:293`).
  It is a priority ladder: emergency/manual/idle states → breakdown (`:424`) → **drop
  crossing** `role="drop" reason="drop_crossing"` once per drop (`:439`) → **post-drop
  hold** `role="post_drop"`/`role="drop" reason="drop_hold"` (`:453-477`) → **buildup
  window** `role="buildup"` (`:507`) → fall-through to `_decide_phrase_default` →
  `role="phrase"` groove (`:538`).
- [confirmed] **The drop→groove reversion is that fall-through**: once the post-drop hold
  window (`_post_drop_hold_beats`) expires, nothing keeps the drop role, so the next
  phrase edge returns `role="phrase"` (groove) — even if the track is still in its chorus
  section.
- [confirmed] `current_phrase_is_chorus` already exists and is plumbed into `_decide`
  (`laser_director.py:485`, sourced from `smart_phrasing.py:13,297` `PhraseLabel` /
  chorus markers). **No smart_phrasing change is needed** to know we are in a chorus.
- [confirmed] The **executor** `LaserSceneExecutor.on_decision` (`laser_executor.py:106`)
  consumes the decision and fires the scene's MIDI note via `laser_output_backend →
  midi_output`. The scene's MIDI note IS the SoundSwitch autoloop+laser identity.
- [confirmed] **Scene rotation** is already implemented: `_choose_bank_scene_locked`
  (`laser_executor.py:401`) advances `self._role_cursors[role]` over `_bank_for_role(role)`;
  `drop_bank` exists on the personality (`laser_models.py:98`, `laser_config.py:64`).
- [confirmed] But **drop does not refire/rotate today**:
  - `_select_scene` (`laser_executor.py:375`) rotates the bank **only** for `role=="phrase"`
    on a phrase trigger (`:388-394`). For every other auto role (incl. `drop`) it returns
    the **held** `_role_active_scene` unless `role_changed` (`:396-399`) — so a drop look is
    latched, not cycled.
  - `refire_roles = ("phrase", "buildup", "breakdown")` (`laser_executor.py:181`) — `drop`
    is excluded, so `refire_allowed` is never true for drop (`:184-189`).
- [confirmed] `autoloop_controller.py` manages arm-pending / `autoloop_arm_bpm` /
  beat-sync / live-BPM-follow (`autoloop_controller.py:68,102,119`) — it sets the refire
  cadence (`ctx.autoloop_tick_just_fired`) but does **not** choose the scene identity.
  **No change here.**
- [confirmed] `ctx.autoloop_tick_just_fired` is true on **both** a 32-beat interval refire
  **and** a phrase-marker boundary (observed in capture logs: `[SM] midi-refire
  source=interval` and `source=marker`). Gating the chorus-drop refire on
  `autoloop_tick_just_fired` therefore yields the requested "both cadences" for free.
- [confirmed] `_drop_style` is `"drop_mode"` or `"emphasized_drop"` (`laser_director.py:202`).
  Rotation of the drop look itself is a `drop_mode` concept (`:464-477`); in
  `emphasized_drop` the post-drop look is a separate `post_drop_scene`.
- [assumed] Changing the **laser role's fired note** during chorus is sufficient to make
  SoundSwitch cycle the drop autoloops, because the scene note is the SS trigger and
  `autoloop_controller` keeps whatever is armed beat-synced. **Codex must confirm** there
  is no separate groove-autoloop arm being emitted in parallel during chorus that would
  fight the drop note (search for other `midi_output.trigger`/note-send call sites active
  on an autoloop tick).

### A2. MIDI mapping must stay synced — BACKEND + FRONTEND (verified; operator-critical)
Rotating the drop bank only works if **every drop note the bridge sends is mapped to the
intended drop autoloop on every surface**. Three surfaces must agree, today they do NOT:
- [confirmed] **Backend — scene catalog** `config/laser_director.json` `scenes`: 15 autoloop
  drop scenes `house_drop_2..16` (notes 97–111) plus the **one-shot** `house_drop_1`
  (`scene_type:"static"`, note 96). The static one is the drop *hit*; the autoloop ones are
  the cyclable drop *looks*.
- [confirmed] **Backend — per-personality `drop_bank`** (`config/laser_director.json`
  `personalities`): `house` lists 16 entries but **entry 0 is the static `house_drop_1`**
  and entries `house_drop_2/3` are `safety_class:"high_impact"`; `dubstep`'s drop_bank is
  **only `["house_drop_1"]`** (the static hit) → dubstep would have nothing cyclable.
- [confirmed] The executor gates a refire on `scene_def.scene_type == "autoloop"`
  (`laser_executor.py:187`) and on `allow_high_impact` for high-impact scenes (`:172-179`).
  So with the Part B change, **static and high-impact drop_bank entries are silently
  skipped** — the cursor lands on them and no MIDI fires that tick.
- [confirmed] **Frontend (a) — laser_pad UI**: `config/laser_director.json` `_pad_meta`
  (`banks`, `note_labels`, `ui`) drives the pad; its note labels must match the drop notes.
- [confirmed] **Frontend (b) — SoundSwitch project**: the bounded RAVE project must map
  each drop note (96–111) to the intended drop autoloop, and the SoundSwitch **pack export**
  must include them (authority for future native DMX). `~/vln_ss_analysis/soundswitch_laser_cues.json`
  is keyed by cue/fixture/dmx, **not** MIDI note, so this check is done in SoundSwitch's
  MIDI mapping / the exported pack, not that file.
- [confirmed] No existing tool cross-checks bridge drop notes against the pad labels or
  SoundSwitch (`tools/` has none). One is added in Task 5.

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **Do not** modify `smart_phrasing.py`, `autoloop_controller.py`, `smart_rearm.py`, the
  push loop (`state_manager.py`), SoundSwitch pack code, or any LED/Govee module.
- **Do not** change drop_crossing (`laser_director.py:439`) or post-drop-hold
  (`:453-477`) behavior. The new branch is strictly **lower priority** than both.
- New behavior is **OFF by default** (`chorus_drop_sustain=False`). With it off, output
  must be byte-for-byte identical to today.
- Follow AGENTS.md §7: this is the `laser` change-contract; update the docs it lists
  (`docs/subsystems/laser.md`, `docs/architecture/laser_director_design.md`) and run §8
  hard checks.

### Task 1 — `laser_models.py` + `laser_config.py`: add the opt-in flag
- `laser_models.py`: add to the personality dataclass (near `drop_style`, ~`:110`):
  `chorus_drop_sustain: bool = False`.
- `laser_config.py`: accept/validate `chorus_drop_sustain` (bool; default `False`) in the
  personality parser/whitelist (mirror how `drop_style` / `post_drop_hold_beats` are read,
  `:57-73`). Unknown/missing → `False`. Invalid type → config error consistent with the
  existing validator.
- `personality_resolver.py` / wherever the personality is built from config: pass the new
  field through (mirror `drop_style`).

### Task 2 — `laser_director.py`: sustain the drop role during chorus
Add `self._chorus_drop_sustain = bool(getattr(personality, "chorus_drop_sustain", False))`
where `_drop_style` is set (`:102` and the personality-reload path `:197`).

In `_decide`, insert a new branch **after** the buildup handling (`:514-529`) and
**immediately before** `return self._decide_phrase_default(...)` (`:538`):

```python
# Priority 11.5: Sustain + cycle drop looks while in a chorus phrase.
# Lower priority than drop_crossing (9) and post_drop_hold (10): a real drop
# and its hold still win. Only once the hold has expired AND we are still in a
# chorus do we keep the drop role and let the executor rotate the drop bank on
# each autoloop tick. reason="chorus_drop_refire" is NOT "drop_crossing", so it
# does not re-arm the one-shot drop path; the executor gates the actual MIDI on
# autoloop_tick_just_fired and rotates the bank.
if (
    self._chorus_drop_sustain
    and current_phrase_is_chorus
    and self._drop_style == "drop_mode"
    and self._drop_scene
    and not in_post_drop_hold
):
    self._last_smart_abs_beat = abs_beat
    return LaserSceneDecision(
        scene=self._drop_scene,
        reason="chorus_drop_refire",
        priority=11,
        source="policy",
        role="drop",
    )
```
(`current_phrase_is_chorus` and `in_post_drop_hold` are already computed above at
`:485` and `:448`. Keep the existing `post_drop_start_abs_beat` reset at `:531-536` ahead
of this branch so post-drop accounting is unchanged.)

### Task 3 — `laser_executor.py`: let the drop role refire + rotate for the new reason
1. Treat the new reason as a refire trigger. Replace the `refire_allowed` computation
   (`:182-189`) so `drop` is eligible **only** for `reason=="chorus_drop_refire"`:
   ```python
   chorus_drop_refire = (role == "drop" and decision.reason == "chorus_drop_refire")
   refire_allowed = (
       ctx.autoloop_tick_just_fired
       and (role in refire_roles or chorus_drop_refire)
       and scene_def.scene_type == "autoloop"
       and (last_role_trigger_beat < 0.0 or float(ctx.abs_beat) > last_role_trigger_beat)
   )
   ```
2. In `_select_scene` (`:375`), make `role=="drop"` with `reason=="chorus_drop_refire"`
   behave like the phrase refire — fire **only** on an autoloop tick and **rotate** the
   drop bank — instead of returning the held active scene. Add, before the generic
   non-phrase handling at `:396`:
   ```python
   if role == "drop" and decision.reason == "chorus_drop_refire":
       if not ctx.autoloop_tick_just_fired:
           return ""   # no MIDI between ticks (no arm spam)
       return self._choose_bank_scene_locked(role="drop", fallback_scene=decision.scene)
   ```
   Leave the existing `drop_crossing` / `drop_hold` paths untouched (they keep the
   latched look via the unchanged `:396-399` branch).

### Task 4 — release path (verify, add only if a test proves a leak)
When the chorus ends, `_decide` stops returning the chorus branch and falls through to
`_decide_phrase_default` → `role="phrase"`; `on_decision` sees `role_changed`, clears
`_role_active_scene["drop"]` (`:120-124`). Confirm with the Task-D release test that the
look returns to groove on the first post-chorus phrase edge and no stuck drop remains.
Only if the test fails, reset `_role_cursors["drop"]`/`_role_active_scene["drop"]` on the
drop→non-drop transition.

### Task 5 — Keep the laser MIDI mapping synced (BACKEND + FRONTEND)
The behavior is only correct if every cyclable drop note is mapped end-to-end. Do all of:

5a. **Backend config — curate `drop_bank` for cycling** (`config/laser_director.json`,
each personality used live: `house`, `dubstep`). The cyclable drop bank must contain
**only `scene_type:"autoloop"`** drop scenes whose `safety_class` is allowed by the
personality (`allow_high_impact`). Remove the static `house_drop_1` from the cyclable set
(it stays as the drop-crossing one-shot `drop_scene`), and either drop the high-impact
entries or set `allow_high_impact` deliberately. **`dubstep` must be populated** with real
autoloop drop looks or it cannot cycle. (Operator decides the exact membership; Codex makes
the config valid and the validator below enforce it.)

5b. **Config validation** (`laser_config.py`): when `chorus_drop_sustain` is true for a
personality, validate that its `drop_bank` contains **≥1 scene that is `scene_type=="autoloop"`
and allowed under `allow_high_impact`**, and that **every** `drop_bank` entry resolves to a
scene present in `scenes` with a MIDI note. Emit a clear config error (not silent) listing
any entry that is static / high-impact-while-not-allowed / missing-note, so a mis-synced
bank fails loudly at load instead of silently not cycling.

5c. **Frontend (a) — laser_pad `_pad_meta`**: ensure `note_labels`/`banks` label every
cyclable drop note consistently with the scene catalog. If Codex changes any drop scene's
note, update `_pad_meta` in the same commit.

5d. **Frontend (b) — SoundSwitch sync checker** `tools/check_laser_midi_sync.py` (new,
pure + CLI): given `config/laser_director.json` and a SoundSwitch mapping export, print a
table of every drop_bank note → bridge scene (type/safety) → pad label → SoundSwitch
autoloop, and **exit non-zero** on any of: drop_bank note not mapped in SoundSwitch, note
collision across banks, drop_bank entry missing from `scenes`, or static/high-impact entry
in a cyclable bank. Pure-function core (`reconcile(config_dict, ss_map) -> list[issue]`)
unit-tested with fixtures. The operator runs this after editing either side; it does NOT
mutate SoundSwitch and does NOT touch the live project.

5e. **Operator step (documented, not code)**: in the bounded SoundSwitch project, confirm
each cyclable drop note triggers the intended drop autoloop, and re-export the pack so the
future native-DMX path has them. The exporter pins the project UUID (see the SoundSwitch
exporter spec); adding/renaming autoloops requires a re-export.

## Part C — Invariants that MUST still hold (live safety)
1. **Default-off = no change.** With `chorus_drop_sustain=False`, every decision/MIDI is
   identical to today (assert via unchanged existing tests).
2. **No arm spam.** Chorus-drop MIDI fires **only** on `ctx.autoloop_tick_just_fired`
   (both 32-beat interval and phrase boundary), never every tick.
3. **Real drops win.** `drop_crossing` (pri 9) and post-drop hold (pri 10) are unchanged
   and still pre-empt the new pri-11.5 branch.
4. **No push-loop I/O.** Decision logic only; no network/MIDI/file/subprocess added to the
   tick path beyond the existing single scene trigger.
5. **Don't touch arm/BPM state.** `autoloop_controller` arm-pending, `autoloop_arm_bpm`,
   beat-sync, and live-BPM-follow are untouched.
6. **Mode transitions.** idle / not-playing / scripted / position-stale branches (earlier
   in `_decide`) still pre-empt; chorus-drop only occurs in a valid playing autoloop state
   (`_passes_automatic_gates`, `laser_executor.py:455`).
7. **emphasized_drop unaffected.** Branch is gated on `_drop_style == "drop_mode"`.
8. **MIDI-mapping integrity (no wrong looks).** Every note the rotation can send must map
   to the intended drop autoloop on all three surfaces (scene catalog, laser_pad `_pad_meta`,
   SoundSwitch). A mis-synced or static/high-impact-not-allowed `drop_bank` entry must fail
   the Task 5b config validation at load (loud), never silently send an unmapped/wrong note
   live. No note collisions across banks.

## Part D — Tests (pure-function seam; no files/subprocess)
- `tests/test_laser_director*.py`: construct a `LaserContext` with
  `smart_phrasing.current_phrase_is_chorus=True`, post-drop hold expired, drop scene set:
  - flag ON, `drop_mode` → decision `role=="drop"`, `reason=="chorus_drop_refire"`.
  - flag OFF → `role=="phrase"` (unchanged).
  - within post-drop hold → still `role=="post_drop"`/`drop_hold` (pri 10 wins).
  - `current_phrase_is_chorus=False` → `role=="phrase"`.
  - `_drop_style=="emphasized_drop"` → `role=="phrase"` (no sustain).
- `tests/test_laser_executor*.py`: feed repeated `chorus_drop_refire` decisions:
  - with `autoloop_tick_just_fired=True` across ticks and a multi-entry `drop_bank` →
    fired scene **rotates** through the bank (cursor advances), MIDI fired each tick.
  - with `autoloop_tick_just_fired=False` → `_select_scene` returns `""`, **no** MIDI.
  - release: switch `current_phrase_is_chorus`→False → next phrase edge fires `role=="phrase"`.
- All existing laser tests must pass unchanged (default-off regression).

## Part E — Acceptance (definition of done)
- [ ] `chorus_drop_sustain` flag added (model + config + resolver), default `False`.
- [ ] Flag OFF: full existing laser test suite passes with no behavior change.
- [ ] Flag ON + `drop_mode` + chorus: drop role sustains and **rotates** the drop bank on
      both phrase-boundary and 32-beat-interval autoloop ticks; releases to groove when the
      chorus ends.
- [ ] Real drop crossing + post-drop hold behavior unchanged.
- [ ] **MIDI mapping synced (backend+frontend):** each personality's cyclable `drop_bank`
      is autoloop-only + allowed-safety with mapped, collision-free notes; `dubstep` is
      populated (not just the static hit); `_pad_meta` labels match;
      `tools/check_laser_midi_sync.py` exits 0 against the SoundSwitch mapping; bad banks
      fail Task 5b validation loudly.
- [ ] Part A `[assumed]` confirmed (no parallel groove-autoloop arm fights the drop note).
- [ ] `python3 -m unittest discover tests` green; AGENTS.md §8 hard checks green;
      `laser` change-contract docs updated.
- [ ] No I/O added to the push/tick path.

## When you finish
- Commit per task with real messages (e.g. `laser(chorus): sustain+rotate drop looks
  during chorus phrases behind chorus_drop_sustain flag`).
- Report: files touched, the resolved answer to the Part A `[assumed]` check, test names
  added, and confirmation that flag-off is a no-op.

## Note — interaction with the T7d capture pass (for the operator, not Codex)
This adds a **new transition pattern** (drop-role refire during a chorus). The **live
SoundSwitch-rendered path is unaffected** — SS renders whatever note is armed. The
future **native-DMX (T7d) path** has no phase-contract evidence for this pattern yet, so
T7d will **safe-zero** it until a `chorus-drop-refire` capture is taken (it cannot render
it wrong). When this ships and is enabled, add one capture scenario for it before T7d
native DMX drives that case.
