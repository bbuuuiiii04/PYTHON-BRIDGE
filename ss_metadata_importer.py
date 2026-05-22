from __future__ import annotations

import logging
import os
import plistlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

log = logging.getLogger("ss_metadata_importer")

SS_PROJECT_DIR_ENV = "RBSS_SS_PROJECT_DIR"
DEFAULT_SS_PROJECT_DIR = "~/Music/SoundSwitch/default.ssproj"
DEFAULT_SS_PLIST_PATH = "~/Library/Preferences/com.soundswitch.SoundSwitch.plist"

_AUTOLOOP_FILES = (
    "SoundSwitchAutoLoops.bin",
    "SoundSwitchAutoLoopsEx.bin",
)
_VENUES_FILE = "SoundSwitchVenues.bin"
_ASCII_TEXT_RE = re.compile(r"[\x20-\x7e]{3,}")
_VENUE_BANK_HEADERS = {
    "INTRO",
    "BREAKDOWN",
    "BUILDUP",
    "DROP",
    "STATIC LASERS",
    "TRACK SPECIFIC CUES",
    "AUTOLOOPS",
    "FLOWER",
    "COLOR",
    "GREEN LASER SIZES",
    "GROOVE // MID ENERGY",
    "BUILDUP // RISING",
    "DROP // HIGH ENERGY",
}
_PLIST_KEYS = (
    "randomiseAutoLoops",
    "autoloopRepeatMode",
    "overrideScriptedTracks",
)


@dataclass(frozen=True)
class LookRecord:
    name: str
    source_file: str
    bank_header: str
    look_type: str

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "source_file": self.source_file,
            "bank_header": self.bank_header,
            "look_type": self.look_type,
        }


@dataclass(frozen=True)
class LookCatalog:
    records: tuple[LookRecord, ...] = ()

    def as_dicts(self) -> list[dict[str, str]]:
        return [record.as_dict() for record in self.records]


def discover_project_dir() -> Path:
    raw = os.environ.get(SS_PROJECT_DIR_ENV) or DEFAULT_SS_PROJECT_DIR
    return Path(os.path.expanduser(raw))


def _extract_utf16_strings(path: Path, *, offset: int) -> list[str]:
    data = path.read_bytes()
    text = data[offset:].decode("utf-16-le", errors="replace")
    return [match.group(0) for match in _ASCII_TEXT_RE.finditer(text) if match.group(0).strip()]


def parse_autoloops_bin(path: str | os.PathLike[str]) -> list[tuple[str, str]]:
    strings = _extract_utf16_strings(Path(path), offset=0)
    if len(strings) <= 4:
        return []

    headers = strings[:4]
    looks = strings[4:]
    pairs: list[tuple[str, str]] = []
    for index, look_name in enumerate(looks):
        bank_index = min(index * len(headers) // len(looks), len(headers) - 1)
        pairs.append((headers[bank_index], look_name))
    return pairs


def _is_foundation_groove_header(value: str) -> bool:
    normalized = value.strip().upper()
    return normalized.startswith("FOUNDATION - GROOVE ") and normalized.endswith(" BPM")


def _is_venue_bank_header(value: str) -> bool:
    normalized = value.strip().upper()
    return normalized in _VENUE_BANK_HEADERS or _is_foundation_groove_header(value)


def parse_venues_bin(path: str | os.PathLike[str]) -> list[tuple[str, str]]:
    strings = _extract_utf16_strings(Path(path), offset=1)
    pairs: list[tuple[str, str]] = []
    current_bank = ""

    for value in strings:
        if _is_venue_bank_header(value):
            current_bank = value
            if _is_foundation_groove_header(value):
                pairs.append((current_bank, value))
            continue
        if current_bank:
            pairs.append((current_bank, value))

    return pairs


def _append_records(
    records: list[LookRecord],
    seen: set[tuple[str, str]],
    pairs: Iterable[tuple[str, str]],
    *,
    source_file: str,
    look_type: str,
) -> None:
    for bank_header, name in pairs:
        key = (source_file, name)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            LookRecord(
                name=name,
                source_file=source_file,
                bank_header=bank_header,
                look_type=look_type,
            )
        )


def build_catalog(project_dir: str | os.PathLike[str] | None = None) -> LookCatalog:
    project_path = Path(os.path.expanduser(str(project_dir))) if project_dir is not None else discover_project_dir()
    parse_path: Path = project_path

    try:
        if not project_path.is_dir():
            raise FileNotFoundError(project_path)

        records: list[LookRecord] = []
        seen: set[tuple[str, str]] = set()
        for source_file in _AUTOLOOP_FILES:
            parse_path = project_path / source_file
            _append_records(
                records,
                seen,
                parse_autoloops_bin(parse_path),
                source_file=source_file,
                look_type="autoloop",
            )

        parse_path = project_path / _VENUES_FILE
        _append_records(
            records,
            seen,
            parse_venues_bin(parse_path),
            source_file=_VENUES_FILE,
            look_type="static",
        )

        catalog = LookCatalog(tuple(records))
        log.info("[SS-CATALOG] loaded  looks=%d  project_dir=%s", len(catalog.records), project_path)
        return catalog
    except Exception as exc:
        log.warning("[SS-CATALOG] parse-fail  path=%s  err=%s", parse_path, exc)
        return LookCatalog()


def _format_plist_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "missing"
    return str(value)


def check_ss_plist(path: str | os.PathLike[str] | None = None) -> dict[str, object]:
    plist_path = Path(os.path.expanduser(str(path))) if path is not None else Path(os.path.expanduser(DEFAULT_SS_PLIST_PATH))
    try:
        with plist_path.open("rb") as fh:
            payload = plistlib.load(fh)
        values = {key: payload.get(key) for key in _PLIST_KEYS}
        log.info(
            "[SS-PLIST] randomiseAutoLoops=%s  autoloopRepeatMode=%s  overrideScriptedTracks=%s",
            _format_plist_value(values["randomiseAutoLoops"]),
            _format_plist_value(values["autoloopRepeatMode"]),
            _format_plist_value(values["overrideScriptedTracks"]),
        )
        return values
    except Exception as exc:
        log.warning("[SS-PLIST] read-fail  path=%s  err=%s", plist_path, exc)
        return {}
