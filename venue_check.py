"""Install-time Venue Check — read-only guest-Mac self-diagnosis.

Every check is injectable via ``VenueProbes`` so unit tests never touch the
network, MIDI, serial, or the real filesystem. Real defaults are assembled by
``default_probes()`` for the menubar / first-run path.

Read-only throughout: never starts the bridge, never opens MIDI/serial ports,
never writes device state. The Govee LAN probe deliberately triggers the macOS
Local Network permission prompt on first use (prompt-herding) — there is no API
to read that grant, so discovery is both the check and the prompt.
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
STATUS_INFO = "info"

_IAC_PORT_NAME = "IAC Driver Bus 1"
_IAC_HINT = (
    "Lasers only: open Applications → Utilities → Audio MIDI Setup → "
    "Window → Show MIDI Studio → double-click IAC Driver → tick "
    '"Device is online" (keep the default bus name "Bus 1"), then restart '
    "the bridge."
)
_GOVEE_EMPTY_HINT = (
    "click Allow on the Local Network popup / check the strip is on this Wi-Fi"
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # ok | warn | fail | info
    hint: str


@dataclass(frozen=True)
class VenueReport:
    results: tuple[CheckResult, ...]

    @property
    def needs_patch(self) -> bool:
        for row in self.results:
            if row.name == "Rekordbox patch" and row.status == STATUS_FAIL:
                return True
        return False


@dataclass(frozen=True)
class VenueProbes:
    """Every side effect lives here — the test seam."""

    check_bundle_deps: Callable[[], CheckResult]
    check_rekordbox_version: Callable[[], CheckResult]
    check_rekordbox_patch: Callable[[], CheckResult]
    check_govee_lan: Callable[[], CheckResult]
    check_iac_bus: Callable[[], CheckResult]
    check_enttec: Callable[[], CheckResult]


def run_venue_check(probes: VenueProbes) -> VenueReport:
    """Run all venue probes in fixed order and return a report."""
    results = (
        probes.check_bundle_deps(),
        probes.check_rekordbox_version(),
        probes.check_rekordbox_patch(),
        probes.check_govee_lan(),
        probes.check_iac_bus(),
        probes.check_enttec(),
    )
    return VenueReport(results=results)


def format_venue_alert_body(report: VenueReport) -> str:
    """One ✓/⚠/✗/• line per check plus its plain-English hint."""
    symbols = {
        STATUS_OK: "✓",
        STATUS_WARN: "⚠",
        STATUS_FAIL: "✗",
        STATUS_INFO: "•",
    }
    lines: list[str] = []
    for row in report.results:
        mark = symbols.get(row.status, "?")
        lines.append(f"{mark} {row.name}: {row.hint}")
    return "\n".join(lines)


def venue_check_seen_path(app_support: Path | None = None) -> Path:
    """Marker under App Support — first-run auto-check runs only when absent."""
    if app_support is None:
        from rb_ss_bridge_v2.install_controller import APP_SUPPORT_DIR

        app_support = APP_SUPPORT_DIR
    return Path(app_support) / "venue_check_seen"


def should_auto_venue_check(
    *,
    frozen: bool,
    installed: bool,
    marker_exists: bool,
) -> bool:
    """True once after a native install/update relaunch (marker absent)."""
    return bool(frozen) and bool(installed) and not bool(marker_exists)


def write_venue_check_seen(path: Path | None = None) -> None:
    """Record that first-run Venue Check already ran. Best-effort; never raises."""
    target = path if path is not None else venue_check_seen_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("seen\n", encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Default probes (real I/O — menubar only; tests inject fakes)
# ---------------------------------------------------------------------------


def probe_bundle_deps(*, frozen: bool | None = None) -> CheckResult:
    """Import every usb_launcher required module. Frozen builds only."""
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if not frozen:
        return CheckResult(
            "Bundle deps",
            STATUS_OK,
            "Skipped on a source run (frozen app only).",
        )
    from rb_ss_bridge_v2.usb_launcher import _REQUIRED_BUNDLE_MODULES

    missing: list[str] = []
    for mod in _REQUIRED_BUNDLE_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as exc:  # ImportError or submodule init failure
            missing.append(f"{mod} ({type(exc).__name__})")
    if missing:
        return CheckResult(
            "Bundle deps",
            STATUS_FAIL,
            "Rebuild the USB stick — missing: " + ", ".join(missing) + ".",
        )
    return CheckResult("Bundle deps", STATUS_OK, "All required frozen modules import.")


def probe_rekordbox_version() -> CheckResult:
    """Detect installed RB version and require it in the rb_offsets table."""
    from rb_ss_bridge_v2.live_bpm import read_rekordbox_version
    from rb_ss_bridge_v2.rb_offsets import all_offsets, load_offsets_for_version

    version = read_rekordbox_version()
    if not version:
        supported = ", ".join(sorted(all_offsets().keys())) or "(none)"
        return CheckResult(
            "Rekordbox version",
            STATUS_FAIL,
            f"Install a supported Rekordbox version ({supported}).",
        )
    if load_offsets_for_version(version) is None:
        supported = ", ".join(sorted(all_offsets().keys())) or "(none)"
        return CheckResult(
            "Rekordbox version",
            STATUS_FAIL,
            f"Rekordbox {version} is not supported; use {supported}.",
        )
    return CheckResult(
        "Rekordbox version",
        STATUS_OK,
        f"Rekordbox {version} is supported.",
    )


def probe_rekordbox_patch(
    *,
    verdict_fn: Callable[[], tuple[str, str]] | None = None,
) -> CheckResult:
    """Reuse the rekordbox_patch check seam (GTA + deep/strict)."""
    if verdict_fn is None:
        verdict_fn = _default_patch_verdict
    verdict, detail = verdict_fn()
    if verdict == "enabled":
        return CheckResult(
            "Rekordbox patch",
            STATUS_OK,
            f"Target patch present ({detail}).",
        )
    if verdict == "not_enabled":
        return CheckResult(
            "Rekordbox patch",
            STATUS_FAIL,
            "Use Patch Rekordbox… from this alert or the maintenance menu, "
            "then relaunch Rekordbox.",
        )
    return CheckResult(
        "Rekordbox patch",
        STATUS_WARN,
        f"Could not verify the Rekordbox patch ({detail}).",
    )


def _default_patch_verdict() -> tuple[str, str]:
    """Same tokens as the menubar entitlement check — no AppKit import."""
    try:
        from rb_ss_bridge_v2 import rekordbox_patch

        app = rekordbox_patch.find_rekordbox()
        if app is None:
            return "unknown", "Rekordbox app not found in /Applications"
        if rekordbox_patch.has_valid_target_patch(app):
            return "enabled", str(app)
        return "not_enabled", str(app)
    except Exception as exc:
        return "unknown", f"{type(exc).__name__}: {exc}"


def probe_govee_lan(
    *,
    discover_fn: Callable[[float], Sequence] | None = None,
    timeout_s: float = 3.0,
) -> CheckResult:
    """Multicast Govee discovery.

    Prompt-herding: this deliberately triggers the macOS Local Network
    permission popup on first LAN traffic (there is no API to read that grant).
    """
    if discover_fn is None:
        from rb_ss_bridge_v2.govee_lan_discovery import discover_devices

        discover_fn = discover_devices
    devices = list(discover_fn(timeout_s) or [])
    if devices:
        return CheckResult(
            "Govee / Local Network",
            STATUS_OK,
            f"Found {len(devices)} Govee device(s) on this Wi-Fi.",
        )
    return CheckResult(
        "Govee / Local Network",
        STATUS_WARN,
        _GOVEE_EMPTY_HINT,
    )


def probe_iac_bus(
    *,
    output_names_fn: Callable[[], Iterable[str]] | None = None,
) -> CheckResult:
    """Check IAC Driver Bus 1 in MIDI outputs (lasers only). Lazy mido import."""
    if output_names_fn is None:
        try:
            import mido  # type: ignore
        except Exception:
            return CheckResult("IAC Bus 1 (lasers)", STATUS_WARN, _IAC_HINT)
        output_names_fn = mido.get_output_names
    try:
        names = list(output_names_fn() or [])
    except Exception:
        return CheckResult("IAC Bus 1 (lasers)", STATUS_WARN, _IAC_HINT)
    if any(_IAC_PORT_NAME.lower() in str(n).lower() for n in names):
        return CheckResult(
            "IAC Bus 1 (lasers)",
            STATUS_OK,
            "IAC Driver Bus 1 is available (lasers / MIDI look-selection).",
        )
    return CheckResult("IAC Bus 1 (lasers)", STATUS_WARN, _IAC_HINT)


def probe_enttec(
    *,
    find_port_fn: Callable[[], str | None] | None = None,
) -> CheckResult:
    """Metadata-only Enttec presence — never opens the serial port."""
    if find_port_fn is None:
        from rb_ss_bridge_v2.enttec_dmx_pro import find_enttec_port

        find_port_fn = find_enttec_port
    port = find_port_fn()
    if port:
        return CheckResult(
            "Enttec DMX",
            STATUS_INFO,
            f"Enttec serial seen at {port} (informational; port not opened).",
        )
    return CheckResult(
        "Enttec DMX",
        STATUS_INFO,
        "No Enttec serial found (informational — only needed for DMX output).",
    )


def default_probes(*, frozen: bool | None = None) -> VenueProbes:
    """Assemble the real probes used by the menubar / first-run path."""
    return VenueProbes(
        check_bundle_deps=lambda: probe_bundle_deps(frozen=frozen),
        check_rekordbox_version=probe_rekordbox_version,
        check_rekordbox_patch=probe_rekordbox_patch,
        check_govee_lan=probe_govee_lan,
        check_iac_bus=probe_iac_bus,
        check_enttec=probe_enttec,
    )
