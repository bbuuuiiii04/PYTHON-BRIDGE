# Implementation Spec — T7c StateManager scripted-mode pack driver

status: planned — **PENDING REVIEW (ChatGPT), NOT YET IMPLEMENTED**
last_updated: 2026-06-22
implementer: Claude (Opus 4.8) — per operator override for this task (NOT Codex)
target branch/PR: `soundswitch/impl` / #116 (current head `490f1ab`)

> **Review gate:** This plan must be reviewed before implementation begins. A spike was
> written then **fully reverted** (`git checkout state_manager.py`) so the branch carries the
> plan only. The verified findings from that spike are folded in below (see "Spike findings").
> Operator decision captured: an operator-held Static Override **persists across a deck stop**
> (matches the player's emergency/blackout > static > base precedence); the driver does NOT
> force-ZERO a held static on stop.

## Part A — Context & root cause (verified; read, do not implement)

T7b builds the pack player/controller/backend at startup but never wires them into the
runtime tick, so `PackOutputBackend.submit_frame` has **no caller** — pack mode produces
no DMX.

- [confirmed] `__main__.py:919-921` builds `soundswitch_frame_sender`, `soundswitch_midi_input`,
  `soundswitch_pack_player`; `__main__.py:1004-1015` constructs `StateManager(...)` **without**
  passing any of them. The backend (`soundswitch_pack_bundle.laser_backend`) is only handed to the
  laser-executor wiring (`__main__.py:912`).
- [confirmed] `PackOutputBackend` (`laser_output_backend.py:132-204`) has two independent paths:
  `trigger(msg)` (executor scene-SELECTION; records `last_accepted_identity`, **no DMX**) and
  `submit_frame(frame)` → `frame_sender.submit(frame)` (the DMX path). `grep submit_frame` shows
  **no production caller today**. So adding a StateManager `submit_frame` caller cannot collide with
  the executor's `trigger` path — they are complementary, not competing.
- [confirmed] `LaserPackPlayer` (`soundswitch_laser_player.py:180-360`) is a pure state controller.
  `select_scripted(soundswitch_id, elapsed_ms, *, transport, metadata_ready, authority,
  source_errored, elapsed_discontinuous, track_changed)` (213-224), `select_autoloop` (226-232),
  `hold_static(slot)` (234-239), `release_static(slot)` (241-245), `set_masks(*, blackout, emergency)`
  (253-258), `render()` (334-360). `reload(pack)` (203-211) clears all state and latches
  `_waiting_after_reload` (renders a diagnostic until the next `select_*`).
- [confirmed — KEY SAFETY FACT] **Every non-output path already renders `ZERO_FRAME`.**
  `_diagnostic()` returns `PlayerResult(ZERO_FRAME, ...)` (`:65-67`); `render()` returns `ZERO_FRAME`
  on emergency/blackout (`:335-336`) and on `missing_selection` (`:340-342`). Scripted diagnostics
  cover `transport_{stopped,ended,unloaded}`, `metadata_not_ready`, `source_error`, `track_change`,
  `elapsed_discontinuity`, `stale_authority`, `ambiguous_authority`, `missing_identity`,
  `scripted_not_found`, `unsupported_*`, `player_error` (`:260-304`). Therefore
  `player.render().frame` is **always safe to submit**: a valid scripted frame, or ZERO on any
  idle/stop/stale/error/mask condition. The driver does not need its own ZERO logic — it must only
  (a) feed correct inputs, and (b) **fail conservative**: when a flag is uncertain, set it to the
  ZERO-producing value (e.g. `authority="stale"`, `metadata_ready=False`).
- [confirmed] `MidiInputSnapshot` (`soundswitch_midi_input.py:36-44`): `held_static_slot: int|None`,
  `blackout_held: bool`. `snapshot()` (`:100-118`) self-expires stale holds; **non-blocking**.
- [confirmed] `_push_tick` (`state_manager.py:3149`) is the 200 Hz loop body. Per tick it sets
  `active = os.active_deck`, `d = self._deck[active]` (the authoritative `DeckState`), `mirror`,
  `snap = self._cache.get(active)`. The laser decision path runs in several branches via
  `self._laser_executor.on_tick/on_decision` (3197-3198, 3235-3236, 3432-3433, 3673-3674). The
  stale path is `snap is None or snap.is_stale(MEM_STALE_S)` (3182-…).
- [confirmed] Authoritative deck fields: `d.elapsed_ms`, `d.playing`, `d.meta.soundswitch_id`,
  `d.load_gen` (incremented on track load, `state_manager.py:2559`; echoed via FILEPATH_RESOLVED).
- [confirmed] Constructor `StateManager.__init__` (`state_manager.py:309-324`) is all-keyword with
  defaults; storing `self._laser_*`/`self._led_*` at 332-338 is the established pattern.
- [confirmed] Invariant (AGENTS.md §6): `_push_tick` must not gain blocking network/socket/MIDI/
  filesystem/subprocess I/O. `submit_frame` is a bounded non-blocking mailbox
  (`laser_output_backend.py:178-181` → `frame_sender.submit`); `snapshot()` is in-memory. Both are
  tick-safe. `StateManager` is the only `DeckState` writer — the driver READS deck state, never
  mutates it.

### Derived-flag sourcing (label per flag)
- `soundswitch_id` ← `d.meta.soundswitch_id` [confirmed]
- `elapsed_ms` ← `d.elapsed_ms` (int, ≥0) [confirmed]
- `transport` ← `"playing"` if `d.playing` else `"stopped"`; stop-stale branch ⇒ `"stopped"` [confirmed]
- `authority` ← `"stale"` when `snap is None or snap.is_stale(MEM_STALE_S)`, else `"fresh"`;
  `"ambiguous"` reserved (see unknown below) [confirmed for fresh/stale]
- `track_changed` ← driver-local: `True` when `(active, d.load_gen)` differs from the value the
  driver saw last tick [confirmed signal: load_gen at :2559]
- `metadata_ready` ← [assumed] `bool(normalize_soundswitch_id(d.meta.soundswitch_id))` i.e. an exact
  UUID is resolved. Conservative: unresolved ⇒ False ⇒ ZERO. VERIFY no separate "resolution pending"
  flag is more correct during impl.
- `source_errored` ← [unknown] no single SM field confirmed. Default `False`; if a reader/resolver
  error flag exists, wire it. Safe either way (a missed error still ZEROs via stale/identity paths).
- `elapsed_discontinuous` ← [assumed] driver-local: large backward/forward jump in `d.elapsed_ms`
  within the same `(active, load_gen)` vs last tick. SM has a seek concept for LED
  (`_clamp_led_beat`/`_reset_led_phrase_latch`, :2334-2374) but that is LED-beat, not pack-elapsed.
  Implement a local monotonic check; VERIFY threshold during impl. Conservative: on detected jump ⇒
  one ZERO tick, then resume.
- `ambiguous` ← [unknown] no confirmed SM signal in scope; leave as `"fresh"`/`"stale"` only for T7c.

### Spike findings (verified during the reverted spike — load-bearing for impl)
- [confirmed] `_push_tick` has **5 early `return`s** (now ~3219, 3258, 3398, 3428, 3449). A single
  end-of-method driver call would MISS those branches. **Use the wrap pattern:** rename the current
  body to `_push_tick_inner`, and a new `_push_tick` does
  `try: self._push_tick_inner()` / `finally: if self._pack_enabled: self._drive_pack_output()`.
  The `finally` guarantees once-per-tick driving across all returns AND drives ZERO even if the inner
  tick raised (supports C7). `_push_tick` is the public name called from prod (`state_manager.py`
  ~863/870), `session_replayer.py`, and ~150 test sites — the wrap keeps that name, and those callers
  are neutral because `_pack_enabled` is False without pack params.
- [confirmed] `_drive_pack_output(self)` should take **no args** and re-derive
  `active = self._os.active_deck`, `d = self._deck[active]`, `snap = self._cache.get(active)`
  itself (cheap dict reads) — decouples it from the inner tick's locals.
- [confirmed] **No mode branch needed.** The driver always calls `select_scripted(...)`. Autoloop is
  safe-zero *by omission*: `select_autoloop` is simply never called, and a non-scripted
  `soundswitch_id` yields the player's `scripted_not_found` → ZERO.
- [confirmed] Imports are safe at top of `state_manager.py` (no circular):
  `from .soundswitch_laser_player import ZERO_FRAME as _PACK_ZERO_FRAME,
  normalize_soundswitch_id`. `soundswitch_laser_player` does not import `state_manager`.
- [confirmed] `MEM_STALE_S` is already imported (`state_manager.py:39`); reuse it for the stale check.
- [proposed] Module constant `_PACK_SEEK_JUMP_MS = 2000` for the `elapsed_discontinuous` threshold
  (err HIGH — a missed discontinuity just renders at the new position; a false one ZEROs a tick).

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Do NOT modify: `laser_executor.py`, `laser_director.py`, `soundswitch_laser_player.py`,
  `soundswitch_midi_input.py`, `laser_output_backend.py`, the OS2L path, or any reader. T7c is
  injection + a read-only driver in `state_manager.py` plus the `__main__` wiring.
- No behavior change when all three pack params are `None` (default) — byte/order-neutral, the
  existing MIDI/laser path must be identical.
- Autoloop pack mode stays **safe-zero or held-static only** (T7d unproven). Do NOT call
  `select_autoloop`.

### Task 1 — `state_manager.py`: inject pack deps (default None, neutral)
Add to `__init__` signature (after `led_color_engine=None`, keyword, defaulted):
```python
        soundswitch_pack_player=None,
        soundswitch_midi_input=None,
        soundswitch_pack_backend=None,
```
Store alongside the laser attrs (near :333):
```python
        self._pack_player = soundswitch_pack_player
        self._pack_input = soundswitch_midi_input
        self._pack_backend = soundswitch_pack_backend
        self._pack_enabled = (
            soundswitch_pack_player is not None
            and soundswitch_pack_backend is not None
        )
        self._pack_last_load_gen: tuple[int, int] | None = None   # (active, load_gen)
        self._pack_last_elapsed_ms: int | None = None
        self._pack_last_static_slot: int | None = None
```
(Controller/`_pack_input` may be None even when player+backend exist — controller is optional.)

### Task 2 — `state_manager.py`: the driver method (read-only)
Add `_drive_pack_output(self, active, d, snap, now)` and call it ONCE at the END of `_push_tick`
(after every laser branch has run), guarded by `if self._pack_enabled:`. The method:
1. If `self._pack_player is None or self._pack_backend is None`: return (defensive; never raises).
2. Controller masks/static FIRST (if `self._pack_input is not None`):
   `s = self._pack_input.snapshot()`; `self._pack_player.set_masks(blackout=s.blackout_held,
   emergency=False)`; reconcile static: if `s.held_static_slot != self._pack_last_static_slot`:
   call `hold_static(s.held_static_slot)` when not None else `release_static(self._pack_last_static_slot)`;
   update `self._pack_last_static_slot`.
3. Derive flags per Part A (track_changed via `_pack_last_load_gen`; elapsed_discontinuous via
   `_pack_last_elapsed_ms`; transport/authority from `d.playing`/`snap`). Update the two trackers.
4. Selection:
   - scripted/idle/stopped/stale/error/deck-change/track-change → always
     `self._pack_player.select_scripted(soundswitch_id=d.meta.soundswitch_id,
     elapsed_ms=max(0, int(d.elapsed_ms or 0)), transport=…, metadata_ready=…, authority=…,
     source_errored=…, elapsed_discontinuous=…, track_changed=…)`. The player ZEROs all
     non-playing/uncertain cases — no separate idle branch needed.
   - autoloop → DO NOT call `select_autoloop`. Leave/clear the scripted selection so `render()`
     yields ZERO (plus any held static). (T7d gate.)
5. `self._pack_backend.submit_frame(self._pack_player.render().frame)`.
6. Wrap the whole method body in `try/except Exception` → log once + `submit_frame(ZERO_FRAME)`;
   never propagate into the tick.

### Task 3 — `__main__.py`: pass the deps to StateManager
At the `StateManager(...)` call (`:1004`), add:
```python
        soundswitch_pack_player=soundswitch_pack_player,
        soundswitch_midi_input=soundswitch_midi_input,
        soundswitch_pack_backend=soundswitch_pack_bundle.laser_backend,
```
Only the `PackOutputBackend` actually submits frames; `NoneBackend.submit_frame` is a no-op, so
dry-run/none/disabled remain output-free automatically.

## Part C — Invariants that MUST still hold (live safety)
- C1 default-off neutrality: all three params None ⇒ `_pack_enabled` False ⇒ `_drive_pack_output`
  returns immediately ⇒ existing MIDI/laser/LED behavior byte/order-identical.
- C2 no new tick I/O: only `snapshot()` (in-memory) + `submit_frame()` (bounded mailbox). No fs/MIDI/
  serial/net/subprocess in `_push_tick`. (AGENTS.md §6.)
- C3 StateManager remains the only `DeckState` writer — the driver READS `d`, never mutates it.
- C4 every stop/stale/error/reload/disable/deck-change/track-change/mode-transition/shutdown path
  resolves **ZERO**, never retained non-zero DMX. (Player guarantees this; driver must not bypass it
  with a stale held-static — reconcile static every tick.)
- C5 autoloop pack output is safe-zero/held-static only until T7d proves ticks/beat + universal phase
  origin.
- C6 `dry_run`/`output_backend=none`/disabled open neither MIDI nor serial and emit no DMX.
- C7 fail-conservative: any uncertain flag ⇒ ZERO-producing value; any exception ⇒ ZERO + log, never
  raise into the tick.

## Part D — Tests (`tests/test_state_manager_pack_driver.py`, new)
Pure/seam tests with fakes — NO real MIDI/serial/Enttec/DMX/network. Use a fake player recording
`select_scripted`/`set_masks`/`hold_static`/`release_static` calls and a fake backend recording
`submit_frame` frames; drive `_drive_pack_output` directly with synthetic `d`/`snap`.
1. default-off: player/backend None ⇒ `_drive_pack_output` no-ops; no submit_frame; existing tick
   unaffected (smoke).
2. scripted playing fresh ⇒ `select_scripted(..., transport="playing", authority="fresh",
   metadata_ready=True)`; backend gets a non-ZERO frame for a known id (use a tiny synthetic pack).
3. metadata_not_ready / source_error / track_change / elapsed_discontinuity / stale / ambiguous each
   ⇒ submitted frame == ZERO_FRAME (assert diagnostic code via player or ZERO frame).
4. transitions → ZERO: scripted→autoloop, deck change, track load (load_gen bump), stop, stale,
   pack reload (`reload()` then no select ⇒ ZERO), backend/player exception, shutdown.
5. autoloop mode ⇒ `select_autoloop` NEVER called; submitted frame ZERO (or held static only).
6. controller: blackout_held ⇒ `set_masks(blackout=True,...)` ⇒ ZERO; held_static_slot set/clear ⇒
   `hold_static`/`release_static` reconciled exactly once per change; submit reflects static.
7. exception in snapshot/render/submit ⇒ caught, ZERO submitted, no raise.
8. no-I/O assertion: monkeypatch `open`/socket/serial to fail; one driver tick must not touch them.

## Part E — Acceptance (definition of done)
- [ ] Tasks 1-3 implemented; `python3 -m unittest discover tests` green on **3.11 and 3.14**.
- [ ] New test file covers D1-D8; default-off neutrality proven.
- [ ] Autoloop path proven to never call `select_autoloop` and to ZERO.
- [ ] No new I/O in `_push_tick` (D8 + code review of the method).
- [ ] `tools/check_docs_metadata.py` / `check_agent_contracts.py` / `check_docs_drift.py` pass;
      update `docs/subsystems/soundswitch_output.md` + change-contract `soundswitch_output` if the
      contract lists docs for a StateManager wiring change.
- [ ] Proof gate still `PASS_IMPLEMENTATION_MAY_BEGIN`; CI `unit` job green.
- [ ] Ledger updated with commit + gate outputs. Status stays SOFTWARE-VALIDATED / HARDWARE-UNVALIDATED.

## Adversarial self-review (checklist item 9)
- "Double-write to Enttec?" — No: executor uses `trigger` (selection only); driver uses `submit_frame`
  (sole caller). Confirmed by grep. BUT: if a future change makes the executor call `submit_frame`,
  this driver would conflict — note in `soundswitch_output.md` that `submit_frame` has exactly one
  owner (the StateManager pack driver).
- "Held static survives a stop and keeps lights on?" — Risk if static reconciled only on change.
  Mitigation: player applies emergency/blackout > static > base each `render()`, and a stop/stale
  selection still renders ZERO base; a *held static with no mask* WOULD persist by design (operator
  intent). C4 covers selection ZERO; document that an operator-held static is intentional and cleared
  only by controller release or `reload()`. VERIFY this matches operator intent before shipping.
- "elapsed_discontinuous false-positives on normal playback?" — A per-tick monotonic check with too
  tight a threshold could ZERO mid-track. Use the same seek semantics as LED
  (`LED_BACKSTEP_SEEK_BEATS` analog) and only flag genuine jumps; one ZERO tick then resume.
- "load_gen tracker stale across deck switch?" — Track `(active, load_gen)` as a tuple so a deck
  switch (active change) counts as track_changed ⇒ ZERO for one tick. Confirmed needed.
- "Pack reload mid-show?" — `reload()` latches `_waiting_after_reload` ⇒ ZERO until next `select_*`;
  driver calls `select_scripted` next tick ⇒ resumes only with fresh authority. Safe.
