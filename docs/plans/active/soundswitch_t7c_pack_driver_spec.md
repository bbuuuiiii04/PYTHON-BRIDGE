# Implementation Spec — T7c StateManager scripted-mode pack driver

status: **implemented / software-accepted** (ChatGPT review ACCEPT as software checkpoint)
last_updated: 2026-06-22
implementer: Claude (Opus 4.8) — per operator override for this task (NOT Codex)
implemented at `1adbe5c`; current PR head `d3a9645` (CI green). Spec rev 2 applied + post-accept
manual-static policy resolved (see below).
target branch/PR: `soundswitch/impl` / #116

> **Manual-static policy (resolved 3a, tested):** a held Static Override is operator-controlled via
> the independent MIDI controller, so it stays VISIBLE during any deck-authority problem (idle / stop
> / stale / error / track-change / discontinuity) — it loses ONLY to blackout, emergency, pack
> disabled, and shutdown. The controller's own hold-timeout auto-releases it. Tests:
> `test_state_manager_pack_driver.py::{test_stale_authority_with_held_static_shows_static,
> test_track_change_with_held_static_shows_static, test_shutdown_style_disable_drops_even_held_static}`.

> **Revision 2** folds in the ChatGPT review + operator corrections:
> 1. metadata head `419a044`;
> 2. **held-static model corrected** — SoundSwitch shows manual Static Looks even with no track
>    playing, so manual static must stay visible while idle; automatic base must ZERO on
>    stop/stale/error/track-change; static still loses to blackout/emergency/pack-disabled/shutdown;
> 3. `_drive_pack_output(self)` takes **no args**, re-derives `active/d/snap/now` itself (wrap pattern
>    only — no `(self, active, d, snap, now)`);
> 4. **inner-exception safety**: a plain `finally` does NOT guarantee ZERO — if `_push_tick_inner`
>    raises, submit `ZERO_FRAME` directly to the backend, then **re-raise**; do not run the normal
>    driver after an inner exception;
> 5. C4 rewritten (below).

## Part A — Context & root cause (verified; read, do not implement)

T7b builds the pack player/controller/backend at startup but never wires them into the runtime tick,
so `PackOutputBackend.submit_frame` has **no caller** — pack mode produces no DMX.

- [confirmed] `__main__.py:919-921` builds the player/controller/sender; `__main__.py:1004-1015`
  constructs `StateManager(...)` WITHOUT passing them. Backend goes only to the laser wiring (`:912`).
- [confirmed] `PackOutputBackend` (`laser_output_backend.py:132-204`): `trigger(msg)` = executor
  scene-SELECTION (records `last_accepted_identity`, **no DMX**); `submit_frame(frame)` →
  `frame_sender.submit(frame)` (the DMX path, **no production caller today**). So a StateManager
  `submit_frame` caller cannot collide with the executor's `trigger` path.
- [confirmed] `LaserPackPlayer` (`soundswitch_laser_player.py:180-362`) is a pure state controller:
  `select_scripted(...)` (213-224), `select_autoloop(...)` (226-232), `hold_static(slot)` (234-239),
  `release_static(slot)` (241-245), `set_masks(*, blackout, emergency)` (253-258), `render()`
  (334-362), `reload(pack)` (203-211, clears all state + latches `_waiting_after_reload`).
  There is currently **no** public way to clear the automatic base selection without clearing static
  (Task 1 adds one).
- [confirmed — KEY SAFETY FACTS in `render()`]:
  - emergency/blackout ⇒ `ZERO_FRAME` BEFORE static (`:335-336`) → **static loses to masks**.
  - `_waiting_after_reload` ⇒ reload diagnostic ZERO (`:337-339`).
  - `_selection is None` ⇒ base = `missing_selection` (`:340-342`); this is the ONLY base diagnostic
    that does NOT early-return (`:350` returns early only when `code != "missing_selection"`).
  - With base `missing_selection` AND `_active_static_slot is not None`, render applies the static
    look via `resolve_frame(...)` and returns the static frame (`:352-362`).
  - Every other non-output condition (`transport_stopped`, `stale_authority`, `metadata_not_ready`,
    `source_error`, `track_change`, `elapsed_discontinuity`, `missing_identity`, `scripted_not_found`,
    `unsupported_*`, `player_error`) returns its `_diagnostic()` result, which is
    `PlayerResult(ZERO_FRAME, …)` (`:65-67`) and **suppresses static** (early-return at `:350`).
  - **Consequence:** to show a standalone manual static while idle, the driver must put the player in
    the `missing_selection` state (i.e. `_selection = None`) — NOT call `select_scripted(transport=
    "stopped")` (that yields `transport_stopped` → ZERO, static suppressed).
- [confirmed] `MidiInputSnapshot` (`soundswitch_midi_input.py:36-44`): `held_static_slot: int|None`,
  `blackout_held: bool`. `snapshot()` (`:100-118`) self-expires stale holds; in-memory, non-blocking.
- [confirmed] `_push_tick` (`state_manager.py:3164` after the reverted-spike line shift; re-verify):
  the 200 Hz loop. Sets `active = self._os.active_deck`, `d = self._deck[active]`,
  `snap = self._cache.get(active)`. Laser path runs via `self._laser_executor.on_tick/on_decision`.
  Stale check: `snap is None or snap.is_stale(MEM_STALE_S)`. **`_push_tick` has 5 early `return`s** —
  a single end-of-method call would miss branches; use the wrap pattern (Task 4).
- [confirmed] Authoritative deck fields: `d.elapsed_ms`, `d.playing`, `d.meta.soundswitch_id`,
  `d.load_gen` (incremented on track load, `:2559`). `MEM_STALE_S` already imported (`:39`).
- [confirmed] Invariant (AGENTS.md §6): `_push_tick` must not gain blocking I/O. `submit_frame` is a
  bounded non-blocking mailbox; `snapshot()` is in-memory. The driver READS `DeckState`; StateManager
  remains the only writer.
- [confirmed] No circular import: `from .soundswitch_laser_player import ZERO_FRAME as
  _PACK_ZERO_FRAME, normalize_soundswitch_id` is safe at the top of `state_manager.py`.

### Accepted held-static / idle model (operator-corrected)
- Automatic scripted/autoloop **base** ⇒ ZERO when stopped / no track / no valid playback authority
  (stale/error/track-change/discontinuity/metadata-not-ready). The driver expresses this by calling
  `clear_selection()` (base → `missing_selection`), NOT `select_scripted(transport="stopped")`.
- Manual **Static Override** is operator-controlled and MAY visibly output even with no track playing
  (stands alone via the `missing_selection` base).
- Manual static still LOSES to: blackout, emergency, pack disabled, shutdown, explicit output stop.
- Autoloop DMX stays **safe-zero** (driver never calls `select_autoloop`) until T7d.
- Known T7c limitation (acceptable): while a deck is *playing a valid-UUID track that is not a pack
  scripted row* (`scripted_not_found`) the held static is suppressed (base diagnostic ≠
  missing_selection). Idle/stopped/stale/error all show standalone static correctly. Revisit only if
  the operator needs static over non-scripted playback.

### Derived-flag sourcing
- `soundswitch_id` ← `d.meta.soundswitch_id` [confirmed]; `elapsed_ms` ← `max(0, int(d.elapsed_ms or 0))` [confirmed]
- `playing` ← `bool(d.playing)` [confirmed]; `fresh` ← `not (snap is None or snap.is_stale(MEM_STALE_S))` [confirmed]
- `metadata_ready` ← `normalize_soundswitch_id(soundswitch_id) is not None` [assumed; conservative]
- `track_changed` ← driver-local `(active, d.load_gen)` change [confirmed signal]
- `elapsed_discontinuous` ← driver-local jump ≥ `_PACK_SEEK_JUMP_MS` within same `(active, load_gen)` [assumed]
- `source_errored` ← [unknown] no confirmed SM field; default `False` (safe — other gates ZERO)

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Touch only: `soundswitch_laser_player.py` (Task 1, additive method + test), `state_manager.py`
  (Tasks 2-4), `__main__.py` (Task 5), and new/updated tests. Do NOT modify `laser_executor.py`,
  `laser_director.py`, `soundswitch_midi_input.py`, `laser_output_backend.py`, the OS2L path, readers.
- All three pack params `None` (default) ⇒ byte/order-neutral; existing MIDI/laser/LED path identical.
- Never call `select_autoloop`. Never reach into the player's private `_selection` from StateManager.

### Task 1 — `soundswitch_laser_player.py`: add `clear_selection()`
Additive public method on `LaserPackPlayer` (does not change any existing path):
```python
    def clear_selection(self) -> PlayerResult:
        """Clear the automatic scripted/autoloop base WITHOUT touching held static or masks.

        render() then yields a ``missing_selection`` base (ZERO), so a held Static Override
        stands alone — matching SoundSwitch showing a manual Static Look while idle. Static
        still loses to blackout/emergency and to the post-reload wait latch.
        """
        self._selection = None
        return self.render()
```
Tests (extend `tests/test_soundswitch_laser_player.py`): (a) `clear_selection` with a held static ⇒
returns the static frame; (b) `clear_selection` with no static ⇒ ZERO; (c) `clear_selection` while
blackout held ⇒ ZERO (static loses to mask); (d) `clear_selection` does not clear `_active_static_slot`.

### Task 2 — `state_manager.py`: inject pack deps (default None, neutral)
Add to `__init__` (keyword, after `recorder=...`): `soundswitch_pack_player=None`,
`soundswitch_midi_input=None`, `soundswitch_pack_backend=None`. Store near the laser attrs:
```python
        self._pack_player = soundswitch_pack_player
        self._pack_input = soundswitch_midi_input
        self._pack_backend = soundswitch_pack_backend
        self._pack_enabled = (soundswitch_pack_player is not None
                              and soundswitch_pack_backend is not None)
        self._pack_last_load_gen: tuple[int, int] | None = None
        self._pack_last_elapsed_ms: int | None = None
        self._pack_last_static_slot: int | None = None
        self._pack_logged_error = False
```
Add module constant near `_LATENCY_WARN_MS`: `_PACK_SEEK_JUMP_MS = 2000`. Add the top import noted in
Part A.

### Task 3 — `state_manager.py`: `_drive_pack_output(self)` (no args; read-only)
```python
    def _drive_pack_output(self) -> None:
        player, backend = self._pack_player, self._pack_backend
        if player is None or backend is None:
            return
        try:
            active = self._os.active_deck
            d = self._deck[active]
            snap = self._cache.get(active)

            # 1. Controller masks + static overrides (in-memory snapshot; no I/O).
            if self._pack_input is not None:
                s = self._pack_input.snapshot()
                player.set_masks(blackout=bool(s.blackout_held), emergency=False)
                slot = s.held_static_slot
                if slot != self._pack_last_static_slot:
                    if slot is not None:
                        player.hold_static(int(slot))
                    elif self._pack_last_static_slot is not None:
                        player.release_static(int(self._pack_last_static_slot))
                    self._pack_last_static_slot = slot

            # 2. Derive happy-path gate (fail-conservative; uncertain ⇒ clear_selection ⇒ ZERO base).
            load_key = (active, int(getattr(d, "load_gen", 0)))
            track_changed = (self._pack_last_load_gen is not None
                             and load_key != self._pack_last_load_gen)
            self._pack_last_load_gen = load_key
            elapsed_ms = max(0, int(getattr(d, "elapsed_ms", 0) or 0))
            discont = (not track_changed and self._pack_last_elapsed_ms is not None
                       and abs(elapsed_ms - self._pack_last_elapsed_ms) >= _PACK_SEEK_JUMP_MS)
            self._pack_last_elapsed_ms = elapsed_ms
            fresh = not (snap is None or snap.is_stale(MEM_STALE_S))
            playing = bool(getattr(d, "playing", False))
            ssid = getattr(getattr(d, "meta", None), "soundswitch_id", "") or ""
            metadata_ready = _pack_normalize_id(ssid) is not None

            # 3. Automatic base: scripted only on the full happy path; else clear (static stands alone).
            if playing and fresh and metadata_ready and not track_changed and not discont:
                player.select_scripted(
                    soundswitch_id=ssid, elapsed_ms=elapsed_ms, transport="playing",
                    metadata_ready=True, authority="fresh", source_errored=False,
                    elapsed_discontinuous=False, track_changed=False)
            else:
                player.clear_selection()

            # 4. Submit exactly one frame.
            backend.submit_frame(player.render().frame)
        except Exception:
            if not self._pack_logged_error:
                log.exception("[SM] pack driver error; resolving ZERO")
                self._pack_logged_error = True
            try:
                backend.submit_frame(_PACK_ZERO_FRAME)
            except Exception:
                pass
```

### Task 4 — `state_manager.py`: wrap `_push_tick` (covers 5 early returns + inner-exception ZERO)
Rename the current `def _push_tick(self) -> None:` body to `def _push_tick_inner(self) -> None:`.
Add a new wrapper (keep the public name — prod, replayer, ~150 tests call it):
```python
    def _push_tick(self) -> None:
        try:
            self._push_tick_inner()
        except BaseException:
            # An inner crash must not retain non-zero DMX. Submit ZERO directly
            # (NOT via _drive_pack_output, which reads possibly-partial state), then re-raise.
            if self._pack_enabled and self._pack_backend is not None:
                try:
                    self._pack_backend.submit_frame(_PACK_ZERO_FRAME)
                except Exception:
                    pass
            raise
        if self._pack_enabled:
            self._drive_pack_output()
```

### Task 5 — `__main__.py`: pass the deps to StateManager (`:1004`)
```python
        soundswitch_pack_player=soundswitch_pack_player,
        soundswitch_midi_input=soundswitch_midi_input,
        soundswitch_pack_backend=soundswitch_pack_bundle.laser_backend,
```
`NoneBackend.submit_frame` is a no-op ⇒ dry-run/none/disabled stay output-free automatically.

## Part C — Invariants that MUST still hold (live safety)
- C1 default-off neutrality: all params None ⇒ `_pack_enabled` False ⇒ no driver; existing behavior
  byte/order-identical (wrapper's normal branch just returns).
- C2 no new tick I/O: only `snapshot()` (in-memory) + `submit_frame()` (bounded mailbox).
- C3 StateManager remains the only `DeckState` writer; driver READS `d`.
- **C4 (rewritten):** every stop / stale / error / reload / disable / deck-change / track-change /
  mode-transition / shutdown path must produce **ZERO automatic base output**. Held static STATE may
  remain stored internally, but must NOT visibly override a known stop/stale/error diagnostic — the
  driver enforces this by calling `clear_selection()` (base → `missing_selection` ⇒ ZERO base; a held
  static stands alone only because it is operator-controlled and idle is not an error). A genuine
  blackout/emergency/pack-disabled/shutdown still ZEROs even a held static.
- C5 autoloop output is safe-zero (never `select_autoloop`) until T7d.
- C6 dry-run/`output_backend=none`/disabled open neither MIDI nor serial and emit no DMX.
- C7 inner `_push_tick_inner` exception ⇒ ZERO submitted directly + original exception re-raised;
  any driver exception ⇒ ZERO + log-once, never raised into the tick.

## Part D — Tests (`tests/test_state_manager_pack_driver.py`, new) + Task-1 player tests
No real MIDI/serial/Enttec/DMX/network. Use a real `LaserPackPlayer` + tiny synthetic pack
(`_document`/`_look`/`_pack` in `tests/test_soundswitch_laser_player.py`), a fake backend recording
`submit_frame` frames, an optional fake input returning a `MidiInputSnapshot`, and synthetic
`d`/`snap` (SimpleNamespace) — drive via `sm._drive_pack_output()` / `sm._push_tick()`.
1. default-off: player/backend None ⇒ no `submit_frame`; existing tick unaffected.
2. scripted playing+fresh+valid id ⇒ `select_scripted(...)`; non-ZERO frame for a known scripted id.
3. **no track playing + held static ⇒ static frame submitted** (driver used `clear_selection`).
4. **no track playing + no held static ⇒ ZERO.**
5. **stopped automatic base does not retain old scripted frame** (play→stop ⇒ ZERO base next tick).
6. **blackout held + static held ⇒ ZERO.**
7. **pack disabled / shutdown ⇒ no DMX / ZERO** as appropriate.
8. **stale/error automatic authority does not retain old scripted frame** (⇒ `clear_selection` base ZERO).
9. track-change / deck-change ⇒ automatic base ZERO (clear_selection) for that tick.
10. **autoloop never calls `select_autoloop`.**
11. once-per-tick through early returns: `_push_tick()` with each early-return branch still drives once.
12. no `submit_frame` double-writer (driver is the only caller; executor uses `trigger`).
13. **inner `_push_tick_inner` exception ⇒ ZERO submitted directly AND original exception re-raised.**
14. no blocking I/O in the driver path (monkeypatch `open`/socket/serial to fail; one tick must not hit them).

## Part E — Acceptance (definition of done)
- [ ] Tasks 1-5 done; `python3 -m unittest discover tests` green on **3.11 and 3.14**.
- [ ] D1-D14 + Task-1 player tests pass; default-off neutrality proven.
- [ ] No new I/O in `_push_tick`/driver (D14 + review). Driver is the sole `submit_frame` caller.
- [ ] Hard checks pass; update `docs/subsystems/soundswitch_output.md` + `soundswitch_output`
      contract (note: `submit_frame` has exactly one owner — the StateManager pack driver).
- [ ] Proof gate still PASS; CI `unit` job green. Ledger updated with commit + gate outputs.
- [ ] Status stays SOFTWARE-VALIDATED / HARDWARE-UNVALIDATED.

## Adversarial self-review (checklist item 9)
- "Idle held static never shows?" — Fixed by Task 1 `clear_selection()` (base `missing_selection` ⇒
  static stands alone). Verified against `render()` :350-362.
- "Stopped/stale retains last scripted frame?" — No: driver calls `clear_selection()` (base ZERO) on
  any non-happy-path; `submit_frame` is called every tick with the fresh `render()`.
- "Inner tick crash leaves lights on?" — No: wrapper submits ZERO directly then re-raises (C7); the
  normal driver is NOT run after an inner crash (it reads possibly-partial state).
- "Double-write to Enttec?" — No: executor `trigger` (selection only) vs driver `submit_frame` (sole
  caller). Document the single-owner rule in `soundswitch_output.md`.
- "elapsed_discontinuous false-positives?" — `_PACK_SEEK_JUMP_MS=2000` errs HIGH; a missed jump just
  renders at the new position, a false one ZEROs one tick.
- "Static suppressed over a non-scripted playing track" — known acceptable T7c limitation (documented
  in Part A); idle/stopped/stale/error all show standalone static correctly.
