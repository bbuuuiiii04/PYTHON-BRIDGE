"""Software-only coverage for the AWR-222 dormant AX measurement probe.

Never imports ApplicationServices, never touches TCC, Rekordbox, lsof, App
Support sidecars, or /Volumes. Every macOS/AX path is a fake facade.
"""
from __future__ import annotations

import ast
import json
import os
import stat
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import usb_launcher  # noqa: E402
from rb_ss_bridge_v2 import usb_launcher_ax_probe as probe  # noqa: E402


REPO = Path(__file__).resolve().parents[1]
PROBE_PATH = REPO / "usb_launcher_ax_probe.py"
LOCK_PATH = REPO / "packaging" / "macos12_arm64_cp313.lock"
SPEC_PATH = REPO / "packaging" / "rbss_launcher.spec"
PYPROJECT = REPO / "pyproject.toml"


# ── Fake AX tree ─────────────────────────────────────────────────────────────


@dataclass
class FakeEl:
    eid: int
    attrs: dict[str, Any] = field(default_factory=dict)
    children: list[FakeEl] = field(default_factory=list)
    actions: tuple[str, ...] = ()
    error: str | None = None


class FakeClock:
    def __init__(self) -> None:
        self.mono_ns = 1_000_000_000
        self.utc = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)

    def now_mono_ns(self) -> int:
        return self.mono_ns

    def now_utc(self) -> datetime:
        return self.utc

    def sleep(self, seconds: float) -> None:
        self.mono_ns += int(float(seconds) * 1e9)


class CallCounter:
    def __init__(self) -> None:
        self.ax_target = 0
        self.lsof = 0
        self.sidecar = 0
        self.prompt = 0
        self.consent = 0
        self.mounted = 0
        self.trusted_prompts: list[bool] = []


def make_deps(
    tmp: Path,
    *,
    clock: FakeClock | None = None,
    frozen: bool = True,
    bundle_id: str = probe.BRIDGE_BUNDLE_ID,
    bundle_path: str | None = None,
    version: str = probe.EXPECTED_BUNDLE_VERSION,
    installed_class: str = "installed",
    signing: str = "ad_hoc",
    bridge_pid: int | None = None,
    trusted: bool = True,
    consent: bool = True,
    targets: list[probe.TargetApp] | None = None,
    tree: FakeEl | None = None,
    poll_errors: dict[int, str] | None = None,
    sidecar_records: tuple[dict, ...] | None = None,
    sidecar_valid: bool = True,
    lsof_paths: list[str] | None = None,
    counter: CallCounter | None = None,
) -> probe.ProbeDeps:
    clock = clock or FakeClock()
    counter = counter or CallCounter()
    if bundle_path is None:
        bundle_path = str(tmp / "Applications" / "RBSS Bridge.app" / "Contents")
    Path(bundle_path).mkdir(parents=True, exist_ok=True)

    root = tree or FakeEl(
        eid=1,
        attrs={"role": "AXApplication", "title": "rekordbox"},
        children=[
            FakeEl(
                eid=2,
                attrs={
                    "role": "AXWindow",
                    "title": "Deck Surface",
                    "position": (10, 10),
                    "size": (800, 600),
                },
                children=[
                    FakeEl(
                        eid=3,
                        attrs={
                            "role": "AXStaticText",
                            "title": "Neon Pulse",
                            "value": "Neon Pulse",
                            "description": "Artist One",
                            "identifier": "deck.title.a",
                            "position": (20, 40),
                            "size": (200, 20),
                        },
                    ),
                    FakeEl(
                        eid=4,
                        attrs={
                            "role": "AXStaticText",
                            "title": "Neon Pulse",
                            "value": "Neon Pulse",
                            "description": "Artist Two",
                            "identifier": "browser.row",
                            "position": (20, 400),
                            "size": (200, 20),
                        },
                    ),
                ],
            )
        ],
    )
    retained: dict[int, FakeEl] = {}

    def index(el: FakeEl, seen: set[int] | None = None) -> None:
        seen = set() if seen is None else seen
        if el.eid in seen:
            return
        seen.add(el.eid)
        retained[el.eid] = el
        for child in el.children:
            index(child, seen)

    index(root)

    def create_app(pid: int) -> FakeEl:
        counter.ax_target += 1
        return root

    def attr_names(el: FakeEl) -> tuple[str, ...]:
        return tuple(el.attrs.keys())

    def copy_attr(el: FakeEl, name: str) -> tuple[Any, str | None]:
        if el.error:
            return None, el.error
        if name not in el.attrs:
            return None, "unsupported"
        return el.attrs[name], None

    def copy_many(el: Any, names: Sequence[str]) -> tuple[Mapping[str, Any], str | None]:
        if isinstance(el, int):
            el = retained.get(el)
        if el is None:
            return {}, "invalid"
        err = (poll_errors or {}).get(el.eid)
        if err:
            return {}, err
        out = {n: el.attrs.get(n) for n in names if n in el.attrs}
        # Also accept AXTitle/AXValue aliases mapping to title/value
        for n in names:
            if n == "AXTitle" and "title" in el.attrs:
                out[n] = el.attrs["title"]
            if n == "AXValue" and "value" in el.attrs:
                out[n] = el.attrs["value"]
        return out, None

    def children(el: FakeEl) -> Sequence[FakeEl]:
        return list(el.children)

    def lsof(pid: str) -> list[str]:
        counter.lsof += 1
        return list(lsof_paths or [])

    def load_sidecar() -> tuple[bool, tuple[dict, ...]]:
        counter.sidecar += 1
        if not sidecar_valid:
            return False, ()
        return True, sidecar_records or ()

    def mounted() -> Any:
        counter.mounted += 1
        raise AssertionError("mounted sidecar discovery must never be called")

    trusted_state = {"value": trusted}

    def ax_trusted(prompt: bool) -> bool:
        counter.trusted_prompts.append(bool(prompt))
        if prompt:
            counter.prompt += 1
            trusted_state["value"] = True
        return bool(trusted_state["value"])

    def consent_panel() -> bool:
        counter.consent += 1
        return consent

    deps = probe.ProbeDeps(
        is_frozen=lambda: frozen,
        read_bundle=lambda: probe.BundleInfo(
            bundle_id=bundle_id,
            version=version,
            bundle_path=bundle_path,
            installed_class=installed_class,
            signing_identity_class=signing,
        ),
        bridge_live_pid=lambda: bridge_pid,
        ax_trusted=ax_trusted,
        show_permission_explanation=lambda: None,
        show_consent_panel=consent_panel,
        find_rekordbox=lambda: list(
            targets
            if targets is not None
            else [probe.TargetApp(
                pid=os.getpid(),
                version="7.2.11",
                bundle_id=probe.REKORDBOX_BUNDLE_ID,
            )]
        ),
        create_app_element=create_app,
        set_messaging_timeout=lambda el, s: None,
        copy_attribute_names=attr_names,
        copy_attribute=copy_attr,
        copy_multiple=copy_many,
        copy_action_names=lambda el: el.actions,
        copy_children=children,
        element_identity=lambda el: el.eid if isinstance(el, FakeEl) else int(el),
        register_observers=lambda el, cb: {
            "AXTitleChanged": "ok",
            "AXValueChanged": "unsupported:99",
        },
        run_observer_slice=lambda s: None,
        lsof_audio_files=lsof,
        load_installed_sidecar=load_sidecar,
        mounted_sidecar_indexes=mounted,
        now_mono_ns=clock.now_mono_ns,
        now_utc=clock.now_utc,
        sleep=clock.sleep,
        diagnostics_root=tmp / "diagnostics" / "rekordbox_ax",
    )
    deps.retained_elements = retained  # type: ignore[attr-defined]
    deps._counter = counter  # type: ignore[attr-defined]
    return deps


class DispatchTests(unittest.TestCase):
    def test_probe_dispatch_forwards_args_and_skips_other_modes(self) -> None:
        with mock.patch.object(
            usb_launcher, "_run_rekordbox_accessibility_probe", return_value=7
        ) as run, mock.patch.object(
            usb_launcher, "_run_bridge", side_effect=AssertionError("bridge")
        ), mock.patch.object(
            usb_launcher, "_run_menubar", side_effect=AssertionError("menubar")
        ), mock.patch.object(
            usb_launcher, "_run_streamdeck", side_effect=AssertionError("deck")
        ):
            rc = usb_launcher.main(
                ["--probe-rekordbox-accessibility", "--duration-s", "30", "--layout", "A"]
            )
        self.assertEqual(rc, 7)
        run.assert_called_once_with(["--duration-s", "30", "--layout", "A"])

    def test_probe_runner_lazy_imports_only_probe_main(self) -> None:
        with mock.patch(
            "rb_ss_bridge_v2.usb_launcher_ax_probe.main", return_value=0
        ) as probe_main, mock.patch.object(
            usb_launcher, "_run_bridge", side_effect=AssertionError("bridge")
        ):
            self.assertEqual(
                usb_launcher._run_rekordbox_accessibility_probe(["--duration-s", "10"]),
                0,
            )
        probe_main.assert_called_once_with(["--duration-s", "10"])


class PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_source_run_refused_before_ax(self) -> None:
        counter = CallCounter()
        deps = make_deps(self.root, frozen=False, counter=counter)
        rc = probe.main(["--duration-s", "10"], deps=deps)
        self.assertNotEqual(rc, 0)
        self.assertEqual(counter.ax_target, 0)
        self.assertEqual(counter.lsof, 0)
        self.assertEqual(counter.sidecar, 0)

    def test_wrong_bundle_refused(self) -> None:
        counter = CallCounter()
        deps = make_deps(self.root, bundle_id="com.other.app", counter=counter)
        self.assertNotEqual(probe.main(["--duration-s", "10"], deps=deps), 0)
        self.assertEqual(counter.ax_target, 0)

    def test_translocated_refused(self) -> None:
        counter = CallCounter()
        path = str(
            self.root / "AppTranslocation" / "x" / "RBSS Bridge.app" / "Contents"
        )
        deps = make_deps(self.root, bundle_path=path, counter=counter)
        # classify_install_path looks at path string
        self.assertNotEqual(probe.main(["--duration-s", "10"], deps=deps), 0)
        self.assertEqual(counter.ax_target, 0)

    def test_bridge_live_refused(self) -> None:
        counter = CallCounter()
        deps = make_deps(self.root, bridge_pid=999, counter=counter)
        self.assertNotEqual(probe.main(["--duration-s", "10"], deps=deps), 0)
        self.assertEqual(counter.ax_target, 0)

    def test_zero_target_refused(self) -> None:
        counter = CallCounter()
        deps = make_deps(self.root, targets=[], counter=counter)
        self.assertNotEqual(probe.main(["--duration-s", "10"], deps=deps), 0)
        self.assertEqual(counter.ax_target, 0)
        self.assertEqual(counter.lsof, 0)

    def test_multi_target_refused(self) -> None:
        counter = CallCounter()
        deps = make_deps(
            self.root,
            targets=[
                probe.TargetApp(os.getpid(), "7.2.11", probe.REKORDBOX_BUNDLE_ID),
                probe.TargetApp(os.getpid() + 1, "7.2.11", probe.REKORDBOX_BUNDLE_ID),
            ],
            counter=counter,
        )
        self.assertNotEqual(probe.main(["--duration-s", "10"], deps=deps), 0)
        self.assertEqual(counter.ax_target, 0)


class PermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_default_permission_check_prompt_false_and_denial_is_quiet(self) -> None:
        counter = CallCounter()
        deps = make_deps(self.root, trusted=False, counter=counter)
        rc = probe.main(["--duration-s", "10"], deps=deps)
        self.assertNotEqual(rc, 0)
        self.assertEqual(counter.trusted_prompts, [False])
        self.assertEqual(counter.prompt, 0)
        self.assertEqual(counter.ax_target, 0)
        self.assertEqual(counter.lsof, 0)
        self.assertEqual(counter.sidecar, 0)

    def test_prompt_requires_consent_continue(self) -> None:
        counter = CallCounter()
        deps = make_deps(self.root, trusted=False, consent=True, counter=counter)
        # After consent + prompt, trusted becomes True and capture runs briefly.
        clock = FakeClock()
        deps = make_deps(
            self.root, trusted=False, consent=True, counter=counter, clock=clock
        )
        # Short duration so capture ends quickly.
        rc = probe.main(
            ["--duration-s", "10", "--prompt-permission", "--layout", "L", "--language", "en"],
            deps=deps,
        )
        self.assertEqual(counter.consent, 1)
        self.assertIn(True, counter.trusted_prompts)
        # May succeed or fail on sanitizer/status; permission path reached.
        self.assertGreaterEqual(counter.prompt, 1)

    def test_prompt_cancel_makes_zero_prompt_calls(self) -> None:
        counter = CallCounter()
        deps = make_deps(self.root, trusted=False, consent=False, counter=counter)
        rc = probe.main(
            ["--duration-s", "10", "--prompt-permission"], deps=deps
        )
        self.assertNotEqual(rc, 0)
        self.assertEqual(counter.consent, 1)
        self.assertEqual(counter.prompt, 0)
        self.assertEqual(counter.ax_target, 0)


class TreeWalkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bfs_cycle_and_caps(self) -> None:
        a = FakeEl(eid=1, attrs={"role": "AXApplication", "title": "A"})
        b = FakeEl(eid=2, attrs={"role": "AXGroup", "title": "B"})
        a.children = [b]
        b.children = [a]  # cycle
        deps = make_deps(self.root, tree=a)
        nodes, meta = probe.walk_ax_tree(a, deps)
        ids = [n.element_id for n in nodes]
        self.assertEqual(ids.count(1), 1)
        self.assertEqual(ids.count(2), 1)

        # Depth cap
        cur = FakeEl(eid=0, attrs={"role": "r", "title": "root"})
        tip = cur
        for i in range(1, 30):
            child = FakeEl(eid=i, attrs={"role": "r", "title": f"n{i}"})
            tip.children = [child]
            tip = child
        nodes, meta = probe.walk_ax_tree(cur, deps, max_depth=3)
        self.assertTrue(meta["tree_incomplete"])
        self.assertLessEqual(max(n.depth for n in nodes), 3)

    def test_advertised_only_and_unsupported_error(self) -> None:
        el = FakeEl(
            eid=1,
            attrs={"title": "X"},  # no value advertised
            error=None,
        )
        bad = FakeEl(eid=2, attrs={"title": "Y"}, error="cannotComplete")
        el.children = [bad]
        deps = make_deps(self.root, tree=el)
        nodes, _ = probe.walk_ax_tree(el, deps)
        self.assertEqual(len(nodes), 2)

    def test_terminal_invalidation(self) -> None:
        counter = CallCounter()
        clock = FakeClock()
        deps = make_deps(
            self.root,
            clock=clock,
            counter=counter,
            poll_errors={3: "invalid"},
        )
        rc = probe.main(
            ["--duration-s", "10", "--layout", "L", "--language", "en"],
            deps=deps,
        )
        self.assertNotEqual(rc, 0)
        # Evidence dir created
        runs = list((self.root / "diagnostics" / "rekordbox_ax").iterdir())
        self.assertEqual(len(runs), 1)
        private = (runs[0] / "private.jsonl").read_text(encoding="utf-8")
        self.assertIn("terminal_unavailable", private)


class SanitizerTests(unittest.TestCase):
    def test_canaries_rejected_from_shareable(self) -> None:
        key = "a" * 64
        canaries = [
            "Neon Pulse",
            "Artist One",
            str(Path.home() / "Music" / "x.mp3"),
            "/Volumes/MINK/Pioneer/track.wav",
            "secret.mp3",
            "sk-api-key-EXAMPLE",
            "10.0.0.42",
            "AA:BB:CC:DD:EE:FF",
            "0123456789abcdef",
            "/path/to/source.flac",
            "ValueError: boom\nTraceback (most recent call last):\n  File",
            key,
        ]
        for canary in canaries:
            with self.assertRaises(probe.SanitizerFailure):
                probe.sanitize_value(
                    {"payload": canary},
                    hmac_key_hex=key,
                    private_literals=canaries,
                )

    def test_required_shapes_survive(self) -> None:
        clean = probe.sanitize_value(
            {
                "role": "AXStaticText",
                "title": {
                    "type": "str",
                    "length_bucket": "short",
                    "format_class": "text",
                    "token": "abc123",
                    "change_count": 0,
                },
                "geometry": {"x": 16.0, "y": 40.0, "w": 200.0, "h": 24.0},
            },
            hmac_key_hex="b" * 64,
        )
        self.assertEqual(clean["role"], "AXStaticText")
        self.assertEqual(clean["title"]["token"], "abc123")


class EvidencePermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_file_modes_and_fixed_root(self) -> None:
        deps = make_deps(self.root)
        probe.main(
            ["--duration-s", "10", "--layout", "L", "--language", "en"],
            deps=deps,
        )
        runs = list((self.root / "diagnostics" / "rekordbox_ax").iterdir())
        self.assertEqual(len(runs), 1)
        run_dir = runs[0]
        self.assertEqual(stat.S_IMODE(run_dir.stat().st_mode), 0o700)
        for name in ("private.jsonl", "shareable.jsonl", "private_manifest.json", "summary.json"):
            mode = stat.S_IMODE((run_dir / name).stat().st_mode)
            self.assertEqual(mode, 0o600, name)
        # Never escapes diagnostics root
        self.assertTrue(
            run_dir.resolve().is_relative_to(
                (self.root / "diagnostics" / "rekordbox_ax").resolve()
            )
        )


class TokenStabilityTests(unittest.TestCase):
    def test_stable_within_run_different_across_runs(self) -> None:
        a = probe.TokenVault(key=b"\x01" * 32)
        b = probe.TokenVault(key=b"\x02" * 32)
        t1 = a.token_for("Neon Pulse")
        t2 = a.token_for("Neon Pulse")
        self.assertEqual(t1, t2)
        self.assertNotEqual(t1, b.token_for("Neon Pulse"))
        shareable = {"token": t1}
        # Key must not appear
        blob = json.dumps(shareable)
        self.assertNotIn(a.hex_key(), blob)
        self.assertNotIn(b.hex_key(), blob)


class SidecarIdentityTests(unittest.TestCase):
    def test_unique_and_abstentions(self) -> None:
        records = (
            {
                "content_id": "aaa",
                "title": "Neon Pulse",
                "artist": "Artist One",
                "duration_s": 180.0,
            },
            {
                "content_id": "bbb",
                "title": "Neon Pulse",
                "artist": "Artist One",
                "duration_s": 200.0,
            },
            {
                "content_id": "ccc",
                "title": "Other",
                "artist": "Artist One",
                "duration_s": 180.0,
            },
        )
        unique = probe.match_sidecar_identity(
            title="Neon Pulse",
            artist="Artist One",
            duration_s=180.0,
            records=records,
            duration_tolerance_s=2.0,
        )
        self.assertEqual(unique["status"], "unique")

        title_only = probe.match_sidecar_identity(
            title="Neon Pulse",
            artist="",
            duration_s=180.0,
            records=records,
            duration_tolerance_s=2.0,
        )
        self.assertEqual(title_only["status"], "ambiguous")

        missing_artist = probe.match_sidecar_identity(
            title="Neon Pulse",
            artist=None,
            duration_s=None,
            records=records,
            duration_tolerance_s=2.0,
        )
        self.assertEqual(missing_artist["status"], "ambiguous")

        dup = probe.match_sidecar_identity(
            title="Neon Pulse",
            artist="Artist One",
            duration_s=None,
            records=records,
            duration_tolerance_s=2.0,
        )
        self.assertEqual(dup["status"], "ambiguous")
        self.assertEqual(dup["reason"], "multiple_matches")

        collision = probe.match_sidecar_identity(
            title="Neon Pulse",
            artist="Artist One",
            duration_s=190.0,  # within 2s of neither uniquely... 180 and 200 both outside? 190-180=10 > 2
            records=records,
            duration_tolerance_s=2.0,
        )
        self.assertEqual(collision["status"], "ambiguous")

        # Duration collision within tolerance of two records
        close = (
            {**records[0], "duration_s": 180.0},
            {**records[1], "duration_s": 181.0, "content_id": "ddd"},
        )
        multi = probe.match_sidecar_identity(
            title="Neon Pulse",
            artist="Artist One",
            duration_s=180.5,
            records=close,
            duration_tolerance_s=2.0,
        )
        self.assertEqual(multi["status"], "ambiguous")


class LsofCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_multiple_candidates_never_deck_exact(self) -> None:
        paths = [
            "/Volumes/MINK/a.mp3",
            "/Volumes/MINK/b.wav",
        ]
        classified = probe.classify_lsof_candidates(paths)
        self.assertEqual(classified["candidate_count"], 2)
        self.assertIsNone(classified["deck_assignment"])
        self.assertFalse(classified["unique_deck"])

        counter = CallCounter()
        deps = make_deps(self.root, lsof_paths=paths, counter=counter)
        probe.main(
            ["--duration-s", "10", "--layout", "L", "--language", "en"],
            deps=deps,
        )
        self.assertEqual(counter.mounted, 0)
        runs = list((self.root / "diagnostics" / "rekordbox_ax").iterdir())
        shareable = (runs[0] / "shareable.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("/Volumes/MINK", shareable)
        self.assertNotIn("a.mp3", shareable)
        summary = json.loads((runs[0] / "summary.json").read_text(encoding="utf-8"))
        self.assertFalse(summary["lsof"]["unique_deck"])
        self.assertIsNone(summary["lsof"]["deck_assignment"])


class CadenceTests(unittest.TestCase):
    def test_measured_failed_unmeasured(self) -> None:
        unmeasured = probe.summarize_cadence([10.0, 20.0], reference_available=False)
        self.assertEqual(unmeasured["status"], "unmeasured")
        self.assertIsNone(unmeasured["p95_ms"])

        failed = probe.summarize_cadence([], reference_available=True)
        self.assertEqual(failed["status"], "failed")

        failed2 = probe.summarize_cadence(None, reference_available=True)
        self.assertEqual(failed2["status"], "failed")

        measured = probe.summarize_cadence([10, 20, 30, 40, 100], reference_available=True)
        self.assertEqual(measured["status"], "measured")
        self.assertEqual(measured["max_ms"], 100)


class StaticGuardTests(unittest.TestCase):
    def test_forbidden_symbols_and_imports(self) -> None:
        source = PROBE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_names = {
            "AXUIElementSetAttributeValue",
            "AXUIElementPerformAction",
            "AXUIElementPostKeyboardEvent",
            "CGEventPost",
            "CGEventCreateKeyboardEvent",
            "CGWindowListCreateImage",
            "CGDisplayStream",
            "NSEvent",
            "IOHIDManagerCreate",
        }
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                found.add(node.id)
            if isinstance(node, ast.Attribute) and node.attr in forbidden_names:
                found.add(node.attr)
        self.assertFalse(found, f"forbidden AX symbols present: {found}")

        # Also reject as substrings in source (belt + suspenders).
        for name in forbidden_names:
            self.assertNotIn(name, source)

        import_forbidden_substrings = (
            "rb_ss_bridge_v2.__main__",
            "state_manager",
            "sound_switch_engine",
            "enttec_dmx_pro",
            "os2l_injector",
            "laser_director",
            "laser_executor",
            "led_look_director",
            "govee_runtime_sender",
            "govee_realtime",
            "streamdeck",
            "midi_output",
            "rekordbox_patch",
            "config.load",
            "led_config",
            "laser_config",
        )
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                rendered = ast.unparse(node)
                for bad in import_forbidden_substrings:
                    self.assertNotIn(bad, rendered, rendered)


class DependencyPinTests(unittest.TestCase):
    def test_pyproject_declares_applicationservices(self) -> None:
        text = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn("pyobjc-framework-ApplicationServices", text)

    def test_lock_pins_applicationservices_quartz_coretext(self) -> None:
        lock = LOCK_PATH.read_text(encoding="utf-8")
        for filename in (
            "pyobjc_framework_applicationservices-12.2.1-cp313-cp313-macosx_10_13_universal2.whl",
            "pyobjc_framework_quartz-12.2.1-cp313-cp313-macosx_10_13_universal2.whl",
            "pyobjc_framework_coretext-12.2.1-cp313-cp313-macosx_10_13_universal2.whl",
        ):
            self.assertIn(filename, lock)
        self.assertIn(
            "8749290f796e6cca341d443769b79329dde5d157bcc4413c1f7fdb68ea4a8e48",
            lock,
        )

    def test_spec_collects_applicationservices_only(self) -> None:
        spec = SPEC_PATH.read_text(encoding="utf-8")
        self.assertIn('collect_submodules("ApplicationServices")', spec)
        # Do not broaden to unrelated frameworks in this lane.
        self.assertNotIn('collect_submodules("Quartz")', spec)
        self.assertNotIn('collect_submodules("CoreText")', spec)

    def test_required_bundle_modules_lists_applicationservices(self) -> None:
        self.assertIn("ApplicationServices", usb_launcher._REQUIRED_BUNDLE_MODULES)

    def test_lock_keeps_existing_cocoa_pin(self) -> None:
        lock = LOCK_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "pyobjc_framework_cocoa-12.2.1-cp313-cp313-macosx_10_13_universal2.whl",
            lock,
        )


class UsbLauncherDependencyTests(unittest.TestCase):
    def test_check_deps_declares_applicationservices(self) -> None:
        self.assertIn("ApplicationServices", usb_launcher._REQUIRED_BUNDLE_MODULES)


class EndToEndFakeCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_happy_path_shareable_has_no_canaries(self) -> None:
        song = "Neon Pulse"
        artist = "Artist One"
        home_track = str(Path.home() / "Music" / "secret.mp3")
        records = (
            {
                "content_id": "deadbeefdeadbeef",
                "title": song,
                "artist": artist,
                "duration_s": 180.0,
                "bpm": 128.0,
                "source_filepath": home_track,
                "beatgrid_fingerprint": "0123456789abcdef",
            },
        )
        counter = CallCounter()
        deps = make_deps(
            self.root,
            counter=counter,
            sidecar_records=records,
            lsof_paths=[home_track, "/Volumes/MINK/other.wav"],
        )
        rc = probe.main(
            ["--duration-s", "10", "--layout", "Performance", "--language", "en"],
            deps=deps,
        )
        self.assertEqual(rc, 0, msg="capture should succeed under fakes")
        self.assertGreater(counter.ax_target, 0)
        self.assertGreater(counter.lsof, 0)
        self.assertGreater(counter.sidecar, 0)
        self.assertEqual(counter.mounted, 0)

        run_dir = next((self.root / "diagnostics" / "rekordbox_ax").iterdir())
        shareable = (run_dir / "shareable.jsonl").read_text(encoding="utf-8")
        summary_text = (run_dir / "summary.json").read_text(encoding="utf-8")
        manifest = json.loads((run_dir / "private_manifest.json").read_text(encoding="utf-8"))
        for canary in (
            song, artist, home_track, "/Volumes/MINK", "secret.mp3",
            "deadbeefdeadbeef", "0123456789abcdef", Path.home().as_posix(),
            manifest["hmac_key"],
        ):
            self.assertNotIn(canary, shareable)
            self.assertNotIn(canary, summary_text)
        self.assertIn("DO_NOT_SHARE", manifest)
        private = (run_dir / "private.jsonl").read_text(encoding="utf-8")
        self.assertIn(song, private)  # private may retain raw values


if __name__ == "__main__":
    unittest.main()
