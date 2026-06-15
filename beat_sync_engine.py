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
    born_bpm: float       # bpm at launch; travel speed is locked to this, not the live bpm


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
                  params: Mapping[str, Any], seed: int, now: float, abs_beat: float,
                  bpm: float) -> None:
        self._effect_name = str(effect_name)
        self._mode = sync_mode if sync_mode in VALID_SYNC_MODES else "continuous"
        self._seed = int(seed)
        self._travel_beats = max(1e-3, float(params.get("travel_beats", 1.0)))
        self._trail_beats = max(0.0, float(params.get("trail_beats", 0.25)))
        self._width = max(1e-3, float(params.get("width", 0.8)))
        self._direction = -1 if bool(params.get("reverse", False)) else 1
        self._max_pulses = min(MAX_PULSES, max(1, int(params.get("max_pulses", MAX_PULSES))))
        self._clock = TriggerClock(beat_division, spawn_on_wrap=bool(params.get("spawn_on_wrap", True)))
        self._clock.seed(abs_beat)
        self._instances = []
        self._spawn_seq = 0
        # clock.seed() above set _last_idx to floor(abs_beat/division), so the first
        # on_tick() advance() returns spawn=0 for this same abs_beat -> no double-spawn.
        # This _spawn() is the single activation-frame instance.
        self._spawn(now, abs_beat, bpm)

    def reset(self) -> None:
        self._clock = None
        self._instances = []
        self._spawn_seq = 0

    def fire_manual(self, now: float, abs_beat: float, bpm: float) -> None:
        if self._clock is None:
            return
        if self._mode == "overlap":
            self._spawn(now, abs_beat, bpm)
        else:  # retrigger / continuous: manual fire restarts the single instance
            self._instances = [self._make_instance(now, abs_beat, bpm)]
            self._spawn_count += 1

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

    def animate(self, now: float) -> list[InstanceRender]:
        """Render in-flight instances on their own locked clock without advancing the
        trigger clock or spawning. Used when playback is paused/unpermitted so launched
        comets finish their flight, then naturally expire."""
        if self._clock is None:
            return []
        self._expire(now)
        return self._render_list(now)

    # ── internals ──
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
