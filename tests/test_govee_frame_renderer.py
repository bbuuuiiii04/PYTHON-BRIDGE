from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    EDM_BUILDS,
    GoveeFrameRenderer,
)


ACTIVE_CUES = (
    "buildup_ramp_1",
    "buildup_ramp_2",
    "buildup_ramp_3",
    "buildup_white_zone_strobe",
    "buildup_white_half_strobe",
    "buildup_freestyle_nebula",
    "groove_chase_blue",
    "groove_chase_cyan",
    "groove_chase_red",
    "groove_chase_green",
    "groove_chase_cyan_white",
    "groove_freestyle_nebula",
    "drop_chase_blue",
    "drop_chase_cyan",
    "drop_chase_red",
    "drop_chase_green",
    "drop_chase_cyan_white",
    "drop_chase_freestyle_nebula",
)


class GoveeFrameRendererTests(unittest.TestCase):
    def test_requested_active_cues_are_registered(self) -> None:
        for cue in ACTIVE_CUES:
            self.assertIn(cue, EDM_BUILDS)

    def test_active_cues_render_segment_frames(self) -> None:
        renderer = GoveeFrameRenderer()
        for cue in ACTIVE_CUES:
            with self.subTest(cue=cue):
                frame = renderer.render(
                    cue,
                    beat_pos=8.25,
                    local_t=1.5,
                    frame_index=12,
                    params={},
                    segments=20,
                    seed=123,
                )
                self.assertEqual(len(frame), 20)
                for pixel in frame:
                    self.assertEqual(len(pixel), 3)
                    self.assertTrue(all(0 <= value <= 255 for value in pixel))

    def test_renderer_is_deterministic_for_fixed_inputs(self) -> None:
        renderer = GoveeFrameRenderer()

        a = renderer.render(
            "drop_chase_freestyle_nebula",
            beat_pos=2.125,
            local_t=0.4,
            frame_index=3,
            params={},
            segments=20,
            seed=77,
        )
        b = renderer.render(
            "drop_chase_freestyle_nebula",
            beat_pos=2.125,
            local_t=0.4,
            frame_index=3,
            params={},
            segments=20,
            seed=77,
        )

        self.assertEqual(a, b)

    def test_unknown_effect_fails_dark(self) -> None:
        renderer = GoveeFrameRenderer()

        frame = renderer.render(
            "missing_effect",
            beat_pos=0.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=4,
            seed=1,
        )

        self.assertEqual(frame, [(0, 0, 0)] * 4)


if __name__ == "__main__":
    unittest.main()
