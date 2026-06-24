---
doc_status: active-plan
truth_level: code-grounded-design-spec
last_verified_commit: f07f3a3
last_verified_date: 2026-06-24
validation_scope: RW-2 scripted runtime transport (pause vs stop) design spec; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; default-off (enabled=false, dry_run=true, output_backend=none) — no restart/enable/hardware authorized
---

# Codex Implementation Spec — RW-2 Scripted Runtime Transport (pause vs stop)

> **Scope.** This spec closes the dependency root of milestone **M2** (scripted
> live-runtime contract closure): the SoundSwitch pack driver cannot today tell a
> *paused* deck from a *stopped* one, so a paused scripted track goes dark instead
> of holding its current cue. RW-2 makes the bridge-native CH1-CH19 pack driver
> distinguish the two using existing StateManager authority plus a small,
> driver-local pause-hold latch (no new `DeckState`/`OutputState` writer).
>
> **Roles.** Opus authored this; **Codex implements it**. No implementation,
> output enable, backend change, restart, or hardware action is authorized by this
> document. Pack output stays default-off.
>
> **Evidence labels:** **[C]** confirmed in current code at `f07f3a3` · **[P]**
> policy decision (operator-confirmed where noted) · **[U]** needs live/hardware
> evidence (none promoted by software inference).

## Revision note (review round 1 incorporated)
This revision folds in an independent ChatGPT review and an Opus code-verification
pass against `f07f3a3`. Two real defects in the first draft were fixed:
- **(was BLOCKER) never-played track rendered as paused.** The original
  `os.was_playing`-only discriminator survives a track replacement, so a freshly
  loaded, never-played track could render as `transport="paused"`. Fixed by
  binding the hold to the **played `(deck, load_gen)` identity** (B.Task 1).
- **(was MAJOR, decision-invalidating) hold was ~3.5 s, not ~0.5 s, and lanes
  diverged.** `os.was_playing` is flipped False late because
  `_apply_lighting("idle")` re-arms `ARM_GUARD_S` (`state_manager.py:3152`), which
  suppresses stop confirmation (`:3518`). Fixed by an **explicit
  `STOP_DEBOUNCE_S` hold deadline** in the driver, independent of `was_playing`'s
  timing — this genuinely delivers the ~0.5 s hold + OS2L-lane consistency that
  Behavior A was chosen for.
Minor review points (proof transient, emergency wording, test strictness, T12
fallback) are also incorporated below.

---

## Part A — Context & root cause (verified; read, do not implement)

### A.1 What happens today
The 200 Hz push loop drives the pack output once per tick from
`StateManager._drive_pack_output()` (`state_manager.py:3251-3322`, called by
`_push_tick` at `3230-3231`). The automatic scripted base is gated at
`state_manager.py:3304-3311`:

```python
if playing and fresh and metadata_ready and not track_changed and not discont:
    player.select_scripted(... transport="playing" ...)
else:
    player.clear_selection()
```

- **[C]** `playing = bool(getattr(d, "playing", False))` (`3293`).
- **[C]** A `PAUSE` event sets `DeckState.playing = False` (`_handle_event`,
  `state_manager.py:1120-1123`). `_do_stop()` *also* sets `playing = False`
  (`4168`). So **the single `playing` boolean cannot separate pause from stop**;
  every false value falls to `clear_selection()` → ZERO base.

### A.2 Root cause
The driver collapses *paused* and *stopped* into one `playing==False` branch. The
pure player already exposes the missing distinction —
`select_scripted(..., transport="paused")` is accepted and rendered
(`soundswitch_laser_player.py:213-224` accept; `271-275` + `312-313` render) — but
the driver never passes it. RW-2 is a driver-side derivation change, not a player
change.

### A.3 The player contract this spec pins to (already authorized)
- **[C] The player caches no output frame.** `render_scripted_frame(document,
  elapsed_ms)` (`soundswitch_laser_player.py:103-115`) rebuilds the frame from an
  all-ZERO state by replaying immutable timeline events with
  `0 <= time <= elapsed_ms` every call (`_apply_events`, `85-100`). "Paused" and
  "playing" take the **same** render path at the same `elapsed_ms`
  (`_scripted_base` `271-275` → `313`). So "paused holds the current frame derived
  from events at authoritative elapsed, never a cached/obsolete frame" holds **by
  construction**, provided the driver passes the current authoritative elapsed
  (A.5).
- **[C] Zero-states must use `clear_selection()`, not `transport="stopped"`.**
  `clear_selection()` (`247-256`) yields a `missing_selection` base (ZERO) and
  **lets a held Static Override stand alone** (`render()` `351-353`, `361-363`).
  `transport in ("stopped","ended","unloaded")` returns a *non-`missing_selection`*
  diagnostic (`272-274`) that `render()` returns **before** the held-static check
  (`361-362`), suppressing static. The accepted manual-static policy
  (`state_manager.py:3299-3303`; tests `200-216`) requires held static to remain
  visible on deck-authority loss, so the driver's zero path **must stay
  `clear_selection()`**; `transport="stopped"/"ended"/"unloaded"` must **not** be
  emitted.

### A.4 Why `os.was_playing` alone is insufficient — the corrected discriminator [C]
The first draft used `os.was_playing` as the sole pause/stop discriminator. Code
verification against `f07f3a3` found two reasons it is insufficient on its own:

1. **Not identity-bound (was a BLOCKER).** `_on_track_loaded()` does `load_gen +=
   1`, `meta.clear()`, `scripted_id = 0` (`state_manager.py:2613-2616`) but
   **never** sets `os.was_playing=False`. `_on_filepath_resolved()` then populates
   `meta.soundswitch_id` purely from track-load resolution, gated only by
   `load_gen` (`2876`, `2864`) — independent of play state. The driver's
   `track_changed` guard lasts exactly one tick (`_pack_last_load_gen` is rewritten
   every tick, `3284`). Therefore a track loaded onto the **active** deck while a
   prior track's `was_playing` is still True would, after the one-tick zero and
   filepath resolve, satisfy a `was_playing`-only paused test and render a
   **never-played** track as a held cue.
2. **Timing polluted by ARM_GUARD (was MAJOR).** `was_playing` is flipped False
   only by `_do_stop()` (`4169`) via stop confirmation
   (`if not d.playing and not arm_guard and os.was_playing`, `3518`), and by
   `_on_master_changed()` (`2578`). But `_update_lighting` transitions the OS2L
   lane to idle after `STOP_DEBOUNCE_S` (`3128-3144`) and calls
   `_apply_lighting("idle")`, which **re-arms** `last_arm_mono = time.monotonic()`
   (`3152`); `arm_guard = (now - last_arm_mono) < ARM_GUARD_S` (`3514`,
   `ARM_GUARD_S=3.0`) then suppresses stop confirmation for ~3 s. Net: a
   `was_playing`-only hold lasts **~3.5 s**, while the OS2L lane already cleared at
   0.5 s — the lanes diverge and the duration is an accident of unrelated
   arm-guard timing.

**Corrected discriminator (this spec).** Hold is decided by a driver-local latch
bound to the *played identity* and a *bounded deadline*, with `was_playing` kept
only as the obsolete-frame guard (A.5):
- On a happy **playing** tick, record `self._pack_play_hold_key = (active,
  load_gen)` and `self._pack_play_hold_deadline = now + STOP_DEBOUNCE_S`.
- Render **paused** only when: `not playing` **and** the happy gate holds **and**
  `os.was_playing` is True **and** `(active, load_gen) == self._pack_play_hold_key`
  **and** `now < self._pack_play_hold_deadline`.
- Otherwise `clear_selection()` (ZERO); reset the latch on identity change.

This adds two **driver-local** fields (peers of the existing `_pack_last_load_gen`
/ `_pack_last_elapsed_ms` / `_pack_last_static_slot`, init at
`state_manager.py:358-361`). It writes **no** `DeckState`/`OutputState` field, so
StateManager stays the sole `DeckState` writer (invariant §7.1). No new transport
owner is created.

### A.5 No obsolete *paused* frame — proof + the one transient — [C]
The authoritative elapsed the driver renders is `d.elapsed_ms`, written every
**non-stale** tick at `state_manager.py:3434-3436`; when paused, `snap.playing` is
false so interpolation adds nothing (`3422`) and `d.elapsed_ms` freezes at the
memory pause position.

Keeping `os.was_playing==True` as a necessary condition for the paused render
makes the held frame obsolete-free:
1. The **only** early return before the elapsed write at `3436` is the stale block
   at `3357`.
2. If inner takes that block while `os.was_playing` was True, it calls
   `_do_stop()` → `was_playing=False` (`3358-3361`, `4169`) **before** the driver
   runs.
3. So `os.was_playing==True` at driver time ⟹ inner did not take the stale early
   return this tick ⟹ inner executed `3436` ⟹ `d.elapsed_ms` is current.

The driver independently re-reads the cache for its own `fresh` gate (`3265`,
`3292`); both cross-thread races fail safe (inner fresh + driver stale →
`clear_selection`; inner stale forces `was_playing=False` → not paused → ZERO). In
neither race can a *held (paused)* frame render at a non-current elapsed.

**Known transient (review finding, MINOR).** A `PAUSE` event sets `d.playing=False`
in the event thread (`1120-1123`) possibly *before* the 60 Hz reader publishes
`snap.playing=False`. During that lag, interpolation `snap.elapsed_ms +
(elapsed_since if snap.playing else 0.0)` (`3422`) advances elapsed **forward**, so
the held frame briefly tracks a forward-moving elapsed, then settles when
`snap.playing` flips. This is the *current* tick's authoritative value (forward,
not cached/obsolete) and self-corrects within the reader lag (≈ one to a few 60 Hz
frames). The settle step is < `_PACK_SEEK_JUMP_MS` so it raises no discontinuity.
Exact lag magnitude on the live rig is **[U]** (needs maintainer/live verification);
runtime effect is negligible (tens of ms of cue drift). The **playing** path is
unchanged from today and keeps its pre-existing bounded resume-settle race;
RW-2 neither introduces nor worsens it.

### A.6 The seven transport states under this derivation — [C]/[P]
| Transport | Detected by | Driver action |
|---|---|---|
| **playing** | `d.playing` True + happy gate | `select_scripted(transport="playing", elapsed_ms=d.elapsed_ms)`; refresh hold latch |
| **paused** | `d.playing` False + happy + `os.was_playing` + key matches played id + `now < deadline` | `select_scripted(transport="paused", elapsed_ms=d.elapsed_ms)` — holds frozen frame ≤`STOP_DEBOUNCE_S` **[P]** |
| **stopped** | hold deadline expired, or `os.was_playing` False, or key ≠ played id | `clear_selection()` → ZERO |
| **ended** | end-of-track while loaded (no distinct signal) | paused → stopped via the same deadline path **[P]** (A.7) |
| **unloaded** | `_pack_normalize_id(ssid) is None` | `clear_selection()` → ZERO |
| **stale** | `snap is None or snap.is_stale(MEM_STALE_S)` | `clear_selection()` → ZERO |
| **errored** | driver `try/except` (`3315-3322`); `discont` (`3286-3290`); `track_changed` (`3281-3284`) | ZERO (except path submits `_PACK_ZERO_FRAME`; discont/track_changed → `clear_selection()`) |

"happy gate" = `fresh and metadata_ready and not track_changed and not discont`
(existing booleans, `3281-3295`).

### A.7 Pause-hold duration — Behavior A, operator-confirmed, now delivered correctly — [P]
The operator chose **Behavior A: a brief debounce-bounded hold that matches the
OS2L idle debounce, then safe black.** The first draft *claimed* this but, per A.4,
actually produced ~3.5 s via `was_playing`. This revision delivers true Behavior A
with an **explicit `STOP_DEBOUNCE_S` (0.5 s) hold deadline** refreshed on every
playing tick:
- Pause and drop back in within 0.5 s → seamless hold then continue.
- Pause/stop longer than 0.5 s → resolve to ZERO **within one 200 Hz tick (~5 ms)**
  of when `_update_lighting` idles the OS2L lane (`3128`, `STOP_DEBOUNCE_S`). The
  small offset is because the pack deadline is anchored to the last *playing* tick
  while the OS2L idle debounce is anchored to the first *not-playing* tick
  (`_update_lighting` is called with `confident_playing=d.playing`, `3495-3496`,
  and sets `lighting_stable_since=now` on the flip, `3123-3125`). Bounded to
  `STOP_DEBOUNCE_S ± one tick` — no multi-second divergence.

The rejected alternative (Behavior B, indefinite hold while loaded) is unchanged in
its rejection. "Ended" gets no separate detector — there is no reliable distinct
end-of-track signal, and genuine end transitions (track replace → `track_changed`
+ identity-latch reset; deck switch → key mismatch; RB stop → stale) already zero;
a track that plays to its end then stops holds at most `STOP_DEBOUNCE_S`, then
zeros.

**Edge (benign).** A track that plays for less than `PLAY_SETTLE_MS` (400 ms,
`config.py:76`) before pausing may not yet have `os.was_playing==True` (resume not
settled, `_do_resume` `4206`); the paused branch then fails closed → ZERO. Safe;
documented so the reviewer is not surprised.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Touch **only** `state_manager.py` (`__init__` pack-field block `358-361`;
  `_drive_pack_output`) and `tests/test_state_manager_pack_driver.py` (plus a new
  inner-tick test module if needed, see Task 3). Do **not** modify
  `soundswitch_laser_player.py`, `soundswitch_pack_runtime.py`, `_push_tick_inner`,
  `_update_lighting`, the OS2L/laser/LED lanes, config, or any startup/dataclass/
  import surface.
- The hold latch is **driver-local** (peers of `_pack_last_*`); write **no**
  `DeckState`/`OutputState` field. No new transport owner.
- Do **not** emit `transport="stopped"/"ended"/"unloaded"`; the zero path stays
  `clear_selection()` (A.3).
- No filesystem/subprocess/MIDI/serial/socket/sleep/retry/blocking-queue work in
  the driver (§7.2). `time.monotonic()` is permitted (no I/O), or inject `now`.
- No behavior change when pack output is absent/disabled/default-off: the driver is
  already inert unless `rt.active` (`3258-3260`).

### Task 1 — `state_manager.py`: add the driver-local hold latch + transport derivation
**1a. Init fields** alongside `state_manager.py:358-361`:
```python
        self._pack_play_hold_key: tuple[int, int] | None = None   # (active, load_gen) last seen PLAYING on the happy path
        self._pack_play_hold_deadline: float = 0.0                 # monotonic deadline; paused-hold expires here
```

**1b. Inject a clock** so the deadline is testable. Change the signature to
`def _drive_pack_output(self, now: float | None = None) -> None:` and, near the
top of the body, `now = time.monotonic() if now is None else now`. `_push_tick`
keeps calling `self._drive_pack_output()` unchanged (default reads the real clock).

**1c. Replace the scripted-base gate at `state_manager.py:3304-3311`** (the
`if playing and fresh ... else clear_selection()` block) with the derivation
below. Keep every line above it (`3261-3295`: masks/static, `track_changed`,
`discont`, `fresh`, `ssid`, `metadata_ready`, and the `load_key` computed at
`3280`) and the single `submit_frame` at `3314` **unchanged**.

```python
            # 3. Automatic base transport derivation (RW-2). The pure player
            #    re-renders from immutable events at elapsed_ms each tick, so paused
            #    holds the current authoritative frame, never a cached one (A.5).
            #    Hold is bound to the PLAYED (deck, load_gen) identity and a
            #    STOP_DEBOUNCE_S deadline so (i) a never-played freshly-loaded track
            #    is never held, and (ii) the hold matches the OS2L idle debounce.
            #    os.was_playing is the obsolete-frame guard (A.5). The ZERO path
            #    stays clear_selection() so a held Static Override stands alone; we
            #    never emit transport="stopped"/"ended"/"unloaded".
            # Reuse the EXISTING bindings computed above (3281-3295): `playing`,
            # `fresh`, `metadata_ready`, `track_changed`, `discont`, `load_key`.
            # Do not re-declare them. Only `happy` and `was_playing` are new.
            happy = fresh and metadata_ready and not track_changed and not discont
            was_playing = bool(getattr(self._os, "was_playing", False))
            if happy and playing:
                transport = "playing"
                self._pack_play_hold_key = load_key
                self._pack_play_hold_deadline = now + STOP_DEBOUNCE_S
            elif (
                happy and was_playing
                and load_key == self._pack_play_hold_key
                and now < self._pack_play_hold_deadline
            ):
                transport = "paused"
            else:
                transport = None  # stopped / hold-expired / unloaded / stale / changed / discont
                if load_key != self._pack_play_hold_key:
                    # New identity (track replaced / deck switched): a prior track's
                    # hold must not resurrect. Only a real PLAY on THIS key re-enables.
                    self._pack_play_hold_key = None
                    self._pack_play_hold_deadline = 0.0
            if transport is not None:
                player.select_scripted(
                    soundswitch_id=ssid, elapsed_ms=elapsed_ms, transport=transport,
                    metadata_ready=True, authority="fresh", source_errored=False,
                    elapsed_discontinuous=False, track_changed=False,
                )
            else:
                player.clear_selection()
```

Notes:
- `getattr(self._os, "was_playing", False)` / `getattr(d, "playing", False)`:
  production `OutputState`/`DeckState` always have these; the defaults only keep
  the synthetic test harness safe. Tests must set them explicitly (Task 2).
- The literal `select_scripted` flags stay valid because the call is only reached
  when `happy` (fresh, not discontinuous, not track-changed) — mirrors the existing
  call.
- Do not move the `_pack_last_load_gen`/`_pack_last_elapsed_ms` bookkeeping
  (`3284`, `3291`); it must keep updating every tick.

Commit: `feat(soundswitch): RW-2 hold scripted cue on pause, zero on stop`.

### Task 2 — `tests/test_state_manager_pack_driver.py`: driver-level pause ≠ stop
1. Extend `_set` (`tests/...:101-106`) to set `was_playing` explicitly (no reliance
   on the `getattr` default) and to allow passing `now` through to the driver:
   ```python
   def _set(sm, *, ssid="", elapsed_ms=0, playing=False, load_gen=1, snap=FRESH,
            active=1, was_playing=None):
       if was_playing is None:
           was_playing = playing
       sm._os = SimpleNamespace(active_deck=active, was_playing=was_playing)
       ...
   ```
   Default `was_playing=playing` keeps the existing playing-path tests unchanged.
2. **Re-scope D5** → `test_confirmed_stop_zeros_scripted_base`: drive a playing tick
   (records the hold latch), then a tick with `playing=False, was_playing=False` and
   `now` past the deadline; assert ZERO.
3. Add the driver-level tests in Part D (T1–T11, T-hold-expiry, T-replace-never-
   played). All use the real `LaserPackPlayer` over `_pack()` and the `_FakeBackend`
   recorder; pass `now` explicitly to exercise the deadline.

Commit: `test(soundswitch): RW-2 pause holds cue, confirmed stop zeros`.

### Task 3 — inner-tick / event-ordering tests (cover what injection cannot)
The existing harness calls `_drive_pack_output()` directly after `_set` injection;
`_push_tick_inner` is never run (D11 stubs it). That **cannot** catch the
ARM_GUARD/lane-divergence timing, the track-replace-while-paused chain, or the
PAUSE-before-snapshot transient — exactly the review findings. Add tests that drive
the **real** `_push_tick_inner` (and the pack driver) with an injected clock and a
real/fake `PositionCache`, not `_set`. See Part D T-real-* and T12. Where a step
genuinely cannot be exercised purely (no AppKit/device), mark it **[U]** — do not
assert a synthetic pass.

Commit: `test(soundswitch): RW-2 inner-tick pause/stop timing + replacement`.

---

## Part C — Invariants that MUST still hold (live safety)

1. **§7.1 sole writer.** The driver only *reads* `os.was_playing`/`d.*` and writes
   its own `_pack_*` locals. StateManager stays the only `DeckState` writer.
2. **No obsolete *paused* frame (A.5).** A paused render requires
   `os.was_playing==True`, impossible on a tick where inner force-stopped; the
   player caches no frame; both freshness races fail to ZERO. The PAUSE-before-
   snapshot forward transient (A.5) is bounded by reader lag and self-corrects.
   The unchanged *playing* path keeps its pre-existing bounded resume-settle race.
3. **Identity-bound hold (review BLOCKER fix).** A freshly loaded, never-played
   track can never render as paused: the latch is set only on a `playing` tick and
   keyed by `(active, load_gen)`; a new `load_gen` (track replace) or new
   `active` (deck switch) mismatches the key → ZERO until that exact identity is
   observed playing.
4. **Bounded hold = OS2L consistency (review MAJOR fix).** Paused holds at most
   `STOP_DEBOUNCE_S` past the last playing tick; the pack lane zeros within one
   200 Hz tick (~5 ms) of when `_update_lighting` idles the OS2L lane (`3128`) —
   bounded to `STOP_DEBOUNCE_S ± one tick`, no multi-second divergence.
5. **§7.8 fail-to-zero.** Every non-happy path and every expired/identity-mismatch
   hold resolves to ZERO via `clear_selection()`; the `try/except` submits
   `_PACK_ZERO_FRAME` on any exception (`3315-3322`).
6. **§7.9 manual-static + blackout precedence.** ZERO path stays
   `clear_selection()` so held static stands alone; a held static still wins over a
   paused base (`render()` `363-372`); **blackout** (the only driver-wired mask,
   `set_masks(blackout=bool(s.blackout_held), emergency=False)`, `3270`) still
   zeroes first (`render()` `346-347`). **Emergency** is a player capability the
   pack driver does not assert; emergency wiring is pre-existing and out of RW-2
   scope (RW-4/RW-5). No `transport="stopped"/"ended"/"unloaded"` is emitted.
7. **§7.2 push-loop purity.** Pure in-memory branching plus a `time.monotonic()`
   read; no I/O, sleep, retry, or blocking added.
8. **§7.10/§7.11 default-off neutrality.** Driver still no-ops unless `rt.active`;
   no implicit enable, backend change, restart, or hardware open.
9. **§7.12 no leaks.** No new status string/path/id/port/byte; `sanitized_status()`
   untouched (RW-5 owns status).
10. **Timecode-only boundary ([C], pre-existing).** When position comes only from
    the timecode anchor (DDJ-800 deck-2 mode=4112 / DVS), inner synthesizes a snap
    (`3342-3352`) that is never stored in `self._cache`, so the driver's own
    `self._cache.get(active)` returns None → `fresh=False` → ZERO. Neither playing
    nor paused engages in that mode; RW-2 changes nothing there.

---

## Part D — Tests (pure seams; no device, no AppKit, no hardware)

`_pack()` frame: at 0 ms CH1==5; at 50/60 ms CH1==9; ZERO_FRAME is all zeros.

**Driver-level (extended `_set`, explicit `was_playing` and `now`):**
- **T1 `test_pause_holds_current_scripted_frame`** — playing@50 (`now=t0`) → non-zero
  (CH1==9); then `playing=False, was_playing=True, elapsed_ms=50, now=t0+0.1` →
  frame **equals** the 50 ms frame (held, not ZERO).
- **T2 `test_confirmed_stop_zeros`** (re-scoped D5) — playing tick, then
  `playing=False, was_playing=False` → ZERO.
- **T3 `test_paused_frame_derives_from_events_not_cache`** — playing@60 (CH1==9);
  pause `elapsed_ms=30, was_playing=True, now=t0+0.1` → frame == 30 ms frame
  (CH1==5), proving re-derivation at the current elapsed (use 60→30; 30 < seek
  threshold so no discontinuity).
- **T-hold-expiry `test_pause_hold_expires_to_zero`** — playing@50 (`now=t0`,
  deadline=t0+0.5); pause `playing=False, was_playing=True, now=t0+0.6` → ZERO even
  though loaded/fresh/`was_playing` (bounded hold, review MAJOR fix).
- **T-replace-never-played `test_loaded_unplayed_track_not_held`** — playing@50
  load_gen=1 (latch=(1,1)); then `playing=False, was_playing=True, load_gen=2,
  ssid=SSID, now=t0+0.1` (simulating a replacement that resolved a scripted id but
  was never played) → ZERO, and assert the latch was reset (review BLOCKER fix).
- **T4 `test_pause_then_resume_continues`** — play@50 → pause@50 (hold) →
  `playing=True, now=t0+0.2` @60 → non-zero at 60 ms; deadline refreshed.
- **T5 `test_pause_with_held_static_shows_static`** — paused base + held slot 8 →
  CH1==200.
- **T6 `test_pause_then_blackout_is_zero`** — paused + `blackout_held=True` → ZERO.
- **T7 `test_stale_while_paused_zeros`** — `playing=False, was_playing=True,
  snap=STALE` → ZERO.
- **T8 `test_unloaded_paused_zeros`** — `playing=False, was_playing=True, ssid=""`
  → ZERO.
- **T9 `test_track_change_while_paused_zeros`** — hold, then `load_gen` bumped →
  ZERO that tick (track_changed); static stands if held.
- **T10 `test_seek_discontinuity_while_paused_zeros`** — paused@50, then
  `elapsed_ms=3000` (≥`_PACK_SEEK_JUMP_MS`) → ZERO that tick; next stable tick holds
  the 3000 ms frame (if still within deadline).
- **T11 `test_master_switch_zeros_until_new_deck_confirmed`** — deck 1 holding; flip
  `active=2, was_playing=False` (as `_on_master_changed`); deck 2 idle → ZERO; deck
  2 `playing=True` → renders deck 2 (and sets latch=(2, gen)).

**Inner-tick / event-ordering (Task 3 harness; drive `_push_tick_inner`, not `_set`):**
- **T-real-hold-vs-osl `test_inner_pause_hold_matches_osl_idle`** — with an injected
  clock and a fake fresh `PositionCache`, pause a playing scripted deck and **assert
  both**: (a) the pack lane holds the cue and then zeros at `last_play +
  STOP_DEBOUNCE_S`, and (b) `os.lighting_mode` reaches `"idle"` within one 200 Hz
  tick of that boundary (proves Findings 1 & 4). This test is **purely exercisable**
  — `_apply_lighting("idle")` only calls `self._out.*`/`self._sse.*` (`3204-3208`),
  both satisfied by the `mock.Mock()` output already in `_make_sm` (`tests/...:97-98`)
  plus a real `PositionCache` and the injected `now`; `lighting_mode` is directly
  observable on the injected `_os`. **The `[U]` escape (Task 3) is NOT permitted for
  this test** — it must assert, or a future `was_playing`-timing regression passes
  green.
- **T-real-replace `test_inner_replacement_while_paused_not_held`** — playing deck,
  PAUSE, then post `TRACK_LOADED` (load_gen++) + resolve a scripted `soundswitch_id`
  via the real `_on_filepath_resolved`, advance ticks → assert the never-played new
  track renders ZERO (real-path Finding 2).
- **T-real-pause-before-snap `test_inner_pause_before_snapshot_settles`** — drive a
  tick with `d.playing=False` but `snap.playing=True`; assert the held frame tracks
  the bounded forward elapsed then settles when `snap.playing` flips (Finding 3).
- **T12 `test_event_chain_load_play_pause_resume_master_replace_stop`** — drive the
  realistic sequence through the real inner/event path and assert the pack frame at
  each step: load → resolve → play → pause(hold) → resume → master switch → replace
  → stop → idle. **No synthetic `_set` fallback** — any step that cannot be
  exercised purely is marked **[U]**, not asserted (review MAJOR fix).

**Purity / regression (unchanged after the `_set` default):** D1, D2, D3, D4, D6,
D7, D8, D10, D11, D13, D14 and the manual-static policy tests (`200-227`).

---

## Part E — Acceptance (definition of done)

- [ ] `_drive_pack_output` distinguishes paused from stopped via the identity-bound,
      deadline-bounded latch with `os.was_playing` as the obsolete-frame guard;
      paused emits `select_scripted(transport="paused", elapsed_ms=d.elapsed_ms)`,
      all zero-states emit `clear_selection()`; `transport="stopped"/"ended"/
      "unloaded"` is never emitted.
- [ ] Two driver-local fields added (peers of `_pack_last_*`); no
      `DeckState`/`OutputState` write; diff confined to `__init__`, the gate block,
      the driver signature, and the test files.
- [ ] Pause holds and is re-derived from events at the current elapsed (T1, T3);
      hold expires to ZERO at `STOP_DEBOUNCE_S` (T-hold-expiry); a never-played
      loaded track is never held (T-replace-never-played, T-real-replace); confirmed
      stop zeros (T2); resume continues (T4); held static and blackout precedence
      preserved while paused (T5, T6).
- [ ] Stale/unload/track-change/discontinuity/master-switch all zero (T7–T11); the
      inner-tick timing/lane and pause-before-snapshot tests pass (T-real-*); the
      event-chain test (T12) passes or marks un-exercisable steps **[U]**.
- [ ] Invariants C.1–C.10 hold; the obsolete-frame proof (C.2) is reflected in T3;
      identity binding (C.3) in T-replace-*; bounded-hold/OS2L consistency (C.4) in
      T-hold-expiry / T-real-hold-vs-osl.
- [ ] **Gates run and outputs recorded (all HARDWARE-UNVALIDATED):**
      ```bash
      cd /Users/bbui
      python3.14 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation \
        --project ~/Music/SoundSwitch/default.ssproj \
        --output-dir /tmp/rbss-soundswitch-rw2-proof          # expect 29/0/0 (RW-2 does not touch pack gen)

      cd /Users/bbui/rb_ss_bridge_v2
      python3 -m unittest discover tests                       # full suite green
      python3 tools/check_docs_metadata.py
      python3 tools/check_agent_contracts.py
      python3 tools/check_docs_drift.py
      python3 tools/check_docs_staleness.py --report           # advisory
      git diff --check
      ```
- [ ] Focused module also run under Python 3.11 (`python3.11 -m unittest
      tests.test_state_manager_pack_driver`) — RW-2 touches no dataclass/import/
      startup surface, so 3.11 is advisory.
- [ ] `enabled=false`, `dry_run=true`, `output_backend=none` unchanged; no restart,
      enable, backend change, MIDI/serial open, or hardware action.
- [ ] Doc update per anti-drift (§7): flip RW-2 in
      `soundswitch_exporter_remaining_work.md` §5 to `[x] [C]` with the implementing
      commit; re-verify the `soundswitch_output` contract docs before bumping
      `last_verified_commit`.

## When you finish
Commit per task with the messages above. Report back: the gate diff, the
`__init__` field additions, the new/re-scoped test names with pass counts, the
proof-gate verdict (expect `PASS_IMPLEMENTATION_MAY_BEGIN`, 29/0/0), full-suite and
hard-docs-check results.

---

## RW-3/RW-4/RW-5 sequencing (one paragraph; do not spec yet)
RW-2 is first because pause-vs-stop is the **transport** foundation every later M2
task builds on: **RW-3** (explicit scripted/autoloop/idle mode-authority gate)
decides *whether* the scripted base is owned at all, reusing `active_deck`,
`d.scripted_id`, `d.meta.soundswitch_id`, `os.lighting_mode`, and fresh-position
authority — it can only gate a base whose transport is already correctly derived,
so it depends on RW-2. **RW-4** (controller-input health fail-to-zero) latches
held-static/blackout inputs to zero on worker death / mailbox loss / stale hold; it
layers on the RW-2/RW-3 base because "fail to zero" is well-defined only once the
base's normal value (including a legitimately held *paused* cue) is settled.
**RW-5** (operational status/menubar) then exposes the completed machine
(`scripted_active` vs `paused` vs `zero_safe` vs `input_degraded`) as sanitized
status — last, because it reports the contract the prior three define. Sequence:
**RW-2 → RW-3 → RW-4 → RW-5**, each a separate reviewed Part A–E spec and separate
commit, all under the unchanged default-off posture.
