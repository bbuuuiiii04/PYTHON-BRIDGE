from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from urllib.parse import urlparse

from ..govee_frame_renderer import REALTIME_EFFECT_NAMES, REALTIME_EFFECT_PARAM_KEYS, SLOT_EFFECTS
from ..govee_lab_adapter import is_lab_production_scene, lab_draft_from_scene
from ..led_color_engine import LedColorEngine
from ..led_config import LEDConfigResult, _resolve_path, load_led_look_director_config_from_dict
from ..led_pad_controls import (
    FIREWORK_EXPLOSION_LAB_SPECS,
    controls_for,
    effective_lab_specs,
    render_catalog,
)
from ..runtime_status import COMMANDS_PATH, STATUS_PATH
from .led_pad_lab import (
    LabRegistry,
    LabRenderer,
    StaleLabEntry,
    clamp_cue_beats as _clamp_cue_beats,
    load_lab_effects,
    render_preview_frames,
)
from .led_pad_mirror import FrameMirrorRing
from .led_pad_playback import PadPlayback, stable_seed
from .pad_access import _is_loopback_host, access_payload

_MIRROR_SSE_INTERVAL_S = 1.0 / 30.0


def _lab_firework_specs_dead(specs: Any, fn: str) -> bool:
    """True when a firework draft still exposes unused color_b / sparkles_per_beat knobs."""
    if fn not in ("drop_firework_explosion", "drop_firework_explosion_2"):
        return False
    if not isinstance(specs, dict):
        return True
    if "sparkles_per_beat" in specs:
        return True
    if "color_b_r" in specs and "spark_a_r" not in specs:
        return True
    return False


class StaleLook(ValueError):
    """Raised when a pad look save's ``updated`` stamp does not match the draft."""

    def __init__(self, name: str, *, disk_updated: str, client_updated: str) -> None:
        super().__init__(
            f"stale_look: {name} changed since you loaded it "
            f"(disk={disk_updated!r}, client={client_updated!r})"
        )
        self.name = name
        self.disk_updated = disk_updated
        self.client_updated = client_updated
        self.code = "stale_look"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")

_ASSETS_DIR = Path(__file__).resolve().parent / "led_pad_assets"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "led_look_director.json"
# AWR-245/AWR-266: serve sim view + shared preview player read-only. Paths only —
# never import led_sim_engine / led_sim_web (AWR-193 fence; sim already imports pad-lab).
_SIM_VIEW_JS = _REPO_ROOT / "tools" / "led_sim_assets" / "ledsim-view.js"
_SIM_PLAYER_JS = _REPO_ROOT / "tools" / "led_sim_assets" / "ledsim-player.js"
_SIM_EXAMPLE_PROFILE = _REPO_ROOT / "config" / "led_sim_profile.example.json"
_SIM_DEFAULT_PROFILE = _REPO_ROOT / "config" / "led_sim_profile.json"
_SIM_DEFAULT_ROOM_MM = [5216.0, 2284.0]
_IDENT_RE = re.compile(r"^[a-z0-9_]+$")
# AWR-279 #8: look/draft ids are unbounded identifiers ([a-z0-9_]+) — a 500-char
# name breaks the editor header and pushes the ✕ off-screen. Cap the id length so
# the header stays legible and the close control stays reachable.
_MAX_NAME_LEN = 60
# AWR-279 #10: the Preview tempo box declares min=60 max=200; enforce the same
# range server-side so a typed value or a stepper walk-below can't stick a
# nonsense tempo (or a sticky error banner) into the session.
_PREVIEW_BPM_MIN = 60.0
_PREVIEW_BPM_MAX = 200.0
_ROLE_BANKS = ("ambient", "groove", "buildup", "pre_drop", "drop", "post_drop", "breakdown", "utility")
# AWR-279 #2: _clamp_cue_beats is imported from led_pad_lab so lab + pad share ONE
# cue-length validator (see the import block above).
_VISIBLE_BANKS = (
    "drafts",
    "ambient",
    "groove",
    "buildup",
    "drop",
    "post_drop",
    "breakdown",
    "utility",
    "legacy_color_suffix",
)
_STOP_LOOKS = frozenset({"safe_default", "blackout"})
logger = logging.getLogger("led_pad_web")


def _load_sim_profile_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("profile root must be a JSON object")
    return data


def _with_sim_lock_defaults(profile: dict[str, Any]) -> dict[str, Any]:
    """Mirror LedSimService.profile_state lock-key repair (no engine import)."""
    if not isinstance(profile.get("layout_locked"), bool):
        profile["layout_locked"] = False
    if not isinstance(profile.get("calibration_locked"), bool):
        profile["calibration_locked"] = False
    return profile


def resolve_sim_profile_state(
    *,
    example_path: Path | None = None,
    profile_path: Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Example-inherited sim profile merge — same shape as LedSimService.profile_state.

    JSON-only. Does not import ``led_sim_engine`` (pad↔sim Python cycle fence).
    Invalid/unreadable live profile falls back to the example with an error string.
    """
    example_path = Path(example_path) if example_path else _SIM_EXAMPLE_PROFILE
    profile_path = Path(profile_path) if profile_path else _SIM_DEFAULT_PROFILE
    error = ""
    try:
        example = _load_sim_profile_json(example_path)
    except Exception as exc:
        return {}, f"{example_path.name}: {exc}"

    if profile_path.exists():
        try:
            profile = {**example, **_load_sim_profile_json(profile_path)}
            # Independent repairs — layout missing and room_mm missing can both apply.
            if not isinstance(profile.get("layout"), dict):
                fallback = example.get("layout")
                profile["layout"] = (
                    dict(fallback) if isinstance(fallback, dict)
                    else {"preset": "perimeter", "points_mm": [], "flip_chain": False}
                )
            if not isinstance(profile.get("room_mm"), (list, tuple)):
                profile["room_mm"] = list(_SIM_DEFAULT_ROOM_MM)
            return _with_sim_lock_defaults(profile), ""
        except Exception as exc:
            error = f"{profile_path.name}: {exc}"
    return _with_sim_lock_defaults(dict(example)), error


def sim_profile_response(
    *,
    example_path: Path | None = None,
    profile_path: Path | None = None,
) -> dict[str, Any]:
    """Fail-soft JSON for GET /api/sim/profile — never raises to the handler."""
    try:
        profile, err = resolve_sim_profile_state(
            example_path=example_path,
            profile_path=profile_path,
        )
        if not profile:
            return {"ok": False, "error": err or "sim profile unavailable"}
        payload: dict[str, Any] = {"ok": True, "profile": profile}
        if err:
            payload["profile_error"] = err
        return payload
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

# Freshness watchdog (AWR-193 Task 9): the launchd-supervised pad process
# outlives code changes, so a stale catalog surface (import-time module state)
# ships to the operator until something restarts it. Watch these modules'
# mtimes and exit(3) — launchd (KeepAlive/SuccessfulExit=false) relaunches —
# ONLY when playback is idle and the pad does not own the LEDs.
_FRESHNESS_WATCHED: tuple[Path, ...] = (
    _REPO_ROOT / "govee_frame_renderer.py",
    _REPO_ROOT / "led_pad_controls.py",
    _REPO_ROOT / "govee_realtime_runner.py",
    _REPO_ROOT / "led_color_engine.py",
    _REPO_ROOT / "led_config.py",
    _REPO_ROOT / "tools" / "led_pad_web.py",
    _REPO_ROOT / "tools" / "led_pad_lab.py",
    _REPO_ROOT / "tools" / "led_pad_playback.py",
    _REPO_ROOT / "tools" / "led_pad_mirror.py",
    _REPO_ROOT / "tools" / "pad_access.py",
)


def _sample_watched_mtimes() -> dict[str, float]:
    out: dict[str, float] = {}
    for path in _FRESHNESS_WATCHED:
        try:
            out[str(path)] = path.stat().st_mtime
        except FileNotFoundError:
            # Absent key differs from the baseline: a missing watched file
            # counts as changed once stable.
            pass
    return out


def freshness_restart_due(
    baseline: dict[str, float],
    current: dict[str, float],
    *,
    playing: bool,
    pad_owned: bool,
    stable_age_s: float,
    min_stable_s: float = 3.0,
) -> bool:
    """Pure restart decision: change present, settled, and safe.

    True iff any watched mtime differs from baseline AND the newest change is
    at least ``min_stable_s`` old AND playback is idle AND the pad does not
    own the LEDs. A restart while pad-owned would drop the room dark — this
    function refuses that by construction.
    """
    if playing or pad_owned:
        return False
    if current == baseline:
        return False
    return stable_age_s >= min_stable_s


# Mirror OwnershipGate freshness: a status file older than this is dead.
STATUS_FRESH_S = 5.0


def process_start_time(pid: int) -> float | None:
    """Epoch seconds when ``pid`` started, via ``ps -o lstart=`` (no psutil).

    Returns None when the process is gone or ``ps`` output cannot be parsed.
    Bridge status has process.pid but no started_at — this is the pad-side
    heuristic (AWR-255). Does not touch bridge runtime modules.
    """
    try:
        completed = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(int(pid))],
            capture_output=True,
            text=True,
            check=False,
            timeout=2.0,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    raw = (completed.stdout or "").strip()
    if completed.returncode != 0 or not raw:
        return None
    try:
        # macOS/BSD: "Sun Jul 12 16:11:11 2026"
        return datetime.strptime(raw, "%a %b %d %H:%M:%S %Y").timestamp()
    except ValueError:
        return None


def status_file_is_fresh(written_at: float | None, *, now: float) -> bool:
    """True when status ``written_at`` is present and younger than STATUS_FRESH_S."""
    try:
        stamp = float(written_at or 0.0)
    except (TypeError, ValueError):
        return False
    if stamp <= 0.0:
        return False
    return (float(now) - stamp) < STATUS_FRESH_S


def compute_config_stale(
    *,
    config_mtime: float | None,
    bridge_started_at: float | None,
    last_commit_at: float | None = None,
    now: float | None = None,
    bridge_live: bool = True,
) -> dict[str, Any]:
    """Pure staleness: live LED config newer than the running bridge's start.

    When ``bridge_live`` is False (missing/stale status file — AWR-261), signal
    is ``not_running``: applied changes will load on the next bridge start.
    Primary live signal (``bridge_start``): config mtime > process start → stale.
    Weaker live signal (``commit_proxy``): fresh status but process start
    unknown — keep the honest "(can't tell)" warn only for that corner.
    """
    _ = now  # reserved for future age caps; kept for a stable test seam
    payload: dict[str, Any] = {
        "stale": False,
        "signal": "none",
        "config_mtime": config_mtime,
        "bridge_started_at": bridge_started_at,
        "last_commit_at": last_commit_at,
        "lag_s": None,
        "bridge_live": bool(bridge_live),
    }
    if not bridge_live:
        payload["signal"] = "not_running"
        payload["bridge_started_at"] = None
        return payload
    if config_mtime is None:
        return payload
    if bridge_started_at is not None:
        lag = float(config_mtime) - float(bridge_started_at)
        payload["lag_s"] = lag
        payload["signal"] = "bridge_start"
        payload["stale"] = lag > 0.0
        return payload
    if last_commit_at is not None and float(config_mtime) >= float(last_commit_at) - 2.0:
        payload["signal"] = "commit_proxy"
        payload["stale"] = True
        return payload
    return payload


def _resolved_config_path(explicit: Path | str | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    return _resolve_path(None) or _DEFAULT_CONFIG_PATH


def _draft_path_for(path: Path) -> Path:
    return path.with_name("led_look_director.draft.json")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a JSON object")
    return data


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=str(path.parent),
            prefix=f"{path.name}.tmp-",
        ) as fp:
            temp_path = Path(fp.name)
            json.dump(data, fp, indent=2, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def save_config_atomically(config: dict[str, Any], path: Path) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = path.with_name(f"{path.name}.bak-{ts}")
        suffix = 1
        while backup.exists():
            backup = path.with_name(f"{path.name}.bak-{ts}-{suffix}")
            suffix += 1
        shutil.copy2(path, backup)
    _write_json_atomic(path, config)
    return backup


def _normalized(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _default_pad_meta(config: dict[str, Any]) -> dict[str, Any]:
    palettes = list((config.get("color_engine") or {}).get("palettes", {}).keys())
    return {
        "drafts": [],
        "looks": {},
        "ui": {"bpm": 128, "test_palette": palettes[0] if palettes else "", "loop": True},
        # What THIS pad session actually changed, tracked so commit merges only
        # real edits over live and never re-applies stale draft content:
        #   touched = look CONTENT edited/created (looks + per-look color maps)
        #   moved   = look's role-bank PLACEMENT changed/created by the pad
        #   deleted = look removed through the pad
        # A params-only edit is touched but NOT moved, so commit preserves the
        # look's LIVE bank placement. Persisted with the draft (survives a
        # pad-server restart) and rebased to empty after each commit.
        "pad_session": {"touched": [], "moved": [], "deleted": []},
    }


def _ensure_pad_meta(config: dict[str, Any]) -> None:
    meta = config.setdefault("_pad_meta", {})
    if not isinstance(meta, dict):
        config["_pad_meta"] = meta = {}
    defaults = _default_pad_meta(config)
    for key, value in defaults.items():
        if key not in meta or not isinstance(meta.get(key), type(value)):
            meta[key] = copy.deepcopy(value)
    ui = meta.setdefault("ui", {})
    if not isinstance(ui, dict):
        meta["ui"] = ui = {}
    for key, value in defaults["ui"].items():
        ui.setdefault(key, value)
    meta.setdefault("drafts", [])
    meta.setdefault("looks", {})
    session = meta.setdefault("pad_session", {})
    if not isinstance(session, dict):
        meta["pad_session"] = session = {}
    for key in ("touched", "moved", "deleted"):
        if not isinstance(session.get(key), list):
            session[key] = []


def _pad_session(config: dict[str, Any]) -> dict[str, list[str]]:
    _ensure_pad_meta(config)
    return config["_pad_meta"]["pad_session"]


def _mark_touched(config: dict[str, Any], name: str) -> None:
    """Record a CONTENT change (look body / per-look color maps). Not a move."""
    session = _pad_session(config)
    session["deleted"] = [item for item in session["deleted"] if item != name]
    if name not in session["touched"]:
        session["touched"].append(name)


def _mark_moved(config: dict[str, Any], name: str) -> None:
    """Record a role-bank PLACEMENT change/creation by the pad. Not content."""
    session = _pad_session(config)
    session["deleted"] = [item for item in session["deleted"] if item != name]
    if name not in session["moved"]:
        session["moved"].append(name)


def _mark_deleted(config: dict[str, Any], name: str) -> None:
    session = _pad_session(config)
    session["touched"] = [item for item in session["touched"] if item != name]
    session["moved"] = [item for item in session["moved"] if item != name]
    if name not in session["deleted"]:
        session["deleted"].append(name)


def _default_bank(config: dict[str, Any]) -> dict[str, Any]:
    banks = config.setdefault("banks", {})
    if not isinstance(banks, dict):
        config["banks"] = banks = {}
    default = banks.setdefault("default", {})
    if not isinstance(default, dict):
        banks["default"] = default = {}
    for bank in _ROLE_BANKS:
        items = default.setdefault(bank, [])
        if not isinstance(items, list):
            default[bank] = []
    return default


def _dedupe(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        name = str(item)
        if name and name not in seen:
            out.append(name)
            seen.add(name)
    return out


def _pad_lists(config: dict[str, Any]) -> dict[str, list[str]]:
    _ensure_pad_meta(config)
    default = _default_bank(config)
    lists = {bank: _dedupe(default.get(bank, [])) for bank in _ROLE_BANKS}
    lists["drafts"] = _dedupe(config["_pad_meta"].get("drafts", []))
    # AWR-265 FINAL: legacy_color_suffix bank is gone; still expose an empty
    # list so older pad clients get a calm payload (UI hides the empty tab).
    legacy = (config.get("banks") or {}).get("legacy_color_suffix") or {}
    legacy_names: list[str] = []
    if isinstance(legacy, dict):
        for role in _ROLE_BANKS:
            values = legacy.get(role, [])
            if isinstance(values, list):
                legacy_names.extend(str(item) for item in values)
    lists["legacy_color_suffix"] = _dedupe(legacy_names)
    return lists


def _bank_for(config: dict[str, Any], name: str) -> str:
    lists = _pad_lists(config)
    for bank in ("drafts",) + _ROLE_BANKS:
        if name in lists.get(bank, []):
            return bank
    return "other"


def _remove_from_pad_banks(config: dict[str, Any], name: str) -> None:
    default = _default_bank(config)
    for bank in _ROLE_BANKS:
        default[bank] = [item for item in default.get(bank, []) if item != name]
    meta = config.setdefault("_pad_meta", {})
    meta["drafts"] = [item for item in meta.get("drafts", []) if item != name]


def _add_to_bank(config: dict[str, Any], name: str, bank: str) -> None:
    _remove_from_pad_banks(config, name)
    if bank == "drafts":
        drafts = config.setdefault("_pad_meta", {}).setdefault("drafts", [])
        drafts.append(name)
        config["_pad_meta"]["drafts"] = _dedupe(drafts)
        return
    default = _default_bank(config)
    default.setdefault(bank, []).append(name)
    default[bank] = _dedupe(default[bank])


def _drop_pair_refs(config: dict[str, Any], name: str) -> list[str]:
    refs: list[str] = []
    pairs = config.get("drop_pairs", {})
    if not isinstance(pairs, dict):
        return refs
    for drop, raw in pairs.items():
        post = raw.get("post_drop") if isinstance(raw, dict) else None
        if name == drop or name == post:
            refs.append(f"{drop}->{post}")
    return refs


class LedPadService:
    def __init__(
        self,
        config_path: Path | str | None = None,
        *,
        dry_run: bool = False,
        status_path: Path | str = STATUS_PATH,
        playback: Any | None = None,
        playback_factory: Callable[[Any], Any] | None = None,
        lab_dir: Path | str | None = None,
    ) -> None:
        self._config_path = _resolved_config_path(config_path)
        self._draft_path = _draft_path_for(self._config_path)
        # Fingerprint sidecar: sha256 of the live config the draft is based on
        # (gitignored — derived from live operator data).
        self._draft_base_path = self._config_path.with_name("led_look_director.draft.base")
        self._status_path = Path(status_path)
        self._lock = Lock()
        self._draft = self._load_initial_draft()
        self._lab = LabRegistry(lab_dir or (self._config_path.parent / "led_lab"))
        self._lab_renderer = LabRenderer(self._lab.module_path, fn_for=self._lab_fn_for)
        self._playback = playback
        if self._playback is None:
            result = self._load_config_result(self._draft)
            if not result.available or result.config is None:
                raise ValueError("; ".join(result.errors) or "LED config is not available")
            self._playback = playback_factory(result.config) if playback_factory else PadPlayback(result.config, dry_run=dry_run, renderer=self._lab_renderer)
        self._playing_name = ""
        self._last_play_editor: dict[str, Any] | None = None
        # Accept-what-you-hear: last APPLIED pre-injection params per lab draft
        # (author params + live UI overrides; palette-injected colors excluded).
        # AWR-259: persist beside drafts so a pad restart does not lose the snapshot.
        self._last_lab_applied_path = self._lab.lab_dir / "last_applied.json"
        self._last_lab_applied: dict[str, dict[str, Any]] = self._load_last_lab_applied()
        # AWR-255: wall time of last successful /api/commit in this pad process
        # (weaker stale signal when bridge process start cannot be resolved).
        self._last_commit_at: float | None = None
        # AWR-269: SSE handlers exit when the pad service shuts down.
        self._shutdown = threading.Event()

    def _load_last_lab_applied(self) -> dict[str, dict[str, Any]]:
        path = self._last_lab_applied_path
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for key, value in data.items():
            if isinstance(value, dict):
                out[str(key)] = copy.deepcopy(value)
        return out

    def _persist_last_lab_applied_locked(self) -> None:
        _write_json_atomic(self._last_lab_applied_path, self._last_lab_applied)

    @property
    def draft_path(self) -> Path:
        return self._draft_path

    @property
    def config_path(self) -> Path:
        return self._config_path

    def shutdown(self) -> None:
        self._shutdown.set()
        shutdown = getattr(self._playback, "shutdown", None)
        if callable(shutdown):
            shutdown()

    def mirror_ring(self) -> FrameMirrorRing | None:
        """Pad-process send ring, or None when playback has no tee (fake/test)."""
        mirror = getattr(self._playback, "mirror", None)
        return mirror if isinstance(mirror, FrameMirrorRing) else None

    def shutting_down(self) -> bool:
        return self._shutdown.is_set()

    def _lab_fn_for(self, name: str) -> str:
        # Non-throwing resolver for LabRenderer's name-first/fn-fallback lookup:
        # registry entry's fn, else the name itself.
        try:
            entry = self._lab.get(str(name))
        except Exception:
            return str(name)
        return str(entry.get("fn") or name)

    def _live_fingerprint(self) -> str:
        live = _load_json(self._config_path) if self._config_path.exists() else {}
        return hashlib.sha256(_normalized(live).encode("utf-8")).hexdigest()

    def _write_draft_base(self, live_hash: str | None = None) -> None:
        self._draft_base_path.write_text((live_hash or self._live_fingerprint()) + "\n", encoding="utf-8")

    def _read_draft_base(self) -> str | None:
        try:
            return self._draft_base_path.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, OSError):
            return None

    def _load_initial_draft(self) -> dict[str, Any]:
        draft_exists = self._draft_path.exists()
        source = self._draft_path if draft_exists else self._config_path
        if not source.exists():
            raise FileNotFoundError(f"LED config not found: {source}")
        config = _load_json(source)
        _ensure_pad_meta(config)
        _default_bank(config)
        if not draft_exists:
            # Draft freshly derived from live: record the base fingerprint.
            self._write_draft_base()
        return config

    def _persist_draft_locked(self) -> None:
        _ensure_pad_meta(self._draft)
        _write_json_atomic(self._draft_path, self._draft)

    def _load_config_result(self, config: dict[str, Any]) -> LEDConfigResult:
        return load_led_look_director_config_from_dict(config)

    def _validate(self, config: dict[str, Any]) -> tuple[list[str], list[str]]:
        result = self._load_config_result(config)
        errors = list(result.errors)
        warnings: list[str] = []
        return errors, warnings

    def _dirty_for(self, config: dict[str, Any]) -> dict[str, Any]:
        live = _load_json(self._config_path) if self._config_path.exists() else {}
        _ensure_pad_meta(live)
        _default_bank(live)
        looks = sorted(
            name
            for name in set((config.get("looks") or {}).keys()) | set((live.get("looks") or {}).keys())
            if _normalized((config.get("looks") or {}).get(name)) != _normalized((live.get("looks") or {}).get(name))
        )
        current_lists = _pad_lists(config)
        live_lists = _pad_lists(live)
        banks: dict[str, bool] = {}
        for bank in _VISIBLE_BANKS:
            members = set(current_lists.get(bank, []))
            bank_changed = current_lists.get(bank, []) != live_lists.get(bank, [])
            banks[bank] = bank_changed or any(name in members for name in looks)
        meta_current = copy.deepcopy(config.get("_pad_meta", {}))
        meta_live = copy.deepcopy(live.get("_pad_meta", {}))
        meta_current.pop("ui", None)
        meta_live.pop("ui", None)
        meta_changed = _normalized(meta_current) != _normalized(meta_live)
        global_dirty = (
            _normalized(config) != _normalized(live)
            or bool(looks)
            or meta_changed
            or any(banks.values())
        )
        return {"global": global_dirty, "banks": banks, "looks": looks}

    def _bank_payload(self, config: dict[str, Any]) -> dict[str, list[str]]:
        lists = _pad_lists(config)
        payload = {bank: lists.get(bank, []) for bank in _VISIBLE_BANKS}
        default = _default_bank(config)
        other = list(lists.get("pre_drop", []))
        for bank, values in default.items():
            if bank not in _ROLE_BANKS:
                if isinstance(values, list):
                    other.extend(str(item) for item in values)
        payload["other"] = _dedupe(other)
        return payload

    def _guard_mutable(self, config: dict[str, Any], name: str, *, move: bool = False, delete: bool = False) -> None:
        if name in {str(config.get(key, "")) for key in _STOP_LOOKS}:
            action = "move" if move else "delete" if delete else "change"
            raise ValueError(f"{name} is {action}-protected")
        refs = _drop_pair_refs(config, name)
        if refs and delete:
            raise ValueError(f"{name} is referenced by drop pair {', '.join(refs)}")

    def _ensure_unique_bank_locked(self, config: dict[str, Any]) -> None:
        lists = _pad_lists(config)
        counts: dict[str, int] = {}
        for values in lists.values():
            for name in values:
                counts[name] = counts.get(name, 0) + 1
        duplicates = sorted(name for name, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"look appears in more than one LED Pad bank: {', '.join(duplicates)}")

    def get_config_payload(self) -> dict[str, Any]:
        with self._lock:
            config = copy.deepcopy(self._draft)
        errors, warnings = self._validate(config)
        dirty = self._dirty_for(config)
        live_hash = self._live_fingerprint()
        if not dirty["global"]:
            # Clean draft tracks live: refresh the base fingerprint.
            self._write_draft_base(live_hash)
        recorded = self._read_draft_base()
        return {
            "ok": True,
            "config": config,
            "errors": errors,
            "warnings": warnings,
            "dirty": dirty,
            "banks": self._bank_payload(config),
            "live_changed": recorded is not None and recorded != live_hash,
        }

    def get_renders(self) -> dict[str, Any]:
        renders = []
        for item in render_catalog():
            render = dict(item)
            render["controls"] = controls_for(str(item["name"]))
            renders.append(render)
        return {"ok": True, "renders": renders}

    def get_palettes(self) -> dict[str, Any]:
        with self._lock:
            palettes = list(((self._draft.get("color_engine") or {}).get("palettes") or {}).keys())
        return {
            "ok": True,
            "palettes": palettes,
            "warnings": [] if palettes else ["color_engine.palettes is empty or unavailable"],
        }

    def _validate_name(self, name: str, *, new: bool = False, config: dict[str, Any]) -> None:
        if not name or not _IDENT_RE.fullmatch(name):
            raise ValueError("look name must match [a-z0-9_]+")
        if len(name) > _MAX_NAME_LEN:
            raise ValueError(f"look name is too long (max {_MAX_NAME_LEN} characters)")
        if new and name in (config.get("looks") or {}):
            raise ValueError(f"look already exists: {name}")

    def _candidate_save_look(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        look_patch = payload.get("look")
        params = payload.get("params")
        if not isinstance(look_patch, dict):
            raise ValueError("look/save requires look object")
        if not isinstance(params, dict):
            params = {}
        candidate = copy.deepcopy(self._draft)
        self._validate_name(name, config=candidate)
        # AWR-259 L7: same-look two-tab CAS — client must carry the stamp it loaded.
        if "updated" in payload:
            disk_meta = ((candidate.get("_pad_meta") or {}).get("looks") or {}).get(name) or {}
            disk_updated = str(disk_meta.get("updated") or "")
            client_updated = str(payload.get("updated") or "")
            if client_updated != disk_updated:
                raise StaleLook(name, disk_updated=disk_updated, client_updated=client_updated)
        scene_ref = str(look_patch.get("scene_ref") or (candidate.get("looks", {}).get(name) or {}).get("scene_ref") or "")
        from ..govee_lab_adapter import is_lab_production_scene
        if is_lab_production_scene(scene_ref):
            allowed = None  # free-form lab draft params
        else:
            allowed = REALTIME_EFFECT_PARAM_KEYS.get(scene_ref, frozenset())
        if allowed is not None:
            unknown = sorted(str(key) for key in params if str(key) not in allowed)
            if unknown:
                raise ValueError(f"unknown params for {scene_ref}: {', '.join(unknown)}")
        looks = candidate.setdefault("looks", {})
        current = copy.deepcopy(looks.get(name, {}))
        current.update(copy.deepcopy(look_patch))
        current["params"] = copy.deepcopy(params)
        looks[name] = current
        engine = candidate.setdefault("color_engine", {})
        if "slot_fill" in payload:
            engine.setdefault("slot_fill_strategy_by_look", {})[name] = str(payload.get("slot_fill"))
        if "mono_chance" in payload:
            engine.setdefault("slot_mono_chance_by_look", {})[name] = float(payload.get("mono_chance"))
        if "locked_palette" in payload:
            locked = engine.setdefault("locked_palette_by_look", {})
            palette_name = str(payload.get("locked_palette") or "")
            if palette_name:
                locked[name] = palette_name
            else:
                locked.pop(name, None)
        meta = candidate.setdefault("_pad_meta", {}).setdefault("looks", {})
        look_meta = meta.setdefault(name, {})
        if "cue_beats" in payload:
            # Cue length is beats-until-auto-stop. 0 / negatives would make a
            # loop-off cue never end (CueTimer can't auto-stop) and the card would
            # then lie "16 beats". Clamp to a real >=1 length (AWR-279 #2).
            look_meta["cue_beats"] = _clamp_cue_beats(payload.get("cue_beats"), default=1.0)
        look_meta["updated"] = _now_iso()
        _mark_touched(candidate, name)
        self._ensure_unique_bank_locked(candidate)
        return candidate

    def save_look(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            candidate = self._candidate_save_look(payload)
            errors, warnings = self._validate(candidate)
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings, "dirty": self._dirty_for(candidate)}
            self._draft = candidate
            self._persist_draft_locked()
            config = copy.deepcopy(self._draft)
            name = str(payload.get("name", "")).strip()
            updated = str((((config.get("_pad_meta") or {}).get("looks") or {}).get(name) or {}).get("updated") or "")
        return {
            "ok": True,
            "errors": [],
            "warnings": warnings,
            "dirty": self._dirty_for(config),
            "updated": updated,
        }

    def duplicate_look(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = str(payload.get("source", "")).strip()
        new_name = str(payload.get("new_name", "")).strip()
        with self._lock:
            candidate = copy.deepcopy(self._draft)
            self._validate_name(new_name, new=True, config=candidate)
            looks = candidate.setdefault("looks", {})
            if source not in looks:
                raise ValueError(f"unknown look: {source}")
            looks[new_name] = copy.deepcopy(looks[source])
            engine = candidate.setdefault("color_engine", {})
            for key in ("slot_fill_strategy_by_look", "slot_mono_chance_by_look", "locked_palette_by_look"):
                mapping = engine.setdefault(key, {})
                if source in mapping:
                    mapping[new_name] = copy.deepcopy(mapping[source])
            meta = candidate.setdefault("_pad_meta", {})
            meta.setdefault("looks", {})[new_name] = copy.deepcopy(meta.get("looks", {}).get(source, {}))
            _add_to_bank(candidate, new_name, "drafts")
            _mark_touched(candidate, new_name)  # new look content
            _mark_moved(candidate, new_name)  # and its drafts-bank placement
            self._ensure_unique_bank_locked(candidate)
            errors, warnings = self._validate(candidate)
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings, "dirty": self._dirty_for(candidate)}
            self._draft = candidate
            self._persist_draft_locked()
            config = copy.deepcopy(self._draft)
        return {"ok": True, "name": new_name, "errors": [], "warnings": warnings, "dirty": self._dirty_for(config)}

    def rename_look(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Rename a look id in-place (same content, bank, and color-engine maps)."""
        name = str(payload.get("name", "")).strip()
        new_name = str(payload.get("new_name", "")).strip()
        if name == new_name:
            return {"ok": True, "name": new_name, "errors": [], "warnings": [], "dirty": self._dirty_for(self._draft)}
        with self._lock:
            candidate = copy.deepcopy(self._draft)
            looks = candidate.setdefault("looks", {})
            if name not in looks:
                raise ValueError(f"unknown look: {name}")
            self._validate_name(new_name, new=True, config=candidate)
            bank = _bank_for(candidate, name)
            if bank == "other":
                bank = "drafts"
            looks[new_name] = looks.pop(name)
            engine = candidate.setdefault("color_engine", {})
            for key in ("slot_fill_strategy_by_look", "slot_mono_chance_by_look", "locked_palette_by_look"):
                mapping = engine.setdefault(key, {})
                if name in mapping:
                    mapping[new_name] = mapping.pop(name)
            meta = candidate.setdefault("_pad_meta", {})
            look_meta = meta.setdefault("looks", {})
            if name in look_meta:
                look_meta[new_name] = look_meta.pop(name)
            session = meta.setdefault("pad_session", {})
            for key in ("touched", "moved", "deleted"):
                items = session.get(key)
                if isinstance(items, list) and name in items:
                    session[key] = [new_name if item == name else item for item in items]
            _remove_from_pad_banks(candidate, name)
            _add_to_bank(candidate, new_name, bank)
            _mark_touched(candidate, new_name)
            _mark_moved(candidate, new_name)
            # AWR-278 A4: if the OLD name was already committed to live, the
            # merge-commit keeps every live look the pad didn't delete — so a
            # rename would leave the stale old-named look behind (a duplicate,
            # and for lab cues a second look sharing the same scene_ref). Mark
            # the old name deleted so commit drops it. Harmless when the old
            # name was never in live (pop is a no-op there).
            _mark_deleted(candidate, name)
            self._ensure_unique_bank_locked(candidate)
            errors, warnings = self._validate(candidate)
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings, "dirty": self._dirty_for(candidate)}
            self._draft = candidate
            self._persist_draft_locked()
            config = copy.deepcopy(self._draft)
        return {"ok": True, "name": new_name, "errors": [], "warnings": warnings, "dirty": self._dirty_for(config)}

    def move_look(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        bank = str(payload.get("bank", "")).strip()
        if bank not in _ROLE_BANKS + ("drafts",):
            raise ValueError("bank must be one of the LED Pad banks")
        with self._lock:
            candidate = copy.deepcopy(self._draft)
            if name not in (candidate.get("looks") or {}):
                raise ValueError(f"unknown look: {name}")
            self._guard_mutable(candidate, name, move=True)
            _add_to_bank(candidate, name, bank)
            _mark_moved(candidate, name)  # placement only — content stays LIVE
            self._ensure_unique_bank_locked(candidate)
            errors, warnings = self._validate(candidate)
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings, "dirty": self._dirty_for(candidate)}
            self._draft = candidate
            self._persist_draft_locked()
            config = copy.deepcopy(self._draft)
        return {"ok": True, "errors": [], "warnings": warnings, "dirty": self._dirty_for(config)}

    def delete_look(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        with self._lock:
            candidate = copy.deepcopy(self._draft)
            if name not in (candidate.get("looks") or {}):
                raise ValueError(f"unknown look: {name}")
            self._guard_mutable(candidate, name, delete=True)
            removed_scene_ref = str((candidate["looks"].get(name) or {}).get("scene_ref") or "")
            candidate["looks"].pop(name, None)
            _remove_from_pad_banks(candidate, name)
            engine = candidate.setdefault("color_engine", {})
            for key in ("slot_fill_strategy_by_look", "slot_mono_chance_by_look", "locked_palette_by_look"):
                if isinstance(engine.get(key), dict):
                    engine[key].pop(name, None)
            candidate.setdefault("_pad_meta", {}).setdefault("looks", {}).pop(name, None)
            _mark_deleted(candidate, name)
            self._ensure_unique_bank_locked(candidate)
            errors, warnings = self._validate(candidate)
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings, "dirty": self._dirty_for(candidate)}
            self._draft = candidate
            self._persist_draft_locked()
            config = copy.deepcopy(self._draft)
            # AWR-278 A2: a wired Template Lab cue just left the show — put its
            # draft back to "work in progress" so the Lab ledger stops claiming
            # it is still Accepted / in the show.
            self._reconcile_lab_unwire(removed_scene_ref)
        return {"ok": True, "errors": [], "warnings": warnings, "dirty": self._dirty_for(config)}

    def _session(self, config: dict[str, Any]) -> dict[str, Any]:
        _ensure_pad_meta(config)
        return config["_pad_meta"]["ui"]

    def session(self, payload: dict[str, Any]) -> dict[str, Any]:
        update_after = False
        lab_palette_name = ""
        with self._lock:
            session = self._session(self._draft)
            if "bpm" in payload:
                bpm = float(payload["bpm"])
                if not (bpm > 0):  # also rejects NaN
                    raise ValueError("bpm must be > 0")
                # AWR-279 #10: enforce the declared Preview tempo range so a typed
                # value or a stepper walk-below can't stick a nonsense tempo. Clamp
                # (don't reject) so the − button just floors at the minimum, and the
                # returned session carries the clamped value for the UI to sync.
                bpm = max(_PREVIEW_BPM_MIN, min(_PREVIEW_BPM_MAX, bpm))
                session["bpm"] = bpm
                self._playback.set_bpm(bpm)
            if "test_palette" in payload:
                session["test_palette"] = str(payload["test_palette"])
                update_after = bool(self._playing_name and self._last_play_editor)
                # Lab play/switch clear _last_play_editor, so pad-editor update_after
                # never fires for lab_* — push a color-only re-resolve via lab_update.
                if (
                    not update_after
                    and self._playing_name
                    and str(self._playing_name).startswith("lab_")
                ):
                    lab_palette_name = str(self._playing_name).removeprefix("lab_")
            if "loop" in payload:
                session["loop"] = bool(payload["loop"])
                self._playback.set_loop(bool(payload["loop"]))
            self._persist_draft_locked()
            out = copy.deepcopy(session)
        if update_after and self._last_play_editor:
            self.update({"name": self._playing_name, "editor": self._last_play_editor})
        elif lab_palette_name:
            # Re-resolve colors for the new palette WITHOUT throwing away the live
            # tweaks the operator dialed in. Feed the last-applied params so
            # lab_update rebuilds on top of them (and re-stores that same snapshot
            # instead of clobbering the accept-what-you-hear memory with the saved
            # draft params).
            lab_payload: dict[str, Any] = {"name": lab_palette_name}
            snapshot = self._last_lab_applied.get(lab_palette_name)
            if snapshot is not None:
                lab_payload["params"] = copy.deepcopy(snapshot)
            self.lab_update(lab_payload)
        return {"ok": True, "session": out}

    def _look_state(self, config: dict[str, Any], name: str, editor: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any], float]:
        looks = config.get("looks") or {}
        look = copy.deepcopy(looks.get(name) or {})
        if not look:
            raise ValueError(f"unknown look: {name}")
        cue_beats = float(config.get("_pad_meta", {}).get("looks", {}).get(name, {}).get("cue_beats", 16))
        if editor:
            patch = editor.get("look")
            if isinstance(patch, dict):
                look.update(copy.deepcopy(patch))
            params = editor.get("params")
            if isinstance(params, dict):
                look["params"] = copy.deepcopy(params)
            if "cue_beats" in editor:
                cue_beats = float(editor.get("cue_beats") or cue_beats)
        params = dict(look.get("params") or {})
        return look, params, cue_beats

    def _inject_engine_colors(self, config: dict[str, Any], name: str, look: dict[str, Any], params: dict[str, Any], *, force_slot: bool = False) -> None:
        if str(look.get("color_source", "engine")) != "engine":
            return
        result = self._load_config_result(config)
        if result.config is None or result.config.color_engine is None:
            return
        session = self._session(config)
        palette = str(session.get("test_palette") or "")
        engine = LedColorEngine(result.config.color_engine, set_seed=0)
        engine.set_scripted_stand_down(True)  # pad engine is fresh/offline: v2 has no dressing here; stand down to the v1 test-palette fill
        if palette:
            engine.set_palette(palette)
        engine.lock()
        scene_ref = str(look.get("scene_ref", ""))
        role = _bank_for(config, name)
        if force_slot or scene_ref in SLOT_EFFECTS:
            params.update(engine.resolve_slot_colors(
                role=role,
                section_id="led_pad",
                cycle=0,
                look_name=name,
                color_source="engine",
            ))
            return
        multi = "color_a" in REALTIME_EFFECT_PARAM_KEYS.get(scene_ref, ()) or "color_b" in REALTIME_EFFECT_PARAM_KEYS.get(scene_ref, ())
        params.update(engine.resolve_color(
            role=role,
            section_id="led_pad",
            cycle=0,
            look_name=name,
            color_source="engine",
            multi=multi,
        ))

    def _overlay_editor_slot_config(self, config: dict[str, Any], name: str, editor: dict[str, Any] | None) -> dict[str, Any]:
        if not editor:
            return config
        engine = config.setdefault("color_engine", {})
        if "slot_fill" in editor:
            engine.setdefault("slot_fill_strategy_by_look", {})[name] = str(editor["slot_fill"])
        if "mono_chance" in editor:
            engine.setdefault("slot_mono_chance_by_look", {})[name] = float(editor["mono_chance"])
        if "locked_palette" in editor:
            locked = engine.setdefault("locked_palette_by_look", {})
            palette_name = str(editor.get("locked_palette") or "")
            if palette_name:
                locked[name] = palette_name
            else:
                locked.pop(name, None)
        return config

    def _play_spec(self, config: dict[str, Any], name: str, editor: dict[str, Any] | None) -> tuple[dict[str, Any], float]:
        config = self._overlay_editor_slot_config(config, name, editor)
        look, params, cue_beats = self._look_state(config, name, editor)
        scene_ref = str(look.get("scene_ref", ""))
        # Accepted Template Lab cues (scene_ref "lab:<draft>") are first-class in
        # the pad: play them through the same LabRenderer the Lab live-fire uses.
        if is_lab_production_scene(scene_ref):
            return self._lab_production_play_spec(config, name, look, params, cue_beats)
        if scene_ref not in REALTIME_EFFECT_NAMES:
            raise ValueError("cloud scene - not previewable in the pad")
        allowed = REALTIME_EFFECT_PARAM_KEYS.get(scene_ref, frozenset())
        unknown = sorted(str(key) for key in params if str(key) not in allowed)
        if unknown:
            raise ValueError(f"unknown params for {scene_ref}: {', '.join(unknown)}")
        self._inject_engine_colors(config, name, look, params)
        return {
            "look_name": name,
            "scene_ref": scene_ref,
            "params": params,
            "allow_strobe": bool(look.get("allow_strobe")),
            "safety_allow_strobe": bool((config.get("safety") or {}).get("allow_strobe")),
        }, cue_beats

    def _lab_production_play_spec(
        self,
        config: dict[str, Any],
        name: str,
        look: dict[str, Any],
        params: dict[str, Any],
        cue_beats: float,
    ) -> tuple[dict[str, Any], float]:
        """Build a pad-tile Play spec for an accepted Template Lab cue.

        The accepted look stores ``scene_ref = "lab:<draft>"``, but the pad's
        renderer is a ``LabRenderer`` that lights ``lab_<draft>`` names. We
        resolve the draft, confirm its effect is registered, inject show colors
        from the engine (exactly like the Lab live-fire path), and hand the
        renderer the ``lab_<draft>`` scene it already knows how to draw.
        """
        scene_ref = str(look.get("scene_ref", ""))
        draft = lab_draft_from_scene(scene_ref, params)
        if not draft:
            raise ValueError("lab cue - no draft name in scene_ref")
        reload_result = self._lab_renderer.reload()
        if not reload_result["ok"]:
            # AWR-279 copy note: plain operator sentence in the banner, not a raw
            # Python traceback. Fix the details in Template Lab (Reload effect code).
            raise RuntimeError("This cue's effect code has an error, so it can't play. Fix it in Template Lab.")
        effects = reload_result["effects"]
        fn = self._lab_fn_for(draft)
        if draft not in effects and fn not in effects:
            raise ValueError(f"lab cue not registered: {draft}")
        try:
            kind = str(self._lab.get(draft).get("kind") or "frame")
        except Exception:
            kind = "frame"
        self._inject_engine_colors(config, name, look, params, force_slot=(kind == "slot"))
        return {
            "look_name": name,
            # lab_<draft>: the underscore name the LabRenderer lights (colon is
            # the stored production form; only the frame-engine child renders that).
            "scene_ref": LabRegistry.scene_ref(draft),
            "params": params,
            "allow_strobe": bool(look.get("allow_strobe")),
            "safety_allow_strobe": bool((config.get("safety") or {}).get("allow_strobe")),
        }, cue_beats

    def lab_list(self) -> dict[str, Any]:
        entries = self._lab.list()
        loaded = load_lab_effects(self._lab.module_path)
        effect_keys = set(loaded["effects"]) if loaded.get("ok") else set()
        for entry in entries:
            name = str(entry.get("name") or "")
            fn = str(entry.get("fn") or name)
            entry["previewable"] = name in effect_keys or fn in effect_keys
            # Decoration only (never persisted): CONTROL_META wins shared bounds;
            # firework dead-knob drafts get the live spark_a/spark_b family.
            raw_specs = entry.get("param_specs") or {}
            if _lab_firework_specs_dead(raw_specs, fn):
                raw_specs = FIREWORK_EXPLOSION_LAB_SPECS
            specs, conflicts = effective_lab_specs(raw_specs)
            entry["effective_param_specs"] = specs
            entry["spec_conflicts"] = conflicts
        return {"ok": True, "entries": entries, "module_path": str(self._lab.module_path)}

    def lab_reload(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        result = load_lab_effects(self._lab.module_path)
        return {
            "ok": bool(result["ok"]),
            "effects": sorted(result["effects"].keys()),
            "error": result["error"],
            "traceback": result["traceback"],
            "module_path": str(self._lab.module_path),
        }

    def lab_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self._lab.save(payload)

    def _lab_merge_editor(self, entry: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, bool]:
        """Merge editor fields into entry. Accept/Reject = Save then flip status.

        Params preference: payload.params (what the editor shows) wins; else the
        last live-applied pre-injection snapshot (agent Accept-after-Play); else
        leave entry params alone.

        Returns (snapshotted, snapshot_fallback):
        - snapshotted: params came from the last-applied live snapshot
        - snapshot_fallback: the client omitted params EXPECTING a live-tuned
          snapshot (``expect_live_snapshot``) but none existed — a genuine loss the
          UI should warn about. AWR-279 #14: the ordinary preview→Accept flow (the
          operator only previewed, never live-tuned) omits params with no live
          expectation, so it keeps the saved entry params calmly with NO warning
          instead of always flashing "your last live-tuned values weren't
          available".
        """
        snapshotted = False
        snapshot_fallback = False
        if isinstance(payload.get("params"), dict):
            entry["params"] = copy.deepcopy(payload["params"])
        else:
            snapshot = self._last_lab_applied.get(str(entry.get("name", "")))
            if snapshot is not None:
                entry["params"] = copy.deepcopy(snapshot)
                snapshotted = True
            elif bool(payload.get("expect_live_snapshot")):
                # Operator relied on live-tuned values that aren't here → warn.
                snapshot_fallback = True
            # else: no live tuning ever happened for this draft — the saved entry
            # params are exactly what the operator wants; keep them, stay calm.
        for key in ("brief", "notes", "target_role", "timing_mode"):
            if key in payload:
                entry[key] = str(payload.get(key) or "")
        if "cue_beats" in payload:
            entry["cue_beats"] = _clamp_cue_beats(payload.get("cue_beats"))
        return snapshotted, snapshot_fallback

    def _lab_persist_editor(self, payload: dict[str, Any], *, status: str) -> dict[str, Any]:
        """Save editor fields + status under the service lock (AWR-258)."""
        name = str(payload.get("name", "")).strip()
        with self._lock:
            entry = self._lab.get(name)
            snapshotted, snapshot_fallback = self._lab_merge_editor(entry, payload)
            entry["status"] = status
            # CAS uses the stamp the client loaded, not a fresh disk read.
            if "updated" in payload:
                entry["updated"] = payload["updated"]
            if payload.get("overwrite"):
                entry["overwrite"] = True
            result = self._lab.save(entry)
            result["snapshotted"] = snapshotted
            result["snapshot_fallback"] = snapshot_fallback
            return result

    def lab_accept(self, payload: dict[str, Any]) -> dict[str, Any]:
        # AWR-260: Accept = persist + wire into production bank + Apply + reload.
        result = self._lab_persist_editor(payload, status="accepted")
        entry = result.get("entry") or {}
        try:
            wired = self._lab_wire_into_production(entry)
        except Exception as exc:
            result["ok"] = False
            result["wired"] = False
            result["error"] = str(exc)
            result["message"] = f"Accepted as draft, but live wire-in failed: {exc}"
            return result
        result.update(wired)
        return result

    def lab_reject(self, payload: dict[str, Any]) -> dict[str, Any]:
        # AWR-251: Reject also persists the current editor state (named = saved).
        # AWR-278 A1: if this draft was Accepted into the show, Reject must also
        # pull its wired look back out — otherwise "stays out of the show" lies.
        result = self._lab_persist_editor(payload, status="rejected")
        entry = result.get("entry") or {}
        try:
            reconcile = self._reconcile_reject_unwire(str(entry.get("name") or "").strip(), entry)
        except Exception as exc:
            result["unwired"] = False
            result["message"] = (
                "Marked rejected, but I couldn't pull its look out of the show "
                f"automatically ({exc}). Delete that look on the Pad to remove it."
            )
            return result
        result.update(reconcile)
        return result

    def _reconcile_reject_unwire(self, draft: str, entry: dict[str, Any]) -> dict[str, Any]:
        """Pull a rejected draft's wired look out of the show (AWR-278 A1).

        Safe by construction:
        - never wired  → nothing to remove; honest default message.
        - pad-edited (look params drift from the draft) or shared (drop pair /
          stop look) → keep the look, say so, never silently destroy operator
          work.
        - untouched wired look → remove it + its bank memberships through the
          same commit + led_reload_looks pipeline Accept uses.
        """
        default_msg = "Rejected — stays out of the show. You can reopen it anytime."
        if not draft:
            return {"message": default_msg, "unwired": False}
        remove_name = ""
        with self._lock:
            wired_name = self._wired_look_name_locked(self._draft, draft)
            if not wired_name:
                return {"message": default_msg, "unwired": False}
            look = (self._draft.get("looks") or {}).get(wired_name) or {}
            edited = _normalized(look.get("params") or {}) != _normalized(entry.get("params") or {})
            protected = (
                wired_name in {str(self._draft.get(key, "")) for key in _STOP_LOOKS}
                or bool(_drop_pair_refs(self._draft, wired_name))
            )
            if edited or protected:
                reason = (
                    "you changed it on the Pad since accepting"
                    if edited
                    else "it's used elsewhere in your show"
                )
                return {
                    "message": (
                        f'Draft marked rejected. I kept "{wired_name}" in your show '
                        f"because {reason} — delete it on the Pad if you want it gone."
                    ),
                    "unwired": False,
                    "kept_look": wired_name,
                }
            candidate = copy.deepcopy(self._draft)
            candidate["looks"].pop(wired_name, None)
            _remove_from_pad_banks(candidate, wired_name)
            engine = candidate.setdefault("color_engine", {})
            for key in ("slot_fill_strategy_by_look", "slot_mono_chance_by_look", "locked_palette_by_look"):
                if isinstance(engine.get(key), dict):
                    engine[key].pop(wired_name, None)
            candidate.setdefault("_pad_meta", {}).setdefault("looks", {}).pop(wired_name, None)
            _mark_deleted(candidate, wired_name)
            errors, _warnings = self._validate(candidate)
            if errors:
                raise ValueError("; ".join(errors))
            self._draft = candidate
            self._persist_draft_locked()
            remove_name = wired_name
        # Push the removal to the live show + tell the bridge to reload — the
        # mirror of Accept's wire-in. Done OUTSIDE the lock (commit re-locks).
        commit_result = self.commit({})
        if not commit_result.get("ok"):
            raise ValueError("; ".join(commit_result.get("errors") or ["commit failed"]))
        self._append_bridge_command({"cmd": "led_reload_looks"})
        return {
            "message": (
                f'Rejected — removed "{remove_name}" from your show. '
                "You can reopen the draft anytime."
            ),
            "unwired": True,
            "removed_look": remove_name,
        }

    def _wired_look_name_locked(self, config: dict[str, Any], draft: str) -> str:
        """Config look wired to this lab draft, or "" if none.

        The durable link is the look's ``scene_ref`` (``lab:<draft>``), NOT the
        look name — so this scan still finds the wired look after the operator
        renamed it on the Pad. Call while holding ``self._lock``.
        """
        target = f"lab:{draft}"
        for look_name, look in (config.get("looks") or {}).items():
            if isinstance(look, dict) and str(look.get("scene_ref") or "") == target:
                return str(look_name)
        return ""

    def _reconcile_lab_unwire(self, scene_ref: str) -> None:
        """A wired lab cue left the show: flip its draft back to work-in-progress.

        Best-effort Lab-ledger repair (AWR-278 A2) — a lab-registry hiccup never
        fails the pad edit that triggered it. No-op for non-lab looks, an absent
        draft, or a draft that is not currently marked Accepted.
        """
        if not is_lab_production_scene(scene_ref):
            return
        draft = lab_draft_from_scene(scene_ref, {})
        if not draft:
            return
        try:
            entry = self._lab.get(draft)
        except Exception:
            return
        if entry.get("status") != "accepted":
            return
        entry["status"] = "iterating"
        try:
            self._lab.save(entry)
        except Exception:
            pass

    def _lab_wire_into_production(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Write look → bank → commit live → append led_reload_looks (AWR-260).

        AWR-278 A4: if this draft is already wired into the show (its scene_ref
        ``lab:<draft>`` is present, even under a renamed look), UPDATE that look
        in place — refresh its params, keep the operator's look-level tweaks and
        bank — instead of creating a second look with the same scene_ref.
        """
        name = str(entry.get("name") or "").strip()
        if not name:
            raise ValueError("lab accept requires a draft name")
        role = str(entry.get("target_role") or "").strip()
        target_bank = role if role in _ROLE_BANKS else "drafts"
        params = copy.deepcopy(entry.get("params") or {})
        if not isinstance(params, dict):
            params = {}
        cue_beats = _clamp_cue_beats(entry.get("cue_beats"))
        scene_ref = f"lab:{name}"
        with self._lock:
            existing_wired = self._wired_look_name_locked(self._draft, name)
            look_name = existing_wired or name
            if existing_wired:
                # Re-accept: refresh params + scene pointer only, keeping the
                # operator's look-level tweaks (brightness/strobe) and current
                # bank placement. No _add_to_bank / _mark_moved → no duplicate.
                save_payload = {
                    "name": look_name,
                    "look": {"scene_ref": scene_ref},
                    "params": params,
                    "cue_beats": cue_beats,
                }
                disk_meta = ((self._draft.get("_pad_meta") or {}).get("looks") or {}).get(look_name) or {}
                if disk_meta.get("updated"):
                    save_payload["updated"] = disk_meta["updated"]
                candidate = self._candidate_save_look(save_payload)
            else:
                # First accept: prefer a same-backend realtime blackout for lab looks.
                looks = self._draft.get("looks") or {}
                configured_blackout = str(self._draft.get("blackout") or "")
                blackout_look = looks.get(configured_blackout) if configured_blackout else None
                if (
                    isinstance(blackout_look, dict)
                    and blackout_look.get("backend") == "realtime_razer"
                ):
                    blackout = configured_blackout
                elif "rt_blackout" in looks:
                    blackout = "rt_blackout"
                else:
                    blackout = ""
                look = {
                    "target": "room_perimeter",
                    "action": "realtime",
                    "scene_ref": scene_ref,
                    "fallback": blackout,
                    "safety_class": role or "lab",
                    "brightness": 100,
                    "allow_strobe": False,
                    "backend": "realtime_razer",
                    "color_source": "engine",
                }
                save_payload = {
                    "name": look_name,
                    "look": look,
                    "params": params,
                    "cue_beats": cue_beats,
                }
                # Match draft stamp when the look already exists so CAS does not 409.
                disk_meta = ((self._draft.get("_pad_meta") or {}).get("looks") or {}).get(look_name) or {}
                if disk_meta.get("updated"):
                    save_payload["updated"] = disk_meta["updated"]
                candidate = self._candidate_save_look(save_payload)
                _add_to_bank(candidate, look_name, target_bank)
                _mark_moved(candidate, look_name)
            errors, warnings = self._validate(candidate)
            if errors:
                raise ValueError("; ".join(errors))
            self._draft = candidate
            self._persist_draft_locked()
            bank = _bank_for(candidate, look_name)

        commit_result = self.commit({})
        if not commit_result.get("ok"):
            raise ValueError("; ".join(commit_result.get("errors") or ["commit failed"]))

        self._append_bridge_command({"cmd": "led_reload_looks"})
        updated = bool(existing_wired)
        if bank in ("drafts", "other"):
            bank_label = "Untagged"
            message = (
                f'Updated "{look_name}" in your show — still on the Untagged shelf.'
                if updated
                else "In your show — Untagged shelf for now. Tag a phrase to join rotation."
            )
        else:
            bank_label = bank.replace("_", " ").title()
            message = (
                f'Updated "{look_name}" in your show — {bank_label} phrase bank.'
                if updated
                else f"In your show — added to the {bank_label} phrase bank."
            )
        return {
            "ok": True,
            "wired": True,
            "updated": updated,
            "look_name": look_name,
            "scene_ref": scene_ref,
            "bank": bank,
            "bank_label": bank_label,
            "message": message,
            "warnings": warnings,
            "backup_path": commit_result.get("backup_path") or "",
            "reload_appended": True,
        }

    def _append_bridge_command(self, command: dict[str, Any]) -> None:
        path = COMMANDS_PATH
        gate = getattr(getattr(self, "_playback", None), "_ownership", None)
        if gate is not None and getattr(gate, "command_path", None):
            path = str(gate.command_path)
        raw = json.dumps(command, separators=(",", ":")) + "\n"
        fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fp:
            fp.write(raw)

    def lab_archive(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        with self._lock:
            # AWR-279 #9: same guard lab_delete has — don't archive a draft whose
            # scene is live on the lights; make the operator stop it first.
            if self._playing_name == LabRegistry.scene_ref(name):
                return {"ok": False, "error": "stop_playback_first"}
            return self._lab.archive(name)

    def lab_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        with self._lock:
            if self._playing_name == LabRegistry.scene_ref(name):
                return {"ok": False, "error": "stop_playback_first"}
            return self._lab.delete(name)

    def _lab_play_spec(self, config: dict[str, Any], entry: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
        reload_result = self._lab_renderer.reload()
        if not reload_result["ok"]:
            # AWR-279 copy note: the operator banner gets a plain sentence, not a raw
            # Python traceback. The details live behind "Reload effect code" (red Lab
            # health dot → traceback), which surfaces the same failure inspectably.
            raise RuntimeError('Your effect code has an error, so this cue can\'t play. Press "Reload effect code" to see the details.')
        name = str(entry["name"])
        kind = str(entry["kind"])
        fn = str(entry.get("fn") or name)
        effects = reload_result["effects"]
        if name not in effects and fn not in effects:
            raise ValueError(f"lab effect not registered: {name} (fn: {fn})")
        params = copy.deepcopy(entry.get("params") or {})
        if isinstance(payload.get("params"), dict):
            params.update(copy.deepcopy(payload["params"]))
        self._last_lab_applied[name] = copy.deepcopy(params)
        self._persist_last_lab_applied_locked()
        look = {"scene_ref": LabRegistry.scene_ref(name), "color_source": "engine"}
        self._inject_engine_colors(config, LabRegistry.scene_ref(name), look, params, force_slot=(kind == "slot"))
        return {
            "look_name": LabRegistry.scene_ref(name),
            "scene_ref": LabRegistry.scene_ref(name),
            "params": params,
            "allow_strobe": False,
            "safety_allow_strobe": bool((config.get("safety") or {}).get("allow_strobe")),
        }, _clamp_cue_beats(payload.get("cue_beats", entry.get("cue_beats")))

    def lab_play(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        entry = self._lab.get(name)
        with self._lock:
            config = copy.deepcopy(self._draft)
            session = copy.deepcopy(self._session(config))
        ownership = self._playback.ownership()
        if ownership.get("state") == "bridge_owned":
            if not bool(payload.get("takeover")):
                return {"ok": False, "error": "ownership_required", "ownership": ownership}
            self._playback.request_takeover()
        spec, cue_beats = self._lab_play_spec(config, entry, payload)
        self._playback.set_bpm(float(session.get("bpm") or 128))
        # AWR-273 / D5: lab live-fire is always one-shot. Session Loop still applies to
        # Pad tile Play only — do not mutate session loop here.
        self._playback.play(spec, cue_beats=cue_beats, loop=False)
        self._playing_name = str(spec["look_name"])
        self._last_play_editor = None
        return {
            "ok": True,
            "spec": spec,
            "cue_beats": cue_beats,
            "loop": False,
            "playback": self._playback.status(),
        }

    def lab_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        entry = self._lab.get(name)
        scene = LabRegistry.scene_ref(name)
        if not self._playback.status().get("playing"):
            self._playing_name = ""
            self._last_play_editor = None
        if not self._playing_name or self._playing_name != scene:
            return {"ok": True, "applied": False}
        with self._lock:
            config = copy.deepcopy(self._draft)
        spec, _cue_beats = self._lab_play_spec(config, entry, payload)
        self._playback.update(spec)
        return {"ok": True, "applied": True, "spec": spec, "playback": self._playback.status()}

    def lab_switch(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        entry = self._lab.get(name)
        scene = LabRegistry.scene_ref(name)
        if not self._playback.status().get("playing") or not str(self._playing_name).startswith("lab_"):
            return {"ok": False, "error": "no_lab_scene_playing"}
        with self._lock:
            config = copy.deepcopy(self._draft)
        spec, _cue_beats = self._lab_play_spec(config, entry, payload)
        self._playback.update(spec)
        self._playing_name = scene
        self._last_play_editor = None
        return {"ok": True, "applied": True, "spec": spec, "playback": self._playback.status()}

    def lab_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        entry = self._lab.get(name)
        with self._lock:
            config = copy.deepcopy(self._draft)
            session = copy.deepcopy(self._session(config))
        renderer = LabRenderer(self._lab.module_path, fn_for=self._lab_fn_for)
        result = renderer.reload()
        if not result["ok"]:
            return {"ok": False, "error": result["error"], "traceback": result["traceback"]}
        fn = str(entry.get("fn") or name)
        if name not in renderer.effects and fn not in renderer.effects:
            raise ValueError(f"lab effect not registered: {name} (fn: {fn})")
        params = copy.deepcopy(entry.get("params") or {})
        if isinstance(payload.get("params"), dict):
            params.update(copy.deepcopy(payload["params"]))
        scene = LabRegistry.scene_ref(name)
        look = {"scene_ref": scene, "color_source": "engine"}
        self._inject_engine_colors(config, scene, look, params, force_slot=(str(entry["kind"]) == "slot"))
        led_config = self._load_config_result(config).config
        target = next((item for item in led_config.targets.values() if item.realtime.enabled), None) if led_config else None
        if target is None:
            raise ValueError("no realtime-enabled LED target in config")
        fps = max(1, min(40, int(payload.get("fps") or target.realtime.fps)))
        bpm = max(40.0, min(220.0, float(payload.get("bpm") or session.get("bpm") or 128)))
        default_beats = float(entry.get("cue_beats", 16) or 16)
        beats = max(1.0, min(32.0, float(payload.get("beats") or default_beats)))
        frames = render_preview_frames(
            renderer, scene,
            params=params, segments=int(target.realtime.segments),
            seed=stable_seed(scene), fps=fps, bpm=bpm, beats=beats,
        )
        return {"ok": True, "frames": frames, "fps": fps, "bpm": bpm, "beats": beats,
                "segments": int(target.realtime.segments), "slot_colors": params.get("slot_colors") or []}

    def play(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        editor = payload.get("editor") if isinstance(payload.get("editor"), dict) else None
        with self._lock:
            config = copy.deepcopy(self._draft)
            session = copy.deepcopy(self._session(config))
        ownership = self._playback.ownership()
        if ownership.get("state") == "bridge_owned":
            if not bool(payload.get("takeover")):
                return {"ok": False, "error": "ownership_required", "ownership": ownership}
            self._playback.request_takeover()
        spec, cue_beats = self._play_spec(config, name, editor)
        self._playback.set_bpm(float(session.get("bpm") or 128))
        self._playback.play(spec, cue_beats=cue_beats, loop=bool(session.get("loop", True)))
        self._playing_name = name
        self._last_play_editor = copy.deepcopy(editor) if editor else None
        return {"ok": True, "spec": spec, "cue_beats": cue_beats, "playback": self._playback.status()}

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or self._playing_name).strip()
        playback_status = self._playback.status()
        if not playback_status.get("playing"):
            self._playing_name = ""
            self._last_play_editor = None
        if not self._playing_name or name != self._playing_name:
            return {"ok": True, "applied": False}
        editor = payload.get("editor") if isinstance(payload.get("editor"), dict) else None
        with self._lock:
            config = copy.deepcopy(self._draft)
        spec, _cue_beats = self._play_spec(config, name, editor)
        self._playback.update(spec)
        self._last_play_editor = copy.deepcopy(editor) if editor else self._last_play_editor
        return {"ok": True, "applied": True, "spec": spec, "playback": self._playback.status()}

    def stop(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._playback.stop()
        self._playing_name = ""
        self._last_play_editor = None
        return {"ok": True, "playback": self._playback.status()}

    def emergency_stop(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._playback.emergency_stop()
        self._playing_name = ""
        self._last_play_editor = None
        return {"ok": True, "playback": self._playback.status()}

    def release(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._playback.release()
        self._playing_name = ""
        self._last_play_editor = None
        return {"ok": True, "ownership": self._playback.ownership()}

    def takeover(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._playback.request_takeover()
        return {"ok": True, "ownership": self._playback.ownership()}

    def _merged_commit_config(self, draft: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
        """Read-modify-merge for commit: unmanaged live blocks always survive.

        Every top-level block comes from LIVE (including blocks the pad has never
        heard of). Only what this pad session actually changed is overlaid from
        the draft, and content vs placement are tracked separately:
          - ``touched`` drives look CONTENT and the three per-look
            ``color_engine`` maps.
          - ``moved`` drives role-bank PLACEMENT.
        So a params-only edit (touched, not moved) overlays the look body but
        keeps its LIVE bank placement — if live moved that look to another bank
        after the draft went stale, the stale draft placement is NOT replayed.
        An explicit pad move (moved) still repositions it. ``deleted`` removes
        the look from both content and banks. Looks the pad never touched/moved
        keep their LIVE contents and placement, so a stale draft can no longer
        clobber f2/f4/looks added by other tools. ``_pad_meta`` is pad-owned.
        Pure transform.
        """
        session = (draft.get("_pad_meta") or {}).get("pad_session") or {}
        touched = [str(name) for name in (session.get("touched") or [])]
        moved = [str(name) for name in (session.get("moved") or [])]
        deleted = {str(name) for name in (session.get("deleted") or [])}
        moved_set = set(moved)
        placement_changed = moved_set | deleted

        merged = copy.deepcopy(live)

        # looks: LIVE base, overlay only touched looks, drop only deleted looks.
        live_looks = live.get("looks") or {}
        draft_looks = draft.get("looks") or {}
        merged_looks = {name: copy.deepcopy(look) for name, look in live_looks.items()}
        for name in touched:
            if name in draft_looks:
                merged_looks[name] = copy.deepcopy(draft_looks[name])
        for name in deleted:
            merged_looks.pop(name, None)
        merged["looks"] = merged_looks

        # banks.default role lists: keep LIVE placement for every look the pad
        # did not move or delete, then apply the pad's own placement only for
        # the looks it actually moved/created. A touched-but-not-moved look
        # (params-only edit) is untouched here, so its LIVE bank wins.
        live_default = (live.get("banks") or {}).get("default") or {}
        draft_default = (draft.get("banks") or {}).get("default") or {}
        default = merged.setdefault("banks", {}).setdefault("default", {})
        for bank in _ROLE_BANKS:
            live_list = live_default.get(bank) if isinstance(live_default.get(bank), list) else []
            draft_list = draft_default.get(bank) if isinstance(draft_default.get(bank), list) else []
            kept = [str(item) for item in live_list if str(item) not in placement_changed]
            added = [str(item) for item in draft_list if str(item) in moved_set and str(item) not in deleted]
            default[bank] = _dedupe(kept + added)

        # color_engine: everything from LIVE; only the three per-look maps merge.
        engine = merged.setdefault("color_engine", {})
        draft_engine = draft.get("color_engine") or {}
        for key in ("slot_fill_strategy_by_look", "slot_mono_chance_by_look", "locked_palette_by_look"):
            merged_map = dict(engine.get(key)) if isinstance(engine.get(key), dict) else {}
            draft_map = draft_engine.get(key) if isinstance(draft_engine.get(key), dict) else {}
            for name in touched:
                if name in draft_map:
                    merged_map[name] = copy.deepcopy(draft_map[name])
                else:
                    merged_map.pop(name, None)
            for name in deleted:
                merged_map.pop(name, None)
            engine[key] = merged_map

        # _pad_meta: pad-owned, taken from the draft. The session bookkeeping is
        # pad-internal and never belongs in the operator's live config.
        merged_meta = copy.deepcopy(draft.get("_pad_meta") or {})
        merged_meta.pop("pad_session", None)
        merged["_pad_meta"] = merged_meta

        return merged

    def commit(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            draft = copy.deepcopy(self._draft)
            _ensure_pad_meta(draft)
            _default_bank(draft)
            live = _load_json(self._config_path) if self._config_path.exists() else {}
            _ensure_pad_meta(live)
            _default_bank(live)
            merged = self._merged_commit_config(draft, live)
            errors, warnings = self._validate(merged)
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings}
            backup = save_config_atomically(merged, self._config_path)
            # Rebase: next commit starts clean — draft == what we just wrote, and
            # touched/deleted tracking resets (re-added empty by _ensure_pad_meta).
            self._draft = copy.deepcopy(merged)
            self._persist_draft_locked()
            self._write_draft_base()
            self._last_commit_at = time.time()
        return {
            "ok": True,
            "backup_path": str(backup) if backup else "",
            "restart_note": "Pad edits saved — your lights will use them at the next bridge start.",
        }

    def discard(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            self._draft = _load_json(self._config_path)
            _ensure_pad_meta(self._draft)
            _default_bank(self._draft)
            self._draft_path.unlink(missing_ok=True)
            self._write_draft_base()
        return self.get_config_payload()

    def history(self) -> dict[str, Any]:
        items = sorted(self._config_path.parent.glob(f"{self._config_path.name}.bak-*"), reverse=True)
        return {"ok": True, "history": [{"name": item.name, "path": str(item), "size": item.stat().st_size} for item in items]}

    def history_diff(self, name: str) -> dict[str, Any]:
        path = self._config_path.parent / name
        if not path.name.startswith(f"{self._config_path.name}.bak-") or not path.exists():
            raise ValueError("unknown backup")
        old = path.read_text(encoding="utf-8").splitlines()
        current = json.dumps(self._draft, indent=2, sort_keys=True).splitlines()
        diff = "\n".join(difflib.unified_diff(old, current, fromfile=path.name, tofile="draft", lineterm=""))
        return {"ok": True, "name": name, "diff": diff}

    def history_restore(self, name: str) -> dict[str, Any]:
        path = self._config_path.parent / name
        if not path.name.startswith(f"{self._config_path.name}.bak-") or not path.exists():
            raise ValueError("unknown backup")
        config = _load_json(path)
        _ensure_pad_meta(config)
        _default_bank(config)
        errors, warnings = self._validate(config)
        if errors:
            return {"ok": False, "errors": errors, "warnings": warnings}
        # Restore brings back the backup's full look + bank state while unmanaged
        # live top-level blocks (f2/f4/…) stay from live. Mark every restored look
        # touched (its content overlays live) AND moved (its role-bank placement
        # is restored) — without moved, merge-commit keeps live placement and the
        # restore wouldn't actually put looks back in their backed-up banks. Looks
        # that exist only in live (added since the backup) are preserved, not
        # deleted, so a restore never destroys newer work.
        names = sorted((config.get("looks") or {}).keys())
        config["_pad_meta"]["pad_session"] = {"touched": names, "moved": names, "deleted": []}
        with self._lock:
            self._draft = config
            self._persist_draft_locked()
            self._write_draft_base()
        return {"ok": True, "errors": [], "warnings": warnings, "dirty": self._dirty_for(config)}

    def _bridge_started_at(self, bridge: dict[str, Any]) -> float | None:
        """Resolve bridge process start from status process.pid (AWR-255)."""
        proc = bridge.get("process")
        if not isinstance(proc, dict):
            return None
        raw_pid = proc.get("pid")
        try:
            pid = int(raw_pid)
        except (TypeError, ValueError):
            return None
        if pid <= 0:
            return None
        return process_start_time(pid)

    def _config_mtime(self) -> float | None:
        try:
            return float(self._config_path.stat().st_mtime)
        except OSError:
            return None

    def runtime_status(self, *, now: float | None = None) -> dict[str, Any]:
        """Pad runtime snapshot. ``now`` is a test seam for status freshness."""
        now_s = float(now) if now is not None else time.time()
        bridge: dict[str, Any] = {
            "live": False,
            "path": str(self._status_path),
            "state": "not_running",
        }
        try:
            raw = json.loads(self._status_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                bridge.update(raw)
                fresh = status_file_is_fresh(raw.get("written_at"), now=now_s)
                bridge["live"] = fresh
                bridge["state"] = "running" if fresh else "not_running"
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            pass
        playback = self._playback.status()
        live = bool(bridge.get("live"))
        config_stale = compute_config_stale(
            config_mtime=self._config_mtime(),
            bridge_started_at=self._bridge_started_at(bridge) if live else None,
            last_commit_at=self._last_commit_at,
            now=now_s,
            bridge_live=live,
        )
        return {
            "ok": True,
            "bridge": bridge,
            "ownership": self._playback.ownership(),
            "playing_look": playback.get("playing_look", ""),
            "playback": playback,
            "config_stale": config_stale,
        }


def build_handler(service: LedPadService) -> type[BaseHTTPRequestHandler]:
    class _LedPadHandler(BaseHTTPRequestHandler):
        _GET_ROUTES = {
            "/api/config": service.get_config_payload,
            "/api/renders": service.get_renders,
            "/api/palettes": service.get_palettes,
            "/api/history": service.history,
            "/api/runtime_status": service.runtime_status,
            "/api/lab/list": service.lab_list,
            "/api/sim/profile": sim_profile_response,
        }
        _POST_ROUTES = {
            "/api/look/save": service.save_look,
            "/api/look/duplicate": service.duplicate_look,
            "/api/look/rename": service.rename_look,
            "/api/look/move": service.move_look,
            "/api/look/delete": service.delete_look,
            "/api/play": service.play,
            "/api/update": service.update,
            "/api/stop": service.stop,
            "/api/emergency_stop": service.emergency_stop,
            "/api/takeover": service.takeover,
            "/api/release": service.release,
            "/api/session": service.session,
            "/api/commit": service.commit,
            "/api/discard": service.discard,
            "/api/lab/save": service.lab_save,
            "/api/lab/play": service.lab_play,
            "/api/lab/update": service.lab_update,
            "/api/lab/switch": service.lab_switch,
            "/api/lab/preview": service.lab_preview,
            "/api/lab/reload": service.lab_reload,
            "/api/lab/accept": service.lab_accept,
            "/api/lab/reject": service.lab_reject,
            "/api/lab/archive": service.lab_archive,
            "/api/lab/delete": service.lab_delete,
        }

        def log_message(self, fmt: str, *args: object) -> None:
            logger.info("%s - %s", self.address_string(), fmt % args)

        def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(raw)

        def _send_file(self, path: Path) -> None:
            if not path.exists() or not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            raw = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(raw)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _stream_mirror(self) -> None:
            """SSE fan-out of the pad send ring — never runs on the runner thread."""
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            last_ts: float | None = None
            last_playing: bool | None = None
            ring = service.mirror_ring()
            while not service.shutting_down():
                playing = False
                look = ""
                try:
                    st = service._playback.status()
                    playing = bool(st.get("playing"))
                    look = str(st.get("playing_look") or "")
                except Exception:
                    playing = False
                    look = ""
                entry = ring.latest() if ring is not None else None
                payload: dict[str, Any] | None = None
                if entry is not None:
                    ts, frame = entry
                    if last_ts is None or ts != last_ts or playing != last_playing:
                        last_ts = ts
                        last_playing = playing
                        payload = {
                            "ts": ts,
                            "rgb": [list(px) for px in frame],
                            "playing": playing,
                            "playing_look": look,
                        }
                elif last_ts is None or playing != last_playing:
                    last_playing = playing
                    if last_ts is None:
                        last_ts = -1.0
                    payload = {
                        "ts": None,
                        "rgb": None,
                        "playing": playing,
                        "playing_look": look,
                    }
                if payload is not None:
                    raw = f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode("utf-8")
                    try:
                        self.wfile.write(raw)
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                time.sleep(_MIRROR_SSE_INTERVAL_S)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/":
                    # AWR-271 R9a: one shell document for Pad + Lab (view from path).
                    self._send_file(_ASSETS_DIR / "index.html")
                    return
                if path == "/lab":
                    # AWR-273 / N8: /lab bookmarks → shell lab view (never 404).
                    self.send_response(HTTPStatus.FOUND)  # 302
                    self.send_header("Location", "/?view=lab")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    return

                if path == "/api/access":
                    self._send_json(
                        access_payload(self.server.server_address[0], self.server.server_address[1])
                    )
                    return
                # AWR-269: live-play mirror SSE (handler thread only; never the runner).
                if path == "/api/mirror/stream":
                    self._stream_mirror()
                    return
                # AWR-245/AWR-266: sim modules served read-only from disk (not under pad assets).
                if path == "/static/sim/ledsim-view.js":
                    self._send_file(_SIM_VIEW_JS)
                    return
                if path == "/static/sim/ledsim-player.js":
                    self._send_file(_SIM_PLAYER_JS)
                    return
                if path.startswith("/static/"):
                    target = (_ASSETS_DIR / path.removeprefix("/static/")).resolve()
                    if _ASSETS_DIR.resolve() not in target.parents:
                        self.send_error(HTTPStatus.FORBIDDEN)
                        return
                    self._send_file(target)
                    return
                if path.startswith("/api/history/") and path.endswith("/diff"):
                    name = path.removeprefix("/api/history/").removesuffix("/diff")
                    self._send_json(service.history_diff(name))
                    return
                route = self._GET_ROUTES.get(path)
                if route is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._send_json(route())
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path.startswith("/api/history/") and path.endswith("/restore"):
                    name = path.removeprefix("/api/history/").removesuffix("/restore")
                    self._send_json(service.history_restore(name))
                    return
                route = self._POST_ROUTES.get(path)
                if route is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._send_json(route(self._read_json()))
            except (StaleLabEntry, StaleLook) as exc:
                self._send_json(
                    {
                        "ok": False,
                        "error": exc.code,
                        "message": str(exc),
                        "name": exc.name,
                        "disk_updated": exc.disk_updated,
                        "client_updated": exc.client_updated,
                    },
                    status=HTTPStatus.CONFLICT,
                )
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    return _LedPadHandler


def _freshness_watchdog(service: LedPadService) -> None:
    baseline = _sample_watched_mtimes()
    previous = baseline
    last_change = time.monotonic()
    while True:
        time.sleep(5.0)
        current = _sample_watched_mtimes()
        if current != previous:
            previous = current
            last_change = time.monotonic()
        playing = bool(service._playback.status().get("playing"))
        pad_owned = service._playback.ownership().get("state") == "pad_owned"
        if freshness_restart_due(
            baseline,
            current,
            playing=playing,
            pad_owned=pad_owned,
            stable_age_s=time.monotonic() - last_change,
        ):
            logger.info("source changed on disk — restarting for freshness")
            os._exit(3)


def _resolve_bind_host(value: str) -> str:
    if value == "localhost":
        return "127.0.0.1"
    if value == "lan":
        return "0.0.0.0"
    return value


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
    config_path: Path | str | None = None,
    dry_run: bool = False,
) -> ThreadingHTTPServer:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    host = _resolve_bind_host(host)
    if not _is_loopback_host(host):
        print(
            f"WARNING: led_pad_web is exposed to non-loopback {host}; local-only safety assumption is disabled.",
            file=sys.stderr,
        )
    service = LedPadService(config_path=config_path, dry_run=dry_run)
    threading.Thread(target=_freshness_watchdog, args=(service,), name="LedPadFreshness", daemon=True).start()
    server = ThreadingHTTPServer((host, int(port)), build_handler(service))
    setattr(server, "led_pad_service", service)
    logger.info("LED Pad listening on http://%s:%s", host, port)
    try:
        server.serve_forever()
    finally:
        service.shutdown()
        server.server_close()
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local LED Pad web UI")
    parser.add_argument("--host", "--bind", dest="host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--config", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Use the realtime dry-run transport")
    args = parser.parse_args(argv)
    try:
        run_server(host=args.host, port=args.port, config_path=args.config, dry_run=args.dry_run)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"led_pad: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
