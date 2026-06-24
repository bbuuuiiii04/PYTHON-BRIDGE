---
doc_status: active-plan
truth_level: code-grounded-design-spec
last_verified_commit: 8754ef2
last_verified_date: 2026-06-24
validation_scope: RW-2 scripted runtime transport (pause vs stop) design spec; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; default-off (enabled=false, dry_run=true, output_backend=none) — no restart/enable/hardware authorized
---

# Codex Implementation Spec — RW-2 Scripted Runtime Transport (pause vs stop)

> **Scope.** This spec closes the dependency root of milestone **M2** (scripted
> live-runtime contract closure): the SoundSwitch pack driver cannot today tell a
> *paused* deck from a *stopped* one, so a paused scripted track goes dark instead
> of holding its current cue. RW-2 makes the bridge-native CH1-CH19 pack driver
> distinguish the two using **existing** StateManager authority only.
>
> **Roles.** Opus authored this; **Codex implements it** after independent
> adversarial review. No implementation, output enable, backend change, restart,
> or hardware action is authorized by this document. Pack output stays default-off.
>
> **Evidence labels** (per `soundswitch_exporter_remaining_work.md` §1):
> **[C]** confirmed in current code/run · **[P]** policy decision made here, must be
> confirmed at review · **[U]** needs live/hardware evidence (none promoted by software inference).

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
The driver collapses *paused* and *stopped* into one `playing==False` branch.
The pure player already exposes the missing distinction —
`select_scripted(..., transport="paused")` is accepted and rendered
(`soundswitch_laser_player.py:213-224` accept; `271-275` + `312-313` render) — but
the driver never passes it. RW-2 is therefore a driver-side derivation change, not
a player change.

### A.3 The player contract this spec pins to (already authorized)
- **[C] The player caches no output frame.** `render_scripted_frame(document,
  elapsed_ms)` (`soundswitch_laser_player.py:103-115`) rebuilds the frame from an
  all-ZERO state by replaying immutable timeline events with
  `0 <= time <= elapsed_ms` every call (`_apply_events`, `85-100`). "Paused" and
  "playing" take the **same** render path at the same `elapsed_ms`
  (`_scripted_base` `271-275` → `313`). Therefore "paused holds the current frame
  derived from events at authoritative elapsed, never a cached/obsolete frame" is
  satisfied **by construction**, provided the driver passes the *current
  authoritative elapsed*. The only obsolete-frame risk is a stale `elapsed_ms`
  input — addressed in A.5/C.2 below.
- **[C] Zero-states must use `clear_selection()`, not `transport="stopped"`.**
  `clear_selection()` (`247-256`) sets `_selection=None`; `render()` then yields a
  `missing_selection` base (ZERO) **and lets a held Static Override stand alone**
  (`render()` `351-353`, `361-363`). By contrast `transport in
  ("stopped","ended","unloaded")` returns a *non-`missing_selection`* diagnostic
  ZERO (`272-274`), which `render()` returns **before** the held-static check
  (`361-362`) — suppressing a held Static Override. The accepted manual-static
  policy (`state_manager.py:3299-3303`; tests `200-216`) requires held static to
  remain visible on deck-authority loss, so the driver's zero path **must remain
  `clear_selection()`**. `transport="stopped"/"ended"/"unloaded"` must **not** be
  emitted by the driver.

### A.4 The pause-vs-stop discriminator already exists in StateManager — [C]
StateManager already separates a transient pause from a confirmed stop, for the
OS2L/lighting lane, via `os.was_playing` and the `STOP_DEBOUNCE_S` window:

- **[C]** `STOP_DEBOUNCE_S = 0.5` s, `MEM_STALE_S = 3.0` s, `ARM_GUARD_S = 3.0` s,
  `PLAY_SETTLE_MS = 400` (`config.py:62,74-76`); `_PACK_SEEK_JUMP_MS = 2000`
  (`state_manager.py:113`).
- **[C]** On `playing==False`, inner starts a debounce
  (`os.not_playing_since`) and only after `>= STOP_DEBOUNCE_S` declares
  `stop_confirmed` (`state_manager.py:3518-3525`), then calls `_do_stop()` which
  sets **`os.was_playing = False`** (`3552`, `_do_stop` `4165-4190`, flag at
  `4169`). Before the debounce expires, `os.was_playing` stays **True** — that is
  the *paused* state.
- **[C]** `os.was_playing` becomes True only in `_do_resume()` (`4206`) after the
  `PLAY_SETTLE_MS` resume settle (`3581-3588`); it is forced False by `_do_stop()`
  (`4169`) and by `_on_master_changed()` (`2578`).
- **[C]** `_do_stop()` does **not** clear `d.scripted_id`, does **not** clear
  `d.meta` (so `soundswitch_id` survives), and does **not** reset `d.elapsed_ms`.
  A stopped deck therefore still looks "happy" to the existing gate except for the
  `playing` flag — confirming the gap and confirming a hold is physically possible.

So RW-2 needs **no new transport owner and no new state field**: it reuses
`os.was_playing` (the existing pause/stop authority) plus the gate the driver
already computes. StateManager remains the sole `DeckState` writer (invariant §7.1).

### A.5 Why `os.was_playing` is the safe input (no obsolete frame) — [C]
The authoritative elapsed the driver renders is `d.elapsed_ms`, written every
**non-stale** tick at `state_manager.py:3434-3436`. When paused, `snap.playing` is
false so interpolation adds nothing (`3422`) and `d.elapsed_ms` freezes at the
memory pause position — the correct held position.

Critical coupling that makes "render paused only when `was_playing==True`"
obsolete-frame-free:

1. The **only** early return before the elapsed write at `3436` is the stale block
   at `3357`.
2. If inner takes that stale block while `os.was_playing` was True, it calls
   `_do_stop()` → `was_playing=False` (`3358-3361`, `4169`) **before** the driver
   runs.
3. Therefore `os.was_playing == True` at driver time ⟹ inner did **not** take the
   stale early return this tick ⟹ inner executed `3436` ⟹ `d.elapsed_ms` is
   current this tick.

The driver also independently re-reads the position cache for its own `fresh`
gate (`3265`, `3292`). The two possible cross-thread races both fail safe:
- inner saw fresh (elapsed current, `was_playing` True) but the driver's later
  `snap` read is stale → `fresh=False` → `clear_selection()` (ZERO one tick early);
- inner saw stale (`was_playing` forced False) but the driver's later `snap` read
  is fresh → `playing=False && was_playing=False` → `clear_selection()` (ZERO).

In neither race can the driver render a *held (paused)* frame at a non-current
elapsed: a paused render requires `was_playing==True`, which is impossible on a
tick where inner force-stopped (it sets `was_playing=False`).

**Scope of this proof.** It is total for the **paused** path RW-2 adds. The
**playing** path is unchanged from today and carries a pre-existing, bounded
race: during the ≤`PLAY_SETTLE_MS` resume-settle window `d.playing` is True while
`os.was_playing` is still False, and if memory goes stale-then-fresh within one
tick the playing branch can render at a one-tick-old `d.elapsed_ms`, which the
next-tick `discont` gate (`3286-3290`) then zeroes. RW-2 neither introduces nor
worsens this; promoting it out of existence (a published per-tick authority
object) is the RW-3/option-(B) hardening noted in A.7, deliberately out of scope.

### A.6 Behavior of the seven transport states under this derivation — [C]/[P]
| Transport | Detected by (existing state) | Driver action |
|---|---|---|
| **playing** | `d.playing` True + happy gate | `select_scripted(transport="playing", elapsed_ms=d.elapsed_ms)` |
| **paused** | `d.playing` False + `os.was_playing` True + happy gate | `select_scripted(transport="paused", elapsed_ms=d.elapsed_ms)` — holds frozen frame **[P]** |
| **stopped** | `os.was_playing` False (debounce expired / `_do_stop`) | `clear_selection()` → ZERO base |
| **ended** | end-of-track while loaded (no distinct signal) | treated as **paused** then **stopped** via the same path **[P]**, see A.7 |
| **unloaded** | `_pack_normalize_id(ssid) is None` (no/cleared `soundswitch_id`; unscripted) | `clear_selection()` → ZERO |
| **stale** | `snap is None or snap.is_stale(MEM_STALE_S)` | `clear_selection()` → ZERO |
| **errored** | driver `try/except` (`3315-3322`); seek discontinuity `discont` (`3286-3290`); `track_changed` (`3281-3284`) | ZERO (except path submits `_PACK_ZERO_FRAME`; discont/track_changed → `clear_selection()`) |

"happy gate" = `fresh and metadata_ready and not track_changed and not discont`
(the existing booleans at `3292-3295`, `3281-3290`).

### A.7 The one policy decision — pause-hold duration — [P]
The player contract ("paused holds the current frame") does not fix *how long* a
deck may stay "paused" before it is "stopped". Two coherent designs exist:

- **(A) Debounce-bounded hold — RECOMMENDED and specified below.** Paused is
  defined as `was_playing==True` (the existing pre-stop window:
  `STOP_DEBOUNCE_S` plus any active `ARM_GUARD_S`). A brief pause holds the cue;
  if the pause lasts past the debounce, `_do_stop()` flips `was_playing=False` and
  the pack resolves to ZERO — the **same instant** the OS2L/lighting lane idles
  (`_update_lighting` debounce, `3128-3132`). Plain meaning: *pause the music and
  the bridge-native lights freeze on the current cue; resume right away and they
  continue seamlessly; leave it stopped and the lights go to safe black, exactly
  like the SoundSwitch lane already does.* This is race-free (A.5), adds no state,
  and keeps the two output lanes consistent.
- **(B) Indefinite hold while loaded — NOT specified.** Define paused purely by
  the happy gate (ignore `was_playing`), so the frozen cue holds until the track
  is unloaded/replaced, the master deck changes, or memory goes stale. Plain
  meaning: *a stopped-but-loaded deck keeps a frozen partial cue on the rig
  indefinitely.* Rejected for RW-2 because it (i) diverges from the OS2L lane
  after 0.5 s, (ii) leaves a frozen mid-cue look during a long stop (reads as a
  glitch on a live rig), and (iii) reintroduces the bounded obsolete-elapsed race
  A.5 closes (it would rely on `discont` to catch it one tick later).

**[P] Decision pinned: implement (A).** The independent reviewer/operator must
confirm this duration semantics before Codex starts; if (B) is preferred, the
elapsed-authority hardening in A.5 must be promoted to an explicit published
per-tick authority object (out of scope here).

"Ended" is not given a separate detector: there is no reliable distinct
end-of-track signal in current state, and the genuine end-of-show transitions
(track replace → `track_changed`; deck switch → new active deck; RB stop → stale)
already resolve to ZERO. Under (A) a track that plays to its end and stops holds
for at most the debounce window, then zeroes — acceptable and consistent.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Touch **only** `state_manager.py` (`_drive_pack_output` body) and
  `tests/test_state_manager_pack_driver.py`. Do **not** modify
  `soundswitch_laser_player.py`, `soundswitch_pack_runtime.py`, the push-loop
  structure (`_push_tick`/`_push_tick_inner`), `_update_lighting`, the OS2L/laser/
  LED lanes, config, or any startup/dataclass/import surface.
- Do **not** add a new transport state field, timer, or thread. Reuse
  `os.was_playing` and the booleans the driver already computes.
- Do **not** emit `transport="stopped"/"ended"/"unloaded"` (see A.3); the zero
  path stays `clear_selection()`.
- No filesystem/subprocess/MIDI/serial/socket/sleep/retry/blocking-queue work in
  the driver (invariant §7.2). The change is pure in-memory branching.
- No behavior change when pack output is absent/disabled/default-off: the driver
  is already inert unless `rt.active` (`3258-3260`, `PackRuntime.active`
  `soundswitch_pack_runtime.py:29-33`).

### Task 1 — `state_manager.py`: derive transport in `_drive_pack_output`
Replace the scripted-base gate at `state_manager.py:3304-3311` (the
`if playing and fresh ... else clear_selection()` block) with a transport
derivation. Keep every line above (`3261-3295`, masks/static, track_changed,
discont, fresh, ssid, metadata_ready) and the single submit below (`3314`)
**unchanged**.

```python
            # 3. Automatic base transport derivation (RW-2). The pure player
            #    re-renders from immutable events at elapsed_ms every tick, so
            #    paused holds the current authoritative frame, never a cached one.
            #    Manual-static policy (A.3): the ZERO path stays clear_selection()
            #    so a held Static Override stands alone; we never emit
            #    transport="stopped"/"ended"/"unloaded" (those would suppress static).
            happy = fresh and metadata_ready and not track_changed and not discont
            was_playing = bool(getattr(self._os, "was_playing", False))
            if happy and playing:
                transport = "playing"
            elif happy and was_playing:
                # paused: PAUSE set d.playing=False but stop is not yet confirmed
                # (os.was_playing still True). os.was_playing==True guarantees inner
                # wrote d.elapsed_ms this tick (A.5), so elapsed_ms is current.
                transport = "paused"
            else:
                transport = None  # stopped / unloaded / stale / track_changed / discont
            if transport is not None:
                player.select_scripted(
                    soundswitch_id=ssid, elapsed_ms=elapsed_ms, transport=transport,
                    metadata_ready=True, authority="fresh", source_errored=False,
                    elapsed_discontinuous=False, track_changed=False,
                )
            else:
                player.clear_selection()
```

Notes for the implementer:
- `getattr(self._os, "was_playing", False)` is deliberate: production `self._os`
  is `OutputState` (has `was_playing`), but the driver's unit-test harness builds
  `self._os` as a `SimpleNamespace` without it (`tests/...:102`). The default keeps
  the driver safe if the attribute is ever absent (fail to *not paused* → ZERO).
- The literal flags passed to `select_scripted` (`authority="fresh"`,
  `source_errored=False`, `elapsed_discontinuous=False`, `track_changed=False`)
  remain valid because they are only reached when `happy` is True (i.e. fresh, not
  discontinuous, not track-changed). This mirrors the pre-existing call.
- Do not move the `_pack_last_load_gen`/`_pack_last_elapsed_ms` bookkeeping
  (`3284`, `3291`); it must keep updating every tick exactly as today.

Commit: `feat(soundswitch): RW-2 hold scripted cue on pause, zero on stop`.

### Task 2 — `tests/test_state_manager_pack_driver.py`: prove pause ≠ stop
1. Extend the `_set` helper (`tests/...:101-106`) to set `was_playing` on the
   synthetic `self._os`:
   ```python
   def _set(sm, *, ssid="", elapsed_ms=0, playing=False, load_gen=1, snap=FRESH,
            active=1, was_playing=None):
       if was_playing is None:
           was_playing = playing  # playing decks count as "was playing"
       sm._os = SimpleNamespace(active_deck=active, was_playing=was_playing)
       ...
   ```
   Default `was_playing = playing` keeps existing playing-path tests (D2, D8, D9,
   D10, D14, exception tests) behaviorally unchanged.
2. **Re-scope D5** (`test_stop_does_not_retain_old_scripted_frame`, `145-153`):
   make it a *confirmed stop* by passing `playing=False, was_playing=False`; assert
   ZERO. Rename to `test_confirmed_stop_zeros_scripted_base`.
3. **Add** the tests in Part D (T-pause-hold, T-pause-frame-derivation,
   T-resume, T-master-switch, T-event-chain, etc.). Use a real `LaserPackPlayer`
   over the synthetic `_pack()` and the `_FakeBackend` recorder already in the
   file (no MIDI/serial/Enttec/network).

Commit: `test(soundswitch): RW-2 pause holds cue, confirmed stop zeros`.

---

## Part C — Invariants that MUST still hold (live safety)

1. **§7.1 sole writer.** The driver remains read-only w.r.t. `DeckState`/`os`;
   it only *reads* `os.was_playing`. StateManager stays the only `DeckState`
   writer. (No write added.)
2. **No obsolete *paused* frame (A.5).** A paused (held) render happens only when
   `d.elapsed_ms` was written this tick. Proof: a paused render requires
   `os.was_playing==True`, which is impossible on a tick where inner took the
   stale early return (it would have called `_do_stop`→`was_playing=False` first).
   The player itself caches no frame. Both cross-thread freshness races fail to
   ZERO, never to a held non-current frame. (The unchanged *playing* path keeps
   its pre-existing bounded resume-settle race; see A.5 "Scope of this proof".)
3. **§7.8 fail-to-zero.** Every non-happy path (`not fresh`, `not metadata_ready`,
   `track_changed`, `discont`, `was_playing==False` while not playing) resolves the
   automatic base to ZERO via `clear_selection()`; the driver's `try/except`
   already submits `_PACK_ZERO_FRAME` on any exception (`3315-3322`).
4. **§7.9 manual-static + blackout precedence unchanged.** The ZERO path stays
   `clear_selection()` (yields `missing_selection`), so a held Static Override
   still stands alone during deck-authority loss; `select_scripted(transport=
   "paused")` produces a real base over which a held static still wins (`render()`
   `363-372`), and blackout/emergency still zeroes first (`render()` `346-347`).
   No `transport="stopped"/"ended"/"unloaded"` is emitted.
5. **§7.2 push-loop purity.** The change is pure in-memory branching: no I/O,
   sleep, retry, or blocking added to the tick.
6. **§7.10/§7.11 default-off neutrality.** Driver still no-ops unless `rt.active`;
   with pack disabled/absent there is no behavior change and no implicit enable,
   backend change, restart, or hardware open.
7. **§7.12 no leaks.** No new status string, path, id, port, or byte is surfaced;
   `sanitized_status()` is untouched (RW-5 owns status expansion).
8. **Lane-consistency boundary (documented, not a regression).** Under decision
   (A) the pack lane zeroes at the same debounce as the OS2L `_update_lighting`
   idle transition, so the two lanes stay consistent across a pause→stop. The pack
   driver still does not consult `os.lighting_mode`/`d.scripted_id` — that
   explicit mode-authority gate is **RW-3**, intentionally out of RW-2 scope.
9. **Timecode-only boundary (documented, [C], pre-existing).** When position
   comes only from the timecode anchor (e.g. DDJ-800 deck-2 mode=4112 / DVS, where
   inner *synthesizes* a snap at `3342-3352`), that synthesized snap is never
   stored in `self._cache`, so the driver's own `self._cache.get(active)` returns
   None → `fresh=False` → `clear_selection()` → ZERO. The pack lane already does
   not render scripted output in timecode-only mode; RW-2 changes nothing here —
   neither playing nor paused engages, so there is no pause/stop divergence to
   reason about in that mode.

---

## Part D — Tests (pure seams; no device, no AppKit, no hardware)

All tests use the existing harness: real `LaserPackPlayer` over `_pack()`, the
`_FakeBackend` frame recorder, synthetic deck/os/cache via the extended `_set`.
The frame at 50 ms for `_pack()` has CH1 == 9 (D2 already relies on this); the
frame at 0 ms has CH1 == 5; ZERO_FRAME is all zeros.

**Driver-level pause ≠ stop (the core gap):**
- **T1 `test_pause_holds_current_scripted_frame`** — play fresh at 50 ms
  (`playing=True`) → non-zero (CH1==9); then `playing=False, was_playing=True,
  elapsed_ms=50, snap=FRESH` → assert frame **equals the 50 ms frame** (CH1==9),
  i.e. held, **not** ZERO.
- **T2 `test_confirmed_stop_zeros`** (re-scoped D5) — `playing=False,
  was_playing=False` → ZERO.
- **T3 `test_paused_frame_derives_from_events_not_cache`** — play at 60 ms
  (both events applied → CH1==9); then pause with `elapsed_ms=30, was_playing=True`
  → assert frame equals the **30 ms** frame (only the t=0 event → CH1==5), proving
  the paused frame is re-derived from events at the *current* elapsed, not a
  retained 60 ms frame. (Use 60→30, not 0, so no "elapsed==0 means unset"
  ambiguity; the 30 ms step is well under `_PACK_SEEK_JUMP_MS` so it is not a
  discontinuity.)
- **T4 `test_pause_then_resume_continues`** — play@50 (9) → pause@50 (hold 9) →
  `playing=True, was_playing=True` @60 → non-zero frame for 60 ms; proves resume
  renders at the live elapsed.
- **T5 `test_pause_with_held_static_shows_static`** — paused base + held static
  slot 8 → CH1==200 (static wins over paused base, like playing).
- **T6 `test_pause_then_blackout_is_zero`** — paused + `blackout_held=True` → ZERO
  (blackout beats paused base).

**Zero-state coverage (stop / unload / stale / change / discontinuity):**
- **T7 `test_stale_while_paused_zeros`** — `playing=False, was_playing=True,
  snap=STALE` → ZERO (fresh gate fails even though was_playing True).
- **T8 `test_unloaded_paused_zeros`** — `playing=False, was_playing=True, ssid=""`
  → ZERO (metadata_ready False).
- **T9 `test_track_change_while_paused_zeros`** — pause holding, then `load_gen`
  bumped → ZERO that tick (track_changed), static still stands if held (parallels
  existing D9/`208-216`).
- **T10 `test_seek_discontinuity_while_paused_zeros`** — paused at 50, then
  `elapsed_ms=3000, was_playing=True` (jump ≥ `_PACK_SEEK_JUMP_MS`) → ZERO that
  tick; next tick stable at 3000 → holds the 3000 ms frame.
- **T11 `test_master_switch_zeros_until_new_deck_confirmed`** — set active deck 1
  paused-holding; flip `active=2, was_playing=False` (as `_on_master_changed`
  does) with deck 2 idle → ZERO; then deck 2 `playing=True` → renders deck 2.

**Real event-chain integration (one test, exercises the StateManager path, not
just the driver):**
- **T12 `test_event_chain_load_play_pause_resume_master_replace_stop`** — drive a
  realistic sequence through the public event/tick surface and assert the pack
  frame at each step: track load → filepath/`soundswitch_id` resolve → scripted
  match → PLAY (renders playing) → PAUSE within debounce (holds) → resume
  (continues) → master switch to mirror (zeros / renders mirror) → track replace
  on original deck (zeros) → confirmed stop (zeros) → return to autoloop/idle
  (driver base stays ZERO, since autoloop is intentionally never driven —
  `select_autoloop` ban, existing D10). This is the test the roadmap requires that
  "current SSID-injection/source-only tests" do not provide. If wiring the full
  StateManager event loop is impractical in-process, drive it via the same
  synthetic `_set` transitions in sequence and assert the per-step frames; mark any
  step that cannot be exercised purely as **[U]** rather than faking a pass.

**Purity / regression (keep existing, confirm unchanged):**
- Existing D1, D2, D3, D4, D6, D7, D8, D10, D11, D13, D14 and the manual-static
  policy tests (`200-227`) must still pass unchanged after the `_set` default
  `was_playing=playing`.

---

## Part E — Acceptance (definition of done)

- [ ] `_drive_pack_output` distinguishes paused (`was_playing` True, happy gate)
      from stopped/stale/unloaded/changed/discont; paused emits
      `select_scripted(transport="paused", elapsed_ms=d.elapsed_ms)`, all
      zero-states emit `clear_selection()`; `transport="stopped"/"ended"/
      "unloaded"` is never emitted.
- [ ] No new state field, timer, thread, or `DeckState`/`os` write; only
      `os.was_playing` is newly *read*. Diff is confined to the gate block and the
      test file.
- [ ] Pause holds the current cue and is provably re-derived from events at the
      current elapsed (T1, T3); confirmed stop zeros (T2); resume continues (T4);
      held static and blackout precedence preserved while paused (T5, T6).
- [ ] Stale/unload/track-change/discontinuity/master-switch all zero correctly
      while paused (T7-T11); the real event-chain test (T12) passes or marks
      un-exercisable steps **[U]**.
- [ ] Invariants C.1-C.8 hold; the obsolete-frame proof (C.2) is reflected in T3.
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
- [ ] Because RW-2 touches no dataclass/import/startup surface, a Python 3.11 run
      is advisory; still run the focused pack-driver module under 3.11 to confirm
      no version-sensitive behavior (`python3.11 -m unittest
      tests.test_state_manager_pack_driver`).
- [ ] `enabled=false`, `dry_run=true`, `output_backend=none` unchanged; no
      restart, enable, backend change, MIDI/serial open, or hardware action taken.
- [ ] Doc update per anti-drift (§7): flip the RW-2 checkboxes in
      `soundswitch_exporter_remaining_work.md` §5 from `[ ] [P]` to `[x] [C]` with
      the implementing commit, and re-verify the `soundswitch_output` contract
      docs named by `docs/agents/change_contracts.yml` before bumping
      `last_verified_commit`.

## When you finish
Commit per task with the messages above. Report back: the gate diff, the new/
re-scoped test names with pass counts, the proof-gate verdict (expect
`PASS_IMPLEMENTATION_MAY_BEGIN`, 29/0/0), full-suite and hard-docs-check results,
and an updated independent-review prompt that attacks: the pause/stop
discriminator choice (A vs B), the obsolete-frame proof (C.2), manual-static
precedence under paused, and master-switch / track-replace zeroing.

---

## RW-3/RW-4/RW-5 sequencing (one paragraph; do not spec yet)
RW-2 is first because pause-vs-stop is the **transport** foundation every later
M2 task builds on: **RW-3** (explicit scripted/autoloop/idle mode-authority gate)
must decide *whether* the scripted base is owned at all by reusing `active_deck`,
`d.scripted_id`, `d.meta.soundswitch_id`, `os.lighting_mode`, and fresh-position
authority — but it can only gate a base whose transport (playing vs paused vs
zero) is already correctly derived, so it depends on RW-2. **RW-4**
(controller-input health fail-to-zero) latches the held-static/blackout inputs to
zero on worker death / mailbox loss / stale hold; it layers on top of the RW-2/RW-3
base because "fail to zero" is only well-defined once the base's normal
non-failure value (including a legitimately held *paused* cue) is settled.
**RW-5** (operational status/menubar) then exposes the now-complete state machine
(`scripted_active` vs `paused` vs `zero_safe` vs `input_degraded`) as sanitized
status — it must come last because it reports the contract the prior three define.
Sequence: **RW-2 → RW-3 → RW-4 → RW-5**, each a separate reviewed Part A–E spec and
separate commit, all under the unchanged default-off posture.
