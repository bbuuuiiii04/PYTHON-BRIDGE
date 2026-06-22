#!/usr/bin/env python3
"""Task 8 — offline shadow-mode proof for the SoundSwitch pack player.

Drives a verified ``LaserPackPlayer`` through deterministic transition scenarios
with the PHYSICAL output backend forced to ``none`` (no MIDI / serial / DMX is ever
opened or transmitted), recording ONLY per-step frame SHA-256 hashes — never raw
channel values, audio/file paths, SoundSwitch identities, or device names. Each
shadow hash is compared against an INDEPENDENTLY supplied expected frame so any
regression in the player's transition / precedence logic fails closed.

Status: SOFTWARE / OFFLINE ONLY — HARDWARE-UNVALIDATED. This tool opens no device,
sends no output, restarts no bridge, and must never be cited as hardware or show
validation. Single-process: it constructs a throwaway player and exits; there is no
state to roll back (no files written, no devices touched).

Autoloop runtime-phase shadow coverage is DEFERRED — the bridge has no proven T7d
beat-to-animation phase origin yet.  Pure autoloop rendering with an explicitly
supplied ``phase_tick`` is already covered by ``test_soundswitch_laser_player.py``.
The report records only the runtime-integration deferral explicitly
(``autoloop_coverage`` / ``categories_covered``) so that gap is never silent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from rb_ss_bridge_v2.laser_output_backend import NoneBackend  # noqa: E402
from rb_ss_bridge_v2.soundswitch_laser_player import (  # noqa: E402
    CHANNEL_COUNT,
    ZERO_FRAME,
    LaserPackPlayer,
    PlayerResult,
)

# Physical output backends permitted under shadow mode (no device, no transmit).
_ALLOWED_BACKENDS = frozenset(("none", "pack"))
_AUTOLOOP_DEFERRED = "deferred_t7d_phase_origin"


def frame_sha256(frame: tuple[int, ...]) -> str:
    """SHA-256 of a validated CH1-CH19 frame; raises on a malformed frame."""
    if len(frame) != CHANNEL_COUNT or any(
            type(value) is not int or not 0 <= value <= 255 for value in frame):
        raise ValueError("frame must contain exactly 19 integers in 0..255")
    return hashlib.sha256(bytes(frame)).hexdigest()


@dataclass(frozen=True)
class ShadowAction:
    """One scenario step: a sanitized label, category, the player call, and the
    INDEPENDENTLY computed expected frame to compare the player output against."""
    label: str
    category: str
    run: Callable[[LaserPackPlayer], PlayerResult]
    expected_frame: tuple[int, ...]


@dataclass(frozen=True)
class ShadowStep:
    label: str
    category: str
    diagnostic_code: str | None
    frame_sha256: str
    expected_sha256: str
    matches: bool


@dataclass(frozen=True)
class ShadowReport:
    steps: tuple[ShadowStep, ...]
    backend: str
    physical_output: bool
    categories_covered: tuple[str, ...]
    autoloop_coverage: str = _AUTOLOOP_DEFERRED
    hardware_validated: bool = False

    @property
    def all_match(self) -> bool:
        return all(step.matches for step in self.steps)

    def to_dict(self) -> dict:
        """Sanitized report: hashes + categories only, never raw frames/paths/ids."""
        return {
            "status": "software_offline_only_hardware_unvalidated",
            "backend": self.backend,
            "physical_output": self.physical_output,
            "hardware_validated": self.hardware_validated,
            "all_match": self.all_match,
            "categories_covered": list(self.categories_covered),
            "autoloop_coverage": self.autoloop_coverage,
            "autoloop_coverage_note": (
                "autoloop runtime-phase shadow coverage deferred — gated on the T7d "
                "phase-origin proof; pure rendering with an explicit phase_tick is "
                "covered separately; this harness covers scripted/static/blackout"),
            "steps": [
                {
                    "label": step.label,
                    "category": step.category,
                    "diagnostic_code": step.diagnostic_code,
                    "frame_sha256": step.frame_sha256,
                    "expected_sha256": step.expected_sha256,
                    "matches": step.matches,
                }
                for step in self.steps
            ],
        }


def run_shadow(player: LaserPackPlayer, actions, *, backend) -> ShadowReport:
    """Replay ``actions`` against ``player``, hashing each emitted frame and the
    independently expected frame.  ``backend`` must be a physical-none backend
    (``none`` or ``pack`` with NO frame sender) — a backend that could transmit is
    rejected so shadow mode can never reach hardware."""
    status = backend.status()
    name = str(status.get("backend", "unknown"))
    if name not in _ALLOWED_BACKENDS:
        raise ValueError(f"shadow mode requires a physical-none backend, got {name!r}")
    if status.get("has_frame_sender"):
        raise ValueError("shadow mode forbids a physical frame sender")

    steps: list[ShadowStep] = []
    covered: list[str] = []
    for action in actions:
        result = action.run(player)
        # Route through the (none) backend exactly as the live path would; the
        # backend transmits nothing — we only observe the hash.
        backend.submit_frame(result.frame)
        shadow = frame_sha256(result.frame)
        expected = frame_sha256(action.expected_frame)
        code = result.diagnostic.code if result.diagnostic is not None else None
        steps.append(ShadowStep(action.label, action.category, code,
                                shadow, expected, shadow == expected))
        if action.category not in covered:
            covered.append(action.category)
    return ShadowReport(tuple(steps), backend=name, physical_output=False,
                        categories_covered=tuple(covered))


_HERMETIC_SCRIPTED_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _hermetic_pack():
    """A tiny in-memory verified-shape pack with hand-computable render output:
    scripted CH1=100/CH2=50 at t=0, and Static Override slot 7 = CH3=200."""
    from rb_ss_bridge_v2.soundswitch_pack_loader import (
        LoadedAttribute, LoadedDocument, LoadedPack, LoadedScalarValue,
        LoadedStaticLook, LoadedTimelineEvent)
    from types import MappingProxyType

    event = LoadedTimelineEvent(
        time=0, source_order=0, source_offset=100, reference_kind="cue",
        raw_reference=1,
        patch=(LoadedAttribute(0x493, 1, 1, 100), LoadedAttribute(0x493, 2, 2, 50)))
    doc = LoadedDocument("synthetic.ssfile", "shared_441_dictionary_timeline",
                         (event,), (), 19_200)
    look = LoadedStaticLook(
        slot_index=7, record_version=5, name="slot-7",
        generic_attributes=(LoadedAttribute(0x493, 3, 3, 200),),
        intensity_values=(LoadedScalarValue(1, 1, 0.5),),
        strobe_values=(), colour_values=(), position_values=())
    return LoadedPack(
        schema_version="1.0.0", manifest_sha256="0" * 64, has_intensity_channel=False,
        scripted=MappingProxyType({_HERMETIC_SCRIPTED_ID: doc}),
        autoloops=MappingProxyType({}),
        static_looks=MappingProxyType({7: look}))


def build_hermetic_scenario() -> list[ShadowAction]:
    """A self-contained scripted/static/blackout scenario for ``_hermetic_pack``.

    Hand-computed expected frames (independent of the player's renderer) let this
    run with no live project and no hardware.  Runtime-phase autoloop steps are
    intentionally absent; direct ``phase_tick`` rendering is covered in the player
    tests, while this harness reports the T7d integration gap explicitly.
    """
    scripted_id = _HERMETIC_SCRIPTED_ID
    scripted_frame = (100, 50) + (0,) * 17
    static_frame = (0, 0, 200) + (0,) * 16
    return [
        ShadowAction("scripted_playing", "scripted",
                     lambda p: p.select_scripted(scripted_id, 1000), scripted_frame),
        ShadowAction("scripted_stopped", "transition",
                     lambda p: p.select_scripted(scripted_id, 1000, transport="stopped"),
                     ZERO_FRAME),
        ShadowAction("clear_selection", "transition",
                     lambda p: p.clear_selection(), ZERO_FRAME),
        ShadowAction("static_stands_alone", "static",
                     lambda p: p.hold_static(7), static_frame),
        ShadowAction("blackout_over_static", "blackout",
                     lambda p: p.set_blackout(True), ZERO_FRAME),
        ShadowAction("blackout_released", "static",
                     lambda p: p.set_blackout(False), static_frame),
        ShadowAction("emergency_over_static", "blackout",
                     lambda p: p.set_emergency(True), ZERO_FRAME),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    # This harness is deliberately hermetic. Real-pack artifacts and renderer
    # frames are covered by the proof gate and the pack/player test suites.
    player = LaserPackPlayer(_hermetic_pack())

    report = run_shadow(player, build_hermetic_scenario(), backend=NoneBackend())
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    print("status: SOFTWARE/OFFLINE ONLY — HARDWARE-UNVALIDATED", file=sys.stderr)
    return 0 if report.all_match else 1


__all__ = [
    "ShadowAction", "ShadowReport", "ShadowStep",
    "build_hermetic_scenario", "frame_sha256", "run_shadow",
]


if __name__ == "__main__":
    raise SystemExit(main())
