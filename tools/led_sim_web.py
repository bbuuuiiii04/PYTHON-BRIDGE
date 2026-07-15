"""H612D simulator web server (AWR-196) — 127.0.0.1:8767, stdlib only.

Offline tooling. Mirrors the LED Pad server PATTERN (ThreadingHTTPServer +
handler closure) without importing from tools.led_pad_web (AWR-193 fence).
The only socket this process opens is its own loopback HTTP listener — the
sim NEVER contacts the Govee device (no UDP, no transport/discovery imports).

Run: python3 -m tools.led_sim_web [--port 8767] [--profile config/led_sim_profile.json]
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import sys
import tempfile
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parents[1]

try:
    from . import led_sim_engine as engine
except ImportError:  # run as `python3 -m tools.led_sim_web` from the repo root
    if str(_REPO_ROOT.parent) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT.parent))
    from rb_ss_bridge_v2.tools import led_sim_engine as engine  # type: ignore

logger = logging.getLogger("led_sim_web")

ASSETS_DIR = Path(__file__).resolve().parent / "led_sim_assets"

MAX_DURATION_S = 30.0
MAX_FPS = 120


class LedSimService:
    """Request-scoped glue over the pure engine; no state cached across requests."""

    def __init__(self, profile_path: Path | str | None = None) -> None:
        self.profile_path = Path(profile_path) if profile_path else engine.DEFAULT_PROFILE_PATH

    def profile_state(self) -> tuple[dict[str, Any], str]:
        """Current profile + error string; old profiles inherit new defaults."""
        error = ""
        try:
            example = engine.load_profile(engine.EXAMPLE_PROFILE_PATH)
        except Exception as exc:
            return {}, f"{engine.EXAMPLE_PROFILE_PATH.name}: {exc}"
        if self.profile_path.exists():
            try:
                profile = {**example, **engine.load_profile(self.profile_path)}
                errors = engine.validate_profile(profile)
                if not errors:
                    return profile, ""
                error = f"{self.profile_path.name}: " + "; ".join(errors)
            except Exception as exc:
                error = f"{self.profile_path.name}: {exc}"
        return example, error

    def catalog(self) -> dict[str, Any]:
        profile, profile_error = self.profile_state()
        looks = engine.look_params_catalog()
        lab = engine.lab_catalog()
        return {
            "effects": sorted(engine.REALTIME_EFFECT_NAMES),
            "looks": looks,
            "lab": lab,
            "profile": profile,
            "profile_error": profile_error,
            "lab_error": lab.get("error", ""),
            "test_cards": list(engine.TEST_CARD_KINDS),
            "calibration_sequences": list(engine.CALIBRATION_SEQUENCE_NAMES),
            "device": {
                "model": engine.H612D_MODEL,
                "segments": engine.H612D_SEGMENTS,
                "physical_leds": engine.H612D_PHYSICAL_LEDS,
                "leds_per_segment": engine.H612D_LEDS_PER_SEGMENT,
                "strip_length_mm": engine.H612D_LENGTH_MM,
            },
        }

    def segments(self) -> int:
        profile, _ = self.profile_state()
        value = profile.get("segments", 60)
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else 60


def _replay_path_allowed(raw: str) -> Path | None:
    """Frames-JSONL paths must live inside the repo or the temp dir."""
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = _REPO_ROOT / candidate
    resolved = candidate.resolve()
    allowed = {_REPO_ROOT.resolve(), Path("/tmp").resolve(), Path(tempfile.gettempdir()).resolve()}
    for base in allowed:
        try:
            resolved.relative_to(base)
            return resolved
        except ValueError:
            continue
    return None


def build_handler(service: LedSimService) -> type[BaseHTTPRequestHandler]:
    class _LedSimHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            logger.debug("%s %s", self.address_string(), format % args)

        # -- plumbing ---------------------------------------------------------
        def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw or b"{}")
            if not isinstance(data, dict):
                raise ValueError("request body must be a JSON object")
            return data

        def _bad_request(self, message: str, **extra: Any) -> None:
            self._send_json({"error": message, **extra}, HTTPStatus.BAD_REQUEST)

        # -- static ------------------------------------------------------------
        def _serve_static(self, path: str) -> None:
            rel = path.lstrip("/") or "index.html"
            target = (ASSETS_DIR / rel).resolve()
            try:
                target.relative_to(ASSETS_DIR.resolve())
            except ValueError:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            if not target.is_file():
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            body = target.read_bytes()
            self.send_response(int(HTTPStatus.OK))
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # -- routes -------------------------------------------------------------
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                if path == "/api/catalog":
                    self._send_json(service.catalog())
                elif path == "/api/profile":
                    profile, profile_error = service.profile_state()
                    self._send_json({
                        "profile": profile,
                        "profile_error": profile_error,
                        "path": str(service.profile_path),
                    })
                else:
                    self._serve_static(path)
            except Exception as exc:  # surface, never hide (local operator tool)
                self._send_json(
                    {"error": str(exc), "traceback": traceback.format_exc()},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                try:
                    body = self._read_json_body()
                except (json.JSONDecodeError, ValueError) as exc:
                    self._bad_request(f"invalid JSON body: {exc}")
                    return
                if path == "/api/render":
                    self._handle_render(body)
                elif path == "/api/render_card":
                    self._handle_render_card(body)
                elif path == "/api/calibration":
                    self._handle_calibration(body)
                elif path == "/api/profile":
                    self._handle_profile_save(body)
                elif path == "/api/replay/load":
                    self._handle_replay_load(body)
                else:
                    self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except Exception as exc:  # render/engine exception → 500 + traceback
                self._send_json(
                    {"error": str(exc), "traceback": traceback.format_exc()},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        # -- endpoint bodies -----------------------------------------------------
        def _handle_render(self, body: dict[str, Any]) -> None:
            source = body.get("source", "effect")
            if source not in ("effect", "lab"):
                self._bad_request("source must be 'effect' or 'lab'")
                return
            name = body.get("name")
            if not isinstance(name, str) or not name:
                self._bad_request("name must be a non-empty string")
                return
            params = body.get("params", {})
            if not isinstance(params, dict):
                self._bad_request("params must be a JSON object")
                return
            try:
                seed = int(body.get("seed", 0))
                fps = int(body.get("fps", 60))
                duration_s = float(body.get("duration_s", 4.0))
                bpm = float(body.get("bpm", 128.0))
                beat_division = float(body.get("beat_division", 0.0))
            except (TypeError, ValueError):
                self._bad_request("seed/fps/duration_s/bpm/beat_division must be numeric")
                return
            sync_mode = body.get("sync_mode", "")
            if not isinstance(sync_mode, str):
                self._bad_request("sync_mode must be a string")
                return
            if not (1 <= fps <= MAX_FPS):
                self._bad_request(f"fps must be in [1, {MAX_FPS}]")
                return
            if not (0.0 < duration_s <= MAX_DURATION_S):
                self._bad_request(f"duration_s must be in (0, {MAX_DURATION_S:g}]")
                return
            if bpm <= 0:
                self._bad_request("bpm must be positive")
                return
            segments = service.segments()
            if source == "lab":
                result = engine.render_lab_frames(
                    name, params=params, seed=seed, fps=fps,
                    duration_s=duration_s, bpm=bpm, segments=segments,
                )
                if not result["ok"]:
                    self._send_json(
                        {"error": f"lab render failed: {result['error']}"},
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                frames = result["frames"]
            else:
                # Use the real runner composition, not the raw effect function.
                frames = engine.render_runtime_frames(
                    name, params=params, seed=seed, fps=fps,
                    duration_s=duration_s, bpm=bpm, segments=segments,
                    sync_mode=sync_mode, beat_division=beat_division,
                )
            self._send_json({
                "frames": frames,
                "fps": fps,
                "segments": segments,
                "t_ms": engine.frame_timestamps(len(frames), fps),
                "pipeline": "lab" if source == "lab" else "runtime",
            })

        def _handle_render_card(self, body: dict[str, Any]) -> None:
            kind = body.get("kind")
            if not isinstance(kind, str) or kind not in engine.TEST_CARD_KINDS:
                self._bad_request(f"kind must be one of {sorted(engine.TEST_CARD_KINDS)}")
                return
            segments = service.segments()
            frames = engine.test_card_frames(kind, segments)
            self._send_json({"frames": frames, "fps": 1, "segments": segments, "t_ms": [0]})

        def _handle_calibration(self, body: dict[str, Any]) -> None:
            name = body.get("name")
            if not isinstance(name, str) or name not in engine.CALIBRATION_SEQUENCE_NAMES:
                self._bad_request(f"name must be one of {list(engine.CALIBRATION_SEQUENCE_NAMES)}")
                return
            try:
                fps = int(body.get("fps", 60))
            except (TypeError, ValueError):
                self._bad_request("fps must be numeric")
                return
            if not (1 <= fps <= MAX_FPS):
                self._bad_request(f"fps must be in [1, {MAX_FPS}]")
                return
            self._send_json(engine.calibration_sequence(name, segments=service.segments(), fps=fps))

        def _handle_profile_save(self, body: dict[str, Any]) -> None:
            errors = engine.validate_profile(body)
            if errors:
                self._send_json({"ok": False, "errors": errors}, HTTPStatus.BAD_REQUEST)
                return
            engine.save_profile(service.profile_path, body)
            self._send_json({"ok": True, "profile": body, "path": str(service.profile_path)})

        def _handle_replay_load(self, body: dict[str, Any]) -> None:
            raw = body.get("path")
            if not isinstance(raw, str) or not raw:
                self._bad_request("path must be a non-empty string")
                return
            resolved = _replay_path_allowed(raw)
            if resolved is None:
                self._bad_request("path must be inside the repo or the temp dir")
                return
            if not resolved.is_file():
                self._send_json({"error": f"no such file: {resolved}"}, HTTPStatus.NOT_FOUND)
                return
            try:
                payload = engine.read_frames_jsonl(resolved)
            except ValueError as exc:
                self._bad_request(str(exc))
                return
            payload["path"] = str(resolved)
            self._send_json(payload)

    return _LedSimHandler


def run_server(*, port: int = 8767, profile_path: Path | str | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    service = LedSimService(profile_path=profile_path)
    # Loopback ONLY, by design — this tool never accepts non-local connections.
    server = ThreadingHTTPServer(("127.0.0.1", int(port)), build_handler(service))
    logger.info("LED sim listening on http://127.0.0.1:%s", port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local LED room simulator")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--profile", default=None,
                        help="device profile path (default config/led_sim_profile.json, falling back to the example)")
    args = parser.parse_args(argv)
    try:
        run_server(port=args.port, profile_path=args.profile)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
