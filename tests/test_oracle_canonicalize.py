"""Pure-function tests for the oracle-based MIXED-track canonicalizer.

No filesystem/capture/subprocess dependency: the resolver seam operates on
in-memory frames and a synthetic cue library.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

_MOD = Path(__file__).resolve().parents[1] / "tools" / "ssfmt" / "re" / "oracle_canonicalize.py"
_spec = importlib.util.spec_from_file_location("oracle_canonicalize", _MOD)
oc = importlib.util.module_from_spec(_spec)
sys.modules["oracle_canonicalize"] = oc  # required so @dataclass can resolve the module
_spec.loader.exec_module(oc)

Cue = oc.Cue
ZERO = list(oc.ZERO_FRAME)


def frame(**channels):
    f = [0] * oc.CHANNEL_COUNT
    for ch, val in channels.items():
        f[int(ch[2:]) - 1] = val  # "ch8" -> index 7
    return f


PATTERN = Cue("RECT", "guid-rect", {1: 62, 3: 28, 4: 176, 7: 138, 15: 169})
WHITE = Cue("WHITE", "guid-white", {1: 17, 8: 172, 9: 255})       # color cue
CYAN = Cue("CYAN", "guid-cyan", {1: 17, 8: 165, 9: 255})           # color cue
CUELIB = [PATTERN, WHITE, CYAN]
COLORCUES = [c for c in CUELIB if set(c.patch) <= {1, 8, 9}]


class TestResolveFrame(unittest.TestCase):
    def test_persist_no_change(self):
        prior = frame(ch8=172, ch9=255)
        r = oc.resolve_frame(prior, list(prior), CUELIB, COLORCUES)
        self.assertEqual(r.kind, "persist")

    def test_clear_persists_control_channels(self):
        prior = frame(ch1=62, ch3=28, ch8=172, ch9=255, ch11=200)
        observed = frame(ch8=172, ch9=255, ch11=200)  # main zeroed, control kept
        r = oc.resolve_frame(prior, observed, CUELIB, COLORCUES)
        self.assertEqual(r.kind, "clear")

    def test_single_cue(self):
        observed = oc.apply_patch(ZERO, WHITE.patch)
        r = oc.resolve_frame(ZERO, observed, CUELIB, COLORCUES)
        self.assertEqual(r.kind, "cue")
        self.assertEqual(r.pattern_guid, "guid-white")

    def test_pattern_plus_decoupled_color(self):
        # pattern (CH8=0 absent) then a color cue setting CH8/CH9
        observed = oc.apply_patch(oc.apply_patch(ZERO, PATTERN.patch), CYAN.patch)
        r = oc.resolve_frame(ZERO, observed, CUELIB, COLORCUES)
        self.assertEqual(r.kind, "cue+color")
        self.assertEqual(r.pattern_guid, "guid-rect")
        self.assertEqual(r.color_guid, "guid-cyan")

    def test_pattern_color_independent_strobe(self):
        base = oc.apply_patch(oc.apply_patch(ZERO, PATTERN.patch), CYAN.patch)
        observed = list(base)
        observed[10] = 210  # CH11 strobe set independently
        r = oc.resolve_frame(ZERO, observed, CUELIB, COLORCUES)
        self.assertEqual(r.kind, "cue+color+strobe")
        self.assertEqual(r.strobe_value, 210)

    def test_literal_fallback_is_byte_exact(self):
        observed = frame(ch2=99, ch17=42)  # no cue/composition produces this
        r = oc.resolve_frame(ZERO, observed, CUELIB, COLORCUES)
        self.assertEqual(r.kind, "literal")
        self.assertEqual(list(r.frame), observed)


class TestCanonicalizeRoundTrip(unittest.TestCase):
    def test_every_entry_renders_byte_exact(self):
        seq = [
            (1000, oc.apply_patch(ZERO, WHITE.patch)),
            (2000, oc.apply_patch(oc.apply_patch(ZERO, PATTERN.patch), CYAN.patch)),
            (3000, frame(ch8=165, ch9=255)),     # clear: main zeroed, CYAN color persists
            (4000, frame(ch2=7)),                 # literal
        ]
        pack, stats = oc.canonicalize(seq, CUELIB, COLORCUES)
        self.assertTrue(stats["byte_exact"])
        self.assertEqual(stats["total_events"], 4)
        self.assertEqual(stats["literal_fallback"], 1)
        # re-render the whole pack independently and compare to source frames
        cue_by_guid = {c.guid: c for c in CUELIB}
        prior = list(oc.ZERO_FRAME)
        for entry, (_, src_frame) in zip(pack, seq):
            res = oc.Resolution(entry["kind"], entry["pattern_guid"],
                                entry["color_guid"], entry["strobe_value"],
                                tuple(entry["frame"]))
            self.assertEqual(list(oc.render_resolution(prior, res, cue_by_guid)),
                             list(src_frame))
            prior = list(src_frame)


if __name__ == "__main__":
    unittest.main()
