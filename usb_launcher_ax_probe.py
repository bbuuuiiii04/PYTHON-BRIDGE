#!/usr/bin/env python3
"""Dormant Rekordbox Accessibility MEASUREMENT probe (AWR-222).

Diagnostic only. Not a bridge reader. Does not emit BridgeEvents, does not
start the bridge, and must never be executed during the software-only
implementation round. All live AX / TCC / AppKit UI paths are injectable so
unit tests never touch Accessibility.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

# ── Fixed identity / paths ───────────────────────────────────────────────────

BRIDGE_BUNDLE_ID = "com.bbui.rb-ss-bridge-v2"
REKORDBOX_BUNDLE_ID = "com.pioneerdj.rekordboxdj"
APP_NAME = "RBSS Bridge.app"
EXPECTED_BUNDLE_VERSION = "0.0.1"
BRIDGE_LOCK_PATH = "/tmp/rb_ss_bridge_v2.lock"
SHAREABLE_SCHEMA_VERSION = 1

DIAGNOSTICS_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "RBSS Bridge"
    / "diagnostics"
    / "rekordbox_ax"
)

TREE_MAX_DEPTH = 24
TREE_MAX_ELEMENTS = 2500
TREE_MAX_SCALAR = 1000
TREE_MAX_WALL_S = 10.0
AX_MSG_TIMEOUT_S = 1.0
POLL_HZ = 10.0
LSOF_MAX_HZ = 2.0
CANNOT_COMPLETE_LIMIT = 3

# Geometry quantization (points) for shareable grouping evidence.
_GEO_QUANT = 8.0

# Shareable length buckets (inclusive upper bounds).
_LENGTH_BUCKETS = (
    (0, "empty"),
    (8, "tiny"),
    (32, "short"),
    (128, "medium"),
    (512, "long"),
    (None, "huge"),
)

_PRIVATE_PATH_MARKERS = (
    str(Path.home()),
    "/Volumes/",
    "/private/var/",
    "/Users/",
)

_SECRET_KEY_NAMES = frozenset({
    "hmac_key", "run_hmac_key", "key", "api_key", "GOVEE_API_KEY",
})


# ── Pure helpers (test seams) ────────────────────────────────────────────────


def normalize_text(value: object) -> str:
    """NFKC + casefold + whitespace collapse — matches filepath_resolver USB tags."""
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def length_bucket(n: int) -> str:
    for upper, name in _LENGTH_BUCKETS:
        if upper is None or n <= upper:
            return name
    return "huge"


def format_class(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return "empty_string"
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return "numeric_string"
        if ":" in s and re.search(r"\d", s):
            return "timed_string"
        if "/" in s or "\\" in s:
            return "pathlike_string"
        return "text"
    if isinstance(value, (list, tuple)):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def shape_token(text: str) -> str:
    """Stable non-revealing shape for layout/language/identifier strings."""
    raw = str(text or "")
    if not raw:
        return "empty"
    letters = sum(ch.isalpha() for ch in raw)
    digits = sum(ch.isdigit() for ch in raw)
    other = len(raw) - letters - digits
    return f"L{letters}_D{digits}_O{other}_N{len(raw)}"


def quantize_geometry(pos: object, size: object) -> dict[str, float | None]:
    def _q(pair: object) -> tuple[float | None, float | None]:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            return None, None
        try:
            a = float(pair[0])
            b = float(pair[1])
        except (TypeError, ValueError):
            return None, None
        return round(a / _GEO_QUANT) * _GEO_QUANT, round(b / _GEO_QUANT) * _GEO_QUANT

    x, y = _q(pos)
    w, h = _q(size)
    return {"x": x, "y": y, "w": w, "h": h}


class TokenVault:
    """Per-run HMAC tokens. Key stays in private_manifest only."""

    def __init__(self, key: bytes | None = None) -> None:
        self.key = key if key is not None else secrets.token_bytes(32)
        self._cache: dict[str, str] = {}

    def token_for(self, value: object) -> str:
        norm = normalize_text(value)
        if not norm:
            return "empty"
        cached = self._cache.get(norm)
        if cached is not None:
            return cached
        digest = hmac.new(self.key, norm.encode("utf-8"), hashlib.sha256).hexdigest()
        token = digest[:24]
        self._cache[norm] = token
        return token

    def hex_key(self) -> str:
        return self.key.hex()


def summarize_cadence(
    intervals_ms: Sequence[float] | None,
    *,
    reference_available: bool,
) -> dict[str, Any]:
    """Pure cadence summary. Never invents action-to-observation latency."""
    if not reference_available:
        return {
            "status": "unmeasured",
            "reason": "no_independent_reference",
            "count": 0,
            "p95_ms": None,
            "max_ms": None,
        }
    if intervals_ms is None:
        return {
            "status": "failed",
            "reason": "intervals_unavailable",
            "count": 0,
            "p95_ms": None,
            "max_ms": None,
        }
    values = [float(v) for v in intervals_ms if isinstance(v, (int, float))]
    if not values:
        return {
            "status": "failed",
            "reason": "empty_intervals",
            "count": 0,
            "p95_ms": None,
            "max_ms": None,
        }
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    return {
        "status": "measured",
        "reason": "ok",
        "count": len(ordered),
        "p95_ms": ordered[idx],
        "max_ms": ordered[-1],
    }


def match_sidecar_identity(
    *,
    title: object,
    artist: object,
    duration_s: float | None,
    records: Sequence[Mapping[str, Any]],
    duration_tolerance_s: float,
) -> dict[str, Any]:
    """Exact title+artist(+duration) uniqueness. Abstain on ambiguity."""
    nt = normalize_text(title)
    na = normalize_text(artist)
    if not nt or not na:
        return {
            "status": "ambiguous",
            "reason": "title_only_or_missing_artist" if nt else "missing_title",
            "match_count": 0,
            "content_tokens": [],
        }
    tagged = [
        r for r in records
        if normalize_text(r.get("title")) == nt and normalize_text(r.get("artist")) == na
    ]
    if duration_s is not None:
        tagged = [
            r for r in tagged
            if abs(float(r.get("duration_s", -1e9)) - float(duration_s))
            <= float(duration_tolerance_s)
        ]
    if len(tagged) == 1:
        return {
            "status": "unique",
            "reason": "exact_title_artist_duration" if duration_s is not None
            else "exact_title_artist",
            "match_count": 1,
            "content_tokens": [str(tagged[0].get("content_id", ""))],
        }
    if not tagged:
        return {
            "status": "ambiguous",
            "reason": "no_match",
            "match_count": 0,
            "content_tokens": [],
        }
    return {
        "status": "ambiguous",
        "reason": "multiple_matches",
        "match_count": len(tagged),
        "content_tokens": [str(r.get("content_id", "")) for r in tagged],
    }


def classify_lsof_candidates(paths: Sequence[str]) -> dict[str, Any]:
    """Process-wide candidates only — never a deck assignment."""
    return {
        "candidate_count": len(paths),
        "deck_assignment": None,
        "identity": "process_wide_set",
        "unique_deck": False,
        "extensions": sorted({
            Path(p).suffix.lower().lstrip(".") or "none" for p in paths
        }),
    }


# ── Sanitizer (fail-closed) ──────────────────────────────────────────────────


class SanitizerFailure(Exception):
    """Shareable record contained a private/secret string."""


def _looks_like_ip(text: str) -> bool:
    return bool(re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text))


def _looks_like_exception(text: str) -> bool:
    return "Traceback (most recent call last)" in text or (
        "Error:" in text and "\n" in text
    )


def sanitize_value(
    value: Any,
    *,
    hmac_key_hex: str,
    private_literals: Sequence[str] = (),
) -> Any:
    """Recursively sanitize. Raises SanitizerFailure on private leakage."""
    banned = [hmac_key_hex] if hmac_key_hex else []
    banned.extend(str(x) for x in private_literals if x)
    return _sanitize_walk(value, banned=banned, path="$")


def _sanitize_walk(value: Any, *, banned: Sequence[str], path: str) -> Any:
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            key_s = str(key)
            if key_s in _SECRET_KEY_NAMES:
                raise SanitizerFailure(f"secret_key_name:{path}.{key_s}")
            out[key_s] = _sanitize_walk(item, banned=banned, path=f"{path}.{key_s}")
        return out
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_walk(item, banned=banned, path=f"{path}[{i}]")
            for i, item in enumerate(value)
        ]
    if isinstance(value, bytes):
        raise SanitizerFailure(f"raw_bytes:{path}")
    if isinstance(value, str):
        _reject_private_string(value, banned=banned, path=path)
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    raise SanitizerFailure(f"unsupported_type:{path}:{type(value).__name__}")


def _reject_private_string(text: str, *, banned: Sequence[str], path: str) -> None:
    if not text:
        return
    for marker in banned:
        if marker and marker in text:
            raise SanitizerFailure(f"banned_literal:{path}")
    for marker in _PRIVATE_PATH_MARKERS:
        if marker and marker in text:
            raise SanitizerFailure(f"path_marker:{path}")
    lower = text.casefold()
    if "source_filepath" in lower:
        raise SanitizerFailure(f"source_filepath:{path}")
    if re.search(r"\.(mp3|wav|flac|aiff|m4a|aac)\b", lower):
        raise SanitizerFailure(f"audio_basename:{path}")
    if _looks_like_ip(text):
        raise SanitizerFailure(f"ip:{path}")
    if _looks_like_exception(text):
        raise SanitizerFailure(f"exception_text:{path}")
    # Hex HMAC key leakage (64 hex chars for 32-byte key).
    if re.fullmatch(r"[0-9a-f]{64}", lower):
        raise SanitizerFailure(f"hmac_key_hex:{path}")


# ── Evidence writer ──────────────────────────────────────────────────────────


@dataclass
class EvidenceSink:
    run_dir: Path
    vault: TokenVault
    private_literals: list[str] = field(default_factory=list)
    sequence: int = 0
    shareable_ok: bool = True
    sanitizer_error: str | None = None

    def __post_init__(self) -> None:
        self.run_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.run_dir, 0o700)
        self._private_path = self.run_dir / "private.jsonl"
        self._shareable_path = self.run_dir / "shareable.jsonl"
        self._manifest_path = self.run_dir / "private_manifest.json"
        self._summary_path = self.run_dir / "summary.json"
        for path in (self._private_path, self._shareable_path):
            path.touch(mode=0o600, exist_ok=True)
            os.chmod(path, 0o600)

    def next_seq(self) -> int:
        self.sequence += 1
        return self.sequence

    def append_private(self, record: Mapping[str, Any]) -> None:
        self._append_jsonl(self._private_path, dict(record))

    def append_shareable(self, record: Mapping[str, Any]) -> None:
        if not self.shareable_ok:
            return
        try:
            clean = sanitize_value(
                dict(record),
                hmac_key_hex=self.vault.hex_key(),
                private_literals=self.private_literals,
            )
        except SanitizerFailure as exc:
            self.shareable_ok = False
            self.sanitizer_error = type(exc).__name__
            self.append_private({
                "event": "sanitizer_failure",
                "error_class": type(exc).__name__,
                "detail": str(exc),
            })
            return
        self._append_jsonl(self._shareable_path, clean)

    def write_manifest(self, payload: Mapping[str, Any]) -> None:
        body = {
            "DO_NOT_SHARE": True,
            "warning": "PRIVATE — contains run HMAC key and exact paths. Never share.",
            "hmac_key": self.vault.hex_key(),
            **dict(payload),
        }
        self._atomic_json(self._manifest_path, body, mode=0o600)

    def write_summary(self, payload: Mapping[str, Any]) -> None:
        if not self.shareable_ok:
            safe = {
                "schema_version": SHAREABLE_SCHEMA_VERSION,
                "status": "failed",
                "error_class": "sanitizer_failure",
                "sanitizer_error": self.sanitizer_error or "unknown",
                "shareable_truncated": True,
            }
            self._atomic_json(self._summary_path, safe, mode=0o600)
            return
        try:
            clean = sanitize_value(
                dict(payload),
                hmac_key_hex=self.vault.hex_key(),
                private_literals=self.private_literals,
            )
        except SanitizerFailure as exc:
            self.shareable_ok = False
            self.sanitizer_error = type(exc).__name__
            self.write_summary({})  # writes minimal safe summary
            self.append_private({
                "event": "sanitizer_failure",
                "error_class": type(exc).__name__,
                "detail": str(exc),
            })
            return
        self._atomic_json(self._summary_path, clean, mode=0o600)

    @staticmethod
    def _append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        tmp = path.with_suffix(path.suffix + ".tmp")
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        tmp.write_text(existing + line + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)

    @staticmethod
    def _atomic_json(path: Path, payload: Mapping[str, Any], *, mode: int) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        os.chmod(path, mode)


# ── Facades / deps ───────────────────────────────────────────────────────────


@dataclass
class BundleInfo:
    bundle_id: str
    version: str
    bundle_path: str
    installed_class: str  # installed | dmg | translocated | source | unknown
    signing_identity_class: str  # ad_hoc | development | distribution | unknown


@dataclass
class TargetApp:
    pid: int
    version: str
    bundle_id: str


@dataclass
class AxNode:
    element_id: int
    parent_id: int | None
    depth: int
    child_ordinal: int
    role: str | None = None
    subrole: str | None = None
    identifier: str | None = None
    title: Any = None
    value: Any = None
    description: Any = None
    help: Any = None
    enabled: Any = None
    focused: Any = None
    selected: Any = None
    position: Any = None
    size: Any = None
    attribute_names: tuple[str, ...] = ()
    action_names: tuple[str, ...] = ()
    scalar: bool = False


@dataclass
class ProbeDeps:
    """Injected facades. Tests supply fakes; live path builds macOS facades lazily."""

    is_frozen: Callable[[], bool]
    read_bundle: Callable[[], BundleInfo]
    bridge_live_pid: Callable[[], int | None]
    ax_trusted: Callable[[bool], bool]
    show_permission_explanation: Callable[[], None]
    show_consent_panel: Callable[[], bool]
    find_rekordbox: Callable[[], list[TargetApp]]
    create_app_element: Callable[[int], Any]
    set_messaging_timeout: Callable[[Any, float], None]
    copy_attribute_names: Callable[[Any], tuple[str, ...] | None]
    copy_attribute: Callable[[Any, str], tuple[Any, str | None]]
    copy_multiple: Callable[[Any, Sequence[str]], tuple[Mapping[str, Any], str | None]]
    copy_action_names: Callable[[Any], tuple[str, ...] | None]
    copy_children: Callable[[Any], Sequence[Any] | None]
    element_identity: Callable[[Any], int]
    register_observers: Callable[[Any, Callable[..., None]], dict[str, str]]
    run_observer_slice: Callable[[float], None]
    lsof_audio_files: Callable[[str], list[str]]
    load_installed_sidecar: Callable[[], tuple[bool, tuple[dict, ...]]]
    mounted_sidecar_indexes: Callable[[], Any]
    now_mono_ns: Callable[[], int]
    now_utc: Callable[[], datetime]
    sleep: Callable[[float], None]
    stderr_write: Callable[[str], None] = field(
        default_factory=lambda: (lambda msg: sys.stderr.write(msg))
    )
    diagnostics_root: Path = DIAGNOSTICS_ROOT


# ── Preflight ────────────────────────────────────────────────────────────────


def read_bridge_live_pid(lock_path: str = BRIDGE_LOCK_PATH) -> int | None:
    """Read lock PID without creating/locking. Live PID => refuse."""
    try:
        with open(lock_path, "r", encoding="utf-8") as fp:
            pid = int(fp.readline().strip())
    except (OSError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def classify_install_path(bundle_path: str, *, frozen: bool | None = None) -> str:
    lowered = bundle_path.replace("\\", "/")
    if "/AppTranslocation/" in lowered:
        return "translocated"
    if ".dmg/" in lowered.lower() or (
        "/Volumes/" in lowered and "/RBSS Bridge.app" in lowered
    ):
        return "dmg"
    is_frozen = bool(getattr(sys, "frozen", False) if frozen is None else frozen)
    if not is_frozen:
        return "source"
    return "installed"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="usb_launcher --probe-rekordbox-accessibility",
        description="Dormant Rekordbox Accessibility measurement probe (AWR-222).",
    )
    parser.add_argument("--duration-s", type=int, default=120)
    parser.add_argument("--layout", default=None)
    parser.add_argument("--language", default=None)
    parser.add_argument(
        "--prompt-permission",
        action="store_true",
        default=False,
        help="After native Continue consent, request an Accessibility prompt.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not (10 <= int(args.duration_s) <= 900):
        parser.error("--duration-s must be an integer 10..900")
    return args


def _fail(deps: ProbeDeps, message: str, code: int = 1) -> int:
    deps.stderr_write(f"ax-probe: {message}\n")
    return code


def preflight_bundle(deps: ProbeDeps) -> tuple[BundleInfo | None, str | None]:
    if not deps.is_frozen():
        return None, "source_run_refused"
    info = deps.read_bundle()
    if info.bundle_id != BRIDGE_BUNDLE_ID:
        return None, "wrong_bundle_id"
    if not info.bundle_path.replace("\\", "/").endswith(APP_NAME) and (
        f"/{APP_NAME}/" not in info.bundle_path.replace("\\", "/")
    ):
        # Require enclosing RBSS Bridge.app somewhere in the path.
        if APP_NAME not in info.bundle_path:
            return None, "missing_app_bundle"
    installed = classify_install_path(info.bundle_path, frozen=True)
    if installed in {"dmg", "translocated", "source"}:
        return None, f"install_class_{installed}"
    info.installed_class = installed
    if info.version != EXPECTED_BUNDLE_VERSION:
        return None, "bundle_version_mismatch"
    return info, None


# ── Tree walk ────────────────────────────────────────────────────────────────


_SCALAR_ATTRS = (
    "title", "value", "description", "help", "enabled", "focused", "selected",
    "position", "size", "identifier", "role", "subrole",
)


def walk_ax_tree(
    root: Any,
    deps: ProbeDeps,
    *,
    max_depth: int = TREE_MAX_DEPTH,
    max_elements: int = TREE_MAX_ELEMENTS,
    max_scalar: int = TREE_MAX_SCALAR,
    max_wall_s: float = TREE_MAX_WALL_S,
) -> tuple[list[AxNode], dict[str, Any]]:
    started = deps.now_mono_ns()
    seen: set[int] = set()
    nodes: list[AxNode] = []
    scalar_count = 0
    incomplete = False
    incomplete_reason: str | None = None
    queue: deque[tuple[Any, int | None, int, int]] = deque()
    queue.append((root, None, 0, 0))

    deps.set_messaging_timeout(root, AX_MSG_TIMEOUT_S)

    while queue:
        elapsed = (deps.now_mono_ns() - started) / 1e9
        if elapsed > max_wall_s:
            incomplete = True
            incomplete_reason = "wall_time"
            break
        if len(nodes) >= max_elements:
            incomplete = True
            incomplete_reason = "element_cap"
            break

        element, parent_id, depth, ordinal = queue.popleft()
        eid = deps.element_identity(element)
        if eid in seen:
            continue
        seen.add(eid)
        if depth > max_depth:
            incomplete = True
            incomplete_reason = incomplete_reason or "depth_cap"
            continue

        names = deps.copy_attribute_names(element) or ()
        advertised = set(names)
        fields: dict[str, Any] = {}
        for attr in _SCALAR_ATTRS:
            # Read only attributes the element advertises.
            # Role/subrole often appear under AXRole / AXSubrole — accept either.
            candidates = {attr, f"AX{attr[:1].upper()}{attr[1:]}", attr.upper()}
            hit = next((c for c in candidates if c in advertised), None)
            if hit is None and attr in {"role", "subrole", "title", "value"}:
                # Common AX names when the facade uses canonical short names.
                hit = attr if attr in advertised else None
            if hit is None:
                continue
            value, err = deps.copy_attribute(element, hit)
            fields[attr] = value if err is None else {"error": err}

        actions = deps.copy_action_names(element) or ()
        is_scalar = any(
            fields.get(k) not in (None, "", {"error": "unsupported"})
            for k in ("title", "value", "description", "identifier")
        )
        if is_scalar:
            scalar_count += 1
            if scalar_count > max_scalar:
                incomplete = True
                incomplete_reason = incomplete_reason or "scalar_cap"
                is_scalar = False

        node = AxNode(
            element_id=eid,
            parent_id=parent_id,
            depth=depth,
            child_ordinal=ordinal,
            role=_as_str(fields.get("role")),
            subrole=_as_str(fields.get("subrole")),
            identifier=_as_str(fields.get("identifier")),
            title=fields.get("title"),
            value=fields.get("value"),
            description=fields.get("description"),
            help=fields.get("help"),
            enabled=fields.get("enabled"),
            focused=fields.get("focused"),
            selected=fields.get("selected"),
            position=fields.get("position"),
            size=fields.get("size"),
            attribute_names=tuple(names),
            action_names=tuple(actions),
            scalar=is_scalar,
        )
        nodes.append(node)

        children = deps.copy_children(element) or ()
        for idx, child in enumerate(children):
            cid = deps.element_identity(child)
            if cid in seen:
                continue
            queue.append((child, eid, depth + 1, idx))

    meta = {
        "tree_incomplete": incomplete,
        "incomplete_reason": incomplete_reason,
        "element_count": len(nodes),
        "scalar_count": sum(1 for n in nodes if n.scalar),
        "wall_s": (deps.now_mono_ns() - started) / 1e9,
    }
    return nodes, meta


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict) and "error" in value:
        return None
    return str(value)


def build_grouping_candidates(nodes: Sequence[AxNode]) -> list[dict[str, Any]]:
    """Grouping candidates only — never assign deck 1/2."""
    by_parent: dict[int | None, list[AxNode]] = {}
    for node in nodes:
        by_parent.setdefault(node.parent_id, []).append(node)

    candidates: list[dict[str, Any]] = []
    role_shapes: dict[tuple[Any, ...], list[int]] = {}
    for parent_id, children in by_parent.items():
        shape = tuple(
            (c.role, c.subrole, length_bucket(len(str(c.title or ""))))
            for c in children
        )
        if len(children) >= 2:
            role_shapes.setdefault(shape, []).append(parent_id if parent_id is not None else -1)

    for shape, parents in role_shapes.items():
        if len(parents) >= 2:
            candidates.append({
                "kind": "mirrored_subtree_shape",
                "reason": "repeated_child_role_shape",
                "parent_count": len(parents),
                "shape_hash": hashlib.sha256(repr(shape).encode()).hexdigest()[:16],
                "deck_assignment": None,
            })

    ancestry: dict[str, int] = {}
    for node in nodes:
        if not node.scalar:
            continue
        fp = f"{node.depth}:{node.role}:{node.subrole}:{node.child_ordinal}"
        ancestry[fp] = ancestry.get(fp, 0) + 1
    repeated = [fp for fp, n in ancestry.items() if n >= 2]
    if repeated:
        candidates.append({
            "kind": "stable_ancestry_fingerprint",
            "reason": "repeated_depth_role_ordinal",
            "fingerprint_count": len(repeated),
            "deck_assignment": None,
        })

    geo_buckets: dict[tuple[Any, ...], int] = {}
    for node in nodes:
        geo = quantize_geometry(node.position, node.size)
        key = (geo["x"], geo["y"], geo["w"], geo["h"], node.role)
        if None in key[:4]:
            continue
        geo_buckets[key] = geo_buckets.get(key, 0) + 1
    mirrored_geo = sum(1 for n in geo_buckets.values() if n >= 2)
    if mirrored_geo:
        candidates.append({
            "kind": "quantized_geometry",
            "reason": "mirrored_or_repeated_boxes",
            "bucket_count": mirrored_geo,
            "deck_assignment": None,
        })
    return candidates


def node_shareable_record(
    node: AxNode,
    *,
    vault: TokenVault,
    run_id: str,
    seq: int,
    utc: str,
    mono_ns: int,
    source: str,
    call_duration_ms: float | None = None,
    ax_error: str | None = None,
) -> dict[str, Any]:
    title_s = "" if node.title is None else str(node.title)
    value_s = "" if node.value is None else str(node.value)
    desc_s = "" if node.description is None else str(node.description)
    return {
        "schema_version": SHAREABLE_SCHEMA_VERSION,
        "run_id": run_id,
        "sequence": seq,
        "utc": utc,
        "monotonic_ns": mono_ns,
        "source": source,
        "node_token": vault.token_for(f"node:{node.element_id}"),
        "parent_token": (
            None if node.parent_id is None
            else vault.token_for(f"node:{node.parent_id}")
        ),
        "depth": node.depth,
        "child_ordinal": node.child_ordinal,
        "role": node.role,
        "subrole": node.subrole,
        "identifier_shape": shape_token(node.identifier or ""),
        "identifier_token": vault.token_for(node.identifier or ""),
        "title": {
            "type": type(node.title).__name__ if node.title is not None else "null",
            "length_bucket": length_bucket(len(title_s)),
            "format_class": format_class(node.title),
            "token": vault.token_for(title_s),
            "change_count": 0,
        },
        "value": {
            "type": type(node.value).__name__ if node.value is not None else "null",
            "length_bucket": length_bucket(len(value_s)),
            "format_class": format_class(node.value),
            "token": vault.token_for(value_s),
            "change_count": 0,
        },
        "description": {
            "type": type(node.description).__name__ if node.description is not None else "null",
            "length_bucket": length_bucket(len(desc_s)),
            "format_class": format_class(node.description),
            "token": vault.token_for(desc_s),
            "change_count": 0,
        },
        "geometry": quantize_geometry(node.position, node.size),
        "supported_attributes": list(node.attribute_names),
        "supported_actions": list(node.action_names),
        "ax_error": ax_error,
        "call_duration_ms": call_duration_ms,
        "deck_assignment": None,
    }


# ── Capture loop ─────────────────────────────────────────────────────────────


def run_capture(
    deps: ProbeDeps,
    *,
    args: argparse.Namespace,
    bundle: BundleInfo,
    target: TargetApp,
    sink: EvidenceSink,
    run_id: str,
) -> dict[str, Any]:
    app_el = deps.create_app_element(target.pid)
    deps.set_messaging_timeout(app_el, AX_MSG_TIMEOUT_S)

    nodes, tree_meta = walk_ax_tree(app_el, deps)
    observer_outcomes = deps.register_observers(app_el, lambda *a, **k: None)

    # Initial private + shareable tree records
    for node in nodes:
        seq = sink.next_seq()
        utc = deps.now_utc().isoformat()
        mono = deps.now_mono_ns()
        sink.append_private({
            "event": "node",
            "sequence": seq,
            "utc": utc,
            "monotonic_ns": mono,
            "source": "initial",
            "element_id": node.element_id,
            "parent_id": node.parent_id,
            "depth": node.depth,
            "child_ordinal": node.child_ordinal,
            "role": node.role,
            "subrole": node.subrole,
            "identifier": node.identifier,
            "title": node.title,
            "value": node.value,
            "description": node.description,
            "help": node.help,
            "enabled": node.enabled,
            "focused": node.focused,
            "selected": node.selected,
            "position": node.position,
            "size": node.size,
            "attribute_names": list(node.attribute_names),
            "action_names": list(node.action_names),
        })
        sink.append_shareable(node_shareable_record(
            node,
            vault=sink.vault,
            run_id=run_id,
            seq=seq,
            utc=utc,
            mono_ns=mono,
            source="initial",
        ))
        if not sink.shareable_ok:
            break

    # Sidecar + lsof (only after trust + unique target — caller guarantees)
    sidecar_ok, sidecar_records = deps.load_installed_sidecar()
    # Mounted discovery must never be called; keep the hook for tests to explode.
    # Intentionally unused:
    _ = deps.mounted_sidecar_indexes  # noqa: F841 — presence only; never invoke

    lsof_paths = deps.lsof_audio_files(str(target.pid))
    lsof_class = classify_lsof_candidates(lsof_paths)
    for path in lsof_paths:
        sink.private_literals.append(path)
        sink.private_literals.append(Path(path).name)
    sink.append_private({
        "event": "lsof_candidates",
        "paths": list(lsof_paths),
        "classification": lsof_class,
    })
    sink.append_shareable({
        "schema_version": SHAREABLE_SCHEMA_VERSION,
        "run_id": run_id,
        "sequence": sink.next_seq(),
        "utc": deps.now_utc().isoformat(),
        "monotonic_ns": deps.now_mono_ns(),
        "source": "initial",
        "event": "lsof_candidates",
        "candidate_count": lsof_class["candidate_count"],
        "extensions": lsof_class["extensions"],
        "tokens": [sink.vault.token_for(p) for p in lsof_paths],
        "deck_assignment": None,
        "unique_deck": False,
    })

    # Sidecar tokenized equality against AX title/artist scalars
    equality_candidates: list[dict[str, Any]] = []
    for node in nodes:
        if not node.scalar:
            continue
        title = node.title
        artist = node.description if node.description else None
        # Prefer pairing title + a sibling-ish artist only when both look like text.
        match = match_sidecar_identity(
            title=title,
            artist=artist if artist is not None else "",
            duration_s=None,
            records=sidecar_records if sidecar_ok else (),
            duration_tolerance_s=2.0,
        )
        if match["status"] == "unique" or match["match_count"]:
            equality_candidates.append({
                "node_token": sink.vault.token_for(f"node:{node.element_id}"),
                "title_token": sink.vault.token_for(title or ""),
                "artist_token": sink.vault.token_for(artist or ""),
                "status": match["status"],
                "reason": match["reason"],
                "match_count": match["match_count"],
            })

    for record in sidecar_records if sidecar_ok else ():
        for key in ("title", "artist", "content_id", "source_filepath", "fingerprint",
                    "beatgrid_fingerprint"):
            val = record.get(key)
            if isinstance(val, str) and val:
                sink.private_literals.append(val)
        sink.append_private({
            "event": "sidecar_record",
            "content_id": record.get("content_id"),
            "title": record.get("title"),
            "artist": record.get("artist"),
            "duration_s": record.get("duration_s"),
            "bpm": record.get("bpm"),
            "source_filepath": record.get("source_filepath"),
            "beatgrid_fingerprint": record.get("beatgrid_fingerprint"),
        })

    sink.append_shareable({
        "schema_version": SHAREABLE_SCHEMA_VERSION,
        "run_id": run_id,
        "sequence": sink.next_seq(),
        "utc": deps.now_utc().isoformat(),
        "monotonic_ns": deps.now_mono_ns(),
        "source": "initial",
        "event": "sidecar_index",
        "valid": sidecar_ok,
        "track_count": len(sidecar_records) if sidecar_ok else 0,
        "equality_candidates": equality_candidates,
    })

    grouping = build_grouping_candidates(nodes)
    scalar_ids = {n.element_id: n for n in nodes if n.scalar}
    # Poll loop: only scalar-bearing set at 10 Hz.
    deadline = deps.now_mono_ns() + int(float(args.duration_s) * 1e9)
    poll_interval = 1.0 / POLL_HZ
    last_lsof = deps.now_mono_ns()
    cannot_complete = 0
    terminal: dict[str, Any] | None = None
    last_values: dict[int, tuple[Any, Any]] = {
        n.element_id: (n.title, n.value) for n in nodes if n.scalar
    }
    change_intervals_ms: list[float] = []
    last_change_mono: int | None = None

    # Map element_id -> live element is not retained from BFS (opaque). Polling
    # reuses create_app_element + re-walk is forbidden; instead poll via a
    # scalar snapshot API: copy_multiple on nodes we still have as AxNode only
    # stores ids. Live deps may ignore poll if elements aren't retained.
    # For the software path, deps.copy_multiple receives the element_id int when
    # tests pass FakeAx; the live facade re-resolves via retained map.
    retained = getattr(deps, "retained_elements", {})

    while deps.now_mono_ns() < deadline and terminal is None and sink.shareable_ok:
        # Permission / PID loss checks
        if not deps.ax_trusted(False):
            terminal = {"reason": "permission_revoked", "error_class": "revoked"}
            break
        live = deps.bridge_live_pid()
        if live is not None:
            terminal = {"reason": "bridge_became_live", "error_class": "bridge_live"}
            break
        # Target PID loss
        try:
            os.kill(target.pid, 0)
        except OSError:
            terminal = {"reason": "target_quit", "error_class": "target_quit"}
            break

        deps.run_observer_slice(0.0)
        for eid, node in list(scalar_ids.items()):
            element = retained.get(eid, eid)
            t0 = deps.now_mono_ns()
            values, err = deps.copy_multiple(
                element, ("title", "value", "AXTitle", "AXValue")
            )
            dt_ms = (deps.now_mono_ns() - t0) / 1e6
            if err == "cannotComplete":
                cannot_complete += 1
                if cannot_complete >= CANNOT_COMPLETE_LIMIT:
                    terminal = {
                        "reason": "repeated_cannotComplete",
                        "error_class": "cannotComplete",
                    }
                    break
            elif err in {"invalid", "invalidUIElement"}:
                terminal = {"reason": "invalid_element", "error_class": err}
                break
            elif err == "layout_lost":
                terminal = {"reason": "layout_lost", "error_class": "layout_lost"}
                break
            else:
                cannot_complete = 0

            title = values.get("title", values.get("AXTitle"))
            value = values.get("value", values.get("AXValue"))
            prev = last_values.get(eid)
            changed = prev is not None and (title, value) != prev
            last_values[eid] = (title, value)
            if changed:
                now = deps.now_mono_ns()
                if last_change_mono is not None:
                    change_intervals_ms.append((now - last_change_mono) / 1e6)
                last_change_mono = now
                seq = sink.next_seq()
                utc = deps.now_utc().isoformat()
                sink.append_private({
                    "event": "scalar_update",
                    "sequence": seq,
                    "element_id": eid,
                    "title": title,
                    "value": value,
                    "source": "poll",
                    "ax_error": err,
                    "call_duration_ms": dt_ms,
                })
                updated = AxNode(
                    element_id=eid,
                    parent_id=node.parent_id,
                    depth=node.depth,
                    child_ordinal=node.child_ordinal,
                    role=node.role,
                    subrole=node.subrole,
                    identifier=node.identifier,
                    title=title,
                    value=value,
                    description=node.description,
                    attribute_names=node.attribute_names,
                    action_names=node.action_names,
                    scalar=True,
                )
                sink.append_shareable(node_shareable_record(
                    updated,
                    vault=sink.vault,
                    run_id=run_id,
                    seq=seq,
                    utc=utc,
                    mono_ns=now,
                    source="poll",
                    call_duration_ms=dt_ms,
                    ax_error=err,
                ))

            # lsof at most 2 Hz / on scalar change
            now = deps.now_mono_ns()
            if changed or (now - last_lsof) >= int(1e9 / LSOF_MAX_HZ):
                last_lsof = now
                paths = deps.lsof_audio_files(str(target.pid))
                sink.append_private({
                    "event": "lsof_candidates",
                    "paths": list(paths),
                    "classification": classify_lsof_candidates(paths),
                })

        if terminal is not None:
            break
        deps.sleep(poll_interval)

    if terminal is not None:
        sink.append_private({"event": "terminal_unavailable", **terminal})
        sink.append_shareable({
            "schema_version": SHAREABLE_SCHEMA_VERSION,
            "run_id": run_id,
            "sequence": sink.next_seq(),
            "utc": deps.now_utc().isoformat(),
            "monotonic_ns": deps.now_mono_ns(),
            "source": "terminal",
            "event": "unavailable",
            "error_class": terminal.get("error_class"),
            "reason": terminal.get("reason"),
            "held_last_value": False,
        })

    layout_raw = args.layout
    language_raw = args.language
    layout_missing = layout_raw is None
    language_missing = language_raw is None
    validation_incomplete = layout_missing or language_missing

    summary = {
        "schema_version": SHAREABLE_SCHEMA_VERSION,
        "run_id": run_id,
        "status": "failed" if terminal or not sink.shareable_ok else "ok",
        "permission_state": "trusted",
        "bridge_bundle_id": BRIDGE_BUNDLE_ID,
        "rekordbox_bundle_id": REKORDBOX_BUNDLE_ID,
        "bridge_version": bundle.version,
        "rekordbox_version": target.version,
        "installed_class": bundle.installed_class,
        "signing_identity_class": bundle.signing_identity_class,
        "layout_shape": shape_token(layout_raw or ""),
        "layout_token": "unknown" if layout_missing else sink.vault.token_for(layout_raw),
        "language_shape": shape_token(language_raw or ""),
        "language_token": (
            "unknown" if language_missing else sink.vault.token_for(language_raw)
        ),
        "validation_incomplete": validation_incomplete,
        "tree": tree_meta,
        "observer_registration": observer_outcomes,
        "grouping_candidates": grouping,
        "lsof": {
            "candidate_count": lsof_class["candidate_count"],
            "unique_deck": False,
            "deck_assignment": None,
        },
        "sidecar": {
            "valid": sidecar_ok,
            "track_count": len(sidecar_records) if sidecar_ok else 0,
            "equality_candidate_count": len(equality_candidates),
        },
        "cadence": {
            # AX callback intervals alone are never action latency.
            "ax_change_intervals": summarize_cadence(
                change_intervals_ms, reference_available=False
            ),
            "action_latency": summarize_cadence(
                None, reference_available=False
            ),
        },
        "completeness": {
            "tree_incomplete": bool(tree_meta.get("tree_incomplete")),
            "quit": bool(terminal and terminal.get("reason") == "target_quit"),
            "layout_loss": bool(
                terminal and terminal.get("reason") == "layout_lost"
            ),
            "permission_revoked": bool(
                terminal and terminal.get("reason") == "permission_revoked"
            ),
            "sanitizer_truncated": not sink.shareable_ok,
        },
        "pass_fail_unmeasured": {
            "software_dispatch": "pass",
            "ax_fields": "unmeasured",
            "tcc_persistence": "unmeasured",
            "usb_identity": "unmeasured",
            "action_latency": "unmeasured",
            "hardware": "unmeasured",
        },
    }
    return summary


# ── main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None, deps: ProbeDeps | None = None) -> int:
    args = parse_args(argv)
    active = deps if deps is not None else build_live_deps()

    bundle, err = preflight_bundle(active)
    if err is not None:
        return _fail(active, f"preflight refused ({err})")

    assert bundle is not None
    live_pid = active.bridge_live_pid()
    if live_pid is not None:
        return _fail(active, f"bridge already running (pid {live_pid})")

    # Permission check — default never prompts.
    trusted = active.ax_trusted(False)
    permission_state = "trusted" if trusted else "not_trusted"
    prompt_requested = False

    if not trusted and args.prompt_permission:
        if not active.show_consent_panel():
            return _fail(active, "permission consent cancelled")
        prompt_requested = True
        permission_state = "prompt_requested"
        active.ax_trusted(True)  # may prompt
        trusted = active.ax_trusted(False)
        permission_state = "trusted" if trusted else "not_trusted"

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    run_dir = Path(active.diagnostics_root) / run_id
    # Refuse to write outside the fixed diagnostics root.
    try:
        run_dir.resolve().relative_to(Path(active.diagnostics_root).resolve())
    except ValueError:
        return _fail(active, "diagnostics path escaped fixed root")

    vault = TokenVault()
    sink = EvidenceSink(run_dir=run_dir, vault=vault)
    sink.write_manifest({
        "run_id": run_id,
        "argv": list(argv or []),
        "layout": args.layout,
        "language": args.language,
        "bundle_path": bundle.bundle_path,
        "bundle_id": bundle.bundle_id,
        "permission_state": permission_state,
        "prompt_requested": prompt_requested,
    })

    if not trusted:
        active.show_permission_explanation()
        sink.append_private({
            "event": "permission_denied",
            "permission_state": permission_state,
            "prompt_requested": prompt_requested,
        })
        sink.write_summary({
            "schema_version": SHAREABLE_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "failed",
            "permission_state": permission_state,
            "prompt_requested": prompt_requested,
            "bridge_bundle_id": BRIDGE_BUNDLE_ID,
            "installed_class": bundle.installed_class,
            "error_class": "not_trusted",
            "target_calls": 0,
            "lsof_calls": 0,
            "sidecar_calls": 0,
            "pass_fail_unmeasured": {
                "ax_fields": "unmeasured",
                "tcc_persistence": "unmeasured",
                "action_latency": "unmeasured",
            },
        })
        return _fail(active, "Accessibility permission not granted")

    targets = active.find_rekordbox()
    if len(targets) == 0:
        sink.write_summary({
            "schema_version": SHAREABLE_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "failed",
            "permission_state": permission_state,
            "error_class": "zero_target",
        })
        return _fail(active, "no Rekordbox process (need exactly one)")
    if len(targets) > 1:
        sink.write_summary({
            "schema_version": SHAREABLE_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "failed",
            "permission_state": permission_state,
            "error_class": "multi_target",
            "target_count": len(targets),
        })
        return _fail(active, f"multiple Rekordbox processes ({len(targets)})")

    target = targets[0]
    try:
        summary = run_capture(
            active,
            args=args,
            bundle=bundle,
            target=target,
            sink=sink,
            run_id=run_id,
        )
        summary["permission_state"] = permission_state
        summary["prompt_requested"] = prompt_requested
        sink.write_summary(summary)
    except OSError:
        sink.append_private({
            "event": "evidence_write_failure",
            "error_class": "OSError",
        })
        sink.write_summary({
            "schema_version": SHAREABLE_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "failed",
            "error_class": "evidence_write_failure",
        })
        return _fail(active, "evidence write failure")

    if not sink.shareable_ok:
        return _fail(active, "sanitizer failure (private evidence only)")
    if summary.get("status") != "ok":
        return _fail(active, f"capture ended ({summary.get('status')})")
    return 0


def build_live_deps() -> ProbeDeps:
    """Lazy macOS facades. Must not be called from unit tests."""
    from rb_ss_bridge_v2.filepath_resolver import (
        _INSTALLED_SIDECAR_INDEX,
        _load_sidecar_index,
        _lsof_audio_files,
    )

    def _is_frozen() -> bool:
        return bool(getattr(sys, "frozen", False))

    def _read_bundle() -> BundleInfo:
        from Foundation import NSBundle  # type: ignore

        bundle = NSBundle.mainBundle()
        bid = str(bundle.bundleIdentifier() or "")
        version = str(
            bundle.objectForInfoDictionaryKey_("CFBundleShortVersionString") or ""
        )
        path = str(bundle.bundlePath() or "")
        installed = classify_install_path(path)
        # Signing identity class without person/cert names.
        signing = "unknown"
        try:
            out = subprocess.run(
                ["codesign", "-dv", path],
                capture_output=True, text=True, timeout=5,
            ).stderr
            if "Signature=adhoc" in out or "flags=0x2(adhoc)" in out:
                signing = "ad_hoc"
            elif "Authority=" in out:
                signing = "signed"
        except (OSError, subprocess.SubprocessError):
            signing = "unknown"
        return BundleInfo(
            bundle_id=bid,
            version=version,
            bundle_path=path,
            installed_class=installed,
            signing_identity_class=signing,
        )

    def _ax_trusted(prompt: bool) -> bool:
        from ApplicationServices import (  # type: ignore
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )
        from Foundation import NSDictionary  # type: ignore

        opts = NSDictionary.dictionaryWithObject_forKey_(
            bool(prompt), kAXTrustedCheckOptionPrompt
        )
        return bool(AXIsProcessTrustedWithOptions(opts))

    def _show_permission_explanation() -> None:
        from AppKit import NSAlert  # type: ignore

        alert = NSAlert.alloc().init()
        alert.setMessageText_("Rekordbox Access Needed")
        alert.setInformativeText_(
            "RBSS Bridge needs read-only Accessibility access to measure "
            "Rekordbox's on-screen controls. This does not start the bridge "
            "or change lights. Enable it in System Settings → Privacy & "
            "Security → Accessibility for RBSS Bridge, then re-run the probe."
        )
        alert.addButtonWithTitle_("OK")
        alert.runModal()

    def _show_consent_panel() -> bool:
        from AppKit import NSAlert, NSAlertFirstButtonReturn  # type: ignore

        alert = NSAlert.alloc().init()
        alert.setMessageText_("Allow Rekordbox Observation?")
        alert.setInformativeText_(
            "Continue grants read-only Accessibility observation to this "
            "exact installed RBSS Bridge app so it can measure Rekordbox. "
            "It does not start the bridge or control lighting. Cancel leaves "
            "permissions unchanged."
        )
        alert.addButtonWithTitle_("Continue")
        alert.addButtonWithTitle_("Cancel")
        return alert.runModal() == NSAlertFirstButtonReturn

    def _find_rekordbox() -> list[TargetApp]:
        from AppKit import NSRunningApplication, NSWorkspace  # type: ignore

        apps = NSWorkspace.sharedWorkspace().runningApplications()
        found: list[TargetApp] = []
        for app in apps:
            bid = str(app.bundleIdentifier() or "")
            if bid != REKORDBOX_BUNDLE_ID:
                continue
            if app.isTerminated():
                continue
            pid = int(app.processIdentifier())
            version = ""
            url = app.bundleURL()
            if url is not None:
                from Foundation import NSBundle  # type: ignore
                b = NSBundle.bundleWithURL_(url)
                if b is not None:
                    version = str(
                        b.objectForInfoDictionaryKey_("CFBundleShortVersionString") or ""
                    )
            found.append(TargetApp(pid=pid, version=version, bundle_id=bid))
        return found

    retained: dict[int, Any] = {}

    def _create_app_element(pid: int) -> Any:
        from ApplicationServices import AXUIElementCreateApplication  # type: ignore

        el = AXUIElementCreateApplication(pid)
        retained[id(el)] = el
        return el

    def _set_timeout(element: Any, seconds: float) -> None:
        from ApplicationServices import AXUIElementSetMessagingTimeout  # type: ignore

        AXUIElementSetMessagingTimeout(element, float(seconds))

    def _copy_names(element: Any) -> tuple[str, ...] | None:
        from ApplicationServices import AXUIElementCopyAttributeNames  # type: ignore

        err, names = AXUIElementCopyAttributeNames(element, None)
        if err:
            return None
        return tuple(str(n) for n in (names or []))

    def _copy_attr(element: Any, name: str) -> tuple[Any, str | None]:
        from ApplicationServices import AXUIElementCopyAttributeValue  # type: ignore

        err, value = AXUIElementCopyAttributeValue(element, name, None)
        if err:
            return None, str(err)
        return value, None

    def _copy_many(
        element: Any, names: Sequence[str]
    ) -> tuple[Mapping[str, Any], str | None]:
        from ApplicationServices import (  # type: ignore
            AXUIElementCopyMultipleAttributeValues,
        )

        err, values = AXUIElementCopyMultipleAttributeValues(
            element, list(names), 0, None
        )
        if err:
            return {}, str(err)
        out: dict[str, Any] = {}
        if values is not None:
            for key in names:
                if hasattr(values, "objectForKey_"):
                    out[str(key)] = values.objectForKey_(key)
                elif hasattr(values, "get"):
                    out[str(key)] = values.get(key)
                else:
                    out[str(key)] = None
        return out, None

    def _copy_actions(element: Any) -> tuple[str, ...] | None:
        from ApplicationServices import AXUIElementCopyActionNames  # type: ignore

        err, names = AXUIElementCopyActionNames(element, None)
        if err:
            return None
        return tuple(str(n) for n in (names or []))

    def _copy_children(element: Any) -> Sequence[Any] | None:
        from ApplicationServices import (  # type: ignore
            AXUIElementCopyAttributeValue,
            kAXChildrenAttribute,
        )

        err, children = AXUIElementCopyAttributeValue(
            element, kAXChildrenAttribute, None
        )
        if err or children is None:
            return None
        result = list(children)
        for child in result:
            retained[id(child)] = child
        return result

    def _element_id(element: Any) -> int:
        return id(element)

    def _register_observers(element: Any, callback: Callable[..., None]) -> dict[str, str]:
        # Notification names as strings — registration recorded; unsupported is data.
        from ApplicationServices import (  # type: ignore
            AXObserverAddNotification,
            AXObserverCreate,
            AXObserverGetRunLoopSource,
        )

        notifications = (
            "AXTitleChanged",
            "AXValueChanged",
            "AXSelectedChildrenChanged",
            "AXRowCountChanged",
            "AXLayoutChanged",
            "AXFocusedUIElementChanged",
            "AXWindowCreated",
            "AXUIElementDestroyed",
        )
        outcomes: dict[str, str] = {}
        err, observer = AXObserverCreate(os.getpid(), callback, None)
        if err or observer is None:
            return {n: "observer_create_failed" for n in notifications}
        # Keep source alive for the run loop; probe may not spin a long CFRunLoop
        # in this round — outcomes still recorded.
        _ = AXObserverGetRunLoopSource(observer)
        for name in notifications:
            add_err = AXObserverAddNotification(observer, element, name, None)
            outcomes[name] = "ok" if not add_err else f"unsupported:{add_err}"
        return outcomes

    def _run_observer_slice(_seconds: float) -> None:
        return

    def _load_sidecar() -> tuple[bool, tuple[dict, ...]]:
        loaded = _load_sidecar_index(_INSTALLED_SIDECAR_INDEX)
        if loaded is None:
            return False, ()
        _root, records = loaded
        return True, records

    def _mounted_explode() -> Any:
        raise AssertionError("mounted sidecar discovery must never be called")

    deps = ProbeDeps(
        is_frozen=_is_frozen,
        read_bundle=_read_bundle,
        bridge_live_pid=read_bridge_live_pid,
        ax_trusted=_ax_trusted,
        show_permission_explanation=_show_permission_explanation,
        show_consent_panel=_show_consent_panel,
        find_rekordbox=_find_rekordbox,
        create_app_element=_create_app_element,
        set_messaging_timeout=_set_timeout,
        copy_attribute_names=_copy_names,
        copy_attribute=_copy_attr,
        copy_multiple=_copy_many,
        copy_action_names=_copy_actions,
        copy_children=_copy_children,
        element_identity=_element_id,
        register_observers=_register_observers,
        run_observer_slice=_run_observer_slice,
        lsof_audio_files=_lsof_audio_files,
        load_installed_sidecar=_load_sidecar,
        mounted_sidecar_indexes=_mounted_explode,
        now_mono_ns=time.monotonic_ns,
        now_utc=lambda: datetime.now(timezone.utc),
        sleep=time.sleep,
        diagnostics_root=DIAGNOSTICS_ROOT,
    )
    deps.retained_elements = retained  # type: ignore[attr-defined]
    return deps
