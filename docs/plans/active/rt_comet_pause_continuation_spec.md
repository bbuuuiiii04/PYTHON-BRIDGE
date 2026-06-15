# Codex Implementation Spec — Comet Free-Flight: Rate-Lock + Pause Continuation

**Implementer: Codex.** Live Rekordbox → Govee LED bridge; audience-visible. Implement Part B
exactly. Do NOT edit `config/led_look_director.json`, do NOT restart/deploy the bridge. This touches
the **engine** (`beat_sync_engine.py`) and the **runner** (`govee_realtime_runner.py`) only.

---

## Part A — Goal & current behavior

**Operator's core requirement:** each beat crossing launches a comet; once launched, the comet's
travel is **completely free-running** — untied to the beat grid, `abs_beat_pos`, loops, or playback
state. Its travel duration is `travel_beats` evaluated at the **bpm at launch** (rate-locked), then it
glides on wall-clock to completion. **If you pause the track the instant a comet launches, that comet
must still travel all the way across the strip** before the strip goes dark.

**Two gaps today:**

1. **Not rate-locked.** `BeatSyncEngine._render_list(now, bpm)` and `_expire(now, bpm)` use the
   *live* bpm passed each tick, so an in-flight comet's speed tracks tempo changes instead of the
   bpm at launch.
2. **Pause kills in-flight comets.** On pause, `get_active_beat_anchor()` returns `None` (bails on
   `not playing`), so `GoveeRealtimeRunner._tick_once` hits `not permitted` → `_idle_tick`, which
   freezes the last frame and deactivates after the 0.25 s grace. The comet never advances again.

The animation clock is already monotonic wall-time (`local_t = now - born_monotonic`), so the fix is
to (a) stamp each instance with its launch bpm and animate/expire on that, and (b) keep animating
in-flight instances while unpermitted, only spawning on real beat crossings.

---

## Part B — Tasks (implement exactly)

### Engine — `beat_sync_engine.py`

**B1. `AnimInstance` gains `born_bpm`.**
Current:
```python
@dataclass
class AnimInstance:
    born_monotonic: float
    born_abs_beat: float
    bucket: int
```
Replacement:
```python
@dataclass
class AnimInstance:
    born_monotonic: float
    born_abs_beat: float
    bucket: int
    born_bpm: float       # bpm at launch; travel speed is locked to this, not the live bpm
```

**B2. `_make_instance` / `_spawn` stamp `born_bpm` (floored positive so an instance always expires).**
Current:
```python
    def _make_instance(self, now: float, abs_beat: float) -> AnimInstance:
        bucket = (self._seed ^ (self._spawn_seq * 2654435761)) & 0x7FFFFFFF
        self._spawn_seq += 1
        return AnimInstance(born_monotonic=float(now), born_abs_beat=float(abs_beat), bucket=bucket)

    def _spawn(self, now: float, abs_beat: float) -> None:
        self._instances.append(self._make_instance(now, abs_beat))
        self._spawn_count += 1
        if len(self._instances) > self._max_pulses:
            self._instances = self._instances[-self._max_pulses:]
```
Replacement:
```python
    def _make_instance(self, now: float, abs_beat: float, bpm: float) -> AnimInstance:
        bucket = (self._seed ^ (self._spawn_seq * 2654435761)) & 0x7FFFFFFF
        self._spawn_seq += 1
        return AnimInstance(
            born_monotonic=float(now), born_abs_beat=float(abs_beat),
            bucket=bucket, born_bpm=max(1.0, float(bpm)),
        )

    def _spawn(self, now: float, abs_beat: float, bpm: float) -> None:
        self._instances.append(self._make_instance(now, abs_beat, bpm))
        self._spawn_count += 1
        if len(self._instances) > self._max_pulses:
            self._instances = self._instances[-self._max_pulses:]
```

**B3. `configure` takes `bpm` and seeds the activation instance with it.**
Change the signature to add `bpm: float` and the final activation spawn:
```python
    def configure(self, *, effect_name: str, sync_mode: str, beat_division: float,
                  params: Mapping[str, Any], seed: int, now: float, abs_beat: float,
                  bpm: float) -> None:
        ...   # body unchanged up to the final spawn
        self._spawn(now, abs_beat, bpm)
```

**B4. `fire_manual` takes `bpm`.**
```python
    def fire_manual(self, now: float, abs_beat: float, bpm: float) -> None:
        if self._clock is None:
            return
        if self._mode == "overlap":
            self._spawn(now, abs_beat, bpm)
        else:
            self._instances = [self._make_instance(now, abs_beat, bpm)]
            self._spawn_count += 1
```

**B5. `on_tick` stamps spawns with the live bpm but renders/expires on each instance's `born_bpm`.**
```python
    def on_tick(self, abs_beat: float, now: float, bpm: float) -> list[InstanceRender]:
        if self._clock is None:
            return []
        spawn, wrapped = self._clock.advance(abs_beat)
        if self._mode == "overlap":
            for _ in range(spawn):
                self._spawn(now, abs_beat, bpm)
            self._expire(now)
        elif self._mode == "retrigger":
            if spawn > 0:
                self._instances = [self._make_instance(now, abs_beat, bpm)]
                self._spawn_count += 1
        elif self._mode == "continuous":
            if wrapped:
                self._instances = [self._make_instance(now, abs_beat, bpm)]
        return self._render_list(now)
```

**B6. `_expire` / `_render_list` use per-instance `born_bpm` and drop the `bpm` param.**
```python
    def _expire(self, now: float) -> None:
        ttl = self._travel_beats + self._trail_beats
        self._instances = [
            inst for inst in self._instances
            if (float(now) - inst.born_monotonic) * (inst.born_bpm / 60.0) <= ttl
        ]

    def _render_list(self, now: float) -> list[InstanceRender]:
        out: list[InstanceRender] = []
        for inst in self._instances:
            local_t = max(0.0, float(now) - inst.born_monotonic)
            local_beat = local_t * (inst.born_bpm / 60.0)
            out.append(InstanceRender(
                local_beat=local_beat,
                local_t=local_t,
                bucket=inst.bucket,
                progress=local_beat / self._travel_beats,
            ))
        return out
```

**B7. New `animate(now)` — advance + expire in-flight instances with no clock advance, no spawn.**
Add (used by the runner while playback is unpermitted/paused):
```python
    def animate(self, now: float) -> list[InstanceRender]:
        """Render in-flight instances on their own locked clock without advancing the
        trigger clock or spawning. Used when playback is paused/unpermitted so launched
        comets finish their flight, then naturally expire."""
        if self._clock is None:
            return []
        self._expire(now)
        return self._render_list(now)
```

### Runner — `govee_realtime_runner.py`

**B8. Pass `bpm` to `configure` and `fire_manual`.**
- In `_tick_once`, the `self._engine.configure(...)` call gains `bpm=float(anchor.bpm)`.
- The manual drain `self._engine.fire_manual(float(now), abs_pos)` becomes
  `self._engine.fire_manual(float(now), abs_pos, float(anchor.bpm))`.

**B9. Continue in-flight comets while unpermitted (the pause fix).**
Current:
```python
        if spec is None or not permitted:
            self._idle_tick(now)
            return
```
Replacement:
```python
        if spec is None:
            self._idle_tick(now)
            return
        if not permitted:
            # Paused / momentarily unpermitted: let any launched comet finish its flight
            # on its own locked clock (free-running, untied to the beat grid). No new
            # spawns while paused. When the last comet expires, fall through to idle.
            if self._active and self._engine.instance_count > 0:
                instances = self._engine.animate(float(now))
                frame = self._compose_frame(spec, instances)
                if self._emergency.is_set():
                    self._emergency_teardown()
                    return
                sent_ok = self._transport.send_frame(frame)
                self._last_frame = frame
                with self._lock:
                    self._last_error = "" if sent_ok else "transport_send_failed"
                    self._frame_index += 1
                    self._idle_since = None
                self._publish_engine_status(cleared=False)
                return
            self._idle_tick(now)
            return
```

No other runner changes. `_idle_tick`, `_emergency_teardown`, `force_deactivate`, the 0.25 s grace,
owner-lock, and `_signature`/reconfigure-on-deactivate logic stay exactly as-is.

---

## Part C — Invariants that MUST still hold (live safety)

1. **Emergency stop / `force_deactivate` / realtime→cloud handoff cut immediately** — the pause branch
   must not delay them (note the mid-tick `_emergency.is_set()` recheck is preserved above).
2. **No spawns while unpermitted** — `animate()` never advances the trigger clock; a paused track
   produces no new comets.
3. **Bounded** — every instance expires at `travel_beats + trail_beats` on its `born_bpm` (floored ≥1),
   so a paused strip always goes dark within one comet lifetime, then `_idle_tick` deactivates.
4. **Resume works** — after a full pause→dark→deactivate, `_active_signature` was reset to `None`, so
   the next permitted tick reconfigures and the beat-synced spawns resume. Don't change that path.
5. **Rate-lock** — a comet's progress depends only on `born_bpm`; a live bpm change mid-flight does
   not alter in-flight comets (only the next spawn picks up the new bpm).

---

## Part D — Tests

**`tests/test_beat_sync_engine.py`:**
- `born_bpm` stamped on spawn (overlap + retrigger + activation instance).
- **Rate-lock:** spawn at bpm=120; call `on_tick`/`animate` with later `now` (and a different live
  bpm passed to `on_tick`); assert the instance's `progress` matches the 120 launch rate, not the new
  bpm.
- **`animate` advances + expires:** spawn one instance; call `animate(now)` with increasing `now` and
  no `abs_beat`; assert `progress` rises and the instance is gone once
  `(now-born)*born_bpm/60 > travel+trail`. Assert `animate` never spawns (instance_count never rises).
- `animate` with no clock / no instances returns `[]`.

**`tests/test_govee_realtime_runner.py`** (reuse `_FakeTransport`/`_anchor`/`_tick_once`):
- **Pause continuation:** drive a few permitted ticks (overlap groove_chase) to launch a comet, then
  feed **unpermitted** ticks (anchor `playing=False` or `None`) with advancing `now`; assert
  `frame_index` keeps advancing, `active` stays `True`, the comet centroid keeps moving across the
  strip, and after one comet lifetime the instances reach 0 and it then deactivates (idle path).
- **Pause with no in-flight comet** → `_idle_tick`/deactivate immediately (no animate).
- **Emergency during pause** still blackouts + clears (`instance_count == 0`).
- **Resume after pause-to-dark** reconfigures and spawns on the next beat.
- Existing comet-routing / smoothness / manual-spam / teardown tests stay green.

Run `python3 -m unittest discover -s tests -p 'test*.py'` — all green.

---

## Part E — Acceptance

- Pause the track as a comet launches → that comet glides fully across and fades; strip then dark.
- Resume → comets relaunch on the beat. Tempo change mid-flight doesn't warp in-flight comets.
- Emergency/handoff still instant. No config edits. Engine/runner only.

## When you finish

Output a final `PASTE BACK TO CLAUDE` block: files changed + rationale; deviations; exact test
command + pass/fail; explicit confirmation that the 5 Part-C invariants hold; and a request for Claude
to review the pause branch (active/instance gating, idle fall-through), rate-lock correctness, the
`configure`/`fire_manual` bpm threading, and that emergency/teardown paths are untouched.
