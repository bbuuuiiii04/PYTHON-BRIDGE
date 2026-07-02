"""Scripted first-event and carry-forward fidelity tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_laser_player import ZERO_FRAME, render_scripted_frame
from rb_ss_bridge_v2.soundswitch_pack import render_document_boundaries
from rb_ss_bridge_v2.soundswitch_pack_loader import LoadedAttribute, LoadedDocument, LoadedTimelineEvent
from rb_ss_bridge_v2.soundswitch_pack_models import (
    AttributeCue,
    CueAttribute,
    LightingDocument,
    TimelineRecord,
)


def _cue(guid: str, *attrs: tuple[int, int]) -> AttributeCue:
    return AttributeCue(
        0,
        0,
        "fixture_payload",
        guid,
        "0" * 64,
        "p",
        tuple(CueAttribute(i, 0x493, 81 + channel, channel, value)
              for i, (channel, value) in enumerate(attrs)),
    )


class ScriptedFirstEventTests(unittest.TestCase):
    def test_boundary_render_all_zero_seed_and_unresolved_rows_hold(self) -> None:
        cue = _cue("a" * 32, (1, 12), (8, 99))
        doc = LightingDocument(
            "script.ssfile",
            "0" * 64,
            3,
            1,
            "p",
            "x",
            1,
            (),
            (
                TimelineRecord(100, 1, 10, 1, "cue", 1, None),
                TimelineRecord(116, 1, 20, 2, "cue", 2, cue.cue_guid),
                TimelineRecord(132, 1, 30, 3, "cue", 3, None),
            ),
            (),
            1,
            b"0123456789",
            "1" * 64,
            None,
        )

        boundaries = render_document_boundaries(doc, {cue.cue_guid: cue})

        self.assertEqual(boundaries[0]["frame"], [0] * 19)
        self.assertEqual(boundaries[1]["frame"][0], 12)
        self.assertEqual(boundaries[1]["frame"][7], 99)
        self.assertEqual(boundaries[2]["frame"], boundaries[1]["frame"])

    def test_runtime_scripted_first_event_does_not_underlay_gaps(self) -> None:
        doc = LoadedDocument(
            "script.ssfile",
            "shared_441_dictionary_timeline",
            (
                LoadedTimelineEvent(10, 0, 100, "cue", 1, ()),
                LoadedTimelineEvent(
                    20,
                    1,
                    116,
                    "cue",
                    2,
                    (LoadedAttribute(0x493, 1, 1, 12),),
                ),
                LoadedTimelineEvent(30, 2, 132, "cue", 3, ()),
            ),
            (),
        )

        self.assertEqual(render_scripted_frame(doc, 9), ZERO_FRAME)
        self.assertEqual(render_scripted_frame(doc, 10), ZERO_FRAME)
        self.assertEqual(render_scripted_frame(doc, 20)[0], 12)
        self.assertEqual(render_scripted_frame(doc, 30)[0], 12)


if __name__ == "__main__":
    unittest.main()
