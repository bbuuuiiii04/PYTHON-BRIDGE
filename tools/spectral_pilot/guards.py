"""Rollback + no-write proof obligations for the Phase-0 pilot (spec B11).

Four guards, all offline:
(a) AST no-runtime-importer — no repo-root runtime module imports this package.
(b) workspace fence — see ``session._safe_path``; here we hash directory listings.
(c) byte-identity watch set — SHA-256 of sorted (name, mtime, size) listings before
    and after a run; any difference fails.
(d) zero network — the package imports no socket/subprocess/network lib at module
    level, and a runtime ``no_network_guard`` blocks socket creation.
"""
from __future__ import annotations

import ast
import contextlib
from pathlib import Path

from .canonical import sha256_hex

PKG = "spectral_pilot"
SKIP_DIRS = {".git", "graphify-out", "__pycache__", "node_modules", "build", "dist"}
FORBIDDEN_IMPORTS = frozenset(
    {"socket", "subprocess", "requests", "urllib", "http", "ftplib", "smtplib",
     "asyncio", "mido", "rtmidi", "serial", "websocket", "websockets", "aiohttp"}
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]  # tools/spectral_pilot -> repo root


def _module_level_imports(text: str):
    """Names imported at module top level (nested/function imports are ignored)."""
    names = set()
    for node in ast.parse(text).body:
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _imports_spectral_pilot(text: str) -> bool:
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(PKG in a.name.split(".") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and PKG in node.module.split("."):
                return True
            if any(a.name == PKG for a in node.names):   # `from tools import spectral_pilot`
                return True
    if PKG in text and ("import_module" in text or "__import__" in text):
        return True
    return False


def no_runtime_importer_offenders(root=None):
    """Repo-root runtime modules (not under tools/, tests/, or local/) that import us (B11a).

    ``local/`` is the gitignored pilot workspace: sanctioned session-driver scripts
    live there and legitimately import this package, so they are not offenders.
    """
    root = Path(root) if root else _repo_root()
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.split("/")):
            continue
        if rel.startswith(("tools/", "tests/", "local/")):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _imports_spectral_pilot(text):
            offenders.append(rel)
    return offenders


def forbidden_module_level_imports():
    """Package modules that import a network/subprocess lib at module level (B11d).

    ``guards.py`` is skipped: it names ``socket`` on purpose to block it, but only
    inside ``no_network_guard`` (a nested import), so it never appears here anyway.
    """
    pkg_dir = Path(__file__).resolve().parent
    found = {}
    for path in sorted(pkg_dir.glob("*.py")):
        if path.name == "guards.py":
            continue
        bad = {n.split(".")[0] for n in _module_level_imports(path.read_text(encoding="utf-8"))}
        bad &= FORBIDDEN_IMPORTS
        if bad:
            found[path.name] = sorted(bad)
    return found


def listing_hash(paths) -> str:
    """SHA-256 of the sorted (path, name, mtime_ns, size) listing of ``paths`` (B11c)."""
    entries = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            entries.append([str(p), "__absent__"])
            continue
        targets = sorted(p.rglob("*")) if p.is_dir() else [p]
        for f in targets:
            try:
                st = f.stat()
            except OSError:
                continue
            entries.append([str(f), f.name, st.st_mtime_ns, st.st_size])
    return sha256_hex(sorted(entries))


def assert_unchanged(before: str, after: str) -> None:
    """Fail if the watch-set listing hash moved across a run (B11c)."""
    if before != after:
        raise RuntimeError("byte-identity watch set changed during the pilot run")


@contextlib.contextmanager
def no_network_guard():
    """Block socket creation for the duration of a pilot run (B11d)."""
    import socket
    orig = socket.socket

    def _blocked(*a, **k):
        raise RuntimeError("network access is forbidden inside the spectral pilot")

    socket.socket = _blocked
    try:
        yield
    finally:
        socket.socket = orig
