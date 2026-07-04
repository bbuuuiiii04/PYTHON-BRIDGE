"""Pure U0-grounded SoundSwitch parity oracle.

The oracle compares a candidate pack render to explicit SoundSwitch U0 samples.
It performs no file, socket, subprocess, MIDI, serial, or hardware I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Literal, Mapping

from rb_ss_bridge_v2.soundswitch_laser_player import (
    CHANNEL_COUNT,
    ZERO_FRAME,
    render_autoloop_frame,
    render_scripted_frame,
)
from rb_ss_bridge_v2.soundswitch_pack_loader import LoadedAutoloop, LoadedDocument, LoadedScriptedTrack

OracleClass = Literal["MATCH", "BLIP", "VALUE_DIFF", "U0_DARK"]
IssueClass = Literal[
    "dropped_cue",
    "missing_hold",
    "pack_lit_u0_dark",
    "value_diff",
    "match",
    "u0_dark",
]


@dataclass(frozen=True, slots=True)
class ScriptedSample:
    elapsed_ms: int
    u0_frame: tuple[int, ...]
    label: str = ""


@dataclass(frozen=True, slots=True)
class AutoloopSample:
    phase_tick: int
    u0_frame: tuple[int, ...]
    label: str = ""


@dataclass(frozen=True, slots=True)
class StaticSample:
    u0_frame: tuple[int, ...]
    label: str = ""


@dataclass(frozen=True, slots=True)
class OracleSampleResult:
    label: str
    position: int
    class_name: OracleClass
    issue: IssueClass
    expected_frame: tuple[int, ...]
    u0_frame: tuple[int, ...]
    elapsed_ms: int | None = None
    phase_tick: int | None = None


@dataclass(frozen=True, slots=True)
class OracleReport:
    surface: Literal["scripted", "autoloop", "static"]
    verdict: Literal["PASS", "FAIL"]
    truth_source: Literal["SoundSwitch U0"] = "SoundSwitch U0"
    counts: Mapping[str, int] = None  # type: ignore[assignment]
    issues: Mapping[str, int] = None  # type: ignore[assignment]
    samples: tuple[OracleSampleResult, ...] = ()

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"

    def to_dict(self) -> dict[str, object]:
        return {
            "surface": self.surface,
            "verdict": self.verdict,
            "truth_source": self.truth_source,
            "counts": dict(self.counts or {}),
            "issues": dict(self.issues or {}),
            "samples": [
                {
                    "label": row.label,
                    "position": row.position,
                    "class_name": row.class_name,
                    "issue": row.issue,
                    "elapsed_ms": row.elapsed_ms,
                    "phase_tick": row.phase_tick,
                    "expected_frame": list(row.expected_frame),
                    "u0_frame": list(row.u0_frame),
                }
                for row in self.samples
            ],
        }


def _frame(value: Iterable[int], label: str) -> tuple[int, ...]:
    frame = tuple(value)
    if len(frame) != CHANNEL_COUNT or any(type(item) is not int or not 0 <= item <= 255 for item in frame):
        raise ValueError(f"{label} must contain exactly {CHANNEL_COUNT} integers in 0..255")
    return frame


def _lit(frame: tuple[int, ...]) -> bool:
    return any(frame)


def _bump(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _classify(expected: tuple[int, ...], u0: tuple[int, ...],
              previous_expected: tuple[int, ...]) -> tuple[OracleClass, IssueClass]:
    if expected == u0:
        return ("MATCH", "match") if _lit(u0) else ("U0_DARK", "u0_dark")
    if not _lit(u0):
        return "U0_DARK", "pack_lit_u0_dark"
    if not _lit(expected):
        if _lit(previous_expected) and u0 == previous_expected:
            return "BLIP", "missing_hold"
        return "BLIP", "dropped_cue"
    return "VALUE_DIFF", "value_diff"


def _report(surface: Literal["scripted", "autoloop", "static"],
            rows: list[OracleSampleResult]) -> OracleReport:
    counts: dict[str, int] = {}
    issues: dict[str, int] = {}
    for row in rows:
        _bump(counts, row.class_name)
        _bump(issues, row.issue)
    failures = sum(issues.get(key, 0) for key in (
        "dropped_cue", "missing_hold", "pack_lit_u0_dark", "value_diff",
    ))
    return OracleReport(
        surface=surface,
        verdict="FAIL" if failures else "PASS",
        counts=dict(sorted(counts.items())),
        issues=dict(sorted(issues.items())),
        samples=tuple(rows),
    )


def classify_scripted(
    document: LoadedDocument | LoadedScriptedTrack,
    samples: Iterable[ScriptedSample],
    *,
    renderer: Callable[[LoadedDocument | LoadedScriptedTrack, int], tuple[int, ...]] = render_scripted_frame,
) -> OracleReport:
    rows: list[OracleSampleResult] = []
    previous_expected = ZERO_FRAME
    for position, sample in enumerate(samples):
        if type(sample.elapsed_ms) is not int or sample.elapsed_ms < 0:
            raise ValueError("scripted sample elapsed_ms must be a non-negative integer")
        u0 = _frame(sample.u0_frame, "U0 frame")
        expected = _frame(renderer(document, sample.elapsed_ms), "scripted render")
        class_name, issue = _classify(expected, u0, previous_expected)
        rows.append(OracleSampleResult(
            label=sample.label,
            position=position,
            class_name=class_name,
            issue=issue,
            expected_frame=expected,
            u0_frame=u0,
            elapsed_ms=sample.elapsed_ms,
        ))
        previous_expected = expected
    return _report("scripted", rows)


def classify_autoloop(
    document: LoadedDocument | LoadedAutoloop,
    samples: Iterable[AutoloopSample],
    *,
    renderer: Callable[[LoadedDocument | LoadedAutoloop, int], tuple[int, ...]] = render_autoloop_frame,
) -> OracleReport:
    rows: list[OracleSampleResult] = []
    for position, sample in enumerate(samples):
        if type(sample.phase_tick) is not int or sample.phase_tick < 0:
            raise ValueError("autoloop sample phase_tick must be a non-negative integer")
        u0 = _frame(sample.u0_frame, "U0 frame")
        expected = _frame(renderer(document, sample.phase_tick), "autoloop render")
        class_name, issue = _classify(expected, u0, ZERO_FRAME)
        rows.append(OracleSampleResult(
            label=sample.label,
            position=position,
            class_name=class_name,
            issue=issue,
            expected_frame=expected,
            u0_frame=u0,
            phase_tick=sample.phase_tick,
        ))
    return _report("autoloop", rows)


def classify_static(pre_rendered_frame: Iterable[int], sample: StaticSample) -> OracleReport:
    expected = _frame(pre_rendered_frame, "static render")
    u0 = _frame(sample.u0_frame, "U0 frame")
    class_name, issue = _classify(expected, u0, ZERO_FRAME)
    return _report("static", [OracleSampleResult(
        label=sample.label,
        position=0,
        class_name=class_name,
        issue=issue,
        expected_frame=expected,
        u0_frame=u0,
    )])


__all__ = [
    "AutoloopSample", "OracleReport", "OracleSampleResult", "ScriptedSample",
    "StaticSample", "classify_autoloop", "classify_scripted", "classify_static",
]
