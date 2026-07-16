"""Pad-process live-play mirror (AWR-269): tee at the transport boundary + ring.

Read-only mirror of what *this pad process* is sending. Bridge show output is
out of scope. The frame-runner thread may only O(1)-append an immutable
snapshot into a bounded deque — never lock with readers, never I/O.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable, Sequence

RGB = tuple[int, int, int]
MirrorEntry = tuple[float, tuple[RGB, ...]]

DEFAULT_MIRROR_RING_MAXLEN = 16


class FrameMirrorRing:
    """Newest-wins ring. ``append`` is O(1); drop-oldest by ``maxlen``."""

    def __init__(
        self,
        *,
        maxlen: int = DEFAULT_MIRROR_RING_MAXLEN,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        if int(maxlen) < 1:
            raise ValueError("maxlen must be >= 1")
        self._time_fn = time_fn or time.monotonic
        self._ring: deque[MirrorEntry] = deque(maxlen=int(maxlen))

    @property
    def maxlen(self) -> int:
        return int(self._ring.maxlen or 0)

    def __len__(self) -> int:
        return len(self._ring)

    def append(self, rgb_list: Sequence[Sequence[int]]) -> None:
        # Immutable snapshot; deque.append is thread-safe under the GIL.
        frame = tuple((int(r), int(g), int(b)) for r, g, b in rgb_list)
        self._ring.append((float(self._time_fn()), frame))

    def latest(self) -> MirrorEntry | None:
        if not self._ring:
            return None
        return self._ring[-1]

    def clear(self) -> None:
        self._ring.clear()


class TeeTransport:
    """Wraps a realtime transport; tees every ``send_frame`` into a mirror ring.

    Same surface as ``GoveeRealtimeTransport`` / dry-run: ``send_frame`` returns
    the wrapped result unchanged. All other methods delegate.
    """

    def __init__(self, wrapped: Any, ring: FrameMirrorRing) -> None:
        self._wrapped = wrapped
        self._ring = ring

    @property
    def wrapped(self) -> Any:
        return self._wrapped

    @property
    def ring(self) -> FrameMirrorRing:
        return self._ring

    def send_frame(self, rgb_list: Sequence[Sequence[int]]) -> bool:
        ok = bool(self._wrapped.send_frame(rgb_list))
        # Tee after the forward so a raise in the wrapped send is unchanged;
        # append itself must stay allocation-light and never raise into the caller
        # path beyond ordinary MemoryError (acceptable).
        self._ring.append(rgb_list)
        return ok

    def activate(self) -> bool:
        return bool(self._wrapped.activate())

    def deactivate(self) -> bool:
        return bool(self._wrapped.deactivate())

    def set_brightness(self, value: int) -> bool:
        return bool(self._wrapped.set_brightness(value))

    def blackout(self) -> bool:
        return bool(self._wrapped.blackout())

    def close(self) -> None:
        close = getattr(self._wrapped, "close", None)
        if callable(close):
            close()

    def status(self) -> dict[str, Any]:
        status = getattr(self._wrapped, "status", None)
        if callable(status):
            return dict(status())
        return {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)
