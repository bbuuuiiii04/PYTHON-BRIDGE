#!/usr/bin/env python3
"""Direct UDP groove chase — bypasses bridge, drives Govee strip via production runner."""
from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    GoveeFrameRenderer,
    default_beat_division,
    default_sync_mode,
)
from rb_ss_bridge_v2.govee_realtime_runner import EffectSpec, GoveeRealtimeRunner  # noqa: E402
from rb_ss_bridge_v2.govee_realtime_transport import GoveeRealtimeTransport  # noqa: E402
from rb_ss_bridge_v2.led_config import load_led_look_director_config  # noqa: E402
from rb_ss_bridge_v2.led_models import BeatAnchor  # noqa: E402

DEFAULT_BPM = 126.0
CONFIG = ROOT / "config" / "led_look_director.json"
DEFAULT_LOOK = "rt_groove_chase_blue"


def main() -> None:
    look_key = DEFAULT_LOOK
    beat_limit: float | None = None
    bpm = DEFAULT_BPM
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--beats" and i + 1 < len(args):
            beat_limit = float(args[i + 1])
            i += 2
        elif args[i] == "--bpm" and i + 1 < len(args):
            bpm = float(args[i + 1])
            i += 2
        else:
            look_key = args[i]
            i += 1
    if bpm <= 0.0:
        raise SystemExit("--bpm must be positive")
    loaded = load_led_look_director_config(str(CONFIG))
    if not loaded.available:
        raise SystemExit(f"config invalid: {loaded.errors}")
    cfg = loaded.config
    if look_key not in cfg.looks:
        raise SystemExit(f"unknown look: {look_key}")
    rt = cfg.targets["room_perimeter"].realtime
    look = cfg.looks[look_key]

    transport = GoveeRealtimeTransport(
        rt.ip,
        port=rt.port,
        segments=rt.segments,
        header_bytes=rt.header_bytes,
        stretch=rt.stretch,
        activate_pt=rt.activate_pt,
        deactivate_pt=rt.deactivate_pt,
    )
    runner = GoveeRealtimeRunner(
        transport,
        GoveeFrameRenderer(),
        segments=rt.segments,
        fps=rt.fps,
    )
    t0 = time.monotonic()

    def beat_provider() -> BeatAnchor:
        now = time.monotonic()
        return BeatAnchor(
            deck=1,
            abs_beat_pos=(now - t0) * (bpm / 60.0),
            bpm=bpm,
            captured_monotonic=now,
            playing=True,
            permitted=True,
        )

    runner.set_beat_provider(beat_provider)
    runner.set_desired(
        EffectSpec(
            effect_name=look.scene_ref,
            params=dict(look.params),
            seed=42,
            applied_monotonic=t0,
            sync_mode=default_sync_mode(look.scene_ref),
            beat_division=default_beat_division(look.scene_ref),
        )
    )
    runner.fire_trigger()
    runner.start()
    print(
        f"[direct-rt] {look_key} ({look.scene_ref}) → {rt.ip}:{rt.port} "
        f"@ {rt.fps}fps {bpm}bpm params={dict(look.params)}"
        + (f" duration={beat_limit} beats" if beat_limit else " duration=∞"),
        flush=True,
    )

    end_at = (t0 + beat_limit * (60.0 / bpm)) if beat_limit else None

    def stop(*_: object) -> None:
        print("[direct-rt] stopping", flush=True)
        runner.stop()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    last_fi = -1
    while True:
        if end_at is not None and time.monotonic() >= end_at:
            print(f"[direct-rt] finished {beat_limit} beats", flush=True)
            runner.stop()
            return
        time.sleep(1.0 if end_at is None else min(1.0, max(0.05, end_at - time.monotonic())))
        if not runner._thread or not runner._thread.is_alive():
            print("[direct-rt] ERROR runner thread died — exiting", flush=True)
            runner.stop()
            raise SystemExit(1)
        st = runner.status()
        fi = int(st.get("frame_index", 0))
        if fi == last_fi:
            print(f"[direct-rt] WARN no frames in 1s (frame_index={fi})", flush=True)
        else:
            print(f"[direct-rt] ok frame_index={fi} instances={st.get('instance_count')}", flush=True)
        last_fi = fi


if __name__ == "__main__":
    main()
