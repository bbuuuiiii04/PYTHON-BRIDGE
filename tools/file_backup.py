"""Rotating pre-write backups for operator-owned JSON/config files.

Keeps the newest ``keep`` copies named ``{name}.bak-{timestamp}``. Used by
Template Lab + LED Sim integrity paths (AWR-258); pad commit history stays
unlimited via ``save_config_atomically``.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def rotate_backup(path: Path | str, *, keep: int = 5) -> Path | None:
    """Copy ``path`` to a timestamped ``.bak-*`` sibling, then prune older copies.

    Returns the new backup path, or ``None`` when ``path`` does not exist yet
    (first write — nothing to snapshot).
    """
    target = Path(path)
    if not target.exists():
        return None
    keep = max(1, int(keep))
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = target.with_name(f"{target.name}.bak-{ts}")
    suffix = 1
    while backup.exists():
        backup = target.with_name(f"{target.name}.bak-{ts}-{suffix}")
        suffix += 1
    shutil.copy2(target, backup)
    pattern = f"{target.name}.bak-*"
    existing = sorted(target.parent.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in existing[keep:]:
        try:
            stale.unlink()
        except OSError:
            pass
    return backup
