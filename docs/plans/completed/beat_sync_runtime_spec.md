---
doc_status: completed-spec
truth_level: code-grounded
last_verified_commit: fc56bb5
last_verified_date: 2026-07-03
validation_scope: spec only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Implementation Spec — Universal Beat-Sync Trigger Runtime (Govee Realtime LEDs)

Status: COMPLETED — landed; AWR-104 operator hardware sign-off 2026-06-29. Implementer: Composer 2.5. Reviewer: Claude.
Package: `rb_ss_bridge_v2` (tests import `from rb_ss_bridge_v2...`).
Live system — wrong behavior is visible to an audience. Implement exactly as written.

Revision note: the first beat-sync draft made `groove_chase_*` default to `overlap`. Live visual
feedback showed that regressed chase smoothness because it replaced the existing named
`_groove_chase()` / `_dual_chase()` scene with one-shot comets. This revision restores
`groove_chase_*` defaults to the continuous named renderer. `overlap` remains available only when
explicitly requested with `params.sync_mode="overlap"`.

---

## Part A — Context (read, do not implement)

Realtime LED effects today are pure functions of *absolute* beat position. In
`govee_realtime_runner.py:_tick_once`, `effect_beat = max(0.0, abs_beat_pos - _active_origin_beat)`;
`_active_origin_beat` is pinned at activation and reset only on effect-signature change. On a
Rekordbox beat-loop wrap, `abs_beat_pos` jumps backward, `effect_beat` clamps to 0, and the
animation **freezes**. The chase is also phase-offset from the downbeat, and manual cue re-fires
dedup by signature (so spamming a cue does nothing).

**Fix:** one **beat-division trigger clock** detects grid crossings from `abs_beat_pos`; spawned
animation **instances** animate on **monotonic wall-time × bpm**, never on `abs_beat_pos`, so loop
wraps cannot move them backward. Each effect resolves a `sync_mode`:

| mode | lifecycle | renders via | effects |
|---|---|---|---|
| `retrigger` | one instance, reborn each beat-division crossing AND manual fire | the **named** effect fn with `beat_pos=local_beat` | beat_chase, beat_strobe, drop_burst, color_pulse, bar_wipe, sparkle |
| `overlap` | spawn a new comet instance each crossing AND manual fire; many coexist; composite additively; expire past `travel_beats+trail_beats` | the **comet primitive** (NOT the named fn) | opt-in only for groove_chase_blue/cyan/red/green/cyan_white when `params.sync_mode="overlap"` |
| `continuous` | one long-lived instance; never re-spawn per crossing; re-anchor (restart local clock) only on backward wrap | the **named** effect fn with `beat_pos=local_beat` | groove_chase_blue/cyan/red/green/cyan_white plus everything else (solid, blackout, breathe, gradient_sweep, groove_freestyle_nebula, twinkle_blue, all buildup_*, all drop_chase_*) |

**Critical design point:** do not make `groove_chase_*` default to `overlap`. Normal groove chase
looks must keep using the registered `_groove_chase()` / `_dual_chase()` renderer because that is
the smoother live visual. `overlap` is an explicit experimental mode; when requested, it does NOT
call the registered `groove_chase` function. It renders each instance as a single **non-wrapping
comet** that travels the strip once and exits. `retrigger`/`continuous` reuse the existing pure
effect functions unchanged — only the `beat_pos`/`local_t` they receive changes.

Defaults (resolved in code by effect name; live JSON stays `params={}`): groove_chase
`beat_division=1.0`, `travel_beats=1.0` (used only when explicit overlap is selected),
`sync_mode=continuous`.

---

## Part B — Tasks (implement in order; commit after each)

### Absolute rules
- Follow this spec exactly. Use the shown code. Do not refactor beyond it, do not add features,
  do not add comments not shown.
- `GoveeFrameRenderer` effect functions stay **pure** — no new state inside them.
- **Concurrency model (load-bearing):** the `BeatSyncEngine` instance is touched **only on the
  runner's 30 fps thread** — i.e. inside `_tick_once`, `_compose_frame`, `_emergency_teardown`, and
  the `_idle_tick` deactivate branch. Event-thread paths (`fire_trigger`, `force_deactivate`, called
  from the StateManager/dispatch thread) must **never** call engine methods; they touch only
  lock-guarded primitives (`_pending_manual`, `_emergency`, `_desired_spec`, `_engine_status`).
  `status()` (status thread) reads a runner-published snapshot dict, never the engine directly.
- Do NOT edit `config/led_look_director.json`, do NOT commit/deploy/restart the bridge, do NOT
  enable anything live. Work on a branch only.
- If a `file:line` reference has drifted, locate by the quoted snippet / function name.
- All existing tests must stay green.

---

### Task 1 — New module `beat_sync_engine.py`

Create `/Users/bbui/rb_ss_bridge_v2/beat_sync_engine.py`:

```python
"""Beat-division trigger clock + animation-instance lifecycle for realtime LEDs.

Stateful; pure of transport and threads. The runner owns the lock and calls this
under it. Animation instances run on monotonic wall-time x bpm so they are immune
to Rekordbox loop wraps (abs_beat_pos jumping backward).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

MAX_PULSES = 16          # overlap: max concurrent comets
MAX_CATCHUP = 1          # max spawns per tick from a forward beat jump/seek
MAX_MANUAL_PENDING = 4   # max queued manual fires drained per tick

VALID_SYNC_MODES = frozenset({"retrigger", "overlap", "continuous"})
_EPS = 1e-6


@dataclass
class AnimInstance:
    born_monotonic: float
    born_abs_beat: float
    bucket: int


@dataclass(frozen=True)
class InstanceRender:
    local_beat: float
    local_t: float
    bucket: int
    progress: float   # local_beat / travel_beats; comet sweep position in [0, 1+trail]


class TriggerClock:
    """Detects beat-division boundary crossings and backward (wrap) jumps."""

    def __init__(self, division: float, *, spawn_on_wrap: bool = False) -> None:
        self.division = max(_EPS, float(division))
        self.spawn_on_wrap = bool(spawn_on_wrap)
        self._last_idx: int | None = None
        self._last_abs: float | None = None

    def seed(self, abs_beat: float) -> None:
        self._last_idx = math.floor(abs_beat / self.division)
        self._last_abs = float(abs_beat)

    def advance(self, abs_beat: float) -> tuple[int, bool]:
        """Return (spawn_count, wrapped). spawn_count is forward crossings capped at
        MAX_CATCHUP; wrapped is True when abs_beat moved backward."""
        abs_beat = float(abs_beat)
        idx = math.floor(abs_beat / self.division)
        if self._last_idx is None or self._last_abs is None:
            self._last_idx = idx
            self._last_abs = abs_beat
            return (0, False)
        wrapped = abs_beat < self._last_abs - _EPS
        spawn = 0
        if wrapped:
            self._last_idx = idx
            spawn = 1 if self.spawn_on_wrap else 0
        elif idx > self._last_idx:
            spawn = min(idx - self._last_idx, MAX_CATCHUP)
            self._last_idx = idx
        self._last_abs = abs_beat
        return (spawn, wrapped)


class BeatSyncEngine:
    def __init__(self) -> None:
        self._mode = "continuous"
        self._effect_name = ""
        self._seed = 0
        self._travel_beats = 1.0
        self._trail_beats = 0.25
        self._width = 0.8
        self._direction = 1
        self._max_pulses = MAX_PULSES
        self._clock: TriggerClock | None = None
        self._instances: list[AnimInstance] = []
        self._spawn_seq = 0
        self._spawn_count = 0

    # ── public read-only state (for runner status + render branch) ──
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def direction(self) -> int:
        return self._direction

    @property
    def division(self) -> float:
        return self._clock.division if self._clock is not None else 0.0

    @property
    def instance_count(self) -> int:
        return len(self._instances)

    @property
    def spawn_count(self) -> int:
        return self._spawn_count

    # ── lifecycle ──
    def configure(self, *, effect_name: str, sync_mode: str, beat_division: float,
                  params: Mapping[str, Any], seed: int, now: float, abs_beat: float) -> None:
        self._effect_name = str(effect_name)
        self._mode = sync_mode if sync_mode in VALID_SYNC_MODES else "continuous"
        self._seed = int(seed)
        self._travel_beats = max(1e-3, float(params.get("travel_beats", 1.0)))
        self._trail_beats = max(0.0, float(params.get("trail_beats", 0.25)))
        self._width = max(1e-3, float(params.get("width", 0.8)))
        self._direction = -1 if bool(params.get("reverse", False)) else 1
        self._max_pulses = min(MAX_PULSES, max(1, int(params.get("max_pulses", MAX_PULSES))))
        # spawn_on_wrap defaults TRUE so a loop wrap re-fires a trigger on the loop in-point
        # (the downbeat). Without it, the most important beat goes silent on every loop.
        self._clock = TriggerClock(beat_division, spawn_on_wrap=bool(params.get("spawn_on_wrap", True)))
        self._clock.seed(abs_beat)
        self._instances = []
        self._spawn_seq = 0
        # clock.seed() above set _last_idx to floor(abs_beat/division), so the first
        # on_tick() advance() returns spawn=0 for this same abs_beat -> no double-spawn.
        # This _spawn() is the single activation-frame instance.
        self._spawn(now, abs_beat)

    def reset(self) -> None:
        self._clock = None
        self._instances = []
        self._spawn_seq = 0

    def fire_manual(self, now: float, abs_beat: float) -> None:
        if self._clock is None:
            return
        if self._mode == "overlap":
            self._spawn(now, abs_beat)
        else:  # retrigger / continuous: manual fire restarts the single instance
            self._instances = [self._make_instance(now, abs_beat)]
            self._spawn_count += 1

    def on_tick(self, abs_beat: float, now: float, bpm: float) -> list[InstanceRender]:
        if self._clock is None:
            return []
        spawn, wrapped = self._clock.advance(abs_beat)
        if self._mode == "overlap":
            for _ in range(spawn):
                self._spawn(now, abs_beat)
            self._expire(now, bpm)
        elif self._mode == "retrigger":
            if spawn > 0:
                self._instances = [self._make_instance(now, abs_beat)]
                self._spawn_count += 1
        elif self._mode == "continuous":
            if wrapped:
                self._instances = [self._make_instance(now, abs_beat)]
        return self._render_list(now, bpm)

    # ── internals ──
    def _make_instance(self, now: float, abs_beat: float) -> AnimInstance:
        bucket = (self._seed ^ (self._spawn_seq * 2654435761)) & 0x7FFFFFFF
        self._spawn_seq += 1
        return AnimInstance(born_monotonic=float(now), born_abs_beat=float(abs_beat), bucket=bucket)

    def _spawn(self, now: float, abs_beat: float) -> None:
        self._instances.append(self._make_instance(now, abs_beat))
        self._spawn_count += 1
        if len(self._instances) > self._max_pulses:
            self._instances = self._instances[-self._max_pulses:]

    def _expire(self, now: float, bpm: float) -> None:
        ttl = self._travel_beats + self._trail_beats
        rate = max(0.0, float(bpm)) / 60.0
        self._instances = [
            inst for inst in self._instances
            if (now - inst.born_monotonic) * rate <= ttl
        ]

    def _render_list(self, now: float, bpm: float) -> list[InstanceRender]:
        rate = max(0.0, float(bpm)) / 60.0
        out: list[InstanceRender] = []
        for inst in self._instances:
            local_t = max(0.0, float(now) - inst.born_monotonic)
            local_beat = local_t * rate
            out.append(InstanceRender(
                local_beat=local_beat,
                local_t=local_t,
                bucket=inst.bucket,
                progress=local_beat / self._travel_beats,
            ))
        return out
```

Note: `heads` is accepted/validated in config (Task 2) for forward-compat but v1 spawns ONE comet
per trigger; do not implement multi-head yet.

---

### Task 2 — Config: permit + validate new params

**2a. `govee_frame_renderer.py`** — insert ALL of the following **immediately after line 609**
(after the `for _name in EDM_BUILDS:` loop has populated every entry). The union loop MUST run when
all entries already exist; if you run it before the `EDM_BUILDS` loop, the groove/buildup/drop
effects never get the sync keys and their looks fail to load.

```python
_SYNC_PARAM_KEYS = frozenset({
    "sync_mode", "beat_division", "travel_beats", "width",
    "trail_beats", "heads", "max_pulses", "spawn_on_wrap", "reverse",
})
for _k in list(REALTIME_EFFECT_PARAM_KEYS):
    REALTIME_EFFECT_PARAM_KEYS[_k] = REALTIME_EFFECT_PARAM_KEYS[_k] | _SYNC_PARAM_KEYS
# Allow explicit color override on the comet (overlap) chases.
for _k in ("groove_chase_blue", "groove_chase_cyan", "groove_chase_red",
           "groove_chase_green", "groove_chase_cyan_white"):
    REALTIME_EFFECT_PARAM_KEYS[_k] = REALTIME_EFFECT_PARAM_KEYS[_k] | frozenset({"color"})

_OVERLAP_EFFECTS = frozenset({
    "groove_chase_blue", "groove_chase_cyan", "groove_chase_red",
    "groove_chase_green", "groove_chase_cyan_white",
})
_RETRIGGER_EFFECTS = frozenset({
    "beat_chase", "beat_strobe", "drop_burst", "color_pulse", "bar_wipe", "sparkle",
})

def default_sync_mode(name: str) -> str:
    name = str(name)
    if name in _RETRIGGER_EFFECTS:
        return "retrigger"
    return "continuous"

def default_beat_division(name: str) -> float:
    return 1.0
```

**2b. `led_config.py:_validate_realtime_params`** — insert before the closing of the function
(after the unit-interval block at `:447-452`):

```python
    if "sync_mode" in params and params["sync_mode"] not in ("retrigger", "overlap", "continuous"):
        errors.append(f"{prefix} params.sync_mode must be one of [retrigger, overlap, continuous]")
    if "beat_division" in params:
        value = params["beat_division"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            errors.append(f"{prefix} params.beat_division must be a number > 0")
    if "trail_beats" in params:
        _validate_non_negative_number(f"{prefix} params.trail_beats", params["trail_beats"], errors)
    for field_name in ("travel_beats", "width"):  # divisors in the engine -> must be > 0
        if field_name in params:
            value = params[field_name]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                errors.append(f"{prefix} params.{field_name} must be a number > 0")
    for field_name in ("heads", "max_pulses"):
        if field_name in params:
            value = params[field_name]
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                errors.append(f"{prefix} params.{field_name} must be an integer >= 1")
    if "spawn_on_wrap" in params and not isinstance(params["spawn_on_wrap"], bool):
        errors.append(f"{prefix} params.spawn_on_wrap must be a boolean")
    if "reverse" in params and not isinstance(params["reverse"], bool):
        errors.append(f"{prefix} params.reverse must be a boolean")
```

(The generic whitelist at `led_config.py:360-363` already rejects keys not in
`REALTIME_EFFECT_PARAM_KEYS[scene_ref]`; 2a makes the new keys permitted.)

---

### Task 3 — Renderer: comet primitive + compose helpers

**`govee_frame_renderer.py`** — insert module-level `_comet_frame` immediately **before**
`def _dual_chase` (`:70`); it uses `_scale` (`:43`) and `math`, already available above that point:

```python
def _comet_frame(progress: float, segments: int, color: RGB, width: float, direction: int) -> Frame:
    """Single non-wrapping head sweeping the strip once. progress 0 -> 1 moves the head
    from one end to the other; past 1 it has exited (frame goes dark via distance falloff)."""
    if segments <= 0:
        return []
    if direction >= 0:
        pos = progress * segments
    else:
        pos = (1.0 - progress) * segments
    width = max(1.0, float(width))
    frame = [(0, 0, 0) for _ in range(segments)]

    # Normalize the sampled triangular kernel against virtual neighbors so the
    # head keeps steady energy while crossing between physical LED zones. At
    # the strip edges, out-of-range virtual samples remain excluded from the
    # actual frame, so the comet still fades in and out cleanly.
    radius = int(math.ceil(width)) + 1
    center = math.floor(pos)
    ideal_sum = 0.0
    for sample in range(center - radius, center + radius + 1):
        dist = abs(float(sample) - pos)
        ideal_sum += max(0.0, 1.0 - dist / width)
    if ideal_sum <= 0.0:
        return frame

    for idx in range(segments):
        dist = abs(float(idx) - pos)            # NOT ring-wrapped: comet exits the strip
        intensity = max(0.0, 1.0 - dist / width) / ideal_sum
        if intensity > 0.0:
            frame[idx] = _scale(color, intensity)
    return frame
```

Add three methods to `class GoveeFrameRenderer` (alongside `render`, `:615`):

```python
    def blank(self, segments: int) -> Frame:
        return _empty(max(0, int(segments)))

    def render_comet(self, name: str, *, progress: float, segments: int,
                     width: float, direction: int, params: Mapping[str, Any] | None) -> Frame:
        seg = max(0, int(segments))
        safe = params if isinstance(params, Mapping) else {}
        color = _color(safe.get("color"), _edm_color_for_look(str(name), 0.0)[0])
        frame = _comet_frame(float(progress), seg, color, float(width), int(direction))
        clamped = [(_clamp_channel(r), _clamp_channel(g), _clamp_channel(b)) for r, g, b in frame[:seg]]
        if len(clamped) < seg:
            clamped.extend([(0, 0, 0)] * (seg - len(clamped)))
        return clamped

    @staticmethod
    def fold_additive(frames: list[Frame], segments: int) -> Frame:
        seg = max(0, int(segments))
        acc = [[0, 0, 0] for _ in range(seg)]
        for f in frames:
            for i in range(min(seg, len(f))):
                acc[i][0] += f[i][0]; acc[i][1] += f[i][1]; acc[i][2] += f[i][2]
        return [(_clamp_channel(r), _clamp_channel(g), _clamp_channel(b)) for r, g, b in acc]
```

---

### Task 4 — `EffectSpec` + plumbing

**4a. `govee_realtime_runner.py:EffectSpec` (`:15-21`)** — add two keyword-defaulted fields:

```python
@dataclass(frozen=True)
class EffectSpec:
    effect_name: str
    params: Mapping[str, Any]
    seed: int
    applied_monotonic: float
    sync_mode: str = ""
    beat_division: float = 0.0
```

**4b. `govee_realtime_runner.py:_signature` (`:247-249`)** — fold the new fields in so an override
re-configures the engine:

```python
    def _signature(self, spec: EffectSpec) -> tuple[Any, ...]:
        params_key = tuple(sorted((str(k), repr(v)) for k, v in dict(spec.params).items()))
        return (str(spec.effect_name), params_key, int(spec.seed),
                str(spec.sync_mode), float(spec.beat_division))
```

**4c. `led_dispatch_coordinator.py:_spec_from_decision` (`:108-114`)** — resolve mode/division from
params with code defaults. Add the import at top:
`from .govee_frame_renderer import default_sync_mode, default_beat_division`.

```python
    def _spec_from_decision(self, decision: LEDLookDecision) -> EffectSpec:
        scene_ref = str(getattr(decision, "scene_ref", ""))
        params = dict(getattr(decision, "params", {}) or {})
        sync_mode = str(params.get("sync_mode") or default_sync_mode(scene_ref))
        beat_division = float(params.get("beat_division") or default_beat_division(scene_ref))
        return EffectSpec(
            effect_name=scene_ref,
            params=params,
            seed=_stable_seed(str(getattr(decision, "look", ""))),
            applied_monotonic=self._time_fn(),
            sync_mode=sync_mode,
            beat_division=beat_division,
        )
```

(The inline `tactical_blackout` `EffectSpec(...)` at `:70-75` keeps its keyword form; the two new
fields default, so it resolves to `sync_mode=""`/`beat_division=0.0` → runner falls back to
`default_sync_mode("blackout")`="continuous". No change needed there.)

---

### Task 5 — Runner: engine wiring, manual queue, tick branch, status, teardown

**5a. imports (`govee_realtime_runner.py:9`)** — extend:
`from .govee_frame_renderer import GoveeFrameRenderer`
add `from .beat_sync_engine import BeatSyncEngine, MAX_MANUAL_PENDING`
and `from .govee_frame_renderer import default_sync_mode, default_beat_division`.

**5b. `__init__` (`:26-58`)** — add after `self._renderer = renderer`:
```python
        self._engine = BeatSyncEngine()
        self._pending_manual = 0
        self._engine_status = {
            "sync_mode": "", "beat_division": 0.0,
            "instance_count": 0, "spawn_count": 0,
        }
```

**5c. new method `fire_trigger` (place after `set_desired`, `:68`)**:
```python
    def fire_trigger(self) -> None:
        with self._lock:
            self._pending_manual = min(self._pending_manual + 1, MAX_MANUAL_PENDING)
```

**5d. replace `_tick_once` (`:161-216`) entirely with:**
```python
    def _tick_once(self, anchor: BeatAnchor | None, now: float) -> None:
        if self._emergency.is_set():
            self._emergency_teardown()
            return

        with self._lock:
            spec = self._desired_spec

        permitted = bool(
            spec is not None
            and anchor is not None
            and anchor.permitted
            and anchor.playing
            and anchor.bpm > 0.0
        )
        if spec is None or not permitted:
            self._idle_tick(now)
            return

        assert anchor is not None
        abs_pos = float(anchor.abs_beat_pos) + (
            max(0.0, float(now) - float(anchor.captured_monotonic))
            * (float(anchor.bpm) / 60.0)
        )

        signature = self._signature(spec)
        if signature != self._active_signature:
            mode = spec.sync_mode or default_sync_mode(spec.effect_name)
            division = spec.beat_division if spec.beat_division > 0 else default_beat_division(spec.effect_name)
            with self._lock:
                self._active_signature = signature
                self._active_applied_monotonic = float(now)
                self._idle_since = None
            self._engine.configure(
                effect_name=spec.effect_name,
                sync_mode=mode,
                beat_division=division,
                params=spec.params,
                seed=spec.seed,
                now=float(now),
                abs_beat=abs_pos,
            )

        if not self._active:
            self._transport.activate()
            self._transport.set_brightness(100)
            with self._lock:
                self._active = True

        with self._lock:
            pending = self._pending_manual
            self._pending_manual = 0
        for _ in range(pending):
            self._engine.fire_manual(float(now), abs_pos)

        instances = self._engine.on_tick(abs_pos, float(now), float(anchor.bpm))
        frame = self._compose_frame(spec, instances)

        if self._emergency.is_set():
            self._emergency_teardown()
            return
        sent_ok = self._transport.send_frame(frame)
        self._last_frame = frame
        with self._lock:
            self._last_error = "" if sent_ok else "transport_send_failed"
            self._frame_index += 1
        self._publish_engine_status(cleared=False)

    def _compose_frame(self, spec: EffectSpec, instances: list) -> list[RGB]:
        # Runs on the runner thread; reading self._engine here is safe.
        segments = self._segments
        if not instances:
            return self._renderer.blank(segments)
        if self._engine.mode == "overlap":
            width = float(spec.params.get("width", 0.8))
            direction = self._engine.direction
            frames = [
                self._renderer.render_comet(
                    spec.effect_name,
                    progress=ir.progress,
                    segments=segments,
                    width=width,
                    direction=direction,
                    params=spec.params,
                )
                for ir in instances
            ]
            return self._renderer.fold_additive(frames, segments)
        ir = instances[0]
        return self._renderer.render(
            spec.effect_name,
            beat_pos=ir.local_beat,
            local_t=ir.local_t,
            frame_index=self._frame_index,
            params=spec.params,
            segments=segments,
            seed=spec.seed ^ ir.bucket,
        )

    def _publish_engine_status(self, *, cleared: bool) -> None:
        # Called ONLY from the runner thread. Publishes a lock-guarded snapshot that
        # status() (a different thread) reads, so status never touches the engine.
        if cleared:
            snap = {"sync_mode": "", "beat_division": 0.0,
                    "instance_count": 0, "spawn_count": self._engine.spawn_count}
        else:
            snap = {
                "sync_mode": self._engine.mode,
                "beat_division": self._engine.division,
                "instance_count": self._engine.instance_count,
                "spawn_count": self._engine.spawn_count,
            }
        with self._lock:
            self._engine_status = snap
```

**5e. `status` (`:117-143`)** — inside the existing `with self._lock:` block, read the published
snapshot and `_pending_manual` (do NOT touch `self._engine` here — it's owned by the runner thread):
```python
            engine_status = dict(self._engine_status)
            pending_manual = self._pending_manual
```
and merge into the returned dict: `**engine_status, "pending_manual": pending_manual,`.

**5f. teardown clears (runner-thread reset; event-thread only flips flags)** —
- `_emergency_teardown` (`:241-245`, runner thread): inside the `with self._lock:` add
  `self._pending_manual = 0`; then **after** the lock block call `self._engine.reset()` and
  `self._publish_engine_status(cleared=True)`.
- `_idle_tick` deactivate branch (`:227-231`, runner thread): after `self._active = False` inside
  the lock add `self._pending_manual = 0`; then after the lock call `self._engine.reset()` and
  `self._publish_engine_status(cleared=True)`.
- `force_deactivate` (`:73-94`, **event thread**): do NOT call `self._engine.reset()` here (it would
  race the runner thread). Inside the existing `with self._lock:` block add `self._pending_manual = 0`
  and `self._engine_status = {"sync_mode": "", "beat_division": 0.0, "instance_count": 0, "spawn_count": 0}`.
  The existing `self._emergency.set()` guarantees the runner thread runs `_emergency_teardown` on its
  next tick, which performs the actual `self._engine.reset()`. Status reads as cleared immediately.

---

### Task 6 — Coordinator: fire on manual realtime trigger

**`led_dispatch_coordinator.py:trigger` realtime branch (`:45-52`)** — after `set_desired(...)`:
```python
            self._runner.set_desired(self._spec_from_decision(decision))
            self._runner.fire_trigger()
            self._realtime_trigger_count += 1
            return True
```
This makes each manual cue fire spawn/retrigger an instance even though `set_desired` dedups by
signature. The beat-division auto-trigger inside the engine is the other source — same mechanism.

---

## Part C — Tests

### `tests/test_beat_sync_engine.py` (new) — pure engine, no transport
1. `test_overlap_division_spawns_once`: configure explicit overlap, division=1.0, travel=0.25; advance
   abs_beat 0→1 with two ticks (0.4, 1.1 beats) → exactly 1 *additional* spawn beyond the seed.
2. `test_wrap_no_freeze`: overlap; hold a comet alive; feed monotonically increasing `now` while
   abs_beat jumps 7.6→0.0 → the comet's `progress` (from `on_tick`) keeps increasing across the
   wrap (assert strictly greater after the wrap tick).
3. `test_wrap_no_flood`: abs_beat 0→1→2→0 → total spawns over the sequence ≤ seed + crossings,
   and the backward step adds 0 (or 1 if `spawn_on_wrap=True`), never the negative delta.
4. `test_forward_seek_capped`: abs_beat jumps 0→50 in one tick → ≤ MAX_CATCHUP spawns.
5. `test_retrigger_keeps_single_instance`: retrigger mode; many crossings → `instance_count == 1`.
6. `test_continuous_reanchors_on_wrap_only`: continuous; forward crossings do NOT change the
   instance (same `bucket`); a backward wrap replaces it (bucket changes, local_beat resets near 0).
7. `test_overlap_instance_cap`: spam crossings+manual → `instance_count <= MAX_PULSES`, oldest evicted.
8. `test_reset_clears`: populate, `reset()`, then `on_tick` returns `[]` until reconfigured.
9. `test_manual_fire_overlap_spawns`: overlap; `fire_manual` adds one instance without a crossing.
10. `test_bucket_stable_within_continuous_arc`: continuous; bucket constant across forward ticks.

### `tests/test_govee_realtime_runner.py` (extend) — reuse `_FakeTransport`, `_anchor`, `_tick_once`
- `test_overlap_no_freeze_across_backward_wrap` (**the freeze-fix proof, runner level**): set an
  explicit-overlap groove_chase spec; drive `_tick_once` with a sequence of anchors whose `abs_beat_pos`
  jumps backward (e.g. 7.5 → 0.0) while `now` advances monotonically; assert the composed
  `transport.frames[-1]` keeps changing across the wrap (not equal frame-to-frame, not all-dark) —
  i.e. the comet does not freeze. Construct anchors with distinct `captured_monotonic`/`now`.
- `test_manual_fire_trigger_spawns_without_signature_change`: set_desired same overlap spec twice +
  `fire_trigger()` → frames change / `status()["instance_count"]` grows (spam works).
- `test_groove_chase_default_uses_named_continuous_renderer`: with `sync_mode=""` and
  `beat_division=0.0`, `groove_chase_blue` resolves to `continuous`; its composed frame matches
  `GoveeFrameRenderer.render("groove_chase_blue", ...)` rather than `render_comet(...)`.
- `test_manual_spam_capped`: 100× `fire_trigger()` then one tick → bounded (no exception; pending
  drained to 0).
- `test_force_deactivate_clears_engine` and `test_emergency_teardown_clears_engine`:
  after teardown, `status()["instance_count"] == 0` (force_deactivate publishes cleared snapshot;
  emergency_teardown also physically resets the engine).
- Existing 4 tests (`solid`/unpermitted/zero-bpm/emergency) must pass unchanged — note `solid`
  resolves to `continuous`, single instance, frame identical to before.

### `tests/test_led_config.py` (extend) — this is where realtime-param validation is tested today
Mirror the existing tests `test_realtime_params_reject_unknown_keys`, `test_realtime_floor_param_above_one_is_rejected`, and `test_realtime_config_loads_and_preserves_backend_fields` (build config via `load_led_look_director_config_from_dict`, assert `.available` / `.errors`):
- New params accepted on every realtime effect (no load error).
- `sync_mode="bogus"` → error; `beat_division=0` → error; `travel_beats=0` → error;
  `width=0` → error; `max_pulses=0` → error; `spawn_on_wrap="yes"` → error; `reverse=1` → error.
- A look that loads the unmodified `config/led_look_director.json` (all `rt_*` `params={}`) still
  validates clean (back-compat regression).

### `tests/test_govee_frame_renderer.py` (extend)
- `test_groove_chase_defaults_to_continuous_named_scene`: `default_sync_mode("groove_chase_blue")`
  returns `"continuous"` so live JSON `params={}` preserves the old smooth chase.
- `test_comet_frame_exits_strip`: `render_comet` at `progress=1.5` returns an all-dark (or
  near-dark) frame; at `progress=0.0` lights the first segment.
- `test_fold_additive_clamps`: folding two bright frames clamps to ≤255 per channel.

---

## Part D — Acceptance (definition of done)

1. `python -m pytest tests/test_beat_sync_engine.py tests/test_govee_realtime_runner.py tests/test_led_config.py tests/test_govee_frame_renderer.py` — all green; full suite green.
2. Loading the unchanged live `config/led_look_director.json` produces no validation errors.
3. With a `BeatAnchor` whose `abs_beat_pos` is scripted to wrap backward, an overlap effect's
   composed frame keeps changing (no frozen pixels) across the wrap — covered by a runner test.
4. `solid`/`blackout`/existing continuous effects render the same pixels as before for a
   monotonic, non-wrapping anchor (no visual regression).
5. `groove_chase_*` with live JSON `params={}` resolves to `continuous` and renders through the
   existing named `_groove_chase()` path; `overlap` is used only when explicitly requested.
6. `force_deactivate` / `_emergency_teardown` leave `instance_count == 0` and `pending_manual == 0`.

Out of scope for v1 (do not implement): multi-head comets (`heads>1` validated but treated as 1),
per-instance bpm rate-lock, downbeat phase fine-tuning.

Known/accepted limitations (do not "fix" — these are intentional):
- `retrigger` effects compute phase from a per-frame `local_beat` (reset each beat-division), so a
  strobe's sub-beat phase may drift up to one frame (~33 ms at 30 fps) from the grid. Acceptable.
- On a large backward/forward seek (not a clean loop wrap), `MAX_CATCHUP=1` means only one comet
  spawns; with a very small `beat_division` this can leave a visible gap until the grid re-aligns.
  Intentional flood-guard.
- Strobe safety is unchanged: `beat_strobe` stays in `REALTIME_STROBE_EFFECTS`; the existing
  `allow_strobe` / `safety.allow_strobe` cross-checks (`led_config.py:489-493`) still gate it.
