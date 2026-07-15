"""Canonical JSON bytes + SHA-256 helpers for the Phase-0 spectral pilot (spec B2).

Every hash the pilot records flows through here so two runs of the same protocol
produce byte-identical bytes. Pure module: no I/O, no runtime imports.

Canonical JSON (B2): UTF-8, ``sort_keys=True``, separators ``(",", ":")``, no
NaN/Inf (nonfinite is a protocol error), numbers only as Python ``int``/``float``
(NumPy scalars rejected at the boundary), ``-0.0`` normalized to ``0.0``, floats
serialized via ``repr`` round-trip (Python's ``json`` already does this).
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import unicodedata
from typing import Any

# The single byte joining selection-hash fields (B2: ``SHA256(a || b || …)``).
FIELD_SEP = b"\x1f"


def _normalize(obj: Any) -> Any:
    """Validate + normalize a value tree for canonical serialization (B2).

    Rejects NaN/Inf and any scalar whose *exact* type is not ``int``/``float``/
    ``str``/``bool``/``None`` — so ``numpy.float64`` (a ``float`` subclass) is
    rejected here rather than serialized silently. Collapses ``-0.0`` to ``0.0``.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if type(k) is not str:
                raise TypeError(f"canonical JSON object keys must be str, got {type(k)!r}")
            out[k] = _normalize(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    t = type(obj)
    if obj is None or t is bool or t is str or t is int:
        return obj
    if t is float:
        if not math.isfinite(obj):
            raise ValueError(f"nonfinite float is a protocol error: {obj!r}")
        return 0.0 if obj == 0.0 else obj  # collapses -0.0 -> 0.0
    raise TypeError(f"non-canonical type at serialization boundary: {t!r} ({obj!r})")


def canonical_bytes(obj: Any) -> bytes:
    """Canonical UTF-8 JSON bytes for ``obj`` (B2)."""
    return json.dumps(
        _normalize(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    """Lower-case SHA-256 hex over the canonical bytes of ``obj``."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def jsonl_line(obj: Any) -> bytes:
    """One canonical JSON object as a ``\\n``-terminated JSONL line (B2)."""
    return canonical_bytes(obj) + b"\n"


def hash_omitting(obj: dict, *omit: str) -> str:
    """SHA-256 hex of ``obj`` with the named digest fields removed (B2 §15.1).

    For any artifact that embeds its own digest: hash with the digest field(s)
    omitted, then the caller inserts the result.
    """
    return sha256_hex({k: v for k, v in obj.items() if k not in omit})


def _render_field(x: Any) -> bytes:
    """Render one selection-hash field as UTF-8 bytes (B2 canonical number rules)."""
    t = type(x)
    if t is str:
        return x.encode("utf-8")
    if t is bool:
        raise TypeError("bool is not a valid selection-hash field")
    if t is int:
        return str(x).encode("utf-8")
    if t is float:
        if not math.isfinite(x):
            raise ValueError(f"nonfinite float in selection-hash field: {x!r}")
        x = 0.0 if x == 0.0 else x
        return repr(x).encode("utf-8")
    raise TypeError(f"non-canonical selection-hash field: {t!r} ({x!r})")


def selection_hash(*fields: Any) -> str:
    """``SHA256(a || b || …)`` with fields joined by the single byte 0x1F (B2).

    This is the ONLY concatenation the protocol permits for selection hashing.
    """
    joined = FIELD_SEP.join(_render_field(f) for f in fields)
    return hashlib.sha256(joined).hexdigest()


def environment_lock() -> dict:
    """Environment lock: Python, NumPy, and ``unicodedata.unidata_version`` (B2).

    NumPy is imported lazily so merely importing this module stays dependency-free.
    """
    import numpy  # lazy: only the pilot run needs it

    return {
        "python_version": platform.python_version(),
        "numpy_version": numpy.__version__,
        "unidata_version": unicodedata.unidata_version,
    }
