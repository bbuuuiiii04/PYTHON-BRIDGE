from __future__ import annotations

import glob
import logging
import os
import re
import threading
import time
from typing import Callable

log = logging.getLogger("ss_library_scanner")

_SS_TRACKMAP_ENV = "RBSS_SS_TRACKMAP_PATH"
_SS_SCAN_ENV = "RBSS_SS_SCAN"
_SS_SCAN_ROOTS_ENV = "RBSS_SS_SCAN_ROOTS"
_SS_SCRIPTED_DENYLIST_ENV = "RBSS_SS_SCRIPTED_DENYLIST"
_SS_SCAN_LOG_CANDIDATES_ENV = "RBSS_SS_SCAN_LOG_CANDIDATES"
_AUDIO_RE = re.compile(
    r"/[^\x00-\x1f\ufffd]{4,}\.(mp3|wav|aiff?|m4a|flac|aac)",
    re.IGNORECASE,
)
_SSFILE_RE = re.compile(
    r"^\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}\.ssfile$",
    re.IGNORECASE,
)
_AUDIO_EXTS = {".mp3", ".wav", ".aiff", ".aif", ".m4a", ".flac", ".aac"}


def _auto_trackmap_path() -> str | None:
    pattern = os.path.expanduser("~/Music/SoundSwitch/*/SoundSwitchTrackMap.bin")
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else None


def parse_trackmap_filepaths(path: str) -> list[str]:
    with open(path, "rb") as f:
        data = f.read()
    text = data.decode("utf-16-le", errors="replace")
    return sorted({m.group(0) for m in _AUDIO_RE.finditer(text)})


def parse_project_scripted_ids(project_dir: str) -> list[str]:
    ids = []
    for path in glob.glob(os.path.join(project_dir, "*.ssfile")):
        name = os.path.basename(path)
        if _SSFILE_RE.match(name):
            ids.append(name[:-7].upper())
    return sorted(set(ids))


def _normalize_soundswitch_id(ssid: str) -> str:
    ssid = (ssid or "").strip().upper()
    if not ssid:
        return ""
    if not ssid.startswith("{"):
        ssid = "{" + ssid
    if not ssid.endswith("}"):
        ssid = ssid + "}"
    return ssid


def _scripted_denylist() -> set[str]:
    result: set[str] = set()
    raw = os.environ.get(_SS_SCRIPTED_DENYLIST_ENV, "")
    for part in re.split(r"[,:\s]+", raw):
        normalized = _normalize_soundswitch_id(part)
        if normalized:
            result.add(normalized)
    return result


def _default_scan_roots() -> list[str]:
    roots = [
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Music"),
    ]
    return [root for root in roots if os.path.isdir(root)]


def _scan_roots() -> list[str]:
    raw = os.environ.get(_SS_SCAN_ROOTS_ENV)
    if raw is None:
        return _default_scan_roots()
    if raw.strip() == "0":
        return []
    return [
        os.path.expanduser(part)
        for part in raw.split(os.pathsep)
        if part.strip()
    ]


def _iter_audio_files(roots: list[str]) -> list[str]:
    sound_switch_root = os.path.expanduser("~/Music/SoundSwitch")
    result = []
    seen: set[str] = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if os.path.abspath(dirpath).startswith(os.path.abspath(sound_switch_root)):
                dirnames[:] = []
                continue
            for filename in filenames:
                if os.path.splitext(filename.lower())[1] not in _AUDIO_EXTS:
                    continue
                path = os.path.join(dirpath, filename)
                if path not in seen:
                    seen.add(path)
                    result.append(path)
    return sorted(result)


def _scan_worker(
    trackmap_path: str,
    callback: Callable[[dict[str, str]], None],
    scripted_id_callback: Callable[[list[str]], None] | None = None,
) -> None:
    from .filepath_resolver import _read_soundswitch_id

    t0 = time.monotonic()
    project_scripted_ids = parse_project_scripted_ids(os.path.dirname(trackmap_path))
    denylist = _scripted_denylist()
    scripted_ids = [
        ssid for ssid in project_scripted_ids
        if _normalize_soundswitch_id(ssid) not in denylist
    ]
    scripted_id_set = set(scripted_ids)
    if scripted_id_callback:
        scripted_id_callback(scripted_ids)

    try:
        paths = parse_trackmap_filepaths(trackmap_path)
    except Exception as exc:
        log.warning("[SS-SCAN] trackmap-read-fail  path=%s  err=%s", trackmap_path, exc)
        return

    result: dict[str, str] = {}
    checked_paths = set(paths)
    for fp in paths:
        if not os.path.isfile(fp):
            continue
        try:
            ssid = _read_soundswitch_id(fp)
            if ssid:
                result[fp] = ssid
        except Exception:
            pass

    root_checked = 0
    extra_scripted = 0
    if scripted_id_set:
        for fp in _iter_audio_files(_scan_roots()):
            if fp in checked_paths:
                continue
            root_checked += 1
            try:
                ssid = _read_soundswitch_id(fp)
            except Exception:
                continue
            if ssid and ssid.strip().upper() in scripted_id_set:
                result[fp] = ssid
                extra_scripted += 1

    elapsed = time.monotonic() - t0
    scripted = {
        fp: ssid for fp, ssid in result.items()
        if ssid.strip().upper() in scripted_id_set
    }
    log.info(
        "[SS-SCAN] complete  tagged=%d  candidate_paths=%d  show_files=%d"
        "  excluded_show_files=%d  trackmap_checked=%d  root_checked=%d"
        "  extra_candidates=%d  elapsed=%.1fs",
        len(result),
        len(scripted),
        len(scripted_ids),
        len(project_scripted_ids) - len(scripted_ids),
        len(paths),
        root_checked,
        extra_scripted,
        elapsed,
    )
    log_candidates = os.environ.get(_SS_SCAN_LOG_CANDIDATES_ENV, "0") == "1"
    for fp, ssid in scripted.items():
        log_fn = log.info if log_candidates else log.debug
        log_fn("[SS-SCAN] candidate  file=%s  ssid=%s", os.path.basename(fp), ssid)
    callback(result)


def start_ss_library_scan(
    callback: Callable[[dict[str, str]], None],
    scripted_id_callback: Callable[[list[str]], None] | None = None,
) -> None:
    if os.environ.get(_SS_SCAN_ENV, "1") == "0":
        log.info("[SS-SCAN] disabled  (%s=0)", _SS_SCAN_ENV)
        return

    trackmap_path = os.environ.get(_SS_TRACKMAP_ENV) or _auto_trackmap_path()
    if not trackmap_path:
        log.warning("[SS-SCAN] skip  reason=trackmap-not-found")
        return

    log.info("[SS-SCAN] start  path=%s", trackmap_path)
    threading.Thread(
        target=_scan_worker,
        args=(trackmap_path, callback, scripted_id_callback),
        daemon=True,
        name="ss-library-scan",
    ).start()
