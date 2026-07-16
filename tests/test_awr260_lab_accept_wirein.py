"""AWR-260: lab production adapter + reload + accept wire-in tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from rb_ss_bridge_v2.govee_frame_renderer import GoveeFrameRenderer
from rb_ss_bridge_v2.govee_lab_adapter import (
    LabProductionAdapter,
    is_lab_production_scene,
    lab_draft_from_scene,
)
from rb_ss_bridge_v2.led_look_director import LEDLookDirector
from rb_ss_bridge_v2.led_models import (
    LEDAutomation,
    LEDBank,
    LEDConfig,
    LEDLook,
    LEDRateLimits,
    LEDSafety,
    LEDTarget,
)
from rb_ss_bridge_v2.runtime_status import CommandReader, parse_command


def _write_lab_module(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


_GOOD_LAB = """
def pulse(beat_pos, local_t, frame_index, params, segments, seed):
    return [(10, 20, 30)] * max(0, int(segments))

def boom(beat_pos, local_t, frame_index, params, segments, seed):
    raise RuntimeError("boom")

def slow(beat_pos, local_t, frame_index, params, segments, seed):
    import time
    time.sleep(0.025)
    return [(1, 2, 3)] * max(0, int(segments))

def comet_trio_orbit(beat_pos, local_t, frame_index, params, segments, seed):
    return [(40, 50, 60)] * max(0, int(segments))

LAB_EFFECTS = {
    "pulse": ("frame", pulse),
    "boom": ("frame", boom),
    "slow": ("frame", slow),
    "comet_trio_orbit": ("frame", comet_trio_orbit),
}
"""


def _write_drafts(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")


def _draft_entry(
    name: str,
    *,
    fn: str | None = None,
    target_role: str = "drop",
    params: dict | None = None,
    status: str = "iterating",
) -> dict:
    return {
        "name": name,
        "kind": "frame",
        "fn": fn if fn is not None else name,
        "params": params if params is not None else {},
        "cue_beats": 16,
        "notes": "",
        "brief": "",
        "status": status,
        "timing_mode": "beat",
        "target_role": target_role,
        "param_specs": {},
        "created": "2026-07-16T00:00:00+00:00",
        "updated": "2026-07-16T00:00:00+00:00",
    }


class LabAdapterHelpersTests(unittest.TestCase):
    def test_scene_ref_helpers(self) -> None:
        self.assertTrue(is_lab_production_scene("lab:pulse"))
        self.assertTrue(is_lab_production_scene("lab_adapter"))
        self.assertFalse(is_lab_production_scene("lab_pulse"))
        self.assertEqual(lab_draft_from_scene("lab:pulse"), "pulse")
        self.assertEqual(
            lab_draft_from_scene("lab_adapter", {"lab_draft": "pulse"}), "pulse"
        )


class LabAdapterFailDarkTests(unittest.TestCase):
    def test_exception_returns_black_and_engine_alive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "effects_lab.py"
            _write_lab_module(module, _GOOD_LAB)
            adapter = LabProductionAdapter(module)
            adapter.reload()
            frame = adapter.render(
                "lab:boom",
                beat_pos=0.0,
                local_t=0.0,
                frame_index=0,
                params={},
                segments=4,
                seed=1,
            )
            self.assertEqual(frame, [(0, 0, 0)] * 4)
            # Still usable after the exception.
            ok = adapter.render(
                "lab:pulse",
                beat_pos=1.0,
                local_t=0.5,
                frame_index=1,
                params={},
                segments=2,
                seed=2,
            )
            self.assertEqual(ok, [(10, 20, 30), (10, 20, 30)])

    def test_budget_disables_after_n_overruns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "effects_lab.py"
            _write_lab_module(module, _GOOD_LAB)
            clock = {"t": 0.0}

            def time_fn() -> float:
                return clock["t"]

            adapter = LabProductionAdapter(
                module,
                time_fn=time_fn,
                budget_s=0.010,
                budget_hits_to_disable=3,
                budget_window=10,
            )
            adapter.reload()

            def render_once() -> list:
                # Each call: start at T, end at T+0.020 (over budget).
                started = []

                def stepped() -> float:
                    if not started:
                        started.append(True)
                        return clock["t"]
                    clock["t"] += 0.020
                    return clock["t"]

                adapter._time_fn = stepped
                return adapter.render(
                    "lab:slow",
                    beat_pos=0.0,
                    local_t=0.0,
                    frame_index=0,
                    params={},
                    segments=1,
                    seed=0,
                )

            for _ in range(3):
                frame = render_once()
                self.assertEqual(frame, [(1, 2, 3)])
            # Fourth call (or the call after 3 hits) is disabled → black.
            # After 3 over-budget hits in the window, subsequent renders are black.
            self.assertIn("slow", adapter._disabled)
            black = adapter.render(
                "lab:slow",
                beat_pos=0.0,
                local_t=0.0,
                frame_index=9,
                params={},
                segments=1,
                seed=0,
            )
            self.assertEqual(black, [(0, 0, 0)])

    def test_renderer_routes_lab_scene_through_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "effects_lab.py"
            _write_lab_module(module, _GOOD_LAB)
            adapter = LabProductionAdapter(module)
            adapter.reload()
            renderer = GoveeFrameRenderer(lab_adapter=adapter)
            frame = renderer.render(
                "lab:pulse",
                beat_pos=0.0,
                local_t=0.0,
                frame_index=0,
                params={},
                segments=3,
                seed=0,
            )
            self.assertEqual(frame, [(10, 20, 30)] * 3)


class LabAdapterFnAliasTests(unittest.TestCase):
    """AWR-260 follow-up: clone/Save-as drafts where name ≠ fn must still light."""

    def test_fn_neq_name_renders_lit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lab_dir = Path(tmp)
            module = lab_dir / "effects_lab.py"
            _write_lab_module(module, _GOOD_LAB)
            _write_drafts(
                lab_dir / "drafts.json",
                [_draft_entry("walkthrough_probe", fn="comet_trio_orbit")],
            )
            adapter = LabProductionAdapter(module)
            adapter.reload()
            frame = adapter.render(
                "lab:walkthrough_probe",
                beat_pos=0.0,
                local_t=0.0,
                frame_index=0,
                params={},
                segments=2,
                seed=1,
            )
            self.assertEqual(frame, [(40, 50, 60), (40, 50, 60)])
            self.assertTrue(
                adapter.is_available("lab:walkthrough_probe"),
                "fn≠name draft must be available for director bank picks",
            )

    def test_missing_drafts_json_name_eq_fn_still_renders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "effects_lab.py"
            _write_lab_module(module, _GOOD_LAB)
            # No drafts.json — name-only resolution must keep working.
            self.assertFalse((Path(tmp) / "drafts.json").exists())
            adapter = LabProductionAdapter(module)
            adapter.reload()
            self.assertEqual(adapter.draft_fn, {})
            frame = adapter.render(
                "lab:pulse",
                beat_pos=0.0,
                local_t=0.0,
                frame_index=0,
                params={},
                segments=1,
                seed=0,
            )
            self.assertEqual(frame, [(10, 20, 30)])

    def test_reload_picks_up_newly_accepted_fn_neq_name_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lab_dir = Path(tmp)
            module = lab_dir / "effects_lab.py"
            _write_lab_module(module, _GOOD_LAB)
            _write_drafts(lab_dir / "drafts.json", [_draft_entry("pulse")])
            adapter = LabProductionAdapter(module)
            adapter.reload()
            # Before the rename entry exists, walkthrough_probe is unknown → black.
            black = adapter.render(
                "lab:walkthrough_probe",
                beat_pos=0.0,
                local_t=0.0,
                frame_index=0,
                params={},
                segments=1,
                seed=0,
            )
            self.assertEqual(black, [(0, 0, 0)])
            # Accept / Save-as lands a new drafts.json entry; reload must see it.
            _write_drafts(
                lab_dir / "drafts.json",
                [
                    _draft_entry("pulse"),
                    _draft_entry("walkthrough_probe", fn="comet_trio_orbit"),
                ],
            )
            adapter.reload()
            lit = adapter.render(
                "lab:walkthrough_probe",
                beat_pos=1.0,
                local_t=0.5,
                frame_index=2,
                params={},
                segments=1,
                seed=0,
            )
            self.assertEqual(lit, [(40, 50, 60)])


def _minimal_led_config(*, looks: dict[str, LEDLook], banks: dict[str, list[str]]) -> LEDConfig:
    bank_kwargs = {role: tuple(names) for role, names in banks.items()}
    return LEDConfig(
        schema_version=1,
        enabled=True,
        dry_run=True,
        automation_enabled=True,
        targets={
            "room": LEDTarget(
                name="room",
                label="Room",
                device_ref="x",
                expected_model="",
                control_route="cloud",
            )
        },
        looks=looks,
        banks={"default": LEDBank(**bank_kwargs)},
        safe_default="safe",
        blackout="safe",
        automation=LEDAutomation(),
        rate_limits=LEDRateLimits(),
        safety=LEDSafety(),
    )


class LedReloadLooksTests(unittest.TestCase):
    def test_parse_command_accepts_led_reload_looks(self) -> None:
        self.assertEqual(parse_command('{"cmd":"led_reload_looks"}')["cmd"], "led_reload_looks")

    def test_parse_command_rejects_payload(self) -> None:
        with self.assertRaises(ValueError):
            parse_command('{"cmd":"led_reload_looks","x":1}')

    def test_replace_config_swaps_look_table(self) -> None:
        look_a = LEDLook(
            name="a",
            target="room",
            action="realtime",
            scene_ref="rt_groove_chase",
            safety_class="groove",
            backend="realtime_razer",
        )
        look_b = LEDLook(
            name="b",
            target="room",
            action="realtime",
            scene_ref="lab:pulse",
            safety_class="drop",
            backend="realtime_razer",
        )
        cfg1 = _minimal_led_config(
            looks={"a": look_a, "safe": look_a},
            banks={"drop": ["a"], "ambient": ["safe"]},
        )
        cfg2 = _minimal_led_config(
            looks={"b": look_b, "safe": look_a},
            banks={"drop": ["b"], "ambient": ["safe"]},
        )
        director = LEDLookDirector(cfg1)
        self.assertIn("a", director._config.looks)
        director.replace_config(cfg2)
        self.assertIn("b", director._config.looks)
        self.assertNotIn("a", director._config.looks)

    def test_command_reader_invokes_reload_callback(self) -> None:
        called = []

        class _VR:
            def mark_running(self, *_a, **_k):
                return None

            def run(self):
                return None

            def mark_failed(self, *_a, **_k):
                return None

            def last_result(self):
                return MagicMock(to_dict=lambda: {})

        reader = CommandReader(
            _VR(),
            led_reload_looks_callback=lambda: called.append(True) or True,
        )
        reader.handle_command({"cmd": "led_reload_looks"})
        self.assertEqual(called, [True])


class LabAcceptWireInTests(unittest.TestCase):
    def test_accept_writes_look_commits_and_appends_reload(self) -> None:
        from rb_ss_bridge_v2.tools.led_pad_web import LedPadService

        example = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"
        raw = json.loads(example.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "led_look_director.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            lab_dir = root / "led_lab"
            lab_dir.mkdir()
            _write_lab_module(lab_dir / "effects_lab.py", _GOOD_LAB)
            _write_drafts(
                lab_dir / "drafts.json",
                [
                    _draft_entry(
                        "walkthrough_probe",
                        fn="comet_trio_orbit",
                        target_role="drop",
                        params={"width": 2},
                    )
                ],
            )
            cmds: list[dict] = []

            class _FakePlayback:
                def ownership(self):
                    return {"state": "free"}

                def status(self):
                    return {"playing": False}

                def set_bpm(self, *_a, **_k):
                    return None

                def set_loop(self, *_a, **_k):
                    return None

                def play(self, *_a, **_k):
                    return None

                def update(self, *_a, **_k):
                    return None

                def stop(self):
                    return None

                def emergency_stop(self):
                    return None

                def request_takeover(self):
                    return None

                def release(self):
                    return None

                def shutdown(self):
                    return None

            service = LedPadService(
                config_path,
                dry_run=True,
                playback=_FakePlayback(),
                lab_dir=lab_dir,
            )
            service._append_bridge_command = cmds.append  # type: ignore[method-assign]
            result = service.lab_accept(
                {
                    "name": "walkthrough_probe",
                    "updated": "2026-07-16T00:00:00+00:00",
                    "target_role": "drop",
                    "params": {"width": 2},
                }
            )
            self.assertTrue(result.get("ok"), result)
            self.assertTrue(result.get("wired"), result)
            self.assertEqual(result.get("bank"), "drop")
            self.assertIn("Drop", result.get("message", ""))
            live = json.loads(config_path.read_text(encoding="utf-8"))
            look = (live.get("looks") or {}).get("walkthrough_probe")
            self.assertIsNotNone(look)
            self.assertEqual(look.get("scene_ref"), "lab:walkthrough_probe")
            self.assertEqual(look.get("color_source"), "engine")
            bank = ((live.get("banks") or {}).get("default") or {}).get("drop") or []
            self.assertIn("walkthrough_probe", bank)
            self.assertEqual(cmds, [{"cmd": "led_reload_looks"}])
            # Gate class: production adapter must light the fn≠name accepted draft.
            adapter = LabProductionAdapter(lab_dir / "effects_lab.py")
            adapter.reload()
            frame = adapter.render(
                "lab:walkthrough_probe",
                beat_pos=0.0,
                local_t=0.0,
                frame_index=0,
                params=look.get("params") or {},
                segments=2,
                seed=0,
            )
            self.assertEqual(frame, [(40, 50, 60), (40, 50, 60)])

    def test_accept_untagged_goes_to_drafts_shelf(self) -> None:
        from rb_ss_bridge_v2.tools.led_pad_web import LedPadService

        example = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"
        raw = json.loads(example.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "led_look_director.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            lab_dir = root / "led_lab"
            lab_dir.mkdir()
            _write_lab_module(lab_dir / "effects_lab.py", _GOOD_LAB)
            _write_drafts(
                lab_dir / "drafts.json",
                [_draft_entry("pulse", fn="pulse", target_role="")],
            )

            class _FakePlayback:
                def ownership(self):
                    return {"state": "free"}

                def status(self):
                    return {"playing": False}

                def set_bpm(self, *_a, **_k):
                    return None

                def set_loop(self, *_a, **_k):
                    return None

                def shutdown(self):
                    return None

            service = LedPadService(
                config_path,
                dry_run=True,
                playback=_FakePlayback(),
                lab_dir=lab_dir,
            )
            service._append_bridge_command = lambda *_a, **_k: None  # type: ignore[method-assign]
            result = service.lab_accept(
                {"name": "pulse", "updated": "2026-07-16T00:00:00+00:00", "target_role": ""}
            )
            self.assertTrue(result.get("ok"), result)
            self.assertEqual(result.get("bank"), "drafts")
            self.assertIn("untagged", result.get("message", "").lower())
            live = json.loads(config_path.read_text(encoding="utf-8"))
            drafts = (live.get("_pad_meta") or {}).get("drafts") or []
            self.assertIn("pulse", drafts)


if __name__ == "__main__":
    unittest.main()
