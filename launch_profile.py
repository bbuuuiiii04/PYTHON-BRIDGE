"""Single source of truth for the bridge launch profile.

Both the dev watcher (``scripts/ss_bridge_watcher.sh``) and the USB bundle
(``usb_launcher.py``) build the bridge's environment from THIS module, so the
two launch paths can never drift. Pure data + pure functions — no bridge
imports, no I/O, no side effects (the test seam).

The env set is copied from ``ss_bridge_watcher.sh`` ``start_bridge()`` (the
``exec env`` block) at HEAD. Code is the source of truth: if that block ever
changes, change this module AND ``tests/test_launch_profile.py`` in the same
commit.
"""
from __future__ import annotations

import sys
from pathlib import Path, PurePath

# The 19 RBSS_* launch flags, verbatim from ss_bridge_watcher.sh start_bridge()
# (the `exec env` block) at HEAD. All "1" except the transport cooldown, which
# AWR-149 (2026-07-08) set to "0" when it removed RBSS_LED_TRANSPORT_STICKY in
# favor of the deterministic transport rotation. Do NOT resurrect
# RBSS_LED_TRANSPORT_STICKY here — the sticky latch it gated no longer exists.
BRIDGE_ENV: dict[str, str] = {
    "RBSS_GOVEE_REALTIME": "1",
    "RBSS_LIVE_BPM_FOLLOW": "1",
    "RBSS_ANLZ_DIRECT": "1",
    "RBSS_POS_CHAIN_DIRECT": "1",
    "RBSS_POS_CHAIN_SKIP_OBJC": "1",
    "RBSS_MASTER_SEED_DIRECT": "1",
    "RBSS_MASTER_DIRECT": "1",
    "RBSS_PLAY_DIRECT": "1",
    "RBSS_TRACK_LOAD_DIRECT": "1",
    "RBSS_SCRIPTED_DIRECT": "1",
    "RBSS_SCRIPTED_SHOWFILE_DIRECT": "1",
    "RBSS_SMART_REARM_EXPERIMENT": "1",
    "RBSS_SMART_DROP": "1",
    "RBSS_SMART_BREAKDOWN": "1",
    "RBSS_LED_PHRASE_MONOTONIC": "1",
    "RBSS_LED_MIN_DWELL": "1",
    "RBSS_LED_CANCEL_PENDING": "1",
    "RBSS_LED_RT_RECONCILE": "1",
    "RBSS_LED_TRANSPORT_COOLDOWN": "0",
}

# Env var carrying the laser director config path (dynamic — resolved per host,
# so it is NOT a member of the static BRIDGE_ENV set above).
LASER_CONFIG_ENV = "RBSS_LASER_CONFIG"

# Home-parity config overrides (AWR-186 M2): the live-config files the native
# installer lands in App Support, mapped to each subsystem's existing env seam
# (laser_config.py / led_config.py / soundswitch_pack_player_config.py /
# laser_color_engine.py resolve these). Installed copy present -> env points at
# it; absent -> the subsystem keeps today's default resolution, byte-identical.
APP_SUPPORT_CONFIG_ENV: dict[str, str] = {
    "laser_director.json": LASER_CONFIG_ENV,
    "led_look_director.json": "RBSS_LED_CONFIG",
    "soundswitch_pack_player.json": "RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG",
    "laser_color_map.json": "RBSS_LASER_COLOR_MAP_CONFIG",
}


def app_support_config_env(
    app_support_dir: str, present_names: "set[str] | frozenset[str] | list[str]"
) -> dict[str, str]:
    """Env overrides for the App Support config copies that actually exist.

    Pure: the caller supplies the directory listing (``present_names``); no
    filesystem access here (the test seam, same rule as the rest of this
    module).
    """
    present = set(present_names)
    return {
        env: f"{app_support_dir}/{name}"
        for name, env in APP_SUPPORT_CONFIG_ENV.items()
        if name in present
    }


def bridge_env(laser_config_path: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return the full bridge launch env: the 19 flags + the laser config path.

    ``extra`` (if given) is merged last so a caller can add host-specific vars
    (e.g. the bundle sourcing ``govee.env``); passing a base key in ``extra``
    overrides it intentionally — nothing is dropped silently.
    """
    env = dict(BRIDGE_ENV)
    env[LASER_CONFIG_ENV] = laser_config_path
    if extra:
        env.update(extra)
    return env


def bridge_argv(python_exe: str) -> list[str]:
    """Return the argv that launches the bridge module with ``python_exe``."""
    return [python_exe, "-m", "rb_ss_bridge_v2"]


# Where frozen runs keep the learned stores (AWR-186 M2 Task 3). A double-
# clicked app's cwd is "/", so the repo's cwd-relative "local/state/*" paths
# are unwritable there — the stores silently never persist.
FROZEN_STATE_DIR = Path.home() / "Library" / "Application Support" / "RBSS Bridge" / "state"


def resolve_state_path(path: str) -> str:
    """Map relative ``local/state/*`` store paths to App Support — FROZEN ONLY.

    Source runs (the watcher, tests, dev CLIs) return ``path`` unchanged,
    byte-identical: no gate, no rewrite. Frozen runs rewrite ONLY relative
    paths under local/state/ (an operator-configured absolute store path still
    wins). Pure path math — no filesystem access, no directory creation (the
    store owners already mkdir/degrade on failure).
    """
    if not getattr(sys, "frozen", False):
        return path
    parts = PurePath(path).parts
    if PurePath(path).is_absolute() or parts[:2] != ("local", "state"):
        return path
    return str(FROZEN_STATE_DIR.joinpath(*parts[2:]))
