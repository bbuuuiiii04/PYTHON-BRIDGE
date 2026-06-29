"""Load SoundSwitch Autoloop content and gate it against capture hashes."""
from __future__ import annotations

import json
from pathlib import Path
import sys

MATCHED_SOURCE = "MATCHED_SOURCE"
CONTENT_DRIFTED = "CONTENT_DRIFTED"
MISSING = "MISSING"


class AutoloopMap(dict):
    def __init__(self, *args, source_sha256_by_identity: dict[str, str] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_sha256_by_identity = source_sha256_by_identity or {}


def _ensure_repo_parent_on_path() -> None:
    parent = str(Path(__file__).resolve().parents[5])
    if parent not in sys.path:
        sys.path.insert(0, parent)


def _pack_source_hashes(root: Path) -> dict[str, str]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return {
        str(row["path"]): str(row["sha256"])
        for row in manifest.get("source_inventory", ())
        if isinstance(row, dict) and str(row.get("path", "")).startswith("SSAutoLoop")
    }


def load_autoloops(pack_or_project: str | Path) -> AutoloopMap:
    _ensure_repo_parent_on_path()
    from rb_ss_bridge_v2.soundswitch_pack_loader import LoadedAutoloop, load_pack

    root = Path(pack_or_project).expanduser()
    pack = load_pack(root)
    loops = AutoloopMap(source_sha256_by_identity=_pack_source_hashes(root))
    for identity, row in pack.autoloops.items():
        if isinstance(row, LoadedAutoloop):
            loops[str(identity)] = row
    return loops


def _capture_source_hashes(project_before_sha256_path: str | Path) -> dict[str, str]:
    result: dict[str, str] = {}
    with Path(project_before_sha256_path).open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.strip().split(None, 1)
            if len(parts) != 2:
                continue
            digest, path = parts
            result[Path(path).name] = digest
    return result


def verify_against_capture(
    loaded: dict[str, object],
    project_before_sha256_path: str | Path,
) -> dict[str, str]:
    capture_hashes = _capture_source_hashes(project_before_sha256_path)
    source_hashes = getattr(loaded, "source_sha256_by_identity", {})
    result: dict[str, str] = {}
    for identity in sorted(loaded):
        source_sha = source_hashes.get(identity)
        capture_sha = capture_hashes.get(identity)
        if source_sha is None or capture_sha is None:
            result[identity] = MISSING
        elif source_sha == capture_sha:
            result[identity] = MATCHED_SOURCE
        else:
            result[identity] = CONTENT_DRIFTED
    return result
