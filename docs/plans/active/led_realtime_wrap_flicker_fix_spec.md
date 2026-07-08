---
doc_status: active-spec
truth_level: implementation-spec, code-grounded (verified at HEAD 63c52e0 + Opus/Fable adversarial verify 2026-07-07)
last_verified_commit: 63c52e0
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — realtime LED wrap-flicker guard (AWR-141)

Contract key: `led_govee` (`beat_sync_engine.py`). Root cause of the 2026-07-07 live
"RT effects flicker/strobe live but are calm in the LED Pad" report (RC2). This is a single
guard in one shared function; do not touch the runner, the renderer, or the WI-1 live clamp.

## Part A — Context & Root Cause (verified; read, do not implement)

Operator symptom: during live bridge runtime the realtime LED effects (breathing, twinkle, the
ambient/breakdown looks) visibly strobe and flicker; the **same** effects played in the standalone
LED Pad (no Rekordbox, no bridge) are smooth. The look definitions are fine — something in the live
path corrupts the frame stream.

Confirmed mechanism (each link read in current code; adversarially re-verified by a fresh-context
Opus pass 2026-07-07):

- The live beat the runner animates from can step **backward by a few thousandths of a beat**
  between render frames. Chain:
  - `state_manager.py:4062-4063` interpolates `raw_elapsed_ms = snap.elapsed_ms + (now −
    snap.updated_at)*1000` between ~60 Hz memory snapshots; a fresh snapshot can land below the
    interpolated overshoot ⇒ a small backward correction. [confirmed]
  - The WI-1 clamp `led_dispatch_policy.py:1690-1694` holds sub-beat backward moves **flat**
    (`abs_beat_pos = prev`) while the published tuple's timestamp advances every 200 Hz tick
    (`state_manager.py:4147-4153`, `now` at `:4151`). Beat frozen, wall-time advancing. [confirmed]
  - The runner extrapolates `abs_pos = anchor.abs_beat_pos + max(0, now − captured_monotonic)*
    bpm/60` at 30 fps (`govee_realtime_runner.py:289-292`), anchor re-fetched every frame (`:216`).
    During a flat-hold the memory beat contributes nothing, so `abs_pos` follows the 200 Hz-vs-30 fps
    beat between publishes and steps back ~0.003–0.01 beat on its down phases. [confirmed]
- `TriggerClock.advance` flags **any** backward move larger than `_EPS` (1e-6) as a wrap:
  `wrapped = abs_beat < self._last_abs - _EPS` (`beat_sync_engine.py:59`, `_EPS` `:18`). The
  ~0.003–0.01 beat step is 10³–10⁴× that threshold, so every down-phase of the wobble reads as a
  track-loop wrap. [confirmed]
- A wrap **restarts the animation** in all three sync modes:
  - continuous: `if wrapped: self._instances = [self._make_instance(...)]` (`beat_sync_engine.py:154-156`)
    → new instance `local_beat=0` → the breathing/twinkle sine phase snaps to 0 mid-cycle
    (`govee_frame_renderer.py` renders `beat=ir.local_beat`, breathing intensity at
    `:1671-1674`). [confirmed]
  - overlap (comets) and retrigger: `advance` forces `spawn = 1 if self.spawn_on_wrap else 0` on a
    wrap (`beat_sync_engine.py:61-63`), so a jitter wrap spawns/retriggers a spurious instance too.
    [confirmed]
  Repeated restarts = the visible strobe/flicker. The breathing look is the sharpest case because
  its whole appearance is a slow sine that a phase-snap breaks most visibly. [confirmed]
- The LED Pad path derives **both** `abs_beat_pos` and `captured_monotonic` from the same monotonic
  clock (`tools/led_pad_playback.py:41-43,62-73`), so its beat is strictly monotonic — no wrap, no
  restart, smooth. This is why the Pad is the clean reference. [confirmed]

Net: `TriggerClock.advance` cannot tell a real track-loop/seek (a large backward jump) from
sub-beat extrapolation jitter, and treats both as wraps. The fix is to give it a threshold, exactly
as the WI-1 live clamp already does one layer up.

Not captured in this session's log: `[RGB] beat-clamp` and wrap events are DEBUG and this session
logged INFO/WARNING only. The mechanism is code-confirmed; the live *frequency* would be confirmed
by a DEBUG capture of `[RGB] beat-clamp` deltas. [unknown — needs live DEBUG, not blocking this fix]

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `beat_sync_engine.py`, `tests/test_beat_sync_engine.py` (extend), Part E docs.
- Do NOT touch: `govee_realtime_runner.py`, `govee_frame_renderer.py`, the WI-1 clamp in
  `led_dispatch_policy.py`, `state_manager.py`, or any config. The fix is entirely inside
  `TriggerClock.advance`.
- Do NOT change the method signature or return contract: `advance(abs_beat) -> (spawn_count:int,
  wrapped:bool)`. `configure`, `_spawn`, `_make_instance`, `_render_list`, `on_tick`, `animate`
  stay byte-identical.
- Error handling: pure arithmetic, no I/O, nothing to catch. Do not add try/except.
- Recover nothing from git; this is a new guard, not a restore.

### Task 1 — `beat_sync_engine.py`: add a wrap-hold threshold to `TriggerClock.advance`
Add a module constant near the existing constants (`MAX_PULSES`, `MAX_CATCHUP`, `_EPS`):

```python
WRAP_HOLD_BEATS = 0.5   # backward moves smaller than this are extrapolation jitter (~0.01 beat) or
                        # sub-beat loop rolls: hold, do not wrap/restart. A real track loop or seek
                        # is >= this (typically many beats) and still wraps. Tunable ceiling: raise
                        # toward 1.0 if any real short loop must NOT restart; lower toward the jitter
                        # magnitude (~0.02) if a ~half-beat loop must restart the animation.
```

Rewrite the body of `advance` so a backward move is a wrap **only** when it is at least
`WRAP_HOLD_BEATS`; a smaller backward move is held (no wrap, no spawn, and `_last_abs`/`_last_idx`
are NOT lowered so a later recovery does not spuriously spawn):

```python
def advance(self, abs_beat: float) -> tuple[int, bool]:
    """Return (spawn_count, wrapped). spawn_count is forward crossings capped at MAX_CATCHUP;
    wrapped is True only on a genuine backward jump (>= WRAP_HOLD_BEATS) — a track loop/seek.
    Sub-threshold backward moves (extrapolation jitter, short rolls) are held: no wrap, no spawn,
    and the high-water position is retained so recovery does not re-spawn."""
    abs_beat = float(abs_beat)
    idx = math.floor(abs_beat / self.division)
    if self._last_idx is None or self._last_abs is None:
        self._last_idx = idx
        self._last_abs = abs_beat
        return (0, False)
    delta = abs_beat - self._last_abs
    if delta <= -WRAP_HOLD_BEATS:
        # genuine backward jump: track loop / cue / seek
        self._last_idx = idx
        self._last_abs = abs_beat
        return (1 if self.spawn_on_wrap else 0, True)
    if delta < 0.0:
        # sub-threshold backward jitter / short roll: hold high-water mark, do not wrap or spawn
        return (0, False)
    spawn = 0
    if idx > self._last_idx:
        spawn = min(idx - self._last_idx, MAX_CATCHUP)
        self._last_idx = idx
    self._last_abs = abs_beat
    return (spawn, False)
```

Keep `_EPS` for any other current use; it is no longer the wrap boundary. Do not remove
`spawn_on_wrap`, `MAX_CATCHUP`, or the seed/reset logic.

## Part C — Invariants That MUST Still Hold (live safety)
- No I/O, no blocking, no allocation growth added — `advance` stays a pure arithmetic step on the
  30 fps runner thread (bridge_design 200 Hz push loop and the runner hot path unchanged).
- Real track-loop / seek behavior preserved: a backward jump ≥ `WRAP_HOLD_BEATS` still returns
  `wrapped=True` and still spawns/retriggers per `spawn_on_wrap`, so continuous effects re-sync at
  a genuine loop point and comets still spawn on a real loop.
- Forward behavior byte-identical: forward division crossings still spawn, capped at `MAX_CATCHUP`;
  a forward seek is unaffected.
- The WI-1 live playhead clamp (`led_dispatch_policy._clamp_led_beat`) is upstream and untouched;
  this guard is the runner-internal counterpart, not a replacement.
- Animation never freezes during a hold: instances run on `born_monotonic × bpm` in `_render_list`,
  so a held beat keeps the effect moving at tempo (it just does not restart).

## Part D — Tests (`tests/test_beat_sync_engine.py`, pure in-memory)
Extend the existing suite (no files, no runner, no transport):
1. `advance` sub-threshold backward (e.g. division=1.0, feed 10.00 then 9.995) → returns `(0, False)`;
   `_last_abs` stays 10.00 (held, not lowered).
2. Oscillating jitter (10.00 → 9.995 → 10.00 → 9.996 …) over many calls → zero wraps, zero spawns.
3. Genuine loop: 10.00 → 2.00 (delta −8) → returns `wrapped=True`, spawn = 1 with `spawn_on_wrap=True`,
   0 with `spawn_on_wrap=False`; `_last_abs`/`_last_idx` re-seed to 2.00.
4. Boundary: backward exactly −`WRAP_HOLD_BEATS` wraps; −(`WRAP_HOLD_BEATS`−0.01) holds.
5. Forward regression: crossing one division boundary forward spawns 1; a forward jump of many
   divisions spawns exactly `MAX_CATCHUP`.
6. Engine-level (continuous): configure a `breathe`-style continuous effect, tick forward normally,
   then feed a sub-threshold backward step — assert the active instance's `born_abs_beat` is
   unchanged (no replacement / no phase reset); then feed a ≥`WRAP_HOLD_BEATS` backward step and
   assert the instance IS replaced (re-sync at a real loop).

## Part E — Acceptance (definition of done)
- [ ] Task 1 exact; `advance` return contract unchanged.
- [ ] `python3 -m unittest tests.test_beat_sync_engine` and `tests.test_govee_realtime_runner` pass;
      full `discover tests` at the known ~3-red baseline (live-config LED test, export parity
      fixtures, SS golden slot 16) — do not "fix" those.
- [ ] Hard checks pass: `check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`.
- [ ] `led_govee` `docs_update`: note the wrap-guard in `docs/subsystems/led_govee.md`; add an
      AWR-141 row to `docs/status/active_work_registry.md` (implemented / software-tested;
      HARDWARE-UNVALIDATED); record the new tests in `docs/validation/software_test_inventory.md`.
      Leave feature/support/validation matrices consistent (no status upgrade).
- [ ] Status language §10 only.

## When You Finish
Report changed files, tests/checks run, and this operator summary: "The realtime LED effects were
restarting themselves a few times a second because a tiny backward wobble in the live beat looked
like a track loop; now only a real loop or seek restarts them, so breathing and the ambient looks
render as smoothly live as they do in the LED Pad. Nothing about real loops, comets, or forward
playback changes. Watch live for smooth breathing during a breakdown; a DEBUG capture of
`[RGB] beat-clamp` would quantify how often the wobble was firing." Rollback = revert the single
`advance` change. End with the literal line CODEX-WRAPGUARD-DONE.
