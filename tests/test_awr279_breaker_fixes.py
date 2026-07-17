"""AWR-279 breaker-audit fixes — live-safety, conflict honesty, input hygiene.

Behavior tests for the Python surfaces (playback belt, cue clamp, ownership
warning lifecycle, name caps, archive guard, preview-tempo range) plus static
integrity checks for the JS/CSS surfaces (no browser required, matching the
existing led-pad UI-integrity pattern).
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools.led_pad_lab import (  # noqa: E402
    LabRegistry,
    _MAX_NAME_LEN as LAB_MAX_NAME_LEN,
    slugify_lab_name,
)
from rb_ss_bridge_v2.tools.led_pad_playback import CueTimer, OwnershipGate  # noqa: E402
from rb_ss_bridge_v2.tools.led_pad_web import (  # noqa: E402
    LedPadService,
    _MAX_NAME_LEN,
    _clamp_cue_beats,
)

_ASSETS = Path(__file__).resolve().parents[1] / "tools" / "led_pad_assets"
_SIM = Path(__file__).resolve().parents[1] / "tools" / "led_sim_assets"
_EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"


class _FakePlayback:
    """Records the values the service hands the playback engine."""

    def __init__(self) -> None:
        self.ownership_state = "free"
        self.play_calls: list[dict] = []
        self.bpm = 128.0
        self.playing = ""

    def ownership(self) -> dict:
        return {"state": self.ownership_state, "warning": ""}

    def request_takeover(self) -> None:
        self.ownership_state = "pad_owned"

    def play(self, spec: dict, *, cue_beats: float, loop: bool) -> None:
        self.play_calls.append({"spec": spec, "cue_beats": cue_beats, "loop": loop})
        self.playing = spec["look_name"]

    def update(self, spec: dict) -> None:
        pass

    def set_bpm(self, bpm: float) -> None:
        self.bpm = bpm

    def set_loop(self, loop: bool) -> None:
        pass

    def stop(self) -> None:
        self.playing = ""

    def status(self) -> dict:
        return {"playing_look": self.playing, "playing": bool(self.playing), "bpm": self.bpm}


def _lab_service(td: str) -> tuple[LedPadService, _FakePlayback]:
    playback = _FakePlayback()
    path = Path(td) / "led_look_director.json"
    shutil.copy2(_EXAMPLE, path)
    lab_dir = Path(td) / "led_lab"
    lab_dir.mkdir(parents=True, exist_ok=True)
    (lab_dir / "effects_lab.py").write_text(
        "def pulse(beat_pos, local_t, frame_index, params, segments, seed):\n"
        "    return [[params.get('level', 1.0), 0, 0, 0, 0, 0] for _ in range(segments)]\n"
        "LAB_EFFECTS = {'pulse': ('slot', pulse)}\n",
        encoding="utf-8",
    )
    return LedPadService(path, dry_run=True, playback=playback, lab_dir=lab_dir), playback


# --------------------------------------------------------------------------- #
# Priority 1 — live-set dangers
# --------------------------------------------------------------------------- #
class Awr279NeverStoppingPlayOnce(unittest.TestCase):
    """#2 — a loop-off 'Play once' can never stream forever."""

    def test_cue_timer_nonpositive_non_loop_stops_immediately(self) -> None:
        now = [0.0]
        timer = CueTimer(time_fn=lambda: now[0])
        # A nonpositive length that slips past the server clamp must still stop.
        for bad in (0.0, -4.0):
            timer.start(cue_beats=bad, bpm=120, loop=False)
            self.assertTrue(timer.active, f"non-loop cue {bad} must arm the guard")
            self.assertTrue(timer.should_stop(), f"non-loop cue {bad} must stop now")

    def test_cue_timer_nonpositive_loop_never_stops(self) -> None:
        now = [0.0]
        timer = CueTimer(time_fn=lambda: now[0])
        timer.start(cue_beats=0, bpm=120, loop=True)
        now[0] = 100.0
        self.assertFalse(timer.should_stop())

    def test_cue_timer_positive_non_loop_unchanged(self) -> None:
        now = [0.0]
        timer = CueTimer(time_fn=lambda: now[0])
        timer.start(cue_beats=4, bpm=120, loop=False)
        now[0] = 1.9
        self.assertFalse(timer.should_stop())
        now[0] = 2.0
        self.assertTrue(timer.should_stop())

    def test_clamp_cue_beats_floors_and_defaults(self) -> None:
        self.assertEqual(_clamp_cue_beats(-5), 16.0)
        self.assertEqual(_clamp_cue_beats(0), 16.0)
        self.assertEqual(_clamp_cue_beats(0, default=1.0), 1.0)
        self.assertEqual(_clamp_cue_beats(0.5), 1.0)
        self.assertEqual(_clamp_cue_beats(8), 8.0)
        self.assertEqual(_clamp_cue_beats("nan"), 16.0)
        self.assertEqual(_clamp_cue_beats(None), 16.0)

    def test_lab_save_clamps_negative_cue_beats(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _pb = _lab_service(td)
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {}, "cue_beats": 8})
            # A negative from another client must be floored, not stored.
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {}, "cue_beats": -20})
            self.assertGreaterEqual(float(service._lab.get("pulse")["cue_beats"]), 1.0)

    def test_lab_play_clamps_negative_cue_beats(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback = _lab_service(td)
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {}, "cue_beats": 8})
            service.lab_play({"name": "pulse", "cue_beats": -3})
            self.assertGreaterEqual(playback.play_calls[-1]["cue_beats"], 1.0)
            self.assertFalse(playback.play_calls[-1]["loop"])


class Awr279StopButtonReachable(unittest.TestCase):
    """#1 — the ■ STOP cluster is never occluded by the look-editor drawer."""

    @staticmethod
    def _z(css: str, selector: str) -> int:
        block = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
        assert block, f"missing rule {selector}"
        z = re.search(r"z-index:\s*(\d+)", block.group(1))
        assert z, f"no z-index in {selector}"
        return int(z.group(1))

    def test_topbar_stacks_above_drawer_and_drawer_is_offset(self) -> None:
        css = (_ASSETS / "pad.css").read_text(encoding="utf-8")
        topbar_z = self._z(css, ".topbar")
        drawer_z = self._z(css, ".drawer")
        # STOP lives in the topbar; it must win the stack so it stays hit-testable.
        self.assertGreater(topbar_z, drawer_z)
        # A modal backdrop must still cover the topbar.
        self.assertLess(topbar_z, self._z(css, ".modal-backdrop"))
        # The drawer starts BELOW the topbar (never overlays the STOP cluster).
        drawer_block = re.search(r"\.drawer\s*\{([^}]*)\}", css).group(1)
        self.assertIn("top: var(--topbar-h", drawer_block)
        self.assertNotRegex(drawer_block, r"top:\s*0\b")

    def test_shell_measures_topbar_height(self) -> None:
        shell = (_ASSETS / "shell.js").read_text(encoding="utf-8")
        self.assertIn("--topbar-h", shell)
        self.assertIn("ResizeObserver", shell)
        self.assertIn(".topbar", shell)


# --------------------------------------------------------------------------- #
# Priority 2 — conflict / failure honesty
# --------------------------------------------------------------------------- #
class Awr279OwnershipWarningLifecycle(unittest.TestCase):
    """#6 — the 'bridge reappeared' warning expires, it does not stick forever."""

    def _gate(self, status):
        return OwnershipGate(
            time_fn=lambda: 100.0,
            sleep_fn=lambda _s: None,
            status_reader=lambda: status,
            appender=lambda _c: None,
        )

    def test_reassert_sets_then_clears_on_healthy_tick(self) -> None:
        status = {"written_at": 100.0, "led_look_director": {"emergency_blackout": False}}
        gate = self._gate(status)
        gate.state = "pad_owned"
        gate.poll_owned()  # bridge reasserting (no blackout latched) → warn
        self.assertEqual(gate.last_warning, "bridge_reasserted_takeover")
        status["led_look_director"]["emergency_blackout"] = True  # our blackout holds
        gate.poll_owned()  # healthy pad-owned tick → warning expires
        self.assertEqual(gate.last_warning, "")

    def test_reassert_clears_when_bridge_goes_away(self) -> None:
        status = {"written_at": 100.0, "led_look_director": {"emergency_blackout": False}}
        gate = self._gate(status)
        gate.state = "pad_owned"
        gate.poll_owned()
        self.assertEqual(gate.last_warning, "bridge_reasserted_takeover")
        gate._status_reader = lambda: None  # bridge down
        gate.poll_owned()
        self.assertEqual(gate.last_warning, "")

    def test_release_and_takeover_clear_warning(self) -> None:
        status = {"written_at": 100.0, "led_look_director": {"emergency_blackout": False}}
        gate = self._gate(status)
        gate.state = "pad_owned"
        gate.last_warning = "auto_stopped_bridge_active"
        gate.release()
        self.assertEqual(gate.last_warning, "")
        gate.last_warning = "bridge_reasserted_takeover"
        gate.request_takeover()
        self.assertEqual(gate.last_warning, "")


class Awr279ConflictHonestyStatic(unittest.TestCase):
    """#3/#4/#5 — Reload lands disk state; stale play-once aborts; reload failure shows."""

    def test_reload_discards_local_stash(self) -> None:
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        # A guard flag stops the dirty DOM being re-stashed over the pulled version.
        self.assertIn("let suppressStash = false;", lab)
        self.assertIn("if (suppressStash) return;", lab)
        self.assertIn("function reloadFromDisk()", lab)
        self.assertIn("suppressStash = true;", lab)
        # Reload buttons use the discard-stash path, not a bare refresh.
        self.assertEqual(lab.count('{label: "Reload", className: "ghost", run: reloadFromDisk}'), 3)

    def test_stale_save_signals_failure_and_play_aborts(self) -> None:
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        # save() returns false on a stale conflict; play() bails on a falsy save.
        self.assertIn("return false;", lab)
        self.assertIn("saved = await save();", lab)
        self.assertIn("if (!saved) return;", lab)

    def test_reload_code_recovers_failure_payload(self) -> None:
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        # request() throws on {ok:false,error}; reloadCode recovers err.payload.
        self.assertIn("res = (err && err.payload)", lab)
        self.assertIn('$("tracePanel").hidden = false;', lab)
        self.assertIn("state.health.labOk = Boolean(res.ok);", lab)


# --------------------------------------------------------------------------- #
# Priority 3 — shell + input hygiene
# --------------------------------------------------------------------------- #
class Awr279EscapeOwner(unittest.TestCase):
    """#7 — one shell-level Escape owner; per-view handlers don't fight the modal."""

    def test_shell_owns_escape(self) -> None:
        shell = (_ASSETS / "shell.js").read_text(encoding="utf-8")
        self.assertIn("function registerEscape(view, fn)", shell)
        self.assertIn("function onEscape(ev)", shell)
        self.assertIn('document.addEventListener("keydown", onEscape)', shell)
        self.assertIn("window.PadModal.close()", shell)
        self.assertIn("registerEscape,", shell)  # exported on LightingShell

    def test_views_register_and_do_not_double_close_modal(self) -> None:
        pad = (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        self.assertIn('window.LightingShell.registerEscape("pad", padEscape)', pad)
        self.assertIn('window.LightingShell.registerEscape("lab", labEscape)', lab)
        # The registered view handlers themselves must not touch the shared modal.
        self.assertIn("function padEscape() {", pad)
        self.assertIn("function labEscape() {", lab)


class Awr279NameHygiene(unittest.TestCase):
    """#8 — names are length-capped end to end; empty names are refused honestly."""

    def test_pad_name_length_cap(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _pb = _lab_service(td)
            too_long = "a" * (_MAX_NAME_LEN + 1)
            with self.assertRaises(ValueError):
                service.duplicate_look({"source": "rt_groove_chase", "new_name": too_long})

    def test_lab_name_length_cap_and_slug_truncation(self) -> None:
        with self.assertRaises(ValueError):
            LabRegistry._validate_name("z" * (LAB_MAX_NAME_LEN + 1), check_collision=False)
        slug = slugify_lab_name("Some Very " + "Long " * 40 + "Name")
        self.assertLessEqual(len(slug), LAB_MAX_NAME_LEN)

    def test_client_name_inputs_capped_and_validated(self) -> None:
        pad_core = (_ASSETS / "pad-core.js").read_text(encoding="utf-8")
        pad = (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        # Modal fields accept a maxlength and validate before closing.
        self.assertIn("maxlength=", pad_core)
        self.assertIn("opts.validate", pad_core)
        self.assertIn("showFieldError", pad_core)
        # Duplicate/rename cap + honest empty message; New-cue validates before close.
        self.assertIn('maxlength: 60, validate:', pad)
        self.assertIn('showError("Give the look a name")', pad)
        self.assertIn("validate: (v) => String(v.display_name", lab)


class Awr279ArchiveGuard(unittest.TestCase):
    """#9 — a draft that's live on the lights can't be archived."""

    def test_archive_blocked_while_playing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _pb = _lab_service(td)
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {}, "cue_beats": 8})
            service.lab_play({"name": "pulse"})
            result = service.lab_archive({"name": "pulse"})
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "stop_playback_first")

    def test_archive_allowed_when_idle(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _pb = _lab_service(td)
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {}, "cue_beats": 8})
            result = service.lab_archive({"name": "pulse"})
            self.assertTrue(result["ok"])


class Awr279PreviewTempoRange(unittest.TestCase):
    """#10 — the Preview tempo is clamped to the declared 60-200 range."""

    def _service(self, td: str) -> tuple[LedPadService, _FakePlayback]:
        playback = _FakePlayback()
        path = Path(td) / "led_look_director.json"
        shutil.copy2(_EXAMPLE, path)
        return LedPadService(path, dry_run=True, playback=playback), playback

    def test_high_bpm_clamps_to_max(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._service(td)
            out = service.session({"bpm": 300})
            self.assertEqual(out["session"]["bpm"], 200.0)
            self.assertEqual(playback.bpm, 200.0)

    def test_low_bpm_clamps_to_min(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._service(td)
            out = service.session({"bpm": 30})
            self.assertEqual(out["session"]["bpm"], 60.0)
            self.assertEqual(playback.bpm, 60.0)

    def test_client_syncs_and_clears_banner(self) -> None:
        pad = (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")
        self.assertIn("Math.max(60, Math.min(200,", pad)
        self.assertIn("res.session.bpm", pad)


# --------------------------------------------------------------------------- #
# Priority 4 — sim + cosmetics
# --------------------------------------------------------------------------- #
class Awr279SimFixes(unittest.TestCase):
    """#11/#12/#13 — sim error copy, dialog keyboard, rail-tab expand."""

    def test_error_banner_prefers_message(self) -> None:
        sim = (_SIM / "sim-app.js").read_text(encoding="utf-8")
        self.assertIn("data.message || data.error", sim)

    def test_dialog_keyboard_bound_at_dialog_level(self) -> None:
        sim = (_SIM / "sim-app.js").read_text(encoding="utf-8")
        # Both dialogs bind keys on the dialog (survive tabbing to a button), and
        # neither leaves an input-level keydown binding.
        self.assertNotIn("input.onkeydown", sim)
        self.assertGreaterEqual(sim.count("dialog.onkeydown = (event)"), 2)
        # Outside-click keeps focus in the dialog.
        self.assertIn("dialog.contains(event.target)", sim)

    def test_rail_tab_expands_collapsed_sidecar(self) -> None:
        sim = (_SIM / "sim-app.js").read_text(encoding="utf-8")
        # The rail-tab CLICK handler expands the sidecar when it's collapsed. The
        # only place the collapse class is REMOVED in sim-app.js is this handler.
        self.assertIn('if (document.body.classList.contains("sidecar-collapsed")) {', sim)
        self.assertIn('document.body.classList.remove("sidecar-collapsed")', sim)
        click_handler = re.search(
            r'\.rail-btn\[data-tab\]"\)\) \{\s*\n\s*btn\.addEventListener\("click", \(\) => \{(.*?)\n    \}\);',
            sim,
            flags=re.S,
        )
        self.assertIsNotNone(click_handler)
        self.assertIn('classList.remove("sidecar-collapsed")', click_handler.group(1))


class Awr279SnapshotFallbackCalm(unittest.TestCase):
    """#14 — the client only claims a live snapshot when it actually live-tuned."""

    def test_client_gates_expect_live_snapshot(self) -> None:
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        self.assertIn("state.liveApplied", lab)
        self.assertIn("payload.expect_live_snapshot = true", lab)


if __name__ == "__main__":
    unittest.main()
