"""Pure CH1-CH19 renderer and controller for verified SoundSwitch packs.

This module owns no threads and performs no I/O.  Every transport/phase query
replays immutable events, so seeks, back-seeks, pause/resume, refires, mask
release, and override release never depend on a cached output frame.
"""
from __future__ import annotations

from dataclasses import dataclass
import uuid
from typing import Literal, Mapping, Sequence

from .soundswitch_midi_input import LayerEntry
from .soundswitch_pack_loader import (
    LoadedAttribute,
    LoadedAutoloop,
    LoadedDocument,
    LoadedPack,
    LoadedScriptedTrack,
    LoadedStaticLook,
)

CHANNEL_COUNT = 19
PRIMARY_FIXTURE_GROUP = 0x493
CONTROL_CHANNELS = frozenset((8, 9, 11))
SUPPORTED_LAYOUTS = frozenset((
    "shared_441_dictionary_timeline",
    "dictionary_timeline_addressed_footer",
    "dictionary_timeline_no_shared_anchor",
))
UNVERIFIED_PARITY_LANE = "unverified_parity"
ZERO_FRAME = (0,) * CHANNEL_COUNT


@dataclass(frozen=True, slots=True)
class PlayerDiagnostic:
    code: str
    message: str
    context: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class PlayerResult:
    frame: tuple[int, ...]
    diagnostic: PlayerDiagnostic | None = None


@dataclass(frozen=True, slots=True)
class LayerApplyResult:
    frame: tuple[int, ...]
    diagnostic: PlayerDiagnostic | None = None


@dataclass(frozen=True, slots=True)
class _ScriptedSelection:
    soundswitch_id: str | None
    elapsed_ms: int
    transport: str
    metadata_ready: bool
    authority: str
    source_errored: bool
    elapsed_discontinuous: bool
    track_changed: bool


@dataclass(frozen=True, slots=True)
class _AutoloopSelection:
    identity: str
    phase_tick: int | None
    authority: str


def _diagnostic(code: str, message: str, **context: object) -> PlayerResult:
    return PlayerResult(ZERO_FRAME, PlayerDiagnostic(
        code, message, tuple(sorted((key, str(value)) for key, value in context.items()))))


def parity_live_blocks_document(document: LoadedDocument, parity_live: bool) -> bool:
    """True when an unverified document must not drive trusted parity-live output."""
    if type(parity_live) is not bool:
        raise ValueError("parity_live must be boolean")
    return bool(parity_live and document.parity_lane == UNVERIFIED_PARITY_LANE)


def _validate_frame(frame: tuple[int, ...], label: str) -> tuple[int, ...]:
    if len(frame) != CHANNEL_COUNT or any(
            type(value) is not int or not 0 <= value <= 255 for value in frame):
        raise ValueError(f"{label} must contain exactly 19 integers in 0..255")
    return frame


def _apply_attribute(frame: list[int], row: LoadedAttribute) -> None:
    if row.fixture_group != PRIMARY_FIXTURE_GROUP:
        return
    if not 1 <= row.dmx_channel <= CHANNEL_COUNT or not 0 <= row.value <= 255:
        raise ValueError("loaded cue attribute is outside CH1-CH19/byte range")
    frame[row.dmx_channel - 1] = row.value


def _apply_events(document: LoadedDocument, initial: tuple[int, ...], predicate) -> tuple[int, ...]:
    frame = list(_validate_frame(initial, "initial frame"))
    # SoundSwitch's cue cache is cumulative in *serialized* order (saved order),
    # which the loader preserves.  Saved order is not always time-monotonic —
    # {528E8B22} serializes 60065 before 60064 and U0 proves the later-serialized
    # event wins — so events must never be re-sorted by timestamp here.
    for event in document.events:
        if not predicate(event.time):
            continue
        if event.reference_kind == "clear_control":
            frame = [value if channel in CONTROL_CHANNELS else 0
                     for channel, value in enumerate(frame, 1)]
        elif event.reference_kind == "cue":
            for attribute in event.patch:
                _apply_attribute(frame, attribute)
        else:  # Frozen loader currently prevents this; fail closed if constructed manually.
            raise ValueError(f"unsupported reference kind {event.reference_kind!r}")
    return tuple(frame)


def _valid_channel_byte(value: object) -> bool:
    return type(value) is int and 0 <= value <= 255


def _merge_color_snapshot(frame: tuple[int, ...], snapshot: object | None) -> tuple[int, ...]:
    """Overwrite CH8/CH9 independently; a channel with no valid byte is left authored.

    ``snapshot.ch9`` may be ``None`` (e.g. white moments preserve authored speed;
    a null ``fixed_ch9`` config leaves the quantized-color path's CH9 untouched).
    An absent/invalid snapshot injects nothing on either channel.
    """
    if snapshot is None:
        return frame
    ch8 = getattr(snapshot, "ch8", None)
    ch9 = getattr(snapshot, "ch9", None)
    if not _valid_channel_byte(ch8) and not _valid_channel_byte(ch9):
        return frame
    merged = list(frame)
    if _valid_channel_byte(ch8):
        merged[7] = ch8
    if _valid_channel_byte(ch9):
        merged[8] = ch9
    return tuple(merged)


def render_scripted_frame(track: LoadedDocument | LoadedScriptedTrack, elapsed_ms: int) -> tuple[int, ...]:
    """Render a scripted track at authoritative integer milliseconds."""
    if type(elapsed_ms) is not int or elapsed_ms < 0:
        raise ValueError("elapsed_ms must be a non-negative integer")
    if isinstance(track, LoadedScriptedTrack):
        if not track.supported_active or track.document is None:
            return ZERO_FRAME
        document = track.document
    else:
        document = track
    if document.layout not in SUPPORTED_LAYOUTS:
        return ZERO_FRAME
    if document.events and all(event.boundary_frame is not None for event in document.events):
        # SoundSwitch's cache is cumulative in *serialized* order, and playback
        # holds the entry with the greatest serialized index whose time has
        # arrived — NOT the latest by timestamp.  Two cues authored ~1ms apart
        # (e.g. {528E8B22} at 60065 then 60064) resolve to the later-serialized
        # one even though its timestamp is earlier, so select by saved order and
        # never break early (saved order is not time-monotonic).
        frame = ZERO_FRAME
        for event in document.events:
            if event.time <= elapsed_ms:
                frame = event.boundary_frame or frame
        return frame
    return _apply_events(document, ZERO_FRAME, lambda time: 0 <= time <= elapsed_ms)


def render_autoloop_frame(loop: LoadedDocument | LoadedAutoloop,
                          phase_tick: int) -> tuple[int, ...]:
    """Render an Autoloop at an authoritative bridge beat/phrase tick.

    The current verified profile uses a 19,200-tick cycle.  Each cycle starts
    from zero, applies signed negative pre-roll, then applies events through
    the wrapped phase.
    """
    if type(phase_tick) is not int or phase_tick < 0:
        raise ValueError("phase_tick must be a non-negative integer")
    if isinstance(loop, LoadedAutoloop):
        if not loop.supported_active:
            return ZERO_FRAME
        loop = loop.document
    if loop.layout not in SUPPORTED_LAYOUTS:
        return ZERO_FRAME
    if type(loop.cycle_ticks) is not int or loop.cycle_ticks <= 0:
        raise ValueError("Autoloop cycle_ticks must be a positive integer")
    wrapped = phase_tick % loop.cycle_ticks
    return _apply_events(loop, ZERO_FRAME, lambda time: time < 0 or 0 <= time <= wrapped)


def _layer_diagnostic(skipped_count: int, skipped_slots: list[int]) -> PlayerDiagnostic | None:
    if skipped_count == 0:
        return None
    context = (("skipped_count", str(skipped_count)),)
    if skipped_slots:
        context += (("slots", ",".join(str(slot) for slot in skipped_slots)),)
    return PlayerDiagnostic(
        "static_layers_skipped",
        "one or more Static Look layers were skipped",
        context,
    )


def _layer_slot(layer: object) -> int | None:
    slot = getattr(layer, "slot", None)
    kind = getattr(layer, "kind", None)
    seq = getattr(layer, "seq", None)
    if type(slot) is not int or kind not in ("toggle", "press") or type(seq) is not int:
        return None
    return slot


def apply_layers(
    base: tuple[int, ...],
    layers: Sequence[LayerEntry],
    static_looks: Mapping[int, LoadedStaticLook],
    blackout: bool,
    emergency: bool,
) -> LayerApplyResult:
    """Apply sparse Static Look layers over a valid base frame, bottom to top."""
    base = _validate_frame(base, "base frame")
    if type(blackout) is not bool or type(emergency) is not bool:
        raise ValueError("blackout and emergency must be booleans")
    if emergency or blackout:
        return LayerApplyResult(ZERO_FRAME)
    frame = list(base)
    skipped = 0
    skipped_slots: list[int] = []
    for layer in tuple(layers):
        slot = _layer_slot(layer)
        if slot is None:
            skipped += 1
            continue
        look = static_looks.get(slot)
        if look is None or look.profile_has_intensity_channel:
            skipped += 1
            skipped_slots.append(slot)
            continue
        candidate = list(frame)
        try:
            for attribute in look.generic_attributes:
                _apply_attribute(candidate, attribute)
        except (TypeError, ValueError):
            skipped += 1
            skipped_slots.append(slot)
            continue
        frame = candidate
    return LayerApplyResult(tuple(frame), _layer_diagnostic(skipped, skipped_slots))


def normalize_soundswitch_id(value: str | None) -> str | None:
    """Normalize only an exact UUID identity; never inspect/fuzzy-match paths."""
    if not isinstance(value, str) or not value:
        return None
    candidate = value[1:-1] if value.startswith("{") and value.endswith("}") else value
    try:
        parsed = uuid.UUID(candidate)
    except (ValueError, AttributeError):
        return None
    if str(parsed) != candidate.lower():
        return None
    return str(parsed)


class LaserPackPlayer:
    """Small pure state controller around an already verified immutable pack."""

    def __init__(self, pack: LoadedPack, *, parity_live: bool = False):
        if type(parity_live) is not bool:
            raise ValueError("parity_live must be boolean")
        self._pack = pack
        self._parity_live = parity_live
        self._selection: _ScriptedSelection | _AutoloopSelection | None = None
        self._static_layers: tuple[LayerEntry, ...] = ()
        self._blackout = False
        self._emergency = False
        self._waiting_after_reload = False
        self._color_snapshot = None
        self._base_suppressed = False

    @property
    def pack(self) -> LoadedPack:
        return self._pack

    @property
    def parity_live(self) -> bool:
        return self._parity_live

    @property
    def static_layers(self) -> tuple[LayerEntry, ...]:
        return self._static_layers

    @property
    def blackout(self) -> bool:
        return self._blackout

    @property
    def emergency(self) -> bool:
        return self._emergency

    def reload(self, pack: LoadedPack) -> PlayerResult:
        self._pack = pack
        self._selection = None
        self._static_layers = ()
        self._blackout = False
        self._emergency = False
        self._waiting_after_reload = True
        return _diagnostic("reload_waiting_authority",
                           "pack reloaded; waiting for fresh authoritative state")

    def select_scripted(
        self, soundswitch_id: str | None, elapsed_ms: int, *,
        transport: Literal["playing", "paused", "stopped", "ended", "unloaded"] = "playing",
        metadata_ready: bool = True, authority: Literal["fresh", "stale", "ambiguous"] = "fresh",
        source_errored: bool = False,
        elapsed_discontinuous: bool = False, track_changed: bool = False,
    ) -> PlayerResult:
        self._selection = _ScriptedSelection(
            soundswitch_id, elapsed_ms, transport, metadata_ready, authority,
            source_errored, elapsed_discontinuous, track_changed)
        self._waiting_after_reload = False
        return self.render()

    def select_autoloop(
        self, identity: str, phase_tick: int | None, *,
        authority: Literal["fresh", "stale", "ambiguous"] = "fresh",
    ) -> PlayerResult:
        self._selection = _AutoloopSelection(identity, phase_tick, authority)
        self._waiting_after_reload = False
        return self.render()

    def set_static_layers(self, layers: Sequence[LayerEntry]) -> PlayerResult:
        self._static_layers = tuple(layers)
        return self.render()

    def clear_selection(self) -> PlayerResult:
        """Clear the automatic scripted/autoloop base WITHOUT touching held static or masks.

        ``render()`` then yields a ``missing_selection`` base (ZERO), so a held Static
        Override stands alone — matching SoundSwitch showing a manual Static Look while
        no track is playing.  Static still loses to blackout/emergency and to the
        post-reload wait latch (both checked before static in ``render()``).
        """
        self._selection = None
        return self.render()

    def set_color_snapshot(self, snapshot: object | None) -> None:
        self._color_snapshot = snapshot

    def set_base_suppressed(self, held: bool) -> PlayerResult:
        """Drop presentation `leds_only`: withhold the automatic base WITHOUT
        clearing ``_selection`` — the drop keeps rendering the instant
        suppression lifts. Mirrors ``clear_selection()``'s ZERO-base/held-static-
        stands-alone shape (render() below), but is a distinct diagnostic code
        so it is indistinguishable from "no drop autoloop selected" to anything
        downstream while still being observable. Never touches blackout/
        emergency state — suppression is not blackout (authority rule)."""
        if type(held) is not bool:
            return _diagnostic("invalid_mask_state", "base suppression state must be boolean")
        self._base_suppressed = held
        return self.render()

    def set_blackout(self, held: bool) -> PlayerResult:
        return self.set_masks(blackout=held, emergency=self._emergency)

    def set_emergency(self, held: bool) -> PlayerResult:
        return self.set_masks(blackout=self._blackout, emergency=held)

    def set_masks(self, *, blackout: bool, emergency: bool) -> PlayerResult:
        if type(blackout) is not bool or type(emergency) is not bool:
            return _diagnostic("invalid_mask_state", "mask state must be boolean")
        self._blackout = blackout
        self._emergency = emergency
        return self.render()

    def _scripted_base(self, selection: _ScriptedSelection) -> PlayerResult:
        if selection.transport in ("stopped", "ended", "unloaded"):
            return _diagnostic(f"transport_{selection.transport}",
                               "scripted transport is idle", transport=selection.transport)
        if selection.transport not in ("playing", "paused"):
            return _diagnostic("unsupported_transport", "unsupported scripted transport")
        if selection.authority not in ("fresh", "stale", "ambiguous"):
            return _diagnostic("unsupported_authority", "unsupported active-deck authority")
        if type(selection.metadata_ready) is not bool or type(selection.source_errored) is not bool \
                or type(selection.elapsed_discontinuous) is not bool \
                or type(selection.track_changed) is not bool:
            return _diagnostic("invalid_source_state", "scripted source flags must be boolean")
        normalized = normalize_soundswitch_id(selection.soundswitch_id)
        if normalized is None:
            return _diagnostic("missing_identity", "valid normalized soundswitch_id is required")
        if not selection.metadata_ready:
            return _diagnostic("metadata_not_ready", "track metadata is not ready")
        if selection.source_errored:
            return _diagnostic("source_error", "scripted source reported an error")
        if selection.track_changed:
            return _diagnostic("track_change", "track identity changed; await fresh state")
        if selection.elapsed_discontinuous:
            return _diagnostic("elapsed_discontinuity", "elapsed authority reported a discontinuity")
        if selection.authority == "stale":
            return _diagnostic("stale_authority", "active-deck authority is stale")
        if selection.authority == "ambiguous":
            return _diagnostic("ambiguous_authority", "active-deck authority is ambiguous")
        track = self._pack.scripted.get(normalized)
        if track is None:
            return _diagnostic("scripted_not_found", "no scripted pack row matches soundswitch_id",
                               soundswitch_id=normalized)
        if isinstance(track, LoadedScriptedTrack):
            if not track.supported_active or track.document is None:
                return _diagnostic("unsupported_scripted", "scripted row is inactive or unsupported",
                                   soundswitch_id=normalized)
            document = track.document
        else:  # Supports narrow synthetic tests while retaining immutable semantics.
            document = track
        if document.layout not in SUPPORTED_LAYOUTS:
            return _diagnostic("unsupported_layout", "active scripted layout is unsupported",
                               layout=document.layout)
        if parity_live_blocks_document(document, self._parity_live):
            return _diagnostic(
                "unverified_parity",
                "unverified scripted document cannot drive parity-live output",
                kind="scripted",
            )
        try:
            return PlayerResult(render_scripted_frame(document, selection.elapsed_ms))
        except (TypeError, ValueError) as exc:
            return _diagnostic("player_error", type(exc).__name__)

    def _autoloop_base(self, selection: _AutoloopSelection) -> PlayerResult:
        if selection.authority not in ("fresh", "stale", "ambiguous"):
            return _diagnostic("unsupported_authority", "unsupported beat/phrase authority")
        if selection.authority == "stale":
            return _diagnostic("stale_authority", "beat/phrase authority is stale")
        if selection.authority == "ambiguous":
            return _diagnostic("ambiguous_authority", "beat/phrase authority is ambiguous")
        if selection.phase_tick is None:
            return _diagnostic("missing_phase", "authoritative Autoloop phase is missing")
        loop = self._pack.autoloops.get(selection.identity)
        if loop is None:
            return _diagnostic("autoloop_not_found", "Autoloop identity is absent",
                               identity=selection.identity)
        if isinstance(loop, LoadedAutoloop):
            if not loop.supported_active:
                return _diagnostic("inactive_autoloop", "Autoloop is retained but not active",
                                   identity=selection.identity)
            document = loop.document
        else:
            document = loop
        if document.layout not in SUPPORTED_LAYOUTS:
            return _diagnostic("unsupported_layout", "active Autoloop layout is unsupported",
                               layout=document.layout)
        if parity_live_blocks_document(document, self._parity_live):
            return _diagnostic(
                "unverified_parity",
                "unverified Autoloop document cannot drive parity-live output",
                kind="autoloop",
            )
        try:
            frame = render_autoloop_frame(document, selection.phase_tick)
            return PlayerResult(_merge_color_snapshot(frame, self._color_snapshot))
        except (TypeError, ValueError) as exc:
            return _diagnostic("player_error", type(exc).__name__)

    def render(self) -> PlayerResult:
        if self._emergency or self._blackout:
            return PlayerResult(ZERO_FRAME)
        if self._waiting_after_reload:
            return _diagnostic("reload_waiting_authority",
                               "pack reloaded; waiting for fresh authoritative state")
        if self._base_suppressed:
            # Drop presentation `leds_only`: withhold the base exactly like
            # missing_selection, WITHOUT consulting/clearing `_selection` — the
            # drop keeps rendering the instant suppression lifts.
            base = PlayerResult(ZERO_FRAME, PlayerDiagnostic(
                "base_suppressed", "laser base withheld by drop presentation policy"))
        elif self._selection is None:
            base = PlayerResult(ZERO_FRAME, PlayerDiagnostic(
                "missing_selection", "no authoritative pack selection is active"))
        elif isinstance(self._selection, _ScriptedSelection):
            base = self._scripted_base(self._selection)
        else:
            base = self._autoloop_base(self._selection)

        # A manual Static Override may stand alone when no base selection is
        # active, but it must never bypass a known stop/stale/error condition.
        if (
            base.diagnostic is not None
            and base.diagnostic.code not in ("missing_selection", "unverified_parity", "base_suppressed")
        ):
            return base
        if self._static_layers:
            try:
                layered = apply_layers(
                    base.frame, self._static_layers, self._pack.static_looks,
                    self._blackout, self._emergency,
                )
                diagnostic = (
                    base.diagnostic
                    if base.diagnostic is not None and base.diagnostic.code == "unverified_parity"
                    else layered.diagnostic
                )
                return PlayerResult(layered.frame, diagnostic)
            except (TypeError, ValueError) as exc:
                return _diagnostic("player_error", type(exc).__name__)
        return base


__all__ = [
    "CHANNEL_COUNT", "CONTROL_CHANNELS", "LayerApplyResult", "LaserPackPlayer", "PlayerDiagnostic",
    "PlayerResult", "UNVERIFIED_PARITY_LANE", "ZERO_FRAME", "normalize_soundswitch_id",
    "parity_live_blocks_document", "render_autoloop_frame", "render_scripted_frame",
    "apply_layers",
]
